#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEPLOY_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

install_packages() {
  if command -v docker >/dev/null 2>&1 && docker compose version >/dev/null 2>&1; then
    return
  fi

  if command -v dnf >/dev/null 2>&1; then
    sudo dnf update -y
    sudo dnf install -y docker git curl jq openssl
  elif command -v apt-get >/dev/null 2>&1; then
    sudo apt-get update
    sudo apt-get install -y docker.io docker-compose-plugin git curl jq openssl ca-certificates
  else
    echo "Unsupported OS: install Docker Compose v2, git, curl, jq, and openssl manually." >&2
    exit 1
  fi
}

install_packages

sudo systemctl enable --now docker
sudo usermod -aG docker "$USER" || true

if [ ! -f "$DEPLOY_DIR/.env.aws" ]; then
  bash "$SCRIPT_DIR/init-env.sh"
fi

cat <<MSG
Host bootstrap complete.

Next:
  1. Log out and back in if Docker says permission denied.
  2. Edit $DEPLOY_DIR/.env.aws and fill the LLM, embedding, and R2 values.
  3. Run:
       cd $DEPLOY_DIR
       bash scripts/democtl.sh setup
       bash scripts/democtl.sh start

Use start-live instead of start if you need live document uploads through Docling.
MSG

