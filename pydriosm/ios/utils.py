"""
Utilities for the :mod:`~pydriosm.ios` module.
"""

import pandas as pd
from pyhelpers.text import find_similar_str, remove_punctuation

from pydriosm.reader import PBF, SHP


def get_default_layer_name(schema_name):
    """
    Get default name (as an input schema name) of an OSM layer
    for the class :py:class:`PostgresOSM<pydriosm.ios.PostgresOSM>`.

    See, for example, the method :meth:`pydriosm.ios.PostgresOSM.import_osm_layer`.

    :param schema_name: name of a schema (or name of an OSM layer)
    :type schema_name: str
    :return: default name of the layer
    :rtype: str

    **Examples**::

        >>> from pydriosm.ios.utils import get_default_layer_name
        >>> lyr_name = get_default_layer_name(schema_name='point')
        >>> lyr_name
        'points'
        >>> lyr_name = get_default_layer_name(schema_name='land')
        >>> lyr_name
        'landuse'
    """

    valid_layer_names = set(PBF.LAYER_GEOM.keys()).union(SHP.LAYER_NAMES)

    layer_name_ = find_similar_str(schema_name, lookup_list=valid_layer_names)

    return layer_name_


def validate_schema_names(schema_names=None, schema_named_as_layer=False):
    """
    Validate schema names for importing data into a database.

    :param schema_names: one or multiple names of layers, e.g. 'points', 'lines', defaults to ``None``
    :type schema_names: typing.Iterable | None
    :param schema_named_as_layer: whether to use default PBF layer name as the schema name,
        defaults to ``False``
    :type schema_named_as_layer: bool
    :return: valid names of the schemas in the database
    :rtype: list

    **Examples**::

        >>> from pydriosm.ios.utils import validate_schema_names
        >>> valid_names = validate_schema_names()
        >>> valid_names
        []
        >>> input_schema_names = ['point', 'polygon']
        >>> valid_names = validate_schema_names(input_schema_names)
        >>> valid_names
        ['point', 'polygon']
        >>> valid_names = validate_schema_names(input_schema_names, schema_named_as_layer=True)
        >>> valid_names
        ['points', 'multipolygons']
    """

    if schema_names:
        if isinstance(schema_names, str):
            schema_names_ = [
                get_default_layer_name(schema_names) if schema_named_as_layer else schema_names]
            # assert schema_names_[0] in valid_layer_names, assertion_msg
        else:  # isinstance(schema_names, list) is True
            if schema_named_as_layer:
                schema_names_ = [get_default_layer_name(x) for x in schema_names]
            else:
                schema_names_ = schema_names
    else:
        schema_names_ = []

    return schema_names_


def validate_table_name(table_name, sub_space=''):
    """
    Validate a table name for importing OSM data into a database.

    :param table_name: name as input of a table in a PostgreSQL database
    :type table_name: str
    :param sub_space: substitute for space, defaults to ``''``
    :type sub_space: str
    :return: valid name of the table in the database
    :rtype: str

    **Examples**::

        >>> from pydriosm.ios.utils import validate_table_name
        >>> subrgn_name = 'greater london'
        >>> valid_table_name = validate_table_name(subrgn_name)
        >>> valid_table_name
        'greater london'
        >>> subrgn_name = 'Llanfairpwllgwyngyllgogerychwyrndrobwllllantysiliogogogoch, Wales'
        >>> valid_table_name = validate_table_name(subrgn_name, sub_space='_')
        >>> valid_table_name
        'Llanfairpwllgwyngyllgogerychwyrndrobwllllantysiliogogogoch_W..'
    """

    table_name_ = remove_punctuation(table_name, rm_whitespace=True)

    if sub_space:
        table_name_ = table_name_.replace(' ', sub_space)

    table_name_ = table_name_[:60] + '..' if len(table_name_) >= 63 else table_name_

    return table_name_


def make_data_items(osm_data, schema_names):
    if isinstance(schema_names, list):
        schema_names_ = validate_schema_names(
            schema_names=schema_names, schema_named_as_layer=True)
        assert all(x in osm_data.keys() for x in schema_names)
        data_items = zip(schema_names_, (osm_data[x] for x in schema_names_))

    elif isinstance(schema_names, dict):
        # e.g. schema_names = {'schema_0': 'lines', 'schema_1': 'points'}
        schema_names_ = validate_schema_names(
            schema_names=schema_names.values(), schema_named_as_layer=True)
        assert all(x in osm_data.keys() for x in schema_names_)
        data_items = zip(schema_names.keys(), (osm_data[x] for x in schema_names_))

    else:
        data_items = osm_data.items()

    return data_items


def preprocess_pdf_layer(layer_data, layer_name):
    if isinstance(layer_data, list):
        # osgeo_ogr = _check_dependency('osgeo.ogr')
        # if all(isinstance(f, osgeo_ogr.Feature) for f in layer_data):
        lyr_dat = pd.DataFrame([f.ExportToJson() for f in layer_data], columns=[layer_name])

    else:
        lyr_dat = layer_data.copy()
        if isinstance(lyr_dat, pd.Series):
            lyr_dat = pd.DataFrame(lyr_dat)

        if 'coordinates' in lyr_dat.columns:
            if not isinstance(lyr_dat.coordinates[0], list):
                lyr_dat.coordinates = lyr_dat.coordinates.map(lambda x: x.wkt)

        if 'geometry' in [x.name for x in lyr_dat.dtypes]:
            geom_col_name = lyr_dat.dtypes[lyr_dat.dtypes == 'geometry'].index[0]
            lyr_dat[geom_col_name] = lyr_dat[geom_col_name].map(lambda x: x.wkt)

    return lyr_dat
