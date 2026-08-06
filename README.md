# common-auth

Shared Firebase authentication and Gemini usage tracking for Cloud Run apps.

## Install

```bash
pip install git+https://github.com/jshames-doc/common-auth.git@v0.1.0
```

## Usage

```python
from common_auth import verify_firebase_token, is_active, can_access_app

# Verify a Firebase ID token from the Authorization header
identity = verify_firebase_token(bearer_token)
uid = identity["uid"]

# Check user status and app permission
if not is_active(uid):
    raise Exception("User is disabled")
if not can_access_app(uid, "medical_summarizer"):
    raise Exception("Access denied")
```

## Environment Variables

- `APP_ID` — the identifier for the current app (e.g. `medical_summarizer`)
- `FIREBASE_CREDENTIALS_JSON` — service account JSON as a string (Cloud Run)
- `FIREBASE_CREDENTIALS_PATH` — path to a service account JSON file (local dev)
- `FIREBASE_PROJECT_ID` — GCP project ID (defaults to `gen-lang-client-0026629090`)

## Tests

```bash
pip install -e ".[dev]"
pytest tests/ -v
```
