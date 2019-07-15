""" Utilities - Helper functions """

import os

import math
import pkg_resources
import shapely.geometry
from pyhelpers.dir import cd

# ====================================================================================================================
""" Change directory """


# Change directory to "dat_GeoFabrik" and sub-directories
def cd_dat_geofabrik(*sub_dir):
    path = cd("dat_GeoFabrik")
    for x in sub_dir:
        path = os.path.join(path, x)
    return path


# Change directory to "dat_BBBike" and sub-directories
def cd_dat_bbbike(*sub_dir):
    path = cd("dat_BBBike")
    for x in sub_dir:
        path = os.path.join(path, x)
    return path


# Change directory to "dat" and sub-directories
def cd_dat(*sub_dir):
    path = pkg_resources.resource_filename(__name__, 'dat/')
    for x in sub_dir:
        path = os.path.join(path, x)
    return path


# ====================================================================================================================
""" Misc """


# Make a dictionary with keys and values being shape_type (in OSM .shp file) and shapely.geometry, respectively
def osm_geom_types():
    shape_types = {'Point': shapely.geometry.Point,
                   'LineString': shapely.geometry.LineString,
                   'LinearRing': shapely.geometry.LinearRing,
                   'MultiLineString': shapely.geometry.MultiLineString,
                   'Polygon': shapely.geometry.Polygon,
                   'MultiPolygon': shapely.geometry.MultiPolygon,
                   'GeometryCollection': shapely.geometry.GeometryCollection}
    return shape_types


# Split a list into (evenly sized) chunks
def split_list(lst, no_chunks):
    """Yield successive n-sized chunks from a list
    Reference: https://stackoverflow.com/questions/312443/how-do-you-split-a-list-into-evenly-sized-chunks

    """
    chunk_size = math.ceil(len(lst) / no_chunks)
    for i in range(0, len(lst), chunk_size):
        yield lst[i:i + chunk_size]
