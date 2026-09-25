-- Reference copy of the guild-service Lab 1 self-seed (applied by the
-- service itself when SEED_ON_START=true and the guilds table is empty).
-- Fixed IDs come from section 5 of docs/lab-1-conventions.md.
BEGIN;
LOCK TABLE guilds IN EXCLUSIVE MODE;
INSERT INTO guilds (guild_id, name, leader_id, created_at)
SELECT '00000000-0000-4000-8000-0000000000c1', 'Founders',
       '00000000-0000-4000-8000-000000000001', '2026-09-01T12:00:00Z'
WHERE NOT EXISTS (SELECT 1 FROM guilds);
INSERT INTO guild_members (guild_id, user_id, role, joined_at)
SELECT m.guild_id::uuid, m.user_id::uuid, m.role, m.joined_at::timestamptz
FROM (VALUES
  ('00000000-0000-4000-8000-0000000000c1', '00000000-0000-4000-8000-000000000001', 'leader', '2026-09-01T12:00:00Z'),
  ('00000000-0000-4000-8000-0000000000c1', '00000000-0000-4000-8000-000000000002', 'member', '2026-09-01T12:01:00Z'),
  ('00000000-0000-4000-8000-0000000000c1', '00000000-0000-4000-8000-000000000003', 'member', '2026-09-01T12:02:00Z')
) AS m (guild_id, user_id, role, joined_at)
WHERE NOT EXISTS (SELECT 1 FROM guild_members);
COMMIT;
