""" Utilities - Helper functions """

import math
import os
import shutil

import pkg_resources
import shapely.geometry
from pyhelpers.dir import cd


# -- Source homepage ----------------------------------------------------------------------------------

def geofabrik_homepage():
    """
    Specify the source homepage URL of the GeoFabrik data extracts.

    :return: URL of the data source homepage
    :rtype: str
    """

    return 'http://download.geofabrik.de/'


def bbbike_homepage():
    """
    Specify the source homepage URL of the BBBike data extracts.

    :return: URL of the data source homepage
    :rtype: str
    """

    return 'http://download.bbbike.org/osm/bbbike/'


# -- Directory ----------------------------------------------------------------------------------------

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

        from pydriosm.utils import cd_dat

        dat_dir = "dat"
        mkdir = False

        path = cd_dat()

        print(path)
        # dat
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


# -- Geometric object ---------------------------------------------------------------------------------

def pbf_layer_feat_types_dict():
    # {Layer name in .pbf data: the corresponding feature type}
    pbf_layer_feat_types = {'points': 'Point',
                            'lines': 'LineString',
                            'multilinestrings': 'MultiLineString',
                            'multipolygons': 'MultiPolygon',
                            'other_relations': 'GeometryCollection'}

    return pbf_layer_feat_types


def osm_geom_shapely_object_dict():
    """
    Make a dictionary for OSM geometry types.

    :return: a dictionary with keys and values being shape type (in OSM .shp file) and shapely.geometry
    :rtype: dict
    """

    shape_object_dict = {'Point': shapely.geometry.Point,
                         'LineString': shapely.geometry.LineString,
                         'LinearRing': shapely.geometry.LinearRing,
                         'MultiLineString': shapely.geometry.MultiLineString,
                         'Polygon': shapely.geometry.Polygon,
                         'MultiPolygon': shapely.geometry.MultiPolygon,
                         'GeometryCollection': shapely.geometry.GeometryCollection}

    return shape_object_dict


# -- Miscellaneous ------------------------------------------------------------------------------------

def remove_subregion_osm_file(path_to_osm_file, verbose=True):
    """
    Remove the downloaded file.

    :param path_to_osm_file:
    :type path_to_osm_file: str
    :param verbose: defaults to ``True``
    :type verbose: bool

    **Example**::

        from utils import validate_input_subregion_name
        from download.geofabrik import GeoFabrik

        geofabrik = GeoFabrik()

        verbose = True
        subregion_name = 'great britain'
        _, path_to_osm_file = geofabrik.get_default_path_to_osm_file(subregion_name, ".shp.zip")

        path_to_osm_file_ = geofabrik.make_default_sub_subregion_download_dir(subregion_name,
                                                                              osm_file_format,
                                                                              download_dir)

        remove_subregion_osm_file(path_to_osm_file_)
    """

    if not os.path.exists(path_to_osm_file):
        if verbose:
            print("\"{}\" does not exist at \"{}\".".format(*os.path.split(path_to_osm_file)[::-1]))

    else:
        try:
            if os.path.isfile(path_to_osm_file):
                os.remove(path_to_osm_file)

            elif os.path.isdir(path_to_osm_file):
                shutil.rmtree(path_to_osm_file)

            if verbose:
                print("\"{}\" has been removed.\n".format(os.path.basename(path_to_osm_file)))

        except Exception as e:
            print(e)


def get_number_of_chunks(path_to_file, chunk_size_limit=50):
    """
    Compute  to parse the data file in a chunk-wise way

    :param path_to_file: full path to a file
    :type path_to_file: str
    :param chunk_size_limit: threshold (in MB) above which the file is to be split into chunks, defaults to ``50``;
    :type chunk_size_limit: int
    :return: number of chunks
    :rtype: int, None
    """

    file_size_in_mb = round(os.path.getsize(path_to_file) / (1024 ** 2), 1)

    if chunk_size_limit and file_size_in_mb > chunk_size_limit:
        number_of_chunks = math.ceil(file_size_in_mb / chunk_size_limit)
    else:
        number_of_chunks = None

    return number_of_chunks
