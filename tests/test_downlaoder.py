"""Test the module :py:mod:`pydriosm.downloader`."""

import os
import tempfile

import pandas as pd
import pytest
from pyhelpers.dirs import delete_dir

from pydriosm.downloader import BBBikeDownloader, GeofabrikDownloader, _Downloader
from pydriosm.errors import InvalidFileFormatError, InvalidSubregionNameError

gfd, bbd = GeofabrikDownloader(), BBBikeDownloader()


class TestDownloader:

    @staticmethod
    def test_init():
        d = _Downloader()

        assert d.NAME == 'OSM Downloader'
        assert os.path.relpath(d.download_dir) == 'osm_data'
        assert os.path.relpath(d.cdd()) == 'osm_data'
        assert d.download_dir == d.cdd()

        d = _Downloader(download_dir="tests\\osm_data")
        assert os.path.relpath(d.download_dir) == 'tests\\osm_data'

    @staticmethod
    def test_cdd():
        assert os.path.relpath(_Downloader.cdd()) == 'osm_data'

    @staticmethod
    def test_compose_cfm_msg():
        assert _Downloader.compose_cfm_msg() == 'To compile data of <data_name>\n?'
        assert _Downloader.compose_cfm_msg(update=True) == 'To update the data of <data_name>\n?'

    @staticmethod
    def test_print_act_msg(capfd):
        assert _Downloader.print_act_msg(verbose=False) is None

        _Downloader.print_act_msg(verbose=True)
        print("Done.")
        out, _ = capfd.readouterr()
        assert out == 'Compiling the data ... Done.\n'

        _Downloader.print_act_msg(verbose=True, note="(Some notes here.)")
        print("Done.")
        out, _ = capfd.readouterr()
        assert out == 'Compiling the data (Some notes here.) ... Done.\n'

        _Downloader.print_act_msg(verbose=True, confirmation_required=False)
        print("Done.")
        out, _ = capfd.readouterr()
        assert out == 'Compiling data of <data_name> ... Done.\n'

    @staticmethod
    def test_print_otw_msg(capfd):
        assert _Downloader.print_otw_msg() is None

        _Downloader.print_otw_msg(verbose=True)
        out, _ = capfd.readouterr()
        assert out == 'Cancelled.\n'

        _Downloader.print_otw_msg(verbose=2)
        out, _ = capfd.readouterr()
        assert out == 'The collecting of <data_name> is cancelled, or no data is available.\n'

        _Downloader.print_otw_msg(verbose=True, error_message="Errors.")
        out, _ = capfd.readouterr()
        assert out == 'Failed. Errors.\n'

    @staticmethod
    @pytest.mark.parametrize('data_name', [None, '<data_name>'])
    def test_get_prepacked_data(data_name, monkeypatch, capfd):
        rslt = _Downloader.get_prepacked_data(
            callable, data_name=data_name, confirmation_required=False)
        assert rslt is None

        monkeypatch.setattr('builtins.input', lambda _: "No")
        rslt = _Downloader.get_prepacked_data(callable, verbose=True)
        out, _ = capfd.readouterr()
        assert 'Cancelled.' in out
        assert rslt is None

    @staticmethod
    def test_validate_subregion_name():
        with pytest.raises(InvalidSubregionNameError) as e:
            _Downloader.validate_subregion_name('abc')
            assert '1)' in e and '2)' in e

        with pytest.raises(InvalidSubregionNameError) as e:
            _Downloader.validate_subregion_name('abc', ['ab'])
            assert ' -> ' in e

        subrgn_name = 'usa'
        subrgn_name_ = _Downloader.validate_subregion_name(subrgn_name)
        assert subrgn_name_ == 'United States of America'

        avail_subrgn_names = ['Greater London', 'Great Britain', 'Birmingham', 'Leeds']

        subrgn_name = 'Britain'
        subrgn_name_ = _Downloader.validate_subregion_name(subrgn_name, avail_subrgn_names)
        assert subrgn_name_ == 'Great Britain'

        subrgn_name = 'london'
        subrgn_name_ = _Downloader.validate_subregion_name(subrgn_name, avail_subrgn_names)
        assert subrgn_name_ == 'Greater London'

    @staticmethod
    def test_validate_file_format():
        with pytest.raises(InvalidFileFormatError) as e:
            file_fmt = 'abc'
            _Downloader.validate_file_format(file_fmt)  # Raise an error
            assert "`osm_file_format='abc'` -> The input `osm_file_format` is unidentifiable." in e

        avail_file_fmts = ['.osm.pbf', '.shp.zip', '.osm.bz2']

        file_fmt = 'pbf'
        assert _Downloader.validate_file_format(file_fmt, avail_file_fmts) == '.osm.pbf'

        file_fmt = 'shp'
        assert _Downloader.validate_file_format(file_fmt, avail_file_fmts) == '.shp.zip'

    @staticmethod
    def test_get_default_sub_path():
        subrgn_name_ = 'London'
        dwnld_url = 'https://download.bbbike.org/osm/bbbike/London/London.osm.pbf'

        assert _Downloader.get_default_sub_path(subrgn_name_, dwnld_url) == '\\london'

    @staticmethod
    def test_make_subregion_dirname():
        subrgn_name_ = 'England'
        assert _Downloader.make_subregion_dirname(subrgn_name_) == 'england'

        subrgn_name_ = 'Greater London'
        assert _Downloader.make_subregion_dirname(subrgn_name_) == 'greater-london'

    @staticmethod
    def test_get_subregion_download_url():
        rslt = _Downloader.get_subregion_download_url('<subregion_name_>', '<download_url>')
        assert rslt == ('<subregion_name_>', '<download_url>')

    @staticmethod
    def test_get_valid_download_info():
        d = _Downloader()

        subregion_name, osm_file_format = 'subregion_name', 'osm_file_format'

        valid_dwnld_info = d.get_valid_download_info(subregion_name, osm_file_format)
        subregion_name_, osm_filename, download_url, file_pathname = valid_dwnld_info
        assert subregion_name_ == '<subregion_name_>'
        assert osm_filename == '<download_url>'
        assert download_url == '<download_url>'
        assert os.path.relpath(file_pathname) == 'osm_data\\<subregion_name_>\\<download_url>'

        d.download_dir = os.path.join(d.download_dir, '<subregion_name_>')
        _, _, _, file_pathname = d.get_valid_download_info(subregion_name, osm_file_format)
        assert os.path.relpath(file_pathname) == 'osm_data\\<subregion_name_>\\<download_url>'

        download_dir = 'x-osm-pbf'
        _, _, _, file_pathname = d.get_valid_download_info(
            subregion_name, osm_file_format, download_dir)
        assert os.path.relpath(file_pathname) == 'x-osm-pbf\\<download_url>'

        subregion_name, osm_file_format = '', ''
        _, osm_filename, _, file_pathname = d.get_valid_download_info(
            subregion_name=subregion_name, osm_file_format=osm_file_format)
        assert osm_filename is None and file_pathname is None

    @staticmethod
    def test_file_exists(capfd):
        d = _Downloader()

        subregion_name = '<subregion_name>'
        osm_file_format = 'shp'
        rslt = d.file_exists(subregion_name=subregion_name, osm_file_format=osm_file_format)
        assert not rslt

        subregion_name, osm_file_format = '', ''
        rslt = d.file_exists(
            subregion_name=subregion_name, osm_file_format=osm_file_format, verbose=2)
        out, _ = capfd.readouterr()
        assert 'None data for "None" is not available' in out
        assert not rslt

    @staticmethod
    def test_file_exists_and_more():
        subrgn_names, file_format = 'London', ".pbf"

        rslt = gfd.file_exists_and_more(subregion_names=subrgn_names, osm_file_format=file_format)
        assert rslt == (['Greater London'], '.osm.pbf', True, 'download', ['Greater London'], [])

        rslt = bbd.file_exists_and_more(subregion_names=subrgn_names, osm_file_format=file_format)
        assert rslt == (['London'], '.pbf', True, 'download', ['London'], [])

        subrgn_names = ['london', 'rutland']
        rslt = gfd.file_exists_and_more(subregion_names=subrgn_names, osm_file_format=file_format)
        assert rslt == (
            ['Greater London', 'Rutland'], '.osm.pbf', True, 'download',
            ['Greater London', 'Rutland'],
            [])

        subrgn_names = ['birmingham', 'leeds']
        rslt = bbd.file_exists_and_more(subregion_names=subrgn_names, osm_file_format=file_format)
        assert rslt == (
            ['Birmingham', 'Leeds'], '.pbf', True, 'download', ['Birmingham', 'Leeds'], [])

    @staticmethod
    def test_verify_download_dir():
        d = _Downloader()
        assert os.path.relpath(d.download_dir) == 'osm_data'

        d.verify_download_dir(download_dir='tests\\osm_data', verify_download_dir=True)
        assert os.path.relpath(d.download_dir) == 'tests\\osm_data'


