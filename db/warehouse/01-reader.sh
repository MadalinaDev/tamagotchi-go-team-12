#!/bin/sh
# Lab 5 (grade 4): runs once, when the warehouse volume is empty. Creates the schema the
# ETL service loads (as the owner, POSTGRES_USER) and dw_reader, the read-only user
# Grafana's Warehouse data source logs in with: it may read every table and view of `dw`,
# including the ones the ETL creates later (default privileges).
set -eu

: "${WAREHOUSE_READER_PASSWORD:?set WAREHOUSE_READER_PASSWORD}"
case "$WAREHOUSE_READER_PASSWORD" in
  *[!a-zA-Z0-9_]*)
    echo "WAREHOUSE_READER_PASSWORD must be letters, digits or underscores only" >&2
    exit 1
    ;;
esac

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<SQL
CREATE ROLE dw_reader LOGIN PASSWORD '$WAREHOUSE_READER_PASSWORD';
CREATE SCHEMA IF NOT EXISTS dw AUTHORIZATION $POSTGRES_USER;
GRANT CONNECT ON DATABASE $POSTGRES_DB TO dw_reader;
GRANT USAGE ON SCHEMA dw TO dw_reader;
ALTER DEFAULT PRIVILEGES FOR ROLE $POSTGRES_USER IN SCHEMA dw GRANT SELECT ON TABLES TO dw_reader;
SQL
