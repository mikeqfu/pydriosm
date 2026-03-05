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
    """
    Map OSM data layers to specific schema names.

    :param osm_data: Dictionary of OSM data where keys are layer names.
    :type osm_data: dict
    :param schema_names: List of layers, dict mapping schema to layer, or ``None``.
    :type schema_names: list | dict | None
    :return: An iterable of (schema_name, data) tuples.
    :rtype: zip
    :raises KeyError: If a requested layer name is missing from ``osm_data``.
    """

    # Handle the 'None' or 'All' case immediately
    if not isinstance(schema_names, (list, dict)):
        return osm_data.items()

    # 2. Extract targets based on input type
    if isinstance(schema_names, dict):
        # e.g. schema_names = {'schema_0': 'lines', 'schema_1': 'points'}
        keys_to_return = schema_names.keys()
        layer_targets = list(schema_names.values())
    else:  # list
        keys_to_return = layer_targets = schema_names

    # Validate and check keys
    validated_layers = validate_schema_names(
        schema_names=layer_targets,
        schema_named_as_layer=True
    )

    missing_keys = [k for k in validated_layers if k not in osm_data]

    if missing_keys:
        raise KeyError(f"The following layers are missing from osm_data: {missing_keys}")

    # Construct generator
    return zip(keys_to_return, (osm_data[layer] for layer in validated_layers))


def preprocess_pdf_layer(layer_data, layer_name):
    """
    Preprocess PBF layer data into a pandas DataFrame with WKT geometries.

    :param layer_data: Layer data as a list of OGR features, a Series, or a DataFrame.
    :type layer_data: list | pandas.Series | pandas.DataFrame
    :param layer_name: Name of the layer for column labeling.
    :type layer_name: str
    :return: Processed DataFrame with serialized geometries.
    :rtype: pandas.DataFrame
    """

    # Handle OGR Feature list
    if isinstance(layer_data, list):
        # osgeo_ogr = _check_dependency('osgeo.ogr')
        # if all(isinstance(f, osgeo_ogr.Feature) for f in layer_data):
        lyr_dat = pd.DataFrame([f.ExportToJson() for f in layer_data], columns=[layer_name])

    else:
        # Ensure we have a DataFrame to work with
        lyr_dat = layer_data.to_frame() if isinstance(layer_data, pd.Series) else layer_data.copy()

        if lyr_dat.empty:
            return lyr_dat

        # Handle 'coordinates' column (Check for existence first)
        if 'coordinates' in lyr_dat.columns:
            # Check first non-null value to avoid IndexError
            valid_coords = lyr_dat['coordinates'].dropna()
            if not valid_coords.empty:
                first_val = valid_coords.iloc[0]
                # If it's a shapely object/geometry (has .wkt) but isn't a list
                if not isinstance(first_val, list) and hasattr(first_val, 'wkt'):
                    lyr_dat['coordinates'] = lyr_dat['coordinates'].map(
                        lambda x: x.wkt if hasattr(x, 'wkt') else x,
                        na_action='ignore')

        # Handle Geometry columns
        geom_cols = [
            col for col in lyr_dat.columns
            if any(hasattr(val, 'wkt') for val in lyr_dat[col].dropna().head(1))
        ]
        for col in geom_cols:
            lyr_dat[col] = lyr_dat[col].map(
                lambda x: x.wkt if hasattr(x, 'wkt') else x,
                na_action='ignore')

    return lyr_dat
