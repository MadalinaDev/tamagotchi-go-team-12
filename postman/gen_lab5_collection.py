"""Writes postman/lab-5.postman_collection.json: Lab 5 grade by grade (docs/lab-5-conventions.md).

    python postman/gen_lab5_collection.py
"""

from __future__ import annotations

import json
from pathlib import Path

JSON = [{"key": "Content-Type", "value": "application/json"}]


def bearer(variable: str) -> list[dict[str, str]]:
    return [{"key": "Authorization", "value": f"Bearer {{{{{variable}}}}}"}]


def request(
    name: str,
    method: str,
    url: str,
    tests: list[str],
    *,
    headers: list[dict[str, str]] | None = None,
    body: str | None = None,
    pre: list[str] | None = None,
) -> dict:
    item: dict = {
        "name": name,
        "request": {"method": method, "header": headers or [], "url": url},
        "event": [{"listen": "test", "script": {"type": "text/javascript", "exec": tests}}],
    }
    if body is not None:
        item["request"]["body"] = {
            "mode": "raw",
            "raw": body,
            "options": {"raw": {"language": "json"}},
        }
    if pre:
        item["event"].insert(
            0, {"listen": "prerequest", "script": {"type": "text/javascript", "exec": pre}}
        )
    return item


def folder(name: str, description: str, items: list[dict]) -> dict:
    return {"name": name, "description": description, "item": items}


def poll(variable: str, done: str, attempts: int = 40) -> list[str]:
    """Test lines that send the same request again (every 0.5 s) until `done` holds."""
    return [
        f"const tries = Number(pm.collectionVariables.get('{variable}') || 0) + 1;",
        "const saga = pm.response.json();",
        f"if (!({done}) && tries < {attempts}) {{",
        f"  pm.collectionVariables.set('{variable}', tries);",
        "  postman.setNextRequest(pm.info.requestName);",
        "  return;",
        "}",
        f"pm.collectionVariables.set('{variable}', 0);",
    ]


WAIT = ["setTimeout(() => {}, 500);"]

setup = folder(
    "Setup",
    "Log in the seeded admin and Alice.",
    [
        request(
            "Log in the admin",
            "POST",
            "{{gateway_url}}/api/v1/auth/login",
            [
                "pm.test('200', () => pm.response.to.have.status(200));",
                "pm.collectionVariables.set('admin_token', pm.response.json().access_token);",
            ],
            headers=JSON,
            body='{\n  "email": "{{admin_email}}",\n  "password": "{{password}}"\n}',
        ),
        request(
            "Log in Alice",
            "POST",
            "{{gateway_url}}/api/v1/auth/login",
            [
                "pm.test('200', () => pm.response.to.have.status(200));",
                "pm.collectionVariables.set('alice_token', pm.response.json().access_token);",
            ],
            headers=JSON,
            body='{\n  "email": "{{alice_email}}",\n  "password": "{{password}}"\n}',
        ),
        request(
            "Alice's profile",
            "GET",
            "{{gateway_url}}/api/v1/users/me",
            [
                "pm.test('200', () => pm.response.to.have.status(200));",
                "pm.collectionVariables.set('alice_id', pm.response.json().user_id);",
            ],
            headers=bearer("alice_token"),
        ),
    ],
)

