# Seed data (Lab 1)

Every service seeds **itself** on startup when `SEED_ON_START=true`. After its migrations it checks its main table; only if that table is empty does it insert its seed. Existing data is never overwritten or duplicated, so restarting a container or running `docker compose up` again is safe. To reseed from scratch, wipe the volume with `docker compose down -v`; that deletes all data.

The databases themselves (one per service, each with its own owner) are created by [`db/init/01-create-databases.sh`](init/01-create-databases.sh). Postgres runs that script only on the first start with an empty `pgdata` volume.

## Shared IDs

Seeds and the `Mock<Name>Client` implementations use the fixed IDs from [section 5 of the conventions](../docs/lab-1-conventions.md#5-seed-data-populate-if-empty), so data in different services agrees: Alice `…0001`, Bob `…0002`, Carol `…0003`, admin `…0009`, package A `…00a1`, package B `…00a2`, guild "Founders" `…00c1`, raid definition "Big Slime" `…00d1`. Alice and Bob are accepted friends; Carol has marked Bob as an enemy.

## Reference copies

The files in [`seed/`](seed) are read-only copies for reviewers and for Postman. The service code is what actually runs.

| Service | Reference copy | What it seeds |
| --- | --- | --- |
| Battle | [`seed/battle-service.sql`](seed/battle-service.sql) | One battle between Alice and Bob |
| Tamagotchi | [`seed/tamagotchi-service.sql`](seed/tamagotchi-service.sql) | Alice's and Bob's starter pets |
| User Management | [`seed/user-management-service.json`](seed/user-management-service.json) | Alice, Bob, Carol and admin (password `password123`), the Alice–Bob friendship, Carol's enemy marker on Bob, and global/local wallet balances recorded as one ledger operation |
| Map | none | Nothing: Map stores only live locations, which expire after 120 s. The Postman collection shares locations itself |
| Guild | [`seed/guild-service.sql`](seed/guild-service.sql) | Guild "Founders" `…00c1` with leader Alice and members Bob and Carol |
| Notification | [`seed/notification-service.sql`](seed/notification-service.sql) | Two unread entries in Bob's inbox: Alice's friend request (friendship `…00e1`) and battle challenge (battle `…00e1`) |

Owners of the remaining services add their row and file when their seed exists.
