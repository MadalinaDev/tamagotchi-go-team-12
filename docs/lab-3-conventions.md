# Lab 3 conventions — Tamagotchi Go, Team 12

Shared reference for Lab 3 (scaling up). Builds on
[lab-2-conventions.md](lab-2-conventions.md): the Gateway stays the only REST
entry point, and services still call each other only through it. Lab 3 adds a
Service Discovery service, several instances per service, round-robin load
balancing in the Gateway, circuit breakers and health alerts. Every image built
for Lab 3 is tagged **`0.4.0`** (+ `latest`).

## Service Discovery

- Python (the banned language, like the Gateway), FastAPI. Compose service
  `service-discovery`, port **8090**, `expose:` only. Private repository
  `service-discovery` (professors and all teammates are collaborators).
- Every `/api/v1/*` route requires `X-Discovery-Secret: <DISCOVERY_SECRET>`
  (shared `.env` value). `/health` and `/status` are open.
- The registry is in memory (one Discovery instance). If Discovery restarts,
  heartbeats answer `404` and every instance registers again within one
  heartbeat interval.

| Route | Body | Result |
| --- | --- | --- |
| `POST /api/v1/registry/instances` | `{service, instance_id, url, status_url?, version?}` | `201` new, `200` re-registered; `409 INSTANCE_EVICTED` during eviction cooldown |
| `PUT /api/v1/registry/instances/{instance_id}/heartbeat` | none | `200`; `404 INSTANCE_NOT_FOUND` → register again; `409 INSTANCE_EVICTED` |
| `DELETE /api/v1/registry/instances/{instance_id}` | none | `204` (graceful shutdown) |
| `POST /api/v1/registry/instances/{instance_id}/evict` | `{reason, reporter}` | `200`; removes the instance, starts the cooldown, alerts |
| `GET /api/v1/registry/services` | none | `{services: {name: Instance[]}}`, healthy instances only (`?all=true` for every state) |
| `GET /api/v1/registry/services/{service}` | none | `{service, instances: Instance[]}`, healthy only (`?all=true` for every state) |

```text
Instance = {service, instance_id, url, status_url, version, health: "healthy" | "unhealthy",
            registered_at, last_heartbeat_at, last_status: Status | null}
```

- `service` uses the canonical wire names (`battle`, `tamagotchi`, `guild`,
  `notification`, `user-management`, `map`, `monster-raid`,
  `package-registry`, plus `gateway`).
- `instance_id` = `<service>-<container hostname>`; `url` = the instance's own
  address, `http://<container IP>:<port>` (Docker gives each replica its own IP).
  `ADVERTISE_URL` overrides it.
- Defaults (all configurable): heartbeat every **10 s**, instance dropped after
  **30 s** without heartbeat, eviction cooldown **60 s**.

### Health polling and alerts (grades 8–9)

- Every **10 s** Discovery calls each instance's `status_url` (2 s timeout).
- **3** consecutive failed polls → `unhealthy`: hidden from the Gateway, alerted.
  First successful poll → `healthy` again, alerted as recovered.
- Load is critical when `load.utilization >= 0.8` (in-flight tasks / 50).
  Critical load, recovery from it, health changes, expiry and evictions are
  logged at `WARNING`/`ERROR` and sent to the developers' **Telegram** chat
  (`TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID` in `.env`). Alerts fire on state
  changes, with a 5-minute repeat for a state that persists. Without a token
  Discovery logs the alert and says it was not sent.

## Every service

1. **`GET /status`** (no auth, no gateway secret, like `/health`):

   ```text
   Status = {status: "ok", service, instance_id, version, uptime_seconds,
             load: {in_flight: Int, max_concurrent: Int, utilization: Float},
             requests_total: Int}
   ```

   `/health` stays a plain liveness check.
2. **Register on startup** with Discovery, heartbeat every 10 s, register again
   on `404`, keep retrying on `409`/unreachable Discovery (never block startup),
   and `DELETE` the registration on graceful shutdown. Env: `DISCOVERY_URL`
   (`http://service-discovery:8090`), `DISCOVERY_SECRET`, `PORT`.
3. **Logs**: one structured line per request (method, path, status, duration,
   `request_id`, `instance_id`), per outbound call (target, method, path,
   status, duration), per business event (created/accepted/settled…), per
   registration/heartbeat failure and per circuit-breaker transition. Include
   `instance_id` in every line so replicas can be told apart in `docker compose logs`.
4. **Circuit breaker** on every outbound call (grade 7), one breaker per target
   service covering all its endpoints: **3 failures within 17.5 s**
   (`TASK_TIMEOUT` 5 s × 3.5) trip it. A failure is a transport error, a timeout
   or a `5xx`. Tripping logs at `ERROR`; while open (30 s) calls fail fast with
   `503 DEPENDENCY_UNAVAILABLE`; one half-open trial then closes or reopens it.
5. **Instance-agnostic**: no in-process state that another replica needs.
   Data lives in each service's database; startup migrations and seeding must
   be safe when 3 replicas start at once; idempotency keys are stored in the
   database.
6. **Replicas**: Compose runs services with `deploy.replicas` (2–3), no
   `container_name`, no fixed host ports.

## Gateway (grades 5, 6, 10)

- Reads Discovery every **2 s** (`DISCOVERY_URL`, `DISCOVERY_SECRET`) and
  balances each service's healthy instances **round-robin**. The static
  `*_URL` variables are only a fallback while a service has no registered
  instance, so services that have not migrated yet keep working.
- One breaker per **instance**, same threshold (3 failures in 17.5 s). Tripping
  logs at `ERROR`, takes the instance out of rotation and **evicts it from
  Discovery** (`POST .../evict`, grade 10), so it is removed for every consumer
  until the cooldown ends and it registers again. A connection failure before
  the request reached the instance is retried on the next instance.
- The access log line names the chosen `instance_id`; `GET /status` lists the
  routing table and breaker states. The Gateway registers itself as `gateway`
  so Discovery watches its load too.
- Guild WebSocket negotiation still returns a direct `ws_url`; with several
  Guild instances that URL must name the instance holding the ticket (Vica).

## Ownership

| Work | Owner |
| --- | --- |
| Service Discovery service, Gateway load balancer, Gateway circuit breaker, this page, Compose wiring for Discovery and the Gateway | Sava |
| Battle and Tamagotchi: status, logs, registration, breakers, replicas | Sava |
| Guild and Notification: status, logs, registration, breakers, replicas | Vica |
| User Management and Map: status, logs, registration, breakers, replicas | Mădălina |
| Monster Raid and Package Registry: status, logs, registration, breakers, replicas | Sabina |
| Creating the `service-discovery` repository and inviting collaborators | Mădălina |
