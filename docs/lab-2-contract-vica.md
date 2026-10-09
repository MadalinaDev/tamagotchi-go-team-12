# Lab 2 implemented contract — Vica

This addendum describes **tamagotchi-guild-service:0.3.0** and **tamagotchi-notification-service:0.3.0**, the Lab 2 versions of Guild and Notification. They implement the per-service items of the Lab 2 conventions (section 3) and Guild's WebSocket chat (grade 7). Everything in the [Lab 1 page](lab-1-contract-vica.md) still applies unless this page says otherwise. Owners of affected services, please review the sections that concern you: the gateway (Mădălina, Sava, Sabina), User Management (Guild calls it), and every service that sends events to Notification.

## Behind the gateway (both services)

- **Reachability.** In [`docker-compose.yml`](../docker-compose.yml) Notification uses `expose:` only. Guild keeps `8083:8083` published, but only for the direct chat WebSocket that the gateway hands out (`GUILD_PUBLIC_WS_URL=ws://localhost:8083`). Clients use `http://localhost:8080`.
- **Users.**
  - The services no longer read `X-Mock-User-Id` / `X-Mock-Roles`.
  - The gateway validates `Authorization: Bearer <JWT>`, does not forward it, and sets `X-Auth-User-Id` (the token subject) and `X-Auth-Roles` (comma-separated).
  - A missing or non-UUID `X-Auth-User-Id` returns `401 UNAUTHENTICATED`.
- **Services.** `/internal/v1` routes require `X-Service-Name`, which the gateway sets from the caller's service token. Without it they return `401`.
- **Gateway secret.** Both services accept `/api` and `/internal` requests only when `X-Gateway-Secret` equals their `GATEWAY_SECRET` (constant-time compare); anything else is `401`.
  - The gateway strips any client-supplied secret and identity headers.
  - This matters for Guild: its port is public for the socket, so a request sent straight to `localhost:8083` with a forged `X-Auth-User-Id` must be rejected.
  - `GET /health` stays open for the container healthcheck.
