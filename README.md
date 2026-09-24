# SyncFit Backend

Asynchronous application server of SyncFit Edge. Persists data, ingests continuous telemetry, orchestrates the numerical core and the reasoning layer, and serves the frontend.

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

## Related repositories

- [`syncfit-contracts`](../syncfit-contracts) — request/response schemas.
- [`syncfit-core`](../syncfit-core) — deterministic engine.
- [`syncfit-ai-reasoning`](../syncfit-ai-reasoning) — reasoning layer.
- [`syncfit-hardware`](../syncfit-hardware) — telemetry source.
- [`syncfit-frontend`](../syncfit-frontend) — client.

All code, comments, documentation and commits in this repository are written in English.

## Context for a new session

**What it is.** FastAPI server: auth, onboarding, telemetry, routines, catalog,
supplements, sharing. Reuses core/simulator/ai.

**Stack.** Python 3.11+, FastAPI, SQLAlchemy (via syncfit-database), PyJWT,
OpenAI SDK (optional reasoning).

**Run.** `uvicorn app.main:app --reload --port 8000`. Config from `.env`
(`SYNCFIT_DATABASE_URL`, `BACKEND_SECRET_KEY`, `BACKEND_CORS_ORIGINS`,
`BACKEND_CORS_ORIGIN_REGEX`). CORS allows localhost any port (regex).

**Endpoints (`/api/v1`).** `auth/register|login|me`; `profiles/me` (GET/PUT),
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


## Roles, super admin and gyms

- **Roles** on `users.role`: `ATHLETE`, `GYM_ADMIN`, `SUPER_ADMIN`. `/auth/me`,
  login and register return `role`.
- **Super admin bootstrap (env):** `SUPERADMIN_EMAIL`, `SUPERADMIN_PASSWORD`,
  `SUPERADMIN_NAME`. Seeded idempotently on startup.
- **Admin API:** `POST/GET /admin/gym-admins` (super admin creates/lists gym
  admins), `GET /admin/gyms`, `GET /admin/me`.
- **Gyms:** creation and machine management require `require_gym_admin`
  (`POST /gyms`, `POST /gyms/{id}/machines`, `GET /gyms/{id}/qr.png`). Athletes
  join with `POST /gyms/join {code}`. Machine `purpose`/`weight_factor` are
  inferred by the AI from the machine name (`syncfit-ai` `analyze_machine`).
- **AI-first symptoms:** no keyword blocking; only an absolute contraindication
  yields a gentle, still-active routine; `k_load` is preserved.
- Example: super admin creates `nico` (Asgard) and `daniel` (Valhalla); each gym
  admin creates their own gym(s) and manages machines.
