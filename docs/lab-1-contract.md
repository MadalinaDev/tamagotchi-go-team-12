# Lab 1 implemented contract — Sava

This addendum describes **Battle/Tamagotchi 1.0.1**, superseding the corresponding Lab 0 behavior for the independent Lab 1 demonstration. It is a reviewable contract change, not a claim that the complete semester design is finished.

## Scope and mock boundary

Implemented: persisted CRUD, validation, caller ownership checks, optimistic update versions, six type definitions, battle-rule constants, initial pet stats and durable starter issuance.

`DEPENDENCY_MODE=mock` must be selected explicitly. The runtime simulates User Management/Tamagotchi lookups in Battle and Registry registration/care definitions in Tamagotchi. Provider DTOs (`User`, `Pet`, `Registration`, `CareDefinition`, `StatRule`) are defined with their agreed JSON field names. Injectable interfaces allow failure-path tests and future HTTP adapters. Mocks accept non-nil canonical UUIDs and fabricate users, pets, ownership and package membership: they do not prove any external record exists. No Registry call is needed for pending battle CRUD; stat interpretation remains part of future combat execution.

Planned, **not exposed by these images**: JWT/JWKS authentication, inter-service HTTP, real package registration checks, pagination, Idempotency-Key replay, pet selections/reservations, combat actions/settlement, wallet operations and RabbitMQ delivery. These are described in the retained Lab 0 design. There are no working turn/reward APIs hidden behind the mocks.

Lab 1 adds PATCH/DELETE for pending battle records and DELETE for pets to demonstrate all CRUD operations. Before integrating active gameplay, deletion must coordinate with reservations. There are no reservations or active battles in this release.

## Common wire rules

- JSON, `snake_case`; `Id` is a canonical non-nil UUID string; `Time` is a UTC RFC3339 timestamp; integers are JSON numbers. All fields listed below are required.
- All `/api/` requests require `X-User-ID: <Id>`. This is a **mock identity selector**, not trusted authentication; selecting someone else's ID impersonates them. Bind this demo to localhost. `/health` is public.
- Missing/invalid mock identity: 401. Unknown JSON fields, malformed JSON or trailing JSON: 400. Invalid field values/malformed resource IDs: 422. Wrong owner/participant: 403. Absent valid resource ID: 404. Duplicate starter or stale version: 409. Unexpected storage error: 500 with a generic message.
- Error: `{code: string, message: string, request_id: Id, details: []}`. `request_id` equals response header `X-Request-ID`, including failures. Database errors are not returned to clients.
- PATCH requires `expected_version` from the current record. The SQL version predicate and increment are atomic; a stale update cannot overwrite another change.
- List: `{items: T[], next_cursor: null}` returns all records authorized for the mock actor. No pagination or state query filtering yet. Do not rely on retry replay; transport idempotency is future work.
- `GET /health` → 200 `{status:"ok"}` is process liveness, not a continuous database readiness probe. Startup connects to PostgreSQL and executes the embedded schema before listening.

## Battle

```text
Loadout = {primary_pet_id: Id, secondary_pet_id: Id, boost: "none" | "guard" | "power"}
BattleCRUD = {battle_id: Id, challenger_id: Id, opponent_id: Id, loadout: Loadout,
              state: "pending", version: integer, created_at: Time, updated_at: Time}
```

| Method / path | Input | Success / permission |
| --- | --- | --- |
| POST `/api/v1/battles` | `{opponent_id: Id, loadout: Loadout}` | 201 BattleCRUD; actor becomes challenger; different opponent and two distinct pet IDs |
| GET `/api/v1/battles` | None | 200 list of BattleCRUD where actor is either participant |
| GET `/api/v1/battles/{id}` | None | 200 BattleCRUD; either participant |
| PATCH `/api/v1/battles/{id}` | `{loadout: Loadout, expected_version: integer}` | 200 BattleCRUD; pending challenge's creator only; version increments |
| DELETE `/api/v1/battles/{id}` | None | 204 no body; pending challenge's creator only |
| GET `/api/v1/battle-rules` | None | 200 rules object below |

```json
{"version":1,"winner_currency":50,"loser_penalty":20,"winner_xp":100,"loser_xp":40,"primary_xp_percent":60,"turn_seconds":30,"challenge_seconds":120,"max_turns":100}
```

The rules endpoint exposes future combat constants, not a combat engine. Challenge expiry is not executed in Lab 1. `BattleCRUD` exposes the creator's loadout to both participants; it is a different response from the future combat `Battle` snapshot defined in Lab 0. Boost names are case-sensitive.

## Tamagotchi

```text
PetCRUD = {pet_id: Id, owner_id: Id, package_id: Id, name: string,
           type: "flame" | "nature" | "earth" | "electric" | "water" | "shadow",
           xp: integer, level: integer, sprite_urls: string[], definition_version: integer,
           care_stats: {hunger: number, happiness: number, tiredness: number},
           version: integer, created_at: Time, updated_at: Time}
```

| Method / path | Input | Success / permission |
| --- | --- | --- |
| POST `/api/v1/tamagotchis` | `{package_id: Id, name: string, type: CombatType}` | 201 PetCRUD; mock actor owns it |
| GET `/api/v1/tamagotchis` | Optional `owner_id: Id` query, must equal actor | 200 list of PetCRUD; owner only |
| GET `/api/v1/tamagotchis/{id}` | None | 200 PetCRUD; owner only (public pet views deferred) |
| PATCH `/api/v1/tamagotchis/{id}` | `{name: string, expected_version: integer}` | 200 PetCRUD; owner only, version increments |
| DELETE `/api/v1/tamagotchis/{id}` | None | 204; owner only; issuance ledger retained |
| GET `/api/v1/tamagotchi-types` | None | 200 `{types: {type: CombatType, strong_against: CombatType, weak_against: CombatType}[]}` |

Names are trimmed, 1–40 Unicode characters. New pets have XP 0, level 1 and version 1. Mock definition 1 sets hunger=20, happiness=80, tiredness=10 and an example sprite URL. Other care models will come from real Registry integration. Type advantages follow flame → nature → earth → electric → water → shadow → flame.

Unique starter issuance is tracked separately from live pets. Creating the pet and issuance is one transaction; failure rolls both back. A second starter for the same `(user_id,package_id)` returns 409, including after DELETE. This prevents deletion/recreation farming. Old 1.0.0 data is backfilled into the ledger at startup. XP, ownership and care updates are not public CRUD inputs.

## Team integration status

The common Compose file has Sava's two versioned images and two isolated PostgreSQL services. It is the common deployment starting point, **not yet an eight-service deployment**. The other owners must provide their published image tags, ports, environment/DB requirements and seed scripts. Full grade-7 team deployment remains pending until those entries are contributed and verified. Shared PR approval is also pending; a passing CI check is not a peer review.
