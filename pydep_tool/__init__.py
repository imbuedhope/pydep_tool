"""
"""

import click
import importlib.metadata as md
import sys
from typing import Dict, Set

from ._scanner import get_imports_in_modules_at

__all__ = ['pydep']

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

