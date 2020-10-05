"""
Read the free OSM data extracts.
"""

import collections
import gc
import glob
import itertools
import lzma
import shutil
import zipfile

import geopandas as gpd
import ogr
import rapidjson
import shapefile
import shapely.geometry
from pyhelpers.ops import split_list

from .downloader import *
from .utils import append_fclass_to_shp_filename, find_shp_layer_name, get_number_of_chunks, \
    get_osm_geom_shapely_object_dict, get_pbf_layer_feat_types_dict, get_valid_shp_layer_names, \
    remove_subregion_osm_file


def get_osm_pbf_layer_idx_names(path_to_osm_pbf):
    """
    Get names of all layers in a PBF data file.

    :param path_to_osm_pbf: absolute path to a PBF data file
    :type path_to_osm_pbf: str
    :return: name (and index) of each layer of the PBF data file
    :rtype: dict

    **Example**::

        >>> import os
        >>> from pydriosm import GeofabrikDownloader, get_osm_pbf_layer_idx_names

        >>> geofabrik_downloader = GeofabrikDownloader()

        >>> sr_name = 'Rutland'
        >>> file_fmt = ".pbf"
        >>> dwnld_dir = "tests"

        >>> path_to_rutland_pbf = geofabrik_downloader.download_osm_data(sr_name, file_fmt,
        ...                                                              dwnld_dir, verbose=True,
        ...                                                              ret_download_path=True)
        Confirm to download .osm.pbf data of the following geographic region(s):
            Rutland
        ? [No]|Yes: yes
        Downloading "rutland-latest.osm.pbf" to "\\tests" ...
        Done.

        >>> lyr_idx_names = get_osm_pbf_layer_idx_names(path_to_rutland_pbf)

        >>> for k, v in lyr_idx_names.items(): print(f'{k}: {v}')
        0: points
        1: lines
        2: multilinestrings
        3: multipolygons
        4: other_relations

        >>> # Delete the downloaded PBF data file
        >>> os.remove(path_to_rutland_pbf)
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


def parse_osm_pbf_layer(pbf_layer_data, geo_typ, transform_geom, transform_other_tags):
    """
    Parse data of a layer of PBF data.

    :param pbf_layer_data: data of a specific layer of PBF data.
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

    See the examples for the function :ref:`parse_osm_pbf()<pydriosm-reader-parse_osm_pbf>`.
    """

    def make_point_as_polygon(mp_coords):
        mp_coords, temp = mp_coords.copy(), mp_coords[0][0].copy()

        if len(temp) == 2 and temp[0] == temp[1]:
            mp_coords[0][0] += [temp[0]]

        return mp_coords

    def transform_single_geometry_(geom_data):
        """
        Transform a single coordinate into a geometric object by using `shapely.geometry_`.
        """

        geom_types_funcs, pbf_layer_feat_types = get_osm_geom_shapely_object_dict(), get_pbf_layer_feat_types_dict()
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

        geom_obj_funcs = get_osm_geom_shapely_object_dict()
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
        :type other_tags: str or None
        :return: parsed data of the ``'other_tags'`` record
        :rtype: dict or None
        """

        if other_tags:
            raw_other_tags = (re.sub('^"|"$', '', each_tag) for each_tag in re.split('(?<="),(?=")', other_tags))
            other_tags_ = {k: v.replace('<br>', ' ') for k, v in
                           (re.split('"=>"?', each_tag) for each_tag in filter(None, raw_other_tags))}

        else:  # e.g. other_tags_x is None
            other_tags_ = other_tags

        return other_tags_

    # def decode_other_relations_geometries(other_relations_geom):
    #     or_types = list(set([d['type'] for d in other_relations_geom]))
    #
    #     if len(or_types) == 1:
    #         or_types = or_types[0]
    #
    #     return or_types

    if not pbf_layer_data.empty:
        # Start parsing 'geometry' column
        dat_geometry = pd.DataFrame(x for x in pbf_layer_data.geometry).rename(columns={'type': 'geom_type'})

        if geo_typ != 'other_relations':  # `geo_type` can be 'points', 'lines', 'multilinestrings' or 'multipolygons'
            if transform_geom:
                dat_geometry.coordinates = transform_single_geometry_(dat_geometry)
        else:  # geo_typ == 'other_relations'
            # dat_geometry['geom_types'] = dat_geometry.geometries.map(decode_other_relations_geometries)
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

    if 'id' in parsed_layer_data.columns:
        parsed_layer_data.sort_values('id', inplace=True)
        parsed_layer_data.index = range(len(parsed_layer_data))

    return parsed_layer_data


def parse_osm_pbf(path_to_osm_pbf, number_of_chunks, parse_raw_feat, transform_geom, transform_other_tags):
    """
    Parse a PBF data file.

    :param path_to_osm_pbf: absolute path to a PBF data file
    :type path_to_osm_pbf: str
    :param number_of_chunks: number of chunks
    :type number_of_chunks: int or None
    :param parse_raw_feat: whether to parse each feature in the raw data
    :type parse_raw_feat: bool
    :param transform_geom: whether to transform a single coordinate (or a collection of coordinates) into a geometric
        object
    :param transform_other_tags: whether to transform a ``'other_tags'`` into a dictionary
    :type transform_other_tags: bool
    :return: parsed OSM PBF data
    :rtype: dict

    .. _pydriosm-reader-parse_osm_pbf:

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

        >>> import os
        >>> from pydriosm.reader import GeofabrikDownloader, parse_osm_pbf

        >>> geofabrik_downloader = GeofabrikDownloader()

        >>> sr_name = 'Rutland'
        >>> file_fmt = ".pbf"
        >>> dwnld_dir = "tests"

        >>> path_to_rutland_pbf = geofabrik_downloader.download_osm_data(sr_name, file_fmt,
        ...                                                              dwnld_dir, verbose=True,
        ...                                                              ret_download_path=True)
        Confirm to download .osm.pbf data of the following geographic region(s):
            Rutland
        ? [No]|Yes: yes
        Downloading "rutland-latest.osm.pbf" to "\\tests" ...
        Done.

        >>> rutland_pbf_raw = parse_osm_pbf(path_to_rutland_pbf, number_of_chunks=50,
        ...                                 parse_raw_feat=False, transform_geom=False,
        ...                                 transform_other_tags=False)

        >>> print(list(rutland_pbf_raw.keys()))
        ['points', 'lines', 'multilinestrings', 'multipolygons', 'other_relations']

        >>> rutland_pbf_raw_points = rutland_pbf_raw['points']
        >>> print(rutland_pbf_raw_points.head())
                                                      points
        0  {"type": "Feature", "geometry": {"type": "Poin...
        1  {"type": "Feature", "geometry": {"type": "Poin...
        2  {"type": "Feature", "geometry": {"type": "Poin...
        3  {"type": "Feature", "geometry": {"type": "Poin...
        4  {"type": "Feature", "geometry": {"type": "Poin...

        >>> rutland_pbf_parsed = parse_osm_pbf(path_to_rutland_pbf, number_of_chunks=50,
        ...                                    parse_raw_feat=True, transform_geom=False,
        ...                                    transform_other_tags=False)

        >>> rutland_pbf_parsed_points = rutland_pbf_parsed['points']
        >>> print(rutland_pbf_parsed_points.head())
                 id               coordinates  ... man_made                    other_tags
        0    488432  [-0.5134241, 52.6555853]  ...     None               "odbl"=>"clean"
        1    488658  [-0.5313354, 52.6737716]  ...     None                          None
        2  13883868  [-0.7229332, 52.5889864]  ...     None                          None
        3  14049101  [-0.7249922, 52.6748223]  ...     None  "traffic_calming"=>"cushion"
        4  14558402  [-0.7266686, 52.6695051]  ...     None      "direction"=>"clockwise"
        [5 rows x 12 columns]

        >>> rutland_pbf_parsed_1 = parse_osm_pbf(path_to_rutland_pbf, number_of_chunks=50,
        ...                                      parse_raw_feat=True, transform_geom=True,
        ...                                      transform_other_tags=False)

        >>> rutland_pbf_parsed_points_1 = rutland_pbf_parsed_1['points']
        >>> print(rutland_pbf_parsed_points_1[['coordinates']].head())
                                        coordinates
        0             POINT (-0.5134241 52.6555853)
        1             POINT (-0.5313354 52.6737716)
        2    POINT (-0.7229332000000001 52.5889864)
        3             POINT (-0.7249922 52.6748223)
        4             POINT (-0.7266686 52.6695051)

        >>> rutland_pbf_parsed_2 = parse_osm_pbf(path_to_rutland_pbf, number_of_chunks=50,
        ...                                      parse_raw_feat=True, transform_geom=True,
        ...                                      transform_other_tags=True)

        >>> rutland_pbf_parsed_points_2 = rutland_pbf_parsed_2['points']
        >>> print(rutland_pbf_parsed_points_2[['coordinates', 'other_tags']].head())
                                      coordinates                      other_tags
        0           POINT (-0.5134241 52.6555853)               {'odbl': 'clean'}
        1           POINT (-0.5313354 52.6737716)                            None
        2  POINT (-0.7229332000000001 52.5889864)                            None
        3           POINT (-0.7249922 52.6748223)  {'traffic_calming': 'cushion'}
        4           POINT (-0.7266686 52.6695051)      {'direction': 'clockwise'}

        >>> # Delete the downloaded PBF data file
        >>> os.remove(path_to_rutland_pbf)

    .. seealso::

        The examples for the method :ref:`GeofabrikReader.read_osm_pbf()<pydriosm-reader-geofabrik-read_osm_pbf>`.
    """

    parse_raw_feat_ = True if transform_geom or transform_other_tags else copy.copy(parse_raw_feat)

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
                if parse_raw_feat_:
                    lyr_dat_ = pd.DataFrame(f.ExportToJson(as_object=True) for f in feat)
                    lyr_dat = parse_osm_pbf_layer(lyr_dat_, geo_typ=layer_name, transform_geom=transform_geom,
                                                  transform_other_tags=transform_other_tags)
                    del lyr_dat_
                    gc.collect()
                else:
                    lyr_dat = pd.DataFrame(f.ExportToJson() for f in feat)
                    lyr_dat.columns = [layer_name]

                all_lyr_dat.append(lyr_dat)

                del feat, lyr_dat
                gc.collect()

            layer_data = pd.concat(all_lyr_dat, ignore_index=True, sort=False)

        else:
            if parse_raw_feat_:
                layer_data_ = pd.DataFrame(feature.ExportToJson(as_object=True) for _, feature in enumerate(layer_dat))
                layer_data = parse_osm_pbf_layer(layer_data_, geo_typ=layer_name, transform_geom=transform_geom,
                                                 transform_other_tags=transform_other_tags)
                del layer_data_
                gc.collect()
            else:
                layer_data = pd.DataFrame(feature.ExportToJson() for _, feature in enumerate(layer_dat))
                layer_data.columns = [layer_name]

        all_layer_data.append(layer_data)

        del layer_data
        gc.collect()

    # Make a dictionary in a dictionary form: {Layer name: Layer data}
    osm_pbf_data = dict(zip(layer_names, all_layer_data))

    return osm_pbf_data


