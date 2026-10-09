# Lab 2 implemented contract — Mădălina

This addendum describes **tamagotchi-user-management-service:0.3.0** and **tamagotchi-map-service:0.3.0**, the Lab 2 versions of User Management and Map. They implement the per-service items of the [Lab 2 conventions](lab-2-conventions.md). Everything in the [Lab 1 page](lab-1-contract-madalina.md) still applies unless this page says otherwise. Owners of affected services, please review the sections that concern you: every service logs in through User Management, Package Registry relies on the new `roles` claim, and Map calls User Management through the gateway.

## Behind the gateway (both services)

- **Reachability.** In [`docker-compose.yml`](../docker-compose.yml) both services use `expose:` instead of `ports:`, with `AUTH_MODE=gateway` and `USE_MOCKS=false`. Clients use `http://localhost:8080` (the gateway).
- **Users.** The gateway validates `Authorization: Bearer <JWT>` and does not forward it. The services take the caller from `X-Auth-User-Id`; a missing or non-UUID value is `401`. `X-Mock-User-Id` is no longer trusted. `AUTH_MODE=mock` remains only for running a private repo on its own.
- **Gateway secret.** Every request must carry `X-Gateway-Secret` equal to the service's `GATEWAY_SECRET`, otherwise `401 UNTRUSTED_CALLER`. A direct call on the compose network therefore cannot forge the identity headers. Two routes are exempt: `GET /health` (Docker health check) and User Management's `GET /api/v1/auth/jwks`, because the gateway fetches the JWKS directly from User Management without its secret.
- **Services.** User Management's `/internal/v1` routes take the caller from `X-Service-Name`, which the gateway sets from the caller's service token. Each route keeps its list of allowed callers (`403 SERVICE_NOT_ALLOWED`). `AUTH_MODE=jwt` and `INTERNAL_SERVICE_TOKENS` are removed from User Management: authorization is the gateway's job.
- **Outgoing calls.** User Management → Package Registry and Map → User Management go to `GATEWAY_URL` (`http://gateway-service:8080`) with the contract paths unchanged, sending `Authorization: Bearer <GATEWAY_SERVICE_TOKEN>` (`USER_MANAGEMENT_SERVICE_TOKEN` / `MAP_SERVICE_TOKEN` in `.env`). Each attempt has a 2 s timeout, now with **one** retry instead of two, so a call fits inside the 5 s task timeout. An unreachable dependency is still `503 DEPENDENCY_UNAVAILABLE` with `Retry-After`.

## Roles in access tokens (User Management)

