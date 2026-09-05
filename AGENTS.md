# AGENTS.md — common-auth

Shared Firebase authentication and Gemini usage tracking package for Cloud Run apps.

## Project Overview

- **Package:** `common-auth` — framework-agnostic core + thin Flask/FastAPI adapters
- **Python:** >=3.10, PEP 484 type hints required
- **GCP Project:** `gen-lang-client-0026629090`, Region: `me-west1`
- **Repo:** public (`github.com/jshames-doc/common-auth`) — no secrets stored here

## Secrets

Three secrets live in Google Secret Manager and are mapped to env vars on every Cloud Run service:

| Secret name | Env var | Purpose |
|---|---|---|
| `firebase-service-account` | `FIREBASE_CREDENTIALS_JSON` | Firebase Admin SDK credentials |
| `firebase-api-key` | `FIREBASE_API_KEY` | Firebase Web API key (served to clients via `/auth/config`) |
| `gemini-api-key` | `GEMINI_API_KEY` | Gemini API key |

**Never commit any of these to source files.** Use `--update-secrets` in cloudbuild.yaml / deploy.bat, not `--update-env-vars` with a plaintext value.

## Apps in Scope

| App | `APP_ID` | Cloud Run service |
|---|---|---|
| Medical Document Summarizer | `medical_summarizer` | `medical-summarizer` |
| Clinical Dictation | `clinical_dictation` | `clinical-dictation` |
| AI Neuro Exam | `neuro_exam` | `neuro-exam` |
| Rehab Consultant | `rehab_platform` | `rehab-platform` |
| Orthotics Assistant | `orthotics_assistant` | `brace-and-shoe` |
| Auth Admin | `auth_admin` | `auth-admin` |

## Coding Conventions

- Functions <= 25 lines where practical (Single Responsibility Principle)
- pytest for all tests; add a unit test per new function in `tests/`
- `python -m pytest tests/ -v` to run the suite
- FastAPI union return types need `response_model=None` on the route decorator
- `python:3.12-slim` has no `git` — Dockerfiles must `apt-get install git` before `pip install` if requirements include `git+https://...`

## Local Dev

- Set `FIREBASE_CREDENTIALS_PATH` to a local (gitignored) service account JSON file
- Check for stale processes on port 8000 before starting backend: `netstat -ano | findstr ":8000"`

## Key Files

- `AUTH_IMPLEMENTATION_PLAN.md` — full phased implementation plan (715 lines)
- `common_auth/` — package source
- `tests/` — pytest suite
