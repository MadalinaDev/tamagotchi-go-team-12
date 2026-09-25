-- Reference copy of the notification-service Lab 1 self-seed (applied by
-- the service itself when SEED_ON_START=true and the notifications table is
-- empty). Bob's inbox gets Alice's friend request (User Management
-- friendship …00e1) and Alice's battle challenge (Battle …00e1).
BEGIN;
LOCK TABLE notifications IN EXCLUSIVE MODE;
INSERT INTO notifications (notification_id, event_id, recipient_id, type, title, body, resource_type, resource_id, created_at)
SELECT n.notification_id::uuid, n.event_id::uuid, n.recipient_id::uuid, n.type, n.title, n.body,
       n.resource_type, n.resource_id::uuid, n.created_at::timestamptz
FROM (VALUES
  ('00000000-0000-4000-8000-000000000f11', '00000000-0000-4000-8000-000000000f01', '00000000-0000-4000-8000-000000000002',
   'FriendRequested', 'New friend request', 'Someone wants to be your friend.',
   'friendship', '00000000-0000-4000-8000-0000000000e1', '2026-09-01T12:00:00Z'),
  ('00000000-0000-4000-8000-000000000f12', '00000000-0000-4000-8000-000000000f02', '00000000-0000-4000-8000-000000000002',
   'BattleRequested', 'Battle challenge', 'You have been challenged to a battle.',
   'battle', '00000000-0000-4000-8000-0000000000e1', '2026-09-01T12:01:00Z')
) AS n (notification_id, event_id, recipient_id, type, title, body, resource_type, resource_id, created_at)
WHERE NOT EXISTS (SELECT 1 FROM notifications);
COMMIT;
