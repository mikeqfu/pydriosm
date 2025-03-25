"""
Tests the :py:class:`pydriosm.downloader._bbbike.BBBikeDownloader` class.
"""

import os

import pandas as pd
import pytest
from pyhelpers.dirs import delete_dir

from pydriosm.downloader._bbbike import BBBikeDownloader


class TestBBBikeDownloader:

    @pytest.fixture(scope='class')
    def bbd(self):
        return BBBikeDownloader()

    def test_init(self, bbd):
        assert bbd.NAME == 'BBBike'
        assert bbd.LONG_NAME == 'BBBike exports of OpenStreetMap data'
        assert bbd.URL == 'https://download.bbbike.org/osm/bbbike/'
        assert os.path.relpath(bbd.download_dir) == os.path.normpath('osm_data/bbbike')

        bbd_ = BBBikeDownloader(download_dir="tests/osm_data")
        assert os.path.relpath(bbd_.download_dir) == os.path.normpath('tests/osm_data')

        assert isinstance(bbd.valid_subregion_names, list)
        assert isinstance(bbd.subregion_coordinates, pd.DataFrame)
        assert isinstance(bbd.subregion_index, pd.DataFrame)
        assert isinstance(bbd.catalogue, dict)

    @pytest.mark.parametrize('update', [True, False])
    def test_get_names_of_cities(self, bbd, update, monkeypatch, capfd):
        monkeypatch.setattr('builtins.input', lambda _: "Yes")
        bbbike_cities = bbd.get_bbbike_cities(update=update, verbose=True)
        out, _ = capfd.readouterr()
        if update:
            assert "Retrieving/compiling the data" in out and "Done." in out
        assert isinstance(bbbike_cities, list)

    @pytest.mark.parametrize('update', [True, False])
    def test_get_coordinates_of_cities(self, bbd, update, monkeypatch):
        monkeypatch.setattr('builtins.input', lambda _: "Yes")
        coords_of_cities = bbd.get_coordinates_of_cities(update=update, verbose=True)
        assert isinstance(coords_of_cities, pd.DataFrame)
        assert coords_of_cities.columns.to_list() == [
            'city',
            'real_name',
            'pref_language',
            'local_language',
            'country',
            'area_or_continent',
            'population',
            'step',
            'other_cities',
            'll_longitude',
            'll_latitude',
            'ur_longitude',
            'ur_latitude']

    @pytest.mark.parametrize('update', [True, False])
    def test_get_subregion_index(self, bbd, update, monkeypatch):
        monkeypatch.setattr('builtins.input', lambda _: "Yes")
        subregion_index = bbd.get_subregion_index(update=update, verbose=True)

        assert isinstance(subregion_index, pd.DataFrame)
        assert subregion_index.columns.to_list() == ['name', 'last_modified', 'url']

    def test_get_valid_subregion_names(self, bbd):
        assert isinstance(bbd.get_valid_subregion_names(), list)

    def test_validate_subregion_name(self, bbd):
        subregion_name = 'birmingham'
        assert bbd.validate_subregion_name(subregion_name=subregion_name) == 'Birmingham'

    def test_get_subregion_catalogue(self, bbd, capfd):
        subregion_name = 'birmingham'

        bham_dwnld_cat = bbd.get_sub_catalogue(
            subregion_name=subregion_name, confirmation_required=False, verbose=True)
        out, _ = capfd.readouterr()
        assert 'Retrieving/compiling data of a download catalogue for "Birmingham" ... Done.' in out
        assert isinstance(bham_dwnld_cat, pd.DataFrame)
        assert bham_dwnld_cat.columns.to_list() == [
            'filename', 'url', 'data_type', 'size', 'last_update']

    def test_get_catalogue(self, bbd):
        bbbike_catalogue = bbd.get_catalogue()
        assert list(bbbike_catalogue.keys()) == ['FileFormat', 'DataType', 'Catalogue']

        catalogue = bbbike_catalogue['Catalogue']
        assert isinstance(catalogue, dict)

        bham_catalogue = catalogue['Birmingham']
        assert isinstance(bham_catalogue, pd.DataFrame)

    @pytest.mark.parametrize('osm_file_format', ['PBF', '.osm.pbf'])
    def test_validate_file_format(self, bbd, osm_file_format):
        assert bbd.validate_file_format(osm_file_format=osm_file_format) == '.pbf'

    def test_get_subregion_download_url(self, bbd):
        subrgn_name = 'birmingham'
        file_format = "pbf"

        subrgn_name_, dwnld_url = bbd.get_subregion_download_url(subrgn_name, file_format)
        assert subrgn_name_ == 'Birmingham'
        assert dwnld_url == 'https://download.bbbike.org/osm/bbbike/Birmingham/Birmingham.osm.pbf'

        file_format = "csv.xz"
        subrgn_name_, dwnld_url = bbd.get_subregion_download_url(subrgn_name, file_format)

        assert subrgn_name_ == 'Birmingham'
        assert dwnld_url == \
               'https://download.bbbike.org/osm/bbbike/Birmingham/Birmingham.osm.csv.xz'

    def test_get_valid_download_info(self, bbd):
        subrgn_name = 'birmingham'
        file_format = "pbf"

        info = bbd.get_valid_download_info(subrgn_name, file_format)
        valid_subrgn_name, pbf_filename, dwnld_url, pbf_pathname = info

        assert valid_subrgn_name == 'Birmingham'
        assert pbf_filename == 'Birmingham.osm.pbf'
        assert dwnld_url == 'https://download.bbbike.org/osm/bbbike/Birmingham/Birmingham.osm.pbf'
        assert os.path.relpath(pbf_pathname) == 'osm_data\\bbbike\\birmingham\\Birmingham.osm.pbf'

        bbd_ = BBBikeDownloader(download_dir="tests\\osm_data")
        _, _, _, pbf_pathname = bbd_.get_valid_download_info(subrgn_name, file_format)
        assert os.path.relpath(pbf_pathname) == 'tests\\osm_data\\birmingham\\Birmingham.osm.pbf'

    def test_file_exists(self, bbd, tmp_path):
        subregion_name = 'birmingham'
        osm_file_format = ".pbf"

        pbf_exists = bbd.file_exists(
            subregion_name=subregion_name, osm_file_format=osm_file_format, data_dir=tmp_path)
        assert not pbf_exists

    def test_download_subregion_data(self, bbd, monkeypatch, capfd, tmp_path):
        subregion_name = 'leeds'

        monkeypatch.setattr('builtins.input', lambda _: "Yes")
        dwnld_paths = bbd.download_subregion_data(
            subregion_name=subregion_name, download_dir=tmp_path, ret_download_path=True,
            verbose=True)
        out, _ = capfd.readouterr()

        common_path = os.path.commonpath(dwnld_paths)
        assert common_path == os.path.normpath(f"{tmp_path}/leeds/")
        assert f'Check out the downloaded OSM data in' in out

        monkeypatch.setattr('builtins.input', lambda _: "Yes")
        delete_dir(tmp_path, verbose=True)

    def test_download_osm_data(self, bbd, monkeypatch, tmp_path):
        bbd.data_paths = []
        bbd.download_dir = bbd.cdd()

        subregion_name, osm_file_format = 'London', "pbf"

        monkeypatch.setattr('builtins.input', lambda _: "Yes")
        bbd.download_osm_data(
            subregion_names=subregion_name, osm_file_format=osm_file_format, download_dir=None,
            verbose=True)
        assert len(bbd.data_paths) == 1
        assert os.path.normpath('osm_data/bbbike/') in os.path.normpath(bbd.data_paths[0])

        london_download_dir = os.path.normpath(bbd.download_dir)
        assert os.path.normpath('osm_data/bbbike') in london_download_dir

        subregion_names, osm_file_format = ['leeds', 'birmingham'], "shp"

        monkeypatch.setattr('builtins.input', lambda _: "Yes")
        dwnld_paths = bbd.download_osm_data(
            subregion_names, osm_file_format, download_dir=tmp_path, ret_download_path=True)
        assert len(dwnld_paths) == 2
        assert len(bbd.data_paths) == 3
        assert os.path.normpath(bbd.download_dir) == os.path.normpath(tmp_path)
        assert os.path.normpath(os.path.commonpath(dwnld_paths)) == os.path.normpath(tmp_path)

        monkeypatch.setattr('builtins.input', lambda _: "Yes")
        delete_dir([os.path.dirname(london_download_dir), tmp_path], verbose=True)


if __name__ == '__main__':
    pytest.main()
