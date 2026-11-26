#!/bin/sh
# Lab 5, grade 5: crash the Patroni leader and check that
#   1. a replica is promoted on its own;
#   2. the services keep working through the router (the old hostname, postgres:5432);
#   3. no committed write is lost (a player registered before the crash can still log in);
#   4. the old leader rejoins as a replica when it comes back.
set -eu

GATEWAY=${GATEWAY:-http://localhost:8080}
PATRONI=${PATRONI:-http://localhost:8008}

cluster() { curl -fsS -m 3 "$PATRONI/cluster" 2>/dev/null || true; }
role_of() {  # role_of <member> -> leader / sync_standby / replica (state "running"/"streaming")
  cluster | python3 -c '
import json, sys
try:
    members = json.load(sys.stdin)["members"]
except ValueError:
    sys.exit(0)
for m in members:
    if m["name"] == sys.argv[1]:
        print(m["role"], m["state"])' "$1"
}
leader() {
  cluster | python3 -c '
import json, sys
try:
    members = json.load(sys.stdin)["members"]
except ValueError:
    sys.exit(0)
print(next((m["name"] for m in members if m["role"] == "leader" and m["state"] == "running"), ""))'
}

suffix=$(date +%s)
email="failover_${suffix}@example.com"
curl -fsS -X POST "$GATEWAY/api/v1/users" -H 'Content-Type: application/json' \
  -H "Idempotency-Key: $(python3 -c 'import uuid; print(uuid.uuid4())')" \
  -d "{\"username\":\"failover_${suffix}\",\"email\":\"$email\",\"password\":\"password123\",\"display_name\":\"Failover\"}" \
  > /dev/null
echo "registered $email before the crash"

old=$(leader)
[ -n "$old" ] || { echo "no leader to crash: $(cluster)"; exit 1; }
docker compose kill "$old" > /dev/null
echo "killed the leader $old (SIGKILL)"

new=""
for i in $(seq 1 60); do
  new=$(leader)
  if [ -n "$new" ] && [ "$new" != "$old" ]; then break; fi
  new=""
  sleep 1
done
[ -n "$new" ] || { echo "no replica was promoted: $(cluster)"; exit 1; }
echo "$new was promoted after about ${i} s"

ok=""
for i in $(seq 1 45); do
  # 503 DEPENDENCY_UNAVAILABLE is expected until the router reaches the new leader.
  if curl -fs -m 5 -o /dev/null -X POST "$GATEWAY/api/v1/auth/login" -H 'Content-Type: application/json' \
    -d "{\"email\":\"$email\",\"password\":\"password123\"}"; then ok=yes; break; fi
  sleep 1
done
[ -n "$ok" ] || { echo "the services did not recover on the new leader"; exit 1; }
echo "the player registered before the crash logs in through the new leader (after ${i} s)"

docker compose start "$old" > /dev/null
for i in $(seq 1 90); do
  case "$(role_of "$old")" in
    "replica streaming"|"sync_standby streaming") echo "$old rejoined as a replica after ${i} s"; exit 0 ;;
  esac
  sleep 1
done
echo "$old did not rejoin: $(cluster)"
exit 1
