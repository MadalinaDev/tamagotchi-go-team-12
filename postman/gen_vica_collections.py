"""Regenerate the Guild and Notification Postman collections (Lab 2).

Every request goes to {{base_url}}, the gateway (default http://localhost:8080;
the shared environment's gateway_base_url overrides it). The collections log
the seed users in through the gateway and send their access tokens as
Authorization: Bearer; internal routes send the service credential from the
service_token variable (one of the *_SERVICE_TOKEN values in .env). Both
collections run against the seeded data and leave it as they found it.

    python3 postman/gen_vica_collections.py
"""

import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))

USERS = {
    "alice": ("00000000-0000-4000-8000-000000000001", "alice@example.com"),
    "bob": ("00000000-0000-4000-8000-000000000002", "bob@example.com"),
    "carol": ("00000000-0000-4000-8000-000000000003", "carol@example.com"),
    "admin": ("00000000-0000-4000-8000-000000000009", "admin@example.com"),
}
FOUNDERS = "00000000-0000-4000-8000-0000000000c1"

PREREQUEST = [
    "if (pm.environment.get('gateway_base_url')) pm.collectionVariables.set('base_url', pm.environment.get('gateway_base_url'));",
    "if (pm.environment.get('service_token')) pm.collectionVariables.set('service_token', pm.environment.get('service_token'));",
]


def req(name, method, path, who="alice", body=None, status=200, save=None, service=False, tests=None, base="{{base_url}}", headers=None):
    hdrs = []
    if service:
        hdrs.append({"key": "Authorization", "value": "Bearer {{service_token}}"})
    elif who:
        hdrs.append({"key": "Authorization", "value": "Bearer {{token_%s}}" % who})
    if method in ("POST", "PUT", "PATCH", "DELETE"):
        hdrs.append({"key": "Idempotency-Key", "value": "{{$guid}}"})
    if body is not None:
        hdrs.append({"key": "Content-Type", "value": "application/json"})
    hdrs += headers or []
    exec_ = [f'pm.test("status {status}", () => pm.response.to.have.status({status}));']
    if status != 204:
        exec_.append('pm.test("request id", () => pm.expect(pm.response.headers.get("X-Request-ID")).to.match(/^[0-9a-f-]{36}$/));')
    if status >= 400:
        exec_.append('pm.test("error body", () => { const b = pm.response.json(); pm.expect(b.code).to.be.a("string"); pm.expect(b.request_id).to.eql(pm.response.headers.get("X-Request-ID")); });')
    for var, expr in (save or {}).items():
        exec_.append(f'if (pm.response.code === {status}) pm.collectionVariables.set("{var}", pm.response.json().{expr});')
    exec_ += tests or []
    raw_path, _, query = path.partition("?")
    url = {"raw": base + path, "host": [base], "path": raw_path.strip("/").split("/")}
    if query:
        url["query"] = [{"key": k, "value": v} for k, v in (p.split("=", 1) for p in query.split("&"))]
    item = {"name": name, "request": {"method": method, "header": hdrs, "url": url},
            "event": [{"listen": "test", "script": {"type": "text/javascript", "exec": exec_}}]}
    if body is not None:
        item["request"]["body"] = {"mode": "raw", "raw": json.dumps(body, indent=2), "options": {"raw": {"language": "json"}}}
    return item


def login(user):
    _, email = USERS[user]
    return req(f"Login {user.capitalize()}", "POST", "/api/v1/auth/login", who=None,
               body={"email": email, "password": "password123"}, save={f"token_{user}": "access_token"})


def folder(name, items):
    return {"name": name, "item": items}


def collection(name, description, variables, folders):
    return {
        "info": {"name": name, "description": description,
                 "schema": "https://schema.getpostman.com/json/collection/v2.1.0/collection.json"},
        "event": [{"listen": "prerequest", "script": {"type": "text/javascript", "exec": PREREQUEST}}],
        "item": folders,
        "variable": [{"key": k, "value": v} for k, v in variables],
    }


