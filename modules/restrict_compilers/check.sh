#!/bin/bash
GCC=$(command -v gcc 2>/dev/null)
[ -z "$GCC" ] && exit 2
stat -c "%G" "$GCC" 2>/dev/null | grep -q "compiler" && exit 0 || exit 1
