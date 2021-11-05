"""
Provide various helper functions across the package.
"""

import os
import re
import shutil

import numpy as np
import pkg_resources
import shapely.geometry
from pyhelpers.dir import cd
from pyhelpers.text import find_similar_str


# == Data directories ========================================================================

def cd_dat(*sub_dir, dat_dir="dat", mkdir=False, **kwargs):
    """
    Change directory to ``dat_dir`` and its sub-directories within a package.

    :param sub_dir: name of directory; names of directories (and/or a filename)
    :type sub_dir: str
    :param dat_dir: name of a directory to store data, defaults to ``"dat"``
    :type dat_dir: str
    :param mkdir: whether to create a directory, defaults to ``False``
    :type mkdir: bool
    :param kwargs: [optional] parameters of `os.makedirs`_, e.g. ``mode=0o777``
    :return: an absolute path to a directory (or a file) under ``data_dir``
    :rtype: str

    .. _`os.makedirs`: https://docs.python.org/3/library/os.html#os.makedirs

    **Example**::

        >>> import os
        >>> from pydriosm.downloader import cd_dat

        >>> path_to_dat = cd_dat()

        >>> os.path.relpath(path_to_dat)
        'pydriosm\\dat'
    """

    path = pkg_resources.resource_filename(__name__, dat_dir)

    for x in sub_dir:
        path = os.path.join(path, x)

    if mkdir:
        path_to_file, ext = os.path.splitext(path)

        if ext == '':
            os.makedirs(path_to_file, exist_ok=True, **kwargs)
        else:
            os.makedirs(os.path.dirname(path_to_file), exist_ok=True, **kwargs)

    return path


def cd_dat_geofabrik(*sub_dir, mkdir=False, default_dir="osm_geofabrik", **kwargs):
    """
    Change directory to ``osm_geofabrik\\`` and its sub-directories within a package.

    :param sub_dir: name of directory; names of directories (and/or a filename)
    :type sub_dir: str or typing.PathLike
    :param mkdir: whether to create a directory, defaults to ``False``
    :type mkdir: bool
    :param default_dir: default folder name of the root directory for downloading data from Geofabrik,
        defaults to ``"osm_geofabrik"``
    :type default_dir: str
    :param kwargs: [optional] parameters of `pyhelpers.dir.cd`_
    :return: an absolute path to a directory (or a file) under ``data_dir``
    :rtype: str or typing.PathLike

    .. _`pyhelpers.dir.cd`: https://pyhelpers.readthedocs.io/en/latest/_generated/pyhelpers.dir.cd.html

    **Examples**::

        >>> import os
        >>> from pydriosm.utils import cd_dat_geofabrik

        >>> os.path.relpath(cd_dat_geofabrik())
        'osm_geofabrik'
    """

    path = cd(default_dir, *sub_dir, mkdir=mkdir, **kwargs)

    return path


def cd_dat_bbbike(*sub_dir, mkdir=False, default_dir="osm_bbbike", **kwargs):
    """
    Change directory to ``osm_bbbike\\`` and its sub-directories.

    :param sub_dir: name of directory; names of directories (and/or a filename)
    :type sub_dir: str
    :param mkdir: whether to create a directory, defaults to ``False``
    :type mkdir: bool
    :param default_dir: default folder name of the root directory for downloading data from BBBike,
        defaults to ``"osm_bbbike"``
    :type default_dir: str
    :param kwargs: [optional] parameters of `pyhelpers.dir.cd`_
    :return: an absolute path to a directory (or a file) under ``data_dir``
    :rtype: str

    .. _`pyhelpers.dir.cd`: https://pyhelpers.readthedocs.io/en/latest/_generated/pyhelpers.dir.cd.html

    **Examples**::

        >>> import os
        >>> from pydriosm.utils import cd_dat_bbbike

        >>> os.path.relpath(cd_dat_bbbike())
        'osm_bbbike'
    """

    path = cd(default_dir, *sub_dir, mkdir=mkdir, **kwargs)

    return path


# == Specifications and cross-references =====================================================

