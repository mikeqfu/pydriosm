"""Tests the submodule: :mod:`pydriosm.ios.utils`."""

import pytest

from pydriosm.ios.utils import get_default_layer_name, validate_schema_names, validate_table_name


def test_get_default_layer_name():
    lyr_name = get_default_layer_name(schema_name='point')
    assert lyr_name == 'points'

    lyr_name = get_default_layer_name(schema_name='land')
    assert lyr_name == 'landuse'


def test_validate_schema_names():
    valid_names = validate_schema_names()
    assert valid_names == []

    input_schema_names = ['point', 'polygon']
    valid_names = validate_schema_names(input_schema_names)
    assert valid_names == ['point', 'polygon']

    valid_names = validate_schema_names(input_schema_names, schema_named_as_layer=True)
    assert valid_names == ['points', 'multipolygons']


def test_validate_table_name():
    subrgn_name = 'greater london'
    valid_table_name = validate_table_name(subrgn_name)
    assert valid_table_name == 'greater london'

    subrgn_name = 'Llanfairpwllgwyngyllgogerychwyrndrobwllllantysiliogogogoch, Wales'
    valid_table_name = validate_table_name(subrgn_name, sub_space='_')
    assert valid_table_name == 'Llanfairpwllgwyngyllgogerychwyrndrobwllllantysiliogogogoch_W..'


if __name__ == '__main__':
    pytest.main()
