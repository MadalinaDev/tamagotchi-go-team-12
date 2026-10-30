# Lab 3 implemented contract — Vica

This addendum describes **tamagotchi-guild-service:0.4.1** and **tamagotchi-notification-service:0.4.1**, the Lab 3 versions of Guild and Notification. They implement the "every service" items of the Lab 3 conventions and section 9 for both services. Everything in the [Lab 2 page](lab-2-contract-vica.md) still applies unless this page says otherwise. Two drafts of the conventions are open (CPR #55 and #56), and both services support either one (see [Service Discovery](#service-discovery-both-services)).

Owners of affected services, please review the sections that concern you: the gateway and Service Discovery (registration, `/status`, Guild's WebSocket port), and the compose file (replicas).

## `GET /status` (both services)

- **Access.** No gateway secret. Like `/health`, it is outside `/api` and `/internal`, so the task limit does not count it: an overloaded replica still answers.
- **Status code.** `200` while the process answers: `status` is `ok`, or `degraded` when the database check fails or a breaker is open. No answer means the replica is down.
- **Body:**

  ```json
  {
    "status": "ok",
    "service": "guild",
    "instance_id": "guild-c044c34e6d11",
    "version": "0.4.1",
    "started_at": "2026-10-29T13:24:33Z",
    "uptime_seconds": 42,
    "load": {"in_flight": 1, "max_concurrent": 50, "utilization": 0.02,
             "requests_total": 120, "rejected_total": 0, "timeouts_total": 0},
    "requests_total": 120,
    "checks": {"database": "ok"},
    "circuit_breakers": [{"name": "user-management", "state": "closed", "failures_in_window": 0, "opened_at": null}],
    "extra": {"open_chat_sockets": 3}
  }
  ```

  - `utilization` is `in_flight / max_concurrent`, rounded to two decimals.
  - `requests_total` is repeated at the top level for the #55 draft.
  - `extra` exists only in Guild.
  - The database check has a 500 ms timeout.
  - `version` comes from the `VERSION` file, which is baked into the binary at build time.

## Structured logs (both services)

- **Format.** One JSON object per line on stdout: `time`, `level`, `service`, `instance_id`, `event`, `msg`, and `request_id` when there is one, plus event fields.
- **Events:**

  | Event | Level | Fields |
  | --- | --- | --- |
  | `service.started` / `service.stopping` | INFO | port, version, storage, mocks, gateway and discovery URLs, limits, pool size, breaker settings (never secrets) |
  | `http.request` | DEBUG for `/health` and `/status`; INFO; WARN for `4xx`; ERROR for `5xx` | method, path without the query string, status, duration_ms, caller |
  | `http.call` | INFO; WARN on failure | dependency, method, path, status, duration_ms, attempt |
  | `auth.rejected` | WARN | reason |
  | `task.rejected` / `task.timeout` | WARN | in_flight, max_concurrent / timeout_ms |
  | `circuit.opened` | ERROR | breaker, failures, window_ms, open_ms, last_error |
  | `circuit.half_open` / `circuit.closed` / `circuit.rejected` | INFO / INFO / WARN | breaker |
  | `discovery.registered` / `register_failed` / `heartbeat_failed` / `deregistered` / `disabled` | INFO / WARN | discovery_url, url, attempt, error, retry_in_ms |
  | `db.waiting` / `db.migrated` / `seed.checked` | INFO | |
  | `error.unhandled` | ERROR | error, stack for panics |
  | Business events | INFO | Guild: `guild.created`, `invite.created`, `member.removed`, `message.sent`, `ticket.issued`, `chat.connected`, … Notification: `notification.created`, `event.handled`, `device.registered`, `preferences.updated`, `push.sent`, … |

- **Request IDs.** The gateway's `X-Request-Id` is reused and sent on every outgoing call (Guild → User Management, Package Registry, Notification; Notification → Guild). `docker compose logs | grep <request_id>` follows one request through the gateway and both services.
- **Never logged:** chat tickets, tokens, secrets or query strings. Push tokens appear only as their last four characters.
- **Level.** `LOG_LEVEL` (default `INFO`).

## Service Discovery (both services)

- **When.** Registration starts after the server listens. It retries with backoff (1, 2, 4 … 10 s) and never blocks requests. A heartbeat follows every `HEARTBEAT_INTERVAL_MS` (5 s). After `404` the replica registers again, and after `409` it waits for `Retry-After` first. On `SIGTERM` it deregisters (1 s, best effort), then shuts down.
- **Drafts.** `DISCOVERY_API` picks one of the two open drafts:

  | | `v55` (default; CPR #55, what the gateway implements) | `v56` (CPR #56) |
  | --- | --- | --- |
  | Register | `POST /api/v1/registry/instances` `{service, instance_id, url, status_url, version}` | `POST /v1/instances` `{service, instance_id, host, port, version}` |
  | Heartbeat | `PUT /api/v1/registry/instances/{id}/heartbeat` | `PUT /v1/instances/{id}/heartbeat`; `heartbeat_interval_ms` in the answer is honoured |
  | Deregister | `DELETE /api/v1/registry/instances/{id}` | `DELETE /v1/instances/{id}` |
  | Auth | `X-Discovery-Secret: <secret>` | `Authorization: Bearer <token>` |

- **Identity.** `instance_id` defaults to `<service>-<hostname>`, which in Docker is the container id, as in `docker ps`. The address is the container's IPv4 address (`SERVICE_HOST`), not the compose service name, which resolves to every replica.
- **Settings.** `DISCOVERY_URL` (empty = do not register), `DISCOVERY_API`, `DISCOVERY_SECRET` (or `DISCOVERY_TOKEN`), `INSTANCE_ID`, `SERVICE_HOST`, `ADVERTISE_URL`, `HEARTBEAT_INTERVAL_MS`.

## Circuit breakers (both services)

- **Scope.** One breaker per dependency, by wire name. Guild has `user-management`, `package-registry` and `notification`; Notification has `guild`. Every call already goes through the gateway.
- **Failure.** A network error, a timeout or a `5xx` answer. A `404` is a valid answer and not a failure.
- **Lifecycle.** 3 failures within 17.5 s open the breaker (`circuit.opened`, ERROR). While it is open, calls fail at once with `503 DEPENDENCY_UNAVAILABLE`, without a request (`circuit.rejected`). After 17.5 s one trial call runs (`circuit.half_open`): success closes the breaker, and failure opens it again.
- **Retries.** Each retry of a call counts as an attempt, so a dependency that keeps failing opens the breaker within one request.
- **Guild events.** The `GuildInvited` publisher skips delivery while the `notification` breaker is open (`event.dropped`), and the invite still succeeds, as in Lab 2.
- **Settings.** `CIRCUIT_BREAKER_FAILURES`, `CIRCUIT_BREAKER_WINDOW_MS`, `CIRCUIT_BREAKER_OPEN_MS`.

## Instance-agnostic logic (section 9)

### Guild — chat across replicas

| Lab 2 | Lab 3 |
| --- | --- |
| Chat tickets in a map in one process | Table `chat_tickets` (migration `000002`): only the SHA-256 hash of the ticket, the guild, the user and the expiry. Redeeming deletes the row in the same statement, so a ticket works once on any replica |
| Chat events sent to the sockets of the same process | After the change is committed, Guild runs `SELECT pg_notify('guild_chat', <json>)`. Every replica keeps one connection with `LISTEN guild_chat` (reconnecting with backoff) and passes the events to its own sockets |

- **Payloads.** They carry ids only: `{kind, guild_id, user_id?, message_id?}`, where `kind` is `message`, `member_removed` or `guild_disbanded`. The receiving replica reads the message from the database and rechecks membership before it delivers.
- **WebSocket port.** Guild replicas publish no host port, because replicas cannot share one and Docker does not say which replica gets which port of a range (an earlier `8083-8085:8083` range left `8083` unbound in some runs, so the gateway's `ws://localhost:8083` was refused). Instead, a small `guild-ws` service (`alpine/socat`) publishes `8083` and forwards each TCP connection to `guild-service:8083`; Docker DNS rotates the replicas. Any replica can take the socket, and every message reaches it through `NOTIFY`. Connections that cannot be served are only those that arrive while no Guild replica is running.
- **Not done here.** The gateway does not proxy the socket. Moving `8083` behind the gateway is a gateway change, listed in [Open items](#open-items).

### Notification

- **State.** Everything is already in Postgres. The inbox entry is unique per `(event_id, recipient_id)` in the database, so one event handled by two replicas creates one entry.
- **Retries.** Push is sent synchronously inside the request through the logging Firebase mock, so there are no delivery attempts or retries to claim. `SKIP LOCKED` becomes necessary once real FCM delivery with retries is added (a later lab).

### Both services

- **Startup.** golang-migrate takes an advisory lock, so migrations run once even when replicas start together. The seed runs in a transaction under `LOCK TABLE … IN EXCLUSIVE MODE` and is applied once.
- **Pool size.** `DB_POOL_SIZE` (default 5) caps each replica's pool.
- **Per replica by design.** The 50-task limit, the breakers and the open sockets.

## Compose

- **Images.** `nikvnln/tamagotchi-guild-service:0.4.1` and `nikvnln/tamagotchi-notification-service:0.4.1` (+ `latest`, amd64 and arm64), published by each repository's CI on merge to `main`; tagged `v0.4.1`.
- **0.4.1.** The discovery client opens a new connection for every call. With the real Service Discovery about every other heartbeat failed with `EOF` or `connection reset by peer`: it closes idle connections, a heartbeat can arrive just as it does, and net/http does not retry a `PUT`. On `0.4.1` the compose stack logged no `discovery.heartbeat_failed`, and both replicas of each service stayed `up` with version `0.4.1`.
- **Replicas.** `deploy.replicas: 2` for both. Both use `expose:` only; port `8083` is published by `guild-ws` (see above), so scaling Guild never conflicts on a host port.
- **Lab 3 settings.** Both services share the anchor `x-vica-lab3-env`:
  - `DISCOVERY_URL` defaults to `http://service-discovery:8090` and `DISCOVERY_API` to `v55`, which is draft #55.
  - With draft #56, set `DISCOVERY_URL=http://service-discovery:8089` and `DISCOVERY_API=v56` in `.env`.
  - `DISCOVERY_SECRET` comes from `.env`.
  - `DB_POOL_SIZE=5`, `LOG_LEVEL=INFO`.
- **Without Service Discovery.** Until a `service-discovery` container is in the compose file, both services log `discovery.register_failed` with backoff and serve normally. The gateway reaches them through the static `GUILD_URL` and `NOTIFICATION_URL`.

## Verification

- **Tests.**
  - `go vet` and `go test -race ./...` with the Postgres suite pass in both repositories.
  - Coverage of `internal/` is 95.9 % for Guild and 96.8 % for Notification.
  - New tests cover:
    - breaker states;
    - the v55 and v56 discovery lifecycle against a fake server (backoff, `404` re-registration, `409` with `Retry-After`, deregistration);
    - `/status`, including that it answers while the task limit is full;
    - tickets redeemed on another replica;
    - chat across two hubs, and real `LISTEN`/`NOTIFY` across two pools.
- **Compose.** Run with the local `0.4.0` images, a fresh volume, and both services at 2 replicas:
  - all four replicas were healthy; `8083` was published by `guild-ws` only, and six `GET /status` calls through it were split 3 and 3 between the two Guild replicas;
  - four sockets opened through `8083` landed 2 and 2 on the two replicas, and one message sent over REST reached all four as `chat.message` (`scripts/guild-chat-demo`);
  - with one Guild replica stopped, `8083` and the chat kept working on the other;
  - a request with a forged `X-Auth-User-Id` and no gateway secret sent to `localhost:8083` was `401`;
  - `/status` of each replica showed its own `instance_id` and version `0.4.0`;
  - the logs were JSON lines, including `chat.listening` and `discovery.register_failed` with backoff 1, 2, 4, 8 s, because no Service Discovery was running.
- **Single image.** One Notification image was run with an unreachable `DISCOVERY_URL` and stopped with `SIGTERM`: it logged `service.stopping`, then attempted deregistration (`discovery.deregister_failed`), then exited.

## Open items

| Item | Depends on |
| --- | --- |
| End-to-end registration, round robin and eviction with the real Service Discovery | The `service-discovery` repository and image, and the choice between #55 and #56 |
| Gateway proxies Guild's WebSocket, so that the `guild-ws` helper is no longer needed | Gateway owner |
| `SKIP LOCKED` claiming of push retries | Real FCM delivery with retries (later lab) |
