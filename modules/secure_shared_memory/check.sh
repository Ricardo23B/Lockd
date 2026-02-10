#!/bin/bash
findmnt -n -o OPTIONS /dev/shm 2>/dev/null | grep -q "noexec" && exit 0 || exit 1
