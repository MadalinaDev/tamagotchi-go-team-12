# Lab 5 — Consistent hashing: research, our cache, and Redis Cluster

Grade 7 asks us to shard the cache with consistent hashing and, where Redis Cluster is involved, to compare the two algorithms in detail. This document covers what consistent hashing solves, how the team's cache uses it, and how it compares with Redis Cluster's hash slots and the other well-known schemes. The numbers come from the gateway's simulation endpoint (`GET /api/v1/admin/cache/simulation`), run on the Lab 5 stack.

## 1. The problem: which node holds a key

The cache has three Redis nodes (`cache-1`, `cache-2`, `cache-3`) and two clients that must agree on where every key lives: the API Gateway and the Message Broker. Neither has a central directory to ask. Each must compute the node from the key alone.

**The naive answer, `hash(key) % N`,** balances keys well but breaks when `N` changes. A key stays on its node only if `hash % N == hash % (N + 1)`, which holds for about `1 / (N + 1)` of the keys. Going from 3 to 4 nodes therefore moves about three quarters of all keys. For a cache that means three quarters of the entries become misses at once, and the services behind the gateway take the whole load.

## 2. Consistent hashing

Consistent hashing (Karger et al., 1997) maps nodes and keys onto the same circle of hash values:

1. Every node is hashed to a position on the ring.
2. A key belongs to the first node clockwise from the key's own position.
3. Adding a node takes over only the arc between the new node and its predecessor, about `1 / (N + 1)` of the keys. Every other key stays where it was.
4. Removing a node hands only its own keys to its successor.

One point per node gives very uneven arcs. With three random points, one node often owns half the ring. **Virtual nodes** fix this: every physical node owns `v` points (`cache-1#0` … `cache-1#159`), so its share is the sum of many small arcs. The relative spread of the shares shrinks roughly like `1 / sqrt(v)`. Amazon's Dynamo (DeCandia et al., 2007) popularised the scheme for data stores.

## 3. The team's cache

| Choice | Value | Why |
| --- | --- | --- |
| Hash | MD5 of the string, first 8 bytes big-endian: a 64-bit ring | Fast, evenly spread and in every standard library. It isn't used for security here. |
| Virtual nodes | 160 per node (`CACHE_VNODES`) | 480 points for 3 nodes. The shares stay within a few percent and the ring costs a few kilobytes. |
| Node names | the host names in `CACHE_NODES` (`cache-1:6379,cache-2:6379,cache-3:6379`) | Both clients read the same Compose anchor (`x-cache-env`), so they build the same ring. |
| Lookup | binary search over the sorted points, `O(log(N·v))` | Constant memory per lookup, microseconds per key. |
| Node down | skipped for 10 s (`CACHE_DOWN_MS`); its keys go to the next node clockwise | Only the failed node's keys move. Requests never fail: an error or a 250 ms timeout counts as a miss. |
| Replication | none | It's a cache: a lost entry is recomputed by the service that owns it. |

**Both clients agree.** The ring is implemented twice, in `gateway-service/app/cache/ring.py` and `message-broker/app/cache.py`. Both test suites pin the same placement table. For example, `auth:jwks` lives on `cache-2` and moves to `cache-1` when `cache-2` is down. A change to either implementation that would split the cache fails a test.

**What is cached, and under which keys:**

| Key | Written by | TTL | Purpose |
| --- | --- | --- | --- |
| `resp:<service>:g<gen>:<owner>:<sha256>` | gateway | 60–300 s | GET answers on an allowlist: packages, definitions, rules, profiles. `<owner>` is the user for per-user answers, `shared` for definitions. |
| `auth:token:<sha256 of the token>` | gateway | until the token expires, at most 300 s | A verified JWT, so the signature isn't checked on every request. |
| `auth:jwks` | gateway | 300 s | User Management's public keys, shared by every gateway instance. |
| `gen:<service>` | gateway, broker | none | A generation counter. A successful write to a service increments it, and every cached answer of that service becomes stale at once, because its key names the old generation. |
| `lookup:user-management:g<gen>:<id>` | broker | 60 s | User profiles that services look up from each other. |
| `auth:revoked:<user>` | broker | 24 h | Set while an account is being deleted. The gateway refuses that user's tokens. |

