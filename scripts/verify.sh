#!/usr/bin/env sh
# Run only on a disposable Compose project; collections create/delete test rows.
set -eu
cd "$(dirname "$0")/.."
for port in 8081 8082; do
  curl --fail --silent --show-error --retry 30 --retry-all-errors --retry-delay 1 "http://localhost:$port/health"
done
./scripts/seed.sh
snapshot() {
  docker compose exec -T battle-db psql -U battle_user -d battle_db -Atc 'SELECT md5(coalesce(string_agg(row_to_json(b)::text, chr(10) ORDER BY battle_id),chr(10))) FROM battles b'
  docker compose exec -T tamagotchi-db psql -U tamagotchi_user -d tamagotchi_db -Atc 'SELECT md5(coalesce(string_agg(row_to_json(t)::text, chr(10) ORDER BY pet_id),chr(10))) FROM tamagotchis t'
  docker compose exec -T tamagotchi-db psql -U tamagotchi_user -d tamagotchi_db -Atc 'SELECT count(*) FROM starter_issuances'
}
before=$(snapshot)
./scripts/seed.sh
test "$before" = "$(snapshot)" || { echo 'Seed changed existing data' >&2; exit 1; }
npx --yes newman@6.2.1 run postman/battle-service.postman_collection.json --bail
npx --yes newman@6.2.1 run postman/tamagotchi-service.postman_collection.json --bail
# Also prove seed leaves a database containing another user's data untouched.
./scripts/seed.sh
before=$(snapshot)
docker compose down
docker compose up -d --wait
for port in 8081 8082; do
  curl --fail --silent --show-error --retry 30 --retry-all-errors --retry-delay 1 "http://localhost:$port/health"
done
test "$before" = "$(snapshot)" || { echo 'Database state lost after down/up' >&2; exit 1; }
echo 'PASS: API regression collections, seed idempotency and volume persistence.'
