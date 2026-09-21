#!/bin/bash
[ -f /etc/sysctl.d/99-lockd-hardening.conf ] && exit 0 || exit 1
