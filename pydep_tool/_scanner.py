"""
Functions used to scan a repo and environment to derive information about the projects dependencies
and related things
"""

import ast
import os

from typing import Set

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

def get_imports_in_modules_at(directory_path: str | os.PathLike) -> Set[str]:
    """
    returns a set of modules that are imported any modules that are present in the folder specified
    by `directory_path`
    """

    imports = set()

    _root_folder = True
    for subdir, dirs, files in os.walk(directory_path):
        if _root_folder:
            _root_folder = False

            # any .py files in the root folder are tracked
            for file in files:
                if file.endswith('.py'):
                    file_path = os.path.join(subdir, file)

                    imports.update(get_imports_from_file(file_path))
            continue

        # check if the current subdir is a Python package
        if _dir_is_module(subdir):
            for file in files:
                if file.endswith('.py'):
                    file_path = os.path.join(subdir, file)

                    imports.update(get_imports_from_file(file_path))
            # remove non-package directories from further traversal
            dirs[:] = [d for d in dirs if _dir_is_module(os.path.join(subdir, d))]
        else:
            # skip non-package directories
            dirs.clear()

    return imports

