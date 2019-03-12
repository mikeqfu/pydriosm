""" Parse/read OSM data """

import gc
import glob
import itertools
import math
import os
import rapidjson
import re
import shutil
import zipfile

import fuzzywuzzy.process
import geopandas as gpd
import ogr
import pandas as pd
import shapefile
import shapely.geometry

from pydriosm.download_GeoFabrik import download_subregion_osm_file, remove_subregion_osm_file
from pydriosm.download_GeoFabrik import get_download_url, get_subregion_info_index, make_default_file_path
from pydriosm.utils import cd_dat_geofabrik, confirmed, download, load_pickle, osm_geom_types, save_pickle, split_list


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
    subregion_names = get_subregion_info_index("GeoFabrik-subregion-name-list", update=update)
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
    subregion_name_, download_url = get_download_url(subregion_name, file_format, update=False)
    _, file_path = make_default_file_path(subregion_name_, file_format)
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
    subregion_name_and_url = [get_download_url(subregion_name, ".shp.zip") for subregion_name in subregion_names]
    # Download the requested OSM file
    filename_and_path = [make_default_file_path(k, ".shp.zip") for k, _ in subregion_name_and_url]

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
                 update=False, download_confirmation_required=True, pickle_it=True, rm_extracts=False):
    """
    :param subregion_name: [str] name of a subregion, e.g. 'england', 'oxfordshire', or 'europe'; case-insensitive
    :param layer: [str] name of a OSM layer, e.g. 'railways'
    :param feature: [str] name of a feature, e.g. 'rail'; if None, all available features included; default None
    :param update: [bool] indicates whether to update the relevant file/information; default False
    :param download_confirmation_required: [bool]
    :param pickle_it: [bool]
    :param rm_extracts: [bool] indicates whether to keep extracted files from the .shp.zip file; default True
    :return: [GeoDataFrame]
    """
    subregion_name_, _ = get_download_url(subregion_name, file_format=".shp.zip")
    _, path_to_shp_zip = make_default_file_path(subregion_name_, file_format=".shp.zip")

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
                    download_subregion_osm_file(subregion_name, file_format='.shp.zip', update=update)

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

        if pickle_it:
            save_pickle(shp_data, path_to_shp_pickle)

        if rm_extracts:
            # Alternatively, import shutil; shutil.rmtree(extract_dir)
            for f in glob.glob(os.path.join(extract_dir, "gis.osm*")):
                # if layer not in f:
                os.remove(f)

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
            download_subregion_osm_file(subregion_filename, download_path=path_to_osm_pbf, update=update)

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


