#!/usr/bin/env sh
# Run from any directory. No host PostgreSQL, Python or jq installation required.
set -eu
cd "$(dirname "$0")/.."
for pair in 'tamagotchi-db tamagotchi_user tamagotchi_db tamagotchis' 'battle-db battle_user battle_db battles'; do
  set -- $pair
  attempts=0
  until docker compose exec -T "$1" psql -U "$2" -d "$3" -v ON_ERROR_STOP=1 -c "SELECT 1 FROM $4 LIMIT 0" >/dev/null 2>&1; do
    attempts=$((attempts + 1))
    if [ "$attempts" -ge 30 ]; then echo "Schema unavailable in $1; start Compose and inspect service logs" >&2; exit 1; fi
    sleep 2
  done
done
docker compose exec -T tamagotchi-db psql -U tamagotchi_user -d tamagotchi_db -v ON_ERROR_STOP=1 < db/tamagotchi/002_seed.sql
docker compose exec -T battle-db psql -U battle_user -d battle_db -v ON_ERROR_STOP=1 < db/battle/002_seed.sql
echo 'Seed completed. Each nonempty domain database was left unchanged.'
