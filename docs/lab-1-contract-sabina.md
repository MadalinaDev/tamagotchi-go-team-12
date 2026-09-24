# Lab 1 implemented contract — Sabina

This addendum describes **tamagotchi-monster-raid-service:0.1.1** and **tamagotchi-package-registry-service:0.1.0**, which implement the Lab 1 subset of the [team Lab 1 conventions](lab-1-conventions.md) (§13). Paths, `snake_case` field names, status codes and schemas are those of the Lab 0 [Monster Raid API](../README.md#monster-raid-api) and [Package Registry API](../README.md#package-registry-api). This page records only what Lab 1 adds, leaves out or interprets. Owners of affected services: please review the sections that concern you.

## Common wire rules (both services)

- **Public routes** (`/api/v1`) require `X-Mock-User-Id: <Id>`; `X-Mock-Roles: admin` marks a global admin. A missing or non-UUID header returns `401`; a missing role returns `403`. The header is a mock identity selector, not authentication.
- **Internal routes** (`/internal/v1`) require only `X-Service-Name: <caller>`, otherwise `401`.
- **Idempotency:** `Idempotency-Key` is accepted and ignored. Business operation ids are still enforced: raid settlement `operation_id`, one raid per `schedule_id`, and one participation per (raid, user).
- **Errors:** `{code, message, request_id, details: {field, reason}[]}`. Invalid body field values return `422`. Package Registry also returns `422` for malformed path ids and echoes `request_id` in the `X-Request-Id` response header. Monster Raid 0.1.1 returns `400 BAD_REQUEST` for a malformed `raid_id` and puts `request_id` only in error bodies; aligning it to `422` and the header is a follow-up.
- **Pagination:** lists accept `limit` (1–100, default 20) and an opaque `cursor`, and return `{items, next_cursor}` ordered by `created_at`, then id.
- **Storage:** PostgreSQL with Prisma migrations, applied by the container entrypoint when `RUN_MIGRATIONS=true`. There is no seeding on startup and no health endpoint (§0).
- **Events:** go through an `EventPublisher` interface whose Lab 1 implementation logs the `Event<T>` envelope. There is no RabbitMQ or outbox.

## Package Registry (port 8088)

Implemented as in Lab 0:

- packages: create, list, get, patch;
- care definitions: create a new immutable version, get;
- registrations and `GET /package-registrations/me`;
- raid definitions: create, new version, list latest, get version;
- raid schedules: create, list, activate, cancel;
- all four `/internal/v1` routes.

Validation follows the Lab 0 rules:

- care stats: 1–32 unique keys, `min <= initial <= max`, threshold in range, `combat_bonus` 0..0.10, HTTPS sprites;
- monsters: HP > 0, disjoint `weak_to` / `resistant_to`, duration 60–86400 s, participant limit 1–100.

| Lab 1 behaviour | Contract impact |
| --- | --- |
| Staff/moderator endpoints (`GET …/staff`, `PUT`/`DELETE …/moderators/{user_id}`) are **not exposed**, and there is no `PackageMember` table. The package's `developer_id` is its only staff. | "Package staff/admin" rules become "developer or admin". `PackageMember` is unused until the endpoints return. |
| `developer_id` on package create and `guild_id` on schedule create are checked through mocks (`MockUserManagementClient`, `MockGuildClient`). Unknown ids return `422`. | Valid ids are only the shared test users (Alice, Bob, Carol, admin) and guild Founders `…00c1`. |
| No persisted scheduler. Schedules become `activated` only through `POST …/activate`. | `starts_at` does not trigger activation in Lab 1. |
| Activate and cancel are one conditional `UPDATE` (the `revision` increments). The event is published after the state change commits, not through an outbox. | Concurrent activations still apply once (`202` then `409`). If the process crashes after the commit but before publishing, the event is lost; the outbox returns with RabbitMQ. |
| Events `RaidActivationRequested` / `RaidCancellationRequested` keep the Lab 0 payloads and routing keys, with a deterministic `event_id` per (schedule, revision). | Nothing consumes them in Lab 1. Monster Raid takes activation through its dev endpoint (below). |

## Monster Raid (port 8087)

Implemented as in Lab 0:

- list guild raids, get raid, join, list participants, attack;
- `GET /internal/v1/raids/by-schedule/{schedule_id}`.

Game rules as in Lab 0:

- damage formula, with `armored` doubling defense and care bonus capped at 0.20;
- HP updated atomically under the per-raid lock and never below 0;
- persisted join attempt with an idempotent reservation that is released on failure;
- participant limit and no duplicate participation;
- the killing transaction chooses settlement;
- rewards only for participants with at least one damaging attack;
- `RaidStarted` / `RaidFinished` emitted once.

| Lab 1 behaviour | Contract impact |
| --- | --- |
| **Temporary** `POST /internal/v1/dev/raid-events` (`X-Service-Name`) accepts `Event<RaidActivationRequested>` and returns `201 Raid`. It creates at most one raid per `schedule_id`; repeating the event returns the same raid. A missing guild or a late activation creates a `failed` raid. | Stands in for the `raid.scheduling.v1` consumer; removed when RabbitMQ is added. |
| **Lazy expiry (0.1.1).** There is no timer worker. The first request that loads a raid after `ends_at` (get, list, participants, by-schedule, join, attack) marks it `failed` under the per-raid lock, releases every reservation without rewards and emits `RaidFinished` once. Joins and attacks after the deadline return `409 RAID_ENDED`. | Same terminal outcome as the Lab 0 timer, but applied on the next request instead of at `ends_at`. If nobody touches the raid, its stored state stays `active`. |
| `RaidCancellationRequested` is **not consumed**, and there are no schedule tombstones. | Cancelling a schedule in Package Registry does not stop a raid that already exists. |
| No `429` attack rate limit (Lab 0: one accepted attack per second per user). | Clients may attack faster in Lab 1. |
| Settlement runs inline in the request that kills the monster. A failed operation stays pending and resumes on the next request that finishes the raid. There are no background retries. | Terminal state and `operation_id` idempotency are unchanged. |
| Global admins (`X-Mock-Roles: admin`) may read any raid and its participants. | Addition to the Lab 0 caller column (read-only). |
| Guild, Tamagotchi, Package Registry and User Management are mocks with the contract types. Guild Founders `…00c1` contains Alice, Bob and Carol. Raid definition Big Slime `…00d1` v1 has 300 HP, defense 2, weakness flame and resistance water. Alice's mocked pet is flame, level 3, and deals 24 damage per attack. | Real clients replace the mocks in the integration lab. |

## Team integration status

Both images are public on Docker Hub. Both are missing from the common Compose file: the `docker-compose.yml` on `dev` currently holds `.env` content (see the PR that adds this page). They can be run standalone as described in the [README](../README.md#lab-1--running-sabinas-services). The Postman collections `postman/monster-raid-service.postman_collection.json` and `postman/package-registry-service.postman_collection.json` cover every endpoint above and pass with Newman on repeated runs.
