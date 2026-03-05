"""
Test the module :py:mod:`pydriosm.errors`.
"""

import pytest


class TestInvalidSubregionNameError:

    @staticmethod
    def test_error():
        from pydriosm.errors import InvalidSubregionNameError

        msg = InvalidSubregionNameError('abc').message
        assert 'The input of `subregion_name` is not recognizable.' in msg

        msg = InvalidSubregionNameError('abc').__str__()
        assert ' -> ' in msg

        msg = InvalidSubregionNameError('abc', msg=1).message
        assert '1)' in msg and '2)' in msg


class TestInvalidFileFormatError:

    @staticmethod
    def test_error():
        from pydriosm.errors import InvalidFileFormatError

        msg = InvalidFileFormatError('abc').message
        assert 'The input `osm_file_format` is unidentifiable.' in msg

        msg = InvalidFileFormatError('abc').__str__()
        assert ' -> ' in msg

        msg = InvalidFileFormatError('abc', valid_file_formats={'valid_file_formats'}).message
        assert 'Valid options include:' in msg


class TestOtherTagsReformatError:

    @staticmethod
    def test_error():
        from pydriosm.errors import OtherTagsReformatError

        msg = OtherTagsReformatError('abc').message
        assert 'Failed to reformat the `other_tags`.' in msg

        msg = OtherTagsReformatError('abc').__str__()
        assert ' -> ' in msg


class TestMethodNotAvailableError:

    @staticmethod
    def test_error():
        from pydriosm.errors import MethodNotAvailableError
        from pydriosm.downloader import Downloader
        downloader = Downloader()

        msg = MethodNotAvailableError(method_name='download', instance=downloader).message
        assert ("The '.download()' method is not available for 'Downloader' "
                "(for 'Geofabrik' source).") in msg

        with pytest.raises(MethodNotAvailableError) as exc_info:
            downloader = Downloader()
            downloader.get_sub_catalogue(subregion_name='Leeds', raise_error=True)

        assert ("The '.get_sub_catalogue()' method is not available for 'GeofabrikDownloader'"
                in str(exc_info.value))


if __name__ == '__main__':
    pytest.main()
