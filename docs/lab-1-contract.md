# Lab 1 implemented contract — Sava

This addendum describes **tamagotchi-battle-service:0.1.0** and **tamagotchi-tamagotchi-service:0.1.0**, implementing the Lab 1 CRUD subset of the [team Lab 1 conventions](lab-1-conventions.md). It is a reviewable contract change, not a claim that the complete semester design is finished. The combat engine, reservations and settlements follow next.

## Scope and mock boundary

Implemented: persisted CRUD, validation, caller ownership checks, optimistic update versions, contract pagination, six type definitions, battle-rule constants, package-specific initial stats, durable starter issuance, Tamagotchi internal pet/care endpoints, in-service seeding and startup migrations.

`USE_MOCKS=true` with `AUTH_MODE=mock` is the Lab 1 setting. The runtime uses `MockUserManagementClient`/`MockTamagotchiClient` in Battle and `MockRegistryClient` in Tamagotchi; `Http*Client` stubs with contract DTOs exist for later labs. Provider DTOs (`User`, `Pet`, `Registration`, `CareDefinition`, `StatRule`) use the agreed JSON field names. Mocks return the fixed seed identities (Alice, Bob, Carol, admin; PetHub/MoodPets definitions) and fabricate other valid UUIDs for independent testing, except the Registry mock which accepts only the two seed packages. No mock proves an external record exists. Stat interpretation for combat remains part of the future engine.

Planned, **not exposed by these images**: JWT/JWKS authentication, real inter-service calls, enforced Idempotency-Key replay, pet selections/reservations, combat actions/settlement, wallet operations and RabbitMQ delivery. These are described in the retained Lab 0 design.

Lab 1 adds PATCH/DELETE for pending battle records and DELETE for pets to demonstrate all CRUD operations. Before integrating active gameplay, deletion must coordinate with reservations. There are no reservations or active battles in this release.

## Common wire rules

- JSON, `snake_case`; `Id` is a canonical non-nil UUID string; `Time` is a UTC RFC3339 timestamp; integers are JSON numbers. All fields listed below are required.
- All `/api/` requests require `X-Mock-User-Id: <Id>`. This is a **mock identity selector**, not trusted authentication; selecting someone else's ID impersonates them. Bind this demo to localhost. `/health` is public. Internal `/internal/` routes require `X-Service-Name: <caller>` instead.
- Missing/invalid mock identity: 401. Unknown JSON fields, malformed JSON or trailing JSON: 400. Invalid field values/malformed resource IDs: 422. Wrong owner/participant: 403. Absent valid resource ID: 404. Duplicate starter or stale version: 409. Unexpected storage error: 500 with a generic message.
- Error: `{code: string, message: string, request_id: Id, details: []}`. `request_id` equals response header `X-Request-ID`, including failures. Database errors are not returned to clients.
- PATCH requires `expected_version` from the current record. The version predicate and increment are atomic; a stale update cannot overwrite another change.
- Lists accept `limit` (default 20, max 100) and opaque `cursor`, returning `{items: T[], next_cursor: string | null}` ordered by creation time then ID. Idempotency-Key is accepted but not enforced in Lab 1.
- `GET /health` → 200 `{status:"ok"}` is process liveness, not a continuous database readiness probe. With `STORAGE=postgres` the service connects, migrates (`RUN_MIGRATIONS=true`) and seeds (`SEED_ON_START=true`, empty tables only) before listening.

## Battle

```text
Loadout = {primary_pet_id: Id, secondary_pet_id: Id, boost: "none" | "guard" | "power"}
BattleCRUD = {battle_id: Id, challenger_id: Id, opponent_id: Id, loadout: Loadout,
              state: "pending", version: integer, created_at: Time, updated_at: Time}
```

| Method / path | Input | Success / permission |
| --- | --- | --- |
| POST `/api/v1/battles` | `{opponent_id: Id, loadout: Loadout}` | 201 BattleCRUD; actor becomes challenger; different opponent and two distinct pet IDs |
| GET `/api/v1/battles` | `limit?`, `cursor?` | 200 page of BattleCRUD where actor is either participant |
| GET `/api/v1/battles/{id}` | None | 200 BattleCRUD; either participant |
| PATCH `/api/v1/battles/{id}` | `{loadout: Loadout, expected_version: integer}` | 200 BattleCRUD; pending challenge's creator only; version increments |
| DELETE `/api/v1/battles/{id}` | None | 204 no body; pending challenge's creator only |
| GET `/api/v1/battle-rules` | None | 200 rules object below |

```json
{"version":1,"winner_currency":50,"loser_penalty":20,"winner_xp":100,"loser_xp":40,"primary_xp_percent":60,"turn_seconds":30,"challenge_seconds":120,"max_turns":100}
```

The rules endpoint exposes future combat constants, not a combat engine. Challenge expiry is not executed in Lab 1. `BattleCRUD` exposes the creator's loadout to both participants; it is a different response from the future combat `Battle` snapshot defined in Lab 0. Boost names are case-sensitive. Creating a battle emits a `lab1.battle.created` event through the logging publisher.

## Tamagotchi

```text
PetCRUD = {pet_id: Id, owner_id: Id, package_id: Id, name: string,
           type: "flame" | "nature" | "earth" | "electric" | "water" | "shadow",
           xp: integer, level: integer, sprite_urls: string[], definition_version: integer,
           care_stats: object, version: integer, created_at: Time, updated_at: Time}
```

| Method / path | Input | Success / permission |
| --- | --- | --- |
| POST `/api/v1/tamagotchis` | `{package_id: Id, name: string, type: CombatType}` | 201 PetCRUD; mock actor owns it; package must be a known seed package |
| GET `/api/v1/tamagotchis` | Optional `owner_id: Id` query (must equal actor), `limit?`, `cursor?` | 200 page of PetCRUD; owner only |
| GET `/api/v1/tamagotchis/{id}` | None | 200 PetCRUD; owner only (public pet views deferred) |
| PATCH `/api/v1/tamagotchis/{id}` | `{name: string, expected_version: integer}` | 200 PetCRUD; owner only, version increments |
| DELETE `/api/v1/tamagotchis/{id}` | None | 204; owner only; issuance ledger retained |
| GET `/api/v1/tamagotchi-types` | None | 200 `{types: {type: CombatType, strong_against: CombatType, weak_against: CombatType}[]}` |
| GET `/internal/v1/tamagotchis/{id}` | `X-Service-Name` | 200 full PetCRUD without owner scoping |
| PUT `/internal/v1/tamagotchis/{id}/care-stats` | `{care_stats: object, expected_version: integer}` + `X-Service-Name` | 200 PetCRUD; keys/ranges validated against the pinned Registry definition |

Names are trimmed, 1–40 Unicode characters. New pets have XP 0, level 1 and version 1. PetHub pets start with hunger=20/happiness=80; MoodPets pets with energy=90/mood=80. Type advantages follow flame → nature → earth → electric → water → shadow → flame.

Unique starter issuance is tracked separately from live pets. Creating the pet and issuance is one transaction; failure rolls both back. A second starter for the same `(user_id,package_id)` returns 409, including after DELETE. This prevents deletion/recreation farming. Data created before the ledger existed is backfilled at startup. XP, ownership and care updates are not public CRUD inputs.

## Team integration status

The common Compose file runs Sava's two versioned images together with the other six services on the shared postgres host; see [Lab 1 — Running the whole system](../README.md#lab-1--running-the-whole-system).
