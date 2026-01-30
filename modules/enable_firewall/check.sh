#!/bin/bash
command -v ufw &>/dev/null || exit 2
ufw status 2>/dev/null | grep -qi "active" && exit 0 || exit 1
