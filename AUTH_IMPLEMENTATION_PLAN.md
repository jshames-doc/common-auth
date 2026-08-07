# Shared Firebase Authentication — Implementation Plan (Agent Handoff)

A phased plan to replace hard-coded PINs with one Firebase-backed identity system shared across all of Jeff's Cloud Run apps, without rewriting the apps. Built for a coding agent to execute incrementally, starting with the Medical Document Summarizer as the pilot.

---

## What You Are Building

A single authentication and usage-tracking layer that every Cloud Run app imports. Users sign in once with email/password through Firebase Auth; each app verifies the Firebase ID token, checks the user's status and app permission in Firestore, and logs Gemini token usage to a shared `usage_logs` collection. An admin app manages users, permissions, and a usage dashboard.

**Design goals (from the source plan):**
- One auth system shared by all apps — no per-app PINs.
- No app rewrites; only auth middleware + a shared package are added.
- No Google OAuth initially (email/password only).
- Lightweight access control, not enterprise IAM.
- Gemini cost monitoring via a shared usage log.

**Hard constraints:**
- Do not change Docker workflows, Cloud Run deployment mechanics, or Gemini integration logic.
- Do not commit secrets. Use Google Secret Manager in production.
- Keep each app's existing test suite passing.

---

## Tech Stack & Constraints

- **Identity:** Firebase Authentication (email/password provider only — do NOT enable Google OAuth in Phase 1).
- **Database:** Firestore (Native mode) in the same GCP project.
- **Backend SDK:** `firebase-admin` Python SDK.
- **Shared package:** `common-auth` — a small Python package, framework-agnostic core + thin Flask and FastAPI adapters.
- **Apps:** mix of Flask and FastAPI, all on Cloud Run, region `me-west1`, project `gen-lang-client-0026629090`.
- **Secrets:** Firebase service account JSON and Gemini API keys move to Google Secret Manager (Phase 8).
- **Python:** PEP 484 type hints on all new code. Functions ≤ 25 lines where practical. Single Responsibility Principle.
- **Testing:** pytest for Python packages and FastAPI/Flask backends. Add a unit test per new function in `common-auth/tests/`. Do not break existing app test suites.

---

## Apps In Scope

| # | App name | Stack | Cloud Run service | Repo path | Current auth | Gemini model |
|---|----------|-------|-------------------|-----------|--------------|--------------|
| 1 | Medical Document Summarizer (pilot) | FastAPI | `medical-summarizer` | `C:\Users\jsham\CascadeProjects\Medical Document Summarizer` | 4-digit `APP_PIN` + signed session cookie | `gemini-3.1-flash-lite` |
| 2 | Clinical Dictation | FastAPI | `clinical-dictation` | `C:\Users\jsham\CascadeProjects\Clinical Dictation` | None (open) | `gemini-3.1-flash-lite` |
| 3 | AI Neuro Exam | Flask | `neuro-exam` | `C:\Users\jsham\Documents\antigravity\Neuro Exam` | None (open) | `gemini-3-flash` (fallback when no key) |
| 4 | Rehab Consultant | Flask | `rehab-platform` | `C:\Users\jsham\Documents\antigravity\rehab-platform` | None (open) | `gemini-3.1-flash-lite` |
| 5 | Orthotics Assistant | FastAPI | `brace-and-shoe` (verify in `deploy.bat`) | `C:\Users\jsham\CascadeProjects\Brace and Shoe Assistant` | None (open) | `gemini-3.1-flash-lite` |
| — | Admin app (NEW) | FastAPI | `auth-admin` | new repo: `C:\Users\jsham\CascadeProjects\Auth Admin` | Firebase Auth (admin role required) | none |

> **Note on app identifiers:** each app must declare a stable `APP_ID` string (see schema below). Use these exact values in Firestore `app_access` documents and `usage_logs.app`.

| App | `APP_ID` |
|-----|----------|
| Medical Document Summarizer | `medical_summarizer` |
| Clinical Dictation | `clinical_dictation` |
| AI Neuro Exam | `neuro_exam` |
| Rehab Consultant | `rehab_platform` |
| Orthotics Assistant | `orthotics_assistant` |

---

## Package Layout (Recommended)

**Decision: separate private git repo, installed via pip git URL.**

Rationale: 5 apps across two parent folders, mix of Flask/FastAPI, all on Cloud Run. A single source of truth avoids drift; a pip git dependency is the smallest change to each app's `requirements.txt` and works with both Docker and buildpack deploys. Vendoring a copy would cause drift across 5 services; a monorepo would force restructuring unrelated apps.

```
common-auth/                      # NEW private git repo
  common_auth/
    __init__.py
    firebase_init.py              # Initialize Firebase Admin SDK + Firestore client (singleton)
    verify_token.py               # verify_firebase_token(id_token) -> {uid, email}
    users.py                      # get_user / is_active / get_limits
    permissions.py                # can_access_app(uid, app_id) -> bool
    usage.py                      # log_gemini_usage / check_usage_limit
    config.py                     # Reads APP_ID, Firebase creds path/env, limits
    errors.py                     # AuthError, PermissionDeniedError, QuotaExceededError, UsageLimitExceededError
    adapters/
      __init__.py
      fastapi_auth.py             # require_user / current_user dependencies
      flask_auth.py               # @login_required decorator + request.user
  tests/
    test_verify_token.py
    test_users.py
    test_permissions.py
    test_usage.py
    test_fastapi_adapter.py
    test_flask_adapter.py
  pyproject.toml                  # name: common-auth, deps: firebase-admin, google-cloud-firestore
  README.md
```

**Install in each app** (add to `requirements.txt`):
```
git+https://github.com/jshames-doc/common-auth.git@v0.1.0
```

Tag releases (`v0.1.0`, `v0.2.0`, ...) so apps pin a version and don't silently pull breaking changes.

---

## File Structure (Shared Package Responsibilities)

### `firebase_init.py`
- Initialize `firebase_admin.initialize_app(credential, {'projectId': PROJECT_ID})` exactly once per process (guard with a module-level flag).
- Read credentials from `FIREBASE_CREDENTIALS_JSON` (env var containing the service account JSON) — preferred for Cloud Run — or `FIREBASE_CREDENTIALS_PATH` (file path) for local dev.
- Expose `get_firestore()` returning a cached `firestore.Client`.

