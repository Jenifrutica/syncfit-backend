# SyncFit Backend

Asynchronous application server of SyncFit Edge. Persists data, ingests continuous telemetry, orchestrates the numerical core and the reasoning layer, and serves the frontend.

## Documentation

- **[`API.md`](./API.md)** — API & integration guide for the frontend (run, auth,
  conventions, all endpoints with examples, end-to-end journey, routine pipeline).
- **[`docs/FUNCTIONS.md`](./docs/FUNCTIONS.md)** — module & function reference.
- **[`docs/openapi.json`](./docs/openapi.json)** — frozen OpenAPI snapshot
  (live at `/openapi.json` and `/docs`).

## Purpose

Own the runtime: low-latency telemetry ingestion, in-memory analytics over the cycle and gestation timeline, and persistence. This is where the four mandatory data structures of the project are fully implemented.

## What belongs here

- **REST API** (`api/`): FastAPI endpoints for persistence and queries.
- **WebSockets** (`ws/`): continuous JSON telemetry ingestion at low latency (< 50 ms).
- **Analytics** (`analytics/`): the mandatory data structures and the timeline queries built on them.
- **Orchestration** (`services/`): `core → reasoning → adapted routine`.
- **Persistence** (`persistence/`): storage layer for sessions, telemetry and prescriptions.
- Integration tests and load tests.

## What does NOT belong here

- Sensor drivers or embedded firmware.
- ML training or DSP internals.
- Prompt internals of the reasoning kernel.
- UI rendering.

## Data Structures

All four structures required by the technical document are implemented here:

| Structure | Complexity | Purpose |
|-----------|:----------:|---------|
| **Time-Series Segment Tree** | O(log n) | Range queries (min / max / mean) over temperature and HRV across cycle days or gestation weeks. |
| **Priority Queue / Max-Heap** | O(1) dispatch | Dispatching critical physiological alerts. |
| **Directed State Graph** | Graph traversal | Formal multimodal transitions between phases and trimesters. |
| **Ring Buffer** | O(1) insert | Python-side ingestion buffer for the incoming 100 Hz stream. |

Recommended extras:

| Structure | Complexity | Purpose |
|-----------|:----------:|---------|
| **HashMap / session map** | O(1) | Fast session lookup. |
| **deque ingest queue** | O(1) append | WebSocket ingestion queue. |
| **LRU Cache** | O(1) amortized | Reusing repeated inference results. |
| **Set / Bloom filter** | O(1) / O(k) | Alert de-duplication. |

### Applied in the gym feature

`app/services/gyms.py` resolves the athlete's joined gyms with three structures
so the endpoint is a single pass instead of N+1 queries:

| Structure | How it is implemented | Purpose |
|-----------|-----------------------|---------|
| **Hash map** | `gyms_by_id = {g.id: g for g in ...}` from one `Gym.id.in_(...)` query | O(1) gym lookup per membership. |
| **Grouping map** | `machines_by_gym = defaultdict(list)` filled from one `GymMachine.gym_id.in_(...)` query | Machines grouped by gym in O(G + M). |
| **Set-like check** | `gym.id == profile.active_gym_id` | O(1) "is this the active gym?". |

The membership itself is a **set of `(profile_id, gym_id)` pairs** persisted with a
unique constraint in `syncfit-database`, so `POST /gyms/join` is idempotent.

Additional structures in the gym/routine feature:

| Structure | How | Purpose |
|-----------|-----|---------|
| **Token set** | `_tokens(machine.name/purpose)` ∩ `_tokens(exercise.name)` | Fuzzy fallback that matches a machine to exercises when `exercise_ids` is empty (prefers `equipment_type=MACHINE`). |
| **Movement family** | `variant_of` from the catalog | `GET /exercises/{id}/variants` returns interchangeable options (barbell/Smith/machine) for the routine editor. |
| **Name validation** | Regex + reserved set + exceptions | `validate_person_name`/`validate_gym_name`; `users.document_id` (cedula) unique. |

`DELETE /gyms/{gym_id}` removes the gym's memberships, clears `active_gym_id` and
cascades its machines. `capture` now also returns `biomarkers` for the detail view.
Machines are **not copied** into the profile: they are read live per membership,
so a gym admin's edits show up immediately. Admin machine CRUD
(`PATCH`/`DELETE /gyms/{gym_id}/machines/{machine_id}`) reuses the same ownership check.

