"""Adds the Lab 5 components to the system map (docs/diagrams), in place.

    python docs/diagrams/lab5_system_map.py

The Lab 4 map (system-map.svg, system-map.html and one SVG per view) gains:

* the sharded cache (cache-1..3), used by the API Gateway and the Message Broker;
* the database router `postgres` (HAProxy) in front of the Patroni cluster (pg-1..3) and etcd;
* the ETL service, which reads every database from a replica, and the data warehouse, which
  Grafana reads;
* two views, "Cache" and "Replication and warehouse", details for every new container, the
  0.6.0 images and the container table.

It refuses to run twice (the map already has a cache node).
"""

from __future__ import annotations

import json
import re
from pathlib import Path

HERE = Path(__file__).parent
SVG_GROW = 200  # the static SVG: new band below the services, the legend moves down
HTML_GROW = 190

CSS = """
/* Lab 5 */
:root { --cache: #0e7490; --repl: #4d7c0f; }
@media (prefers-color-scheme: dark) { :root:not([data-theme="light"]) { --cache: #67e8f9; --repl: #a3e635; } }
:root[data-theme="dark"] { --cache: #67e8f9; --repl: #a3e635; }
.c-cache { stroke: var(--cache); } .c-repl { stroke: var(--repl); }
.m-cache { fill: var(--cache); } .m-repl { fill: var(--repl); }
.elabel.c-cache { fill: var(--cache); stroke: var(--surface); }
.elabel.c-repl { fill: var(--repl); stroke: var(--surface); }
#map[data-view="cache"] .l-cache, #map[data-view="repl"] .l-repl { display: inline; }
#map[data-view="cache"] .node:not(.v-cache), #map[data-view="repl"] .node:not(.v-repl) { opacity: .28; }
"""

MARKERS = "".join(
    f'<marker id="a-{layer}" viewBox="0 0 10 10" refX="9.5" refY="5" markerWidth="9" '
    f'markerHeight="9" markerUnits="userSpaceOnUse" orient="auto-start-reverse">'
    f'<path class="m-{layer}" d="M0,0.8 L10,5 L0,9.2 z"/></marker>'
    for layer in ("cache", "repl")
)

FRAME = (
    '<rect class="frame" x="252" y="682" width="462" height="248" rx="12"/>'
    '<text class="frame-t" x="706" y="922" text-anchor="end">one name, postgres: a Patroni cluster</text>'
)


def box(node_id, classes, title, x, y, w, h, lines):
    texts = [f'<text class="t" x="{x + 12}" y="{y + 22}">{lines[0]}</text>']
    texts += [
        f'<text class="s" x="{x + 12}" y="{y + 40 + 15 * index}">{line}</text>'
        for index, line in enumerate(lines[1:])
    ]
    return (
        f'<g class="node {classes}" id="n-{node_id}" data-id="{node_id}" tabindex="0" role="button" '
        f'aria-label="{title}"><title>{title}</title>'
        f'<rect class="box" x="{x}" y="{y}" width="{w}" height="{h}" rx="7"/>{"".join(texts)}</g>'
    )


def cylinder(node_id, classes, title, cx, top, rx, body, lines):
    x = cx - rx
    return (
        f'<g class="node {classes}" id="n-{node_id}" data-id="{node_id}" tabindex="0" role="button" '
        f'aria-label="{title}"><title>{title}</title>'
        f'<path class="box" d="M{x},{top} a{rx},8 0 0 0 {2 * rx},0 v{body} a{rx},8 0 0 1 -{2 * rx},0 z"/>'
        f'<ellipse class="box cap" cx="{cx}" cy="{top}" rx="{rx}" ry="8"/>'
        f'<text class="t" x="{cx}" y="{top + 26}" text-anchor="middle">{lines[0]}</text>'
        f'<text class="s" x="{cx}" y="{top + 44}" text-anchor="middle">{lines[1]}</text></g>'
    )


SERVICES = "guild notification map user-management package-registry monster-raid tamagotchi battle"

