# Lab 2 conventions — Tamagotchi Go, Team 12

Shared reference for the Lab 2 integration. Builds on
[lab-1-conventions.md](lab-1-conventions.md). The Gateway is authoritative for
routing and authorization; this page records what Sava implemented and what the
rest of the team still has to adopt. Suggestion-level items from the team draft
are marked; where this page is stricter (error semantics), HTTP semantics win.

## Gateway

- Python gateway, port **8080**, image
  `madalina060504/tamagotchi-gateway-service:0.3.0` (+ `latest`). Only REST
  port published to the host (Guild keeps its port for direct WebSocket).
  Until Madalina publishes it, Compose uses the identical code as
  `ekkusuu/tamagotchi-gateway-service:0.3.0` (temporary, same digest source).
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
  service and Gateway. Saturation returns **429** with `Retry-After` (HTTP
  semantics; stricter than the draft's 503). Upstream outage → `503`,
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
- Guild WebSocket negotiation is implemented in the Gateway; the live Guild
  `0.1.1` image has no chat tickets yet (Vica).
