"""
Functions used to scan a repo and environment to derive information about the projects dependencies
and related things
"""

import ast
import base64
from functools import lru_cache
import hashlib
import importlib.metadata as md
from importlib.machinery import EXTENSION_SUFFIXES, PathFinder
import os
from pathlib import Path
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

def _path_finder_origin(module: str) -> Path | None:
    """Find a module file through Python's path finder without importing parents."""
    search_path = None
    name = ''
    for part in module.split('.'):
        name = f'{name}.{part}' if name else part
        spec = PathFinder.find_spec(name, search_path)
        if spec is None:
            return None
        search_path = spec.submodule_search_locations

    if not spec.has_location or not spec.origin:
        return None
    try:
        return Path(spec.origin).resolve(strict=True)
    except (OSError, TypeError, ValueError):
        return None

def _record_path(dist: md.Distribution, file: md.PackagePath) -> Path | None:
    try:
        return Path(dist.locate_file(file)).resolve(strict=True)
    except (OSError, TypeError, ValueError):
        return None

def _file_hash(path: Path, algorithm: str) -> str | None:
    if algorithm not in hashlib.algorithms_guaranteed:
        return None
    try:
        digest = hashlib.new(algorithm)
        with path.open('rb') as source:
            for chunk in iter(lambda: source.read(1024 * 1024), b''):
                digest.update(chunk)
        return base64.urlsafe_b64encode(digest.digest()).decode('ascii').rstrip('=')
    except (OSError, TypeError, ValueError):
        return None

def _resolve_active_provider(module: str, providers):
    """Resolve competing records only when path or content identifies one owner."""
    origin = _path_finder_origin(module)
    if origin is None:
        return None

    matches = []
    for dist, files in providers:
        for file in files:
            if _record_path(dist, file) == origin:
                matches.append((dist, file))

    if len(matches) == 1:
        return matches[0][0]
    if len(matches) < 2:
        return None

    # Overlaid wheels can share an initializer while shipping different code
    # beneath it. Check their common recorded files for a consistent owner.
    if len(matches) != len(providers):
        return None

    package_prefix = module.replace('.', '/') + '/' if origin.name.startswith('__init__.') else None
    records = []
    for dist, module_files in providers:
        if package_prefix:
            records.append({str(file): file for file in dist.files or ()
                            if str(file).startswith(package_prefix)})
        else:
            records.append({str(file): file for file in module_files})

    possible = set(range(len(providers)))
    hashed = {}
    for name in set.intersection(*(set(record) for record in records)):
        files = [record[name] for record in records]
        if any(file.hash is None for file in files):
            continue
        paths = [_record_path(dist, file)
                 for (dist, _), file in zip(providers, files)]
        if paths[0] is None or any(path != paths[0] for path in paths[1:]):
            continue
        matching = set()
        for index, file in enumerate(files):
            key = (paths[0], file.hash.mode)
            if key not in hashed:
                hashed[key] = _file_hash(*key)
            if hashed[key] == file.hash.value:
                matching.add(index)
        possible &= matching
        if not possible:
            return None

    return providers[next(iter(possible))][0] if len(possible) == 1 else None

@lru_cache(maxsize=None)
def get_dist(res: str) -> md.Distribution | None:
    """
    returns dist associated with the specified resource
    returns None if a valid, unambiguous distribution can not be found
    """

    # a lil hack so mod_to_dist is "static" (and isn't a global so imports are fast)
    if not hasattr(get_dist, 'mod_to_dist'):
        mod_to_dist = {}
        for dist in md.distributions():
            # Keep file-level mappings for distributions with multiple packages, and include
            # standalone Python and extension modules such as cv2. No package code is imported.
            mods = {}
            for f in dist.files or ():
                parts = str(f).split('/')
                for suffix in ('.py', *EXTENSION_SUFFIXES):
                    if parts[-1].endswith(suffix):
                        parts[-1] = parts[-1][:-len(suffix)]
                        if parts[-1] == '__init__':
                            parts.pop()
                        if parts and all(part.isidentifier() for part in parts):
                            mods.setdefault('.'.join(parts), []).append(f)
                        break

            # A declared root such as google is not an owner of every namespace sibling.
            # Keep declarations as a fallback for metadata-only and editable installations.
            roots_with_files = {mod.split('.')[0] for mod in mods}
            for root in (dist.read_text('top_level.txt') or '').split():
                if root.isidentifier() and root not in roots_with_files:
                    mods.setdefault(root, [])

            for mod, files in mods.items():
                providers = mod_to_dist.setdefault(mod, {})
                identity = _distribution_identity(dist)
                if identity not in providers:
                    providers[identity] = (dist, files)
                else:
                    # Duplicate discovery of one distribution is not a conflict.
                    providers[identity][1].extend(files)
        setattr(get_dist, 'mod_to_dist', mod_to_dist)
    else:
        mod_to_dist = getattr(get_dist, 'mod_to_dist')

    # Prefer a concrete child over a parent package, regardless of discovery order.
    # Attribute imports such as flask.jsonify still fall back to their owning package.
    mod = res
    while mod:
        if mod in mod_to_dist:
            providers = list(mod_to_dist[mod].values())
            if len(providers) == 1:
                return providers[0][0]
            return _resolve_active_provider(mod, providers)
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
