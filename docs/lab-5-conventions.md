# Lab 5 conventions — sharding and replication

Lab 5 ("Sharding and Replication") adds the platform's data layer:
- a replicated database cluster with automatic failover;
- a sharded cache;
- a data warehouse with an ETL service;
- distributed transactions as sagas coordinated by the message broker.

This page is the team contract: what changed, and what it means for every service.

**Status (2026-11-26).** Everything below is implemented and verified on the full local stack. See [lab-5-contract-madalina.md](lab-5-contract-madalina.md) for the endpoints, data formats and test results, and [lab-5-demo.md](lab-5-demo.md) for the demo. The other services need no code change (section 11).

## 1. The requirements and where they are met

| Grade | Requirement | Where | Owner |
| --- | --- | --- | --- |
| 2 | Architecture diagram with the forgotten components | [README](../README.md#architecture): the diagrams and the [system map](diagrams/system-map.html) now show the guild-ws proxy, the alert channels, the broker's SQLite store, the database router, etcd and Firebase | Mădălina |
| 3 | Data warehouse, ETL and cache in the diagram | Same diagrams; system map views "Cache" and "Replication and warehouse" | Mădălina |
| 4 | A data warehouse database in Docker Compose; an ETL job from the other databases | `warehouse` (Postgres, star schema) and [MadalinaDev/etl-service](https://github.com/MadalinaDev/etl-service) (section 5) | Mădălina |
| 5 | Database replication with failover, at least 2 replicas | Patroni cluster `pg-1`, `pg-2`, `pg-3` (1 leader + 2 replicas) behind the router `postgres` (section 3) | Mădălina |
| 6 | Cache for common GETs and for authentication data | Gateway response cache and token cache; broker user-lookup cache (section 4) | Mădălina |
| 7 | Research consistent hashing; shard the cache with it | Three Redis nodes on a consistent-hash ring ([research and comparison with Redis Cluster](lab-5-consistent-hashing.md)) | Mădălina |
| 8–9 | Distributed transactions; long-running sagas instead of 2PC, coordinated by the gateway or the broker | Account-deletion saga, coordinated by the message broker (section 6) | Mădălina |
| 10 | Postman, diagram and Docker Hub up to date; new endpoints and data formats in the README | [postman/lab-5.postman_collection.json](../postman/lab-5.postman_collection.json); README; images `0.6.0` | Mădălina |

## 2. Components and ports

| Compose service | Image | Ports | What |
| --- | --- | --- | --- |
| `etcd` | `quay.io/coreos/etcd:v3.5.17` | 2379 (internal) | Patroni's leader lock and settings |
| `pg-1`, `pg-2`, `pg-3` | `madalina060504/tamagotchi-postgres-ha:0.6.0` (Postgres 16 + PostGIS + Patroni, built from [db/ha](../db/ha)) | 5432, 8008 (internal) | The database cluster |
| `postgres` | `haproxy:3.0.5-alpine` | **5432** leader, **5433** replicas, 7000 stats page, 8008 Patroni API | The database router; the old hostname |
| `cache-1`, `cache-2`, `cache-3` | `redis:7.4.1-alpine` | 6379 (internal) | The sharded cache |
| `warehouse` | `postgres:16.14-alpine` | 5434 → 5432 | The data warehouse |
| `etl-service` | `madalina060504/tamagotchi-etl-service:0.6.0` | 8091 | The ETL job and its API |

The gateway, message broker, User Management, Map, Monster Raid and Package Registry are `0.6.0`. Every other image is unchanged (`0.5.0`).

## 3. The database cluster: replication and failover (grade 5)

### 3.1 What changes for a service: nothing

Services still connect to `postgres:5432` with their own database, user and password. `postgres` is now a router that always forwards to the cluster's current leader. The databases, owners and passwords are created as before by [db/init/01-create-databases.sh](../db/init/01-create-databases.sh), now once, when the cluster is first created (Patroni's `post_bootstrap`). Port 5433 reaches the replicas (read-only). Only the ETL service uses it.

### 3.2 How it works

- **Patroni** runs next to Postgres on every node and keeps a **leader lock** in etcd. The leader renews it every 2 s (`loop_wait`). If the lock isn't renewed for 20 s (`ttl`, Patroni's minimum), the replicas promote one of themselves.
- **Synchronous replication** (`synchronous_mode: true`): one replica, the *synchronous standby*, confirms every commit before the client gets its answer, and it is the one promoted. A crash therefore loses no acknowledged write. If no replica is left, the leader keeps accepting writes alone (non-strict mode). A replica more than 1 MB behind is never promoted.
- **The router** asks every node's Patroni REST API once a second: `GET /primary` for port 5432 and `GET /replica` for 5433. When a node stops being the leader, HAProxy cuts its client connections (`on-marked-down shutdown-sessions`), so the services reconnect to the new leader instead of writing to a demoted node.
- **The old leader rejoins** as a replica on its own, rewinding diverged history with `pg_rewind`.

