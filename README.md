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
      is how this tool determines if a dependency is for development use
4. the repo must has `requriements.txt`, `setup.cfg`, (inclusive) or `pyproject.toml` files at in
   the root folder
   1. while `setup.py` is (deprecated but) valid, this tool does not support in place modification
      of those files due to obviouss reasons

## `pydep list`

This command is scans the repository path (default `.`) and provides information about dependencies
in the repository.

> There are a number of optional flags that may be useful, if you are attempting to subscript this
> tool.

## `pydep update`

Updates any `requriements.txt`, `setup.cfg`, or `pyproject.toml` files found at the specified
repository path (default `.`)
