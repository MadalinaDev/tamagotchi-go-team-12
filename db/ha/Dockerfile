# Lab 5 (grade 5): Postgres 16 with PostGIS 3 (Map needs it), managed by Patroni.
# Three containers of this image form one cluster: a leader and two streaming replicas.
# Patroni keeps the leader lock in etcd and promotes a replica when the leader fails.
#
# Build context: the db/ folder (so the image reuses init/01-create-databases.sh):
#   docker build -f db/ha/Dockerfile -t madalina060504/tamagotchi-postgres-ha:0.6.0 db
# The latest 16.x: apt.postgresql.org builds PostGIS against the newest minor release.
FROM postgres:16.14-bookworm

ARG PATRONI_VERSION=4.0.4

# PostGIS comes from apt.postgresql.org (bookworm is supported; the postgis/postgis images
# are still on Debian 11, whose package repositories are retired). The server is upgraded in
# the same step: PostGIS there is built against the newest 16.x and needs its symbols.
RUN apt-get update \
 && apt-get install -y --no-install-recommends \
      postgresql-16 postgresql-16-postgis-3 postgresql-16-postgis-3-scripts \
      python3 python3-venv curl \
 && python3 -m venv /opt/patroni \
 && /opt/patroni/bin/pip install --no-cache-dir \
      "patroni[etcd3]==${PATRONI_VERSION}" "psycopg2-binary==2.9.10" \
 && rm -rf /var/lib/apt/lists/*

COPY ha/patroni.yml /etc/patroni/patroni.yml
COPY ha/entrypoint.sh ha/post-bootstrap.sh /usr/local/bin/
COPY init/01-create-databases.sh /usr/local/share/tamagotchi/01-create-databases.sh
RUN chmod 0755 /usr/local/bin/entrypoint.sh /usr/local/bin/post-bootstrap.sh \
      /usr/local/share/tamagotchi/01-create-databases.sh \
 && mkdir -p /var/lib/postgresql/data \
 && chown -R postgres:postgres /var/lib/postgresql /etc/patroni

USER postgres
EXPOSE 5432 8008

HEALTHCHECK --interval=5s --timeout=3s --retries=30 CMD curl -fs http://localhost:8008/health || exit 1

# The postgres base image stops with SIGINT (a fast Postgres shutdown); Patroni needs SIGTERM
# to stop Postgres cleanly and hand the leader lock over at once. With SIGINT a stopped leader
# kept the lock until it expired (a 20 s outage instead of a 1-2 s switchover).
STOPSIGNAL SIGTERM
ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]