Measured on the full stack, writing through the gateway every 250 ms:

| Event | New leader after | Writes failing for | Data lost |
| --- | --- | --- | --- |
| Leader stopped (`docker compose stop pg-x`: a planned switchover) | 2.3 s | about 5 s (2 requests) | none |
| Leader crashed (`docker kill`, SIGKILL) | 22.5 s (the lock's 20 s TTL) | 24 s | none |
| Old leader started again | rejoins as a replica in 4–8 s | — | — |

### 3.3 What a service does during a failover

For a few seconds (up to about 24 s after a crash) its queries fail. A service should then:

1. **Answer `503 DEPENDENCY_UNAVAILABLE` with `Retry-After`**, not `500`. The broker then doesn't count the failure against the replica (section 7). Without this, a database failover trips the broker's breakers and evicts every replica that got traffic. Service Discovery then quarantines them for 30 s, which nearly doubled the outage in our first test.
2. **Reconnect.** Prisma, pgx and the other drivers open new connections on the next query; nothing to configure.

User Management and Map (`0.6.0`) do both. Prisma's connection errors (`P1001`, `P1002`, `P1008`, `P1017`, `P2024`, and closed connections) become `503 DEPENDENCY_UNAVAILABLE` with `Retry-After: 2`.

Monster Raid and Package Registry (`0.6.0`) do the same ([lab-5-contract-sabina.md](lab-5-contract-sabina.md)). They also set Prisma's `connect_timeout=2` and `pool_timeout=3`, under the 5 s task timeout. With Prisma's defaults (5 s and 10 s), a connection opened during a planned switchover waited until the task timeout, and the request answered `504 TASK_TIMEOUT`, which the broker counts.

### 3.4 Operating the cluster

```sh
curl -s localhost:8008/cluster                     # members, roles, lag (any node's Patroni API)
open http://localhost:7000                         # the router's live status page
docker compose exec pg-1 /opt/patroni/bin/patronictl -c /etc/patroni/patroni.yml list
docker compose exec pg-1 /opt/patroni/bin/patronictl -c /etc/patroni/patroni.yml switchover --leader pg-1 --candidate pg-2 --force
```

Patroni's read endpoints are open (the router and Prometheus use them). Every change (`switchover`, `restart`, `PATCH /config`) needs user `patroni` and `PATRONI_API_PASSWORD`. `patronictl` inside a node already has them. The cluster's settings live in etcd; `db/ha/patroni.yml` only seeds a new cluster.

## 4. The cache (grades 6 and 7)

### 4.1 Nodes and placement

Three independent Redis nodes (64 MB each, least-recently-used eviction, no persistence). The gateway and the broker place every key on one of them with **consistent hashing**:
- MD5 positions on a 64-bit ring;
- 160 virtual nodes per node;
- node names from `CACHE_NODES`, the same Compose anchor for both.

A node that fails is skipped for 10 s and its keys go to the next node on the ring. The cache never fails a request: any error, or a 250 ms timeout, is a miss. The algorithm, the measurements and the comparison with Redis Cluster are in [lab-5-consistent-hashing.md](lab-5-consistent-hashing.md).

### 4.2 What the gateway caches

Only successful GETs (`200`) on this allowlist are cached:

| Route | Service | TTL | Cached for |
| --- | --- | --- | --- |
| `GET /api/v1/packages`, `/api/v1/packages/{id}` | Package Registry | 60 s | each user (answers depend on the caller) |
| `GET /api/v1/packages/{id}/care-definitions/{version}` | Package Registry | 300 s | each user |
| `GET /api/v1/raid-definitions`, `/api/v1/raid-definitions/{id}/versions/{v}` | Package Registry | 60 / 300 s | each user |
| `GET /api/v1/battle-rules` | Battle | 300 s | everyone (shared) |
| `GET /api/v1/tamagotchi-types` | Tamagotchi | 300 s | everyone (shared) |
| `GET /api/v1/users/me`, `/api/v1/users/{id}` | User Management | 60 s | each user |

**Response headers:**
- `X-Cache: HIT | MISS | BYPASS`;
- `X-Cache-Node: cache-2` (where the ring put the key);
- `Age` (seconds since the answer was stored).

The gateway ignores a client's `Cache-Control`. Postman sends `no-cache` on every request, and no client may force misses on the services. An administrator can ask for a fresh answer with `X-Cache-Bypass: true`.

### 4.3 Staying fresh: generation counters

Every cached answer's key carries the generation of its service (`gen:<service>`). After any successful write the gateway forwards to a service (`POST`, `PUT`, `PATCH` or `DELETE` with a 2xx answer), it increments that counter. From then on every cached answer of that service is a miss and gets fetched fresh; the old keys expire on their own.

**For owners:** a change that does *not* go through the gateway (an internal call from another service, an event) can show stale data for up to the TTL. That's why the allowlist holds only data that changes through its own service's public writes. Anyone adding a route to the list should check the same.

### 4.4 Authentication data

| Key | TTL | What |
| --- | --- | --- |
| `auth:token:<sha256>` | until the token expires, at most 300 s | A verified JWT: its signature, issuer, audience and expiry aren't checked again |
| `auth:jwks` | 300 s | User Management's public keys, shared by every gateway instance (an unknown key ID still fetches fresh keys) |
| `auth:revoked:<user id>` | 24 h | Set by the broker while that account is being deleted: the gateway answers `401 ACCOUNT_DISABLED` |

### 4.5 Between services

The broker caches User Management's answers to `GET /internal/v1/users/{id}` for 60 s. The key carries `gen:user-management`, so a write to User Management makes them stale too. It does this for gRPC `Broker.Call` and HTTP `/internal` calls alike, and marks the answer `X-Broker-Cache: HIT | MISS` (with `X-Broker-Transport: cache` on a hit).

## 5. The data warehouse and the ETL service (grades 3 and 4)

### 5.1 What is read from each database

The ETL service reads every database every 60 s:
- from a replica (`postgres:5433`), as `etl_reader`, which may only read (`pg_read_all_data`);
- each database in one read-only, repeatable-read transaction, so its rows form one consistent snapshot;
- from the leader (5432) only when no replica answers.

| Database | Tables and columns read |
| --- | --- |
| `user_management_db` | `users` (id, username, display_name, is_admin, created_at, status), `friendships`, `wallet_entries` + `wallet_operations` |
| `registry_db` | `packages` (id, name, status, app_version, developer_id, created_at), `registrations` |
| `tamagotchi_db` | `tamagotchis` (id, owner, package, name, combat_type, level, xp, created_at), `battle_results` |
| `battle_db` | `battles` (id, players, state, created_at) and the number and damage of their `battle_actions` |
| `guild_db` | `guilds`, `guild_members`, `guild_messages` (author, time and length; never the text) |
| `notification_db` | `notifications` (recipient, type, resource type, read and created times) |
| `raid_db` | `raids` (guild, state, hp, max_hp, rewards, times, monster name), `raid_participants` |
| `map_db` | counts only: users with a location, users sharing now, proximity pairs (no coordinates) |

**For owners:** renaming or dropping one of these columns makes that extract fail. The run is then recorded as `partial`, the affected warehouse tables keep the previous run's rows, and the error shows in `GET :8091/v1/runs` and in Grafana. Tell the ETL's owner, or update `app/sources.py`, when you change them.

### 5.2 The star schema (`dw`)

- **Dimensions** (rows keep their surrogate key across runs; a row the service no longer has stays, marked `in_source = false`):
  - `dim_date`;
  - `dim_user`;
  - `dim_package`;
  - `dim_pet`;
  - `dim_guild`.
- **Facts**, rebuilt on every run:
  - `fact_battle`;
  - `fact_raid`;
  - `fact_raid_participation`;
  - `fact_wallet_entry`;
  - `fact_friendship`;
  - `fact_notification`;
  - `fact_guild_membership`;
  - `fact_guild_message`;
  - `fact_registration`.
- **`fact_map_snapshot`** gains one row per run: history the Map database doesn't keep.
- **Views:**
  - `v_daily_activity`;
  - `v_player_stats`;
  - `v_package_popularity`;
  - `v_raid_outcomes`;
  - `v_notification_types`;
  - `v_guild_activity`.

A fact that names a user, pet, package or guild the warehouse has never seen gets an *inferred* placeholder member, filled in by the next extract, so every fact joins its dimensions.

Each run loads everything in **one transaction**. Readers (Grafana, the reports) see the previous run's data until it commits, then all of the new run's data at once. No email address, password, message text, device token or coordinate is copied.

## 6. Distributed transactions: the account-deletion saga (grades 8 and 9)

### 6.1 Why a saga and not two-phase commit

Deleting an account changes two databases: User Management's (the account, its friendships and sessions) and Map's (the location and proximity pairs). Two-phase commit would need prepared transactions in every database (`max_prepared_transactions` is 0 by default). It would hold locks in both services until the coordinator decides, and a coordinator that fails between the phases leaves both blocked.

A **saga** runs one local transaction per service, in order. If a step fails for good, it undoes the completed ones with **compensations**, in reverse order. Nothing is locked across services. In exchange the system is briefly inconsistent while the saga runs, which section 6.5 handles.

### 6.2 The steps

| # | Step | Service | Action | Compensation | Kind |
| --- | --- | --- | --- | --- | --- |
| 1 | `deactivate-account` | User Management | Status `deactivated`, every session revoked; the broker also sets `auth:revoked:<user>` | `reactivate` | compensatable |
| 2 | `hide-from-map` | Map | The user is on nobody's map and can't send locations; their proximity pairs are re-armed | `unhide` | compensatable |
| 3 | `erase-account` | User Management | Personal data overwritten (username, email, display name, password), friendships, enemy markers and sessions deleted. The anonymous row stays, because the wallet ledger refers to it | — | **pivot** |
| 4 | `purge-map-data` | Map | The location and proximity pairs deleted; a tombstone keeps the user hidden | — | retriable |

**How a step ends:**
- *Compensatable* steps are undone when a later step fails, until the pivot succeeds.
- After the pivot nothing is undone: the *retriable* step is retried until it succeeds.
- If a participant refuses a step after the pivot, or refuses a compensation, the saga ends `failed` and an operator looks at it.

### 6.3 The participant protocol

The broker calls every step and compensation as:

```
POST /internal/v1/sagas/{type}/{subject}/{action}
X-Service-Name: message-broker      (set by the broker itself; services can't forge it)
X-Gateway-Secret: …                 X-Request-Id: <the request that started the saga>
Idempotency-Key: <uuid5(saga, step, action)>
{"saga_id": "…", "type": "account-deletion", "subject": "<user id>", "step": "hide-from-map", "action": "action" | "compensation"}
```

A participant must:

- **accept only `message-broker`.** The saga paths aren't in the broker's route table, so another service can't even reach them through it.
- **be safe to repeat.** The same step can arrive twice when the broker stopped between the call and recording its result. Every step checks the state it starts from: deactivating an account that is already deactivated is a no-op, not an error. The `Idempotency-Key` also replays the stored answer.
- **answer with meaning:**
  - `2xx`: done;
  - `4xx`: refused, so the broker compensates, or fails the saga after the pivot;
  - `5xx`, `408`, `425` or `429`: try again later.

**How the broker retries:**
- It retries with back-off (0.5, 1, 2, 4, then every 8 s).
- A step still failing after 30 s (`SAGA_STEP_TIMEOUT_MS`) counts as refused.
- Each attempt has 4.5 s.

### 6.4 What the coordinator guarantees

- **Durable:** every saga and every step transition is written to the broker's SQLite file before the next call. A broker restart resumes every running saga where it stopped.
- **One deletion per account at a time:** a second request returns the running saga (`X-Saga-Created: false`).
- **Observable:** `GET /api/v1/sagas/{id}` (the subject or an admin) shows every step's status, attempts, replica and error. The broker logs `saga.*` events and exports `broker_sagas_total` and `broker_saga_steps_total`.

### 6.5 Isolation while the saga runs

The account is *semantically locked* from the first step:
- the gateway refuses the user's tokens (`auth:revoked:<user>`);
- User Management refuses logins and refreshes (`ACCOUNT_DISABLED`);
- Map shows the user to nobody.

Other users can still see the profile until the pivot, because the deletion may yet be compensated. After the pivot the profile is gone for everyone (`404`).

## 7. Circuit breakers and failing dependencies (amends Lab 4, section 5)

The broker still opens a replica's breaker after 3 failures in 17.5 s and evicts it, except for one kind of answer:

- **What doesn't count:** a `503` whose body has the team's code `DEPENDENCY_UNAVAILABLE`. That replica works; what it depends on (its database during a failover, or a service it calls) doesn't. Evicting it would only keep it away longer than its dependency.
- **What still happens:** such answers are rerouted to another replica, like any failure.
- **What still counts:** timeouts, connection errors, `500`, `502`, `504` and other `503`s (`TOO_MANY_CONCURRENT_TASKS`).

## 8. Monitoring

- **Prometheus** also scrapes `etl-service:8091` (runs, rows per warehouse table, extract errors) and every Patroni node (`pg-1..3:8008/metrics`: role, timeline, WAL positions).
- **Grafana** has a second provisioned dashboard, *Tamagotchi Go: database cluster, cache, sagas and warehouse (Lab 5)*:
  - the leader, the synchronous standby, the timeline and the replication lag;
  - cache hit ratios and operations per node;
  - saga outcomes and steps;
  - ETL runs;
  - SQL panels on the warehouse (data source *Warehouse*, read-only user `dw_reader`).

## 9. Configuration

New entries in `.env` (see [.env.example](../.env.example)), letters, digits and underscores only:

| Variable | Used by |
| --- | --- |
| `REPLICATION_PASSWORD` | the cluster's replication user |
| `PATRONI_API_PASSWORD` | Patroni REST API changes (user `patroni`) |
| `ETL_DB_PASSWORD` | `etl_reader`, created at bootstrap |
| `WAREHOUSE_DB_PASSWORD` | the warehouse owner, which the ETL loads with |
| `WAREHOUSE_READER_PASSWORD` | `dw_reader`, Grafana's read-only user |
| `ETL_ADMIN_TOKEN` | `POST /v1/runs` and `/v1/reports` on the ETL service (empty disables them) |

The gateway and the broker get `CACHE_NODES` from the same anchor. Their tuning variables are listed in their READMEs (`CACHE_*`, `AUTH_CACHE_SECONDS`, `USER_CACHE_SECONDS`, `SAGA_*`).

## 10. Postman and CI

- **Postman:** [postman/lab-5.postman_collection.json](../postman/lab-5.postman_collection.json) (generated by `postman/gen_lab5_collection.py`) walks the grades: 44 requests, 89 assertions. It needs `etl_admin_token`, `broker_admin_token` and `map_service_token` from `.env`.
- **The smoke workflow** builds the database image from the pull request's `db/ha`, starts the stack and runs every collection, including Lab 5's. Then [.github/smoke/failover.sh](../.github/smoke/failover.sh):
  1. crashes the leader;
  2. waits for a promotion;
  3. logs in a player registered before the crash, through the new leader;
  4. checks that the old leader rejoins as a replica.
- **[Publish the database image](../.github/workflows/postgres-ha-image.yml)** pushes `madalina060504/tamagotchi-postgres-ha:<db/ha/VERSION>` on merges to `main`.

## 11. What each owner does

- **Mădălina:** everything above. That covers the gateway, the broker, User Management, Map, the ETL service, the database image, Compose, monitoring, Postman and the diagrams.
- **Sabina:** Monster Raid and Package Registry `0.6.0` follow the recommendation below ([lab-5-contract-sabina.md](lab-5-contract-sabina.md)); their schemas keep the columns of section 5.1.
- **Everyone else:** no change is required, and the images stay `0.5.0`.
  - *Recommended:* answer `503 DEPENDENCY_UNAVAILABLE` with `Retry-After` when the database can't be reached, so a database failover doesn't get your replicas evicted (section 7).
  - *When you change your schema:* keep the columns in section 5.1 stable, or tell Mădălina.
