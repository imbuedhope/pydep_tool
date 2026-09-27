# pydep-tool

Wares to perform dependency wizardry!

`pydep` scans the imports in your Python project, matches them to installed packages in the
**environment running `pydep`**, and helps keep your dependency declarations in step with your
code. It gives you the package names, installed versions, and source files behind those imports.
Handy for humans and coding agents alike: let the tool do the bookkeeping.

## Install

Requires Python **3.10 or newer**. Activate the environment you use for your project, then install:

```sh
python -m pip install 'git+https://github.com/imbuedhope/pydep_tool.git'
```

This installs the `pydep` command. Your project's dependencies should be installed in that same
Python environment so their distribution metadata and versions are available to the scanner.

## How to use this tool

1. Work on your Python project: add dependencies, remove dependencies, make cool things.
2. Open a terminal at the project root with its environment activated.
3. Run `pydep list` to see which installed packages your imports use.
4. Run `pydep update` to refresh the dependency files you maintain.
5. Review the diff and run your project's tests.
6. ???
7. Profit.

Both commands accept a repository path; it defaults to the current directory:

```sh
pydep list
pydep update
pydep list /path/to/project
pydep update --mode compat /path/to/project
```

> All commands and subcommands support `--help`. The wizard has documentation.

## Commands

### `pydep list [PATH]`

Prints a table of distribution names, installed versions, and the source files that reference them.
Standard-library imports are omitted. Imports that cannot be mapped to a distribution are reported
on stderr, while the table still shows the packages that were resolved. Listing does not modify
project files; unresolved imports alone do not make this command fail.

Import names and distribution names often differ. For example:

| Import in your code | Installed distribution |
| --- | --- |
| `from PIL import Image` | `Pillow` |
| `import yaml` | `PyYAML` |
| `from bs4 import BeautifulSoup` | `beautifulsoup4` |
| `import sklearn` | `scikit-learn` |
| `import cv2` | The installed OpenCV provider, such as `opencv-python-headless` |
| `from google.cloud import storage` | `google-cloud-storage` |

These mappings come from your environment's metadata; they are not a built-in package-name list.

### `pydep update [PATH]`

Writes a sorted dependency list using the distributions discovered in the source and their
installed versions. Every supported file that already exists at the repository root is updated:

| File | What gets replaced |
| --- | --- |
| `requirements.txt` | The entire file, with one dependency per line |
| `setup.cfg` | `install_requires` in the `[options]` section |
| `pyproject.toml` | `dependencies` in the `[project]` table |

Missing sections or dependency fields are created inside existing files. Missing files are not
created, and `setup.py` is not edited. With none of the supported files present, there is nothing
to write.

The generated entries replace the existing declarations in those locations. Handwritten extras,
environment markers, direct URLs, and requirements-file options or comments are not carried into
the new list. Optional dependency groups and build-system requirements are outside this update.
`setup.cfg` is rewritten using Python's configuration parser, so its comments and formatting may
also change. Give the diff a look before committing your freshly tidied dependencies.

If any imports are unresolved or have conflicting providers, `update` exits with an error before
changing dependency files. Run `pydep list` to see which imports need attention.

#### Version modes

Use `--mode` (or `-m`) to choose the version rule. Given an installed version of `2.4.1`:

