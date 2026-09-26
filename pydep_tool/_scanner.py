"""
Functions used to scan a repo and environment to derive information about the projects dependencies
and related things
"""

import ast
from functools import lru_cache
import importlib.metadata as md
from importlib.machinery import EXTENSION_SUFFIXES
import os
import re
import sys
from typing import Dict, Set

from more_itertools import partition

def _dir_is_module(directory_path: str | os.PathLike):
    """
    returns true if the directory specified is a python module; i.e. it has an `__init__.py` file
    """
    return '__init__.py' in os.listdir(directory_path)

def get_imports_from_file(file_path: str | os.PathLike):
    """
    yields imported modules in the python source file specified by `file_path`
    """
    with open(file_path, 'r', encoding='utf-8') as file:
        root = ast.parse(file.read(), filename=file_path)

    for node in ast.walk(root):
        if isinstance(node, ast.Import):
            for name in node.names:
                yield str(name.name)
        elif isinstance(node, ast.ImportFrom):
            if node.level != 0:
                continue

            if node.module:
                for alias in node.names:
                    if alias.name != '*':
                        yield f'{node.module}.{alias.name}'
                    else:
                        yield str(node.module)

def get_imports_in_code_at(directory_path: str | os.PathLike) -> Dict[str | os.PathLike, Set[str]]:
    """
    returns a set of modules that are imported any modules that are present in the folder specified
    by `directory_path`
    """

    imports_by_file: Dict[str | os.PathLike, Set[str]] = {}

    _root_folder = True
    for subdir, dirs, files in os.walk(directory_path):
        if _root_folder:
            _root_folder = False

            # any .py files in the root folder are tracked
            for file in files:
                if file.endswith('.py'):
                    file_path = os.path.join(subdir, file)

                    if imports := get_imports_from_file(file_path):
                        imports_by_file[file_path] = set(imports)
            continue

        # check if the current subdir is a Python package
        if _dir_is_module(subdir):
            for file in files:
                if file.endswith('.py'):
                    file_path = os.path.join(subdir, file)

                    if imports := get_imports_from_file(file_path):
                        imports_by_file[file_path] = set(imports)
            # remove non-package directories from further traversal
            dirs[:] = [d for d in dirs if _dir_is_module(os.path.join(subdir, d))]
        else:
            # skip non-package directories
            dirs.clear()

    return imports_by_file

@lru_cache(maxsize=None)
def _is_not_stdlib_resource(res: str) -> bool:
    # if the res is a part of sys.stdlib_module_names then it's a builtin
    for mod in sys.stdlib_module_names:
        if res.startswith(mod) and (len(res) == len(mod) or res.startswith(mod+'.')):
            return False
    return True

def _distribution_identity(dist: md.Distribution):
    return re.sub(r'[-_.]+', '-', dist.name).lower(), dist.version

@lru_cache(maxsize=None)
def get_dist(res: str) -> md.Distribution | None:
    """
    returns dist associated with the specified resource
    returns None if a valid, unambiguous distribution can not be found
    """

    # a lil hack so mod_to_dist is "static" (and isn't a global so imports are fast)
    if not hasattr(get_dist, 'mod_to_dist'):
        mod_to_dist : Dict[str, md.Distribution | None] = {}
        for dist in md.distributions():
            # Keep file-level mappings for distributions with multiple packages, and include
            # standalone Python and extension modules such as cv2. No package code is imported.
            mods = set()
            for f in dist.files or ():
                parts = str(f).split('/')
                for suffix in ('.py', *EXTENSION_SUFFIXES):
                    if parts[-1].endswith(suffix):
                        parts[-1] = parts[-1][:-len(suffix)]
                        if parts[-1] == '__init__':
                            parts.pop()
                        if parts and all(part.isidentifier() for part in parts):
                            mods.add('.'.join(parts))
                        break

            # A declared root such as google is not an owner of every namespace sibling.
            # Keep declarations as a fallback for metadata-only and editable installations.
            roots_with_files = {mod.split('.')[0] for mod in mods}
            for root in (dist.read_text('top_level.txt') or '').split():
                if root.isidentifier() and root not in roots_with_files:
                    mods.add(root)

            for mod in mods:
                if mod not in mod_to_dist:
                    mod_to_dist[mod] = dist
                elif (previous := mod_to_dist[mod]) is not None:
                    # Duplicate discovery of the same distribution is harmless. Different
                    # providers of one module (e.g. two OpenCV variants) are ambiguous.
                    if _distribution_identity(previous) != _distribution_identity(dist):
                        mod_to_dist[mod] = None
        setattr(get_dist, 'mod_to_dist', mod_to_dist)
    else:
        mod_to_dist : Dict[str, md.Distribution | None] = getattr(get_dist, 'mod_to_dist')

    # Prefer a concrete child over a parent package, regardless of discovery order.
    # Attribute imports such as flask.jsonify still fall back to their owning package.
    mod = res
    while mod:
        if mod in mod_to_dist:
            return mod_to_dist[mod]
        mod = mod.rpartition('.')[0]

    return None

def get_res_info_by_file(path: str | os.PathLike):
    """
    returns resource info in a convoluted data structure
    """

    import_info_by_file = {}
    for file, resources in get_imports_in_code_at(path).items():
        stdlib_resources, non_stdlib_resources = partition(_is_not_stdlib_resource, resources)

        import_info_by_file[file] = {}
        for res in non_stdlib_resources:
            import_info_by_file[file][res] = {
                "dist": get_dist(res),
                "in_stdlib" : False
            }

        for res in stdlib_resources:
            import_info_by_file[file][res] = {
                "dist": None,
                "in_stdlib" : True
            }

    return import_info_by_file
