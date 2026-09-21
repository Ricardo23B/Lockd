#!/bin/bash
systemctl is-active apparmor &>/dev/null || exit 1
TOOL=$(command -v apparmor_status || command -v aa-status 2>/dev/null)
[ -z "$TOOL" ] && exit 2
"$TOOL" 2>/dev/null | grep -q "enforce" && exit 0 || exit 1
