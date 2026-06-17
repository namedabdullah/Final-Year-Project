#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEPLOY_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
TEMPLATE="$DEPLOY_DIR/.env.aws.example"
ENV_FILE="$DEPLOY_DIR/.env.aws"

rand_hex() {
  local bytes="${1:-24}"
  if command -v openssl >/dev/null 2>&1; then
    openssl rand -hex "$bytes"
  else
    od -An -N "$bytes" -tx1 /dev/urandom | tr -d ' \n'
    printf "\n"
  fi
}

replace_token() {
  local token="$1"
  local value="$2"
  sed -i "s|$token|$value|g" "$ENV_FILE"
}

if [ -e "$ENV_FILE" ]; then
  echo "$ENV_FILE already exists; leaving it unchanged."
  exit 0
fi

cp "$TEMPLATE" "$ENV_FILE"
chmod 600 "$ENV_FILE"

POSTGRES_PASSWORD="$(rand_hex 18)"
ADMIN_PASSWORD="$(rand_hex 10)"

replace_token "REPLACE_POSTGRES_PASSWORD" "$POSTGRES_PASSWORD"
replace_token "REPLACE_NEO4J_PASSWORD" "$(rand_hex 18)"
replace_token "REPLACE_LIGHTRAG_API_KEY" "$(rand_hex 24)"
replace_token "REPLACE_APP_JWT_SECRET" "$(rand_hex 32)"
replace_token "REPLACE_TOKEN_SECRET" "$(rand_hex 32)"
replace_token "REPLACE_ADMIN_PASSWORD" "$ADMIN_PASSWORD"

cat <<MSG
Created $ENV_FILE with local demo secrets.

Edit the remaining REPLACE_* values before starting SAMpai:
  - LLM_BINDING_API_KEY, LLM_MODEL
  - EMBEDDING_BINDING_API_KEY, EMBEDDING_MODEL, EMBEDDING_DIM if different
  - R2_ENDPOINT, R2_ACCESS_KEY_ID, R2_SECRET_ACCESS_KEY, R2_BUCKET

Temporary SAMpai login:
  username: admin
  password: $ADMIN_PASSWORD

For a public demo, replace AUTH_ACCOUNTS with a bcrypt value after the API image
is built:
  docker compose ... exec api python -m lightrag.tools.hash_password --username admin
MSG
