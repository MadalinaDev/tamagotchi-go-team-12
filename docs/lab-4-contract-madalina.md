# Lab 4 — Mădălina's message broker, gateway, Service Discovery, User Management and Map

This page describes what Mădălina's parts of Lab 4 implement of the [Lab 4 conventions](lab-4-conventions.md), and how they were verified. It also covers what they wire into [docker-compose.yml](../docker-compose.yml) for everybody.

## Message broker `0.5.0` (grades 2, 5, 6, 7, 9, 10)

Repository [MadalinaDev/message-broker](https://github.com/MadalinaDev/message-broker), image `madalina060504/tamagotchi-message-broker:0.5.0`, Python 3.12 (the team's banned language). Ports: HTTP 8090, gRPC 50051. The durable store is SQLite on the volume `broker-data`.

- **Repository (grade 2):**
  - a README, the CPR's PR template and PR policy;
  - CI that checks the generated gRPC code against `proto/broker.proto` and runs `ruff` and 37 tests on every PR;
  - the image published on every merge to `main`;
  - linked as the `services/message-broker` submodule.
- **Gateway → service (grade 6):** a queue per service (`/v1/queues/{service}/...`). Its subscribers are the replicas the service registered. A request waits, first in first out, until a replica has room (50 in flight per replica).
- **Service → service (grades 5 and 8):** HTTP on the `/internal/...` contract paths with the service tokens (no change for the services), and gRPC `Broker.Call`. Replicas that registered a `grpc_port` are reached over gRPC `ServiceEndpoint.Handle`.
- **Balancing, breakers, high availability (grades 5 and 10):**
  - The least-loaded replica wins: the higher of Service Discovery's polled utilization and the broker's in-flight ÷ 50. Equal loads take turns.
  - Each replica has a breaker: 3 failures in 17.5 s open it, and the replica is evicted through Service Discovery.
  - A failed attempt is rerouted to another replica when that is safe (conventions, section 3.4).
- **Topics (grade 6):**
  - Publishing over HTTP or gRPC.
  - Subscriptions come from the `topics` of the Service Discovery registrations and are remembered for 24 h.
  - Delivery goes to one replica of every subscribed service, over gRPC `Deliver` or HTTP `POST /internal/v1/events`.
- **Durable queues and dead letters (grade 9):**
  - Events and deliveries are stored before the publisher gets its answer, and recovered after a restart.
  - Retries after 1, 2, 4, 8 and 16 s. A delivery waits, without using attempts, while the subscriber has no replica.
  - The dead-letter channel lists rejected, failed and expired deliveries (`GET /v1/dead-letters`). With the admin token they can be replayed or deleted.
- **Thread-per-request (grade 7):**
  - HTTP: one connection, one request, one thread.
  - gRPC: one thread per call. Each delivery also gets a thread of its own.
  - `GET /v1/topics` and `Broker.ListTopics` list the topics.
- **Monitoring:** Prometheus `/metrics`, and JSON logs with a `thread` field (`http.request`, `grpc.request`, `http.call`, `request.rerouted`, `circuit.opened`, `instance.removed`, `topic.published`, `delivery.*`).

## Gateway `0.5.0` (grades 4, 5, 8)

[gateway-service](https://github.com/MadalinaDev/gateway-service). Sava wrote the Lab 3 gateway; Mădălina made the Lab 4 change:

- **Routing:** every request goes to `{BROKER_URL}/v1/queues/{service}{path}`. The load balancer, the per-replica breakers and the evictions moved to the broker, and the gateway keeps one breaker on the broker. The JWKS also comes through the broker.
- **No service routes:** there is no `/internal` route and no service token any more. `/internal/...` answers `404`.
- **Log download:** `GET /api/v1/admin/logs` (admins) downloads the logs of every container from Loki as NDJSON or text, filtered by service, level, request ID, text and time range.
- **Metrics:** `GET /metrics`.
- **Tests:** 134; the Lab 3 balancer tests moved to the broker.

## Service Discovery `0.5.0` (grades 6, 8, 10)

[service-discovery](https://github.com/MadalinaDev/service-discovery):

- Registrations carry `grpc_port` and `topics` (validated, and returned in every `Instance`).
- `message-broker` may register.
- `GET /metrics` exports every replica's health, load, in-flight tasks and request counters from the `/status` polls.
- Tests: 51.

## User Management and Map `0.5.0` (grades 6, 8)

- **gRPC client (grade 8):** outgoing calls go through gRPC `Broker.Call` when `BROKER_GRPC_URL` is set (Map → User Management, User Management → Package Registry). The per-dependency breakers stay.
- **gRPC endpoint (grade 8):** `ServiceEndpoint` on 9085 and 9086. `Handle` forwards to the replica's own HTTP routes over loopback, so the guards, validation, limits and logs are the HTTP ones. `Deliver` receives topic events and requires `X-Gateway-Secret`. Both register `grpc_port` and their topics.
- **Topics (grade 6):** the transactional outboxes publish on the broker (`EVENT_PUBLISHER=broker`).
  - User Management publishes `user.registered`, `friend.requested`, `friend.accepted`, `friend.removed`, `enemy.marked` and `enemy.unmarked`.
  - Map publishes `users.nearby`.
  - Map subscribes to `friend.removed` and `enemy.unmarked`: two users who are strangers again get their proximity pair re-armed. The handler is idempotent, and malformed events are refused into the dead-letter channel.
- **Tests:** User Management 56, Map 53.

## Compose and monitoring

- **Broker and routing:**
  - The broker runs with its volume.
  - Every service's `GATEWAY_URL` now points at the broker, and every service starts after it is healthy.
  - The gateway, Service Discovery, User Management and Map run `0.5.0`.
- **Monitoring** (grade 10):
  - Prometheus (`monitoring/prometheus.yml`).
  - Loki, with Grafana Alloy reading the containers' logs (`monitoring/config.alloy`).
  - Grafana, with the provisioned data sources and the dashboard `monitoring/grafana/dashboards/tamagotchi-go.json`.
- **`.env`:** `BROKER_ADMIN_TOKEN` and `GRAFANA_ADMIN_PASSWORD` (both optional).
- **Postman:** the internal requests of the collections use `{{broker_url}}`. The new `postman/lab-4-broker.postman_collection.json` walks through the lab grade by grade.

## Verification

The whole stack of this compose file ran on 2026-11-09, with these images:

- the broker, the gateway, Service Discovery, User Management and Map built from their branches;
- the published images of the other services: Battle and Tamagotchi `0.4.0`, Guild and Notification `0.4.1`, Monster Raid and Package Registry `0.4.0`.

| Check | Result |
| --- | --- |
| `docker compose up -d --wait` | 26 containers healthy; 18 replicas registered (the broker included); User Management and Map with `grpc_port`, Map with its topics |
| The eight service collections | 200 requests, 419 assertions, 0 failures. Every service-to-service call went through the broker: HTTP for Guild, Notification, Monster Raid, Package Registry, Battle and Tamagotchi; gRPC for User Management and Map |
| The Lab 4 collection | 27 requests, 30 assertions, 0 failures: the log download (an admin gets the file, a player `403`), the queues, a service call with Map's token, the topics, the gRPC counters, the dead-letter flow (rejected, replayed, rejected again, deleted), the metrics, Prometheus and Grafana |
| One request traced by its ID | gateway → broker queue `map` → Map → gRPC `Broker.Call` → broker → gRPC `Handle` on User Management, all with the same `request_id` |
| `GET /internal/...` through the gateway | `404 ROUTE_NOT_FOUND` |
| Topics | `friend.removed` and `enemy.unmarked`, published by User Management's outbox, delivered to Map (`event.received`, `pair.rearmed`). Consecutive events went to both Map replicas, one replica each |
| Dead-letter channel | A malformed `friend.removed` was refused by Map (`INVALID_ARGUMENT`) and listed by `GET /v1/dead-letters` with reason `rejected` |
| Durability | Map was stopped completely and an event was published. It waited (`delivery.waiting`), survived a broker restart (1 pending before and after) and reached Map when Map came back: `attempt 1`, `pair.rearmed` |
| High availability | One User Management replica was paused, with a cold gateway JWKS cache. Every request answered `200`. Those that hit the paused replica were rerouted (`X-Broker-Attempts: 2`, about 2 s). After 3 failures the breaker opened and the replica was evicted; later requests took one attempt |
| Monitoring | Prometheus targets broker, gateway and Service Discovery `up`; `sum(discovery_replica_up)` = 17. Loki had logs of every service; Grafana healthy with the dashboard |
| Log download | Admin: `200`, `Content-Disposition: attachment; filename="tamagotchi-logs-….ndjson"`, the broker's WARN lines. A player: `403` |
| Unit tests | Broker 37, gateway 134, Service Discovery 51, User Management 56, Map 53 |

A bug found on the way: the first gRPC `Handle` of User Management and Map used light-my-request to call the Express app in-process. It rewires Express's shared request prototype, and later real requests crashed the process. `Handle` now forwards over loopback (conventions, section 3.3).

## Open items

- Teammates: gRPC clients and endpoints, and topics in their services (conventions, section 12). Their services already call through the broker over HTTP.
- Publishing: the broker repository needs the `DOCKERHUB_USERNAME` and `DOCKERHUB_TOKEN` secrets for its image. The `0.5.0` images are published when the service PRs reach `main`. Until then the smoke test cannot pull them.
