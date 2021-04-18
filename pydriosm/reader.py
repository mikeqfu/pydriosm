"""
Read OpenStreetMap (`OSM <https://www.openstreetmap.org/>`_) data extracts.
"""

import collections
import gc
import glob
import itertools
import lzma
import zipfile

import osgeo.ogr
import rapidjson
import shapefile as pyshp
import shapely.geometry
from pyhelpers.ops import split_list

from .downloader import *
from .settings import gdal_configurations
from .utils import *


# == .osm.pbf / .pbf / .osm.bz2 ==============================================================

def get_osm_pbf_layer_names(path_to_osm_pbf):
    """
    Get indices and names of all layers in a PBF data file.

    :param path_to_osm_pbf: path to a PBF data file
    :type path_to_osm_pbf: str
    :return: indices and names of each layer of the PBF data file
    :rtype: dict

    **Example**::

        >>> import os
        >>> from pydriosm.downloader import GeofabrikDownloader
        >>> from pydriosm.reader import get_osm_pbf_layer_names

        >>> # Download the PBF data file of Rutland as an example
        >>> geofabrik_downloader = GeofabrikDownloader()

        >>> path_to_rutland_pbf = geofabrik_downloader.download_osm_data(
        ...     subregion_names='Rutland', osm_file_format=".pbf", download_dir="tests",
        ...     verbose=True, ret_download_path=True)
        To download .osm.pbf data of the following geographic region(s):
            Rutland
        ? [No]|Yes: yes
        Downloading "rutland-latest.osm.pbf" to "tests\\" ... Done.

        >>> # Get indices and names of all layers in the downloaded PBF data file
        >>> lyr_idx_names = get_osm_pbf_layer_names(path_to_rutland_pbf)

        >>> for k, v in lyr_idx_names.items():
        ...     print(f'{k}: {v}')
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
        osm_pbf = osgeo.ogr.Open(path_to_osm_pbf)

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
    :param transform_geom: whether to transform a single coordinate
        (or a collection of coordinates) into a geometric object
    :type transform_geom: bool
    :param transform_other_tags: whether to transform a ``'other_tags'`` into a dictionary
    :type transform_other_tags: bool
    :return: parsed data of the ``geo_typ`` layer of a given .pbf file
    :rtype: pandas.DataFrame

    .. _`shapely.geometry`: https://shapely.readthedocs.io/en/latest/manual.html#geometric-objects

    See the examples for the function :py:func:`parse_osm_pbf()<pydriosm.reader.parse_osm_pbf>`.
    """

    def _make_point_as_polygon(mp_coords):
        mp_coords, temp = mp_coords.copy(), mp_coords[0][0].copy()

        if len(temp) == 2 and temp[0] == temp[1]:
            mp_coords[0][0] += [temp[0]]

        return mp_coords

    def _transform_single_geometry(geom_data):
        """
        Transform a single coordinate into a geometric object by using
        `shapely.geometry <https://shapely.readthedocs.io/en/latest/manual.html#geometric-objects>`_.
        """

        pbf_layer_feat_types = get_pbf_layer_feat_types_dict()

        geom_type = pbf_layer_feat_types[geo_typ]
        geom_type_func = getattr(shapely.geometry, geom_type)

        if geom_type == 'MultiPolygon':
            geom_coords = geom_data.coordinates.map(
                lambda x: geom_type_func(
                    shapely.geometry.Polygon(y) for ls in _make_point_as_polygon(x) for y in ls))

        else:
            geom_coords = geom_data.coordinates.map(lambda x: geom_type_func(x))

        return geom_coords

    def _transform_multi_geometries(geom_collection):
        """
        Transform a collection of coordinates into a geometric object formatted by
        `shapely.geometry <https://shapely.readthedocs.io/en/latest/manual.html#geometric-objects>`_.
        """

        geom_types = [g['type'] for g in geom_collection]
        coordinates = [gs['coordinates'] for gs in geom_collection]

        geometry_collection = [
            getattr(shapely.geometry, geom_type)(coords) if 'Polygon' not in geom_type
            else getattr(shapely.geometry, geom_type)(pt for pts in coords for pt in pts)
            for geom_type, coords in zip(geom_types, coordinates)]

        geom_collection_ = shapely.geometry.GeometryCollection(geometry_collection)

        return geom_collection_

    def _transform_other_tags(other_tags):
        """
        Transform a ``'other_tags'`` into a dictionary.

        :param other_tags: data of a single record in the ``'other_tags'`` feature
        :type other_tags: str or None
        :return: parsed data of the ``'other_tags'`` record
        :rtype: dict or None
        """

        if other_tags:
            raw_other_tags = (
                re.sub('^"|"$', '', each_tag) for each_tag in re.split('(?<="),(?=")', other_tags)
            )
            other_tags_ = {
                k: v.replace('<br>', ' ')
                for k, v in (re.split('"=>"?', each_tag) for each_tag in filter(None, raw_other_tags))
            }

        else:  # e.g. other_tags_x is None
            other_tags_ = other_tags

        return other_tags_

    if not pbf_layer_data.empty:
        # Start parsing 'geometry' column
        dat_geometry = pd.DataFrame(x for x in pbf_layer_data.geometry).rename(columns={'type': 'geom_type'})

        if geo_typ != 'other_relations':
            # `geo_type` can be 'points', 'lines', 'multilinestrings' or 'multipolygons'
            if transform_geom:
                dat_geometry.coordinates = _transform_single_geometry(dat_geometry)
        else:  # geo_typ == 'other_relations'
            if transform_geom:
                dat_geometry.geometries = dat_geometry.geometries.map(_transform_multi_geometries)
                dat_geometry.rename(columns={'geometries': 'coordinates'}, inplace=True)

        # Start parsing 'properties' column
        dat_properties = pd.DataFrame(x for x in pbf_layer_data.properties)

        if transform_other_tags:
            dat_properties.other_tags = dat_properties.other_tags.map(_transform_other_tags)

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


