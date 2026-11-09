#!/usr/bin/env bash
# Fail if the agent guides have drifted apart. AGENTS.md is canonical; CLAUDE.md
# and .cursor/rules/opencg.mdc carry the same body under their own title, note
# and (for the .mdc) front matter. The body starts at "You are working on".
set -euo pipefail

cd "$(dirname "$0")/.."

body() {
  local text
  text="$(sed -n '/^You are working on/,$p' "$1")"
  [ -n "$text" ] || { echo "✗ $1 has no line starting 'You are working on'" >&2; exit 1; }
  printf '%s\n' "$text"
}

canonical="$(body AGENTS.md)"
status=0
for copy in CLAUDE.md .cursor/rules/opencg.mdc; do
  if ! diff -u --label AGENTS.md --label "$copy" <(printf '%s\n' "$canonical") <(body "$copy"); then
    echo "✗ $copy differs from AGENTS.md; copy the body across so all three match" >&2
    status=1
  fi
done
[ "$status" -eq 0 ] && echo "✓ AGENTS.md, CLAUDE.md and .cursor/rules/opencg.mdc bodies match"
exit "$status"
