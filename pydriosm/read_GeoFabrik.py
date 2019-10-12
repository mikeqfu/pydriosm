""" Parse/read OSM data """

import gc
import glob
import math
import os
import re
import shutil
import zipfile

import geopandas as gpd
import ogr
import pandas as pd
import rapidjson
import json
import shapefile
import shapely.geometry
from pyhelpers.dir import cd, regulate_input_data_dir
from pyhelpers.store import load_pickle
from flatten_json import flatten

from pydriosm.download_GeoFabrik import download_subregion_osm_file, remove_subregion_osm_file
from pydriosm.download_GeoFabrik import get_default_path_to_osm_file, regulate_input_subregion_name
from pydriosm.utils import osm_geom_types, save_pickle, split_list


# Search the OSM data directory and its sub-directories to get the path to the file
def find_osm_shp_file(subregion_name, layer=None, feature=None, data_dir=None, file_ext=".shp"):
    """
    :param subregion_name: [str] case-insensitive, e.g. 'greater London', 'london'
    :param layer: [str; None (default)] name of a .shp layer, e.g. 'railways'
    :param feature: [str or None(default)] feature name, e.g. 'rail'; if None, all available features included
    :param data_dir: [str; None (default)] directory in which the function go to; if None, use default directory
    :param file_ext: [str] (default: ".shp") file extension, e.g. ".shp" (default)
    :return: [list] a list of paths
                fetch_osm_file('england', 'railways', feature=None, file_format=".shp", update=False) should return
                ['...\\Europe\\Great Britain\\england-latest-free.shp\\gis.osm_railways_free_1.shp'],
                if such a file exists, and [] otherwise.

    Testing e.g.
        subregion_name = 'london'
        layer          = None
        feature        = None
        data_dir       = None
        file_ext       = ".shp"
        find_osm_shp_file(subregion_name, layer, feature, data_dir, file_ext)
    """
    if not data_dir:  # Go to default file path
        _, path_to_shp_zip = get_default_path_to_osm_file(subregion_name, osm_file_format=".shp.zip", mkdir=False)
        shp_dir = os.path.splitext(path_to_shp_zip)[0]
    else:
        shp_dir = regulate_input_data_dir(data_dir)

    if not layer:
        osm_file_paths = glob.glob(shp_dir + "\\*" + file_ext)
    else:
        pat = re.compile("{}(_a)?_free".format(layer)) if not feature else re.compile("{}_{}".format(layer, feature))
        osm_file_paths = [f for f in glob.glob(shp_dir + "\\*" + file_ext) if re.search(pat, f)]

    # if not osm_file_paths: print("The required file may not exist.")
    return osm_file_paths


# Retrieve path to subregion .osm.pbf file (if available)
def find_osm_pbf_file(subregion_name, data_dir=None):
    """
    :param subregion_name: [str]
    :param data_dir: [str; None (default)]
    :return: [str; None] path to .osm.pbf file

    Testing e.g.
        subregion_name = 'london'
        data_dir       = None
        find_osm_pbf_file(subregion_name, data_dir)
    """
    osm_pbf_filename, path_to_osm_pbf = get_default_path_to_osm_file(subregion_name, ".osm.pbf", mkdir=False)
    if not data_dir:  # Go to default file path
        path_to_osm_pbf_ = path_to_osm_pbf
    else:
        osm_pbf_dir = regulate_input_data_dir(data_dir)
        path_to_osm_pbf_ = os.path.join(osm_pbf_dir, osm_pbf_filename)
    return path_to_osm_pbf_ if os.path.isfile(path_to_osm_pbf_) else None


""" ================================================ .shp.zip files ============================================== """