class TestGeofabrikDownloader:

    @staticmethod
    def test_init():
        assert gfd.NAME == 'Geofabrik'
        assert gfd.URL == 'https://download.geofabrik.de/'
        assert gfd.DOWNLOAD_INDEX_URL == 'https://download.geofabrik.de/index-v1.json'
        assert os.path.relpath(gfd.download_dir) == 'osm_data\\geofabrik'

        gfd_ = GeofabrikDownloader(download_dir="tests\\osm_data")
        assert os.path.relpath(gfd_.download_dir) == 'tests\\osm_data'

        assert isinstance(gfd.valid_subregion_names, set)
        assert isinstance(gfd.download_index, pd.DataFrame)
        assert isinstance(gfd.continent_tables, dict)
        assert isinstance(gfd.region_subregion_tier, dict)
        assert isinstance(gfd.having_no_subregions, list)
        assert isinstance(gfd.catalogue, pd.DataFrame)

    @staticmethod
    def test_get_raw_directory_index(capfd):
        raw_index = gfd.get_raw_directory_index(gfd.URL, verbose=True)
        out, _ = capfd.readouterr()
        assert out == \
               "Collecting the raw directory index on 'https://download.geofabrik.de/' ... " \
               "Failed.\n" \
               "No raw directory index is available on the web page.\n"
        assert raw_index is None

        great_britain_url = 'https://download.geofabrik.de/europe/great-britain.html'
        raw_index = gfd.get_raw_directory_index(great_britain_url)
        assert isinstance(raw_index, pd.DataFrame)
        assert raw_index.columns.to_list() == ['file', 'date', 'size', 'metric_file_size', 'url']

    @staticmethod
    def test_get_download_index():
        geofabrik_dwnld_idx = gfd.get_download_index()

        assert isinstance(geofabrik_dwnld_idx, pd.DataFrame)
        assert geofabrik_dwnld_idx.columns.to_list() == [
            'id',
            'parent',
            'iso3166-1:alpha2',
            'name',
            'iso3166-2',
            'geometry',
            '.osm.pbf',
            '.osm.bz2',
            '.shp.zip',
            'pbf-internal',
            'history',
            'taginfo',
            'updates']

    @staticmethod
    def test_get_subregion_table(capfd):
        homepage = gfd.get_subregion_table(url=gfd.URL)

        assert homepage.columns.to_list() == [
            'subregion',
            'subregion-url',
            '.osm.pbf',
            '.osm.pbf-size',
            '.shp.zip',
            '.osm.bz2']

        great_britain_url = 'https://download.geofabrik.de/europe/great-britain.html'
        great_britain = gfd.get_subregion_table(great_britain_url)
        assert isinstance(great_britain, pd.DataFrame)

        antarctica_url = 'https://download.geofabrik.de/antarctica.html'
        antarctica = gfd.get_subregion_table(antarctica_url, verbose=True)
        out, _ = capfd.readouterr()
        assert out == 'Compiling information about subregions of "Antarctica" ... Failed.\n'
        assert antarctica is None

        antarctica2 = gfd.get_subregion_table(antarctica_url, verbose=2)
        out, _ = capfd.readouterr()
        assert out == \
               "Compiling information about subregions of \"Antarctica\" ... Failed.\n" \
               "No subregion data is available for \"Antarctica\" on " \
               "Geofabrik's free download server.\n"
        assert antarctica2 is None

    @staticmethod
    def test_get_continent_tables():
        continent_tables = gfd.get_continent_tables()
        assert isinstance(continent_tables, dict)

        asia_table = continent_tables['Asia']
        assert asia_table.columns.to_list() == [
            'subregion',
            'subregion-url',
            '.osm.pbf',
            '.osm.pbf-size',
            '.shp.zip',
            '.osm.bz2']

    @staticmethod
    def test_get_region_subregion_tier():
        rgn_subrgn_tier, no_subrgn_list = gfd.get_region_subregion_tier()
        assert isinstance(rgn_subrgn_tier, dict)
        assert isinstance(no_subrgn_list, list)

    @staticmethod
    def test_get_catalogue():
        dwnld_catalog = gfd.get_catalogue()
        assert isinstance(dwnld_catalog, pd.DataFrame)
        assert len(dwnld_catalog) >= 474
        assert dwnld_catalog.columns.to_list() == [
            'subregion',
            'subregion-url',
            '.osm.pbf',
            '.osm.pbf-size',
            '.shp.zip',
            '.osm.bz2']

    @staticmethod
    def test_get_valid_subregion_names():
        valid_subrgn_names = gfd.get_valid_subregion_names()
        assert isinstance(valid_subrgn_names, set)

    @staticmethod
    def test_validate_subregion_name():
        input_subrgn_name = 'london'
        valid_subrgn_name = gfd.validate_subregion_name(subregion_name=input_subrgn_name)
        assert valid_subrgn_name == 'Greater London'

        input_subrgn_name = 'https://download.geofabrik.de/europe/great-britain.html'
        valid_subrgn_name = gfd.validate_subregion_name(subregion_name=input_subrgn_name)
        assert valid_subrgn_name == 'Great Britain'

    @staticmethod
    def test_validate_file_format():
        input_file_format = ".pbf"
        valid_file_format = gfd.validate_file_format(osm_file_format=input_file_format)
        assert valid_file_format == '.osm.pbf'

        input_file_format = "shp"
        valid_file_format = gfd.validate_file_format(osm_file_format=input_file_format)
        assert valid_file_format == '.shp.zip'

    @staticmethod
    def test_get_subregion_download_url():
        subrgn_name = 'England'
        file_format = ".pbf"
        valid_name, dwnld_link = gfd.get_subregion_download_url(subrgn_name, file_format)
        assert valid_name == 'England'
        assert dwnld_link == \
               'https://download.geofabrik.de/europe/great-britain/england-latest.osm.pbf'

        subrgn_name = 'britain'
        file_format = ".shp"
        valid_name, dwnld_link = gfd.get_subregion_download_url(subrgn_name, file_format)
        assert valid_name == 'Great Britain'
        assert dwnld_link is None

    @staticmethod
    def test_get_default_filename(capfd):
        subrgn_name, file_format = 'london', ".pbf"
        default_fn = gfd.get_default_filename(subrgn_name, file_format)
        assert default_fn == 'greater-london-latest.osm.pbf'

        subrgn_name, file_format = 'britain', ".shp"
        default_fn = gfd.get_default_filename(subrgn_name, file_format)
        out, _ = capfd.readouterr()
        assert out == 'No .shp.zip data is available to download for Great Britain.\n'
        assert default_fn is None

    @staticmethod
    def test_get_default_pathname():
        subrgn_name, file_format = 'london', ".pbf"

        pathname, filename = gfd.get_default_pathname(subrgn_name, file_format)
        assert os.path.relpath(os.path.dirname(pathname)) == \
               'osm_data\\geofabrik\\europe\\great-britain\\england\\greater-london'
        assert filename == 'greater-london-latest.osm.pbf'

    @staticmethod
    def test_get_subregions():
        all_subrgn_names = gfd.get_subregions()
        assert isinstance(all_subrgn_names, list)

        e_na_subrgn_names = gfd.get_subregions('england', 'n america')
        assert isinstance(e_na_subrgn_names, list)

        na_subrgn_names = gfd.get_subregions('n america', deep=True)
        assert isinstance(na_subrgn_names, list)

        gb_subrgn_names = gfd.get_subregions('britain')
        gb_subrgn_names_ = gfd.get_subregions('britain', deep=True)
        assert len(gb_subrgn_names_) >= len(gb_subrgn_names)

    @staticmethod
    def test_specify_sub_download_dir():
        subrgn_name = 'london'
        file_format = ".pbf"

        dwnld_dir = gfd.specify_sub_download_dir(subrgn_name, file_format)
        assert os.path.dirname(os.path.relpath(dwnld_dir)) == \
               'osm_data\\geofabrik\\europe\\great-britain\\england\\greater-london'

        dwnld_dir = "tests\\osm_data"

        subrgn_name = 'britain'
        file_format = ".shp"

        dwnld_pathname = gfd.specify_sub_download_dir(subrgn_name, file_format, dwnld_dir)
        assert os.path.relpath(dwnld_pathname) == 'tests\\osm_data\\great-britain-shp-zip'

        gfd_ = GeofabrikDownloader(download_dir=dwnld_dir)
        dwnld_pathname_ = gfd_.specify_sub_download_dir(subrgn_name, file_format)
        assert os.path.relpath(dwnld_pathname_) == \
               'tests\\osm_data\\europe\\great-britain\\great-britain-shp-zip'

    @staticmethod
    def test_get_valid_download_info():
        subrgn_name = 'london'
        file_format = "pbf"

        info1 = gfd.get_valid_download_info(subrgn_name, file_format)
        valid_subrgn_name, pbf_filename, dwnld_url, path_to_pbf = info1

        assert valid_subrgn_name == 'Greater London'
        assert pbf_filename == 'greater-london-latest.osm.pbf'
        assert dwnld_url == \
               'https://download.geofabrik.de/europe/great-britain/england/' \
               'greater-london-latest.osm.pbf'
        assert os.path.relpath(path_to_pbf) == \
               'osm_data\\geofabrik\\europe\\great-britain\\england\\greater-london\\' \
               'greater-london-latest.osm.pbf'

        dwnld_dir = "tests\\osm_data"

        info2 = gfd.get_valid_download_info(subrgn_name, file_format, dwnld_dir)
        _, _, _, path_to_pbf2 = info2

        assert os.path.relpath(path_to_pbf2) == \
               'tests\\osm_data\\greater-london\\greater-london-latest.osm.pbf'

        gfd_ = GeofabrikDownloader(download_dir=dwnld_dir)

        info3 = gfd_.get_valid_download_info(subrgn_name, file_format)
        _, _, _, path_to_pbf3 = info3

        assert os.path.relpath(path_to_pbf3) == \
               'tests\\osm_data\\europe\\great-britain\\england\\greater-london\\' \
               'greater-london-latest.osm.pbf'

    @staticmethod
    def test_download_osm_data(capfd):
        gfd_ = GeofabrikDownloader()

        subrgn_names = ['london', 'rutland']
        file_format = ".pbf"
        gfd_.download_osm_data(
            subregion_names=subrgn_names, osm_file_format=file_format, verbose=True,
            confirmation_required=False)
        out, _ = capfd.readouterr()
        assert "Downloading " in out and "Done." in out
        assert len(gfd_.data_paths) == 2
        assert os.path.relpath(gfd_.download_dir) == 'osm_data\\geofabrik'

        dwnld_dir = os.path.dirname(gfd_.download_dir)

        region_name = 'west midlands'
        file_format = ".shp"
        temp_dwnld_dir = tempfile.TemporaryDirectory().name

        gfd_.download_osm_data(
            subregion_names=region_name, osm_file_format=file_format, download_dir=temp_dwnld_dir,
            confirmation_required=False)
        assert len(gfd_.data_paths) == 3
        assert gfd_.data_paths[-1] == \
               f'{temp_dwnld_dir}\\west-midlands\\west-midlands-latest-free.shp.zip'
        assert gfd_.download_dir == temp_dwnld_dir
        assert os.path.relpath(gfd_.cdd()) == 'osm_data\\geofabrik'

        delete_dir([dwnld_dir, temp_dwnld_dir], confirmation_required=False)

    # @staticmethod
    # def test_download_subregion_data():
    #     gfd_ = GeofabrikDownloader()
    #
    #     subrgn_name = 'England'
    #     file_format = ".pbf"
    #     dwnld_dir = "tests\\osm_data"
    #
    #     dwnld_file_pathnames = gfd_.download_subregion_data(
    #         subrgn_name, file_format, download_dir=dwnld_dir, update=True, verbose=True,
    #         ret_download_path=True, confirmation_required=False)
    #
    #     assert len(dwnld_file_pathnames) >= 47
    #     assert os.path.commonpath(dwnld_file_pathnames) == gfd_.download_dir
    #
    #     delete_dir(gfd_.download_dir, confirmation_required=False)