grade4 = folder(
    "Grade 4 - data warehouse and ETL",
    "etl-service (port 8091) extracts every team database from the replicas (postgres:5433, "
    "read-only etl_reader) into the star schema dw of the warehouse Postgres.",
    [
        request(
            "ETL status",
            "GET",
            "{{etl_url}}/status",
            [
                "pm.test('200', () => pm.response.to.have.status(200));",
                "const body = pm.response.json();",
                "pm.test('the warehouse is reachable', () => {",
                "  pm.expect(body.status).to.eql('ok');",
                "  pm.expect(body.checks.warehouse).to.eql('ok');",
                "});",
                "pm.test('it reads the replicas (port 5433)', () => "
                "pm.expect(body.source.port).to.eql(5433));",
            ],
        ),
        request(
            "Run the ETL now (operator token)",
            "POST",
            "{{etl_url}}/v1/runs",
            [
                "pm.test('200', () => pm.response.to.have.status(200));",
                "const run = pm.response.json();",
                "pm.collectionVariables.set('etl_run_id', run.run_id);",
                "pm.test('every extract succeeded', () => {",
                "  pm.expect(run.status).to.eql('succeeded');",
                "  pm.expect(run.errors).to.eql({});",
                "});",
                "pm.test('it extracted users, battles and raids', () => {",
                "  pm.expect(run.extracted.users).to.be.above(0);",
                "  pm.expect(run.extracted).to.have.property('battles');",
                "  pm.expect(run.extracted).to.have.property('raids');",
                "});",
                "pm.test('it loaded the dimensions and facts', () => {",
                "  pm.expect(run.loaded.dim_user).to.be.above(0);",
                "  pm.expect(run.loaded).to.have.property('fact_battle');",
                "  pm.expect(run.loaded.fact_map_snapshot).to.be.above(0);",
                "});",
                "pm.test('every database was read from a replica', () => {",
                "  Object.values(run.source).forEach((endpoint) => "
                "pm.expect(endpoint).to.match(/:5433$/));",
                "});",
            ],
            headers=bearer("etl_admin_token"),
        ),
        request(
            "Running it without the token -> 401",
            "POST",
            "{{etl_url}}/v1/runs",
            [
                "pm.test('401', () => pm.response.to.have.status(401));",
                "pm.test('team error format', () => "
                "pm.expect(pm.response.json()).to.have.keys('code', 'message', 'request_id', "
                "'details'));",
            ],
        ),
        request(
            "The run, by its ID",
            "GET",
            "{{etl_url}}/v1/runs/{{etl_run_id}}",
            [
                "pm.test('200', () => pm.response.to.have.status(200));",
                "pm.test('the same run', () => pm.expect(pm.response.json().run_id)"
                ".to.eql(Number(pm.collectionVariables.get('etl_run_id'))));",
            ],
        ),
        request(
            "Recent runs",
            "GET",
            "{{etl_url}}/v1/runs?limit=5",
            [
                "pm.test('200', () => pm.response.to.have.status(200));",
                "pm.test('newest first', () => pm.expect(pm.response.json().runs[0].run_id)"
                ".to.be.at.least(Number(pm.collectionVariables.get('etl_run_id'))));",
            ],
        ),
        request(
            "The warehouse: tables, views and reports",
            "GET",
            "{{etl_url}}/v1/warehouse",
            [
                "pm.test('200', () => pm.response.to.have.status(200));",
                "const dw = pm.response.json();",
                "pm.test('a star schema', () => {",
                "  pm.expect(dw.dimensions).to.include.members(['dim_date', 'dim_user', "
                "'dim_package', 'dim_pet', 'dim_guild']);",
                "  pm.expect(dw.facts).to.include.members(['fact_battle', 'fact_raid', "
                "'fact_wallet_entry', 'fact_notification', 'fact_map_snapshot']);",
                "  pm.expect(dw.views).to.include('v_player_stats');",
                "});",
                "pm.test('loaded', () => pm.expect(dw.tables.dim_user).to.be.above(0));",
            ],
        ),
        request(
            "Report: top players (operator token)",
            "GET",
            "{{etl_url}}/v1/reports/players?limit=5",
            [
                "pm.test('200', () => pm.response.to.have.status(200));",
                "const report = pm.response.json();",
                "pm.test('rows from dw.v_player_stats', () => {",
                "  pm.expect(report.rows.length).to.be.within(1, 5);",
                "  pm.expect(report.rows[0]).to.include.keys('username', 'battles', 'wins', "
                "'raid_damage', 'global_coins');",
                "});",
            ],
            headers=bearer("etl_admin_token"),
        ),
        request(
            "Report: daily activity of the last 7 days",
            "GET",
            "{{etl_url}}/v1/reports/daily-activity?days=7",
            [
                "pm.test('200', () => pm.response.to.have.status(200));",
                "pm.test('one row per day', () => "
                "pm.expect(pm.response.json().rows.length).to.be.within(1, 7));",
            ],
            headers=bearer("etl_admin_token"),
        ),
        request(
            "ETL metrics",
            "GET",
            "{{etl_url}}/metrics",
            [
                "pm.test('200', () => pm.response.to.have.status(200));",
                "pm.test('runs and warehouse rows are exported', () => {",
                "  pm.expect(pm.response.text()).to.include('etl_runs_total');",
                "  pm.expect(pm.response.text()).to.include('etl_warehouse_rows');",
                "});",
            ],
        ),
    ],
)

