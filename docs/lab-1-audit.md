# Lab 1 audit — Sava (Battle + Tamagotchi)

Audited release: **0.1.0** (`tamagotchi-battle-service`, `tamagotchi-tamagotchi-service`), September 2026. This record separates the verified Sava deliverables from pending team work. An earlier 1.0.x release line used different image names and is superseded.

The professor removed three rubric items from grading: the build/run shell script, the populate-DBMS script, and the 80% coverage gate. Those artifacts were deleted from the private repos and the CPR; the team conventions file still mentions them, which is recorded as a deviation below. Tests themselves remain and run with `go test ./...`.

## Rubric mapping (updated)

| Grade | Requirement | Evidence / status |
| --- | --- | --- |
| 2 | Two HTTP CRUD services in their repositories | Both Go services implement persisted create/read/update/delete in `STORAGE=memory` and `STORAGE=postgres` modes and have private GitHub repositories |
| 3 | Dropped by professor | `scripts/run.sh`, `scripts/test.sh` and CI test workflows removed; run instructions use `go run` / Docker directly |
| 4 | Postman collection in common public repo | Two collections (28 requests) with per-response assertions plus a shared `local.postman_environment.json`; CI runs them with Newman |
| 5 | Public Docker Hub images with version tags | `ekkusuu/tamagotchi-battle-service:0.1.0` and `ekkusuu/tamagotchi-tamagotchi-service:0.1.0`, published and anonymously pulled |
| 6 | Docker DBMS, volumes, documented environment | Single PostGIS container, `pgdata` volume, `db/init` creates all eight databases/owners; Compose fails fast on missing passwords |
| 7 | Seed-if-empty; common image-based team deployment | Each service seeds itself when `SEED_ON_START=true` and tables are empty; reference copies in `db/seed/`. Common YAML uses versioned images without builds. **Six teammates' services still need image/runtime contributions** |
| 8 | Dropped by professor | Coverage gates removed; unit + sqlmock + integration tests retained and passing |
| 9 | Mock dependencies and agreed data types | Per-dependency Mock/Http clients with seed-consistent fixtures; provider-compatible DTOs; explicit `USE_MOCKS` wiring |
| 10 | Update contracts; Docker Hub/runtime docs in CPR | [Lab 1 contract addendum](lab-1-contract.md) records the implemented subset and deviations; [team conventions](lab-1-conventions.md) committed to the CPR |

## Checks performed

- `go vet` and `gofmt` checks plus full unit suites for both services (in-memory stores, mock clients, sqlmock adapter tests). Real PostgreSQL CRUD integration tests pass in dedicated `battle_test`/`tamagotchi_test` databases; the harness refuses application database names.
- Conventions deviations introduced by the rubric update: `run.sh` layout, standalone seed script, and coverage gate are intentionally not implemented; Sava's §13 engine scope (combat actions, reservations, settlements) is deferred to the next phase while the CRUD surface, mocks, and integration points land first.
- Linux container run of both applications from source-validated images; health endpoints respond successfully.
- Newman suites cover CRUD, pagination, stale versions, duplicate issuance after deletion, internal endpoints, invalid IDs, structured errors and mock authorization.
- In-service seeds run under table locks only when tables are empty; repeat starts preserve data. The starter ledger survives pet deletion.
- Application images run as non-root with a container healthcheck and contain a compiled Go binary. Missing `USE_MOCKS`/`AUTH_MODE` configuration fails startup instead of silently impersonating real authentication.

## Remaining team actions

1. A teammate must review/approve PR #28 and merge into `dev`; normal milestone release then goes `dev` → `main`. No review bypass is used.
2. Vica, Mădălina and Sabina need to supply the six remaining public image tags (`:0.1.0`), ports, environment/database settings and seeds, then extend the common Compose file. Tracked in shared infrastructure issue #12.
3. Team members should review the Lab 1 contract changes before integration; the retained Lab 0 combat, JWT and messaging designs are not implemented by these CRUD images.
