from importlib import metadata
from importlib.machinery import EXTENSION_SUFFIXES
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from click.testing import CliRunner

from pydep_tool import pydep
from pydep_tool._scanner import get_dist, get_imports_from_file


class ImportResolutionTests(unittest.TestCase):
    def setUp(self):
        self.clear_cache()
        self.addCleanup(self.clear_cache)
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)

    @staticmethod
    def clear_cache():
        get_dist.cache_clear()
        if hasattr(get_dist, 'mod_to_dist'):
            del get_dist.mod_to_dist

    def distribution(self, name, files=(), top_level=None):
        info = self.root / (name + '-1.2.dist-info')
        info.mkdir()
        (info / 'METADATA').write_text(f'Name: {name}\nVersion: 1.2\n')
        if files:
            (info / 'RECORD').write_text(''.join(f'{file},,\n' for file in files))
        if top_level is not None:
            (info / 'top_level.txt').write_text(top_level)
        return metadata.PathDistribution(info)

    def test_native_cv2_module_without_package_initializer(self):
        for suffix in EXTENSION_SUFFIXES:
            with self.subTest(suffix=suffix):
                self.clear_cache()
                dist = self.distribution('opencv-' + str(EXTENSION_SUFFIXES.index(suffix)), ['cv2' + suffix])
                with patch('pydep_tool._scanner.md.distributions', return_value=[dist]):
                    self.assertIs(get_dist('cv2'), dist)
                    self.assertIsNone(get_dist('cv2_other'))

    def test_top_level_metadata_without_file_list(self):
        dist = self.distribution('opencv-python', top_level='cv2\n')
        self.assertIsNone(dist.files)
        with patch('pydep_tool._scanner.md.distributions', return_value=[dist]):
            self.assertIs(get_dist('cv2'), dist)

    def test_standalone_python_module(self):
        dist = self.distribution('example-dist', ['example.py'])
        with patch('pydep_tool._scanner.md.distributions', return_value=[dist]):
            self.assertIs(get_dist('example'), dist)

    def test_flask_attribute_resolves_through_its_package(self):
        dist = self.distribution('Flask', ['flask/__init__.py'])
        with patch('pydep_tool._scanner.md.distributions', return_value=[dist]):
            self.assertIs(get_dist('flask.jsonify'), dist)

    def test_missing_metadata_does_not_prevent_other_matches(self):
        missing = self.distribution('missing')
        flask = self.distribution('Flask', ['flask/__init__.py'])
        with patch('pydep_tool._scanner.md.distributions', return_value=[missing, flask]):
            self.assertIs(get_dist('flask.jsonify'), flask)
            self.assertIsNone(get_dist('unknown'))

    def test_multiple_packages_in_one_distribution(self):
        dist = self.distribution('setuptools', ['setuptools/__init__.py', 'pkg_resources/__init__.py'])
        with patch('pydep_tool._scanner.md.distributions', return_value=[dist]):
            self.assertIs(get_dist('setuptools'), dist)
            self.assertIs(get_dist('pkg_resources'), dist)

    def test_metadata_and_external_scripts_are_not_modules(self):
        dist = self.distribution('example', ['example-1.2.dist-info/setup.py', '../../../bin/helper.py'])
        with patch('pydep_tool._scanner.md.distributions', return_value=[dist]):
            self.assertIsNone(get_dist('setup'))
            self.assertIsNone(get_dist('helper'))

    def test_list_and_update_resolve_cv2_and_flask_attributes(self):
        opencv = self.distribution('opencv-python', ['cv2' + EXTENSION_SUFFIXES[0]])
        flask = self.distribution('Flask', ['flask/__init__.py'])
        project = self.root / 'project'
        project.mkdir()
        source = project / 'app.py'
        source.write_text('import cv2 as cv\nfrom flask import jsonify as response\n')
        requirements = project / 'requirements.txt'
        requirements.write_text('')
        self.assertEqual(set(get_imports_from_file(source)), {'cv2', 'flask.jsonify'})
        with patch('pydep_tool._scanner.md.distributions', return_value=[opencv, flask]):
            listed = CliRunner().invoke(pydep, ['list', str(project)])
            updated = CliRunner().invoke(pydep, ['update', str(project)])
        self.assertEqual(listed.exit_code, 0, listed.output)
        self.assertNotIn('unable to find packages', listed.output)
        self.assertIn('opencv-python', listed.output)
        self.assertIn('Flask', listed.output)
        self.assertEqual(updated.exit_code, 0, updated.output)
        self.assertEqual(requirements.read_text(), 'Flask==1.2\nopencv-python==1.2\n')


if __name__ == '__main__':
    unittest.main()
