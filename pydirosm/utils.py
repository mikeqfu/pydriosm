""" Utilities - Helper functions """

import copy
import functools
import json
import math
import os
import pickle
import re

import nltk.metrics
import pandas as pd
import progressbar
import requests
import shapely.geometry
import tqdm


# Type to confirm whether to proceed or not
def confirmed(prompt=None, resp=False):
    """
    Reference: http://pydirosm.activestate.com/recipes/541096-prompt-the-user-for-confirmation/

    :param prompt: [str] or None
    :param resp: [bool]
    :return:

    Example: confirm(prompt="Create Directory?", resp=True)
             Create Directory? Yes|No:

    """
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


# ====================================================================================================================
""" Change directory """


# Change directory and sub-directories
def cd(*directories):
    # Current working directory
    path = os.getcwd()
    for directory in directories:
        path = os.path.join(path, directory)
    return path


# Change directory to "dat" and sub-directories
def cd_dat(*directories):
    path = cd("dat")
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


# Save and load json files
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


def load_json(path_to_json):
    """
    :param path_to_json: [str] local file path
    :return: the json data retrieved
    """
    json_in = open(path_to_json, 'r')
    data = json.load(json_in)
    json_in.close()
    return data


# Save Excel workbook
def save_workbook(excel_data, path_to_excel, sep, sheet_name, engine='xlsxwriter'):
    """
    :param excel_data: any [DataFrame] that could be dumped saved as a Excel workbook, e.g. '.csv', '.xlsx'
    :param path_to_excel: [str] local file path
    :param sep: [str] separator for saving excel_data to a '.csv' file
    :param sheet_name: [str] name of worksheet for saving the excel_data to a e.g. '.xlsx' file
    :param engine: [str] ExcelWriter engine; pandas writes Excel files using the 'xlwt' module for '.xls' files and the
                        'openpyxl' or 'xlsxWriter' modules for '.xlsx' files.
    :return: whether the data has been successfully saved or updated
    """
    excel_filename = os.path.basename(path_to_excel)
    filename, save_as = os.path.splitext(excel_filename)
    print("{} \"{}\" ... ".format("Updating" if os.path.isfile(path_to_excel) else "Saving", excel_filename), end="")
    try:
        os.makedirs(os.path.dirname(path_to_excel), exist_ok=True)
        if save_as == ".csv":  # Save the data to a .csv file
            excel_data.to_csv(path_to_excel, index=False, sep=sep)
        else:  # Save the data to a .xlsx or .xls file
            xlsx_writer = pd.ExcelWriter(path_to_excel, engine)
            excel_data.to_excel(xlsx_writer, sheet_name, index=False)
            xlsx_writer.save()
            xlsx_writer.close()
        print("Done.")
    except Exception as e:
        print("failed due to {}.".format(e))


# Save data locally (.pickle, .csv or .xlsx)
def save(data, path_to_file, sep=',', engine='xlsxwriter', sheet_name='Details', deep_copy=True):
    """
    :param data: any object that could be dumped
    :param path_to_file: [str] local file path
    :param sep: [str] separator for '.csv'
    :param engine: [str] 'xlwt' for .xls; 'xlsxwriter' or 'openpyxl' for .xlsx
    :param sheet_name: [str] name of worksheet
    :param deep_copy: [bool] whether make a deep copy of the data before saving it
    :return: whether the data has been successfully saved or updated
    """

    dat = copy.deepcopy(data) if deep_copy else copy.copy(data)

    # The specified path exists?
    os.makedirs(os.path.dirname(os.path.abspath(path_to_file)), exist_ok=True)

    # Get the file extension
    _, save_as = os.path.splitext(path_to_file)

    if isinstance(dat, pd.DataFrame) and dat.index.nlevels > 1:
        dat.reset_index(inplace=True)

    # Save the data according to the file extension
    if save_as == ".csv" or save_as == ".xlsx" or save_as == ".xls":
        save_workbook(dat, path_to_file, sep, sheet_name, engine)
    elif save_as == ".json":
        save_json(dat, path_to_file)
    else:
        save_pickle(dat, path_to_file)


# ====================================================================================================================
""" Misc """


