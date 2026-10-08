# SyncFit Edge — Backend integration guide

FastAPI service that orchestrates the `hardware → local model → DeepSeek/GPT-6 Luna`
pipeline, enforces the clinical/safety rules and persists everything. This guide
is written for the frontend developer who will build the final UI.

- Base URL (dev): `http://localhost:8000`
- API prefix: `/api/v1`
- Interactive docs (when the app runs): `/docs` (Swagger) and `/openapi.json`
- A frozen snapshot lives in `docs/openapi.json`.

---

## 1. Run & configuration

```bash
# PostgreSQL (from syncfit-database)
bash scripts/up.sh

# Backend (IMPORTANT: no --reload; editable sibling packages are not hot-reloaded)
uvicorn app.main:app --port 8000
```

Environment (`.env`, git-ignored; see `.env.example`):

| Variable | Default | Purpose |
|---|---|---|
| `SYNCFIT_DATABASE_URL` / `DATABASE_URL` | local Postgres | Database URL. |
| `BACKEND_SECRET_KEY` | change-me | JWT signing secret (use a long random string). |
| `BACKEND_TOKEN_EXPIRE_MINUTES` | 10080 | Token lifetime (7 days). |
| `BACKEND_CORS_ORIGINS` | `http://localhost:3000` | Comma-separated allowed origins (production: the frontend origin, since the API is served from its own subdomain). |
| `BACKEND_CORS_ORIGIN_REGEX` | localhost any port | Regex origin fallback. |
| `SUPERADMIN_EMAIL` / `SUPERADMIN_PASSWORD` / `SUPERADMIN_NAME` | — | Seed super admin on startup. |
| `BACKEND_ROUTINE_ENGINE` | `ai` | `ai` (OpenCode models) or `deterministic` (fast, offline). |
| `REASONING_API_KEY` | — | OpenCode Go key shared by primary and fallback models. |
| `REASONING_MODEL` | `deepseek-v4-pro` | Primary reasoning model. |
| `REASONING_FALLBACK_MODEL` | `gpt-6-luna` | Responses API fallback for transient primary failures; empty disables it. |
| `REASONING_TIMEOUT` | `90` | Primary model call timeout (seconds). |
| `REASONING_FALLBACK_TIMEOUT` | `20` | Backup model call timeout (seconds). |
| `REASONING_DEADLINE` | `115` | Whole generation budget (seconds); then the deterministic routine. |
| `REASONING_PRODUCT` | `go` | OpenCode product (`go`/`zen`). |
| `BACKEND_RESERVED_NAMES` / `BACKEND_NAME_EXCEPTIONS` | — | Name validation. |

**Schema.** `Database.init_db()` runs on startup: it creates missing tables and
**adds missing columns** (`ALTER TABLE ADD COLUMN`, booleans with `DEFAULT true`)
without data loss. Production must use Alembic.

---

## 2. Conventions

- **Auth:** `Authorization: Bearer <jwt>` on protected endpoints.
- **Roles:** `ATHLETE`, `GYM_ADMIN`, `SUPER_ADMIN`.
- **Errors:** standard FastAPI shape `{ "detail": "<message>" }`.
  `401` invalid/missing token, `403` forbidden/inactive/deactivated, `404` not found,
  `409` duplicated (email/cedula), `422` validation.
- **Delete:** returns `204 No Content`.
- **Language:** most GETs accept `?language=EN|ES|ZH`.
- **Images:** uploaded as compressed **data URLs** (client-side), stored as text.

---

## 3. Authentication

| Method | Path | Access | Body | Returns |
|---|---|---|---|---|
| POST | `/api/v1/auth/register` | public | `{email, password, display_name, document_id}` | `{access_token, token_type, user}` |
| POST | `/api/v1/auth/login` | public | `{email, password}` | `{access_token, token_type, user}` |
| GET | `/api/v1/auth/me` | auth | — | `user` |
| PUT | `/api/v1/auth/password` | auth | `{current_password, new_password}` | `{access_token, token_type, user}` (old tokens are revoked) |
| POST | `/api/v1/auth/logout` | auth | — | `204` (revokes every token of the user, on all devices) |
| DELETE | `/api/v1/auth/me` | auth | `{password}` | `204` (deletes the account and all its data; super admin gets `403`) |

