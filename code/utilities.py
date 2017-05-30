import copy
import functools
import json
import math
import os
import pickle
import re

import nltk.metrics
import pandas as pd
import shapely.geometry


# Change directory ===================================================================================================
def cdd_osm(*directories):
    # Current working directory
    path = os.getcwd()
    for directory in directories:
        path = os.path.join(path, directory)
    return path


# Change to data directory ===========================================================================================
def cdd_osm_dat(*directories):
    path = cdd_osm("dat")
    for directory in directories:
        path = os.path.join(path, directory)
    return path


# Make a dictionary with keys and values being shape_type code (in OSM .shp file) and shapely.geometry, respectively =
def osm_geom_types():
    shape_types = {'Point': shapely.geometry.Point,
                   'LineString': shapely.geometry.LineString,
                   'LinearRing': shapely.geometry.LinearRing,
                   'MultiLineString': shapely.geometry.MultiLineString,
                   'Polygon': shapely.geometry.Polygon,
                   'MultiPolygon': shapely.geometry.MultiPolygon,
                   'GeometryCollection': shapely.geometry.GeometryCollection}
    return shape_types


# Save pickles =======================================================================================================
def save_pickle(data, path_to_pickle):
    pickle_filename = os.path.basename(path_to_pickle)
    if os.path.isfile(path_to_pickle):
        print("Updating \"{}\" ... ".format(pickle_filename), end="")
    else:
        print("Saving \"{}\" ... ".format(pickle_filename), end="")
    try:
        pickle_out = open(path_to_pickle, 'wb')
        pickle.dump(data, pickle_out)
        pickle_out.close()
        print("Done.")
    except Exception as e:
        print("Failed.")
        print(e)


# Load pickles =======================================================================================================
def load_pickle(path_to_pickle):
    pickle_in = open(path_to_pickle, 'rb')
    data = pickle.load(pickle_in)
    pickle_in.close()
    return data


# Save and load json files ===========================================================================================
def save_json(data, path_to_json):
    json_filename = os.path.basename(path_to_json)
    if os.path.isfile(path_to_json):
        print("Updating \"{}\" ... ".format(json_filename), end="")
    else:
        print("Saving \"{}\" ... ".format(json_filename), end="")
    try:
        json_out = open(path_to_json, 'w')
        json.dump(data, json_out)
        json_out.close()
        print("Done.")
    except Exception as e:
        print("Failed.")
        print(e)


def load_json(path_to_json):
    json_in = open(path_to_json, 'r')
    data = json.load(json_in)
    json_in.close()
    return data


# Save data locally (.pickle, .csv or .xlsx) =========================================================================
def save(data, path_to_file, sep=',', sheet_name='Details', deep_copy=True):

    dat = copy.deepcopy(data) if deep_copy else copy.copy(data)

    # The specified path exists?
    os.makedirs(os.path.dirname(os.path.abspath(path_to_file)), exist_ok=True)

    # Get the file extension
    _, save_as = os.path.splitext(path_to_file)

    if isinstance(dat, pd.DataFrame) and dat.index.nlevels > 1:
        dat.reset_index(inplace=True)

    # Save the data according to the file extension
    print("Updating the data ... ", end="") if os.path.isfile(path_to_file) else print("Saving the data ... ", end="")
    if save_as == ".csv":  # Save the data to a .csv file
        dat.to_csv(path_to_file, index=False, sep=sep)
    elif save_as == ".xlsx":  # Save the data to a .xlsx file
        xlsx_writer = pd.ExcelWriter(path_to_file, engine='xlsxwriter')
        dat.to_excel(xlsx_writer, sheet_name, index=False)
        xlsx_writer.save()
        xlsx_writer.close()
    elif save_as == ".json":
        save_json(dat, path_to_file)
    else:
        save_pickle(dat, path_to_file)
    print("Done.")


# Find from a list the closest, case-insensitive, string to the given one ============================================
def find_match(x, lookup):
    # assert isinstance(x, str), "'x' must be a string."
    # assert isinstance(lookup, list) or isinstance(lookup, tuple), "'lookup' must be a list/tuple"
    if x is '' or x is None:
        return None
    else:
        for y in lookup:
            if re.match(x, y, re.IGNORECASE):
                return y


# Find similar string from a list of strings
def find_similar_str(s, strs):
    l_distances = [nltk.metrics.edit_distance(s, a, substitution_cost=100) for a in strs]
    the_one = strs[l_distances.index(min(l_distances))]
    return the_one


#
def distance_on_unit_sphere(x_coord, y_coord):
    """
    Reference:
    http://www.johndcook.com/blog/python_longitude_latitude/

    The following code returns the distance between two locations based on each point’s  longitude and latitude. The 
    distance returned is relative to Earth’s radius. To get the distance in miles, multiply by 3960. To get the 
    distance in kilometers, multiply by 6373.

    Latitude is measured in degrees north of the equator; southern locations have negative latitude. Similarly, 
    longitude is measured in degrees east of the Prime Meridian. A location 10° west of the Prime Meridian, 
    for example, could be expressed as either 350° east or as -10° east.

    :param x_coord: [list]
    :param y_coord: [list]
    :return:

    The code above assumes the earth is perfectly spherical. For a discussion of how accurate this assumption is, 
    see my blog post on http://www.johndcook.com/blog/2009/03/02/what-is-the-shape-of-the-earth/

    The algorithm used to calculate distances is described in detail at http://www.johndcook.com/lat_long_details.html

    A web page to calculate the distance between to cities based on longitude and latitude is available at 
    http://www.johndcook.com/lat_long_distance.html

    This code is in the public domain. Do whatever you want with it, no strings attached.

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

    cosine = (math.sin(phi1) * math.sin(phi2) * math.cos(theta1 - theta2) +
              math.cos(phi1) * math.cos(phi2))
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

    hypot(x, y) return the Euclidean norm, sqrt(x*x + y*y).
    This is the length of the vector from the origin to point (x, y).

    """
    # Define a function calculating distance between two points
    def distance(o, d):
        # math.hypot(o_long - d_long, o_lat - d_lat)
        return math.hypot(o[0] - d[0], o[1] - d[1])
    # Find the min value using the distance function with coord parameter
    return min(pts, key=functools.partial(distance, point))


# Midpoint of two GPS points
def get_gps_midpoint(x_long, x_lat, y_long, y_lat):
    """
    Reference: 
    http://code.activestate.com/recipes/577713-midpoint-of-two-gps-points/
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
