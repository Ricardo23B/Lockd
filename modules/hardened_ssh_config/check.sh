#!/bin/bash
[ -f /etc/ssh/sshd_config.d/99-lockd-hardening.conf ] && exit 0 || exit 1
