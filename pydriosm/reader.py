""" A module for parsing/reading OSM data extracts. """

import gc
import glob
import lzma
import shutil
import zipfile

import geopandas as gpd
import ogr
import rapidjson
import shapefile
import shapely.geometry
from pyhelpers.ops import split_list

from pydriosm.downloader import *
from pydriosm.utils import get_number_of_chunks, osm_geom_shapely_object_dict, pbf_layer_feat_types_dict, \
    remove_subregion_osm_file


def unzip_shp_zip(path_to_shp_zip, path_to_extract_dir=None, layer=None, mode='r', clustered=False, verbose=False,
                  ret_extract_dir=False):
    """
    Unzip a .shp.zip file.

    :param path_to_shp_zip: full path to a .shp.zip file
    :type path_to_shp_zip: str
    :param path_to_extract_dir: full path to a directory where extracted files will be saved;
        if None (default), use the directory where the .shp.zip file is located
    :type path_to_extract_dir: str, None
    :param layer: name of a .shp layer (e.g. 'railways'), defaults to ``None``
    :type layer: str, None
    :param mode: the ``mode`` parameter of `zipfile.ZipFile`_, defaults to ``'r'``
    :type mode: str
    :param clustered: whether to put the data files of different layer in respective folders, defaults to ``False``
    :type clustered: bool
    :param verbose: whether to print relevant information in console as the function runs, defaults to ``False``
    :type verbose: bool, int
    :param ret_extract_dir: whether to return the path to the directory where extracted files are saved,
        defaults to ``False``
    :type ret_extract_dir: bool

    .. `zipfile.ZipFile`: https://docs.python.org/3/library/zipfile.html#zipfile-objects

    **Examples**::

        from pyhelpers.dir import cd
        from pydriosm.downloader import GeoFabrikDownloader
        from pydriosm.reader import unzip_shp_zip, read_shp

        geofabrik_downloader = GeoFabrikDownloader()

        verbose = True
        subregion_name = 'rutland'
        osm_file_format = ".shp"

        # Download .shp.zip data of "Rutland"
        geofabrik_downloader.download_subregion_osm_file(subregion_name, osm_file_format=osm_file_format,
                                                         download_dir="tests", verbose=verbose)

        # Get default filename of the downloaded data
        shp_zip_filename = geofabrik_downloader.get_default_osm_filename(subregion_name, osm_file_format)

        path_to_shp_zip = cd("tests", shp_zip_filename)

        extract_dir = None
        mode = 'r'
        clustered = False

        layer = 'railways'
        unzip_shp_zip(path_to_shp_zip, layer=layer, verbose=verbose)
        # Extracting "railways" layer of "rutland-latest-free.shp.zip" to
        # "<cwd>\\tests\\rutland-latest-free.shp" ...
        # Done.

        layer = None
        unzip_shp_zip(path_to_shp_zip, verbose=verbose)
        # Extracting all "rutland-latest-free.shp.zip" to
        # "<cwd>\\tests\\rutland-latest-free.shp" ...
        # Done.

        clustered = True
        unzip_shp_zip(path_to_shp_zip, clustered=clustered, verbose=2)
        # Extracting all "rutland-latest-free.shp.zip" to
        # "<cwd>\\tests\\rutland-latest-free.shp" ...
        # Clustering the layer data ... Finished.
        # Done.
    """

    extract_dir_ = path_to_extract_dir if path_to_extract_dir else os.path.splitext(path_to_shp_zip)[0]

    if layer:
        msg = "\nExtracting \"{}\" layer of \"{}\" to \n\"{}\" ... ".format(
            layer, os.path.basename(path_to_shp_zip), extract_dir_) if verbose else ""
        # ".." + "\\".join(extract_dir_.split("\\")[-2:])

    else:
        msg = "\nExtracting all \"{}\" to \n\"{}\" ... ".format(os.path.basename(path_to_shp_zip), extract_dir_) \
            if verbose else ""

    print(msg)

    try:
        with zipfile.ZipFile(path_to_shp_zip, mode) as shp_zip:
            selected_files = [f.filename for f in shp_zip.filelist if layer and layer in f.filename]
            members = selected_files if selected_files else None
            shp_zip.extractall(extract_dir_, members=members)
        shp_zip.close()

        if clustered:
            print("Clustering the layer data ... ")
            file_list = os.listdir(extract_dir_)

            if 'README' in file_list:
                file_list.remove('README')
            filenames, exts = [os.path.splitext(x)[0] for x in file_list], [os.path.splitext(x)[1] for x in file_list]
            layer_names = [re.search(r'(?<=gis_osm_)\w+(?=(_a)?_free_1)', f).group(0) for f in list(set(filenames))]
            layer_names = [x.strip('_a') for x in layer_names]

            for x, f in zip(layer_names, list(set(filenames))):
                if verbose == 2:
                    print("    {}".format(x), end=" ... ") if verbose == 2 else ""
                for e in list(set(exts)):
                    filename = f + e
                    orig, dest = cd(extract_dir_, filename, mkdir=True), cd(extract_dir_, x, filename, mkdir=True)
                    shutil.copyfile(orig, dest)
                    os.remove(orig)
                print("Done.") if verbose == 2 else ""

            print("    Finished.") if verbose == 2 else ""

        print("Done.") if verbose else ""

    except Exception as e:
        print("Failed. {}".format(e)) if verbose else ""

    if ret_extract_dir:
        return extract_dir_


