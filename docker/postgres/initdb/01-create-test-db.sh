#!/bin/sh
# Creates the separate database used by pytest. Runs only on first volume init.
set -eu

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<-EOSQL
    CREATE DATABASE "${TEST_DB}" OWNER "${POSTGRES_USER}";
EOSQL
