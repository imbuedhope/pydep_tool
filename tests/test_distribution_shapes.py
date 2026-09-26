from itertools import permutations
from importlib import metadata
from unittest.mock import patch
import zipfile

from pydep_tool._scanner import get_dist
from support import DistributionTestCase


class DistributionShapeTests(DistributionTestCase):
    def assert_resolutions_in_any_order(self, distributions, expected):
        for ordering in permutations(distributions):
            with self.subTest(order=[dist.name for dist in ordering]):
                self.clear_cache()
                with patch('pydep_tool._scanner.md.distributions', return_value=ordering):
                    for resource, owner in expected.items():
                        with self.subTest(resource=resource):
                            self.assertIs(get_dist(resource), owner)

    def test_google_namespace_does_not_steal_sibling_imports(self):
        protobuf = self.distribution('protobuf', ['google/protobuf/__init__.py'], 'google\n')
        storage = self.distribution('google-cloud-storage', ['google/cloud/storage/__init__.py'], 'google\n')
        bigquery = self.distribution('google-cloud-bigquery', ['google/cloud/bigquery/__init__.py'], 'google\n')
        self.assert_resolutions_in_any_order([protobuf, storage, bigquery], {
            'google.protobuf': protobuf,
            'google.protobuf.message.Message': protobuf,
            'google.cloud.storage.Client': storage,
            'google.cloud.bigquery.Client': bigquery,
            'google.cloud.not_installed': None,
            'google.cloud.storage_extra': None,
            'google': None,
            'google.cloud': None,
        })

    def test_namespace_without_top_level_metadata(self):
        core = self.distribution('azure-core', ['azure/core/__init__.py'])
        blob = self.distribution('azure-storage-blob', ['azure/storage/blob/__init__.py'])
        self.assert_resolutions_in_any_order([core, blob], {
            'azure.core.exceptions': core,
            'azure.storage.blob.BlobClient': blob,
            'azure.storage.queue': None,
            'azure': None,
        })

    def test_most_specific_package_wins_over_regular_parent(self):
        # Legacy namespace packages may include a shared parent __init__.py.
        parent = self.distribution('legacy-core', ['legacy/__init__.py'])
        plugin = self.distribution('legacy-plugin', ['legacy/plugin/__init__.py'])
        self.assert_resolutions_in_any_order([parent, plugin], {
            'legacy': parent, 'legacy.plugin.Client': plugin,
        })

    def test_conflicting_opencv_distributions_are_unresolved(self):
        normal = self.distribution('opencv-python', ['cv2/__init__.py'], 'cv2\n')
        headless = self.distribution('opencv-python-headless', ['cv2/__init__.py'], 'cv2\n')
        self.assert_resolutions_in_any_order([normal, headless], {
            'cv2': None, 'cv2.imread': None,
        })

    def test_ambiguous_child_does_not_fall_back_to_parent(self):
        parent = self.distribution('parent', ['example/__init__.py'])
        first = self.distribution('first', ['example/plugin.py'])
        second = self.distribution('second', ['example/plugin.py'])
        self.assert_resolutions_in_any_order([parent, first, second], {
            'example': parent, 'example.plugin.call': None,
        })

    def test_distribution_names_need_not_match_imports(self):
        shapes = {
            'Pillow': ('PIL/__init__.py', 'PIL.Image'),
            'PyYAML': ('yaml/__init__.py', 'yaml.safe_load'),
            'beautifulsoup4': ('bs4/__init__.py', 'bs4.BeautifulSoup'),
            'python-dateutil': ('dateutil/__init__.py', 'dateutil.parser.parse'),
            'scikit-learn': ('sklearn/__init__.py', 'sklearn.linear_model'),
            'six': ('six.py', 'six.moves'),
        }
        distributions = [self.distribution(name, [path]) for name, (path, _) in shapes.items()]
        with patch('pydep_tool._scanner.md.distributions', return_value=distributions):
            for dist, (_, resource) in zip(distributions, shapes.values()):
                with self.subTest(distribution=dist.name):
                    self.assertIs(get_dist(resource), dist)

    def test_stub_only_distribution_is_not_a_runtime_provider(self):
        stubs = self.distribution('types-requests', ['requests-stubs/__init__.pyi'], 'requests-stubs\n')
        with patch('pydep_tool._scanner.md.distributions', return_value=[stubs]):
            self.assertIsNone(get_dist('requests'))
            self.assertIsNone(get_dist('requests-stubs'))

    def test_invalid_top_level_names_are_ignored(self):
        invalid = self.distribution('invalid', top_level='../outside\n/absolute\nbad-name\n')
        with patch('pydep_tool._scanner.md.distributions', return_value=[invalid]):
            for resource in ['../outside', '/absolute', 'bad-name']:
                self.assertIsNone(get_dist(resource))

    def test_editable_metadata_can_supply_names_without_source_records(self):
        editable = self.distribution('editable-project', ['__editable__.project.pth'], 'actual_name\n')
        with patch('pydep_tool._scanner.md.distributions', return_value=[editable]):
            self.assertIs(get_dist('actual_name.function'), editable)

    def test_missing_and_empty_file_lists(self):
        missing = self.distribution('missing')
        empty = self.distribution('empty', [])
        real = self.distribution('real', ['real.py'])
        self.assert_resolutions_in_any_order([missing, empty, real], {'real': real, 'missing': None})

    def test_duplicate_metadata_does_not_make_a_distribution_ambiguous(self):
        dist = self.distribution('one', ['one.py'])
        duplicate = metadata.PathDistribution(self.root / 'one-1.2.dist-info')
        with patch('pydep_tool._scanner.md.distributions', return_value=[dist, duplicate]):
            self.assertIs(get_dist('one'), dist)

    def test_metadata_inside_zip_archive(self):
        archive = self.root / 'zipped.zip'
        with zipfile.ZipFile(archive, 'w') as package:
            package.writestr('zipped-1.2.dist-info/METADATA', 'Name: zipped\nVersion: 1.2\n')
            package.writestr('zipped-1.2.dist-info/RECORD', 'zipped.py,,\n')
            package.writestr('zipped.py', 'raise RuntimeError("do not import")\n')
        distributions = list(metadata.distributions(path=[str(archive)]))
        self.assertEqual(len(distributions), 1)
        with patch('pydep_tool._scanner.md.distributions', return_value=distributions):
            self.assertIs(get_dist('zipped.function'), distributions[0])
