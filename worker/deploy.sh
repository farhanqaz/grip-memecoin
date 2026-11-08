# One command deploy, after `npx wrangler login` has been done once.
#
#   ./worker/deploy.sh
#
# It pushes the two secrets and then the Worker itself. Nothing here reads a password: wrangler login is an
# OAuth click in a browser, and the NEAR key is pushed from demo/canonical-account.json, which is gitignored.

set -euo pipefail
cd "$(dirname "$0")"

KEY_FILE="${KEY_FILE:-../demo/canonical-account.json}"
TOKEN_FILE=".trigger-token"

if [ ! -f "$KEY_FILE" ]; then
  echo "no key file at $KEY_FILE" >&2
  exit 1
fi

if ! npx wrangler whoami >/dev/null 2>&1; then
  echo "not logged in. run this first:  cd worker && npx wrangler login" >&2
  exit 1
fi

# the Worker has to exist before it can hold secrets, so deploy first; secrets apply immediately after
npx wrangler deploy

npx wrangler secret put GRIP_SIGNER < "$KEY_FILE"

if [ ! -f "$TOKEN_FILE" ]; then
  head -c 24 /dev/urandom | base64 | tr -d '/+=' > "$TOKEN_FILE"
  chmod 600 "$TOKEN_FILE"
fi
npx wrangler secret put TRIGGER_TOKEN < "$TOKEN_FILE"
echo
echo "token for GET /run is in worker/$TOKEN_FILE"
echo "test it with:  curl -H \"x-token: \$(cat worker/$TOKEN_FILE)\" https://grip-keeper.<your-subdomain>.workers.dev/run"
