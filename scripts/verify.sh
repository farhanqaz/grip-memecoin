#!/usr/bin/env bash
# One command that checks the claims in the README.
#   ./scripts/verify.sh
# Exits non-zero on the first failed claim, so it is safe to wire into CI.

set -uo pipefail
cd "$(dirname "$0")/.."

CONTRACT="${CONTRACT:-grip5391e9.grip-21a10e2e.testnet}"
RPC="${RPC:-https://rpc.testnet.fastnear.com}"
fails=0

say()  { printf '\n\033[1m%s\033[0m\n' "$1"; }
pass() { printf '  \033[32mPASS\033[0m %s\n' "$1"; }
fail() { printf '  \033[31mFAIL\033[0m %s\n' "$1"; fails=$((fails + 1)); }
skip() { printf '  \033[33mSKIP\033[0m %s\n' "$1"; }

say "1. contract: unit tests"
if command -v cargo >/dev/null 2>&1; then
  out=$(cd contract && cargo test 2>&1)
  if grep -q "test result: ok" <<<"$out"; then
    pass "$(grep -o 'test result: ok\. [0-9]* passed' <<<"$out" | head -1)"
  else
    fail "cargo test did not pass"
    grep -E "^(error|test .* FAILED)" <<<"$out" | head -5
  fi

  say "2. contract: wasm build"
  if (cd contract && cargo build --release --target wasm32-unknown-unknown >/dev/null 2>&1); then
    wasm=contract/target/wasm32-unknown-unknown/release/grip_contract.wasm
    pass "built $(du -h "$wasm" | cut -f1) wasm"
  else
    fail "wasm build failed (is the wasm32-unknown-unknown target installed?)"
  fi
else
  skip "cargo not installed"
fi

say "3. simulation: 60 epoch supply study"
if command -v python3 >/dev/null 2>&1; then
  out=$(cd sim && python3 sim.py 2>&1)
  if grep -q "CHOSEN" <<<"$out"; then
    pass "study runs, parameters print"
    grep -E "^(grip|churn|fold) " <<<"$out" | head -3 | sed 's/^/       /'
  else
    fail "sim.py did not produce the study"
  fi
else
  skip "python3 not installed"
fi

say "4. chain: the deployed contract answers"
body=$(curl -sS -m 20 "$RPC" -X POST -H 'Content-Type: application/json' \
  -d "{\"jsonrpc\":\"2.0\",\"id\":\"v\",\"method\":\"query\",\"params\":{\"request_type\":\"call_function\",\"finality\":\"final\",\"account_id\":\"$CONTRACT\",\"method_name\":\"get_state\",\"args_base64\":\"e30=\"}}" 2>/dev/null)
state=$(python3 - "$body" <<'PY' 2>/dev/null
import base64, json, sys
try:
    r = json.loads(sys.argv[1])["result"]
    s = json.loads(bytes(r["result"]).decode())
    print(json.dumps({"supply": s["total_supply"], "locked": s["total_locked"],
                      "grip_bps": s["locked_share_bps"], "epoch": s["epoch"],
                      "mint": s["mint_epochs"], "burn": s["burn_epochs"]}))
except Exception:
    pass
PY
)
if [ -n "${state:-}" ]; then
  pass "get_state: $state"
else
  fail "no usable get_state from $CONTRACT"
fi

say "5. artefacts"
for f in docs/index.html docs/demo.mp4 demo/demo.mp4 contract/README.md README.md; do
  if [ -s "$f" ]; then pass "$f"; else fail "$f missing or empty"; fi
done

printf '\n'
if [ "$fails" -eq 0 ]; then
  printf '\033[32m%s\033[0m\n' "all checks passed"
  exit 0
fi
printf '\033[31m%s\033[0m\n' "$fails check(s) failed"
exit 1
