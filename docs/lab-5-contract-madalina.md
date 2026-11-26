# Lab 5 — Mădălina's parts: endpoints, data formats and verification

The team contract is [lab-5-conventions.md](lab-5-conventions.md). This page lists what Mădălina's services added for Lab 5: every new endpoint and its request and response formats, and how it was verified. Errors keep the team format `{"code", "message", "request_id", "details"}`.

| Component | Repository | Version | Image |
| --- | --- | --- | --- |
| API Gateway | [MadalinaDev/gateway-service](https://github.com/MadalinaDev/gateway-service) | `0.6.0` | `madalina060504/tamagotchi-gateway-service:0.6.0` |
| Message broker | [MadalinaDev/message-broker](https://github.com/MadalinaDev/message-broker) | `0.6.0` | `madalina060504/tamagotchi-message-broker:0.6.0` |
| User Management | [MadalinaDev/user-management-service](https://github.com/MadalinaDev/user-management-service) | `0.6.0` | `madalina060504/tamagotchi-user-management-service:0.6.0` |
| Map | [MadalinaDev/map-service](https://github.com/MadalinaDev/map-service) | `0.6.0` | `madalina060504/tamagotchi-map-service:0.6.0` |
| ETL service (new) | [MadalinaDev/etl-service](https://github.com/MadalinaDev/etl-service) | `0.6.0` | `madalina060504/tamagotchi-etl-service:0.6.0` |
| Database image (new) | this repository, [db/ha](../db/ha) | `0.6.0` | `madalina060504/tamagotchi-postgres-ha:0.6.0` |

## API Gateway `0.6.0` (grades 6, 7 and 9)

| Method and path | Who | Answer |
| --- | --- | --- |
| `DELETE /api/v1/users/me` | the signed-in user | `202` Saga; `Location: /api/v1/sagas/{saga_id}`; `X-Saga-Created: true` (or `false`: this account's deletion was already running) |
| `GET /api/v1/sagas/{saga_id}` | the saga's subject, or an admin | `200` Saga; `404 SAGA_NOT_FOUND` for anyone else |
| `GET /api/v1/admin/sagas?type=&status=&limit=` | admin | `200 {"sagas": [Saga], "types": ["account-deletion"]}` |
| `GET /api/v1/admin/cache` | admin | `200` CacheOverview |
| `GET /api/v1/admin/cache/locate?key=` | admin | `200 {"key", "ring_position", "node", "ttl_seconds"}` |
| `GET /api/v1/admin/cache/simulation?keys=10000&add=&remove=&vnodes=` | admin | `200` Simulation; `400` when the keys aren't 1–50,000, the vnodes aren't 1–1,000, or `remove` isn't a node |
| `DELETE /api/v1/admin/cache` | admin | `200 {"flushed": {"cache-1": true, "cache-2": true, "cache-3": true}}` |

**Cached routes** (the allowlist is in the [conventions](lab-5-conventions.md#42-what-the-gateway-caches)) also answer:

| Header | Value |
| --- | --- |
| `X-Cache` | `HIT`, `MISS` or `BYPASS` |
| `X-Cache-Node` | the node the ring chose, for example `cache-2` |
| `Age` | seconds since the answer was stored (on a hit) |

- **Bypassing the cache:** an admin's `X-Cache-Bypass: true` skips it. A client's `Cache-Control` is ignored.
- **A token whose account is being deleted** gets `401 ACCOUNT_DISABLED`.

**Saga** (the same document the broker returns):

```json
{
  "saga_id": "8eb37a7d-19a4-47d6-b161-a30b1f67fb9c",
  "type": "account-deletion",
  "description": "Deletes a user's account: User Management and Map, two databases",
  "subject": "760675d8-801e-4cb9-be25-3e1941421b49",
  "status": "completed",
  "current_step": null,
  "attempts": 0,
  "started_by": "760675d8-801e-4cb9-be25-3e1941421b49",
  "request_id": "5678e68d-bca0-492a-9aa7-65208b79f7d0",
  "last_error": null,
  "created_at": "2026-11-26T08:20:28.543Z",
  "updated_at": "2026-11-26T08:20:28.763Z",
  "finished_at": "2026-11-26T08:20:28.762Z",
  "steps": [
    {
      "index": 0, "name": "deactivate-account", "service": "user-management", "kind": "compensatable",
      "status": "succeeded", "attempts": 1, "compensation_attempts": 0,
      "replica": "user-management-f0d9dc01d366", "last_error": null,
      "started_at": "2026-11-26T08:20:28.551Z", "finished_at": "2026-11-26T08:20:28.586Z", "compensated_at": null
    }
  ]
}
```

| Field | Values |
| --- | --- |
| `status` | `running`, `compensating`, `completed`, `compensated` (every completed step undone) or `failed` (an operator must look) |
| `current_step` | the step in progress while the saga runs; `null` when it has finished |
| `steps[].kind` | `compensatable`, `pivot` or `retriable` |
| `steps[].status` | `pending`, `running`, `succeeded`, `failed`, `compensating` or `compensated` |
| `last_error` | the reason for the last retry, or for the compensation, for example `hide-from-map: gave up after 33 s: 503 NO_REPLICA: …` |

**CacheOverview:**

```json
{
  "algorithm": "consistent hashing: MD5 of the key, 64-bit ring, virtual nodes",
  "vnodes": 160,
  "nodes": [
    {"node": "cache-1", "address": "cache-1:6379", "up": true, "skipped": false, "keys": 1,
     "ring_share_percent": 35.33, "hits": 309, "misses": 50, "hit_ratio": 0.861, "sets": 48, "errors": 0}
  ],
  "rules": [{"service": "package-registry", "path": "^/api/v1/packages$", "ttl_seconds": 60, "scope": "user"}]
}
```

`skipped` means the node failed less than 10 s ago and the ring passes over it.

**Simulation** (`keys`, `vnodes`, `nodes_before`, `nodes_after`, `ideal_moved_percent`, and one block per algorithm):

```json
{
  "consistent_hashing": {
    "moved": {"keys": 12640, "percent": 25.28},
    "distribution_after": {"cache-1": {"keys": 12825, "percent": 25.65}},
    "imbalance_percent": 1.93,
    "imbalance_percent_with_1_point_per_node": 39.34
  },
  "modulo": {"moved": {"keys": 37645, "percent": 75.29}, "distribution_after": {}},
  "redis_cluster_slots": {"moved": {"keys": 12450, "percent": 24.9}, "slots_moved": 4096, "distribution_after": {}}
}
```

The gateway's settings are `CACHE_NODES`, `CACHE_VNODES` (160), `CACHE_TIMEOUT_MS` (250), `CACHE_DOWN_MS` (10000) and `AUTH_CACHE_SECONDS` (300).

## Message broker `0.6.0` (grades 6 and 9)

| Method and path | Who | Answer |
| --- | --- | --- |
| `POST /v1/sagas` `{"type": "account-deletion"}` | the gateway for a user (`X-Gateway-Secret` + `X-Auth-User-Id`) | `202` Saga, `Location: /v1/sagas/{id}`, `X-Saga-Created` |
| `POST /v1/sagas` `{"type": "account-deletion", "user_id": "<uuid>"}` | the operator (`Bearer BROKER_ADMIN_TOKEN`) or an admin user | `202` Saga for that account; `403` for a non-admin |
| `GET /v1/sagas/{id}` | the subject or an admin | `200` Saga, else `404 SAGA_NOT_FOUND` |
| `GET /v1/sagas?type=&status=&subject=&limit=` | an admin | `200 {"sagas", "types"}`; `403` otherwise |

- **Errors:**
  - `400 UNKNOWN_SAGA` for an unknown type;
  - `400 INVALID_REQUEST` when no user is named;
  - `401` without credentials.
- **User lookups:** `GET /internal/v1/users/{id}` on User Management is answered from the cache for 60 s, over gRPC `Broker.Call` and HTTP `/internal` alike. Answers carry `X-Broker-Cache: HIT | MISS`, and a hit has `X-Broker-Transport: cache`.
- **Status and metrics:**
  - `GET /status` adds `"sagas": {"completed": 12, "compensated": 2}` and `"cache": {"nodes": 3}`;
  - `/metrics` adds `broker_sagas_total{type,outcome}`, `broker_saga_steps_total{type,step,outcome}` and `broker_user_lookup_cache_total{result}`.
- **Breakers:** a replica's `503 DEPENDENCY_UNAVAILABLE` no longer counts against its breaker ([conventions, section 7](lab-5-conventions.md#7-circuit-breakers-and-failing-dependencies-amends-lab-4-section-5)).
- **Settings:**
  - the cache: `CACHE_NODES`, `CACHE_VNODES`, `CACHE_TIMEOUT_MS`, `CACHE_DOWN_MS`, `USER_CACHE_SECONDS` (60);
  - the sagas: `SAGA_STEP_TIMEOUT_MS` (30000), `SAGA_ATTEMPT_TIMEOUT_MS` (4500), `SAGA_RETRY_MAX_MS` (8000).

## User Management `0.6.0` (grade 9)

**The steps of the account-deletion saga** (only `X-Service-Name: message-broker`, with `Idempotency-Key`):

| Method and path | Does | Refuses |
| --- | --- | --- |
| `POST /internal/v1/sagas/account-deletion/{user_id}/deactivate` | status `deactivated`, every refresh session revoked | `404 USER_NOT_FOUND`, `409 ACCOUNT_DELETED` |
| `POST /internal/v1/sagas/account-deletion/{user_id}/reactivate` | status `active` again (the compensation) | `409 ACCOUNT_DELETED` (erased accounts can't come back) |
| `POST /internal/v1/sagas/account-deletion/{user_id}/erase` | username `deleted~<id>`, email `<id>@deleted.invalid`, display name *Deleted user*, an unusable password, not an admin; friendships, enemy markers and sessions deleted; wallets kept | `409 ACCOUNT_ACTIVE` (it was reactivated) |

- **Request body:**
  - `{"saga_id": "<uuid>", "type": "account-deletion", "subject": "<user_id>", "step": "<name>", "action": "action" | "compensation"}`;
  - `422 SUBJECT_MISMATCH` when `subject` isn't the user in the path.
- **Answer:**
  - `{"user_id", "saga_id", "step", "status": "active" | "deactivated" | "deleted", "changed": true, "removed": {"refresh_sessions": 2}}`;
  - `changed: false` when the step had already been applied.
- **Elsewhere:**
  - login answers `401 ACCOUNT_DISABLED` for an account that isn't active, and so does refresh;
  - an erased account is `404` on every profile lookup;
  - a database that can't be reached answers `503 DEPENDENCY_UNAVAILABLE` with `Retry-After: 2`.
- **Migration** `20261125000000_account_deletion`: enum `user_status`, plus `users.status`, `deactivated_at` and `deleted_at`.

## Map `0.6.0` (grade 9)

| Method and path | Does |
| --- | --- |
| `POST /internal/v1/sagas/account-deletion/{user_id}/hide` | the user is on nobody's map (`hidden_users`), and their proximity pairs are re-armed |
| `POST /internal/v1/sagas/account-deletion/{user_id}/unhide` | the compensation: shown again (a purged user stays hidden) |
| `POST /internal/v1/sagas/account-deletion/{user_id}/purge` | the location and proximity pairs deleted; the hidden row stays as a tombstone |

- **Request and answer:** the same request body and guard as User Management. The answer is `{"user_id", "saga_id", "step", "hidden", "changed", "removed": {"locations": 1, "proximity_pairs": 2}}`.
- **Hidden users:**
  - a hidden user's `PUT /api/v1/map/location` answers `409 ACCOUNT_BEING_DELETED`;
  - nearby detection, friends and enemies, and strangers all leave hidden users out.
- **Migration** `20261125000000_hidden_users`. Database connection errors answer `503 DEPENDENCY_UNAVAILABLE`, as in User Management.

## ETL service `0.6.0` (grade 4)

| Method and path | Who | Answer |
| --- | --- | --- |
| `GET /health` | anyone | `{"status": "ok"}` |
| `GET /status` | anyone | version, schedule (`interval_seconds`, `running`, `next_run_at`), the source (`postgres:5433`, fallback 5432, `etl_reader`), `checks.warehouse`, the last run |
| `GET /metrics` | anyone | `etl_runs_total{trigger,status}`, `etl_run_duration_seconds`, `etl_warehouse_rows{table}`, `etl_rows_extracted{extract}`, `etl_extract_errors_total{extract}`, `etl_last_success_timestamp_seconds`, `etl_source_reads_total{endpoint}` |
| `GET /v1/runs?limit=20`, `GET /v1/runs/{id}` | anyone | `{"runs": [Run]}`, Run |
| `POST /v1/runs` | `Bearer ETL_ADMIN_TOKEN` | runs now; `200` Run; `409 RUN_IN_PROGRESS`; `503 WAREHOUSE_UNAVAILABLE` |
| `GET /v1/warehouse` | anyone | `{"schema": "dw", "tables": {table: rows}, "dimensions", "facts", "views", "reports", "last_successful_run"}` |
| `GET /v1/reports`, `GET /v1/reports/{name}?limit=50&days=30` | `Bearer ETL_ADMIN_TOKEN` | `{"report", "description", "rows", "generated_at"}` |

**Reports** (one per warehouse view):
- `daily-activity`;
- `players`;
- `packages`;
- `raids`;
- `notifications`;
- `guilds`;
- `map`, from `fact_map_snapshot`.

Without `ETL_ADMIN_TOKEN` the operator routes answer `403 DISABLED`.

**Run:**

```json
{
  "run_id": 46, "trigger": "schedule", "status": "succeeded",
  "started_at": "2026-11-26T08:31:47.665Z", "finished_at": "2026-11-26T08:31:48.047Z", "duration_ms": 377,
  "source": {"user_management_db": "postgres:5433", "map_db": "postgres:5433"},
  "extracted": {"users": 13, "battles": 2, "notifications": 23},
  "loaded": {"dim_user": 13, "dim_date": 330, "fact_battle": 2, "fact_map_snapshot": 45},
  "kept": [],
  "errors": {}
}
```

| Field | Values |
| --- | --- |
| `trigger` | `startup`, `schedule` or `manual` |
| `status` | `running`, `succeeded`, `partial` (an extract failed; its tables kept the previous rows, listed in `kept`) or `failed` (the load failed; the warehouse is unchanged) |
| `source` | the endpoint each database was read from (`postgres:5432` means no replica answered) |

**Settings:** `SOURCE_DB_HOST`, `SOURCE_DB_PORT` (5433), `SOURCE_DB_FALLBACK_PORT` (5432), `SOURCE_DB_USER`, `SOURCE_DB_PASSWORD`, `WAREHOUSE_DB_*`, `ETL_INTERVAL_SECONDS` (60 in Compose), `ETL_RUN_ON_START`, `ETL_ADMIN_TOKEN`, `ETL_RUN_RETENTION_DAYS` (7).

## The database image `0.6.0` (grade 5)

[db/ha](../db/ha) builds `madalina060504/tamagotchi-postgres-ha`:
- **Contents:** Postgres 16 with PostGIS 3 from the PostgreSQL apt repository, plus Patroni 4.0.4 (etcd v3).
- **Configuration:** [patroni.yml](../db/ha/patroni.yml) sets the timings, synchronous replication, `pg_rewind` and replication slots.
- **Entrypoint:** [entrypoint.sh](../db/ha/entrypoint.sh) checks the passwords.
- **Bootstrap:** [post-bootstrap.sh](../db/ha/post-bootstrap.sh) creates the team's databases and `etl_reader`.
- **Router:** [haproxy.cfg](../db/ha/haproxy.cfg).
- **Stop signal:** the image stops with `SIGTERM`, so Patroni hands the leader lock over at once (the postgres base image's `SIGINT` left it held until it expired).

## Verification (2026-11-26, local stack of 34 containers)

- **Unit and integration tests:**
  - gateway: 151;
  - broker: 57;
  - User Management: 69;
  - Map: 64;
  - ETL service: 22, including 5 against a real Postgres (source databases shaped like the team's, a warehouse, failing extracts, the fallback to the leader).
- **Postman:**
  - every Lab 1–4 collection passes on the Lab 5 stack (480 assertions);
  - [lab-5.postman_collection.json](../postman/lab-5.postman_collection.json): 44 requests, 89 assertions, 0 failures.
- **Failover, writing through the gateway every 250 ms:**
  - a stopped leader hands over in 2.3 s, and about 5 s of writes fail;
  - a crashed leader is replaced after 22.5 s, and writes fail for 24 s;
  - no acknowledged write was lost, and the old leader rejoined as a replica within 8 s;
  - before the fixes in [conventions, sections 3.3 and 7](lab-5-conventions.md#33-what-a-service-does-during-a-failover), the same crash cost 39 s and evicted both User Management replicas.
- **Compensation:** with Map stopped, the deletion saga retried `hide-from-map` 8 times over 33 s, then reactivated the account. The saga ended `compensated`, and the player logged in again.
- **Grafana:** every panel of the Lab 5 dashboard returns data, and the Warehouse data source connects as `dw_reader`.

## Open items

- **Publishing:**
  - merge the five repositories so their CI publishes the `0.6.0` images;
  - create `MadalinaDev/etl-service` and add it as a submodule;
  - add the `DOCKERHUB_USERNAME` and `DOCKERHUB_TOKEN` secrets to this repository (database image) and to `etl-service`.
- **The other owners (optional):** answer `503 DEPENDENCY_UNAVAILABLE` on database connection errors ([conventions, section 11](lab-5-conventions.md#11-what-each-owner-does)).
