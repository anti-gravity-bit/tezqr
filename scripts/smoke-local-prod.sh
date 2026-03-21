#!/bin/sh
set -eu

ENV_FILE="${ENV_FILE:-.env.local.prod}"
COMPOSE_FILES="-f docker-compose-prod.yml -f docker-compose-local.prod.yml"
BASE_CMD="docker compose --env-file ${ENV_FILE} ${COMPOSE_FILES}"
KEEP_RUNNING="${KEEP_RUNNING:-1}"

if [ ! -f "${ENV_FILE}" ]; then
  echo "Missing ${ENV_FILE}. Copy .env.local.prod.example to ${ENV_FILE} first."
  exit 1
fi

case "${ENV_FILE}" in
  /*|./*|../*)
    ENV_SOURCE_PATH="${ENV_FILE}"
    ;;
  *)
    ENV_SOURCE_PATH="./${ENV_FILE}"
    ;;
esac

set -a
. "${ENV_SOURCE_PATH}"
set +a

API_HOST_PORT="${API_HOST_PORT:-18000}"
CADDY_HTTP_PORT="${CADDY_HTTP_PORT:-18080}"

if [ "${KEEP_RUNNING}" = "0" ]; then
  trap 'sh -c "${BASE_CMD} down -v --remove-orphans"' EXIT
fi

sh -c "${BASE_CMD} up -d --build"

attempt=0
until curl -fsS "http://127.0.0.1:${API_HOST_PORT}/health" >/dev/null; do
  attempt=$((attempt + 1))
  if [ "${attempt}" -ge 30 ]; then
    sh -c "${BASE_CMD} ps"
    sh -c "${BASE_CMD} logs api db caddy"
    exit 1
  fi
  sleep 2
done

attempt=0
until curl -fsS "http://localhost:${CADDY_HTTP_PORT}/health" >/dev/null; do
  attempt=$((attempt + 1))
  if [ "${attempt}" -ge 30 ]; then
    sh -c "${BASE_CMD} ps"
    sh -c "${BASE_CMD} logs api db caddy"
    exit 1
  fi
  sleep 2
done

curl -fsS "http://127.0.0.1:${API_HOST_PORT}/health"
echo
curl -fsS "http://localhost:${CADDY_HTTP_PORT}/health"
echo
sh -c "${BASE_CMD} ps"
