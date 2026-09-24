-- Reference copy of the battle-service Lab 1 self-seed (applied by the
-- service itself when SEED_ON_START=true and the battles table is empty).
-- Fixed IDs come from section 5 of docs/lab-1-conventions.md.
BEGIN;
LOCK TABLE battles IN EXCLUSIVE MODE;
INSERT INTO battles(battle_id, challenger_id, opponent_id, primary_pet_id, secondary_pet_id, boost, state, version, created_at, updated_at)
SELECT '00000000-0000-4000-8000-0000000000e1',
       '00000000-0000-4000-8000-000000000001',
       '00000000-0000-4000-8000-000000000002',
       '00000000-0000-4000-8000-0000000000b1',
       '00000000-0000-4000-8000-0000000000b2',
       'power', 'pending', 1, now(), now()
WHERE NOT EXISTS (SELECT 1 FROM battles);
COMMIT;