grade5 = folder(
    "Grade 5 - replication and failover",
    "Patroni: pg-1, pg-2, pg-3, one leader and two streaming replicas (one synchronous), the "
    "leader lock in etcd. The router `postgres` sends 5432 to the leader and 5433 to the "
    "replicas. Failover: docker compose stop <leader> (see docs/lab-5-demo.md).",
    [
        request(
            "The cluster (Patroni REST API)",
            "GET",
            "{{patroni_url}}/cluster",
            [
                "pm.test('200', () => pm.response.to.have.status(200));",
                "const members = pm.response.json().members;",
                "const leader = members.filter((m) => m.role === 'leader');",
                "const replicas = members.filter((m) => m.role !== 'leader');",
                "pm.test('three nodes, one leader', () => {",
                "  pm.expect(members.length).to.eql(3);",
                "  pm.expect(leader.length).to.eql(1);",
                "});",
                "pm.test('two replicas streaming from it, one synchronous', () => {",
                "  pm.expect(replicas.length).to.eql(2);",
                "  replicas.forEach((m) => pm.expect(m.state).to.eql('streaming'));",
                "  pm.expect(members.filter((m) => m.role === 'sync_standby').length).to.eql(1);",
                "});",
                "pm.collectionVariables.set('leader', leader[0].name);",
                "console.log(`leader: ${leader[0].name} (stop it to fail over)`);",
            ],
        ),
        request(
            "The router (HAProxy): 5432 -> the leader, 5433 -> the replicas",
            "GET",
            "{{haproxy_url}}/;csv",
            [
                "pm.test('200', () => pm.response.to.have.status(200));",
                "const rows = pm.response.text().split('\\n').map((line) => line.split(','));",
                "const up = (proxy) => rows.filter((r) => r[0] === proxy && /^pg-/.test(r[1]) "
                "&& r[17] === 'UP').map((r) => r[1]);",
                "pm.test('one server behind the primary port: the leader', () => {",
                "  pm.expect(up('primary')).to.eql([pm.collectionVariables.get('leader')]);",
                "});",
                "pm.test('two servers behind the replica port', () => "
                "pm.expect(up('replicas').length).to.eql(2));",
            ],
        ),
    ],
)