#
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
    with open(path_to_file, 'wb') as f:
        for data in tqdm.tqdm(r.iter_content(block_size), total=total_size//block_size, unit='MB'):
            wrote = wrote + len(data)
            f.write(data)
    if total_size != 0 and wrote != total_size:
        print("ERROR, something went wrong")


# Make a custom bar to show downloading progress --------------------------
def make_custom_progressbar():
    widgets = [progressbar.Bar(),
               ' ',
               progressbar.Percentage(),
               ' [',
               progressbar.Timer(),
               '] ',
               progressbar.FileTransferSpeed(),
               ' (',
               progressbar.ETA(),
               ') ']
    progress_bar = progressbar.ProgressBar(widgets=widgets)
    return progress_bar


#
def show_progress(block_count, block_size, total_size):
    p_bar = make_custom_progressbar()
    if p_bar.max_value is None:
        p_bar.max_value = total_size
        p_bar.start()
    p_bar.update(min(block_count * block_size, total_size))


# Make a dictionary with keys and values being shape_type pydirosm (in OSM .shp file) and shapely.geometry, respectively =
def osm_geom_types():
    shape_types = {'Point': shapely.geometry.Point,
                   'LineString': shapely.geometry.LineString,
                   'LinearRing': shapely.geometry.LinearRing,
                   'MultiLineString': shapely.geometry.MultiLineString,
                   'Polygon': shapely.geometry.Polygon,
                   'MultiPolygon': shapely.geometry.MultiPolygon,
                   'GeometryCollection': shapely.geometry.GeometryCollection}
    return shape_types


# Find from a list the closest, case-insensitive, str to the given one
def find_match(x, lookup):
    """
    :param x: [str] If x is None, return None
    :param lookup: [list], [tuple] or any other iterable object
    :return: [str], [list]
    """
    # assert isinstance(x, str), "'x' must be a string."
    # assert isinstance(lookup, list) or isinstance(lookup, tuple), "'lookup' must be a list/tuple"
    if x is '' or x is None:
        return None
    else:
        for y in lookup:
            if re.match(x, y, re.IGNORECASE):
                return y


# Find similar string from a list of strings
def find_similar_str(s, str_list):
    l_distances = [nltk.metrics.edit_distance(s, a, substitution_cost=100) for a in str_list]
    the_one = str_list[l_distances.index(min(l_distances))]
    return the_one


#
def distance_on_unit_sphere(x_coord, y_coord):
    """
    Reference:
    http://www.johndcook.com/blog/python_longitude_latitude/

    The following pydirosm returns the distance between two locations based on each point’s  longitude and latitude. The
    distance returned is relative to Earth’s radius. To get the distance in miles, multiply by 3960. To get the 
    distance in kilometers, multiply by 6373.

    Latitude is measured in degrees north of the equator; southern locations have negative latitude. Similarly, 
    longitude is measured in degrees east of the Prime Meridian. A location 10° west of the Prime Meridian, 
    for example, could be expressed as either 350° east or as -10° east.

    :param x_coord: [list]
    :param y_coord: [list]
    :return:

    The pydirosm above assumes the earth is perfectly spherical. For a discussion of how accurate this assumption is,
    see my blog post on http://www.johndcook.com/blog/2009/03/02/what-is-the-shape-of-the-earth/

    The algorithm used to calculate distances is described in detail at http://www.johndcook.com/lat_long_details.html

    A web page to calculate the distance between to cities based on longitude and latitude is available at 
    http://www.johndcook.com/lat_long_distance.html

    This pydirosm is in the public domain. Do whatever you want with it, no strings attached.

    """
    lat1, long1 = x_coord[0], x_coord[1]
    lat2, long2 = y_coord[0], y_coord[1]

    # Convert latitude and longitude to spherical coordinates in radians.
    degrees_to_radians = math.pi / 180.0

    # phi = 90 - latitude
    phi1 = (90.0 - lat1) * degrees_to_radians
    phi2 = (90.0 - lat2) * degrees_to_radians

    # theta = longitude
    theta1 = long1 * degrees_to_radians
    theta2 = long2 * degrees_to_radians

    # Compute spherical distance from spherical coordinates.

    # For two locations in spherical coordinates
    # (1, theta, phi) and (1, theta', phi')
    # cosine( arc length ) = sin phi sin phi' cos(theta-theta') + cos phi cos phi'
    # distance = rho * arc length

    cosine = (math.sin(phi1) * math.sin(phi2) * math.cos(theta1 - theta2) + math.cos(phi1) * math.cos(phi2))
    arc = math.acos(cosine) * 3960  # in miles

    # Remember to multiply arc by the radius of the earth
    # in your favorite set of units to get length.
    return arc


#
def find_closest_point(point, pts):
    """
    :param point: (long, lat)
    :param pts: a sequence of reference points
    :return:

    math.hypot(x, y) return the Euclidean norm, sqrt(x*x + y*y).
    This is the length of the vector from the origin to point (x, y).

    """
    # Define a function calculating distance between two points
    def distance(o, d):
        return math.hypot(o[0] - d[0], o[1] - d[1])
    # Find the min value using the distance function with coord parameter
    return min(pts, key=functools.partial(distance, point))


# Midpoint of two GPS points
def get_gps_midpoint(x_long, x_lat, y_long, y_lat):
    """
    Reference: 
    http://pydirosm.activestate.com/recipes/577713-midpoint-of-two-gps-points/
    http://www.movable-type.co.uk/scripts/latlong.html
    """
    # Input values as degrees, convert them to radians
    long_1, lat_1 = math.radians(x_long), math.radians(x_lat)
    long_2, lat_2 = math.radians(y_long), math.radians(y_lat)

    b_x, b_y = math.cos(lat_2) * math.cos(long_2 - long_1), math.cos(lat_2) * math.sin(long_2 - long_1)
    lat_3 = math.atan2(math.sin(lat_1) + math.sin(lat_2),
                       math.sqrt((math.cos(lat_1) + b_x) * (math.cos(lat_1) + b_x) + b_y ** 2))
    long_3 = long_1 + math.atan2(b_y, math.cos(lat_1) + b_x)

    midpoint = math.degrees(long_3), math.degrees(lat_3)

    return midpoint


# (between <shapely.geometry.point.Point>s)
def get_midpoint(start_point, end_point):
    """
    :param start_point: [shapely.geometry.point.Point]
    :param end_point: [shapely.geometry.point.Point]
    :return: 
    """
    midpoint = (start_point.x + end_point.x) / 2, (start_point.y + end_point.y) / 2
    return midpoint