Access tokens now carry a `roles` claim: `["admin"]` for the global admin (`is_admin`), `[]` for everyone else. The gateway forwards it as `X-Auth-Roles`. This closes the open item in [Sabina's Lab 2 page](lab-2-contract-sabina.md#open-items): admin-only Package Registry routes work through the gateway once User Management `0.3.0` runs. Roles are read when a token is issued, so a change applies at the next login or refresh.

## Task timeout and concurrent task limit (both services)

A global NestJS interceptor bounds every route except `/health` and Map's stream. Both errors use the shared error envelope.

| Limit | Value | When reached |
| --- | --- | --- |
| Task timeout | `TASK_TIMEOUT_MS=5000` | `504 TASK_TIMEOUT` |
| Concurrent task limit | `MAX_CONCURRENT_TASKS=50` requests in flight | `429 TOO_MANY_CONCURRENT_TASKS` with `Retry-After: 1`, refused at once instead of queued |

`429` follows the [Lab 2 conventions](lab-2-conventions.md) and the gateway. A request that timed out keeps its slot until its work really finishes, because a transaction cannot be cut off halfway. If that work then succeeds, its result is stored under the request's `Idempotency-Key`, so a retry with the same key returns it instead of repeating it.

## Live nearby users over SSE (Map, grade 7)

New route, not in the Lab 0 contract:

| Method / path | Caller | Success |
| --- | --- | --- |
| `GET /api/v1/map/stream` | User | `200 text/event-stream` |

| Event | When | `data` |
| --- | --- | --- |
| `users` | Right after connecting, then whenever the visible users or their positions change | `{users: LocatedUser[], generated_at: Time}`, the body of `GET /api/v1/map/users` |
| `error` | A read failed, e.g. User Management unavailable; once per outage | `{code, message}` |
| `ping` | Every 15 s | `{}` |

- The stream re-reads the visible users every `MAP_STREAM_INTERVAL_MS` (5 s) and sends them only when they changed. It never ends on its own; an outage sends `error` and the stream continues.
- A refused request gets its normal JSON error (`401`), not a stream.
- The stream holds no task slot in Map and has no deadline. The gateway streams it without buffering and counts it as one of its own concurrent tasks.
- Each re-read costs up to two internal calls to User Management through the gateway.

SSE goes **through** the gateway: the route is under `/api/v1/map`, which the gateway already sends to Map. Only Guild's WebSocket bypasses the gateway.

## Gateway routes these services need

Routed **to** these services (already in `gateway-service`):

| Prefix | Service |
| --- | --- |
| `/api/v1/users`, `/api/v1/auth`, `/api/v1/friendships`, `/api/v1/enemies`, `/api/v1/relationships`, `/api/v1/wallets`, `/api/v1/wallet-entries`, `/internal/v1/users` (except `…/package-registrations`), `/internal/v1/wallets` | `user-management-service:8085` |
| `/api/v1/map` | `map-service:8086` |

Called **by** these services through the gateway, so they must be routed to their owners:

| Caller | Route | Owner |
| --- | --- | --- |
| Map | `GET /internal/v1/users/{user_id}/relationships`, `POST /internal/v1/users/batch` | User Management |
| User Management | `GET /internal/v1/users/{user_id}/package-registrations`, `GET /internal/v1/raid-definitions/{id}/versions/{version}` | Package Registry |

## Postman

[`postman/user-management-service.postman_collection.json`](../postman/user-management-service.postman_collection.json) and [`postman/map-service.postman_collection.json`](../postman/map-service.postman_collection.json) now target the gateway (`gateway_base_url`, default `http://localhost:8080`).

- The first request of a run logs the seed users in through `POST /api/v1/auth/login` (password `password123`). Requests then send `Authorization: Bearer <access token>` instead of `X-Mock-User-Id`.
- User Management's internal requests send the `map` or `battle` service token (`map_service_token` / `battle_service_token`, the values of `MAP_SERVICE_TOKEN` / `BATTLE_SERVICE_TOKEN` in `.env`). The smoke workflow passes them with `--env-var`.
- New checks: the access token's `roles` (`[]` for Alice, `["admin"]` for the admin), the gateway's `401` for a missing token, and the gateway refusing a user token on an internal route. The Lab 1 local-wallet request with `X-Service-Name: package:<id>` is replaced by that last check (see open items).
- The SSE route never ends, so it is not in the collection. Check it with `curl -N http://localhost:8080/api/v1/map/stream -H "Authorization: Bearer <token>"`. Each private repo's tests read the stream in-process.

## CI and images

Each repository has `.github/workflows/ci.yml`. Pull requests into `dev` and `main` run the type check, the Jest tests (27 in User Management, 25 in Map) and the build. A push to `main` also builds the image and pushes `madalina060504/tamagotchi-<service>:<package.json version>` and `:latest` to Docker Hub. The version is `0.3.0` for Lab 2. The workflow reads the `DOCKERHUB_USERNAME` and `DOCKERHUB_TOKEN` repository secrets.

| Image | Pull request |
| --- | --- |
| `madalina060504/tamagotchi-user-management-service:0.3.0` | MadalinaDev/user-management-service#1 |
| `madalina060504/tamagotchi-map-service:0.3.0` | MadalinaDev/map-service#1 |

## Open items

| Item | Depends on |
| --- | --- |
| The `0.3.0` images are **not published yet**, so `docker compose pull` and the smoke workflow fail on this branch until they are. | Docker Hub secrets in both repositories, then the release pull request `dev` → `main` (Mădălina) |
| The submodule pointers still pin the Lab 1 commits. | The releases above |
| Trusted package backends (`package:<package_id>`) cannot call `POST /internal/v1/wallets/local-operations` through the gateway: it only maps the eight team services to service tokens. User Management still binds such callers to their package. | Package-backend identities in the gateway |
| The gateway image in the compose file is Sava's temporary build. | `madalina060504/tamagotchi-gateway-service:0.3.0` on Docker Hub (Mădălina) |
