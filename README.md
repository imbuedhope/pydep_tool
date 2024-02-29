# pydep-tool

Installing this package will install the `pydep` command which is a group of commands that enables
you to scan the code in your python repository to determine which packages (in your env) your code
actually depends on update dependencies.

## How to use this tool

1. work on your python project (add / remove dependencies, etc.)
2. open a terminal at the root folder of your project
3. run `pydep update`
5. ???
6. profit

> NOTE: all the commands and subcommands support `--help`, `-h`, & `-?` which includes information
> that may not be covered here.

## Requirements

Your repo must be structured according to PEP recommendations. In specifc the following critera must
be met.

1. any modules that are "released" as part of the repo must be top level folders (i.e. in the root
   folder) and contain a `__init__.py` file
2. any submodules must contain a `__init__.py` file and submodules should not skip folder levels;
   i.e. you can't have `a/b/c/__init__.py` without `a/b/__init__.py`
3. tests and other standalone scripts must be in their own top level folders that are not modules
   1. you may implement modules inside those folders, but the top level folder not being a module
      is how this tool determines if a folder should be ignored when looking for dependencies
4. the repo must has `requriements.txt`, `setup.cfg`, (inclusive) or `pyproject.toml` files at in
   the root folder
   1. while `setup.py` is (deprecated but) valid, this tool does not support in place modification
      of those files due to obvious reasons

## `pydep list`

This command scans the repository path (default `.`) and provides information about packages that
are used (directly through imports) in the repository and which python source files they are used
in. This command also lists any imports that could not be mapped to a package in the current
enviornment.

## `pydep update`

Updates any `requriements.txt`, `setup.cfg`, or `pyproject.toml` files found at the specified
repository path (default `.`). The files must be formated as per their specific implementation
guidelines; however, if the dependencies or install_requires field is missing in `pyproject.toml` or
`setup.cfg` the update command will create them
