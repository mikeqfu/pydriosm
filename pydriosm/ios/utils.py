"""
Utilities for the :mod:`~pydriosm.ios` module.
"""

from pyhelpers.text import find_similar_str, remove_punctuation

from pydriosm.reader import PBFReadParse, SHPReadParse


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

        >>> from pydriosm.ios import get_default_layer_name

        >>> lyr_name = get_default_layer_name(schema_name='point')
        >>> lyr_name
        'points'

        >>> lyr_name = get_default_layer_name(schema_name='land')
        >>> lyr_name
        'landuse'
    """

    valid_layer_names = set(PBFReadParse.LAYER_GEOM.keys()).union(SHPReadParse.LAYER_NAMES)

    layer_name_ = find_similar_str(x=schema_name, lookup_list=valid_layer_names)

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

        >>> from pydriosm.ios import validate_schema_names

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

        >>> from pydriosm.ios import validate_table_name

        >>> subrgn_name = 'greater london'
        >>> valid_table_name = validate_table_name(subrgn_name)
        >>> valid_table_name
        'greater london'

        >>> subrgn_name = 'Llanfairpwllgwyngyllgogerychwyrndrobwllllantysiliogogogoch, Wales'
        >>> valid_table_name = validate_table_name(subrgn_name, sub_space='_')
        >>> valid_table_name
        'Llanfairpwllgwyngyllgogerychwyrndrobwllllantysiliogogogoch_W..'
    """

    table_name_ = remove_punctuation(x=table_name, rm_whitespace=True)

    if sub_space:
        table_name_ = table_name_.replace(' ', sub_space)

    table_name_ = table_name_[:60] + '..' if len(table_name_) >= 63 else table_name_

    return table_name_
