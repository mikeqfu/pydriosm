"""Tests the class: :class:`pydriosm.downloader._geofabrik.GeofabrikDownloader`."""

import os

import pandas as pd
import pytest
from pyhelpers.dirs import delete_dir

from pydriosm.downloader._geofabrik import GeofabrikDownloader


class TestGeofabrikDownloader:

    SUBREGION_TABLE_COLUMN_NAMES = [
        'subregion',
        'subregion-url',
        '.osm.pbf',
        '.osm.pbf-size',
        '.gpkg.zip',
        '.shp.zip',
        '.osm.bz2',
    ]

    @pytest.fixture(scope='class')
    def gfd(self):
        # gfd = GeofabrikDownloader()
        return GeofabrikDownloader()

    def test_init(self, gfd):
        assert gfd.NAME == 'Geofabrik'
        assert gfd.URL == 'https://download.geofabrik.de/'
        assert gfd.DOWNLOAD_INDEX_URL == f'{gfd.URL}index-v1.json'
        assert os.path.relpath(gfd.download_dir) == os.path.join("osm_data", "geofabrik")

        download_dir = os.path.join("tests", "osm_data")

        gfd_ = GeofabrikDownloader(download_dir=download_dir)
        assert os.path.relpath(gfd_.download_dir) == download_dir

        assert isinstance(gfd.valid_subregion_names, set)
        assert isinstance(gfd.download_index, pd.DataFrame)
        assert isinstance(gfd.continent_tables, dict)
        assert isinstance(gfd.region_subregion_tiers, dict)
        assert isinstance(gfd.having_no_subregions, list)
        assert isinstance(gfd.catalogue, pd.DataFrame)

    def test_get_raw_directory_index(self, gfd, capfd):
        raw_index = gfd.get_raw_directory_index(url=gfd.URL, verbose=True)
        out, _ = capfd.readouterr()
        assert "Collecting the raw directory index on 'https://download.geofabrik.de/' ... " in out
        assert "Failed." in out
        assert raw_index is None

        uk_url = 'https://download.geofabrik.de/europe/united-kingdom.html'
        raw_index = gfd.get_raw_directory_index(url=uk_url, verbose=True)
        out, _ = capfd.readouterr()
        assert f"Collecting the raw directory index on '{uk_url}' ... Done." in out
        assert isinstance(raw_index, pd.DataFrame)
        assert set(raw_index.columns) == {'file', 'date', 'size', 'metric_file_size', 'url'}

    @pytest.mark.parametrize('update', [True, False])
    def test_get_download_index(self, gfd, update, monkeypatch, capfd):
        monkeypatch.setattr('builtins.input', lambda _: "Yes")
        download_index = gfd.get_download_index(update=update, verbose=True)
        out, _ = capfd.readouterr()
        if update:
            assert "Retrieving/compiling the data" in out and "Done." in out
        assert isinstance(download_index, pd.DataFrame)
        col_names = {
            'id', 'parent', 'iso3166-1:alpha2', 'name', 'iso3166-2',
            'geometry', '.osm.pbf', '.shp.zip', 'pbf-internal', 'history', 'taginfo', 'updates'
        }
        assert all(x in col_names for x in download_index.columns)

        monkeypatch.setattr('builtins.input', lambda _: "No")
        download_index = gfd.get_download_index(update=True, verbose=True)
        out, _ = capfd.readouterr()
        assert "Cancelled" in out
        assert download_index is None

    def test_get_subregion_table(self, gfd, capfd):
        homepage = gfd.get_subregion_table(url=gfd.URL, verbose=True)
        out, _ = capfd.readouterr()
        assert "Compiling a subregion list" in out and "Done." in out

        assert isinstance(homepage, pd.DataFrame)
        assert all(x in self.SUBREGION_TABLE_COLUMN_NAMES for x in homepage.columns)

        uk_url = 'https://download.geofabrik.de/europe/united-kingdom.html'
        uk = gfd.get_subregion_table(uk_url, verbose=True)
        assert isinstance(uk, pd.DataFrame)

        antarctica_url = 'https://download.geofabrik.de/antarctica.html'
        antarctica = gfd.get_subregion_table(antarctica_url, verbose=True, raise_error=True)
        out, _ = capfd.readouterr()
        assert 'Compiling a subregion list of "Antarctica" ... Failed.' in out
        assert antarctica is None

        with pytest.raises(AttributeError, match="'NoneType' object has no attribute 'empty'"):
            antarctica2 = gfd.get_subregion_table(antarctica_url, verbose=2, raise_error=True)
            out, _ = capfd.readouterr()
            assert 'Compiling a subregion list of "Antarctica" ... Failed.' in out
            assert antarctica2 is None

    @pytest.mark.parametrize('update', [True, False])
    def test_get_continent_tables(self, gfd, update):
        continent_tables = gfd.get_continent_tables(
            update=update, confirmation_required=False, verbose=True)
        assert isinstance(continent_tables, dict)

        asia_table = continent_tables['Asia']
        assert all(x in self.SUBREGION_TABLE_COLUMN_NAMES for x in asia_table.columns)

    @pytest.mark.parametrize('update', [True, False])
    def test_get_region_subregion_tiers(self, gfd, update):
        rgn_subrgn_tier, no_subrgn_list = gfd.get_region_subregion_tiers(
            update=update, confirmation_required=False, verbose=True)
        assert isinstance(rgn_subrgn_tier, dict)
        assert isinstance(no_subrgn_list, list)

    @pytest.mark.parametrize('update', [True, False])
    def test_get_catalogue(self, gfd, update, monkeypatch):
        monkeypatch.setattr('builtins.input', lambda _: "Yes")
        download_catalog = gfd.get_catalogue(update=update, verbose=True)
        assert isinstance(download_catalog, pd.DataFrame)
        assert len(download_catalog) >= 450
        assert all(x in self.SUBREGION_TABLE_COLUMN_NAMES for x in download_catalog.columns)

    @pytest.mark.parametrize('update', [True, False])
    def test_get_valid_subregion_names(self, gfd, update):
        valid_subrgn_names = gfd.get_valid_subregion_names(
            update=update, confirmation_required=False, verbose=True)
        assert isinstance(valid_subrgn_names, set)

    def test_validate_subregion_name(self, gfd):
        input_subrgn_name = 'london'
        valid_subrgn_name = gfd.validate_subregion_name(subregion_name=input_subrgn_name)
        assert valid_subrgn_name == 'Greater London'

        input_subrgn_name = 'https://download.geofabrik.de/europe/great-britain.html'
        valid_subrgn_name = gfd.validate_subregion_name(subregion_name=input_subrgn_name)
        assert valid_subrgn_name == 'Great Britain'

    def test_validate_file_format(self, gfd):
        input_file_format = ".pbf"
        valid_file_format = gfd.validate_file_format(osm_file_format=input_file_format)
        assert valid_file_format == '.osm.pbf'

        input_file_format = "shp"
        valid_file_format = gfd.validate_file_format(osm_file_format=input_file_format)
        assert valid_file_format == '.shp.zip'

        input_file_format = "geopackage"
        valid_file_format = gfd.validate_file_format(osm_file_format=input_file_format)
        assert valid_file_format == '.gpkg.zip'

    def test_get_subregion_download_url(self, gfd):
        subrgn_name = 'England'
        file_format = ".pbf"
        valid_name, download_link = gfd.get_subregion_download_url(subrgn_name, file_format)
        assert valid_name == 'England'
        assert download_link.endswith('united-kingdom/england-latest.osm.pbf')

        subrgn_name = 'britain'
        file_format = ".shp"
        valid_name, download_link = gfd.get_subregion_download_url(subrgn_name, file_format)
        assert valid_name == 'Great Britain'
        assert download_link is None

    def test_get_default_filename(self, gfd, capfd):
        subrgn_name, file_format = 'london', ".pbf"
        default_fn = gfd.get_default_filename(subrgn_name, file_format)
        assert default_fn == 'greater-london-latest.osm.pbf'

        subrgn_name, file_format = 'britain', ".shp"
        default_fn = gfd.get_default_filename(subrgn_name, file_format)
        out, _ = capfd.readouterr()
        assert out == 'No .shp.zip data is available to download for "Great Britain".\n'
        assert default_fn is None

    def test_get_default_pathname(self, gfd):
        subrgn_name, file_format = 'london', ".pbf"

        pathname, filename = gfd.get_default_pathname(subrgn_name, file_format)
        assert os.path.relpath(os.path.dirname(pathname)) == os.path.join(
            "osm_data", "geofabrik", "europe", "united-kingdom", "england", "greater-london")
        assert filename == 'greater-london-latest.osm.pbf'

    def test_get_subregions(self, gfd):
        all_subrgn_names = gfd.get_subregions()
        assert isinstance(all_subrgn_names, list)

        e_na_subrgn_names = gfd.get_subregions('england', 'n america')
        assert isinstance(e_na_subrgn_names, list)

        na_subrgn_names = gfd.get_subregions('n america', deep=True)
        assert isinstance(na_subrgn_names, list)

        gb_subrgn_names = gfd.get_subregions('britain')
        gb_subrgn_names_ = gfd.get_subregions('britain', deep=True)
        assert len(gb_subrgn_names_) >= len(gb_subrgn_names)

    def test_specify_sub_download_dir(self, gfd):
        subrgn_name = 'london'
        file_format = ".pbf"

        download_dir = gfd.specify_sub_download_dir(subrgn_name, file_format)
        assert os.path.dirname(os.path.relpath(download_dir)) == os.path.join(
            "osm_data", "geofabrik", "europe", "united-kingdom", "england", "greater-london")

        download_dir = os.path.join("tests", "osm_data")

        subrgn_name = 'britain'
        file_format = ".shp"

        download_pathname = gfd.specify_sub_download_dir(
            subregion_name=subrgn_name, osm_file_format=file_format, download_dir=download_dir)
        assert os.path.relpath(download_pathname) == os.path.join(
            "tests", "osm_data", "great-britain-shp-zip")

        gfd_ = GeofabrikDownloader(download_dir=download_dir)
        download_pathname_ = gfd_.specify_sub_download_dir(subrgn_name, file_format)
        assert os.path.relpath(download_pathname_) == os.path.join(
            "tests", "osm_data", "europe", "great-britain", "great-britain-shp-zip")

    def test_get_valid_download_info(self, gfd):
        subrgn_name = 'london'
        file_format = "pbf"

        valid_subrgn_name, pbf_filename, download_url, path_to_pbf = gfd.get_valid_download_info(
            subrgn_name, file_format)

        assert valid_subrgn_name == 'Greater London'
        assert pbf_filename == 'greater-london-latest.osm.pbf'
        assert download_url == \
               'https://download.geofabrik.de/europe/united-kingdom/england/' \
               'greater-london-latest.osm.pbf'
        assert os.path.relpath(path_to_pbf) == os.path.join(
            "osm_data", "geofabrik", "europe", "united-kingdom", "england", "greater-london",
            "greater-london-latest.osm.pbf")

        download_dir = os.path.join("tests", "osm_data")

        _, _, _, path_to_pbf2 = gfd.get_valid_download_info(subrgn_name, file_format, download_dir)

        assert os.path.relpath(path_to_pbf2) == os.path.join(
            "tests", "osm_data", "greater-london", "greater-london-latest.osm.pbf")

        gfd_ = GeofabrikDownloader(download_dir=download_dir)

        _, _, _, path_to_pbf3 = gfd_.get_valid_download_info(subrgn_name, file_format)

        assert os.path.relpath(path_to_pbf3) == os.path.join(
            "tests", "osm_data", "europe", "united-kingdom", "england", "greater-london",
            "greater-london-latest.osm.pbf")

    def test_download_data(self, gfd, monkeypatch, capfd, tmp_path):
        subregion_names = ['rutland', 'Isle of Wight']
        osm_file_format = ".pbf"

        monkeypatch.setattr('builtins.input', lambda _: "Yes")
        gfd.download_data(
            subregion_names=subregion_names, osm_file_formats=osm_file_format, verbose=True)
        out, _ = capfd.readouterr()
        assert "Saving " in out and "Done." in out
        assert len(gfd.data_paths) == 2
        assert os.path.relpath(gfd.download_dir) == os.path.join("osm_data", "geofabrik")

        download_dir = os.path.dirname(gfd.download_dir)

        delete_dir(download_dir, confirmation_required=False, verbose=True)

        subregion_names = 'west yorkshire'
        osm_file_format = ".shp"

        # import tempfile; tmp_path = tempfile.mkdtemp()
        gfd.download_data(
            subregion_names=subregion_names, osm_file_formats=osm_file_format,
            download_dir=tmp_path, confirmation_required=False, verbose=True)
        out, _ = capfd.readouterr()
        assert "No '.shp.zip' data is available for \"West Yorkshire\"." in out
        assert len(gfd.data_paths) == 2

        osm_file_format = ".geopackage"
        gfd.download_data(
            subregion_names=subregion_names, osm_file_formats=osm_file_format,
            download_dir=tmp_path, confirmation_required=False, verbose=True)
        assert len(gfd.data_paths) == 3
        assert os.path.normpath(gfd.data_paths[-1]) == os.path.join(
            tmp_path, "west-yorkshire", "west-yorkshire-latest-free.gpkg.zip")
        assert os.path.normpath(gfd.download_dir) == str(tmp_path)
        assert os.path.relpath(gfd.cdd()) == os.path.join("osm_data", "geofabrik")

        delete_dir(tmp_path, confirmation_required=False, verbose=True)

        subrgn_name = 'England'
        file_format = ".pbf"
        download_dir = "tests/osm_data"

        monkeypatch.setattr('builtins.input', lambda _: "Yes")
        download_file_pathnames = gfd.download_data(
            subrgn_name, file_format, download_dir=download_dir, deep=True, update=True,
            verbose=True, ret_download_path=True)

        assert len(download_file_pathnames) > 40
        assert os.path.commonpath(download_file_pathnames) == os.path.normpath(gfd.download_dir)

        delete_dir(gfd.download_dir, confirmation_required=False)


if __name__ == '__main__':
    pytest.main()
