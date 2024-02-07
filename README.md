# Wizard Ware

Installing this package will install the `spell` command which is a group of commands that lets you
do some useful stuff that I've found handy (it's just one atm, but I'll add more over time).

# `spell pydeps`

This command scans your python project for dependencies based on the active env and the import
statements in the code, and outputs them. This is cleaner than using `pip freeze`.

1. work on your python project (add / remove dependencies, etc.)
2. open a terminal at the root folder of your project; i.e. the folder that contains your `setup.py`
   and similar (where the folder that defines your module is present)
3. run `spell pydeps`
5. ???
6. profit

> you can use `spell pydeps --update` to update files in place
