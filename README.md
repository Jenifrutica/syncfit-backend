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

## Related repositories

- [`syncfit-contracts`](../syncfit-contracts) — request/response schemas.
- [`syncfit-core`](../syncfit-core) — deterministic engine.
- [`syncfit-ai-reasoning`](../syncfit-ai-reasoning) — reasoning layer.
- [`syncfit-hardware`](../syncfit-hardware) — telemetry source.
- [`syncfit-frontend`](../syncfit-frontend) — client.

All code, comments, documentation and commits in this repository are written in English.
