"""Test the module :py:mod:`pydriosm.ios`."""

import pytest


def test_get_default_layer_name():
    from pydriosm.ios import get_default_layer_name

    lyr_name = get_default_layer_name(schema_name='point')
    assert lyr_name == 'points'

    lyr_name = get_default_layer_name(schema_name='land')
    assert lyr_name == 'landuse'


def test_validate_schema_names():
    from pydriosm.ios import validate_schema_names

    valid_names = validate_schema_names()
    assert valid_names == []

    input_schema_names = ['point', 'polygon']
    valid_names = validate_schema_names(input_schema_names)
    assert valid_names == ['point', 'polygon']

    valid_names = validate_schema_names(input_schema_names, schema_named_as_layer=True)
    assert valid_names == ['points', 'multipolygons']


def test_validate_table_name():
    from pydriosm.ios import validate_table_name

    subrgn_name = 'greater london'
    valid_table_name = validate_table_name(subrgn_name)
    assert valid_table_name == 'greater london'

    subrgn_name = 'Llanfairpwllgwyngyllgogerychwyrndrobwllllantysiliogogogoch, Wales'
    valid_table_name = validate_table_name(subrgn_name, sub_space='_')
    assert valid_table_name == 'Llanfairpwllgwyngyllgogerychwyrndrobwllllantysiliogogogoch_W..'


# from pydriosm.ios import PostgresOSM
# from pydriosm.downloader import GeofabrikDownloader, BBBikeDownloader
# from pydriosm.reader import GeofabrikReader, BBBikeReader
#
#
# osmdb = PostgresOSM(database_name='osmdb_test')
#
#
# class TestPostgresOSM:
#
#     @staticmethod
#     def test_init():
#         assert osmdb.data_source == 'Geofabrik'
#         assert osmdb.name == 'Geofabrik OpenStreetMap data extracts'
#         assert osmdb.url == 'https://download.geofabrik.de/'
#         assert isinstance(osmdb.downloader, GeofabrikDownloader)
#         assert isinstance(osmdb.reader, GeofabrikReader)
#
#         # Change the data source
#         assert osmdb.data_source == 'BBBike'
#         assert osmdb.name == 'BBBike exports of OpenStreetMap data'
#         assert osmdb.url == 'https://download.bbbike.org/osm/bbbike/'
#         assert isinstance(osmdb.downloader, BBBikeDownloader)
#         assert isinstance(osmdb.reader, BBBikeReader)


if __name__ == '__main__':
    pytest.main()