# Extract only the specified layer
def extract_shp_zip(path_to_shp_zip, extract_dir=None, layer=None, mode='r', clustered=False, verbose=False):
    """
    :param path_to_shp_zip: [str]
    :param extract_dir: [str; None (default)]
    :param layer: [str; None (default)]
    :param mode: [str] (default: 'r')
    :param clustered: [bool] (default: False)
    :param verbose: [bool] (default: False)

    Testing e.g.
        path_to_shp_zip =
        extract_dir     = None
        layer           = None
        mode            = 'r'
        clustered       = False
        verbose         = False
    """
    extract_dir_ = extract_dir if extract_dir else os.path.splitext(path_to_shp_zip)[0]
    if layer:
        msg = "\nExtracting \"{}\" layer of \"{}\" to \n\"{}\" ... ".format(
            layer, os.path.basename(path_to_shp_zip), extract_dir_)  # ".." + "\\".join(extract_dir_.split("\\")[-2:])
    else:
        msg = "\nExtracting all \"{}\" to \n\"{}\" ... ".format(os.path.basename(path_to_shp_zip), extract_dir_) \
            if verbose else None
    print(msg, end="")
    try:
        with zipfile.ZipFile(path_to_shp_zip, mode) as shp_zip:
            selected_files = [f.filename for f in shp_zip.filelist if layer and layer in f.filename]
            members = selected_files if selected_files else None
            shp_zip.extractall(extract_dir_, members=members)
        shp_zip.close()
        if clustered:
            file_list = os.listdir(extract_dir_)
            if 'README' in file_list:
                file_list.remove('README')
            filenames, exts = [os.path.splitext(x)[0] for x in file_list], [os.path.splitext(x)[1] for x in file_list]
            layer_names = [re.search(r'(?<=gis_osm_)\w+(?=(_a)?_free_1)', f).group(0) for f in list(set(filenames))]
            layer_names = [x.strip('_a') for x in layer_names]
            for l, f in zip(layer_names, list(set(filenames))):
                os.makedirs(cd(extract_dir_, l), exist_ok=True)
                for e in list(set(exts)):
                    filename = f + e
                    print("{} ... ".format(filename), end="") if verbose else None
                    orig, dest = cd(extract_dir_, filename), cd(extract_dir_, l, filename)
                    shutil.copyfile(orig, dest)
                    os.remove(orig)
                    print("Done.") if verbose else None
        print("\nDone.") if verbose else None
    except Exception as e:
        print("\nFailed. {}".format(e)) if verbose else None


# Merge a set of .shp files (for a given layer)
def merge_multi_shp(subregion_names, layer, update_shp_zip=False, download_confirmation_required=True, output_dir=None):
    """
    :param subregion_names: [list] a list of subregion names, e.g. ['london', 'essex']
    :param layer: [str] name of a OSM layer, e.g. 'railways'
    :param update_shp_zip: [bool] (default: False) indicates whether to update the relevant file/information
    :param download_confirmation_required: [bool] (default: True)
    :param output_dir: [str; None]

    Layers include 'buildings', 'landuse', 'natural', 'places', 'points', 'railways', 'roads' and 'waterways'

    Note that this function does not create projection (.prj) for the merged map.
    Reference: http://geospatialpython.com/2011/02/create-prj-projection-file-for.html for creating a .prj file.

    Testing e.g.
        subregion_names                = ['london', 'essex']
        layer                          = 'railways'
        update_shp_zip                 = False
        download_confirmation_required = True
        output_dir                     = None
    """
    # Make sure all the required shape files are ready
    subregion_names_, file_format = [regulate_input_subregion_name(x) for x in subregion_names], ".shp.zip"
    download_subregion_osm_file(*subregion_names_, osm_file_format=file_format, download_dir=output_dir,
                                update=update_shp_zip, download_confirmation_required=download_confirmation_required)

    # Extract all files from .zip
    file_paths = (get_default_path_to_osm_file(x, file_format, mkdir=False)[1] for x in subregion_names_)
    extract_info = [(p, os.path.splitext(p)[0]) for p in file_paths]
    extract_dirs = []
    for file_path, extract_dir in extract_info:
        extract_shp_zip(file_path, extract_dir)
        extract_dirs.append(extract_dir)

    # Specify a directory that stores files for the specific layer
    if output_dir:
        assert os.path.isabs(output_dir)
        path_to_merged = output_dir
    else:
        path_to_merged = os.path.join(os.path.commonpath(extract_info[0]), "merged_" + layer)

    if not os.path.exists(path_to_merged):
        os.mkdir(path_to_merged)

    # Copy .shp files (e.g. gis_osm_***_free_1.shp) into the output directory
    for subregion, p in zip(subregion_names, extract_dirs):
        for original_filename in glob.glob1(p, "*{}*".format(layer)):
            dest = os.path.join(path_to_merged, "{}_{}".format(subregion.lower().replace(' ', '-'), original_filename))
            shutil.copyfile(os.path.join(p, original_filename), dest)

    # Resource: https://github.com/GeospatialPython/pyshp
    shp_file_paths = glob.glob(os.path.join(path_to_merged, '*.shp'))

    w = shapefile.Writer(os.path.join(path_to_merged, "merged_" + layer))
    print("\nMerging the following shape files:\n    {}".format(
        "\n    ".join(os.path.basename(f) for f in shp_file_paths)))
    print("In progress ... ", end="")
    try:
        for f in shp_file_paths:
            r = shapefile.Reader(f)
            w.fields = r.fields[1:]  # skip first deletion field
            w.shapeType = r.shapeType
            for shaperec in r.iterShapeRecords():
                w.record(*shaperec.record)
                w.shape(shaperec.shape)
            r.close()
        w.close()
        print("Successfully.")
    except Exception as e:
        print("Failed. {}".format(e))
    print("\nCheck out \"{}\".\n".format(path_to_merged))


