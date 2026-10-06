"""
Model versioning registry.

Problem this solves: right now there is exactly one copy of the model on
disk (ml/artifacts/model.joblib), so retraining means overwriting the only
copy that's currently serving traffic - no way to compare versions, no way
to roll back a bad retrain, and model_metadata.json for the *old* model
gets silently replaced with no history.

This introduces a versioned layout:

    ml/artifacts/
        registry.json              <- points at the currently "active" version
        v1.0.0/
            model.joblib
            model_metadata.json
        v1.1.0/
            model.joblib
            model_metadata.json

registry.json is the single source of truth for "which version is live".
Promoting a new version is an atomic write to registry.json - the old
version's files are untouched on disk, so rollback is instant (just point
the registry back at the old version, no retraining needed).

This module only manages the registry + file layout. It does not change
ml/predict.py's loading behaviour by itself - see MIGRATION NOTE at the
bottom for how to wire ReverseLogisticsPredictor to use this once you're
ready to cut over.
"""
from __future__ import annotations

import json
import shutil
from datetime import UTC, datetime
from pathlib import Path

ARTIFACTS_DIR = Path(__file__).resolve().parent / "artifacts"
REGISTRY_PATH = ARTIFACTS_DIR / "registry.json"


class ModelRegistryError(Exception):
    pass


def _read_registry() -> dict:
    if not REGISTRY_PATH.exists():
        return {"active_version": None, "versions": {}}
    with open(REGISTRY_PATH) as f:
        return json.load(f)


def _write_registry(data: dict) -> None:
    # Write to a temp file then rename, so a crash mid-write can never leave
    # registry.json half-written / corrupt (which would break every
    # subsequent server boot, since predict.py would depend on this).
    tmp = REGISTRY_PATH.with_suffix(".json.tmp")
    with open(tmp, "w") as f:
        json.dump(data, f, indent=2)
    tmp.replace(REGISTRY_PATH)


def register_version(version: str, model_path: Path, metadata_path: Path, *, activate: bool = False) -> dict:
    """
    Copy a trained model + its metadata into the versioned artifact layout
    and record it in the registry. Does NOT overwrite any existing version's
    files. Pass activate=True to also make this the live version
    immediately; otherwise it's registered but not yet serving traffic
    (useful for "stage it, then promote after a manual check" workflows).
    """
    if not model_path.exists():
        raise ModelRegistryError(f"model file not found: {model_path}")
    if not metadata_path.exists():
        raise ModelRegistryError(f"metadata file not found: {metadata_path}")

    version_dir = ARTIFACTS_DIR / version
    if version_dir.exists():
        raise ModelRegistryError(
            f"version '{version}' already registered - use a new version "
            f"string, never overwrite a registered version in place"
        )
    version_dir.mkdir(parents=True)
    shutil.copy2(model_path, version_dir / "model.joblib")
    shutil.copy2(metadata_path, version_dir / "model_metadata.json")

    registry = _read_registry()
    registry["versions"][version] = {
        "registered_at": datetime.now(UTC).isoformat(),
        "path": str(version_dir.relative_to(ARTIFACTS_DIR)),
    }
    if activate or registry["active_version"] is None:
        registry["active_version"] = version
    _write_registry(registry)
    return registry


def activate_version(version: str) -> dict:
    """Point the registry at an already-registered version. Instant rollback lever."""
    registry = _read_registry()
    if version not in registry["versions"]:
        raise ModelRegistryError(
            f"version '{version}' is not registered. Known versions: "
            f"{list(registry['versions'].keys())}"
        )
    registry["active_version"] = version
    _write_registry(registry)
    return registry


def get_active_version_paths() -> tuple[Path, Path]:
    """Returns (model_path, metadata_path) for the currently active version."""
    registry = _read_registry()
    active = registry.get("active_version")
    if active is None:
        raise ModelRegistryError("no active model version registered")
    version_dir = ARTIFACTS_DIR / registry["versions"][active]["path"]
    return version_dir / "model.joblib", version_dir / "model_metadata.json"


def list_versions() -> dict:
    return _read_registry()


# ─────────────────────────────────────────────────────────────────────────────
# MIGRATION NOTE (not applied automatically - this is a deliberate decision,
# see the Phase 4 writeup for why):
#
# The currently-deployed ml/artifacts/model.joblib was NOT auto-migrated
# into this versioned layout by this module. Doing that silently would mean
# a background script moving the exact file `predict.py` depends on, with
# no way to verify nothing broke before it happened. To adopt versioning
# for real:
#
#   1. python -c "from ml.model_registry import register_version; from pathlib import Path; \
#        register_version('v1.0.0', Path('ml/artifacts/model.joblib'), \
#        Path('ml/artifacts/model_metadata.json'), activate=True)"
#   2. Update ml/predict.py's MODEL_PATH / METADATA_PATH to call
#      get_active_version_paths() instead of the hardcoded artifacts/ paths.
#   3. Run the full test suite before deploying that change.
#
# Until step 2 is done, predict.py keeps loading the flat file exactly as
# it does today - nothing about current production behaviour changes just
# by this file existing.