COMMON_VARS = [("base_url", "http://localhost:8080"), ("service_token", "")] + \
    [(f"{u}_id", uid) for u, (uid, _) in USERS.items()] + [(f"token_{u}", "") for u in USERS]

G = "{{founders_guild_id}}"
guild = collection(
    "guild-service",
    "Guild service (Vica), Lab 2. All REST requests go through the gateway ({{base_url}}): the collection logs Alice, Bob, "
    "Carol and the admin user in and sends their access tokens; internal requests send {{service_token}} (set it to one of the "
    "*_SERVICE_TOKEN values from .env). Runs against the seeded guild Founders (Alice leader, Bob and Carol members) and leaves it as "
    "seeded, so it can be re-run. The chat WebSocket itself is not proxied: the gateway answers GET .../ws with a direct ws_url to Guild "
    "(see the README); Postman checks the ticket and the negotiation.",
    COMMON_VARS + [("founders_guild_id", FOUNDERS), ("guild_direct_url", "http://localhost:8083"),
                   ("guild_id", ""), ("invite_id", ""), ("message_id", ""), ("ticket", "")],
    [
        folder("Login (gateway)", [login(u) for u in ("alice", "bob", "carol", "admin")]),
        folder("Gateway protection", [
            req("No token -> 401 at the gateway", "GET", f"/api/v1/guilds/{G}", who=None, status=401),
            req("Direct call to Guild with a forged identity -> 401", "GET", f"/api/v1/guilds/{G}", who=None, status=401,
                base="{{guild_direct_url}}", headers=[{"key": "X-Auth-User-Id", "value": "{{alice_id}}"}]),
        ]),
        folder("Seeded guild (Founders)", [
            req("List guilds", "GET", "/api/v1/guilds?limit=20"),
            req("Get Founders", "GET", f"/api/v1/guilds/{G}"),
            req("List members", "GET", f"/api/v1/guilds/{G}/members"),
            req("Rename guild (leader)", "PATCH", f"/api/v1/guilds/{G}", body={"name": "Founders Club"}),
            req("Rename back", "PATCH", f"/api/v1/guilds/{G}", body={"name": "Founders"}),
        ]),
        folder("Create and disband (admin user)", [
            req("Create guild (admin becomes leader)", "POST", "/api/v1/guilds", who="admin", body={"name": "Admin Hall {{$timestamp}}"}, status=201, save={"guild_id": "guild_id"}),
            req("Get new guild", "GET", "/api/v1/guilds/{{guild_id}}", who="admin"),
            req("Invite Carol -> 409 NOT_FRIENDS", "POST", "/api/v1/guilds/{{guild_id}}/invites", who="admin", body={"invitee_id": "{{carol_id}}"}, status=409),
            req("Disband guild (leader)", "DELETE", "/api/v1/guilds/{{guild_id}}", who="admin", status=204),
        ]),
        folder("Invites and roles", [
            req("Leave guild (Bob)", "DELETE", f"/api/v1/guilds/{G}/members/{{{{bob_id}}}}", who="bob", status=204),
            req("Invite Bob (friendship checked in User Management)", "POST", f"/api/v1/guilds/{G}/invites", body={"invitee_id": "{{bob_id}}"}, status=201, save={"invite_id": "invite_id"}),
            req("List my invites (Bob)", "GET", "/api/v1/guild-invites", who="bob"),
            req("Decline invite (Bob)", "POST", "/api/v1/guild-invites/{{invite_id}}/decline", who="bob", body={}),
            req("Invite Bob to cancel it", "POST", f"/api/v1/guilds/{G}/invites", body={"invitee_id": "{{bob_id}}"}, status=201, save={"invite_id": "invite_id"}),
            req("Cancel invite (inviter or leader)", "DELETE", "/api/v1/guild-invites/{{invite_id}}", status=204),
            req("Invite Bob again", "POST", f"/api/v1/guilds/{G}/invites", body={"invitee_id": "{{bob_id}}"}, status=201, save={"invite_id": "invite_id"}),
            req("Accept invite (Bob)", "POST", "/api/v1/guild-invites/{{invite_id}}/accept", who="bob", body={}),
            req("Change role: Bob -> officer (leader)", "PATCH", f"/api/v1/guilds/{G}/members/{{{{bob_id}}}}", body={"role": "officer"}),
            req("Change role: Bob -> member (leader)", "PATCH", f"/api/v1/guilds/{G}/members/{{{{bob_id}}}}", body={"role": "member"}),
            req("Invite Carol -> 409 ALREADY_MEMBER", "POST", f"/api/v1/guilds/{G}/invites", body={"invitee_id": "{{carol_id}}"}, status=409),
            req("Invite unknown user -> 404 (User Management)", "POST", f"/api/v1/guilds/{G}/invites", body={"invitee_id": "00000000-0000-4000-8000-0000000000ff"}, status=404),
            req("Remove member Bob (leader)", "DELETE", f"/api/v1/guilds/{G}/members/{{{{bob_id}}}}", status=204),
            req("Invite Bob back", "POST", f"/api/v1/guilds/{G}/invites", body={"invitee_id": "{{bob_id}}"}, status=201, save={"invite_id": "invite_id"}),
            req("Accept (Bob is back as in the seed)", "POST", "/api/v1/guild-invites/{{invite_id}}/accept", who="bob", body={}),
        ]),
        folder("Messages (REST history and send)", [
            req("Send message (Bob)", "POST", f"/api/v1/guilds/{G}/messages", who="bob", body={"client_message_id": "{{$guid}}", "text": "Hello, Founders!"}, status=201, save={"message_id": "message_id"}),
            req("Send message (Alice)", "POST", f"/api/v1/guilds/{G}/messages", body={"client_message_id": "{{$guid}}", "text": "Welcome back, Bob!"}, status=201),
            req("List messages", "GET", f"/api/v1/guilds/{G}/messages?limit=50"),
            req("List messages after a message (reconnect)", "GET", f"/api/v1/guilds/{G}/messages?after_message_id={{{{message_id}}}}"),
        ]),
        folder("WebSocket chat (ticket and negotiation)", [
            req("Get chat ticket (member)", "POST", f"/api/v1/guilds/{G}/chat-tickets", body={}, status=201, save={"ticket": "ticket"},
                tests=['pm.test("30 s single-use ticket", () => { const b = pm.response.json(); pm.expect(b.ticket).to.have.length(43); pm.expect(new Date(b.expires_at) > new Date()).to.be.true; });']),
            req("Negotiate socket -> direct Guild ws_url", "GET", f"/api/v1/guilds/{G}/ws?ticket={{{{ticket}}}}",
                tests=['pm.test("direct ws_url to Guild", () => pm.expect(pm.response.json().ws_url).to.match(/^wss?:\\/\\/.+\\/api\\/v1\\/guilds\\/.+\\/ws\\?ticket=.+/));']),
            req("Ticket for a non-member -> 403", "POST", f"/api/v1/guilds/{G}/chat-tickets", who="admin", body={}, status=403),
        ]),
        folder("Internal (service token)", [
            req("Internal: get guild", "GET", f"/internal/v1/guilds/{G}", service=True),
            req("Internal: list all members", "GET", f"/internal/v1/guilds/{G}/members", service=True,
                tests=['pm.test("three seeded members", () => pm.expect(pm.response.json().members).to.have.length(3));']),
            req("Internal: get member", "GET", f"/internal/v1/guilds/{G}/members/{{{{bob_id}}}}", service=True),
            req("Internal without service token -> 401", "GET", f"/internal/v1/guilds/{G}", who="alice", status=401),
        ]),
    ])