def pbf_layer_geom_type_dict(geom=False):
    """
    A dictionary cross-referencing the names of PBF layers and their corresponding names (or classes) of
    `geometric objects <https://shapely.readthedocs.io/en/latest/manual.html#geometric-objects>`_
    defined in `Shapely <https://pypi.org/project/Shapely/>`_.

    :param geom: whether to return `geometric objects`_ classes, defaults to ``False``
    :type geom: bool
    :return: a dictionary with keys and values being, respectively,
        PBF layers and (names of) `geometric objects`_ defined in `Shapely`_
    :rtype: dict

    .. _`geometric objects`: https://shapely.readthedocs.io/en/latest/manual.html#geometric-objects
    .. _`Shapely`: https://pypi.org/project/Shapely/

    **Examples**::

        >>> from pydriosm.utils import pbf_layer_geom_type_dict

        >>> pbf_layer_geom_type_dict()
        {'points': 'Point',
         'lines': 'LineString',
         'multilinestrings': 'MultiLineString',
         'multipolygons': 'MultiPolygon',
         'other_relations': 'GeometryCollection'}

        >>> pbf_layer_geom_type_dict(geom=True)
        {'points': shapely.geometry.point.Point,
         'lines': shapely.geometry.linestring.LineString,
         'multilinestrings': shapely.geometry.multilinestring.MultiLineString,
         'multipolygons': shapely.geometry.multipolygon.MultiPolygon,
         'other_relations': shapely.geometry.collection.GeometryCollection}
    """

    # {Layer name in .pbf data: the corresponding feature type}

    pbf_feat_geom_dict = {
        'points': 'Point',
        'lines': 'LineString',
        'multilinestrings': 'MultiLineString',
        'multipolygons': 'MultiPolygon',
        'other_relations': 'GeometryCollection',
    }

    if geom:
        pbf_feat_geom_dict = {k: getattr(shapely.geometry, v) for k, v in pbf_feat_geom_dict.items()}

    return pbf_feat_geom_dict


def shp_shape_types_dict():
    """
    A dictionary for shape types of shapefiles.

    :return: a dictionary with keys and values being codes and shape types
    :rtype: dict

    **Example**::

        >>> from pydriosm.utils import shp_shape_types_dict

        >>> shp_shape_types_dict()
        {0: None,
         1: 'Point',
         3: 'Polyline',
         5: 'Polygon',
         8: 'MultiPoint',
         11: 'PointZ',
         13: 'PolylineZ',
         15: 'PolygonZ',
         18: 'MultiPointZ',
         21: 'PointM',
         23: 'PolylineM',
         25: 'PolygonM',
         28: 'MultiPointM',
         31: 'MultiPatch'}
    """

    shape_types = {
        0: None,
        1: 'Point',  # shapely.geometry.Point
        3: 'Polyline',  # shapely.geometry.LineString
        5: 'Polygon',  # shapely.geometry.Polygon
        8: 'MultiPoint',  # shapely.geometry.MultiPoint
        11: 'PointZ',
        13: 'PolylineZ',
        15: 'PolygonZ',
        18: 'MultiPointZ',
        21: 'PointM',
        23: 'PolylineM',
        25: 'PolygonM',
        28: 'MultiPointM',
        31: 'MultiPatch',
    }

    return shape_types