grade6 = folder(
    "Grade 6 - caching",
    "The gateway caches common GETs (per user, or shared for definitions) and verified tokens "
    "on three Redis nodes; a write to a service makes that service's cached answers stale.",
    [
        request(
            "Empty the cache (admin)",
            "DELETE",
            "{{gateway_url}}/api/v1/admin/cache",
            [
                "pm.test('200', () => pm.response.to.have.status(200));",
                "pm.test('every node flushed', () => pm.expect(pm.response.json().flushed)"
                ".to.eql({ 'cache-1': true, 'cache-2': true, 'cache-3': true }));",
            ],
            headers=bearer("admin_token"),
        ),
        request(
            "Packages: first read -> MISS",
            "GET",
            "{{gateway_url}}/api/v1/packages",
            [
                "pm.test('200', () => pm.response.to.have.status(200));",
                "pm.test('X-Cache: MISS', () => pm.expect(pm.response.headers.get('X-Cache'))"
                ".to.eql('MISS'));",
            ],
            headers=bearer("alice_token"),
        ),
        request(
            "Packages: second read -> HIT, from one node",
            "GET",
            "{{gateway_url}}/api/v1/packages",
            [
                "pm.test('200', () => pm.response.to.have.status(200));",
                "pm.test('X-Cache: HIT', () => pm.expect(pm.response.headers.get('X-Cache'))"
                ".to.eql('HIT'));",
                "pm.test('the node the ring chose', () => "
                "pm.expect(pm.response.headers.get('X-Cache-Node')).to.match(/^cache-[123]$/));",
                "pm.test('Age is set', () => pm.expect(pm.response.headers.has('Age')).to.be.true);",
            ],
            headers=bearer("alice_token"),
        ),
        request(
            "My profile: MISS",
            "GET",
            "{{gateway_url}}/api/v1/users/me",
            [
                "pm.test('200', () => pm.response.to.have.status(200));",
                "pm.test('X-Cache: MISS', () => pm.expect(pm.response.headers.get('X-Cache'))"
                ".to.eql('MISS'));",
            ],
            headers=bearer("alice_token"),
        ),
        request(
            "My profile again: HIT",
            "GET",
            "{{gateway_url}}/api/v1/users/me",
            [
                "pm.test('X-Cache: HIT', () => pm.expect(pm.response.headers.get('X-Cache'))"
                ".to.eql('HIT'));",
            ],
            headers=bearer("alice_token"),
        ),
        request(
            "Change my display name (a write to User Management)",
            "PATCH",
            "{{gateway_url}}/api/v1/users/me",
            [
                "pm.test('200', () => pm.response.to.have.status(200));",
            ],
            headers=JSON + bearer("alice_token") + [{"key": "Idempotency-Key", "value": "{{$guid}}"}],
            body='{\n  "display_name": "{{alice_display_name}}"\n}',
            pre=["pm.collectionVariables.set('alice_display_name', 'Alice ' + Date.now() % 100000);"],
        ),
        request(
            "My profile after the write: MISS, the new name",
            "GET",
            "{{gateway_url}}/api/v1/users/me",
            [
                "pm.test('X-Cache: MISS (the write made it stale)', () => "
                "pm.expect(pm.response.headers.get('X-Cache')).to.eql('MISS'));",
                "pm.test('the new display name', () => pm.expect(pm.response.json().display_name)"
                ".to.eql(pm.collectionVariables.get('alice_display_name')));",
            ],
            headers=bearer("alice_token"),
        ),
        request(
            "Cache nodes, their keys, shares and hit ratios (admin)",
            "GET",
            "{{gateway_url}}/api/v1/admin/cache",
            [
                "pm.test('200', () => pm.response.to.have.status(200));",
                "const nodes = pm.response.json().nodes;",
                "pm.test('three nodes, all up', () => {",
                "  pm.expect(nodes.length).to.eql(3);",
                "  nodes.forEach((node) => pm.expect(node.up).to.be.true);",
                "});",
                "pm.test('the ring shares add up to 100 %', () => {",
                "  const total = nodes.reduce((sum, node) => sum + node.ring_share_percent, 0);",
                "  pm.expect(total).to.be.within(99.5, 100.5);",
                "});",
            ],
            headers=bearer("admin_token"),
        ),
        request(
            "Broker: a user lookup between services -> MISS",
            "GET",
            "{{broker_url}}/internal/v1/users/{{alice_id}}",
            [
                "pm.test('200', () => pm.response.to.have.status(200));",
                "pm.test('X-Broker-Cache: MISS', () => "
                "pm.expect(pm.response.headers.get('X-Broker-Cache')).to.eql('MISS'));",
            ],
            headers=bearer("map_service_token"),
        ),
        request(
            "Broker: the same lookup -> HIT, User Management not called",
            "GET",
            "{{broker_url}}/internal/v1/users/{{alice_id}}",
            [
                "pm.test('200', () => pm.response.to.have.status(200));",
                "pm.test('X-Broker-Cache: HIT', () => "
                "pm.expect(pm.response.headers.get('X-Broker-Cache')).to.eql('HIT'));",
                "pm.test('answered by the cache', () => "
                "pm.expect(pm.response.headers.get('X-Broker-Transport')).to.eql('cache'));",
            ],
            headers=bearer("map_service_token"),
        ),
    ],
)

