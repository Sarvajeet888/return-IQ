"""PHASE 22 — image processing for return evidence.

THE PRIVACY DEFECT THIS FIXES
-----------------------------
Uploaded images are stored byte-for-byte: `store_file(key, contents, type)`
writes exactly what arrived. Whatever a customer's phone embedded is what
sits in the merchant's object storage.

A phone photograph typically carries:

    GPS latitude/longitude   the customer's home, to a few metres
    Device make and model    a fingerprint that links submissions
    Original timestamp       when the photo was actually taken
    Software, serial fields  further identifiers depending on the device

Verified in this environment: EXIF survives a JPEG round trip intact, and no
code path anywhere in ReturnIQ removes it. Pillow was not even a dependency.

Three separate problems:

**Privacy.** A merchant asking for a photo of a damaged shirt receives the
customer's home coordinates. Neither party intended that, and most merchants
do not know it is happening.

**DPDP.** Location is personal data. Collecting it without purpose or consent
is not defensible under the Digital Personal Data Protection framework, and
"we did not realise the file contained it" is not a lawful basis.

**Security.** Object storage misconfiguration is common. The difference
between leaking "photos of returned goods" and leaking "photos of returned
goods tagged with customer home addresses" is the difference between an
embarrassment and a serious incident.

WHAT ELSE THIS DOES
-------------------
The same pass prepares images for computer vision (Phase 22 proper):
consistent orientation, bounded dimensions, recorded properties. Doing it at
upload rather than at training time means the archive is usable when there is
finally a model to train — and means the orientation fix happens once instead
of on every epoch.

WHAT THIS DOES NOT DO
---------------------
It does not detect damage. That needs thousands of labelled images, which do
not exist. This is the pipeline that makes collecting them possible.
"""
from __future__ import annotations

import io
from dataclasses import dataclass
from typing import Any, Final

__all__ = [
    "ImageProcessingError",
    "ProcessedImage",
    "PRIVACY_TAGS",
    "inspect_metadata",
    "process_evidence_image",
]


class ImageProcessingError(ValueError):
    """The image could not be processed and must not be stored."""


# EXIF tags that identify a person or place. Named explicitly so the reason
# each is stripped is legible, rather than hidden behind "we drop everything".
PRIVACY_TAGS: Final[dict[int, str]] = {
    34853: "GPS block (latitude, longitude, altitude)",
    271: "Camera make",
    272: "Camera model",
    305: "Software",
    306: "Original timestamp",
    36867: "Date taken",
    36868: "Date digitised",
    42032: "Camera owner name",
    42033: "Body serial number",
    37500: "Maker note (vendor-specific, often contains identifiers)",
    270: "Image description (free text, user-supplied)",
    315: "Artist",
    33432: "Copyright",
}

# Above this, images are downscaled. A 48-megapixel phone photo of a torn
# t-shirt carries no more damage information than a 2-megapixel one, and
# storing the original multiplies storage cost and inference latency for
# nothing.
MAX_DIMENSION: Final[int] = 2048

# Below this, an image cannot show meaningful damage detail. Rejected at
# upload rather than accepted and found useless during inspection.
MIN_DIMENSION: Final[int] = 200


@dataclass(frozen=True)
class ProcessedImage:
    """A cleaned image plus what was removed and why."""

    content: bytes
    width: int
    height: int
    format: str
    original_bytes: int
    stripped_tags: list[str]
    was_resized: bool
    was_reoriented: bool

    def as_dict(self) -> dict[str, Any]:
        return {
            "width": self.width,
            "height": self.height,
            "format": self.format,
            "bytes": len(self.content),
            "original_bytes": self.original_bytes,
            "stripped_metadata": self.stripped_tags,
            "was_resized": self.was_resized,
            "was_reoriented": self.was_reoriented,
            "privacy_note": (
                f"{len(self.stripped_tags)} identifying metadata field(s) were "
                f"removed before storage."
                if self.stripped_tags else
                "No identifying metadata was present."
            ),
        }


def _no_metadata() -> dict[str, Any]:
    """The clean result.

    Returns the full key set rather than a shorter dict. Callers should not
    have to branch on which shape they got — that inconsistency is exactly
    what made the first version of this raise KeyError on a successfully
    stripped image.
    """
    return {
        "available": True,
        "has_metadata": False,
        "tags": [],
        "has_location": False,
        "total_exif_fields": 0,
    }