NODES = "".join(
    [
        cylinder("cache", "k-data v-cache v-mon", "Cache: cache-1, cache-2, cache-3", 600, 566, 110,
                 46, ["cache-1 · 2 · 3", "Redis · consistent hashing"]),
        box("postgres", "k-platform v-mon v-repl", "postgres: the database router (HAProxy)", 470,
            690, 220, 70, ["postgres (router)", "HAProxy · 5432 leader", "5433 replicas · 7000 stats"]),
        cylinder("cluster", "k-data v-mon v-repl", "Database cluster: pg-1, pg-2, pg-3 (Patroni)", 580,
                 820, 110, 62, ["pg-1 · pg-2 · pg-3", "Patroni · leader + 2 replicas"]),
        box("etcd", "k-plain v-repl", "etcd", 276, 818, 160, 46, ["etcd", "leader lock"]),
        box("etl", "k-platform v-mon v-repl", "ETL service", 800, 820, 200, 60,
            ["ETL service", "Python · :8091 · 60 s"]),
        cylinder("warehouse", "k-data v-mon v-repl", "Data warehouse", 1180, 822, 100, 58,
                 ["Data warehouse", "Postgres · star schema"]),
    ]
)


def edge(layers, nodes, title, d, color, dashed=False):
    dash = ' stroke-dasharray="6 4"' if dashed else ""
    return (
        f'<g class="edge {layers}" data-nodes="{nodes}"><title>{title}</title>'
        f'<path class="hitarea" d="{d}"/>'
        f'<path class="ln c-{color}" d="{d}"{dash} marker-end="url(#a-{color})"/></g>'
    )


EDGES = "".join(
    [
        edge("l-cache", "gateway cache",
             "API Gateway → cache · cached GET answers (X-Cache) and verified tokens, on the node "
             "the hash ring picks", "M436,382 H462 V596 H490", "cache"),
        edge("l-cache", "broker cache",
             "Message Broker → cache · user lookups between services; gen:&lt;service&gt; makes "
             "cached answers stale; auth:revoked:&lt;user&gt; locks out an account being deleted",
             "M700,408 V560", "cache"),
        edge("l-repl l-data", "postgres cluster",
             "postgres router → pg-1, pg-2, pg-3 · 5432 to the leader, 5433 to a replica, from each "
             "node's Patroni REST API (/primary, /replica), checked every second",
             "M580,760 V812", "repl"),
        edge("l-repl", "cluster etcd",
             "pg-1, pg-2, pg-3 → etcd · the leader renews its lock every 2 s; when it expires "
             "(20 s), the synchronous replica takes it", "M470,841 H436", "repl"),
        edge("l-repl l-data", "etl postgres",
             "ETL service → postgres:5433 · every team database, from a replica, as the "
             "read-only etl_reader (the leader only when no replica answers)",
             "M800,836 H740 V752 H690", "repl"),
        edge("l-repl l-data", "etl warehouse",
             "ETL service → warehouse · loads the star schema in one transaction, every 60 s",
             "M1000,850 H1080", "repl"),
        edge("l-mon l-repl", "grafana warehouse",
             "Grafana → warehouse · the Lab 5 dashboard's SQL panels, as the read-only dw_reader",
             "M40,548 H20 V954 H1180 V888", "mon"),
        edge("l-mon", "prometheus cluster etl",
             "Prometheus → pg-1, pg-2, pg-3 · Patroni's /metrics (role, timeline, replication lag); "
             "it also scrapes the ETL service", "M276,566 H246 V876 H470", "mon"),
    ]
)

LABELS = "".join(
    [
        '<text class="elabel l-cache c-cache" data-nodes="gateway cache" x="456" y="470" '
        'text-anchor="end">answers, tokens</text>',
        '<text class="elabel l-cache c-cache" data-nodes="broker cache" x="694" y="532" '
        'text-anchor="end">lookups · gen:*</text>',
        '<text class="elabel l-repl c-repl" data-nodes="postgres cluster" x="590" y="792">'
        "5432 · 5433</text>",
        '<text class="elabel l-repl c-repl" data-nodes="etl postgres" x="746" y="806">'
        "5433, read-only</text>",
        '<text class="elabel l-repl c-repl" data-nodes="etl warehouse" x="1040" y="842" '
        'text-anchor="middle">load</text>',
        '<text class="elabel l-repl c-repl" data-nodes="grafana warehouse" x="640" y="948" '
        'text-anchor="middle">SQL panels</text>',
    ]
)


