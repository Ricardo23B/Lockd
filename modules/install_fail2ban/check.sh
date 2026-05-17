#!/bin/bash
command -v fail2ban-client &>/dev/null || exit 1
systemctl is-active fail2ban &>/dev/null && exit 0 || exit 1
