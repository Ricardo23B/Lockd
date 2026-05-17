#!/bin/bash
BL="/etc/modprobe.d/lockd-module-blacklist.conf"
[ -f "$BL" ] && grep -q "blacklist cramfs" "$BL" && exit 0 || exit 1
