""" Load OSM data """

import glob
import itertools
import json
import os
import shutil
import time
import urllib.request
import zipfile
import re

import fuzzywuzzy.process
import geopandas as gpd
import ogr
import pandas as pd
import progressbar
import shapefile
import shapely.geometry

from download import get_download_url, make_file_path, download_subregion_osm_file, get_subregion_index
from psql import OSM
from utilities import cdd_osm_dat, load_pickle, save_pickle, osm_geometry_types


# Search the OSM directory and its sub-directories to get the path to the file =======================================
def fetch_osm_file(subregion, layer, feature=None, file_format=".shp", update=False):
    subregion_index = get_subregion_index("subregion-index", update)
    subregion_name = fuzzywuzzy.process.extractOne(subregion, subregion_index, score_cutoff=10)[0]
    subregion = subregion_name.lower().replace(" ", "-")
    osm_file_path = []

    for dirpath, dirnames, filenames in os.walk(cdd_osm_dat()):
        if feature is None:
            for fname in [f for f in filenames if (layer + "_a" in f or layer + "_free" in f) and f.endswith(
                    file_format)]:
                if subregion in os.path.basename(dirpath) and dirnames == []:
                    osm_file_path.append(os.path.join(dirpath, fname))
        else:
            for fname in [f for f in filenames if layer + "_" + feature in f and f.endswith(file_format)]:
                if subregion not in os.path.dirname(dirpath) and dirnames == []:
                    osm_file_path.append(os.path.join(dirpath, fname))
    # if len(osm_file_path) > 1:
    #     osm_file_path = [p for p in osm_file_path if "_a_" not in p]
    return osm_file_path


# Merge a set of .shp files (for a given layer) ======================================================================
def merge_shp_files(subregions, layer, update=False):
    """
    Layers include buildings, landuse, natural, places, points, railways, roads and waterways

    Create a .prj projection file for a .shp file: 
    http://geospatialpython.com/2011/02/create-prj-projection-file-for.html

    :param subregions: 
    :param layer:
    :param update: 
    :return:
    """
    # Make sure all the required shapefiles are ready
    subregion_name_and_download_url = [get_download_url(subregion, '.shp.zip') for subregion in subregions]
    # Download the requested OSM file
    filename_and_path = [make_file_path(download_url) for k, download_url in subregion_name_and_download_url]

    info_list = [list(itertools.chain(*x)) for x in zip(subregion_name_and_download_url, filename_and_path)]

    extract_dirs = []
    for subregion_name, download_url, filename, file_path in info_list:
        if not os.path.isfile(file_path) or update:

            # Make a custom bar to show downloading progress
            def make_custom_progressbar():
                widgets = [progressbar.Bar(), ' ',
                           progressbar.Percentage(),
                           ' [', progressbar.Timer(), '] ',
                           progressbar.FileTransferSpeed(),
                           ' (', progressbar.ETA(), ') ']
                progress_bar = progressbar.ProgressBar(widgets=widgets)
                return progress_bar

            pbar = make_custom_progressbar()

            def show_progress(block_count, block_size, total_size):
                if pbar.max_value is None:
                    pbar.max_value = total_size
                    pbar.start()
                pbar.update(block_count * block_size)

            urllib.request.urlretrieve(download_url, file_path, reporthook=show_progress)
            pbar.finish()
            time.sleep(0.01)
            print("\n'{}' is downloaded for {}.".format(filename, subregion_name))

        extract_dir = os.path.splitext(file_path)[0]
        with zipfile.ZipFile(file_path, 'r') as shp_zip:
            shp_zip.extractall(extract_dir)
            shp_zip.close()
        extract_dirs.append(extract_dir)

    # Specify a directory that stores files for the specific layer
    layer_path = cdd_osm_dat(os.path.commonpath(extract_dirs), layer)
    if not os.path.exists(layer_path):
        os.mkdir(layer_path)

    # Copy railways .shp files into Railways folder
    for subregion, p in zip(subregions, extract_dirs):
        for original_filename in glob.glob1(p, "*{}*".format(layer)):
            dest = os.path.join(layer_path, "{}_{}".format(subregion.lower().replace(' ', '-'), original_filename))
            shutil.copyfile(os.path.join(p, original_filename), dest)

    # Resource: http://geospatialpython.com/2011/02/merging-lots-of-shapefiles-quickly.html
    shp_file_paths = glob.glob(os.path.join(layer_path, '*.shp'))
    w = shapefile.Writer()
    for f in shp_file_paths:
        readf = shapefile.Reader(f)
        w.shapes().extend(readf.shapes())
        w.records.extend(readf.records())
        w.fields = list(readf.fields)
    w.save(os.path.join(layer_path, layer))