def read_shp(path_to_shp, method='geopandas', **kwargs):
    """
    Read a .shp file.

    :param path_to_shp: full path to a .shp file
    :type: str
    :param method: the method used to read the .shp file;
        if ``'geopandas'`` (default), use the `geopandas.read_file_` method,
        for otherwise use `shapefile.Reader_`
    :type method: str
    :param kwargs: optional parameters of `geopandas.read_file`_
    :return: data frame of the .shp data
    :rtype: pandas.DataFrame, geopandas.GeoDataFrame

    .. _`geopandas.read_file`: https://geopandas.org/reference/geopandas.read_file.html
    .. _`shapefile.Reader`: https://github.com/GeospatialPython/pyshp#reading-shapefiles

    **Examples**::

        from pydriosm.downloader import GeoFabrikDownloader
        from pydriosm.reader import unzip_shp_zip, read_shp

        geofabrik_downloader = GeoFabrikDownloader()

        subregion_name = 'rutland'
        osm_file_format = ".shp"

        # Download .shp.zip data of "Rutland"
        geofabrik_downloader.download_subregion_osm_file(subregion_name, osm_file_format=osm_file_format,
                                                         download_dir="tests", verbose=True)

        # Get default filename of the downloaded data
        shp_zip_filename = geofabrik_downloader.get_default_osm_filename(subregion_name, osm_file_format)

        # Extract the downloaded data file
        unzip_shp_zip(cd("tests", shp_zip_filename), verbose=True)

        # Specify the path to a .shp file
        path_to_shp = cd("tests\\rutland-latest-free.shp\\gis_osm_railways_free_1.shp")

        method = 'geopandas'  # or 'gpd'
        shp_data = read_shp(path_to_shp, method)  # geopandas.GeoDataFrame
        print(shp_data)

        method = 'pyshp'  # (Or anything except 'geopandas')
        shp_data = read_shp(path_to_shp, method)  # pandas.DataFrame
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
    Get names of all layers contained in a .osm.pbf file for a given subregion.

    :param path_to_osm_pbf: full path to a .osm.pbf file
    :type path_to_osm_pbf: str
    :return: name and index of each layer of the .osm.pbf file
    :rtype: dict

    **Example**::

        from pydriosm.downloader import GeoFabrikDownloader

        subregion_name = 'rutland'
        osm_file_format=".osm.pbf"

        geofabrik_downloader.download_subregion_osm_file(subregion_name, osm_file_format=osm_file_format,
                                                         download_dir="tests", verbose=True)
        osm_pbf_filename = geofabrik_downloader.get_default_osm_filename(subregion_name, osm_file_format)

        path_to_osm_pbf = cd("tests", osm_pbf_filename)

        layer_idx_names = get_osm_pbf_layer_idx_names(path_to_osm_pbf)

        print(layer_idx_names)
        # {0: 'points', 1: 'lines', 2: 'multilinestrings', 3: 'multipolygons', 4: 'other_relations'}
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


def make_point_as_polygon(x):
    x_, y = x.copy(), x[0][0].copy()
    if len(y) == 2 and y[0] == y[1]:
        x_[0][0] += [y[0]]
    return x_


def parse_osm_pbf_layer(pbf_layer_data, geo_typ, transform_geom, transform_other_tags):
    """
    Parse data of each layer in a .osm.pbf file.

    :param pbf_layer_data: data of a specific layer of a given .pbf file.
    :type pbf_layer_data: pandas.DataFrame
    :param geo_typ: geometric type
    :type geo_typ: str
    :param transform_geom: whether to transform a single coordinate (or a collection of coordinates) into
        a geometric object
    :type transform_geom: bool
    :param transform_other_tags: whether to transform a ``'other_tags'`` into a dictionary
    :type transform_other_tags: bool
    :return: parsed data of the ``geo_typ`` layer of a given .pbf file
    :rtype: pandas.DataFrame

    .. _`shapely.geometry`: https://shapely.readthedocs.io/en/latest/manual.html#geometric-objects

    **Examples**::

        import ogr
        import pandas as pd
        from pyhelpers.dir import cd
        from pydriosm.downloader import GeoFabrikDownloader
        from pydriosm.reader import parse_osm_pbf_layer

        geofabrik_downloader = GeoFabrikDownloader()

        # Specify subregion name and file format
        subregion_name = 'rutland'
        osm_file_format=".osm.pbf"

        # Get the data ready
        geofabrik_downloader.download_subregion_osm_file(subregion_name, osm_file_format=osm_file_format,
                                                         download_dir="tests", verbose=True)
        osm_pbf_filename = geofabrik_downloader.get_default_osm_filename(subregion_name, osm_file_format)
        raw_osm_pbf = ogr.Open(cd("tests", osm_pbf_filename))

        # To parse the data of the 'points' layer
        geo_typ = 'points'

        points_data = raw_osm_pbf.GetLayerByName(geo_typ)
        pbf_points = pd.DataFrame(feat.ExportToJson(as_object=True) for feat in points_data)

        # Maintain the original format
        transform_geom = False
        transform_other_tags = False
        parsed_points_data = parse_osm_pbf_layer(pbf_points, geo_typ, transform_geom=transform_geom,
                                                 transform_other_tags=transform_other_tags)
        print(parsed_points_data)

        # Reformat the original data
        transform_geom = True
        transform_other_tags = False
        parsed_points_data = parse_osm_pbf_layer(pbf_points, geo_typ, transform_geom=transform_geom,
                                                 transform_other_tags=transform_other_tags)

        transform_geom = True
        transform_other_tags = True
        parsed_points_data = parse_osm_pbf_layer(pbf_points, geo_typ, transform_geom=transform_geom,
                                                 transform_other_tags=transform_other_tags)
    """

    def transform_single_geometry_(geom_data):
        """
        Transform a single coordinate into a geometric object by using `shapely.geometry_`.
        """

        geom_types_funcs, pbf_layer_feat_types = osm_geom_shapely_object_dict(), pbf_layer_feat_types_dict()
        geom_type = pbf_layer_feat_types[geo_typ]
        geom_type_func = geom_types_funcs[geom_type]

        if geom_type == 'MultiPolygon':
            sub_geom_type_func = geom_types_funcs['Polygon']
            geom_coords = geom_data.coordinates.map(
                lambda x: geom_type_func(sub_geom_type_func(y) for ls in make_point_as_polygon(x) for y in ls))
        else:
            geom_coords = geom_data.coordinates.map(lambda x: geom_type_func(x))

        return geom_coords

    def transform_multi_geometries_(geom_collection):
        """
        Transform a collection of coordinates into a geometric object formatted by `shapely.geometry_`.
        """

        geom_obj_funcs = osm_geom_shapely_object_dict()
        geom_types = [g['type'] for g in geom_collection]
        coordinates = [gs['coordinates'] for gs in geom_collection]
        geometry_collection = [geom_obj_funcs[geom_type](coords)
                               if 'Polygon' not in geom_type
                               else geom_obj_funcs[geom_type](pt for pts in coords for pt in pts)
                               for geom_type, coords in zip(geom_types, coordinates)]

        return shapely.geometry.GeometryCollection(geometry_collection)

    def transform_other_tags_(other_tags):
        """
        Transform a ``'other_tags'`` into a dictionary.

        :param other_tags: data of a single record in the ``'other_tags'`` feature
        :type other_tags: str, None
        :return: parsed data of the ``'other_tags'`` record
        :rtype: dict, None
        """

        if other_tags:
            raw_other_tags = (re.sub('^"|"$', '', each_tag) for each_tag in re.split('(?<="),(?=")', other_tags))
            other_tags_ = {k: v.replace('<br>', ' ') for k, v in
                           (re.split('"=>"?', each_tag) for each_tag in filter(None, raw_other_tags))}

        else:  # e.g. other_tags_x is None
            other_tags_ = other_tags

        return other_tags_

    if not pbf_layer_data.empty:
        # Start parsing 'geometry' column
        dat_geometry = pd.DataFrame(x for x in pbf_layer_data.geometry).rename(columns={'type': 'geom_type'})

        if geo_typ != 'other_relations':  # `geo_type` can be 'points', 'lines', 'multilinestrings' or 'multipolygons'
            if transform_geom:
                dat_geometry.coordinates = transform_single_geometry_(dat_geometry)
        else:  # geo_typ == 'other_relations'
            if transform_geom:
                dat_geometry.geometries = dat_geometry.geometries.map(transform_multi_geometries_)
                dat_geometry.rename(columns={'geometries': 'coordinates'}, inplace=True)

        # Start parsing 'properties' column
        dat_properties = pd.DataFrame(x for x in pbf_layer_data.properties)

        if transform_other_tags:
            dat_properties.other_tags = dat_properties.other_tags.map(transform_other_tags_)

        parsed_layer_data = pbf_layer_data[['id']].join(dat_geometry).join(dat_properties)
        parsed_layer_data.drop(['geom_type'], axis=1, inplace=True)

        del dat_geometry, dat_properties
        gc.collect()

    else:
        parsed_layer_data = pbf_layer_data

    return parsed_layer_data


def parse_osm_pbf(path_to_osm_pbf, number_of_chunks, parse_raw_feat, transform_geom, transform_other_tags):
    """
    Parse a .osm.pbf file.
    
    :param path_to_osm_pbf: full path to a .osm.pbf file
    :type path_to_osm_pbf: str
    :param number_of_chunks: number of chunks
    :type number_of_chunks: int, None
    :param parse_raw_feat: whether to parse each feature in the raw data
    :type parse_raw_feat: bool
    :param transform_geom: whether to transform a single coordinate (or a collection of coordinates) into
        a geometric object
    :param transform_other_tags: whether to transform a ``'other_tags'`` into a dictionary
    :type transform_other_tags: bool
    :return: parsed OSM PBF data
    :rtype: dict

    .. note::

        This function can require fairly high amount of physical memory to read large files e.g. > 200MB

        The driver will categorize features into 5 layers (OpenStreetMap XML and PBF (GDAL/OGR >= 1.10.0)):

        - 0: 'points' - "node" features having significant tags attached
        - 1: 'lines' - "way" features being recognized as non-area
        - 2: 'multilinestrings' - "relation" features forming a multilinestring(type='multilinestring' / type='route')
        - 3: 'multipolygons' - "relation" features forming a multipolygon (type='multipolygon' / type='boundary'),
            and "way" features being recognized as area
        - 4: 'other_relations' - "relation" features not belonging to the above 2 layers

        See also [`POP-1 <http://www.gdal.org/drv_osm.html>`_].

    **Example**::

        from pyhelpers.dir import cd
        from pydriosm.downloader import GeoFabrikDownloader
        from pydriosm.reader import parse_osm_pbf

        geofabrik_downloader = GeoFabrikDownloader()

        subregion_name = 'rutland'
        osm_file_format=".osm.pbf"

        geofabrik_downloader.download_subregion_osm_file(subregion_name, osm_file_format=osm_file_format,
                                                         download_dir="tests", verbose=True)
        osm_pbf_filename = geofabrik_downloader.get_default_osm_filename(subregion_name, osm_file_format)

        path_to_osm_pbf = cd("tests", osm_pbf_filename)

        chunks_no = 50
        parsed = True
        transform_geom = False
        fmt_multi_geom = False
        transform_other_tags = False

        osm_pbf_data = parse_osm_pbf(path_to_osm_pbf, chunks_no, parsed, transform_geom, fmt_multi_geom,
                                     transform_other_tags)

        print(osm_pbf_data)
        # {'points': <data frame>,
        #  'lines': <data frame>,
        #  'multilinestrings': <data frame>,
        #  'multipolygons': <data frame>,
        #  'other_relations: <data frame>'}
    """

    raw_osm_pbf = ogr.Open(path_to_osm_pbf)
    # Grab available layers in file: points, lines, multilinestrings, multipolygons, & other_relations
    layer_names, all_layer_data = [], []
    # Parse the data feature by feature
    layer_count = raw_osm_pbf.GetLayerCount()

    # Loop through all available layers
    for i in range(layer_count):
        # Get the data and name of the i-th layer
        layer_dat = raw_osm_pbf.GetLayerByIndex(i)
        layer_name = layer_dat.GetName()

        layer_names.append(layer_name)

        if number_of_chunks:
            features = [feature for _, feature in enumerate(layer_dat)]
            # number_of_chunks = file_size_in_mb / chunk_size_limit; chunk_size = len(features) / number_of_chunks
            feats = split_list(lst=features, num_of_sub=number_of_chunks)

            del features
            gc.collect()

            all_lyr_dat = []
            for feat in feats:
                if parse_raw_feat:
                    lyr_dat_ = pd.DataFrame(f.ExportToJson(as_object=True) for f in feat)
                    lyr_dat = parse_osm_pbf_layer(lyr_dat_, geo_typ=layer_name, transform_geom=transform_geom,
                                                  transform_other_tags=transform_other_tags)
                    del lyr_dat_
                    gc.collect()
                else:
                    lyr_dat = pd.DataFrame(f.ExportToJson() for f in feat)

                all_lyr_dat.append(lyr_dat)

                del feat, lyr_dat
                gc.collect()

            layer_data = pd.concat(all_lyr_dat, ignore_index=True, sort=False)

        else:
            if parse_raw_feat:
                layer_data_ = pd.DataFrame(feature.ExportToJson(as_object=True) for _, feature in enumerate(layer_dat))
                layer_data = parse_osm_pbf_layer(layer_data_, geo_typ=layer_name, transform_geom=transform_geom,
                                                 transform_other_tags=transform_other_tags)
                del layer_data_
                gc.collect()
            else:
                layer_data = pd.DataFrame(feature.ExportToJson() for _, feature in enumerate(layer_dat))
                layer_data.columns = ['{}_data'.format(layer_name)]

        all_layer_data.append(layer_data)

        del layer_data
        gc.collect()

    # Make a dictionary in a dictionary form: {Layer name: Layer data}
    osm_pbf_data = dict(zip(layer_names, all_layer_data))

    return osm_pbf_data


def parse_csv_xz(path_to_csv_xz, col_names=None):
    """
    Parse a .csv.xz file.

    :param path_to_csv_xz: full path to a .csv.xz file
    :type path_to_csv_xz: str
    :param col_names: column names of .csv.xz data
    :type col_names: list, None
    :return: tabular data of the .csv.xz file
    :rtype: pandas.DataFrame

    **Example**::

        See the example for :ref:`BBBikeReader.read_csv_xz()<pydriosm-reader-bbbike-read_csv_xz>`.
    """

    csv_xz_raw = lzma.open(path_to_csv_xz, mode='rt', encoding='utf-8').readlines()
    csv_xz_dat = [x.rstrip('\t\n').split('\t') for x in csv_xz_raw]

    if col_names is None:
        col_names = ['type', 'id', 'feature']

    csv_xz = pd.DataFrame.from_records(csv_xz_dat, columns=col_names)

    return csv_xz


def parse_geojson_xz(path_to_geojson_xz, fmt_geom=False, decode_properties=False):
    """
    Parse a .geojson.xz file.

    :param path_to_geojson_xz: full path to a .csv.xz file
    :type path_to_geojson_xz: str
    :param fmt_geom: whether to reformat coordinates into a geometric object, defaults to ``False``
    :type fmt_geom: bool
    :param decode_properties: whether to transform a 'properties' dictionary into tabular form, defaults to ``False``
    :type decode_properties: bool
    :return: tabular data of the .geojson.xz file
    :rtype: pandas.DataFrame

    **Example**::

        See the example for :ref:`BBBikeReader.read_geojson_xz()<pydriosm-reader-bbbike-read_geojson_xz>`.
    """

    geojson_xz_raw = lzma.open(path_to_geojson_xz, mode='rt', encoding='utf-8')

    geojson_xz_raw_ = rapidjson.load(geojson_xz_raw)
    geojson_xz_dat = pd.DataFrame.from_dict(geojson_xz_raw_)

    pd.concat([pd.json_normalize(geojson_xz_dat.features[10]['properties']),
               pd.json_normalize(geojson_xz_dat.features[100]['properties'])])

    feature_types = geojson_xz_dat.features.map(lambda x: x['type']).to_frame(name='feature_name')

    geom_types = geojson_xz_dat.features.map(lambda x: x['geometry']['type'])

    if fmt_geom:
        geom_types_funcs = osm_geom_shapely_object_dict()

        def reformat_geom(geo_typ, coords):
            sub_geom_type_func = geom_types_funcs[geo_typ]
            if geo_typ == 'MultiPolygon':
                geom_coords = sub_geom_type_func(geom_types_funcs['Polygon'](y) for x in coords for y in x)
            else:
                geom_coords = sub_geom_type_func(coords)
            return geom_coords

        coordinates = geojson_xz_dat.features.map(
            lambda x: reformat_geom(x['geometry']['type'], x['geometry']['coordinates']))
    else:
        coordinates = geojson_xz_dat.features.map(lambda x: x['geometry']['coordinates'])

    properties = geojson_xz_dat.features.map(lambda x: x['properties'])

    if decode_properties:
        if confirmed("Confirmed to decode \"properties\"\n"
                     "(Note that it can be very computationally expensive and taking fairly large amount of memory)?"):
            properties = pd.concat(properties.map(pd.json_normalize).to_list())

    geojson_xz = pd.concat([feature_types, geom_types, coordinates, properties], axis=1)

    del feature_types, geom_types, coordinates, properties
    gc.collect()

    return geojson_xz


class GeoFabrikReader:
    """
    A class representation of a tool for reading GeoFabrik data extracts.
    """

    def __init__(self):
        """
        Constructor method.
        """
        self.Downloader = GeoFabrikDownloader()
        self.Name = copy.copy(self.Downloader.Name)
        self.URL = copy.copy(self.Downloader.URL)

    def get_path_to_osm_shp(self, subregion_name, layer=None, feature=None, data_dir=None, file_ext=".shp"):
        """
        Search the directory of GeoFabrik data to get the full path(s) to the .shp file(s) for a subregion.

        :param subregion_name: name of a region/subregion (case-insensitive)
        :type subregion_name: str
        :param layer: name of a .shp layer (e.g. ``'railways'``), defaults to ``None``
        :type layer: str, None
        :param feature: name of a feature (e.g. ``'rail'``); if ``None`` (default), all available features included
        :type feature: str, None
        :param data_dir: directory where the search is conducted; if ``None`` (default), the default directory
        :type data_dir: str, None
        :param file_ext: file extension, defaults to ``".shp"``
        :type file_ext: str
        :return: path(s) to .shp file(s)
        :rtype: list, str

        **Examples**::

            from pydriosm.downloader import GeoFabrikDownloader
            from pydriosm.reader import GeoFabrikReader, unzip_shp_zip

            geofabrik_downloader = GeoFabrikDownloader()
            geofabrik_reader = GeoFabrikReader()

            subregion_name = 'rutland'
            file_ext = ".shp"

            layer = None
            feature = None
            data_dir = None
            path_to_osm_shp_file = geofabrik_reader.get_path_to_osm_shp(subregion_name)

            print(path_to_osm_shp_file)
            # if "gis.osm_railways_free_1.shp" is available at the package data directory, return:
            # <pkg>\\dat_GeoFabrik\\Rutland-latest-free.shp\\gis.osm_railways_free_1.shp'
            # otherwise:
            # []

            # Download .shp.zip data of "Rutland" to a directory named "tests"
            osm_file_format = ".shp.zip"
            download_dir = "tests"
            path_to_shp_zip = geofabrik_downloader.download_subregion_osm_file(
                subregion_name, osm_file_format=osm_file_format, download_dir=download_dir,
                ret_download_path=True)
            # Confirm to download the .shp.zip data of "Rutland"? [No]|Yes: >? yes

            unzip_shp_zip(path_to_shp_zip, verbose=True)
            # Extracting all "rutland-latest-free.shp.zip" to
            # "<cwd>\\tests\\rutland-latest-free.shp" ...
            # Done.

            layer = 'railways'
            feature = 'rail'
            data_dir = download_dir
            path_to_osm_shp_file = geofabrik_reader.get_path_to_osm_shp(subregion_name, layer=layer,
                                                                        feature=feature,
                                                                        data_dir=data_dir)

            print(path_to_osm_shp_file)
            # '<cwd>\\tests\\rutland-latest-free.shp\\gis_osm_railways_free_1.shp'
        """

        if data_dir is None:  # Go to default file path
            _, path_to_shp_zip = self.Downloader.get_default_path_to_osm_file(
                subregion_name, osm_file_format=".shp.zip", mkdir=False)
        else:
            shp_zip_filename = self.Downloader.get_default_osm_filename(subregion_name, osm_file_format=".shp.zip")
            path_to_shp_zip = cd(regulate_input_data_dir(data_dir), shp_zip_filename)
        shp_dir = os.path.splitext(path_to_shp_zip)[0]

        if layer is None:
            path_to_osm_shp_file = glob.glob(shp_dir + "\\*" + file_ext)
        else:
            if feature is not None:
                pat = re.compile(r"{}(_a)?(_free)?(_1)?".format(layer))
            else:
                pat = re.compile(r"{}_*_{}".format(layer, feature))
            path_to_osm_shp_file = [f for f in glob.glob(shp_dir + "\\*" + file_ext) if re.search(pat, f)]

        # if not osm_file_paths: print("The required file may not exist.")

        if len(path_to_osm_shp_file) == 1:
            path_to_osm_shp_file = path_to_osm_shp_file[0]

        return path_to_osm_shp_file

    def merge_multi_shp(self, subregion_names, layer, method='geopandas', update=False,
                        download_confirmation_required=True, data_dir=None, rm_zip_extracts=False, merged_shp_dir=None,
                        rm_shp_temp=False, verbose=False, ret_merged_shp_path=False):
        """
        Merge GeoFabrik .shp files for a layer for two or more subregions.

        :param subregion_names: a list of subregion names
        :type subregion_names: list
        :param layer: name of a .shp layer (e.g. 'railways')
        :type layer: str
        :param method: the method used to merge/save .shp files;
            if ``'geopandas'`` (default), use the `geopandas.GeoDataFrame.to_file_` method,
            use `shapefile.Writer_` otherwise
        :type method: str
        :param update: whether to update the source .shp.zip files, defaults to ``False``
        :type update: bool
        :param download_confirmation_required: whether to ask for confirmation before starting to download a file,
            defaults to ``True``
        :type download_confirmation_required: bool
        :param data_dir: directory where the .shp.zip data files are located/saved; if ``None``, the default directory
        :type data_dir: str, None
        :param rm_zip_extracts: whether to delete the extracted files, defaults to ``False``
        :type rm_zip_extracts: bool
        :param rm_shp_temp: whether to delete temporary layer files, defaults to ``False``
        :type rm_shp_temp: bool
        :param merged_shp_dir: if ``None`` (default), use the layer name as the name of the folder where the merged .shp
            files will be saved
        :type merged_shp_dir: str, None
        :param verbose: whether to print relevant information in console as the function runs, defaults to ``False``
        :type verbose: bool, int
        :param ret_merged_shp_path: whether to return the path to the merged .shp file, defaults to ``False``
        :type ret_merged_shp_path: bool
        :return: the path to the merged file when ``ret_merged_shp_path=True``
        :rtype: list, str

        .. _`geopandas.GeoDataFrame.to_file`: https://geopandas.org/reference.html#geopandas.GeoDataFrame.to_file
        .. _`shapefile.Writer`: https://github.com/GeospatialPython/pyshp#writing-shapefiles

        .. note::

            Valid names for ``layer`` include:

                - 'buildings'
                - 'landuse'
                - 'natural'
                - 'places'
                - 'points'
                - 'railways'
                - 'roads'
                - 'waterways'

            Note that this function does not create projection (.prj) for the merged map
            (see also [`MMS-1 <http://geospatialpython.com/2011/02/create-prj-projection-file-for.html>`_])

        **Examples**::

            from pydriosm.reader import GeoFabrikReader

            geofabrik_reader = GeoFabrikReader()

            # To merge 'railways' layers of Greater Manchester and West Yorkshire
            subregion_names = ['Manchester', 'West Yorkshire']
            layer = 'railways'
            data_dir = "tests"
            rm_shp_temp = True
            verbose = True

            geofabrik_reader.merge_multi_shp(subregion_names, layer, data_dir=data_dir,
                                             rm_shp_temp=rm_shp_temp, verbose=verbose)

            # Extracting "railways" layer of "greater-manchester-latest-free.shp.zip" to
            # "<cwd>\\tests\\greater-manchester-latest-free.shp" ...
            # Done.
            #
            # Extracting "railways" layer of "west-yorkshire-latest-free.shp.zip" to
            # "<cwd>\\tests\\west-yorkshire-latest-free.shp" ...
            # Done.
            #
            # Merging the following shape files:
            #     manchester_gis_osm_railways_free_1.shp
            #     west-yorkshire_gis_osm_railways_free_1.shp
            # In progress ... Done.
            # The merged .shp file is saved at "<cwd>\\tests\\merged_railways".


            rm_zip_extracts = True
            ret_merged_shp_path = True

            path_to_merged_shp = geofabrik_reader.merge_multi_shp(
                subregion_names, layer, data_dir=data_dir, rm_zip_extracts=rm_zip_extracts,
                rm_shp_temp=rm_shp_temp,  verbose=verbose, ret_merged_shp_path=ret_merged_shp_path)

            print(path_to_merged_shp)
            # <cwd>\\tests\\merged_railways\\merged_railways.shp
        """

        # Make sure all the required shape files are ready
        subregion_names_ = [self.Downloader.validate_input_subregion_name(x) for x in subregion_names]
        file_format = ".shp.zip"
        self.Downloader.download_subregion_osm_file(*subregion_names_, osm_file_format=file_format,
                                                    download_dir=data_dir, update=update,
                                                    confirmation_required=download_confirmation_required,
                                                    deep_retry=True, interval_sec=0, verbose=verbose)

        # Extract all files from .zip
        if data_dir is None:
            file_paths = (self.Downloader.get_default_path_to_osm_file(x, file_format, mkdir=False)[1]
                          for x in subregion_names_)
        else:
            default_filenames = (self.Downloader.get_default_path_to_osm_file(x, file_format, mkdir=False)[0]
                                 for x in subregion_names_)
            file_paths = [cd(regulate_input_data_dir(data_dir), f) for f in default_filenames]

        extract_info = [(p, os.path.splitext(p)[0]) for p in file_paths]
        extract_dirs = []
        for file_path, extract_dir in extract_info:
            unzip_shp_zip(file_path, extract_dir, layer=layer, verbose=verbose)
            extract_dirs.append(extract_dir)

        # Specify a directory that stores files for the specific layer
        layer_ = "merged_{}_temp".format(layer)
        if data_dir is None:
            temp_path_to_merged = cd(os.path.commonpath(extract_info[0]), layer_, mkdir=True)
        else:
            temp_path_to_merged = cd(regulate_input_data_dir(data_dir), layer_, mkdir=True)

        # Copy .shp files (e.g. gis_osm_***_free_1.shp) into the output directory
        for subregion, p in zip(subregion_names, extract_dirs):
            for original_filename in glob.glob1(p, "*{}*".format(layer)):
                dest = cd(temp_path_to_merged, "{}_{}".format(subregion.lower().replace(' ', '-'), original_filename))
                shutil.copyfile(cd(p, original_filename), dest)

        if rm_zip_extracts:
            for p in extract_dirs:
                shutil.rmtree(p)

        shp_file_paths = [x for x in glob.glob(cd(temp_path_to_merged, "*.shp"))
                          if not os.path.basename(x).startswith("merged_")]

        if verbose:
            print("\nMerging the following shape files:\n    {}".format(
                "\n    ".join(os.path.basename(f) for f in shp_file_paths)))
            print("In progress ... ", end="")

        try:

            if method in ('geopandas', 'gpd'):
                merged_shp_data_ = [gpd.read_file(x) for x in shp_file_paths]
                merged_shp_data = pd.concat(merged_shp_data_, ignore_index=True)
                merged_shp_data.crs = {'no_defs': True, 'ellps': 'WGS84', 'datum': 'WGS84', 'proj': 'longlat'}
                merged_shp_data.to_file(filename=temp_path_to_merged.replace("_temp", "", -1), driver="ESRI Shapefile")

            else:  # method == 'pyshp'
                # Resource: https://github.com/GeospatialPython/pyshp
                w = shapefile.Writer(cd(temp_path_to_merged, layer_))
                for f in shp_file_paths:
                    r = shapefile.Reader(f)
                    w.fields = r.fields[1:]  # skip first deletion field
                    w.shapeType = r.shapeType
                    for shaperec in r.iterShapeRecords():
                        w.record(*shaperec.record)
                        w.shape(shaperec.shape)
                    r.close()
                w.close()
            print("Done.") if verbose else ""

            if merged_shp_dir:
                path_to_merged = cd(regulate_input_data_dir(merged_shp_dir), mkdir=True)
            else:
                path_to_merged = cd(data_dir, layer_.replace("_temp", "", -1), mkdir=True)
            for x in glob.glob(cd(temp_path_to_merged, "merged_*")):
                shutil.move(x, cd(path_to_merged, os.path.basename(x).replace("_temp", "")))

            if rm_shp_temp:
                shutil.rmtree(temp_path_to_merged)

            print("The merged .shp file is saved at \"{}\".".format(path_to_merged)) if verbose else ""

            if ret_merged_shp_path:
                path_to_merged_shp = glob.glob(cd(path_to_merged, "*.shp"))[0]
                return path_to_merged_shp

        except Exception as e:
            print("Failed. {}".format(e)) if verbose else ""

    def read_shp_zip(self, subregion_name, layer, feature=None, data_dir=None, update=False,
                     download_confirmation_required=True, pickle_it=False, rm_extracts=False, rm_shp_zip=False,
                     verbose=False):
        """
        Read GeoFabrik .shp.zip file of a subregion.

        :param subregion_name: name of a region/subregion (case-insensitive)
        :type subregion_name: str
        :param layer: name of a .shp layer (e.g. 'railways'), defaults to ``None``
        :type layer: str, None
        :param feature: name of a feature, e.g. 'rail'; if ``None`` (default), all available features included
        :type feature: str, None
        :param data_dir: directory where the .shp.zip data file is located/saved;
            if ``None``, the default directory
        :type data_dir: str, None
        :param update: whether to check to update pickle backup (if available), defaults to ``False``
        :type update: bool
        :param download_confirmation_required: whether to ask for confirmation before starting to download a file,
            defaults to ``True``
        :type download_confirmation_required: bool
        :param pickle_it: whether to save the .shp data as a .pickle file, defaults to ``False``
        :type pickle_it: bool
        :param rm_extracts: whether to delete extracted files from the .shp.zip file, defaults to ``False``
        :type rm_extracts: bool
        :param rm_shp_zip: whether to delete the downloaded .shp.zip file, defaults to ``False``
        :type rm_shp_zip: bool
        :param verbose: whether to print relevant information in console as the function runs, defaults to ``False``
        :type verbose: bool, int
        :return: tabular data of the .shp.zip file
        :rtype: geopandas.GeoDataFrame

        **Example**::

            from pydriosm.reader import GeoFabrikReader

            geofabrik_reader = GeoFabrikReader()

            rm_extracts = True
            rm_shp_zip = True
            verbose = True

            subregion_name = 'Rutland'
            layer = 'railways'
            feature = None
            data_dir = "tests"

            shp_data = geofabrik_reader.read_shp_zip(subregion_name, layer, feature, data_dir,
                                                     rm_extracts=rm_extracts, rm_shp_zip=rm_shp_zip,
                                                     verbose=verbose)

            print(shp_data)
        """

        shp_zip_filename, path_to_shp_zip = self.Downloader.get_default_path_to_osm_file(
            subregion_name, osm_file_format=".shp.zip", mkdir=False)

        if shp_zip_filename and path_to_shp_zip:
            extract_dir = os.path.splitext(path_to_shp_zip)[0]
            if data_dir:
                shp_zip_dir = regulate_input_data_dir(data_dir)
                path_to_shp_zip = os.path.join(shp_zip_dir, shp_zip_filename)
                extract_dir = os.path.join(shp_zip_dir, os.path.basename(extract_dir))

            # Make a local path for saving a pickle file for .shp data
            sub_name = "-".join(x for x in [shp_zip_filename.replace("-latest-free.shp.zip", ""), layer, feature] if x)
            path_to_shp_pickle = os.path.join(os.path.dirname(extract_dir), sub_name + ".shp.pickle")

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
                    unzip_shp_zip(path_to_shp_zip, extract_dir, layer=layer, verbose=verbose)

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
                    # for f in glob.glob(os.path.join(extract_dir, "gis_osm*")):
                    #     # if layer not in f:
                    #     os.remove(f)
                    shutil.rmtree(extract_dir)

                if os.path.isfile(path_to_shp_zip) and rm_shp_zip:
                    remove_subregion_osm_file(path_to_shp_zip, verbose=verbose)

            return shp_data

    def get_path_to_osm_pbf(self, subregion_name, data_dir=None):
        """
        Retrieve path to GeoFabrik .osm.pbf file (if available) for a subregion.

        :param subregion_name: name of a region/subregion (case-insensitive)
        :type subregion_name: str
        :param data_dir: directory where the data file of the ``subregion_name`` is located/saved;
            if ``None`` (default), the default directory
        :type data_dir: str, None
        :return: path to .osm.pbf file
        :rtype: str, None

        **Examples**::

            from pydriosm.reader import GeoFabrikReader

            geofabrik_downloader = GeoFabrikDownloader()
            geofabrik_reader = GeoFabrikReader()

            subregion_name = 'rutland'
            data_dir = None
            path_to_osm_pbf = geofabrik_reader.get_path_to_osm_pbf(subregion_name, data_dir)

            print(path_to_osm_pbf)
            # if "rutland-latest.osm.pbf" is available at the default package data directory, return:
            # <pkg>\\dat_GeoFabrik\\Europe\\Great Britain\\England\\rutland-latest.osm.pbf
            # otherwise:
            # None


            # Download .osm.pbf data of "Rutland" to a directory named "tests"
            osm_file_format = ".osm.pbf"
            download_dir = "tests"
            geofabrik_downloader.download_subregion_osm_file(subregion_name,
                                                             osm_file_format=osm_file_format,
                                                             download_dir=download_dir)
            # Confirm to download the .osm.pbf data of "Rutland"? [No]|Yes: >? yes

            path_to_osm_pbf = geofabrik_reader.get_path_to_osm_pbf(subregion_name, data_dir=download_dir)

            print(path_to_osm_pbf)
            # <cwd>\\tests\\rutland-latest.osm.pbf
        """

        osm_pbf_filename_, path_to_osm_pbf_ = self.Downloader.get_default_path_to_osm_file(
            subregion_name, osm_file_format=".osm.pbf", mkdir=False)

        if data_dir is None:  # Go to default file path
            path_to_osm_pbf = path_to_osm_pbf_

        else:
            osm_pbf_dir = regulate_input_data_dir(data_dir)
            path_to_osm_pbf = os.path.join(osm_pbf_dir, osm_pbf_filename_)

        if not os.path.isfile(path_to_osm_pbf):
            path_to_osm_pbf = None

        return path_to_osm_pbf

    def read_osm_pbf(self, subregion_name, data_dir=None, chunk_size_limit=50,
                     parse_raw_feat=False, transform_geom=False, transform_other_tags=False,
                     update=False, download_confirmation_required=True, pickle_it=False, rm_osm_pbf=False,
                     verbose=False):
        """
        Read GeoFabrik .osm.pbf file of a subregion.

        :param subregion_name: name of a region/subregion (case-insensitive)
        :type subregion_name: str
        :param data_dir: directory where the .osm.pbf data file is located/saved; if ``None``, the default directory
        :type data_dir: str, None
        :param chunk_size_limit: threshold (in MB) that triggers the use of chunk parser, defaults to ``50``;
            if the size of the .osm.pbf file (in MB) is greater than ``chunk_size_limit``, it will be parsed in a
            chunk-wise way
        :type chunk_size_limit: int
        :param parse_raw_feat: whether to parse each feature in the raw data, defaults to ``False``
        :type parse_raw_feat: bool
        :param transform_geom: whether to transform a single coordinate (or a collection of coordinates)
            into a geometric object, defaults to ``False``
        :type transform_geom: bool
        :param transform_other_tags: whether to transform a ``'other_tags'`` into a dictionary, defaults to ``False``
        :type transform_other_tags: bool
        :param update: whether to check to update pickle backup (if available), defaults to ``False``
        :type update: bool
        :param download_confirmation_required: whether to ask for confirmation before starting to download a file,
            defaults to ``True``
        :type download_confirmation_required: bool
        :param pickle_it: whether to save the .shp data as a .pickle file, defaults to ``False``
        :type pickle_it: bool
        :param rm_osm_pbf: whether to delete the downloaded .osm.pbf file, defaults to ``False``
        :type rm_osm_pbf: bool
        :param verbose: whether to print relevant information in console as the function runs, defaults to ``False``
        :type verbose: bool, int
        :return: data of the .osm.pbf file
        :rtype: dict, None

        **Example**::

            from pydriosm.reader import GeoFabrikReader

            geofabrik_reader = GeoFabrikReader()

            chunk_size_limit = 50
            update = False
            download_confirmation_required = True
            pickle_it = False
            rm_osm_pbf = False
            verbose = True

            subregion_name = 'Rutland'
            data_dir = "tests"

            parse_raw_feat = False
            transform_geom = False
            transform_other_tags = False
            rutland_osm_pbf = geofabrik_reader.read_osm_pbf(subregion_name, data_dir, verbose=verbose)

            print(osm_pbf_data)
            # {'points': <data frame>,
            #  'lines': <data frame>,
            #  'multilinestrings': <data frame>,
            #  'multipolygons': <data frame>,
            #  'other_relations: <data frame>'}

            print(rutland_osm_pbf['points'])
            # <data frame of a single column>


            parse_raw_feat = True
            transform_geom = False
            transform_other_tags = False
            rutland_osm_pbf = geofabrik_reader.read_osm_pbf(subregion_name, data_dir, verbose=verbose,
                                                            parse_raw_feat=parse_raw_feat)
            # Parsing "rutland-latest.osm.pbf" ... Successfully.
            print(rutland_osm_pbf['points'])
            # <data frame of 12 columns>


            parse_raw_feat = True
            transform_geom = True
            transform_other_tags = False
            rutland_osm_pbf = geofabrik_reader.read_osm_pbf(subregion_name, data_dir, verbose=verbose,
                                                            parse_raw_feat=parse_raw_feat,
                                                            transform_geom=transform_geom)
            # Parsing "rutland-latest.osm.pbf" ... Successfully.
            print(rutland_osm_pbf['points'].coordinates[0])
            # POINT (-0.5134241 52.6555853)


            parse_raw_feat = True
            transform_geom = True
            transform_other_tags = True
            rutland_osm_pbf = geofabrik_reader.read_osm_pbf(subregion_name, data_dir,
                                                            parse_raw_feat=parse_raw_feat,
                                                            transform_geom=transform_geom,
                                                            transform_other_tags=transform_other_tags,
                                                            verbose=verbose)
            # Parsing "rutland-latest.osm.pbf" ... Successfully.
            print(rutland_osm_pbf['points'].other_tags[0])
            # {'odbl': 'clean'}
        """

        assert isinstance(chunk_size_limit, int) or chunk_size_limit is None

        osm_pbf_filename, path_to_osm_pbf = self.Downloader.get_default_path_to_osm_file(
            subregion_name, osm_file_format=".osm.pbf", mkdir=False)

        if osm_pbf_filename and path_to_osm_pbf:
            if not data_dir:  # Go to default file path
                path_to_osm_pbf = path_to_osm_pbf
            else:
                osm_pbf_dir = regulate_input_data_dir(data_dir)
                path_to_osm_pbf = os.path.join(osm_pbf_dir, osm_pbf_filename)

            path_to_pickle = path_to_osm_pbf.replace(".osm.pbf", ".pickle" if parse_raw_feat else "-raw.pickle")
            if os.path.isfile(path_to_pickle) and not update:
                osm_pbf_data = load_pickle(path_to_pickle, verbose=verbose)

            else:
                if not os.path.isfile(path_to_osm_pbf) or update:
                    # If the target file is not available, try downloading it first.
                    self.Downloader.download_subregion_osm_file(
                        subregion_name, osm_file_format=".osm.pbf", download_dir=data_dir, update=update,
                        confirmation_required=download_confirmation_required, verbose=False)

                if verbose and parse_raw_feat:
                    print("Parsing \"{}\"".format(os.path.basename(path_to_osm_pbf)), end=" ... ")
                try:
                    number_of_chunks = get_number_of_chunks(path_to_osm_pbf, chunk_size_limit)

                    osm_pbf_data = parse_osm_pbf(path_to_osm_pbf, number_of_chunks=number_of_chunks,
                                                 parse_raw_feat=parse_raw_feat, transform_geom=transform_geom,
                                                 transform_other_tags=transform_other_tags)
                    print("Successfully. ") if verbose and parse_raw_feat else ""

                    if pickle_it:
                        save_pickle(osm_pbf_data, path_to_pickle, verbose=verbose)

                    if rm_osm_pbf:
                        remove_subregion_osm_file(path_to_osm_pbf, verbose=verbose)

                except Exception as e:
                    print("Failed. {}".format(e))
                    osm_pbf_data = None

            return osm_pbf_data

        else:
            print("Errors occur. Data might not be available for the \"subregion_name\".")


class BBBikeReader:
    """
    A class representation of a tool for reading GeoFabrik data extracts.
    """

    def __init__(self):
        """
        Constructor method.
        """
        self.Downloader = BBBikeDownloader()
        self.Name = copy.copy(self.Downloader.Name)
        self.URL = copy.copy(self.Downloader.URL)

    def get_path_to_file(self, subregion_name, osm_file_format, data_dir=None):
        """
        Retrieve path to BBBike data file (if available) for a subregion.

        :param subregion_name: name of a region/subregion (case-insensitive)
        :type subregion_name: str
        :param osm_file_format: format (file extension) of an OSM data
        :type osm_file_format: str
        :param data_dir: directory where the data file is located/saved; if ``None`` (None), the default directory
        :type data_dir: str, None
        :return: path to the data file
        :rtype: str, None

        **Example**::

            from pydriosm.reader import BBBikeReader

            bbbike_reader = BBBikeReader()

            subregion_name = 'leeds'
            data_dir = "tests"

            osm_file_format = '.osm.pbf'
        """

        _, _, _, path_to_file = self.Downloader.get_valid_download_info(
            subregion_name, osm_file_format=osm_file_format, download_dir=data_dir)

        return path_to_file

    def read_osm_pbf(self, subregion_name, data_dir=None, download_confirmation_required=True, chunk_size_limit=50,
                     parse_raw_feat=False, transform_geom=False, transform_other_tags=False, verbose=False):
        """
        Read BBBike .osm.pbf file of a subregion.

        :param subregion_name: name of a region/subregion (case-insensitive)
        :type subregion_name: str
        :param data_dir: directory where the .osm.pbf data file is located/saved;
            if ``None`` (default), the default directory
        :type data_dir: str, None
        :param download_confirmation_required: whether to ask for confirmation before starting to download a file,
            defaults to ``True``
        :type download_confirmation_required: bool
        :param chunk_size_limit: threshold (in MB) that triggers the use of chunk parser, defaults to ``50``;
            if the size of the .osm.pbf file (in MB) is greater than ``chunk_size_limit``, it will be parsed in a
            chunk-wise way
        :type chunk_size_limit: int
        :param parse_raw_feat: whether to parse each feature in the raw data, defaults to ``False``
        :type parse_raw_feat: bool
        :param transform_geom: whether to transform a single coordinate (or a collection of coordinates) into
            a geometric object, defaults to ``False``
        :type transform_geom: bool
        :param transform_other_tags: whether to transform a ``'other_tags'`` into a dictionary, defaults to ``False``
        :type transform_other_tags: bool
        :param verbose: whether to print relevant information in console as the function runs, defaults to ``False``
        :type verbose: bool, int
        :return: data of the .osm.pbf file
        :rtype: dict, None

        **Example**::

            from pydriosm.reader import BBBikeReader

            bbbike_reader = BBBikeReader()

            subregion_name = 'Leeds'
            download_confirmation_required = True
            chunk_size_limit = 50
            verbose = True

            data_dir = "tests"
            parse_raw_feat = True
            transform_geom = True
            transform_other_tags = True
            leeds_osm_pbf = bbbike_reader.read_osm_pbf(subregion_name, data_dir=data_dir,
                                                       parse_raw_feat=parse_raw_feat,
                                                       transform_geom=transform_geom,
                                                       transform_other_tags=transform_other_tags,
                                                       verbose=verbose)
            # Parsing "Leeds.osm.pbf" ... Successfully.

            print(leeds_osm_pbf)
            # {'points': <data frame>,
            #  'lines': <data frame>,
            #  'multilinestrings': <data frame>,
            #  'multipolygons': <data frame>,
            #  'other_relations: <data frame>'}
        """

        assert isinstance(chunk_size_limit, int) or chunk_size_limit is None

        osm_file_format = ".osm.pbf"

        path_to_osm_pbf = self.get_path_to_file(subregion_name, osm_file_format, data_dir)

        if not os.path.isfile(path_to_osm_pbf):
            path_to_osm_pbf = self.Downloader.download_osm(subregion_name, osm_file_format=osm_file_format,
                                                           download_dir=data_dir,
                                                           confirmation_required=download_confirmation_required,
                                                           verbose=verbose, ret_download_path=True)

        if verbose and parse_raw_feat:
            print("Parsing \"{}\"".format(os.path.basename(path_to_osm_pbf)), end=" ... ")
        try:
            number_of_chunks = get_number_of_chunks(path_to_osm_pbf, chunk_size_limit=chunk_size_limit)

            osm_pbf_data = parse_osm_pbf(path_to_osm_pbf, number_of_chunks=number_of_chunks,
                                         parse_raw_feat=parse_raw_feat, transform_geom=transform_geom,
                                         transform_other_tags=transform_other_tags)

            print("Successfully. ") if verbose and parse_raw_feat else ""

        except Exception as e:
            print("Failed. {}".format(e))
            osm_pbf_data = None

        return osm_pbf_data

    def read_csv_xz(self, subregion_name, data_dir=None, download_confirmation_required=True, verbose=False):
        """
        Read BBBike .csv.xz file of a subregion.

        :param subregion_name: name of a region/subregion (case-insensitive)
        :type subregion_name: str
        :param data_dir: directory where the .csv.xz data file is located/saved;
            if ``None`` (default), the default directory
        :type data_dir: str, None
        :param download_confirmation_required: whether to ask for confirmation before starting to download a file,
            defaults to ``True``
        :type download_confirmation_required: bool
        :param verbose: whether to print relevant information in console as the function runs, defaults to ``False``
        :type verbose: bool, int
        :return: tabular data of the .csv.xz file
        :rtype: pandas.DataFrame

        .. _pydriosm-reader-bbbike-read_csv_xz:

        **Example**::

            from pydriosm.reader import BBBikeReader

            bbbike_reader = BBBikeReader()

            subregion_name = 'Leeds'
            data_dir = "tests"
            download_confirmation_required = True
            verbose = True

            csv_xz_data = bbbike_reader.read_csv_xz(subregion_name, data_dir, verbose=verbose)

            print(csv_xz_data)
            # <data frame>
        """

        osm_file_format = ".csv.xz"

        path_to_csv_xz = self.get_path_to_file(subregion_name, osm_file_format, data_dir)

        if not os.path.isfile(path_to_csv_xz):
            path_to_csv_xz = self.Downloader.download_osm(subregion_name, osm_file_format=osm_file_format,
                                                          download_dir=data_dir,
                                                          confirmation_required=download_confirmation_required,
                                                          verbose=verbose, ret_download_path=True)

        csv_xz_data = parse_csv_xz(path_to_csv_xz)

        return csv_xz_data

    def read_geojson_xz(self, subregion_name, data_dir=None, fmt_geom=False, decode_properties=False,
                        download_confirmation_required=True, verbose=False):
        """
        Read BBBike .geojson.xz file of a subregion.

        :param subregion_name: name of a region/subregion (case-insensitive)
        :type subregion_name: str
        :param data_dir: directory where the .geojson.xz data file is located/saved;
            if ``None`` (default), the default directory
        :type data_dir: str, None
        :param fmt_geom: whether to reformat coordinates into a geometric object, defaults to ``False``
        :type fmt_geom: bool
        :param decode_properties: whether to transform a 'properties' dictionary into tabular form,
            defaults to ``False``
        :type decode_properties: bool
        :param download_confirmation_required: whether to ask for confirmation before starting to download a file,
            defaults to ``True``
        :type download_confirmation_required: bool
        :param verbose: whether to print relevant information in console as the function runs, defaults to ``False``
        :type verbose: bool, int
        :return: tabular data of the .csv.xz file
        :rtype: pandas.DataFrame

        .. _pydriosm-reader-bbbike-read_geojson_xz:

        **Examples**::

            from pydriosm.reader import BBBikeReader

            bbbike_reader = BBBikeReader()

            subregion_name = 'Leeds'
            fmt_geom = False
            decode_properties = False
            download_confirmation_required = True
            verbose = True

            data_dir = "tests"
            geojson_xz = bbbike_reader.read_geojson_xz(subregion_name, data_dir, verbose=verbose)
            print(geojson_xz)
            # <data frame>


            fmt_geom = True
            geojson_xz_data = bbbike_reader.read_geojson_xz(subregion_name, data_dir, fmt_geom=fmt_geom)

            print(geojson_xz_data)
            # <data frame>
        """

        osm_file_format = ".geojson.xz"

        path_to_geojson_xz = self.get_path_to_file(subregion_name, osm_file_format, data_dir)

        if not os.path.isfile(path_to_geojson_xz):
            path_to_geojson_xz = self.Downloader.download_osm(subregion_name, osm_file_format=osm_file_format,
                                                              download_dir=data_dir,
                                                              confirmation_required=download_confirmation_required,
                                                              verbose=verbose, ret_download_path=True)

        geojson_xz_data = parse_geojson_xz(path_to_geojson_xz, fmt_geom=fmt_geom, decode_properties=decode_properties)

        return geojson_xz_data
