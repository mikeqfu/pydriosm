"""
Parsing/reading OSM data extracts.
"""

import collections
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

from .downloader import *
from .utils import append_fclass_to_shp_filename, find_shp_layer_name, get_number_of_chunks, \
    get_osm_geom_shapely_object_dict, get_pbf_layer_feat_types_dict, get_valid_shp_layer_names, \
    remove_subregion_osm_file


def get_osm_pbf_layer_idx_names(path_to_osm_pbf):
    """
    Get names of all layers contained in a PBF file for a given subregion.

    :param path_to_osm_pbf: full path to a .osm.pbf file
    :type path_to_osm_pbf: str
    :return: name and index of each layer of the .osm.pbf file
    :rtype: dict

    **Example**::

        import os
        from pydriosm import GeoFabrikDownloader, get_osm_pbf_layer_idx_names

        geofabrik_downloader = GeoFabrikDownloader()

        subregion_name = 'rutland'
        osm_file_format = ".osm.pbf"
        download_dir = "tests"

        path_to_rutland_pbf = geofabrik_downloader.download_subregion_osm_file(
            subregion_name, osm_file_format, download_dir, verbose=True, ret_download_path=True)
        # Confirm to download .osm.pbf data of the following (sub)region(s):
        # 	rutland
        # ? [No]|Yes: yes
        # Downloading "rutland-latest.osm.pbf" to "tests" ...
        # Done.

        layer_idx_names = get_osm_pbf_layer_idx_names(path_to_rutland_pbf)

        print(layer_idx_names)
        # {0: 'points', 1: 'lines', 2: 'multilinestrings', 3: 'multipolygons', 4: 'other_relations'}

        os.remove(path_to_rutland_pbf)
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
        import os
        import pandas as pd
        from pyhelpers.dir import cd
        from pydriosm.reader import GeoFabrikDownloader, parse_osm_pbf_layer

        geofabrik_downloader = GeoFabrikDownloader()

        subregion_name = 'rutland'
        osm_file_format = ".pbf"
        download_dir = "tests"

        path_to_rutland_pbf = geofabrik_downloader.download_subregion_osm_file(
            subregion_name, osm_file_format, download_dir, verbose=True, ret_download_path=True)
        # Confirm to download .osm.pbf data of the following (sub)region(s):
        # 	rutland
        # ? [No]|Yes: yes
        # Downloading "rutland-latest.osm.pbf" to "tests" ...
        # Done.

        raw_rutland_pbf = ogr.Open(path_to_rutland_pbf)

        geo_typ = 'points'

        rutland_points_ = raw_rutland_pbf.GetLayerByName(geo_typ)
        rutland_points = pd.DataFrame(feat.ExportToJson(as_object=True) for feat in rutland_points_)

        rutland_points_parsed = parse_osm_pbf_layer(
            rutland_points, geo_typ, transform_geom=False, transform_other_tags=False)

        print(rutland_points_parsed.head())
        #          id               coordinates  ... man_made                    other_tags
        # 0    488432  [-0.5134241, 52.6555853]  ...     None               "odbl"=>"clean"
        # 1    488658  [-0.5313354, 52.6737716]  ...     None                          None
        # 2  13883868  [-0.7229332, 52.5889864]  ...     None                          None
        # 3  14049101  [-0.7249922, 52.6748223]  ...     None  "traffic_calming"=>"cushion"
        # 4  14558402  [-0.7266686, 52.6695051]  ...     None      "direction"=>"clockwise"
        #
        # [5 rows x 12 columns]

        rutland_points_parsed = parse_osm_pbf_layer(
            rutland_points, geo_typ, transform_geom=True, transform_other_tags=False)

        print(rutland_points_parsed.head())
        #          id  ...                    other_tags
        # 0    488432  ...               "odbl"=>"clean"
        # 1    488658  ...                          None
        # 2  13883868  ...                          None
        # 3  14049101  ...  "traffic_calming"=>"cushion"
        # 4  14558402  ...      "direction"=>"clockwise"
        #
        # [5 rows x 12 columns]

        rutland_points_parsed = parse_osm_pbf_layer(
            rutland_points, geo_typ, transform_geom=True, transform_other_tags=True)

        print(rutland_points_parsed.head())
        #          id  ...                      other_tags
        # 0    488432  ...               {'odbl': 'clean'}
        # 1    488658  ...                            None
        # 2  13883868  ...                            None
        # 3  14049101  ...  {'traffic_calming': 'cushion'}
        # 4  14558402  ...      {'direction': 'clockwise'}
        #
        # [5 rows x 12 columns]

        raw_rutland_pbf.Release()

        os.remove(path_to_rutland_pbf)
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
    :type number_of_chunks: int or None
    :param parse_raw_feat: whether to parse each feature in the raw data
    :type parse_raw_feat: bool
    :param transform_geom: whether to transform a single coordinate (or a collection of coordinates) into a geometric
        object
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

        import os
        from pydriosm.reader import GeoFabrikDownloader, parse_osm_pbf

        geofabrik_downloader = GeoFabrikDownloader()

        subregion_name = 'rutland'
        osm_file_format = ".osm.pbf"
        download_dir = "tests"

        path_to_rutland_pbf = geofabrik_downloader.download_subregion_osm_file(
            subregion_name, osm_file_format, download_dir, ret_download_path=True)
        # Confirm to download .osm.pbf data of the following (sub)region(s):
        # 	rutland
        # ? [No]|Yes: yes

        chunks_no = 50
        parsed = True
        transform_geom = False
        fmt_multi_geom = False
        transform_other_tags = False

        rutland_pbf_data = parse_osm_pbf(path_to_rutland_pbf, chunks_no, transform_geom,
                                         fmt_multi_geom, transform_other_tags)

        print(list(rutland_pbf_data.keys()))
        # ['points', 'lines', 'multilinestrings', 'multipolygons', 'other_relations']

        print(rutland_pbf_data['points'].head())
        #                                               points
        # 0  {"type": "Feature", "geometry": {"type": "Poin...
        # 1  {"type": "Feature", "geometry": {"type": "Poin...
        # 2  {"type": "Feature", "geometry": {"type": "Poin...
        # 3  {"type": "Feature", "geometry": {"type": "Poin...
        # 4  {"type": "Feature", "geometry": {"type": "Poin...

        os.remove(path_to_rutland_pbf)
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
                    lyr_dat.columns = [layer_name]

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

    :param path_to_shp_zip: full path to a .shp.zip file
    :type path_to_shp_zip: str
    :param path_to_extract_dir: full path to a directory where extracted files will be saved;
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

        import os
        from pyhelpers.dir import cd, rm_dir
        from pydriosm.reader import GeoFabrikDownloader, unzip_shp_zip

        geofabrik_downloader = GeoFabrikDownloader()

        subregion_name = 'rutland'
        osm_file_format = ".shp"
        download_dir = "tests"

        path_to_rutland_shp_zip = geofabrik_downloader.download_subregion_osm_file(
            subregion_name, osm_file_format, download_dir, verbose=True, ret_download_path=True)
        # Confirm to download .shp.zip data of the following (sub)region(s):
        # 	rutland
        # ? [No]|Yes: yes
        # Downloading "rutland-latest-free.shp.zip" to "tests" ...
        # Done.

        layer_names = 'railways'

        unzip_shp_zip(path_to_rutland_shp_zip, layer_names=layer_names, verbose=True)
        # Extracting from "rutland-latest-free.shp.zip" the following layer(s):
        # 	'railways'
        # to "tests\\rutland-latest-free-shp" ...
        # In progress ... Done.

        layer_names = None

        path_to_extract_dir = unzip_shp_zip(path_to_rutland_shp_zip, verbose=True,
                                            ret_extract_dir=True)
        # Extracting all of "rutland-latest-free.shp.zip" to "tests\\rutland-latest-free-shp" ...
        # In progress ... Done.

        layer_names = ['railways', 'transport', 'traffic']

        paths_to_extract_dirs = unzip_shp_zip(path_to_rutland_shp_zip, layer_names=layer_names,
                                              clustered=True, verbose=2, ret_extract_dir=True)
        # Extracting from "rutland-latest-free.shp.zip" the following layer(s):
        # 	'railways'
        # 	'transport'
        # 	'traffic'
        # to "tests\\rutland-latest-free-shp" ...
        # In progress ... Done.
        # Clustering the layer data ...
        # 	railways ...
        # 	transport ...
        # 	traffic ...
        # 	transport_a ...
        # 	traffic_a ...
        # Done.

        print(paths_to_extract_dirs)
        # ['<cwd>\\tests\\rutland-latest-free-shp\\transport',
        #  '<cwd>\\tests\\rutland-latest-free-shp\\traffic',
        #  '<cwd>\\tests\\rutland-latest-free-shp\\railways']

        rm_dir(path_to_extract_dir)
        # "<cwd>\\tests\\rutland-latest-free-shp" is not empty. Confirmed to remove the directory?
        # [No]|Yes: yes

        os.remove(path_to_rutland_shp_zip)
    """

    extract_dir = path_to_extract_dir if path_to_extract_dir \
        else os.path.splitext(path_to_shp_zip)[0].replace(".", "-")

    if not layer_names:
        layer_names_ = layer_names
        if verbose:
            print("Extracting all of \"{}\" to \"{}\" ... ".format(
                os.path.basename(path_to_shp_zip), os.path.relpath(extract_dir)))
    else:
        layer_names_ = [layer_names] if isinstance(layer_names, str) else layer_names.copy()
        if verbose:
            print("Extracting from \"{}\" the following layer(s):".format(os.path.basename(path_to_shp_zip)))
            print("\t{}".format("\n\t".join([f"'{x}'" for x in layer_names_])))
            print("to \"{}\" ... ".format(os.path.relpath(extract_dir)))

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


