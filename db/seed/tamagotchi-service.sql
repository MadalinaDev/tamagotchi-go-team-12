-- Reference copy of the tamagotchi-service Lab 1 self-seed (applied by the
-- service itself when SEED_ON_START=true and pets/issuance are empty).
-- Fixed IDs come from section 5 of docs/lab-1-conventions.md.
BEGIN;
LOCK TABLE tamagotchis, starter_issuances IN EXCLUSIVE MODE;
INSERT INTO tamagotchis(pet_id, owner_id, package_id, name, combat_type, xp, level, sprite_urls, definition_version, care_stats, version, created_at, updated_at)
SELECT v.pet_id::uuid, v.owner_id::uuid, v.package_id::uuid, v.name, v.combat_type, 0, 1, '[]'::jsonb, 1,
       v.care_stats::jsonb, 1, now(), now()
FROM (VALUES
  ('00000000-0000-4000-8000-0000000000b1', '00000000-0000-4000-8000-000000000001', '00000000-0000-4000-8000-0000000000a1', 'Ember', 'flame', '{"hunger":20,"happiness":80}'),
  ('00000000-0000-4000-8000-0000000000b2', '00000000-0000-4000-8000-000000000001', '00000000-0000-4000-8000-0000000000a2', 'Ripple', 'water', '{"energy":90,"mood":80}'),
  ('00000000-0000-4000-8000-0000000000b3', '00000000-0000-4000-8000-000000000002', '00000000-0000-4000-8000-0000000000a1', 'Sprout', 'nature', '{"hunger":20,"happiness":80}')
) AS v(pet_id, owner_id, package_id, name, combat_type, care_stats)
WHERE NOT EXISTS (SELECT 1 FROM tamagotchis) AND NOT EXISTS (SELECT 1 FROM starter_issuances);
INSERT INTO starter_issuances(owner_id, package_id)
SELECT owner_id, package_id FROM tamagotchis ON CONFLICT DO NOTHING;
COMMIT;