# Parse each layer's data
def parse_layer_data(layer_data, geo_typ, fmt_other_tags, fmt_single_geom, fmt_multi_geom):
    """
    :param layer_data: [pandas.DataFrame]
    :param geo_typ: [str]
    :param fmt_other_tags: [bool]
    :param fmt_single_geom: [bool]
    :param fmt_multi_geom: [bool]
    :return:
    """

    def reformat_single_geometry(geom_data):
        """ Format the coordinates with shapely.geometry
        :param geom_data:
        :return:
        """
        geom_types_funcs, geom_type = osm_geom_types(), list(set(geom_data.geom_type))[0]
        geom_type_func = geom_types_funcs[geom_type]
        if geom_type == 'MultiPolygon':
            sub_geom_type_func = geom_types_funcs['Polygon']
            geom_coords = geom_data.coordinates.map(
                lambda x: geom_type_func(sub_geom_type_func(l) for ls in x for l in ls))
        else:
            geom_coords = geom_data.coordinates.map(lambda x: geom_type_func(x))
        return geom_coords

    def reformat_multi_geometries(geom_collection):
        """ Format geometry collections with shapely.geometry
        :param geom_collection:
        :return:
        """
        geom_types_funcs = osm_geom_types()
        geom_types = [g['type'] for g in geom_collection]
        coordinates = [gs['coordinates'] for gs in geom_collection]
        geometry_collection = [geom_types_funcs[geom_type](coords)
                               if 'Polygon' not in geom_type
                               else geom_types_funcs[geom_type](pt for pts in coords for pt in pts)
                               for geom_type, coords in zip(geom_types, coordinates)]
        return shapely.geometry.GeometryCollection(geometry_collection)

    def decompose_other_tags(other_tags_x):
        """ Transform a 'other_tags' into a dictionary
        :param other_tags_x: [str] or None
        :return:
        """
        if other_tags_x:
            raw_other_tags = (re.sub('^"|"$', '', each_tag) for each_tag in re.split('(?<="),(?=")', other_tags_x))
            other_tags = {k: v.replace('<br>', ' ') for k, v in
                          (re.split('"=>"?', each_tag) for each_tag in filter(None, raw_other_tags))}
        else:  # e.g. other_tags_x is None
            other_tags = other_tags_x
        return other_tags

    # Start parsing 'geometry' column
    dat_geometry = pd.DataFrame(x for x in layer_data.geometry).rename(columns={'type': 'geom_type'})

    if geo_typ != 'other_relations':  # geo_type can be 'points', 'lines', 'multilinestrings', or 'multipolygons'
        if fmt_single_geom:
            dat_geometry.coordinates = reformat_single_geometry(dat_geometry)
    else:  # geo_typ == 'other_relations'
        if fmt_multi_geom:
            dat_geometry.geometries = dat_geometry.geometries.map(reformat_multi_geometries)
            dat_geometry.rename(columns={'geometries': 'coordinates'}, inplace=True)

    # Start parsing 'properties' column
    dat_properties = pd.DataFrame(x for x in layer_data.properties)

    if fmt_other_tags:
        dat_properties.other_tags = dat_properties.other_tags.map(decompose_other_tags)

    parsed_layer_data = layer_data[['id']].join(dat_geometry).join(dat_properties)
    parsed_layer_data.drop(['geom_type'], axis=1, inplace=True)

    del dat_geometry, dat_properties

    return parsed_layer_data