`gyms.station_index()` powers "build the routine on the gym's machines" with:

| Structure | How it is implemented | Purpose |
|-----------|-----------------------|---------|
| **Hash map** | `exercise_id -> serialized station` | O(1) lookups while scanning routine entries; injects the machine's photo, id and name. |
| **Set** | `set(index)` | The preferred exercise ids handed to the routine builder. |
| **Localized JSON** | `name`/`purpose` stored as `{"en","es","zh"}` | A machine typed in Spanish is shown in the athlete's language (AI translates on write, with a copy fallback). |

## Suggested structure

```
syncfit-backend/
├── app/
│   ├── api/            # REST routers
│   ├── ws/             # WebSocket endpoints
│   ├── analytics/      # segment tree, heap, state graph, ring buffer
│   ├── services/       # orchestration (core + reasoning)
│   └── persistence/    # storage layer
├── tests/
├── pyproject.toml
└── README.md
```

## Stack

Python 3.11+, FastAPI, WebSockets, Pydantic, imports `syncfit-core` and `syncfit-ai-reasoning`.

## Tasks

> **Language: Python 3.11+ (mandatory).** This service is written in Python; no other language is allowed for the backend.

### Requirements

- [ ] Scaffold the FastAPI application and configuration loading.
- [ ] Implement REST endpoints for persistence and queries.
- [ ] Implement the OpenAPI spec consumed from `syncfit-contracts`.
- [ ] Implement WebSocket ingestion of JSON telemetry at < 50 ms latency.
- [ ] Implement the **Time-Series Segment Tree** (O(log n) range min/max/mean).
- [ ] Implement the **Priority Queue / Max-Heap** (O(1) alert dispatch).
- [ ] Implement the **Directed State Graph** (phase and trimester transitions).
- [ ] Implement the **Ring Buffer** (O(1) ingestion of the 100 Hz stream).
- [ ] Implement recommended extras: HashMap session map, deque ingest queue, LRU Cache, alert de-duplication.
- [ ] Orchestrate `core → reasoning → adapted routine`.
- [ ] Implement the persistence layer for sessions, telemetry and prescriptions.
- [ ] Validate every payload against `syncfit-contracts`.
- [ ] Write integration tests and load tests.
- [ ] Provide a Dockerfile consumable by `syncfit-infra`.

## Routine engine (two AIs)

`capture` runs hardware -> **local model** (`syncfit-core`: biomarkers + `k_load`)
-> **DeepSeek** (`syncfit-ai-reasoning`, OpenCode):

- The local model produces a `PhysiologicalAssessment`; DeepSeek never recomputes `k_load`.
- `BACKEND_ROUTINE_ENGINE=ai|deterministic` (default `ai`); the deterministic
  evidence engine is also the fallback.
- Symptom `avoid_patterns` become `contraindicated_patterns`; responses include
  `assessment`, `biomarkers` and per-exercise `movement_pattern` / `rationale`.

Full endpoint reference: [`API.md`](./API.md).

## Related repositories

- [`syncfit-contracts`](../syncfit-contracts) — request/response schemas.
- [`syncfit-core`](../syncfit-core) — deterministic engine.
- [`syncfit-ai-reasoning`](../syncfit-ai-reasoning) — reasoning layer.
- [`syncfit-hardware`](../syncfit-hardware) — telemetry source.
- [`syncfit-frontend`](../syncfit-frontend) — client.

All code, comments, documentation and commits in this repository are written in English.

## Handoff for the team

**Role.** FastAPI runtime: orchestrates hardware → core → DeepSeek → validator,
enforces the system rules, persists and serves the frontend.

**Run / test.** `uvicorn app.main:app --port 8000` (no `--reload`; editable
siblings are not hot-reloaded) · `pytest`.

**Docs (read these first).** [`API.md`](./API.md) (integration guide),
[`docs/FUNCTIONS.md`](./docs/FUNCTIONS.md) (module/function reference),
[`docs/openapi.json`](./docs/openapi.json) (openapi snapshot).

