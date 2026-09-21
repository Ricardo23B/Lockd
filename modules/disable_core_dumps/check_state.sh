#!/bin/bash
[ -f /etc/security/limits.d/lockd-coredumps.conf ] && exit 0 || exit 1
