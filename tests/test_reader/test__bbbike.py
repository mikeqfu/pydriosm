import pytest

from pydriosm.reader._bbbike import BBBikeReader


class TestGeofabrikReader:

    @pytest.fixture(scope='class')
    def bbr(self):
        # bbr = BBBikeReader()
        return BBBikeReader()


if __name__ == '__main__':
    pytest.main()
