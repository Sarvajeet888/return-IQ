# Open Source License Audit — ReturnIQ Enterprise

**Audit Date:** 1 August 2025
**Scope:** Python backend dependencies + JavaScript frontend dependencies

---

## Summary

| Finding | Result |
|---|---|
| License conflicts | ✅ None found |
| Copyleft (GPL) licenses that would require source disclosure | ✅ None |
| Attribution requirements | ✅ Listed in THIRD_PARTY_NOTICES.md |
| ReturnIQ project LICENSE file present | ❌ Must be created before release |

---

## Backend — Python Dependencies

| Package | Version | License | Notes |
|---|---|---|---|
| fastapi | 0.115.6 | MIT | ✅ Permissive |
| uvicorn | 0.34.0 | BSD 3-Clause | ✅ Permissive |
| pydantic | 2.10.4 | MIT | ✅ Permissive |
| pydantic-settings | 2.7.1 | MIT | ✅ Permissive |
| email-validator | 2.2.0 | CC0 1.0 / MIT | ✅ Permissive |
| python-dotenv | 1.2.2 | BSD 3-Clause | ✅ Permissive |
| python-jose[cryptography] | 3.4.0 | MIT | ✅ Permissive |
| bcrypt | ≥4.0.0 | Apache 2.0 | ✅ Permissive |
| python-multipart | 0.0.32 | Apache 2.0 | ✅ Permissive |
| python-magic | 0.4.27 | MIT | ✅ Permissive |
| sqlalchemy | 2.0.36 | MIT | ✅ Permissive |
| alembic | 1.14.0 | MIT | ✅ Permissive |
| psycopg2-binary | 2.9.10 | LGPL 3.0 | ⚠️ LGPL — dynamic linking via binary wheel is acceptable; do not statically link |
| slowapi | 0.1.9 | MIT | ✅ Permissive |
| redis | 5.2.1 | MIT | ✅ Permissive |
| pytest | 8.3.4 | MIT | ✅ Dev-only |
| pytest-cov | 6.0.0 | MIT | ✅ Dev-only |
| httpx | 0.28.1 | BSD 3-Clause | ✅ Dev-only |
| xgboost | 2.1.3 | Apache 2.0 | ✅ Permissive |
| pandas | 2.2.3 | BSD 3-Clause | ✅ Permissive |
| numpy | ≥1.26.0 | BSD 3-Clause | ✅ Permissive |
| joblib | 1.4.2 | BSD 3-Clause | ✅ Permissive |

**psycopg2 note:** psycopg2-binary is LGPL licensed. Using it as a dynamically-linked
library (the default in all pip install scenarios) satisfies LGPL requirements. No
source code disclosure obligation arises from this use.

---

## Frontend — JavaScript Dependencies

| Package | Version | License | Notes |
|---|---|---|---|
| react | 18.3.1 | MIT | ✅ Permissive |
| react-dom | 18.3.1 | MIT | ✅ Permissive |
| react-router-dom | 7.18.1 | MIT | ✅ Permissive |
| axios | 1.18.1 | MIT | ✅ Permissive |
| lucide-react | 1.25.0 | ISC | ✅ Permissive |
| recharts | 3.10.0 | MIT | ✅ Permissive |
| vite | 6.3.5 | MIT | ✅ Dev-only |
| @vitejs/plugin-react | 4.3.4 | MIT | ✅ Dev-only |

---

## Icons

**Lucide Icons** (via lucide-react) — ISC License. Icons are provided as React
components. No separate attribution file is required for ISC; however, attribution is
recommended practice and is included in `THIRD_PARTY_NOTICES.md`.

No custom icon fonts, images, or videos are included in this codebase.

---

## Fonts

No custom fonts are loaded. The frontend uses the system font stack defined in
`index.css`. No third-party font services (Google Fonts, Adobe Fonts) are called.

---

## Action Required

1. **Create a `LICENSE` file** in the project root before any public release. Choose
   one of:
   - MIT (recommended for an open-source release)
   - Proprietary/All Rights Reserved (if this is a closed commercial product)
   - A commercial license with source-available components

2. **Create `THIRD_PARTY_NOTICES.md`** — see `docs/compliance/THIRD_PARTY_NOTICES.md`.

---

## License Compatibility Assessment

All runtime dependencies use MIT, BSD, Apache 2.0, or CC0 licenses. These are all
permissive and compatible with any license choice for the ReturnIQ codebase itself,
including proprietary use. The LGPL psycopg2 does not restrict the license choice for
the application as long as it is dynamically linked (which it is).

**Conclusion: No license conflicts. No copyleft obligations.**