def parse_shp(path_to_shp, method='geopandas', **kwargs):
    """
    Read a shapefile format (.shp) file.

    :param path_to_shp: full path to a .shp data file
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

        from pyhelpers.dir import cd, rm_dir
        from pydriosm.reader import GeoFabrikDownloader, unzip_shp_zip, parse_shp

        geofabrik_downloader = GeoFabrikDownloader()

        subregion_name = 'rutland'
        osm_file_format = ".shp"
        download_dir = "tests"

        path_to_rutland_shp_zip = geofabrik_downloader.download_subregion_osm_file(
            subregion_name, osm_file_format, download_dir, ret_download_path=True)
        # Confirm to download .shp.zip data of the following (sub)region(s):
        # 	rutland
        # ? [No]|Yes: yes

        rutland_shp_dir = unzip_shp_zip(path_to_rutland_shp_zip, ret_extract_dir=True)

        path_to_railways_shp = cd(rutland_shp_dir, "gis_osm_railways_free_1.shp")

        method = 'geopandas'  # or 'gpd'
        rutland_railways_shp = parse_shp(path_to_railways_shp, method)  # geopandas.GeoDataFrame

        print(rutland_railways_shp.head())
        #     osm_id  code  ... tunnel                                           geometry
        # 0  2162114  6101  ...      F  LINESTRING (-0.45281 52.69934, -0.45189 52.698...
        # 1  3681043  6101  ...      F  LINESTRING (-0.65312 52.57308, -0.65318 52.572...
        # 2  3693985  6101  ...      F  LINESTRING (-0.73234 52.67821, -0.73191 52.678...
        # 3  3693986  6101  ...      F  LINESTRING (-0.61731 52.61323, -0.62419 52.614...
        # 4  4806329  6101  ...      F  LINESTRING (-0.45769 52.70352, -0.45654 52.702...
        #
        # [5 rows x 8 columns]

        method = 'pyshp'  # (Or anything except 'geopandas')
        rutland_railways_shp = parse_shp(path_to_railways_shp, method)  # pandas.DataFrame

        print(rutland_railways_shp.head())
        #     osm_id  code  ...                                             coords shape_type
        # 0  2162114  6101  ...  [(-0.4528083, 52.6993402), (-0.4518933, 52.698...          3
        # 1  3681043  6101  ...  [(-0.6531215, 52.5730787), (-0.6531793, 52.572...          3
        # 2  3693985  6101  ...  [(-0.7323403, 52.6782102), (-0.7319059, 52.678...          3
        # 3  3693986  6101  ...  [(-0.6173072, 52.6132317), (-0.6241869, 52.614...          3
        # 4  4806329  6101  ...  [(-0.4576926, 52.7035194), (-0.4565358, 52.702...          3
        #
        # [5 rows x 9 columns]

        rm_dir(path_to_extract_dir)
        # "<cwd>\\tests\\rutland-latest-free-shp" is not empty. Confirmed to remove the directory?
        # [No]|Yes: yes

        os.remove(path_to_rutland_shp_zip)
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


def specify_shp_crs():
    """
    Specify the coordinate reference system (CRS) for saving shapefile format data.

    :return: default settings of CRS
    :rtype: dict

    **Example**::

        from pydriosm.reader import specify_shp_crs

        crs = specify_shp_crs()

        print(crs)
        # {'no_defs': True, 'ellps': 'WGS84', 'datum': 'WGS84', 'proj': 'longlat'}
    """

    crs = {'no_defs': True, 'ellps': 'WGS84', 'datum': 'WGS84', 'proj': 'longlat'}

    return crs


def parse_shp_layer(path_to_layer_shp, feature_names=None, crs=None, save_fclass_shp=False, driver='ESRI Shapefile',
                    ret_path_to_fclass_shp=False, **kwargs):
    """
    Parse a layer of OSM .shp data file.

    :param path_to_layer_shp: full paths to one or multiple .shp data files (of the one layer)
    :type path_to_layer_shp: str or list
    :param feature_names: class name (or names) of a feature (or features), defaults to ``None``
    :type feature_names: str or list or None
    :param crs: specification of coordinate reference system; if ``None`` (default),
        check :py:func:`specify_shp_crs()<pydriosm.reader.specify_shp_crs>`
    :type crs: dict
    :param save_fclass_shp: (when ``fclass`` is not ``None``) whether to save the data of the ``fclass`` as shapefile,
        defaults to ``False``
    :type save_fclass_shp: bool
    :param driver: the OGR format driver, defaults to ``'ESRI Shapefile'``;
        see also the ``driver`` parameter of `geopandas.GeoDataFrame.to_file()`_
    :type driver: str
    :param ret_path_to_fclass_shp: (when ``save_fclass_shp`` is ``True``) whether to return the path to
        the saved data of ``fclass``, defaults to ``False``
    :type ret_path_to_fclass_shp: bool
    :param kwargs: optional parameters of `geopandas.read_file()`_
    :return: shapefile data
    :rtype: geopandas.GeoDataFrame

    .. _`geopandas.read_file()`: https://geopandas.org/reference/geopandas.read_file.html
    .. _`geopandas.GeoDataFrame.to_file()`: https://geopandas.org/reference.html#geopandas.GeoDataFrame.to_file

    **Examples**::

        from pyhelpers.dir import cd, rm_dir
        from pydriosm.reader import GeoFabrikDownloader, parse_shp_layer, unzip_shp_zip

        geofabrik_downloader = GeoFabrikDownloader()

        subregion_name = 'rutland'

        path_to_shp_zip = geofabrik_downloader.download_subregion_osm_file(
            subregion_name, osm_file_format=".shp", download_dir="tests", ret_download_path=True,
            confirmation_required=False)

        rutland_shp_dir = unzip_shp_zip(path_to_rutland_shp_zip, ret_extract_dir=True)

        path_to_railways_shp = cd(rutland_shp_dir, "gis_osm_railways_free_1.shp")

        rutland_railways_shp = parse_shp_layer(path_to_railways_shp)

        print(rutland_railways_shp.head())
        #     osm_id  code  ... tunnel                                           geometry
        # 0  2162114  6101  ...      F  LINESTRING (-0.45281 52.69934, -0.45189 52.698...
        # 1  3681043  6101  ...      F  LINESTRING (-0.65312 52.57308, -0.65318 52.572...
        # 2  3693985  6101  ...      F  LINESTRING (-0.73234 52.67821, -0.73191 52.678...
        # 3  3693986  6101  ...      F  LINESTRING (-0.61731 52.61323, -0.62419 52.614...
        # 4  4806329  6101  ...      F  LINESTRING (-0.45769 52.70352, -0.45654 52.702...
        #
        # [5 rows x 8 columns]

        rutland_railways_rail, path_to_rutland_railways_rail = parse_shp_layer(
            path_to_railways_shp, feature_names='rail', save_fclass_shp=True,
            ret_path_to_fclass_shp=True)

        print(rutland_railways_rail.head())
        #     osm_id  code  ... tunnel                                           geometry
        # 0  2162114  6101  ...      F  LINESTRING (-0.45281 52.69934, -0.45189 52.698...
        # 1  3681043  6101  ...      F  LINESTRING (-0.65312 52.57308, -0.65318 52.572...
        # 2  3693985  6101  ...      F  LINESTRING (-0.73234 52.67821, -0.73191 52.678...
        # 3  3693986  6101  ...      F  LINESTRING (-0.61731 52.61323, -0.62419 52.614...
        # 4  4806329  6101  ...      F  LINESTRING (-0.45769 52.70352, -0.45654 52.702...
        #
        # [5 rows x 8 columns]

        print(path_to_rutland_railways_rail)
        # <cwd>\\tests\\rutland-latest-free-shp\\railways\\gis_osm_railways_free_1_rail.shp

        rm_dir(rutland_shp_dir)
        # "<cwd>\\tests\\rutland-latest-free-shp" is not empty. Confirmed to remove the directory?
        # [No]|Yes: yes

        os.remove(path_to_rutland_shp_zip)
    """

    path_to_lyr_shp = [path_to_layer_shp] if isinstance(path_to_layer_shp, str) else copy.copy(path_to_layer_shp)

    if len(path_to_lyr_shp) == 0:
        shp_data = None

    else:
        if crs is None:
            crs = specify_shp_crs()

        if len(path_to_lyr_shp) == 1:
            path_to_lyr_shp_ = path_to_lyr_shp[0]
            shp_data = gpd.read_file(path_to_lyr_shp_, **kwargs)  # gpd.GeoDataFrame(read_shp_file(path_to_shp))
        else:
            shp_data = [gpd.read_file(path_to_lyr_shp_, **kwargs) for path_to_lyr_shp_ in path_to_lyr_shp]
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


def parse_csv_xz(path_to_csv_xz, col_names=None):
    """
    Parse a .csv.xz file.

    :param path_to_csv_xz: full path to a .csv.xz file
    :type path_to_csv_xz: str
    :param col_names: column names of .csv.xz data, defaults to ``None``
    :type col_names: list or None
    :return: tabular data of the .csv.xz file
    :rtype: pandas.DataFrame

    See the example for :ref:`BBBikeReader.read_csv_xz()<pydriosm-reader-bbbike-read_csv_xz>`.
    """

    csv_xz_raw = lzma.open(path_to_csv_xz, mode='rt', encoding='utf-8').readlines()
    csv_xz_dat = [x.rstrip('\t\n').split('\t') for x in csv_xz_raw]

    if col_names is None:
        col_names = ['type', 'id', 'feature']

    csv_xz = pd.DataFrame.from_records(csv_xz_dat, columns=col_names)

    return csv_xz


def parse_geojson_xz(path_to_geojson_xz, fmt_geom=False):
    """
    Parse a .geojson.xz file.

    :param path_to_geojson_xz: full path to a .csv.xz file
    :type path_to_geojson_xz: str
    :param fmt_geom: whether to reformat coordinates into a geometric object, defaults to ``False``
    :type fmt_geom: bool
    :return: tabular data of the .geojson.xz file
    :rtype: pandas.DataFrame

    See the example for :ref:`BBBikeReader.read_geojson_xz()<pydriosm-reader-bbbike-read_geojson_xz>`.
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


