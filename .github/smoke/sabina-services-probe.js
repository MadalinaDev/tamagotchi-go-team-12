// Smoke check for Monster Raid and Package Registry while gateway-service is
// not in docker-compose.yml yet. Since Lab 2 both services are reachable only
// on the compose network (expose:), and their Postman collections go through
// the gateway. This script runs inside the monster-raid-service container:
//
//   docker compose exec -T monster-raid-service node - < .github/smoke/sabina-services-probe.js
//
// It plays the gateway's part by sending the X-Auth-* / X-Service-Name headers
// the gateway will set, and exits non-zero if any check fails.

const RAID = 'http://monster-raid-service:8087';
const REGISTRY = 'http://package-registry-service:8088';
const ALICE = '00000000-0000-4000-8000-000000000001';
const OUTSIDER = '00000000-0000-4000-8000-0000000000ff';
const FOUNDERS = '00000000-0000-4000-8000-0000000000c1';
const BIG_SLIME = '00000000-0000-4000-8000-0000000000d1';

let failures = 0;
function check(name, ok, got) {
  console.log(`${ok ? 'ok  ' : 'FAIL'} ${name}${ok ? '' : ` (got ${got})`}`);
  if (!ok) failures++;
}

/** The services have no healthcheck; wait until they answer at all. */
async function waitFor(url) {
  for (let i = 0; i < 90; i++) {
    try {
      await fetch(url);
      return;
    } catch {
      await new Promise((r) => setTimeout(r, 1000));
    }
  }
  throw new Error(`${url} did not come up within 90 s`);
}

async function main() {
  await waitFor(`${REGISTRY}/api/v1/packages`);
  await waitFor(`${RAID}/api/v1/raids`);

  // Identity comes only from the gateway's X-Auth-* headers.
  const routes = [
    ['Package Registry', `${REGISTRY}/api/v1/packages`],
    ['Monster Raid', `${RAID}/api/v1/raids?guild_id=${FOUNDERS}`],
  ];
  for (const [service, url] of routes) {
    let r = await fetch(url);
    check(`${service}: no X-Auth-User-Id -> 401`, r.status === 401, r.status);
    r = await fetch(url, { headers: { 'x-mock-user-id': ALICE, 'x-mock-roles': 'admin' } });
    check(`${service}: Lab 1 X-Mock-User-Id only -> 401`, r.status === 401, r.status);
    r = await fetch(url, { headers: { 'x-auth-user-id': ALICE } });
    check(`${service}: X-Auth-User-Id -> 200`, r.status === 200, r.status);
  }

  let r = await fetch(`${REGISTRY}/api/v1/raid-definitions`, { headers: { 'x-auth-user-id': ALICE } });
  check('Package Registry: admin route without X-Auth-Roles: admin -> 403', r.status === 403, r.status);
  r = await fetch(`${REGISTRY}/internal/v1/packages/${FOUNDERS}`);
  check('Package Registry: internal route without X-Service-Name -> 401', r.status === 401, r.status);

  // Live raid HP (SSE): a raid activated after its deadline is created as
  // failed, so its stream sends one `raid` event and closes.
  r = await fetch(`${RAID}/internal/v1/dev/raid-events`, {
    method: 'POST',
    headers: { 'content-type': 'application/json', 'x-service-name': 'package-registry' },
    body: JSON.stringify({
      type: 'RaidActivationRequested',
      payload: {
        schedule_id: crypto.randomUUID(),
        revision: 1,
        definition_id: BIG_SLIME,
        definition_version: 1,
        guild_id: FOUNDERS,
        starts_at: new Date(Date.now() - 2 * 3600 * 1000).toISOString(),
      },
    }),
  });
  const raid = await r.json();
  check('Monster Raid: late activation -> 201 failed raid', r.status === 201 && raid.state === 'failed', `${r.status} ${raid.state}`);

  r = await fetch(`${RAID}/api/v1/raids/${raid.raid_id}/events`, {
    headers: { 'x-auth-user-id': ALICE },
    signal: AbortSignal.timeout(10000),
  });
  const stream = await r.text();
  check(
    'Monster Raid: event stream -> 200 text/event-stream, one raid event, then closed',
    r.status === 200 &&
      (r.headers.get('content-type') ?? '').startsWith('text/event-stream') &&
      stream.includes('event: raid') &&
      stream.includes('"state":"failed"'),
    `${r.status} ${r.headers.get('content-type')}`,
  );

  r = await fetch(`${RAID}/api/v1/raids/${raid.raid_id}/events`, { headers: { 'x-auth-user-id': OUTSIDER } });
  const refused = await r.json().catch(() => ({}));
  check('Monster Raid: event stream for a non-member -> JSON 403', r.status === 403 && refused.code === 'RAID_FORBIDDEN', `${r.status} ${refused.code}`);

  console.log(failures ? `${failures} check(s) failed` : 'all checks passed');
  process.exit(failures ? 1 : 0);
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
