BEGIN;
LOCK TABLE battles IN EXCLUSIVE MODE;
INSERT INTO battles(battle_id,challenger_id,opponent_id,primary_pet_id,secondary_pet_id,boost,state,version,created_at,updated_at)
SELECT 'eeeeeeee-eeee-4eee-8eee-eeeeeeeeeeee','11111111-1111-4111-8111-111111111111','22222222-2222-4222-8222-222222222222',
       'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa','bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb','power','pending',1,now(),now()
WHERE NOT EXISTS (SELECT 1 FROM battles);
COMMIT;
