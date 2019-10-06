""" Utilities - Helper functions """

import math
import os
import pickle

import pkg_resources
import pyhelpers.dir
import rapidjson
import shapely.geometry

# ====================================================================================================================
""" Change directory """


# Change directory to "dat_GeoFabrik" and sub-directories
def cd_dat_geofabrik(*sub_dir):
    path = pyhelpers.dir.cd("dat_GeoFabrik")
    for x in sub_dir:
        path = os.path.join(path, x)
    return path


# Change directory to "dat_BBBike" and sub-directories
def cd_dat_bbbike(*sub_dir):
    path = pyhelpers.dir.cd("dat_BBBike")
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
""" Save data """


# Save Pickle file
def save_pickle(pickle_data, path_to_pickle, verbose=True):
    """
    :param pickle_data: any object that could be dumped by the 'pickle' package
    :param path_to_pickle: [str] local file path
    :param verbose: [bool] (default: True)
    :return: whether the data has been successfully saved
    """
    pickle_filename = os.path.basename(path_to_pickle)
    pickle_dir = os.path.basename(os.path.dirname(path_to_pickle))
    pickle_dir_parent = os.path.basename(os.path.dirname(os.path.dirname(path_to_pickle)))

    if verbose:
        print("{} \"{}\" ... ".format("Updating" if os.path.isfile(path_to_pickle) else "Saving",
                                      " - ".join([pickle_dir_parent, pickle_dir, pickle_filename])), end="")

    try:
        os.makedirs(os.path.dirname(os.path.abspath(path_to_pickle)), exist_ok=True)
        pickle_out = open(path_to_pickle, 'wb')
        pickle.dump(pickle_data, pickle_out)
        pickle_out.close()
        print("Successfully.") if verbose else None
    except Exception as e:
        print("Failed. {}.".format(e))


# Save JSON file
def save_json(json_data, path_to_json, verbose=True):
    """
    :param json_data: any object that could be dumped by the 'json' package
    :param path_to_json: [str] local file path
    :param verbose: [bool] (default: True)
    :return: whether the data has been successfully saved
    """
    json_filename = os.path.basename(path_to_json)
    json_dir = os.path.basename(os.path.dirname(path_to_json))
    json_dir_parent = os.path.basename(os.path.dirname(os.path.dirname(path_to_json)))

    print("{} \"{}\" ... ".format("Updating" if os.path.isfile(path_to_json) else "Saving",
                                  " - ".join([json_dir_parent, json_dir, json_filename])), end="") if verbose else None
    try:
        os.makedirs(os.path.dirname(os.path.abspath(path_to_json)), exist_ok=True)
        json_out = open(path_to_json, 'w')
        rapidjson.dump(json_data, json_out)
        json_out.close()
        print("Successfully.") if verbose else None
    except Exception as e:
        print("Failed. {}.".format(e))


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
