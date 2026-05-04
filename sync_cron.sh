#!/bin/bash
# Install cron/eink.crontab onto the Pi, replacing only the marked
# "eink-managed" block. Other crontab entries on the Pi are preserved.
#
# Uses one ssh connection (single password prompt). The new managed-block
# content is base64-encoded into the remote command so quoting is safe.
set -euo pipefail

PI="juhani@kitchen.local"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
CRON_FILE="$SCRIPT_DIR/cron/eink.crontab"

[ -f "$CRON_FILE" ] || { echo "Missing $CRON_FILE"; exit 1; }

encoded=$(base64 < "$CRON_FILE" | tr -d '\n')

ssh "$PI" "
set -euo pipefail
new_block=\$(printf '%s' '$encoded' | base64 -d)
existing=\$(crontab -l 2>/dev/null || true)
cleaned=\$(printf '%s\n' \"\$existing\" | sed '/^# >>> eink-managed >>>/,/^# <<< eink-managed <<</d')
{
  [ -n \"\$cleaned\" ] && printf '%s\n' \"\$cleaned\"
  printf '%s' \"\$new_block\"
} | crontab -
echo '--- installed crontab ---'
crontab -l
"