class GeoFabrikReader:
    """
    A class representation of a tool for reading `GeoFabrik <https://download.geofabrik.de/>`_ data extracts.
    """

    def __init__(self):
        """
        Constructor method.
        """
        self.Downloader = GeoFabrikDownloader()
        self.Name = copy.copy(self.Downloader.Name)
        self.URL = copy.copy(self.Downloader.URL)

    def get_path_to_osm_shp(self, subregion_name, layer_name=None, feature_name=None, data_dir=None, file_ext=".shp"):
        """
        Search the directory of GeoFabrik data to get the full path(s) to the .shp file(s) for a subregion.

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

            import os
            from pyhelpers.dir import rm_dir
            from pydriosm.downloader import GeoFabrikDownloader
            from pydriosm.reader import GeoFabrikReader, unzip_shp_zip, parse_shp_layer

            geofabrik_downloader = GeoFabrikDownloader()
            geofabrik_reader = GeoFabrikReader()

            subregion_name = 'rutland'
            file_ext = ".shp"

            path_to_osm_shp_file = geofabrik_reader.get_path_to_osm_shp(subregion_name)

            print(path_to_osm_shp_file)
            # (if "gis.osm_railways_free_1.shp" is not available at the package data directory)
            # []

            osm_file_format = ".shp"
            download_dir = "tests"

            path_to_rutland_shp_zip = geofabrik_downloader.download_subregion_osm_file(
                subregion_name, osm_file_format, download_dir, verbose=True, ret_download_path=True)
            # Confirm to download .shp.zip data of the following (sub)region(s):
            # 	rutland
            # ? [No]|Yes: yes
            # Downloading "rutland-latest-free.shp.zip" to "tests" ...
            # Done.

            unzip_shp_zip(path_to_rutland_shp_zip, verbose=True)
            # Extracting all of "rutland-latest-free.shp.zip" to "tests\\rutland-latest-free-shp"...
            # In progress ... Done.

            layer_name = 'railways'

            path_to_rutland_railways_shp = geofabrik_reader.get_path_to_osm_shp(
                subregion_name, layer_name, data_dir=download_dir)

            print(path_to_rutland_railways_shp)
            # '<cwd>\\tests\\rutland-latest-free-shp\\gis_osm_railways_free_1.shp'

            feature_name = 'rail'

            _ = parse_shp_layer(path_to_rutland_railways_shp, feature_names=feature_name,
                                save_fclass_shp=True)

            path_to_rutland_railways_shp = geofabrik_reader.get_path_to_osm_shp(
                subregion_name, layer_name, feature_name='rail', data_dir=download_dir)

            print(path_to_rutland_railways_shp)
            # '<cwd>\\tests\\rutland-latest-free-shp\\railways\\gis_osm_railways_free_1_rail.shp'

            rm_dir(path_to_rutland_shp_zip.replace(".shp.zip", "-shp"))
            # "<cwd>\\tests\\rutland-latest-free-shp" is not empty. Confirmed to remove the directory?
            # [No]|Yes: yes

            os.remove(path_to_rutland_shp_zip)
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

    def merge_multi_shp(self, subregion_names, layer_name, method='geopandas', update=False,
                        download_confirmation_required=True, data_dir=None, rm_zip_extracts=False, merged_shp_dir=None,
                        rm_shp_temp=False, verbose=False, ret_merged_shp_path=False):
        """
        Merge GeoFabrik .shp files for a layer for two or more subregions.

        :param subregion_names: a list of subregion names
        :type subregion_names: list
        :param layer_name: name of a .shp layer (e.g. 'railways')
        :type layer_name: str
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

        .. note::

            This function does not create projection (.prj) for the merged map
            (see also [`MMS-1 <http://geospatialpython.com/2011/02/create-prj-projection-file-for.html>`_])

            For valid ``layer_name``,
            check :py:func:`get_valid_shp_layer_names()<pydriosm.utils.get_valid_shp_layer_names>`.

        **Examples**::

            import os
            from pyhelpers.dir import cd, rm_dir
            from pydriosm.reader import GeoFabrikReader

            geofabrik_reader = GeoFabrikReader()

            # To merge 'railways' layers of "Greater Manchester" and "West Yorkshire"
            subregion_names = ['Manchester', 'West Yorkshire']
            layer_name = 'railways'
            data_dir = "tests"

            geofabrik_reader.merge_multi_shp(subregion_names, layer_name, data_dir=data_dir,
                                             rm_shp_temp=True, verbose=True)
            # Confirm to download .shp.zip data of the following (sub)region(s):
            # 	Greater Manchester
            # 	West Yorkshire
            # ? [No]|Yes: yes
            # Downloading "greater-manchester-latest-free.shp.zip" to "tests" ...
            # Done.
            # Downloading "west-yorkshire-latest-free.shp.zip" to "tests" ...
            # Done.
            # Extracting from "greater-manchester-latest-free.shp.zip" the following layer(s):
            # 	'railways'
            # to "tests\\greater-manchester-latest-free-shp" ...
            # In progress ... Done.
            # Extracting from "west-yorkshire-latest-free.shp.zip" the following layer(s):
            # 	'railways'
            # to "tests\\west-yorkshire-latest-free-shp" ...
            # In progress ... Done.
            # Merging the following shape files:
            # 	manchester_gis_osm_railways_free_1.shp
            # 	west-yorkshire_gis_osm_railways_free_1.shp
            # In progress ... Done.
            # Find the merged .shp file(s) at "tests\\greater-manchester_west-yorkshire_railways".

            path_to_merged_shp = geofabrik_reader.merge_multi_shp(
                subregion_names, layer_name, download_confirmation_required=False,
                data_dir=data_dir, rm_zip_extracts=True, rm_shp_temp=True,  verbose=True,
                ret_merged_shp_path=True)
            # "greater-manchester-latest-free.shp.zip" of Greater Manchester is already available...
            # "west-yorkshire-latest-free.shp.zip" of West Yorkshire is already available...
            # Extracting from "greater-manchester-latest-free.shp.zip" the following layer(s):
            # 	'railways'
            # to "tests\\greater-manchester-latest-free-shp" ...
            # In progress ... Done.
            # Extracting from "west-yorkshire-latest-free.shp.zip" the following layer(s):
            # 	'railways'
            # to "tests\\west-yorkshire-latest-free-shp" ...
            # In progress ... Done.
            # Merging the following shape files:
            # 	manchester_gis_osm_railways_free_1.shp
            # 	west-yorkshire_gis_osm_railways_free_1.shp
            # In progress ... Done.
            # Find the merged .shp file(s) at "tests\\greater-manchester_west-yorkshire_railways".

            print(path_to_merged_shp)
            # <cwd>\\tests\\...\\greater-manchester_west-yorkshire_railways.shp

            rm_dir(os.path.dirname(path_to_merged_shp))
            # ... is not empty. Confirmed to remove the directory?
            # [No]|Yes: yes

            os.remove(cd(data_dir, "greater-manchester-latest-free.shp.zip"))
            os.remove(cd(data_dir, "west-yorkshire-latest-free.shp.zip"))
        """

        # Make sure all the required shape files are ready
        subregion_names_ = [self.Downloader.validate_input_subregion_name(x) for x in subregion_names]
        layer_name_ = find_similar_str(layer_name, get_valid_shp_layer_names())

        osm_file_format = ".shp.zip"

        self.Downloader.download_subregion_osm_file(subregion_names_, osm_file_format=osm_file_format,
                                                    download_dir=data_dir, update=update,
                                                    confirmation_required=download_confirmation_required,
                                                    deep_retry=True, interval_sec=0, verbose=verbose)

        # Extract all files from .zip
        if data_dir is None:
            file_paths = (self.Downloader.get_default_path_to_osm_file(x, osm_file_format, mkdir=False)[1]
                          for x in subregion_names_)
        else:
            default_filenames = (self.Downloader.get_default_path_to_osm_file(x, osm_file_format, mkdir=False)[0]
                                 for x in subregion_names_)
            file_paths = [cd(validate_input_data_dir(data_dir), f) for f in default_filenames]

        extract_info = [(p, os.path.splitext(p)[0].replace(".", "-")) for p in file_paths]
        extract_dirs = []
        for file_path, extract_dir in extract_info:
            unzip_shp_zip(file_path, extract_dir, layer_names=layer_name_, verbose=verbose)
            extract_dirs.append(extract_dir)

        # Specify a directory that stores files for the specific layer
        prefix, suffix = "_".join([x.lower().replace(' ', '-') for x in subregion_names_]) + "_", "_temp"
        layer_ = f"{prefix}{layer_name_}{suffix}"
        if data_dir is None:
            temp_path_to_merged = cd(os.path.commonpath(extract_info[0]), layer_, mkdir=True)
        else:
            temp_path_to_merged = cd(validate_input_data_dir(data_dir), layer_, mkdir=True)

        # Copy .shp files (e.g. gis_osm_***_free_1.shp) into the output directory
        for subregion, p in zip(subregion_names, extract_dirs):
            for original_filename in glob.glob1(p, "*{}*".format(layer_name)):
                dest = cd(temp_path_to_merged, "{}_{}".format(subregion.lower().replace(' ', '-'), original_filename))
                shutil.copyfile(cd(p, original_filename), dest)

        shp_file_paths = [x for x in glob.glob(cd(temp_path_to_merged, "*.shp"))
                          if not os.path.basename(x).startswith(prefix)]

        if verbose:
            print("Merging the following shape files:")
            print("\t{}".format("\n\t".join(os.path.basename(f) for f in shp_file_paths)))
            print("In progress ... ", end="")

        if merged_shp_dir:
            path_to_merged = cd(validate_input_data_dir(merged_shp_dir), mkdir=True)
        else:
            if data_dir:
                path_to_merged = cd(data_dir, layer_.replace(suffix, "", -1), mkdir=True)
            else:
                path_to_merged = cd(os.path.commonpath(extract_info[0]), layer_.replace(suffix, "", -1), mkdir=True)

        try:
            if method in ('geopandas', 'gpd'):
                shp_data, geom_types = [], []
                for shp_file_path in shp_file_paths:
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
                        shp_data_.crs = specify_shp_crs()
                        shp_data_.to_file(filename=path_to_merged + f"_{k.lower()}", driver="ESRI Shapefile")

                    temp_dir_ = []
                    for x in glob.glob(cd(path_to_merged + "*", "{}*".format(prefix))):
                        shutil.move(x, cd(temp_path_to_merged.replace(suffix, "")))
                        temp_dir_.append(os.path.dirname(x))

                    for x in set(temp_dir_):
                        shutil.rmtree(x)

                else:
                    merged_shp_data = pd.concat(shp_data, ignore_index=True)
                    merged_shp_data.crs = specify_shp_crs()
                    merged_shp_data.to_file(filename=path_to_merged, driver="ESRI Shapefile")

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

                for x in glob.glob(cd(temp_path_to_merged, "{}*".format(prefix))):
                    shutil.move(x, cd(path_to_merged, os.path.basename(x).replace(suffix, "")))

            print("Done.") if verbose else ""

            if rm_zip_extracts:
                for p in extract_dirs:
                    shutil.rmtree(p)

            if rm_shp_temp:
                shutil.rmtree(temp_path_to_merged)

            print("Find the merged .shp file(s) at \"{}\".".format(os.path.relpath(path_to_merged))) if verbose else ""

            if ret_merged_shp_path:
                path_to_merged_shp = glob.glob(cd("{}*".format(path_to_merged), "*.shp"))
                if len(path_to_merged_shp) == 1:
                    path_to_merged_shp = path_to_merged_shp[0]
                return path_to_merged_shp

        except Exception as e:
            print("Failed. {}".format(e)) if verbose else ""

    def read_shp_zip(self, subregion_name, layer_names=None, feature_names=None, data_dir=None, update=False,
                     download_confirmation_required=True, pickle_it=False, ret_pickle_path=False, rm_extracts=False,
                     rm_shp_zip=False,
                     verbose=False):
        """
        Read GeoFabrik .shp.zip file of a subregion.

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
        :param ret_pickle_path: whether to return a full path to the saved pickle file (when ``pickle_it=True``)
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

            from pydriosm.reader import GeoFabrikReader

            geofabrik_reader = GeoFabrikReader()

            subregion_name = 'Rutland'
            data_dir = "tests"

            shp_data = geofabrik_reader.read_shp_zip(subregion_name, data_dir=data_dir)
            # Confirm to download .shp.zip data of the following (sub)region(s):
            # 	Rutland
            # ? [No]|Yes: yes

            print(list(shp_data.keys()))
            # ['buildings',
            #  'landuse',
            #  'natural',
            #  'places',
            #  'pofw',
            #  'pois',
            #  'railways',
            #  'roads',
            #  'traffic',
            #  'transport',
            #  'water',
            #  'waterways']

            print(shp_data['railways'].head())
            #     osm_id  code  ... tunnel                                           geometry
            # 0  2162114  6101  ...      F  LINESTRING (-0.45281 52.69934, -0.45189 52.698...
            # 1  3681043  6101  ...      F  LINESTRING (-0.65312 52.57308, -0.65318 52.572...
            # 2  3693985  6101  ...      F  LINESTRING (-0.73234 52.67821, -0.73191 52.678...
            # 3  3693986  6101  ...      F  LINESTRING (-0.61731 52.61323, -0.62419 52.614...
            # 4  4806329  6101  ...      F  LINESTRING (-0.45769 52.70352, -0.45654 52.702...
            #
            # [5 rows x 8 columns]

            layer_names = 'transport'
            feature_names = None

            shp_data = geofabrik_reader.read_shp_zip(subregion_name, layer_names, feature_names,
                                                     data_dir, rm_extracts=True, verbose=True)
            # Deleting the extracted files ... Done.

            print(list(shp_data.keys()))
            # ['transport']

            print(shp_data['transport'].head())
            #       osm_id  code    fclass                    name                   geometry
            # 0  472398147  5621  bus_stop                    None  POINT (-0.73213 52.66974)
            # 1  502322073  5621  bus_stop              Fife Close  POINT (-0.50962 52.66052)
            # 2  502322075  5621  bus_stop              Fife Close  POINT (-0.50973 52.66058)
            # 3  502322076  5621  bus_stop          Aberdeen Close  POINT (-0.51039 52.65817)
            # 4  502322077  5621  bus_stop  Arran Road (South End)  POINT (-0.50973 52.65469)

            layer_names = 'transport'
            feature_names = 'bus_stop'

            shp_data = geofabrik_reader.read_shp_zip(subregion_name, layer_names, feature_names,
                                                     data_dir, verbose=True)
            # Extracting from "rutland-latest-free.shp.zip" the following layer(s):
            # 	'transport'
            # to "tests\\rutland-latest-free-shp" ...
            # In progress ... Done.

            print(list(shp_data.keys()))
            # ['transport']

            print(shp_data['transport'].head())
            #       osm_id  code    fclass                    name                   geometry
            # 0  472398147  5621  bus_stop                    None  POINT (-0.73213 52.66974)
            # 1  502322073  5621  bus_stop              Fife Close  POINT (-0.50962 52.66052)
            # 2  502322075  5621  bus_stop              Fife Close  POINT (-0.50973 52.66058)
            # 3  502322076  5621  bus_stop          Aberdeen Close  POINT (-0.51039 52.65817)
            # 4  502322077  5621  bus_stop  Arran Road (South End)  POINT (-0.50973 52.65469)

            layer_names = ['traffic', 'roads']
            feature_names = ['parking', 'trunk']

            shp_data = geofabrik_reader.read_shp_zip(subregion_name, layer_names, feature_names,
                                                     data_dir, rm_extracts=True,
                                                     rm_shp_zip=True, verbose=True)
            # Extracting from "rutland-latest-free.shp.zip" the following layer(s):
            # 	'traffic'
            # 	'roads'
            # to "tests\\rutland-latest-free-shp" ...
            # In progress ... Done.
            # Deleting the extracted files ... Done.
            # Deleting "tests\\rutland-latest-free.shp.zip" ... Done.

            print(list(shp_data.keys()))
            # ['traffic', 'roads']

            print(shp_data['traffic'][['fclass', 'name', 'geometry']].head())
            #     fclass  name                                           geometry
            # 0  parking  None  POLYGON ((-0.66704 52.71108, -0.66670 52.71121...
            # 1  parking  None  POLYGON ((-0.78712 52.71974, -0.78700 52.71991...
            # 2  parking  None  POLYGON ((-0.70368 52.65567, -0.70362 52.65587...
            # 3  parking  None  POLYGON ((-0.63381 52.66442, -0.63367 52.66441...
            # 4  parking  None  POLYGON ((-0.62814 52.64093, -0.62701 52.64169...

            print(shp_data['roads'][['fclass', 'name', 'geometry']].head())
            #    fclass           name                                           geometry
            # 0   trunk           None  LINESTRING (-0.72461 52.59642, -0.72452 52.596...
            # 1   trunk   Glaston Road  LINESTRING (-0.64671 52.59353, -0.64590 52.593...
            # 3   trunk  Orange Street  LINESTRING (-0.72293 52.58899, -0.72297 52.588...
            # 11  trunk    Ayston Road  LINESTRING (-0.72483 52.59610, -0.72493 52.596...
            # 12  trunk    London Road  LINESTRING (-0.72261 52.58759, -0.72264 52.587...
        """

        osm_file_format = ".shp.zip"

        shp_zip_filename, path_to_shp_zip = self.Downloader.get_default_path_to_osm_file(
            subregion_name=subregion_name, osm_file_format=osm_file_format, mkdir=False)

        if layer_names:
            layer_names_ = [layer_names] if isinstance(layer_names, str) else layer_names.copy()
        else:
            layer_names_ = get_valid_shp_layer_names()
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
                        self.Downloader.download_subregion_osm_file(
                            subregion_name, osm_file_format=osm_file_format, download_dir=data_dir, update=update,
                            confirmation_required=download_confirmation_required, verbose=verbose)

                    unzip_shp_zip(path_to_shp_zip, path_to_extract_dir, layer_names=layer_names_, verbose=verbose)

                else:
                    unavailable_layers = []

                    layer_names_temp = [find_shp_layer_name(x) for x in os.listdir(cd(path_to_extract_dir))]
                    layer_names_temp = list(set(layer_names_ + layer_names_temp))

                    for lyr_name in layer_names_temp:
                        shp_filename = self.get_path_to_osm_shp(subregion_name, layer_name=lyr_name, data_dir=data_dir)
                        if not shp_filename:
                            unavailable_layers.append(lyr_name)

                    if unavailable_layers:
                        # if unavailable_layers == get_valid_shp_layer_names():
                        #     unavailable_layers = None
                        if not os.path.exists(path_to_shp_zip):
                            self.Downloader.download_subregion_osm_file(
                                subregion_name, osm_file_format=osm_file_format, download_dir=data_dir, update=update,
                                confirmation_required=download_confirmation_required, verbose=verbose)

                        unzip_shp_zip(path_to_shp_zip, path_to_extract_dir, layer_names=unavailable_layers,
                                      verbose=verbose)

                paths_to_layers_shp = [glob.glob(cd(path_to_extract_dir, r"gis_osm_{}_*.shp".format(layer_name)))
                                       for layer_name in layer_names_]
                paths_to_layers_shp = [x for x in paths_to_layers_shp if x]

                shp_data_ = [parse_shp_layer(p, feature_names=feature_names_) for p in paths_to_layers_shp]

                shp_data = dict(zip(layer_names_, shp_data_))

                if pickle_it:
                    save_pickle(shp_data, path_to_shp_pickle, verbose=verbose)

                    if ret_pickle_path:
                        shp_data = shp_data, path_to_shp_pickle

                if os.path.exists(path_to_extract_dir) and rm_extracts:
                    print("Deleting the extracted files", end=" ... ") if verbose else ""
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

    def get_path_to_osm_pbf(self, subregion_name, data_dir=None):
        """
        Retrieve path to GeoFabrik .osm.pbf file (if available) for a subregion.

        :param subregion_name: name of a region/subregion (case-insensitive)
        :type subregion_name: str
        :param data_dir: directory where the data file of the ``subregion_name`` is located/saved;
            if ``None`` (default), the default directory
        :type data_dir: str or None
        :return: path to .osm.pbf file
        :rtype: str or None

        **Example**::

            import os
            from pydriosm.reader import GeoFabrikReader

            geofabrik_reader = GeoFabrikReader()

            subregion_name = 'rutland'
            data_dir = None

            path_to_osm_pbf = geofabrik_reader.get_path_to_osm_pbf(subregion_name, data_dir)

            print(path_to_osm_pbf)
            # (if "rutland-latest.osm.pbf" is not available at the default package data directory)
            # None

            osm_file_format = ".pbf"
            download_dir = "tests"

            geofabrik_reader.Downloader.download_subregion_osm_file(subregion_name, osm_file_format,
                                                                    download_dir, verbose=True)
            # Confirm to download .osm.pbf data of the following (sub)region(s):
            # 	rutland
            # ? [No]|Yes: yes
            # Downloading "rutland-latest.osm.pbf" to "tests" ...
            # Done.

            path_to_osm_pbf = geofabrik_reader.get_path_to_osm_pbf(subregion_name,
                                                                   data_dir=download_dir)

            print(path_to_osm_pbf)
            # <cwd>\\tests\\rutland-latest.osm.pbf

            os.remove(path_to_osm_pbf)
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

    def read_osm_pbf(self, subregion_name, data_dir=None, chunk_size_limit=50,
                     parse_raw_feat=False, transform_geom=False, transform_other_tags=False,
                     update=False, download_confirmation_required=True, pickle_it=False, ret_pickle_path=False,
                     rm_osm_pbf=False, verbose=False):
        """
        Read GeoFabrik .osm.pbf file of a subregion.

        :param subregion_name: name of a region/subregion (case-insensitive)
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
        :param ret_pickle_path: whether to return a full path to the saved pickle file (when ``pickle_it=True``)
        :type ret_pickle_path: bool
        :param rm_osm_pbf: whether to delete the downloaded .osm.pbf file, defaults to ``False``
        :type rm_osm_pbf: bool
        :param verbose: whether to print relevant information in console as the function runs, defaults to ``False``
        :type verbose: bool or int
        :return: dictionary of the .osm.pbf data; when ``pickle_it=True``, return a tuple of the dictionary and
            a full path to the pickle file
        :rtype: dict or tuple or None

        **Examples**::

            import os
            from pyhelpers.dir import cd
            from pydriosm.reader import GeoFabrikReader

            geofabrik_reader = GeoFabrikReader()

            subregion_name = 'Rutland'
            data_dir = "tests"

            rutland_osm_pbf = geofabrik_reader.read_osm_pbf(subregion_name, data_dir, verbose=True)
            # Confirm to download .osm.pbf data of the following (sub)region(s):
            # 	Rutland
            # ? [No]|Yes: yes

            print(list(rutland_osm_pbf.keys()))
            # ['points', 'lines', 'multilinestrings', 'multipolygons', 'other_relations']

            print(rutland_osm_pbf['points'].head())
            #                                          points_data
            # 0  {"type": "Feature", "geometry": {"type": "Poin...
            # 1  {"type": "Feature", "geometry": {"type": "Poin...
            # 2  {"type": "Feature", "geometry": {"type": "Poin...
            # 3  {"type": "Feature", "geometry": {"type": "Poin...
            # 4  {"type": "Feature", "geometry": {"type": "Poin...

            rutland_osm_pbf = geofabrik_reader.read_osm_pbf(subregion_name, data_dir,
                                                            parse_raw_feat=True)

            print(rutland_osm_pbf['points'].head())
            #          id               coordinates  ... man_made                    other_tags
            # 0    488432  [-0.5134241, 52.6555853]  ...     None               "odbl"=>"clean"
            # 1    488658  [-0.5313354, 52.6737716]  ...     None                          None
            # 2  13883868  [-0.7229332, 52.5889864]  ...     None                          None
            # 3  14049101  [-0.7249922, 52.6748223]  ...     None  "traffic_calming"=>"cushion"
            # 4  14558402  [-0.7266686, 52.6695051]  ...     None      "direction"=>"clockwise"
            #
            # [5 rows x 12 columns]

            rutland_osm_pbf = geofabrik_reader.read_osm_pbf(subregion_name, data_dir,
                                                            parse_raw_feat=True,
                                                            transform_geom=True)

            print(rutland_osm_pbf['points'].coordinates.head())
            # 0             POINT (-0.5134241 52.6555853)
            # 1             POINT (-0.5313354 52.6737716)
            # 2    POINT (-0.7229332000000001 52.5889864)
            # 3             POINT (-0.7249922 52.6748223)
            # 4             POINT (-0.7266686 52.6695051)
            # Name: coordinates, dtype: object

            rutland_osm_pbf = geofabrik_reader.read_osm_pbf(subregion_name, data_dir,
                                                            parse_raw_feat=True,
                                                            transform_geom=True,
                                                            transform_other_tags=True)

            print(rutland_osm_pbf['points'].other_tags.head())
            # 0                 {'odbl': 'clean'}
            # 1                              None
            # 2                              None
            # 3    {'traffic_calming': 'cushion'}
            # 4        {'direction': 'clockwise'}
            # Name: other_tags, dtype: object

            os.remove(cd(data_dir, "rutland-latest.osm.pbf"))
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

            path_to_pickle = path_to_osm_pbf.replace(osm_file_format, ".pickle" if parse_raw_feat else "-raw.pickle")
            if os.path.isfile(path_to_pickle) and not update:
                osm_pbf_data = load_pickle(path_to_pickle)

                if ret_pickle_path:
                    osm_pbf_data = osm_pbf_data, path_to_pickle

            else:
                if not os.path.isfile(path_to_osm_pbf) or update:
                    # If the target file is not available, try downloading it first.
                    self.Downloader.download_subregion_osm_file(
                        subregion_name, osm_file_format=osm_file_format, download_dir=data_dir, update=update,
                        confirmation_required=download_confirmation_required, verbose=False)

                if verbose and parse_raw_feat:
                    print("Parsing \"{}\"".format(os.path.basename(path_to_osm_pbf)), end=" ... ")
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


class BBBikeReader:
    """
    A class representation of a tool for reading `BBBike <https://extract.bbbike.org/>`_ data extracts.
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
        :param data_dir: directory where the data file is located/saved; if ``None`` (default), the default directory
        :type data_dir: str or None
        :return: path to the data file
        :rtype: str or None

        **Example**::

            import os
            from pydriosm.reader import BBBikeReader

            bbbike_reader = BBBikeReader()

            subregion_name = 'leeds'
            osm_file_format = ".pbf"
            data_dir = "tests"

            path_to_leeds_pbf = bbbike_reader.Downloader.download_osm(
                subregion_name, osm_file_format, data_dir, verbose=True, ret_download_path=True)
            # Confirm to download .osm.pbf data of the following (sub)region(s):
            # 	Leeds
            # ? [No]|Yes: yes
            # Downloading "Leeds.osm.pbf" to "tests" ...
            # Done.

            path_to_file = bbbike_reader.get_path_to_file(subregion_name, osm_file_format, data_dir)

            print(path_to_leeds_pbf == path_to_file)
            # True

            os.remove(path_to_leeds_pbf)
        """

        _, _, _, path_to_file = self.Downloader.get_valid_download_info(
            subregion_name, osm_file_format=osm_file_format, download_dir=data_dir)

        return path_to_file

    def read_shp_zip(self, subregion_name, layer_names=None, feature_names=None, data_dir=None, update=False,
                     download_confirmation_required=True, pickle_it=False, ret_pickle_path=False, rm_extracts=False,
                     rm_shp_zip=False, verbose=False):
        """
        Read BBBike shapefile of a subregion.

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
        :param ret_pickle_path: whether to return a full path to the saved pickle file (when ``pickle_it=True``)
        :type ret_pickle_path: bool
        :param rm_extracts: whether to delete extracted files from the .shp.zip file, defaults to ``False``
        :type rm_extracts: bool
        :param rm_shp_zip: whether to delete the downloaded .shp.zip file, defaults to ``False``
        :type rm_shp_zip: bool
        :param verbose: whether to print relevant information in console as the function runs, defaults to ``False``
        :type verbose: bool or int
        :return: dictionary of the shapefile data, with keys and values being layer names and
            tabular data (in the format of `geopandas.GeoDataFrame`_), respectively;
            when ``pickle_it=True``, return a tuple of the dictionary and a full path to the pickle file
        :rtype: dict or tuple or None

        .. _`geopandas.GeoDataFrame`: https://geopandas.org/reference.html#geodataframe

        **Example**::

            from pydriosm.reader import BBBikeReader

            bbbike_reader = BBBikeReader()

            subregion_name = 'Birmingham'
            data_dir = "tests"

            shp_data = bbbike_reader.read_shp_zip(subregion_name, data_dir=data_dir)
            # Confirm to download .osm.shp.zip data of the following (sub)region(s):
            # 	Birmingham
            # ? [No]|Yes: yes

            print(list(shp_data.keys()))
            # ['buildings', 'landuse', 'natural', 'places', 'points', 'pofw', 'pois', 'railways']

            print(shp_data['railways'].head())
            #     osm_id  ...                                           geometry
            # 0      741  ...  LINESTRING (-1.82347 52.56051, -1.82332 52.560...
            # 1      743  ...  LINESTRING (-1.81016 52.53529, -1.81017 52.535...
            # 2   305256  ...  LINESTRING (-1.85928 52.50857, -1.85860 52.508...
            # 3  2807237  ...  LINESTRING (-1.97420 52.40375, -1.97412 52.403...
            # 4  3994755  ...  LINESTRING (-1.83725 52.56062, -1.83719 52.560...
            #
            # [5 rows x 4 columns]

            layer_names = 'roads'
            feature_name = None

            shp_data = bbbike_reader.read_shp_zip(subregion_name, layer_names, feature_name,
                                                  data_dir, rm_extracts=True, verbose=True)
            # Deleting the extracted files ... Done.

            print(list(shp_data.keys()))
            # ['roads']

            print(shp_data['roads'].head())
            #    osm_id  ...                                           geometry
            # 0      37  ...  LINESTRING (-1.82675 52.55580, -1.82646 52.555...
            # 1      38  ...  LINESTRING (-1.81541 52.54785, -1.81475 52.547...
            # 2      41  ...  LINESTRING (-1.81931 52.55219, -1.81860 52.552...
            # 3      42  ...  LINESTRING (-1.82492 52.55504, -1.82309 52.556...
            # 4      45  ...  LINESTRING (-1.82121 52.55389, -1.82056 52.55432)
            #
            # [5 rows x 8 columns]

            layer_names = ['railways', 'waterways']
            feature_names = ['rail', 'canal']

            shp_data = bbbike_reader.read_shp_zip(subregion_name, layer_names, feature_names,
                                                  data_dir, rm_extracts=True, rm_shp_zip=True,
                                                  verbose=True)
            # Extracting from "Birmingham.osm.shp.zip" the following layer(s):
            # 	'railways'
            # 	'waterways'
            # to "tests" ...
            # In progress ... Done.
            # Deleting the extracted files ... Done.
            # Deleting "tests\\Birmingham.osm.shp.zip" ... Done.

            print(list(shp_data.keys()))
            # ['railways', 'waterways']

            print(shp_data['railways'][['fclass', 'name']].head())
            #   fclass                             name
            # 0   rail                  Cross-City Line
            # 1   rail                  Cross-City Line
            # 2   rail                             None
            # 3   rail  Birmingham to Peterborough Line
            # 4   rail                     Freight Line

            print(shp_data['waterways'][['fclass', 'name']].head())
            #    fclass                                              name
            # 2   canal                      Birmingham and Fazeley Canal
            # 8   canal                      Birmingham and Fazeley Canal
            # 9   canal  Birmingham Old Line Canal Navigations - Rotton P
            # 10  canal                               Oozells Street Loop
            # 11  canal                      Worcester & Birmingham Canal
        """

        osm_file_format = ".shp.zip"

        path_to_shp_zip = self.get_path_to_file(subregion_name, osm_file_format, data_dir)

        path_to_extract_dir, shp_zip_filename = os.path.split(path_to_shp_zip)
        path_to_extract_dir_ = os.path.splitext(path_to_shp_zip)[0].replace(".osm.", "-")

        if layer_names:
            layer_names_ = [layer_names] if isinstance(layer_names, str) else layer_names.copy()
        else:
            layer_names_ = get_valid_shp_layer_names()
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
                        self.Downloader.download_osm(subregion_name, osm_file_format=osm_file_format,
                                                     download_dir=data_dir, update=update,
                                                     confirmation_required=download_confirmation_required,
                                                     verbose=verbose)

                    unzip_shp_zip(path_to_shp_zip, path_to_extract_dir, layer_names=layer_names_, verbose=verbose)

                else:
                    unavailable_layers = []

                    layer_names_temp = [x.rsplit(".", 1)[0] for x in os.listdir(cd(path_to_extract_dir_, "shape"))]
                    layer_names_temp = list(set(layer_names_ + layer_names_temp))

                    for lyr_name in layer_names_temp:
                        shp_filename = cd(path_to_extract_dir_, "shape", f"{lyr_name}.shp")
                        if not os.path.isfile(shp_filename):
                            unavailable_layers.append(lyr_name)

                    if unavailable_layers:
                        # if unavailable_layers == layer_names_temp:
                        #     unavailable_layers = None
                        if not os.path.exists(path_to_shp_zip):
                            self.Downloader.download_osm(subregion_name, osm_file_format=osm_file_format,
                                                         download_dir=data_dir, update=update,
                                                         confirmation_required=download_confirmation_required,
                                                         verbose=verbose)

                        unzip_shp_zip(path_to_shp_zip, path_to_extract_dir, layer_names=unavailable_layers,
                                      verbose=verbose)

                paths_to_layers_shp = [
                    glob.glob(cd(path_to_extract_dir_, "shape", f"{lyr_name}.shp")) for lyr_name in layer_names_]
                paths_to_layers_shp = [x for x in paths_to_layers_shp if x]

                shp_data_ = [parse_shp_layer(p, feature_names=feature_names_) for p in paths_to_layers_shp]

                shp_data = dict(zip(layer_names_, shp_data_))

                if pickle_it:
                    save_pickle(shp_data, path_to_shp_pickle, verbose=verbose)

                    if ret_pickle_path:
                        shp_data = shp_data, path_to_shp_pickle

                if rm_extracts and os.path.exists(path_to_extract_dir_):
                    print("Deleting the extracted files", end=" ... ") if verbose else ""
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

    def read_osm_pbf(self, subregion_name, data_dir=None, chunk_size_limit=50,
                     parse_raw_feat=False, transform_geom=False, transform_other_tags=False,
                     update=False, download_confirmation_required=True, pickle_it=False, ret_pickle_path=False,
                     rm_osm_pbf=False, verbose=False):
        """
        Read BBBike .osm.pbf file of a subregion.

        :param subregion_name: name of a region/subregion (case-insensitive)
        :type subregion_name: str
        :param data_dir: directory where the .osm.pbf data file is located/saved;
            if ``None`` (default), the default directory
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
        :param ret_pickle_path: whether to return a full path to the saved pickle file (when ``pickle_it=True``)
        :type ret_pickle_path: bool
        :param rm_osm_pbf: whether to delete the downloaded .osm.pbf file, defaults to ``False``
        :type rm_osm_pbf: bool
        :param verbose: whether to print relevant information in console as the function runs, defaults to ``False``
        :type verbose: bool or int
        :return: dictionary of the .osm.pbf data; when ``pickle_it=True``, return a tuple of the dictionary and
            a full path to the pickle file
        :rtype: dict or tuple or None

        **Example**::

            import os
            from pyhelpers.dir import cd
            from pydriosm.reader import BBBikeReader

            bbbike_reader = BBBikeReader()

            data_dir = "tests"

            # (Note that this process may take a long time.)
            leeds_osm_pbf = bbbike_reader.read_osm_pbf(subregion_name, data_dir,
                                                       parse_raw_feat=True, transform_geom=True,
                                                       transform_other_tags=True, verbose=True)
            # Parsing "Leeds.osm.pbf" ... Done.

            print(list(leeds_osm_pbf.keys()))
            # ['points', 'lines', 'multilinestrings', 'multipolygons', 'other_relations']

            print(leeds_osm_pbf['multipolygons'].head())
            #       id                                        coordinates  ... tourism other_tags
            # 0  10595  (POLYGON ((-1.5030223 53.6725382, -1.5034495 5...  ...    None       None
            # 1  10600  (POLYGON ((-1.5116994 53.6764287, -1.5099361 5...  ...    None       None
            # 2  10601  (POLYGON ((-1.5142403 53.6710831, -1.5143686 5...  ...    None       None
            # 3  10612  (POLYGON ((-1.5129341 53.6704885, -1.5131883 5...  ...    None       None
            # 4  10776  (POLYGON ((-1.5523801 53.7029081, -1.5522831 5...  ...    None       None
            #
            # [5 rows x 27 columns]

            os.remove(cd(data_dir, "Leeds.osm.pbf"))
        """

        assert isinstance(chunk_size_limit, int) or chunk_size_limit is None

        osm_file_format = ".osm.pbf"

        path_to_osm_pbf = self.get_path_to_file(subregion_name, osm_file_format, data_dir)

        path_to_pickle = path_to_osm_pbf.replace(".osm.pbf", ".pickle" if parse_raw_feat else "-raw.pickle")
        if os.path.isfile(path_to_pickle) and not update:
            osm_pbf_data = load_pickle(path_to_pickle)

            if ret_pickle_path:
                osm_pbf_data = osm_pbf_data, path_to_pickle

        else:
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

    def read_csv_xz(self, subregion_name, data_dir=None, download_confirmation_required=True, verbose=False):
        """
        Read BBBike .csv.xz file of a subregion.

        :param subregion_name: name of a region/subregion (case-insensitive)
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

        .. _pydriosm-reader-bbbike-read_csv_xz:

        **Example**::

            from pydriosm.reader import BBBikeReader

            bbbike_reader = BBBikeReader()

            subregion_name = 'Leeds'
            data_dir = "tests"

            csv_xz_data = bbbike_reader.read_csv_xz(subregion_name, data_dir, verbose=True)
            # Confirm to download the .osm.csv.xz data of "Leeds" [No]|Yes: yes
            # Done.
            # Parsing the .csv.xz data for "Leeds" ... Done.

            print(csv_xz_data.head())
            #    type      id feature
            # 0  node  154915    None
            # 1  node  154916    None
            # 2  node  154921    None
            # 3  node  154922    None
            # 4  node  154923    None
        """

        subregion_name_ = self.Downloader.validate_input_subregion_name(subregion_name)
        osm_file_format = ".csv.xz"

        path_to_csv_xz = self.get_path_to_file(subregion_name_, osm_file_format, data_dir)

        if not os.path.isfile(path_to_csv_xz):
            path_to_csv_xz = self.Downloader.download_osm(subregion_name_, osm_file_format=osm_file_format,
                                                          download_dir=data_dir,
                                                          confirmation_required=download_confirmation_required,
                                                          verbose=verbose, ret_download_path=True)

        if verbose:
            print("Parsing the {} data for \"{}\"".format(osm_file_format, subregion_name_), end=" ... ")
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

        .. _pydriosm-reader-bbbike-read_geojson_xz:

        **Examples**::

            from pydriosm.reader import BBBikeReader

            bbbike_reader = BBBikeReader()

            subregion_name = 'Leeds'
            data_dir = "tests"

            geojson_xz_data = bbbike_reader.read_geojson_xz(subregion_name, data_dir, verbose=True)
            # Confirm to download the .osm.geojson.xz data of "Leeds" [No]|Yes: yes
            # Done.
            # Parsing the .geojson.xz data for "Leeds" ... Done.

            print(geojson_xz_data.head())
            #   feature_name  ...                                         properties
            # 0      Feature  ...  {'ref': '40', 'name': 'Flushdyke', 'highway': ...
            # 1      Feature  ...  {'ref': '44', 'name': 'Bramham', 'highway': 'm...
            # 2      Feature  ...  {'ref': '43', 'name': 'Belle Isle', 'highway':...
            # 3      Feature  ...  {'ref': '42', 'name': 'Lofthouse', 'highway': ...
            # 4      Feature  ...  {'ref': '42', 'name': 'Lofthouse', 'highway': ...
            #
            # [5 rows x 4 columns]

            geojson_xz_data = bbbike_reader.read_geojson_xz(subregion_name, data_dir, fmt_geom=True)

            print(geojson_xz_data[['coordinates']].head())
            #                      coordinates
            # 0  POINT (-1.5558097 53.6873431)
            # 1     POINT (-1.34293 53.844618)
            # 2   POINT (-1.517335 53.7499667)
            # 3   POINT (-1.514124 53.7416937)
            # 4   POINT (-1.516511 53.7256632)
        """

        subregion_name_ = self.Downloader.validate_input_subregion_name(subregion_name)
        osm_file_format = ".geojson.xz"

        path_to_geojson_xz = self.get_path_to_file(subregion_name_, osm_file_format, data_dir)

        if not os.path.isfile(path_to_geojson_xz):
            path_to_geojson_xz = self.Downloader.download_osm(subregion_name_, osm_file_format=osm_file_format,
                                                              download_dir=data_dir,
                                                              confirmation_required=download_confirmation_required,
                                                              verbose=verbose, ret_download_path=True)

        if verbose:
            print("Parsing the {} data for \"{}\"".format(osm_file_format, subregion_name_), end=" ... ")
        try:
            geojson_xz_data = parse_geojson_xz(path_to_geojson_xz, fmt_geom=fmt_geom)

            print("Done. ") if verbose else ""

        except Exception as e:
            print("Failed. {}".format(e))
            geojson_xz_data = None

        return geojson_xz_data
