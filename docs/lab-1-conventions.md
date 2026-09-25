# Lab 1 Conventions — Tamagotchi Go, Team 12

Binding for all four team members. If something is unclear, this file wins over personal preference. Changes go through a PR to dev with one approval.

Stack (as fixed in the Lab 0 README): Go for Battle, Tamagotchi, Guild and Notification; TypeScript / NestJS with Prisma for User Management, Map, Monster Raid and Package Registry. Storage is PostgreSQL everywhere, with PostGIS for Map.

## 1. Ownership

| Owner | Services (stack) | Shared task in the CPR |
| --- | --- | --- |
| Sava | Battle, Tamagotchi (Go) | This file, postman/ structure and shared environment, final "everything starts with one command" check |
| Vica | Guild, Notification (Go) | docker-compose.yml, .env.example, db/init/ (Postgres init) |
| Madalina | User Management, Map (NestJS + Prisma) | db/seed/ and db/seed.md (seed mechanism, reference copies of all seeds) |
| Sabina | Monster Raid, Package Registry (NestJS + Prisma) | Final CPR README (Docker Hub links, run requirements) and contract updates |

## 2. Ports, names, images

| Service | Port | Stack | Docker Hub image name | DB name / user |
| --- | --- | --- | --- | --- |
| Battle | 8081 | Go | tamagotchi-battle-service | battle_db / battle_user |
| Tamagotchi | 8082 | Go | tamagotchi-tamagotchi-service | tamagotchi_db / tamagotchi_user |
| Guild | 8083 | Go | tamagotchi-guild-service | guild_db / guild_user |
| Notification | 8084 | Go | tamagotchi-notification-service | notification_db / notification_user |
| User Management | 8085 | NestJS | tamagotchi-user-management-service | user_management_db / user_management_user |
| Map | 8086 | NestJS | tamagotchi-map-service | map_db / map_user |
| Monster Raid | 8087 | NestJS | tamagotchi-monster-raid-service | raid_db / raid_user |
| Package Registry | 8088 | NestJS | tamagotchi-package-registry-service | registry_db / registry_user |

Image reference: `<owner_dockerhub_username>/<image name>:0.1.0`. Each owner publishes to their own public Docker Hub repositories. Docker Hub usernames: Sava **ekkusuu**, Vica **nikvnln**, Madalina **madalina060504**, Sabina ____.

Lab 1 tag for every image: **0.1.0**. Fixes: 0.1.1, etc. Never rely on latest.

Git tag in the CPR when Lab 1 is done: **v0.2.0**.

Docker Compose service names equal the repository folder names: battle-service, tamagotchi-service, guild-service, notification-service, user-management-service, map-service, monster-raid-service, package-registry-service. Services reach each other at `http://<compose-service-name>:<port>`.

## 3. Environment variables (identical in every service)

| Variable | Meaning | Default for local run |
| --- | --- | --- |
| PORT | HTTP port (see table above) | service port |
| STORAGE | memory or postgres | memory |
| DB_HOST | Postgres host | localhost (postgres in compose) |
| DB_PORT | Postgres port | 5432 |
| DB_NAME | Database name | see table |
| DB_USER | Database user | see table |
| DB_PASSWORD | Database password | from .env, never committed |
| RUN_MIGRATIONS | Apply schema migrations on startup (Postgres mode only) | true |
| USE_MOCKS | true = mock clients for other services | true |
| AUTH_MODE | mock = trust X-Mock-User-Id | mock |
| SEED_ON_START | Seed data if tables are empty | true |

URLs of other services for later integration (unused while USE_MOCKS=true): BATTLE_URL, TAMAGOTCHI_URL, GUILD_URL, NOTIFICATION_URL, USER_MANAGEMENT_URL, MAP_URL, RAID_URL, REGISTRY_URL.

Stack-specific notes:

- NestJS (Prisma) reads DATABASE_URL. Do not add it to .env by hand: the container entrypoint and run.sh build it from the DB_* variables (`postgresql://$DB_USER:$DB_PASSWORD@$DB_HOST:$DB_PORT/$DB_NAME`). Use passwords without special characters (letters and digits only), otherwise they must be URL-encoded.
- Go builds its DSN from the same DB_* variables (add DB_SSLMODE, default disable).
- Every service ships a .env.example with placeholders. .env is git-ignored. Every service repo has its own .gitignore (.env, node_modules/, dist/, bin/, coverage*, IDE files).

## 4. Database

One Postgres container named postgres, image postgis/postgis:16-3.4 (PostGIS is needed only by Map, the same image serves all).

