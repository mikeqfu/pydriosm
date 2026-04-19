import os

import pytest
from pyhelpers.dirs import cd

from pydriosm.reader._base import BaseReader
from pydriosm.reader._shp import SHP


class TestBaseReader:

    @pytest.fixture(scope='class')
    def base_reader(self):
        # base_reader = BaseReader()
        return BaseReader()

    def test_init(self, base_reader):
        assert base_reader.NAME == 'OSM Reader'
        assert isinstance(base_reader.SHP, type) and base_reader.SHP == SHP

    @staticmethod
    def test_cdd():
        assert os.path.normpath(BaseReader.cdd()) == os.path.normpath(cd('osm_data'))

    def test_data_dir(self, base_reader):
        assert os.path.relpath(base_reader.data_dir) == 'osm_data'

        r1 = BaseReader(data_source='geofabrik')
        assert os.path.relpath(r1.data_dir) == os.path.join("osm_data", "geofabrik")

        r2 = BaseReader(data_source='bbbike')
        assert os.path.relpath(r2.data_dir) == os.path.join("osm_data", "bbbike")

    def test_data_paths(self, base_reader):
        assert base_reader.data_paths == []


if __name__ == '__main__':
    pytest.main()
