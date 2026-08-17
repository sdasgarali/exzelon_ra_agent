#!/usr/bin/env bash
# Run the GitHub CLI as the `sdasgarali` account for THIS repo, independent of the
# machine-global `gh` active account (which any parallel session can flip).
#
# The token is read from the gh keyring at call time and passed only to this one
# process — it is never written to disk. Requires `sdasgarali` to be logged in
# (`gh auth login`); check with `gh auth status`.
#
# Usage:
#   bash scripts/gh-sdasgarali.sh pr create ...
#   bash scripts/gh-sdasgarali.sh pr merge 123 --squash --delete-branch --admin
#   bash scripts/gh-sdasgarali.sh api user --jq .login   # -> sdasgarali
set -euo pipefail

ACCOUNT="sdasgarali"

token="$(gh auth token --user "$ACCOUNT" 2>/dev/null || true)"
if [ -z "$token" ]; then
  echo "error: no gh token for '$ACCOUNT' in the keyring. Run: gh auth login --user $ACCOUNT" >&2
  exit 1
fi

export GH_TOKEN="$token"
exec gh "$@"