def shp_shape_types_geom_dict(geom=False):
    """
    A dictionary cross-referencing the shape types of shapefiles and their corresponding names (or classes)
    of `geometric objects`_ defined in `Shapely`_.

    :param geom: whether to return
        `geometric objects <https://shapely.readthedocs.io/en/latest/manual.html#geometric-objects>`_
        classes, defaults to ``False``
    :type geom: bool
    :return: a dictionary with keys and values being, respectively,
        shape-type codes of shapefiles and names (or classes) of
        `geometric objects <https://shapely.readthedocs.io/en/latest/manual.html#geometric-objects>`_
        defined in `Shapely <https://pypi.org/project/Shapely/>`_
    :rtype: dict

    .. _`geometric objects`: https://shapely.readthedocs.io/en/latest/manual.html#geometric-objects
    .. _`Shapely`: https://pypi.org/project/Shapely/

    **Examples**::

        >>> from pydriosm.utils import shp_shape_types_geom_dict

        >>> shp_shape_types_geom_dict()
        {1: 'Point', 3: 'LineString', 5: 'Polygon', 8: 'MultiPoint'}

        >>> shp_shape_types_geom_dict(geom=True)
        {1: shapely.geometry.point.Point,
         3: shapely.geometry.linestring.LineString,
         5: shapely.geometry.polygon.Polygon,
         8: shapely.geometry.multipoint.MultiPoint}
    """

    shp_geom_dict = {
        1: 'Point',
        3: 'LineString',
        5: 'Polygon',
        8: 'MultiPoint',
    }

    if geom:
        shp_geom_dict = {k: getattr(shapely.geometry, v) for k, v in shp_geom_dict.items()}

    return shp_geom_dict


def valid_shapefile_layer_names():
    """
    Get valid layer names of OSM shapefiles.

    :return: a list of valid layer names of OSM shapefiles
    :rtype: list

    **Example**::

        >>> from pydriosm.utils import valid_shapefile_layer_names

        >>> valid_shapefile_layer_names()
        ['buildings',
         'landuse',
         'natural',
         'places',
         'points',
         'pofw',
         'pois',
         'railways',
         'roads',
         'traffic',
         'transport',
         'water',
         'waterways']
    """

    valid_shp_layer_names = [
        'buildings',
        'landuse',
        'natural',
        'places',
        'points',
        'pofw',
        'pois',
        'railways',
        'roads',
        'traffic',
        'transport',
        'water',
        'waterways',
    ]

    return valid_shp_layer_names


def postgres_pd_dtype_dict():
    """
    Specify data-type dictionary for
    `PostgreSQL data types <https://www.postgresql.org/docs/current/datatype.html>`_ and
    `pandas.read_csv <https://pandas.pydata.org/pandas-docs/stable/reference/api/pandas.read_csv.html>`_.

    :return: a dictionary as data-type convertor between PostgreSQL and `pandas.read_csv`_
    :rtype: dict

    .. _`pandas.read_csv`: https://pandas.pydata.org/pandas-docs/stable/reference/api/pandas.read_csv.html

    **Example**::

        >>> from pydriosm.utils import postgres_pd_dtype_dict

        >>> postgres_pd_dtype_dict()
        {'text': str, 'bigint': numpy.int64, 'json': str}
    """

    data_types = {
        'text': str,
        'bigint': np.int64,
        'json': str,
    }

    return data_types


# == Miscellaneous helpers ===================================================================

def validate_shp_layer_names(layer_names):
    """
    Validate the input of layer name(s) for reading shape files.

    :param layer_names: name of a shapefile layer, e.g. 'railways',
        or names of multiple layers; if ``None`` (default), returns an empty list;
        if ``layer_names='all'``, the function returns a list of all available layers
    :type layer_names: str or list or None
    :return: valid layer names to be input
    :rtype: list

    **Examples**::

        >>> from pydriosm.utils import validate_shp_layer_names

        >>> lyr_names = None
        >>> lyr_names_ = validate_shp_layer_names(lyr_names)
        >>> print(lyr_names_)
        []

        >>> lyr_names = 'point'
        >>> lyr_names_ = validate_shp_layer_names(lyr_names)
        >>> print(lyr_names_)
        ['points']

        >>> lyr_names = ['point', 'land']
        >>> lyr_names_ = validate_shp_layer_names(lyr_names)
        >>> print(lyr_names_)
        ['points', 'landuse']

        >>> lyr_names = 'all'
        >>> lyr_names_ = validate_shp_layer_names(lyr_names)
        >>> print(lyr_names_)
        ['buildings',
         'landuse',
         'natural',
         'places',
         'points',
         'pofw',
         'pois',
         'railways',
         'roads',
         'traffic',
         'transport',
         'water',
         'waterways']
    """

    if layer_names:
        if layer_names == 'all':
            layer_names_ = valid_shapefile_layer_names()
        else:
            layer_names_ = [layer_names] if isinstance(layer_names, str) \
                else layer_names.copy()
            layer_names_ = [find_similar_str(x, valid_shapefile_layer_names())
                            for x in layer_names_]
    else:
        layer_names_ = []

    return layer_names_