grade7 = folder(
    "Grade 7 - consistent hashing",
    "Every key has a position on a 64-bit ring (MD5); every node owns 160 virtual points. "
    "docs/lab-5-consistent-hashing.md compares it with hash % N and Redis Cluster's slots.",
    [
        request(
            "Where a key lives",
            "GET",
            "{{gateway_url}}/api/v1/admin/cache/locate?key=auth:jwks",
            [
                "pm.test('200', () => pm.response.to.have.status(200));",
                "pm.test('one of the three nodes', () => pm.expect(pm.response.json().node)"
                ".to.match(/^cache-[123]$/));",
            ],
            headers=bearer("admin_token"),
        ),
        request(
            "Simulation: add a fourth node",
            "GET",
            "{{gateway_url}}/api/v1/admin/cache/simulation?keys=10000&add=cache-4",
            [
                "pm.test('200', () => pm.response.to.have.status(200));",
                "const s = pm.response.json();",
                "pm.test('the ring moves about 1/4 of the keys', () => "
                "pm.expect(s.consistent_hashing.moved.percent).to.be.within(15, 35));",
                "pm.test('hash % N moves about 3/4', () => "
                "pm.expect(s.modulo.moved.percent).to.be.above(60));",
                "pm.test('Redis Cluster moves about 1/4 too (whole slots)', () => "
                "pm.expect(s.redis_cluster_slots.moved.percent).to.be.within(15, 35));",
                "pm.test('virtual nodes keep the shares even', () => "
                "pm.expect(s.consistent_hashing.imbalance_percent).to.be.below("
                "s.consistent_hashing.imbalance_percent_with_1_point_per_node));",
            ],
            headers=bearer("admin_token"),
        ),
        request(
            "Simulation: remove cache-2",
            "GET",
            "{{gateway_url}}/api/v1/admin/cache/simulation?keys=10000&remove=cache-2",
            [
                "pm.test('200', () => pm.response.to.have.status(200));",
                "const s = pm.response.json();",
                "pm.test('only cache-2 keys move (about 1/3)', () => "
                "pm.expect(s.consistent_hashing.moved.percent).to.be.within(20, 45));",
                "pm.test('hash % N moves most keys', () => "
                "pm.expect(s.modulo.moved.percent).to.be.above(50));",
            ],
            headers=bearer("admin_token"),
        ),
        request(
            "A player may not inspect the cache -> 403",
            "GET",
            "{{gateway_url}}/api/v1/admin/cache",
            ["pm.test('403', () => pm.response.to.have.status(403));"],
            headers=bearer("alice_token"),
        ),
    ],
)

