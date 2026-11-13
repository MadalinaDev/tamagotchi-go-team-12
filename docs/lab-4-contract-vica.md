# Lab 4 — Vica's Guild and Notification

This page describes **tamagotchi-guild-service:0.5.0** and **tamagotchi-notification-service:0.5.0**, the Lab 4 versions of Guild and Notification (Go), and how they were verified. They implement the "every owner" items of the [Lab 4 conventions](lab-4-conventions.md) (section 12): gRPC client and endpoint (grade 8) and topics (grade 6).

Repositories: [vikanicologlo/guild-service](https://github.com/vikanicologlo/guild-service) and [vikanicologlo/notification-service](https://github.com/vikanicologlo/notification-service), branch `feat/lab-4/grpc-and-topics`. Each README has a "Lab 4 at a glance" section.

## What changed

| | Guild | Notification |
| --- | --- | --- |
| HTTP port / gRPC port (`grpc_port`) | 8083 / **9083** | 8084 / **9084** |
| gRPC client (`Broker.Call`) | User Management, Package Registry | Guild |
| `ServiceEndpoint.Handle` | the `/internal/v1/guilds/...` routes | the `/internal/v1/...` routes |
| Publishes (`Broker.Publish`) | `guild.invited` (`GuildInvited`), from an outbox | — |
| Subscribes (`topics`, `Deliver`) | none: `Deliver` answers `FAILED_PRECONDITION` | `friend.requested`, `users.nearby`, `guild.invited`, `raid.started`, `raid.finished` |

No public REST route changes. Without `BROKER_GRPC_URL` both services behave as in Lab 3 (HTTP through `GATEWAY_URL`), so each still runs alone.

## gRPC client (section 3.2)

- **Connection.** One long-lived `grpc.NewClient` connection to `BROKER_GRPC_URL` (`message-broker:50051`). It connects lazily and reconnects by itself, so a broker that starts later is no startup failure. `/status` shows `extra.broker_grpc: ok | down`.
- **Calls.** The client classes and their DTOs are unchanged; only the transport under them is new. Metadata: `authorization: Bearer <SERVICE_TOKEN>` and `x-request-id`. Deadline `RPC_TIMEOUT_MS` (4000 ms).
- **Breaker.** The Lab 3 breaker per dependency still wraps every attempt. Failures: gRPC `UNAVAILABLE`, `DEADLINE_EXCEEDED` and other broker errors, and replies of `500` or more. A `404` is an answer, not a failure.
- **Logs.** `rpc.call` (INFO, WARN on failure, with the gRPC `code` when there was no reply) replaces `http.call`.

## gRPC endpoint (section 3.3)

Both services serve `tamagotchi.broker.v1.ServiceEndpoint` on `GRPC_PORT`. Registration (`POST /v1/instances`) starts only once the HTTP and the gRPC port listen, and carries `grpc_port` and `topics`:

```json
{"service": "notification", "instance_id": "notification-5183ee2f4a10", "host": "172.18.0.9", "port": 8084,
 "version": "0.5.0", "grpc_port": 9084,
 "topics": ["friend.requested", "guild.invited", "raid.finished", "raid.started", "users.nearby"]}
```

- **`Handle`.** The call becomes an `http.Request` that runs through the service's own `http.Handler` into an `httptest.ResponseRecorder`, in process. The gateway-secret guard, validation, the 50-task limit, `TASK_TIMEOUT` and the `http.request` log are therefore the HTTP ones. Only `/internal/...` paths are served (`404 ROUTE_NOT_FOUND` otherwise). HTTP failures are statuses in the reply, never gRPC errors.
- **`Deliver`.** The metadata `x-gateway-secret` and `x-service-name` become headers, and the delivery runs through `POST /internal/v1/events` (the HTTP delivery route of section 6.3) in process. Its HTTP answer becomes the gRPC code (next section).
- **Logs.** `rpc.request` for each incoming call (`rpc`, `method`/`path` or `topic`/`event_id`, `status`, `code`, `duration_ms`, `caller`).
- **Proto.** `proto/broker.proto`, copied unchanged from the broker. The Go code is generated into `internal/brokerpb` with `protoc-gen-go` 1.35.2 and `protoc-gen-go-grpc` 1.5.1 (`grpc` 1.67.3, so `go 1.22` stays).

## Topics (section 6)

### Guild publishes `guild.invited`

- **Outbox.** Creating an invite writes the `GuildInvited` envelope to `outbox_events` in the **same transaction** as the invite (migration `000003_outbox`). A failed invite (for example `INVITE_ALREADY_PENDING`) leaves no event.
- **Relay.** It publishes with `Broker.Publish` right after the commit, and every second for pending rows. Replicas claim rows with `FOR UPDATE SKIP LOCKED`. A failed publish is retried after 1, 2, 4 … 60 s with the **same event ID**, which the broker stores once. Sent rows are dropped after a day.
- **Logs.** `event.published` (with the subscribers the broker named) and `event.publish_failed`.
- **Effect.** An invite no longer depends on Notification being up. In Lab 3 it was posted to Notification's `/internal/v1/dev/events`.

Example, as delivered to Notification:

```json
{
  "event_id": "45f9cb20-78f6-42f7-801f-1978f990049a",
  "type": "GuildInvited", "version": 1, "producer": "guild",
  "occurred_at": "2026-11-10T21:18:15.204Z",
  "correlation_id": "38293a4c-1b63-4b95-a4e6-f67d92b546c8",
  "payload": {
    "invite_id": "38293a4c-1b63-4b95-a4e6-f67d92b546c8",
    "guild_id": "00000000-0000-4000-8000-0000000000c1",
    "inviter_id": "00000000-0000-4000-8000-000000000001",
    "invitee_id": "00000000-0000-4000-8000-000000000002"
  }
}
```

### Notification subscribes

| Topic | Type | Producer | Inbox entry for |
| --- | --- | --- | --- |
| `friend.requested` | `FriendRequested` | User Management | the recipient |
| `users.nearby` | `UsersNearby` | Map | both users of the encounter |
| `guild.invited` | `GuildInvited` | Guild | the invitee |
| `raid.started` | `RaidStarted` | Monster Raid | every member of the guild (read from Guild with `Broker.Call`) |
| `raid.finished` | `RaidFinished` | Monster Raid | the participants |

The body of a delivery is the Lab 0 `Event<T>` envelope, the same one `/internal/v1/dev/events` takes, so the existing handler does the work. Delivery is at least once: the inbox is unique per `(event_id, recipient_id)`, so a redelivery creates nothing and logs `event.duplicate`.

### Answers of `Deliver` and `POST /internal/v1/events`

| Situation | HTTP | gRPC | The broker |
| --- | --- | --- | --- |
| Handled, or already handled | `200` | `OK` | delivered |
| Topic not subscribed | `422 UNKNOWN_TOPIC` (gRPC: checked first, `FAILED_PRECONDITION`) | `FAILED_PRECONDITION` | dead letter, `rejected` |
| Not valid JSON | `400` | `INVALID_ARGUMENT` | dead letter, `rejected` |
| Type is not the topic's type; publisher is not the envelope's `producer`; invalid envelope or payload | `422 INVALID_EVENT` | `INVALID_ARGUMENT` | dead letter, `rejected` |
| Wrong or missing `x-gateway-secret` | `401` | `UNAUTHENTICATED` | dead letter, `rejected` |
| Guild unavailable (raid members), database error, task limit, timeout | `503`, `500`, `504` | `UNAVAILABLE` | retried |

## Bottleneck found on the way

Inviting a user checks four things in other services: the invitee exists, the inviter's friendships, and both users' package registrations. Through the broker, one after the other, they took about 2 s in the team stack: the services under amd64 emulation answer in 0.3–0.5 s. That is the broker's limit per attempt (section 3.4). The broker timed the invite out, rerouted it to the second replica, timed it out again, and the user got `504`. The four lookups are independent, so they now run at once (about 0.1 s together). They are still checked in the contract's order, so the error a caller sees does not change.

## Configuration

| Variable | Default | Meaning |
| --- | --- | --- |
| `BROKER_GRPC_URL` | empty | Broker gRPC address (`message-broker:50051`). Empty = Lab 3 behaviour |
| `GRPC_PORT` | `0` | Port of `ServiceEndpoint`, also the registered `grpc_port`; `0` = no gRPC server |
| `RPC_TIMEOUT_MS` | `4000` | Deadline of `Broker.Call` and `Broker.Publish` |
| `SERVICE_TOKEN` | — | Unchanged; sent as `authorization: Bearer …` (the broker's `INTERNAL_SERVICE_TOKENS`) |

## Compose

Both images are `0.5.0` with `BROKER_GRPC_URL: message-broker:50051`, `GRPC_PORT` 9083 / 9084, and the gRPC port in `expose`. `GATEWAY_URL` stays as the Lab 3 fallback.

## Verification

| What | Result |
| --- | --- |
| Tests | `go vet` and `go test -race ./...` with the Postgres suites pass in both repositories; coverage of `internal/` without the generated code: Guild 95.8 %, Notification 96.8 %. New tests cover the broker client and the endpoint over an in-memory gRPC connection, the broker transport and its breaker, the outbox in both storages, the relay, the delivery route, gRPC `Deliver`/`Handle` on the real routes, and the registration fields |
| Registration | `GET :8089/v1/services`: both replicas of each service `up`, version `0.5.0`, `grpc_port` 9083 / 9084, Notification's five topics |
| Topic list | `GET :8090/v1/topics`: `friend.requested`, `users.nearby`, `guild.invited`, `raid.started`, `raid.finished` with subscriber `notification` |
| Invite end to end | `POST /api/v1/guilds/{id}/invites` through the gateway: `201`. One `request_id` showed Guild's `rpc.call`s, `invite.created`, `event.published`; the broker's `topic.published` and `delivery.succeeded`; Notification's `event.received`, `notification.created` and `rpc.request Deliver`. Bob's inbox had the `GuildInvited` about 0.1 s after the publish |
| Notification → Guild over gRPC | A `raid.started` published with Monster Raid's token: Notification's `rpc.call` to Guild, the broker's `http.call` with `transport: grpc`, Guild's `rpc.request Handle`; one inbox entry per member |
| `friend.requested` | A real friend request through the gateway: User Management's outbox published it, Notification created the recipient's entry |
| Dead letters | A `guild.invited` published with producer `map`: `GET :8090/v1/dead-letters` listed it, reason `rejected`, 1 attempt, `INVALID_EVENT: published by guild but the producer is "map"` |
| Durability | Both Notification replicas stopped, an invite created: `201`, `guild.invited` `pending 1`. Notification started: delivered within ~3 s, `pending 0` |

The stack for these runs was Postgres, Service Discovery, the broker and the gateway `0.5.0`, User Management and Package Registry `0.5.0` (one replica each), and Guild and Notification `0.5.0` (two replicas each). The whole compose file (about 23 containers) did not fit in the 3.8 GB the Docker VM has on an 8 GB Mac: after a while Postgres stopped answering its health checks. The presentation laptop needs more memory for Docker.

## Open items

| Item | Depends on |
| --- | --- |
| A `users.nearby` from the real Map and a `raid.started` / `raid.finished` from the real Monster Raid, end to end | A run of the whole stack on a machine with enough memory; both were verified with events published by hand |
| The Postman check that Bob's inbox gets the `GuildInvited` (Guild collection) | The smoke workflow of this PR (Newman could not be run locally) |