# (Alternative to, though may not exactly be the same as, geopandas.read_file())
def read_shp(path_to_shp, mode='geopandas', bbox=None):
    """
    :param path_to_shp: [str] path to a .shp file
    :param mode: [str] (default: 'geopandas')
    :param bbox: [tuple; GeoDataFrame or GeoSeries; None (default)]
    :return: [pd.DataFrame]

    len(shp.records()) == shp.numRecords
    len(shp.shapes()) == shp.numRecords
    shp.bbox  # boundaries

    Testing e.g.
        path_to_shp =
        mode        = 'geopandas'
        bbox        = None
        read_shp(path_to_shp, mode, bbox)
    """
    if mode == 'geopandas':  # default
        shp_data = gpd.read_file(path_to_shp, bbox)

    else:
        # Read .shp file using shapefile.Reader()
        shp_reader = shapefile.Reader(path_to_shp)

        # Transform the data to a DataFrame
        filed_names = [field[0] for field in shp_reader.fields[1:]]
        shp_data = pd.DataFrame(shp_reader.records(), columns=filed_names)

        # shp_data['name'] = shp_data.name.str.encode('utf-8').str.decode('utf-8')  # Clean data
        shape_info = pd.DataFrame(((s.points, s.shapeType) for s in shp_reader.iterShapes()),
                                  index=shp_data.index, columns=['coords', 'shape_type'])
        shp_data = shp_data.join(shape_info)

        shp_reader.close()

    return shp_data


