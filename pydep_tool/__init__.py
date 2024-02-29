"""
"""

import configparser
import importlib.metadata as md
from os.path import relpath, isfile
from typing import Dict, List, Set

import click
import prettytable
import tomlkit

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

_mode_to_op = {
    "compat" : "~=",
    "gt" : ">=",
    "eq" : "=="
}

@pydep.command()
@click.argument(
    "PATH", default='.',
    type = click.Path(exists=True, resolve_path=True)
)
@click.option(
    "--mode", "-m", type=click.Choice(['compat','gt','eq']), default='eq',
    help="sets dynamic versioning mode (default 'eq')"
)
def update(path: str, mode: str):
    """
    Updates `requirements.txt`, `setup.cfg`, and `pyproject.toml` files based on the dependencies
    that are found in the project.
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

    if missing_resources:
        raise click.ClickException(
            "unable to update because some imports could not be mapped to packages\n"
            "run the `pydep list` for a set of missing imports\n"
            "this issue is likely because your env (or venv) is missing one or more packages"
        )

    op = _mode_to_op[mode]
    deps = [
        f"{dist.name}{op}{dist.version}"
        for dist, info in sorted(dist_info.items(), key=lambda x: x[0].name.lower())
    ]
    deps.sort()

    if isfile((fpath := path + '/requirements.txt')):
        # there is a requirements.txt file so we update it with the latest
        with open(fpath, 'w') as f:
            f.writelines(d+'\n' for d in deps)

    if isfile((fpath := path + '/setup.cfg')):
        config = configparser.ConfigParser()
        config.read(fpath)

        if 'options' not in config:
            config['options'] = {}

        config['options']['install_requires'] = ('\n' + '\n'.join(deps))
        with open(fpath, 'w') as f:
            config.write(f)

    if isfile((fpath := path + '/pyproject.toml')):
        # has pyproject.toml file
        with open(fpath, 'r') as f:
            prj = tomlkit.load(f)

        if 'project' not in prj:
            prj['project'] = {}


        _deps = tomlkit.array(deps)
        _deps.multiline(True)
        prj['project']['dependencies'] = _deps

        with open(fpath, 'w') as f:
            tomlkit.dump(prj, f)
