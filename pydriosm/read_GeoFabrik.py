""" Parse/read OSM data """

import errno
import glob
import itertools
import rapidjson
import os
import re
import shutil
import zipfile

import fuzzywuzzy.process
import geopandas as gpd
import ogr
import pandas as pd
import shapefile
import shapely.geometry

import pydriosm.download_GeoFabrik as dGF
from pydriosm.utils import cd_dat_geofabrik, confirmed, download, load_pickle, osm_geom_types, save_pickle


# Search the OSM data directory and its sub-directories to get the path to the file
def fetch_osm_file(subregion_name, layer, feature=None, file_format=".shp", update=False):
    """
    :param subregion_name: [str] Name of a subregion, e.g. 'england', 'oxfordshire', or 'Europe'; case-insensitive
    :param layer: [str] Name of a OSM layer, e.g. 'railways'
    :param feature: [str] Name of a feature, e.g. 'rail'; if None, all available features included; default None
    :param file_format: [str] Extension of a file; e.g. ".shp" (default)
    :param update: [bool] indicates whether to update the relevant file/information; default False
    :return: [list] a list of paths
                fetch_osm_file('england', 'railways', feature=None, file_format=".shp", update=False) should return
                ['...\\dat_GeoFabrik\\Europe\\Great Britain\\england-latest-free.shp\\gis.osm_railways_free_1.shp'],
                if such a file exists, and [] otherwise.
    """
    subregion_names = dGF.get_subregion_info_index("GeoFabrik-subregion-name-list", update=update)
    subregion_name_ = fuzzywuzzy.process.extractOne(subregion_name, subregion_names, score_cutoff=10)[0]
    subregion = subregion_name_.lower().replace(" ", "-")
    osm_file_path = []

    for dir_path, dir_names, filenames in os.walk(cd_dat_geofabrik()):
        if feature is None:
            for f_name in [f for f in filenames if (layer + "_a" in f or layer + "_free" in f) and f.endswith(
                    file_format)]:
                if subregion in os.path.basename(dir_path) and dir_names == []:
                    osm_file_path.append(os.path.join(dir_path, f_name))
        else:
            for f_name in [f for f in filenames if layer + "_" + feature in f and f.endswith(file_format)]:
                if subregion not in os.path.dirname(dir_path) and dir_names == []:
                    osm_file_path.append(os.path.join(dir_path, f_name))
    # if len(osm_file_path) > 1:
    #     osm_file_path = [p for p in osm_file_path if "_a_" not in p]
    if not osm_file_path:
        print("The required file may not exist.")
        osm_file_path = None
    return osm_file_path


# Get the local path to a OSM file
def get_local_file_path(subregion_name, file_format=".osm.pbf"):
    """
    :param subregion_name: [str] name of a subregion, e.g. 'england'
    :param file_format: [str] ".osm.pbf" (default), ".shp.zip", or ".osm.bz2"
    :return: [str] default local path to the file with the extension of the specified file_format
    """
    subregion_name_, download_url = dGF.get_download_url(subregion_name, file_format, update=False)
    _, file_path = dGF.make_default_file_path(subregion_name_, file_format)
    return file_path


""" ================================================ .shp.zip files ============================================== """


