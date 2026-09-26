"""Smoke-test the installed wheel against real, separately installed distributions."""

import configparser
import importlib
from importlib import metadata
import os
from pathlib import Path
import subprocess
import sys
import sysconfig
import tempfile
import unittest

import tomlkit

from pydep_tool._scanner import get_res_info_by_file


# Module, distribution, and representative source import. Names deliberately differ.
CASES = [
    ('flask', 'Flask', 'from flask import jsonify'),
    ('cv2', 'opencv-python-headless', 'import cv2'),
    ('yaml', 'PyYAML', 'from yaml import safe_load'),
    ('PIL.Image', 'Pillow', 'from PIL import Image'),
    ('bs4', 'beautifulsoup4', 'from bs4 import BeautifulSoup'),
    ('dateutil.parser', 'python-dateutil', 'from dateutil import parser'),
    ('sklearn.linear_model', 'scikit-learn', 'from sklearn import linear_model'),
    ('google.cloud.storage', 'google-cloud-storage', 'from google.cloud import storage'),
    ('google.cloud.bigquery', 'google-cloud-bigquery', 'import google.cloud.bigquery'),
    ('google.protobuf.message', 'protobuf', 'from google.protobuf.message import Message'),
    ('azure.storage.blob', 'azure-storage-blob', 'from azure.storage.blob import BlobClient'),
    ('azure.core.exceptions', 'azure-core', 'from azure.core import exceptions'),
    ('cffi', 'cffi', 'from cffi import FFI'),
    ('_cffi_backend', 'cffi', 'import _cffi_backend'),
    ('requests', 'requests', 'from requests import Session'),
    ('six', 'six', 'from six import moves'),
]


class InstalledPackageTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.project = Path(temporary.name)
        (self.project / 'app.py').write_text('\n'.join(case[2] for case in CASES) + '\n', encoding='utf-8')
        self.cli = str(Path(sysconfig.get_path('scripts')) / ('pydep.exe' if os.name == 'nt' else 'pydep'))

    def run_cli(self, *arguments):
        return subprocess.run([self.cli, *arguments, str(self.project)],
                              capture_output=True, text=True, check=True)

    def test_real_libraries_are_importable_and_map_to_their_distributions(self):
        result = get_res_info_by_file(self.project)[str(self.project / 'app.py')]
        # Attribute imports may be represented with their complete dotted resource name.
        expected = {metadata.distribution(name).name for _, name, _ in CASES}
        self.assertTrue(all(info['dist'] is not None for info in result.values()), result)
        self.assertEqual({info['dist'].name for info in result.values()}, expected)
        # Also check each statement on its own, so swapping namespace owners cannot pass.
        for module, distribution, source in CASES:
            with self.subTest(module=module):
                (self.project / 'single.py').write_text(source + '\n', encoding='utf-8')
                resources = get_res_info_by_file(self.project)[str(self.project / 'single.py')]
                self.assertEqual({info['dist'].name for info in resources.values()},
                                 {metadata.distribution(distribution).name})
                importlib.import_module(module)
        self.assertIsNotNone(metadata.distribution('types-requests'))

    def test_scanning_does_not_import_inspected_libraries(self):
        # A fresh interpreter keeps this independent of test order and import caches.
        code = '''
import sys
from pydep_tool._scanner import get_res_info_by_file
before = set(sys.modules)
get_res_info_by_file(sys.argv[1])
roots = {'flask', 'cv2', 'yaml', 'PIL', 'bs4', 'dateutil', 'sklearn',
         'google', 'azure', 'cffi', '_cffi_backend', 'requests', 'six'}
loaded = {name.split('.')[0] for name in set(sys.modules) - before}
assert not roots & loaded, roots & loaded
'''
        result = subprocess.run([sys.executable, '-I', '-c', code, str(self.project)],
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_installed_cli_updates_every_format_and_mode(self):
        expected_names = {metadata.distribution(name).name for _, name, _ in CASES}
        listed = self.run_cli('list')
        self.assertEqual(listed.stderr, '')
        for name in expected_names:
            self.assertIn(name, listed.stdout)
        files = [self.project / name for name in ['requirements.txt', 'setup.cfg', 'pyproject.toml']]
        for path in files:
            path.write_text('', encoding='utf-8')
        for mode, operator in [('eq', '=='), ('compat', '~='), ('gt', '>=')]:
            with self.subTest(mode=mode):
                self.run_cli('update', '--mode', mode)
                expected = sorted(f'{name}{operator}{metadata.version(name)}' for name in expected_names)
                self.assertEqual(files[0].read_text().splitlines(), expected)
                config = configparser.ConfigParser()
                config.read(files[1])
                self.assertEqual(config['options']['install_requires'].split(), expected)
                self.assertEqual(tomlkit.parse(files[2].read_text())['project']['dependencies'], expected)
                previous = [path.read_bytes() for path in files]
                self.run_cli('update', '--mode', mode)
                self.assertEqual([path.read_bytes() for path in files], previous)
