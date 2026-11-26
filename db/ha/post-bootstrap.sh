#!/bin/sh
# Patroni's post_bootstrap: runs once, on the node that initialises the cluster, before it
# accepts connections. The replicas copy everything from it (pg_basebackup).
set -eu

# The same databases and owners as the single Postgres of Labs 1-4 (local socket, trust).
POSTGRES_USER=postgres POSTGRES_DB=postgres /usr/local/share/tamagotchi/01-create-databases.sh

# Lab 5 (grade 4): the ETL job reads every database, never writes.
: "${ETL_DB_PASSWORD:?set ETL_DB_PASSWORD}"
case "$ETL_DB_PASSWORD" in
  *[!a-zA-Z0-9_]*)
    echo "ETL_DB_PASSWORD must be letters, digits or underscores only" >&2
    exit 1
    ;;
esac
psql -v ON_ERROR_STOP=1 --username postgres --dbname postgres <<SQL
DO \$\$ BEGIN
  IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'etl_reader') THEN
    CREATE ROLE etl_reader LOGIN PASSWORD '$ETL_DB_PASSWORD';
  END IF;
END \$\$;
GRANT pg_read_all_data TO etl_reader;
SQL