# Read a .shp.zip file
def read_shp_zip(subregion_name, layer, feature=None, data_dir=None, update=False, download_confirmation_required=True,
                 pickle_it=False, rm_extracts=False, rm_shp_zip=False):
    """
    :param subregion_name: [str] e.g. 'england', 'oxfordshire', or 'europe'; case-insensitive
    :param layer: [str] e.g. 'railways'
    :param feature: [str; None (default)] e.g. 'rail'; if None, all available features included
    :param data_dir: [str; None (default)]
    :param update: [bool] (default: False) whether to update the relevant file/information
    :param download_confirmation_required: [bool] (default: False)
    :param pickle_it: [bool] (default: False)
    :param rm_extracts: [bool] (default: False) whether to delete extracted files from the .shp.zip file
    :param rm_shp_zip: [bool] (default: False) whether to delete the downloaded .shp.zip file
    :return: [gpd.GeoDataFrame]

    Testing e.g.
        subregion_name                 = 'oxfordshire'
        layer                          = 'railways'
        feature                        = None
        data_dir                       = None
        update                         = False
        download_confirmation_required = True
        pickle_it                      = False
        rm_extracts                    = False
        rm_shp_zip                     = False
        read_shp_zip(subregion_name, layer, feature, data_dir, update, download_confirmation_required, pickle_it,
                     rm_extracts, rm_shp_zip)
    """
    shp_zip_filename, path_to_shp_zip = get_default_path_to_osm_file(subregion_name, ".shp.zip", mkdir=False)
    extract_dir = os.path.splitext(path_to_shp_zip)[0]
    if data_dir:
        shp_zip_dir = regulate_input_data_dir(data_dir)
        path_to_shp_zip = os.path.join(shp_zip_dir, shp_zip_filename)
        extract_dir = os.path.join(shp_zip_dir, os.path.basename(extract_dir))

    # Make a local path for saving a pickle file for .shp data
    sub_name = "-".join(x for x in [shp_zip_filename.replace("-latest-free.shp.zip", ""), layer, feature] if x)
    path_to_shp_pickle = os.path.join(extract_dir, sub_name + ".shp.pickle")

    if os.path.isfile(path_to_shp_pickle) and not update:
        shp_data = load_pickle(path_to_shp_pickle)
    else:
        # Download the requested OSM file urlretrieve(download_url, file_path)
        if not os.path.exists(extract_dir):
            download_subregion_osm_file(shp_zip_filename, osm_file_format=".shp.zip", download_dir=data_dir,
                                        update=update, download_confirmation_required=download_confirmation_required,
                                        verbose=False)
        if os.path.isfile(path_to_shp_zip):
            extract_shp_zip(path_to_shp_zip, extract_dir, layer=layer)

        path_to_shp = glob.glob(os.path.join(extract_dir, "*{}*.shp".format(layer)))
        if len(path_to_shp) == 0:
            shp_data = None
        elif len(path_to_shp) == 1:
            shp_data = gpd.read_file(path_to_shp[0])  # gpd.GeoDataFrame(read_shp_file(path_to_shp))
            if feature:
                path_to_shp_feat = path_to_shp[0].replace(layer, layer + "_" + feature)
                shp_data = gpd.GeoDataFrame(shp_data[shp_data.fclass == feature])
                shp_data.crs = {'no_defs': True, 'ellps': 'WGS84', 'datum': 'WGS84', 'proj': 'longlat'}
                shp_data.to_file(path_to_shp_feat, driver='ESRI Shapefile')
        else:  # len(path_to_shp) > 1:
            if not feature:
                path_to_orig_shp = [p for p in path_to_shp if layer + '_a' in p or layer + '_free' in p]
                if len(path_to_orig_shp) == 1:  # "_a*.shp" is not available
                    shp_data = gpd.read_file(path_to_orig_shp[0])
                else:
                    shp_data = [gpd.read_file(p) for p in path_to_shp]
                    shp_data = pd.concat(shp_data, axis=0, ignore_index=True)
            else:  # feature is None
                path_to_shp_feat = [p for p in path_to_shp if layer + "_" + feature not in p]
                if len(path_to_shp_feat) == 1:  # "_a*.shp" does not exist
                    shp_data = gpd.read_file(path_to_shp_feat[0])
                    shp_data = shp_data[shp_data.fclass == feature]
                else:  # both "_a*" and "_free*" .shp for feature is available
                    shp_data = [dat[dat.fclass == feature] for dat in (gpd.read_file(p) for p in path_to_shp_feat)]
                    shp_data = pd.concat(shp_data, axis=0, ignore_index=True)
                shp_data.crs = {'no_defs': True, 'ellps': 'WGS84', 'datum': 'WGS84', 'proj': 'longlat'}
                shp_data.to_file(path_to_shp_feat[0].replace(layer, layer + "_" + feature), driver='ESRI Shapefile')

        if pickle_it:
            save_pickle(shp_data, path_to_shp_pickle)

        if os.path.exists(extract_dir) and rm_extracts:
            # import shutil; shutil.rmtree(extract_dir)
            for f in glob.glob(os.path.join(extract_dir, "gis_osm*")):
                # if layer not in f:
                os.remove(f)

        if os.path.isfile(path_to_shp_zip) and rm_shp_zip:
            remove_subregion_osm_file(path_to_shp_zip)

    return shp_data


""" ================================================ .osm.pbf files ============================================== """


# Get names of all layers contained in the .osm.pbf file for a given subregion
def get_osm_pbf_layer_idx_names(path_to_osm_pbf):
    """
    :param path_to_osm_pbf: [str] path to .osm.pbf file
    :return: [dict]

    Testing e.g.
        path_to_osm_pbf =
        get_osm_pbf_layer_idx_names(path_to_osm_pbf)
    """
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
        return layer_idx_names

    except Exception as e:
        print("Failed to get layer names of \"{}\". {}.".format(path_to_osm_pbf, e))


