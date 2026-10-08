# Lab 2 implemented contract — Sabina

This addendum describes **tamagotchi-monster-raid-service:0.3.0** and **tamagotchi-package-registry-service:0.3.0**, the Lab 2 versions of Monster Raid and Package Registry. They implement the per-service items of the Lab 2 conventions (section 3). Everything in the [Lab 1 page](lab-1-contract-sabina.md) still applies unless this page says otherwise. Owners of affected services: please review the sections that concern you.

## Behind the gateway (both services)

- **Reachability.** In [`docker-compose.yml`](../docker-compose.yml) both services use `expose:` instead of `ports:`. They are reachable from `gateway-service` on the compose network, but not from the host. Clients use `http://localhost:8080` (the gateway).
- **Users.** The services no longer read `X-Mock-User-Id` / `X-Mock-Roles`, and `AUTH_MODE` is gone. The gateway validates `Authorization: Bearer <JWT>`, does not forward it, and sets `X-Auth-User-Id` (the token subject, a UUID) and `X-Auth-Roles` (comma-separated). The `admin` role is the global admin. A missing or non-UUID `X-Auth-User-Id` returns `401`, and a missing role returns `403`.
- **Services.** `/internal/v1` routes require `X-Service-Name`, which the gateway sets for service callers. Without it they return `401`.
- **Outgoing calls.** Calls to other services go to `GATEWAY_URL` (`http://gateway-service:8080`), never to another service's host. Every call sends `X-Service-Name: monster-raid` or `X-Service-Name: package-registry`, plus `SERVICE_TOKEN` as `Authorization: Bearer` when it is set. Each attempt has a 2 s timeout, with one retry for reads and idempotent commands. An unreachable dependency becomes `503 DEPENDENCY_UNAVAILABLE`, and business errors keep the dependency's status and code.
- **Mocks.** `USE_MOCKS=true` (the compose default for now) keeps the Lab 1 in-process mocks. With `USE_MOCKS=false`, `MOCK_DEPENDENCIES` keeps single dependencies mocked, e.g. `MOCK_DEPENDENCIES=tamagotchi` while Tamagotchi does not serve reservations and settlements.

## Task timeout and concurrent task limit (both services)

A global NestJS interceptor bounds every route. Both errors use the shared error envelope.

| Limit | Value | When reached |
| --- | --- | --- |
| Task timeout | `TASK_TIMEOUT_MS=5000` | `504 TASK_TIMEOUT` |
| Concurrent task limit | `MAX_CONCURRENT_TASKS=50` requests in flight | `503 TOO_MANY_CONCURRENT_TASKS` with `Retry-After: 1` |

A request that timed out keeps its slot until its work really finishes, because a transaction cannot be cut off halfway. The limit therefore always counts the work in flight.

## Live raid HP over SSE (Monster Raid, grade 7)

New route, not in the Lab 0 contract:

| Method / path | Caller | Success |
| --- | --- | --- |
| `GET /api/v1/raids/{raid_id}/events` | Current guild member or recorded participant (or admin) | `200 text/event-stream` |

| Event | When | `data` |
| --- | --- | --- |
| `raid` | Right after connecting, then on every state change (`settling`, `completed`, `failed`) | `Raid` |
| `attack` | Every accepted attack, by anyone | `RaidAttack` (with `remaining_hp`) |
| `ping` | Every 15 s while nothing else happens | `{}` |

- The stream ends once the raid is `completed`, `failed` or `cancelled`. For a raid that is already over, the client gets one `raid` event and the stream ends.
- A refused, unknown or malformed raid gets its normal `403` / `404` / `422` JSON error, not a stream. The service writes the stream itself, after the access check, instead of using Nest's `@Sse()`.
- Updates are published only after their transaction commits. Since there is no timer worker, an open stream also fails the raid itself when its deadline passes.
- Updates are fanned out in memory, so all clients of a raid must reach the same instance. That holds with the single replica in the compose file.
- The 5 s task timeout covers only opening the stream. An open stream holds no concurrency slot.