class TestBBBikeDownloader:

    @staticmethod
    def test_init():
        assert bbd.NAME == 'BBBike'
        assert bbd.LONG_NAME == 'BBBike exports of OpenStreetMap data'
        assert bbd.URL == 'https://download.bbbike.org/osm/bbbike/'
        assert os.path.relpath(bbd.download_dir) == 'osm_data\\bbbike'

        bbd_ = BBBikeDownloader(download_dir="tests\\osm_data")
        assert os.path.relpath(bbd_.download_dir) == 'tests\\osm_data'

        assert isinstance(bbd.valid_subregion_names, list)
        assert isinstance(bbd.subregion_coordinates, pd.DataFrame)
        assert isinstance(bbd.subregion_index, pd.DataFrame)
        assert isinstance(bbd.catalogue, dict)

    @staticmethod
    def test_get_names_of_cities():
        bbbike_cities = bbd.get_names_of_cities()
        assert isinstance(bbbike_cities, list)

    @staticmethod
    def test_get_coordinates_of_cities():
        coords_of_cities = bbd.get_coordinates_of_cities()

        assert isinstance(coords_of_cities, pd.DataFrame)
        assert coords_of_cities.columns.to_list() == [
            'city',
            'real_name',
            'pref._language',
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

    @staticmethod
    def test_get_subregion_index():
        subrgn_idx = bbd.get_subregion_index()

        assert isinstance(subrgn_idx, pd.DataFrame)
        assert subrgn_idx.columns.to_list() == ['name', 'last_modified', 'url']

    @staticmethod
    def test_get_valid_subregion_names():
        subrgn_names = bbd.get_valid_subregion_names()

        assert isinstance(subrgn_names, list)

    @staticmethod
    def test_validate_subregion_name():
        subrgn_name = 'birmingham'

        valid_name = bbd.validate_subregion_name(subregion_name=subrgn_name)
        assert valid_name == 'Birmingham'

    @staticmethod
    def test_get_subregion_catalogue(capfd):
        subrgn_name = 'birmingham'

        bham_dwnld_cat = bbd.get_subregion_catalogue(
            subregion_name=subrgn_name, confirmation_required=False, verbose=True)
        out, _ = capfd.readouterr()
        assert 'Compiling the data of a download catalogue for "Birmingham" ... Done.\n' == out
        assert isinstance(bham_dwnld_cat, pd.DataFrame)
        assert bham_dwnld_cat.columns.to_list() == [
            'filename', 'url', 'data_type', 'size', 'last_update']

    @staticmethod
    def test_get_catalogue():
        bbbike_catalogue = bbd.get_catalogue()
        assert list(bbbike_catalogue.keys()) == ['FileFormat', 'DataType', 'Catalogue']

        catalogue = bbbike_catalogue['Catalogue']
        assert isinstance(catalogue, dict)

        bham_catalogue = catalogue['Birmingham']
        assert isinstance(bham_catalogue, pd.DataFrame)

    @staticmethod
    def test_validate_file_format():
        valid_file_format = bbd.validate_file_format(osm_file_format='PBF')
        assert valid_file_format == '.pbf'

        valid_file_format = bbd.validate_file_format(osm_file_format='.osm.pbf')
        assert valid_file_format == '.pbf'

    @staticmethod
    def test_get_subregion_download_url():
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

    @staticmethod
    def test_get_valid_download_info():
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

    @staticmethod
    def test_file_exists():
        subrgn_name = 'birmingham'
        file_format = ".pbf"
        dwnld_dir = "tests\\osm_data"

        pbf_exists = bbd.file_exists(subrgn_name, file_format, dwnld_dir)
        assert not pbf_exists

    # @staticmethod
    # def test_download_subregion_data(capfd):
    #     subrgn_name = 'leeds'
    #     dwnld_dir = "tests\\osm_data"
    #
    #     bbd.download_subregion_data(
    #         subregion_name=subrgn_name, download_dir=dwnld_dir, ret_download_path=True,
    #         verbose=True, confirmation_required=False)
    #     out, _ = capfd.readouterr()
    #     assert 'Check out the downloaded OSM data at "tests\\osm_data\\leeds\\".' in out

    @staticmethod
    def test_download_osm_data():
        subrgn_name = 'London'
        file_format = "pbf"

        bbd.download_osm_data(subrgn_name, file_format, confirmation_required=False)
        assert len(bbd.data_paths) == 1
        assert os.path.relpath(bbd.data_paths[0]) == 'osm_data\\bbbike\\london\\London.osm.pbf'

        london_dwnld_dir = os.path.relpath(bbd.download_dir)
        assert london_dwnld_dir == 'osm_data\\bbbike'

        subrgn_names = ['leeds', 'birmingham']
        dwnld_dir = "tests\\osm_data"

        dwnld_paths = bbd.download_osm_data(
            subrgn_names, file_format, dwnld_dir, confirmation_required=False,
            ret_download_path=True)
        assert len(dwnld_paths) == 2
        assert len(bbd.data_paths) == 3
        assert os.path.relpath(bbd.download_dir) == os.path.relpath(dwnld_dir)
        assert os.path.relpath(os.path.commonpath(dwnld_paths)) == 'tests\\osm_data'

        delete_dir([os.path.dirname(london_dwnld_dir), dwnld_dir], confirmation_required=False)


if __name__ == '__main__':
    pytest.main()
