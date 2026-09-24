# Lab 1 audit — Sava (Battle + Tamagotchi)

Audited release: **1.0.1**, September 2026. The previous completion report overstated contract compatibility and full-team deployment. This record separates the verified Sava deliverables from pending team work.

## Rubric mapping

| Grade | Requirement | Evidence / status |
| --- | --- | --- |
| 2 | Two HTTP CRUD services in their repositories | Both Go services implement persisted create/read/update/delete and have private GitHub repositories |
| 3 | Build/run shell script; private run instructions | Executable LF `scripts/run.sh` and `scripts/test.sh`; script builds and runs the binary, loads `.env`, and was exercised under Linux/Go 1.24 |
| 4 | Postman collection in common public repo | Two collections with 28 requests and 79 passing assertions, including negative paths |
| 5 | Public Docker Hub images with version tags | Both `1.0.1` tags published and pulled using an empty Docker credential configuration; anonymous repository metadata also reports `is_private: false` |
| 6 | Docker DBMS, volumes, documented environment | Isolated PostgreSQL containers and named volumes; snapshots retained across full Compose down/up; no password fallbacks in YAML |
| 7 | Seed-if-empty; common image-based team deployment | Sava's transactional SQL seed passes repeat-run verification. Common YAML uses versioned images without builds. **Six teammates' services still need image/runtime contributions** |
| 8 | At least 80% unit coverage | Battle **93.6%**, Tamagotchi **93.9%** across all executable `internal/...` code, including SQL adapter unit tests. CI/script enforces 80% |
| 9 | Mock dependencies and agreed data types | Injectable mocks and provider-compatible User/Pet/Registration/CareDefinition/StatRule DTOs; explicit mock mode and documented fabricated identity/membership |
| 10 | Update contracts; Docker Hub/runtime docs in CPR | [Lab 1 contract addendum](lab-1-contract.md) records actual implemented behavior and deviations; shared/private running instructions updated |

Grades are cumulative. This is **not a guarantee of a grade 10** while the team deployment and shared PR approval remain outstanding.

## Checks performed

Published image index digests:

- Battle: `sha256:69fe622f0c82a2d4f67364ac0a6b182c72a0af4e9ef69e1a244016bcae8d3418`
- Tamagotchi: `sha256:d1be6186e05c5cd6c03eaa51f7f130e612136f7d7739bd66a5a16bac32380514`

Private fixes merged after successful GitHub Actions unit, race and build jobs: [Battle PR #1](https://github.com/Ekkusuu/battle-service/pull/1), [Tamagotchi PR #1](https://github.com/Ekkusuu/tamagotchi-service/pull/1). Private links require authorized access.

- Unit tests, vet and formatting checks for both services. The unit coverage denominator includes domain, HTTP handlers, service logic, runtime mocks and SQL adapters; only entry-point wiring and the embedded SQL variable are excluded. SQL adapter unit tests run without PostgreSQL using sqlmock. This is distinct from integration coverage.
- Real PostgreSQL CRUD integration tests pass for both services in dedicated `battle_test`/`tamagotchi_test` databases. Tests refuse application database names; they no longer instruct users to truncate their demo data.
- Linux `scripts/run.sh` builds/tests and starts both applications; their health endpoints respond successfully.
- Newman: Battle 13 requests / 36 assertions; Tamagotchi 15 requests / 43 assertions; no failures.
- Seeds run under table locks and `ON_ERROR_STOP`; empty databases get four fixed pets and one challenge. Repeated seeds preserve data. Seed and Postman use separate identities so tests can run after seeding.
- Whole-record database hashes and starter-ledger counts match across repeated seed and full container teardown/recreation with named volumes retained.
- Application images run as non-root and contain a compiled Go binary; source is not needed by Compose. Missing `DEPENDENCY_MODE=mock` fails startup instead of silently impersonating real authentication.

## Corrections made

- Missing executable bits/line-ending controls and missing build output directory.
- Coverage reporting used integration tests and excluded storage from some commands; now a repeatable unit gate covers all internal code and runs in CI.
- Malformed resource IDs returned 500; JSON allowed trailing objects; error envelopes lost request IDs and could expose raw database messages.
- Uppercase boosts passed validation but disagreed with the database contract; validation now follows the case-sensitive enum.
- Duplicate starters returned database errors; deleting pets enabled starter farming. A transactionally maintained issuance ledger now returns 409 even after deletion.
- Startup schema differed from the distributed DDL; the startup migration now embeds that DDL directly.
- Seed checked only one user's list and ignored HTTP error status; replaced by global database emptiness checks with transactional SQL and no Python dependency.
- Postman checked only POST; it now checks CRUD, wrong actor, missing identity, stale version, invalid IDs, trailing JSON and duplicate issuance.
- Documentation claimed full Lab 0 compatibility, real package checks and published-image testing before those were verified. The addendum states the implemented CRUD subset, added routes and mocked/deferred features explicitly.

## Remaining team actions

1. A teammate must review/approve PR #28 and merge into `dev`; normal milestone release then goes `dev` → `main`. No review bypass is used.
2. Vica, Mădălina and Sabina need to supply the six remaining public image tags, ports, required environment variables, database volumes and seed behavior, then extend the common Compose file. Tracked in shared infrastructure issue #12.
3. Team members should review the Lab 1 contract changes before integration; the retained Lab 0 combat, JWT and messaging designs are not implemented by these CRUD images.
