# Lab 3 contract notes — Mădălina (Service Discovery, User Management, Map)

This page describes what Mădălina's parts of Lab 3 implement of the [Lab 3 conventions](lab-3-conventions.md) (#56), how they were verified, and what is still open. It also wires the shared pieces into [docker-compose.yml](../docker-compose.yml).

## Service Discovery `0.4.0` (grades 2, 4, 8, 9, 10)

Repository [MadalinaDev/service-discovery](https://github.com/MadalinaDev/service-discovery), image `madalina060504/tamagotchi-service-discovery:0.4.0`. It is Python and FastAPI, the team's banned language.

- **Repository (grade 2).** Private repository with a README, the CPR's PR template and PR policy, and CI: `ruff` and the tests on every PR, and the image on every merge to `main`. The professor and all teammates are invited. Linked as the `services/service-discovery` submodule.
- **API (section 5).**
  - `POST /v1/instances`, `PUT /v1/instances/{id}/heartbeat`, `DELETE /v1/instances/{id}` and `POST /v1/instances/{id}/evictions`, with writes behind `Authorization: Bearer <DISCOVERY_TOKEN>`.
  - `GET /v1/services` and `GET /v1/services/{service}/instances`.
  - `GET /health` and `GET /status` (section 4).
  - The registry lives in memory. Heartbeats come every 5 s and the TTL is 15 s. After an eviction the instance ID is quarantined for 30 s (`409 INSTANCE_EVICTED` with `Retry-After`).
- **Polling and alerts (section 10).** Every replica's `GET /status` is polled every 5 s with a 2 s timeout. Health becomes `down` after 2 failed polls in a row.
  - High load (≥ 0.6) is logged; critical load (≥ 0.8), down and evicted are notified.
  - A recovery is sent when the alert was. A condition that lasts repeats every 5 minutes.
  - Notifications go to Discord (`ALERT_DISCORD_WEBHOOK_URL`) or Telegram (`ALERT_TELEGRAM_BOT_TOKEN` + `ALERT_TELEGRAM_CHAT_ID`), each channel behind its own circuit breaker.
- **Logs (section 3).** JSON lines with the conventions' events: `instance.registered`, `instance.expired`, `instance.removed`, `health.alert`, `health.recovered`, `alert.sent`, `alert.failed`, `circuit.*`, `http.request`, `http.call`, `service.started` and `service.stopping`.

The first version of the repository (Sava, written for the earlier #55 draft) is kept in its history. It was replaced on `main` by this `#56` version once the team merged #56 (the #55 version is kept on the `archive/lab-3/v55-draft` branch).

## User Management and Map `0.4.0` (grades 3, 5, 6, 7)

Repositories [user-management-service](https://github.com/MadalinaDev/user-management-service) and [map-service](https://github.com/MadalinaDev/map-service). Each runs as 2 replicas.

- **Registration (section 6).**
  - The replica registers `{service, instance_id: <service>-<container id>, host: <container IPv4>, port, version}` once it listens, retrying with backoff while Service Discovery is not up.
  - It heartbeats at the interval Service Discovery returns, registers again after `404`, and waits for `Retry-After` after `409`.
  - On SIGTERM it deregisters (best effort, 1 s).
- **`GET /status` (section 4).**
  - `load` (`in_flight`, `max_concurrent`, `utilization`, `requests_total`, `rejected_total`, `timeouts_total`), `checks.database` with a 500 ms timeout, and `circuit_breakers`.
  - Always `200`; `degraded` when a check failed or a breaker is open.
  - It needs no gateway secret and the task limit does not count it.
- **Circuit breaker (section 8).** One `HttpClient` makes every outgoing call through the gateway, with a breaker per dependency: `package-registry` for User Management, `user-management` for Map.
  - Every failed attempt counts: connection error, timeout or any `5xx`. 3 failures in 17.5 s open the breaker for 17.5 s, then one trial call runs.
  - While it is open, callers get `503 DEPENDENCY_UNAVAILABLE` with `Retry-After`.
- **Logs (section 3).** JSON lines.
  - Every request: `http.request`. Every outgoing attempt: `http.call`.
  - Lifecycle and limits: `service.started`, `service.stopping`, `discovery.*`, `task.rejected`, `task.timeout`, `auth.rejected`, `circuit.*`, `error.unhandled`.
  - Business events such as `user.registered`, `friendship.accepted`, `settlement.applied` and `location.updated`.

  The gateway's `X-Request-Id` is in scope for every line and is sent on every outgoing call.
- **Instance-agnostic (section 9).**
  - User Management's RS256 signing key is shared by all replicas through `user_management_db` (table `signing_keys`): the first replica creates it and the others load it. A mounted `JWT_PRIVATE_KEY_PATH` still wins.
  - The seed runs under `pg_advisory_xact_lock`, so replicas starting together seed once.
  - Map's state is all in PostGIS, and every SSE push re-reads it. `DB_POOL_SIZE` caps every replica's pool.

## Compose wiring (grade 5)

- **Service Discovery.** The new `service-discovery` service listens on port 8089 (published for the demo) with `DISCOVERY_TOKEN` and the alert variables.
- **Gateway.** Version `0.4.0` (gateway-service#10, Sava) gets `DISCOVERY_URL` and `DISCOVERY_TOKEN`. It routes round-robin over registered replicas, evicts failing ones and registers itself as `gateway`.
- **Shared settings.** One `x-lab3-env` anchor for every registering service: Service Discovery URL, `DISCOVERY_API=v56` for Guild, Notification, Monster Raid and Package Registry (which support both drafts), `DISCOVERY_TOKEN`, `DB_POOL_SIZE`, `LOG_LEVEL`.
- **Replicas.** User Management and Map run at `0.4.0` with 2 replicas; Postgres gets `max_connections=300`.
- **Battle and Tamagotchi** stay at `0.3.0` with 1 replica until Sava publishes `0.4.0`. The gateway reaches them through their configured URLs meanwhile.

## Verification

The whole stack of this compose file ran on 2026-10-29 in a separate Compose project, with the images of Service Discovery `0.4.0`, the Gateway of gateway-service#10 and User Management and Map `0.4.0` built from their branches, and the published `0.4.0` images of Guild, Notification, Monster Raid and Package Registry:

| Check | Result |
| --- | --- |
| `docker compose up -d --wait` | All 18 containers healthy |
| `GET :8089/v1/services` | 13 replicas registered and `up` with their load: the Gateway, and two each of Guild, Notification, Monster Raid, Package Registry, User Management and Map (the four teammates' services in `DISCOVERY_API=v56` mode, without code changes) |
| The eight Postman collections through the Gateway | 204 requests, 423 assertions, 0 failures |
| Round-robin | Every pair of replicas split the Gateway's traffic evenly: 39/38, 33/32, 23/22, 19/18, 8/7, 5/5. Battle and Tamagotchi used their configured URLs |
| `docker kill` of a User Management replica, then 9 parallel requests | 4 timed out on it; the Gateway logged `circuit.opened` and `instance.removed` and called `/evictions`. Service Discovery logged `instance.removed` and sent the alert to the webhook. The next 9 requests all succeeded in 208 ms |
| Restarting the evicted replica | `409 INSTANCE_EVICTED` during the quarantine, then registered again after `Retry-After`; two replicas after 13 s |
| Unit tests | Service Discovery 44, User Management 52, Map 46; CI green on gateway-service#10, user-management-service#3 and map-service#3 |

Load alerts (grade 8) are covered by Service Discovery's tests (high load logged, critical load notified once, then the recovery, plus the 5-minute repeat). An earlier run of the stack showed them live: 60 concurrent logins against User Management limited to 5 tasks produced `load_critical` and then `load_normal` on every replica.

## Open items

- Battle and Tamagotchi `0.4.0` (Sava): publish the images, then set them to `0.4.0` with 2 replicas and `<<: [*service-env, *lab3-env]` here.
- CPR #55 predates the merged conventions. Its compose and conventions changes are replaced by this page and #56.