def insert_edges(text: str) -> str:
    """Appends the new edges to the end of <g class="edges"> and the labels to the labels group."""
    start = text.index('<g class="edges">')
    depth, index = 0, start
    for match in re.finditer(r"<g\b|</g>", text[start:]):
        depth += 1 if match.group(0) == "<g" else -1
        if depth == 0:
            index = start + match.start()
            break
    text = text[:index] + EDGES + text[index:]
    labels = text.rfind('<text class="elabel')
    end = text.index("</g>", labels)
    return text[:end] + LABELS + text[end:]


def grow(text: str, old_height: int, new_height: int) -> str:
    text = text.replace(f'viewBox="0 0 1340 {old_height}"', f'viewBox="0 0 1340 {new_height}"', 1)
    text = text.replace(f'height="{old_height}"', f'height="{new_height}"', 1)
    return text.replace(
        f'<rect class="bg" x="0" y="0" width="1340" height="{old_height}"/>',
        f'<rect class="bg" x="0" y="0" width="1340" height="{new_height}"/>', 1
    )


def patch_svg(text: str) -> str:
    text = re.sub(r'(<style>.*?)(</style>)', lambda m: m.group(1) + CSS + m.group(2), text,
                  count=1, flags=re.S)
    text = text.replace("</defs>", MARKERS + "</defs>", 1)
    text = common(text)
    text = grow(text, 876, 876 + SVG_GROW + 10)
    row = 846 + SVG_GROW + 22  # a second legend row, under the moved first one
    legend_extra = (
        f'<line x1="40" y1="{row}" x2="74" y2="{row}" class="ln c-cache" marker-end="url(#a-cache)"/>'
        f'<text class="s legend-t" x="92" y="{row + 4}">Cache (Lab 5)</text>'
        f'<line x1="210" y1="{row}" x2="244" y2="{row}" class="ln c-repl" marker-end="url(#a-repl)"/>'
        f'<text class="s legend-t" x="262" y="{row + 4}">Replication, ETL and warehouse (Lab 5)</text>'
    )
    text = text.replace('<g class="legend">', f'<g class="legend"><g transform="translate(0,{SVG_GROW})">', 1)
    # The legend's last </g> closes the moved first row; the second row follows it.
    tail = text.rindex("</g>")
    return text[:tail] + "</g>" + legend_extra + text[tail:]


def common(text: str) -> str:
    text = re.sub(r'<g class="node k-data v-mon" id="n-postgres".*?</g>', "", text, count=1, flags=re.S)
    text = text.replace(
        '<g class="edge l-data" data-nodes="postgres', '<g class="edge l-data l-repl" data-nodes="postgres', 1
    ).replace(
        "Every service → PostgreSQL · its own database",
        "Every service → postgres (the router) · its own database, on the current leader", 1
    )
    for service in SERVICES.split():
        text = re.sub(rf'(<g class="node k-service [^"]*)(" id="n-{service}")', r"\1 v-repl\2", text, count=1)
    for node_id, extra in (("gateway", "v-cache"), ("broker", "v-cache"), ("grafana", "v-repl")):
        text = re.sub(rf'(<g class="node [^"]*)(" id="n-{node_id}")', rf"\1 {extra}\2", text, count=1)
    text = text.replace('<g class="edges">', FRAME + '<g class="edges">', 1)
    text = text.replace('<g class="nodes">', '<g class="nodes">' + NODES, 1)
    return insert_edges(text)


VIEWS = {
    "all": ("system-map.svg", "Tamagotchi Go system map: every container and every kind of traffic"),
    "req": ("system-map-request.svg", "A user request: client, API Gateway, the broker's queue of the "
            "service, the least-loaded replica"),
    "grpc": ("system-map-grpc.svg", "gRPC calls between services, all through the message broker"),
    "topic": ("system-map-events.svg", "Topic events from publishers to subscribers, stored by the "
              "broker before delivery"),
    "disc": ("system-map-discovery.svg", "Service Discovery: registration, heartbeats, status polls, "
             "evictions and alerts"),
    "mon": ("system-map-monitoring.svg", "Data and monitoring: the database cluster, the broker's "
            "SQLite store, the warehouse, Prometheus, Loki, Alloy and Grafana"),
    "cache": ("system-map-cache.svg", "The sharded cache: the API Gateway and the Message Broker place "
              "every key on one of three Redis nodes by consistent hashing"),
    "repl": ("system-map-replication.svg", "Replication and the warehouse: the router postgres, the "
             "Patroni cluster and etcd, the ETL service and the data warehouse"),
}