# (Alternative to geopandas.read_file()) =============================================================================
def read_shp_file(path_to_shp):
    """
    :param path_to_shp:
    :return:

    len(shp.records()) == shp.numRecords
    len(shp.shapes()) == shp.numRecords
    shp.bbox  # boundaries

    """

    # Read .shp file using shapefile.Reader()
    shp_reader = shapefile.Reader(path_to_shp)

    # Transform the data to a DataFrame
    filed_names = [field[0] for field in shp_reader.fields[1:]]
    shp_data = pd.DataFrame(shp_reader.records(), columns=filed_names)

    # shp_data['name'] = shp_data.name.str.encode('utf-8').str.decode('utf-8')  # Clean data
    shape_info = pd.DataFrame([(s.points, s.shapeType) for s in shp_reader.iterShapes()],
                              index=shp_data.index, columns=['coords', 'shape_type'])
    shp_data = shp_data.join(shape_info)

    return shp_data


#
def make_osm_pickle_file_path(extract_dir, layer, feature, suffix='shp'):
    subregion_name = os.path.basename(extract_dir).split('-')[0]
    filename = "-".join((s for s in [subregion_name, layer, feature, suffix] if s is not None)) + ".pickle"
    path_to_file = os.path.join(extract_dir, filename)
    return path_to_file


#
def read_shp_zip(subregion, layer, feature=None, update=False, keep_extracts=True):
    """
    :param subregion: 
    :param layer: 
    :param feature: 
    :param update: 
    :param keep_extracts: 
    :return: 
    """
    _, download_url = get_download_url(subregion, file_format=".shp.zip")
    _, file_path = make_file_path(download_url)

    extract_dir = os.path.splitext(file_path)[0]

    path_to_shp_pickle = make_osm_pickle_file_path(extract_dir, layer, feature)

    if os.path.isfile(path_to_shp_pickle) and not update:
        shp_data = load_pickle(path_to_shp_pickle)
    else:
        if not os.path.exists(extract_dir) or glob.glob(os.path.join(extract_dir, '*{}*.shp'.format(layer))) == [] or \
                update:

            if not os.path.isfile(file_path) or update:
                # Download the requested OSM file urlretrieve(download_url, file_path)
                download_subregion_osm_file(subregion, file_format='.shp.zip', update=update)

            with zipfile.ZipFile(file_path, 'r') as shp_zip:
                members = [f.filename for f in shp_zip.filelist if layer in f.filename]
                shp_zip.extractall(extract_dir, members)
                shp_zip.close()

        path_to_shp = glob.glob(os.path.join(extract_dir, "*{}*.shp".format(layer)))
        if len(path_to_shp) > 1:
            if feature is not None:
                path_to_shp_feature = [p for p in path_to_shp if layer + "_" + feature not in p]
                if len(path_to_shp_feature) == 1:  # The "a_*.shp" file does not exist
                    path_to_shp_feature = path_to_shp_feature[0]
                    shp_data = gpd.read_file(path_to_shp_feature)
                    shp_data = shp_data[shp_data.fclass == feature]
                    shp_data.crs = {'no_defs': True, 'ellps': 'WGS84', 'datum': 'WGS84', 'proj': 'longlat'}
                    shp_data.to_file(path_to_shp_feature.replace(layer, layer + "_" + feature), driver='ESRI Shapefile')
                else:   # An old .shp for feature is available, but an "a_" file also exists
                    shp_data = [gpd.read_file(p) for p in path_to_shp_feature]
                    shp_data = [dat[dat.fclass == feature] for dat in shp_data]
            else:  # feature is None
                path_to_orig_shp = [p for p in path_to_shp if layer + '_a' in p or layer + '_free' in p]
                if len(path_to_orig_shp) > 1:  # An "a_*.shp" file does not exist
                    shp_data = [gpd.read_file(p) for p in path_to_shp]
                    # shp_data = pd.concat([read_shp_file(p) for p in path_to_shp], axis=0, ignore_index=True)
                else:  # The "a_*.shp" file does not exist
                    shp_data = gpd.read_file(path_to_orig_shp[0])
        else:
            path_to_shp = path_to_shp[0]
            shp_data = gpd.read_file(path_to_shp)  # gpd.GeoDataFrame(read_shp_file(path_to_shp))
            if feature is not None:
                shp_data = gpd.GeoDataFrame(shp_data[shp_data.fclass == feature])
                path_to_shp_feature = path_to_shp.replace(layer, layer + "_" + feature)
                shp_data = shp_data[shp_data.fclass == feature]
                shp_data.crs = {'no_defs': True, 'ellps': 'WGS84', 'datum': 'WGS84', 'proj': 'longlat'}
                shp_data.to_file(path_to_shp_feature, driver='ESRI Shapefile')

        if not keep_extracts:
            # import shutil
            # shutil.rmtree(extract_dir)
            for f in glob.glob(os.path.join(extract_dir, "gis.osm*")):
                # if layer not in f:
                os.remove(f)

        save_pickle(shp_data, path_to_shp_pickle)

    return shp_data


