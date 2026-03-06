#!/usr/bin/env bash
set -euo pipefail

# oh-my-librpa installer (chat-first)
#
# Optional env vars:
# - OH_MY_LIBRPA_SOURCE: local source dir containing this repo
# - OH_MY_LIBRPA_REPO: git URL used when source dir is not present
# - OH_MY_LIBRPA_WORKSPACE: override OpenClaw workspace dir
# - OH_MY_LIBRPA_SKIP_RESTART=1: skip gateway restart

say() { printf "[oh-my-librpa] %s\n" "$*"; }
fail() { printf "[oh-my-librpa] ERROR: %s\n" "$*" >&2; exit 1; }

command -v openclaw >/dev/null 2>&1 || fail "openclaw command not found. Install OpenClaw first."

source_dir="${OH_MY_LIBRPA_SOURCE:-}"
if [[ -z "$source_dir" ]]; then
  script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
  if [[ -d "$script_dir/skills" ]]; then
    source_dir="$script_dir"
  fi
fi

tmp_dir=""
cleanup() {
  if [[ -n "$tmp_dir" && -d "$tmp_dir" ]]; then
    rm -rf "$tmp_dir"
  fi
}
trap cleanup EXIT

if [[ -z "$source_dir" ]]; then
  repo_url="${OH_MY_LIBRPA_REPO:-https://github.com/AroundPeking/oh-my-LibRPA.git}"
  tmp_dir="$(mktemp -d)"
  say "Cloning $repo_url"
  git clone --depth 1 "$repo_url" "$tmp_dir/repo" >/dev/null 2>&1 || fail "failed to clone $repo_url"
  source_dir="$tmp_dir/repo"
fi

[[ -d "$source_dir/skills" ]] || fail "skills directory not found in source: $source_dir"

workspace_dir="${OH_MY_LIBRPA_WORKSPACE:-}"
if [[ -z "$workspace_dir" ]]; then
  workspace_dir="$({ openclaw status --json 2>/dev/null || true; } | python3 - <<'PY' 2>/dev/null
import json, sys
raw = sys.stdin.read().strip()
if not raw:
    print("")
    raise SystemExit
def find_workspace(node):
    if isinstance(node, dict):
        value = node.get("workspaceDir")
        if isinstance(value, str) and value:
            return value
        for child in node.values():
            result = find_workspace(child)
            if result:
                return result
    elif isinstance(node, list):
        for child in node:
            result = find_workspace(child)
            if result:
                return result
    return ""
try:
    data = json.loads(raw)
except Exception:
    print("")
    raise SystemExit
print(find_workspace(data))
PY
)"
fi

if [[ -z "$workspace_dir" ]]; then
  workspace_dir="$HOME/.openclaw/workspace"
fi

skills_target="$workspace_dir/skills"
assets_target="$workspace_dir/oh-my-librpa"

say "Installing skills into $skills_target"
mkdir -p "$skills_target"
rsync -a "$source_dir/skills/" "$skills_target/"

say "Installing rulebook assets into $assets_target"
mkdir -p "$assets_target"
for dir in rules templates references docs scripts registry examples; do
  if [[ -d "$source_dir/$dir" ]]; then
    rsync -a "$source_dir/$dir/" "$assets_target/$dir/"
  fi
done

if [[ "${OH_MY_LIBRPA_SKIP_RESTART:-0}" != "1" ]]; then
  say "Restarting OpenClaw gateway"
  if ! openclaw gateway restart >/dev/null 2>&1; then
    say "Gateway restart failed; trying start"
    openclaw gateway start >/dev/null 2>&1 || true
  fi
fi

say "Install complete."
say "Now just chat naturally, e.g.:"
say "  Help me run GW for GaAs with a conservative setup first."
