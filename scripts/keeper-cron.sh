#!/usr/bin/env bash
# Cron wrapper for the public demo instance. Silent when there is nothing to do, so a scheduled job
# only reports when it actually ticked or re-locked.
#
#   */10 * * * *  /path/to/repo/scripts/keeper-cron.sh
#
# Uses only public contract methods: tick() and lock(). No admin path exists to call.

set -uo pipefail
cd "$(dirname "$0")/../demo" || exit 1

STATE_FILE="${STATE_FILE:-./canonical-account.json}" \
LOCK_EPOCHS="${LOCK_EPOCHS:-30}" \
node auto.mjs 2>&1
