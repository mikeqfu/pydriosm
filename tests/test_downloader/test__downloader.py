"""
Tests the :py:mod:`pydriosm.downloader._downloader` module.
"""

import copy
import os

import pytest
from pyhelpers.dirs import delete_dir, normalize_pathname

from pydriosm.downloader._base import BaseDownloader
from pydriosm.downloader._bbbike import BBBikeDownloader
from pydriosm.downloader._geofabrik import GeofabrikDownloader
from pydriosm.errors import InvalidFileFormatError, InvalidSubregionNameError


class TestBaseDownloader:

    @pytest.fixture(scope='class')
    def gfd(self):
        # gfd = GeofabrikDownloader()
        return GeofabrikDownloader()

    @pytest.fixture(scope='class')
    def bbd(self):
        # bbd = BBBikeDownloader()
        return BBBikeDownloader()

    @pytest.fixture(scope='class')
    def bd(self):
        # bd = BaseDownloader()
        return BaseDownloader()

    def test_init(self, bd):
        assert bd.NAME == 'OSM downloader'
        assert os.path.relpath(bd.download_dir) == 'osm_data'
        assert os.path.relpath(bd.cdd()) == 'osm_data'
        assert bd.download_dir == bd.cdd()

        _d_test = BaseDownloader(download_dir="tests/osm_data")
        assert normalize_pathname(os.path.relpath(_d_test.download_dir)) == 'tests/osm_data'

    @staticmethod
    def test_cdd():
        assert os.path.relpath(BaseDownloader.cdd()) == 'osm_data'

    @staticmethod
    def test_format_confirmation_prompt():
        test_1 = BaseDownloader.format_confirmation_prompt()
        assert test_1 == 'To retrieve/compile data of <data_name>\n?'

        test2 = BaseDownloader.format_confirmation_prompt(update=True)
        assert test2 == 'To update the data of <data_name>\n?'

    @staticmethod
    def test_print_action_prompt(capfd):
        assert BaseDownloader.print_action_prompt(verbose=False) is None

        BaseDownloader.print_action_prompt(verbose=True)
        print("Done.")
        out, _ = capfd.readouterr()
        assert "Retrieving/compiling the data ... Done." in out

        BaseDownloader.print_action_prompt(verbose=True, note="(Some notes)")
        print("Done.")
        out, _ = capfd.readouterr()
        assert "Retrieving/compiling the data (Some notes) ... Done." in out

        BaseDownloader.print_action_prompt(verbose=True, confirmation_required=False)
        print("Done.")
        out, _ = capfd.readouterr()
        assert "Retrieving/compiling data of <data_name> ... Done." in out

    @staticmethod
    def test_print_status(capfd):
        assert BaseDownloader.print_status() is None

        BaseDownloader.print_status(verbose=True)
        out, _ = capfd.readouterr()
        assert out == 'Cancelled.\n'

        BaseDownloader.print_status(verbose=2)
        out, _ = capfd.readouterr()
        assert out == 'The collecting of <data_name> is cancelled, or no data is available.\n'

        BaseDownloader.print_status(verbose=True, error_message="Errors.")
        out, _ = capfd.readouterr()
        assert out == 'Failed. Errors.\n'

    @staticmethod
    @pytest.mark.parametrize('data_name', [None, '<data_name>'])
    def test_get_prepacked_data(data_name, monkeypatch, capfd):
        output = BaseDownloader.get_prepacked_data(
            callable, data_name=data_name, confirmation_required=False)
        assert output is None

        monkeypatch.setattr('builtins.input', lambda _: "No")
        output = BaseDownloader.get_prepacked_data(callable, verbose=True)
        out, _ = capfd.readouterr()
        assert 'Cancelled.' in out
        assert output is None

    @staticmethod
    def test_validate_subregion_name():
        with pytest.raises(InvalidSubregionNameError) as exc_info:
            BaseDownloader.validate_subregion_name('abc')
        assert '1)' in str(exc_info.value) and '2)' in str(exc_info.value)

        with pytest.raises(InvalidSubregionNameError) as exc_info:
            BaseDownloader.validate_subregion_name('abc', ['ab'])
        assert ' -> ' in str(exc_info.value)

        subrgn_name = 'usa'
        subrgn_name_ = BaseDownloader.validate_subregion_name(subrgn_name)
        assert subrgn_name_ == 'United States of America'

        avail_subrgn_names = ['Birmingham', 'Leeds', 'Greater London', 'Great Britain']

        subrgn_name = 'Britain'
        subrgn_name_ = BaseDownloader.validate_subregion_name(subrgn_name, avail_subrgn_names)
        assert subrgn_name_ == 'Great Britain'

        subrgn_name = 'london'
        subrgn_name_ = BaseDownloader.validate_subregion_name(subrgn_name, avail_subrgn_names)
        assert subrgn_name_ == 'Greater London'

    @staticmethod
    def test_validate_file_format():
        assert BaseDownloader.validate_file_format(osm_file_format='pbf') == '.osm.pbf'
        assert BaseDownloader.validate_file_format(osm_file_format='shp') == '.shp.zip'

        with pytest.raises(InvalidFileFormatError) as e:
            _ = BaseDownloader.validate_file_format(osm_file_format='abc')  # Raise an error
            assert "`osm_file_format='abc'` -> The input `osm_file_format` is unidentifiable." in e

    @staticmethod
    def test_get_default_sub_path():
        subrgn_name_ = 'London'
        dwnld_url = 'https://download.bbbike.org/osm/bbbike/London/London.osm.pbf'

        assert BaseDownloader.get_default_sub_path(subrgn_name_, dwnld_url) == '\\london'

    @staticmethod
    def test_make_subregion_dirname():
        assert BaseDownloader.make_subregion_dirname('England') == 'england'
        assert BaseDownloader.make_subregion_dirname('Greater London') == 'greater-london'

    @staticmethod
    def test_get_subregion_download_url():
        output = BaseDownloader.get_subregion_download_url('<subregion_name_>', '<download_url>')
        assert output == ('<subregion_name_>', '<download_url>')

    def test_get_valid_download_info(self, bd):
        cur_dir = copy.copy(bd.download_dir)

        subregion_name, osm_file_format = 'subregion_name', 'osm_file_format'

        valid_dwnld_info = bd.get_valid_download_info(subregion_name, osm_file_format)
        subregion_name_, osm_filename, download_url, file_pathname = valid_dwnld_info
        assert subregion_name_ == '<subregion_name_>'
        assert osm_filename == '<download_url>'
        assert download_url == '<download_url>'
        assert os.path.relpath(file_pathname) == os.path.join(
            "osm_data", "<subregion_name_>", "<download_url>")

        bd.download_dir = os.path.join(cur_dir, '<subregion_name_>')
        _, _, _, file_pathname = bd.get_valid_download_info(subregion_name, osm_file_format)
        assert os.path.relpath(file_pathname) == os.path.join(
            "osm_data", "<subregion_name_>", "<download_url>")

        download_dir = 'x-osm-pbf'
        _, _, _, file_pathname = bd.get_valid_download_info(
            subregion_name, osm_file_format, download_dir)
        assert os.path.relpath(file_pathname) == os.path.join("x-osm-pbf", "<download_url>")

        subregion_name, osm_file_format = '', ''
        _, osm_filename, _, file_pathname = bd.get_valid_download_info(
            subregion_name=subregion_name, osm_file_format=osm_file_format)
        assert osm_filename is None and file_pathname is None

        bd.download_dir = cur_dir

    def test_file_exists(self, bd, capfd):
        subregion_name = '<subregion_name>'
        osm_file_format = 'shp'
        rslt = bd.file_exists(subregion_name=subregion_name, osm_file_format=osm_file_format)
        assert not rslt

        subregion_name, osm_file_format = '', ''
        rslt = bd.file_exists(
            subregion_name=subregion_name, osm_file_format=osm_file_format, verbose=2)
        out, _ = capfd.readouterr()
        assert 'None data for "None" is not available' in out
        assert not rslt

    def test_file_exists_and_more(self, gfd, bbd):
        subrgn_names, file_format = 'London', ".pbf"

        output = gfd.file_exists_and_more(
            subregion_names=subrgn_names, osm_file_formats=file_format)
        assert output[0] == ['Greater London']
        assert output[1] == ['.osm.pbf']
        assert output[2] is True
        assert output[3].startswith('To download data in the format')
        assert output[4] == []

        output = bbd.file_exists_and_more(
            subregion_names=subrgn_names, osm_file_formats=file_format)
        assert output[0] == ['London']
        assert output[1] == ['.pbf']
        assert output[2] is True
        assert output[3].startswith('To download data in the format')
        assert output[4] == []

        subrgn_names = ['london', 'rutland']
        output = gfd.file_exists_and_more(
            subregion_names=subrgn_names, osm_file_formats=file_format)
        assert output[0] == ['Greater London', 'Rutland']
        assert output[1] == ['.osm.pbf']
        assert output[2] is True
        assert output[3].startswith('To download data in the format')
        assert output[4] == []

        subrgn_names = ['birmingham', 'leeds']
        output = bbd.file_exists_and_more(
            subregion_names=subrgn_names, osm_file_formats=file_format)
        assert output[0] == ['Birmingham', 'Leeds']
        assert output[1] == ['.pbf']
        assert output[2] is True
        assert output[3].startswith('To download data in the format')
        assert output[4] == []

    def test_verify_download_dir(self, bd):
        assert os.path.relpath(bd.download_dir) == 'osm_data'

        test_download_dir = 'tests/osm_data'
        bd.verify_download_dir(download_dir=test_download_dir, verify_download_dir=True)

        assert normalize_pathname(os.path.relpath(bd.download_dir)) == test_download_dir

    def test__download_data(self, bd, tmp_path, capfd):
        filename = "rutland-latest.osm.pbf"
        path_to_file = os.path.join(tmp_path, filename)
        url_ = f'https://download.geofabrik.de/europe/united-kingdom/england/'

        bd._download_data(f'{url_}{filename}', path_to_file, verbose=True)
        out, _ = capfd.readouterr()
        assert f'Saving "{filename}"' in out and ' ... Done.' in out
        assert os.path.isfile(path_to_file)

        bd._download_data(f'{url_}{filename}', path_to_file, verbose=2)
        out, _ = capfd.readouterr()
        assert f'Updating "{filename}"' in out and ' ... Done.' in out
        assert os.path.basename(bd.data_paths[0]) == filename

        assert bd.download_dir == str(tmp_path)

        with pytest.raises(Exception) as exc_info:
            bd._download_data(f'{url_}unknown.osm.pbf', path_to_file, raise_error=True)
        assert 'Failed' in str(exc_info.value)

        delete_dir(tmp_path, confirmation_required=False, verbose=True)


if __name__ == '__main__':
    pytest.main()