- **Request IDs.** The gateway's `X-Request-Id` is reused when it is a UUID, so one ID follows a request through the gateway and the services. It is returned in `X-Request-ID` and in error bodies.
- **Outgoing calls.**
  - Calls to other services go to `GATEWAY_URL` (`http://gateway-service:8080`) with `Authorization: Bearer $SERVICE_TOKEN` (the `guild=` / `notification=` entry of the gateway's `INTERNAL_SERVICE_TOKENS`).
  - Each attempt has a 2 s timeout, with two retries with backoff for network errors and `5xx`.
  - A `404` keeps its meaning (not found), and any other failure becomes `503 DEPENDENCY_UNAVAILABLE` with `Retry-After`.
- **Mocks.** `USE_MOCKS=true` keeps the Lab 1 mocks. With `USE_MOCKS=false`, `MOCK_DEPENDENCIES` keeps single dependencies mocked.

## Task timeout and concurrent task limit (both services)

The limits are Go middleware around `/api` and `/internal`: a buffered semaphore and `context.WithTimeout`. Both errors use the shared error envelope.

| Limit | Value | When reached |
| --- | --- | --- |
| Task timeout | `TASK_TIMEOUT_MS=5000` | `504 TASK_TIMEOUT`. The request context is cancelled, so database calls stop |
| Concurrent task limit | `MAX_CONCURRENT_TASKS=50` requests in flight, no queueing | `503 TOO_MANY_CONCURRENT_TASKS` with `Retry-After: 1` |

- **No late writes:** the handler writes into a buffer, so a late handler never writes over the `504`.
- **Slots:** a timed-out request keeps its slot until its work really finishes, so the limit always counts the work in flight. This is the same rule as Sabina's interceptor.
- **Not limited:** `/health` and open chat sockets. Each `chat.send` on a socket has its own 5 s deadline.
- **Status code:** `503`, the team rule in [`lab-2-conventions.md`](lab-2-conventions.md), as in the gateway and Sabina's services.

## Guild — WebSocket chat (grade 7)

These routes implement the Lab 0 chat contract. In Lab 1 they were skipped.

| Method / path | Caller | Success |
| --- | --- | --- |
| `POST /api/v1/guilds/{guild_id}/chat-tickets` `{}` | Member, through the gateway | `201 {ticket: string, expires_at: Time}` |
| `GET /api/v1/guilds/{guild_id}/ws?ticket=...` | The gateway answers `200 {ws_url}`; the client then connects **directly** to Guild | `101` WebSocket upgrade |

- **Tickets:** 32 random bytes (base64url), single-use, valid for 30 s and bound to the guild and user. They are kept in memory.
  - A missing, unknown, used, expired or other-guild ticket is `401` before the upgrade.
  - Membership is rechecked when the socket opens (`403 NOT_GUILD_MEMBER`).
  - Query strings are never logged, so tickets do not reach the logs.
- **Frames** follow the Lab 0 table:
  - `chat.send` `{client_message_id, text}` stores the message with the same rules as REST (1–2000 characters, unique `(author_id, client_message_id)`).
  - `chat.ack` `{client_message_id, message_id}` is sent after persistence. An identical resend gets the original `message_id` and is not broadcast again.
  - `chat.message` `{message}` is broadcast to every open socket of the guild, for socket and REST sends alike. Membership is rechecked before delivery.
  - `chat.error` `{client_message_id | null, error}` uses the shared error body: `CLIENT_MESSAGE_ID_REUSED`, `VALIDATION_FAILED`, `MALFORMED_REQUEST` or `TASK_TIMEOUT`.
- **Closing:** leaving, removal and disband close the user's or the guild's sockets with `1008`. A forbidden `chat.send` also closes with `1008`. A server shutdown closes with `1001`, and a client that cannot keep up gets `1013`.
- **Heartbeat:** a ping every 30 s; two missed pongs close the socket.
- **Scaling:** sockets are fanned out in memory, so all members of a guild must reach the same Guild instance. That holds with the single replica in the compose file.
- **Gateway side:** already in `gateway-service`. `GET /api/v1/guilds/{id}/ws` returns `{"ws_url": "<GUILD_PUBLIC_WS_URL>/api/v1/guilds/{id}/ws?ticket=..."}` and never proxies the socket. `POST .../chat-tickets` is proxied like any `/api/v1/guilds` route.

## Guild — calls through the gateway

| Call | Owner | In compose |
| --- | --- | --- |
| `GET /internal/v1/users/{user_id}` (invitee exists) | User Management | Real, through the gateway |
| `GET /internal/v1/users/{user_id}/relationships` (accepted friendship) | User Management | Real, through the gateway |
| `GET /internal/v1/users/{user_id}/package-registrations` (shared package) | Package Registry | Real, through the gateway (Registry 0.3.1 seeds the convention packages and registrations) |
| `POST /internal/v1/dev/events` (`GuildInvited`) | Notification | Real, through the gateway |

- **`MOCK_DEPENDENCIES`** (`user-management`, `registry`, `notification`) can still keep single dependencies mocked when one has no data. The compose file needs none since Package Registry 0.3.1 seeds Alice (packages A and B), Bob (A) and Carol (B), which is exactly what the mock returned.
- **`GuildInvited`** is sent to Notification's temporary intake instead of RabbitMQ. A delivery failure is logged and the invite still succeeds, because there is no outbox yet.

## Notification — calls through the gateway

| Call | Owner | In compose |
| --- | --- | --- |
| `GET /internal/v1/guilds/{guild_id}/members` (`RaidStarted` recipients) | Guild | Real, through the gateway |

`POST /internal/v1/dev/events` is unchanged, but it is now reached through the gateway with a service token. Any service may call it: its `producer` field is still validated against the event table.

## Postman

[`postman/guild-service.postman_collection.json`](../postman/guild-service.postman_collection.json) (41 requests) and [`postman/notification-service.postman_collection.json`](../postman/notification-service.postman_collection.json) (15 requests) now target the gateway (`gateway_base_url` in the shared environment). They are generated by [`postman/gen_vica_collections.py`](../postman/gen_vica_collections.py).

- **Login:** the first requests log Alice, Bob, Carol and the admin in through `POST /api/v1/auth/login` (seed password `password123`), and requests then send `Authorization: Bearer <access token>`.
- **Internal requests** send `{{service_token}}`: one of the `*_SERVICE_TOKEN` values from `.env`, passed with `--env-var service_token=...`. The smoke workflow passes `RAID_SERVICE_TOKEN`.
- **Guild collection checks:**
  - gateway protection: no token is `401`, and a forged identity sent straight to `:8083` is `401`;
  - the seeded flows, including a real User Management lookup;
  - the chat ticket and the gateway's `ws_url` negotiation;
  - the internal routes.
- **Notification collection checks:** the seeded inbox, devices, preferences, deduplicated events, `RaidStarted` resolved through the real Guild, and that the event intake needs a service token.
- **Re-runs:** both collections pass twice in a row against the same data.
- **The socket itself:** Newman cannot open a WebSocket. Guild's Go tests connect real WebSocket clients, and the live check below did the same against the compose stack.

## CI and images

Each repository has `.github/workflows/ci.yml`:

- **Pull requests into `dev` and `main`:** `gofmt`, `go vet` and `go test -race`, with a Postgres service container so the repository suite also runs on Postgres.
- **Push to `main`:** builds `linux/amd64` + `linux/arm64` and pushes `nikvnln/tamagotchi-<service>:<VERSION>` and `:latest`. `VERSION` is `0.3.0` for Lab 2.
- **Secrets:** the workflow reads the `DOCKERHUB_USERNAME` and `DOCKERHUB_TOKEN` repository secrets.

Coverage of `internal/` with the Postgres suite, as measured in CI, is 94.7% (Guild) and 95.6% (Notification).

## Verified against the compose stack

The stack was a fresh volume, with Guild and Notification `0.3.0` pulled from Docker Hub as published by CI, the gateway, and every other service at its current image, all with `USE_MOCKS=false` for Guild and Notification. Results:

- All ten containers started, and every one with a healthcheck was healthy.
- Gateway protection:
  - a JWT through the gateway is `200`, and no token is `401`;
  - a forged `X-Auth-User-Id` sent straight to `:8083` is `401`;
  - Notification is not reachable from the host.
- Bob left Founders and Alice invited him back: the friendship was checked in the real User Management, the shared package in the real Package Registry, and Bob's inbox got the `GuildInvited` delivered through the gateway. An unknown invitee was `404 USER_NOT_FOUND` from the real User Management.
- A `RaidStarted` event sent through the gateway reached all three Founders members, resolved through the real Guild.
- Chat: the ticket (`201`) and `ws_url` (`200`) came through the gateway, the socket connected directly (`101`), and a message reached both members while the sender got `chat.ack`. No ticket appeared in Guild's logs.
- Postman: guild 88/88 and notification 34/34 assertions passed, twice in a row. In the same run every other team collection passed: battle 30, tamagotchi 29, user-management 50, map 23, monster-raid 56, package-registry 82.

## Open items

| Item | Depends on |
| --- | --- |
| `GuildInvited` and the other events over RabbitMQ with an outbox | Later lab |