grade9 = folder(
    "Grade 9 - account deletion saga",
    "DELETE /api/v1/users/me starts a saga the broker coordinates across User Management and "
    "Map: deactivate -> hide -> erase (pivot) -> purge. A refused step undoes the earlier "
    "ones in reverse (reactivate, unhide).",
    [
        request(
            "Register a player to delete",
            "POST",
            "{{gateway_url}}/api/v1/users",
            [
                "pm.test('201', () => pm.response.to.have.status(201));",
                "pm.collectionVariables.set('doomed_id', pm.response.json().user_id);",
            ],
            headers=JSON + [{"key": "Idempotency-Key", "value": "{{$guid}}"}],
            body=(
                '{\n  "username": "{{doomed_username}}",\n  "email": "{{doomed_email}}",\n'
                '  "password": "{{password}}",\n  "display_name": "Doomed player"\n}'
            ),
            pre=[
                "const suffix = Date.now().toString(36);",
                "pm.collectionVariables.set('doomed_username', `doomed_${suffix}`);",
                "pm.collectionVariables.set('doomed_email', `doomed_${suffix}@example.com`);",
            ],
        ),
        request(
            "The player logs in",
            "POST",
            "{{gateway_url}}/api/v1/auth/login",
            [
                "pm.test('200', () => pm.response.to.have.status(200));",
                "pm.collectionVariables.set('doomed_token', pm.response.json().access_token);",
            ],
            headers=JSON,
            body='{\n  "email": "{{doomed_email}}",\n  "password": "{{password}}"\n}',
        ),
        request(
            "The player shares a location (Map has data about them)",
            "PUT",
            "{{gateway_url}}/api/v1/map/location",
            ["pm.test('200', () => pm.response.to.have.status(200));"],
            headers=JSON + bearer("doomed_token") + [{"key": "Idempotency-Key", "value": "{{$guid}}"}],
            body=(
                '{\n  "latitude": 47.0105,\n  "longitude": 28.8638,\n  "accuracy_m": 5,\n'
                '  "recorded_at": "{{now}}"\n}'
            ),
            pre=["pm.collectionVariables.set('now', new Date().toISOString());"],
        ),
        request(
            "Delete my account -> 202, the saga starts",
            "DELETE",
            "{{gateway_url}}/api/v1/users/me",
            [
                "pm.test('202', () => pm.response.to.have.status(202));",
                "const saga = pm.response.json();",
                "pm.collectionVariables.set('saga_id', saga.saga_id);",
                "pm.test('an account-deletion saga about this player', () => {",
                "  pm.expect(saga.type).to.eql('account-deletion');",
                "  pm.expect(saga.subject).to.eql(pm.collectionVariables.get('doomed_id'));",
                "  pm.expect(saga.steps.map((s) => s.name)).to.eql(['deactivate-account', "
                "'hide-from-map', 'erase-account', 'purge-map-data']);",
                "  pm.expect(saga.steps.map((s) => s.kind)).to.eql(['compensatable', "
                "'compensatable', 'pivot', 'retriable']);",
                "});",
                "pm.test('Location: /api/v1/sagas/{id}', () => "
                "pm.expect(pm.response.headers.get('Location')).to.eql(`/api/v1/sagas/${saga.saga_id}`));",
            ],
            headers=bearer("doomed_token"),
        ),
        request(
            "Wait for the saga to complete (admin)",
            "GET",
            "{{gateway_url}}/api/v1/sagas/{{saga_id}}",
            [
                *poll("saga_polls", "saga.status === 'completed' || saga.status === 'failed' "
                      "|| saga.status === 'compensated'"),
                "pm.test('completed', () => pm.expect(saga.status).to.eql('completed'));",
                "pm.test('every step succeeded, on a replica of its service', () => {",
                "  saga.steps.forEach((step) => {",
                "    pm.expect(step.status).to.eql('succeeded');",
                "    pm.expect(step.replica).to.be.a('string');",
                "  });",
                "});",
            ],
            headers=bearer("admin_token"),
            pre=WAIT,
        ),
        request(
            "The deleted player is locked out -> 401",
            "GET",
            "{{gateway_url}}/api/v1/users/me",
            ["pm.test('401', () => pm.response.to.have.status(401));"],
            headers=bearer("doomed_token"),
        ),
        request(
            "Their credentials no longer work -> 401",
            "POST",
            "{{gateway_url}}/api/v1/auth/login",
            ["pm.test('401', () => pm.response.to.have.status(401));"],
            headers=JSON,
            body='{\n  "email": "{{doomed_email}}",\n  "password": "{{password}}"\n}',
        ),
        request(
            "Nobody can find their profile -> 404",
            "GET",
            "{{gateway_url}}/api/v1/users/{{doomed_id}}",
            ["pm.test('404', () => pm.response.to.have.status(404));"],
            headers=bearer("alice_token"),
        ),
        request(
            "Another player cannot read the saga -> 404",
            "GET",
            "{{gateway_url}}/api/v1/sagas/{{saga_id}}",
            ["pm.test('404', () => pm.response.to.have.status(404));"],
            headers=bearer("alice_token"),
        ),
        request(
            "The admin lists the sagas",
            "GET",
            "{{gateway_url}}/api/v1/admin/sagas?type=account-deletion&limit=20",
            [
                "pm.test('200', () => pm.response.to.have.status(200));",
                "pm.test('the saga is listed', () => pm.expect(pm.response.json().sagas"
                ".map((s) => s.saga_id)).to.include(pm.collectionVariables.get('saga_id')));",
            ],
            headers=bearer("admin_token"),
        ),
        request(
            "Operator: delete an account that does not exist",
            "POST",
            "{{broker_url}}/v1/sagas",
            [
                "pm.test('202', () => pm.response.to.have.status(202));",
                "pm.collectionVariables.set('ghost_saga_id', pm.response.json().saga_id);",
            ],
            headers=JSON + bearer("broker_admin_token"),
            body='{\n  "type": "account-deletion",\n  "user_id": "{{$guid}}"\n}',
        ),
        request(
            "...User Management refuses the first step: the saga is compensated",
            "GET",
            "{{broker_url}}/v1/sagas/{{ghost_saga_id}}",
            [
                *poll("ghost_polls", "saga.status !== 'running' && saga.status !== 'compensating'"),
                "pm.test('compensated', () => pm.expect(saga.status).to.eql('compensated'));",
                "pm.test('the refusal is recorded', () => {",
                "  pm.expect(saga.steps[0].status).to.eql('failed');",
                "  pm.expect(saga.last_error).to.include('404');",
                "});",
            ],
            headers=bearer("broker_admin_token"),
            pre=WAIT,
        ),
        request(
            "A service cannot call a saga step through the broker -> 404",
            "POST",
            "{{broker_url}}/internal/v1/sagas/account-deletion/{{alice_id}}/erase",
            ["pm.test('404', () => pm.response.to.have.status(404));"],
            headers=JSON + bearer("map_service_token"),
            body="{}",
        ),
    ],
)