Volume pgdata mounted at /var/lib/postgresql/data.

db/init/01-create-databases.sh creates the 8 databases and 8 users, reading passwords from env (BATTLE_DB_PASSWORD, TAMAGOTCHI_DB_PASSWORD, GUILD_DB_PASSWORD, NOTIFICATION_DB_PASSWORD, USER_MANAGEMENT_DB_PASSWORD, MAP_DB_PASSWORD, RAID_DB_PASSWORD, REGISTRY_DB_PASSWORD), grants each user ownership of its database, and runs CREATE EXTENSION postgis in map_db. Init scripts only run on an empty volume; to redo: docker compose down -v.

Each service only connects to its own database. No cross-database access.

STORAGE=memory must keep working (grade 2, and fast unit tests). In NestJS the Prisma client is created only when STORAGE=postgres.

Schema migrations (Lab 1):

| Stack | Tool | How it runs |
| --- | --- | --- |
| Go | golang-migrate with SQL files in migrations/ embedded via go:embed | On startup when RUN_MIGRATIONS=true |
| NestJS | Prisma Migrate (prisma/schema.prisma, prisma/migrations/), committed to Git | Container entrypoint runs npx prisma migrate deploy before starting the app; developers create migrations with npx prisma migrate dev |

Do not use ORM auto-sync (db push, synchronize) in anything that is committed as the default path.

Map and PostGIS with Prisma: Prisma has no native PostGIS type. Declare the column as Unsupported("geography(Point,4326)"), write and query it with $executeRaw / $queryRaw (ST_SetSRID(ST_MakePoint(lng, lat), 4326)::geography, ST_DWithin), and add the GiST index and CREATE EXTENSION IF NOT EXISTS postgis in a hand-edited migration (prisma migrate dev --create-only). Do not use migrate dev against the compose database; use migrate deploy there.

## 5. Seed data ("populate if empty")

Each service seeds itself on startup when SEED_ON_START=true and its main tables are empty (after migrations). Never overwrite or duplicate existing data.

A reference copy of each seed lives in the CPR as db/seed/\<service>.sql (or .json if the seed is done through code). db/seed.md explains the mechanism.

Seeds use these fixed UUIDs, so mocks in different services agree with each other:

| Entity | Id |
| --- | --- |
| User Alice (package A + B) | 00000000-0000-4000-8000-000000000001 |
| User Bob (package A) | 00000000-0000-4000-8000-000000000002 |
| User Carol (package B) | 00000000-0000-4000-8000-000000000003 |
| Admin user | 00000000-0000-4000-8000-000000000009 |
| Package A "PetHub" (hunger, happiness) | 00000000-0000-4000-8000-0000000000a1 |
| Package B "MoodPets" (energy, mood) | 00000000-0000-4000-8000-0000000000a2 |
| Guild "Founders" (leader Alice, members Bob, Carol) | 00000000-0000-4000-8000-0000000000c1 |
| Raid definition "Big Slime" v1 | 00000000-0000-4000-8000-0000000000d1 |

Alice and Bob are accepted friends; Carol has marked Bob as an enemy.

## 6. Cross-cutting API rules (Lab 1 subset of the contract)

Paths, field names (snake_case), types, status codes and error body follow the Lab 0 contract exactly. Do not invent new field names. Go: json:"user_id" struct tags. NestJS: DTO properties are written in snake_case directly (Prisma models may keep camelCase and use @map, but the API never does).

Every service exposes GET /health → 200 {"status":"ok"} (no auth, not under /api/v1).

Auth (temporary): with AUTH_MODE=mock, the caller is the UUID in header X-Mock-User-Id; global admin if X-Mock-Roles: admin. Missing header → 401. Wrong role → 403. Real JWT/JWKS validation comes in the integration lab. This is a documented mock, not the final design.

Internal endpoints (/internal/v1/...) are implemented, but in Lab 1 require only the header X-Service-Name: \<caller> (mock).

Idempotency-Key is accepted but not enforced in Lab 1 (documented gap, to be implemented later). Optimistic expected_version checks are implemented where the contract lists them.

Pagination limit / cursor and Page\<T> exactly as in the contract.

Errors: {code, message, request_id, details[]} with statuses from the contract.

Amounts, XP and HP are integers; Long values stay within 2^53-1 (int64 in Go, number in TypeScript).

Outgoing HTTP calls (real clients) use a 2 second timeout.

No RabbitMQ in Lab 1. Where the contract emits an event, write it through an EventPublisher interface with a no-op/logging implementation.

