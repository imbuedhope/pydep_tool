import csv
from importlib import metadata
from pathlib import Path
import tempfile
import unittest

from pydep_tool._scanner import get_dist


class DistributionTestCase(unittest.TestCase):
    """Build real metadata records without importing fixture packages."""

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

    def distribution(self, name, files=None, top_level=None, version='1.2'):
        info = self.root / (name + '-' + version + '.dist-info')
        info.mkdir()
        (info / 'METADATA').write_text(f'Name: {name}\nVersion: {version}\n', encoding='utf-8')
        if files is not None:
            with (info / 'RECORD').open('w', newline='', encoding='utf-8') as record:
                csv.writer(record).writerows((file, '', '') for file in files)
            # Newer importlib.metadata versions filter out RECORD entries that do not
            # exist. Materialize the fixture without following external script paths.
            for file in files:
                path = (self.root / file).resolve()
                if path.is_relative_to(self.root):
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.touch(exist_ok=True)
        if top_level is not None:
            (info / 'top_level.txt').write_text(top_level, encoding='utf-8')
        return metadata.PathDistribution(info)
