#!/bin/sh
# Starts Patroni for one node of the cluster. PATRONI_NAME (pg-1, pg-2, pg-3) is also the
# node's hostname on the compose network.
set -eu

: "${PATRONI_NAME:?set PATRONI_NAME to this node's name (pg-1, pg-2 or pg-3)}"
: "${POSTGRES_PASSWORD:?set POSTGRES_PASSWORD}"
: "${REPLICATION_PASSWORD:?set REPLICATION_PASSWORD}"
# The REST API's changes (switchover, restart, configuration) need this login.
: "${PATRONI_RESTAPI_USERNAME:?set PATRONI_RESTAPI_USERNAME}"
: "${PATRONI_RESTAPI_PASSWORD:?set PATRONI_RESTAPI_PASSWORD}"

export PATRONI_RESTAPI_CONNECT_ADDRESS="${PATRONI_NAME}:8008"
export PATRONI_POSTGRESQL_CONNECT_ADDRESS="${PATRONI_NAME}:5432"
export PATRONI_SUPERUSER_USERNAME=postgres
export PATRONI_SUPERUSER_PASSWORD="$POSTGRES_PASSWORD"
export PATRONI_REPLICATION_USERNAME=replicator
export PATRONI_REPLICATION_PASSWORD="$REPLICATION_PASSWORD"

exec /opt/patroni/bin/patroni /etc/patroni/patroni.yml
