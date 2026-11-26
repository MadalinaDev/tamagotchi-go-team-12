# Lab 5 — Vica's Guild and Notification

This page describes **tamagotchi-guild-service:0.6.0** and **tamagotchi-notification-service:0.6.0**. They follow the recommendation of the [Lab 5 conventions](lab-5-conventions.md) (sections 3.3, 7 and 11): while the database fails over, they answer `503 DEPENDENCY_UNAVAILABLE` instead of `500`, so the broker no longer evicts their replicas.

Repositories: [vikanicologlo/guild-service](https://github.com/vikanicologlo/guild-service) and [vikanicologlo/notification-service](https://github.com/vikanicologlo/notification-service), branch `feat/lab-5/db-failover`. Each README has a "Lab 5 at a glance" section.

## What changed

The services still connect to `postgres:5432`, which is now the router in front of the Patroni cluster. Configuration is unchanged.

During a failover, queries fail for a few seconds. In the run below this lasted about 15 s after a leader crash. These errors now answer `503 DEPENDENCY_UNAVAILABLE` with `Retry-After: 2`, in the team envelope:

| Error (pgx) | Why it happens |
| --- | --- |
| `*pgconn.ConnectError` | No leader accepts connections yet |
| `io.EOF`, `io.ErrUnexpectedEOF`, connection reset, `conn closed`, `closed pool` | The router cut the connection to the old leader (`on-marked-down shutdown-sessions`) |
| SQLSTATE class `08` | Connection exception |
| `57P01`, `57P02`, `57P03` | The server is shutting down, crashed, or not yet accepting connections |
| `25006` | Read-only transaction: a write that reached a node just demoted to replica |
| `53300` | Too many connections |

- **Classification.** It lives in `httpx.DatabaseUnavailable`. Every other error is unchanged: a unique violation stays `409`, and a bug stays `500`.
- **Logs.** `db.unavailable` (WARN) replaces `error.unhandled` (ERROR).
- **Reconnecting.** The pgx pool drops a broken connection and opens a new one on the next query. There is nothing to configure.
- **Broker deliveries.** Through gRPC `Deliver`, the `503` becomes `UNAVAILABLE`, so the broker retries the event later instead of dead-lettering it.
- **Canceled requests.** When the broker's per-attempt deadline cancels a request that is hanging on a dead leader, the service now logs `request.canceled` with status `499`. Before, it logged `error.unhandled`. Nobody reads that answer.

**Why it matters (conventions section 7).** The broker does not count a `503 DEPENDENCY_UNAVAILABLE` against the replica's breaker; it only reroutes it. With `500` it opened the breakers, evicted every replica through Service Discovery, and the 30 s quarantine kept the service away long after the database was back.

## Warehouse (section 5.1)

The ETL service reads these columns. All of them exist and are kept stable, checked by running the ETL's queries against the migrated schemas.

| Database | Query of `app/sources.py` |
| --- | --- |
| `guild_db` | `guilds (guild_id, name, leader_id, created_at)`, `guild_members (guild_id, user_id, role, joined_at)`, `guild_messages (message_id, guild_id, author_id, sent_at, char_length(text))` |
| `notification_db` | `notifications (notification_id, recipient_id, type, resource_type, read_at, created_at)` |

Lab 4's `outbox_events` (Guild) is not read.

## Verification

### Tests

- `go vet` and `go test -race ./...` pass in both repositories, with the Postgres suites. CI is green on both pull requests.
- **Unit tests:** which errors count as an outage, which do not, and the `503` + `Retry-After: 2` answer.
- **Postgres tests:** a real connection cut. The pool's only connection is terminated with `pg_terminate_backend`, as the router does on a failover. The next query's error is classed as an outage, and the query after it works on a new connection.

### Failover runs

The stack:

- the Lab 5 database part: etcd, `pg-1`..`pg-3` built from `db/ha`, the router `postgres`;
- Service Discovery, the broker and the gateway `0.6.0`, User Management and the cache;
- Guild and Notification with two replicas each.

A probe sent, every 250 ms through the gateway, a Guild read (`GET /api/v1/guilds/{id}`), a Guild write (`POST …/messages`) and a Notification read (`GET /api/v1/notifications`). Each run counts the answers and the broker's log events for Guild and Notification, and compares the acknowledged writes with the rows stored afterwards.

| Event | `0.5.0` | `0.6.0` |
| --- | --- | --- |
| Leader crashed (`docker kill`) | `500 INTERNAL`, then `circuit.opened` and `instance.removed` for all 4 replicas; from then on `503 NO_REPLICA` or `CIRCUIT_OPEN` until the end of the 55 s run (about 105 failed requests per route) | only `503 DEPENDENCY_UNAVAILABLE` (49 per route, about 15 s) and one `504` for the write in flight at the crash; **no breaker opened, no eviction**, the broker only rerouted; 118 of 118 acknowledged writes stored |
| Leader stopped (`docker stop`, planned switchover) | — | **no failed request** (one reroute); 76 of 76 writes stored |

After the crash, `pg-2` became the leader. The old leader rejoined as a replica when it was started again.

## Open items

| Item | Depends on |
| --- | --- |
| Run on the full stack and every collection with the released `0.6.0` images | #74 and #75 merged, then this pull request |
