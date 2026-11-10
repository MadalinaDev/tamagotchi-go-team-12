# Lab 4 conventions — the message broker

Lab 4 ("Breaking and Brokering") puts a **message broker** between the gateway and the services, and between the services themselves. This page is the team contract: what the broker offers, and what every owner changes in their services.

**Status (2026-11-09).** Mădălina's parts are implemented and verified on the full stack. See [lab-4-contract-madalina.md](lab-4-contract-madalina.md):

- the broker ([MadalinaDev/message-broker](https://github.com/MadalinaDev/message-broker));
- Service Discovery, the gateway, User Management and Map, all `0.5.0`;
- Compose and monitoring.

The other services already go through the broker without code changes (section 3.1). What their owners add for grades 6 and 8 is in section 12.

## 1. The requirements and where they are met

| Grade | Requirement | Where | Owner |
| --- | --- | --- | --- |
| 2 | Message broker in the banned language (Python); repository and workflow like the gateway's and Service Discovery's | [MadalinaDev/message-broker](https://github.com/MadalinaDev/message-broker), submodule `services/message-broker` | Mădălina |
| 3 | README and architecture diagram show the broker; Postman collections up to date | [README](../README.md#architecture); `postman/` (section 11) | Mădălina, every owner for their collection |
| 4 | Endpoint to download the system's logs | Gateway `GET /api/v1/admin/logs` (section 9.3) | Mădălina |
| 5 | Broker dockerized and published; service-to-service calls through the broker; load balancing and breakers moved from the gateway to the broker | `madalina060504/tamagotchi-message-broker`; sections 3 and 5 | Mădălina (every service already calls through the broker) |
| 6 | Subscriber-based queues for gateway → service; topic-based queues between services; the topics in the Service Discovery registration | Sections 4, 6 and 8 | Mădălina (broker, User Management, Map); **every owner: publish or subscribe** |
| 7 | Thread-per-request in the broker; endpoint listing the topics | Section 7 | Mădălina |
| 8 | gRPC between services; no service-only routes in the gateway | Section 3.2 and 3.3; gateway 0.5.0 serves no `/internal` route | Mădălina (broker, gateway, User Management, Map); **every owner: gRPC client and endpoint** |
| 9 | Durable queues; dead-letter channel; endpoint listing it | Section 6.4 and 6.5 | Mădălina |
| 10 | Rerouting after a breaker trips; routing by service load; Grafana + Prometheus (+ Loki for logs) | Sections 5 and 9 | Mädălina |

## 2. Components and ports

The architecture diagram is in the [README](../README.md#architecture).

| Component | Ports (Docker network) | Published on the host |
| --- | --- | --- |
| Gateway | 8080 | 8080 |
| Message broker | 8090 HTTP, 50051 gRPC | 8090, 50051 (demo) |
| Service Discovery | 8089 | 8089 (demo) |
| Battle, Tamagotchi, Guild, Notification | 8081, 8082, 8083, 8084 (HTTP); gRPC `90xx` once added (suggested 9081, 9082, 9083, 9084) | Guild's chat WebSocket only |
| User Management, Map | 8085, 8086 (HTTP); 9085, 9086 (gRPC) | no |
| Monster Raid, Package Registry | 8087, 8088 (HTTP); 9087, 9088 (gRPC) | no |
| Prometheus, Loki, Grafana | 9090, 3100, 3000 | 9090, 3100, 3000 |

Every service still registers with Service Discovery (Lab 3, section 6). The broker reads the registry every 2 s.

## 3. Calls between services (grades 5 and 8)

### 3.1 HTTP through the broker (works today, no code change)

The broker serves the `/internal/...` contract paths exactly as the gateway did in Labs 2–3. Compose now sets every service's `GATEWAY_URL` to `http://message-broker:8090`, so existing clients keep working: same paths, same service token (`Authorization: Bearer <SERVICE_TOKEN>`; `INTERNAL_SERVICE_TOKENS` moved from the gateway to the broker).

- The broker finds the owner of the path (the gateway's Lab 2 route table) and picks a replica (section 5).
- On the way to the target it removes client-supplied identity headers and sets `X-Service-Name` (from the token), `X-Gateway-Secret` and `X-Request-Id`. Services keep checking `X-Gateway-Secret` as before.
- The response carries `X-Upstream-Instance` (the replica that answered), `X-Broker-Attempts`, `X-Broker-Queue-Ms` and `X-Broker-Transport`.
- Broker errors use the team envelope:

  | Status | Code | Meaning |
  | --- | --- | --- |
  | 401 | `UNAUTHORIZED` | Missing or unknown service token |
  | 404 | `ROUTE_NOT_FOUND` | No service owns the path |
  | 503 | `NO_REPLICA` | The service has no registered replica |
  | 503 | `CIRCUIT_OPEN` | Every replica has an open breaker |
  | 503 | `QUEUE_TIMEOUT` | No replica had room within the request deadline |
  | 503 | `UPSTREAM_UNAVAILABLE` | The replica could not be reached |
  | 504 | `UPSTREAM_TIMEOUT` | The replica did not answer in time |

  503 always comes with `Retry-After`.

### 3.2 gRPC client (grade 8)

The contract is [`proto/broker.proto`](https://github.com/MadalinaDev/message-broker/blob/main/proto/broker.proto) (package `tamagotchi.broker.v1`). Copy it into your repository.

- **Call** `Broker.Call(CallRequest) → CallReply` on `message-broker:50051` (env `BROKER_GRPC_URL`):
  - `CallRequest`: `service` (or empty: resolved from `path`), `method`, `path` (with query), `headers` (lower-case), `body` (bytes, usually JSON).
  - Metadata: `authorization: Bearer <SERVICE_TOKEN>` and `x-request-id: <current request id>`.
- **Answer** `CallReply` has HTTP semantics: `status`, `headers`, `body`, `instance_id`.
  - Broker errors come back as `status` 4xx/5xx with the team error body, not as gRPC errors. The one exception is a missing or invalid token, which is gRPC `UNAUTHENTICATED`.
  - A gRPC `UNAVAILABLE` or `DEADLINE_EXCEEDED` means the broker itself could not be reached: count it as a failure of the dependency.
- **Keep your per-dependency circuit breaker** (Lab 3, section 8) around the call.
- **Examples:**
  - Node: `@grpc/grpc-js` + `@grpc/proto-loader` (User Management's [`src/broker/broker.client.ts`](https://github.com/MadalinaDev/user-management-service/blob/dev/src/broker/broker.client.ts)).
  - Go: `protoc --go_out=. --go-grpc_out=. broker.proto`, then `brokerv1.NewBrokerClient(conn).Call(ctx, req)` with `metadata.AppendToOutgoingContext(ctx, "authorization", "Bearer "+token, "x-request-id", id)`.

### 3.3 gRPC endpoint of a service (grade 8)

Serve `ServiceEndpoint` from the same proto on a gRPC port, and register it as `grpc_port` (section 8). The broker then sends service-to-service calls to your replicas over gRPC. Requests from users (through the gateway) and server-sent event streams stay HTTP.

- **`Handle(CallRequest) → CallReply`:** the same meaning as the HTTP route at `path`.
  - The simplest correct implementation hands the request to your own HTTP routes. User Management and Map forward it to `http://127.0.0.1:<PORT>` over loopback; in Go, call your `http.Handler.ServeHTTP` with an `httptest.NewRecorder()`. Either way, guards, validation, task limits and logs stay the HTTP ones.
  - Keep checking `x-gateway-secret` (it is in `headers`).
  - Do not inject requests into a live Express app with tools like light-my-request: they rewire the request prototype that every later HTTP request shares.
- **`Deliver(EventDelivery) → DeliveryReply`:** one event of a topic you subscribed to (section 6.3).
  - Check the metadata `x-gateway-secret`.
  - `OK` = handled. `ALREADY_EXISTS` counts as handled too: you had the event already.
  - **Rejected for good**, so the event goes to the dead-letter channel:
    - `INVALID_ARGUMENT`, `NOT_FOUND`, `FAILED_PRECONDITION` and `OUT_OF_RANGE`;
    - `UNIMPLEMENTED`;
    - `UNAUTHENTICATED` and `PERMISSION_DENIED`.

    This mirrors the final HTTP 4xx answers of section 6.3. Retrying a wrong `x-gateway-secret` or a missing method cannot succeed; once it is fixed, replay the dead letter (section 6.5).
  - Any other error (use `UNAVAILABLE`) is retried later. `DEADLINE_EXCEEDED` counts as a failed attempt.

### 3.4 Rerouting and idempotency (grade 10)

A failed attempt counts towards the replica's breaker: no connection, no answer within 2 s, or 500/502/503/504. The broker then tries **another replica**:

- **always** when the request never reached the replica (connection refused or reset);
- otherwise only when the request can be repeated: `GET`, `HEAD`, `OPTIONS`, `PUT`, `DELETE`, or any request with an `Idempotency-Key` header.

Send `Idempotency-Key` on commands that may be retried; most services already honour it since Lab 2. The whole request, queue wait and reroutes included, gets 4.5 s, so the gateway (5 s) always has an answer.

## 4. Gateway → service: subscriber-based queues (grade 6)

The gateway authenticates the user, finds the service that owns the path (its route table: "the gateway knows the services to which to send the request") and sends the request to that service's **queue** in the broker: `ANY {BROKER_URL}/v1/queues/{service}{path}`, with `X-Auth-User-Id`, `X-Auth-Roles`, `X-Gateway-Secret` and `X-Request-Id`.

- **Subscribers:** every service has one queue, and its subscribers are the replicas the service registered.
- **Waiting:** a request waits in the queue, first in first out, until a replica has room. The broker keeps at most 50 requests in flight on one replica (the services' task limit), so bursts queue in the broker instead of failing with the services' `503 TOO_MANY_CONCURRENT_TASKS`.
- **Unchanged for users:** the request body, response, status and streaming (SSE) are unchanged; `X-Upstream-Instance` names the replica.
- **No service routes (grade 8):** the gateway serves no `/internal/...` route any more; they answer `404 ROUTE_NOT_FOUND`. It keeps one circuit breaker, on the broker itself.
- **JWKS:** in the team stack the gateway also fetches its JWKS through the `user-management` queue, so a frozen User Management replica is rerouted around.

## 5. Load balancing and circuit breakers (grades 5 and 10)

Both moved from the gateway to the broker.

- **Choice of replica:**
  - Skipped: replicas Service Discovery marks `down`, replicas whose breaker is open, and replicas at 50 in flight.
  - Among the rest, the **least loaded** wins. Load is the higher of the utilization Service Discovery polled from the replica's `/status` (`load.utilization`) and the broker's own in-flight requests on it ÷ 50.
  - Replicas with the same load take turns (round-robin).
- **Breaker per replica** (Lab 3, section 8):
  - 3 failures within 17.5 s (5 s × 3.5) open it, and the broker logs `circuit.opened`.
  - It also evicts the replica through Service Discovery (`POST /v1/instances/{id}/evictions`, 30 s quarantine) and logs `instance.removed`.
  - After 17.5 s, one trial request goes through (`circuit.half_open`); success closes the breaker (`circuit.closed`).
- **High availability:** the request that tripped the breaker, and every later one, goes to another replica (section 3.4). Users see no error while one replica of a service is alive.

## 6. Topics between services (grade 6) and durable delivery (grade 9)

### 6.1 Names and payloads

- **Topic names:** lower-case dotted words, `<entity>.<event>`: `user.registered`, `friend.removed`, `users.nearby`.
- **Payload:** JSON. Use the team event envelope (README, "Asynchronous event contract"): `{event_id, type, version, producer, occurred_at, correlation_id, payload}`.
- **Publishing from a database change:** write the event in the same transaction as the change (an outbox, like User Management and Map), so the event leaves only once the change is committed.

### 6.2 Publishing

Publish without knowing who listens, either way:

- **HTTP:** `POST {broker}/v1/topics/{topic}/events` with the service token, `Content-Type: application/json` and the JSON payload. An `Idempotency-Key` (or `X-Event-Id`) header makes it the event ID.
- **gRPC:** `Broker.Publish({topic, payload, event_id, content_type})` with the token in the metadata.

The broker answers `202 {event_id, topic, subscribers, duplicate}` once the event is stored durably. Publishing the same event ID again stores it once (`duplicate: true`), so an outbox may retry safely.

### 6.3 Subscribing

1. **List the topics in your registration** with Service Discovery: `"topics": ["friend.removed", "user.*"]`. Allowed forms are an exact name, a `prefix.*` pattern or `*` (section 8).
2. **Receive deliveries**, in one of two ways:
   - **gRPC `ServiceEndpoint.Deliver`**, if you registered a `grpc_port`.
   - **HTTP `POST /internal/v1/events`** on your service, with the payload as the body and these headers:
     - `X-Event-Topic`, `X-Event-Id`, `X-Event-Source`, `X-Event-Published-At`, `X-Event-Attempt`;
     - plus `X-Request-Id`, `X-Gateway-Secret`, and `X-Service-Name: message-broker`.

     Answer `2xx` once the event is handled. Answer `4xx` (except 408, 425 and 429) to reject it for good: the event goes to the dead-letter channel. Answer `5xx` or nothing to have it retried.
3. **Delivery is at least once.** Deduplicate on the event ID, or make the handler idempotent; Map re-arms a pair, so a repeat changes nothing.

### 6.4 What the broker guarantees (durable queues)

- **Durable:** an event, and one delivery per subscribed **service**, is written to SQLite on the volume `broker-data` (WAL, `synchronous=FULL`) before the publisher gets `202`.
  - Deliveries that were in flight when the broker stopped are queued again when it starts (`store.recovered`).
  - Verified: an event published while Map was stopped survived a broker restart and reached Map when it came back.
- **One replica per service:** each subscribing service gets the event once, on one of its replicas, chosen like any request (section 5).
- **Retries:** a failed delivery is tried again after 1, 2, 4, 8 and 16 s, on another replica when possible; there are 6 attempts in total.
- **Waiting:** while a subscriber has no replica to take the delivery (none registered, every breaker open, every replica full), the delivery waits and is checked every 5 s **without using an attempt** (`delivery.waiting`).
- **Durable subscriptions:** a service keeps its subscriptions for 24 h after its last replica left, so events published while it is completely stopped wait for it.
- **Expiry:** an event older than 1 h (`EVENT_TTL_MS`) is not delivered any more.

### 6.5 Dead-letter channel (grade 9)

A delivery goes to the dead-letter channel when:

- the subscriber rejects it (`rejected`);
- it fails 6 times (`max_attempts`);
- or it outlives `EVENT_TTL_MS` (`expired`).

The broker logs `delivery.dead_lettered` (ERROR).

- `GET {broker}/v1/dead-letters?topic=&subscriber=&limit=` lists them: event ID, topic, publisher, subscriber, payload, reason, attempts, last error and replica.
- `POST /v1/dead-letters/{id}/replay` sends one back to its queue with fresh attempts (needs `Authorization: Bearer <BROKER_ADMIN_TOKEN>`).
- `DELETE /v1/dead-letters/{id}` drops one (same token).

### 6.6 Topic catalogue

| Topic | Publisher | Payload (`payload` of the envelope) | Subscribers today | Suggested subscribers |
| --- | --- | --- | --- | --- |
| `user.registered` | User Management | `{user_id, username, display_name}` | — | Notification (welcome), Tamagotchi (starter pet) |
| `friend.requested` | User Management | `{friendship_id, requester_id, recipient_id}` | — | **Notification** (it was the Lab 1 RabbitMQ consumer) |
| `friend.accepted` | User Management | `{friendship_id, user_ids: [a, b]}` | — | Notification, Guild |
| `friend.removed` | User Management | `{friendship_id, user_ids: [a, b]}` | **Map** | Guild (invites need a friendship) |
| `enemy.marked` | User Management | `{user_id, enemy_id}` | — | Battle |
| `enemy.unmarked` | User Management | `{user_id, enemy_id}` | **Map** | — |
| `users.nearby` | Map | `{user_ids, ...}` (`UsersNearby`) | — | **Notification** (push), Battle |
| `guild.invited` | Guild (to add) | the `GuildInvited` event of `/internal/v1/dev/events` | — | **Notification** |
| `raid.activation-requested` | Package Registry | `RaidActivationRequested`: `{schedule_id, revision, definition_id, definition_version, guild_id, starts_at}` | **Monster Raid** | — |
| `raid.cancellation-requested` | Package Registry | `RaidCancellationRequested`: `{schedule_id, revision}` | **Monster Raid** | — |
| `raid.started`, `raid.finished` | Monster Raid | `RaidStarted` `{raid_id, guild_id, ends_at}`; `RaidFinished` `{raid_id, guild_id, state, participant_ids}` | — | **Notification**, Tamagotchi |
| `battle.finished` | Battle (to add) | battle ID, winner, loser | — | **Notification**, Tamagotchi |

The `/internal/v1/dev/events` and `/internal/v1/dev/raid-events` endpoints were the Lab 2 stand-ins for a broker. They become topics: the producer publishes, and the consumer subscribes and keeps its handler.

## 7. Thread-per-request and the topic list (grade 7)

- **HTTP:** the broker's server (`ThreadingHTTPServer`) starts a thread for every connection and closes the connection after the response, so **every request runs on a thread of its own** (`http-<n>` in the logs).
- **gRPC:** the server uses an executor that starts a new thread per call (`grpc-<n>`).
- **Deliveries:** every delivery also runs on its own thread (`deliver-<n>`). `GET /status` shows `threads: {model: "thread-per-request", active: N}`.
- **Topic list:** `GET {broker}/v1/topics` (and gRPC `Broker.ListTopics`) lists every topic known from registrations or publications, with its subscribers and counters (`published`, `delivered`, `pending`, `dead_letters`), plus the subscription patterns.

## 8. Service Discovery 0.5.0: registration fields

`POST /v1/instances` accepts two optional fields; Lab 3 registrations keep working unchanged:

```json
{"service": "map", "instance_id": "map-3f2a1b9c4d5e", "host": "172.18.0.7", "port": 8086, "version": "0.5.0",
 "grpc_port": 9086, "topics": ["enemy.unmarked", "friend.removed"]}
```

- `grpc_port`: 1–65535. The broker reaches the replica over gRPC for service-to-service calls and deliveries.
- `topics`: at most 50. Each is an exact name, a `prefix.*` pattern or `*`. Invalid names are refused with `422 INVALID_FIELDS`.
- Both come back in every `Instance`, which is how the broker learns the subscriptions.
- `message-broker` may register too (it does, with `grpc_port: 50051`).
- `GET /metrics` exports every replica's health, load, in-flight tasks and request counters from the `/status` polls (section 9).

## 9. Monitoring and logs (grades 4 and 10)

### 9.1 Prometheus and Grafana

Prometheus scrapes three components every 5 s (`monitoring/prometheus.yml`):

- **Service Discovery** `/metrics`: every replica of every service, built from its `/status`, so no service needs its own metrics endpoint: `discovery_replica_up`, `discovery_replica_load`, `discovery_replica_in_flight`, `discovery_replica_requests_total`, `discovery_replica_rejected_total`, `discovery_replica_timeouts_total`, `discovery_alerts_active`.
- **The broker** `/metrics`: queue depth, in flight and load per replica, breaker states, reroutes, published and delivered events, dead letters, threads, request durations.
- **The gateway** `/metrics`: requests by service and status, latency, the breaker on the broker.

Grafana (<http://localhost:3000>, viewable without logging in) opens on the provisioned dashboard **Tamagotchi Go: services, broker and logs**: replicas, requests and load per service, gateway statuses and latency, queues, breakers, reroutes, topic events, deliveries, and two log panels.

### 9.2 Loki

Grafana Alloy reads the stdout of every container of the Compose project through the Docker API and ships it to Loki with the labels `project`, `service` (the Compose service), `container` and `replica` (`monitoring/config.alloy`). The JSON log lines of Lab 3 (section 3) need no change.

### 9.3 Downloading the logs (grade 4)

`GET /api/v1/admin/logs` on the gateway, for admins only: a JWT with the `admin` role (the seed admin through `GATEWAY_ADMIN_USER_IDS`). Other users get `403`.

| Parameter | Default | Meaning |
| --- | --- | --- |
| `since` | `1h` | `30s`, `15m`, `2h`, `1d` (at most 7 days) |
| `service` | all | e.g. `map`, `message-broker` |
| `level` | all | `DEBUG`, `INFO`, `WARN` or `ERROR` |
| `request_id` | — | One request across every service |
| `contains` | — | A text the line contains |
| `limit` | 5000 | The newest lines |
| `format` | `ndjson` | Or `text` |

The answer is a file (`Content-Disposition: attachment; filename="tamagotchi-logs-<time>.ndjson"`): every log line as written, in time order, each with the `container` it came from. If Loki does not answer, the gateway returns `503 LOGS_UNAVAILABLE`.

## 10. Configuration

| Component | Variables (new in Lab 4) |
| --- | --- |
| Broker | `GATEWAY_SECRET`, `INTERNAL_SERVICE_TOKENS`, `BROKER_ADMIN_TOKEN` (optional), `DISCOVERY_URL`, `DISCOVERY_TOKEN`; timings in its README |
| Gateway | `BROKER_URL` (`http://message-broker:8090`), `LOKI_URL` (`http://loki:3100`), `LOGS_MAX_LINES`; `JWKS_URL` through the broker. Removed: `*_URL` of the services, `INTERNAL_SERVICE_TOKENS`, `DISCOVERY_REFRESH_MS` |
| Every service | `GATEWAY_URL` → `http://message-broker:8090` (in Compose) |
| Services using gRPC | `BROKER_GRPC_URL` (`message-broker:50051`), `GRPC_PORT` (`90xx`); User Management and Map also `EVENT_PUBLISHER=broker` |
| `.env` | `BROKER_ADMIN_TOKEN` (`openssl rand -hex 24`), `GRAFANA_ADMIN_PASSWORD` (optional) |

## 11. Postman (grade 3)

- **The 25 `/internal/...` requests** of the service collections now use `{{broker_url}}` (`http://localhost:8090`), since the gateway no longer serves them. The variable is in every collection and in `local.postman_environment.json`.
- **`postman/lab-4-broker.postman_collection.json`** demonstrates the lab grade by grade: queues, topics, the dead-letter channel, `/internal` → 404 at the gateway, gRPC counters, metrics, Prometheus, Grafana and the log download. It needs `broker_admin_token` (`BROKER_ADMIN_TOKEN`) and `map_service_token` (`MAP_SERVICE_TOKEN`).
- **The smoke workflow** runs all of them.
- **Owners:** update your collection when you move a `/internal/v1/dev/*` call to a topic.

## 12. What each owner does

**Every service, already done in Compose (no action):**

- calls through the broker (section 3.1);
- 2 replicas;
- its logs collected by Loki;
- its load in Prometheus through Service Discovery.

**Every owner (Sava: Battle, Tamagotchi; Vica: Guild, Notification; Sabina: Monster Raid, Package Registry):**

1. **Grade 8, gRPC.**
   - Call other services with `Broker.Call` instead of HTTP (section 3.2; set `BROKER_GRPC_URL` in Compose).
   - Serve `ServiceEndpoint` on a gRPC port, and register `grpc_port` (sections 3.3 and 8).
2. **Grade 6, topics.**
   - Publish your domain events on topics instead of `/internal/v1/dev/*`.
   - Subscribe to the topics you consume: list them in `topics` at registration, and handle `Deliver` or `POST /internal/v1/events` (section 6).

   Suggested split, from the catalogue in section 6.6:
   - **Vica:** Notification subscribes to `friend.requested` and `users.nearby`; Guild publishes `guild.invited`.
   - **Sabina:** Package Registry publishes `raid.activation-requested` and `raid.cancellation-requested` (the Lab 0 routing keys; a cancellation is its own event); Monster Raid subscribes to both and publishes `raid.started` and `raid.finished` ([lab-4-contract-sabina.md](lab-4-contract-sabina.md)).
   - **Sava:** Battle publishes `battle.finished`; Tamagotchi subscribes to it.
3. **Release.**
   - Images `0.5.0`, with Compose updated (image, `GRPC_PORT`, `BROKER_GRPC_URL`) in a PR to `dev`.
   - Contract notes `docs/lab-4-contract-<name>.md` (what you implemented and verified).
   - Postman collection updated.