## 7. Mocking other services (grade 9)

For every external dependency define an interface and two implementations:

- Mock\<Name>Client — used when USE_MOCKS=true, returns data consistent with the seed IDs above.
- Http\<Name>Client — real HTTP client to \<NAME>_URL, may be a stub in Lab 1, but the DTOs must match the contract.

Suggested names: RegistryClient, UserManagementClient, TamagotchiClient, GuildClient, FirebaseSender. Types (DTOs) come from the Lab 0 contract.

| Stack | How to switch |
| --- | --- |
| Go | Interface per dependency; main.go picks the implementation from USE_MOCKS and passes it to the service constructor |
| NestJS | Abstract class or injection token per dependency; a provider with useFactory picks the implementation from USE_MOCKS |

| Service | Mocks |
| --- | --- |
| Battle | Registry, User Management, Tamagotchi (reservation/settlement) |
| Tamagotchi | Registry |
| Guild | User Management, Registry |
| Notification | Guild, Firebase |
| User Management | Registry |
| Map | User Management |
| Monster Raid | Guild, Tamagotchi, Registry, User Management |
| Package Registry | User Management, Guild |

## 8. Repository layout

Each private service repo (common part):

```text
README.md          how to run (script, Docker, env, tests), API summary, mocks
run.sh             builds and runs locally (STORAGE=memory by default); `./run.sh docker` builds and runs the image
Dockerfile
.env.example
.gitignore
```

Go service:

```text
cmd/<service>/main.go     wiring: config, storage, mocks, HTTP server
internal/                 handlers, service (business logic), repository, clients, seed
migrations/               NNN_name.up.sql / NNN_name.down.sql
go.mod  go.sum
```

NestJS service:

```text
src/                      modules, controllers, services, repositories, clients, dto
prisma/schema.prisma      prisma/migrations/
test/                     e2e / integration tests
package.json  package-lock.json
```

Common public repo (CPR):

```text
docker-compose.yml   images from Docker Hub only, no `build:`
.env.example
db/init/  db/seed/  db/seed.md
postman/<service>.postman_collection.json   (8 files)
postman/local.postman_environment.json      (base URLs, user ids)
docs/lab-1-conventions.md
README.md            Docker Hub links, requirements, how to run
```

## 9. Toolbox per stack (recommended, keep consistent within a stack)

| Need | Go | NestJS |
| --- | --- | --- |
| HTTP / routing | chi (or net/http) | NestJS controllers |
| Validation | go-playground/validator | class-validator + class-transformer (global ValidationPipe, 422 for invalid values) |
| Database | database/sql with the pgx stdlib driver; plain SQL or sqlc (no GORM, matches the README) | Prisma; $queryRaw where needed |
| Migrations | golang-migrate | Prisma Migrate |
| Config | environment variables read once into a config struct | @nestjs/config |
| UUIDs | github.com/google/uuid | crypto.randomUUID() |
| Tests | testing + testify | Jest + supertest |
| Extras | gorilla/websocket or nhooyr.io/websocket (Guild), firebase.google.com/go/v4 (Notification) | @nestjs/jwt or jose and argon2/bcrypt (User Management), @nestjs/schedule (Registry) |

Docker images:

- Go: multi-stage build (golang:1.22 → gcr.io/distroless/static or alpine), CGO_ENABLED=0, non-root user.
- NestJS: multi-stage build on node:20-slim (not Alpine, Prisma needs OpenSSL; install openssl if a slim image lacks it), npx prisma generate at build, npm ci --omit=dev in the final stage, non-root user, entrypoint runs prisma migrate deploy then the app.

## 10. Postman

One collection per service, file postman/\<service>.postman_collection.json, with every implemented endpoint plus one example request body each.

