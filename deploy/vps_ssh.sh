#!/bin/bash
# Helper script for non-interactive SSH to VPS
# Usage: ./deploy/vps_ssh.sh "command to run on VPS"
#
# Auth: uses the passphrase-less deploy key (id_ed25519_deploy) so deploys run
# fully autonomously — no password, no passphrase, no prompts. The old root
# password / SSH_ASKPASS approach was removed (the password was rotated and is
# now rejected by the server).
#
# Override the key or host without editing this file:
#   VPS_SSH_KEY=~/.ssh/other_key ./deploy/vps_ssh.sh "..."
#   VPS_HOST=root@1.2.3.4        ./deploy/vps_ssh.sh "..."

VPS_HOST="${VPS_HOST:-root@187.124.74.175}"
VPS_SSH_KEY="${VPS_SSH_KEY:-$HOME/.ssh/id_ed25519_deploy}"

if [ ! -f "$VPS_SSH_KEY" ]; then
    echo "[vps_ssh] ERROR: SSH key not found: $VPS_SSH_KEY" >&2
    echo "[vps_ssh] Set VPS_SSH_KEY to the passphrase-less deploy key for $VPS_HOST." >&2
    exit 1
fi

# BatchMode=yes guarantees it never blocks on a prompt — if the key fails it
# errors out instead of falling back to an interactive password request.
exec ssh \
    -i "$VPS_SSH_KEY" \
    -o IdentitiesOnly=yes \
    -o BatchMode=yes \
    -o ConnectTimeout=30 \
    -o StrictHostKeyChecking=no \
    -o ServerAliveInterval=30 \
    "$VPS_HOST" "$@" < /dev/null
