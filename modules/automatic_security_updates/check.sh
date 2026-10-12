#!/bin/bash
grep -q '"1"' "${LOCKD_SYSROOT:-}/etc/apt/apt.conf.d/20auto-upgrades" 2>/dev/null && exit 0 || exit 1
