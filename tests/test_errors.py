"""Test the module :py:mod:`pydriosm.errors`."""

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


if __name__ == '__main__':
    pytest.main()
