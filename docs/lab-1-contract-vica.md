# Lab 1 implemented contract — Vica

This addendum describes **tamagotchi-guild-service:0.1.0** and **tamagotchi-notification-service:0.1.0**. They implement the Lab 1 subset of the [team Lab 1 conventions](lab-1-conventions.md) (§13). Paths, `snake_case` field names, status codes and schemas are those of the Lab 0 [Guild API](../README.md#guild-api-and-chat) and [Notification API](../README.md#notification-api). This page records only what Lab 1 adds, leaves out or interprets.

Owners of affected services, please review the sections that concern you:

- Monster Raid and Package Registry call Guild's internal routes.
- Notification consumes events from every producer.

## Common wire rules (both services)

- **Public routes** (`/api/v1`) require `X-Mock-User-Id: <Id>`. A missing or non-UUID header returns `401 UNAUTHENTICATED`. `X-Mock-Roles` is parsed, but neither service has admin-only routes. The header is a mock identity selector, not authentication.
- **Internal routes** (`/internal/v1`) require only `X-Service-Name: <caller>`, otherwise `401`. Any non-empty caller name is accepted; there is no per-route allow list yet.
- **Idempotency:** `Idempotency-Key` is accepted and ignored. Business keys are still enforced:
  - Guild: `(author_id, client_message_id)` for chat, and one pending invite per `(guild_id, invitee_id)`.
  - Notification: `(event_id, recipient_id)` for inbox entries, and one device per Firebase token.
- **Errors:** `{code, message, request_id, details: {field, reason}[]}`.
  - Malformed JSON, trailing data and unknown body fields: `400 MALFORMED_REQUEST`.
  - Invalid field values and malformed path or query IDs: `422 VALIDATION_FAILED`, with the field named in `details`.
  - Paths outside `/api` and `/internal`: `404 ROUTE_NOT_FOUND`. A known gap in 0.1.0: an unknown path or wrong method under `/api/v1` or `/internal/v1` gets Go's plain-text `404` / `405` instead of the error body.
  - `503 DEPENDENCY_UNAVAILABLE` carries `Retry-After: 5`. The Lab 1 mocks never fail, so it does not occur yet.
  - Every response carries a new UUID in `X-Request-ID`, and error bodies repeat it as `request_id`.
- **Pagination:** lists accept `limit` (1–100, default 20) and an opaque `cursor`, and return `{items, next_cursor}` ordered by creation time, then ID, oldest first. The cursor encodes only the position (time and ID). It is not bound to the caller or the query yet.
- **Storage:** PostgreSQL only. golang-migrate applies the SQL files embedded in the binary on startup when `RUN_MIGRATIONS=true`. Per conventions §0, there is no memory mode, no seeding on startup and no health endpoint. The Postman collections create the data they need.
- **Configuration:** `PORT`, `DB_HOST`, `DB_PORT`, `DB_NAME`, `DB_USER`, `DB_PASSWORD`, `RUN_MIGRATIONS` and `AUTH_MODE` (`mock` only). Mocks are always wired in `main.go`; there is no `USE_MOCKS` switch (§0).
- **Images:** a static Go binary on `distroless/static`, running as a non-root user and published for linux/amd64 and linux/arm64.

## Guild (port 8083)

Implemented as in Lab 0:

- create, list, get, rename and disband guild;
- list members, change role, remove member or leave;
- invites: create, list mine, accept, decline, cancel;
- `GET /internal/v1/guilds/{guild_id}`, `…/members` and `…/members/{user_id}`.

Rules implemented:

- one guild per user;
- a unique case-insensitive name of 3–50 characters (trimmed, counted in Unicode characters);
- at most 100 members;
- exactly one leader;
- an invite only for an accepted friend of the inviter who shares at least one package with them.

| Lab 1 behaviour | Contract impact |
| --- | --- |
| **REST chat instead of WebSocket.** `POST /api/v1/guilds/{guild_id}/messages` takes `{client_message_id: Id, text: string}` from a member and returns `201 Message`. The text must be 1–2000 characters and not blank. Resending the same `client_message_id` with the same text in the same guild returns `200` with the original message; with a different text it is `409 CLIENT_MESSAGE_ID_REUSED`. `GET …/messages` works as in Lab 0: chronological order, and `after_message_id` or `cursor`, not both (`422`). An unknown anchor is `404 MESSAGE_NOT_FOUND`. | **New route.** It replaces `chat.send` / `chat.ack` until the socket exists. `chat-tickets` and `ws` are not exposed. The uniqueness rule is the Lab 0 one. |
| Leadership transfer (`POST …/leadership`) is **not exposed**. The leader cannot leave or be removed (`409 LEADER_CANNOT_LEAVE`); they can only disband the guild. | Skipped per conventions §13. |
| Invite errors: caller not a member `403 NOT_GUILD_MEMBER`; plain member `403 INSUFFICIENT_GUILD_ROLE`; self-invite `422`; invitee already in this guild `409 ALREADY_MEMBER`; unknown invitee (User Management `404`) `404 USER_NOT_FOUND`; not an accepted friend `409 NOT_FRIENDS`; no shared package `409 NO_SHARED_PACKAGE`; second pending invite `409 INVITE_ALREADY_PENDING`. | Error codes are additions. A user who belongs to another guild can still be invited; the check happens on acceptance, as in Lab 0. |
| Accept: invitee only (`403 NOT_INVITEE`), pending only (`409 INVITE_NOT_PENDING`). Friendship and shared package are **rechecked** through the mocks. The guild row is locked, so the 100-member limit cannot be raced (`409 GUILD_FULL`). Joining while in a guild is `409 ALREADY_IN_GUILD`. Decline has the same checks and returns `200 GuildInvite`. | As in Lab 0. |
| Cancel (`DELETE /guild-invites/{id}`): only the inviter or the current leader; another officer gets `403 NOT_INVITER_OR_LEADER`. Only pending invites can be cancelled (`409`). | Clarifies "Leader or inviter". |
| Role change: leader only. Changing their own role is `409 CANNOT_CHANGE_OWN_ROLE`, and a non-member target is `404 MEMBER_NOT_FOUND`. Remove: self, or the leader removing another member (`403 NOT_GUILD_LEADER` otherwise). | Error codes are additions. |
| Disband deletes the guild with its members, invites and messages. Afterwards `GET` returns `404 GUILD_NOT_FOUND`, and the internal routes do too. | Raid snapshots live in Monster Raid and are unaffected. |
| `GET /api/v1/guilds` lists all guilds to any user. `GET /api/v1/guild-invites` returns invites in every state addressed to the caller. | Directory and invite list as in Lab 0. |
| `POST …/invites` publishes `GuildInvited` (routing key `guild.invited`, correlation ID = invite ID) through `LogPublisher`, which only logs the `Event<T>` envelope. It is written after the insert, with no outbox. | No RabbitMQ in Lab 1. The payload is the Lab 0 one. |
| Internal `GET …/members/{user_id}`: guild missing `404 GUILD_NOT_FOUND`, not a member `404 MEMBER_NOT_FOUND`. `GET …/members` returns `{members: Member[]}` for all members (at most 100), ordered by `joined_at`. | As in Lab 0. |
| **Mocks.** `MockUserManagementClient`: users Alice `…0001`, Bob `…0002`, Carol `…0003` and admin `…0009`. Alice and Bob are accepted friends; Carol marks Bob as an enemy; any other user ID is not found. `MockRegistryClient`: Alice is registered in packages A and B, Bob in A, Carol in B. | Real clients replace them in the integration lab. With the mocks, only Alice ↔ Bob invites succeed. |

## Notification (port 8084)

Implemented as in Lab 0:

- register and delete device;
- get and put preferences;
- list notifications (`unread` filter);
- mark read.

The inbox holds one entry per `(event_id, recipient_id)`. Preferences suppress push, never the inbox entry.

| Lab 1 behaviour | Contract impact |
| --- | --- |
| **Temporary** `POST /internal/v1/dev/events` (`X-Service-Name`) takes one `Event<T>` envelope and returns `200 {event_id, recipient_ids: Id[], created_notifications: Int}`. The envelope is checked: `event_id`, `correlation_id` and `occurred_at` present, `version = 1`, the type is one of the nine notification events, and `producer` matches the Lab 0 table (`user-management`, `map`, `guild`, `battle`, `tamagotchi`, `monster-raid`). Required payload IDs must be non-nil. Unknown payload fields are allowed (forward compatible). A violation is `422 INVALID_EVENT`. Repeating an `event_id` creates nothing new (`created_notifications: 0`). | Stands in for the `notification.events.v1` consumer; removed when RabbitMQ is added. Already listed in conventions §14. |
| Recipients follow the Lab 0 table: `FriendRequested` → recipient; `UsersNearby` → the two users (exactly two distinct IDs, otherwise `422`); `GuildInvited` → invitee; `BattleRequested` → opponent; `BattleCompleted` → winner and loser; `PetActivityStarted` → distinct owners; `PetTransferred` → previous and new owner; `RaidFinished` → distinct participants; `RaidStarted` → guild members read through `GuildClient` when the event is processed. A guild that no longer exists is handled with no recipients. | As in Lab 0. |
| Inbox fields the contract left open: `type` is the event type; `resource_type` / `resource_id` are `friendship` / friendship ID, `encounter` / encounter ID, `guild_invite` / invite ID, `battle` / battle ID, `pet_activity` / activity ID, `pet` / pet ID and `raid` / raid ID. `title` and `body` are fixed English texts with no coordinates, stats or credentials. | Pins down values for clients. |
| Devices: `firebase_token` is trimmed, 1–4096 characters; `platform` is `web`, `android` or `ios` (`422` otherwise). Registering a known token rebinds it to the caller, keeps its `device_id` and returns `201`. The token is never returned. Delete: `404 DEVICE_NOT_FOUND`, or `403 NOT_DEVICE_OWNER` for someone else's device. | As in Lab 0, with the error codes fixed. |
| Preferences: without a stored row, `GET` returns `{push_enabled: true, disabled_types: []}`. `PUT` requires both fields (`422` if one is missing). Every entry of `disabled_types` must be one of the nine event types (`422` otherwise), and the list is stored sorted and de-duplicated. | Default values are an addition. |
| Notifications: `GET` returns only the caller's entries, oldest first; `unread` must be `true` or `false`. `PUT …/read` is for the recipient only (`403 NOT_RECIPIENT`, `404 NOTIFICATION_NOT_FOUND`) and keeps the first `read_at` on repeated calls. | As in Lab 0. |
| Push runs synchronously during event handling, only for new inbox entries, only when `push_enabled` is true and the type is not disabled. It goes to every device of the recipient through `FirebaseSender` with the Lab 0 FCM data payload `{notification_id, type, resource_type, resource_id}`. There are no delivery jobs, retries or invalid-token cleanup. | Skipped per conventions §13 (retries, delivery jobs). |
| **Mocks.** `MockGuildClient`: guild Founders `…00c1` has leader Alice, and members Bob and Carol; other guilds are not found. `MockFirebaseSender` logs the push with the token redacted to its last four characters. | Real clients replace them in the integration lab. |

## Team integration status

Both images are public on Docker Hub and run in the common [docker-compose.yml](../docker-compose.yml) as `guild-service` and `notification-service` on the shared `postgres`. How to run them is in the [README](../README.md#lab-1--running-vicas-services). The Postman collections `postman/guild-service.postman_collection.json` (26 requests) and `postman/notification-service.postman_collection.json` (10 requests) cover every endpoint above. They pass with Newman on repeated runs against the team stack. The private repositories are [vikanicologlo/guild-service](https://github.com/vikanicologlo/guild-service) and [vikanicologlo/notification-service](https://github.com/vikanicologlo/notification-service) (tag `v0.1.0`).
