# Lab 3 conventions — Tamagotchi Go, Team 12

Binding for all four team members for Lab 3 (Scaling Up). It builds on
[lab-1-conventions.md](lab-1-conventions.md) and
[lab-2-conventions.md](lab-2-conventions.md): everything there still applies
unless this page changes it. Changes go through a PR into `dev` with one
approval. A change to an API or a rule in sections 3–10 needs a review from
every owner whose service implements it.

Lab 3 in one paragraph: every service runs as 2–3 replicas that register with
a new **Service Discovery** service. The Gateway learns the replicas from it
and spreads requests over them with **round robin**. Every component that
calls another one protects itself with a **circuit breaker**. Service
Discovery polls every replica's **`/status`** and alerts the team when the
load becomes critical. Logs are JSON lines with a request id that follows a
request through every service.

## Open decisions

Fill these in during the review of this page. Nothing else on the page
depends on them.

| Decision | Value |
| --- | --- |
| Language of Service Discovery (the team's banned language) | ____ |
| Owner of the Service Discovery repository (creates it, invites everyone) | ____ |
| Owners of the shared tasks in section 1 | the `____` cells below |
| Alert channel (grade 9) | Discord webhook (proposed); Telegram or email are also allowed |

## 1. Grades, scope and owners

Every grade needs the lower ones. "Each owner" means each member for their
own two services. The house rules lower the grade of anyone without
contributions to the common services, so every member takes at least one
shared task.

| Grade | Task | Done when | Owner |
| --- | --- | --- | --- |
| 2 | Service Discovery repository: private, README, PR policy and CI workflows, professor **and all teammates** as collaborators, submodule `services/service-discovery` in the CPR | The submodule points at a pushed commit and the invitations are accepted | ____ |
| 3 | `GET /status` in every service, the Gateway and Service Discovery (section 4) | Every container answers with the section 4 body | Each owner; Gateway ____ |
| 3 | Structured logs everywhere (section 3) | `docker compose logs` shows the section 3 events as JSON lines | Each owner; Gateway ____ |
| 4 | Service Discovery with the registration API (section 5), in the banned language, Dockerized and on Docker Hub | Image `0.4.0` is public and a service registers on startup | ____ |
| 5 | Compose runs 2–3 replicas per service (section 11); every service registers and deregisters itself (section 6); the Gateway picks replicas up and drops them | `--scale` adds and removes replicas in the Gateway without restarting it | Compose ____; each owner; Gateway ____ |
| 6 | Round-robin load balancing in the Gateway (section 7); instance-agnostic business logic (section 9) | Consecutive requests reach different replicas; SSE, WebSocket and timers work with replicas | Gateway ____; each owner |
| 7 | Circuit breaker that trips and logs at 3 errors in 17.5 s, in every component that makes calls, for every endpoint (section 8) | Stopping a dependency logs `circuit.opened` | Each owner; Gateway ____ |
| 8 | Service Discovery polls `/status` at an interval and logs alerts on critical load (section 10) | A load test logs `health.alert` | ____ |
| 9 | The alerts reach the developers through Discord, Telegram or email (section 10) | The message arrives in the team channel | ____ |
| 10 | The breaker removes the failing instance (section 8) | A failing replica disappears from Service Discovery and the Gateway | Gateway ____; Service Discovery ____ |

## 2. Names, ports, versions

| Item | Value |
| --- | --- |
| Service Discovery compose service and port | `service-discovery`, **8089** |
| Service Discovery repository and submodule | `<owner>/service-discovery`, `services/service-discovery` |
| Service Discovery image | `<owner_dockerhub_username>/tamagotchi-service-discovery:0.4.0` |
| Lab 3 image tag | **0.4.0** (+ `latest`) for every image changed in Lab 3; fixes `0.4.1`, … Compose pins `0.4.x`, never `latest` |
| Service names on the wire | The Gateway's canonical names: `battle`, `tamagotchi`, `guild`, `notification`, `user-management`, `map`, `monster-raid`, `package-registry`, plus `gateway` |
| Branches | `<type>/lab-3/<kebab-description>` from `dev`, as before |

Unlike the eight service repositories, the Service Discovery repository is a
common service, so the lab asks to invite the professor **and all
teammates**. Copy the CPR's `.github/workflows/pr-policy.yml` and
`.github/pull_request_template.md`, protect `main` and `dev` like the other
repositories, and add a `ci.yml` that runs the tests on every PR and pushes
the image on every merge to `main`. The README states what the service does,
how to run it, its environment variables and the API of section 5.

## 3. Logs (grade 3)

Every service, the Gateway and Service Discovery write **one JSON object per
line to stdout**. Nothing spans several lines; a stack trace goes into the
`stack` key.

| Key | Required | Example |
| --- | --- | --- |
| `time` | yes | `2026-10-28T20:15:03.120Z` (RFC 3339) |
| `level` | yes | `DEBUG`, `INFO`, `WARN` or `ERROR` |
| `service` | yes | `monster-raid` |
| `instance_id` | yes | `monster-raid-3f9a1c2b7d4e` (section 6) |
| `event` | yes | `http.request`: dot-separated, from the table below |
| `msg` | yes | `POST /api/v1/raids/{id}/attacks -> 201 in 14 ms` |
| `request_id` | while handling a request | the request's `X-Request-Id` |
| anything else | as needed | `snake_case`: `raid_id`, `status`, `duration_ms`, `dependency`, … |

`LOG_LEVEL` (default `INFO`) sets the lowest level that is written.
Go: `log/slog` with `slog.NewJSONHandler` already writes `time`, `level` and
`msg`. Python: `logging` with a small JSON formatter (write `WARNING` as
`WARN`). NestJS: a custom `LoggerService` that serializes each call, or
`nestjs-pino`. Business events are named `<entity>.<past tense>`, for example
`raid.attacked` or `battle.finished`. Every component logs at least these:

| Event | Level | Extra keys | When |
| --- | --- | --- | --- |
| `service.started` | INFO | `port`, `version`, the configuration without secrets | The server listens |
| `service.stopping` | INFO | `signal` | SIGTERM or SIGINT |
| `http.request` | INFO; WARN for 4xx; ERROR for 5xx; DEBUG for `/health` and `/status` | `method`, `path` (no query string), `status`, `duration_ms`, `caller` (user id or service name) | Once per incoming request, when the response ends |
| `http.call` | INFO; WARN when it failed | `dependency`, `method`, `path`, `status` or `error`, `duration_ms`, `attempt` | Every outgoing attempt |
| `task.rejected`, `task.timeout` | WARN | `in_flight` and `max_concurrent`, or `timeout_ms` | The task limits answer 503 or 504 |
| `auth.rejected` | WARN | `reason` (never the rejected value) | The secret or identity check answers 401 or 403 |
| `discovery.registered`, `discovery.deregistered` | INFO | `discovery_url`, `url` | Section 6 |
| `discovery.register_failed`, `discovery.heartbeat_failed` | WARN | `attempt`, `error` | Section 6 |
| `circuit.opened` | ERROR | `breaker`, `failures`, `window_ms`, `open_ms`, `last_error` | A breaker trips (grade 7) |
| `circuit.half_open`, `circuit.closed` | INFO | `breaker` | Section 8 |
| `circuit.rejected` | WARN | `breaker` | A call is refused while the breaker is open |
| `instance.removed` | ERROR | `service`, `instance_id`, `reason` | Grade 10 (Gateway and Service Discovery) |
| `health.alert`, `health.recovered` | WARN or ERROR, INFO | `service`, `instance_id`, `condition`, `load` | Section 10 |
| `error.unhandled` | ERROR | `error`, `stack` | An unexpected exception |

Never log passwords, `Authorization` headers, JWTs, service tokens,
`X-Gateway-Secret`, `DISCOVERY_TOKEN`, chat tickets, webhook URLs or bot
tokens, query strings, or request bodies with personal data. Log ids, not
emails.

**Request ids.** The Gateway gives every request an `X-Request-Id` and keeps
the one the caller sent if it is a UUID. Every service puts the incoming value
on its own log lines and **sends it on every outgoing call**. One id then
follows a request through the Gateway into each service it touches:
`docker compose logs | grep <request_id>`.

## 4. `/health` and `/status` (grade 3)

| Route | Purpose | Answer |
| --- | --- | --- |
| `GET /health` | Liveness for the Docker health check (unchanged since Lab 1) | `200 {"status":"ok"}` |
| `GET /status` | Health and load, for Service Discovery and for people | the body below |

Both routes need no authentication and **no gateway secret**, are not under
`/api/v1`, are **not counted by the task limit** (an overloaded replica must
still be able to say so), and answer within 1 s: no calls to other services,
and the database check has a short timeout. They are reachable only on the
compose network.

```json
{
  "status": "ok",
  "service": "monster-raid",
  "instance_id": "monster-raid-3f9a1c2b7d4e",
  "version": "0.4.0",
  "started_at": "2026-10-28T20:00:00.000Z",
  "uptime_seconds": 915,
  "load": {
    "in_flight": 12,
    "max_concurrent": 50,
    "utilization": 0.24,
    "requests_total": 5310,
    "rejected_total": 0,
    "timeouts_total": 1
  },
  "checks": { "database": "ok" },
  "circuit_breakers": [
    { "name": "tamagotchi", "state": "closed", "failures_in_window": 0, "opened_at": null }
  ]
}
```

- `status` is `ok`, or `degraded` when a check failed or a breaker is open.
  The HTTP status is `200` in both cases. No answer, a timeout or any other
  status code means the replica is down.
- `load.in_flight` is the counter that the 50-task limit uses, and
  `utilization` is `in_flight / max_concurrent` with two decimals. Service
  Discovery alerts on `utilization` only.
- The `*_total` counters count since the replica started. Extra keys (memory,
  open streams, goroutines, event-loop lag) are welcome; Service Discovery
  ignores them.

## 5. Service Discovery API (grade 4)

Base URL `http://service-discovery:8089` on the compose network. It is not
behind the Gateway, because the Gateway depends on it. Writes need
`Authorization: Bearer <DISCOVERY_TOKEN>`; reads are open. Field names are
`snake_case` and errors use the shared envelope
`{code, message, request_id, details[]}`.

| Method and path | Caller | Request | Success | Errors |
| --- | --- | --- | --- | --- |
| `POST /v1/instances` | Every replica, on startup | `Registration` | `201 Instance`; `200 Instance` when the same `instance_id` registers again (it is replaced) | `401`; `422 INVALID_FIELDS`; `409 INSTANCE_EVICTED` with `Retry-After` |
| `PUT /v1/instances/{instance_id}/heartbeat` | Every replica, every `heartbeat_interval_ms` | — | `200 Instance` | `404 INSTANCE_NOT_FOUND`: register again |
| `DELETE /v1/instances/{instance_id}` | Every replica, on shutdown | — | `204` | `404` (already gone, fine) |
| `POST /v1/instances/{instance_id}/evictions` | Gateway, when a breaker removes a replica | `{reason, failures, window_ms}` | `200 Instance` | `404` |
| `GET /v1/services` | Gateway (every 2 s), people | — | `200 {services: {<service>: Instance[]}}` | — |
| `GET /v1/services/{service}/instances` | Anyone | — | `200 {service, instances: Instance[]}`, an empty list if there are none | — |
| `GET /health`, `GET /status` | Docker, people | — | Section 4 | — |

```text
Registration = {service: string, instance_id: string, host: string, port: Int, version: string}
Instance     = {service, instance_id, host, port, url: "http://<host>:<port>", version,
                health: "unknown"|"up"|"down", load: Number|null,
                registered_at: Time, last_heartbeat_at: Time,
                heartbeat_interval_ms: Int, ttl_ms: Int}
```

- `service` is a wire name from section 2, `instance_id` matches
  `^[a-z0-9][a-z0-9._-]{0,99}$` and `port` is 1–65535.
- The registry lives in memory. After a restart of Service Discovery, every
  replica's next heartbeat gets `404` and the replica registers again, so the
  registry refills within one heartbeat interval.
- A replica without a heartbeat for `ttl_ms` (default 15 s, three missed
  heartbeats) is removed and logged as `instance.expired`.
- The `GET` routes list every registered replica with its last polled
  `health` and `load` (section 10). `health` is `unknown` until the first
  poll. The Gateway routes to every replica that is not `down`.
- An eviction (grade 10) removes the replica at once, logs
  `instance.removed` and sends an alert. For `EVICTION_QUARANTINE_MS`
  (default 30 s) it refuses `POST /v1/instances` for that `instance_id` with
  `409 INSTANCE_EVICTED` and `Retry-After`. After that the replica's own
  heartbeat gets `404`, it registers again and rejoins the rotation.

Service Discovery reads `PORT=8089`, `DISCOVERY_TOKEN`,
`HEARTBEAT_INTERVAL_MS=5000`, `INSTANCE_TTL_MS=15000` and
`EVICTION_QUARANTINE_MS=30000`, plus the variables of section 10. With
`DISCOVERY_TOKEN` empty, writes are not checked and it logs a warning at
startup.

## 6. Registration in every service (grade 5)

New environment variables, with the same names everywhere:

| Variable | Meaning | Default |
| --- | --- | --- |
| `DISCOVERY_URL` | Service Discovery base URL; empty = do not register (a repository run alone) | empty; `http://service-discovery:8089` in compose |
| `DISCOVERY_TOKEN` | Bearer token for writes to Service Discovery | from `.env` |
| `INSTANCE_ID` | Unique id of this replica | `<service>-<hostname>`; in Docker the hostname is the container id, so it matches `docker ps` |
| `SERVICE_HOST` | Address other containers use to reach this replica | this container's IPv4 address |
| `HEARTBEAT_INTERVAL_MS` | Heartbeat period until Service Discovery answers with its own | `5000` |
| `DB_POOL_SIZE` | Most database connections one replica opens (section 11) | `5` |
| `CIRCUIT_BREAKER_FAILURES`, `CIRCUIT_BREAKER_WINDOW_MS`, `CIRCUIT_BREAKER_OPEN_MS` | Section 8 | `3`, `17500`, `17500` |
| `LOG_LEVEL` | Section 3 | `INFO` |

Register the container's IP address, not the compose service name. With
replicas, `monster-raid-service` resolves to all of them (Docker DNS round
robin), so it cannot name one replica. Go: the first non-loopback IPv4 address
from `net.InterfaceAddrs()`. Python: `socket.gethostbyname(socket.gethostname())`.
Node: the first non-internal IPv4 address from `os.networkInterfaces()`.

Lifecycle:

1. Start the HTTP server, and register only once it listens, so nothing is
   routed to a replica that cannot answer yet.
2. `POST /v1/instances`. On a network error or a `5xx`, retry with backoff
   (1 s, 2 s, 4 s, … at most 10 s) until it works, and keep serving
   meanwhile. On `409 INSTANCE_EVICTED`, wait for `Retry-After`.
3. Send a heartbeat every `heartbeat_interval_ms` of the answer. On `404`,
   register again (Service Discovery restarted, the TTL ran out or the replica
   was evicted). On other failures, log and keep the loop running.
4. On SIGTERM or SIGINT, `DELETE /v1/instances/{instance_id}` (best effort,
   1 s timeout), then let the requests in flight finish and exit. `docker stop`
   waits 10 s.
5. With `DISCOVERY_URL` empty, log `discovery.disabled` once and skip the
   steps above.

The Gateway registers itself as `gateway` in the same way, so that Service
Discovery polls it too. It is never load-balanced.

## 7. Gateway: discovery and round robin (grades 5–6)

- Every `DISCOVERY_REFRESH_MS` (2000 ms) fetch `GET /v1/services` and replace
  the replica lists. When Service Discovery does not answer, keep the last
  good lists and log once per outage. Before the first good answer, and for a
  service without registered replicas, use the static `*_URL` (the compose
  DNS name), so the stack still works without Service Discovery.
- **Round robin** per service: order the replicas by `instance_id`, skip the
  `down` ones and the ones whose breaker is open, and send each request to the
  next replica in turn. No usable replica → `503 UPSTREAM_UNAVAILABLE` with
  `Retry-After: 1`.
- When the connection to the chosen replica fails before the request was sent
  (refused, reset, DNS error), send the request once to the next replica. The
  first one never saw it, so this is safe for every method. Timeouts and `5xx`
  answers are **not** retried on another replica for `POST`, `PUT`, `PATCH`
  and `DELETE`, because the first replica may already have done the work.
- The access log line of every proxied request names the replica
  (`upstream_instance`), so `docker compose logs -f gateway-service` shows the
  rotation. Returning it as an `X-Upstream-Instance` header is optional, for
  the demo.
- The Gateway's own `GET /status` lists the replicas it routes to per service
  and the state of each breaker.

## 8. Circuit breaker (grades 7 and 10)

The lab's rule: a breaker trips when calls fail **3 times within 3.5 × the task
timeout**, which is 3.5 × 5 s = **17.5 s**.

- **A failure** is a refused or reset connection, a DNS error, a call
  timeout, or any `5xx` answer, including the Gateway's `502`, `503` and
  `504`. Every failed attempt counts, retries included. `2xx`–`4xx` answers
  are not failures: a `404` or a `409` is a correct answer.
- **Where:** inside the one HTTP client each component uses for its outgoing
  calls, so every endpoint is covered without code per route.
- **States:** closed → (3 failures within 17.5 s) → **open** for
  `CIRCUIT_BREAKER_OPEN_MS` (17.5 s) → **half-open**, which lets exactly one
  trial call through. Its success closes the breaker (`circuit.closed`); its
  failure opens it again. Calls refused while open log `circuit.rejected`.
  Every `/status` lists its breakers (section 4).

| Component | One breaker per | Trip (grade 7) | Remove (grade 10) |
| --- | --- | --- | --- |
| Each service (its calls go through the Gateway) | Dependency, by wire name (`tamagotchi`, `guild`, …) | Log `circuit.opened`; while open, answer `503 DEPENDENCY_UNAVAILABLE` at once, without calling | The same: the dependency is out of this caller's rotation until a trial call succeeds |
| Gateway | Upstream replica (`instance_id`) | Log `circuit.opened`; skip the replica in round robin while open | Drop the replica from the pool and call `POST /v1/instances/{instance_id}/evictions`, so that every client stops using it; log `instance.removed` |
| Service Discovery | Notification channel | Its `/status` polls are health checks: they set `health` (section 10) instead of tripping a breaker. A broken webhook trips the channel's breaker | — |

Discovery traffic itself (registration, heartbeats, the Gateway's refresh)
has its own backoff and is not behind a breaker.

## 9. Instance-agnostic business logic (grade 6)

With round robin, two requests of one user can reach different replicas.

1. State that must survive between requests lives in the database, never
   only in memory: tickets, sessions, idempotency records, locks, settlement
   progress, anything a later request reads.
2. **Live fan-out across replicas** (SSE, WebSocket): a change committed on
   replica A must reach the clients connected to replica B. Use Postgres
   `LISTEN`/`NOTIFY`, which needs no new infrastructure. After the commit run
   `SELECT pg_notify('<channel>', '<json>')`; every replica `LISTEN`s on one
   dedicated connection and forwards to its own clients. Keep payloads under
   8000 bytes (send ids and read the rest if more is needed), and reconnect
   the listener with backoff.
3. **Timers and background work** (expiry, turn timeouts, delivery retries,
   scheduled activation) run on every replica. Claim each piece of work in the
   database so that only one replica applies it: a row lock, a compare-and-set
   `UPDATE … WHERE state = … RETURNING`, `SELECT … FOR UPDATE SKIP LOCKED` or
   `pg_try_advisory_xact_lock`.
4. **Shared keys:** whatever signs a token must be the same on every replica,
   for example User Management's RS256 key pair, loaded from the environment
   or a mounted file instead of being generated at startup. The Gateway
   fetches the JWKS from whichever replica answers.
5. **Startup with replicas:** Prisma Migrate and golang-migrate take an
   advisory lock, so migrations run once. Seeding ("populate if empty") must
   be race-free: seed in a transaction that holds
   `pg_advisory_xact_lock(<number of your service>)`, or insert the fixed seed
   ids with `ON CONFLICT DO NOTHING`.
6. **Per replica by design (fine as it is):** the 50-task limit, breaker
   state, caches that may be stale (the Gateway's JWKS), the round-robin
   counter.

Instance-local state known from the Lab 2 pages. Owners confirm or correct
their rows in their Lab 3 PR:

| Service | Today | Lab 3 change | Owner |
| --- | --- | --- | --- |
| Monster Raid | SSE updates fanned out in memory ([lab-2-contract-sabina.md](lab-2-contract-sabina.md)) | `LISTEN`/`NOTIFY` between replicas (done, Monster Raid 0.4.0); the expiry already claims the raid under a row lock | Sabina |
| Package Registry | Nothing instance-local: the seed already runs under table locks, versions come from row-locked increments, schedule transitions are one conditional `UPDATE` | None needed (checked with two replicas seeding together, Package Registry 0.4.0) | Sabina |
| Guild | Chat tickets in memory, sockets fanned out in memory, one public WebSocket port `8083` ([lab-2-contract-vica.md](lab-2-contract-vica.md)) | Tickets in the database and `LISTEN`/`NOTIFY` fan-out; then either the Gateway proxies the WebSocket to any replica (`8083` is no longer published), or Guild stays at one replica as a documented exception | Vica |
| Notification | Delivery attempts and retries | Claim retries with `SKIP LOCKED`; keep the deduplication key unique in the database | Vica |
| User Management | JWT signing key | One key pair for all replicas (rule 4) | Mădălina |
| Map | SSE `GET /api/v1/map/stream` | Every push reads from the database (or `LISTEN`/`NOTIFY`), not from memory that only one replica filled | Mădălina |
| Battle | 30 s turn timeout, 120 s challenge expiry, preparation worker | Claim each timeout with a row lock or compare-and-set, so only one replica applies it (done, Battle 0.4.0: the coordinator claims due battles with `FOR UPDATE SKIP LOCKED` and a lease; seeding runs under `pg_advisory_xact_lock`) | Sava |
| Tamagotchi | Reservations and settlement | Confirm that nothing lives only in memory (confirmed, Tamagotchi 0.4.0: reservations, settlement and idempotency records are rows; the outbox is claimed with `FOR UPDATE SKIP LOCKED`; seeding runs under `pg_advisory_xact_lock`) | Sava |

## 10. Health polling and alerts (grades 8–9)

Service Discovery polls `GET <url>/status` of every registered replica every
`HEALTH_POLL_INTERVAL_MS` (5000 ms) with a 2 s timeout.

| Condition | Rule | Log | Notification (grade 9) |
| --- | --- | --- | --- |
| High load | `utilization` ≥ `LOAD_WARN_THRESHOLD` (0.6) | `health.alert`, WARN | no |
| Critical load | `utilization` ≥ `LOAD_CRITICAL_THRESHOLD` (0.8) | `health.alert`, ERROR | yes |
| Down | 2 failed polls in a row; `health` becomes `down` | `health.alert`, ERROR | yes |
| Evicted | Section 5 | `instance.removed`, ERROR | yes |
| Recovered | Load back under 0.6, or answering again | `health.recovered`, INFO | yes, if the alert was sent |

- Alert when a condition **starts or ends**, not on every poll. While it lasts,
  repeat it at most every `ALERT_REPEAT_MS` (300000 ms).
- Channels (empty = off; the values live only in `.env`):
  `ALERT_DISCORD_WEBHOOK_URL`, or `ALERT_TELEGRAM_BOT_TOKEN` with
  `ALERT_TELEGRAM_CHAT_ID`, or SMTP settings for email. Sending runs in the
  background and never delays polling; a failure is logged as `alert.failed`.
  A webhook URL is a secret: anyone who has it can post in the channel.
- Message format:
  `[CRITICAL] monster-raid / monster-raid-3f9a1c2b7d4e: load 0.86 (43/50 tasks) at 2026-10-28T20:15:03Z`.

To show it, lower `MAX_CONCURRENT_TASKS` on one service and load it through
the Gateway, for example
`npx autocannon -c 60 -d 20 -H "Authorization: Bearer <token>" http://localhost:8080/api/v1/<route>`.

## 11. Compose (grade 5)

- Add `service-discovery`. Publish `8089` for the demo (writes still need the
  token). Every service and the Gateway get `DISCOVERY_URL` and
  `DISCOVERY_TOKEN`; the Gateway also gets `depends_on: service-discovery`.
  Services do not need it, because registration retries.
- Replicas: `deploy: { replicas: 2 }` on every service (Guild only once
  section 9 is solved for it), and 3 for the demo with
  `docker compose up -d --scale monster-raid-service=3`. Scaled services keep
  `expose:` and must not set `container_name` or a fixed host port.
- Postgres: `command: ["postgres", "-c", "max_connections=300"]`. With
  replicas, the default of 100 connections runs out, because Prisma opens
  `2 × CPU cores + 1` connections per replica unless `connection_limit` is
  set. Every replica also caps its pool with `DB_POOL_SIZE`.
- Every service has a Docker `healthcheck` on `/health` (a Lab 1 rule), so
  `docker compose up -d --wait` waits for every replica. The NestJS images
  have no `curl`; use
  `node -e "fetch('http://127.0.0.1:<port>/health').then(r=>process.exit(r.ok?0:1),()=>process.exit(1))"`.
- `.env.example` gets `DISCOVERY_TOKEN` and empty alert variables.

## 12. Delivery and demo

Each owner adds `docs/lab-3-contract-<name>.md` (what changed, how it was
verified, open items), as in Lab 2, and bumps their submodules and image tags
in the compose file. About 20 containers run on the presentation laptop:
check that it has the memory before the presentation day.

Definition of done, from the CPR alone:

1. `docker compose up -d --wait`, then
   `curl http://localhost:8089/v1/services` lists 2–3 replicas of every
   service.
2. Repeating one request through the Gateway shows a different
   `upstream_instance` in the Gateway log each time.
3. `docker compose up -d --scale monster-raid-service=3`: the third replica
   registers and gets traffic. `docker compose stop` of one replica
   deregisters it at once.
4. `docker pause` on a replica: after 3 failed calls within 17.5 s the
   Gateway logs `circuit.opened` and `instance.removed`, and the alert
   arrives in the team channel. After `docker unpause` the replica rejoins
   once the quarantine ends.
5. With a raid's SSE stream open, every attack arrives on the stream,
   whichever replica handled it.
6. The load test of section 10 produces a critical alert in the team
   channel.
