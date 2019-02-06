""" Utilities - Helper functions """

import collections
import json
import os
import pickle
import re

import pkg_resources
import requests
import shapely.geometry
import tqdm


# Type to confirm whether to proceed or not
def confirmed(prompt=None, resp=False, confirmation_required=True):
    """
    Reference: http://pydriosm.activestate.com/recipes/541096-prompt-the-user-for-confirmation/

    :param prompt: [str] or None
    :param resp: [bool]
    :param confirmation_required: [bool]
    :return:

    Example: confirm(prompt="Create Directory?", resp=True)
             Create Directory? Yes|No:

    """
    if confirmation_required:
        if prompt is None:
            prompt = "Confirmed? "

        if resp is True:  # meaning that default response is True
            prompt = "{} [{}]|{}: ".format(prompt, "Yes", "No")
        else:
            prompt = "{} [{}]|{}: ".format(prompt, "No", "Yes")

        ans = input(prompt)
        if not ans:
            return resp

        if re.match('[Yy](es)?', ans):
            return True
        if re.match('[Nn](o)?', ans):
            return False

    else:
        return True


# ====================================================================================================================
""" Change directory """


# Change directory and sub-directories
def cd(*directories):
    # Current working directory
    path = os.getcwd()
    for directory in directories:
        path = os.path.join(path, directory)
    return path


# Change directory to "dat_GeoFabrik" and sub-directories
def cd_dat_geofabrik(*directories):
    path = cd("dat_GeoFabrik")
    for directory in directories:
        path = os.path.join(path, directory)
    return path


# Change directory to "dat_BBBike" and sub-directories
def cd_dat_bbbike(*directories):
    path = cd("dat_BBBike")
    for directory in directories:
        path = os.path.join(path, directory)
    return path


# Change directory to "dat" and sub-directories
def cd_dat(*directories):
    path = pkg_resources.resource_filename(__name__, 'dat/')
    for directory in directories:
        path = os.path.join(path, directory)
    return path


# ====================================================================================================================
""" Save and Load files """


# Save pickles
def save_pickle(pickle_data, path_to_pickle):
    """
    :param pickle_data: any object that could be dumped by the 'pickle' package
    :param path_to_pickle: [str] local file path
    :return: whether the data has been successfully saved
    """
    pickle_filename = os.path.basename(path_to_pickle)
    print("{} \"{}\" ... ".format("Updating" if os.path.isfile(path_to_pickle) else "Saving", pickle_filename), end="")
    try:
        os.makedirs(os.path.dirname(path_to_pickle), exist_ok=True)
        pickle_out = open(path_to_pickle, 'wb')
        pickle.dump(pickle_data, pickle_out)
        pickle_out.close()
        print("Done.")
    except Exception as e:
        print("failed due to {}.".format(e))


# Load pickles
def load_pickle(path_to_pickle):
    """
    :param path_to_pickle: [str] local file path
    :return: the object retrieved from the pickle
    """
    pickle_in = open(path_to_pickle, 'rb')
    data = pickle.load(pickle_in)
    pickle_in.close()
    return data


# Save JSON files
def save_json(json_data, path_to_json):
    """
    :param json_data: any object that could be dumped by the 'json' package
    :param path_to_json: [str] local file path
    :return: whether the data has been successfully saved
    """
    json_filename = os.path.basename(path_to_json)
    print("{} \"{}\" ... ".format("Updating" if os.path.isfile(path_to_json) else "Saving", json_filename), end="")
    try:
        os.makedirs(os.path.dirname(path_to_json), exist_ok=True)
        json_out = open(path_to_json, 'w')
        json.dump(json_data, json_out)
        json_out.close()
        print("Done.")
    except Exception as e:
        print("failed due to {}.".format(e))


# Load JSON files
def load_json(path_to_json):
    """
    :param path_to_json: [str] local file path
    :return: the json data retrieved
    """
    json_in = open(path_to_json, 'r')
    data = json.load(json_in)
    json_in.close()
    return data


# ====================================================================================================================
""" Misc """


# Download and show progress
def download(url, path_to_file):
    """

    Ref: https://stackoverflow.com/questions/37573483/progress-bar-while-download-file-over-http-with-requests

    :param url:
    :param path_to_file:
    :return:
    """
    r = requests.get(url, stream=True)  # Streaming, so we can iterate over the response
    total_size = int(r.headers.get('content-length'))  # Total size in bytes
    block_size = 1024 * 1024
    wrote = 0

    directory = os.path.dirname(path_to_file)
    if not os.path.exists(directory):
        os.mkdir(directory)

    with open(path_to_file, 'wb') as f:
        for data in tqdm.tqdm(r.iter_content(block_size), total=total_size // block_size, unit='MB'):
            wrote = wrote + len(data)
            f.write(data)
    if total_size != 0 and wrote != total_size:
        print("ERROR, something went wrong")


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


# Get all subregions
def get_all_subregions(region_name, region_subregion_index):
    """
    Source:
    https://gist.github.com/douglasmiranda/5127251
    https://stackoverflow.com/questions/9807634/find-all-occurrences-of-a-key-in-nested-python-dictionaries-and-lists

    :param region_name: [str]
    :param region_subregion_index: [dict]
    :return:
    """
    for k, v in region_subregion_index.items():
        if k == region_name:
            yield v
        elif isinstance(v, dict):
            for x in get_all_subregions(region_name, v):
                yield x
        elif isinstance(v, list):
            for d in v:
                for y in get_all_subregions(region_name, d):
                    yield y
        else:
            pass


# Update a nested dictionary or similar mapping.
def update_nested_dict(source_dict, overrides):
    """
    Source: https://stackoverflow.com/questions/3232943/update-value-of-a-nested-dictionary-of-varying-depth

    :param source_dict: [dict]
    :param overrides: [dict]
    :return:
    """

    for key, val in overrides.items():
        if isinstance(val, collections.Mapping):
            source_dict[key] = update_nested_dict(source_dict.get(key, {}), val)
        elif isinstance(val, list):
            source_dict[key] = (source_dict.get(key, []) + val)
        else:
            source_dict[key] = overrides[key]
    return source_dict
