#!/usr/bin/env sh
# Idempotent seed script for Sava's Lab 1 services (Battle + Tamagotchi).
# Populates each database through the public HTTP API only when it is empty,
# so it is safe to run multiple times.
#
# Usage:
#   BATTLE_URL=http://localhost:8081 TAMAGOTCHI_URL=http://localhost:8082 ./scripts/seed.sh
set -eu

BATTLE_URL="${BATTLE_URL:-http://localhost:8081}"
TAMAGOTCHI_URL="${TAMAGOTCHI_URL:-http://localhost:8082}"

SEED_USER="${SEED_USER:-11111111-1111-4111-8111-111111111111}"
SEED_OPPONENT="${SEED_OPPONENT:-22222222-2222-4222-8222-222222222222}"
SEED_PACKAGE="${SEED_PACKAGE:-aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa}"
SEED_PRIMARY="${SEED_PRIMARY:-aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa}"
SEED_SECONDARY="${SEED_SECONDARY:-bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb}"

command -v curl >/dev/null 2>&1 || { echo "curl is required" >&2; exit 1; }

count_items() {
  curl -s -H "X-User-ID: $2" "$1" | python -c "import json,sys; print(len(json.load(sys.stdin).get('items', [])))"
}

echo "Seeding tamagotchi-service at $TAMAGOTCHI_URL ..."
TAMA_COUNT=$(count_items "$TAMAGOTCHI_URL/api/v1/tamagotchis" "$SEED_USER")
if [ "$TAMA_COUNT" -eq 0 ]; then
  curl -s -X POST "$TAMAGOTCHI_URL/api/v1/tamagotchis" \
    -H "X-User-ID: $SEED_USER" -H 'Content-Type: application/json' \
    -d "{\"package_id\":\"$SEED_PACKAGE\",\"name\":\"Ember\",\"type\":\"flame\"}"
  echo
  echo "Seeded 1 tamagotchi."
else
  echo "Tamagotchi database already contains $TAMA_COUNT item(s); skipping."
fi

echo "Seeding battle-service at $BATTLE_URL ..."
BATTLE_COUNT=$(count_items "$BATTLE_URL/api/v1/battles" "$SEED_USER")
if [ "$BATTLE_COUNT" -eq 0 ]; then
  curl -s -X POST "$BATTLE_URL/api/v1/battles" \
    -H "X-User-ID: $SEED_USER" -H 'Content-Type: application/json' \
    -d "{\"opponent_id\":\"$SEED_OPPONENT\",\"loadout\":{\"primary_pet_id\":\"$SEED_PRIMARY\",\"secondary_pet_id\":\"$SEED_SECONDARY\",\"boost\":\"power\"}}"
  echo
  echo "Seeded 1 battle."
else
  echo "Battle database already contains $BATTLE_COUNT item(s); skipping."
fi

echo "Seed complete."