# Parse each layer's data
def parse_layer_data(layer_data, geo_typ, fmt_other_tags, fmt_single_geom, fmt_multi_geom):
    """
    :param layer_data: [pd.DataFrame]
    :param geo_typ: [str]
    :param fmt_other_tags: [bool]
    :param fmt_single_geom: [bool]
    :param fmt_multi_geom: [bool]
    :return: [pd.DataFrame]

    Testing e.g.
        layer_data      =
        geo_typ         =
        fmt_other_tags  = True
        fmt_single_geom = True
        fmt_multi_geom  = True
        parse_layer_data(layer_data, geo_typ, fmt_other_tags, fmt_single_geom, fmt_multi_geom)
    """

    def reformat_single_geometry(geom_data):
        """ Re-format the coordinates with shapely.geometry
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
        """ Re-format geometry collections with shapely.geometry
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

    def decompose_other_tags(other_tags_x: (str, None)):
        """
        Transform a 'other_tags' into a dictionary
        """
        if other_tags_x:
            raw_other_tags = (re.sub('^"|"$', '', each_tag) for each_tag in re.split('(?<="),(?=")', other_tags_x))
            other_tags = {k: v.replace('<br>', ' ') for k, v in
                          (re.split('"=>"?', each_tag) for each_tag in filter(None, raw_other_tags))}
        else:  # e.g. other_tags_x is None
            other_tags = other_tags_x
        return other_tags

    if not layer_data.empty:
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

    else:
        parsed_layer_data = layer_data

    return parsed_layer_data