def unzip_shp_zip(path_to_shp_zip, path_to_extract_dir=None, layer_names=None, mode='r', clustered=False, verbose=False,
                  ret_extract_dir=False):
    """
    Unzip a .shp.zip file.

    :param path_to_shp_zip: absolute path to a .shp.zip file
    :type path_to_shp_zip: str
    :param path_to_extract_dir: absolute path to a directory where extracted files will be saved;
        if ``None`` (default), use the same directory where the .shp.zip file is
    :type path_to_extract_dir: str or None
    :param layer_names: name of a .shp layer, e.g. 'railways', or names of multiple layers;;
        if ``None`` (default), all available layers
    :type layer_names: str or list or None
    :param mode: the ``mode`` parameter of `zipfile.ZipFile()`_, defaults to ``'r'``
    :type mode: str
    :param clustered: whether to put the data files of different layer in respective folders, defaults to ``False``
    :type clustered: bool
    :param verbose: whether to print relevant information in console as the function runs, defaults to ``False``
    :type verbose: bool or int
    :param ret_extract_dir: whether to return the path to the directory where extracted files are saved,
        defaults to ``False``
    :type ret_extract_dir: bool
    :return: the path to the directory of extracted files when ``ret_extract_dir=True``
    :rtype: str

    .. _`zipfile.ZipFile()`: https://docs.python.org/3/library/zipfile.html#zipfile-objects

    **Examples**::

        >>> import os
        >>> from pyhelpers.dir import cd, delete_dir
        >>> from pydriosm.reader import GeofabrikDownloader, unzip_shp_zip

        >>> geofabrik_downloader = GeofabrikDownloader()

        >>> sr_name = 'Rutland'
        >>> file_fmt = ".shp"
        >>> dwnld_dir = "tests"

        >>> path_to_rutland_shp_zip = geofabrik_downloader.download_osm_data(sr_name, file_fmt,
        ...                                                                  dwnld_dir,
        ...                                                                  ret_download_path=True)
        Confirm to download .shp.zip data of the following geographic region(s):
            Rutland
        ? [No]|Yes: yes

        >>> layer_name = 'railways'

        >>> unzip_shp_zip(path_to_rutland_shp_zip, layer_names=layer_name, verbose=True)
        Extracting from "rutland-latest-free.shp.zip" the following layer(s):
            'railways'
        to "\\tests\\rutland-latest-free-shp" ...
        In progress ... Done.

        >>> path_to_rutland_shp_dir = unzip_shp_zip(path_to_rutland_shp_zip, verbose=True,
        ...                                         ret_extract_dir=True)
        Extracting all of "rutland-latest-free.shp.zip" to "\\tests\\rutland-latest-free-shp" ...
        In progress ... Done.

        >>> print(os.path.relpath(path_to_rutland_shp_dir))
        tests\\rutland-latest-free-shp

        >>> lyr_names = ['railways', 'transport', 'traffic']

        >>> paths_to_layer_dirs = unzip_shp_zip(path_to_rutland_shp_zip, layer_names=lyr_names,
        ...                                     clustered=True, verbose=2, ret_extract_dir=True)
        Extracting from "rutland-latest-free.shp.zip" the following layer(s):
            'railways'
            'transport'
            'traffic'
        to "\\tests\\rutland-latest-free-shp" ...
        In progress ... Done.
        Clustering the layer data ...
            railways ...
            transport ...
            traffic ...
            traffic_a ...
            transport_a ...
        Done.

        >>> for path_to_lyr_dir in paths_to_layer_dirs: print(os.path.relpath(path_to_lyr_dir))
        tests\\rutland-latest-free-shp\\railways
        tests\\rutland-latest-free-shp\\transport
        tests\\rutland-latest-free-shp\\traffic

        >>> # Delete the extracted files
        >>> delete_dir(os.path.dirname(path_to_lyr_dir), verbose=True)
        The directory "\\tests\\rutland-latest-free-shp" is not empty.
        Confirmed to delete it? [No]|Yes: yes
        Deleting "\\tests\\rutland-latest-free-shp" ... Done.

        >>> # Delete the downloaded .shp.zip data file
        >>> os.remove(path_to_rutland_shp_zip)
    """

    extract_dir = path_to_extract_dir if path_to_extract_dir \
        else os.path.splitext(path_to_shp_zip)[0].replace(".", "-")

    if not layer_names:
        layer_names_ = layer_names
        if verbose:
            print("Extracting all of \"{}\" to \"\\{}\" ... ".format(
                os.path.basename(path_to_shp_zip), os.path.relpath(extract_dir)))
    else:
        layer_names_ = [layer_names] if isinstance(layer_names, str) else layer_names.copy()
        if verbose:
            print("Extracting from \"{}\" the following layer(s):".format(os.path.basename(path_to_shp_zip)))
            print("\t{}".format("\n\t".join([f"'{x}'" for x in layer_names_])))
            print("to \"\\{}\" ... ".format(os.path.relpath(extract_dir)))

    print("In progress", end=" ... ") if verbose else ""
    try:
        with zipfile.ZipFile(path_to_shp_zip, mode) as shp_zip:
            if layer_names_:
                extract_files = [f.filename for f in shp_zip.filelist if any(x in f.filename for x in layer_names_)]
            else:
                extract_files = None

            shp_zip.extractall(extract_dir, members=extract_files)

        shp_zip.close()

        if isinstance(extract_files, list) and len(extract_files) == 0:
            print("The specified layer does not exist.\nNo data has been extracted. ") if verbose else ""
        else:
            print("Done. ") if verbose else ""

        if clustered:
            print("Clustering the layer data ... ") if verbose else ""
            file_list = extract_files if extract_files else os.listdir(extract_dir)

            if 'README' in file_list:
                file_list.remove('README')
            filenames_, exts_ = [os.path.splitext(x)[0] for x in file_list], [os.path.splitext(x)[1] for x in file_list]
            filenames, exts = list(set(filenames_)), list(set(exts_))
            layer_names_ = [find_shp_layer_name(f) for f in filenames]

            extract_dirs = []
            for lyr, fn in zip(layer_names_, filenames):
                extract_dir_ = cd(extract_dir, lyr)
                if verbose == 2:
                    print("\t{} ... ".format(lyr if '_a_' not in fn else lyr + '_a')) if verbose == 2 else ""
                for ext in exts:
                    filename = fn + ext
                    orig, dest = cd(extract_dir, filename, mkdir=True), cd(extract_dir_, filename, mkdir=True)
                    shutil.copyfile(orig, dest)
                    os.remove(orig)
                extract_dirs.append(extract_dir_)

            extract_dir = list(set(extract_dirs))

            print("Done. ") if verbose == 2 else ""

    except Exception as e:
        print("Failed. {}".format(e)) if verbose else ""

    if ret_extract_dir:
        return extract_dir