`user = {id, email, display_name, document_id, role, active}`.
`document_id` (cedula) is **required at registration** (6–15 digits, unique).
Deactivated accounts (`active=false`) cannot log in (`403`).

```ts
const api = "http://localhost:8000/api/v1";
const res = await fetch(`${api}/auth/login`, {
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify({ email, password }),
});
const { access_token, user } = await res.json();
localStorage.setItem("syncfit_token", access_token);
```

---

## 4. WebSocket (live telemetry)

- `GET /api/v1/ws/telemetry` (no auth) accepts JSON frames and replies.
- Send either a raw `TelemetryFrame` or a `WsEnvelope` `{type, payload}`.
- Receive `{type:"prescription", payload:<decision>}` or `{type:"error", payload:{detail}}`.

---

## 5. Endpoint reference

### Catalog & telemetry
| Method | Path | Access | Purpose |
|---|---|---|---|
| GET | `/health` | public | `{status, version}`. |
| GET | `/muscle-groups` | public | Muscle group list. |
| GET | `/catalog?language=` | public | Localized exercises (id, name, groups, impact, image…). |
| POST | `/telemetry` | public | `{decision}` for a telemetry frame. |
| GET | `/machines?language=` | auth | Localized catalog machines. |
| GET | `/exercises/{id}/alternatives?language=` | auth | Ordered replacement options (Change button). |
| GET | `/exercises/{id}/variants` | public | Movement-family variants. |

### Profiles / cycle / calendar
| Method | Path | Access | Purpose |
|---|---|---|---|
| PUT | `/profiles/me` | auth | Upsert athlete profile (onboarding/settings). |
| GET | `/profiles/me` | auth | Profile + `document_id` + `timeline`. |
| GET | `/cycle` | auth | `{timeline}`. |
| GET | `/calendar?month=&language=` | auth | Cycle/gestation calendar. |
| POST/GET | `/profiles`, `/profiles/by-id/{id}`, `/energy` | public | In-memory profile/energy (guest/legacy). |

### Routine
| Method | Path | Access | Purpose |
|---|---|---|---|
| POST | `/capture?language=&muscle_groups=&exercises_count=&time_budget_minutes=&energy_level=&include_warmup=` | auth | Full capture → **validated routine**. |
| POST | `/routines?engine=simulator\|ai&profile_id=` | public | Generate a routine directly. |
| GET | `/routine/latest` | auth | Latest stored routine. |
| GET | `/stats` | auth | Streak / weekly training stats. |

`capture` returns, among others:
`{session_id, routine_id, phase_inferred, fatigue_level, k_load, assessment,
engine_used, machine_preferences, biomarkers, alerts, total_estimated_minutes,
warmup, routine}`. Each `routine` item:
`{order_index, exercise_id, name, role, blocked, block_reason, substitute,
series, reps, weight_suggested_kg, rest_seconds, estimated_seconds, image_url,
sets, description, how_to, tips, machine_id, machine_name, movement_pattern, rationale}`.

### Supplements
| Method | Path | Access | Purpose |
|---|---|---|---|
| GET | `/supplements?modality=&language=&objective=&goal_phase=&week=&weight_kg=&height_cm=&body_fat_pct=&age=&daily_calories=` | public | Pregnancy-safe advice. |
| GET | `/supplements/catalog?language=` | auth | Catalog with brands/frequency. |
| POST/GET | `/supplement-intakes` | auth | Track daily intake. |

### Sharing
| Method | Path | Access | Purpose |
|---|---|---|---|
| POST/GET/DELETE | `/shares` | auth | Create/list/delete read-only share links. |
| GET | `/shared/{token}?language=` | public | Public shared profile. |

### Gyms & equipment
| Method | Path | Access | Purpose |
|---|---|---|---|
| POST | `/gyms` | **gym_admin** | Create a gym (GYM_ADMIN only). |
| PATCH/DELETE | `/gyms/{id}` | auth (owner) | Rename / delete gym (+memberships+equipment). |
| GET | `/gyms/mine?language=` | auth | Owned gyms. |
| GET | `/gyms/joined?language=` | auth | Joined gyms with live equipment. |
| POST | `/gyms/{id}/machines` | auth (owner) | Add equipment. |
| PATCH/DELETE | `/gyms/{id}/machines/{mid}` | auth (owner) | Edit / delete equipment. |
| GET | `/gyms/{code}` | public | Gym by code. |
| POST/DELETE | `/gyms/join`, `/gyms/{id}/leave` | auth | Join/leave. |
| POST | `/gyms/{id}/activate` | auth | Set active gym. |
| GET | `/gyms/{id}/qr.png` | auth (owner) | QR PNG. |

