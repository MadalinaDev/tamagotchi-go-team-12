# Lab 4 — Sava's Battle and Tamagotchi

This page describes **tamagotchi-battle-service:0.5.0** and **tamagotchi-tamagotchi-service:0.5.0**, the Lab 4 versions of Battle and Tamagotchi (Go), and how they were verified. They implement the "every owner" items of the [Lab 4 conventions](lab-4-conventions.md), section 12: grade 8 (gRPC client and endpoint) and grade 6 (topics). Everything in the Lab 1–3 pages still applies unless this page says otherwise. Mădălina's parts (broker, gateway, Service Discovery, User Management, Map) are in [lab-4-contract-madalina.md](lab-4-contract-madalina.md).

Repositories: [Ekkusuu/battle-service](https://github.com/Ekkusuu/battle-service) and [Ekkusuu/tamagotchi-service](https://github.com/Ekkusuu/tamagotchi-service), branch `feat/lab-4/grpc-and-topics`. Each README has a "Lab 4" section with the details.

## What changed

| | Battle | Tamagotchi |
| --- | --- | --- |
| Image | `ekkusuu/tamagotchi-battle-service:0.5.0` | `ekkusuu/tamagotchi-tamagotchi-service:0.5.0` |
| HTTP port / gRPC port (`grpc_port`) | 8081 / **9081** | 8082 / **9082** |
| gRPC client (`Broker.Call`) | User Management, Tamagotchi, Package Registry | Package Registry |
| `ServiceEndpoint.Handle` | only `/internal/v1/…`; Battle serves no such route, so a call gets `401` or `404 ROUTE_NOT_FOUND` | the `/internal/v1/…` routes: pets, reservations, settlements, care stats |
| `ServiceEndpoint.Deliver` | no subscription: every event is rejected (`FAILED_PRECONDITION`) | `battle.finished` |
| Publishes (`Broker.Publish`) | `battle.finished`, `battle.requested` | `pet.activity-started`, `pet.transferred` |
| Subscribes (`topics` in the registration) | none (`[]`) | `battle.finished` |
| New tables | none | `inbox_events`, `battle_results` (migration `000004_lab4_inbox`) |

Neither service adds a public REST route. Both keep the HTTP fallback (`GATEWAY_URL`) for running alone: without `BROKER_GRPC_URL` they behave as in Lab 3 and events are only logged.

## gRPC client (section 3.2)

- **Connection.** One long-lived `grpc.NewClient` connection to `BROKER_GRPC_URL` (`message-broker:50051`). It connects lazily and reconnects by itself, so a broker that starts later is no startup failure.
- **Call.** `Broker.Call(CallRequest)` with `service` set to the canonical name (`user-management`, `tamagotchi`, `package-registry`), the HTTP `method`, the `path` with its query, lower-case `headers` and the JSON `body`. Metadata on every call: `authorization: Bearer <GATEWAY_SERVICE_TOKEN>` and `x-request-id` (the current request ID).
- **Idempotency.** Battle forwards its `Idempotency-Key` (the operation ID of reservations, settlements and wallet settlements) in `headers`, so the broker may reroute these POSTs to another replica (section 3.4) and a retried command is applied once. Tamagotchi only sends GETs.
- **Answer.** `CallReply` has HTTP semantics, so the status handling of Lab 3 is unchanged (`404`/`400` → invalid, `409` → conflict, `408`/`504` → timeout, `5xx`/`429` → dependency unavailable).
- **Timeouts.** A call may take 4.5 s in Battle and 5 s in Tamagotchi (the broker spends up to 4.5 s on queueing and reroutes); the HTTP fallback keeps 2 s.
- **Breaker.** The Lab 3 breaker per dependency still wraps the call. Failures: gRPC `UNAVAILABLE`, `DEADLINE_EXCEEDED` and other broker errors, and a reply status of `500` or more. `UNAUTHENTICATED` means a wrong `GATEWAY_SERVICE_TOKEN`: it is logged as `rpc.unauthenticated` (ERROR) and does not count against the breaker.
- **Logs.** `rpc.call` (INFO, WARN on failure) replaces `http.call` for calls through the broker, with `dependency`, `method`, `path`, `status` or gRPC `code`, `duration_ms`, `request_id`.

## gRPC endpoint (section 3.3)

Both services serve `tamagotchi.broker.v1.ServiceEndpoint` on `GRPC_PORT` and register it as `grpc_port`. Registration (`POST /v1/instances`) starts only after the HTTP **and** the gRPC port listen:

```json
{"service": "tamagotchi", "instance_id": "tamagotchi-56072a86fa9a", "host": "172.21.0.25", "port": 8082,
 "version": "0.5.0", "grpc_port": 9082, "topics": ["battle.finished"]}
```

- **`Handle(CallRequest) → CallReply`.**
  - Only paths under `/internal/v1/` are served. Anything else (a path with `..` or `//` included) is `404 ROUTE_NOT_FOUND` in the team error body.
  - The call becomes an `http.Request` that runs through the service's own `http.Handler` into an `httptest.ResponseRecorder`, in process. Guards, validation, idempotency, the 50-task limit, `TASK_TIMEOUT` and the access logs are therefore the HTTP ones.
  - `x-gateway-secret` and `x-service-name` arrive in `headers`; the existing guard checks them (a missing secret is the usual `401`). Failures are statuses in the reply, never gRPC errors.
  - Reply headers are lower-case; `instance_id` is the replica.
- **`Deliver(EventDelivery) → DeliveryReply`.**
  - The metadata `x-gateway-secret` is checked first. A wrong or missing one is `UNAUTHENTICATED`; the broker treats that code as a rejection (it is in its `REJECTING_GRPC_CODES`), so the event goes to the dead-letter channel at once.
  - Tamagotchi then runs the delivery **under the same task control as an HTTP request**: it takes one of the `MAX_CONCURRENT_TASKS` slots (`/status` counts it), is bounded by `TASK_TIMEOUT` and by the broker's 2 s attempt deadline, and is waited for on shutdown. A full or draining replica answers `UNAVAILABLE`.
  - Battle subscribes to nothing, so it answers `FAILED_PRECONDITION` (dead letter).
- **Logs.** One `rpc.request` line per incoming call: `rpc` (`Handle` or `Deliver`), `method` and `path` or `topic`, `status` or `code`, `duration_ms`, `request_id`, `caller` (`x-service-name`).
- **Shutdown.** On `SIGTERM` the replica leaves Service Discovery first, then the gRPC server drains the running calls (`GracefulStop`), then the HTTP server. If the 10 s deadline passes, the gRPC server is cut off without waiting for it.

## Topics (section 6)

Payloads are the team envelope `{event_id, type, version, producer, occurred_at, correlation_id, payload}`; `event_id` is also the broker's event ID. Both services keep their transactional outbox (claimed with `FOR UPDATE SKIP LOCKED`, retried with the **same `event_id`**); only the relay changed: with `BROKER_GRPC_URL` set it calls `Broker.Publish` and marks a row sent only after the broker's OK, so an event is never lost between the commit and the broker.

| Topic | Publisher | Payload (`payload` of the envelope) | Subscribers |
| --- | --- | --- | --- |
| `battle.finished` | Battle (`BattleCompleted`) | `{battle_id, winner_id, loser_id, captured_pet_id}` | Tamagotchi |
| `battle.requested` | Battle (`BattleRequested`) | `{battle_id, challenger_id, opponent_id}` | none yet (suggested: Notification) |
| `pet.activity-started` | Tamagotchi (`PetActivityStarted`) | `{activity_id, kind, owner_ids, pet_ids}` | none |
| `pet.transferred` | Tamagotchi (`PetTransferred`) | `{operation_id, pet_id, previous_owner_id, new_owner_id}` | none |

`winner_id` and `loser_id` are user IDs; `captured_pet_id` is the loser's primary pet that settlement transferred to the winner. The event ID of `battle.finished` is generated once and stored with the battle, so a relay retry or a second replica publishes the same ID.

Example, as delivered to Tamagotchi:

```json
{
  "event_id": "c55097a6-0455-4949-b126-6000a1ed96d2",
  "type": "BattleCompleted", "version": 1, "producer": "battle",
  "occurred_at": "2026-11-10T05:41:52Z",
  "correlation_id": "37efb0d5-10c9-4ac3-942f-ba96891e446f",
  "payload": {
    "battle_id": "37efb0d5-10c9-4ac3-942f-ba96891e446f",
    "winner_id": "00000000-0000-4000-8000-000000000001",
    "loser_id": "00000000-0000-4000-8000-000000000003",
    "captured_pet_id": "01b77200-3ec2-4015-886d-51524306b4aa"
  }
}
```

### What Tamagotchi does with `battle.finished`

Delivery is at least once and unordered, so the effect is idempotent. Migration `000004_lab4_inbox` adds:

- **`inbox_events(event_id PK, topic, received_at)`**: every event handled.
- **`battle_results(battle_id PK, event_id → inbox_events, winner_id, loser_id, captured_pet_id, occurred_at, recorded_at)`**: the outcome of one battle, kept once per battle.

The inbox row and the `battle_results` row are written in **one transaction**, and the broker gets `OK` only after the commit. The pets and wallets themselves were already settled by Battle (`tamagotchi-settlements`, `wallets/settlements`); this is Tamagotchi's own record of the result.

### Answers of `Deliver`

| Situation | gRPC answer | The broker |
| --- | --- | --- |
| Recorded, or the event ID is already in `inbox_events` (`event.duplicate`, nothing changes) | `OK` | delivered |
| Same battle, new event ID, same result | `OK` (a second inbox row, one `battle_results` row) | delivered |
| Not valid JSON, `producer` not `battle`, `version` not 1, no event ID, bad `occurred_at`, `battle_id`, `winner_id` or `loser_id` not a non-nil UUID, winner = loser, bad `captured_pet_id` | `INVALID_ARGUMENT` (`event.rejected`) | dead letter, reason `rejected` |
| Same battle, a different winner, loser or captured pet | `FAILED_PRECONDITION` (`event.rejected`), nothing written | dead letter, reason `rejected` |
| Topic other than `battle.finished` | `INVALID_ARGUMENT` | dead letter |
| Database error, timeout, task limit reached, shutting down | `UNAVAILABLE` (`event.failed`) | retried after 1, 2, 4, 8, 16 s, on another replica when possible |
| Wrong or missing `x-gateway-secret` | `UNAUTHENTICATED` (`auth.rejected`) | dead letter at once, reason `rejected`, `attempts: 1` (observed with a Tamagotchi started with another `GATEWAY_SECRET`); the conventions' section 3.3 says only the three codes above reject |

## Configuration

| Variable | Default | Meaning |
| --- | --- | --- |
| `BROKER_GRPC_URL` | empty | Broker gRPC address (`message-broker:50051`). Empty = Lab 3 behaviour (HTTP through `GATEWAY_URL`, log-only events). Needs `GATEWAY_SERVICE_TOKEN`; it replaces the `GATEWAY_URL` requirement. |
| `GRPC_PORT` | 9081 (Battle), 9082 (Tamagotchi) | Port of `ServiceEndpoint`, also the registered `grpc_port`; must differ from `PORT`. |
| `GATEWAY_SERVICE_TOKEN` | — | The service token, sent as `authorization: Bearer …` metadata (the broker's `INTERNAL_SERVICE_TOKENS`). |
| `GATEWAY_SECRET` | — | Checked on every HTTP request and on `Deliver`. |

`GATEWAY_URL` is gone from the two services in Compose; `EVENT_PUBLISHER` (User Management, Map) does not exist in the Go services: the broker publisher is on whenever `BROKER_GRPC_URL` is set.

## Compose

Battle and Tamagotchi run `0.5.0` as two replicas each, with `BROKER_GRPC_URL: message-broker:50051`, `GRPC_PORT` 9081 and 9082 (`expose:` only, no host port) and no `GATEWAY_URL`.

## Verification

Full stack of this compose file on 2026-11-10 with alerts switched off (`ALERT_*` empty in the Service Discovery container). Images: Gateway `0.5.0` built from `dev` of MadalinaDev/gateway-service (not published yet), Battle and Tamagotchi `0.5.0` built locally from the branches of battle-service#5 and tamagotchi-service#5, the sources of the published images, the published `0.5.0` images of the broker, Service Discovery, User Management and Map, and the `0.4.x` images of the other services.

| Check | Result |
| --- | --- |
| `docker compose up -d --wait` | 25 containers; every container with a healthcheck `healthy`; 18 replicas registered |
| `GET :8089/v1/services` | both Battle replicas: `version 0.5.0`, `grpc_port 9081`, `topics []`; both Tamagotchi replicas: `grpc_port 9082`, `topics ["battle.finished"]` |
| `GET :8090/v1/topics` | `battle.finished` with subscriber `tamagotchi` |
| The Battle, Tamagotchi and Lab 4 collections | Battle 14 requests, 36 assertions; Tamagotchi 14 requests, 35 assertions; Lab 4 broker 27 requests, 30 assertions; 0 failures |
| The other six collections | Guild 88, Notification 34, User Management 54, Map 24, Monster Raid 77, Package Registry 82 assertions; 0 failures |
| A complete battle (Alice challenges Carol, Carol accepts, 15 turns) through the gateway | `completed`, settlement `pets: applied, currency: applied` |
| The broker's log for that battle | `grpc.request` lines with `caller: battle` for `GET /internal/v1/tamagotchis/{id}`, `POST /internal/v1/tamagotchi-reservations`, `GET …/care-definitions/1` (Package Registry), `POST /internal/v1/tamagotchi-settlements` and `POST /internal/v1/wallets/settlements` (User Management); each followed by an `http.call … (grpc)` line (`transport: grpc`) naming the replica that answered |
| Battle's and Tamagotchi's own logs | `rpc.call` lines in Battle for the same calls; `rpc.request` `Handle` lines in Tamagotchi (`POST /internal/v1/tamagotchi-reservations -> 201`, `POST …/tamagotchi-settlements -> 200`); Tamagotchi's `rpc.call` to `package-registry` when a pet was created |
| `battle.finished` | `topic.published battle published battle.finished … to tamagotchi`, `delivery.succeeded … (attempt 1)`; in Tamagotchi `rpc.request Deliver battle.finished -> OK` and `event.handled` |
| Tamagotchi's database | one `inbox_events` row (the event ID above) and one `battle_results` row (winner, loser, captured pet as published) |
| The same event ID published again through the broker | `202 {"duplicate": true}`; still one `inbox_events` row and one `battle_results` row |
| Same battle, new event ID, same result | accepted: two inbox rows, one `battle_results` row |
| Same battle, new event ID, winner and loser swapped | `FAILED_PRECONDITION`, dead letter with reason `rejected`, nothing written |
| Invalid `battle.finished` (`battle_id` not a UUID, and `winner_id` not a UUID) | `GET :8090/v1/dead-letters?topic=battle.finished`: `reason: rejected`, `attempts: 1`, `last_error: gRPC INVALID_ARGUMENT: battle_id must be a non-nil UUID` |
| Durability | both Tamagotchi replicas stopped (0 registered), `battle.finished` published: `202`, `delivery.waiting … (no_replica)`, `pending 1`; `docker compose restart message-broker`: still `pending 1`; Tamagotchi started: `delivery.succeeded … (attempt 1)`, `pending 0`, one inbox row and one `battle_results` row |
| High availability | one Tamagotchi replica paused during 50 s of `GET /api/v1/tamagotchis` through the gateway (8 requests per second): 399 requests, all `200`; 3 were rerouted (`X-Broker-Attempts: 2`, about 2.1 s); the broker logged `request.rerouted … (timeout)`, then `circuit.opened … after 3 failure(s) within 17500 ms` and `instance.removed`; later requests took one attempt; after `docker unpause` and the 30 s quarantine the replica registered again |
| Unit and integration tests | `go build`, `go vet` and `go test ./...` pass in both repositories with a throwaway Postgres (`TEST_DATABASE_URL`): Battle 181, Tamagotchi 191 passed, none skipped, including the migration up/down test and `TestPostgresRecordBattleResultIsExactlyOnce`. `go test -race ./...` also passes (run in a Linux Go container) |

Not observed on the stack: `event.duplicate` in Tamagotchi's log. The broker stores an event ID once, so a duplicate reaches Tamagotchi only after a redelivery (a lost answer); that path is covered by `TestDeliverKnownEventIsOKAndLoggedAsDuplicate` and `TestPostgresRecordBattleResultIsExactlyOnce` (concurrent deliveries of one event).

## Bugs found on the way

- **Tamagotchi test:** `TestPostgresMigrationsAreSafeWhenReplicasStartTogether` still expected migration version 3. It only fails once a database is given, so CI without Postgres did not show it.
- **Tamagotchi `Deliver`:** it bypassed the task controller, so deliveries ignored `MAX_CONCURRENT_TASKS` and `TASK_TIMEOUT`, were not waited for on shutdown, and `/status` under-reported the load the broker balances on. It now runs under the task control (see "gRPC endpoint").
- **gRPC shutdown (both):** grpc-go's `Stop()` can itself block on a connection that is still closing. `TestShutdownCutsOffCallsWhenTheDeadlinePasses` hung about once in 60 runs under `-race`. Both services now run `Stop()` in its own goroutine once the shutdown deadline has passed.

## Open items

- Publishing: the Gateway's `0.5.0` image is not on Docker Hub yet. It comes with the Gateway's release to `main`, and Compose needs it.
- Nobody subscribes to `battle.requested`, `pet.activity-started` or `pet.transferred` yet. Notification could subscribe to `battle.finished` and `battle.requested` (conventions, section 6.6).
- Service Discovery closes idle connections, so a replica's heartbeat sometimes fails once with `connection reset by peer` or `EOF` and succeeds on the next beat (about every 5 s, 15 s TTL). This predates Lab 4 and did not make any replica leave the registry during the checks above.
