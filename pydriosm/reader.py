""" Parse/read OSM data """

import copy
import gc
import glob
import lzma
import math
import os
import re
import shutil
import zipfile

import geopandas as gpd
import ogr
import pandas as pd
import shapefile
from pyhelpers.dir import cd, regulate_input_data_dir
from pyhelpers.ops import split_list
from pyhelpers.store import load_pickle, save_pickle

from pydriosm.downloader import BBBikeDownloader, GeoFabrikDownloader
from pydriosm.utils import osm_geom_types, remove_subregion_osm_file


def extract_shp_zip(path_to_shp_zip, extract_dir=None, layer=None, mode='r', clustered=False, verbose=False):
    """
    Extract only the specified layer.

    :param path_to_shp_zip: [str]
    :type path_to_shp_zip: str
    :param extract_dir: [str; None (default)]
    :type extract_dir: str, None
    :param layer: [str; None (default)]
    :type layer: str, None
    :param mode: [str] (default: 'r')
    :type mode: str
    :param clustered: [bool], defaults to ``False``
    :type clustered: bool
    :param verbose: whether to print relevant information in console as the function runs, defaults to ``False``
    :type verbose: bool, int

    **Example**::

        path_to_shp_zip = cd("test_read_GeoFabrik")
        extract_dir     = None
        layer           = None
        mode            = 'r'
        clustered       = False
        verbose         = False
    """

    extract_dir_ = extract_dir if extract_dir else os.path.splitext(path_to_shp_zip)[0]

    if layer:
        msg = "\nExtracting \"{}\" layer of \"{}\" to \n\"{}\" ... ".format(
            layer, os.path.basename(path_to_shp_zip), extract_dir_) if verbose else ""
        # ".." + "\\".join(extract_dir_.split("\\")[-2:])

    else:
        msg = "\nExtracting all \"{}\" to \n\"{}\" ... ".format(os.path.basename(path_to_shp_zip), extract_dir_) \
            if verbose else ""

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

            for x, f in zip(layer_names, list(set(filenames))):
                os.makedirs(cd(extract_dir_, x), exist_ok=True)

                for e in list(set(exts)):
                    filename = f + e
                    print("{} ... ".format(filename), end="") if verbose else None
                    orig, dest = cd(extract_dir_, filename), cd(extract_dir_, x, filename)
                    shutil.copyfile(orig, dest)
                    os.remove(orig)
                    print("Done.") if verbose else ""

        print("\nDone.") if verbose else ""

    except Exception as e:
        print("\nFailed. {}".format(e)) if verbose else ""


def read_shp(path_to_shp, method='geopandas', **kwargs):
    """
    :param path_to_shp: path to a .shp file
    :type: str
    :param method: if ``'geopandas'`` (default), use the ``geopandas.read_file`` method,
        for otherwise use ``shapefile.Reader_``
    :type method: str
    :param kwargs: optional parameters of `geopandas.read_file`_
    :return: data frame of the .shp data
    :rtype: pandas.DataFrame, geopandas.GeoDataFrame

    .. _`geopandas.read_file`: https://geopandas.org/reference/geopandas.read_file.html
    .. _`shapefile.Reader`: https://github.com/GeospatialPython/pyshp#reading-shapefiles

    **Examples**::

        from pydriosm.downloader import GeoFabrikDownloader
        from pydriosm.reader import extract_shp_zip, read_shp

        geofabrik_downloader = GeoFabrikDownloader()

        subregion_name = 'rutland'
        osm_file_format = ".shp"

        # Download .shp.zip data of "Rutland"
        geofabrik_downloader.download_subregion_osm_file(subregion_name, osm_file_format=osm_file_format,
                                                         download_dir="tests", verbose=True)

        # Get default filename of the downloaded data
        shp_zip_filename = geofabrik_downloader.get_default_osm_filename(subregion_name, osm_file_format)

        # Extract the downloaded data file
        extract_shp_zip(cd("tests", shp_zip_filename), verbose=True)

        # Specify the path to a .shp file
        path_to_shp = cd("tests\\rutland-latest-free.shp\\gis_osm_railways_free_1.shp")

        bbox = None

        method = 'geopandas'  # or 'gpd'
        shp_data = read_shp(path_to_shp, method, bbox)  # geopandas.GeoDataFrame
        print(shp_data)

        method = 'pyshp'  # (Or anything except 'geopandas')
        shp_data = read_shp(path_to_shp, method, bbox)  # pandas.DataFrame
        print(shp_data)
    """

    if method in ('geopandas', 'gpd'):  # default
        shp_data = gpd.read_file(path_to_shp, **kwargs)

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