def event(type_, producer, payload, event_id="{{$guid}}", correlation="{{$guid}}"):
    return {"event_id": event_id, "type": type_, "version": 1, "producer": producer,
            "occurred_at": "2026-10-09T12:00:00Z", "correlation_id": correlation, "payload": payload}


notification = collection(
    "notification-service",
    "Notification service (Vica), Lab 2. All requests go through the gateway ({{base_url}}): the collection logs Alice and Bob in "
    "and sends their access tokens; the temporary event intake POST /internal/v1/dev/events sends {{service_token}} (set it to one "
    "of the *_SERVICE_TOKEN values from .env). RaidStarted is resolved through the real Guild via the gateway. With "
    "SEED_ON_START=true Bob starts with two unread inbox entries. Re-runnable.",
    COMMON_VARS + [("founders_guild_id", FOUNDERS), ("device_id", ""), ("notification_id", ""), ("event_id", "")],
    [
        folder("Login (gateway)", [login(u) for u in ("alice", "bob")]),
        folder("Seeded data", [
            req("Inbox of Bob (seeded friend request and battle challenge)", "GET", "/api/v1/notifications?unread=true", who="bob",
                tests=['pm.test("seeded entries", () => { const t = pm.response.json().items.map(i => i.type); pm.expect(t).to.include.members(["FriendRequested", "BattleRequested"]); });']),
            req("No token -> 401 at the gateway", "GET", "/api/v1/notifications", who=None, status=401),
        ]),
        folder("Devices", [
            req("Register device (Alice)", "POST", "/api/v1/notification-devices", body={"firebase_token": "demo-token-alice-{{$timestamp}}", "platform": "web"}, status=201, save={"device_id": "device_id"}),
        ]),
        folder("Preferences", [
            req("Get preferences", "GET", "/api/v1/notification-preferences"),
            req("Put preferences", "PUT", "/api/v1/notification-preferences", body={"push_enabled": True, "disabled_types": ["UsersNearby"]}),
        ]),
        folder("Dev events (service token)", [
            {**req("Dev event: GuildInvited -> Alice", "POST", "/internal/v1/dev/events", service=True,
                   body=event("GuildInvited", "guild", {"invite_id": "{{$guid}}", "guild_id": "{{founders_guild_id}}", "inviter_id": "{{bob_id}}", "invitee_id": "{{alice_id}}"}, event_id="{{event_id}}")),
             "event": [
                 {"listen": "prerequest", "script": {"type": "text/javascript", "exec": ['pm.collectionVariables.set("event_id", pm.variables.replaceIn("{{$guid}}"));']}},
                 {"listen": "test", "script": {"type": "text/javascript", "exec": ['pm.test("status 200", () => pm.response.to.have.status(200));', 'pm.test("one entry", () => pm.expect(pm.response.json().created_notifications).to.eql(1));']}},
             ]},
            req("Dev event: same event again (deduplicated)", "POST", "/internal/v1/dev/events", service=True,
                body=event("GuildInvited", "guild", {"invite_id": "{{$guid}}", "guild_id": "{{founders_guild_id}}", "inviter_id": "{{bob_id}}", "invitee_id": "{{alice_id}}"}, event_id="{{event_id}}"),
                tests=['pm.test("nothing new", () => pm.expect(pm.response.json().created_notifications).to.eql(0));']),
            req("Dev event: RaidStarted -> Founders members (Guild via gateway)", "POST", "/internal/v1/dev/events", service=True,
                body=event("RaidStarted", "monster-raid", {"raid_id": "{{$guid}}", "guild_id": "{{founders_guild_id}}", "ends_at": "2026-10-09T13:00:00Z"}),
                tests=['pm.test("three members", () => pm.expect(pm.response.json().recipient_ids).to.have.length(3));']),
            req("Dev event without service token -> 401", "POST", "/internal/v1/dev/events", who="alice", body={}, status=401),
        ]),
        folder("Inbox", [
            req("List notifications", "GET", "/api/v1/notifications?limit=20", save={"notification_id": "items[0].notification_id"}),
            req("List unread notifications", "GET", "/api/v1/notifications?unread=true"),
            req("Mark notification read", "PUT", "/api/v1/notifications/{{notification_id}}/read", body={}),
        ]),
        folder("Cleanup", [
            req("Delete device", "DELETE", "/api/v1/notification-devices/{{device_id}}", status=204),
        ]),
    ])

for name, col in (("guild-service", guild), ("notification-service", notification)):
    with open(os.path.join(HERE, f"{name}.postman_collection.json"), "w") as f:
        json.dump(col, f, indent=2, ensure_ascii=False)
        f.write("\n")
print("written")
