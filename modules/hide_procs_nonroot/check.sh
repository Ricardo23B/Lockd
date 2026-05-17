#!/bin/bash
findmnt -n -o OPTIONS /proc 2>/dev/null | grep -q "hidepid" && exit 0 || exit 1
