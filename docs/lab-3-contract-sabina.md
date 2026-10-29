# Lab 3 implemented contract — Sabina

This addendum describes **tamagotchi-monster-raid-service:0.4.0** and **tamagotchi-package-registry-service:0.4.0**, the Lab 3 versions of Monster Raid and Package Registry. They implement the "every service" items of the [Lab 3 conventions](lab-3-conventions.md) and section 9 for both services. Everything in the [Lab 2 page](lab-2-contract-sabina.md) still applies unless this page says otherwise. Two drafts of the Service Discovery API are open (CPR #55 and #56), and both services support either one (see [Service Discovery](#service-discovery-both-services)).

Owners of affected services, please review the sections that concern you: the gateway and Service Discovery (registration, `/status`), and the compose file (replicas).

## `GET /health` and `GET /status` (both services)

- **`/health` is new.** Lab 1 required it, but neither service had it. It answers `200 {"status":"ok"}`, and both images now have a Docker `HEALTHCHECK` on it, so `docker compose up --wait` waits for every replica.
- **Access.** Neither route needs the gateway secret, and the task limit does not count them: an overloaded replica still answers.
- **Status code.** `200` while the process answers: `status` is `ok`, or `degraded` when the database check fails or a breaker is not closed. No answer means the replica is down.
- **Body** (Monster Raid):

  ```json
  {
    "status": "ok",
    "service": "monster-raid",
    "instance_id": "monster-raid-61f3c4c10cdf",
    "version": "0.4.0",
    "started_at": "2026-10-29T17:52:02.000Z",
    "uptime_seconds": 42,
    "load": {"in_flight": 1, "max_concurrent": 50, "utilization": 0.02,
             "requests_total": 120, "rejected_total": 0, "timeouts_total": 0,
             "open_streams": 3},
    "checks": {"database": "ok"},
    "circuit_breakers": [{"name": "guild", "state": "closed", "failures_in_window": 0, "opened_at": null}]
  }
  ```

  - `utilization` is `in_flight / max_concurrent`, rounded to two decimals; it counts the same slots as the 50-task limit.
  - `load.open_streams` exists only in Monster Raid: the live HP streams this replica serves.
  - The database check (`SELECT 1`) gives up after 1 s.
  - `version` comes from `package.json`.

## Structured logs (both services)

- **Format.** One JSON object per line on stdout: `time`, `level`, `service`, `instance_id`, `event`, `msg`, and `request_id` when there is one, plus event fields. Nest's own startup lines come out the same way, as event `log`.
- **Events:**

  | Event | Level | Fields |
  | --- | --- | --- |
  | `service.started` / `service.stopping` | INFO | port, version, database, pool size, gateway and discovery URLs, mocked dependencies, limits, breaker settings (never secrets) / signal |
  | `http.request` | DEBUG for `/health` and `/status`; INFO; WARN for `4xx`; ERROR for `5xx` | method, path without the query string, status, duration_ms, caller |
  | `http.call` | INFO; WARN on failure | dependency, method, path, status or error, duration_ms, attempt |
  | `auth.rejected` | WARN | reason |
  | `task.rejected` / `task.timeout` | WARN | in_flight, max_concurrent / timeout_ms |
  | `circuit.failure` / `circuit.opened` | WARN / ERROR | breaker, failures_in_window, window_ms, open_ms, last_error |
  | `circuit.half_open` / `circuit.closed` / `circuit.rejected` | INFO / INFO / WARN | breaker |
  | `discovery.registered` / `register_failed` / `heartbeat_failed` / `heartbeat_rejected` / `evicted` / `deregistered` / `disabled` | INFO / WARN | discovery_url, discovery_api, url, attempt, error, retry_in_ms |
  | `live.listening` / `live.listener_lost` / `live.publish_failed` (Monster Raid) | INFO / WARN | channel, reason, retry_in_ms |
  | `stream.opened` / `stream.closed` / `stream.closed_for_shutdown` (Monster Raid) | INFO | raid_id, duration_ms, streams |
  | `error.unhandled` | ERROR | error, stack |
  | Business events | INFO; WARN for failures | Monster Raid: `raid.created`, `raid.joined`, `raid.join_failed`, `raid.attacked`, `raid.defeated`, `raid.failed`, `settlement.op_applied`, `settlement.op_failed`, `raid.finalized`. Package Registry: `package.created`, `package.updated`, `package.user_registered`, `care_definition.published`, `raid_definition.created`, `raid_definition.version_added`, `raid_schedule.created`, `raid_schedule.activated`, `raid_schedule.cancelled`, `seed.packages`, `seed.raid_definition`. Both: `domain_event.published` |

- **Request IDs.** The gateway's `X-Request-Id` is reused through `AsyncLocalStorage` and sent on every outgoing call, so `docker compose logs | grep <request_id>` follows one request through the gateway and every service it reaches.
- **Never logged:** tokens, secrets, `X-Gateway-Secret`, the discovery secret or query strings.
- **Level.** `LOG_LEVEL` (default `INFO`).

## Service Discovery (both services)

- **When.** Registration starts after the server listens. It retries with backoff (1, 2, 4 … 10 s) and never blocks requests. A heartbeat follows every `HEARTBEAT_INTERVAL_MS` (10 s), or the interval Service Discovery answers with. After `404` the replica registers again; after `409` it waits for `Retry-After` (the eviction cooldown) first. On `SIGTERM` it deregisters (1 s, best effort), then shuts down.
- **Drafts.** `DISCOVERY_API` picks one of the two open drafts, with the same values as Guild and Notification:

  | | `v55` (default; CPR #55, what the gateway implements) | `v56` (CPR #56) |
  | --- | --- | --- |
  | Register | `POST /api/v1/registry/instances` `{service, instance_id, url, status_url, version}` | `POST /v1/instances` `{service, instance_id, host, port, version}` |
  | Heartbeat | `PUT /api/v1/registry/instances/{id}/heartbeat` | `PUT /v1/instances/{id}/heartbeat`; `heartbeat_interval_ms` in the answer is honoured |
  | Deregister | `DELETE /api/v1/registry/instances/{id}` | `DELETE /v1/instances/{id}` |
  | Auth | `X-Discovery-Secret: <secret>` | `Authorization: Bearer <token>` |

- **Identity.** `instance_id` defaults to `<service>-<hostname>`, which in Docker is the container id, as in `docker ps`. The address is `ADVERTISE_URL`, or `http://<SERVICE_HOST>:<PORT>` with the container's IPv4 address, not the compose service name, which resolves to every replica.
- **Settings.** `DISCOVERY_URL` (empty = do not register), `DISCOVERY_API`, `DISCOVERY_SECRET` (or `DISCOVERY_TOKEN`), `INSTANCE_ID`, `ADVERTISE_URL`, `SERVICE_HOST`, `HEARTBEAT_INTERVAL_MS`.

## Circuit breakers (both services)

- **Scope.** One breaker per dependency, by wire name, inside the one HTTP client both services use for outgoing calls. Monster Raid has `guild`, `tamagotchi`, `package-registry` and `user-management`; Package Registry has `user-management` and `guild`. Every call already goes through the gateway.
- **Failure.** A network error, a timeout or a `5xx` answer. A `404` or a `409` is a valid answer and not a failure.
- **Lifecycle.** 3 failures within 17.5 s (3.5 × `TASK_TIMEOUT_MS`) open the breaker (`circuit.opened`, ERROR). While it is open, calls fail at once with `503 DEPENDENCY_UNAVAILABLE` and `Retry-After` (the seconds left), without a request (`circuit.rejected`). After 17.5 s one trial call runs (`circuit.half_open`): success closes the breaker, and failure opens it again.
- **Retries.** Each retry of a call counts as an attempt, so a dependency that keeps failing opens the breaker within two requests.
- **Settings.** `CIRCUIT_BREAKER_FAILURES`, `CIRCUIT_BREAKER_WINDOW_MS`, `CIRCUIT_BREAKER_OPEN_MS`.

## Instance-agnostic logic (section 9)

### Monster Raid — live HP across replicas

| Lab 2 | Lab 3 |
| --- | --- |
| Raid updates fanned out to the SSE streams of the same process | After the change is committed, the replica runs `SELECT pg_notify('raid_live_updates', <json>)`. Every replica keeps one connection with `LISTEN raid_live_updates` (reconnecting with backoff) and passes the updates to its own streams; it skips its own notifications by their `origin` |

- **Order.** One replica sends its notifications one after the other, so the killing attack still arrives before `settling` and `completed` on every replica.
- **Payloads.** A `Raid` or `RaidAttack` view, well under the 8000-byte `NOTIFY` limit.
- **Deadline.** Every replica may expire a raid, but only under the per-raid row lock, so a raid fails and is cleaned up once.
- **Shutdown.** On `SIGTERM` the replica ends its open streams, and their clients reconnect through the gateway to another replica.

### Package Registry

- **State.** Nothing is instance-local. Care-definition and raid-definition versions come from a row-locked increment, schedule transitions are one conditional `UPDATE`, and registrations and package names are unique in the database.

### Both services

- **Startup.** Prisma Migrate takes an advisory lock, so migrations run once even when replicas start together. Package Registry's seed runs in one transaction under `LOCK TABLE … IN EXCLUSIVE MODE` and is applied once.
- **Pool size.** `DB_POOL_SIZE` (default 5) is Prisma's `connection_limit` on every replica; Monster Raid adds one listener connection.
- **Per replica by design.** The 50-task limit and the breakers.

## Compose

- **Images.** `sabinapopescu/tamagotchi-monster-raid-service:0.4.0` and `sabinapopescu/tamagotchi-package-registry-service:0.4.0` (+ `latest`, amd64), published by each repository's CI on merge to `main`:

  | Image | Release | Submodule |
  | --- | --- | --- |
  | [`sabinapopescu/tamagotchi-monster-raid-service:0.4.0`](https://hub.docker.com/r/sabinapopescu/tamagotchi-monster-raid-service) | sabinapopescu/monster-raid-service#10 | `services/monster-raid-service` at `e0b09e1` |
  | [`sabinapopescu/tamagotchi-package-registry-service:0.4.0`](https://hub.docker.com/r/sabinapopescu/tamagotchi-package-registry-service) | sabinapopescu/package-registry-service#8 | `services/package-registry-service` at `7c99413` |

- **Replicas.** `deploy.replicas: 2` for both, `expose:` only.
- **Lab 3 settings.** Both services use the shared anchor `x-vica-lab3-env`, like Guild and Notification: `DISCOVERY_URL` defaults to `http://service-discovery:8090` and `DISCOVERY_API` to `v55`; with draft #56, set `DISCOVERY_URL=http://service-discovery:8089` and `DISCOVERY_API=v56` in `.env`.
- **Without Service Discovery.** Until a `service-discovery` container is in the compose file, both services log `discovery.register_failed` with backoff and serve normally. The gateway reaches them through the static `RAID_URL` and `REGISTRY_URL`. Gateway 0.3.1 keeps one connection to the DNS name, so requests stay on one replica; round robin comes with gateway-service#10.

## Verification

- **Tests.** Monster Raid: eslint, `tsc` and 154 Jest tests. Package Registry: `tsc` and 96 Jest tests. New tests cover:
  - breaker states, and calls failing fast while a breaker is open;
  - the JSON logger, and the request id surviving express's body parser;
  - the v55 and v56 registration lifecycle with fake timers (backoff, `404` re-registration, `409` with `Retry-After`, deregistration);
  - `/status`, including that it answers while the task limit is full;
  - two Monster Raid replicas sharing one repository through `NOTIFY`/`LISTEN`.
- **Real Service Discovery and gateway.** Images built locally from `MadalinaDev/service-discovery` (`main`), gateway-service#10 and both services, with two replicas each:
  - all four replicas registered, Service Discovery polled their `/status`, and the gateway's routing table listed them;
  - six reads of `/api/v1/packages` through the gateway were served three by each Package Registry replica;
  - a live HP stream opened through the gateway got all four attacks in order (276, 252, 228, 204), while the gateway sent two attacks to each Monster Raid replica;
  - with one Monster Raid replica paused, the gateway's breaker opened after 3 timeouts and evicted it; after unpausing, its heartbeat got `409`, it waited out the cooldown and rejoined the rotation.
- **Shutdown and restarts** (an earlier run against a stub of the API): `docker stop` of a replica with an open stream deregistered it and took 0.7 s, and after the stub forgot every instance both replicas registered again within 2 s.
- **Team stack from this branch.** Fresh volume, `0.4.0` of both services built locally under the published tags, two replicas each:
  - all eight Postman collections pass with 0 failures: Battle 30, Tamagotchi 29, Guild 88, Notification 34, User Management 54, Map 24, Monster Raid 82 and Package Registry 82 assertions;
  - one Package Registry replica seeded, the other found the tables full.

## Open items

| Item | Depends on |
| --- | --- |
| One Service Discovery API for the team | The decision on CPR #55 (draft #55 or #56); both services follow it through `DISCOVERY_API` |
| Round robin over these replicas in the team stack | gateway-service#10, and Service Discovery in the compose file (CPR #55) |
