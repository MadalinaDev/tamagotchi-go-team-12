# Lab 2 implemented contract — Sabina

This addendum describes **tamagotchi-monster-raid-service:0.3.2** and **tamagotchi-package-registry-service:0.3.1**, the Lab 2 versions of Monster Raid and Package Registry. They implement the per-service items of the Lab 2 conventions (section 3). Everything in the [Lab 1 page](lab-1-contract-sabina.md) still applies unless this page says otherwise. Owners of affected services: please review the sections that concern you.

## Behind the gateway (both services)

- **Reachability.** In [`docker-compose.yml`](../docker-compose.yml) both services use `expose:` instead of `ports:`. They are reachable from `gateway-service` on the compose network, but not from the host. Clients use `http://localhost:8080` (the gateway).
- **Users.** The services no longer read `X-Mock-User-Id` / `X-Mock-Roles`, and `AUTH_MODE` is gone. The gateway validates `Authorization: Bearer <JWT>`, does not forward it, and sets `X-Auth-User-Id` (the token subject, a UUID) and `X-Auth-Roles` (comma-separated). The `admin` role is the global admin. A missing or non-UUID `X-Auth-User-Id` returns `401`, and a missing role returns `403`.
- **Services.** `/internal/v1` routes require `X-Service-Name`, which the gateway sets for service callers. Without it they return `401`.
- **Gateway secret (0.3.1).** With `GATEWAY_SECRET` set, every request must carry the gateway's matching `X-Gateway-Secret`, checked before anything else, otherwise `401`. The comparison is constant-time. Empty means not checked, which is the compose default until the gateway runs there.
- **Outgoing calls.** Calls to other services go to `GATEWAY_URL` (`http://gateway-service:8080`), never to another service's host. Every call sends `X-Service-Name: monster-raid` or `X-Service-Name: package-registry`, plus `SERVICE_TOKEN` as `Authorization: Bearer` when it is set. Each attempt has a 2 s timeout, with one retry for reads and idempotent commands. An unreachable dependency becomes `503 DEPENDENCY_UNAVAILABLE`, and business errors keep the dependency's status and code.
- **Seed (Package Registry 0.3.1).** With `SEED_ON_START=true` (set in compose), Package Registry seeds PetHub `…00a1` and MoodPets `…00a2` with care definitions v1, the registrations Alice → both, Bob → PetHub, Carol → MoodPets, and Big Slime `…00d1` v1. It only seeds empty tables (see [`db/seed.md`](../db/seed.md)). Tamagotchi and Battle need these packages to create and reserve pets.
- **Real calls and remaining mocks.** In the team compose file both services run with `USE_MOCKS=false`, and `MOCK_DEPENDENCIES` keeps single dependencies mocked:

  | Service | Real, through the gateway | Still mocked | Why |
  | --- | --- | --- | --- |
  | Package Registry | User Management (`GET /internal/v1/users/{id}`), Guild (`GET /internal/v1/guilds/{id}`) | — | — |
  | Monster Raid | Guild (guild, membership), Package Registry (raid and care definitions) | Tamagotchi | Tamagotchi 0.3.0 rejects every raid reservation of a user who has a secondary pet selected: `409 TAMAGOTCHI_CONFLICT` with `secondary_pet_id: null` (raids use only the primary, Lab 0 contract), `422 INVALID_TAMAGOTCHI` with the secondary. The team smoke's Tamagotchi collection gives Alice a secondary pet, so no raid can be joined after it. Without a secondary pet the real path works end to end: reservation, busy-pet `409`, XP settlement (Ember XP 0 → 100, level 2) and release on the kill. |
  | Monster Raid | | User Management (wallet settlements) | User Management 0.1.1 checks raid rewards against its own mock raid definition and rejects the real one (`reward_per_recipient does not match the pinned raid definition`), which would leave every won raid in `settling` |

  Checked in the full team stack: a package with a newly registered user as developer is accepted (only the real User Management knows that user), the Guild service logs Monster Raid's membership checks and Package Registry's guild lookups, a raid played to the kill ends `completed`, and all eight Postman collections pass.

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

With `gateway-service` in the compose file, the smoke workflow runs both collections through the gateway, with `service_token` set to `RAID_SERVICE_TOKEN` / `REGISTRY_SERVICE_TOKEN`. Without a gateway it falls back to [`.github/smoke/sabina-services-probe.js`](../.github/smoke/sabina-services-probe.js) inside the compose network.

