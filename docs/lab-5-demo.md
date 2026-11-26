# Lab 5 — demo guide

A walk through Lab 5 grade by grade, with what to run and what to point at. The background is in [lab-5-conventions.md](lab-5-conventions.md); the endpoints and data formats are in [lab-5-contract-madalina.md](lab-5-contract-madalina.md).

## Before the demo

```sh
docker compose up -d --wait                       # about 2 minutes; 34 containers
curl -s localhost:8008/cluster | python -m json.tool   # who leads the database cluster now
```

Open these:

| What | Where |
| --- | --- |
| Grafana | <http://localhost:3000>, dashboard *Tamagotchi Go: database cluster, cache, sagas and warehouse (Lab 5)* |
| The router's status page | <http://localhost:7000> |
| The system map | `docs/diagrams/system-map.html` in a browser |
| Postman | import [postman/lab-5.postman_collection.json](../postman/lab-5.postman_collection.json) and set `etl_admin_token`, `broker_admin_token` and `map_service_token` from `.env` |

To run the whole collection at once:

```sh
npx newman run postman/lab-5.postman_collection.json \
  --env-var etl_admin_token=$ETL_ADMIN_TOKEN --env-var broker_admin_token=$BROKER_ADMIN_TOKEN \
  --env-var map_service_token=$MAP_SERVICE_TOKEN
```

## Grades 2 and 3 — the diagrams

**Show:** the README's [architecture](../README.md#architecture), and in the system map the views **Cache** and **Replication and warehouse**. Click a box to see its details.

**Point at the components the earlier diagrams left out:**
- the `guild-ws` proxy;
- the alert channels;
- the broker's SQLite store;
- Firebase.

**And the new ones:**
- the three cache nodes;
- the router `postgres`;
- `pg-1`, `pg-2` and `pg-3` with etcd;
- the ETL service and the data warehouse.

## Grade 4 — data warehouse and ETL

1. **Run the ETL.** In Postman's *Grade 4* folder, *Run the ETL now* shows:
   - every database read from `postgres:5433` (a replica);
   - the rows extracted per table;
   - the rows loaded per warehouse table.

   It runs by itself every 60 s too: `curl localhost:8091/v1/runs?limit=3`.
2. **Query the star schema directly:**

   ```sh
   docker compose exec warehouse psql -U warehouse -c "\dt dw.*"
   docker compose exec warehouse psql -U warehouse -c "select username, battles, wins, raid_damage, global_coins from dw.v_player_stats order by wins desc limit 5"
   ```

3. **Show the analytics.** In Grafana, scroll to the warehouse panels: daily activity, top players, packages, notifications, raids, guilds and Map snapshots.
4. **Show its resilience.** An extract that fails is recorded and doesn't stop the others. Rename a column in a scratch copy, or show run 1 in `/v1/runs` after a fresh start: it was `partial` because the services hadn't migrated yet, and the next run succeeded.

## Grade 5 — replication and failover

1. **Show the cluster.** Run *The cluster* and *The router* in Postman's *Grade 5* folder, or `curl localhost:8008/cluster`. There is one leader, a synchronous standby and a replica, all streaming. The router's page (port 7000) shows `primary` with one server UP and `replicas` with two.
2. **Planned failover:** `docker compose stop <leader>`.
   - Within about 2 s the synchronous standby is the leader (`curl localhost:8008/cluster`).
   - The router switches, and Postman requests (for example *My profile*) keep working.
   - Grafana's *Role per node* moves the 1 to another node, and the *Timeline* goes up by one.
3. **Crash:** `docker compose kill <leader>`.
   - For about 20 s there is no leader, because the lock has to expire.
   - Requests that need the database answer `503 DEPENDENCY_UNAVAILABLE` with `Retry-After`, or now and then a `504` timeout. The services aren't evicted (`curl localhost:8090/v1/queues`).
   - Then a replica is promoted and everything works again. Nothing acknowledged is lost: synchronous replication.
4. **The old node rejoins:** `docker compose start <old leader>`. It comes back as a replica within seconds, using `pg_rewind` if needed.

## Grade 6 — caching

Postman's *Grade 6* folder, in order:

1. **Empty the cache, then read twice.** *Packages* shows `X-Cache: MISS`, then `HIT`, with `X-Cache-Node` and `Age`.
2. **Show invalidation.** *My profile* is `MISS`, then `HIT`. After *Change my display name* it is `MISS` again, with the new name, because the write bumped `gen:user-management`.
3. **Show the nodes.** *Cache nodes* lists the keys per node, their ring shares and hit ratios.
4. **Show the cached tokens:**

   ```sh
   for n in cache-1 cache-2 cache-3; do echo "== $n"; docker compose exec $n redis-cli --scan; done
   ```

   This shows `auth:token:…` (verified JWTs), `auth:jwks`, `gen:*` counters and `resp:*` answers spread over the three nodes.
5. **Show the cache between services.** *Broker: a user lookup* is `X-Broker-Cache: MISS`, then `HIT`.

## Grade 7 — consistent hashing

1. **Locate a key.** *Where a key lives*: `auth:jwks` is on `cache-2`.
2. **Simulate adding a node.** About 25 % of keys move on the ring, 75 % with `hash % N`, and 25 % with Redis Cluster's slots (moved on purpose). Virtual nodes keep the imbalance near 2 %, against about 40 % with one point per node.
3. **Simulate removing a node.** Only `cache-2`'s third of the keys moves.
4. **Kill a node for real:**
   1. `docker compose stop cache-2`.
   2. Requests keep working: `cache-2`'s keys go to the next node on the ring, and every other key stays.
   3. *Cache nodes* shows `cache-2` with `"up": false, "skipped": true`.
   4. `docker compose start cache-2`.
5. **The research write-up:** [lab-5-consistent-hashing.md](lab-5-consistent-hashing.md), including the comparison with Redis Cluster.

## Grades 8 and 9 — the account-deletion saga

1. **Happy path:** Postman's *Grade 9* folder.
   1. Register a player and give them a location.
   2. *Delete my account* answers `202` with the saga.
   3. *Wait for the saga* shows its four steps `succeeded`, each on a replica of its service.
   4. The player's token is refused (`401`), their login fails, and nobody finds their profile (`404`).
2. **Compensation:**
   1. Stop Map: `docker compose stop map-service`.
   2. Register a new player in Postman and delete their account.
   3. `GET /api/v1/sagas/{id}` (admin) shows `hide-from-map` retrying (attempts grow, `last_error: 503 NO_REPLICA`).
   4. After 30 s the step is given up, `deactivate-account` is compensated (`reactivate`), and the saga is `compensated`.
   5. The player can log in again.
   6. `docker compose start map-service`.
3. **Durability:** start a deletion while Map is stopped, then `docker compose restart message-broker`. The saga is still there afterwards and continues where it stopped (its state is in the broker's SQLite volume).
4. **A refused first step:** *Operator: delete an account that does not exist*. User Management refuses `deactivate` (`404`), and the saga ends `compensated` with the error recorded.
5. **Why a saga and not 2PC:** [conventions, section 6.1](lab-5-conventions.md#61-why-a-saga-and-not-two-phase-commit).

## Grade 10

- **Postman:** every collection passes (`lab-1` to `lab-5`).
- **Docker Hub:** the `0.6.0` images of the gateway, broker, User Management, Map, ETL service and the database.
- **The README:** endpoints and data formats in the [Lab 5 section](../README.md#lab-5--sharding-and-replication) and the [contract](lab-5-contract-madalina.md).
- **The diagrams:** updated as described under grades 2 and 3.
