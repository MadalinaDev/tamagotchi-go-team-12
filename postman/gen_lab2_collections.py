"""Regenerate Battle/Tamagotchi Lab 2 Postman collections (gateway + JWT).

All requests go to {{base_url}} (default http://localhost:8080, the Gateway).
Collection-level scripts attach Bearer tokens per [Alice]/[Bob] prefix and a
fresh Idempotency-Key to mutating requests. Rerunnable against seeded data.
"""

import json

ALICE_ID = "00000000-0000-4000-8000-000000000001"
BOB_ID = "00000000-0000-4000-8000-000000000002"
EMBER = "00000000-0000-4000-8000-0000000000b1"
RIPPLE = "00000000-0000-4000-8000-0000000000b2"

PREREQUEST = """if (pm.environment.get('gateway_base_url')) pm.collectionVariables.set('base_url', pm.environment.get('gateway_base_url'));
function uuidv4() { return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, function (c) { var r = Math.random() * 16 | 0; return (c === 'x' ? r : (r & 0x3 | 0x8)).toString(16); }); }
pm.request.headers.upsert({key: 'Content-Type', value: 'application/json'});
var publicRequests = ['Gateway health', 'Login Alice', 'Login Bob', 'Missing identity'];
if (publicRequests.indexOf(pm.info.requestName) === -1) {
    var m = pm.info.requestName.match(/^\\[(Alice|Bob)\\]/);
    var tokenKey = (m && m[1] === 'Bob') ? 'token_bob' : 'token_alice';
    pm.request.headers.upsert({key: 'Authorization', value: 'Bearer ' + pm.collectionVariables.get(tokenKey)});
}
var mutating = ['Create', 'Update', 'Decline', 'Accept', 'Cancel', 'Select', 'Rename'];
if (mutating.some(function (k) { return pm.info.requestName.indexOf(k) !== -1; })) {
    pm.request.headers.upsert({key: 'Idempotency-Key', value: uuidv4()});
}
if (pm.info.requestName === '[Alice] Select') {
    pm.request.body.update({mode: 'raw', raw: JSON.stringify({primary_pet_id: '00000000-0000-4000-8000-0000000000b1', secondary_pet_id: '00000000-0000-4000-8000-0000000000b2', expected_version: Number(pm.collectionVariables.get('sel_version'))}), options: {raw: {language: 'json'}}});
}
if (pm.info.requestName === '[Alice] Rename') {
    pm.request.body.update({mode: 'raw', raw: JSON.stringify({name: 'Ember', expected_version: Number(pm.collectionVariables.get('pet_version'))}), options: {raw: {language: 'json'}}});
}
"""


def req(name, method, path, body=None):
    r = {"name": name, "request": {"method": method, "url": "{{base_url}}" + path}}
    if body is not None:
        raw = json.dumps(body)
        if isinstance(body, dict) and any(
            isinstance(v, str) and v.startswith("{{") for v in body.values()
        ):
            # Numeric template filled in the prerequest script; keep a valid placeholder.
            r["request"]["body"] = {"mode": "raw", "raw": "{}"}
        else:
            r["request"]["body"] = {"mode": "raw", "raw": raw}
    return r


SEED_VARS = [
    {"key": "base_url", "value": "http://localhost:8080"},
    {"key": "pet_ember", "value": EMBER},
    {"key": "pet_ripple", "value": RIPPLE},
]


def collection(name, items, expectations, extras=""):
    return {
        "info": {
            "name": name,
            "schema": "https://schema.getpostman.com/json/collection/v2.1.0/collection.json",
        },
        "variable": [dict(v) for v in SEED_VARS],
        "event": [
            {
                "listen": "prerequest",
                "script": {"type": "text/javascript", "exec": PREREQUEST.splitlines()},
            },
            {
                "listen": "test",
                "script": {
                    "type": "text/javascript",
                    "exec": (
                        "var expected = %s;\n"
                        "pm.test(pm.info.requestName + ' status', function () { pm.response.to.have.status(expected[pm.info.requestName]); });\n"
                        "if (pm.response.code !== 204) { var b = pm.response.json();\n"
                        "pm.test('Request ID returned', function () { pm.expect(pm.response.headers.get('X-Request-ID')).to.match(/^[a-f0-9-]{36}$/); });\n"
                        "if (pm.response.code >= 400) { pm.test('Structured error', function () { pm.expect(b.request_id).to.eql(pm.response.headers.get('X-Request-ID')); pm.expect(b.code).to.be.a('string'); }); }\n"
                        "%s}" % (json.dumps(expectations), extras)
                    ).splitlines(),
                },
            },
        ],
        "item": items,
    }


battle_items = [
    req("Gateway health", "GET", "/health"),
    req(
        "Login Alice",
        "POST",
        "/api/v1/auth/login",
        {"email": "alice@example.com", "password": "password123"},
    ),
    req(
        "Login Bob",
        "POST",
        "/api/v1/auth/login",
        {"email": "bob@example.com", "password": "password123"},
    ),
    req("[Alice] Rules", "GET", "/api/v1/battle-rules"),
    req(
        "[Alice] Create",
        "POST",
        "/api/v1/battles",
        {
            "opponent_id": BOB_ID,
            "loadout": {
                "primary_pet_id": EMBER,
                "secondary_pet_id": RIPPLE,
                "boost": "none",
            },
        },
    ),
    req("[Alice] Get", "GET", "/api/v1/battles/{{battle_id}}"),
    req("[Alice] List", "GET", "/api/v1/battles"),
    req("[Alice] Invalid ID", "GET", "/api/v1/battles/not-a-uuid"),
    req("Missing identity", "GET", "/api/v1/battles"),
    req("[Bob] Decline", "POST", "/api/v1/battles/{{battle_id}}/decline", {}),
    req(
        "[Alice] Update declined",
        "PATCH",
        "/api/v1/battles/{{battle_id}}",
        {"loadout": {"primary_pet_id": EMBER, "secondary_pet_id": RIPPLE, "boost": "guard"}, "expected_version": 1},
    ),
    req("[Alice] Cancel declined", "POST", "/api/v1/battles/{{battle_id}}/cancel", {}),
]

