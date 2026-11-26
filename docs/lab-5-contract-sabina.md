# Lab 5 — Sabina's Monster Raid and Package Registry

This page covers **tamagotchi-monster-raid-service:0.6.0** and
**tamagotchi-package-registry-service:0.6.0**, the Lab 5 versions of Monster
Raid and Package Registry (NestJS + Prisma), and how they were verified.

- They follow the recommendation for every owner in the
  [Lab 5 conventions](lab-5-conventions.md), section 11: during a database
  failover, answer `503 DEPENDENCY_UNAVAILABLE` with `Retry-After`, so the
  broker doesn't evict the replicas (sections 3.3 and 7).
- They keep the columns the ETL reads (section 5.1) unchanged.
- Everything in the Lab 1–4 pages still applies unless this page says
  otherwise. Mădălina's parts are in
  [lab-5-contract-madalina.md](lab-5-contract-madalina.md).

Repositories:

- [sabinapopescu/monster-raid-service](https://github.com/sabinapopescu/monster-raid-service):
  #13, released to `main` by #14 (`9afe055`);
- [sabinapopescu/package-registry-service](https://github.com/sabinapopescu/package-registry-service):
  #11, released by #12 (`3acd367`).

CI published both `0.6.0` images from those commits, and the submodules point
to them. Each README has a "Database failover (Lab 5)" section with the
details.

## What changed

| | Monster Raid | Package Registry |
| --- | --- | --- |
| Image | `sabinapopescu/tamagotchi-monster-raid-service:0.6.0` | `sabinapopescu/tamagotchi-package-registry-service:0.6.0` |
| Database unreachable | `503 DEPENDENCY_UNAVAILABLE`, `Retry-After: 2` (was `500 INTERNAL_ERROR`) | `503 DEPENDENCY_UNAVAILABLE`, `Retry-After: 2` (was `500 INTERNAL`) |
| Prisma URL | adds `connect_timeout=2&pool_timeout=3` | adds `connect_timeout=2&pool_timeout=3` unless `DATABASE_URL` sets them |
| `LISTEN` connection (live HP between replicas) | reconnects at least every 2 s (was up to 10 s); connect timeout 2 s | — |
| Log event | `db.unavailable` (WARN) | `db.unavailable` (WARN) |
| Routes, DTOs, schema, ports, environment | unchanged | unchanged |

## The answer during a failover

```http
HTTP/1.1 503 Service Unavailable
Retry-After: 2

{"code": "DEPENDENCY_UNAVAILABLE", "message": "The database is unavailable; retry shortly.", "request_id": "…", "details": []}
```

**Which errors count as the database being unreachable.** The same module is
in both services (`database-unavailable.ts`):

- Prisma `P1001`, `P1002`, `P1008`, `P1017` and `P2024`, the codes section
  3.3 lists;
- a connection lost under a query: Prisma's `Error in PostgreSQL connection`,
  `Server has closed the connection`, `terminating connection`;
- a raw query refused with SQLSTATE class `08`, `57P01`–`57P03` (shut down,
  crashed, starting up) or `25006` (read-only: a demoted leader before the
  router cuts it);
- `P2028` "Unable to start a transaction in the given time".

Everything else, for example a unique violation or a bug, stays `500`.

**Over gRPC.** `ServiceEndpoint.Handle` runs the HTTP route on the replica's
own port, so the broker gets the same `503` in the `CallReply` and applies the
section 7 rule to it. `Deliver` already answered `UNAVAILABLE` to a database
outage, and the broker redelivers the event.

## No `504` in a planned switchover

With Prisma's defaults, a connection opened while the leader was handing over
waited 5 s (`connect_timeout`), the same as the task timeout. The request
answered `504 TASK_TIMEOUT`, and the broker counts a `504` against the
replica. Both services now set `connect_timeout=2` and `pool_timeout=3`
(seconds), under the 5 s task timeout. A connection that can't be had fails as
`P1001` or `P2024`, which answers `503`.

User Management and Map use Prisma too. Unless their URLs set these
timeouts, they may also answer a `504` in a planned switchover, as `0.5.0` of
these two services did in the measurements below.

## Retrying

- **Reads:** retry after `Retry-After`. The gateway caches only `200`
  answers, so a `503` is never cached (section 4.2).
- **Joining a raid:** a join that loses the database keeps its attempt
  `reserving`. Its retry resumes the attempt with the same reservation
  `Idempotency-Key` and gets the same pet reservation back.
- **In doubt.** A write can commit while its answer is lost, when the
  connection is cut between the commit and the answer. It happened to 2 of
  more than 3,000 writes in the tests below, both of them registrations. The
  retry of such a registration answers `409 ALREADY_REGISTERED`, which a
  client can treat as done. Raids are created once per `schedule_id`, and
  schedule events have ids derived from the schedule, so their retries are
  harmless.

## Verification

**Unit tests.** Monster Raid 217 tests (17 new) and Package Registry 129 (11
new), with `eslint`/`tsc`. They cover:

- which errors count as an outage, and the filter's body and `Retry-After`;
- a join that loses the database right after reserving the pet, then
  succeeds on the retry with the same reservation;
- a registration that loses the database and fails with that error, not as
  `409`;
- the `LISTEN` connection retrying every 2 s during a 22 s outage;
- the Prisma URLs.

**Against the cluster of this lab.** A scratch compose ran:

- the database part of this repository's Lab 5 compose: etcd; `pg-1..3`
  built from [db/ha](../db/ha); and the router with
  [db/ha/haproxy.cfg](../db/ha/haproxy.cfg);
- next to it, Monster Raid and Package Registry twice each: the released
  `0.5.0` images and the `0.6.0` branches.

A probe sent one read and one write to each instance every 250 ms:

- **Monster Raid:** `GET /internal/v1/raids/by-schedule/{id}`, and a raid
  through the dev route;
- **Package Registry:** `GET /api/v1/packages`, and a registration.

The leader was killed or stopped, and the database was compared with the
answers afterwards.

| Failover | `0.5.0` answered | `0.6.0` answered | Acknowledged writes |
| --- | --- | --- | --- |
| Leader killed (`docker kill`), 3 runs | `500` for about 23 s | only `503 DEPENDENCY_UNAVAILABLE` with `Retry-After: 2`; slowest answer 2.0 s | 863 by `0.6.0`, none lost |
| Leader stopped (`docker compose stop`), 2 runs | one `500` and one `504 TASK_TIMEOUT` per probe | 2–3 × `503`, no `504`; slowest answer 2.0 s | 403 by `0.6.0`, none lost |

- Every request succeeded again as soon as a replica was promoted, without a
  restart. The outage lasted about 23 s after a crash and under 1 s after a
  stop.
- After a crash, Monster Raid's `LISTEN` connection was back 1–3 s after the
  database (`0.5.0`: 6–8 s).

## Not changed

- **The ETL.** The extracts of `raids`, `raid_participants`, `packages` and
  `registrations` (section 5.1) read only columns that exist in both schemas.
- **The cache.** The gateway caches Package Registry's package and definition
  reads (section 4.2). Their data changes only through Package Registry's own
  public writes, which bump `gen:package-registry`: its internal routes are
  reads, and it subscribes to no topic. The allowlist is safe as it is.
- **The saga.** Neither service takes part in account deletion. After the
  pivot, raids and registrations keep the user's id, which no longer leads to
  personal data.