def escape(value: str) -> str:
    return value.replace("&", "&amp;").replace("'", "&#x27;").replace('"', "&quot;")


def write_views(all_view: str) -> None:
    title = VIEWS["all"][1]
    for view, (name, label) in VIEWS.items():
        text = all_view.replace('data-view="all"', f'data-view="{view}"', 1)
        text = text.replace(f'aria-label="{title}"', f'aria-label="{escape(label)}"', 1)
        text = text.replace(f"<title>{title}</title>", f"<title>{escape(label)}</title>", 1)
        (HERE / name).write_text(text, encoding="utf-8")


DETAILS_NEW = {
    "cache": {
        "title": "Cache (Redis × 3)",
        "rows": [["Containers", "cache-1, cache-2, cache-3"], ["Image", "redis:7.4.1-alpine"],
                 ["Memory", "64 MB each, least recently used evicted, no persistence"],
                 ["Owner", "Mădălina"]],
        "text": "Three independent Redis nodes, sharded by consistent hashing in the gateway and the "
                "broker (MD5 on a 64-bit ring, 160 virtual nodes per node), not by Redis Cluster. A "
                "node that fails is skipped for 10 s and its keys go to the next node on the ring; "
                "every other key stays where it is. The cache never fails a request: an error is a miss.",
        "lists": [["Used by", [
            "API Gateway: cached GET answers (60–300 s, per user or shared) and verified tokens",
            "Message Broker: user lookups between services; gen:<service> counters that make cached "
            "answers stale; auth:revoked:<user> while an account is being deleted"]]],
    },
    "postgres": {
        "title": "postgres (the database router)",
        "rows": [["Container", "postgres (1)"], ["Image", "haproxy:3.0.5-alpine"],
                 ["Ports", "5432 leader · 5433 replicas · 7000 stats · 8008 Patroni API"],
                 ["Owner", "Mădălina"]],
        "text": "It keeps the old hostname, so no service changed its configuration. Once a second it "
                "asks every node's Patroni REST API which role it has: 5432 goes to the leader (reads "
                "and writes), 5433 to the replicas (read-only). When a node stops being the leader, "
                "its client connections are cut and the services reconnect to the new one.",
        "lists": [["Called by", ["All 8 services: their own database, on the leader",
                                 "ETL service: every database, on a replica"]],
                  ["Talks to", ["pg-1, pg-2, pg-3"]]],
    },
    "cluster": {
        "title": "Database cluster (Patroni)",
        "rows": [["Containers", "pg-1, pg-2, pg-3"],
                 ["Image", "madalina060504/tamagotchi-postgres-ha:0.6.0"],
                 ["Inside", "Postgres 16 + PostGIS 3 + Patroni 4"],
                 ["Storage", "pg1-data, pg2-data, pg3-data volumes"], ["Owner", "Mădălina"]],
        "text": "One leader and two streaming replicas, one of them synchronous: a commit is "
                "acknowledged once a replica has it, so a failover loses nothing. When the leader "
                "crashes, its lock in etcd expires (20 s) and the synchronous replica is promoted; a "
                "leader that is stopped hands over in 1–2 s. The old leader comes back as a replica "
                "(pg_rewind). Every service still has its own database and user.",
        "lists": [["Talks to", ["etcd: the leader lock", "Each other: streaming replication (WAL)"]],
                  ["Called by", ["postgres router: /primary and /replica checks, then connections",
                                 "Prometheus: Patroni's /metrics"]]],
    },
    "etcd": {
        "title": "etcd",
        "rows": [["Container", "etcd (1)"], ["Image", "quay.io/coreos/etcd:v3.5.17"]],
        "text": "Patroni's configuration store: who leads the cluster (a lock with a 20 s TTL, renewed "
                "every 2 s) and the cluster's settings.",
        "lists": [["Called by", ["pg-1, pg-2, pg-3 (Patroni)"]]],
    },
    "etl": {
        "title": "ETL service",
        "rows": [["Container", "etl-service (1)"],
                 ["Image", "madalina060504/tamagotchi-etl-service:0.6.0"],
                 ["Language", "Python 3.12"], ["Ports", "8091 (published for the demo)"],
                 ["Owner", "Mădălina"]],
        "text": "Every 60 s it reads every team database from a replica (postgres:5433, as the "
                "read-only etl_reader), builds the star schema and loads the warehouse in one "
                "transaction. An extract that fails keeps its tables' previous rows; every run is "
                "recorded in dw.etl_runs.",
        "lists": [["Talks to", ["postgres router: port 5433 (5432 only when no replica answers)",
                                "Data warehouse: the load"]],
                  ["Endpoints", ["GET /status, /metrics, /v1/runs, /v1/warehouse",
                                 "POST /v1/runs and GET /v1/reports/{name} (operator token)"]],
                  ["Read by", ["Prometheus: /metrics"]]],
    },
    "warehouse": {
        "title": "Data warehouse",
        "rows": [["Container", "warehouse (1)"], ["Image", "postgres:16.14-alpine"],
                 ["Ports", "5434 (published for the demo)"], ["Storage", "warehouse-data volume"],
                 ["Owner", "Mădălina"]],
        "text": "A star schema in a Postgres of its own: dimensions (date, user, package, pet, guild), "
                "facts (battles, raids and their participants, wallet entries, friendships, "
                "notifications, guild membership and messages, registrations, Map snapshots) and "
                "analytics views. No emails, message texts, device tokens or coordinates.",
        "lists": [["Loaded by", ["ETL service"]],
                  ["Read by", ["Grafana: the Lab 5 dashboard, as dw_reader",
                               "ETL service: GET /v1/reports"]]],
    },
}