### `verify_token.py`
```python
def verify_firebase_token(id_token: str) -> dict[str, str]:
    """Verify a Firebase ID token. Returns {'uid': ..., 'email': ...}.
    Raises AuthError if the token is invalid, expired, or revoked."""
```
Uses `firebase_admin.auth.verify_id_token(id_token, check_revoked=True)`.

### `users.py`
```python
def get_user(uid: str) -> dict | None:        # Firestore users/{uid} or None
def is_active(uid: str) -> bool               # False if missing or active != True
def get_limits(uid: str) -> dict              # daily_token_limit etc. (defaults if missing)
```

### `permissions.py`
```python
def can_access_app(uid: str, app_id: str) -> bool:
    """True if a user with role 'admin' OR an app_access doc {uid, app_id, allowed: True} exists."""
```
Admin role bypasses per-app checks (admin = all apps).

### `usage.py`
```python
def log_gemini_usage(uid: str, app_id: str, model: str,
                     input_tokens: int, output_tokens: int,
                     success: bool, error: str | None = None) -> None:
    """Append a doc to usage_logs with server timestamp."""

def check_usage_limit(uid: str, app_id: str) -> bool:
    """True if the user is under their daily_token_limit for today (UTC).
    Sums usage_logs for today for this uid; compares to users/{uid}.daily_token_limit."""
```

### `adapters/fastapi_auth.py`
```python
def require_user(app_id: str):
    """FastAPI dependency factory. Reads `Authorization: Bearer <id_token>`,
    verifies token, checks is_active + can_access_app(app_id).
    Returns a UserContext {uid, email, app_id}. Raises HTTPException(401/403)."""

current_user = require_user  # alias for `Depends(require_user(APP_ID))` usage
```

### `adapters/flask_auth.py`
```python
def login_required(app_id: str):
    """Decorator factory. Verifies Firebase token from Authorization header,
    checks status + permission, attaches request.user, else returns 401/403 JSON."""
```

---

## Data Schemas (Firestore — exact)

### `users/{uid}`
```json
{
  "uid": "firebase_uid",
  "email": "jeff@example.com",
  "display_name": "Jeff",
  "active": true,
  "role": "admin",
  "created_at": "2026-08-06T12:00:00Z",
  "daily_token_limit": 100000
}
```
- `role`: `"admin"` (all apps) | `"user"` (per-app checks apply).
- `active`: `false` disables login everywhere.
- `daily_token_limit`: total tokens/day across all apps. Default `100000` if field missing.

### `app_access/{uid}_{app_id}`
```json
{
  "uid": "firebase_uid",
  "app": "medical_summarizer",
  "allowed": true
}
```
- Document ID = `{uid}_{app_id}` for uniqueness.
- Only consulted when `role != "admin"`.

### `usage_logs/{auto_id}`
```json
{
  "uid": "firebase_uid",
  "app": "medical_summarizer",
  "timestamp": "2026-08-06T12:00:00Z",
  "model": "gemini-3.1-flash-lite",
  "input_tokens": 2500,
  "output_tokens": 900,
  "total_tokens": 3400,
  "estimated_cost_usd": 0.0001,
  "success": true,
  "error": null
}
```
- `timestamp`: server timestamp (`firestore.SERVER_TIMESTAMP`).
- `total_tokens` = `input_tokens + output_tokens` (store for easy aggregation).
- `estimated_cost_usd`: computed from a per-model cost table in `usage.py` (see below). Keep it simple; update the table as pricing changes.

**Cost table (in `usage.py`), per 1K tokens — update with real pricing:**
```python
COST_PER_1K = {
    "gemini-3.1-flash-lite": {"input": 0.000075, "output": 0.0003},
    "gemini-3-flash":        {"input": 0.0001,   "output": 0.0004},
    # default fallback:
    "_default":              {"input": 0.0001,   "output": 0.0004},
}
```

---

## Core Logic & Rules

### Auth flow per protected request (all apps)
```
Request arrives
  → read Authorization: Bearer <firebase_id_token>
  → verify_firebase_token(token)  → {uid, email}        (401 if invalid)
  → is_active(uid)                                         (403 if inactive)
  → can_access_app(uid, APP_ID)                            (403 if denied)
  → [if endpoint calls Gemini] check_usage_limit(uid, APP_ID)  (429 if over quota)
  → handle request
  → [if Gemini was called] log_gemini_usage(uid, APP_ID, model, in, out, success)
```

### Frontend login flow (replaces PIN modal)
```
Login page (email + password)
  → Firebase Auth client SDK: signInWithEmailAndPassword()
  → receive Firebase ID token
  → store token in memory (NOT localStorage long-term) — use sessionStorage or in-memory var
  → attach `Authorization: Bearer <token>` to every API call
  → on 401: token expired → re-authenticate silently or show login
```
**Token refresh:** use Firebase client SDK's `onAuthStateChanged` / `getIdToken(forcingRefresh=true)` to get fresh ID tokens (they expire after 1 hour). Do NOT cache a token for longer than 1 hour.

### App identifier rule
- Every app sets `APP_ID` via env var (e.g. `APP_ID=medical_summarizer`).
- The adapter reads it at startup. Do not hard-code the app_id in routes.

### Admin role rule
- `role == "admin"` → `can_access_app` always returns `True` for every `app_id`.
- Admin app additionally requires `role == "admin"`.