Use variables {{base_url}} (per service, from the shared environment), {{user_id}} (default Alice's id) and {{admin_id}}. Requests send X-Mock-User-Id: {{user_id}}.

No real secrets or tokens in collections.

## 11. Testing

Target ≥80% line coverage on business logic (controllers, config, main, DTOs and generated code may be excluded, but say so in the README). Tests run against STORAGE=memory and mock clients, no external services required. README states the exact command and where the coverage report is.

| Stack | Command | Coverage |
| --- | --- | --- |
| Go | go test -race ./... -coverprofile=coverage.out -covermode=atomic | go tool cover -func=coverage.out (total line at the bottom); keep business logic in internal/service so the number is meaningful |
| NestJS | npm test -- --coverage | Jest coverageThreshold set to 80 in package.json/jest.config, with main.ts, `\*.module.ts`, `\*.dto.ts` and prisma/ in coveragePathIgnorePatterns |

Mandatory focus areas: Battle damage formula and turn rules; Tamagotchi reservation and settlement; wallet settlement idempotency and no negative balance (User Management); concurrency of atomic HP updates (Raid); Map staleness and pair de-duplication.

## 12. Git workflow (from the Lab 0 README, reminder)

Branches from updated dev: feat/lab-1/\<short-kebab-description>; PRs into dev, one teammate approval, squash merge, delete the branch.

Conventional Commits: feat(battle): add damage calculation. PR title \<type>(\<scope>): \<imperative summary>, description with Summary, Verification, Contract impact, Checklist.

Shared CPR files (compose, seed, README) need a review from an owner of an affected service. Any contract change needs review by an affected owner.

Release PR dev → main with a merge commit; tag v0.2.0 after the Lab 1 presentation-ready state.

Never commit .env, Firebase keys, node_modules, build output. Each private repo has its own .gitignore.

## 13. What each owner implements in their own services

The scope below is the Lab 1 minimum taken from the Lab 0 contract. Everything not listed (RabbitMQ, real JWKS validation of other services' tokens, enforced idempotency keys, full Guild WebSocket, saga workers) stays for later labs. Each item must be covered by the README, a Postman request and unit tests.

Every service, no exceptions:

- GET /health, mock auth middleware (section 6), error format and validation (400 / 422) as in the contract.
- Both storage modes (memory and postgres) behind one repository interface.
- Dockerfile as described in section 9, plus a container healthcheck; image runs with only env variables.
- Migrations and seed on start (sections 4 and 5).
- Interfaces and mocks for every dependency listed in section 7; no direct calls to other services' code or databases.
- Events written through an EventPublisher interface (log/no-op implementation).
- README: how to run (script, Docker, compose), env variables, endpoint list, what is mocked, how to run tests, coverage number.

Sava (Go): Battle and Tamagotchi are implemented as the Lab 1 CRUD subset first (create/list/get/update/delete plus battle-rules, tamagotchi-types and Tamagotchi internal pet/care endpoints); the combat engine, reservations and settlements follow next. See the service READMEs for the exact implemented surface.

Vica (Go): Guild and Notification per the Lab 0 contract (see sections 6–7 for mock auth, events and client interfaces).

Madalina (NestJS + Prisma): User Management and Map per the Lab 0 contract (JWT issuance, friendships, wallets, PostGIS proximity).

Sabina (NestJS + Prisma): Package Registry and Monster Raid per the Lab 0 contract (immutable definitions, schedules, atomic HP updates).

## 14. Known deviations from the Lab 0 contract in Lab 1

Record these in the CPR README (Sabina, Lab 1 grade 10) so that nobody mistakes them for the final design:

| Deviation | Why | Removed when |
| --- | --- | --- |
| X-Mock-User-Id / X-Mock-Roles instead of JWT validation via JWKS (AUTH_MODE=mock) | Services are developed and tested alone | Integration lab |
| X-Service-Name instead of scoped service credentials on /internal/v1 routes | Same | Integration lab |
| Idempotency-Key accepted but not enforced; business operation IDs (wallet settlement, reservations) are still enforced | Time; the ledger-level guarantees are the critical part | Later lab |
| No RabbitMQ; events go through EventPublisher (log only) | Broker is not part of Lab 1 | Later lab |
| Dev-only endpoints POST /internal/v1/dev/events (Notification) and POST /internal/v1/dev/raid-events (Monster Raid), active only when USE_MOCKS=true | Replace queue consumers so the flows can be tested | When RabbitMQ is added |
| Other services are replaced by Mock\<Name>Client implementations | Grade 9 | Integration lab |
| Guild WebSocket chat may be missing (REST history and send only) | Stretch goal | Later lab |
| User Management and Map support only STORAGE=postgres (no memory mode) | Wallet settlement relies on row locks and constraints; Map relies on PostGIS | Not planned |
| User Management and Map enforce Idempotency-Key on mutating routes instead of only accepting it | Follows the Lab 0 contract; their Postman collections send the header | Not a contract deviation |
| User Management and Map images are tagged 0.1.1 | 0.1.1 is their first release that follows these conventions | — |

Any other deviation must be added to this table in the same PR that introduces it.

## 15. Definition of done

Someone who did not write a service can start the whole system from the CPR alone, and every Postman collection returns the expected results against the seeded data.