[`postman/monster-raid-service.postman_collection.json`](../postman/monster-raid-service.postman_collection.json) and [`postman/package-registry-service.postman_collection.json`](../postman/package-registry-service.postman_collection.json) now target the gateway (`gateway_base_url` in the shared environment). The first request of a run logs Alice, Bob and the admin in through `POST /api/v1/auth/login` (seed password `password123`). The Raid collection also registers a fresh outsider. Requests then send `Authorization: Bearer <access token>`. Internal requests send the service credential from the `service_token` environment variable.

The Raid collection joins with Alice's current primary pet (read from `GET /api/v1/tamagotchi-selections/me`) and checks damage by formula, so it works against the mock and the real Tamagotchi. It then attacks until the monster dies (one request that repeats itself with `setNextRequest`), and checks that the raid is `completed` and Alice's reward `applied`: the kill settles the raid and frees the pet, so the collection can be re-run. It also has a **Live updates (SSE)** folder. It creates an already-ended raid, checks that its stream answers `200 text/event-stream` with one `raid` snapshot and closes, and checks that a non-member gets a JSON `403`.

## CI and images

Each service repository has `.github/workflows/ci.yml`. Pull requests into `dev` and `main` run the type check and unit tests. A push to `main` also builds the image and pushes `sabinapopescu/tamagotchi-<service>:<package.json version>` and `:latest` to Docker Hub. The version is `0.3.x` for Lab 2. The workflow reads the `DOCKERHUB_USERNAME` and `DOCKERHUB_TOKEN` repository secrets.

The Lab 2 releases were published by that workflow. `:latest` has the same digest as the newest one:

| Image | Release | Submodule | Adds |
| --- | --- | --- | --- |
| [`sabinapopescu/tamagotchi-monster-raid-service:0.3.2`](https://hub.docker.com/r/sabinapopescu/tamagotchi-monster-raid-service) | sabinapopescu/monster-raid-service#8 | `services/monster-raid-service` at `813b138` | new reservation `Idempotency-Key` per join attempt: a join refused because the pet was busy can be retried once the pet is free (with one key per (raid, user), the real Tamagotchi replayed the old `409` forever) |
| `sabinapopescu/tamagotchi-monster-raid-service:0.3.1` | sabinapopescu/monster-raid-service#6 | — | gateway secret check |
| [`sabinapopescu/tamagotchi-package-registry-service:0.3.1`](https://hub.docker.com/r/sabinapopescu/tamagotchi-package-registry-service) | sabinapopescu/package-registry-service#6 | `services/package-registry-service` at `67bc3cf` | seed, gateway secret check |
| `sabinapopescu/tamagotchi-monster-raid-service:0.3.0` | sabinapopescu/monster-raid-service#3 | — | first Lab 2 release |
| `sabinapopescu/tamagotchi-package-registry-service:0.3.0` | sabinapopescu/package-registry-service#4 | — | first Lab 2 release |

## Gateway changes for these services

MadalinaDev/gateway-service#3 (Sabina's gateway part: Raid/Registry routes and the task-limit middleware):

- The concurrent task limit answers `503 TOO_MANY_CONCURRENT_TASKS` with `Retry-After: 1` (was 429), as in section 1 of the Lab 2 conventions and in these services.
- An open SSE stream gives its task slot back once its headers are sent, so long-lived raid streams cannot block other requests.
- The upstream connection pool is no longer capped by the task limit. Before, as many open streams as the limit made every other request time out (504).
- Tests for every Monster Raid / Package Registry route and service-to-service call, plus an end-to-end run of the gateway image in front of both 0.3.1 images.

## Open items

| Item | Depends on |
| --- | --- |
| Monster Raid → Tamagotchi for real (pets, reservations, settlements) | Tamagotchi checking only `primary_pet_id` against the stored selection for `kind: "raid"` reservations (Sava) |
| Monster Raid → User Management wallet settlements for real | User Management checking raid rewards against Package Registry's raid definitions instead of its mock (Mădălina) |
| The published `madalina060504/tamagotchi-gateway-service:0.3.0` predates gateway-service#3 and #5; compose still uses Sava's temporary build | A new gateway `dev` → `main` release (Mădălina) |
| Admins recognised from the token. User Management's access tokens (0.1.1) carry only `sub`, `iss`, `aud`, `iat`, `exp` and `jti`, with no roles. In the meantime the gateway treats the users in `GATEWAY_ADMIN_USER_IDS` (the seeded admin `…0009`) as `admin`. | A roles claim in User Management's access token (Mădălina) |