### Quota rule
- `check_usage_limit` sums `usage_logs` where `uid == uid` and `timestamp >= start_of_today_utc`, compares `total_tokens` sum to `users/{uid}.daily_token_limit`.
- Over quota → `UsageLimitExceededError` → HTTP 429.
- Quota is per-user across all apps (matches the source plan's `daily_token_limit` field).

---

## Phase 1 — Establish the shared identity system

**Goal:** Firebase Auth + Firestore ready; first user can authenticate.

1. Enable Firebase on the existing GCP project `gen-lang-client-0026629090` (no new project).
2. Enable **Firebase Authentication** with the **Email/password** provider. Do NOT enable Google OAuth.
3. Enable **Firestore** (Native mode) in region `me-west1` (or nearest available).
4. Create the three collections above by inserting the first documents:
   - `users/{uid}` for Jeff: `role: "admin"`, `active: true`, `daily_token_limit: 100000`.
   - `app_access/{uid}_medical_summarizer` with `allowed: true` (not strictly needed for admin, but documents intent).
5. Create a Firebase service account key (JSON). Store it in **Google Secret Manager** as `firebase-service-account` (Phase 8 makes this mandatory; do it now to avoid rework).
6. Create the initial Firebase Auth user manually (Jeff, `jeff@example.com`, a real password).

**Deliverable:** `firebase-admin` can verify a token issued to Jeff; Firestore reads return his user doc.

**Acceptance check (write as `common-auth/tests/test_phase1_smoke.py`, skip if no creds):**
```python
# Manual: sign in via Firebase client SDK in a browser, copy the ID token,
# then run: python -m pytest tests/test_phase1_smoke.py -k smoke --token=<id_token>
# Verifies: verify_firebase_token(token) returns Jeff's uid/email,
# is_active(uid) is True, can_access_app(uid, "medical_summarizer") is True.
```

---

## Phase 2 — Create the shared `common-auth` package

**Goal:** framework-agnostic package with token verification, user/permission/usage helpers, and unit tests.

1. Create the `common-auth` repo with the file structure above.
2. `pyproject.toml`: name `common-auth`, deps `firebase-admin>=6`, `google-cloud-firestore>=2`.
3. Implement `firebase_init.py`, `verify_token.py`, `users.py`, `permissions.py`, `usage.py`, `errors.py`, `config.py`.
4. Write unit tests in `tests/` using mocked Firestore clients (do not require live Firebase in CI). Cover:
   - `verify_firebase_token`: valid token, expired token, revoked token, malformed token.
   - `is_active`: active user, inactive user, missing user.
   - `can_access_app`: admin bypass, allowed user, denied user, missing doc.
   - `check_usage_limit`: under limit, at limit, over limit, no usage yet.
   - `log_gemini_usage`: writes correct fields + total + estimated cost.
5. Tag `v0.1.0` and push to the private GitHub repo.

**Deliverable:** `pip install git+...@v0.1.0` works; `pytest` passes in `common-auth`.

---

## Phase 3 — Build framework adapters

**Goal:** thin Flask and FastAPI wrappers so apps add ≤ 5 lines.

### FastAPI adapter (`adapters/fastapi_auth.py`)
- `require_user(app_id: str)` returns a dependency that does the full auth flow and returns a `UserContext`.
- Usage in an app:
```python
from common_auth.adapters.fastapi_auth import require_user
user = Depends(require_user(os.environ["APP_ID"]))
@app.post("/extract")
async def extract(payload: ExtractRequest, user: UserContext):
    ...
```

### Flask adapter (`adapters/flask_auth.py`)
- `login_required(app_id: str)` decorator that runs the auth flow, sets `flask.request.user`, or returns 401/403 JSON.
- Usage:
```python
from common_auth.adapters.flask_auth import login_required
@app.route("/api/interpret", methods=["POST"])
@login_required(os.environ["APP_ID"])
def interpret():
    uid = request.user.uid
    ...
```

- Add adapter tests (`test_fastapi_adapter.py`, `test_flask_adapter.py`) using mocked `verify_token` / Firestore.
- Tag `v0.2.0`.

**Deliverable:** both adapters pass their tests; a sample FastAPI and Flask route can be protected with one line.

---

## Phase 4 — Convert the pilot: Medical Document Summarizer

**Goal:** replace the 4-digit PIN with Firebase Auth on `medical-summarizer`. This establishes the exact pattern copied to every other app.

### Backend changes (`backend/`)
1. Add `common-auth` to `backend/requirements.txt` (pinned git tag).
2. Add `firebase-admin` is already a transitive dep — no extra line needed.
3. Set `APP_ID=medical_summarizer` in `cloudbuild.yaml` `--update-env-vars`.
4. **Delete** `backend/auth.py` (PIN logic) and its tests `backend/tests/test_auth.py`. Remove the `APP_PIN` / `APP_SESSION_SECRET` env vars and Secret Manager references from `cloudbuild.yaml`.
5. In `backend/main.py`:
   - Remove `/auth/session` and `/auth/unlock` endpoints.
   - Remove `is_valid_session` / `verify_pin` / `set_session_cookie` imports.
   - Protect `/extract` with `Depends(require_user(os.environ["APP_ID"]))` instead of the session cookie check.
   - Keep `/health` and `/build` public.
6. Add a public `/auth/config` endpoint returning the Firebase web config (apiKey, authDomain, projectId) so the frontend can initialize Firebase client SDK without hard-coding. (Or load it from env vars set at deploy.)

### Frontend changes (`frontend/`)
1. Add Firebase client SDK via CDN (or npm if a build step exists — this app has none, so CDN):
   - `firebase/app`, `firebase/auth`.
2. Replace the PIN modal (`#auth-modal` in `index.html`, `submitAccessPin` / `checkAccess` in `app.js`) with an email/password login form.
3. On login: `firebase.auth().signInWithEmailAndPassword(email, password)` → `user.getIdToken()` → store token in memory (module-scoped variable in `api.js`).
4. In `frontend/api.js`: add `Authorization: Bearer <token>` to every fetch to `/extract`. On 401, re-fetch a fresh token via `user.getIdToken(true)` and retry once.
5. Use `onAuthStateChanged` to drive the login-vs-app UI state (replaces the PIN modal show/hide logic).

### Tests
- Update `backend/tests/conftest.py`: remove `APP_PIN` / `APP_SESSION_SECRET` setup; add a fixture that monkeypatches `common_auth.verify_token.verify_firebase_token` to return a fake `{uid, email}`.
- Update `backend/tests/test_extract.py` to pass the fake `Authorization` header instead of a session cookie.
- Delete `backend/tests/test_auth.py`.
- Run `python -m pytest backend/tests/ -v` — all must pass.

### Deploy
- Add `APP_ID=medical_summarizer` and `FIREBASE_CREDENTIALS_JSON` (from Secret Manager) to `cloudbuild.yaml` `--update-env-vars` / `--update-secrets`.
- Remove the `APP_PIN` / `APP_SESSION_SECRET` secret mappings.
- Push to `main` → Cloud Build deploys.

**Deliverable:** Jeff logs in with email/password on the deployed app, `/extract` works, no PIN is involved.

**Acceptance checks:**
- [ ] `pytest backend/tests/ -v` passes.
- [ ] Deployed app shows a login form, not a PIN modal.
- [ ] `/extract` returns 401 without a valid Firebase token.
- [ ] `/extract` returns 200 with a valid token for an allowed user.
- [ ] A disabled user (`active: false`) gets 403.
- [ ] A non-admin user without `app_access` for `medical_summarizer` gets 403.

---

## Phase 5 — Add Gemini usage tracking

**Goal:** every Gemini call is logged and quota-enforced.

### Pattern (apply to every app that calls Gemini)
Wrap each Gemini call site. The exact integration point varies per app:

| App | Gemini call site | Notes |
|-----|------------------|-------|
| Medical Document Summarizer | `backend/gemini_client.py: extract()` | Already returns a response with `usage_metadata` available on the SDK response. |
| Clinical Dictation | `backend/gemini.py: format_note()` / `transcribe_audio()` | Already extracts `usage_metadata` via `_extract_usage()`. |
| AI Neuro Exam | `backend/gemini_client.py: GeminiClient.interpret()` | Has a fallback when no key; only log on real calls. |
| Rehab Consultant | `server_hebrew.py` Gemini call | Single Flask route. |
| Orthotics Assistant | `backend/app/ai/gemini_client.py` | Optional AI layer; only log when AI is actually called. |

### Implementation rule (same in every app)
```python
# BEFORE calling Gemini:
if not check_usage_limit(user.uid, APP_ID):
    raise UsageLimitExceededError()  # → 429

# AFTER the Gemini call succeeds or fails:
log_gemini_usage(
    uid=user.uid,
    app_id=APP_ID,
    model=model_name,
    input_tokens=usage.prompt_token_count,
    output_tokens=usage.candidates_token_count,
    success=not error,
    error=str(error) if error else None,
)
```
- Read token counts from the SDK's `response.usage_metadata` (`prompt_token_count`, `candidates_token_count`, `total_token_count`).
- Log on **both** success and failure (with `success=false` and a sanitized error string — never log prompts, responses, or keys).
- `estimated_cost_usd` is computed inside `log_gemini_usage` from the cost table.

### Tests
- Add a test per app that mocks the Gemini response's `usage_metadata` and asserts a `usage_logs` doc was written (mock Firestore).
- Add a test that `check_usage_limit` returning `False` produces a 429 before any Gemini call.

**Deliverable:** the admin dashboard (Phase 6) can show real per-app token usage and cost.

---

## Phase 6 — Create the admin app

**Goal:** a new Cloud Run service `auth-admin` for user/permission/usage management.

### New repo: `C:\Users\jsham\CascadeProjects\Auth Admin`
- FastAPI backend + vanilla HTML/JS frontend (match the style of the other apps).
- Uses `common-auth` with `APP_ID=auth_admin` and an extra guard: every route requires `role == "admin"`.

### Backend endpoints
```
GET  /admin/users              → list users (uid, email, display_name, active, role)
POST /admin/users              → create user (auto-generates temp password, returns reset_link)
PATCH /admin/users/{uid}       → update active / role / daily_token_limit / display_name
DELETE /admin/users/{uid}      → delete user (Firebase Auth + Firestore + app_access cleanup; blocks self-deletion)
POST /admin/users/{uid}/reset  → reset password (firebase_admin.auth.generate_password_reset_link)
GET  /admin/access             → list app_access docs
POST /admin/access             → {uid, app, allowed} upsert
DELETE /admin/access/{doc_id}
GET  /admin/usage?app=&from=&to=&group_by=app|user|day
GET  /admin/usage/summary      → aggregated: {app, requests, total_tokens, estimated_cost_usd}
```

### Frontend views
- **Users table:** User | Status (Active/Disabled) | Role | Daily limit | Actions (Edit, Reset, Delete).
- **Add User modal:** email, display name, role, daily token limit (no password field). After creation, shows a complete email text with the password reset link and a "Copy Email Text" button so the admin can paste it into an email to the user.
- **Reset Password modal:** shows a complete email text (greeting, instructions, reset link, signature) with a "Copy Email Text" button — no more console.log.
- **Delete User:** red Delete button on each row with a confirmation dialog. Cleans up Firebase Auth, Firestore user doc, and all app_access records. Prevents self-deletion.
- **App access matrix:** rows = users, columns = apps, cells = allowed toggle. (Convenience view over `app_access`.)
- **Usage dashboard:** table `Application | Requests | Tokens | Est. Cost` with date-range filter. Match the source plan's example:
  ```
  Application      Requests  Tokens    Cost
  Medical AI       523       1.2M      $4.20
  OCR App          92        180K      $0.60
  ```

### Deploy
- `deploy.bat` uses `gcloud run deploy --source .` (single-step build + deploy with Dockerfile).
- `--allow-unauthenticated` is set so the infrastructure is public; the app itself enforces Firebase auth + admin role at the application level.
- Set `APP_ID=auth_admin` and `FIREBASE_CREDENTIALS_JSON` from Secret Manager.
- `run.bat` provided for local dev (kills port 8000, starts uvicorn, opens browser).

**Deliverable:** Jeff can log into `auth-admin.<domain>` and manage users, app access, and view Gemini spend.

---

## Phase 7 — Convert the remaining apps

**Goal:** roll the Phase 4 pattern out to the other four apps. Each conversion is independent and can be done in any order.

### Per-app checklist (apply to each)
1. Add `common-auth` (pinned git tag) to the app's `requirements.txt`.
2. Set `APP_ID=<value from the table above>` in `cloudbuild.yaml` / `deploy.bat`.
3. Add `FIREBASE_CREDENTIALS_JSON` and `FIREBASE_API_KEY` (both from Secret Manager) + `FIREBASE_AUTH_DOMAIN` / `FIREBASE_PROJECT_ID` (plain env vars) to the deploy config.
4. **Backend:**
   - FastAPI apps: create a `get_current_user` wrapper dependency (see "Backend Integration" lessons above), protect every Gemini-calling route with `Depends(get_current_user)`, and catch `UsageLimitExceededError` → 429 in each route handler.
   - Flask apps: protect every Gemini-calling route with `@login_required(APP_ID)`. Catch `UsageLimitExceededError` and return a 429 JSON response.
   - Add a public `/auth/config` endpoint returning Firebase web config (with an `AuthConfigResponse` model for FastAPI apps).
5. **Frontend:** add the Firebase client SDK + email/password login (copy the pilot's `api.js` token handling and login UI). Remove any existing PIN/access UI. Include:
   - A visible "Sign Out" button (with text label) in the top bar when logged in.
   - A "Forgot your password? Contact the admin" `mailto:` link on the login screen.
   - A password visibility toggle (eye icon) on the password field.
   - Bump the PWA service worker cache version when adding Firebase SDK scripts to `index.html`.
6. **Gemini usage:** apply the Phase 5 wrap at each Gemini call site listed in the Phase 5 table. Pass `uid` and `app_id` through to the Gemini functions. Use a `_log_usage_safe()` wrapper so Firestore errors don't break user requests.
7. **Tests:**
   - Create a `conftest.py` with `mock_usage_tracking` (autouse) and `client` (dependency override) fixtures — see "Test Infrastructure" lessons above.
   - Update direct Gemini function calls in unit tests to pass `uid`/`app_id` args.
   - Remove any PIN-related tests. Run the suite; all must pass.
8. **Deploy:** push to `main` (Cloud Build) or run `deploy.bat`. Verify on the live service.

### App-specific notes
- **Clinical Dictation** — ✅ DONE (Phase 7). No PIN to remove; just added auth. Protected both `/api/format` and `/api/transcribe`. Kept the 32 KB and 20 MB limits. 63 tests pass.
- **AI Neuro Exam** — ✅ DONE (Phase 7). Flask + `unittest` (not pytest). Tests use Flask test client; auth mocked by patching `verify_firebase_token`/`is_active`/`can_access_app`/`firebase_init.init_firebase` at the `common_auth.adapters.flask_auth` module level in a shared `AuthenticatedTestCase` base class. Gemini has a fallback when no key — `check_usage_limit` and `log_gemini_usage` are only called on the real Gemini path (not the fallback). 53 tests pass.
- **Rehab Consultant** — Flask (`server_hebrew.py`), Cypress e2e tests on port 5001. The Cypress smoke spec will need a Firebase login step (seed a test user, sign in via the UI in a `beforeEach`). Keep the bilingual/RTL layout intact.
- **Orthotics Assistant** — ✅ DONE (Phase 7). FastAPI with a deterministic engine + optional AI layer. Cloud Run service name is `brace-shoe-assistant` (NOT `brace-and-shoe` as guessed in the plan table — verified via `gcloud run services list`). Protected 4 Gemini-calling routes (`/api/recommendations`, `/api/reports`, `/api/ai/extract`, `/api/ai/perspective`); left `/api/health`, `/api/devices`, `/api/patient/validate` public. Usage tracking (`check_usage_limit` + `log_gemini_usage`) is inside `GeminiClient._generate()` — AFTER the `is_available` check, so the deterministic-only path and `ai_unavailable` results never touch Firestore. Extracted auth wiring (`APP_ID` + `get_current_user`) into a separate `app/auth.py` module to avoid a circular import between `main.py` and `api/routes.py`. 155 tests pass (146 original + 9 new auth tests).

**Deliverable:** all five apps share one login; no PINs remain; all Gemini calls are logged.

---

## Phase 8 — Production hardening

**Goal:** secrets, rate limits, and alerts.

### Secrets
- Move to **Google Secret Manager**:
  - `firebase-service-account` (Firebase Admin SDK creds) — referenced by `FIREBASE_CREDENTIALS_JSON` in every Cloud Run service.
  - `gemini-api-key` (one shared key for all apps) — referenced by `GEMINI_API_KEY` in every Cloud Run service. Per-app cost attribution comes from `usage_logs.app`, not from separate keys.
- Update each `cloudbuild.yaml` `--update-secrets` line. Remove any secrets from `.env` files committed to repos or passed via `--set-env-vars`.

### Protection
- **Rate limiting:** keep each app's existing in-memory limiter (e.g. Medical Summarizer's `rate_limit.py`). Add a per-user rate limit in `common-auth` (e.g. 60 requests/min/uid) using Firestore or in-memory.
- **Max request size:** enforce at the framework level (FastAPI/Flask) — already present in some apps (Clinical Dictation's 32 KB / 20 MB limits). Add where missing.
- **Token quotas:** `daily_token_limit` per user (already enforced in Phase 5). Add a global project-level cap in `common-auth` if needed.
- **Logging alerts:** create Cloud Logging alerts for:
  - Spike in `usage_logs` total_tokens over 1 hour (cost anomaly).
  - Repeated 401/403 from the same IP (abuse).
  - `active: false` users attempting login.

### Final architecture (matches the source plan)
```
Firebase Auth  →  User identity
        |
        v
+-------+-------+-------+
|       |       |       |
v       v       v       v
Flask   FastAPI Flask   FastAPI   (5 Cloud Run services)
        |       |       |       |
        +-------+-------+-------+
                |
                v
        Shared Auth Package (common-auth)
                |
                v
        Firestore: users / app_access / usage_logs
                |
                v
        Gemini API
```

**Deliverable:** secrets out of repos, rate limits + quotas active, alerts configured.

---

## Implementation Order (for the agent)

1. **Phase 1** — Firebase + Firestore setup (manual + `common-auth` smoke test).
2. **Phase 2** — `common-auth` core + tests → tag `v0.1.0`.
3. **Phase 3** — Flask + FastAPI adapters + tests → tag `v0.2.0`.
4. **Phase 4** — Convert Medical Document Summarizer (pilot). Verify on Cloud Run.
5. **Phase 5** — Add Gemini usage tracking to the pilot.
6. **Phase 6** — Build the admin app.
7. **Phase 7** — Convert the other four apps (Clinical Dictation → AI Neuro Exam → Orthotics Assistant → Rehab Consultant).
8. **Phase 8** — Production hardening.

Stop and confirm with the user after each phase before proceeding to the next.

---

## Resolved Decisions

1. **Firebase project:** enable Firebase on the existing GCP project `gen-lang-client-0026629090` (keeps Firestore + Cloud Run in one place; no new project).
2. **Custom domains:** none. Keep the default `*.run.app` Cloud Run URLs for all services including the admin app.
3. **Gemini API key:** one shared key across all apps. Store as a single Secret Manager secret `gemini-api-key` and reference it via `GEMINI_API_KEY` in every Cloud Run service. Cost attribution is done per-app via the `usage_logs.app` field, not via separate keys.
4. **Orthotics Assistant:** confirmed as the **Brace and Shoe Assistant** repo (`C:\Users\jsham\CascadeProjects\Brace and Shoe Assistant`). Cloud Run service name is `brace-and-shoe` (verify exact casing in `deploy.bat` before deploying).

---

## Deployment Lessons Learned (from Phase 4 pilot)

These apply to every app converted in Phase 7. Check each item before pushing.

### Docker / Cloud Build
- **`python:3.12-slim` has no `git`.** If `requirements.txt` includes `git+https://...` (for `common-auth`), the Dockerfile must `apt-get install -y --no-install-recommends git` before `pip install`. Same for the cloudbuild.yaml test step if it uses a bare `python:3.12-slim` image.
- **`common-auth` repo is public.** The repo at `github.com/jshames-doc/common-auth` was made public during Phase 4 so Cloud Build can clone it without credentials. The repo contains no secrets (all secrets are in Secret Manager). Do not make it private again without switching to a token-based install URL.
- **FastAPI union return types need `response_model=None`.** When an endpoint returns `SomeModel | JSONResponse` (e.g. `/auth/config` returning 503 on missing config), add `response_model=None` to the route decorator or FastAPI will fail at startup with "Invalid args for response field".

### Secret Manager / IAM
- **Cloud Run runtime SA needs `roles/secretmanager.secretAccessor`.** The runtime service account (`<project-number>-compute@developer.gserviceaccount.com`) must be granted Secret Manager Secret Accessor at the project level (or per-secret) to read `firebase-service-account` and `gemini-api-key`. This was granted once during Phase 4 and applies to all services in the project.
- **Three secrets are required for every app:** `firebase-service-account` (mapped to `FIREBASE_CREDENTIALS_JSON`), `gemini-api-key` (mapped to `GEMINI_API_KEY`), and `firebase-api-key` (mapped to `FIREBASE_API_KEY`). All three already exist in Secret Manager.

### Frontend (Firebase client SDK)
- **Firebase ID tokens expire after 1 hour.** The frontend must refresh the token on 401 via `firebase.auth().currentUser.getIdToken(true)` and retry the request once. Without this, users get auth failures after ~1 hour of use.
- **Clear the stored token on sign-out.** `onAuthStateChanged(null)` must call `Api.setIdToken(null)` and re-show the login modal, otherwise stale tokens get sent.
- **Validate `/auth/config` response before initializing Firebase.** Check that `apiKey`, `authDomain`, and `projectId` are non-empty before calling `firebase.initializeApp()`.
- **Firebase Web API key must be stored in Secret Manager.** Although the key is designed to be exposed to clients at runtime (via the `/auth/config` endpoint), it must NOT be committed to source files (`cloudbuild.yaml`, `deploy.bat`, `.env.example`, etc.). Secret scanners flag hardcoded keys as leaked credentials. Store it as a Secret Manager secret (`firebase-api-key`) and reference it via `--update-secrets FIREBASE_API_KEY=firebase-api-key:latest` in all deploy configs. The `/auth/config` endpoint reads it from the environment at runtime — that is the only place it should appear in plaintext.

### Local Development
- **`FIREBASE_CREDENTIALS_PATH` for local dev.** In production, `FIREBASE_CREDENTIALS_JSON` (the full JSON string) is injected from Secret Manager. For local dev, pull the service account JSON to a local file (gitignored) and set `FIREBASE_CREDENTIALS_PATH` to its path in `backend/.env`.
- **Check for stale processes on port 8000.** Before starting the backend, run `netstat -ano | findstr ":8000"` and kill any stale uvicorn processes from other apps.

### User Management & Password Reset (from Phase 6 admin app)
- **Auto-generate temp password on user creation.** The admin never types a password. The backend generates a random 16-char password, creates the Firebase Auth user, then immediately calls `generate_password_reset_link` and returns it in the response. The frontend shows a complete email text with the link for the admin to copy and send to the user.
- **`min_length` on optional Pydantic fields rejects `None`.** If a field is `str | None = Field(default=None, min_length=6)`, Pydantic will reject `None` with a 422 error. Remove `min_length` from optional fields, or use a validator that only applies the constraint when a value is provided.
- **Firebase Admin SDK `generate_password_reset_link` does not send an email.** It only returns a URL. The admin must copy the link (or a complete email text containing it) and send it to the user manually. To actually email the user, you would need the Firebase Client SDK's `sendPasswordResetEmail` (client-side only).
- **Delete user cleanup.** When deleting a user, clean up all three layers: Firebase Auth user, Firestore `users/{uid}` doc, and all `app_access` docs where `uid` matches. Prevent self-deletion (admin cannot delete their own account).
- **Forgot password link on login screens.** All apps' login screens should include a "Forgot your password or need access? Contact the admin" link with a `mailto:` to the admin email. This gives users a clear path when they can't log in.
- **Password visibility toggle.** All password fields should include an eye icon to toggle between hidden/visible. Implementation: wrap the input in a `.password-field` div with a `.password-toggle` button that switches `input.type` between `password` and `text` and swaps the Lucide icon between `eye` and `eye-off`.
- **Sign Out button on all apps.** Every app should have a visible "Sign Out" button (with text label, not just an icon) in the top bar when the user is logged in. This allows users to test the login flow and is essential for shared/kiosk devices.

### Deployment (from Phase 6 admin app)
- **`gcloud run deploy --source .` vs two-step build+deploy.** The single-step `--source .` approach combines `gcloud builds submit` and `gcloud run deploy --image` into one command. When a `Dockerfile` exists, it uses Docker build (not buildpacks). Buildpacks are only used when there is no Dockerfile. The single-step approach is cleaner but not inherently faster — build time is dominated by pip install.
- **Docker layer caching in Cloud Build.** Cloud Build does not cache Docker layers by default. Each deploy rebuilds from scratch (re-installs all pip packages). The Dockerfile should copy `requirements.txt` and install deps before copying code, so unchanged requirements benefit from any available cache. For explicit caching, use the two-step approach with `gcloud builds submit --cache-from`.
- **Browser cache and static files.** When updating frontend HTML/JS/CSS, users may see stale versions due to browser cache. Use hard refresh (Ctrl+Shift+R) or version query params (`?v=1.0`) on script/style tags to bust cache. The DevTools MCP browser can be used to verify changes are live.

### Backend Integration (from Phase 7 — Clinical Dictation)

- **`require_user(app_id)` returns a closure — not overridable in tests.** You cannot do `app.dependency_overrides[require_user(APP_ID)] = ...` because each call to `require_user(app_id)` creates a new closure. Instead, create a module-level wrapper function in `app.py`:
  ```python
  _require_user = require_user(os.environ.get("APP_ID", "clinical_dictation"))

  def get_current_user() -> UserContext:
      return _require_user()
  ```
  Then use `Depends(get_current_user)` in routes. Tests override `get_current_user`:
  ```python
  app.dependency_overrides[app_module.get_current_user] = lambda: UserContext(
      uid="test-uid", email="test@example.com", app_id="clinical_dictation"
  )
  ```
  This is the single most important pattern for testable auth integration.

- **`UsageLimitExceededError` does not auto-map to 429.** The route handler must catch it explicitly with a try/except around the Gemini call and return a `JSONResponse(status_code=429, ...)`. Without this, the error surfaces as a 500.
  ```python
  try:
      result = await gemini.format_note(req, uid=user.uid, app_id=APP_ID)
  except UsageLimitExceededError:
      return JSONResponse(status_code=429, content={"detail": "Daily usage limit reached."})
  ```

- **Usage logging must be failure-safe.** Wrap `log_gemini_usage` in a try/except inside the Gemini module (e.g. `_log_usage_safe()`) so Firestore errors don't break the user's request. The user should still get their formatted note even if usage logging fails.

- **Gemini function signatures change — unit tests must follow.** Adding `uid` and `app_id` params to `format_note()` and `transcribe_audio()` breaks every direct call in `test_gemini.py`. Each test must be updated to pass `uid="test-uid", app_id="<app_id>"`. The conftest's `mock_usage_tracking` autouse fixture patches `check_usage_limit` and `log_gemini_usage` so these calls don't hit Firestore.

- **`AuthConfigResponse` Pydantic model.** The `/auth/config` endpoint needs a response model with `apiKey`, `authDomain`, `projectId` fields. Without it, FastAPI's response validation fails or the OpenAPI schema is wrong.

- **Firebase web config env vars in deploy config.** In addition to `APP_ID` and `FIREBASE_CREDENTIALS_JSON` (secret), the deploy config (`cloudbuild.yaml` / `deploy.bat`) must set `FIREBASE_API_KEY`, `FIREBASE_AUTH_DOMAIN`, `FIREBASE_PROJECT_ID` as plain env vars in `--update-env-vars`. The `/auth/config` endpoint reads these and returns them to the frontend. They are not secrets (the Web API key is designed for client-side embedding).

- **`.env.example` must include all Firebase vars.** For local dev onboarding, `.env.example` should list `APP_ID`, `FIREBASE_API_KEY`, `FIREBASE_AUTH_DOMAIN`, `FIREBASE_PROJECT_ID`, and `FIREBASE_CREDENTIALS_PATH` (local file path, not the Secret Manager JSON).

### Test Infrastructure (from Phase 7 — Clinical Dictation)

- **`conftest.py` pattern for FastAPI apps.** Two fixtures are needed:
  1. `mock_usage_tracking` (autouse) — patches `check_usage_limit` (returns `True`) and `log_gemini_usage` (no-op) so tests never hit Firestore.
  2. `client` — sets env vars (`APP_ID`, `FIREBASE_API_KEY`, etc.), overrides the `get_current_user` dependency with a fake `UserContext`, yields a `TestClient`, and clears overrides at teardown.
  Remove any existing `client` fixture from `test_app.py` so the conftest one is used.

- **Testing 401 (unauthenticated).** To test that a route returns 401 without a token, clear `dependency_overrides` inside the test and mock `firebase_init.init_firebase` (so `require_user` doesn't try to initialize Firebase). Restore the override in a `finally` block for subsequent tests.

- **`_patch_transcribe` fakes must accept `uid`/`app_id` kwargs.** When patching `transcribe_audio` at the module level in tests, the fake function signature must include `uid=""` and `app_id=""` keyword args, otherwise the route handler's call fails with a `TypeError`.

### Frontend / PWA (from Phase 7 — Clinical Dictation)

- **Firebase SDK from CDN doesn't need service worker caching.** The SW only intercepts same-origin GET requests. Cross-origin CDN scripts (e.g. `https://www.gstatic.com/firebasejs/...`) fall through to the network. No need to add them to `SHELL_URLS` or `SHELL_ASSETS`.

- **Bump `SHELL_CACHE` when adding Firebase SDK scripts.** Even though the CDN scripts aren't cached, adding the `<script>` tags to `index.html` changes the shell HTML, so bump the cache version in `sw.js` to force clients to pick up the new shell.

- **`api.js` token handling pattern.** Use a module-scoped `_idToken` variable with `setIdToken()`/`getIdToken()` setters. The `authHeaders()` helper merges the Bearer header into any existing headers (important for `FormData` requests where you must NOT set `Content-Type`). On 401, call `firebase.auth().currentUser.getIdToken(true)` to force-refresh, then retry the request once. If the refresh fails (no current user), throw a "Sign in required" error.

- **`app.js` auth initialization.** Call `wireAuth()` from `init()` (after other setup, before `setView`). `wireAuth()` wires the password toggle, sign-in form submit, sign-out button, and calls `initializeAccess()` which fetches `/auth/config`, initializes Firebase, and registers an `onAuthStateChanged` listener that shows/hides the modal and sets/clears the ID token.

### Flask / unittest Integration (from Phase 7 — AI Neuro Exam)

- **`@login_required(APP_ID)` is applied at import time — you cannot override it in tests.** Unlike FastAPI's `Depends(get_current_user)` which can be overridden via `app.dependency_overrides`, the Flask decorator wraps the view function when the module is imported. By the time the test client is created, the wrapper is already in place. Instead, patch the underlying functions the decorator calls at the `common_auth.adapters.flask_auth` module level: `verify_firebase_token`, `is_active`, `can_access_app`, and `firebase_init.init_firebase`. The test client must send an `Authorization: Bearer fake-token` header so `_extract_bearer_token()` returns a non-None value.
  ```python
  from common_auth.adapters import flask_auth
  patches = [
      patch.object(flask_auth, "verify_firebase_token", return_value={"uid": "test-uid", "email": "test@example.com"}),
      patch.object(flask_auth, "is_active", return_value=True),
      patch.object(flask_auth, "can_access_app", return_value=True),
      patch("common_auth.adapters.flask_auth.firebase_init.init_firebase"),
  ]
  ```
  Use `patch.object(flask_auth, ...)` for the imported names (they're bound in the flask_auth namespace), and `patch("common_auth.adapters.flask_auth.firebase_init.init_firebase")` for the module attribute access.

- **`unittest` has no autouse fixtures — use a base TestCase.** Since Flask apps may use `unittest` (not pytest), there's no `conftest.py` with autouse fixtures. Create a shared `tests/auth_test_base.py` with an `AuthenticatedTestCase(unittest.TestCase)` base class that starts all patches in `setUp()` and stops them in `addCleanup()`. Test classes inherit from it instead of `unittest.TestCase` directly. A separate `UnauthenticatedTestCase` base (only mocks `firebase_init.init_firebase`) is useful for testing the 401 path.

- **`UsageLimitExceededError` → 429 in Flask.** The Flask route handler catches it explicitly with a try/except around the Gemini call and returns `jsonify({...}), 429`. Same pattern as FastAPI but using Flask's `jsonify` + tuple return instead of `JSONResponse`.

- **Gemini fallback apps: guard `check_usage_limit` and `log_gemini_usage` with an `if uid and app_id:` check.** When the app has a fallback path (no API key → return hardcoded response), the fallback must NOT call `check_usage_limit` or `log_gemini_usage`. Only the real Gemini code path (after the `if not self.api_key` guard) should call them. Pass `uid=""` and `app_id=""` as defaults so the guard is clean.

- **`request.user` is the Flask equivalent of FastAPI's `UserContext`.** After `@login_required(APP_ID)` succeeds, `flask.request.user` is a `UserContext` with `.uid`, `.email`, and `.app_id`. Access it in the route handler via `request.user.uid`.

- **No service worker? No SW cache bump needed.** The Neuro Exam app has no `sw.js` (not a PWA). The "bump `SHELL_CACHE`" lesson doesn't apply. Just bump the app version string in `index.html` and `README.md` (and the corresponding test assertions in `test_frontend_assets.py`).

- **`cloudbuild.yaml` test step for unittest.** Use `python -m unittest discover -s tests -p "test_*.py" -v` instead of `python -m pytest`. The `python:3.12-slim` test image still needs `apt-get install git` for the `common-auth` pip git URL.

### Deterministic Engine + Optional AI (from Phase 7 — Orthotics Assistant)

- **Usage tracking goes inside the Gemini client's `_generate()`, NOT in the route handler or orchestrator.** The Orthotics Assistant has a deterministic engine that works without Gemini. The AI orchestrator returns `ai_unavailable` when the AI client is None or `not ai_client.is_available` — no Gemini call happens. Placing `check_usage_limit` and `log_gemini_usage` inside `GeminiClient._generate()` AFTER the `is_available` check ensures usage is only tracked on the real Gemini path. The deterministic-only path and `ai_unavailable` results never touch Firestore.

- **Guard usage tracking with `if uid and app_id:`.** The `_generate()` method accepts optional `uid` and `app_id` params. When they're `None` (e.g. unit tests using `FakeGeminiClient`, or internal calls without a user context), the usage tracking is skipped. This keeps the Gemini client backward-compatible with existing tests that don't pass user context.

- **Extract auth wiring into a separate `app/auth.py` module to avoid circular imports.** When the app has a separate `api/routes.py` module (not everything in `app.py` like Clinical Dictation), importing `APP_ID` and `get_current_user` from `app.main` creates a circular import (`main.py` imports `router` from `routes.py`). Solution: create `app/auth.py` with `APP_ID`, `_require_user`, and `get_current_user`. Both `main.py` and `routes.py` import from `app.auth`. Tests override `get_current_user` via `app.dependency_overrides[get_current_user]` — the function object is the same regardless of which module imported it.

- **Gemini REST API `usageMetadata` field names differ from the google-genai SDK.** The Orthotics Assistant uses httpx directly (not the google-genai SDK). The REST API response contains `usageMetadata` with `promptTokenCount` and `candidatesTokenCount` (camelCase), NOT `prompt_token_count` and `candidates_token_count` (snake_case, which is what the SDK's `usage_metadata` object uses). Extract tokens from `data["usageMetadata"]["promptTokenCount"]` and `data["usageMetadata"]["candidatesTokenCount"]`.

- **`FakeGeminiClient` in tests must accept `uid`/`app_id` kwargs.** The orchestrator passes `uid=uid, app_id=app_id` to `ai_client.recommend()`. The test's `FakeGeminiClient.recommend()` method must accept these as keyword arguments (with `None` defaults) even though it ignores them. Without this, the orchestrator call raises `TypeError: unexpected keyword argument 'uid'`.

- **Cloud Run service name verification.** The plan table guessed `brace-and-shoe` for the Orthotics Assistant, but the actual service name (verified via `gcloud run services list`) is `brace-shoe-assistant`. Always verify the service name in `deploy.bat` AND against the live Cloud Run services before deploying. The `deploy.bat` default matched the live service.

- **No service worker? No SW cache bump needed.** Like the Neuro Exam app, the Orthotics Assistant has no `sw.js` (not a PWA). The "bump `SHELL_CACHE`" lesson doesn't apply. Just add the Firebase SDK `<script>` tags to `index.html` and the auth modal HTML — the browser will fetch them fresh on next load.

- **`cloudbuild.yaml` test step for pytest with separate backend dir.** The Orthotics Assistant runs tests from the `backend/` directory: `cd backend && python -m pytest tests/ -v`. The `python:3.12-slim` test image needs `apt-get install git` for the `common-auth` pip git URL, same as all other apps.