def inspect_metadata(content: bytes) -> dict[str, Any]:
    """Report what identifying metadata an image carries, without modifying it.

    Exists so the privacy problem can be *demonstrated* on a real upload
    rather than asserted — a merchant who can see the GPS coordinates in their
    own evidence archive understands the issue immediately.
    """
    try:
        from PIL import Image
    except ImportError:
        return {"available": False, "reason": "Pillow is not installed"}

    try:
        image = Image.open(io.BytesIO(content))
        exif = image.getexif()
    except Exception:  # noqa: BLE001 -- unreadable metadata is not an error here
        return _no_metadata()

    if not exif:
        return _no_metadata()

    found = [
        {"tag": tag_id, "name": name}
        for tag_id, name in PRIVACY_TAGS.items()
        if tag_id in exif
    ]
    return {
        "available": True,
        "has_metadata": bool(found),
        "tags": found,
        "has_location": 34853 in exif,
        "total_exif_fields": len(exif),
    }


def process_evidence_image(
    content: bytes,
    *,
    max_dimension: int = MAX_DIMENSION,
) -> ProcessedImage:
    """Strip identifying metadata and normalise for storage and future CV.

    Re-encodes rather than editing in place. Selective EXIF editing leaves
    vendor-specific segments (maker notes, thumbnails with their own embedded
    EXIF) intact, and a thumbnail carrying the GPS block is exactly as
    identifying as the full image. Re-encoding from decoded pixels guarantees
    nothing survives that we did not deliberately write.

    The cost is one lossy generation on JPEG. That is an acceptable trade for
    a guarantee, and the alternative — a "mostly stripped" image — is the kind
    of partial protection that reads as protection and is not.
    """
    try:
        from PIL import Image, ImageOps
    except ImportError as exc:
        raise ImageProcessingError(
            "Pillow is required to process evidence images. Without it, "
            "uploads would be stored with identifying metadata intact."
        ) from exc

    original_bytes = len(content)
    inspection = inspect_metadata(content)
    stripped = [t["name"] for t in inspection.get("tags", [])]

    try:
        image = Image.open(io.BytesIO(content))
        image.load()
    except Exception as exc:  # noqa: BLE001
        raise ImageProcessingError(
            "This file could not be read as an image. It may be corrupted."
        ) from exc

    image_format = (image.format or "JPEG").upper()

    if min(image.size) < MIN_DIMENSION:
        raise ImageProcessingError(
            f"This image is {image.width}x{image.height}. Evidence photos "
            f"need to be at least {MIN_DIMENSION}px on the shorter side to "
            f"show damage detail."
        )

    # Apply the EXIF orientation flag, then discard it. Phones record
    # "rotate 90 degrees" as metadata rather than rotating pixels; strip the
    # metadata without applying it and every portrait photo is stored
    # sideways -- which breaks human review and would teach a future CV model
    # that damage appears at arbitrary rotations.
    was_reoriented = image.getexif().get(274, 1) not in (1, None)
    image = ImageOps.exif_transpose(image) or image

    was_resized = max(image.size) > max_dimension
    if was_resized:
        image.thumbnail((max_dimension, max_dimension), Image.LANCZOS)

    # RGBA/P cannot be saved as JPEG, and a transparent background flattened
    # to black would look like damage.
    if image_format in {"JPEG", "JPG"} and image.mode not in ("RGB", "L"):
        image = image.convert("RGB")

    output = io.BytesIO()
    save_format = "JPEG" if image_format in {"JPEG", "JPG"} else image_format
    save_kwargs: dict[str, Any] = {}
    if save_format == "JPEG":
        # 88 keeps damage detail (scratches, tears, hairline cracks) while
        # dropping file size substantially. Below ~80, compression artefacts
        # start to resemble the thing being detected.
        save_kwargs = {"quality": 88, "optimize": True}

    # No `exif=` argument. Nothing carries over.
    image.save(output, save_format, **save_kwargs)

    return ProcessedImage(
        content=output.getvalue(),
        width=image.width,
        height=image.height,
        format=save_format,
        original_bytes=original_bytes,
        stripped_tags=stripped,
        was_resized=was_resized,
        was_reoriented=was_reoriented,
    )
