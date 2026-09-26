from pathlib import Path
from unittest.mock import patch

from pydep_tool._scanner import get_imports_from_file, get_imports_in_code_at, get_res_info_by_file
from support import DistributionTestCase


class ScanningTests(DistributionTestCase):
    def test_import_syntax_preserves_resources_and_ignores_relative_imports(self):
        source = self.root / 'app.py'
        source.write_text('''import yaml as y, PIL.Image
from flask import jsonify as response, Flask
from google.cloud import storage
from requests import *
from . import local
from ..helpers import helper
if False:
    import sklearn
async def run():
    import cv2
''', encoding='utf-8')
        self.assertEqual(set(get_imports_from_file(source)), {
            'yaml', 'PIL.Image', 'flask.jsonify', 'flask.Flask',
            'google.cloud.storage', 'requests', 'sklearn', 'cv2',
        })

    def test_traversal_scans_packages_and_root_scripts_only(self):
        sources = {
            'app.py': 'import yaml',
            'package/__init__.py': 'import PIL',
            'package/sub/__init__.py': 'import bs4',
            'package/sub/worker.py': 'import six',
            'tests/test_app.py': 'import should_not_be_scanned',
            'tests/nested/__init__.py': 'import should_not_be_scanned',
            'package/data/nested/__init__.py': 'import should_not_be_scanned',
            '.venv/site/pkg/__init__.py': 'import should_not_be_scanned',
        }
        for name, source in sources.items():
            path = self.root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(source, encoding='utf-8')
        actual = get_imports_in_code_at(self.root)
        self.assertEqual({Path(file).relative_to(self.root).as_posix(): resources
                          for file, resources in actual.items()}, {
            'app.py': {'yaml'}, 'package/__init__.py': {'PIL'},
            'package/sub/__init__.py': {'bs4'}, 'package/sub/worker.py': {'six'},
        })

    def test_scan_never_executes_source_or_inspected_package(self):
        source = self.root / 'app.py'
        source.write_text('raise RuntimeError("must not execute")\nfrom dangerous import function\n', encoding='utf-8')
        package = self.root / 'dangerous'
        package.mkdir()
        (package / '__init__.py').write_text('raise RuntimeError("must not import")\n', encoding='utf-8')
        dist = self.distribution('dangerous-dist', ['dangerous/__init__.py'])
        with patch('pydep_tool._scanner.md.distributions', return_value=[dist]):
            result = get_res_info_by_file(self.root)
        self.assertIs(result[str(source)]['dangerous.function']['dist'], dist)

    def test_stdlib_names_are_not_confused_with_similar_third_party_names(self):
        source = self.root / 'app.py'
        source.write_text('import os.path, json, email.mime.text, jsonschema\n', encoding='utf-8')
        dist = self.distribution('jsonschema', ['jsonschema/__init__.py'])
        with patch('pydep_tool._scanner.md.distributions', return_value=[dist]):
            result = get_res_info_by_file(self.root)[str(source)]
        for name in ['os.path', 'json', 'email.mime.text']:
            self.assertTrue(result[name]['in_stdlib'])
            self.assertIsNone(result[name]['dist'])
        self.assertFalse(result['jsonschema']['in_stdlib'])
        self.assertIs(result['jsonschema']['dist'], dist)
