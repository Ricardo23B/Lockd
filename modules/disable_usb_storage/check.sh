#!/bin/bash
BL="/etc/modprobe.d/lockd-usb-storage.conf"
[ -f "$BL" ] && grep -q "blacklist usb-storage" "$BL" && exit 0 || exit 1
