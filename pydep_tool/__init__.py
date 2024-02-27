"""
"""

import importlib.metadata as md
from os.path import relpath
from typing import Dict, List, Set

import click
from tabulate import tabulate

from ._scanner import get_res_info_by_file

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
    Scans the PATH specified to detects dependencies based on imports in python code and the active
    python environment.

    NOTE: This tool does not have knowledge of python packages that are not installed locally.
    Ensuring that the code at the specified PATH can be run / imported should generally resolve any
    related issues.
    """
    res_info = get_res_info_by_file(path)

    missing_resources: Set[str] = set()
    dist_info : Dict[md.Distribution, List[Set[str], Set[str]]]= {}
    # convert res_info into a table of package, version, used in
    # skip stdlib and unknowns
    for file, res_ in res_info.items():
        for res_name, res in res_.items():
            if res['in_stdlib']:
                pass
            elif not res['dist']:
                missing_resources.add(res_name)
            else:
                if res['dist'] in dist_info:
                    dist_info[res['dist']][0].add(res_name)
                    dist_info[res['dist']][1].add(relpath(file, path))
                else:
                    dist_info[res['dist']] = [set([res_name]), set([relpath(file, path)])]

    def _fmt_file_set(files: Set[str]):

        if len(files) > 1:
            return '\n'.join(files)
        elif len(files) == 0:
            return ''
        else:
            return next(iter(files))

    if missing_resources:
        click.echo(
            f"unable to find packages associated with one or more imports: {missing_resources}\n",
            err=True
        )

    table = prettytable.PrettyTable()
    table.set_style(prettytable.PLAIN_COLUMNS)
    table.align = 'l'
    table.field_names = ["package", "version", "referenced in"]
    table.sortby = "package"

    table.add_rows(
        (dist.name, dist.version, _fmt_file_set(info[1]))
        for dist, info in sorted(dist_info.items(), key=lambda x: x[0].name.lower())
    )

    click.echo(table)

    click.echo(tabulate(info, ["package", "version", "referenced in"], tablefmt="simple_grid"))

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