grade10 = folder(
    "Grade 10 - monitoring",
    "Prometheus scrapes the ETL service and every Patroni node; the Lab 5 Grafana dashboard "
    "shows the cluster, the cache, the sagas and the warehouse.",
    [
        request(
            "Prometheus: three database nodes running",
            "GET",
            "{{prometheus_url}}/api/v1/query?query=sum(patroni_postgres_running)",
            [
                "pm.test('200', () => pm.response.to.have.status(200));",
                "pm.test('3', () => pm.expect(pm.response.json().data.result[0].value[1])"
                ".to.eql('3'));",
            ],
        ),
        request(
            "Prometheus: the ETL service is scraped",
            "GET",
            '{{prometheus_url}}/api/v1/query?query=up{job="etl"}',
            [
                "pm.test('200', () => pm.response.to.have.status(200));",
                "pm.test('up', () => pm.expect(pm.response.json().data.result[0].value[1])"
                ".to.eql('1'));",
            ],
        ),
        request(
            "Grafana: the Lab 5 dashboard",
            "GET",
            "{{grafana_url}}/api/search?query=Lab%205",
            [
                "pm.test('200', () => pm.response.to.have.status(200));",
                "pm.test('provisioned', () => pm.expect(pm.response.json().map((d) => d.uid))"
                ".to.include('tamagotchi-go-lab5'));",
            ],
        ),
    ],
)

collection = {
    "info": {
        "name": "Lab 5 - sharding and replication",
        "description": (
            "Lab 5 grade by grade (docs/lab-5-conventions.md, demo: docs/lab-5-demo.md). Start the "
            "stack (docker compose up -d --wait), then set etl_admin_token, broker_admin_token "
            "and map_service_token from .env (ETL_ADMIN_TOKEN, BROKER_ADMIN_TOKEN, "
            "MAP_SERVICE_TOKEN; newman: --env-var etl_admin_token=... and so on)."
        ),
        "schema": "https://schema.getpostman.com/json/collection/v2.1.0/collection.json",
    },
    "item": [setup, grade4, grade5, grade6, grade7, grade9, grade10],
    "variable": [
        {"key": key, "value": value}
        for key, value in (
            ("gateway_url", "http://localhost:8080"),
            ("broker_url", "http://localhost:8090"),
            ("etl_url", "http://localhost:8091"),
            ("patroni_url", "http://localhost:8008"),
            ("haproxy_url", "http://localhost:7000"),
            ("prometheus_url", "http://localhost:9090"),
            ("grafana_url", "http://localhost:3000"),
            ("admin_email", "admin@example.com"),
            ("alice_email", "alice@example.com"),
            ("password", "password123"),
            ("etl_admin_token", ""),
            ("broker_admin_token", ""),
            ("map_service_token", ""),
            ("admin_token", ""),
            ("alice_token", ""),
            ("alice_id", ""),
            ("alice_display_name", ""),
            ("etl_run_id", ""),
            ("leader", ""),
            ("doomed_username", ""),
            ("doomed_email", ""),
            ("doomed_id", ""),
            ("doomed_token", ""),
            ("now", ""),
            ("saga_id", ""),
            ("saga_polls", "0"),
            ("ghost_saga_id", ""),
            ("ghost_polls", "0"),
        )
    ],
}

target = Path(__file__).with_name("lab-5.postman_collection.json")
target.write_text(json.dumps(collection, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
print(f"wrote {target}")