def find_shp_layer_name(shp_filename):
    """
    Find the layer name of OSM shapefile given its filename.

    :param shp_filename: filename of a shapefile (.shp)
    :type shp_filename: str
    :return: layer name of the .shp file
    :rtype: str

    **Examples**::

        >>> from pydriosm.utils import find_shp_layer_name

        >>> lyr_name = find_shp_layer_name(shp_filename="")
        >>> print(lyr_name)
        None

        >>> lyr_name = find_shp_layer_name(shp_filename="gis_osm_railways_free_1.shp")
        >>> lyr_name
        'railways'

        >>> lyr_name = find_shp_layer_name(shp_filename="gis_osm_transport_a_free_1.shp")
        >>> lyr_name
        'transport'
    """

    try:
        pattern = re.compile(r'(?<=gis_osm_)\w+(?=(_a)?_free_1)')
        layer_name = re.search(pattern=pattern, string=shp_filename)

    except AttributeError:
        pattern = re.compile(r'(?<=(\\shape)\\)\w+(?=\.*)')
        layer_name = re.search(pattern=pattern, string=shp_filename)

    if layer_name:
        layer_name = layer_name.group(0).replace("_a", "")

    return layer_name


def append_fclass_to_filename(shp_filename, feature_names):
    """
    Append a ``'fclass'`` name to the original filename of shapefile.

    :param shp_filename: original .shp filename
    :type shp_filename: str
    :param feature_names: name (or names) of a ``fclass`` (or multiple ``fclass``) in .shp data
    :type feature_names: str or list
    :return: updated filename used for saving only the ``fclass`` data of the original .shp data file
    :rtype: str

    **Examples**::

        >>> from pydriosm.utils import append_fclass_to_filename

        >>> new_shp_fn = append_fclass_to_filename("gis_osm_railways_free_1.shp", 'transport')
        >>> new_shp_fn
        'gis_osm_railways_free_1_transport.shp'

        >>> new_shp_fn = append_fclass_to_filename("gis_osm_transport_a_free_1.shp", 'railways')
        >>> new_shp_fn
        'gis_osm_transport_a_free_1_railways.shp'
    """

    filename, ext = os.path.splitext(shp_filename)

    feature_names_ = [feature_names] if isinstance(feature_names, str) else feature_names.copy()

    new_shp_filename = "{filename}_{feature_names}{ext}".format(
        filename=filename, feature_names='_'.join(feature_names_), ext=ext)

    if os.path.dirname(new_shp_filename):
        layer_name = find_shp_layer_name(shp_filename)
        new_shp_filename = cd(
            os.path.dirname(new_shp_filename), layer_name, os.path.basename(new_shp_filename), mkdir=True)

    return new_shp_filename


def remove_subregion_osm_file(path_to_osm_file, verbose=True):
    """
    Remove a downloaded OSM data file.

    :param path_to_osm_file: absolute path to a downloaded OSM data file
    :type path_to_osm_file: str
    :param verbose: defaults to ``True``
    :type verbose: bool
    """

    if verbose:
        print("Deleting \"{}\"".format(os.path.relpath(path_to_osm_file)), end=" ... ")

    try:
        if os.path.isfile(path_to_osm_file):
            os.remove(path_to_osm_file)
            print("Done. ") if verbose else ""

        elif os.path.isdir(path_to_osm_file):
            shutil.rmtree(path_to_osm_file)
            print("Done. ") if verbose else ""

        else:
            if verbose:
                print("File not found at {}.".format(*os.path.split(path_to_osm_file)[::-1]))

    except Exception as e:
        print("Failed. {}".format(e))