**Entry points.** `app/main.py`, `app/api/routes.py` + `app/api/auth.py`,
`app/services/*` (capture pipeline, gyms, admin, supplements, sharing…),
`app/ws/routes.py`. Roles: ATHLETE, GYM_ADMIN (gyms+equipment), SUPER_ADMIN
(administrative user/profile CRUD). Config in `app/config.py`; engine via
`BACKEND_ROUTINE_ENGINE`.

## Context for a new session

**What it is.** FastAPI server: auth, onboarding, telemetry, routines, catalog,
supplements, sharing. Reuses core/simulator/ai.

**Stack.** Python 3.11+, FastAPI, SQLAlchemy (via syncfit-database), PyJWT,
OpenAI SDK (optional reasoning).

**Run.** `uvicorn app.main:app --reload --port 8000`. Config from `.env`
(`SYNCFIT_DATABASE_URL`, `BACKEND_SECRET_KEY`, `BACKEND_CORS_ORIGINS`,
`BACKEND_CORS_ORIGIN_REGEX`). CORS allows localhost any port (regex).

**Endpoints (`/api/v1`).** `auth/register|login|logout|me|password`; `profiles/me` (GET/PUT),
`profiles`, `profiles/by-id/{id}`; `cycle`, `calendar`, `stats`; `capture`
(query: muscle_groups, exercises_count, time_budget_minutes, energy_level,
include_warmup); `routine/latest`; `catalog`, `muscle-groups`, `machines`,
`symptoms`; `supplements` (+ `/supplements/catalog`), `supplement-intakes`
(GET/POST); `telemetry` (POST) and WS `/ws/telemetry`; `shares` (GET/POST/DELETE),
`shared/{token}` (public). Services in `app/services/` (auth, capture, cycles,
calendar, routines, supplements, symptoms, sharing, stats, loads, machines).

**Deps for capture.** profile symptoms are applied (block/advice/stop);
available machines scale weights; body comp + goal feed macros.

**Run tests.** `pytest` (needs contracts/core/simulator/database installed).


## Administration and equipment

- **Super admin** (purely administrative): `GET/PATCH /admin/users`,
  `POST /admin/users/{id}/{activate,deactivate,password,role}`,
  `DELETE /admin/users/{id}`. Role change and delete require
  `admin_password` (the super admin's password). Cannot create gyms/machines.
- **Gym admin** only: creates gyms and registers **equipment** (machines and free
  equipment: dumbbell/barbell/smith/bench/cable) with `equipment_key`/`equipment_type`.
- **Routine filters** use the gym inventory: machines first, then free equipment
  (`Exercise.required_equipment`), then bodyweight. A flat bench enables
  Bulgarian/step-ups; dumbbells enable `db-*`, etc.

## Roles, super admin and gyms

- **Roles** on `users.role`: `ATHLETE`, `GYM_ADMIN`, `SUPER_ADMIN`. `/auth/me`,
  login and register return `role`.
- **Super admin bootstrap (env):** `SUPERADMIN_EMAIL`, `SUPERADMIN_PASSWORD`,
  `SUPERADMIN_NAME`. Seeded idempotently on startup.
- **Admin API:** `POST/GET /admin/gym-admins` (super admin creates/lists gym
  admins), `GET /admin/gyms`, `GET /admin/me`.
- **Gyms (admin):** creation and machine management require the gym owner.
  `POST /gyms`, `POST /gyms/{id}/machines`,
  `PATCH /gyms/{id}/machines/{machine_id}`,
  `DELETE /gyms/{id}/machines/{machine_id}` (204), `GET /gyms/{id}/qr.png`.
  Machine `purpose`/`weight_factor` are inferred by the AI from the machine name
  (`syncfit-ai` `analyze_machine`) on creation.
- **Gyms (athlete):** `POST /gyms/join {code}` (idempotent), `GET /gyms/joined`
  (joined gyms with their machines resolved **live**), `POST /gyms/{id}/activate`,
  `DELETE /gyms/{id}/leave` (204). Machines are never copied into the profile;
  the membership is a `(profile_id, gym_id)` pair and `profiles.active_gym_id`
  marks the active one. See the "Applied in the gym feature" note under
  **Data Structures**.
- **AI-first symptoms:** no keyword blocking; only an absolute contraindication
  yields a gentle, still-active routine; `k_load` is preserved.
- Example: super admin creates `nico` (Asgard) and `daniel` (Valhalla); each gym
  admin creates their own gym(s) and manages machines.