# Parse '.osm.pbf' file
def parse_osm_pbf(path_to_osm_pbf, chunks_no, granulated, fmt_other_tags, fmt_single_geom, fmt_multi_geom):
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

    Note that this function can require fairly high amount of physical memory to read large files e.g. > 200MB
    :param path_to_osm_pbf: [str]
    :param chunks_no: [int; None]
    :param granulated: [bool]
    :param fmt_other_tags: [bool]
    :param fmt_single_geom: [bool]
    :param fmt_multi_geom: [bool]
    :return: [dict]
    """
    raw_osm_pbf = ogr.Open(path_to_osm_pbf)
    # Grab available layers in file: points, lines, multilinestrings, multipolygons, & other_relations
    layer_names, layer_data = [], []
    # Parse the data feature by feature
    layer_count = raw_osm_pbf.GetLayerCount()
    # Loop through all available layers
    for i in range(layer_count):
        # Get the data and name of the i-th layer
        lyr = raw_osm_pbf.GetLayerByIndex(i)
        lyr_name = lyr.GetName()

        if chunks_no:
            lyr_feats = [feat for _, feat in enumerate(lyr)]
            # no_chunk = file_size_in_mb / file_size_limit; chunk_size = len(lyr_feats) / no_chunk
            chunked_lyr_feats = split_list(lyr_feats, chunks_no)

            del lyr_feats
            gc.collect()

            lyr_dat = pd.DataFrame()
            for lyr_chunk in chunked_lyr_feats:
                lyr_chunk_feat = (feat.ExportToJson() for feat in lyr_chunk)
                lyr_chunk_dat = pd.DataFrame(rapidjson.loads(feat) for feat in lyr_chunk_feat)
                if granulated:
                    lyr_chunk_dat = parse_layer_data(lyr_chunk_dat, lyr_name,
                                                     fmt_other_tags, fmt_single_geom, fmt_multi_geom)
                lyr_dat = lyr_dat.append(lyr_chunk_dat)

                # feat_dat = pd.DataFrame.from_dict(rapidjson.loads(feat), orient='index').T
                # Or, feat_dat = pd.read_json(feat, typ='series').to_frame().T
                # feat_dat = parse_layer_data(feat_dat, lyr_name, fmt_other_tags, fmt_single_geom, fmt_multi_geom)
                # lyr_dat = lyr_dat.append(feat_dat)

                del lyr_chunk, lyr_chunk_dat
                gc.collect()

        else:
            lyr_feats = (feat.ExportToJson() for _, feat in enumerate(lyr))
            lyr_dat = pd.DataFrame(rapidjson.loads(feat) for feat in lyr_feats)  # Get the data
            if granulated:
                lyr_dat = parse_layer_data(lyr_dat, lyr_name, fmt_other_tags, fmt_single_geom, fmt_multi_geom)

        layer_names.append(lyr_name)
        layer_data.append(lyr_dat)

        del lyr_dat
        gc.collect()

    raw_osm_pbf.Release()

    del raw_osm_pbf
    gc.collect()

    # Make a dictionary, {layer_name: layer_DataFrame}
    osm_pbf_data = dict(zip(layer_names, layer_data))

    return osm_pbf_data


# Read '.osm.pbf' file into pandas.DataFrames, either roughly or with a granularity for a given subregion
def read_osm_pbf(subregion, update=False, download_confirmation_required=True,
                 file_size_limit=60, granulated=True,
                 fmt_other_tags=True, fmt_single_geom=True, fmt_multi_geom=True,
                 pickle_it=True, rm_raw_file=True):
    """
    :param subregion: [str] name of subregion or customised path of a .osm.pbf file
    :param update: [bool]
    :param download_confirmation_required: [bool]
    :param file_size_limit: [numbers.Number] limit of file size (in MB),  e.g. 50, or 100(default)
    :param granulated: [bool]
    :param fmt_other_tags: [bool]
    :param fmt_single_geom: [bool]
    :param fmt_multi_geom: [bool]
    :param pickle_it: [bool]
    :param rm_raw_file: [bool]
    :return: [dict] or None

    If 'subregion' is the name of the subregion, the default file path will be used.
    """
    assert isinstance(file_size_limit, int) or file_size_limit is None

    subregion_filename, path_to_osm_pbf = justify_subregion_input(subregion)

    path_to_pickle = path_to_osm_pbf.replace(".osm.pbf", ".pickle" if granulated else "-raw.pickle")
    if os.path.isfile(path_to_pickle) and not update:
        osm_pbf_data = load_pickle(path_to_pickle)
    else:
        # If the target file is not available, try downloading it first.
        if not os.path.isfile(path_to_osm_pbf) or update:
            if confirmed(prompt="To download \"{}\"?".format(subregion_filename),
                         resp=False, confirmation_required=download_confirmation_required):
                download_subregion_osm_file(subregion, download_path=path_to_osm_pbf, update=update)

        file_size_in_mb = round(os.path.getsize(path_to_osm_pbf) / (1024 ** 2), 1)

        if file_size_limit and file_size_in_mb > file_size_limit:
            chunks_no = math.ceil(file_size_in_mb / file_size_limit)  # Parsing the '.osm.pbf' file in a chunk-wise way
        else:
            chunks_no = None

        print("\nParsing \"{}\" ... ".format(subregion_filename), end="")
        try:
            osm_pbf_data = parse_osm_pbf(path_to_osm_pbf, chunks_no,
                                         granulated, fmt_other_tags, fmt_single_geom, fmt_multi_geom)
            print("Successfully.\n")
        except Exception as e:
            print("Failed. {}\n".format(e))
            osm_pbf_data = None

        if pickle_it:
            save_pickle(osm_pbf_data, path_to_pickle)
        if rm_raw_file:
            remove_subregion_osm_file(path_to_osm_pbf)

    return osm_pbf_data