**Equipment payload** (`POST/PATCH .../machines`):
```json
{
  "name": "Hip Thrust Machine",
  "purpose": "Glutes",
  "image_url": "data:image/jpeg;base64,...",
  "exercise_ids": ["hip-thrust"],
  "equipment_key": "machine",   // machine|smith|barbell|dumbbell|bench|cable|pullup-bar|dip-bar|ghd|box|band|none
  "equipment_type": "MACHINE",
  "weight_factor": 1.4
}
```
`exercise_ids` are validated against the catalog (invalid/unknown ids are dropped).

### Super admin (administrative only)
| Method | Path | Access | Purpose |
|---|---|---|---|
| POST/GET | `/admin/gym-admins` | super_admin | Create/list gym admins. |
| GET | `/admin/gyms?language=` | super_admin | Inspect all gyms. |
| GET | `/admin/me` | super_admin | Current admin. |
| GET | `/admin/users?role=&search=` | super_admin | List/search users. |
| GET | `/admin/users/{id}` | super_admin | User + profile detail. |
| PATCH | `/admin/users/{id}` | super_admin | Edit name/email/document. |
| POST | `/admin/users/{id}/deactivate` | super_admin | Soft-disable. |
| POST | `/admin/users/{id}/activate` | super_admin | Re-enable. |
| POST | `/admin/users/{id}/password` | super_admin | Reset password. |
| POST | `/admin/users/{id}/role` | super_admin + **`admin_password`** | Change role. |
| DELETE | `/admin/users/{id}` | super_admin + **`admin_password`** | Hard delete (cascade). |

---

## 6. End-to-end journey (frontend)

1. **Register** (athlete): `POST /auth/register` with `document_id`.
2. **Onboarding**: `PUT /profiles/me` (modality, cycle/gestation, body comp, goal,
   machines, symptoms, `weekly_training_goal`, `rest_days_allowance`).
3. **Join gym**: `POST /gyms/join {code}` → `GET /gyms/joined` shows equipment.
4. **Capture**: `POST /capture?muscle_groups=GLUTES&exercises_count=5` →
   routine using gym equipment first, with per-exercise `movement_pattern`,
   `machine_id` and `rationale`.
5. **Edit in the UI**: the client edits `series/reps/weight`; use
   `GET /exercises/{id}/alternatives` for the **Change** list.
6. **Train**: the WorkoutRunner uses the returned `sets`.
7. **Extras**: `GET /supplements`, `POST /supplement-intakes`, `GET /stats`,
   `POST /shares`.

---

## 7. Routine pipeline (two AIs)

```
hardware/simulator → syncfit-core (DSP + RandomForest → biomarkers + k_load)
   → PhysiologicalAssessment → DeepSeek (OpenCode Go) designs the routine
   → GPT-6 Luna (Responses API) on transient DeepSeek/provider failures
   → deterministic enforcement → persistence → response
```
- The model **never recomputes `k_load`** (always echoed).
- `engine_used` reports `deepseek`, `gpt-6-luna`, or `deterministic` if both
  generative models fail. Every generated routine passes deterministic enforcement.
- **Equipment filters (priority):** (1) gym machines, (2) free equipment
  registered in the gym, (3) bodyweight. A registered **bench** enables
  Bulgarian/step-ups, dumbbells enable `db-*`, etc.
- **Invariants always enforced:** one exercise per movement pattern (no
  duplicates), required-pattern coverage, compounds before isolation,
  contraindicated patterns excluded (knee pain → no lunge/squat; low back → no
  hinge/row), machine-first, dose within evidence ranges.
- `time_budget_minutes` trims the routine to fit.

---

## 8. Errors & data notes

- Dates: ISO `YYYY-MM-DD`. Images: compressed data URLs.
- `blocked` exercises carry `block_reason` and `substitute`.
- `machine_preferences` maps `movement_pattern → chosen gym machine`.

For the per-module/function reference see [`docs/FUNCTIONS.md`](./docs/FUNCTIONS.md).
