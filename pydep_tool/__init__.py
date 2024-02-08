import ast
import click
import importlib.metadata as md
import os
import sys
from typing import Dict, Set

def _is_package(directory_path: str | os.PathLike):
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
        if _is_package(subdir):
            for file in files:
                if file.endswith('.py'):
                    file_path = os.path.join(subdir, file)

                    imports.update(get_imports_from_file(file_path))
            # remove non-package directories from further traversal
            dirs[:] = [d for d in dirs if _is_package(os.path.join(subdir, d))]
        else:
            # skip non-package directories
            dirs.clear()

    return imports

@click.group()
def pydep():
    """
    A simple python repository dependency management tool.
    """

@pydep.command()
@click.argument(
    "PATH", default='.',
    type = click.Path(exists=True, resolve_path=True)
)
def list(path):
    """
    Scans the PATH specified to detect dependencies based on imports in python code and the active
    python environment.
    """
    imported_resources = get_imports_in_modules_at(path)

    non_stdlib_resources: Set[str] = set()
    for res in imported_resources:
        # if the res is a part of sys.stdlib_module_names then it's a builtin
        for mod in sys.stdlib_module_names:
            if res.startswith(mod) and (len(res) == len(mod) or res.startswith(mod+'.')): break
        else:
            non_stdlib_resources.add(res)

    # generate a set of dists in use
    mod_to_dist : Dict[str, md.Distribution] = {}
    for dist in md.distributions():
        # this code scans the list of distribured files to find modules manually instead of
        # depending on python's built-in mechanism because the built-in mechanism does not work for
        # packages that have multiple top level modules such as `setuptools`
        mods = [
            '.'.join(fs[0:-1]) for f in dist.files
            if (fs := str(f).split('/'))[-1] == "__init__.py"
        ]

        mod_to_dist.update({mod : dist for mod in mods})

    used_dists: Set[md.Distribution] = set()
    for res in non_stdlib_resources:
        # see if we can find the resource that's being imported in mod_to_dist
        for mod in mod_to_dist:
            if res.startswith(mod) and (len(res) == len(mod) or res.startswith(mod+'.')):
                used_dists.add(mod_to_dist[mod])
                break
        else:
            click.echo(
                f"unable to find the package associated with {res} in the current env", err=True
            )

    for dist in used_dists:
        click.echo(f"{dist.name} == {dist.version}")

@pydep.command()
@click.argument(
    "PATH", default='.',
    type = click.Path(exists=True, resolve_path=True)
)
@click.option(
    "--mode", "-m", type=click.Choice(['compat','gt','eq']), default='eq',
    help="sets dynamic versioning mode"
)
def update(path, mode):
    """
    Updates `requirements.txt`, `setup.cfg`, and `pyproject.toml` files based on the dependencies
    that are found in the project.
    """

    _mode_to_op = {
        "compat" : "~=",
        "gt" : ">=",
        "eq" : "=="
    }