# (Alternative to, though not the same as, geopandas.read_file())
def read_shp_file(path_to_shp):
    """
    :param path_to_shp: [str] path to a .shp file
    :return: [DataFrame]

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
                              index=shp_data.index,
                              columns=['coords', 'shape_type'])
    shp_data = shp_data.join(shape_info)

    return shp_data


# Merge a set of .shp files (for a given layer)
def merge_shp_files(subregion_names, layer, update=False, download_confirmation_required=True):
    """
    :param subregion_names: [list] a sequence of subregion names, e.g. ['cambridgeshire', 'oxfordshire']
    :param layer: [str] name of a OSM layer, e.g. 'railways'
    :param update: [bool] indicates whether to update the relevant file/information; default False
    :param download_confirmation_required: [bool]

    Layers include buildings, landuse, natural, places, points, railways, roads and waterways

    Note that this function does not create projection (.prj) for the merged map. Refer to
    http://geospatialpython.com/2011/02/create-prj-projection-file-for.html for creating a .prj file.

    """
    # Make sure all the required shape files are ready
    subregion_name_and_url = [dGF.get_download_url(subregion_name, ".shp.zip") for subregion_name in subregion_names]
    # Download the requested OSM file
    filename_and_path = [dGF.make_default_file_path(k, ".shp.zip") for k, _ in subregion_name_and_url]

    info_list = [list(itertools.chain(*x)) for x in zip(subregion_name_and_url, filename_and_path)]

    extract_dirs = []
    for subregion_name, download_url, filename, path_to_shp in info_list:
        if not os.path.isfile(path_to_shp) or update:
            if confirmed(prompt="\nTo download {}?".format(os.path.basename(path_to_shp)),
                         resp=False, confirmation_required=download_confirmation_required):
                try:
                    download(download_url, path_to_shp)
                    print("\n\"{}\" has been downloaded for \"{}\", which is now available at \n{}".format(
                        filename, subregion_name, path_to_shp))
                except Exception as e:
                    print("\nFailed to download \"{}\". {}.".format(filename, e))

        extract_dir = os.path.splitext(path_to_shp)[0]
        with zipfile.ZipFile(path_to_shp, 'r') as shp_zip:
            shp_zip.extractall(extract_dir)
            shp_zip.close()
        extract_dirs.append(extract_dir)

    # Specify a directory that stores files for the specific layer
    layer_path = cd_dat_geofabrik(os.path.commonpath(extract_dirs), layer)
    if not os.path.exists(layer_path):
        os.mkdir(layer_path)

    # Copy railways .shp files into Railways folder
    for subregion, p in zip(subregion_names, extract_dirs):
        for original_filename in glob.glob1(p, "*{}*".format(layer)):
            dest = os.path.join(layer_path, "{}_{}".format(subregion.lower().replace(' ', '-'), original_filename))
            shutil.copyfile(os.path.join(p, original_filename), dest)

    # Resource: https://github.com/GeospatialPython/pyshp
    shp_file_paths = glob.glob(os.path.join(layer_path, '*.shp'))

    merged_shp_filename = os.path.join(layer_path, "_".join(["merged", layer]))
    w = shapefile.Writer(merged_shp_filename)
    try:
        for f in shp_file_paths:
            r = shapefile.Reader(f)
            w.fields = r.fields[1:]  # skip first deletion field
            w.shapeType = r.shapeType
            for shaperec in r.iterShapeRecords():
                w.record(*shaperec.record)
                w.shape(shaperec.shape)
        w.close()
        print("\nMerging shape files ... Successfully. \nCheck \"{}\".".format(layer_path))
    except Exception as e:
        print("\nFailed to merge the shape files at {}: ".format(os.path.dirname(merged_shp_filename)))
        for i in shp_file_paths:
            print(os.path.basename(i))
        print(e)


# Read a .shp.zip file
def read_shp_zip(subregion_name, layer, feature=None,
                 update=False, download_confirmation_required=True, keep_extracts=True, pickle_it=True):
    """
    :param subregion_name: [str] name of a subregion, e.g. 'england', 'oxfordshire', or 'europe'; case-insensitive
    :param layer: [str] name of a OSM layer, e.g. 'railways'
    :param feature: [str] name of a feature, e.g. 'rail'; if None, all available features included; default None
    :param update: [bool] indicates whether to update the relevant file/information; default False
    :param download_confirmation_required: [bool]
    :param keep_extracts: [bool] indicates whether to keep extracted files from the .shp.zip file; default True
    :param pickle_it: [bool]
    :return: [GeoDataFrame]
    """
    subregion_name_, _ = dGF.get_download_url(subregion_name, file_format=".shp.zip")
    _, path_to_shp_zip = dGF.make_default_file_path(subregion_name_, file_format=".shp.zip")

    extract_dir = os.path.splitext(path_to_shp_zip)[0]

    # Make a local path for saving the pickle file later
    def make_shp_pickle_file_path(extr_dir, lyr, feat, suffix='shp'):
        """
        :param extr_dir: [str] a directory for storing extracted files from the .shp.zip file
        :param lyr: [str] ditto
        :param feat: [str] ditto
        :param suffix: [str] a suffix to the filename
        :return: [str] a path to save the pickle file eventually
        """
        region_name = os.path.basename(extr_dir).split('-')[0]
        filename = "-".join((s for s in [region_name, lyr, feat, suffix] if s is not None)) + ".pickle"
        path_to_file = os.path.join(extr_dir, filename)
        return path_to_file

    path_to_shp_pickle = make_shp_pickle_file_path(extract_dir, layer, feature)

    if os.path.isfile(path_to_shp_pickle) and not update:
        shp_data = load_pickle(path_to_shp_pickle)
    else:
        if not os.path.exists(extract_dir) or glob.glob(os.path.join(extract_dir, '*{}*.shp'.format(layer))) == [] or \
                update:

            if not os.path.isfile(path_to_shp_zip) or update:
                # Download the requested OSM file urlretrieve(download_url, file_path)
                if confirmed(prompt="To download {}?".format(os.path.basename(path_to_shp_zip)),
                             resp=False, confirmation_required=download_confirmation_required):
                    dGF.download_subregion_osm_file(subregion_name, file_format='.shp.zip', update=update)

            with zipfile.ZipFile(path_to_shp_zip, 'r') as shp_zip:
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
                else:  # An old .shp for feature is available, but an "a_" file also exists
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

        if pickle_it:
            save_pickle(shp_data, path_to_shp_pickle)

    return shp_data


""" ================================================ .osm.pbf files ============================================== """


# Justify the input, 'subregion', in the following functions
def justify_subregion_input(subregion):
    if os.path.isabs(subregion):
        assert subregion.endswith(".osm.pbf"), "'subregion' is invalid."
        path_to_osm_pbf = subregion
    else:
        path_to_osm_pbf = get_local_file_path(subregion)
    subregion_filename = os.path.basename(path_to_osm_pbf)
    return subregion_filename, path_to_osm_pbf


# Get names of all layers contained in the .osm.pbf file for a given subregion
def get_osm_pbf_layer_idx_names(subregion, update=False, download_confirmation_required=True):
    """
    :param subregion: [str] Name of a (sub)region or path to the file
    :param update: [bool] indicate whether to update the .osm.pbf file; default, False
    :param download_confirmation_required: [bool]
    :return: [dict] or None
    """
    subregion_filename, path_to_osm_pbf = justify_subregion_input(subregion)

    # If the target file is not available, download it.
    if not os.path.isfile(path_to_osm_pbf) or update:
        if confirmed(prompt="To download \"{}\"?".format(subregion_filename, resp=False),
                     resp=False, confirmation_required=download_confirmation_required):
            dGF.download_subregion_osm_file(subregion_filename, download_path=path_to_osm_pbf, update=update)

    try:
        # Start parsing the '.osm.pbf' file
        osm_pbf = ogr.Open(path_to_osm_pbf)

        # Find out the available layers in the file
        layer_count, layer_names = osm_pbf.GetLayerCount(), []

        # Loop through all available layers
        for i in range(layer_count):
            lyr = osm_pbf.GetLayerByIndex(i)  # Hold the i-th layer
            layer_names.append(lyr.GetName())  # Get the name of the i-th layer

        layer_idx_names = dict(zip(range(layer_count), layer_names))

    except Exception as e:
        print("Failed to get layer names in \"{}\". {}.".format(subregion_filename, e))
        layer_idx_names = None

    return layer_idx_names


# Read '.osm.pbf' file roughly into pandas.DataFrames
def read_raw_osm_pbf(subregion, update=False, download_confirmation_required=True, pickle_it=True, rm_raw_file=True):
    """
    Reference: http://www.gdal.org/drv_osm.html

    OpenStreetMap XML and PBF (GDAL/OGR >= 1.10.0)
    The driver will categorize features into 5 layers :
        'points'            - 0: "node" features that have significant tags attached
        'lines'             - 1: "way" features that are recognized as non-area
        'multilinestrings'  - 2: "relation" features that form a multilinestring(type='multilinestring' or type='route')
        'multipolygons'     - 3; "relation" features that form a multipolygon (type='multipolygon' or type='boundary'),
                                 and "way" features that are recognized as area
        'other_relations'   - 4: "relation" features that do not belong to the above 2 layers


    :param subregion: [str] Name of subregion or customised path of a .osm.pbf file
                        If 'subregion' is the name of the subregion, the default file path will be used.
    :param update: [bool]
    :param download_confirmation_required: [bool]
    :param pickle_it: [bool]
    :param rm_raw_file: [bool]
    :return: [dict] or None
    """
    subregion_filename, path_to_osm_pbf = justify_subregion_input(subregion)

    path_to_pickle = path_to_osm_pbf.replace(".osm.pbf", "-preprocessed.pickle")
    if os.path.isfile(path_to_pickle) and not update:
        raw_osm_pbf_data = load_pickle(path_to_pickle)
    else:
        # If the target file is not available, try downloading it first.
        if not os.path.isfile(path_to_osm_pbf) or update:
            if confirmed(prompt="To download \"{}\"?".format(subregion_filename),
                         resp=False, confirmation_required=download_confirmation_required):
                dGF.download_subregion_osm_file(subregion, download_path=path_to_osm_pbf, update=update)

        if os.path.isfile(path_to_osm_pbf):
            print("\nParsing \"{}\" ... ".format(subregion_filename), end="")
            try:
                # Start parsing the '.osm.pbf' file
                raw_osm_pbf = ogr.Open(path_to_osm_pbf)

                # Grab available layers in file: points, lines, multilinestrings, multipolygons, & other_relations
                layer_count, layer_names, layer_data = raw_osm_pbf.GetLayerCount(), [], []

                # Loop through all available layers
                for i in range(layer_count):
                    lyr = raw_osm_pbf.GetLayerByIndex(i)  # Hold the i-th layer
                    layer_names.append(lyr.GetName())  # Get the name of the i-th layer
                    # # https://gdal.org/python/osgeo.ogr.Feature-class.html
                    # feat, feat_data = lyr.GetNextFeature(), []  # Get features from the i-th layer
                    # while feat is not None:
                    #     feat_dat = rapidjson.loads(feat.ExportToJson())
                    #     feat_data.append(feat_dat)
                    #     feat.Destroy()
                    #     feat = lyr.GetNextFeature()
                    layer_data.append(pd.DataFrame(rapidjson.loads(feat.ExportToJson()) for _, feat in enumerate(lyr)))
                raw_osm_pbf.Release()

                # Make a dictionary, {layer_name: layer_DataFrame}
                raw_osm_pbf_data = dict(zip(layer_names, layer_data))

                print("Successfully.\n")

            except Exception as e:
                err_msg = e if os.path.isfile(path_to_osm_pbf) else os.strerror(errno.ENOENT)
                print("Failed. {}.\n".format(err_msg))
                raw_osm_pbf_data = None

            if pickle_it:
                save_pickle(raw_osm_pbf_data, path_to_pickle)

            if rm_raw_file:
                dGF.remove_subregion_osm_file(path_to_osm_pbf)

        else:
            print("\"{}\" is not available.\n".format(os.path.basename(path_to_osm_pbf)))
            raw_osm_pbf_data = None

    return raw_osm_pbf_data


# Parse each layer's data
def parse_layer_data(layer_data, geo_typ, parse_other_tags=True, fmt_single_geom=True, fmt_multi_geom=True):
    """
    :param layer_data: [pandas.DataFrame]
    :param geo_typ: [str]
    :param parse_other_tags: [bool]
    :param fmt_single_geom: [bool]
    :param fmt_multi_geom: [bool]
    :return:
    """

    # Transform a 'other_tags' into a dictionary
    def parse_other_tags_column(x):
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

    # Format the coordinates with shapely.geometry
    def format_single_geometry(geom_data):
        geom_types_funcs, geom_type = osm_geom_types(), list(set(geom_data.geom_type))[0]
        geom_type_func = geom_types_funcs[geom_type]
        if geom_type == 'MultiPolygon':
            sub_geom_type_func = geom_types_funcs[geom_type.lstrip('Multi')]
            geom_coords = geom_data.coordinates.map(
                lambda x: geom_type_func(sub_geom_type_func(l) for ls in x for l in ls))
        else:
            geom_coords = geom_data.coordinates.map(geom_type_func)
        return geom_coords

    # Format geometry collections with shapely.geometry
    def format_multi_geometries(geometries):
        geom_types, coordinates = [geom['type'] for geom in geometries], [geoms['coordinates'] for geoms in geometries]
        geom_types_funcs = osm_geom_types()
        geom_collection = [geom_types_funcs[geom_type](coords)
                           if 'Polygon' not in geom_type
                           else geom_types_funcs[geom_type](pt for pts in coords for pt in pts)
                           for geom_type, coords in zip(geom_types, coordinates)]
        return shapely.geometry.GeometryCollection(geom_collection)

    dat_properties = pd.DataFrame(x for x in layer_data.properties)
    dat_geometries = pd.DataFrame(x for x in layer_data.geometry).rename(columns={'type': 'geom_type'})
    parsed_layer_data = dat_properties.join(dat_geometries)

    if parse_other_tags:
        parsed_layer_data.other_tags = parsed_layer_data.other_tags.map(parse_other_tags_column)

    if geo_typ != 'other_relations':  # geo_type is any of 'points', 'lines', 'multilinestrings', and 'multipolygons'
        if fmt_single_geom:
            parsed_layer_data.coordinates = format_single_geometry(parsed_layer_data[['geom_type', 'coordinates']])
    else:  # geo_typ == 'other_relations'
        if fmt_multi_geom:
            parsed_layer_data['coordinates'] = parsed_layer_data.geometries.map(format_multi_geometries)

    return parsed_layer_data


# Read parsed .osm.pbf data for a specific subregion
def read_parsed_osm_pbf(subregion, update_osm_pbf=False, download_confirmation_required=True,
                        parse_other_tags=True, fmt_single_geom=True, fmt_multi_geom=True,
                        pickle_it=True, update=False):
    """
    :param subregion: [str] Name of subregion or customised path of a .osm.pbf file
                        If 'subregion' is the name of the subregion, the default file path will be used.
    :param update_osm_pbf: [bool]
    :param download_confirmation_required: [bool]
    :param parse_other_tags: [bool]
    :param fmt_single_geom: [bool]
    :param fmt_multi_geom: [bool]
    :param pickle_it: [bool]
    :param update: [bool]
    :return:
    """
    subregion_filename, path_to_osm_pbf = justify_subregion_input(subregion)

    path_to_pickle = path_to_osm_pbf.replace(".osm.pbf", "-parsed.pickle")

    if os.path.isfile(path_to_pickle) and not update:
        osm_pbf = load_pickle(path_to_pickle)
    else:
        raw_osm_pbf_data = read_raw_osm_pbf(subregion, update_osm_pbf, download_confirmation_required,
                                            pickle_it=True, rm_raw_file=True)

        parsed_data, geom_types = [], []
        for geom_type, layer_data in raw_osm_pbf_data.items():
            geom_types.append(geom_type)
            try:
                parsed_lyr_dat = parse_layer_data(layer_data, geom_type,
                                                  parse_other_tags, fmt_single_geom, fmt_multi_geom)
            except Exception as e:
                print("Failed to parse \"{}\" for \"{}\". {}".format(geom_type, subregion, e))
                parsed_lyr_dat = None

            parsed_data.append(parsed_lyr_dat)

        osm_pbf = dict(zip(geom_types, parsed_data))

        if pickle_it:
            save_pickle(osm_pbf, path_to_pickle)

    return osm_pbf