CAPTIONS_NEW = {
    "cache": "The sharded cache: the gateway caches common GETs and verified tokens, the broker "
             "caches user lookups between services. Both place every key on one of three Redis nodes "
             "by consistent hashing, so adding or losing a node moves only that node's share of keys.",
    "repl": "Replication and the warehouse: the services still connect to postgres, now a router "
            "that sends them to the Patroni cluster's leader. Two replicas stream every change, and "
            "etcd holds the leader lock. The ETL service reads every database from a replica and "
            "loads the data warehouse, which Grafana reads.",
}

TABLE_ROWS = [
    ("etcd", "1", "quay.io/coreos/etcd:v3.5.17", "2379 (internal)", "Mădălina"),
    ("pg-1, pg-2, pg-3", "3", "madalina060504/tamagotchi-postgres-ha:0.6.0", "5432, 8008 (internal)",
     "Mădălina"),
    ("postgres", "1", "haproxy:3.0.5-alpine", "5432, 5433, 7000, 8008", "Mădălina"),
    ("cache-1, cache-2, cache-3", "3", "redis:7.4.1-alpine", "6379 (internal)", "Mădălina"),
    ("warehouse", "1", "postgres:16.14-alpine", "5434", "Mădălina"),
    ("etl-service", "1", "madalina060504/tamagotchi-etl-service:0.6.0", "8091", "Mădălina"),
]


