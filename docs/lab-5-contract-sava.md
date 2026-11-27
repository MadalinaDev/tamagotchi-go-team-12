# Lab 5 — Sava's Battle and Tamagotchi

This page describes **tamagotchi-battle-service:0.6.0** and **tamagotchi-tamagotchi-service:0.6.0**, the Lab 5 versions of Battle and Tamagotchi (Go), and how they were verified.

- They follow the recommendation for every owner in the [Lab 5 conventions](lab-5-conventions.md) (sections 3.3, 7 and 11): while the database fails over, they answer `503 DEPENDENCY_UNAVAILABLE` instead of `500`, so the broker no longer evicts their replicas.
- They keep the columns the ETL reads (section 5.1) unchanged.
- Everything in the Lab 1–4 pages still applies unless this page says otherwise. Mădălina's parts are in [lab-5-contract-madalina.md](lab-5-contract-madalina.md).

Repositories:

- [Ekkusuu/battle-service](https://github.com/Ekkusuu/battle-service): #7, merged to `main` (`838ee25`).
- [Ekkusuu/tamagotchi-service](https://github.com/Ekkusuu/tamagotchi-service): #7, merged to `main` (`c562abf`).

CI publishes the `0.6.0` images from those commits, and the submodules point to them. Each README has a "Lab 5 — Database failover" section with the details.

`0.5.1` (Battle and Tamagotchi #6, Lab 4) came in between. It fixed the occasional heartbeat `EOF` to Service Discovery: the Discovery client opens a new connection for every call. `0.6.0` includes it.

## What changed

| | Battle | Tamagotchi |
| --- | --- | --- |
| Image | `ekkusuu/tamagotchi-battle-service:0.6.0` | `ekkusuu/tamagotchi-tamagotchi-service:0.6.0` |
| Database unreachable | `503 DEPENDENCY_UNAVAILABLE`, `Retry-After: 2` (was `500 INTERNAL_ERROR`) | `503 DEPENDENCY_UNAVAILABLE`, `Retry-After: 2` (was `500 INTERNAL_ERROR`) |
| gRPC `Deliver` during an outage | — (Battle subscribes to nothing) | `UNAVAILABLE`: the broker retries `battle.finished` later instead of dead-lettering it |
| Connection string | `connect_timeout=1` added unless `DATABASE_URL` sets it | same |
| Background work (outbox, sweeps, battle steps) | each database call has a 5 s deadline; an outage is a WARN and the next tick retries | same (outbox relay) |
| Request canceled by the caller | `499 REQUEST_CANCELED` (log `request.canceled`) | same (was `500` or `504`) |
| Log event | `db.unavailable` (WARN) | `db.unavailable` (WARN) |
| Routes, DTOs, schema, ports, environment | unchanged | unchanged |

## The answer during a failover

```http
HTTP/1.1 503 Service Unavailable
Retry-After: 2

{"code": "DEPENDENCY_UNAVAILABLE", "message": "The database is temporarily unavailable", "request_id": "…", "details": []}
```

The driver's error text names the database host and user, so it goes only to the log (`db.unavailable`), never into the answer.

**Which errors count as the database being unreachable.** Both services use `internal/dberr.IsOutage`, with the same rules:

| Error (pgx / `database/sql`) | Why it happens |
| --- | --- |
| `*pgconn.ConnectError`, also when `connect_timeout` ran out | No leader accepts connections yet. While none exists, the router accepts the TCP connection and nothing answers |
| `io.EOF`, `io.ErrUnexpectedEOF`, connection reset, broken pipe, `driver: bad connection`, `conn closed`, `closed pool` | The router cut the connection to the old leader (`on-marked-down shutdown-sessions`) |
| SQLSTATE class `08` | Connection exception |
| `57P01`, `57P02`, `57P03` | The server is shutting down, crashed, or not yet accepting connections |
| `25006` | Read-only transaction: a write that reached a node just demoted to replica |
| `53300` | Too many connections |
| A background call that ran past its 5 s deadline | A connection still hanging on the dead leader |

Every other error keeps its answer: a unique violation stays `409`, a bug stays `500`. When the request's own context is over, the answer is `499 REQUEST_CANCELED` or `504 TASK_TIMEOUT`, whatever the error looks like. Battle also never classes a failure of another service or of the broker as a database outage, even when it says "connection reset".

**Why `connect_timeout=1`.** The broker gives each attempt 2 s, and a timeout counts against the replica (section 7). The first failover run showed that a new connection opened during the promotion hangs until the broker gives up. The requests then failed as timeouts, and all four replicas were evicted, as with `0.5.0`. One second leaves time for the `503` inside the attempt.

**Why the background deadline.** In the same run, a Tamagotchi outbox dispatcher was still blocked opening a connection 89 s after the crash (`pgconn.connectOne ← database/sql.(*DB).conn ← ClaimOutbox`), long after the database was back, so it published nothing. Background contexts had no deadline. Every background database call is now bounded by 5 s: longer than the router's ~4 s cut, shorter than the 10 s and 30 s work leases.

## Idempotency after an outage (Tamagotchi)

Battle calls Tamagotchi's reservations and settlements with an `Idempotency-Key` and retries with the same key. Two cases blocked such a key for good:

- A `503` during a failover was stored as the key's answer, so every retry replayed the `503`.
- A claim left `pending`, because the database went away before the answer was stored, answered `409 IDEMPOTENCY_IN_PROGRESS` to every retry.

Now a `503` releases the claim instead of storing it, so the retry runs again. A pending claim older than 30 s is taken over by the next request with the same key (exactly once, also under concurrent retries). Battle already never stored a `5xx` for replay.

## Warehouse (section 5.1)

The ETL service reads these columns. All of them exist and are unchanged; no migration was added in Lab 5.

| Database | Query of `app/sources.py` |
| --- | --- |
| `tamagotchi_db` | `tamagotchis (pet_id, owner_id, package_id, name, combat_type, level, xp, created_at)`, `battle_results (battle_id, winner_id, loser_id, captured_pet_id, occurred_at)` |
| `battle_db` | `battles (battle_id, challenger_id, opponent_id, state, created_at)`, `battle_actions (battle_id, damage)` |

## Verification

### Tests

`go vet` and `go test ./...` pass in both repositories, with and without the Postgres suites. CI is green on both pull requests. The tests cover:

- **Classification:** which errors count as an outage, which don't, and wrapped errors.
- **Answers:** the `503` + `Retry-After: 2` answer, the `499` and `504` answers, and Tamagotchi's `Deliver` → `UNAVAILABLE`.
- **`connect_timeout`:** it is added to URL and key=value strings, and a value already set wins.
- **Background deadlines:** a tick whose store hangs is abandoned at the deadline and the loop goes on.
- **A real connection cut (Postgres):** the pool's connection is terminated with `pg_terminate_backend`, as the router does. The next query's error is an outage, and the one after it works on a new connection.
- **Idempotency (Tamagotchi):**
  - an outage answers `503` twice, and both requests run;
  - after recovery the retry succeeds, then it is replayed byte for byte;
  - a stale claim is taken over once by 8 concurrent requests.

### Failover runs

**The stack:**

- the whole Lab 5 Compose file: etcd, `pg-1`..`pg-3`, the router `postgres`, the broker, the gateway, Service Discovery and the other services;
- Battle and Tamagotchi with two replicas each;
- alerts switched off (`ALERT_*` empty).

**The probe.** It ran through the gateway, ~60 s per run, with a fresh stack each time:

- a Tamagotchi read (`GET /api/v1/tamagotchis`);
- a Tamagotchi write (`PATCH` of a pet's name, a new `Idempotency-Key` each time);
- a Battle read.

About 10 s in, the leader was crashed with `docker kill`.

**Two load patterns:**

- *Overlapping:* reads sent every 250 ms whatever the answers.
- *Sequential:* one request in flight per route.

**Fixes:** the "fixes" columns are the released `0.6.0`. The "first 0.6.0" columns are the build before `connect_timeout` and the background deadlines.

| | `0.5.0` overlapping | first `0.6.0` overlapping | `0.6.0` overlapping, run 1 | `0.6.0` overlapping, run 2 | `0.6.0` sequential |
| --- | --- | --- | --- | --- | --- |
| New leader after | 23.4 s | 23.8 s | 23.2 s | 23.3 s | 24.2 s |
| Requests failing for (read / write / Battle read) | 36.0 / 35.9 / 36.0 s | 34.0 / 33.8 / 35.9 s | 23.9 / 24.0 / 23.9 s | 23.2 / 24.4 / 23.2 s | 23.6 / 24.3 / 23.6 s |
| What the failing requests got | `503 NO_REPLICA` / `CIRCUIT_OPEN` (replicas gone) | `503 NO_REPLICA` / `CIRCUIT_OPEN` | `503 DEPENDENCY_UNAVAILABLE` | `503 DEPENDENCY_UNAVAILABLE` | `503 DEPENDENCY_UNAVAILABLE` |
| Broker timeouts (Battle / Tamagotchi) | 15 / 15 | 18 / 19 | 0 / 1 | 2 / 6 | 0 / 0 |
| Breakers opened and replicas evicted (Battle / Tamagotchi) | 2 / 2 | 2 / 2 | **0 / 0** | 0 / 1 | **0 / 0** |
| Writes acknowledged / stored | 95 / 95 | 104 / 104 | 144 / 144 | 142 / 142 | 142 / 142 |
| `db.unavailable` / `error.unhandled` | 0 / 0 | 26 / 0 | 648 / 0 | 470 / 0 | 588 / 0 |
| Old leader back as a replica | 5.0 s | 5.0 s | 6.1 s | 5.6 s | 6.1 s |

**What the runs show:**

- **Outage window:** with `0.6.0` the services fail only while no leader exists, about 24 s against 36 s. The rest of the `0.5.0` outage was the 30 s quarantine after the eviction.
- **Durability:** every acknowledged write is stored. Failed writes left no idempotency record, so their retries ran again.
- **Background work:** no background worker got stuck. Claims resumed about 1 s after the promotion, and Battle and Tamagotchi never restarted.

**Remaining risk: one Tamagotchi replica can still be evicted under steady overlapping load.** In 1 of the 3 runs, 3 of its requests timed out within 1.3 s, so the broker opened its breaker.

- **Cause:** each timed-out request was waiting for a free connection in its replica's pool (`DB_POOL_SIZE` 5). `database/sql` opens the queued connections one after another, and during the promotion each attempt takes the full 1 s `connect_timeout`. A request at the back of the queue therefore waited more than 2 s.
- **Effect:** the other replica kept serving, the outage window did not grow, and the evicted replica registered again 15 s after the promotion.
- **Possible fix:** a database deadline under 2 s for each request.

## Open items

None.
