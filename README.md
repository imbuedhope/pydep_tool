# pydep-tool

Installing this package will install the `pydep` command which is a group of commands that enables
you to scan the code in your python repository to determine which packages (in your env) your code
actually depends on and to update dependencies tracked in the repo.

## How to use this tool

1. work on your python project (add / remove dependencies, etc.)
2. open a terminal at the root folder of your project
3. run `pydep update`
5. ???
6. profit

> NOTE: all the commands and subcommands support `--help`

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
4. the repo must have `requriements.txt`, `setup.cfg`, or `pyproject.toml` files at in
   the root folder for the update command to work
   1. while `setup.py` is (deprecated but) valid, this tool does not support in place modification
      of those files due to obvious reasons

## `pydep list`

This command scans the repository path (default `.`) and provides information about packages that
are used (directly through imports) in the repository and which python source files they are used
in. This command also lists any imports that could not be mapped to a package in the current
enviornment.

Imports are mapped to installed distributions using package files, standalone `.py` modules,
compiled extension modules, and `top_level.txt` metadata when available. This includes `cv2`
when an installed OpenCV distribution provides that module. An import such as
`from flask import jsonify` is attributed to Flask through its `flask` package; `jsonify`
does not need to be a separate module. Scanning does not import or execute these packages.

Packages must be installed in the Python environment running `pydep` and provide distribution
metadata. An importable system module without that metadata cannot be assigned a package name
and version automatically.

The most specific recorded module takes precedence over a parent package. Shared namespace
roots such as `google` and `azure` do not identify a single distribution: use concrete imports
such as `from google.cloud import storage` or `from azure.storage.blob import BlobClient`.
Namespace roots without an owning module, and modules provided by conflicting distributions
(for example, installing both OpenCV variants), are reported as unresolved. `pydep update`
leaves dependency files unchanged when any imports are unresolved.

Metadata-only editable installations are supported when they declare their import names in
`top_level.txt`. Editable installations without usable import metadata, dynamic imports, and
determining the existence of an attribute through package execution are outside the scanner's
static analysis. Stub-only `.pyi` files do not supply runtime modules.

## `pydep update`

Updates any `requriements.txt`, `setup.cfg`, or `pyproject.toml` files found at the specified
repository path (default `.`). The files must be formated as per their specific implementation
guidelines; however, if the dependencies or install_requires field is missing in `pyproject.toml` or
`setup.cfg` the update command will create them

## Running tests

The fast suite uses the standard library's `unittest` framework and temporary projects with real
distribution metadata. With this project and its dependencies installed, run from the repository
root:

```sh
python -m unittest discover -s tests -v
```

Coverage includes import aliases, relative and wildcard imports, source traversal, stdlib
boundaries, native module suffixes, shared namespaces, duplicate and missing metadata,
metadata in ZIP archives, and editable import names. CLI tests exercise every version mode
and output format, repeat updates to check idempotency, and verify that unresolved or
ambiguous imports do not change existing dependency files.

For the real-package smoke suite, use a separate virtual environment and install the test-only
fixtures (these are not application dependencies):

```sh
python -m venv /tmp/pydep-tests
. /tmp/pydep-tests/bin/activate
python -m pip install . -r tests/requirements-integration.txt
python -I -m unittest discover -s tests/integration -v
```

This suite checks installed Flask, OpenCV, Pillow, PyYAML, Beautiful Soup, python-dateutil,
scikit-learn, CFFI, six, Requests alongside its type stubs, and Google/Azure namespace packages.
It verifies that the libraries import successfully, that scanning does not import them, and
that the installed `pydep` command generates the expected dependency lists. The `-I` flag
keeps tests from accidentally loading the repository source instead of the installed package.

GitHub Actions runs on pull requests, pushes to `main`, and manual dispatch. It builds an sdist
and wheel and tests the installed wheel on Python 3.10–3.14 on Linux, plus Python 3.14 on
Windows and macOS. A separate Python 3.12 Linux job runs the real-package suite. Direct
fixture versions are pinned in `tests/requirements-integration.txt`; update them together with
the smoke tests when checking new library releases.
