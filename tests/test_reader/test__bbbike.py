import os

import pytest
from pyhelpers.dirs import delete_dir

from pydriosm.errors import InvalidSubregionNameError
from pydriosm.reader._bbbike import BBBikeReader


class TestBBBikeReader:

    @pytest.fixture(scope='class')
    def bbr(self):
        # bbr = BBBikeReader()
        return BBBikeReader()

    def test_get_file_path(self, bbr, monkeypatch, tmp_path):
        osm_file_format = ".pbf"

        with pytest.raises(InvalidSubregionNameError):
            subregion_name = 'rutland'
            _ = bbr.get_file_path(subregion_name, osm_file_format, tmp_path)

        subregion_name = 'birmingham'
        path_to_pbf = bbr.get_file_path(subregion_name, osm_file_format, tmp_path)
        assert not os.path.isfile(path_to_pbf)

        monkeypatch.setattr('builtins.input', lambda _: "Yes")
        bbr.downloader.download_data(subregion_name, osm_file_format, tmp_path, verbose=True)

        path_to_pbf = bbr.get_file_path(subregion_name, osm_file_format, tmp_path)
        assert os.path.isfile(path_to_pbf)

        assert path_to_pbf.startswith(str(tmp_path))

        monkeypatch.setattr('builtins.input', lambda _: "Yes")
        delete_dir(tmp_path, verbose=True)


if __name__ == '__main__':
    pytest.main()
