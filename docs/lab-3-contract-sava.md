# Lab 3 implemented contract — Sava

This addendum describes **tamagotchi-battle-service:0.4.0** and **tamagotchi-tamagotchi-service:0.4.0**, the Lab 3 versions of Battle and Tamagotchi. They implement the "every service" items of the [Lab 3 conventions](lab-3-conventions.md) (#56) and section 9 for both services. Sava also wrote the Gateway's Lab 3 part (gateway-service#10), which [Mădălina's notes](lab-3-contract-madalina.md) describe. Everything in the Lab 2 pages still applies unless this page says otherwise.

Owners of affected services, please review the sections that concern you: the Gateway and Service Discovery (registration, `/status`), and the compose file (replicas).

## `GET /status` (both services)

- **Access.** No gateway secret. Like `/health`, it is outside `/api` and `/internal`, so the task limit does not count it: an overloaded replica still answers.
- **Status code.** `200` while the process answers. `status` is `ok`, or `degraded` when the database check fails or a breaker is not closed.
- **Body:**

  ```json
  {
    "status": "ok",
    "service": "battle",
    "instance_id": "battle-38b4368f049c",
    "version": "0.4.0",
    "started_at": "2026-10-30T05:20:00Z",
    "uptime_seconds": 42,
    "load": {"in_flight": 1, "max_concurrent": 50, "utilization": 0.02,
             "requests_total": 120, "rejected_total": 0, "timeouts_total": 0},
    "checks": {"database": "ok"},
    "circuit_breakers": [{"name": "tamagotchi", "state": "closed", "failures_in_window": 0, "opened_at": null}]
  }
  ```

  - `utilization` is `in_flight / max_concurrent`, rounded to two decimals; it counts the same slots as the 50-task limit.
  - The database check has a 500 ms timeout.
  - `version` is baked into the binary at build time.

## Structured logs (both services)

- **Format.** `log/slog` JSON, one object per line on stdout: `time`, `level`, `msg`, `service`, `instance_id`, `event`, and `request_id` while a request is handled. `LOG_LEVEL` (default `INFO`).
- **Events:**

  | Event | Level | Fields |
  | --- | --- | --- |
  | `service.started` / `service.stopping` | INFO | port, version, configuration without secrets / signal |
  | `http.request` | DEBUG for `/health` and `/status`; INFO; WARN for `4xx`; ERROR for `5xx` | method, path without the query string, status, duration_ms, caller |
  | `http.call` | INFO; WARN on failure | dependency, method, path, status or error, duration_ms, attempt |
  | `task.rejected` / `task.timeout` | WARN | in_flight, max_concurrent / timeout_ms |
  | `auth.rejected` | WARN | reason |
  | `circuit.opened` | ERROR | breaker, failures, window_ms, open_ms, last_error |
  | `circuit.half_open` / `circuit.closed` / `circuit.rejected` | INFO / INFO / WARN | breaker |
  | `discovery.registered` / `deregistered` / `register_failed` / `heartbeat_failed` / `disabled` | INFO / WARN | discovery_url, url, attempt, error |
  | `seed.checked`, `error.unhandled` | INFO, ERROR | error, stack for panics |
  | Business events | INFO | Battle: `battle.challenged`, `battle.accepted`, `battle.started`, `battle.finished`, `battle.expired`, `pets.reserved`, `pets.settled`, … Tamagotchi: pet, selection, reservation and settlement events |

- **Request IDs.** The Gateway's `X-Request-Id` is reused and sent on every outgoing call, so `docker compose logs | grep <request_id>` follows one request through the Gateway and both services.
- **Never logged:** tokens, secrets, query strings or request bodies.
- `event.published` now carries the domain event under `payload`, because `event` is the log event name.

## Service Discovery (both services)

- **When.** Registration starts after the server listens: `POST /v1/instances` with `Authorization: Bearer <DISCOVERY_TOKEN>` and `{service, instance_id, host, port, version}`. Network errors and `5xx` are retried with backoff (1, 2, 4 … 10 s), and requests are served meanwhile. After `409 INSTANCE_EVICTED` the replica waits for `Retry-After`.
- **Heartbeats** every `heartbeat_interval_ms` of the answer (5 s); after `404` the replica registers again. On `SIGTERM` it deregisters (1 s, best effort), then shuts down.
- **Identity.** `instance_id` defaults to `<service>-<hostname>`, which in Docker is the container id. The address is the container's IPv4 address (`SERVICE_HOST` overrides it), not the compose service name.
- **Settings.** `DISCOVERY_URL` (empty = do not register), `DISCOVERY_TOKEN`, `INSTANCE_ID`, `SERVICE_HOST`, `HEARTBEAT_INTERVAL_MS`, `DB_POOL_SIZE` (5), `CIRCUIT_BREAKER_FAILURES` (3), `CIRCUIT_BREAKER_WINDOW_MS` (17500), `CIRCUIT_BREAKER_OPEN_MS` (17500), `LOG_LEVEL`.

## Circuit breakers (both services)

- **Scope.** One breaker per dependency, by wire name, shared by every endpoint of that dependency. Battle has `user-management`, `tamagotchi` and `package-registry`; Tamagotchi has `package-registry`. Every call goes through the Gateway.
- **Failure.** A transport error, a timeout or a `5xx` answer. `4xx` answers are valid answers.
- **Lifecycle.** 3 failures within 17.5 s open the breaker (`circuit.opened`, ERROR). While it is open, calls fail at once with `503 DEPENDENCY_UNAVAILABLE`, without a request (`circuit.rejected`). After 17.5 s one trial call runs (`circuit.half_open`): success closes the breaker, and failure opens it again.

## Instance-agnostic logic (section 9)

- **Battle.** The coordinator claims due battles with `FOR UPDATE SKIP LOCKED` and a lease, so only one replica applies each 30 s turn timeout, 120 s challenge expiry or preparation step. The outbox is claimed the same way. Idempotency records are rows, under a transaction-scoped advisory lock per key.
- **Tamagotchi.** Pets, selections, reservations, settlement and idempotency records are rows; nothing a later request needs lives in memory. The outbox is claimed with `FOR UPDATE SKIP LOCKED`.
- **Startup.** golang-migrate takes its advisory lock. Seeding runs in a transaction holding `pg_advisory_xact_lock` with `ON CONFLICT DO NOTHING`; before this fix, replicas starting together raced on the fixed seed ids.
- **Pool.** Each replica opens at most `DB_POOL_SIZE` (5) connections.

## Compose

Battle and Tamagotchi `0.4.0` run as two replicas each (`deploy.replicas: 2`, `expose:` only), with the shared `x-lab3-env` anchor.

## Verification

Full stack of this compose file with only published images (every service `0.4.0`), from `docker compose pull`:

| Check | Result |
| --- | --- |
| `docker compose up -d --wait` | 19 containers healthy; 17 replicas registered and `up` in `GET :8089/v1/services` (2 per service, plus the Gateway) |
| The eight Postman collections through the Gateway | 0 failures (Battle 30, Tamagotchi 29, Guild 88, Notification 34, User Management 54, Map 24, Monster Raid 74, Package Registry 82 assertions) |
| Round robin (`upstream_instance` in the Gateway's `http.request` lines) | every pair split evenly: battle 4/4, tamagotchi 8/7, user-management 43/42, package-registry 23/22, … |
| `GET /status` of a Battle replica | the section 4 body with three closed breakers (`package-registry`, `tamagotchi`, `user-management`) |
| `docker pause` of a Battle replica, then three parallel Battle collections | the Gateway logged `circuit.opened` after 3 failures within 17500 ms and called `/evictions`; Service Discovery logged `instance.removed`; the other replica served the rest |
| `docker unpause` | the replica's heartbeat got `409`, it waited out the 30 s quarantine and registered again 33 s after the eviction |
| `--scale battle-service=3 --scale tamagotchi-service=3`, then back to 2 | 3 replicas each registered within seconds; scaling down removed them at once (deregistration on `SIGTERM`, no TTL wait) |

Unit tests: `go build`, `go vet` and `go test ./...` pass in both repositories (registration, heartbeat and re-registration against a fake Service Discovery, `/status`, breaker transitions, config).
