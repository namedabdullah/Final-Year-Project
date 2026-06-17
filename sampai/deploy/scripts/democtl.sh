#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEPLOY_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
DOCKER_DIR="$(cd "$DEPLOY_DIR/../docker" && pwd)"
ENV_FILE="${SAMPAI_ENV_FILE:-$DEPLOY_DIR/.env.aws}"

if [ ! -f "$ENV_FILE" ]; then
  echo "Missing $ENV_FILE. Run: bash $SCRIPT_DIR/init-env.sh" >&2
  exit 1
fi

compose() {
  (cd "$DOCKER_DIR" && docker compose --env-file "$ENV_FILE" -f docker-compose.yml -f ../deploy/docker-compose.aws.yml "$@")
}

compose_tunnel() {
  (cd "$DOCKER_DIR" && docker compose --env-file "$ENV_FILE" -f docker-compose.yml -f ../deploy/docker-compose.aws.yml -f ../deploy/docker-compose.cloudflare-tunnel.yml "$@")
}

web_port() {
  awk -F= '/^SAMPAI_WEB_PORT=/{print $2}' "$ENV_FILE" | tail -n 1
}

require_no_placeholders() {
  local include_tunnel="${1:-false}"
  local placeholders
  if [ "$include_tunnel" = "true" ]; then
    placeholders="$(grep 'REPLACE_' "$ENV_FILE" || true)"
  else
    placeholders="$(grep 'REPLACE_' "$ENV_FILE" | grep -v '^CLOUDFLARED_TOKEN=' || true)"
  fi

  if [ -n "$placeholders" ]; then
    echo "$ENV_FILE still contains REPLACE_* placeholders." >&2
    printf '%s\n' "$placeholders" >&2
    exit 1
  fi
}

cmd="${1:-help}"
shift || true

case "$cmd" in
  config)
    compose --profile data --profile parsing --profile app config
    ;;
  setup)
    require_no_placeholders
    compose --profile data --profile parsing pull postgres neo4j qdrant redis docling
    compose --profile data --profile app build api web
    compose --profile data up -d
    ;;
  start)
    require_no_placeholders
    compose --profile data --profile app up -d --build
    ;;
  start-live)
    require_no_placeholders
    compose --profile data --profile parsing --profile app up -d --build
    ;;
  start-tunnel)
    require_no_placeholders true
    compose_tunnel --profile data --profile app --profile tunnel up -d --build --scale cloudflared=2
    ;;
  start-live-tunnel)
    require_no_placeholders true
    compose_tunnel --profile data --profile parsing --profile app --profile tunnel up -d --build --scale cloudflared=2
    ;;
  stop)
    compose_tunnel --profile data --profile parsing --profile app --profile tunnel stop
    ;;
  down)
    compose_tunnel --profile data --profile parsing --profile app --profile tunnel down
    ;;
  destroy-volumes)
    if [ "${SAMPAI_CONFIRM_DESTROY:-}" != "YES" ]; then
      echo "This deletes all local demo data. Re-run with SAMPAI_CONFIRM_DESTROY=YES." >&2
      exit 1
    fi
    compose_tunnel --profile data --profile parsing --profile app --profile tunnel down -v
    ;;
  ps)
    compose --profile data --profile parsing --profile app ps
    ;;
  logs)
    service="${1:-api}"
    compose_tunnel --profile data --profile parsing --profile app --profile tunnel logs -f "$service"
    ;;
  health)
    compose_tunnel --profile data --profile parsing --profile app --profile tunnel exec -T web \
      wget -qO- http://api:9621/api/sampai/health
    printf '\n'
    ;;
  *)
    cat <<'USAGE'
Usage: bash scripts/democtl.sh <command>

Commands:
  config           Render the merged compose config.
  setup            Pull data/docling images, build app images, start data stores.
  start            Start data + app only. Use after pre-ingestion.
  start-live       Start data + docling + app for live document uploads.
  start-tunnel     Start data + app + Cloudflare Tunnel, no public web port.
  start-live-tunnel
                   Start data + docling + app + Cloudflare Tunnel.
  stop             Stop containers but keep volumes.
  down             Remove containers/networks but keep volumes.
  destroy-volumes  Delete containers and volumes. Requires SAMPAI_CONFIRM_DESTROY=YES.
  ps               Show container status.
  logs [service]   Follow logs for a service, default api.
  health           Check the public web edge health route locally.
USAGE
    ;;
esac