def get_osm_pbf_layer_idx_names(path_to_osm_pbf):
    """
    Get names of all layers contained in the .osm.pbf file for a given subregion.

    :param path_to_osm_pbf: [str] path to .osm.pbf file
    :return: [dict]

    **Example**::

        path_to_osm_pbf = cd("test_read_GeoFabrik\\rutland-latest.osm.pbf")
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


def parse_osm_pbf_layer_data(pbf_layer_data, geo_typ, fmt_other_tags, fmt_single_geom, fmt_multi_geom):
    """
    Parse data of each layer in .pbf file.

    :param pbf_layer_data: pandas.DataFrame
    :param geo_typ: [str]
    :param fmt_other_tags: [bool]
    :param fmt_single_geom: [bool]
    :param fmt_multi_geom: [bool]
    :return: pandas.DataFrame

    **Example**::

        pbf_layer_data  # See parse_osm_pbf()
        geo_typ         = 'points'
        fmt_other_tags  = True
        fmt_single_geom = True
        fmt_multi_geom  = True
        parse_layer_data(layer_data, geo_typ, fmt_other_tags, fmt_single_geom, fmt_multi_geom)
    """

    def reformat_single_geometry(geom_data):
        """
        Re-format the coordinates with shapely.geometry
        """

        geom_types_funcs, geom_type = osm_geom_types(), list(set(geom_data.geom_type))[0]
        geom_type_func = geom_types_funcs[geom_type]
        if geom_type == 'MultiPolygon':
            sub_geom_type_func = geom_types_funcs['Polygon']
            geom_coords = geom_data.coordinates.map(
                lambda x: geom_type_func(sub_geom_type_func(y) for ls in x for y in ls))
        else:
            geom_coords = geom_data.coordinates.map(lambda x: geom_type_func(x))
        return geom_coords

    def reformat_multi_geometries(geom_collection):
        """
        Re-format geometry collections with shapely.geometry
        """

        geom_types_funcs = osm_geom_types()
        geom_types = [g['type'] for g in geom_collection]
        coordinates = [gs['coordinates'] for gs in geom_collection]
        geometry_collection = [geom_types_funcs[geom_type](coords)
                               if 'Polygon' not in geom_type
                               else geom_types_funcs[geom_type](pt for pts in coords for pt in pts)
                               for geom_type, coords in zip(geom_types, coordinates)]
        import shapely.geometry
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

    if not pbf_layer_data.empty:
        # Start parsing 'geometry' column
        dat_geometry = pd.DataFrame(x for x in pbf_layer_data.geometry).rename(columns={'type': 'geom_type'})

        if geo_typ != 'other_relations':  # geo_type can be 'points', 'lines', 'multilinestrings', or 'multipolygons'
            if fmt_single_geom:
                dat_geometry.coordinates = reformat_single_geometry(dat_geometry)
        else:  # geo_typ == 'other_relations'
            if fmt_multi_geom:
                dat_geometry.geometries = dat_geometry.geometries.map(reformat_multi_geometries)
                dat_geometry.rename(columns={'geometries': 'coordinates'}, inplace=True)

        # Start parsing 'properties' column
        dat_properties = pd.DataFrame(x for x in pbf_layer_data.properties)

        if fmt_other_tags:
            dat_properties.other_tags = dat_properties.other_tags.map(decompose_other_tags)

        parsed_layer_data = pbf_layer_data[['id']].join(dat_geometry).join(dat_properties)
        parsed_layer_data.drop(['geom_type'], axis=1, inplace=True)

        del dat_geometry, dat_properties

    else:
        parsed_layer_data = pbf_layer_data

    return parsed_layer_data


def parse_osm_pbf(path_to_osm_pbf, chunks_no, parsed, fmt_other_tags, fmt_single_geom, fmt_multi_geom):
    """
    Parse .osm.pbf file.
    
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

    **Example**::

        path_to_osm_pbf = cd("test_read_GeoFabrik\\rutland-latest.osm.pbf")
        chunks_no       = 50
        parsed          = True
        fmt_other_tags  = True
        fmt_single_geom = True
        fmt_multi_geom  = True

        osm_pbf_data = parse_osm_pbf(path_to_osm_pbf, chunks_no, parsed, fmt_other_tags, fmt_single_geom,
                                     fmt_multi_geom)
    """

    raw_osm_pbf = ogr.Open(path_to_osm_pbf)
    # Grab available layers in file: points, lines, multilinestrings, multipolygons, & other_relations
    layer_names, all_layer_data = [], []
    # Parse the data feature by feature
    layer_count = raw_osm_pbf.GetLayerCount()

    # Loop through all available layers
    for i in range(layer_count):
        # Get the data and name of the i-th layer
        layer = raw_osm_pbf.GetLayerByIndex(i)
        layer_name = layer.GetName()

        layer_names.append(layer_name)

        if chunks_no:
            features = [feature for _, feature in enumerate(layer)]
            # chunks_no = file_size_in_mb / file_size_limit; chunk_size = len(features) / chunks_no
            feats = split_list(features, chunks_no)

            del features
            gc.collect()

            all_lyr_dat = []
            for feat in feats:
                if not parsed:
                    lyr_dat = pd.DataFrame(f.ExportToJson() for f in feat)
                else:
                    lyr_dat = pd.DataFrame(f.ExportToJson(as_object=True) for f in feat)
                    lyr_dat = parse_osm_pbf_layer_data(lyr_dat, layer_name,
                                                       fmt_other_tags, fmt_single_geom, fmt_multi_geom)
                all_lyr_dat.append(lyr_dat)
                del feat, lyr_dat
                gc.collect()

            layer_data = pd.concat(all_lyr_dat, ignore_index=True, sort=False)

        else:
            if not parsed:
                layer_data = pd.DataFrame(feature.ExportToJson() for _, feature in enumerate(layer))
                layer_data.columns = ['{}_data'.format(layer_name)]
            else:
                layer_data = pd.DataFrame(feature.ExportToJson(as_object=True) for _, feature in enumerate(layer))
                layer_data = parse_osm_pbf_layer_data(layer_data, layer_name,
                                                      fmt_other_tags, fmt_single_geom, fmt_multi_geom)

        all_layer_data.append(layer_data)

        del layer_data
        gc.collect()

    raw_osm_pbf.Release()

    del raw_osm_pbf
    gc.collect()

    # Make a dictionary, {layer_name: layer_DataFrame}
    osm_pbf_data = dict(zip(layer_names, all_layer_data))

    return osm_pbf_data


def read_csv_xz(path_to_csv_xz):
    """

    :param path_to_csv_xz:
    :return:

    **Example**::

        from download_BBBike import BBBike

        bbbike = BBBike()

        _, _, _, path_to_csv_xz = bbbike.validate_download_info(subregion_name, "csv.xz")

    """

    csv_xz_raw = lzma.open(path_to_csv_xz, mode='rt', encoding='utf-8').readlines()
    csv_xz_dat = [x.rstrip('\t\n').split('\t') for x in csv_xz_raw]

    csv_xz = pd.DataFrame(csv_xz_dat)

    return csv_xz


class GeoFabrikReader:

    def __init__(self):
        self.Downloader = GeoFabrikDownloader()
        self.Name = copy.copy(self.Downloader.Name)
        self.URL = copy.copy(self.Downloader.URL)

    def get_path_to_osm_shp_file(self, subregion_name, layer=None, feature=None, data_dir=None, file_ext=".shp"):
        """
        Search the directory of OSM data to get the path to the file.

        :param subregion_name: name of a region/subregion (case-insensitive)
        :type subregion_name: str
        :param layer: name of a .shp layer (e.g. 'railways'), defaults to ``None``
        :type layer: str; None
        :param feature: feature name, e.g. 'rail'; if None, all available features included
        :type feature: str; None
        :param data_dir: directory in which the function go to; if ``None`` (default), use default directory
        :type data_dir: str; None
        :param file_ext: file extension, defaults to ``".shp"``
        :type file_ext: str
        :return: path(s) to .shp file(s)
        :rtype: list

        **Examples**::

            subregion_name = 'rutland'
            data_dir = None
            file_ext = ".shp"

            layer = None
            feature = None
            get_path_to_osm_shp_file(subregion_name, layer, feature, data_dir, file_ext)

            # if such a file exists
            # ['\\dat_GeoFabrik\\Europe\\Great Britain\\England\\Rutland-latest-free.shp\\gis.osm_railways_free_1.shp'],
            # [] otherwise.

            layer = 'railways'
            feature = 'rail'
        """

        if not data_dir:  # Go to default file path
            _, path_to_shp_zip = self.Downloader.get_default_path_to_osm_file(
                subregion_name, osm_file_format=".shp.zip", mkdir=False)
            shp_dir = os.path.splitext(path_to_shp_zip)[0]

        else:
            shp_dir = regulate_input_data_dir(data_dir)

        if not layer:
            osm_file_paths = glob.glob(shp_dir + "\\*" + file_ext)

        else:
            pat = re.compile(r"{}(_a)?(_free)?(_1)?".format(layer)) if not feature \
                else re.compile(r"{}_*_{}".format(layer, feature))
            osm_file_paths = [f for f in glob.glob(shp_dir + "\\*" + file_ext) if re.search(pat, f)]

        # if not osm_file_paths: print("The required file may not exist.")
        return osm_file_paths

    def find_osm_pbf_file(self, subregion_name, data_dir=None):
        """
        Retrieve path to subregion .osm.pbf file (if available).

        :param subregion_name: name of a region/subregion (case-insensitive)
        :type subregion_name: str
        :param data_dir: [str; None (default)]
        :type data_dir: str, None
        :return: [str; None] path to .osm.pbf file

        **Example**::

            subregion_name = 'rutland'
            data_dir = None
            find_osm_pbf_file(subregion_name, data_dir)
        """

        osm_pbf_filename, path_to_osm_pbf = self.Downloader.get_default_path_to_osm_file(
            subregion_name, osm_file_format=".osm.pbf", mkdir=False)

        if not data_dir:  # Go to default file path
            path_to_osm_pbf_ = path_to_osm_pbf

        else:
            osm_pbf_dir = regulate_input_data_dir(data_dir)
            path_to_osm_pbf_ = os.path.join(osm_pbf_dir, osm_pbf_filename)

        return path_to_osm_pbf_ if os.path.isfile(path_to_osm_pbf_) else None

    # Merge a set of .shp files (for a given layer)
    def merge_multi_shp(self, subregion_names, layer, update_shp_zip=False, download_confirmation_required=True,
                        data_dir=None,
                        prefix="gis_osm", rm_zip_extracts=False, rm_shp_parts=False, merged_shp_dir=None,
                        verbose=False):
        """
        :param subregion_names: [list] a list of subregion names, e.g. ['rutland', 'essex']
        :param layer: [str] name of a OSM layer, e.g. 'railways'
        :param update_shp_zip: [bool], defaults to ``False`` indicates whether to update the relevant file/information
        :param download_confirmation_required: [bool] (default: True)
        :param data_dir: [str; None]
        :param prefix: [str] (default: "gis_osm")
        :param rm_zip_extracts: [bool], defaults to ``False``
        :param rm_shp_parts: [bool], defaults to ``False``
        :param merged_shp_dir: if None (default), use the layer name as the name of the folder in which the merged shp
            files will be saved
        :type merged_shp_dir: str, None
        :param verbose: whether to print relevant information in console as the function runs, defaults to ``False``
        :type verbose: bool, int

        Layers include 'buildings', 'landuse', 'natural', 'places', 'points', 'railways', 'roads' and 'waterways'

        Note that this function does not create projection (.prj) for the merged map.
        Reference: http://geospatialpython.com/2011/02/create-prj-projection-file-for.html for creating a .prj file.

        **Example**::

            subregion_names                = ['Rutland', 'Herefordshire']
            layer                          = 'railways'
            update_shp_zip                 = False
            download_confirmation_required = True
            data_dir                       = cd("test_read_GeoFabrik")
            prefix                         = "gis_osm"
            rm_zip_extracts                = False
            rm_shp_parts                   = False
            merged_shp_dir                 = None
            verbose                        = True
            merge_multi_shp(subregion_names, layer, update_shp_zip, download_confirmation_required, output_dir)
        """

        # Make sure all the required shape files are ready
        subregion_names_ = [self.Downloader.regulate_input_subregion_name(x) for x in subregion_names]
        file_format = ".shp.zip"
        self.Downloader.download_subregion_osm_file(*subregion_names_, osm_file_format=file_format,
                                                    download_dir=data_dir, update=update_shp_zip,
                                                    confirmation_required=download_confirmation_required,
                                                    deep_retry=True, interval_sec=0, verbose=verbose)

        # Extract all files from .zip
        if not data_dir:  # output_dir is None or output_dir == ""
            file_paths = (self.Downloader.get_default_path_to_osm_file(x, file_format, mkdir=False)[1]
                          for x in subregion_names_)
        else:
            default_filenames = (self.Downloader.get_default_path_to_osm_file(x, file_format, mkdir=False)[0]
                                 for x in subregion_names_)
            file_paths = [cd(regulate_input_data_dir(data_dir), f) for f in default_filenames]

        extract_info = [(p, os.path.splitext(p)[0]) for p in file_paths]
        extract_dirs = []
        for file_path, extract_dir in extract_info:
            extract_shp_zip(file_path, extract_dir, layer=layer, verbose=verbose)
            extract_dirs.append(extract_dir)

        # Specify a directory that stores files for the specific layer
        if not data_dir:
            path_to_merged = cd(os.path.commonpath(extract_info[0]), "merged_" + layer)
        else:
            path_to_merged = cd(regulate_input_data_dir(data_dir), "merged_" + layer)

        if not os.path.exists(path_to_merged):
            os.mkdir(path_to_merged)

        # Copy .shp files (e.g. gis_osm_***_free_1.shp) into the output directory
        for subregion, p in zip(subregion_names, extract_dirs):
            for original_filename in glob.glob1(p, "*{}*".format(layer)):
                dest = os.path.join(path_to_merged,
                                    "{}_{}".format(subregion.lower().replace(' ', '-'), original_filename))
                if rm_zip_extracts:
                    shutil.move(os.path.join(p, original_filename), dest)
                    shutil.rmtree(p)
                else:
                    shutil.copyfile(os.path.join(p, original_filename), dest)

        # Resource: https://github.com/GeospatialPython/pyshp
        shp_file_paths = [x for x in glob.glob(os.path.join(path_to_merged, "*.shp"))
                          if not os.path.basename(x).startswith("merged_")]

        path_to_merged_shp_file = cd(path_to_merged, "merged_" + prefix + "_" + layer)
        w = shapefile.Writer(path_to_merged_shp_file)
        if verbose:
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
            merged_shp_data = gpd.read_file(path_to_merged_shp_file + ".shp")
            merged_shp_data.crs = {'no_defs': True, 'ellps': 'WGS84', 'datum': 'WGS84', 'proj': 'longlat'}
            merged_shp_data.to_file(filename=path_to_merged_shp_file, driver="ESRI Shapefile")
            print("Successfully.") if verbose else ""
        except Exception as e:
            print("Failed. {}".format(e)) if verbose else ""
        print("The output .shp file is saved in \"{}\".".format(path_to_merged)) if verbose else ""

        if rm_shp_parts:
            if merged_shp_dir:
                new_shp_dir = cd(regulate_input_data_dir(merged_shp_dir), mkdir=True)
            else:
                new_shp_dir = cd(data_dir, layer, mkdir=True)
            for x in glob.glob(cd(path_to_merged, "merged_*")):
                shutil.move(x, cd(new_shp_dir, os.path.basename(x).replace("merged_", "", 1)))
            shutil.rmtree(path_to_merged)

    def read_shp_zip(self, subregion_name, layer, feature=None, data_dir=None, update=False,
                     download_confirmation_required=True, pickle_it=False, rm_extracts=False, rm_shp_zip=False,
                     verbose=False):
        """
        Read a .shp.zip file.

        :param subregion_name: name of a region/subregion (case-insensitive)
        :type subregion_name: str
        :param layer: [str] e.g. 'railways'
        :param feature: [str; None (default)] e.g. 'rail'; if None, all available features included
        :param data_dir: [str; None (default)]
        :param update: whether to check on update and proceed to update the package data, defaults to ``False``
        :type update: bool
        :param download_confirmation_required: [bool], defaults to ``False``
        :param pickle_it: [bool], defaults to ``False``
        :param rm_extracts: [bool], defaults to ``False`` whether to delete extracted files from the .shp.zip file
        :param rm_shp_zip: [bool], defaults to ``False`` whether to delete the downloaded .shp.zip file
        :param verbose: whether to print relevant information in console as the function runs, defaults to ``False``
        :type verbose: bool, int
        :return: [gpd.GeoDataFrame]

        **Example**::

            subregion_name = 'Rutland'
            layer = 'railways'
            feature = None
            data_dir = cd("test_read_GeoFabrik")
            update = False
            download_confirmation_required = True
            pickle_it = False
            rm_extracts = True
            rm_shp_zip = False
            verbose = True

            read_shp_zip(subregion_name, layer, feature, data_dir, update, download_confirmation_required,
                         pickle_it, rm_extracts, rm_shp_zip, verbose)
        """

        shp_zip_filename, path_to_shp_zip = self.Downloader.get_default_path_to_osm_file(subregion_name,
                                                                                         osm_file_format=".shp.zip",
                                                                                         mkdir=False)

        if shp_zip_filename and path_to_shp_zip:
            extract_dir = os.path.splitext(path_to_shp_zip)[0]
            if data_dir:
                shp_zip_dir = regulate_input_data_dir(data_dir)
                path_to_shp_zip = os.path.join(shp_zip_dir, shp_zip_filename)
                extract_dir = os.path.join(shp_zip_dir, os.path.basename(extract_dir))

            # Make a local path for saving a pickle file for .shp data
            sub_name = "-".join(x for x in [shp_zip_filename.replace("-latest-free.shp.zip", ""), layer, feature] if x)
            path_to_shp_pickle = os.path.join(extract_dir, sub_name + ".shp.pickle")

            if os.path.isfile(path_to_shp_pickle) and not update:
                shp_data = load_pickle(path_to_shp_pickle, verbose=verbose)

            else:
                # Download the requested OSM file urlretrieve(download_url, file_path)
                if not os.path.exists(extract_dir):
                    self.Downloader.download_subregion_osm_file(shp_zip_filename, osm_file_format=".shp.zip",
                                                                download_dir=data_dir, update=update,
                                                                confirmation_required=download_confirmation_required,
                                                                verbose=verbose)

                if os.path.isfile(path_to_shp_zip):
                    extract_shp_zip(path_to_shp_zip, extract_dir, layer=layer, verbose=verbose)

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
                            shp_data = [dat[dat.fclass == feature] for dat in
                                        (gpd.read_file(p) for p in path_to_shp_feat)]
                            shp_data = pd.concat(shp_data, axis=0, ignore_index=True)
                        shp_data.crs = {'no_defs': True, 'ellps': 'WGS84', 'datum': 'WGS84', 'proj': 'longlat'}
                        shp_data.to_file(path_to_shp_feat[0].replace(layer, layer + "_" + feature),
                                         driver='ESRI Shapefile')

                if pickle_it:
                    save_pickle(shp_data, path_to_shp_pickle, verbose=verbose)

                if os.path.exists(extract_dir) and rm_extracts:
                    # import shutil; shutil.rmtree(extract_dir)
                    for f in glob.glob(os.path.join(extract_dir, "gis_osm*")):
                        # if layer not in f:
                        os.remove(f)

                if os.path.isfile(path_to_shp_zip) and rm_shp_zip:
                    remove_subregion_osm_file(path_to_shp_zip, verbose=verbose)

            return shp_data

    def read_osm_pbf(self, subregion_name, data_dir=None, parsed=True, file_size_limit=50,
                     fmt_other_tags=True, fmt_single_geom=True, fmt_multi_geom=True,
                     update=False, download_confirmation_required=True, pickle_it=False, rm_osm_pbf=False,
                     verbose=False):
        """
        Read .osm.pbf file into pd.DataFrames, either roughly or with a granularity for a given subregion.

        :param subregion_name: name of a region/subregion (case-insensitive)
        :type subregion_name: str
        :param data_dir: [str; None (default)] customised path of a .osm.pbf file
        :param parsed: [bool] (default: True)
        :param file_size_limit: [numbers.Number] (default: 50) limit of file size (in MB),  e.g. 50, or 100
        :param fmt_other_tags: [bool] (default: True)
        :param fmt_single_geom: [bool] (default: True)
        :param fmt_multi_geom: [bool] (default: True)
        :param update: [bool], defaults to ``False``
        :param download_confirmation_required: [bool] (default: True)
        :param pickle_it: [bool], defaults to ``False``
        :param rm_osm_pbf: [bool], defaults to ``False``
        :param verbose: whether to print relevant information in console as the function runs, defaults to ``False``
        :type verbose: bool, int
        :return: 
        :rtype: dict, None

        If 'subregion' is the name of the subregion, the default file path will be used.

        **Example**::

            subregion_name                 = 'Rutland'
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

            osm_pbf_data = read_osm_pbf(subregion_name, data_dir, parsed, file_size_limit, fmt_other_tags,
            fmt_single_geom, fmt_multi_geom,
                         update, download_confirmation_required, pickle_it, rm_osm_pbf, verbose)
        """

        assert isinstance(file_size_limit, int) or file_size_limit is None

        osm_pbf_filename, path_to_osm_pbf = self.Downloader.get_default_path_to_osm_file(subregion_name,
                                                                                         osm_file_format=".osm.pbf",
                                                                                         mkdir=False)

        if osm_pbf_filename and path_to_osm_pbf:
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
                if not os.path.isfile(path_to_osm_pbf) or update:
                    try:
                        self.Downloader.download_subregion_osm_file(
                            subregion_name, osm_file_format=".osm.pbf", download_dir=data_dir, update=update,
                            confirmation_required=download_confirmation_required, verbose=False)
                    except Exception as e:
                        print("Cancelled reading data. CAUSE: {}".format(e))
                    osm_pbf_data = None

                else:
                    file_size_in_mb = round(os.path.getsize(path_to_osm_pbf) / (1024 ** 2), 1)

                    if file_size_limit and file_size_in_mb > file_size_limit:
                        # Parsing the '.osm.pbf' file in a chunk-wise way
                        chunks_no = math.ceil(file_size_in_mb / file_size_limit)
                    else:
                        chunks_no = None

                    print("\nParsing \"{}\" ... ".format(subregion_filename), end="") if verbose else ""
                    try:
                        osm_pbf_data = parse_osm_pbf(path_to_osm_pbf, chunks_no, parsed,
                                                     fmt_other_tags, fmt_single_geom, fmt_multi_geom)
                        print("Successfully.\n") if verbose else ""
                        if pickle_it:
                            save_pickle(osm_pbf_data, path_to_pickle, verbose=verbose)
                    except Exception as e:
                        print("Failed. CAUSE: \"{}\"\n".format(e))
                        osm_pbf_data = None

                    if rm_osm_pbf:
                        remove_subregion_osm_file(path_to_osm_pbf, verbose=verbose)

            return osm_pbf_data

        else:
            print("Errors occur. Maybe check with the input \"subregion_name\" first.")


class BBBikeReader:

    def __init__(self):
        self.Downloader = BBBikeDownloader()
        self.Name = copy.copy(self.Downloader.Name)
        self.URL = copy.copy(self.Downloader.URL)

    def _read_csv_xz(self, subregion_name, download_dir=None):
        """

        :param subregion_name:
        :type subregion_name: str
        :param download_dir:
        :type download_dir: str, None
        :return:
        :rtype
        """

        _, _, _, path_to_file = self.Downloader.validate_download_info(subregion_name, osm_file_format=".csv.xz",
                                                                       download_dir=download_dir)

        csv_xz = read_csv_xz(path_to_file)
        return csv_xz
