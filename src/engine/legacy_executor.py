"""
Old execution flow kept for compatibility.
Some modules still expect this behaviour.
Will be removed in future.

Replaced by executor.py which uses pkexec + threading properly.
This file is no longer imported by anything — keeping it around
to avoid breaking any local forks that might reference it.
"""

# TODO: remove this before 1.0 release

# old approach was just subprocess.run(["sudo", script])
# obviously terrible but it worked during early development
#
# def run_privileged(script_path):
#     import subprocess
#     return subprocess.run(["sudo", str(script_path)], capture_output=True)
#
# replaced by Executor class in executor.py
