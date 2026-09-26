import configparser
from unittest.mock import patch

from click.testing import CliRunner
import tomlkit

from pydep_tool import pydep
from support import DistributionTestCase


class CliTests(DistributionTestCase):
    def setUp(self):
        super().setUp()
        self.project = self.root / 'project'
        self.project.mkdir()
        self.source = self.project / 'app.py'
        self.source.write_text('import os\nimport yaml\nfrom PIL import Image\nimport yaml as y\n', encoding='utf-8')
        self.yaml = self.distribution('PyYAML', ['yaml/__init__.py'], version='6.0')
        self.pillow = self.distribution('Pillow', ['PIL/__init__.py'], version='11.0')
        scanner = patch('pydep_tool._scanner.md.distributions', return_value=[self.yaml, self.pillow])
        scanner.start()
        self.addCleanup(scanner.stop)
        self.runner = CliRunner()
        self.files = [self.project / name for name in ['requirements.txt', 'setup.cfg', 'pyproject.toml']]

    def prepare_files(self, with_dependency_fields=True):
        requirements, config, project = self.files
        requirements.write_text('old==0\n', encoding='utf-8')
        config.write_text('[metadata]\nname = keep-me\n' + (
            '[options]\ninstall_requires = old==0\n' if with_dependency_fields else ''), encoding='utf-8')
        project.write_text('# retain this comment\n[project]\nname = "keep-me"\n' + (
            'dependencies = ["old==0"]\n' if with_dependency_fields else ''), encoding='utf-8')

    def test_every_mode_and_format_is_sorted_deduplicated_and_idempotent(self):
        for mode, operator in [('eq', '=='), ('compat', '~='), ('gt', '>=')]:
            for fields in [True, False]:
                with self.subTest(mode=mode, existing_fields=fields):
                    self.prepare_files(fields)
                    expected = [f'Pillow{operator}11.0', f'PyYAML{operator}6.0']
                    command = ['update', '--mode', mode, str(self.project)]
                    result = self.runner.invoke(pydep, command)
                    self.assertEqual(result.exit_code, 0, result.output)
                    self.assertEqual(self.files[0].read_text().splitlines(), expected)
                    config = configparser.ConfigParser()
                    config.read(self.files[1])
                    self.assertEqual(config['options']['install_requires'].split(), expected)
                    self.assertEqual(config['metadata']['name'], 'keep-me')
                    project = tomlkit.parse(self.files[2].read_text())
                    self.assertEqual(project['project']['dependencies'], expected)
                    self.assertEqual(project['project']['name'], 'keep-me')
                    self.assertIn('# retain this comment', self.files[2].read_text())
                    originals = [path.read_bytes() for path in self.files]
                    result = self.runner.invoke(pydep, command)
                    self.assertEqual(result.exit_code, 0, result.output)
                    self.assertEqual([path.read_bytes() for path in self.files], originals)

    def test_unresolved_import_leaves_all_formats_unchanged(self):
        self.prepare_files()
        self.source.write_text('import yaml\nimport unavailable_package\n', encoding='utf-8')
        originals = [path.read_bytes() for path in self.files]
        result = self.runner.invoke(pydep, ['update', str(self.project)])
        self.assertEqual(result.exit_code, 1, result.output)
        self.assertIn('could not be mapped', result.output)
        self.assertEqual([path.read_bytes() for path in self.files], originals)
        listed = self.runner.invoke(pydep, ['list', str(self.project)])
        self.assertEqual(listed.exit_code, 0, listed.output)
        self.assertIn('unavailable_package', listed.output)
        self.assertIn('PyYAML', listed.output)

    def test_ambiguous_distribution_does_not_overwrite_dependencies(self):
        self.prepare_files()
        self.source.write_text('import cv2\n', encoding='utf-8')
        normal = self.distribution('opencv-python', ['cv2/__init__.py'])
        headless = self.distribution('opencv-python-headless', ['cv2/__init__.py'])
        originals = [path.read_bytes() for path in self.files]
        with patch('pydep_tool._scanner.md.distributions', return_value=[normal, headless]):
            result = self.runner.invoke(pydep, ['update', str(self.project)])
        self.assertEqual(result.exit_code, 1, result.output)
        self.assertIn('could not be mapped', result.output)
        self.assertEqual([path.read_bytes() for path in self.files], originals)

    def test_syntax_error_leaves_all_formats_unchanged(self):
        self.prepare_files()
        self.source.write_text('from (invalid syntax\n', encoding='utf-8')
        originals = [path.read_bytes() for path in self.files]
        result = self.runner.invoke(pydep, ['update', str(self.project)])
        self.assertNotEqual(result.exit_code, 0)
        self.assertIsInstance(result.exception, SyntaxError)
        self.assertEqual([path.read_bytes() for path in self.files], originals)

    def test_stdlib_only_project_clears_stale_dependencies(self):
        self.prepare_files()
        self.source.write_text('import sys\nfrom pathlib import Path\n', encoding='utf-8')
        result = self.runner.invoke(pydep, ['update', str(self.project)])
        self.assertEqual(result.exit_code, 0, result.output)
        self.assertEqual(self.files[0].read_text(), '')
        config = configparser.ConfigParser()
        config.read(self.files[1])
        self.assertEqual(config['options']['install_requires'].strip(), '')
        self.assertEqual(tomlkit.parse(self.files[2].read_text())['project']['dependencies'], [])

    def test_update_does_not_create_missing_dependency_files(self):
        result = self.runner.invoke(pydep, ['update', str(self.project)])
        self.assertEqual(result.exit_code, 0, result.output)
        self.assertTrue(all(not path.exists() for path in self.files))
