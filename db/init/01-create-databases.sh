#!/usr/bin/env bash
# Creates the 8 team databases and owners inside the single postgres container.
# Runs automatically on first container start (empty pgdata volume).
# Required passwords come from the container environment (see .env.example):
#   BATTLE_DB_PASSWORD, TAMAGOTCHI_DB_PASSWORD, GUILD_DB_PASSWORD,
#   NOTIFICATION_DB_PASSWORD, USER_MANAGEMENT_DB_PASSWORD, MAP_DB_PASSWORD,
#   RAID_DB_PASSWORD, REGISTRY_DB_PASSWORD
# Passwords must be letters and digits only (they are interpolated into SQL).
# To redo: docker compose down -v (destroys all data).
set -eu

PSQL="psql -v ON_ERROR_STOP=1 --username $POSTGRES_USER --dbname $POSTGRES_DB"

create_role() {
  user="$1"
  password_var="$2"
  password="$(printenv "$password_var")"
  if [ -z "$password" ]; then
    echo "Missing required password variable: $password_var (see .env.example)" >&2
    exit 1
  fi
  case "$password" in
    *[^a-zA-Z0-9]*)
      echo "Password in $password_var must be letters and digits only" >&2
      exit 1
      ;;
  esac
  $PSQL -c "DO \$\$ BEGIN IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = '$user') THEN CREATE ROLE $user LOGIN PASSWORD '$password'; END IF; END \$\$;"
}

create_db() {
  db="$1"
  owner="$2"
  exists="$($PSQL -tAc "SELECT 1 FROM pg_database WHERE datname = '$db'")"
  if [ "$exists" != "1" ]; then
    $PSQL -c "CREATE DATABASE $db OWNER $owner"
  else
    $PSQL -c "ALTER DATABASE $db OWNER TO $owner"
  fi
}

create_role battle_user BATTLE_DB_PASSWORD
create_role tamagotchi_user TAMAGOTCHI_DB_PASSWORD
create_role guild_user GUILD_DB_PASSWORD
create_role notification_user NOTIFICATION_DB_PASSWORD
create_role user_management_user USER_MANAGEMENT_DB_PASSWORD
create_role map_user MAP_DB_PASSWORD
create_role raid_user RAID_DB_PASSWORD
create_role registry_user REGISTRY_DB_PASSWORD

create_db battle_db battle_user
create_db tamagotchi_db tamagotchi_user
create_db guild_db guild_user
create_db notification_db notification_user
create_db user_management_db user_management_user
create_db map_db map_user
create_db raid_db raid_user
create_db registry_db registry_user

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname map_db -c \
  'CREATE EXTENSION IF NOT EXISTS postgis'
