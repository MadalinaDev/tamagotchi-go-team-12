BEGIN;
LOCK TABLE tamagotchis, starter_issuances IN EXCLUSIVE MODE;
INSERT INTO tamagotchis(pet_id,owner_id,package_id,name,combat_type,xp,level,sprite_urls,definition_version,care_stats,version,created_at,updated_at)
SELECT v.pet_id::uuid,v.owner_id::uuid,v.package_id::uuid,v.name,v.combat_type,0,1,'[]'::jsonb,1,
       '{"hunger":20,"happiness":80,"tiredness":10}'::jsonb,1,now(),now()
FROM (VALUES
 ('aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa','11111111-1111-4111-8111-111111111111','cccccccc-cccc-4ccc-8ccc-cccccccccccc','Ember','flame'),
 ('bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb','11111111-1111-4111-8111-111111111111','dddddddd-dddd-4ddd-8ddd-dddddddddddd','Sprout','nature'),
 ('aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaab','22222222-2222-4222-8222-222222222222','cccccccc-cccc-4ccc-8ccc-cccccccccccc','Ripple','water'),
 ('bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbc','22222222-2222-4222-8222-222222222222','dddddddd-dddd-4ddd-8ddd-dddddddddddd','Shade','shadow')
) AS v(pet_id,owner_id,package_id,name,combat_type)
WHERE NOT EXISTS (SELECT 1 FROM tamagotchis) AND NOT EXISTS (SELECT 1 FROM starter_issuances);
INSERT INTO starter_issuances(owner_id,package_id)
SELECT owner_id,package_id FROM tamagotchis ON CONFLICT DO NOTHING;
COMMIT;
