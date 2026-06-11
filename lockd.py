#!/usr/bin/env python3
"""Shim de desarrollo: `python3 lockd.py`. El código real vive en lockd/entry.py
(instalable por pip; el console script `lockd` apunta a lockd.entry:main)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from lockd.entry import main  # noqa: E402

if __name__ == "__main__":
    main()
