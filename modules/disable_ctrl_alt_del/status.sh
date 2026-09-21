#!/bin/bash
systemctl is-enabled ctrl-alt-del.target 2>/dev/null | grep -q "masked" && exit 0 || exit 1
