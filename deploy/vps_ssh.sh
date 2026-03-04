#!/bin/bash
# Helper script for non-interactive SSH to VPS
# Usage: ./deploy/vps_ssh.sh "command to run on VPS"
export DISPLAY=:0
export SSH_ASKPASS="$(dirname "$0")/askpass.sh"
exec ssh -o ConnectTimeout=30 -o StrictHostKeyChecking=no -o PubkeyAuthentication=no root@187.124.74.175 "$@" < /dev/null