battle_expected = {
    "Gateway health": 200,
    "Login Alice": 200,
    "Login Bob": 200,
    "[Alice] Rules": 200,
    "[Alice] Create": 201,
    "[Alice] Get": 200,
    "[Alice] List": 200,
    "[Alice] Invalid ID": 422,
    "Missing identity": 401,
    "[Bob] Decline": 200,
    "[Alice] Update declined": 409,
    "[Alice] Cancel declined": 409,
}

battle_extras = (
    "if (pm.info.requestName === 'Login Alice' && pm.response.code === 200) { pm.collectionVariables.set('token_alice', b.access_token); }\n"
    "if (pm.info.requestName === 'Login Bob' && pm.response.code === 200) { pm.collectionVariables.set('token_bob', b.access_token); }\n"
    "if (pm.info.requestName === '[Alice] Create' && pm.response.code === 201) { pm.collectionVariables.set('battle_id', b.battle_id); pm.test('Pending battle', function () { pm.expect(b.state).to.eql('pending'); }); }\n"
    "if (pm.info.requestName === '[Bob] Decline' && pm.response.code === 200) { pm.test('Declined', function () { pm.expect(b.state).to.eql('declined'); }); }\n"
)

tama_items = [
    req("Gateway health", "GET", "/health"),
    req(
        "Login Alice",
        "POST",
        "/api/v1/auth/login",
        {"email": "alice@example.com", "password": "password123"},
    ),
    req(
        "Login Bob",
        "POST",
        "/api/v1/auth/login",
        {"email": "bob@example.com", "password": "password123"},
    ),
    req("[Alice] Types", "GET", "/api/v1/tamagotchi-types"),
    req("[Alice] List mine", "GET", "/api/v1/tamagotchis"),
    req("[Alice] Get Ember", "GET", "/api/v1/tamagotchis/{{pet_ember}}"),
    req("[Bob] Foreign pet redacted", "GET", "/api/v1/tamagotchis/{{pet_ember}}"),
    req("[Alice] Get selection", "GET", "/api/v1/tamagotchi-selections/me"),
    req(
        "[Alice] Select",
        "PUT",
        "/api/v1/tamagotchi-selections/me",
        {
            "primary_pet_id": EMBER,
            "secondary_pet_id": RIPPLE,
            "expected_version": "{{sel_version}}",
        },
    ),
    req(
        "[Alice] Rename",
        "PATCH",
        "/api/v1/tamagotchis/{{pet_ember}}",
        {"name": "Ember", "expected_version": "{{pet_version}}"},
    ),
    req("[Alice] Invalid ID", "GET", "/api/v1/tamagotchis/not-a-uuid"),
    req("Missing identity", "GET", "/api/v1/tamagotchis"),
]

tama_expected = {
    "Gateway health": 200,
    "Login Alice": 200,
    "Login Bob": 200,
    "[Alice] Types": 200,
    "[Alice] List mine": 200,
    "[Alice] Get Ember": 200,
    "[Bob] Foreign pet redacted": 200,
    "[Alice] Get selection": 200,
    "[Alice] Select": 200,
    "[Alice] Rename": 200,
    "[Alice] Invalid ID": 422,
    "Missing identity": 401,
}

tama_extras = (
    "if (pm.info.requestName === 'Login Alice' && pm.response.code === 200) { pm.collectionVariables.set('token_alice', b.access_token); }\n"
    "if (pm.info.requestName === 'Login Bob' && pm.response.code === 200) { pm.collectionVariables.set('token_bob', b.access_token); }\n"
    "if (pm.info.requestName === '[Alice] List mine' && pm.response.code === 200) { pm.test('Seed pets present', function () { pm.expect(b.items.length).to.be.at.least(2); }); }\n"
    "if (pm.info.requestName === '[Alice] Get Ember' && pm.response.code === 200) { pm.collectionVariables.set('pet_version', b.version); pm.test('Owner sees care stats', function () { pm.expect(b.care_stats).to.be.an('object'); }); }\n"
    "if (pm.info.requestName === '[Bob] Foreign pet redacted' && pm.response.code === 200) { pm.test('Public view redacted', function () { pm.expect(b.care_stats).to.be.undefined; pm.expect(b).to.not.have.property('definition_version'); }); }\n"
    "if (pm.info.requestName === '[Alice] Get selection' && pm.response.code === 200) { pm.collectionVariables.set('sel_version', b.version); }\n"
)

with open("postman/battle-service.postman_collection.json", "w") as f:
    json.dump(
        collection(
            "Battle service (Lab 2, via Gateway)",
            battle_items,
            battle_expected,
            battle_extras,
        ),
        f,
        indent=2,
    )
    f.write("\n")

with open("postman/tamagotchi-service.postman_collection.json", "w") as f:
    json.dump(
        collection(
            "Tamagotchi service (Lab 2, via Gateway)",
            tama_items,
            tama_expected,
            tama_extras,
        ),
        f,
        indent=2,
    )
    f.write("\n")

print("collections regenerated")