def read_shp_file(path_to_shp, method='geopandas', **kwargs):
    """
    Parse a shapefile.

    :param path_to_shp: absolute path to a .shp data file
    :type: str
    :param method: the method used to read the .shp file;
        if ``'geopandas'`` (default), use the `geopandas.read_file()`_ method,
        for otherwise use `shapefile.Reader()`_
    :type method: str
    :param kwargs: optional parameters of `geopandas.read_file()`_
    :return: data frame of the .shp data
    :rtype: pandas.DataFrame or geopandas.GeoDataFrame

    .. _`geopandas.read_file()`: https://geopandas.org/reference/geopandas.read_file.html
    .. _`shapefile.Reader()`: https://github.com/GeospatialPython/pyshp#reading-shapefiles

    **Examples**::

        >>> from pyhelpers.dir import cd, delete_dir
        >>> from pydriosm.reader import GeofabrikDownloader, unzip_shp_zip, read_shp_file

        >>> geofabrik_downloader = GeofabrikDownloader()

        >>> sr_name = 'Rutland'
        >>> file_fmt = ".shp"
        >>> dwnld_dir = "tests"

        >>> path_to_rutland_shp_zip = geofabrik_downloader.download_osm_data(sr_name, file_fmt,
        ...                                                                  dwnld_dir,
        ...                                                                  ret_download_path=True)
        Confirm to download .shp.zip data of the following geographic region(s):
            Rutland
        ? [No]|Yes: yes

        >>> path_to_rutland_shp_dir = unzip_shp_zip(path_to_rutland_shp_zip, ret_extract_dir=True)

        >>> railways_shp_filename = "gis_osm_railways_free_1.shp"
        >>> path_to_rutland_railways_shp = cd(path_to_rutland_shp_dir, railways_shp_filename)

        >>> rutland_railways_shp = read_shp_file(path_to_rutland_railways_shp, method='gpd')

        >>> print(rutland_railways_shp.head())
            osm_id  code  ... tunnel                                           geometry
        0  2162114  6101  ...      F  LINESTRING (-0.45281 52.69934, -0.45189 52.698...
        1  3681043  6101  ...      F  LINESTRING (-0.65312 52.57308, -0.65318 52.572...
        2  3693985  6101  ...      F  LINESTRING (-0.73234 52.67821, -0.73191 52.678...
        3  3693986  6101  ...      F  LINESTRING (-0.61731 52.61323, -0.62419 52.614...
        4  4806329  6101  ...      F  LINESTRING (-0.45769 52.70352, -0.45654 52.702...
        [5 rows x 8 columns]

        >>> rutland_railways_shp_ = read_shp_file(path_to_rutland_railways_shp, method='pyshp')

        >>> print(rutland_railways_shp_.head())
            osm_id  code  ...                                             coords shape_type
        0  2162114  6101  ...  [(-0.4528083, 52.6993402), (-0.4518933, 52.698...          3
        1  3681043  6101  ...  [(-0.6531215, 52.5730787), (-0.6531793, 52.572...          3
        2  3693985  6101  ...  [(-0.7323403, 52.6782102), (-0.7319059, 52.678...          3
        3  3693986  6101  ...  [(-0.6173072, 52.6132317), (-0.6241869, 52.614...          3
        4  4806329  6101  ...  [(-0.4576926, 52.7035194), (-0.4565358, 52.702...          3
        [5 rows x 9 columns]

        >>> delete_dir(path_to_rutland_shp_dir, verbose=True)
        The directory "\\tests\\rutland-latest-free-shp" is not empty.
        Confirmed to delete it? [No]|Yes: yes
        Deleting "\\tests\\rutland-latest-free-shp" ... Done.

        >>> # Delete the downloaded shapefile
        >>> os.remove(path_to_rutland_shp_zip)
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


def get_default_shp_crs():
    """
    Get default specification of the coordinate reference system (CRS) for saving shapefile format data.

    :return: default settings of CRS
    :rtype: dict

    **Example**::

        >>> from pydriosm.reader import get_default_shp_crs

        >>> default_shp_crs = get_default_shp_crs()

        >>> print(default_shp_crs)
        {'no_defs': True, 'ellps': 'WGS84', 'datum': 'WGS84', 'proj': 'longlat'}
    """

    crs = {'no_defs': True, 'ellps': 'WGS84', 'datum': 'WGS84', 'proj': 'longlat'}

    return crs


def parse_layer_shp(path_to_layer_shp, feature_names=None, crs=None, save_fclass_shp=False, driver='ESRI Shapefile',
                    ret_path_to_fclass_shp=False, **kwargs):
    """
    Parse a layer of OSM shapefile data.

    :param path_to_layer_shp: absolute path(s) to one (or multiple) shapefile(s)
    :type path_to_layer_shp: str or list
    :param feature_names: class name(s) of feature(s), defaults to ``None``
    :type feature_names: str or list or None
    :param crs: specification of coordinate reference system; if ``None`` (default),
        check :py:func:`specify_shp_crs()<pydriosm.reader.specify_shp_crs>`
    :type crs: dict
    :param save_fclass_shp: (when ``fclass`` is not ``None``) whether to save data of the ``fclass`` as shapefile,
        defaults to ``False``
    :type save_fclass_shp: bool
    :param driver: the OGR format driver, defaults to ``'ESRI Shapefile'``;
        see also the ``driver`` parameter of `geopandas.GeoDataFrame.to_file()`_
    :type driver: str
    :param ret_path_to_fclass_shp: (when ``save_fclass_shp`` is ``True``) whether to return the path to
        the saved data of ``fclass``, defaults to ``False``
    :type ret_path_to_fclass_shp: bool
    :param kwargs: optional parameters of :py:func:`read_shp_file()<pydriosm.reader.read_shp_file>`
    :return: parsed shapefile data
    :rtype: geopandas.GeoDataFrame

    .. _`geopandas.GeoDataFrame.to_file()`: https://geopandas.org/reference.html#geopandas.GeoDataFrame.to_file

    **Examples**::

        >>> import os
        >>> from pyhelpers.dir import cd, delete_dir
        >>> from pydriosm.reader import GeofabrikDownloader, parse_layer_shp, unzip_shp_zip

        >>> geofabrik_downloader = GeofabrikDownloader()

        >>> sr_name = 'Rutland'

        >>> path_to_rutland_shp_zip = geofabrik_downloader.download_osm_data(
        ...     sr_name, osm_file_format=".shp", download_dir="tests", confirmation_required=False,
        ...     ret_download_path=True)

        >>> # Extract the downloaded .shp.zip file
        >>> rutland_shp_dir = unzip_shp_zip(path_to_rutland_shp_zip, ret_extract_dir=True)
        >>> path_to_railways_shp = cd(rutland_shp_dir, "gis_osm_railways_free_1.shp")

        >>> rutland_railways_shp = parse_layer_shp(path_to_railways_shp)

        >>> print(rutland_railways_shp.head())
            osm_id  code  ... tunnel                                           geometry
        0  2162114  6101  ...      F  LINESTRING (-0.45281 52.69934, -0.45189 52.698...
        1  3681043  6101  ...      F  LINESTRING (-0.65312 52.57308, -0.65318 52.572...
        2  3693985  6101  ...      F  LINESTRING (-0.73234 52.67821, -0.73191 52.678...
        3  3693986  6101  ...      F  LINESTRING (-0.61731 52.61323, -0.62419 52.614...
        4  4806329  6101  ...      F  LINESTRING (-0.45769 52.70352, -0.45654 52.702...
        [5 rows x 8 columns]

        >>> rutland_railways_rail, path_to_rutland_railways_rail = parse_layer_shp(
        ...     path_to_railways_shp, feature_names='rail', save_fclass_shp=True,
        ...     ret_path_to_fclass_shp=True)

        >>> print(rutland_railways_rail.head())
            osm_id  code  ... tunnel                                           geometry
        0  2162114  6101  ...      F  LINESTRING (-0.45281 52.69934, -0.45189 52.698...
        1  3681043  6101  ...      F  LINESTRING (-0.65312 52.57308, -0.65318 52.572...
        2  3693985  6101  ...      F  LINESTRING (-0.73234 52.67821, -0.73191 52.678...
        3  3693986  6101  ...      F  LINESTRING (-0.61731 52.61323, -0.62419 52.614...
        4  4806329  6101  ...      F  LINESTRING (-0.45769 52.70352, -0.45654 52.702...
        [5 rows x 8 columns]

        >>> print(os.path.relpath(path_to_rutland_railways_rail))
        tests\\rutland-latest-free-shp\\railways\\gis_osm_railways_free_1_rail.shp

        >>> # Delete the extracted data files
        >>> delete_dir(rutland_shp_dir, verbose=True)
        The directory "\\tests\\rutland-latest-free-shp" is not empty.
        Confirmed to delete it? [No]|Yes: yes
        Deleting "\\tests\\rutland-latest-free-shp" ... Done.

        >>> # Delete the downloaded shapefile
        >>> os.remove(path_to_rutland_shp_zip)
    """

    path_to_lyr_shp = [path_to_layer_shp] if isinstance(path_to_layer_shp, str) else copy.copy(path_to_layer_shp)

    if len(path_to_lyr_shp) == 0:
        shp_data = None

    else:
        if crs is None:
            crs = get_default_shp_crs()

        if len(path_to_lyr_shp) == 1:
            path_to_lyr_shp_ = path_to_lyr_shp[0]
            shp_data = read_shp_file(path_to_lyr_shp_, **kwargs)  # gpd.GeoDataFrame(read_shp_file(path_to_shp))
        else:
            shp_data = [read_shp_file(path_to_lyr_shp_, **kwargs) for path_to_lyr_shp_ in path_to_lyr_shp]
            shp_data = pd.concat(shp_data, axis=0, ignore_index=True)

        shp_data.crs = crs

        if feature_names:
            feature_names_ = [feature_names] if isinstance(feature_names, str) else feature_names.copy()

            # valid_features = shp_data.fclass.unique().tolist()
            # if any(f for f in feature_names_ if f not in valid_features):
            #     raise ValueError(f"`feature_names` must belong to {valid_features}")

            if ('type' in shp_data.columns) and ('fclass' not in shp_data.columns):
                shp_data.rename(columns={'type': 'fclass'}, inplace=True)

            shp_data = shp_data.query('fclass in @feature_names_')

            if save_fclass_shp:
                path_to_lyr_shp_ = path_to_lyr_shp[0].replace("_a_", "_")
                path_to_lyr_feat_shp = append_fclass_to_shp_filename(path_to_lyr_shp_, feature_names_)
                shp_data.to_file(path_to_lyr_feat_shp, driver=driver)

                if ret_path_to_fclass_shp:
                    shp_data = shp_data, path_to_lyr_feat_shp

    return shp_data


def merge_shps(paths_to_shp_files, path_to_merged_dir, method='geopandas'):
    """
    Merge multiple shapefiles.

    :param paths_to_shp_files: list of absolute paths to shapefiles (in .shp format)
    :type paths_to_shp_files: list
    :param path_to_merged_dir: absolute path to a directory where the merged files are to be saved
    :type path_to_merged_dir: str
    :param method: the method used to merge/save .shp files;
        if ``'geopandas'`` (default), use the `geopandas.GeoDataFrame.to_file`_ method,
        use `shapefile.Writer`_ otherwise
    :type method: str

    .. _`geopandas.GeoDataFrame.to_file`: https://geopandas.org/reference.html#geopandas.GeoDataFrame.to_file
    .. _`shapefile.Writer`: https://github.com/GeospatialPython/pyshp#writing-shapefiles

    See the example for the function :ref:`merge_layer_shps()<pydriosm-reader-merge_layer_shps>`.
    """

    if method in ('geopandas', 'gpd'):
        shp_data, geom_types = [], []
        for shp_file_path in paths_to_shp_files:
            shp_dat = gpd.read_file(shp_file_path)
            shp_data.append(shp_dat)
            geom_types.append(shp_dat['geometry'].type[0])

        geom_types_ = list(set(geom_types))
        if len(geom_types_) > 1:
            shp_data_dict = collections.defaultdict(list)
            for geo_typ, shp_dat in zip(geom_types, shp_data):
                shp_data_dict[geo_typ].append(shp_dat)

            for k, v in shp_data_dict.items():
                shp_data_ = pd.concat(v, ignore_index=True)
                shp_data_.crs = get_default_shp_crs()
                shp_data_.to_file(filename=path_to_merged_dir + f"_{k.lower()}", driver="ESRI Shapefile")

        else:
            merged_shp_data = pd.concat(shp_data, ignore_index=True)
            merged_shp_data.crs = get_default_shp_crs()
            merged_shp_data.to_file(filename=path_to_merged_dir, driver="ESRI Shapefile")

    else:  # method == 'pyshp'
        # Resource: https://github.com/GeospatialPython/pyshp
        w = shapefile.Writer(path_to_merged_dir)
        for f in paths_to_shp_files:
            r = shapefile.Reader(f)
            w.fields = r.fields[1:]  # skip first deletion field
            w.shapeType = r.shapeType
            for shaperec in r.iterShapeRecords():
                w.record(*shaperec.record)
                w.shape(shaperec.shape)
            r.close()
        w.close()


def merge_layer_shps(paths_to_shp_zip_files, layer_name, method='geopandas', rm_zip_extracts=True, merged_shp_dir=None,
                     rm_shp_temp=True, verbose=False, ret_merged_shp_path=False):
    """
    Merge shapefiles for a layer for two or multiple geographic regions.

    :param paths_to_shp_zip_files: list of absolute paths to data of shapefiles (in .shp.zip format)
    :type paths_to_shp_zip_files: list
    :param layer_name: name of a layer (e.g. 'railways')
    :type layer_name: str
    :param method: the method used to merge/save .shp files;
        if ``'geopandas'`` (default), use the `geopandas.GeoDataFrame.to_file`_ method,
        use `shapefile.Writer`_ otherwise
    :type method: str
    :param rm_zip_extracts: whether to delete the extracted files, defaults to ``False``
    :type rm_zip_extracts: bool
    :param rm_shp_temp: whether to delete temporary layer files, defaults to ``False``
    :type rm_shp_temp: bool
    :param merged_shp_dir: if ``None`` (default), use the layer name as the name of the folder where the merged .shp
        files will be saved
    :type merged_shp_dir: str or None
    :param verbose: whether to print relevant information in console as the function runs, defaults to ``False``
    :type verbose: bool or int
    :param ret_merged_shp_path: whether to return the path to the merged .shp file, defaults to ``False``
    :type ret_merged_shp_path: bool
    :return: the path to the merged file when ``ret_merged_shp_path=True``
    :rtype: list or str

    .. _`geopandas.GeoDataFrame.to_file`: https://geopandas.org/reference.html#geopandas.GeoDataFrame.to_file
    .. _`shapefile.Writer`: https://github.com/GeospatialPython/pyshp#writing-shapefiles

    .. note::

        This function does not create projection (.prj) for the merged map
        (see also [`MMS-1 <http://geospatialpython.com/2011/02/create-prj-projection-file-for.html>`_])

        For valid ``layer_name``,
        check :py:func:`get_valid_shp_layer_names()<pydriosm.utils.get_valid_shp_layer_names>`.

    .. _pydriosm-reader-merge_layer_shps:

    **Example**::

        >>> import os
        >>> from pyhelpers.dir import delete_dir
        >>> from pydriosm.downloader import GeofabrikDownloader
        >>> from pydriosm.reader import merge_layer_shps

        >>> # To merge 'railways' layers of Greater Manchester and West Yorkshire"

        >>> geofabrik_downloader = GeofabrikDownloader()

        >>> sr_names = ['Greater Manchester', 'West Yorkshire']
        >>> dat_dir = "tests"

        >>> shp_zip_file_paths = geofabrik_downloader.download_osm_data(
        ...     sr_names, osm_file_format=".shp", download_dir=dat_dir, confirmation_required=False,
        ...     ret_download_path=True)

        >>> lyr_name = 'railways'

        >>> merged_shp_path = merge_layer_shps(shp_zip_file_paths, layer_name=lyr_name,
        ...                                    verbose=True, ret_merged_shp_path=True)
        Extracting from "greater-manchester-latest-free.shp.zip" the following layer(s):
            'railways'
        to "\\tests\\greater-manchester-latest-free-shp" ...
        In progress ... Done.
        Extracting from "west-yorkshire-latest-free.shp.zip" the following layer(s):
            'railways'
        to "\\tests\\west-yorkshire-latest-free-shp" ...
        In progress ... Done.
        Merging the following shapefiles:
            "greater-manchester_gis_osm_railways_free_1.shp"
            "west-yorkshire_gis_osm_railways_free_1.shp"
        In progress ... Done.
        Find the merged .shp file(s) at "tests\\greater-manchester_west-yorkshire_railways".

        >>> print(os.path.relpath(merged_shp_path))
        tests\\greater-manchester_west-yorkshire_railways\\greater-manchester_west-yorkshire_railways.shp

        >>> # Delete the merged shapefile
        >>> delete_dir(os.path.dirname(merged_shp_path), verbose=True)
        The directory "\\tests\\greater-manchester_west-yorkshire_railways" is not empty.
        Confirmed to delete it? [No]|Yes: yes
        Deleting "\\tests\\greater-manchester_west-yorkshire_railways" ... Done.

        >>> # Delete the downloaded shapefiles
        >>> for shp_zip_file_path in shp_zip_file_paths: os.remove(shp_zip_file_path)

    .. seealso::

        The examples for the method
        :ref:`GeofabrikReader.merge_subregion_layer_shp()<pydriosm-GeofabrikReader-merge_subregion_layer_shp>`.
    """

    path_to_extract_dirs = []
    for path_to_shp_zip in paths_to_shp_zip_files:
        extract_dir = unzip_shp_zip(path_to_shp_zip, layer_names=layer_name, verbose=verbose, ret_extract_dir=True)
        path_to_extract_dirs.append(extract_dir)

    region_names = [re.search(r'.*(?=\.shp\.zip)', os.path.basename(x).replace("-latest-free", "")).group(0)
                    for x in paths_to_shp_zip_files]

    # Specify a directory that stores files for the specific layer
    path_to_data_dir = os.path.commonpath(paths_to_shp_zip_files)
    prefix = "_".join([x.lower().replace(' ', '-') for x in region_names]) + "_"
    suffix = "_temp"
    merged_dirname_temp = f"{prefix}{layer_name}{suffix}"
    path_to_merged_dir_temp = cd(path_to_data_dir, merged_dirname_temp, mkdir=True)

    # Copy files into a temp directory
    paths_to_temp_files = []
    for subregion_name, path_to_extract_dir in zip(region_names, path_to_extract_dirs):
        orig_filename_list = glob.glob1(path_to_extract_dir, f"*{layer_name}*")
        for orig_filename in orig_filename_list:
            orig = cd(path_to_extract_dir, orig_filename)
            dest = cd(path_to_merged_dir_temp, f"{subregion_name.lower().replace(' ', '-')}_{orig_filename}")
            shutil.copyfile(orig, dest)
            paths_to_temp_files.append(dest)

    # Get the absolute paths to the target .shp files
    paths_to_shp_files = [x for x in paths_to_temp_files if x.endswith(".shp")]

    if verbose:
        print("Merging the following shapefiles:")
        print("\t{}".format("\n\t".join("\"{}\"".format(os.path.basename(f)) for f in paths_to_shp_files)))
        print("In progress ... ", end="")
    try:
        if merged_shp_dir:
            path_to_merged_dir = cd(validate_input_data_dir(merged_shp_dir), mkdir=True)
        else:
            path_to_merged_dir = cd(path_to_data_dir, merged_dirname_temp.replace(suffix, "", -1), mkdir=True)

        merge_shps(paths_to_shp_files, path_to_merged_dir, method)

        if method in ('geopandas', 'gpd'):
            # shp_data, geom_types = [], []
            # for shp_file_path in paths_to_shp_files:
            #     shp_dat = gpd.read_file(shp_file_path)
            #     shp_data.append(shp_dat)
            #     geom_types.append(shp_dat['geometry'].type[0])
            #
            # geom_types_ = list(set(geom_types))
            # if len(geom_types_) > 1:
            #     shp_data_dict = collections.defaultdict(list)
            #     for geo_typ, shp_dat in zip(geom_types, shp_data):
            #         shp_data_dict[geo_typ].append(shp_dat)
            #
            #     for k, v in shp_data_dict.items():
            #         shp_data_ = pd.concat(v, ignore_index=True)
            #         shp_data_.crs = get_default_shp_crs()
            #         shp_data_.to_file(filename=path_to_merged_dir + f"_{k.lower()}", driver="ESRI Shapefile")

            if not os.listdir(path_to_merged_dir):
                temp_dirs = []
                for temp_output_file in glob.glob(cd(path_to_merged_dir + "*", f"{prefix}*")):
                    output_file = cd(path_to_merged_dir_temp.replace(suffix, ""))
                    shutil.move(temp_output_file, output_file)
                    temp_dirs.append(os.path.dirname(temp_output_file))

                for temp_dir in set(temp_dirs):
                    shutil.rmtree(temp_dir)

            # else:
            #     merged_shp_data = pd.concat(shp_data, ignore_index=True)
            #     merged_shp_data.crs = get_default_shp_crs()
            #     merged_shp_data.to_file(filename=path_to_merged_dir, driver="ESRI Shapefile")

        else:  # method == 'pyshp'
            # # Resource: https://github.com/GeospatialPython/pyshp
            # w = shapefile.Writer(cd(path_to_merged_dir))  # cd(path_to_merged_dir_temp, merged_dirname_temp)
            # for f in paths_to_shp_files:
            #     r = shapefile.Reader(f)
            #     w.fields = r.fields[1:]  # skip first deletion field
            #     w.shapeType = r.shapeType
            #     for shaperec in r.iterShapeRecords():
            #         w.record(*shaperec.record)
            #         w.shape(shaperec.shape)
            #     r.close()
            # w.close()

            temp_dir = os.path.dirname(path_to_merged_dir)
            paths_to_output_files_temp = [glob.glob(cd(temp_dir, f"{prefix}*.{ext}")) for ext in ("dbf", "shp", "shx")]
            paths_to_output_files_temp = list(itertools.chain.from_iterable(paths_to_output_files_temp))

            for temp_output_file in paths_to_output_files_temp:
                output_file = cd(path_to_merged_dir, os.path.basename(temp_output_file).replace(suffix, ""))
                shutil.move(temp_output_file, output_file)

        print("Done.") if verbose else ""

        if rm_zip_extracts:
            for path_to_extract_dir in path_to_extract_dirs:
                shutil.rmtree(path_to_extract_dir)

        if rm_shp_temp:
            shutil.rmtree(path_to_merged_dir_temp)

        if verbose:
            print(f"Find the merged .shp file(s) at \"{os.path.relpath(path_to_merged_dir)}\".")

        if ret_merged_shp_path:
            path_to_merged_shp = glob.glob(cd(f"{path_to_merged_dir}*", "*.shp"))
            if len(path_to_merged_shp) == 1:
                path_to_merged_shp = path_to_merged_shp[0]
            return path_to_merged_shp

    except Exception as e:
        print("Failed. {}".format(e)) if verbose else ""


def parse_csv_xz(path_to_csv_xz, col_names=None):
    """
    Parse a compressed CSV (.csv.xz) data file.

    :param path_to_csv_xz: absolute path to a .csv.xz data file
    :type path_to_csv_xz: str
    :param col_names: column names of .csv.xz data, defaults to ``None``
    :type col_names: list or None
    :return: tabular data of the CSV file
    :rtype: pandas.DataFrame

    See the example for the method :ref:`BBBikeReader.read_csv_xz()<pydriosm-BBBikeReader-read_csv_xz>`.
    """

    csv_xz_raw = lzma.open(path_to_csv_xz, mode='rt', encoding='utf-8').readlines()
    csv_xz_dat = [x.rstrip('\t\n').split('\t') for x in csv_xz_raw]

    if col_names is None:
        col_names = ['type', 'id', 'feature']

    csv_xz = pd.DataFrame.from_records(csv_xz_dat, columns=col_names)

    return csv_xz


def parse_geojson_xz(path_to_geojson_xz, fmt_geom=False):
    """
    Parse a compressed Osmium GeoJSON (.geojson.xz) data file.

    :param path_to_geojson_xz: absolute path to a .geojson.xz data file
    :type path_to_geojson_xz: str
    :param fmt_geom: whether to reformat coordinates into a geometric object, defaults to ``False``
    :type fmt_geom: bool
    :return: tabular data of the Osmium GeoJSON file
    :rtype: pandas.DataFrame

    See the example for the method :ref:`BBBikeReader.read_geojson_xz()<pydriosm-BBBikeReader-read_geojson_xz>`.
    """

    geojson_xz_raw = rapidjson.load(lzma.open(path_to_geojson_xz, mode='rt', encoding='utf-8'))

    geojson_xz_dat = pd.DataFrame.from_dict(geojson_xz_raw)

    feature_types = geojson_xz_dat.features.map(lambda x: x['type']).to_frame(name='feature_name')

    geom_types = geojson_xz_dat.features.map(lambda x: x['geometry']['type']).to_frame(name='geom_types')

    if fmt_geom:
        geom_types_funcs = get_osm_geom_shapely_object_dict()

        def reformat_geom(geo_typ, coords):
            sub_geom_type_func = geom_types_funcs[geo_typ]
            if geo_typ == 'MultiPolygon':
                geom_coords = sub_geom_type_func(geom_types_funcs['Polygon'](y) for x in coords for y in x)
            else:
                geom_coords = sub_geom_type_func(coords)
            return geom_coords

        coordinates = geojson_xz_dat.features.map(
            lambda x: reformat_geom(x['geometry']['type'], x['geometry']['coordinates'])).to_frame(name='coordinates')

    else:
        coordinates = geojson_xz_dat.features.map(lambda x: x['geometry']['coordinates']).to_frame(name='coordinates')

    properties = geojson_xz_dat.features.map(lambda x: x['properties']).to_frame(name='properties')

    # decode_properties=False
    #
    # :param decode_properties: whether to transform a 'properties' dictionary into tabular form, defaults to ``False``
    # :type decode_properties: bool
    #
    # if decode_properties:
    #     if confirmed("Confirmed to decode \"properties\"\n"
    #                  "(Note this can be very computationally expensive and costing fairly large amount of memory)?"):
    #         properties = pd.concat(properties['properties'].map(pd.json_normalize).to_list())

    geojson_xz_data = pd.concat([feature_types, geom_types, coordinates, properties], axis=1)

    del feature_types, geom_types, coordinates, properties
    gc.collect()

    return geojson_xz_data


# def validate_input_layer_names(layer_names):
#     """
#     Validate the input of layer name(s) for reading shape files.
#
#     :param layer_names: name of a .shp layer, e.g. 'railways', or names of multiple layers;;
#         if ``None`` (default), all available layers
#     :type layer_names: str or list or None
#     :return: valid layer names to be input
#     :rtype: list
#
#
#     **Examples**::
#
#         from pydriosm.reader import validate_shp_layer_names
#
#         layer_names = None
#         layer_names_ = validate_shp_layer_names(layer_names)
#         print(layer_names_)
#         # []
#
#         layer_names = ['point', 'line']
#         layer_names_ = validate_shp_layer_names(layer_names)
#         print(layer_names_)
#         # []
#     """
#
#     if layer_names:
#         layer_names_ = [layer_names] if isinstance(layer_names, str) else layer_names.copy()
#         layer_names_ = [find_similar_str(x, get_valid_shp_layer_names()) for x in layer_names_]
#     else:
#         layer_names_ = []
#
#     return layer_names_


class GeofabrikReader:
    """
    A class representation of a tool for reading `Geofabrik <https://download.geofabrik.de/>`_ data extracts.

    **Example**::

        >>> from pydriosm.reader import GeofabrikReader

        >>> geofabrik_reader = GeofabrikReader()

        >>> print(geofabrik_reader.Name)
        Geofabrik OpenStreetMap data extracts
    """

    def __init__(self):
        """
        Constructor method.
        """
        self.Downloader = GeofabrikDownloader()
        self.Name = copy.copy(self.Downloader.Name)
        self.URL = copy.copy(self.Downloader.URL)

    def get_path_to_osm_pbf(self, subregion_name, data_dir=None):
        """
        Get absolute path to Geofabrik PBF (.osm.pbf) data file (if available) for a geographic region.

        :param subregion_name: name of a geographic region (case-insensitive)
        :type subregion_name: str
        :param data_dir: directory where the data file of the ``subregion_name`` is located/saved;
            if ``None`` (default), the default directory
        :type data_dir: str or None
        :return: path to PBF (.osm.pbf) file
        :rtype: str or None

        **Example**::

            >>> import os
            >>> from pydriosm.reader import GeofabrikReader

            >>> geofabrik_reader = GeofabrikReader()

            >>> sr_name = 'Rutland'

            >>> path_to_rutland_pbf = geofabrik_reader.get_path_to_osm_pbf(sr_name)

            >>> print(path_to_rutland_pbf)
            # (if "rutland-latest.osm.pbf" is not available at the default package data directory)
            # None

            >>> file_fmt = ".pbf"
            >>> dwnld_dir = "tests"

            >>> # Download the PBF data file of Rutland to "\\tests"
            >>> geofabrik_reader.Downloader.download_osm_data(sr_name, file_fmt, dwnld_dir,
            ...                                               verbose=True)
            Confirm to download .osm.pbf data of the following geographic region(s):
                Rutland
            ? [No]|Yes: yes
            Downloading "rutland-latest.osm.pbf" to "\\tests" ...
            Done.

            >>> path_to_rutland_pbf = geofabrik_reader.get_path_to_osm_pbf(sr_name, dwnld_dir)

            >>> print(os.path.relpath(path_to_rutland_pbf))
            tests\\rutland-latest.osm.pbf

            >>> # Delete the downloaded PBF data file
            >>> os.remove(path_to_rutland_pbf)
        """

        osm_pbf_filename_, path_to_osm_pbf_ = self.Downloader.get_default_path_to_osm_file(
            subregion_name, osm_file_format=".osm.pbf", mkdir=False)

        if data_dir is None:  # Go to default file path
            path_to_osm_pbf = path_to_osm_pbf_

        else:
            osm_pbf_dir = validate_input_data_dir(data_dir)
            path_to_osm_pbf = os.path.join(osm_pbf_dir, osm_pbf_filename_)

        if not os.path.isfile(path_to_osm_pbf):
            path_to_osm_pbf = None

        return path_to_osm_pbf

    def read_osm_pbf(self, subregion_name, data_dir=None, chunk_size_limit=50, parse_raw_feat=False,
                     transform_geom=False, transform_other_tags=False, update=False,
                     download_confirmation_required=True, pickle_it=False, ret_pickle_path=False, rm_osm_pbf=False,
                     verbose=False):
        """
        Read Geofabrik PBF (.osm.pbf) data file of a geographic region.

        :param subregion_name: name of a geographic region (case-insensitive)
        :type subregion_name: str
        :param data_dir: directory where the .osm.pbf data file is located/saved; if ``None``, the default directory
        :type data_dir: str or None
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
        :param pickle_it: whether to save the .pbf data as a .pickle file, defaults to ``False``
        :type pickle_it: bool
        :param ret_pickle_path: whether to return an absolute path to the saved pickle file (when ``pickle_it=True``)
        :type ret_pickle_path: bool
        :param rm_osm_pbf: whether to delete the downloaded .osm.pbf file, defaults to ``False``
        :type rm_osm_pbf: bool
        :param verbose: whether to print relevant information in console as the function runs, defaults to ``False``
        :type verbose: bool or int
        :return: dictionary of the .osm.pbf data; when ``pickle_it=True``, return a tuple of the dictionary and
            an absolute path to the pickle file
        :rtype: dict or tuple or None

        .. _pydriosm-reader-geofabrik-read_osm_pbf:

        **Examples**::

            >>> import os
            >>> from pydriosm.reader import GeofabrikReader

            >>> geofabrik_reader = GeofabrikReader()

            >>> sr_name = 'Rutland'
            >>> dat_dir = "tests"

            >>> rutland_pbf_raw = geofabrik_reader.read_osm_pbf(sr_name, dat_dir, verbose=True)
            Confirm to download .osm.pbf data of the following geographic region(s):
                Rutland
            ? [No]|Yes: yes

            >>> print(list(rutland_pbf_raw.keys()))
            ['points', 'lines', 'multilinestrings', 'multipolygons', 'other_relations']

            >>> rutland_pbf_raw_points = rutland_pbf_raw['points']
            >>> print(rutland_pbf_raw_points.head())
                                                          points
            0  {"type": "Feature", "geometry": {"type": "Poin...
            1  {"type": "Feature", "geometry": {"type": "Poin...
            2  {"type": "Feature", "geometry": {"type": "Poin...
            3  {"type": "Feature", "geometry": {"type": "Poin...
            4  {"type": "Feature", "geometry": {"type": "Poin...

            >>> rutland_pbf_parsed = geofabrik_reader.read_osm_pbf(sr_name, dat_dir,
            ...                                                    parse_raw_feat=True,
            ...                                                    verbose=True)
            Parsing "\\tests\\rutland-latest.osm.pbf" ... Done.

            >>> rutland_pbf_parsed_points = rutland_pbf_parsed['points']
            >>> print(rutland_pbf_parsed_points.head())
                     id               coordinates  ... man_made                    other_tags
            0    488432  [-0.5134241, 52.6555853]  ...     None               "odbl"=>"clean"
            1    488658  [-0.5313354, 52.6737716]  ...     None                          None
            2  13883868  [-0.7229332, 52.5889864]  ...     None                          None
            3  14049101  [-0.7249922, 52.6748223]  ...     None  "traffic_calming"=>"cushion"
            4  14558402  [-0.7266686, 52.6695051]  ...     None      "direction"=>"clockwise"
            [5 rows x 12 columns]

            >>> rutland_pbf_parsed_1 = geofabrik_reader.read_osm_pbf(sr_name, dat_dir,
            ...                                                      parse_raw_feat=True,
            ...                                                      transform_geom=True,
            ...                                                      verbose=True)
            Parsing "\\tests\\rutland-latest.osm.pbf" ... Done.

            >>> rutland_pbf_parsed_1_points = rutland_pbf_parsed_1['points']
            >>> print(rutland_pbf_parsed_1_points[['coordinates']].head())
                                          coordinates
            0           POINT (-0.5134241 52.6555853)
            1           POINT (-0.5313354 52.6737716)
            2  POINT (-0.7229332000000001 52.5889864)
            3           POINT (-0.7249922 52.6748223)
            4           POINT (-0.7266686 52.6695051)

            >>> rutland_pbf_parsed_2 = geofabrik_reader.read_osm_pbf(sr_name, dat_dir,
            ...                                                      parse_raw_feat=True,
            ...                                                      transform_geom=True,
            ...                                                      transform_other_tags=True,
            ...                                                      verbose=True)

            >>> rutland_pbf_parsed_2_points = rutland_pbf_parsed_2['points']
            >>> print(rutland_pbf_parsed_2_points[['other_tags']].head())
                                   other_tags
            0               {'odbl': 'clean'}
            1                            None
            2                            None
            3  {'traffic_calming': 'cushion'}
            4      {'direction': 'clockwise'}

            >>> # Delete the downloaded PBF data file
            >>> os.remove(f"{dat_dir}\\rutland-latest.osm.pbf")
        """

        osm_file_format = ".osm.pbf"

        assert isinstance(chunk_size_limit, int) or chunk_size_limit is None

        osm_pbf_filename, path_to_osm_pbf = self.Downloader.get_default_path_to_osm_file(
            subregion_name, osm_file_format=osm_file_format, mkdir=False)

        if osm_pbf_filename and path_to_osm_pbf:
            if not data_dir:  # Go to default file path
                path_to_osm_pbf = path_to_osm_pbf
            else:
                osm_pbf_dir = validate_input_data_dir(data_dir)
                path_to_osm_pbf = os.path.join(osm_pbf_dir, osm_pbf_filename)

            path_to_pickle = path_to_osm_pbf.replace(osm_file_format,
                                                     "-pbf.pickle" if parse_raw_feat else "-raw.pickle")
            if os.path.isfile(path_to_pickle) and not update:
                osm_pbf_data = load_pickle(path_to_pickle)

                if ret_pickle_path:
                    osm_pbf_data = osm_pbf_data, path_to_pickle

            else:
                if not os.path.isfile(path_to_osm_pbf) or update:
                    # If the target file is not available, try downloading it first.
                    self.Downloader.download_osm_data(subregion_name, osm_file_format=osm_file_format,
                                                      download_dir=data_dir, update=update,
                                                      confirmation_required=download_confirmation_required,
                                                      verbose=False)

                if verbose and parse_raw_feat:
                    print("Parsing \"\\{}\"".format(os.path.relpath(path_to_osm_pbf)), end=" ... ")
                try:
                    number_of_chunks = get_number_of_chunks(path_to_osm_pbf, chunk_size_limit)

                    osm_pbf_data = parse_osm_pbf(path_to_osm_pbf, number_of_chunks=number_of_chunks,
                                                 parse_raw_feat=parse_raw_feat, transform_geom=transform_geom,
                                                 transform_other_tags=transform_other_tags)
                    print("Done. ") if verbose and parse_raw_feat else ""

                    if pickle_it:
                        save_pickle(osm_pbf_data, path_to_pickle, verbose=verbose)

                        if ret_pickle_path:
                            osm_pbf_data = osm_pbf_data, path_to_pickle

                    if rm_osm_pbf:
                        remove_subregion_osm_file(path_to_osm_pbf, verbose=verbose)

                except Exception as e:
                    print("Failed. {}".format(e))
                    osm_pbf_data = None

            return osm_pbf_data

        else:
            print("Errors occur. Data might not be available for the \"subregion_name\".")

    def get_path_to_osm_shp(self, subregion_name, layer_name=None, feature_name=None, data_dir=None, file_ext=".shp"):
        """
        Get absolute path(s) to .shp file(s) for a geographic region via searching the directory of Geofabrik data.

        :param subregion_name: name of a region/subregion (case-insensitive)
        :type subregion_name: str
        :param layer_name: name of a .shp layer (e.g. ``'railways'``), defaults to ``None``
        :type layer_name: str or None
        :param feature_name: name of a feature (e.g. ``'rail'``); if ``None`` (default), all available features included
        :type feature_name: str or None
        :param data_dir: directory where the search is conducted; if ``None`` (default), the default directory
        :type data_dir: str or None
        :param file_ext: file extension, defaults to ``".shp"``
        :type file_ext: str
        :return: path(s) to .shp file(s)
        :rtype: list or str

        **Examples**::

            >>> import os
            >>> from pyhelpers.dir import delete_dir
            >>> from pydriosm.reader import GeofabrikReader, unzip_shp_zip, parse_layer_shp

            >>> geofabrik_reader = GeofabrikReader()

            >>> sr_name = 'Rutland'
            >>> file_fmt = ".shp"

            >>> path_to_shp_file = geofabrik_reader.get_path_to_osm_shp(sr_name)
            >>> print(path_to_shp_file)
            # (if "gis.osm_railways_free_1.shp" is not available at the package data directory)
            []

            >>> dwnld_dir = "tests"

            >>> # Download the shapefiles of Rutland
            >>> path_to_rutland_shp_zip = geofabrik_reader.Downloader.download_osm_data(
            ...     sr_name, file_fmt, dwnld_dir, confirmation_required=False,
            ...     ret_download_path=True)

            >>> unzip_shp_zip(path_to_rutland_shp_zip, verbose=True)
            Extracting all of "rutland-latest-free.shp.zip" to "\\tests\\rutland-latest-free-shp" ...
            In progress ... Done.

            >>> lyr_name = 'railways'

            >>> path_to_rutland_railways_shp = geofabrik_reader.get_path_to_osm_shp(
            ...     sr_name, lyr_name, data_dir=dwnld_dir)

            >>> print(os.path.relpath(path_to_rutland_railways_shp))
            tests\\rutland-latest-free-shp\\gis_osm_railways_free_1.shp

            >>> feat_name = 'rail'

            >>> _ = parse_layer_shp(path_to_rutland_railways_shp, feature_names=feat_name,
            ...                     save_fclass_shp=True)

            >>> path_to_rutland_railways_rail_shp = geofabrik_reader.get_path_to_osm_shp(
            ...     sr_name, lyr_name, feat_name, data_dir=dwnld_dir)

            >>> print(os.path.relpath(path_to_rutland_railways_rail_shp))
            tests\\rutland-latest-free-shp\\railways\\gis_osm_railways_free_1_rail.shp

            >>> # Delete the extracted files
            >>> delete_dir(os.path.dirname(path_to_rutland_railways_shp), verbose=True)
            The directory "\\tests\\rutland-latest-free-shp" is not empty.
            Confirmed to delete it? [No]|Yes: yes
            Deleting "\\tests\\rutland-latest-free-shp" ... Done.

            >>> # Delete the downloaded .shp.zip file
            >>> os.remove(path_to_rutland_shp_zip)
        """

        if data_dir is None:  # Go to default file path
            _, path_to_shp_zip = self.Downloader.get_default_path_to_osm_file(
                subregion_name, osm_file_format=".shp.zip", mkdir=False)
        else:
            shp_zip_filename = self.Downloader.get_default_osm_filename(subregion_name, osm_file_format=".shp.zip")
            path_to_shp_zip = cd(validate_input_data_dir(data_dir), shp_zip_filename)
        shp_dir = os.path.splitext(path_to_shp_zip)[0].replace(".", "-")

        if layer_name is None:
            path_to_osm_shp_file = glob.glob(shp_dir + "\\*" + file_ext)
        else:
            layer_name_ = find_similar_str(layer_name, get_valid_shp_layer_names())
            if feature_name is None:
                pat = re.compile(r"gis_osm_{}(_a)?(_free)?(_1)?{}".format(layer_name_, file_ext))
                path_to_osm_shp_file = [f for f in glob.glob(cd(shp_dir, f"*{file_ext}")) if re.search(pat, f)]
            else:
                pat = re.compile(r"gis_osm_{}(_a)?(_free)?(_1)_{}{}".format(layer_name_, feature_name, file_ext))
                path_to_osm_shp_file = [f for f in glob.glob(cd(shp_dir, layer_name_, f"*{file_ext}"))
                                        if re.search(pat, f)]

        # if not osm_file_paths: print("The required file may not exist.")

        if len(path_to_osm_shp_file) == 1:
            path_to_osm_shp_file = path_to_osm_shp_file[0]

        return path_to_osm_shp_file

    def merge_subregion_layer_shp(self, layer_name, subregion_names, data_dir=None, method='geopandas', update=False,
                                  download_confirmation_required=True, rm_zip_extracts=True, merged_shp_dir=None,
                                  rm_shp_temp=True, verbose=False, ret_merged_shp_path=False):
        """
        Merge shapefiles for a layer for two or multiple geographic regions.

        :param subregion_names: a list of subregion names
        :type subregion_names: list
        :param layer_name: name of a layer (e.g. 'railways')
        :type layer_name: str
        :param method: the method used to merge/save .shp files;
            if ``'geopandas'`` (default), use the `geopandas.GeoDataFrame.to_file`_ method,
            use `shapefile.Writer`_ otherwise
        :type method: str
        :param update: whether to update the source .shp.zip files, defaults to ``False``
        :type update: bool
        :param download_confirmation_required: whether to ask for confirmation before starting to download a file,
            defaults to ``True``
        :type download_confirmation_required: bool
        :param data_dir: directory where the .shp.zip data files are located/saved; if ``None``, the default directory
        :type data_dir: str or None
        :param rm_zip_extracts: whether to delete the extracted files, defaults to ``False``
        :type rm_zip_extracts: bool
        :param rm_shp_temp: whether to delete temporary layer files, defaults to ``False``
        :type rm_shp_temp: bool
        :param merged_shp_dir: if ``None`` (default), use the layer name as the name of the folder where the merged .shp
            files will be saved
        :type merged_shp_dir: str or None
        :param verbose: whether to print relevant information in console as the function runs, defaults to ``False``
        :type verbose: bool or int
        :param ret_merged_shp_path: whether to return the path to the merged .shp file, defaults to ``False``
        :type ret_merged_shp_path: bool
        :return: the path to the merged file when ``ret_merged_shp_path=True``
        :rtype: list or str

        .. _`geopandas.GeoDataFrame.to_file`: https://geopandas.org/reference.html#geopandas.GeoDataFrame.to_file
        .. _`shapefile.Writer`: https://github.com/GeospatialPython/pyshp#writing-shapefiles

        .. _pydriosm-GeofabrikReader-merge_subregion_layer_shp:

        **Examples**::

            >>> import os
            >>> from pyhelpers.dir import cd, delete_dir
            >>> from pydriosm.reader import GeofabrikReader

            >>> geofabrik_reader = GeofabrikReader()

            >>> # To merge 'railways' of Greater Manchester and West Yorkshire
            >>> lyr_name = 'railways'
            >>> sr_names = ['Manchester', 'West Yorkshire']
            >>> dat_dir = "tests"

            >>> path_to_merged_shp_file = geofabrik_reader.merge_subregion_layer_shp(
            ...     lyr_name, sr_names, dat_dir, verbose=True, ret_merged_shp_path=True)
            Confirm to download .shp.zip data of the following geographic region(s):
                Greater Manchester
                West Yorkshire
            ? [No]|Yes: yes
            Downloading "greater-manchester-latest-free.shp.zip" to "\\tests" ...
            Done.
            Downloading "west-yorkshire-latest-free.shp.zip" to "\\tests" ...
            Done.
            Extracting from "greater-manchester-latest-free.shp.zip" the following layer(s):
                'railways'
            to "\\tests\\greater-manchester-latest-free-shp" ...
            In progress ... Done.
            Extracting from "west-yorkshire-latest-free.shp.zip" the following layer(s):
                'railways'
            to "\\tests\\west-yorkshire-latest-free-shp" ...
            In progress ... Done.
            Merging the following shapefiles:
                "greater-manchester_gis_osm_railways_free_1.shp"
                "west-yorkshire_gis_osm_railways_free_1.shp"
            In progress ... Done.
            Find the merged .shp file(s) at "tests\\greater-manchester_west-yorkshire_railways".

            >>> print(os.path.relpath(path_to_merged_shp_file))
            tests\\greater-manchester_west-yorkshire_railways\\greater-manchester_west-yorkshire_railways.shp

            >>> # Delete the merged files
            >>> delete_dir(os.path.dirname(path_to_merged_shp_file), verbose=True)
            The directory "\\tests\\greater-manchester_west-yorkshire_railways" is not empty.
            Confirmed to delete it? [No]|Yes: yes
            Deleting "\\tests\\greater-manchester_west-yorkshire_railways" ... Done.

            >>> # Delete the downloaded .shp.zip data files
            >>> os.remove(cd(dat_dir, "greater-manchester-latest-free.shp.zip"))
            >>> os.remove(cd(dat_dir, "west-yorkshire-latest-free.shp.zip"))

            >>> # To merge 'transport' of Greater London, Kent and Surrey

            >>> lyr_name = 'transport'
            >>> sr_names = ['London', 'Kent', 'Surrey']

            >>> path_to_merged_shp_files = geofabrik_reader.merge_subregion_layer_shp(
            ...     lyr_name, sr_names, dat_dir, verbose=True, ret_merged_shp_path=True)
            Confirm to download .shp.zip data of the following geographic region(s):
                Greater London
                Kent
                Surrey
            ? [No]|Yes: yes
            Downloading "greater-london-latest-free.shp.zip" to "\\tests" ...
            Done.
            Downloading "kent-latest-free.shp.zip" to "\\tests" ...
            Done.
            Downloading "surrey-latest-free.shp.zip" to "\\tests" ...
            Done.
            Extracting from "greater-london-latest-free.shp.zip" the following layer(s):
                'transport'
            to "\\tests\\greater-london-latest-free-shp" ...
            In progress ... Done.
            Extracting from "kent-latest-free.shp.zip" the following layer(s):
                'transport'
            to "\\tests\\kent-latest-free-shp" ...
            In progress ... Done.
            Extracting from "surrey-latest-free.shp.zip" the following layer(s):
                'transport'
            to "\\tests\\surrey-latest-free-shp" ...
            In progress ... Done.
            Merging the following shapefiles:
                "greater-london_gis_osm_transport_a_free_1.shp"
                "greater-london_gis_osm_transport_free_1.shp"
                "kent_gis_osm_transport_a_free_1.shp"
                "kent_gis_osm_transport_free_1.shp"
                "surrey_gis_osm_transport_a_free_1.shp"
                "surrey_gis_osm_transport_free_1.shp"
            In progress ... Done.
            Find the merged .shp file(s) at "tests\\greater-london_kent_surrey_transport".

            >>> for path_to_merged_shp_file in path_to_merged_shp_files:
            ...     print(os.path.relpath(path_to_merged_shp_file))
            tests\\greater-london_kent_surrey_transport\\greater-london_kent_surrey_transport_point.shp
            tests\\greater-london_kent_surrey_transport\\greater-london_kent_surrey_transport_polygon.shp

            >>> # Delete the merged files
            >>> delete_dir(os.path.commonpath(path_to_merged_shp_files), verbose=True)
            The directory "\\tests\\greater-london_kent_surrey_transport" is not empty.
            Confirmed to delete it? [No]|Yes: yes
            Deleting "\\tests\\greater-london_kent_surrey_transport" ... Done.

            >>> # Delete the downloaded .shp.zip data files
            >>> os.remove(cd(dat_dir, "greater-london-latest-free.shp.zip"))
            >>> os.remove(cd(dat_dir, "kent-latest-free.shp.zip"))
            >>> os.remove(cd(dat_dir, "surrey-latest-free.shp.zip"))
        """

        # Make sure all the required shape files are ready
        layer_name_ = find_similar_str(layer_name, get_valid_shp_layer_names())
        subregion_names_ = [self.Downloader.validate_input_subregion_name(x) for x in subregion_names]

        osm_file_format = ".shp.zip"

        # # Extract all files from .zip
        # if data_dir is None:
        #     paths_to_shp_zip_files = [self.Downloader.get_default_path_to_osm_file(x, osm_file_format, mkdir=False)[1]
        #                               for x in subregion_names_]
        # else:
        #     default_filenames = (self.Downloader.get_default_path_to_osm_file(x, osm_file_format, mkdir=False)[0]
        #                          for x in subregion_names_)
        #     paths_to_shp_zip_files = [cd(validate_input_data_dir(data_dir), f) for f in default_filenames]

        # Download the files (if not available)
        paths_to_shp_zip_files = self.Downloader.download_osm_data(subregion_names_, osm_file_format=osm_file_format,
                                                                   download_dir=data_dir, update=update,
                                                                   confirmation_required=download_confirmation_required,
                                                                   deep_retry=True, interval_sec=0, verbose=verbose,
                                                                   ret_download_path=True)

        if all(os.path.isfile(path_to_shp_zip_file) for path_to_shp_zip_file in paths_to_shp_zip_files):
            path_to_merged_shp = merge_layer_shps(paths_to_shp_zip_files, layer_name_, method=method,
                                                  rm_zip_extracts=rm_zip_extracts, merged_shp_dir=merged_shp_dir,
                                                  rm_shp_temp=rm_shp_temp, verbose=verbose,
                                                  ret_merged_shp_path=ret_merged_shp_path)

            if ret_merged_shp_path:
                return path_to_merged_shp

    def read_shp_zip(self, subregion_name, layer_names=None, feature_names=None, data_dir=None, update=False,
                     download_confirmation_required=True, pickle_it=False, ret_pickle_path=False, rm_extracts=False,
                     rm_shp_zip=False, verbose=False):
        """
        Read Geofabrik .shp.zip file of a subregion.

        :param subregion_name: name of a region/subregion (case-insensitive)
        :type subregion_name: str
        :param layer_names: name of a .shp layer, e.g. 'railways', or names of multiple layers;;
            if ``None`` (default), all available layers
        :type layer_names: str or list or None
        :param feature_names: name of a feature, e.g. 'rail', or names of multiple features;
            if ``None`` (default), all available features
        :type feature_names: str or list or None
        :param data_dir: directory where the .shp.zip data file is located/saved;
            if ``None``, the default directory
        :type data_dir: str or None
        :param update: whether to check to update pickle backup (if available), defaults to ``False``
        :type update: bool
        :param download_confirmation_required: whether to ask for confirmation before starting to download a file,
            defaults to ``True``
        :type download_confirmation_required: bool
        :param pickle_it: whether to save the .shp data as a .pickle file, defaults to ``False``
        :type pickle_it: bool
        :param ret_pickle_path: whether to return an absolute path to the saved pickle file (when ``pickle_it=True``)
        :type ret_pickle_path: bool
        :param rm_extracts: whether to delete extracted files from the .shp.zip file, defaults to ``False``
        :type rm_extracts: bool
        :param rm_shp_zip: whether to delete the downloaded .shp.zip file, defaults to ``False``
        :type rm_shp_zip: bool
        :param verbose: whether to print relevant information in console as the function runs, defaults to ``False``
        :type verbose: bool or int
        :return: dictionary of the shapefile data, with keys and values being layer names and
            tabular data (in the format of `geopandas.GeoDataFrame`_), respectively
        :rtype: dict or None

        .. _`geopandas.GeoDataFrame`: https://geopandas.org/reference.html#geodataframe

        **Example**::

            >>> from pydriosm.reader import GeofabrikReader

            >>> geofabrik_reader = GeofabrikReader()

            >>> sr_name = 'Rutland'
            >>> dat_dir = "tests"

            >>> rutland_shp = geofabrik_reader.read_shp_zip(sr_name, data_dir=dat_dir)
            Confirm to download .shp.zip data of the following geographic region(s):
                Rutland
            ? [No]|Yes: yes

            >>> print(list(rutland_shp.keys()))
            ['buildings',
             'traffic',
             'water',
             'roads',
             'places',
             'pofw',
             'waterways',
             'pois',
             'landuse',
             'transport',
             'natural',
             'railways']

            >>> rutland_shp_railways = rutland_shp['railways']
            >>> print(rutland_shp_railways.head())
                osm_id  code  ... tunnel                                           geometry
            0  2162114  6101  ...      F  LINESTRING (-0.45281 52.69934, -0.45189 52.698...
            1  3681043  6101  ...      F  LINESTRING (-0.65312 52.57308, -0.65318 52.572...
            2  3693985  6101  ...      F  LINESTRING (-0.73234 52.67821, -0.73191 52.678...
            3  3693986  6101  ...      F  LINESTRING (-0.61731 52.61323, -0.62419 52.614...
            4  4806329  6101  ...      F  LINESTRING (-0.45769 52.70352, -0.45654 52.702...
            [5 rows x 8 columns]

            >>> sr_layer = 'transport'

            >>> rutland_shp_transport = geofabrik_reader.read_shp_zip(
            ...     sr_name, sr_layer, data_dir=dat_dir, verbose=True, rm_extracts=True)
            Deleting the extracts "\\tests\\rutland-latest-free-shp"  ... Done.

            >>> print(list(rutland_shp_transport.keys()))
            ['transport']

            >>> print(rutland_shp_transport['transport'].head())
                  osm_id  code    fclass                    name                   geometry
            0  472398147  5621  bus_stop                    None  POINT (-0.73213 52.66974)
            1  502322073  5621  bus_stop              Fife Close  POINT (-0.50962 52.66052)
            2  502322075  5621  bus_stop              Fife Close  POINT (-0.50973 52.66058)
            3  502322076  5621  bus_stop          Aberdeen Close  POINT (-0.51039 52.65817)
            4  502322077  5621  bus_stop  Arran Road (South End)  POINT (-0.50973 52.65469)

            >>> feat_name = 'bus_stop'

            >>> rutland_shp_transport_bus_stop = geofabrik_reader.read_shp_zip(
            ...     sr_name, sr_layer, feat_name, dat_dir, verbose=True, rm_extracts=True)
            Extracting from "rutland-latest-free.shp.zip" the following layer(s):
                'transport'
            to "\\tests\\rutland-latest-free-shp" ...
            In progress ... Done.
            Deleting the extracts "\\tests\\rutland-latest-free-shp"  ... Done.

            >>> print(list(rutland_shp_transport_bus_stop.keys()))
            ['transport']

            >>> print(rutland_shp_transport_bus_stop['transport'].fclass.unique())
            ['bus_stop']

            >>> sr_layers = ['traffic', 'roads']
            >>> feat_names = ['parking', 'trunk']

            >>> rutland_shp_tr_pt = geofabrik_reader.read_shp_zip(sr_name, sr_layers, feat_name,
            ...                                                   dat_dir, verbose=True,
            ...                                                   rm_extracts=True, rm_shp_zip=True)
            Extracting from "rutland-latest-free.shp.zip" the following layer(s):
                'traffic'
                'roads'
            to "\\tests\\rutland-latest-free-shp" ...
            In progress ... Done.
            Deleting the extracts "\\tests\\rutland-latest-free-shp"  ... Done.
            Deleting "tests\\rutland-latest-free.shp.zip" ... Done.

            >>> print(list(rutland_shp_tr_pt.keys()))
            ['traffic', 'roads']

            >>> selected_columns = ['fclass', 'name', 'geometry']

            >>> rutland_shp_tr_pt_traffic = rutland_shp_tr_pt['traffic']
            >>> print(rutland_shp_tr_pt_traffic[selected_columns].head())
                fclass  name                                           geometry
            0  parking  None  POLYGON ((-0.66704 52.71108, -0.66670 52.71121...
            1  parking  None  POLYGON ((-0.78712 52.71974, -0.78700 52.71991...
            2  parking  None  POLYGON ((-0.70368 52.65567, -0.70362 52.65587...
            3  parking  None  POLYGON ((-0.63381 52.66442, -0.63367 52.66441...
            4  parking  None  POLYGON ((-0.62814 52.64093, -0.62701 52.64169...

            >>> rutland_shp_tr_pt_roads = rutland_shp_tr_pt['roads']
            >>> print(rutland_shp_tr_pt_roads[selected_columns].head())
               fclass           name                                           geometry
            0   trunk           None  LINESTRING (-0.72461 52.59642, -0.72452 52.596...
            1   trunk   Glaston Road  LINESTRING (-0.64671 52.59353, -0.64590 52.593...
            3   trunk  Orange Street  LINESTRING (-0.72293 52.58899, -0.72297 52.588...
            11  trunk    Ayston Road  LINESTRING (-0.72483 52.59610, -0.72493 52.596...
            12  trunk    London Road  LINESTRING (-0.72261 52.58759, -0.72264 52.587...
        """

        osm_file_format = ".shp.zip"

        shp_zip_filename, path_to_shp_zip = self.Downloader.get_default_path_to_osm_file(
            subregion_name=subregion_name, osm_file_format=osm_file_format, mkdir=False)

        if layer_names:
            layer_names_ = [layer_names] if isinstance(layer_names, str) else layer_names.copy()
        else:
            layer_names_ = []  # get_valid_shp_layer_names()

        if feature_names:
            feature_names_ = [feature_names] if isinstance(feature_names, str) else feature_names.copy()
        else:
            feature_names_ = []

        if shp_zip_filename and path_to_shp_zip:
            path_to_extract_dir = os.path.splitext(path_to_shp_zip)[0].replace(".", "-")
            if data_dir:
                shp_zip_dir = validate_input_data_dir(data_dir)
                path_to_shp_zip = cd(shp_zip_dir, shp_zip_filename)
                path_to_extract_dir = cd(shp_zip_dir, os.path.basename(path_to_extract_dir))

            if layer_names_:  # layer is not None
                # Make a local path for saving a pickle file for .shp data
                filename_ = shp_zip_filename.replace("-latest-free.shp.zip", "")
                sub_fname = "-".join(x for x in [filename_] + layer_names_ + (feature_names_ if feature_names_ else [])
                                     if x)
                path_to_shp_pickle = cd(os.path.dirname(path_to_extract_dir), sub_fname + "-shp.pickle")
            else:
                path_to_shp_pickle = path_to_extract_dir + ".pickle"

            if os.path.isfile(path_to_shp_pickle) and not update:
                shp_data = load_pickle(path_to_shp_pickle)

                if ret_pickle_path:
                    shp_data = shp_data, path_to_shp_pickle

            else:
                # Download the requested OSM file urlretrieve(download_url, file_path)
                if not os.path.exists(path_to_extract_dir):
                    if not os.path.exists(path_to_shp_zip):
                        self.Downloader.download_osm_data(subregion_name, osm_file_format=osm_file_format,
                                                          download_dir=data_dir, update=update,
                                                          confirmation_required=download_confirmation_required,
                                                          verbose=verbose)

                    unzip_shp_zip(path_to_shp_zip, path_to_extract_dir, layer_names=layer_names_, verbose=verbose)

                    if not layer_names_:
                        layer_names_ = list(set(
                            [find_shp_layer_name(x) for x in os.listdir(cd(path_to_extract_dir)) if x != 'README']))

                else:
                    unavailable_layers = []

                    layer_names_temp_ = [find_shp_layer_name(x) for x in os.listdir(cd(path_to_extract_dir))
                                         if x != 'README']
                    layer_names_temp = list(set(layer_names_ + layer_names_temp_))

                    for lyr_name in layer_names_temp:
                        shp_filename = self.get_path_to_osm_shp(subregion_name, layer_name=lyr_name, data_dir=data_dir)
                        if not shp_filename:
                            unavailable_layers.append(lyr_name)

                    if unavailable_layers:
                        if not os.path.exists(path_to_shp_zip):
                            self.Downloader.download_osm_data(subregion_name, osm_file_format=osm_file_format,
                                                              download_dir=data_dir, update=update,
                                                              confirmation_required=download_confirmation_required,
                                                              verbose=verbose)

                        unzip_shp_zip(path_to_shp_zip, path_to_extract_dir, layer_names=unavailable_layers,
                                      verbose=verbose)

                    if not layer_names_:
                        layer_names_ = layer_names_temp

                paths_to_layers_shp = [glob.glob(cd(path_to_extract_dir, r"gis_osm_{}_*.shp".format(layer_name)))
                                       for layer_name in layer_names_]
                paths_to_layers_shp = [x for x in paths_to_layers_shp if x]

                shp_data_ = [parse_layer_shp(p, feature_names=feature_names_) for p in paths_to_layers_shp]

                shp_data = dict(zip(layer_names_, shp_data_))

                if pickle_it:
                    save_pickle(shp_data, path_to_shp_pickle, verbose=verbose)

                    if ret_pickle_path:
                        shp_data = shp_data, path_to_shp_pickle

                if os.path.exists(path_to_extract_dir) and rm_extracts:
                    if verbose:
                        print(f"Deleting the extracts \"\\{os.path.relpath(path_to_extract_dir)}\" ", end=" ... ")
                    try:
                        # for f in glob.glob(os.path.join(extract_dir, "gis_osm*")):
                        #     # if layer not in f:
                        #     os.remove(f)
                        shutil.rmtree(path_to_extract_dir)
                        print("Done. ") if verbose else ""
                    except Exception as e:
                        print("Failed. {}".format(e))

                if os.path.isfile(path_to_shp_zip) and rm_shp_zip:
                    remove_subregion_osm_file(path_to_shp_zip, verbose=verbose)

        else:
            shp_data = None

        return shp_data


class BBBikeReader:
    """
    A class representation of a tool for reading `BBBike <https://download.bbbike.org/osm/>`_ data extracts.

    **Example**::

        >>> from pydriosm.reader import BBBikeReader

        >>> bbbike_reader = BBBikeReader()

        >>> print(bbbike_reader.Name)
        BBBike OpenStreetMap data extracts
    """

    def __init__(self):
        """
        Constructor method.
        """
        self.Downloader = BBBikeDownloader()
        self.Name = copy.copy(self.Downloader.Name)
        self.URL = copy.copy(self.Downloader.URL)

    def get_path_to_osm_file(self, subregion_name, osm_file_format, data_dir=None):
        """
        Get absolute path to a BBBike data file (if available) of a specific file format for a geographic region.

        :param subregion_name: name of a geographic region (case-insensitive)
        :type subregion_name: str
        :param osm_file_format: format (file extension) of an OSM data
        :type osm_file_format: str
        :param data_dir: directory where the data file is located/saved; if ``None`` (default), the default directory
        :type data_dir: str or None
        :return: path to the data file
        :rtype: str or None

        **Example**::

            >>> import os
            >>> from pydriosm.reader import BBBikeReader

            >>> bbbike_reader = BBBikeReader()

            >>> sr_name = 'Leeds'
            >>> file_fmt = ".pbf"
            >>> dat_dir = "tests"

            >>> path_to_leeds_pbf = bbbike_reader.Downloader.download_osm_data(
            ...     sr_name, file_fmt, dat_dir, verbose=True, ret_download_path=True)
            Confirm to download .pbf data of the following geographic region(s):
                Leeds
            ? [No]|Yes: yes
            Downloading "Leeds.osm.pbf" to "\tests" ...
            Done.

            >>> path_to_leeds_pbf_ = bbbike_reader.get_path_to_osm_file(sr_name, file_fmt, dat_dir)
            >>> print(os.path.relpath(path_to_leeds_pbf_))
            tests\\Leeds.osm.pbf

            >>> print(path_to_leeds_pbf == path_to_leeds_pbf_)
            True

            >>> # Delete the downloaded PBF data file
            >>> os.remove(path_to_leeds_pbf_)
        """

        _, _, _, path_to_file = self.Downloader.get_valid_download_info(
            subregion_name, osm_file_format=osm_file_format, download_dir=data_dir)

        return path_to_file

    def read_osm_pbf(self, subregion_name, data_dir=None, chunk_size_limit=50,
                     parse_raw_feat=False, transform_geom=False, transform_other_tags=False,
                     update=False, download_confirmation_required=True, pickle_it=False, ret_pickle_path=False,
                     rm_osm_pbf=False, verbose=False):
        """
        Read BBBike PBF data file of a geographic region.

        :param subregion_name: name of a geographic region (case-insensitive)
        :type subregion_name: str
        :param data_dir: directory where the PBF data file is saved; if ``None`` (default), the default directory
        :type data_dir: str or None
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
        :param update: whether to check to update pickle backup (if available), defaults to ``False``
        :type update: bool
        :param download_confirmation_required: whether to ask for confirmation before starting to download a file,
            defaults to ``True``
        :type download_confirmation_required: bool
        :param pickle_it: whether to save the .pbf data as a .pickle file, defaults to ``False``
        :type pickle_it: bool
        :param ret_pickle_path: whether to return an absolute path to the saved pickle file (when ``pickle_it=True``)
        :type ret_pickle_path: bool
        :param rm_osm_pbf: whether to delete the downloaded .osm.pbf file, defaults to ``False``
        :type rm_osm_pbf: bool
        :param verbose: whether to print relevant information in console as the function runs, defaults to ``False``
        :type verbose: bool or int
        :return: dictionary of the .osm.pbf data; when ``pickle_it=True``, return a tuple of the dictionary and
            an absolute path to the pickle file
        :rtype: dict or tuple or None

        **Example**::

            >>> import os
            >>> from pyhelpers.dir import cd
            >>> from pydriosm.reader import BBBikeReader

            >>> bbbike_reader = BBBikeReader()

            >>> sr_name = 'Leeds'
            >>> dat_dir = "tests"

            >>> # (Note that this process may take a long time.)
            >>> leeds_osm_pbf = bbbike_reader.read_osm_pbf(sr_name, dat_dir, parse_raw_feat=True,
            ...                                            transform_geom=True,
            ...                                            transform_other_tags=True,
            ...                                            verbose=True)
            Parsing "\\tests\\Leeds.osm.pbf" ... Done.

            >>> print(list(leeds_osm_pbf.keys()))
            ['points', 'lines', 'multilinestrings', 'multipolygons', 'other_relations']

            >>> leeds_osm_pbf_multipolygons = leeds_osm_pbf['multipolygons']
            >>> print(leeds_osm_pbf_multipolygons.head())
                  id                                        coordinates  ... tourism other_tags
            0  10595  (POLYGON ((-1.5030223 53.6725382, -1.5034495 5...  ...    None       None
            1  10600  (POLYGON ((-1.5116994 53.6764287, -1.5099361 5...  ...    None       None
            2  10601  (POLYGON ((-1.5142403 53.6710831, -1.5143686 5...  ...    None       None
            3  10612  (POLYGON ((-1.5129341 53.6704885, -1.5131883 5...  ...    None       None
            4  10776  (POLYGON ((-1.5523801 53.7029081, -1.5522831 5...  ...    None       None
            [5 rows x 27 columns]

            >>> # Delete the downloaded PBF data file
            >>> os.remove(cd(data_dir, "Leeds.osm.pbf"))
        """

        assert isinstance(chunk_size_limit, int) or chunk_size_limit is None

        osm_file_format = ".osm.pbf"

        path_to_osm_pbf = self.get_path_to_osm_file(subregion_name, osm_file_format, data_dir)

        path_to_pickle = path_to_osm_pbf.replace(".osm.pbf", "-pbf.pickle" if parse_raw_feat else "-raw.pickle")
        if os.path.isfile(path_to_pickle) and not update:
            osm_pbf_data = load_pickle(path_to_pickle)

            if ret_pickle_path:
                osm_pbf_data = osm_pbf_data, path_to_pickle

        else:
            if not os.path.isfile(path_to_osm_pbf):
                path_to_osm_pbf = self.Downloader.download_osm_data(
                    subregion_name, osm_file_format=osm_file_format, download_dir=data_dir,
                    confirmation_required=download_confirmation_required, verbose=verbose, ret_download_path=True)

            if verbose and parse_raw_feat:
                print("Parsing \"\\{}\"".format(os.path.relpath(path_to_osm_pbf)), end=" ... ")

            try:
                number_of_chunks = get_number_of_chunks(path_to_osm_pbf, chunk_size_limit=chunk_size_limit)

                osm_pbf_data = parse_osm_pbf(path_to_osm_pbf, number_of_chunks=number_of_chunks,
                                             parse_raw_feat=parse_raw_feat, transform_geom=transform_geom,
                                             transform_other_tags=transform_other_tags)

                print("Done. ") if verbose and parse_raw_feat else ""

                if pickle_it:
                    save_pickle(osm_pbf_data, path_to_pickle, verbose=verbose)

                    if ret_pickle_path:
                        osm_pbf_data = osm_pbf_data, path_to_pickle

                if rm_osm_pbf:
                    remove_subregion_osm_file(path_to_osm_pbf, verbose=verbose)

            except Exception as e:
                print("Failed. {}".format(e))
                osm_pbf_data = None

        return osm_pbf_data

    def read_shp_zip(self, subregion_name, layer_names=None, feature_names=None, data_dir=None, update=False,
                     download_confirmation_required=True, pickle_it=False, ret_pickle_path=False, rm_extracts=False,
                     rm_shp_zip=False, verbose=False):
        """
        Read BBBike shapefile of a geographic region.

        :param subregion_name: name of a geographic region (case-insensitive)
        :type subregion_name: str
        :param layer_names: name of a .shp layer, e.g. 'railways', or names of multiple layers;;
            if ``None`` (default), all available layers
        :type layer_names: str or list or None
        :param feature_names: name of a feature, e.g. 'rail', or names of multiple features;
            if ``None`` (default), all available features
        :type feature_names: str or list or None
        :param data_dir: directory where the .shp.zip data file is located/saved;
            if ``None``, the default directory
        :type data_dir: str or None
        :param update: whether to check to update pickle backup (if available), defaults to ``False``
        :type update: bool
        :param download_confirmation_required: whether to ask for confirmation before starting to download a file,
            defaults to ``True``
        :type download_confirmation_required: bool
        :param pickle_it: whether to save the .shp data as a .pickle file, defaults to ``False``
        :type pickle_it: bool
        :param ret_pickle_path: whether to return an absolute path to the saved pickle file (when ``pickle_it=True``)
        :type ret_pickle_path: bool
        :param rm_extracts: whether to delete extracted files from the .shp.zip file, defaults to ``False``
        :type rm_extracts: bool
        :param rm_shp_zip: whether to delete the downloaded .shp.zip file, defaults to ``False``
        :type rm_shp_zip: bool
        :param verbose: whether to print relevant information in console as the function runs, defaults to ``False``
        :type verbose: bool or int
        :return: dictionary of the shapefile data, with keys and values being layer names and
            tabular data (in the format of `geopandas.GeoDataFrame`_), respectively;
            when ``pickle_it=True``, return a tuple of the dictionary and an absolute path to the pickle file
        :rtype: dict or tuple or None

        .. _`geopandas.GeoDataFrame`: https://geopandas.org/reference.html#geodataframe

        **Examples**::

            >>> import os
            >>> from pydriosm.reader import BBBikeReader

            >>> bbbike_reader = BBBikeReader()

            >>> sr_name = 'Birmingham'
            >>> dat_dir = "tests"

            >>> birmingham_shp = bbbike_reader.read_shp_zip(sr_name, data_dir=dat_dir, verbose=True)
            Confirm to download .shp.zip data of the following geographic region(s):
                Birmingham
            ? [No]|Yes: yes
            Downloading "Birmingham.osm.shp.zip" to "\\tests" ...
            Done.
            Extracting all of "Birmingham.osm.shp.zip" to "\\tests" ...
            In progress ... Done.
            Parsing "\\tests\\Birmingham-shp\\shape" ... Done.

            >>> print(list(birmingham_shp.keys()))
            ['buildings', 'landuse', 'natural', 'places', 'points', 'pofw', 'pois', 'railways']

            >>> birmingham_railways_shp = birmingham_shp['railways']
            >>> print(birmingham_railways_shp.head())
                osm_id  ...                                           geometry
            0      740  ...  LINESTRING (-1.81789 52.57010, -1.81793 52.569...
            1     2148  ...  LINESTRING (-1.87319 52.50555, -1.87271 52.505...
            2  2950000  ...  LINESTRING (-1.87941 52.48138, -1.87960 52.481...
            3  3491845  ...  LINESTRING (-1.74060 52.51858, -1.73942 52.518...
            4  3981454  ...  LINESTRING (-1.77475 52.52284, -1.77449 52.522...
            [5 rows x 4 columns]

            >>> layer_name = 'roads'
            >>> feat_name = None

            >>> birmingham_roads_shp = bbbike_reader.read_shp_zip(sr_name, layer_name, feat_name,
            ...                                                   dat_dir, rm_extracts=True,
            ...                                                   verbose=True)
            Parsing "\\tests\\Birmingham-shp\\shape\\roads.shp" ... Done.
            Deleting the extracts "\\tests\\Birmingham-shp" ... Done.


            >>> print(list(birmingham_roads_shp.keys()))
            ['roads']

            >>> print(birmingham_roads_shp['roads'].head())
               osm_id  ...                                           geometry
            0      37  ...  LINESTRING (-1.82675 52.55580, -1.82646 52.555...
            1      38  ...  LINESTRING (-1.81541 52.54785, -1.81475 52.547...
            2      41  ...  LINESTRING (-1.81931 52.55219, -1.81860 52.552...
            3      42  ...  LINESTRING (-1.82492 52.55504, -1.82309 52.556...
            4      45  ...  LINESTRING (-1.82121 52.55389, -1.82056 52.55432)
            [5 rows x 8 columns]

            >>> lyr_names = ['railways', 'waterways']
            >>> feat_names = ['rail', 'canal']

            >>> bham_rw_rc_shp = bbbike_reader.read_shp_zip(sr_name, lyr_names, feat_names,
            ...                                             dat_dir, rm_extracts=True,
            ...                                             rm_shp_zip=True, verbose=True)
            Extracting from "Birmingham.osm.shp.zip" the following layer(s):
                'railways'
                'waterways'
            to "\\tests" ...
            In progress ... Done.
            Parsing "\\tests\\Birmingham-shp\\shape" ... Done.
            Deleting the extracts "\\tests\\Birmingham-shp" ... Done.
            Deleting "tests\\Birmingham.osm.shp.zip" ... Done.

            >>> print(list(bham_rw_rc_shp.keys()))
            ['railways', 'waterways']

            >>> bham_rw_rc_shp_railways = bham_rw_rc_shp['railways']
            >>> print(bham_rw_rc_shp_railways[['fclass', 'name']].head())
              fclass                             name
            0   rail                  Cross-City Line
            1   rail                  Cross-City Line
            2   rail                             None
            3   rail  Birmingham to Peterborough Line
            4   rail                     Freight Line

            >>> bham_rw_rc_shp_waterways = bham_rw_rc_shp['waterways']
            >>> print(bham_rw_rc_shp_waterways[['fclass', 'name']].head())
               fclass                                              name
            2   canal                      Birmingham and Fazeley Canal
            8   canal                      Birmingham and Fazeley Canal
            9   canal  Birmingham Old Line Canal Navigations - Rotton P
            10  canal                               Oozells Street Loop
            11  canal                      Worcester & Birmingham Canal
        """

        osm_file_format = ".shp.zip"

        path_to_shp_zip = self.get_path_to_osm_file(subregion_name, osm_file_format, data_dir)

        path_to_extract_dir, shp_zip_filename = os.path.split(path_to_shp_zip)
        path_to_extract_dir_ = os.path.splitext(path_to_shp_zip)[0].replace(".osm.", "-")

        if layer_names:
            layer_names_ = [layer_names] if isinstance(layer_names, str) else layer_names.copy()
        else:
            layer_names_ = []  # get_valid_shp_layer_names()

        if feature_names:
            feature_names_ = [feature_names] if isinstance(feature_names, str) else feature_names.copy()
        else:
            feature_names_ = []

        if layer_names_:  # layer is not None
            # Make a local path for saving a pickle file for .shp data
            filename_ = shp_zip_filename.replace(".osm.shp.zip", "").lower()
            sub_fname = "-".join(x for x in [filename_] + layer_names_ + (feature_names_ if feature_names_ else [])
                                 if x)
            path_to_shp_pickle = cd(os.path.dirname(path_to_extract_dir_), sub_fname + "-shp.pickle")
        else:
            path_to_shp_pickle = path_to_extract_dir_ + ".pickle"

        if os.path.isfile(path_to_shp_pickle) and not update:
            shp_data = load_pickle(path_to_shp_pickle)

            if ret_pickle_path:
                shp_data = shp_data, path_to_shp_pickle

        else:
            try:
                # Download the requested OSM file urlretrieve(download_url, file_path)
                if not os.path.exists(path_to_extract_dir_):
                    if not os.path.exists(path_to_shp_zip):
                        self.Downloader.download_osm_data(subregion_name, osm_file_format=osm_file_format,
                                                          download_dir=data_dir, update=update,
                                                          confirmation_required=download_confirmation_required,
                                                          verbose=verbose)

                    unzip_shp_zip(path_to_shp_zip, path_to_extract_dir, layer_names=layer_names_, verbose=verbose)

                    if not layer_names_:
                        layer_names_ = list(set(
                            [x.rsplit(".", 1)[0] for x in os.listdir(cd(path_to_extract_dir_, "shape"))]))

                else:
                    unavailable_layers = []

                    layer_names_temp_ = [x.rsplit(".", 1)[0] for x in os.listdir(cd(path_to_extract_dir_, "shape"))]
                    layer_names_temp = list(set(layer_names_ + layer_names_temp_))

                    for lyr_name in layer_names_temp:
                        shp_filename = cd(path_to_extract_dir_, "shape", f"{lyr_name}.shp")
                        if not os.path.isfile(shp_filename):
                            unavailable_layers.append(lyr_name)

                    if unavailable_layers:
                        if not os.path.exists(path_to_shp_zip):
                            self.Downloader.download_osm_data(subregion_name, osm_file_format=osm_file_format,
                                                              download_dir=data_dir, update=update,
                                                              confirmation_required=download_confirmation_required,
                                                              verbose=verbose)

                        unzip_shp_zip(path_to_shp_zip, path_to_extract_dir, layer_names=unavailable_layers,
                                      verbose=verbose)

                    if not layer_names_:
                        layer_names_ = layer_names_temp

                paths_to_layers_shp = [
                    glob.glob(cd(path_to_extract_dir_, "shape", f"{lyr_name}.shp")) for lyr_name in layer_names_]
                paths_to_layers_shp = [x for x in paths_to_layers_shp if x]

                if verbose:
                    files_dir = os.path.relpath(os.path.commonpath(itertools.chain.from_iterable(paths_to_layers_shp)))
                    print("Parsing \"\\{}\"".format(files_dir), end=" ... ")

                shp_data_ = [parse_layer_shp(p, feature_names=feature_names_) for p in paths_to_layers_shp]

                shp_data = dict(zip(layer_names_, shp_data_))

                print("Done. ") if verbose else ""

                if pickle_it:
                    save_pickle(shp_data, path_to_shp_pickle, verbose=verbose)

                    if ret_pickle_path:
                        shp_data = shp_data, path_to_shp_pickle

                if rm_extracts and os.path.exists(path_to_extract_dir_):
                    if verbose:
                        print(f"Deleting the extracts \"\\{os.path.relpath(path_to_extract_dir_)}\"", end=" ... ")
                    try:
                        # for f in glob.glob(os.path.join(extract_dir, "gis_osm*")):
                        #     # if layer not in f:
                        #     os.remove(f)
                        shutil.rmtree(path_to_extract_dir_)
                        print("Done. ") if verbose else ""
                    except Exception as e:
                        print("Failed. {}".format(e))

                if rm_shp_zip and os.path.isfile(path_to_shp_zip):
                    remove_subregion_osm_file(path_to_shp_zip, verbose=verbose)

            except Exception as e:
                print("Failed. {}".format(e))
                shp_data = None

        return shp_data

    def read_csv_xz(self, subregion_name, data_dir=None, download_confirmation_required=True, verbose=False):
        """
        Read compressed CSV (.csv.xz) data file of a BBBike geographic region.

        :param subregion_name: name of a geographic region (case-insensitive)
        :type subregion_name: str
        :param data_dir: directory where the .csv.xz data file is located/saved;
            if ``None`` (default), the default directory
        :type data_dir: str or None
        :param download_confirmation_required: whether to ask for confirmation before starting to download a file,
            defaults to ``True``
        :type download_confirmation_required: bool
        :param verbose: whether to print relevant information in console as the function runs, defaults to ``False``
        :type verbose: bool or int
        :return: tabular data of the .csv.xz file
        :rtype: pandas.DataFrame or None

        .. _pydriosm-BBBikeReader-read_csv_xz:

        **Example**::

            >>> import os
            >>> from pyhelpers.dir import cd
            >>> from pydriosm.reader import BBBikeReader

            >>> bbbike_reader = BBBikeReader()

            >>> sr_name = 'Leeds'
            >>> dat_dir = "tests"

            >>> leeds_csv_xz = bbbike_reader.read_csv_xz(sr_name, dat_dir, verbose=True)
            Confirm to download .csv.xz data of the following geographic region(s):
                Leeds
            ? [No]|Yes: yes
            Downloading "Leeds.osm.csv.xz" to "\\tests" ...
            Done.
            Parsing "\\tests\\Leeds.osm.csv.xz" ... Done.

            >>> print(leeds_csv_xz.head())
               type      id feature
            0  node  154915    None
            1  node  154916    None
            2  node  154921    None
            3  node  154922    None
            4  node  154923    None

            >>> # Delete the downloaded .csv.xz data file
            >>> os.remove(cd(dat_dir, "Leeds.osm.csv.xz"))
        """

        subregion_name_ = self.Downloader.validate_input_subregion_name(subregion_name)
        osm_file_format = ".csv.xz"

        path_to_csv_xz = self.get_path_to_osm_file(subregion_name_, osm_file_format, data_dir)

        if not os.path.isfile(path_to_csv_xz):
            path_to_csv_xz = self.Downloader.download_osm_data(subregion_name_, osm_file_format=osm_file_format,
                                                               download_dir=data_dir,
                                                               confirmation_required=download_confirmation_required,
                                                               verbose=verbose, ret_download_path=True)

        if verbose:
            print("Parsing \"\\{}\"".format(os.path.relpath(path_to_csv_xz)), end=" ... ")
        try:
            csv_xz_data = parse_csv_xz(path_to_csv_xz)
            print("Done. ") if verbose else ""

        except Exception as e:
            print("Failed. {}".format(e))
            csv_xz_data = None

        return csv_xz_data

    def read_geojson_xz(self, subregion_name, data_dir=None, fmt_geom=False, download_confirmation_required=True,
                        verbose=False):
        """
        Read BBBike .geojson.xz file of a subregion.

        :param subregion_name: name of a region/subregion (case-insensitive)
        :type subregion_name: str
        :param data_dir: directory where the .geojson.xz data file is located/saved;
            if ``None`` (default), the default directory
        :type data_dir: str or None
        :param fmt_geom: whether to reformat coordinates into a geometric object, defaults to ``False``
        :type fmt_geom: bool
        :param download_confirmation_required: whether to ask for confirmation before starting to download a file,
            defaults to ``True``
        :type download_confirmation_required: bool
        :param verbose: whether to print relevant information in console as the function runs, defaults to ``False``
        :type verbose: bool or int
        :return: tabular data of the .csv.xz file
        :rtype: pandas.DataFrame or None

        .. _pydriosm-BBBikeReader-read_geojson_xz:

        **Examples**::

            >>> import os
            >>> from pyhelpers.dir import cd
            >>> from pydriosm.reader import BBBikeReader

            >>> bbbike_reader = BBBikeReader()

            >>> sr_name = 'Leeds'
            >>> dat_dir = "tests"

            >>> leeds_geojson_xz = bbbike_reader.read_geojson_xz(sr_name, dat_dir, verbose=True)
            Confirm to download .geojson.xz data of the following geographic region(s):
                Leeds
            ? [No]|Yes: yes
            Downloading "Leeds.osm.geojson.xz" to "\\tests" ...
            Done.
            Parsing "\\tests\\Leeds.osm.geojson.xz" ... Done.

            >>> print(leeds_geojson_xz.head())
              feature_name  ...                                         properties
            0      Feature  ...  {'ref': '40', 'name': 'Flushdyke', 'highway': ...
            1      Feature  ...  {'ref': '44', 'name': 'Bramham', 'highway': 'm...
            2      Feature  ...  {'ref': '43', 'name': 'Belle Isle', 'highway':...
            3      Feature  ...  {'ref': '42', 'name': 'Lofthouse', 'highway': ...
            4      Feature  ...  {'ref': '42', 'name': 'Lofthouse', 'highway': ...
            [5 rows x 4 columns]

            >>> print(leeds_geojson_xz[['coordinates']].head())
                            coordinates
            0  [-1.5558097, 53.6873431]
            1     [-1.34293, 53.844618]
            2   [-1.517335, 53.7499667]
            3   [-1.514124, 53.7416937]
            4   [-1.516511, 53.7256632]

            >>> leeds_geojson_xz_ = bbbike_reader.read_geojson_xz(sr_name, dat_dir, fmt_geom=True)

            >>> print(leeds_geojson_xz_[['coordinates']].head())
                                 coordinates
            0  POINT (-1.5558097 53.6873431)
            1     POINT (-1.34293 53.844618)
            2   POINT (-1.517335 53.7499667)
            3   POINT (-1.514124 53.7416937)
            4   POINT (-1.516511 53.7256632)

            >>> # Delete the downloaded .csv.xz data file
            >>> os.remove(cd(dat_dir, "Leeds.osm.geojson.xz"))
        """

        subregion_name_ = self.Downloader.validate_input_subregion_name(subregion_name)
        osm_file_format = ".geojson.xz"

        path_to_geojson_xz = self.get_path_to_osm_file(subregion_name_, osm_file_format, data_dir)

        if not os.path.isfile(path_to_geojson_xz):
            path_to_geojson_xz = self.Downloader.download_osm_data(subregion_name_, osm_file_format=osm_file_format,
                                                                   download_dir=data_dir,
                                                                   confirmation_required=download_confirmation_required,
                                                                   verbose=verbose, ret_download_path=True)

        if verbose:
            print("Parsing \"\\{}\"".format(os.path.relpath(path_to_geojson_xz)), end=" ... ")
        try:
            geojson_xz_data = parse_geojson_xz(path_to_geojson_xz, fmt_geom=fmt_geom)

            print("Done. ") if verbose else ""

        except Exception as e:
            print("Failed. {}".format(e))
            geojson_xz_data = None

        return geojson_xz_data