# Parse .osm.pbf file
def parse_osm_pbf(path_to_osm_pbf, chunks_no, parsed, fmt_other_tags, fmt_single_geom, fmt_multi_geom):
    """
    :param path_to_osm_pbf: [str]
    :param chunks_no: [int; None]
    :param parsed: [bool]
    :param fmt_other_tags: [bool]
    :param fmt_single_geom: [bool]
    :param fmt_multi_geom: [bool]
    :return: [dict]

    OpenStreetMap XML and PBF (GDAL/OGR >= 1.10.0)
    The driver will categorize features into 5 layers :
        'points'            - 0: "node" features that have significant tags attached
        'lines'             - 1: "way" features that are recognized as non-area
        'multilinestrings'  - 2: "relation" features that form a multilinestring(type='multilinestring' or type='route')
        'multipolygons'     - 3; "relation" features that form a multipolygon (type='multipolygon' or type='boundary'),
                                 and "way" features that are recognized as area
        'other_relations'   - 4: "relation" features that do not belong to the above 2 layers

    Note that this function can require fairly high amount of physical memory to read large files e.g. > 200MB

    Reference: http://www.gdal.org/drv_osm.html

    Testing e.g.
        path_to_osm_pbf =
        chunks_no       = 50
        parsed          = True
        fmt_other_tags  = True
        fmt_single_geom = True
        fmt_multi_geom  = True
        parse_osm_pbf(path_to_osm_pbf, chunks_no, parsed, fmt_other_tags, fmt_single_geom, fmt_multi_geom)
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
                if parsed:
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
            if parsed:
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

def stream_osm_pbf(path_to_osm_pbf, layer_name): 
    '''
    Generator that returns an iterator that can be used to stream parsed OSM data. 
    
    :type path_to_osm_pbf: str 
    :param path_to_osm_pbf: Path to the *.osm.pbf file you wish to parse and stream 
    
    :type layer_data: str 
    :param layer_data: The layer of the *.osm.pbf file that you wish to parse and stream. 
                       Options include: points, lines, multilinestrings, multipolygons, & other_relations
                       
    :rtype: Iterator 
    :return: An iterator object that can be used to stream the parsed data from the corresponding layer in the *.osm.pbf file
    
    -------
    Example
    -------
    
    stream_data = stream_osm_pbf('/algeria.osm.pbf', 'lines')
    
    for row in stream_data: 
        print(row)
    '''
    
    raw_data = ogr.Open(path_to_osm_pbf)
    layer = raw_data.GetLayer(layer_name)
    for feature in layer: 
        yield flatten(json.loads(feat.ExportToJson()))

# Read .osm.pbf file into pd.DataFrames, either roughly or with a granularity for a given subregion
def read_osm_pbf(subregion_name, data_dir=None, parsed=True, file_size_limit=50,
                 fmt_other_tags=True, fmt_single_geom=True, fmt_multi_geom=True,
                 update=False, download_confirmation_required=True, pickle_it=False, rm_osm_pbf=True, verbose=False):
    """
    :param subregion_name: [str] e.g. 'london'
    :param data_dir: [str; None (default)] customised path of a .osm.pbf file
    :param parsed: [bool] (default: True)
    :param file_size_limit: [numbers.Number] (default: 50) limit of file size (in MB),  e.g. 50, or 100
    :param fmt_other_tags: [bool] (default: True)
    :param fmt_single_geom: [bool] (default: True)
    :param fmt_multi_geom: [bool] (default: True)
    :param update: [bool] (default: False)
    :param download_confirmation_required: [bool] (default: True)
    :param pickle_it: [bool] (default: False)
    :param rm_osm_pbf: [bool] (default: True)
    :param verbose: [bool] (default: False)
    :return: [dict] or None

    If 'subregion' is the name of the subregion, the default file path will be used.

    Testing e.g.
        subregion_name                 = 'london'
        data_dir                       = None
        parsed                         = True
        file_size_limit                = 50
        fmt_other_tags                 = True
        fmt_single_geom                = True
        fmt_multi_geom                 = True
        update                         = False
        download_confirmation_required = True
        pickle_it                      = False
        rm_osm_pbf                     = True
        verbose                        = False
        read_osm_pbf(subregion_name, data_dir, parsed, file_size_limit, fmt_other_tags, fmt_single_geom, fmt_multi_geom,
                     update, download_confirmation_required, pickle_it, rm_osm_pbf, verbose)
    """
    assert isinstance(file_size_limit, int) or file_size_limit is None

    osm_pbf_filename, path_to_osm_pbf = get_default_path_to_osm_file(subregion_name, ".osm.pbf", mkdir=False)
    if not data_dir:  # Go to default file path
        path_to_osm_pbf = path_to_osm_pbf
    else:
        osm_pbf_dir = regulate_input_data_dir(data_dir)
        path_to_osm_pbf = os.path.join(osm_pbf_dir, osm_pbf_filename)

    subregion_filename = os.path.basename(path_to_osm_pbf)

    path_to_pickle = path_to_osm_pbf.replace(".osm.pbf", ".pickle" if parsed else "-raw.pickle")
    if os.path.isfile(path_to_pickle) and not update:
        osm_pbf_data = load_pickle(path_to_pickle, verbose=verbose)
    else:
        # If the target file is not available, try downloading it first.
        download_subregion_osm_file(subregion_name, osm_file_format=".osm.pbf", download_dir=data_dir,
                                    update=update, download_confirmation_required=download_confirmation_required,
                                    verbose=False)

        file_size_in_mb = round(os.path.getsize(path_to_osm_pbf) / (1024 ** 2), 1)

        if file_size_limit and file_size_in_mb > file_size_limit:
            chunks_no = math.ceil(file_size_in_mb / file_size_limit)  # Parsing the '.osm.pbf' file in a chunk-wise way
        else:
            chunks_no = None

        print("\nParsing \"{}\" ... ".format(subregion_filename), end="") if verbose else None
        try:
            osm_pbf_data = parse_osm_pbf(path_to_osm_pbf, chunks_no, parsed,
                                         fmt_other_tags, fmt_single_geom, fmt_multi_geom)
            print("Successfully.\n") if verbose else None
        except Exception as e:
            print("Failed. {}\n".format(e)) if verbose else None
            osm_pbf_data = None

        if pickle_it:
            save_pickle(osm_pbf_data, path_to_pickle, verbose=verbose)
        if rm_osm_pbf:
            remove_subregion_osm_file(path_to_osm_pbf, verbose=verbose)

    return osm_pbf_data
