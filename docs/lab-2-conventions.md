# Lab 2 conventions — Tamagotchi Go, Team 12

Shared reference for the Lab 2 integration. Builds on
[lab-1-conventions.md](lab-1-conventions.md). The Gateway is authoritative for
routing and authorization; this page records what Sava implemented and what the
rest of the team still has to adopt. Suggestion-level items from the team draft
are marked; where this page is stricter (error semantics), HTTP semantics win.

## Gateway

- Python gateway, port **8080**, image
  `madalina060504/tamagotchi-gateway-service:0.3.1` (+ `latest`), published
  by the gateway repository's CI on merge to `main`. Only REST port published
  to the host (Guild keeps its port for direct WebSocket).
- All client-to-service and service-to-service REST goes through the Gateway.
  Migrated services use `expose:` instead of `ports:`.
- Authorization is validated **only** at the Gateway and never forwarded:
  `Authorization: Bearer <JWT>` (User Management RS256 via JWKS,
  `iss=user-management`, `aud=tamagotchi-go`) for public routes; service
  tokens (`INTERNAL_SERVICE_TOKENS`, `name=token`) for `/internal/*`.
- The Gateway strips `Authorization` and every spoofable identity header and
  injects `X-Auth-User-Id` / `X-Auth-Roles` (users), `X-Service-Name`
  (services, canonical wire names: `battle`, `tamagotchi`, `guild`,
  `notification`, `user-management`, `map`, `monster-raid`,
  `package-registry`) and a shared `X-Gateway-Secret`.
- Trusted package backends identify as `package:<package_uuid>`; Tamagotchi
  binds care updates to the pet's package.
- Task timeout **5 s** (`504 TASK_TIMEOUT`); max **50** concurrent tasks per
  service and Gateway. Saturation returns **503**
  `TOO_MANY_CONCURRENT_TASKS` with `Retry-After: 1`, as in the team draft
  (a temporarily overloaded server, RFC 9110 §15.6.4; 429 is for a client
  that sent too many requests). The Gateway (since gateway-service#3) and
  every service answer 503. Upstream outage → `503`,
  upstream timeout → `504`. Errors use the contract envelope with UUID
  `request_id` and `details: []`.
- Guild WebSocket: client tickets through the Gateway; `GET .../ws` returns a
  JSON direct `ws_url` to Guild — the socket is never proxied. SSE streams
  through without buffering.

## Services (same list for every owner)

- Start together via Compose (grade 2); stop publishing REST ports (`expose:`),
  except Guild's WebSocket port.
- Route all outbound REST through the Gateway (`http://gateway:8080/...` paths
  unchanged) with the service token; never forward user `Authorization`.
- Stop trusting `X-Mock-User-Id`; read Gateway identity headers + secret.
- 5 s timeout and 50-task limit as middleware, with the errors above.
- CI per repo: tests on PR; on merge to `main` push `0.3.0` + `latest`.
- Postman collections target the Gateway with a login flow.

## Sava status

- Battle and Tamagotchi `0.3.0` implement all of the above, plus the deferred
  Lab 1 engine work (combat lifecycle; selections/reservations/settlement).
- Full battle accept → settlement is implemented and unit/integration tested,
  but cannot complete live until Package Registry seeds the convention
  packages (`PetHub`, `MoodPets`) with care definitions and user
  registrations: pet creation and reservation snapshots reject unknown
  packages. Registry `0.3.0` must provide them.
- Guild WebSocket negotiation is implemented in the Gateway; Guild `0.3.0`
  serves the chat tickets and the socket (see Vica status).

## Vica status

- Guild and Notification `0.3.0` (+ `latest`, amd64 and arm64) are published
  by each repository's CI on merge to `main`; details in
  [lab-2-contract-vica.md](lab-2-contract-vica.md).
- Both read the Gateway identity headers and require `X-Gateway-Secret`
  (Guild's port 8083 is public for the socket, so forged identity headers sent
  straight to it are rejected); Notification is `expose:` only.
- All outbound calls go through the Gateway with the service token:
  Guild → User Management, Package Registry and Notification (`GuildInvited`),
  Notification → Guild.
- Guild WebSocket chat: single-use 30 s tickets through the Gateway, the
  Gateway's `ws_url`, then a direct socket with `chat.send` / `chat.ack` /
  `chat.message` / `chat.error` and a 30 s heartbeat.
- Task controls: 5 s (`504 TASK_TIMEOUT`) and 50 concurrent tasks, answered
  with **503** `TOO_MANY_CONCURRENT_TASKS` and `Retry-After: 1`, as the rule
  above requires.

## Mădălina status

- User Management and Map `0.3.0` (+ `latest`) are published by each
  repository's CI on merge to `main`; details in
  [lab-2-contract-madalina.md](lab-2-contract-madalina.md).
- Both read the Gateway identity headers and require `X-Gateway-Secret`,
  except `/health` and User Management's JWKS, which the Gateway fetches
  directly. Both are `expose:` only.
- Outbound calls go through the Gateway with the service token:
  Map → User Management, User Management → Package Registry.
- User Management access tokens carry `roles` (`["admin"]` for the global
  admin), which the Gateway forwards as `X-Auth-Roles`.
- Map pushes the caller's visible users over SSE:
  `GET /api/v1/map/stream`, through the Gateway.
- Task controls: 5 s (`504 TASK_TIMEOUT`) and 50 concurrent tasks, answered
  with **503** `TOO_MANY_CONCURRENT_TASKS` and `Retry-After: 1`.
