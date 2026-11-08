#!/usr/bin/env bash
# Read the deployed contract from a terminal, with no browser and no keys.
#
#   ./scripts/state.sh                                  # get_state
#   ./scripts/state.sh ft_metadata                      # any view method
#   ./scripts/state.sh locked_of '{"account_id":"grip-21a10e2e.testnet"}'
#   ./scripts/state.sh ft_balance_of '{"account_id":"grip-21a10e2e.testnet"}'
#
# Deliberately not a jq one-liner. jq's `implode` re-encodes numbers as UTF-8 codepoints, and the
# classic `jq -r '.result.result[]' | awk '{printf "%c",$1}'` depends on awk's locale: under gawk in a
# UTF-8 locale a byte above 127 comes out as a multi-byte character, so the payload is silently
# corrupted for anything but ASCII. `bytes()` in python drops the byte in as a byte. python3 is already
# a dependency of this repo (verify.sh, sim.py), jq is not.
set -euo pipefail

RPC="${RPC:-https://rpc.testnet.fastnear.com}"
CONTRACT="${CONTRACT:-grip599cb0.grip-21a10e2e.testnet}"
METHOD="${1:-get_state}"
ARGS="${2:-{\}}"

ARGS_B64="$(printf '%s' "$ARGS" | base64 -w0)"

curl -sS "$RPC" -X POST -H 'Content-Type: application/json' -d "$(printf \
  '{"jsonrpc":"2.0","id":"state","method":"query","params":{"request_type":"call_function","finality":"final","account_id":"%s","method_name":"%s","args_base64":"%s"}}' \
  "$CONTRACT" "$METHOD" "$ARGS_B64")" |
  python3 -c '
import json, sys

r = json.load(sys.stdin)
if "error" in r:
    sys.exit("rpc error: " + r["error"].get("message", "?"))

d = r["result"]
if "result" not in d:
    sys.exit("no result: " + json.dumps(d)[:400])

raw = bytes(d["result"])
sys.stderr.write("block %s  ·  %d bytes\n" % (d.get("block_height", "?"), len(raw)))
try:
    text = raw.decode()
except UnicodeDecodeError:
    sys.stdout.buffer.write(raw)
    sys.exit(0)


def pretty(t):
    """Some views return a JSON string that holds JSON (ft_metadata does); unwrap it."""
    try:
        v = json.loads(t)
    except ValueError:
        return t
    if isinstance(v, str):
        try:
            v = json.loads(v)
        except ValueError:
            return v
    return json.dumps(v, indent=2)


print(pretty(text))
'