SSE goes **through** the gateway like any other `/api/v1/raids` route (the service port is not published). Only Guild's WebSocket bypasses the gateway. **Gateway requirement:** stream `text/event-stream` responses without buffering, and exempt them from the gateway's own 5 s timeout. Both are part of Sabina's timeout middleware in `gateway-service`.

## Gateway routes these services need

Routed **to** these services (the prefixes proposed in the gateway README):

| Prefix | Service |
| --- | --- |
| `/api/v1/raids`, `/internal/v1/raids`, `/internal/v1/dev/raid-events` | `monster-raid-service:8087` |
| `/api/v1/packages`, `/api/v1/package-registrations`, `/api/v1/raid-definitions`, `/api/v1/raid-schedules`, `/internal/v1/packages`, `/internal/v1/raid-definitions`, `/internal/v1/users/{user_id}/package-registrations` | `package-registry-service:8088` |

Called **by** these services through the gateway, so they must be routed to their owners:

| Caller | Route | Owner |
| --- | --- | --- |
| Package Registry | `GET /internal/v1/users/{user_id}` | User Management |
| Package Registry, Monster Raid | `GET /internal/v1/guilds/{guild_id}` | Guild |
| Monster Raid | `GET /internal/v1/guilds/{guild_id}/members/{user_id}` | Guild |
| Monster Raid | `GET /internal/v1/tamagotchis/{pet_id}`, `POST /internal/v1/tamagotchi-reservations`, `GET /internal/v1/tamagotchi-reservations/{id}`, `POST /internal/v1/tamagotchi-reservations/{id}/release`, `POST /internal/v1/tamagotchi-settlements` | Tamagotchi |
| Monster Raid | `POST /internal/v1/wallets/settlements` | User Management |
| Monster Raid | `GET /internal/v1/raid-definitions/{id}/versions/{version}`, `GET /internal/v1/packages/{id}/care-definitions/{version}` | Package Registry |

Settlement and reservation commands carry a UUID `Idempotency-Key`, which the gateway must pass through.

## Postman

[`postman/monster-raid-service.postman_collection.json`](../postman/monster-raid-service.postman_collection.json) and [`postman/package-registry-service.postman_collection.json`](../postman/package-registry-service.postman_collection.json) now target the gateway (`gateway_base_url` in the shared environment). The first request of a run logs Alice, Bob and the admin in through `POST /api/v1/auth/login` (seed password `password123`). The Raid collection also registers a fresh outsider. Requests then send `Authorization: Bearer <access token>`. Internal requests send the service credential from the `service_token` environment variable.

The Raid collection has a new **Live updates (SSE)** folder. It creates an already-ended raid, checks that its stream answers `200 text/event-stream` with one `raid` snapshot and closes, and checks that a non-member gets a JSON `403`.

## CI and images

Each service repository has `.github/workflows/ci.yml`. Pull requests into `dev` and `main` run the type check and unit tests. A push to `main` also builds the image and pushes `sabinapopescu/tamagotchi-<service>:<package.json version>` and `:latest` to Docker Hub. The version is `0.3.0` for Lab 2. The workflow needs the `DOCKERHUB_USERNAME` and `DOCKERHUB_TOKEN` repository secrets.

## Open items

| Item | Depends on |
| --- | --- |
| Run `USE_MOCKS=false` in the compose file | `gateway-service` in the compose file, and the internal routes above served by their owners |
| The service credential that Postman sends in `service_token`, and that services send in `SERVICE_TOKEN` | The gateway's service authorization (Mădălina) |
| Postman and the smoke workflow reach these services only through the gateway | `gateway-service` in the compose file; the Lab 1 smoke workflow cannot run these two collections until then |
| Bump the `services/` submodules to the Lab 2 merges | The service PRs being merged |