| Mode | Generated requirement | Meaning |
| --- | --- | --- |
| `eq` (default) | `example==2.4.1` | Pin the installed version |
| `gt` | `example>=2.4.1` | Allow that version or newer |
| `compat` | `example~=2.4.1` | Use a [compatible-release constraint](https://packaging.python.org/en/latest/specifications/version-specifiers/#compatible-release) (`>=2.4.1,<2.5.0` in this example) |

```sh
pydep update --mode eq
pydep update -m gt
pydep update -m compat
```

The mode is your policy choice applied to the version in your environment. Compatibility with
other versions still needs your project's own validation.

## Project layout

The scanner uses a simple convention: scan Python files at the repository root, then descend
through package directories containing `__init__.py`. A directory without that file is skipped,
including everything beneath it. Directory names such as `tests` have no special meaning.

```text
my-project/
├── pyproject.toml
├── run.py                    # scanned: Python file at the root
├── my_package/
│   ├── __init__.py            # scanned
│   ├── service.py            # scanned
│   └── helpers/
│       ├── __init__.py        # needed to descend into helpers/
│       └── parsing.py        # scanned
├── tests/                    # skipped: no __init__.py here
│   └── test_service.py
└── .venv/                    # skipped: no __init__.py here
```

Keep tests and development scripts you want excluded in directories without `__init__.py` at
their top level. Each package level you want scanned needs its own `__init__.py`; an initializer
farther down does not make the scanner jump over a skipped parent.

This convention also means a plain `src/` directory or a namespace-only source directory is
skipped. Resolving an *installed dependency's* namespace packages, such as Google or Azure
libraries, is a separate part of the lookup and is supported.

## How it works

A little syntax-tree spelunking, a little package metadata, and no crystal ball:

1. **Walk the source.** Find `.py` files using the layout rules above.
2. **Read imports.** Parse each file with Python's `ast` module. Ordinary imports, aliases, and
   `from ... import ...` statements are collected, including imports inside functions and
   conditional blocks. Relative imports are skipped.
3. **Separate the standard library.** Use the running Python's standard-library module names
   to leave built-in dependencies out of the result.
4. **Look up installed distributions.** Read `importlib.metadata` records for package
   initializers, standalone `.py` modules, and native extensions such as `.so` or `.pyd` files.
   `top_level.txt` declarations provide a fallback for installations with limited file metadata.
5. **Find the owner.** Prefer the most specific recorded module over a parent package.
   `from flask import jsonify` maps through the `flask` package to Flask; `jsonify` does not need
   to be a separate module. Shared namespace roots such as `google` do not claim every sibling
   package. Conflicting providers of the same module are left unresolved.
6. **Report or write.** Group the results by distribution for `list`, or generate the dependency
   entries for `update` using your chosen version mode.

The source and inspected packages are never imported or executed during scanning. The result
reflects imports present in the scanned code and metadata in the active environment. It includes
conditional imports even when their branch would not run, and it does not expand each package's
transitive dependencies into your project's list.

The implementation lives in the [scanner](pydep_tool/_scanner.py) and [CLI](pydep_tool/__init__.py).

## When an import won't resolve

Start with `pydep list` and check the environment running the command:

- **Missing package or metadata:** install the dependency in that environment. A system module
  that is importable but has no distribution metadata cannot supply a package name and version.
- **Shared namespace:** use a concrete import such as `from google.cloud import storage`.
  A bare namespace without an owning module does not identify a distribution.
- **Conflicting providers:** keep the provider you intend to use. For example, multiple OpenCV
  distributions can all supply `cv2`, and the scanner will not pick one arbitrarily.
- **Editable installation:** usable import metadata is needed; a `top_level.txt` declaration can
  supply names when the source files are absent from the distribution's file list.

Relative imports are skipped, while absolute imports of your own packages go through the same
environment lookup as other absolute imports. Dynamic imports made through `importlib` or
`__import__`, plugin discovery, and runtime attribute validation are outside this static scan.
Stub-only `.pyi` files do not provide runtime modules.

## Development and tests

From a checkout, install the project into a development environment and run the fast suite:

```sh
python -m pip install .
python -I -m unittest discover -s tests -v
```

The `unittest` fixtures use temporary projects and distribution metadata to cover package layouts,
import syntax, native modules, shared namespaces, editable and ZIP metadata, and missing or
conflicting providers. CLI tests exercise every version mode and output format, repeated updates,
and unchanged dependency files when imports cannot be resolved.

For the real-package smoke suite, use a separate environment. For example, on a POSIX shell:

```sh
python -m venv /tmp/pydep-tests
. /tmp/pydep-tests/bin/activate
python -m pip install . -r tests/requirements-integration.txt
python -I -m unittest discover -s tests/integration -v
```

These test-only fixtures include Flask, OpenCV, Pillow, PyYAML, Beautiful Soup, python-dateutil,
scikit-learn, CFFI, six, Requests alongside its type stubs, and Google/Azure libraries. They check
real imports, metadata resolution without importing inspected packages, and the installed CLI.
The `-I` flag keeps these tests from loading checkout code in place of the installed package;
reinstall after changing the source.

[GitHub Actions](.github/workflows/tests.yml) runs on pull requests, pushes to `main`, and manual
dispatch. It builds an sdist and wheel, then tests the installed wheel on Python 3.10–3.14 on
Linux and Python 3.14 on Windows and macOS. A separate Python 3.12 Linux job runs the real-package
suite. Its direct fixture versions are pinned in
[`tests/requirements-integration.txt`](tests/requirements-integration.txt).
