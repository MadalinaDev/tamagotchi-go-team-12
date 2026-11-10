# Lab 4 — Sabina's Monster Raid and Package Registry

This page covers **tamagotchi-monster-raid-service:0.5.0** and
**tamagotchi-package-registry-service:0.5.0**, the Lab 4 versions of Monster
Raid and Package Registry (NestJS + Prisma), and how they were verified.

- They implement the "every owner" items of the
  [Lab 4 conventions](lab-4-conventions.md), section 12: grade 8 (gRPC client
  and endpoint) and grade 6 (topics).
- Everything in the Lab 1–3 pages still applies unless this page says
  otherwise.
- Mădălina's parts are in [lab-4-contract-madalina.md](lab-4-contract-madalina.md),
  Sava's in [lab-4-contract-sava.md](lab-4-contract-sava.md).

Repositories:

- [sabinapopescu/monster-raid-service](https://github.com/sabinapopescu/monster-raid-service):
  #11, released to `main` by #12 (`39d6cc7`);
- [sabinapopescu/package-registry-service](https://github.com/sabinapopescu/package-registry-service):
  #9, released by #10 (`546dd35`).

CI published both `0.5.0` images from those commits. Each README has a
"Message Broker (Lab 4)" section with the details.

## What changed

| | Monster Raid | Package Registry |
| --- | --- | --- |
| Image | `sabinapopescu/tamagotchi-monster-raid-service:0.5.0` | `sabinapopescu/tamagotchi-package-registry-service:0.5.0` |
| HTTP port / gRPC port (`grpc_port`) | 8087 / **9087** | 8088 / **9088** |
| gRPC client (`Broker.Call`) | Guild, Tamagotchi, Package Registry, User Management | User Management, Guild |
| `ServiceEndpoint.Handle` | `/internal/v1/raids/by-schedule/{schedule_id}` | the four `/internal/v1/…` routes: registrations, care definitions, package, raid definitions |
| `ServiceEndpoint.Deliver` | `raid.activation-requested`, `raid.cancellation-requested` | no subscription: every event is rejected (`INVALID_ARGUMENT`) |
| Publishes (`Broker.Publish`) | `raid.started`, `raid.finished` | `raid.activation-requested`, `raid.cancellation-requested` |
| Subscribes (`topics` in the registration) | `["raid.activation-requested", "raid.cancellation-requested"]` | none (`[]`) |
| New tables | `outbox_events`, `inbox_events`, `schedule_tombstones` (migration `20261109000000_lab4_outbox_inbox`) | `outbox_events` (migration `20261109000000_lab4_outbox`) |

Neither service adds a public REST route. Both keep the HTTP fallback
(`GATEWAY_URL`) for running alone. Without `BROKER_GRPC_URL` they behave as in
Lab 3, and events are only logged.

The Lab 1 stand-in `POST /internal/v1/dev/raid-events` now answers only with
`USE_MOCKS=true`. In the team stack it is `404`: a raid exists only because
Package Registry published its activation (section 6.6).

## gRPC client (section 3.2)

- **Connection.** One long-lived `@grpc/grpc-js` channel per replica to
  `BROKER_GRPC_URL` (`message-broker:50051`). It reconnects by itself, with
  the backoff capped at 5 s.
- **Call.** `Broker.Call(CallRequest)` sends:
  - `service`, set to the wire name;
  - the HTTP `method`;
  - the `path` with its query;
  - lower-case `headers`;
  - the JSON `body`.

  The metadata carries `authorization: Bearer <SERVICE_TOKEN>` and
  `x-request-id`. The client classes and DTOs of Lab 3 are unchanged; only
  the transport underneath changed.
- **Idempotency.** Every Monster Raid command sends an `Idempotency-Key`, so
  the broker may reroute these POSTs (section 3.4):
  - a reservation key per join attempt;
  - the settlement and wallet operation IDs;
  - the release key.

  Package Registry only sends GETs.
- **Answer.** `CallReply` has HTTP semantics, so the status handling of Lab 3
  is unchanged. A 404 is "not found", business errors keep the dependency's
  code, and 5xx/429 become `503 DEPENDENCY_UNAVAILABLE`. The broker's own
  errors (`NO_REPLICA`, `CIRCUIT_OPEN`, `QUEUE_TIMEOUT`,
  `UPSTREAM_UNAVAILABLE`, `UPSTREAM_TIMEOUT`) arrive the same way.
- **Breaker.** The Lab 3 breaker per dependency still wraps the call.
  - Failures: a reply status of 500 or more, and gRPC `UNAVAILABLE`,
    `DEADLINE_EXCEEDED` or `RESOURCE_EXHAUSTED` (the broker unreachable or at
    its limit).
  - `UNAUTHENTICATED` (a wrong `SERVICE_TOKEN`) is logged as
    `rpc.call_refused` (ERROR) and does not count.
- **Deadline.** `RPC_TIMEOUT_MS` (4000).
- **Logs.** `rpc.call` (INFO, WARN on failure) replaces `http.call` for calls
  through the broker. It has `dependency`, `method`, `path`, `status` or
  gRPC `code`, `upstream_instance`, `duration_ms` and `request_id`.

## gRPC endpoint (section 3.3)

Both services serve `tamagotchi.broker.v1.ServiceEndpoint` on `GRPC_PORT` and
register it as `grpc_port`. Registration starts only after the HTTP and the
gRPC port listen, for example:

```json
{"service": "monster-raid", "instance_id": "monster-raid-0bab566f009b", "host": "172.25.0.21", "port": 8087,
 "version": "0.5.0", "grpc_port": 9087, "topics": ["raid.activation-requested", "raid.cancellation-requested"]}
```

### `Handle(CallRequest) → CallReply`

- Only paths under `/internal/v1/` are served. Anything else is
  `404 ROUTE_NOT_FOUND` in the team error body.
- The request is forwarded over loopback to the replica's own HTTP port
  (`http://127.0.0.1:<PORT>`), as the conventions ask, never injected into
  the Express app. Guards, validation, the 50-task limit, `TASK_TIMEOUT_MS`
  and the access log are the HTTP ones. A `Handle` therefore also counts in
  the `utilization` the broker balances on.
- `x-gateway-secret`, `x-service-name` and `x-request-id` arrive in
  `headers`, set by the broker, and the existing guards check them.
  Failures are statuses in the reply, never gRPC errors.

### `Deliver(EventDelivery) → DeliveryReply`

The metadata `x-gateway-secret` is checked first. A wrong or missing one is
`UNAUTHENTICATED`, which the broker dead-letters at once.

### Logs

One `rpc.request` line per incoming call:

- `rpc` (`Handle` or `Deliver`);
- `method` and `path`, or `topic`;
- `status` or `code`;
- `duration_ms`, `request_id` and `caller`.

## Topics (section 6)

Payloads are the team envelope
`{event_id, type, version, producer, occurred_at, correlation_id, payload}`,
and `event_id` is also the broker's event ID.

Both services publish through a **transactional outbox**:

- The row is written in the transaction that changes the state it reports.
- A relay in every replica claims due rows with `FOR UPDATE SKIP LOCKED`
  and calls `Broker.Publish`.
- A row is marked sent only after the broker's OK.
- A failure is retried after 1, 2, 4, … 30 s with the same `event_id`, which
  the broker stores once.
- The event carries the request ID of the request that caused it, so one
  `request_id` follows an activation from the admin's request into Monster
  Raid.

| Topic | Publisher | Payload (`payload` of the envelope) | Subscribers |
| --- | --- | --- | --- |
| `raid.activation-requested` | Package Registry (`RaidActivationRequested`) | `{schedule_id, revision, definition_id, definition_version, guild_id, starts_at}` | Monster Raid |
| `raid.cancellation-requested` | Package Registry (`RaidCancellationRequested`) | `{schedule_id, revision}` | Monster Raid |
| `raid.started` | Monster Raid (`RaidStarted`) | `{raid_id, guild_id, ends_at}` | none yet (suggested: Notification) |
| `raid.finished` | Monster Raid (`RaidFinished`) | `{raid_id, guild_id, state, participant_ids}`; `state` is `completed`, `failed` or `cancelled` | none yet (suggested: Notification, Tamagotchi) |

**Topic names.** The scheduling topics are the Lab 0 routing keys rather than
the single `raid.scheduled` of the catalogue's first draft, because a
cancellation is its own event. Section 6.6 now lists them.

**Event IDs.** Package Registry's event IDs are deterministic per
(schedule, revision), and Monster Raid's per (raid, started/finished). A
retried transition or a second replica therefore publishes the same ID.

An example of the envelope Monster Raid receives (illustrative IDs):

```json
{
  "event_id": "1d8f8b0e-6c0a-5e58-9c41-3b4a0f2a77c1",
  "type": "RaidActivationRequested", "version": 1, "producer": "package-registry",
  "occurred_at": "2026-11-10T09:12:04.481Z",
  "correlation_id": "6f1f3c0a-2a77-4d0e-9a8e-2b7c1d9e5f10",
  "payload": {
    "schedule_id": "6f1f3c0a-2a77-4d0e-9a8e-2b7c1d9e5f10", "revision": 1,
    "definition_id": "00000000-0000-4000-8000-0000000000d1", "definition_version": 1,
    "guild_id": "00000000-0000-4000-8000-0000000000c1", "starts_at": "2026-11-10T09:12:04.470Z"
  }
}
```

### What Monster Raid does with the two topics

Delivery is at least once and unordered (Lab 0 rules), so:

- **Inbox.** Each event ID is saved in `inbox_events` in the same
  transaction as its effect, and the broker gets `OK` only after the commit.
  A known ID answers `OK` and logs `event.duplicate`. One raid per
  `schedule_id` deduplicates as well.
- **Activation.**
  - Monster Raid reads the raid definition from Package Registry and the
    guild from Guild, both with `Broker.Call`.
  - It then creates the raid, `active`, or `failed` when the guild is gone or
    the deadline has passed.
  - `RaidStarted` is committed with the raid.
- **Cancellation** (new in Lab 4):
  - An `active` raid becomes `cancelled`. Its reservations are released
    without rewards, and `RaidFinished` with `state: cancelled` follows.
  - A raid that is settling or already ended keeps its outcome.
  - A cancellation that arrives before the activation leaves a row in
    `schedule_tombstones`, so the later activation creates no raid.
  - An advisory lock per schedule keeps the activation and the cancellation
    of one schedule from interleaving.

### Answers of `Deliver`

| Situation | gRPC answer | The broker |
| --- | --- | --- |
| Handled, or the event ID is already in `inbox_events` (`event.duplicate`), or the schedule already has its raid | `OK` | delivered |
| Not a JSON envelope, wrong `type` or `version`, `event_id` not a UUID, payload fails validation, or `producer` not `package-registry` | `INVALID_ARGUMENT` (`event.rejected`) | dead letter, reason `rejected` |
| Published by another service than Package Registry (the delivery's `source`, which the broker takes from the publisher's token) | `INVALID_ARGUMENT` (`event.rejected`) | dead letter, reason `rejected` |
| Activation of a raid definition that does not exist | `FAILED_PRECONDITION` (`event.rejected`) | dead letter, reason `rejected` |
| Topic other than the two subscribed | `INVALID_ARGUMENT` | dead letter |
| Database down, a dependency unavailable, or the pets of a cancelled raid not yet released | `UNAVAILABLE` | retried after 1, 2, 4, 8, 16 s, on another replica when possible. A cancellation's redelivery resumes the release |
| Wrong or missing `x-gateway-secret` | `UNAUTHENTICATED` (`auth.rejected`) | dead letter at once |

## Configuration

| Variable | Default | Meaning |
| --- | --- | --- |
| `BROKER_GRPC_URL` | empty | Broker gRPC address (`message-broker:50051`). Empty = Lab 3 behaviour: HTTP through `GATEWAY_URL`, and log-only events |
| `GRPC_PORT` | 9087 (Monster Raid), 9088 (Package Registry) | Port of `ServiceEndpoint`, also the registered `grpc_port` |
| `SERVICE_TOKEN` | — | The service token, sent as `authorization: Bearer …` metadata (the broker's `INTERNAL_SERVICE_TOKENS`) |
| `GATEWAY_SECRET` | — | Checked on every HTTP request, on `Handle` (through the HTTP guard) and on `Deliver` |
| `RPC_TIMEOUT_MS` | 4000 | Deadline of `Broker.Call` and `Broker.Publish` |

Extras, not needed by the team stack:

- `GET /metrics` with the team's metric names and a few business counters;
- `checks.broker` in `/status`;
- `LOG_DIR` for log files (Loki already collects stdout).

## Compose

- Both services run `0.5.0` as two replicas each, with
  `BROKER_GRPC_URL: message-broker:50051`.
- `GRPC_PORT` is 9087 and 9088, under `expose:` only, with no host port.
- There is no `GATEWAY_URL`, and they start after the broker is healthy.
- Monster Raid keeps `USE_MOCKS: "false"`, so its dev route is off.

## Postman (section 11)

- **Monster Raid** creates its raids the Lab 4 way:
  1. The admin schedules and activates a raid in Package Registry.
  2. The collection polls `GET /internal/v1/raids/by-schedule/{schedule_id}`
     until the event has been consumed.
  3. Activating again answers `409` and leaves one raid.
- **The stream test** uses a raid cancelled through
  `raid.cancellation-requested`, instead of the dev route's late activation.
- **A new `[Lab 4] Broker` folder** checks:
  - the registration (`grpc_port` 9087, the two topics);
  - the broker's topic list (Monster Raid subscribes, and `raid.started` and
    `raid.finished` were published);
  - that the dev route answers `404`.
- **Package Registry** gains the same registration check (9088, no topics).
  It also checks that its activation and cancellation were published, with
  Monster Raid as subscriber.

## Verification

**The stack.** The full stack of this compose file ran on 2026-11-10, side by
side with another copy on remapped host ports, with alerts off.

- **Images:** Monster Raid and Package Registry `0.5.0` were built locally
  from #11 (`c28cbcd`) and #9 (`0fc6a84`). The release commits
  `39d6cc7` and `546dd35` have the same file trees, so the published
  images are the code tested here. All other images were the published ones:
  the broker, Service Discovery, the gateway, User Management, Map, Battle and
  Tamagotchi `0.5.0`, and Guild and Notification `0.4.1`.
- **Before that,** both services ran against the released broker and Service
  Discovery `0.5.0` alone, with a Guild stub. 15 checks passed, including
  durability and the dead-letter channel.

| Check | Result |
| --- | --- |
| `docker compose up -d --wait` | 25 containers; every container with a healthcheck `healthy`; 18 replicas registered |
| `GET :8089/v1/services` | both Monster Raid replicas: `version 0.5.0`, `grpc_port 9087`, `topics ["raid.activation-requested","raid.cancellation-requested"]`; both Package Registry replicas: `grpc_port 9088`, `topics []` |
| The Monster Raid and Package Registry collections | Monster Raid 56 requests, 92 assertions; Package Registry 36 requests, 85 assertions; 0 failures |
| The other six collections and the Lab 4 collection | Battle 36, Tamagotchi 35, Guild 88, Notification 34, User Management 54, Map 24, Lab 4 broker 30 assertions; 0 failures |
| An admin activates a schedule through the gateway | `202`; the raid exists in Monster Raid (`active`) |
| The broker's log for that request ID | `topic.published` for `raid.activation-requested`, `delivery.succeeded`, then `grpc.request` lines with `caller: monster-raid`. Package Registry's raid definition was reached over gRPC `Handle` (`transport: grpc`) and Guild's guild over HTTP (Guild registers no `grpc_port` yet), then `topic.published` for `raid.started` |
| Monster Raid's and Package Registry's own logs, same request ID | Monster Raid: `rpc.request Deliver raid.activation-requested -> OK`, `raid.created`, `event.handled`, `event.published`. Package Registry: `rpc.request Handle GET /internal/v1/raid-definitions/… -> 200` with `caller: monster-raid` |
| The collection's raid (join, kill, settlement) | `Broker.Call` from Monster Raid to Tamagotchi (`tamagotchi-reservations` 201, `tamagotchi-settlements` 200), User Management (`wallets/settlements` 200) and Package Registry (care and raid definitions 200). Every attempt to these replicas went over gRPC `Handle` |
| An event on `raid.activation-requested` published with the broker's operator token, with an invalid payload | dead letter at once: `reason: rejected`, `attempts: 1`, `last_error: gRPC INVALID_ARGUMENT: published by operator, expected package-registry; payload.schedule_id: isUuid; …` |
| Durability | both Monster Raid replicas stopped, a schedule activated: `202`, `pending 1`; `docker compose restart message-broker`: still `pending 1`; Monster Raid started: the raid appeared (`active`) |
| High availability | one Monster Raid replica paused during 40 s of `GET /api/v1/raids` through the gateway (8 requests per second): 224 requests, all `200`; 3 rerouted (`X-Broker-Attempts: 2`); the broker logged `request.rerouted`, `circuit.opened` and `instance.removed` for the paused replica |
| Unit tests | Monster Raid: `eslint`, `tsc` and 200 `jest` tests; Package Registry: `tsc` and 118 tests. They use real gRPC servers on random ports for `Broker.Call`, `Broker.Publish`, `Handle` and `Deliver`; CI is green on both PRs |

## Bugs found on the way

- **Two drafts of the contract.** Both services were first written against
  a draft of the conventions with a different proto (`Consumer` instead of
  `ServiceEndpoint`, `x-broker-secret`). They were moved to the merged
  `proto/broker.proto` before any release, and the scratch stack against the
  released broker confirmed the wire format.
- **Route labels.** The `/metrics` route label turned `:package_id` into
  `{package}_id`. Snake-case route parameters are now kept whole.

## Open items

- **Subscribers.** Nobody subscribes to `raid.started` or `raid.finished`
  yet. Notification could notify the guild members and the participants
  (conventions, section 6.6).
- **Guild over HTTP.** Guild registers no `grpc_port` yet, so the broker
  reaches it over HTTP. Monster Raid's and Package Registry's calls to Guild
  move to gRPC by themselves once it does.