def patch_html(text: str) -> str:
    style_end = text.index("</style>")
    text = text[:style_end] + CSS + ".d-cache { background: var(--cache); } .d-repl { background: var(--repl); }\n" + text[style_end:]
    text = text.replace("</defs>", MARKERS + "</defs>", 1)
    text = common(text)
    text = text.replace('viewBox="0 0 1340 820"', f'viewBox="0 0 1340 {820 + HTML_GROW}"', 1)
    nav_end = text.index("</nav>")
    buttons = "".join(
        f'<button type="button" class="view" id="view-{view}" data-view="{view}" aria-pressed="false">'
        f'<span class="dot d-{view}"></span>{label}</button>'
        for view, label in (("cache", "Cache"), ("repl", "Replication and warehouse"))
    )
    text = text[:nav_end] + buttons + text[nav_end:]

    start = text.index("const DETAILS = ") + len("const DETAILS = ")
    end = text.index(";\n", start)
    details = json.loads(text[start:end])
    details.update(DETAILS_NEW)
    for node_id, image in (("gateway", "gateway-service"), ("broker", "message-broker"),
                           ("user-management", "user-management-service"), ("map", "map-service")):
        for row in details[node_id]["rows"]:
            if row[0] == "Image":
                row[1] = f"madalina060504/tamagotchi-{image}:0.6.0"
    details["gateway"]["text"] += (" Since Lab 5 it caches common GETs and verified tokens in the "
                                   "sharded cache, and starts the account-deletion saga "
                                   "(DELETE /api/v1/users/me).")
    details["gateway"]["lists"][0][1].append("Cache: cached answers and tokens (consistent hashing)")
    details["broker"]["text"] += (" Since Lab 5 it coordinates the account-deletion saga across User "
                                  "Management and Map (compensations, state in SQLite) and caches "
                                  "user lookups between services.")
    details["broker"]["lists"][0][1].append("Cache: user lookups, gen:<service>, auth:revoked:<user>")
    for name, item in details["broker"]["lists"]:
        if name == "Endpoints":
            item.append("POST /v1/sagas, GET /v1/sagas, GET /v1/sagas/{id}")
    details["user-management"]["text"] += (" Lab 5: deactivate, reactivate and erase, its steps of the "
                                           "account-deletion saga.")
    details["map"]["text"] += " Lab 5: hide, unhide and purge, its steps of the account-deletion saga."
    for node_id in ("grafana", "prometheus"):
        extra = ("Data warehouse: the Lab 5 dashboard's SQL panels" if node_id == "grafana"
                 else "pg-1, pg-2, pg-3 (Patroni) and the ETL service: /metrics")
        if details[node_id]["lists"]:
            details[node_id]["lists"][0][1].append(extra)
        else:
            details[node_id]["lists"].append(["Talks to", [extra]])
    text = text[:start] + json.dumps(details, ensure_ascii=False) + text[end:]

    start = text.index("const CAPTIONS = ") + len("const CAPTIONS = ")
    end = text.index(";\n", start)
    captions = json.loads(text[start:end])
    captions.update(CAPTIONS_NEW)
    captions["mon"] = captions["mon"].replace(
        "each service keeps its own database in PostgreSQL",
        "each service keeps its own database on the Patroni cluster, behind the router postgres",
    )
    text = text[:start] + json.dumps(captions, ensure_ascii=False) + text[end:]

    for image in ("gateway-service", "message-broker", "user-management-service", "map-service"):
        text = text.replace(f"tamagotchi-{image}:0.5.0", f"tamagotchi-{image}:0.6.0")
    text = re.sub(r"<tr><td><code>postgres</code></td>.*?</tr>", "", text, count=1, flags=re.S)
    rows = "".join(
        f'<tr><td><code>{name}</code></td><td class="num">{count}</td><td><code>{image}</code></td>'
        f"<td>{ports}</td><td>{owner}</td></tr>"
        for name, count, image, ports, owner in TABLE_ROWS
    )
    text = text.replace("</tbody>", rows + "</tbody>", 1)
    text = re.sub(
        r'<tfoot><tr><td>Total</td><td class="num">25</td><td colspan="3">[^<]*</td></tr></tfoot>',
        '<tfoot><tr><td>Total</td><td class="num">34</td><td colspan="3">26 Compose services; the 8 '
        "game services run 2 replicas each, the database 3 nodes, the cache 3 nodes</td></tr></tfoot>",
        text, count=1,
    )
    text = text.replace("The Lab 4 stack: 25 containers from 17 Compose services",
                        "The Lab 5 stack: 34 containers from 26 Compose services", 1)
    legend_end = text.index("</ul></section>", text.index('class="legend"'))
    legend = "".join(
        f'<li><svg viewBox="0 0 44 10" width="44" height="10" aria-hidden="true"><line x1="1" y1="5" '
        f'x2="34" y2="5" class="ln c-{layer}"/><path class="m-{layer}" d="M33,0.8 L43,5 L33,9.2 z"/>'
        f"</svg>{label}</li>"
        for layer, label in (("cache", "Cache (Lab 5)"), ("repl", "Replication, ETL and warehouse (Lab 5)"))
    )
    return text[:legend_end] + legend + text[legend_end:]


def main() -> None:
    svg_path, html_path = HERE / "system-map.svg", HERE / "system-map.html"
    svg, html = svg_path.read_text(encoding="utf-8"), html_path.read_text(encoding="utf-8")
    if 'id="n-cache"' in svg or 'id="n-cache"' in html:
        raise SystemExit("the map already has the Lab 5 components")
    all_view = patch_svg(svg)
    write_views(all_view)
    html_path.write_text(patch_html(html), encoding="utf-8")
    print("system map updated: " + ", ".join(name for name, _ in VIEWS.values()) + ", system-map.html")


if __name__ == "__main__":
    main()
