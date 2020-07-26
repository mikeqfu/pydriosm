""" Utilities - Helper functions """

import os

import pkg_resources
from pyhelpers.dir import cd


# -- Change directory ---------------------------------------------------------------------------------

def cd_dat(*sub_dir, dat_dir="dat", mkdir=False, **kwargs):
    """
    Change directory to ``dat_dir`` and its sub-directories within a package.

    :param sub_dir: name of directory; names of directories (and/or a filename)
    :type sub_dir: str
    :param dat_dir: name of a directory to store data, defaults to ``"dat"``
    :type dat_dir: str
    :param mkdir: whether to create a directory, defaults to ``False``
    :type mkdir: bool
    :param kwargs: optional parameters of `os.makedirs`_, e.g. ``mode=0o777``
    :return: a full path to a directory (or a file) under ``data_dir``
    :rtype: str

    .. _`os.makedirs`: https://docs.python.org/3/library/os.html#os.makedirs

    **Example**::

        from pyrcs.utils import cd_dat

        dat_dir = "dat"
        mkdir = False

        cd_dat("line-data", dat_dir=dat_dir, mkdir=mkdir)
        # "\\dat\\line-data"
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


def cd_dat_geofabrik(*sub_dir, mkdir=False, **kwargs):
    """
    Change directory to ``dat_GeoFabrik`` and its sub-directories within a package.

    :param sub_dir: name of directory; names of directories (and/or a filename)
    :type sub_dir: str
    :param mkdir: whether to create a directory, defaults to ``False``
    :type mkdir: bool
    :param kwargs: optional parameters of `os.makedirs`_, e.g. ``mode=0o777``
    :return: a full path to a directory (or a file) under ``data_dir``
    :rtype: str
    """

    path = cd("dat_GeoFabrik", *sub_dir, mkdir=mkdir, **kwargs)

    return path


def cd_dat_bbbike(*sub_dir, mkdir=False, **kwargs):
    """
    Change directory to ``dat_BBBike`` and its sub-directories.

    :param sub_dir: name of directory; names of directories (and/or a filename)
    :type sub_dir: str
    :param mkdir: whether to create a directory, defaults to ``False``
    :type mkdir: bool
    :param kwargs: optional parameters of `os.makedirs`_, e.g. ``mode=0o777``
    :return: a full path to a directory (or a file) under ``data_dir``
    :rtype: str
    """

    path = cd("dat_BBBike", *sub_dir, mkdir=mkdir, **kwargs)

    return path


# -- Miscellaneous ------------------------------------------------------------------------------------

def osm_geom_types():
    """
    Make a dictionary for OSM geometry types.

    :return: a dictionary with keys and values being shape type (in OSM .shp file) and shapely.geometry
    :rtype: dict
    """

    import shapely.geometry

    shape_types = {'Point': shapely.geometry.Point,
                   'LineString': shapely.geometry.LineString,
                   'LinearRing': shapely.geometry.LinearRing,
                   'MultiLineString': shapely.geometry.MultiLineString,
                   'Polygon': shapely.geometry.Polygon,
                   'MultiPolygon': shapely.geometry.MultiPolygon,
                   'GeometryCollection': shapely.geometry.GeometryCollection}

    return shape_types