#
def get_local_file_path(subregion, file_format='.osm.pbf'):
    """
    :param subregion: 
    :param file_format: 
    :return: 
    """
    _, download_url = get_download_url(subregion, file_format)
    _, file_path = make_file_path(download_url)
    return file_path


#
def parse_other_tags(x):
    """
    :param x: [str] or None
    :return:
    """
    if x is not None:
        raw_other_tags = [re.sub('^"|"$', '', each_tag) for each_tag in re.split('(?<="),(?=")', x)]
        other_tags = {k: v.replace('<br>', ' ') for k, v in (each_tag.split('"=>"') for each_tag in raw_other_tags)}
    else:
        other_tags = x
    return other_tags


#
def parse_osm_pbf(subregion):
    """
    OpenStreetMap XML and PBF (GDAL/OGR >= 1.10.0)

    The driver will categorize features into 5 layers :
        'points'            - 0: "node" features that have significant tags attached
        'lines'             - 1: "way" features that are recognized as non-area
        'multilinestrings'  - 2: "relation" features that form a multilinestring(type='multilinestring' or type='route')
        'multipolygons'     - 3; "relation" features that form a multipolygon (type='multipolygon' or type='boundary'),
                                 and "way" features that are recognized as area
        'other_relations'   - 4: "relation" features that do not belong to the above 2 layers

    """
    osm_pbf_file = get_local_file_path(subregion, file_format='.osm.pbf')

    if not os.path.isfile(osm_pbf_file):
        download_subregion_osm_file(subregion, file_format='.osm.pbf')

    osm = ogr.Open(osm_pbf_file)

    # Grab available layers in file, i.e. points, lines, multilinestrings, multipolygons, and other_relations
    layer_count = osm.GetLayerCount()
    layer_names, layer_data = [], []
    # Loop through all available layers
    for i in range(layer_count):
        lyr = osm.GetLayerByIndex(i)  # Hold the i-th layer
        layer_names.append(lyr.GetName())  # Get the name of the i-th layer

        # Get features from the i-th layer
        feat = lyr.GetNextFeature()
        feat_data = []
        while feat is not None:
            feat_dat = json.loads(feat.ExportToJson())
            feat_data.append(feat_dat)
            feat.Destroy()
            feat = lyr.GetNextFeature()

        layer_data.append(pd.DataFrame(feat_data))

    # Make a dictionary, {layer_name: layer_DataFrame}
    data = dict(zip(layer_names, layer_data))

    return data


#
def format_single_geometry(geo_type, coordinates):
    geo_type_func = osm_geometry_types()
    if not geo_type.startswith('Multi'):
        return geo_type_func[geo_type](coordinates)
    else:
        multi_poly = [shapely.geometry.Polygon(poly) for poly in coordinates[0]]
        return shapely.geometry.MultiPolygon(multi_poly)


#
def format_geometries(geometries):
    geo_types, coordinates = [geo['type'] for geo in geometries], [geo['coordinates'] for geo in geometries]
    geo_type_func = osm_geometry_types()
    geo_collection = [geo_type_func[geo_type](coord) if geo_type != 'Polygon' else geo_type_func[geo_type](coord[0])
                      for geo_type, coord in zip(geo_types, coordinates)]
    return shapely.geometry.GeometryCollection(geo_collection)


#
def parse_layer_data(dat, geo_type):

    dat_properties = pd.DataFrame(x for x in dat.properties)
    dat_geometries = pd.DataFrame(x for x in dat.geometry).rename(columns={'type': 'geo_type'})
    data = dat_properties.join(dat_geometries)
    data.other_tags = data.other_tags.map(parse_other_tags)

    if geo_type != 'other_relations':
        data.coordinates = data.apply(lambda x: format_single_geometry(x.geo_type, x.coordinates), axis=1)
    else:  # geo_type == 'other_relations'
        data.coordinates = data.geometries.map(format_geometries)

    return data


#
def read_osm_pbf(subregion):

    osm_data = parse_osm_pbf(subregion)

    layer_data = []
    for geo_type, dat in osm_data.items():
        layer_dat = parse_layer_data(dat, geo_type)
        layer_data.append(layer_dat)

    osm_pbf_data = dict(zip(list(osm_data.keys()), layer_data))

    return osm_pbf_data


# osmdb = OSM()
# data.to_sql('points', osmdb.engine, index=False)
# x = pd.read_sql_table('points', osmdb.engine, index_col='index')
# lambda x: json.loads('{' + x.other_tags.replace('=>', ':') + '}')
