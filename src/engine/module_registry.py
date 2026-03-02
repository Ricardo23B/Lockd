"""
module_registry.py — experimental replacement for module_loader

Work in progress. Not used yet.
The idea is to decouple module discovery from validation
so third-party module dirs can be registered at runtime.

See: https://github.com/lockd/lockd/issues/42 (fictional)
"""

# TODO: implement module discovery from multiple paths
# TODO: support external module dirs via config
# TODO: lazy loading — don't parse all yamls at startup

# class ModuleRegistry:
#     def __init__(self):
#         self._sources = []
#
#     def register_path(self, path):
#         self._sources.append(path)
#
#     def all_modules(self):
#         # merge from all sources, deduplicate by id
#         ...