Invalidation never scans or deletes keys. Bumping one counter makes the old keys unreachable, and their TTL removes them. Keys that belong together (a service's answers and its counter) may live on different nodes. That is fine, because each lookup reads the counter first.

## 4. Measurements

Gateway simulation, 50,000 sample keys (`key:0` … `key:49999`), the three cache nodes:

| Change | Ring, 160 vnodes | `hash % N` | Redis Cluster slots | Ideal |
| --- | --- | --- | --- | --- |
| Add `cache-4` | **25.3 %** of keys move | 75.3 % | 24.9 % (4,096 slots) | 25 % |
| Remove `cache-2` | **32.8 %** (only `cache-2`'s keys) | 66.7 % | 33.4 % (5,461 slots) | 33.3 % |

Balance after adding `cache-4`, as the standard deviation of the per-node key counts relative to their mean:

| Virtual nodes per node | 1 | 10 | 40 | 160 | 400 |
| --- | --- | --- | --- | --- | --- |
| Imbalance | 49.5 % | 30.1 % | 11.6 % | **1.9 %** | 6.0 % |

- One point per node is unusable: one node held 39 % of the keys and another 9.5 %.
- Past about a hundred points the imbalance is noise from the particular sample. The 400-point ring happened to land slightly worse than the 160-point one.
- On the running stack the three nodes own 35.3 %, 32.5 % and 32.2 % of the ring (`GET /api/v1/admin/cache`).

To reproduce (as an admin):

```sh
curl -H "Authorization: Bearer $ADMIN_TOKEN" \
  "http://localhost:8080/api/v1/admin/cache/simulation?keys=50000&add=cache-4"
curl -H "Authorization: Bearer $ADMIN_TOKEN" \
  "http://localhost:8080/api/v1/admin/cache/simulation?keys=50000&remove=cache-2&vnodes=10"
curl -H "Authorization: Bearer $ADMIN_TOKEN" \
  "http://localhost:8080/api/v1/admin/cache/locate?key=auth:jwks"
```

## 5. Redis Cluster's hash slots, compared in detail

Redis Cluster doesn't use a ring. It splits the key space into **16,384 hash slots**:

- **Placement:** `slot = CRC16(key) mod 16384`, using the CCITT/XMODEM CRC. If the key contains a hash tag (`{user:42}:profile`), only the part between the braces is hashed, so related keys share a slot.
- **Ownership:** every master owns ranges of slots. `redis-cli --cluster create` splits them evenly, so 3 masters get 0–5460, 5461–10922 and 10923–16383.
- **Discovery:** the slot map lives in the cluster itself. Nodes gossip it on the cluster bus (data port + 10,000). Clients cache it and follow `MOVED` (the slot has moved for good) and `ASK` (it is moving right now) redirects.
- **Resharding:** whole slots move between masters, key by key with `MIGRATE`, while the cluster serves traffic. Adding a master and rebalancing moves `16384 / (N + 1)` slots, so the same fraction of keys moves as on a ring.

| | Consistent hashing (our cache) | Redis Cluster hash slots |
| --- | --- | --- |
| Who decides placement | Each client, from the key and the node list | The cluster. Clients learn the slot map and are redirected. |
| Keys moved when a node joins or leaves | About `1 / (N + 1)` (25.3 % measured), and only to or from that node | Exactly the slots moved (24.9 % here). Slots are re-assigned on purpose, so the balance is near perfect. |
| Balance | Statistical, set by the number of virtual nodes (1.9 % spread at 160) | Exact: slots are counted, 16384 / N each |
| Moved data | Not copied. The new owner starts empty, so those keys are misses until recomputed (fine for a cache) | Copied with `MIGRATE`. Nothing is lost, which a primary store needs. |
| Node failure | The client skips the node, and its keys are misses on the next node | A replica of the failed master is promoted by a vote of the other masters. The slots stay served with their data. |
| Multi-key operations | Any keys a client reads separately | Only within one slot (hash tags) |
| Clients | Any Redis client, plus the ring code (here about 100 lines, in two repositories that must agree) | A cluster-aware client that understands `MOVED`/`ASK` |
| Operations | Three plain Redis containers | At least 3 masters (6 nodes with replicas), the cluster bus and resharding commands |
| Consistency during changes | Two clients with different node lists would disagree, so the list comes from one Compose anchor | One authoritative map, versioned by an epoch |

**Why the team chose client-side consistent hashing.** The cache holds only data that can be recomputed. What Redis Cluster adds (moving data, replicas, failover with votes) protects data a cache can afford to lose. It also costs a cluster-aware client in both the gateway and the broker, and twice the containers. Consistent hashing gives the property that matters here: a node joining or failing disturbs only its own share of the keys. It does that with plain Redis and a few lines the two clients share. It also makes the algorithm visible, which the lab asks for: `locate` shows where a key lives, and the simulation shows the 25 % vs 75 % difference.

If the cache ever held data that couldn't be recomputed, such as sessions without a database behind them, Redis Cluster (or Redis Sentinel with replicas) would be the right tool.

## 6. Other schemes considered

- **Rendezvous (highest random weight) hashing** (Thaler & Ravishankar, 1998): score every node with `hash(key, node)` and take the highest. The balance is perfect and the disruption minimal, with no virtual nodes, but every lookup costs `O(N)` hashes. With three nodes that's cheap. The ring was chosen because it's the classic algorithm the lab names and its lookups stay `O(log)` as nodes are added.
- **Jump consistent hash** (Lamping & Veach, 2014): `O(log N)` time, no memory and near-perfect balance. But buckets are numbered `0 … N-1`, and only the last one can be removed. We need to skip any failed node, so it doesn't fit.
- **Maglev hashing** (Eisenbud et al., 2016): a precomputed lookup table, built for load balancers that must change very little on a backend change. More than a three-node cache needs.
- **Consistent hashing with bounded loads** (Mirrokni, Thorup and Zadimoghaddam, 2018): caps every node at `(1 + ε)` times the average load, spilling clockwise past full nodes. It's useful against hot keys on a few nodes, and HAProxy offers it as `hash-balance-factor`. Our hottest keys (`auth:jwks`, the `gen:*` counters) are tiny reads, so it isn't needed.

## References

- D. Karger, E. Lehman, T. Leighton, R. Panigrahy, M. Levine, D. Lewin. *Consistent Hashing and Random Trees.* STOC 1997.
- G. DeCandia et al. *Dynamo: Amazon's Highly Available Key-value Store.* SOSP 2007.
- *Redis Cluster specification* and *Scale with Redis Cluster*, redis.io documentation.
- D. Thaler, C. Ravishankar. *Using Name-Based Mappings to Increase Hit Rates.* IEEE/ACM Transactions on Networking, 1998.
- J. Lamping, E. Veach. *A Fast, Minimal Memory, Consistent Hash Algorithm.* 2014.
- D. Eisenbud et al. *Maglev: A Fast and Reliable Software Network Load Balancer.* NSDI 2016.
- V. Mirrokni, M. Thorup, M. Zadimoghaddam. *Consistent Hashing with Bounded Loads.* SODA 2018.