def parse_osm_pbf(path_to_osm_pbf, parse_raw_feat=False, transform_geom=False, transform_other_tags=False,
                  number_of_chunks=None, max_tmpfile_size=None):
    """
    Parse a PBF data file.

    :param path_to_osm_pbf: path to a PBF data file
    :type path_to_osm_pbf: str
    :param parse_raw_feat: whether to parse each feature in the raw data, defaults to ``False``
    :type parse_raw_feat: bool
    :param transform_geom: whether to transform a single coordinate
        (or a collection of coordinates) into a geometric object, defaults to ``False``
    :param transform_other_tags: whether to transform a ``'other_tags'`` into a dictionary,
        defaults to ``False``
    :type transform_other_tags: bool
    :param number_of_chunks: number of chunks, defaults to ``None``
    :type number_of_chunks: int or None
    :param max_tmpfile_size: defaults to ``None``;
        see also :py:func:`gdal_configurations()<pydriosm.settings.gdal_configurations>`
    :type max_tmpfile_size: int or None
    :return: parsed OSM PBF data
    :rtype: dict

    .. _pydriosm-reader-parse_osm_pbf:

    .. note::

        The driver categorises features into 5 layers:

        - **0: 'points'** - "node" features having significant tags attached
        - **1: 'lines'** - "way" features being recognized as non-area
        - **2: 'multilinestrings'** - "relation" features forming a multilinestring
          (type='multilinestring' / type='route')
        - **3: 'multipolygons'** - "relation" features forming a multipolygon
          (type='multipolygon' / type='boundary'), and "way" features being recognized as area
        - **4: 'other_relations'** - "relation" features not belonging to the above 2 layers

        See also [`POP-1 <https://gdal.org/drivers/vector/osm.html>`_].

        This function may require fairly high amount of physical memory to parse large files
        (e.g. > 200MB), in which case it would be recommended that ``number_of_chunks`` is set
        to be a reasonable value.

    **Example**::

        >>> import os
        >>> from pydriosm.reader import GeofabrikDownloader, parse_osm_pbf

        >>> # Download the PBF data file of Rutland as an example
        >>> geofabrik_downloader = GeofabrikDownloader()

        >>> path_to_rutland_pbf = geofabrik_downloader.download_osm_data(
        ...     subregion_names='Rutland', osm_file_format=".pbf", download_dir="tests",
        ...     verbose=True, ret_download_path=True)
        To download .osm.pbf data of the following geographic region(s):
            Rutland
        ? [No]|Yes: yes
        Downloading "rutland-latest.osm.pbf" to "tests\\" ... Done.

        >>> print(os.path.relpath(path_to_rutland_pbf))
        tests\\rutland-latest.osm.pbf

        >>> # Parse the downloaded PBF data
        >>> rutland_pbf_raw = parse_osm_pbf(path_to_rutland_pbf)

        >>> type(rutland_pbf_raw)
        dict
        >>> list(rutland_pbf_raw.keys())
        ['points', 'lines', 'multilinestrings', 'multipolygons', 'other_relations']

        >>> rutland_pbf_raw_points = rutland_pbf_raw['points']
        >>> rutland_pbf_raw_points.head()
                                                      points
        0  {"type": "Feature", "geometry": {"type": "Poin...
        1  {"type": "Feature", "geometry": {"type": "Poin...
        2  {"type": "Feature", "geometry": {"type": "Poin...
        3  {"type": "Feature", "geometry": {"type": "Poin...
        4  {"type": "Feature", "geometry": {"type": "Poin...

        >>> # Set ``parse_raw_feat`` to be ``True``
        >>> rutland_pbf_parsed_0 = parse_osm_pbf(path_to_rutland_pbf, parse_raw_feat=True)

        >>> rutland_pbf_parsed_points_0 = rutland_pbf_parsed_0['points']
        >>> rutland_pbf_parsed_points_0.head()
                 id               coordinates  ... man_made                    other_tags
        0    488432  [-0.5134241, 52.6555853]  ...     None               "odbl"=>"clean"
        1    488658  [-0.5313354, 52.6737716]  ...     None                          None
        2  13883868  [-0.7229332, 52.5889864]  ...     None                          None
        3  14049101  [-0.7249922, 52.6748223]  ...     None  "traffic_calming"=>"cushion"
        4  14558402  [-0.7266686, 52.6695051]  ...     None      "direction"=>"clockwise"
        [5 rows x 12 columns]

        >>> # Set both ``parse_raw_feat`` and ``transform_geom`` to be ``True``
        >>> rutland_pbf_parsed_1 = parse_osm_pbf(path_to_rutland_pbf, parse_raw_feat=True,
        ...                                      transform_geom=True)

        >>> rutland_pbf_parsed_points_1 = rutland_pbf_parsed_1['points']
        >>> # Check the difference in 'coordinates', compared to ``rutland_pbf_parsed_points_0``
        >>> rutland_pbf_parsed_points_1[['coordinates']].head()
                                        coordinates
        0             POINT (-0.5134241 52.6555853)
        1             POINT (-0.5313354 52.6737716)
        2    POINT (-0.7229332000000001 52.5889864)
        3             POINT (-0.7249922 52.6748223)
        4             POINT (-0.7266686 52.6695051)

        >>> # Further, set ``transform_other_tags`` to be ``True``
        >>> rutland_pbf_parsed_2 = parse_osm_pbf(path_to_rutland_pbf, parse_raw_feat=True,
        ...                                      transform_other_tags=True)

        >>> rutland_pbf_parsed_points_2 = rutland_pbf_parsed_2['points']
        >>> # Check the difference in 'other_tags', compared to ``rutland_pbf_parsed_points_0``
        >>> rutland_pbf_parsed_points_2[['other_tags']].head()
                               other_tags
        0               {'odbl': 'clean'}
        1                            None
        2                            None
        3  {'traffic_calming': 'cushion'}
        4      {'direction': 'clockwise'}

        >>> # Delete the downloaded PBF data file
        >>> os.remove(path_to_rutland_pbf)

    .. seealso::

        More examples for the method
        :py:meth:`GeofabrikReader.read_osm_pbf()<pydriosm.reader.GeofabrikReader.read_osm_pbf>`.
    """

    parse_raw_feat_ = True if transform_geom or transform_other_tags else copy.copy(parse_raw_feat)

    if max_tmpfile_size:
        gdal_configurations(max_tmpfile_size=max_tmpfile_size)

    raw_osm_pbf = osgeo.ogr.Open(path_to_osm_pbf)

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
            # number_of_chunks = file_size_in_mb / chunk_size_limit
            # chunk_size = len(features) / number_of_chunks
            feats = split_list(lst=features, num_of_sub=number_of_chunks)

            del features
            gc.collect()

            all_lyr_dat = []
            for feat in feats:
                if parse_raw_feat_:
                    lyr_dat_ = pd.DataFrame(f.ExportToJson(as_object=True) for f in feat)
                    lyr_dat = parse_osm_pbf_layer(
                        pbf_layer_data=lyr_dat_, geo_typ=layer_name, transform_geom=transform_geom,
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
                layer_data_ = pd.DataFrame(
                    feature.ExportToJson(as_object=True) for _, feature in enumerate(layer_dat))
                layer_data = parse_osm_pbf_layer(
                    layer_data_, geo_typ=layer_name, transform_geom=transform_geom,
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


# == .shp.zip ================================================================================

def unzip_shp_zip(path_to_shp_zip, path_to_extract_dir=None, layer_names=None, mode='r',
                  clustered=False, verbose=False, ret_extract_dir=False):
    """
    Unzip a .shp.zip file.

    :param path_to_shp_zip: path to a zipped shapefile data (.shp.zip)
    :type path_to_shp_zip: str
    :param path_to_extract_dir: path to a directory where extracted files will be saved;
        if ``None`` (default), the same directory where the .shp.zip file is saved
    :type path_to_extract_dir: str or None
    :param layer_names: name of a .shp layer, e.g. 'railways', or names of multiple layers;
        if ``None`` (default), all available layers
    :type layer_names: str or list or None
    :param mode: the ``mode`` parameter of `zipfile.ZipFile()`_, defaults to ``'r'``
    :type mode: str
    :param clustered: whether to put the data files of different layer in respective folders,
        defaults to ``False``
    :type clustered: bool
    :param verbose: whether to print relevant information in console as the function runs,
        defaults to ``False``
    :type verbose: bool or int
    :param ret_extract_dir: whether to return the path to the directory where extracted files are saved,
        defaults to ``False``
    :type ret_extract_dir: bool
    :return: the path to the directory of extracted files when ``ret_extract_dir`` is set to be ``True``
    :rtype: str

    .. _`zipfile.ZipFile()`: https://docs.python.org/3/library/zipfile.html#zipfile-objects

    **Examples**::

        >>> import os
        >>> from pyhelpers.dir import cd, delete_dir
        >>> from pydriosm.reader import GeofabrikDownloader, unzip_shp_zip

        >>> geofabrik_downloader = GeofabrikDownloader()

        >>> path_to_rutland_shp_zip = geofabrik_downloader.download_osm_data(
        ...     subregion_names='Rutland', osm_file_format=".shp.zip", download_dir="tests",
        ...     verbose=True, ret_download_path=True)
        To download .shp.zip data of the following geographic region(s):
            Rutland
        ? [No]|Yes: yes
        Downloading "rutland-latest-free.shp.zip" to "tests\\" ... Done.

        >>> layer_name = 'railways'

        >>> unzip_shp_zip(path_to_rutland_shp_zip, layer_names=layer_name, verbose=True)
        Extracting the following layer(s):
            'railways'
        from "tests\\rutland-latest-free.shp.zip" ...
        to "tests\\rutland-latest-free-shp\\"

        >>> path_to_rutland_shp_dir = unzip_shp_zip(path_to_rutland_shp_zip, verbose=True,
        ...                                         ret_extract_dir=True)
        Extracting "tests\\rutland-latest-free.shp.zip" ...
        to "tests\\rutland-latest-free-shp\\"
        Done.

        >>> print(os.path.relpath(path_to_rutland_shp_dir))
        tests\\rutland-latest-free-shp

        >>> lyr_names = ['railways', 'transport', 'traffic']

        >>> paths_to_layer_dirs = unzip_shp_zip(path_to_rutland_shp_zip, layer_names=lyr_names,
        ...                                     clustered=True, verbose=2, ret_extract_dir=True)
        Extracting the following layer(s):
            'railways'
            'transport'
            'traffic'
        from "tests\\rutland-latest-free.shp.zip" ...
        to "tests\\rutland-latest-free-shp\\"
        Done.
        Clustering layer data ...
            traffic ... Done.
            transport_a ... Done.
            transport ... Done.
            railways ... Done.
            traffic_a ... Done.
        All done.

        >>> for path_to_lyr_dir in paths_to_layer_dirs:
        ...     print(os.path.relpath(path_to_lyr_dir))
        tests\\rutland-latest-free-shp\\railways
        tests\\rutland-latest-free-shp\\transport
        tests\\rutland-latest-free-shp\\traffic

        >>> # Delete the extracted files
        >>> delete_dir(os.path.commonpath(paths_to_layer_dirs), verbose=True)
        The directory "tests\\rutland-latest-free-shp\\" is not empty.
        Confirmed to delete it? [No]|Yes: yes
        Deleting "tests\\rutland-latest-free-shp\\" ... Done.

        >>> # Delete the downloaded .shp.zip data file
        >>> os.remove(path_to_rutland_shp_zip)
    """

    if path_to_extract_dir:
        extract_dir = path_to_extract_dir
    else:
        extract_dir = os.path.splitext(path_to_shp_zip)[0].replace(".", "-")

    from_to_msg = "\"{}\" ... \nto \"{}\\\"".format(
        os.path.relpath(path_to_shp_zip), os.path.relpath(extract_dir))

    if not layer_names:
        layer_names_ = layer_names
        if verbose:
            print("Extracting {}".format(from_to_msg))
    else:
        layer_names_ = [layer_names] if isinstance(layer_names, str) else layer_names.copy()
        if verbose:
            layer_name_list = "\t{}".format("\n\t".join([f"'{x}'" for x in layer_names_]))
            print("Extracting the following layer(s): \n{}".format(layer_name_list))
            print("from {}".format(from_to_msg))

    try:
        with zipfile.ZipFile(path_to_shp_zip, mode) as shp_zip:
            if layer_names_:
                extract_files = [
                    f.filename for f in shp_zip.filelist if any(x in f.filename for x in layer_names_)]
            else:
                extract_files = None

            shp_zip.extractall(extract_dir, members=extract_files)

        shp_zip.close()

        if verbose:
            if isinstance(extract_files, list) and len(extract_files) == 0:
                print("The specified layer does not exist.\nNo data has been extracted.")
            else:
                print("Done.")

        if clustered:
            if verbose:
                print("Clustering layer data ... ", end="\n" if verbose == 2 else "")

            file_list = extract_files if extract_files else os.listdir(extract_dir)

            if 'README' in file_list:
                file_list.remove('README')

            filenames = list(set([os.path.splitext(x)[0] for x in file_list]))
            exts = list(set([os.path.splitext(x)[1] for x in file_list]))

            layer_names_ = [find_shp_layer_name(f) for f in filenames]

            extract_dirs = []
            for lyr, fn in zip(layer_names_, filenames):
                extract_dir_ = cd(extract_dir, lyr)
                if verbose == 2:
                    print("\t{}".format(lyr if '_a_' not in fn else lyr + '_a'), end=" ... ")

                for ext in exts:
                    filename = fn + ext
                    orig = cd(extract_dir, filename, mkdir=True)
                    dest = cd(extract_dir_, filename, mkdir=True)
                    shutil.copyfile(orig, dest)
                    os.remove(orig)

                if verbose == 2:
                    print("Done.")

                extract_dirs.append(extract_dir_)

            extract_dir = list(set(extract_dirs))

            if verbose is True:
                print("Done.")
            elif verbose == 2:
                print("All done.")

    except Exception as e:
        if verbose:
            print("Failed. {}".format(e))

    if ret_extract_dir:
        return extract_dir


def read_shp_file(path_to_shp, method='pyshp', emulate_gpd=False, **kwargs):
    """
    Parse a shapefile.

    :param path_to_shp: path to a .shp data file
    :type: str
    :param method: method used to read shapefiles;
        options include: ``'pyshp'`` (default) and ``'geopandas'`` (or ``'gpd'``)
        if ``method='geopandas'`` (or ``method='gpd'``),
        this function relies on `geopandas.read_file()`_;
        otherwise, it by default uses `shapefile.Reader()`_
    :type method: str
    :param emulate_gpd: whether to emulate the data format produced by `geopandas.read_file()`_,
        when ``method='pyshp'``.
    :type emulate_gpd: bool
    :param kwargs: optional parameters of `geopandas.read_file()`_ or `shapefile.Reader()`_
    :return: data frame of the .shp data
    :rtype: pandas.DataFrame or geopandas.GeoDataFrame

    .. _`shapefile.Reader()`: https://github.com/GeospatialPython/pyshp#reading-shapefiles
    .. _`geopandas.read_file()`: https://geopandas.org/reference/geopandas.read_file.html

    .. note::

        If ``method`` is set to be ``'geopandas'`` (or ``'gpd'``), it requires availability of
        the package `GeoPandas <https://geopandas.org/>`_.

    **Examples**::

        >>> import os
        >>> from pyhelpers.dir import cd, delete_dir
        >>> from pydriosm.reader import GeofabrikDownloader, unzip_shp_zip, read_shp_file

        >>> # Download the .shp.zip file of Rutland as an example
        >>> geofabrik_downloader = GeofabrikDownloader()

        >>> sr_name = 'Rutland'
        >>> file_fmt = ".shp"
        >>> dwnld_dir = "tests"

        >>> path_to_rutland_shp_zip = geofabrik_downloader.download_osm_data(
        ...     sr_name, file_fmt, dwnld_dir, verbose=True, ret_download_path=True)
        To download .shp.zip data of the following geographic region(s):
            Rutland
        ? [No]|Yes: yes
        Downloading "rutland-latest-free.shp.zip" to "tests\\" ... Done.

        >>> path_to_rutland_shp_dir = unzip_shp_zip(path_to_shp_zip=path_to_rutland_shp_zip,
        ...                                         ret_extract_dir=True)

        >>> # .shp data of 'railways'
        >>> railways_shp_filename = "gis_osm_railways_free_1.shp"
        >>> path_to_rutland_railways_shp = cd(path_to_rutland_shp_dir, railways_shp_filename)

        >>> # Set `method` to be 'gpd' or 'geopandas'
        >>> rutland_railways_shp = read_shp_file(path_to_rutland_railways_shp)

        >>> rutland_railways_shp.head()
            osm_id  code  ...                                        coordinates shape_type
        0  2162114  6101  ...  [(-0.4528083, 52.6993402), (-0.4518933, 52.698...          3
        1  3681043  6101  ...  [(-0.6531215, 52.5730787), (-0.6531793, 52.572...          3
        2  3693985  6101  ...  [(-0.7323403, 52.6782102), (-0.7319059, 52.678...          3
        3  3693986  6101  ...  [(-0.6173072, 52.6132317), (-0.6241869, 52.614...          3
        4  4806329  6101  ...  [(-0.4576926, 52.7035194), (-0.4565358, 52.702...          3
        [5 rows x 9 columns]

        >>> # Set `emulate_gpd` to be True
        >>> rutland_railways_shp = read_shp_file(path_to_rutland_railways_shp, emulate_gpd=True)

        >>> rutland_railways_shp.head()
            osm_id  code  ... tunnel                                           geometry
        0  2162114  6101  ...      F  LINESTRING (-0.4528083 52.6993402, -0.4518933 ...
        1  3681043  6101  ...      F  LINESTRING (-0.6531215 52.5730787, -0.6531793 ...
        2  3693985  6101  ...      F  LINESTRING (-0.7323403000000001 52.6782102, -0...
        3  3693986  6101  ...      F  LINESTRING (-0.6173071999999999 52.6132317, -0...
        4  4806329  6101  ...      F  LINESTRING (-0.4576926 52.7035194, -0.4565358 ...
        [5 rows x 8 columns]

        >>> # Alternatively, set `method` to be 'gpd' to use GeoPandas
        >>> rutland_railways_shp_ = read_shp_file(path_to_rutland_railways_shp, method='gpd')

        >>> rutland_railways_shp_.head()
            osm_id  code  ... tunnel                                           geometry
        0  2162114  6101  ...      F  LINESTRING (-0.45281 52.69934, -0.45189 52.698...
        1  3681043  6101  ...      F  LINESTRING (-0.65312 52.57308, -0.65318 52.572...
        2  3693985  6101  ...      F  LINESTRING (-0.73234 52.67821, -0.73191 52.678...
        3  3693986  6101  ...      F  LINESTRING (-0.61731 52.61323, -0.62419 52.614...
        4  4806329  6101  ...      F  LINESTRING (-0.45769 52.70352, -0.45654 52.702...
        [5 rows x 8 columns]

        >>> len(rutland_railways_shp) == len(rutland_railways_shp_)
        True

        >>> # Delete the extracted shapefiles
        >>> delete_dir(path_to_rutland_shp_dir, verbose=True)
        The directory "tests\\rutland-latest-free-shp\\" is not empty.
        Confirmed to delete it? [No]|Yes: yes
        Deleting "tests\\rutland-latest-free-shp\\" ... Done.

        >>> # Delete the downloaded shapefile
        >>> os.remove(path_to_rutland_shp_zip)
    """

    if method == 'pyshp':  # default
        # Read .shp file using shapefile.Reader()
        shp_reader = pyshp.Reader(path_to_shp, **kwargs)

        # Transform the data to a DataFrame
        filed_names = [field[0] for field in shp_reader.fields[1:]]
        shp_data = pd.DataFrame(shp_reader.records(), columns=filed_names)

        # # Clean data
        # shp_data['name'] = shp_data.name.str.encode('utf-8').str.decode('utf-8')
        shape_info_colnames = ['coordinates', 'shape_type']
        shape_info = pd.DataFrame(
            ((s.points, s.shapeType) for s in shp_reader.iterShapes()), index=shp_data.index,
            columns=shape_info_colnames)

        shp_reader.close()

        if emulate_gpd:
            shape_type_geom_dict = get_shp_shape_types_geom_dict()

            shp_data['geometry'] = shape_info[shape_info_colnames].apply(
                lambda x: getattr(shapely.geometry, shape_type_geom_dict[x[1]])(x[0]), axis=1)

        else:
            shp_data = shp_data.join(shape_info)

    else:  # method in ('geopandas', 'gpd')
        import geopandas as gpd

        shp_data = gpd.read_file(path_to_shp, **kwargs)

    return shp_data


def get_epsg4326_wgs84_crs_ref(as_str=False):
    """
    Get reference of EPSG Projection 4326 - WGS 84
    (`EPSG:4326 <https://spatialreference.org/ref/epsg/wgs-84/>`_) for the setting of
    `CRS <https://en.wikipedia.org/wiki/Spatial_reference_system>`_ for saving shapefile data.

    :param as_str: whether to return the reference as a string type
    :type as_str: bool
    :return: reference of EPSG Projection 4326 - WGS 84 (in Proj4 format)
    :rtype: dict or str

    **Example**::

        >>> from pydriosm.reader import get_epsg4326_wgs84_crs_ref

        >>> shp_crs = get_epsg4326_wgs84_crs_ref()
        >>> print(shp_crs)
        {'proj': 'longlat', 'ellps': 'WGS84', 'datum': 'WGS84', 'no_defs': True}

        >>> shp_crs = get_epsg4326_wgs84_crs_ref(as_str=True)
        >>> print(shp_crs)
        +proj=longlat +ellps=WGS84 +datum=WGS84 +no_defs
    """

    crs = {'proj': 'longlat', 'ellps': 'WGS84', 'datum': 'WGS84', 'no_defs': True}

    if as_str:
        crs = '+proj=longlat +ellps=WGS84 +datum=WGS84 +no_defs'

    return crs


def get_epsg4326_wgs84_prj_ref():
    """
    Get reference of EPSG Projection 4326 - WGS 84
    (`EPSG:4326 <https://spatialreference.org/ref/epsg/wgs-84/>`_)
    for saving shapefile projection data.

    :return: reference of EPSG Projection 4326 - WGS 84 (in ESRI WKT format)
    :rtype: str

    **Example**::

        >>> from pydriosm.reader import get_epsg4326_wgs84_prj_ref

        >>> epsg4326_wgs84_prj_ref = get_epsg4326_wgs84_prj_ref()
        >>> print(epsg4326_wgs84_prj_ref)
        GEOGCS["GCS_WGS_1984",DATUM["D_WGS_1984",SPHEROID["WGS_1984",6378137,298.257223563]],...

    .. seealso::

        Source: https://spatialreference.org/ref/epsg/4326/esriwkt/
    """

    epsg4326_wgs84_esri_wkt = \
        'GEOGCS["GCS_WGS_1984",DATUM["D_WGS_1984",SPHEROID["WGS_1984",6378137,298.257223563]],' \
        'PRIMEM["Greenwich",0],UNIT["Degree",0.017453292519943295]]'

    return epsg4326_wgs84_esri_wkt


def make_pyshp_fields(shp_data, field_names, decimal_precision):
    """
    Make fields data for writing shapefiles by `pyshp <https://github.com/GeospatialPython/pyshp>`_.

    :param shp_data: .shp data
    :type shp_data: pandas.DataFrame
    :param field_names: names of fields to be written as shapefile records
    :type field_names: list or pandas.Index
    :param decimal_precision: decimal precision for writing float records
    :type decimal_precision: int
    :return: list of records in the .shp data
    :rtype: list
    """

    dtype_shp_type = {
        'object': 'C',
        'int64': 'N',
        'int32': 'N',
        'float64': 'F',
        'float32': 'F',
        'bool': 'L',
        'datetime64': 'D',
    }

    fields = []

    for field_name, dtype, in shp_data[field_names].dtypes.items():

        if dtype.name == 'object':
            max_size = shp_data[field_name].map(len).max()
        else:
            max_size = shp_data[field_name].astype(str).map(len).max()

        if 'float' in dtype.name:
            decimal = decimal_precision
        else:
            decimal = 0

        fields.append((field_name, dtype_shp_type[dtype.name], max_size, decimal))

    return fields


def write_to_shapefile(shp_data, path_to_shp, decimal_precision=5, prj_file=True):
    """
    Save .shp data as a shapefile by `pyshp <https://github.com/GeospatialPython/pyshp>`_.

    :param shp_data: .shp data
    :type shp_data: pandas.DataFrame
    :param path_to_shp: path where the .shp data is saved
    :type path_to_shp: str
    :param decimal_precision: decimal precision for writing float records, defaults to ``5``
    :type decimal_precision: int
    :param prj_file: whether to create a .prj projection file for the shapefile, defaults to ``True``
    :type prj_file: bool

    **Example**::

        >>> import os
        >>> import glob
        >>> from pyhelpers.dir import cd, delete_dir
        >>> from pydriosm.downloader import GeofabrikDownloader
        >>> from pydriosm.reader import read_shp_file, unzip_shp_zip, write_to_shapefile

        >>> # Download the .shp.zip file of Rutland as an example
        >>> geofabrik_downloader = GeofabrikDownloader()

        >>> sr_name = 'Rutland'

        >>> path_to_rutland_shp_zip = geofabrik_downloader.download_osm_data(
        ...     sr_name, osm_file_format=".shp", download_dir="tests",
        ...     confirmation_required=False, ret_download_path=True)

        >>> # Extract the downloaded .shp.zip file
        >>> rutland_shp_dir = unzip_shp_zip(path_to_rutland_shp_zip, layer_names='railways',
        ...                                 ret_extract_dir=True)

        >>> railways_shp_filename = glob.glob1(rutland_shp_dir, "*.shp")[0]
        >>> path_to_railways_shp = cd(rutland_shp_dir, railways_shp_filename)

        >>> # Read the .shp file
        >>> rutland_railways_shp = read_shp_file(path_to_railways_shp)

        >>> # Save the railways data as "tests\\rutland\\railways.shp"
        >>> save_shp_path = "tests\\rutland\\railways"  # with or without the extension ".shp"
        >>> write_to_shapefile(rutland_railways_shp, save_shp_path)

        >>> # Read the saved the .shp file
        >>> rutland_railways_shp_ = read_shp_file(save_shp_path)

        >>> # Check if the retrieved .shp data is equal to the original one
        >>> rutland_railways_shp_.equals(rutland_railways_shp)
        True

        >>> # Delete the extracted data files
        >>> delete_dir(rutland_shp_dir, confirmation_required=False, verbose=True)
        Deleting "tests\\rutland-latest-free-shp\\" ... Done.
        >>> delete_dir("tests\\rutland", confirmation_required=False, verbose=True)
        Deleting "tests\\rutland\\" ... Done.

        >>> # Delete the downloaded shapefile
        >>> os.remove(path_to_rutland_shp_zip)
    """

    w = pyshp.Writer(path_to_shp)

    field_names, shape_info_colnames = shp_data.columns[0:-2], shp_data.columns[-2:]

    w.fields = make_pyshp_fields(
        shp_data=shp_data, field_names=field_names, decimal_precision=decimal_precision)

    w.shapeType = shp_data.shape_type.unique()[0]

    for i in shp_data.index:
        w.record(*shp_data.loc[i, field_names].values.tolist())
        w.shape(pyshp.Shape(shapeType=w.shapeType, points=shp_data.loc[i, 'coordinates']))

    w.close()

    if prj_file:
        prj_filename = "{}.prj".format(os.path.splitext(path_to_shp)[0])
        prj = open(prj_filename, "w")
        prj.write(get_epsg4326_wgs84_prj_ref())
        prj.close()


def parse_layer_shp(path_to_layer_shp, feature_names=None, crs=None, save_fclass_shp=False,
                    driver='ESRI Shapefile', ret_path_to_fclass_shp=False, **kwargs):
    """
    Parse a layer of OSM shapefile data.

    :param path_to_layer_shp: path(s) to one (or multiple) shapefile(s)
    :type path_to_layer_shp: str or list
    :param feature_names: class name(s) of feature(s), defaults to ``None``
    :type feature_names: str or list or None
    :param crs: specification of coordinate reference system; if ``None`` (default),
        check :py:func:`specify_shp_crs()<pydriosm.reader.specify_shp_crs>`
    :type crs: dict
    :param save_fclass_shp: (when ``fclass`` is not ``None``)
        whether to save data of the ``fclass`` as shapefile, defaults to ``False``
    :type save_fclass_shp: bool
    :param driver: the OGR format driver, defaults to ``'ESRI Shapefile'``;
        see also the ``driver`` parameter of `geopandas.GeoDataFrame.to_file()`_
    :type driver: str
    :param ret_path_to_fclass_shp: (when ``save_fclass_shp`` is ``True``)
        whether to return the path to the saved data of ``fclass``, defaults to ``False``
    :type ret_path_to_fclass_shp: bool
    :param kwargs: optional parameters of :py:func:`read_shp_file()<pydriosm.reader.read_shp_file>`
    :return: parsed shapefile data
    :rtype: geopandas.GeoDataFrame

    .. _`geopandas.GeoDataFrame.to_file()`:
        https://geopandas.org/reference.html#geopandas.GeoDataFrame.to_file

    **Examples**::

        >>> import os
        >>> from pyhelpers.dir import cd, delete_dir
        >>> from pydriosm.downloader import GeofabrikDownloader
        >>> from pydriosm.reader import parse_layer_shp, unzip_shp_zip

        >>> # Download the .shp.zip file of Rutland as an example
        >>> geofabrik_downloader = GeofabrikDownloader()

        >>> sr_name = 'Rutland'

        >>> path_to_rutland_shp_zip = geofabrik_downloader.download_osm_data(
        ...     sr_name, osm_file_format=".shp", download_dir="tests",
        ...     confirmation_required=False, ret_download_path=True)

        >>> # Extract the downloaded .shp.zip file
        >>> rutland_shp_dir = unzip_shp_zip(path_to_rutland_shp_zip, ret_extract_dir=True)
        >>> path_to_railways_shp = cd(rutland_shp_dir, "gis_osm_railways_free_1.shp")

        >>> # Parse the 'railways' layer
        >>> rutland_railways_shp = parse_layer_shp(path_to_railways_shp)

        >>> rutland_railways_shp.head()
            osm_id  code  ...                                        coordinates shape_type
        0  2162114  6101  ...  [(-0.4528083, 52.6993402), (-0.4518933, 52.698...          3
        1  3681043  6101  ...  [(-0.6531215, 52.5730787), (-0.6531793, 52.572...          3
        2  3693985  6101  ...  [(-0.7323403, 52.6782102), (-0.7319059, 52.678...          3
        3  3693986  6101  ...  [(-0.6173072, 52.6132317), (-0.6241869, 52.614...          3
        4  4806329  6101  ...  [(-0.4576926, 52.7035194), (-0.4565358, 52.702...          3
        [5 rows x 9 columns]

        >>> rutland_railways_rail, path_to_rutland_railways_rail = parse_layer_shp(
        ...     path_to_railways_shp, feature_names='rail', save_fclass_shp=True,
        ...     ret_path_to_fclass_shp=True)

        >>> rutland_railways_rail.head()
            osm_id  code  ...                                        coordinates shape_type
        0  2162114  6101  ...  [(-0.4528083, 52.6993402), (-0.4518933, 52.698...          3
        1  3681043  6101  ...  [(-0.6531215, 52.5730787), (-0.6531793, 52.572...          3
        2  3693985  6101  ...  [(-0.7323403, 52.6782102), (-0.7319059, 52.678...          3
        3  3693986  6101  ...  [(-0.6173072, 52.6132317), (-0.6241869, 52.614...          3
        4  4806329  6101  ...  [(-0.4576926, 52.7035194), (-0.4565358, 52.702...          3
        [5 rows x 9 columns]

        >>> print(os.path.relpath(path_to_rutland_railways_rail))
        tests\\rutland-latest-free-shp\\railways\\gis_osm_railways_free_1_rail.shp

        >>> # Delete the extracted data files
        >>> delete_dir(rutland_shp_dir, verbose=True)
        The directory "tests\\rutland-latest-free-shp\\" is not empty.
        Confirmed to delete it? [No]|Yes: yes
        Deleting "tests\\rutland-latest-free-shp\\" ... Done.

        >>> # Delete the downloaded shapefile
        >>> os.remove(path_to_rutland_shp_zip)
    """

    paths_to_lyr_shp = [path_to_layer_shp] if isinstance(path_to_layer_shp, str) \
        else copy.copy(path_to_layer_shp)

    if len(paths_to_lyr_shp) == 0:
        shp_data = None

    else:
        if len(paths_to_lyr_shp) == 1:
            path_to_lyr_shp = paths_to_lyr_shp[0]
            # gpd.GeoDataFrame(read_shp_file(path_to_shp))
            shp_data = read_shp_file(path_to_lyr_shp, **kwargs)
        else:
            shp_data = [read_shp_file(path_to_lyr_shp, **kwargs) for path_to_lyr_shp in paths_to_lyr_shp]
            shp_data = pd.concat(shp_data, axis=0, ignore_index=True)

        if feature_names:
            f_col_name = [x for x in shp_data.columns if x in ('type', 'fclass')][0]

            feat_names_ = [feature_names] if isinstance(feature_names, str) else feature_names.copy()
            valid_features = shp_data[f_col_name].unique().tolist()
            # import warnings
            # if any(f for f in feat_names if f not in valid_features):
            #     warnings.warn(f"`feat_names` must belong to {valid_features}")
            feat_names = [find_similar_str(x, valid_features) for x in feat_names_]

            shp_data = shp_data.query('{} in @feat_names'.format(f_col_name))

            if save_fclass_shp:
                path_to_lyr_shp = paths_to_lyr_shp[0].replace("_a_", "_")
                path_to_lyr_feat_shp = append_fclass_to_filename(path_to_lyr_shp, feat_names)

                if isinstance(shp_data, pd.DataFrame):
                    write_to_shapefile(shp_data, path_to_shp=path_to_lyr_feat_shp)
                else:
                    # assert isinstance(shp_data, gpd.GeoDataFrame)
                    if crs is None:
                        crs = get_epsg4326_wgs84_crs_ref()
                    shp_data.crs = crs
                    shp_data.to_file(path_to_lyr_feat_shp, driver=driver)

                if ret_path_to_fclass_shp:
                    shp_data = shp_data, path_to_lyr_feat_shp

    return shp_data


def merge_shps(paths_to_shp_files, path_to_merged_dir, method='pyshp'):
    """
    Merge multiple shapefiles.

    :param paths_to_shp_files: list of paths to shapefiles (in .shp format)
    :type paths_to_shp_files: list
    :param path_to_merged_dir: path to a directory where the merged files are to be saved
    :type path_to_merged_dir: str
    :param method: the method used to merge/save shapefiles;
        options include: ``'pyshp'`` (default) and ``'geopandas'`` (or ``'gpd'``)
        if ``method='geopandas'``, this function relies on `geopandas.GeoDataFrame.to_file()`_;
        otherwise, it by default uses `shapefile.Writer()`_
    :type method: str

    .. _`shapefile.Writer()`:
        https://github.com/GeospatialPython/pyshp#writing-shapefiles
    .. _`geopandas.GeoDataFrame.to_file()`:
        https://geopandas.org/reference.html#geopandas.GeoDataFrame.to_file

    .. note::

        If ``method`` is set to be ``'geopandas'`` (or ``'gpd'``), it requires availability of
        the package `GeoPandas <https://geopandas.org/>`_.

    .. seealso::

        - The example for the function :py:func:`merge_layer_shps()<pydriosm.reader.merge_layer_shps>`.
        - Resource: https://github.com/GeospatialPython/pyshp
    """

    if method == 'pyshp':
        w = pyshp.Writer(path_to_merged_dir)

        for f in paths_to_shp_files:
            r = pyshp.Reader(f)
            w.fields = r.fields[1:]  # skip first deletion field
            w.shapeType = r.shapeType
            for shaperec in r.iterShapeRecords():
                w.record(*shaperec.record)
                w.shape(shaperec.shape)
            r.close()

        w.close()

        prj_filename = os.path.join(path_to_merged_dir, "{}.prj".format(os.path.basename(path_to_merged_dir)))
        prj = open(prj_filename, "w")
        prj.write(get_epsg4326_wgs84_prj_ref())
        prj.close()

    else:  # method in ('geopandas', 'gpd')
        import geopandas as gpd

        shp_data, geom_types = [], []
        for shp_file_path in paths_to_shp_files:
            shp_dat = gpd.read_file(shp_file_path)
            shp_data.append(shp_dat)
            geom_types.append(shp_dat['geometry'].type[0])

        geom_types_ = list(set(geom_types))

        crs = get_epsg4326_wgs84_crs_ref()

        if len(geom_types_) > 1:
            shp_data_dict = collections.defaultdict(list)
            for geo_typ, shp_dat in zip(geom_types, shp_data):
                shp_data_dict[geo_typ].append(shp_dat)

            for k, v in shp_data_dict.items():
                shp_data_ = pd.concat(v, ignore_index=True)
                shp_data_.crs = crs
                shp_data_.to_file(filename=path_to_merged_dir + f"_{k.lower()}", driver="ESRI Shapefile")

        else:
            merged_shp_data = pd.concat(shp_data, ignore_index=True)
            merged_shp_data.crs = crs
            merged_shp_data.to_file(filename=path_to_merged_dir, driver="ESRI Shapefile")


def merge_layer_shps(paths_to_shp_zip_files, layer_name, method='pyshp',
                     rm_zip_extracts=True, merged_shp_dir=None, rm_shp_temp=True, verbose=False,
                     ret_merged_shp_path=False):
    """
    Merge shapefiles over a layer for multiple geographic regions.

    :param paths_to_shp_zip_files: list of paths to data of shapefiles (in .shp.zip format)
    :type paths_to_shp_zip_files: list
    :param layer_name: name of a layer (e.g. 'railways')
    :type layer_name: str
    :param method: the method used to merge/save shapefiles;
        options include: ``'pyshp'`` (default) and ``'geopandas'`` (or ``'gpd'``)
        if ``method='geopandas'``, this function relies on `geopandas.GeoDataFrame.to_file()`_;
        otherwise, it by default uses `shapefile.Writer()`_
    :type method: str
    :param rm_zip_extracts: whether to delete the extracted files, defaults to ``False``
    :type rm_zip_extracts: bool
    :param rm_shp_temp: whether to delete temporary layer files, defaults to ``False``
    :type rm_shp_temp: bool
    :param merged_shp_dir: if ``None`` (default), use the layer name as the name of the folder
        where the merged .shp files will be saved
    :type merged_shp_dir: str or None
    :param verbose: whether to print relevant information in console as the function runs,
        defaults to ``False``
    :type verbose: bool or int
    :param ret_merged_shp_path: whether to return the path to the merged .shp file, defaults to ``False``
    :type ret_merged_shp_path: bool
    :return: the path to the merged file when ``ret_merged_shp_path=True``
    :rtype: list or str

    .. _`geopandas.GeoDataFrame.to_file()`:
        https://geopandas.org/reference.html#geopandas.GeoDataFrame.to_file
    .. _`shapefile.Writer()`:
        https://github.com/GeospatialPython/pyshp#writing-shapefiles

    .. note::

        This function does not create projection (.prj) for the merged map
        (see also [`MMS-1 <https://code.google.com/archive/p/pyshp/wikis/CreatePRJfiles.wiki>`_])

        For valid ``layer_name``,
        check :py:func:`get_valid_shp_layer_names()<pydriosm.utils.get_valid_shp_layer_names>`.

    .. _pydriosm-reader-merge_layer_shps:

    **Example**::

        >>> import os
        >>> from pyhelpers.dir import delete_dir
        >>> from pydriosm.downloader import GeofabrikDownloader
        >>> from pydriosm.reader import merge_layer_shps, read_shp_file

        >>> # To merge 'railways' layers of Greater Manchester and West Yorkshire"

        >>> geofabrik_downloader = GeofabrikDownloader()

        >>> sr_names = ['Greater Manchester', 'West Yorkshire']
        >>> dat_dir = "tests"

        >>> shp_zip_file_paths = geofabrik_downloader.download_osm_data(
        ...     sr_names, osm_file_format=".shp", download_dir=dat_dir,
        ...     confirmation_required=False, ret_download_path=True, verbose=True)
        Downloading "greater-manchester-latest-free.shp.zip" to "tests\\" ... Done.
        Downloading "west-yorkshire-latest-free.shp.zip" to "tests\\" ... Done.

        >>> lyr_name = 'railways'

        >>> merged_shp_path = merge_layer_shps(shp_zip_file_paths, layer_name=lyr_name,
        ...                                    verbose=True, ret_merged_shp_path=True)
        Extracting the following layer(s):
            'railways'
        from "tests\\greater-manchester-latest-free.shp.zip" ...
        to "tests\\greater-manchester-latest-free-shp\\"
        Done.
        Extracting the following layer(s):
            'railways'
        from "tests\\west-yorkshire-latest-free.shp.zip" ...
        to "tests\\west-yorkshire-latest-free-shp\\"
        Done.
        Merging the following shapefiles:
            "greater-manchester_gis_osm_railways_free_1.shp"
            "west-yorkshire_gis_osm_railways_free_1.shp"
        In progress ... Done.
        Find the merged shapefile at "tests\\greater-manchester_west-yorkshire_railways\\".

        >>> print(os.path.relpath(merged_shp_path))
        tests\\greater-manchester_west-yorksh...\\greater-manchester_west-yorkshire_railways.shp

        >>> # Read the merged .shp file
        >>> merged_shp_data = read_shp_file(merged_shp_path)

        >>> # Delete the merged shapefile
        >>> delete_dir(os.path.dirname(merged_shp_path), verbose=True)
        The directory "tests\\greater-manchester_west-yorkshire_railways\\" is not empty.
        Confirmed to delete it? [No]|Yes: yes
        Deleting "tests\\greater-manchester_west-yorkshire_railways\\" ... Done.

        >>> # Delete the downloaded shapefiles
        >>> for shp_zip_file_path in shp_zip_file_paths:
        ...     os.remove(shp_zip_file_path)

    .. seealso::

        The examples for the method :py:meth:`GeofabrikReader.merge_subregion_layer_shp()
        <pydriosm.reader.GeofabrikReader.merge_subregion_layer_shp>`.
    """

    path_to_extract_dirs = []
    for path_to_shp_zip in paths_to_shp_zip_files:
        extract_dir = unzip_shp_zip(
            path_to_shp_zip=path_to_shp_zip, layer_names=layer_name, verbose=verbose, ret_extract_dir=True)
        path_to_extract_dirs.append(extract_dir)

    region_names = [
        re.search(r'.*(?=\.shp\.zip)', os.path.basename(x).replace("-latest-free", "")).group(0)
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

    # Get the paths to the target .shp files
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

        merge_shps(
            paths_to_shp_files=paths_to_shp_files, path_to_merged_dir=path_to_merged_dir, method=method)

        if method == 'pyshp':
            temp_dir = os.path.dirname(path_to_merged_dir)
            paths_to_output_files_temp_ = [
                glob.glob(cd(temp_dir, f"{prefix}*.{ext}")) for ext in ("dbf", "shp", "shx")]
            paths_to_output_files_temp = list(itertools.chain.from_iterable(paths_to_output_files_temp_))

            for temp_output_file in paths_to_output_files_temp:
                output_file = cd(path_to_merged_dir, os.path.basename(temp_output_file).replace(suffix, ""))
                shutil.move(temp_output_file, output_file)

        else:  # method in ('geopandas', 'gpd')
            if not os.listdir(path_to_merged_dir):
                temp_dirs = []
                for temp_output_file in glob.glob(cd(path_to_merged_dir + "*", f"{prefix}*")):
                    output_file = cd(path_to_merged_dir_temp.replace(suffix, ""))
                    shutil.move(temp_output_file, output_file)
                    temp_dirs.append(os.path.dirname(temp_output_file))

                for temp_dir in set(temp_dirs):
                    shutil.rmtree(temp_dir)

        if verbose:
            print("Done.")

        if rm_zip_extracts:
            for path_to_extract_dir in path_to_extract_dirs:
                shutil.rmtree(path_to_extract_dir)

        if rm_shp_temp:
            shutil.rmtree(path_to_merged_dir_temp)

        if verbose:
            print("Find the merged shapefile at \"{}\\\".".format(
                os.path.relpath(path_to_merged_dir)))

        if ret_merged_shp_path:
            path_to_merged_shp = glob.glob(cd(f"{path_to_merged_dir}*", "*.shp"))
            if len(path_to_merged_shp) == 1:
                path_to_merged_shp = path_to_merged_shp[0]
            return path_to_merged_shp

    except Exception as e:
        if verbose:
            print("Failed. {}".format(e))


# == .csv.xz =================================================================================

def parse_csv_xz(path_to_csv_xz, col_names=None):
    """
    Parse a compressed CSV (.csv.xz) data file.

    :param path_to_csv_xz: path to a .csv.xz data file
    :type path_to_csv_xz: str
    :param col_names: column names of .csv.xz data, defaults to ``None``
    :type col_names: list or None
    :return: tabular data of the CSV file
    :rtype: pandas.DataFrame

    See the example for the method
    :py:meth:`BBBikeReader.read_csv_xz()<pydriosm.reader.BBBikeReader.read_csv_xz>`.
    """

    csv_xz_raw = lzma.open(path_to_csv_xz, mode='rt', encoding='utf-8').readlines()

    # noinspection PyTypeChecker
    csv_xz_dat = [x.rstrip('\t\n').split('\t') for x in csv_xz_raw]

    if col_names is None:
        col_names = ['type', 'id', 'feature']

    csv_xz = pd.DataFrame.from_records(csv_xz_dat, columns=col_names)

    return csv_xz


# == .geojson.xz =============================================================================

def parse_geojson_xz(path_to_geojson_xz, fmt_geom=False):
    """
    Parse a compressed Osmium GeoJSON (.geojson.xz) data file.

    :param path_to_geojson_xz: path to a .geojson.xz data file
    :type path_to_geojson_xz: str
    :param fmt_geom: whether to reformat coordinates into a geometric object, defaults to ``False``
    :type fmt_geom: bool
    :return: tabular data of the Osmium GeoJSON file
    :rtype: pandas.DataFrame

    See the example for the method :py:meth:`BBBikeReader.read_geojson_xz()
    <pydriosm.reader.BBBikeReader.read_geojson_xz>`.
    """

    geojson_xz_raw = rapidjson.load(lzma.open(path_to_geojson_xz, mode='rt', encoding='utf-8'))

    geojson_xz_dat = pd.DataFrame.from_dict(geojson_xz_raw)

    feature_types = geojson_xz_dat.features.map(lambda x: x['type']).to_frame(name='feature_name')

    geom_types = geojson_xz_dat.features.map(lambda x: x['geometry']['type']).to_frame(name='geom_types')

    if fmt_geom:

        def reformat_geom(geo_typ, coords):
            sub_geom_type_func = getattr(shapely.geometry, geo_typ)
            if geo_typ == 'MultiPolygon':
                polygon_geom = getattr(shapely.geometry, 'Polygon')
                geom_coords = sub_geom_type_func(polygon_geom(y) for x in coords for y in x)
            else:
                geom_coords = sub_geom_type_func(coords)
            return geom_coords

        coordinates = geojson_xz_dat.features.map(
            lambda x: reformat_geom(
                x['geometry']['type'], x['geometry']['coordinates'])).to_frame(name='coordinates')

    else:
        coordinates = geojson_xz_dat.features.map(
            lambda x: x['geometry']['coordinates']).to_frame(name='coordinates')

    properties = geojson_xz_dat.features.map(lambda x: x['properties']).to_frame(name='properties')

    # decode_properties=False
    #
    # :param decode_properties: whether to transform a 'properties' dictionary into
    #   tabular form, defaults to ``False``
    # :type decode_properties: bool
    #
    # if decode_properties:
    #     if confirmed("Confirmed to decode \"properties\"\n"
    #                  "(Note this can be very computationally expensive and costing "
    #                  "fairly large amount of memory)?"):
    #         properties = pd.concat(properties['properties'].map(pd.json_normalize).to_list())

    geojson_xz_data = pd.concat([feature_types, geom_types, coordinates, properties], axis=1)

    del feature_types, geom_types, coordinates, properties
    gc.collect()

    return geojson_xz_data


# == Readers classes =========================================================================

class GeofabrikReader:
    """
    Read Geofabrik data extracts.

    :param max_tmpfile_size: defaults to ``5000``,
        see also :py:func:`gdal_configurations()<pydriosm.settings.gdal_configurations>`
    :type max_tmpfile_size: int or None
    :param data_dir: (a path or a name of) a directory where a data file is;
        if ``None`` (default), a folder ``osm_geofabrik`` under the current working directory
    :type data_dir: str or None

    :ivar GeofabrikDownloader Downloader: instance of the class
        :py:class:`GeofabrikDownloader<pydriosm.downloader.GeofabrikDownloader>`
    :ivar str Name: name of the data resource
    :ivar str URL: URL of the homepage to the Geofabrik free download server

    **Example**::

        >>> from pydriosm.reader import GeofabrikReader

        >>> geofabrik_reader = GeofabrikReader()

        >>> print(geofabrik_reader.Name)
        Geofabrik OpenStreetMap data extracts
    """

    def __init__(self, max_tmpfile_size=5000, data_dir=None):
        """
        Constructor method.
        """
        self.Downloader = GeofabrikDownloader(download_dir=data_dir)
        self.Name = self.Downloader.Name
        self.URL = self.Downloader.URL

        if max_tmpfile_size:
            gdal_configurations(max_tmpfile_size=max_tmpfile_size)

    # noinspection PyPep8Naming
    @property
    def DataDir(self):
        return self.Downloader.DownloadDir

    def get_path_to_osm_file(self, subregion_name, osm_file_format, data_dir=None):
        """
        Get the local path to an OSM data file of a geographic region.

        :param subregion_name: name of a geographic region (case-insensitive)
            that is available on Geofabrik free download server
        :type subregion_name: str
        :param osm_file_format: file format of the OSM data available on the free download server
        :type osm_file_format: str
        :param data_dir: directory where the data file of the ``subregion_name`` is located/saved;
            if ``None`` (default), the default local directory
        :type data_dir: str or None
        :return: path to PBF (.osm.pbf) file
        :rtype: str or None

        **Example**::

            >>> import os
            >>> from pydriosm.reader import GeofabrikReader

            >>> geofabrik_reader = GeofabrikReader()

            >>> region_name = 'Rutland'
            >>> file_format = ".pbf"

            >>> path_to_rutland_pbf = geofabrik_reader.get_path_to_osm_file(
            ...     region_name, file_format)

            >>> print(path_to_rutland_pbf)
            # (if "rutland-latest.osm.pbf" is unavailable at the package data directory)
            # None

            >>> # Specify a download directory
            >>> dwnld_dir = "tests"

            >>> # Download the PBF data file of Rutland to "tests\\"
            >>> geofabrik_reader.Downloader.download_osm_data(
            ...     region_name, file_format, download_dir=dwnld_dir, verbose=True)
            To download .osm.pbf data of the following geographic region(s):
                Rutland
            ? [No]|Yes: yes
            Downloading "rutland-latest.osm.pbf" to "tests\\" ... Done.

            >>> path_to_rutland_pbf = geofabrik_reader.get_path_to_osm_file(
            ...     region_name, file_format, data_dir=dwnld_dir)
            >>> print(os.path.relpath(path_to_rutland_pbf))
            tests\\rutland-latest.osm.pbf

            >>> # Delete the downloaded PBF data file
            >>> os.remove(path_to_rutland_pbf)
        """

        osm_pbf_filename_, path_to_osm_pbf_ = self.Downloader.get_default_path_to_osm_file(
            subregion_name, osm_file_format=osm_file_format, mkdir=False)

        if data_dir is None:  # Go to default file path
            path_to_osm_pbf = path_to_osm_pbf_

        else:
            osm_pbf_dir = validate_input_data_dir(data_dir)
            path_to_osm_pbf = os.path.join(osm_pbf_dir, osm_pbf_filename_)

        if not os.path.isfile(path_to_osm_pbf):
            path_to_osm_pbf = None

        return path_to_osm_pbf

    def get_osm_pbf_layer_names(self, subregion_name, data_dir=None):
        """
        Get indices and names of all layers in the PBF data file of a given (sub)region.

        :param subregion_name: name of a geographic region (case-insensitive)
            that is available on Geofabrik free download server
        :type subregion_name: str
        :param data_dir:
        :type data_dir:
        :return: indices and names of each layer of the PBF data file
        :rtype: dict

        **Example**::

            >>> import os
            >>> from pydriosm.reader import GeofabrikReader

            >>> geofabrik_reader = GeofabrikReader()

            >>> # Download the PBF data file of Rutland to "tests\\"
            >>> path_to_rutland_pbf = geofabrik_reader.Downloader.download_osm_data(
            ...     subregion_names='Rutland', osm_file_format=".pbf", download_dir="tests",
            ...     confirmation_required=False, ret_download_path=True)

            >>> lyr_idx_names = geofabrik_reader.get_osm_pbf_layer_names(path_to_rutland_pbf)

            >>> lyr_idx_names
            {0: 'points',
             1: 'lines',
             2: 'multilinestrings',
             3: 'multipolygons',
             4: 'other_relations'}
        """

        if data_dir is None:
            data_dir = self.DataDir

        path_to_osm_pbf = self.get_path_to_osm_file(
            subregion_name=subregion_name, osm_file_format=".osm.pbf", data_dir=data_dir)

        layer_idx_names = get_osm_pbf_layer_names(path_to_osm_pbf)

        return layer_idx_names

    def read_osm_pbf(self, subregion_name, data_dir=None, chunk_size_limit=50,
                     parse_raw_feat=False, transform_geom=False, transform_other_tags=False,
                     update=False, download_confirmation_required=True, pickle_it=False,
                     ret_pickle_path=False, rm_osm_pbf=False, verbose=False, **kwargs):
        """
        Read a PBF (.osm.pbf) data file of a geographic region.

        :param subregion_name: name of a geographic region (case-insensitive)
            that is available on Geofabrik free download server
        :type subregion_name: str
        :param data_dir: directory where the .osm.pbf data file is located/saved;
            if ``None``, the default local directory
        :type data_dir: str or None
        :param chunk_size_limit: threshold (in MB) that triggers the use of chunk parser, defaults to ``50``;
            if the size of the .osm.pbf file (in MB) is greater than ``chunk_size_limit``,
            it will be parsed in a chunk-wise way
        :type chunk_size_limit: int
        :param parse_raw_feat: whether to parse each feature in the raw data, defaults to ``False``
        :type parse_raw_feat: bool
        :param transform_geom: whether to transform a single coordinate
            (or a collection of coordinates) into a geometric object, defaults to ``False``
        :type transform_geom: bool
        :param transform_other_tags: whether to transform a ``'other_tags'`` into a dictionary,
            defaults to ``False``
        :type transform_other_tags: bool
        :param update: whether to check to update pickle backup (if available), defaults to ``False``
        :type update: bool
        :param download_confirmation_required: whether to ask for confirmation
            before starting to download a file, defaults to ``True``
        :type download_confirmation_required: bool
        :param pickle_it: whether to save the .pbf data as a .pickle file, defaults to ``False``
        :type pickle_it: bool
        :param ret_pickle_path: (when ``pickle_it=True``)
            whether to return a path to the saved pickle file
        :type ret_pickle_path: bool
        :param rm_osm_pbf: whether to delete the downloaded .osm.pbf file, defaults to ``False``
        :type rm_osm_pbf: bool
        :param verbose: whether to print relevant information in console as the function runs,
            defaults to ``False``
        :type verbose: bool or int
        :param kwargs: optional parameters of :py:func:`parse_osm_pbf()<pydriosm.reader.parse_osm_pbf>`
        :return: dictionary of the .osm.pbf data;
            when ``pickle_it=True``, return a tuple of the dictionary and a path to the pickle file
        :rtype: dict or tuple or None

        .. _pydriosm-reader-geofabrik-read_osm_pbf:

        **Examples**::

            >>> import os
            >>> from pydriosm.reader import GeofabrikReader

            >>> geofabrik_reader = GeofabrikReader()

            >>> sr_name = 'Rutland'
            >>> dat_dir = "tests"

            >>> # If the PBF data of Rutland is not available at the specified data directory,
            >>> # the function may ask whether to download the latest data
            >>> rutland_pbf_raw = geofabrik_reader.read_osm_pbf(sr_name, dat_dir, verbose=True)
            To download .osm.pbf data of the following geographic region(s):
                Rutland
            ? [No]|Yes: yes
            Downloading "rutland-latest.osm.pbf" to "tests\\" ... Done.

            >>> list(rutland_pbf_raw.keys())
            ['points', 'lines', 'multilinestrings', 'multipolygons', 'other_relations']

            >>> rutland_pbf_raw_points = rutland_pbf_raw['points']
            >>> rutland_pbf_raw_points.head()
                                                          points
            0  {"type": "Feature", "geometry": {"type": "Poin...
            1  {"type": "Feature", "geometry": {"type": "Poin...
            2  {"type": "Feature", "geometry": {"type": "Poin...
            3  {"type": "Feature", "geometry": {"type": "Poin...
            4  {"type": "Feature", "geometry": {"type": "Poin...

            >>> # Set `parse_raw_feat` to be True
            >>> rutland_pbf_parsed = geofabrik_reader.read_osm_pbf(sr_name, dat_dir,
            ...                                                    parse_raw_feat=True,
            ...                                                    verbose=True)
            Parsing "tests\\rutland-latest.osm.pbf" ... Done.

            >>> rutland_pbf_parsed_points = rutland_pbf_parsed['points']
            >>> rutland_pbf_parsed_points.head()
                     id               coordinates  ...                    other_tags
            0    488432  [-0.5134241, 52.6555853]  ...               "odbl"=>"clean"
            1    488658  [-0.5313354, 52.6737716]  ...                          None
            2  13883868  [-0.7229332, 52.5889864]  ...                          None
            3  14049101  [-0.7249922, 52.6748223]  ...  "traffic_calming"=>"cushion"
            4  14558402  [-0.7266686, 52.6695051]  ...      "direction"=>"clockwise"
            [5 rows x 12 columns]

            >>> # Set both `parse_raw_feat` and `transform_geom` to be True
            >>> rutland_pbf_parsed_1 = geofabrik_reader.read_osm_pbf(sr_name, dat_dir,
            ...                                                      parse_raw_feat=True,
            ...                                                      transform_geom=True,
            ...                                                      verbose=True)
            Parsing "tests\\rutland-latest.osm.pbf" ... Done.

            >>> rutland_pbf_parsed_1_points = rutland_pbf_parsed_1['points']
            >>> rutland_pbf_parsed_1_points[['coordinates', 'other_tags']].head()
                                          coordinates                    other_tags
            0           POINT (-0.5134241 52.6555853)               "odbl"=>"clean"
            1           POINT (-0.5313354 52.6737716)                          None
            2  POINT (-0.7229332000000001 52.5889864)                          None
            3           POINT (-0.7249816 52.6748426)  "traffic_calming"=>"cushion"
            4           POINT (-0.7266581 52.6695058)      "direction"=>"clockwise"

            >>> # Set `parse_raw_feat` `transform_geom` and `transform_other_tags` to be True
            >>> rutland_pbf_parsed_2 = geofabrik_reader.read_osm_pbf(sr_name, dat_dir,
            ...                                                      parse_raw_feat=True,
            ...                                                      transform_geom=True,
            ...                                                      transform_other_tags=True,
            ...                                                      verbose=True)
            Parsing "tests\\rutland-latest.osm.pbf" ... Done.

            >>> rutland_pbf_parsed_2_points = rutland_pbf_parsed_2['points']
            >>> rutland_pbf_parsed_2_points[['coordinates', 'other_tags']].head()
                                          coordinates                      other_tags
            0           POINT (-0.5134241 52.6555853)               {'odbl': 'clean'}
            1           POINT (-0.5313354 52.6737716)                            None
            2  POINT (-0.7229332000000001 52.5889864)                            None
            3           POINT (-0.7249816 52.6748426)  {'traffic_calming': 'cushion'}
            4           POINT (-0.7266581 52.6695058)      {'direction': 'clockwise'}

            >>> # Delete the downloaded PBF data file
            >>> os.remove(os.path.join(dat_dir, "rutland-latest.osm.pbf"))
        """

        osm_file_format = ".osm.pbf"

        assert isinstance(chunk_size_limit, int) or chunk_size_limit is None

        osm_pbf_filename, path_to_osm_pbf_ = self.Downloader.get_default_path_to_osm_file(
            subregion_name, osm_file_format=osm_file_format, mkdir=False)

        if osm_pbf_filename and path_to_osm_pbf_:
            if not data_dir:  # Go to default file path
                path_to_osm_pbf = path_to_osm_pbf_
            else:
                osm_pbf_dir = validate_input_data_dir(data_dir)
                path_to_osm_pbf = os.path.join(osm_pbf_dir, osm_pbf_filename)

            path_to_pickle = path_to_osm_pbf.replace(
                osm_file_format, "-pbf.pickle" if parse_raw_feat else "-raw.pickle")
            if os.path.isfile(path_to_pickle) and not update:
                osm_pbf_data = load_pickle(path_to_pickle)

                if ret_pickle_path:
                    osm_pbf_data = osm_pbf_data, path_to_pickle

            else:
                if not os.path.isfile(path_to_osm_pbf) or update:
                    # If the target file is not available, try downloading it first.
                    self.Downloader.download_osm_data(
                        subregion_names=subregion_name, osm_file_format=osm_file_format,
                        download_dir=data_dir, update=update,
                        confirmation_required=download_confirmation_required, verbose=verbose)

                if verbose and parse_raw_feat:
                    print("Parsing \"{}\"".format(os.path.relpath(path_to_osm_pbf)), end=" ... ")
                try:
                    number_of_chunks = get_number_of_chunks(path_to_osm_pbf, chunk_size_limit)

                    osm_pbf_data = parse_osm_pbf(
                        path_to_osm_pbf=path_to_osm_pbf, parse_raw_feat=parse_raw_feat,
                        transform_geom=transform_geom, transform_other_tags=transform_other_tags,
                        number_of_chunks=number_of_chunks, **kwargs)

                    print("Done.") if verbose and parse_raw_feat else ""

                    if pickle_it:
                        save_pickle(osm_pbf_data, path_to_pickle, verbose=verbose)

                        if ret_pickle_path:
                            osm_pbf_data = osm_pbf_data, path_to_pickle

                    if rm_osm_pbf:
                        remove_subregion_osm_file(path_to_osm_pbf, verbose=verbose)

                except Exception as e:
                    if verbose:
                        print("Failed. {}".format(e))
                    osm_pbf_data = None

            return osm_pbf_data

        else:
            print("Errors occur. Data might not be available for the \"subregion_name\".")

    def get_path_to_osm_shp(self, subregion_name, layer_name=None, feature_name=None, data_dir=None,
                            file_ext=".shp"):
        """
        Get path(s) to .shp file(s) for a geographic region (by searching a local data directory).

        :param subregion_name: name of a geographic region (case-insensitive)
            that is available on Geofabrik free download server
        :type subregion_name: str
        :param layer_name: name of a .shp layer (e.g. ``'railways'``), defaults to ``None``
        :type layer_name: str or None
        :param feature_name: name of a feature (e.g. ``'rail'``);
            if ``None`` (default), all available features included
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

            >>> region_name = 'Rutland'
            >>> file_format = ".shp"

            >>> # (if "gis.osm_railways_free_1.shp" is unavailable)
            >>> path_to_shp_file = geofabrik_reader.get_path_to_osm_shp(region_name)
            >>> print(path_to_shp_file)
            []

            >>> dwnld_dir = "tests"

            >>> # Download the shapefiles of Rutland
            >>> path_to_rutland_shp_zip = geofabrik_reader.Downloader.download_osm_data(
            ...     region_name, file_format, dwnld_dir, confirmation_required=False,
            ...     ret_download_path=True)

            >>> # Extract the downloaded .zip file
            >>> unzip_shp_zip(path_to_rutland_shp_zip, verbose=True)
            Extracting "tests\\rutland-latest-free.shp.zip" ...
            to "tests\\rutland-latest-free-shp\\"
            Done.

            >>> lyr_name = 'railways'

            >>> # Get the file path of 'railways' shapefile
            >>> path_to_rutland_railways_shp = geofabrik_reader.get_path_to_osm_shp(
            ...     region_name, lyr_name, data_dir=dwnld_dir)

            >>> print(os.path.relpath(path_to_rutland_railways_shp))
            tests\\rutland-latest-free-shp\\gis_osm_railways_free_1.shp

            >>> feat_name = 'rail'

            >>> # Get/save shapefile data of features labelled 'rail' only
            >>> _ = parse_layer_shp(path_to_rutland_railways_shp, feature_names=feat_name,
            ...                     save_fclass_shp=True)

            >>> # Get the file path to the data of 'rail'
            >>> path_to_rutland_railways_rail_shp = geofabrik_reader.get_path_to_osm_shp(
            ...     region_name, lyr_name, feat_name, data_dir=dwnld_dir)

            >>> print(os.path.relpath(path_to_rutland_railways_rail_shp))
            tests\\rutland-latest-free-shp\\railways\\gis_osm_railways_free_1_rail.shp

            >>> # Retrieve the data of 'rail' feature
            >>> rutland_railways_rail_shp = parse_layer_shp(path_to_rutland_railways_rail_shp)

            >>> rutland_railways_rail_shp.head()
                osm_id  code  ...                                        coordinates shape_type
            0  2162114  6101  ...  [(-0.4528083, 52.6993402), (-0.4518933, 52.698...          3
            1  3681043  6101  ...  [(-0.6531215, 52.5730787), (-0.6531793, 52.572...          3
            2  3693985  6101  ...  [(-0.7323403, 52.6782102), (-0.7319059, 52.678...          3
            3  3693986  6101  ...  [(-0.6173072, 52.6132317), (-0.6241869, 52.614...          3
            4  4806329  6101  ...  [(-0.4576926, 52.7035194), (-0.4565358, 52.702...          3
            [5 rows x 9 columns]

            >>> # Delete the extracted files
            >>> delete_dir(os.path.dirname(path_to_rutland_railways_shp), verbose=True)
            The directory "tests\\rutland-latest-free-shp\\" is not empty.
            Confirmed to delete it? [No]|Yes: yes
            Deleting "tests\\rutland-latest-free-shp\\" ... Done.

            >>> # Delete the downloaded .shp.zip file
            >>> os.remove(path_to_rutland_shp_zip)
        """

        if data_dir is None:  # Go to default file path
            _, path_to_shp_zip = self.Downloader.get_default_path_to_osm_file(
                subregion_name=subregion_name, osm_file_format=".shp.zip", mkdir=False)
        else:
            shp_zip_filename = self.Downloader.get_default_osm_filename(
                subregion_name=subregion_name, osm_file_format=".shp.zip")
            path_to_shp_zip = cd(validate_input_data_dir(data_dir), shp_zip_filename)
        shp_dir = os.path.splitext(path_to_shp_zip)[0].replace(".", "-")

        if layer_name is None:
            path_to_osm_shp_file = glob.glob(shp_dir + "\\*" + file_ext)
        else:
            layer_name_ = find_similar_str(str_x=layer_name, lookup_list=get_valid_shp_layer_names())
            base_pat = 'gis_osm_{}(_a)?(_free)?(_1)?'.format(layer_name_)
            if feature_name is None:
                pat = re.compile(r"{}{}".format(base_pat, file_ext))
                path_to_osm_shp_file = [
                    f for f in glob.glob(cd(shp_dir, f"*{file_ext}")) if re.search(pat, f)
                ]
            else:
                pat = re.compile(r"{}_{}".format(base_pat, feature_name, file_ext))
                path_to_osm_shp_file = [
                    f for f in glob.glob(cd(shp_dir, layer_name_, f"*{file_ext}")) if re.search(pat, f)
                ]

        # if not osm_file_paths: print("The required file may not exist.")

        if len(path_to_osm_shp_file) == 1:
            path_to_osm_shp_file = path_to_osm_shp_file[0]

        return path_to_osm_shp_file

    def merge_subregion_layer_shp(self, subregion_names, layer_name, data_dir=None, method='pyshp',
                                  update=False, download_confirmation_required=True, rm_zip_extracts=True,
                                  merged_shp_dir=None, rm_shp_temp=True, verbose=False,
                                  ret_merged_shp_path=False):
        """
        Merge shapefiles for a specific layer of two or multiple geographic regions.

        :param subregion_names: names of geographic region (case-insensitive)
            that is available on Geofabrik free download server
        :type subregion_names: list
        :param layer_name: name of a layer (e.g. 'railways')
        :type layer_name: str
        :param method: the method used to merge/save shapefiles;
            options include: ``'pyshp'`` (default) and ``'geopandas'`` (or ``'gpd'``)
            if ``method='geopandas'``, this function relies on `geopandas.GeoDataFrame.to_file()`_;
            otherwise, it by default uses `shapefile.Writer()`_
        :type method: str
        :param update: whether to update the source .shp.zip files, defaults to ``False``
        :type update: bool
        :param download_confirmation_required: whether to ask for confirmation
            before starting to download a file, defaults to ``True``
        :type download_confirmation_required: bool
        :param data_dir: directory where the .shp.zip data files are located/saved;
            if ``None`` (default), the default directory
        :type data_dir: str or None
        :param rm_zip_extracts: whether to delete the extracted files, defaults to ``False``
        :type rm_zip_extracts: bool
        :param rm_shp_temp: whether to delete temporary layer files, defaults to ``False``
        :type rm_shp_temp: bool
        :param merged_shp_dir: if ``None`` (default), use the layer name
            as the name of the folder where the merged .shp files will be saved
        :type merged_shp_dir: str or None
        :param verbose: whether to print relevant information in console, defaults to ``False``
        :type verbose: bool or int
        :param ret_merged_shp_path: whether to return the path to the merged .shp file, defaults to ``False``
        :type ret_merged_shp_path: bool
        :return: the path to the merged file when ``ret_merged_shp_path=True``
        :rtype: list or str

        .. _`geopandas.GeoDataFrame.to_file()`:
            https://geopandas.org/reference.html#geopandas.GeoDataFrame.to_file
        .. _`shapefile.Writer()`:
            https://github.com/GeospatialPython/pyshp#writing-shapefiles

        .. _pydriosm-GeofabrikReader-merge_subregion_layer_shp:

        **Examples**::

            >>> import os
            >>> from pyhelpers.dir import cd, delete_dir
            >>> from pydriosm.reader import GeofabrikReader, read_shp_file

            >>> geofabrik_reader = GeofabrikReader()

            >>> # -- Example 1 ---------------------------------------------------------------

            >>> # To merge 'railways' of Greater Manchester and West Yorkshire
            >>> sr_names = ['Manchester', 'West Yorkshire']
            >>> lyr_name = 'railways'
            >>> dat_dir = "tests"

            >>> path_to_merged_shp_file = geofabrik_reader.merge_subregion_layer_shp(
            ...     sr_names, lyr_name, dat_dir, verbose=True, ret_merged_shp_path=True)
            Downloading "greater-manchester-latest-free.shp.zip" to "tests\\" ... Done.
            Downloading "west-yorkshire-latest-free.shp.zip" to "tests\\" ... Done.
            Extracting the following layer(s):
                'railways'
            from "tests\\greater-manchester-latest-free.shp.zip" ...
            to "tests\\greater-manchester-latest-free-shp\\"
            Done.
            Extracting the following layer(s):
                'railways'
            from "tests\\west-yorkshire-latest-free.shp.zip" ...
            to "tests\\west-yorkshire-latest-free-shp\\"
            Done.
            Merging the following shapefiles:
                "greater-manchester_gis_osm_railways_free_1.shp"
                "west-yorkshire_gis_osm_railways_free_1.shp"
            In progress ... Done.
            Find the merged shapefile at "tests\\greater-manchester_west-yorkshire_railways\\".

            >>> print(os.path.relpath(path_to_merged_shp_file))
            tests\\...\\greater-manchester_west-yorkshire_railways.shp

            >>> # Read the merged data
            >>> manchester_yorkshire_railways_shp = read_shp_file(path_to_merged_shp_file)

            >>> manchester_yorkshire_railways_shp.head()
                osm_id  code  ...                                        coordinates shape_type
            0   928999  6101  ...  [(-2.2844594, 53.4802681), (-2.2851997, 53.480...          3
            1   929904  6101  ...  [(-2.2919566, 53.4619298), (-2.2924877, 53.461...          3
            2   929905  6102  ...  [(-2.2794048, 53.4605819), (-2.2799773, 53.460...          3
            3  3663332  6102  ...  [(-2.2382517, 53.4818141), (-2.2381708, 53.481...          3
            4  3996086  6101  ...  [(-2.6003908, 53.4602313), (-2.6009371, 53.459...          3
            [5 rows x 9 columns]

            >>> # Delete the merged files
            >>> delete_dir(os.path.dirname(path_to_merged_shp_file), verbose=True)
            The directory "tests\\greater-manchester_west-yorkshire_railways" is not empty.
            Confirmed to delete it? [No]|Yes: yes
            Deleting "tests\\greater-manchester_west-yorkshire_railways" ... Done.

            >>> # Delete the downloaded .shp.zip data files
            >>> os.remove(cd(dat_dir, "greater-manchester-latest-free.shp.zip"))
            >>> os.remove(cd(dat_dir, "west-yorkshire-latest-free.shp.zip"))

            >>> # -- Example 2 ---------------------------------------------------------------

            >>> # To merge 'transport' of Greater London, Kent and Surrey

            >>> sr_names = ['London', 'Kent', 'Surrey']
            >>> lyr_name = 'transport'

            >>> path_to_merged_shp_file = geofabrik_reader.merge_subregion_layer_shp(
            ...     sr_names, lyr_name, dat_dir, verbose=True, ret_merged_shp_path=True)
            To download .shp.zip data of the following geographic region(s):
                Greater London
                Kent
                Surrey
            ? [No]|Yes: yes
            Downloading "greater-london-latest-free.shp.zip" to "tests\\" ... Done.
            Downloading "kent-latest-free.shp.zip" to "tests\\" ... Done.
            Downloading "surrey-latest-free.shp.zip" to "tests\\" ... Done.
            Extracting the following layer(s):
                'transport'
            from "tests\\greater-london-latest-free.shp.zip" ...
            to "tests\\greater-london-latest-free-shp\\"
            Done.
            Extracting the following layer(s):
                'transport'
            from "tests\\kent-latest-free.shp.zip" ...
            to "tests\\kent-latest-free-shp\\"
            Done.
            Extracting the following layer(s):
                'transport'
            from "tests\\surrey-latest-free.shp.zip" ...
            to "tests\\surrey-latest-free-shp\\"
            Done.
            Merging the following shapefiles:
                "greater-london_gis_osm_transport_a_free_1.shp"
                "greater-london_gis_osm_transport_free_1.shp"
                "kent_gis_osm_transport_a_free_1.shp"
                "kent_gis_osm_transport_free_1.shp"
                "surrey_gis_osm_transport_a_free_1.shp"
                "surrey_gis_osm_transport_free_1.shp"
            In progress ... Done.
            Find the merged .shp file(s) at "tests\\greater-london_kent_surrey_transport\\".

            >>> print(os.path.relpath(path_to_merged_shp_file))
            tests\\...\\greater-london_kent_surrey_transport.shp

            >>> # Read the merged shapefile
            >>> merged_transport_shp = read_shp_file(path_to_merged_shp_file)

            >>> merged_transport_shp.head()
                 osm_id  ...  shape_type
            0   5077928  ...           5
            1   8610280  ...           5
            2  15705264  ...           5
            3  23077379  ...           5
            4  24016945  ...           5
            [5 rows x 6 columns]

            >>> # Delete the merged files
            >>> delete_dir(os.path.dirname(path_to_merged_shp_file), verbose=True)
            The directory "tests\\greater-london_kent_surrey_transport\\" is not empty.
            Confirmed to delete it? [No]|Yes: >? yes
            Deleting "tests\\greater-london_kent_surrey_transport\\" ... Done.

            >>> # Delete the downloaded .shp.zip data files
            >>> os.remove(cd(dat_dir, "greater-london-latest-free.shp.zip"))
            >>> os.remove(cd(dat_dir, "kent-latest-free.shp.zip"))
            >>> os.remove(cd(dat_dir, "surrey-latest-free.shp.zip"))
        """

        # Make sure all the required shape files are ready
        layer_name_ = find_similar_str(str_x=layer_name, lookup_list=get_valid_shp_layer_names())
        subregion_names_ = [self.Downloader.validate_input_subregion_name(x) for x in subregion_names]

        osm_file_format = ".shp.zip"

        # Download the files (if not available)
        paths_to_shp_zip_files = self.Downloader.download_osm_data(
            subregion_names_, osm_file_format=osm_file_format, download_dir=data_dir,
            update=update, confirmation_required=download_confirmation_required,
            deep_retry=True, interval=None, verbose=verbose, ret_download_path=True)

        if all(os.path.isfile(path_to_shp_zip_file) for path_to_shp_zip_file in paths_to_shp_zip_files):
            path_to_merged_shp = merge_layer_shps(
                paths_to_shp_zip_files=paths_to_shp_zip_files, layer_name=layer_name_, method=method,
                rm_zip_extracts=rm_zip_extracts, merged_shp_dir=merged_shp_dir, rm_shp_temp=rm_shp_temp,
                verbose=verbose, ret_merged_shp_path=ret_merged_shp_path)

            if ret_merged_shp_path:
                return path_to_merged_shp

    def read_shp_zip(self, subregion_name, layer_names=None, feature_names=None, data_dir=None,
                     update=False, download_confirmation_required=True, pickle_it=False,
                     ret_pickle_path=False, rm_extracts=False, rm_shp_zip=False, verbose=False):
        """
        Read a .shp.zip data file of a geographic region.

        :param subregion_name: name of a geographic region (case-insensitive)
            that is available on Geofabrik free download server
        :type subregion_name: str
        :param layer_names: name of a .shp layer, e.g. 'railways', or names of multiple layers;
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
        :param download_confirmation_required: whether to ask for confirmation
            before starting to download a file, defaults to ``True``
        :type download_confirmation_required: bool
        :param pickle_it: whether to save the .shp data as a .pickle file, defaults to ``False``
        :type pickle_it: bool
        :param ret_pickle_path: (when ``pickle_it=True``)
            whether to return a path to the saved pickle file
        :type ret_pickle_path: bool
        :param rm_extracts: whether to delete extracted files from the .shp.zip file, defaults to ``False``
        :type rm_extracts: bool
        :param rm_shp_zip: whether to delete the downloaded .shp.zip file, defaults to ``False``
        :type rm_shp_zip: bool
        :param verbose: whether to print relevant information in console as the function runs,
            defaults to ``False``
        :type verbose: bool or int
        :return: dictionary of the shapefile data, with keys and values being layer names and tabular data
            (in the format of `geopandas.GeoDataFrame`_), respectively
        :rtype: dict or None

        .. _`geopandas.GeoDataFrame`: https://geopandas.org/reference.html#geodataframe

        **Example**::

            >>> from pydriosm.reader import GeofabrikReader

            >>> geofabrik_reader = GeofabrikReader()

            >>> sr_name = 'Rutland'
            >>> dat_dir = "tests"

            >>> rutland_shp = geofabrik_reader.read_shp_zip(
            ...     subregion_name=sr_name, data_dir=dat_dir, verbose=True)
            To download .shp.zip data of the following geographic region(s):
                Rutland
            ? [No]|Yes: yes
            Downloading "rutland-latest-free.shp.zip" to "tests\\" ... Done.
            Extracting "tests\\rutland-latest-free.shp.zip" ...
            to "tests\\rutland-latest-free-shp\\"
            Done.

            >>> list(rutland_shp.keys())
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

            >>> # Data of the 'railways' layer
            >>> rutland_shp_railways = rutland_shp['railways']
            >>> rutland_shp_railways.head()
                osm_id  code  ...                                        coordinates shape_type
            0  2162114  6101  ...  [(-0.4528083, 52.6993402), (-0.4518933, 52.698...          3
            1  3681043  6101  ...  [(-0.6531215, 52.5730787), (-0.6531793, 52.572...          3
            2  3693985  6101  ...  [(-0.7323403, 52.6782102), (-0.7319059, 52.678...          3
            3  3693986  6101  ...  [(-0.6173072, 52.6132317), (-0.6241869, 52.614...          3
            4  4806329  6101  ...  [(-0.4576926, 52.7035194), (-0.4565358, 52.702...          3
            [5 rows x 9 columns]

            >>> # Read data of the 'transport' layer only from the original .shp.zip file
            >>> # (and delete any extracts)
            >>> sr_layer = 'transport'

            >>> rutland_shp_transport = geofabrik_reader.read_shp_zip(sr_name, sr_layer,
            ...                                                       data_dir=dat_dir,
            ...                                                       verbose=True,
            ...                                                       rm_extracts=True)
            Deleting the extracts "tests\\rutland-latest-free-shp\\"  ... Done.

            >>> list(rutland_shp_transport.keys())
            ['transport']

            >>> rutland_shp_transport['transport'].head()
                  osm_id  ...  shape_type
            0  232038062  ...           5
            1  468873547  ...           5
            2  468873548  ...           5
            3  468873553  ...           5
            4  468873559  ...           5
            [5 rows x 6 columns]

            >>> # Read data of only the 'bus_stop' feature (in the 'transport' layer)
            >>> # from the original .shp.zip file (and delete any extracts)
            >>> feat_name = 'bus_stop'

            >>> rutland_bus_stop = geofabrik_reader.read_shp_zip(sr_name, sr_layer, feat_name,
            ...                                                  dat_dir, verbose=True,
            ...                                                  rm_extracts=True)
            Extracting the following layer(s):
                'transport'
            from "tests\\rutland-latest-free.shp.zip" ...
            to "tests\\rutland-latest-free-shp\\"
            Done.
            Deleting the extracts "tests\\rutland-latest-free-shp\\"  ... Done.

            >>> list(rutland_bus_stop.keys())
            ['transport']

            >>> print(rutland_bus_stop['transport'].fclass.unique())
            ['bus_stop']

            >>> # Read multiple features of multiple layers
            >>> # (and delete both the original .shp.zip file and extracts)
            >>> sr_layers = ['traffic', 'roads']
            >>> feat_names = ['parking', 'trunk']

            >>> rutland_shp_tr_pt = geofabrik_reader.read_shp_zip(sr_name, sr_layers, feat_name,
            ...                                                   dat_dir, verbose=True,
            ...                                                   rm_extracts=True,
            ...                                                   rm_shp_zip=True)
            Extracting the following layer(s):
                'traffic'
                'roads'
            from "tests\\rutland-latest-free.shp.zip" ...
            to "tests\\rutland-latest-free-shp\\"
            Done.
            Deleting the extracts "tests\\rutland-latest-free-shp\\"  ... Done.
            Deleting "tests\\rutland-latest-free.shp.zip" ... Done.

            >>> list(rutland_shp_tr_pt.keys())
            ['traffic', 'roads']

            >>> # Data of the 'traffic' layer
            >>> rutland_shp_tr_pt_traffic = rutland_shp_tr_pt['traffic']
            >>> rutland_shp_tr_pt_traffic.head()
                     osm_id  code  ...                 coordinates shape_type
            204    14558402  5202  ...  [[-0.7266581, 52.6695058]]          1
            206    14583750  5202  ...  [[-0.4704691, 52.6548803]]          1
            213    18335108  5202  ...  [[-0.7384552, 52.6674072]]          1
            255   862120532  5202  ...  [[-0.7320612, 52.6688328]]          1
            291  1584865939  5202  ...   [[-0.7391079, 52.674775]]          1
            [5 rows x 6 columns]

            >>> # Data of the 'roads' layer
            >>> rutland_shp_tr_pt_roads = rutland_shp_tr_pt['roads']
            >>> rutland_shp_tr_pt_roads.head()
                     osm_id  ...  shape_type
            1320   73599134  ...           3
            1321   73599136  ...           3
            1557  101044857  ...           3
            1561  101044867  ...           3
            1682  101326487  ...           3
            [5 rows x 12 columns]
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
                sub_fname = "-".join(
                    x for x in [filename_] + layer_names_ + (feature_names_ if feature_names_ else []) if x)
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
                        self.Downloader.download_osm_data(
                            subregion_names=subregion_name, osm_file_format=osm_file_format,
                            download_dir=data_dir, update=update,
                            confirmation_required=download_confirmation_required, verbose=verbose)

                    unzip_shp_zip(path_to_shp_zip=path_to_shp_zip, path_to_extract_dir=path_to_extract_dir,
                                  layer_names=layer_names_, verbose=verbose)

                    if not layer_names_:
                        layer_names_ = list(set(
                            [find_shp_layer_name(x) for x in os.listdir(cd(path_to_extract_dir))
                             if x != 'README']
                        ))

                else:
                    unavailable_layers = []

                    layer_names_temp_ = [
                        find_shp_layer_name(x) for x in os.listdir(cd(path_to_extract_dir)) if x != 'README'
                    ]
                    layer_names_temp = list(set(layer_names_ + layer_names_temp_))

                    for lyr_name in layer_names_temp:
                        shp_filename = self.get_path_to_osm_shp(subregion_name=subregion_name,
                                                                layer_name=lyr_name, data_dir=data_dir)
                        if not shp_filename:
                            unavailable_layers.append(lyr_name)

                    if unavailable_layers:
                        if not os.path.exists(path_to_shp_zip):
                            self.Downloader.download_osm_data(
                                subregion_names=subregion_name, osm_file_format=osm_file_format,
                                download_dir=data_dir, update=update,
                                confirmation_required=download_confirmation_required, verbose=verbose)

                        unzip_shp_zip(path_to_shp_zip=path_to_shp_zip,
                                      path_to_extract_dir=path_to_extract_dir, layer_names=unavailable_layers,
                                      verbose=verbose)

                    if not layer_names_:
                        layer_names_ = layer_names_temp

                paths_to_layers_shp = [
                    glob.glob(cd(path_to_extract_dir, r"gis_osm_{}_*.shp".format(layer_name)))
                    for layer_name in layer_names_
                ]
                paths_to_layers_shp = [x for x in paths_to_layers_shp if x]

                shp_data_ = [parse_layer_shp(p, feature_names=feature_names_) for p in paths_to_layers_shp]

                shp_data = dict(zip(layer_names_, shp_data_))

                if pickle_it:
                    save_pickle(shp_data, path_to_shp_pickle, verbose=verbose)

                    if ret_pickle_path:
                        shp_data = shp_data, path_to_shp_pickle

                if os.path.exists(path_to_extract_dir) and rm_extracts:
                    if verbose:
                        print("Deleting the extracts \"{}\\\" ".format(os.path.relpath(path_to_extract_dir)),
                              end=" ... ")
                    try:
                        # for f in glob.glob(os.path.join(extract_dir, "gis_osm*")):
                        #     # if layer not in f:
                        #     os.remove(f)
                        shutil.rmtree(path_to_extract_dir)
                        if verbose:
                            print("Done.")
                    except Exception as e:
                        if verbose:
                            print("Failed. {}".format(e))

                if os.path.isfile(path_to_shp_zip) and rm_shp_zip:
                    remove_subregion_osm_file(path_to_shp_zip, verbose=verbose)

        else:
            shp_data = None

        return shp_data


class BBBikeReader:
    """
    Read BBBike data extracts.

    :param max_tmpfile_size: defaults to ``5000``,
        see also :py:func:`gdal_configurations()<pydriosm.settings.gdal_configurations>`
    :type max_tmpfile_size: int or None
    :param data_dir: (a path or a name of) a directory where a data file is;
        if ``None`` (default), a folder ``osm_bbbike`` under the current working directory
    :type data_dir: str or None

    :ivar BBBikeDownloader Downloader: instance of the class
        :py:class:`BBBikeDownloader<pydriosm.downloader.BBBikeDownloader>`
    :ivar str Name: name of the data resource
    :ivar str URL: URL of the homepage to the BBBike free download server

    **Example**::

        >>> from pydriosm.reader import BBBikeReader

        >>> bbbike_reader = BBBikeReader()

        >>> print(bbbike_reader.Name)
        BBBike OpenStreetMap data extracts
    """

    def __init__(self, max_tmpfile_size=5000, data_dir=None):
        """
        Constructor method.
        """
        self.Downloader = BBBikeDownloader(download_dir=data_dir)
        self.Name = copy.copy(self.Downloader.Name)
        self.URL = copy.copy(self.Downloader.URL)

        if max_tmpfile_size:
            gdal_configurations(max_tmpfile_size=max_tmpfile_size)

    # noinspection PyPep8Naming
    @property
    def DataDir(self):
        return self.Downloader.DownloadDir

    def get_path_to_osm_file(self, subregion_name, osm_file_format, data_dir=None):
        """
        Get the path to an OSM data file (if available) of a specific file format
        for a geographic region.

        :param subregion_name: name of a geographic region (case-insensitive)
            that is available on BBBike free download server
        :type subregion_name: str
        :param osm_file_format: format (file extension) of an OSM data
        :type osm_file_format: str
        :param data_dir: directory where the data file is located/saved;
            if ``None`` (default), the default directory
        :type data_dir: str or None
        :return: path to the data file
        :rtype: str or None

        **Example**::

            >>> import os
            >>> from pydriosm.reader import BBBikeReader

            >>> bbbike_reader = BBBikeReader()

            >>> region_name = 'Leeds'
            >>> file_format = ".pbf"
            >>> dat_dir = "tests"

            >>> path_to_leeds_pbf = bbbike_reader.Downloader.download_osm_data(
            ...     region_name, file_format, dat_dir, verbose=True, ret_download_path=True)
            To download .pbf data of the following geographic region(s):
                Leeds
            ? [No]|Yes: yes
            Downloading "Leeds.osm.pbf" to "tests\\" ... Done.

            >>> path_to_leeds_pbf_ = bbbike_reader.get_path_to_osm_file(
            ...     region_name, file_format, dat_dir)
            >>> print(os.path.relpath(path_to_leeds_pbf_))
            tests\\Leeds.osm.pbf

            >>> print(path_to_leeds_pbf == path_to_leeds_pbf_)
            True

            >>> # Delete the downloaded PBF data file
            >>> os.remove(path_to_leeds_pbf_)
        """

        _, _, _, path_to_file = self.Downloader.get_valid_download_info(
            subregion_name=subregion_name, osm_file_format=osm_file_format, download_dir=data_dir)

        return path_to_file

    def read_osm_pbf(self, subregion_name, data_dir=None, chunk_size_limit=50, parse_raw_feat=False,
                     transform_geom=False, transform_other_tags=False, update=False,
                     download_confirmation_required=True, pickle_it=False, ret_pickle_path=False,
                     rm_osm_pbf=False, verbose=False, **kwargs):
        """
        Read a PBF data file of a geographic region.

        :param subregion_name: name of a geographic region (case-insensitive)
            that is available on BBBike free download server
        :type subregion_name: str
        :param data_dir: directory where the PBF data file is saved;
            if ``None`` (default), the default directory
        :type data_dir: str or None
        :param chunk_size_limit: threshold (in MB) that triggers the use of chunk parser, defaults to ``50``;
            if the size of the .osm.pbf file (in MB) is greater than ``chunk_size_limit``,
            it will be parsed in a chunk-wise way
        :type chunk_size_limit: int
        :param parse_raw_feat: whether to parse each feature in the raw data, defaults to ``False``
        :type parse_raw_feat: bool
        :param transform_geom: whether to transform a single coordinate
            (or a collection of coordinates) into a geometric object, defaults to ``False``
        :type transform_geom: bool
        :param transform_other_tags: whether to transform a ``'other_tags'`` into a dictionary,
            defaults to ``False``
        :type transform_other_tags: bool
        :param update: whether to check to update pickle backup (if available), defaults to ``False``
        :type update: bool
        :param download_confirmation_required: whether to ask for confirmation
            before starting to download a file, defaults to ``True``
        :type download_confirmation_required: bool
        :param pickle_it: whether to save the .pbf data as a .pickle file, defaults to ``False``
        :type pickle_it: bool
        :param ret_pickle_path: (when ``pickle_it=True``)
            whether to return a path to the saved pickle file
        :type ret_pickle_path: bool
        :param rm_osm_pbf: whether to delete the downloaded .osm.pbf file, defaults to ``False``
        :type rm_osm_pbf: bool
        :param verbose: whether to print relevant information in console, defaults to ``False``
        :type verbose: bool or int
        :param kwargs: optional parameters of :py:func:`parse_osm_pbf()<pydriosm.reader.parse_osm_pbf>`
        :return: dictionary of the .osm.pbf data;
            when ``pickle_it=True``, return a tuple of the dictionary and a path to the pickle file
        :rtype: dict or tuple or None

        **Example**::

            >>> import os
            >>> from pyhelpers.dir import cd
            >>> from pydriosm.reader import BBBikeReader

            >>> bbbike_reader = BBBikeReader()

            >>> region_name = 'Leeds'
            >>> dat_dir = "tests"

            >>> # (Parsing the data in this example might take up to a few minutes.)
            >>> leeds_osm_pbf = bbbike_reader.read_osm_pbf(region_name, dat_dir,
            ...                                            parse_raw_feat=True,
            ...                                            transform_geom=True,
            ...                                            transform_other_tags=True,
            ...                                            verbose=True)
            To download .pbf data of the following geographic region(s):
                Leeds
            ? [No]|Yes: yes
            Downloading "Leeds.osm.pbf" to "tests\\" ... Done.
            Parsing "tests\\Leeds.osm.pbf" ... Done.

            >>> list(leeds_osm_pbf.keys())
            ['points', 'lines', 'multilinestrings', 'multipolygons', 'other_relations']

            >>> # Data of the 'multipolygons' layer
            >>> leeds_osm_pbf_multipolygons = leeds_osm_pbf['multipolygons']

            >>> leeds_osm_pbf_multipolygons.head()
                  id                                        coordinates  ... tourism other_tags
            0  10595  (POLYGON ((-1.5030223 53.6725382, -1.5034495 5...  ...    None       None
            1  10600  (POLYGON ((-1.5116994 53.6764287, -1.5099361 5...  ...    None       None
            2  10601  (POLYGON ((-1.5142403 53.6710831, -1.5143686 5...  ...    None       None
            3  10612  (POLYGON ((-1.5129341 53.6704885, -1.5131883 5...  ...    None       None
            4  10776  (POLYGON ((-1.5523801 53.7029081, -1.5522831 5...  ...    None       None
            [5 rows x 27 columns]

            >>> # Delete the downloaded PBF data file
            >>> os.remove(cd(dat_dir, "Leeds.osm.pbf"))
        """

        assert isinstance(chunk_size_limit, int) or chunk_size_limit is None

        osm_file_format = ".osm.pbf"

        path_to_osm_pbf = self.get_path_to_osm_file(subregion_name, osm_file_format, data_dir)

        path_to_pickle = path_to_osm_pbf.replace(
            ".osm.pbf", "-pbf.pickle" if parse_raw_feat else "-raw.pickle")
        if os.path.isfile(path_to_pickle) and not update:
            osm_pbf_data = load_pickle(path_to_pickle)

            if ret_pickle_path:
                osm_pbf_data = osm_pbf_data, path_to_pickle

        else:
            if not os.path.isfile(path_to_osm_pbf):
                path_to_osm_pbf = self.Downloader.download_osm_data(
                    subregion_names=subregion_name, osm_file_format=osm_file_format, download_dir=data_dir,
                    confirmation_required=download_confirmation_required, verbose=verbose,
                    ret_download_path=True)

            if verbose and parse_raw_feat:
                print("Parsing \"{}\"".format(os.path.relpath(path_to_osm_pbf)), end=" ... ")

            try:
                number_of_chunks = get_number_of_chunks(
                    path_to_file=path_to_osm_pbf, chunk_size_limit=chunk_size_limit)

                osm_pbf_data = parse_osm_pbf(
                    path_to_osm_pbf=path_to_osm_pbf, number_of_chunks=number_of_chunks,
                    parse_raw_feat=parse_raw_feat, transform_geom=transform_geom,
                    transform_other_tags=transform_other_tags, **kwargs)

                if verbose and parse_raw_feat:
                    print("Done.")

                if pickle_it:
                    save_pickle(osm_pbf_data, path_to_pickle, verbose=verbose)

                    if ret_pickle_path:
                        osm_pbf_data = osm_pbf_data, path_to_pickle

                if rm_osm_pbf:
                    remove_subregion_osm_file(path_to_osm_pbf, verbose=verbose)

            except Exception as e:
                if verbose:
                    print("Failed. {}".format(e))

                osm_pbf_data = None

        return osm_pbf_data

    def read_shp_zip(self, subregion_name, layer_names=None, feature_names=None, data_dir=None,
                     update=False, download_confirmation_required=True, pickle_it=False,
                     ret_pickle_path=False, rm_extracts=False, rm_shp_zip=False, verbose=False):
        """
        Read a shapefile of a geographic region.

        :param subregion_name: name of a geographic region (case-insensitive)
            that is available on BBBike free download server
        :type subregion_name: str
        :param layer_names: name of a .shp layer, e.g. 'railways', or names of multiple layers;
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
        :param download_confirmation_required: whether to ask for confirmation
            before starting to download a file, defaults to ``True``
        :type download_confirmation_required: bool
        :param pickle_it: whether to save the .shp data as a .pickle file, defaults to ``False``
        :type pickle_it: bool
        :param ret_pickle_path: (when ``pickle_it=True``)
            whether to return a path to the saved pickle file
        :type ret_pickle_path: bool
        :param rm_extracts: whether to delete extracted files from the .shp.zip file, defaults to ``False``
        :type rm_extracts: bool
        :param rm_shp_zip: whether to delete the downloaded .shp.zip file, defaults to ``False``
        :type rm_shp_zip: bool
        :param verbose: whether to print relevant information in console as the function runs,
            defaults to ``False``
        :type verbose: bool or int
        :return: dictionary of the shapefile data, with keys and values being layer names
            and tabular data (in the format of `geopandas.GeoDataFrame`_), respectively;
            when ``pickle_it=True``, return a tuple of the dictionary and a path to the pickle file
        :rtype: dict or tuple or None

        .. _`geopandas.GeoDataFrame`: https://geopandas.org/reference.html#geodataframe

        **Examples**::

            >>> import os
            >>> from pydriosm.reader import BBBikeReader

            >>> bbbike_reader = BBBikeReader()

            >>> region_name = 'Birmingham'
            >>> dat_dir = "tests"

            >>> birmingham_shp = bbbike_reader.read_shp_zip(region_name, data_dir=dat_dir,
            ...                                             verbose=True)
            To download .shp.zip data of the following geographic region(s):
                Birmingham
            ? [No]|Yes: yes
            Downloading "Birmingham.osm.shp.zip" to "tests\\" ... Done.
            Extracting "tests\\Birmingham.osm.shp.zip" ...
            to "tests\\"
            Done.
            Parsing files at "tests\\Birmingham-shp\\shape\\" ... Done.

            >>> list(birmingham_shp.keys())
            ['buildings',
             'landuse',
             'natural',
             'places',
             'points',
             'pofw',
             'pois',
             'railways']

            >>> # Data of 'railways' layer
            >>> birmingham_railways_shp = birmingham_shp['railways']

            >>> birmingham_railways_shp.head()
                osm_id  ... shape_type
            0      740  ...          3
            1     2148  ...          3
            2  2950000  ...          3
            3  3491845  ...          3
            4  3981454  ...          3
            [5 rows x 5 columns]

            >>> # Read data of 'road' layer only from the original .shp.zip file
            >>> # (and delete all extracts)

            >>> layer_name = 'roads'
            >>> feat_name = None

            >>> birmingham_roads_shp = bbbike_reader.read_shp_zip(region_name, layer_name,
            ...                                                   feat_name, data_dir=dat_dir,
            ...                                                   rm_extracts=True,
            ...                                                   verbose=True)
            Parsing "tests\\Birmingham-shp\\shape\\roads.shp" ... Done.
            Deleting the extracts "tests\\Birmingham-shp\\" ... Done.

            >>> list(birmingham_roads_shp.keys())
            ['roads']

            >>> birmingham_roads_shp['roads'].head()
               osm_id  ... shape_type
            0      37  ...          3
            1      38  ...          3
            2      41  ...          3
            3      42  ...          3
            4      45  ...          3
            [5 rows x 9 columns]

            >>> # Read data of multiple layers and features from the original .shp.zip file
            >>> # (and delete all extracts)

            >>> lyr_names = ['railways', 'waterways']
            >>> feat_names = ['rail', 'canal']

            >>> bham_rw_rc_shp = bbbike_reader.read_shp_zip(region_name, lyr_names, feat_names,
            ...                                             dat_dir, rm_extracts=True,
            ...                                             rm_shp_zip=True, verbose=True)
            Extracting the following layer(s):
                'railways'
                'waterways'
            from "tests\\Birmingham.osm.shp.zip" ...
            to "tests\\"
            Done.
            Parsing files at "tests\\Birmingham-shp\\shape\\" ... Done.
            Deleting the extracts "tests\\Birmingham-shp\\" ... Done.
            Deleting "tests\\Birmingham.osm.shp.zip" ... Done.

            >>> list(bham_rw_rc_shp.keys())
            ['railways', 'waterways']

            >>> # Data of the 'railways' layer
            >>> bham_rw_rc_shp_railways = bham_rw_rc_shp['railways']
            >>> bham_rw_rc_shp_railways[['type', 'name']].head()
               type                                             name
            0  rail                                  Cross-City Line
            1  rail                                  Cross-City Line
            2  rail  Derby to Birmingham (Proof House Junction) Line
            3  rail                  Birmingham to Peterborough Line
            4  rail          Water Orton to Park Lane Junction Curve

            >>> # Data of the 'waterways' layer
            >>> bham_rw_rc_shp_waterways = bham_rw_rc_shp['waterways']
            >>> bham_rw_rc_shp_waterways[['type', 'name']].head()
                 type                                              name
            2   canal                      Birmingham and Fazeley Canal
            8   canal                      Birmingham and Fazeley Canal
            9   canal  Birmingham Old Line Canal Navigations - Rotton P
            10  canal                               Oozells Street Loop
            11  canal                      Worcester & Birmingham Canal
        """

        osm_file_format = ".shp.zip"

        path_to_shp_zip = self.get_path_to_osm_file(
            subregion_name=subregion_name, osm_file_format=osm_file_format, data_dir=data_dir)

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
            sub_fname = "-".join(
                x for x in [filename_] + layer_names_ + (feature_names_ if feature_names_ else []) if x)
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
                        self.Downloader.download_osm_data(
                            subregion_names=subregion_name, osm_file_format=osm_file_format,
                            download_dir=data_dir, update=update,
                            confirmation_required=download_confirmation_required, verbose=verbose)

                    unzip_shp_zip(path_to_shp_zip=path_to_shp_zip, path_to_extract_dir=path_to_extract_dir,
                                  layer_names=layer_names_, verbose=verbose)

                    if not layer_names_:
                        layer_names_ = list(
                            set([x.rsplit(".", 1)[0] for x in os.listdir(cd(path_to_extract_dir_, "shape"))])
                        )

                else:
                    unavailable_layers = []

                    layer_names_temp_ = [
                        x.rsplit(".", 1)[0] for x in os.listdir(cd(path_to_extract_dir_, "shape"))
                    ]
                    layer_names_temp = list(set(layer_names_ + layer_names_temp_))

                    for lyr_name in layer_names_temp:
                        shp_filename = cd(path_to_extract_dir_, "shape", f"{lyr_name}.shp")
                        if not os.path.isfile(shp_filename):
                            unavailable_layers.append(lyr_name)

                    if unavailable_layers:
                        if not os.path.exists(path_to_shp_zip):
                            self.Downloader.download_osm_data(
                                subregion_names=subregion_name, osm_file_format=osm_file_format,
                                download_dir=data_dir, update=update,
                                confirmation_required=download_confirmation_required, verbose=verbose)

                        unzip_shp_zip(path_to_shp_zip=path_to_shp_zip,
                                      path_to_extract_dir=path_to_extract_dir, layer_names=unavailable_layers,
                                      verbose=verbose)

                    if not layer_names_:
                        layer_names_ = layer_names_temp

                paths_to_layers_shp = [
                    glob.glob(cd(path_to_extract_dir_, "shape", f"{lyr_name}.shp"))
                    for lyr_name in layer_names_]
                paths_to_layers_shp = [x for x in paths_to_layers_shp if x]

                if verbose:
                    files_dir = os.path.relpath(
                        os.path.commonpath(list(itertools.chain.from_iterable(paths_to_layers_shp))))
                    if os.path.isdir(files_dir):
                        msg = "files at \"{}\\\"".format(files_dir)
                    else:
                        msg = "\"{}\"".format(files_dir)
                    print("Parsing {}".format(msg), end=" ... ")

                shp_data_ = [parse_layer_shp(p, feature_names=feature_names_) for p in paths_to_layers_shp]

                shp_data = dict(zip(layer_names_, shp_data_))

                if verbose:
                    print("Done.")

                if pickle_it:
                    save_pickle(shp_data, path_to_shp_pickle, verbose=verbose)

                    if ret_pickle_path:
                        shp_data = shp_data, path_to_shp_pickle

                if rm_extracts and os.path.exists(path_to_extract_dir_):
                    if verbose:
                        print("Deleting the extracts \"{}\\\"".format(os.path.relpath(path_to_extract_dir_)),
                              end=" ... ")
                    try:
                        # for f in glob.glob(os.path.join(extract_dir, "gis_osm*")):
                        #     # if layer not in f:
                        #     os.remove(f)
                        shutil.rmtree(path_to_extract_dir_)
                        if verbose:
                            print("Done.")
                    except Exception as e:
                        if verbose:
                            print("Failed. {}".format(e))

                if rm_shp_zip and os.path.isfile(path_to_shp_zip):
                    remove_subregion_osm_file(path_to_shp_zip, verbose=verbose)

            except Exception as e:
                if verbose:
                    print("Failed. {}".format(e))
                shp_data = None

        return shp_data

    def read_csv_xz(self, subregion_name, data_dir=None, download_confirmation_required=True,
                    verbose=False):
        """
        Read a compressed CSV (.csv.xz) data file of a geographic region.

        :param subregion_name: name of a geographic region (case-insensitive)
            that is available on BBBike free download server
        :type subregion_name: str
        :param data_dir: directory where the .csv.xz data file is located/saved;
            if ``None`` (default), the default directory
        :type data_dir: str or None
        :param download_confirmation_required: whether to ask for confirmation
            before starting to download a file, defaults to ``True``
        :type download_confirmation_required: bool
        :param verbose: whether to print relevant information in console as the function runs,
            defaults to ``False``
        :type verbose: bool or int
        :return: tabular data of the .csv.xz file
        :rtype: pandas.DataFrame or None

        .. _pydriosm-BBBikeReader-read_csv_xz:

        **Example**::

            >>> import os
            >>> from pyhelpers.dir import cd
            >>> from pydriosm.reader import BBBikeReader

            >>> bbbike_reader = BBBikeReader()

            >>> region_name = 'Leeds'
            >>> dat_dir = "tests"

            >>> leeds_csv = bbbike_reader.read_csv_xz(region_name, dat_dir, verbose=True)
            To download .csv.xz data of the following geographic region(s):
                Leeds
            ? [No]|Yes: yes
            Downloading "Leeds.osm.csv.xz" to "tests\\" ... Done.
            Parsing "tests\\Leeds.osm.csv.xz" ... Done.

            >>> leeds_csv.head()
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
            path_to_csv_xz = self.Downloader.download_osm_data(
                subregion_names=subregion_name_, osm_file_format=osm_file_format, download_dir=data_dir,
                confirmation_required=download_confirmation_required, verbose=verbose,
                ret_download_path=True)

        if verbose:
            print("Parsing \"{}\"".format(os.path.relpath(path_to_csv_xz)), end=" ... ")
        try:
            csv_xz_data = parse_csv_xz(path_to_csv_xz)
            if verbose:
                print("Done.")

        except Exception as e:
            if verbose:
                print("Failed. {}".format(e))
            csv_xz_data = None

        return csv_xz_data

    def read_geojson_xz(self, subregion_name, data_dir=None, fmt_geom=False,
                        download_confirmation_required=True, verbose=False):
        """
        Read a .geojson.xz data file of a geographic region.

        :param subregion_name: name of a geographic region (case-insensitive)
            that is available on BBBike free download server
        :type subregion_name: str
        :param data_dir: directory where the .geojson.xz data file is located/saved;
            if ``None`` (default), the default directory
        :type data_dir: str or None
        :param fmt_geom: whether to reformat coordinates into a geometric object, defaults to ``False``
        :type fmt_geom: bool
        :param download_confirmation_required: whether to ask for confirmation
            before starting to download a file, defaults to ``True``
        :type download_confirmation_required: bool
        :param verbose: whether to print relevant information in console as the function runs,
            defaults to ``False``
        :type verbose: bool or int
        :return: tabular data of the .csv.xz file
        :rtype: pandas.DataFrame or None

        .. _pydriosm-BBBikeReader-read_geojson_xz:

        **Examples**::

            >>> import os
            >>> from pyhelpers.dir import cd
            >>> from pydriosm.reader import BBBikeReader

            >>> bbbike_reader = BBBikeReader()

            >>> region_name = 'Leeds'
            >>> dat_dir = "tests"

            >>> leeds_geoj = bbbike_reader.read_geojson_xz(region_name, dat_dir, verbose=True)
            To download .geojson.xz data of the following geographic region(s):
                Leeds
            ? [No]|Yes: yes
            Downloading "Leeds.osm.geojson.xz" to "tests\\" ... Done.
            Parsing "tests\\Leeds.osm.geojson.xz" ... Done.

            >>> leeds_geoj.head()
              feature_name  ...                                         properties
            0      Feature  ...  {'highway': 'motorway_junction', 'name': 'Flus...
            1      Feature  ...  {'highway': 'motorway_junction', 'name': 'Bram...
            2      Feature  ...  {'highway': 'motorway_junction', 'name': 'Bell...
            3      Feature  ...  {'highway': 'motorway_junction', 'name': 'Loft...
            4      Feature  ...  {'highway': 'motorway_junction', 'name': 'Loft...
            [5 rows x 4 columns]

            >>> leeds_geoj[['coordinates']].head()
                            coordinates
            0  [-1.5558097, 53.6873431]
            1     [-1.34293, 53.844618]
            2   [-1.517335, 53.7499667]
            3   [-1.514124, 53.7416937]
            4   [-1.516511, 53.7256632]

            >>> # Set `fmt_geom` to be True
            >>> leeds_geoj_ = bbbike_reader.read_geojson_xz(region_name, dat_dir, fmt_geom=True)

            >>> leeds_geoj_[['coordinates']].head()
                                 coordinates
            0  POINT (-1.5558097 53.6873431)
            1     POINT (-1.34293 53.844618)
            2   POINT (-1.517335 53.7499667)
            3   POINT (-1.514124 53.7416937)
            4   POINT (-1.516511 53.7256632)

            >>> # Delete the downloaded .csv.xz data file
            >>> os.remove(cd(dat_dir, "Leeds.osm.geojson.xz"))
        """

        osm_file_format = ".geojson.xz"

        subregion_name_ = self.Downloader.validate_input_subregion_name(subregion_name)

        path_to_geojson_xz = self.get_path_to_osm_file(subregion_name_, osm_file_format, data_dir)

        if not os.path.isfile(path_to_geojson_xz):
            path_to_geojson_xz = self.Downloader.download_osm_data(
                subregion_names=subregion_name_, osm_file_format=osm_file_format, download_dir=data_dir,
                confirmation_required=download_confirmation_required, verbose=verbose,
                ret_download_path=True)

        if verbose:
            print("Parsing \"{}\"".format(os.path.relpath(path_to_geojson_xz)), end=" ... ")
        try:
            geojson_xz_data = parse_geojson_xz(path_to_geojson_xz, fmt_geom=fmt_geom)

            if verbose:
                print("Done.")

        except Exception as e:
            if verbose:
                print("Failed. {}".format(e))

            geojson_xz_data = None

        return geojson_xz_data
