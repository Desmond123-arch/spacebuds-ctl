#!/usr/bin/env bash
# tmux status segment: Spacebuds battery, e.g. "🎧 L100 R99".
# Each real read opens a Bluetooth connection through Windows Python, so results are
# cached; unreachable buds (connected to the phone, out of range) show "🎧 --".
# Set BUDS_CMD to override the backend command (used for testing).
dir=$(dirname "$(readlink -f "$0")")
cache=${XDG_CACHE_HOME:-$HOME/.cache}/buds_battery
ttl_ok=120
ttl_fail=45

mkdir -p "$(dirname "$cache")"
ts=0 text=--
[[ -f $cache ]] && IFS=$'\t' read -r ts text <"$cache"
age=$(($(date +%s) - ts))
ttl=$ttl_ok
[[ $text == -- ]] && ttl=$ttl_fail

# The buds accept one Bluetooth client at a time: keep out of the way while the TUI is open.
if ((age < ttl)) || pgrep -f '^[^ ]*python[^ ]* .*buds_tui\.py' >/dev/null; then
  echo "🎧 $text"
  exit 0
fi

exec 9>"$cache.lock"
if ! flock -n 9; then
  echo "🎧 $text"
  exit 0
fi

if [[ -n $BUDS_CMD ]]; then
  read -r -a cmd <<<"$BUDS_CMD"
else
  cmd=(python.exe "$(wslpath -w "$dir/buds.py")")
fi

out=$(cd /mnt/c 2>/dev/null && timeout 25 "${cmd[@]}" --json status 2>/dev/null | tr -d '\r')
text=$(printf '%s' "$out" | python3 -c '
import json, sys
try:
    b = json.loads(sys.stdin.read().strip().splitlines()[-1])["battery"]
    l, r, c = b["left"]["percent"], b["right"]["percent"], b["case"]["percent"]
    print(f"L{l} R{r}" + (f" C{c}" if c else ""))
except Exception:
    print("--")
')
printf '%s\t%s\n' "$(date +%s)" "$text" >"$cache"
echo "🎧 $text"
