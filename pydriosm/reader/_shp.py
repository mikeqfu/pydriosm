"""
Handling shapefiles.
"""

import collections
import copy
import glob
import itertools
import os
import re
import shutil
import zipfile

import numpy as np
import pandas as pd
import shapefile as pyshp
import shapely.geometry
from pyhelpers._cache import _check_dependencies, _print_failure_message
from pyhelpers.dirs import add_slashes, cd, check_relative_pathname, validate_dir
from pyhelpers.text import find_similar_str


def get_layer_name(shp_filename):
    """
    Find the layer name of OSM shapefile given its filename.

    :param shp_filename: filename of a shapefile (.shp)
    :type shp_filename: str
    :return: layer name of the shapefile
    :rtype: str

    **Examples**::

        >>> from pydriosm.reader import SHP

        >>> SHP.get_layer_name("") is None
        True

        >>> SHP.get_layer_name("gis_osm_railways_free_1.shp")
        'railways'

        >>> SHP.get_layer_name("gis_osm_transport_a_free_1.shp")
        'transport'
    """

    try:
        pattern = re.compile(r'(?<=gis_osm_)\w+(?=(_a)?_free_1)')
        layer_name = re.search(pattern=pattern, string=shp_filename)

    except AttributeError:
        pattern = re.compile(r'(?<=(\\shape)\\)\w+(?=\.*)')
        layer_name = re.search(pattern=pattern, string=shp_filename)

    if layer_name:
        layer_name = layer_name.group(0).replace("_a", "")

    return layer_name


def _unzip_prep(shp_zip_pathname, extract_to=None, layer_names=None, verbose=False):
    if extract_to:
        extract_dir = extract_to
    else:
        extract_dir = os.path.splitext(shp_zip_pathname)[0].replace(".", "-")

    shp_zip_rel_path, extrdir_rel_path = map(
        check_relative_pathname, [shp_zip_pathname, extract_dir])

    if not layer_names:
        layer_names_ = layer_names
        if verbose:
            print(
                f"Extracting {add_slashes(shp_zip_rel_path)}\n\t"
                f"to {add_slashes(extrdir_rel_path)}",
                end=" ... ")
    else:
        layer_names_ = [layer_names] if isinstance(layer_names, str) else layer_names.copy()
        if verbose:
            layer_name_list = "\t" + "\n\t".join([f"'{x}'" for x in layer_names_])
            print(f"Extracting the following layer(s):\n{layer_name_list}")
            print(f"\t\tfrom {add_slashes(shp_zip_rel_path)} ... \n"
                  f"\t\t\tto {add_slashes(extrdir_rel_path)}",
                  end=" ... ")

    return extract_dir, layer_names_


def _unzip_trail(extract_dir, extract_files, verbose):
    file_list = extract_files if extract_files else os.listdir(extract_dir)
    if 'README' in file_list:
        file_list.remove('README')

    filenames, exts = map(lambda x: list(set(x)), zip(*map(os.path.splitext, file_list)))

    layer_names_ = [get_layer_name(f) for f in filenames]

    extract_dirs = []
    for lyr, fn in zip(layer_names_, filenames):
        extract_dir_ = os.path.join(extract_dir, lyr)
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

    return extract_dir


class SHP:
    """
    Read/parse `Shapefile <https://wiki.openstreetmap.org/wiki/Shapefiles>`_ data.

    **Examples**::

        >>> from pydriosm.reader import SHP

        >>> SHP.EPSG4326_WGS84_PROJ4
        '+proj=longlat +ellps=WGS84 +datum=WGS84 +no_defs'

        >>> SHP.EPSG4326_WGS84_PROJ4_
        {'proj': 'longlat', 'ellps': 'WGS84', 'datum': 'WGS84', 'no_defs': True}
    """

    #: dict: Shape type codes of shapefiles and their corresponding
    #: `geometric objects <https://shapely.readthedocs.io/en/latest/manual.html#geometric-objects>`_
    #: defined in `Shapely <https://pypi.org/project/Shapely/>`_.
    SHAPE_TYPE_GEOM = {
        1: shapely.geometry.Point,
        3: shapely.geometry.LineString,
        5: shapely.geometry.Polygon,
        8: shapely.geometry.MultiPoint,
    }

    #: Shape type codes of shapefiles and their corresponding geometry object names
    SHAPE_TYPE_GEOM_NAME: dict = {k: v.__name__ for k, v in SHAPE_TYPE_GEOM.items()}

    #: Shape type codes of shapefiles and their corresponding names for an OSM shapefile.
    SHAPE_TYPE_NAME_LOOKUP: dict = {
        0: None,
        1: 'Point',  # shapely.geometry.Point
        3: 'Polyline',  # shapely.geometry.LineString
        5: 'Polygon',  # shapely.geometry.Polygon
        8: 'MultiPoint',  # shapely.geometry.MultiPoint
        11: 'PointZ',
        13: 'PolylineZ',
        15: 'PolygonZ',
        18: 'MultiPointZ',
        21: 'PointM',
        23: 'PolylineM',
        25: 'PolygonM',
        28: 'MultiPointM',
        31: 'MultiPatch',
    }

    #: The encoding method applied to create an OSM shapefile.
    #: This is for writing .cpg (code page) file.
    ENCODING: str = 'UTF-8'  # 'ISO-8859-1'

    #: The metadata associated with the shapefiles coordinate and projection system.
    #: `ESRI WKT <https://spatialreference.org/ref/epsg/4326/esriwkt/>`_ of
    #: EPSG Projection 4326 - WGS 84 (`EPSG:4326 <https://spatialreference.org/ref/epsg/wgs-84/>`_)
    #: for shapefile data.
    EPSG4326_WGS84_ESRI_WKT: str = \
        'GEOGCS["GCS_WGS_1984",DATUM["D_WGS_1984",SPHEROID["WGS_1984",6378137.0,298.257223563]],' \
        'PRIMEM["Greenwich",0.0],' \
        'UNIT["Degree",0.017453292519943295]]'

    #: `Proj4 <https://spatialreference.org/ref/epsg/wgs-84/proj4/>`_ of
    #: EPSG Projection 4326 - WGS 84 (`EPSG:4326 <https://spatialreference.org/ref/epsg/wgs-84/>`_)
    #: for the setting of `CRS <https://en.wikipedia.org/wiki/Spatial_reference_system>`_
    #: for shapefile data.
    EPSG4326_WGS84_PROJ4: str = '+proj=longlat +ellps=WGS84 +datum=WGS84 +no_defs'

    #: A dict-type representation of EPSG Projection 4326 - WGS 84
    #: (`EPSG:4326 <https://spatialreference.org/ref/epsg/wgs-84/>`_) for the setting of
    #: `CRS <https://en.wikipedia.org/wiki/Spatial_reference_system>`_ for shapefile data.
    EPSG4326_WGS84_PROJ4_: dict = {
        'proj': 'longlat',
        'ellps': 'WGS84',
        'datum': 'WGS84',
        'no_defs': True,
    }

    #: Valid layer names for an OSM shapefile.
    LAYER_NAMES: set = {
        'buildings',
        'landuse',
        'natural',
        'places',
        'points',
        'pofw',
        'pois',
        'railways',
        'roads',
        'traffic',
        'transport',
        'water',
        'waterways',
    }

    #: Name of the vector driver for writing shapefile data;
    #: see also the parameter ``driver`` of
    #: `geopandas.GeoDataFrame.to_file()
    #: <https://geopandas.org/reference.html#geopandas.GeoDataFrame.to_file>`_.
    VECTOR_DRIVER: str = 'ESRI Shapefile'

    @classmethod
    def validate_layer_names(cls, layer_names):
        """
        Validate the input of layer name(s) for reading shapefiles.

        :param layer_names: name of a shapefile layer, e.g. 'railways',
            or names of multiple layers; if ``None`` (default), returns an empty list;
            if ``layer_names='all'``, the function returns a list of all available layers
        :type layer_names: str | list | None
        :return: valid layer names to be input
        :rtype: list

        **Examples**::

            >>> from pydriosm.reader import SHP

            >>> SHP.validate_layer_names(None)
            []

            >>> SHP.validate_layer_names('point')
            ['points']

            >>> SHP.validate_layer_names(['point', 'land'])
            ['points', 'landuse']

            >>> SHP.validate_layer_names('all')
            ['buildings',
             'landuse',
             'natural',
             'places',
             'pofw',
             'points',
             'pois',
             'railways',
             'roads',
             'traffic',
             'transport',
             'water',
             'waterways']
        """

        if layer_names:
            if layer_names == 'all':
                layer_names_ = sorted(list(cls.LAYER_NAMES))
            else:
                lyr_names_ = [layer_names] if isinstance(layer_names, str) else layer_names
                layer_names_ = [find_similar_str(x, cls.LAYER_NAMES) for x in lyr_names_]

        else:
            layer_names_ = []

        return layer_names_

    @classmethod
    def get_layer_name(cls, shp_filename):
        """
        Find the layer name of OSM shapefile given its filename.

        :param shp_filename: filename of a shapefile (.shp)
        :type shp_filename: str
        :return: layer name of the shapefile
        :rtype: str

        **Examples**::

            >>> from pydriosm.reader import SHP

            >>> SHP.get_layer_name("") is None
            True

            >>> SHP.get_layer_name("gis_osm_railways_free_1.shp")
            'railways'

            >>> SHP.get_layer_name("gis_osm_transport_a_free_1.shp")
            'transport'
        """

        return get_layer_name(shp_filename)

    @classmethod
    def unzip_shp_zip(cls, shp_zip_pathname, extract_to=None, layer_names=None, separate=False,
                      ret_extract_dir=False, verbose=False, raise_error=False):
        """
        Unzip a zipped shapefile.

        :param shp_zip_pathname: path to a zipped shapefile data (.shp.zip)
        :type shp_zip_pathname: str | os.PathLike[str]
        :param extract_to: path to a directory where extracted files will be saved;
            when ``extract_to=None`` (default), the same directory where the .shp.zip file is saved
        :type extract_to: str | None
        :param layer_names: name of a .shp layer, e.g. 'railways', or names of multiple layers;
            when ``layer_names=None`` (default), all available layers
        :type layer_names: str | list | None
        :param separate: whether to put the data files of different layer in respective folders,
            defaults to ``False``
        :type separate: bool
        :param ret_extract_dir: whether to return the pathname of the directory
            where extracted files are saved, defaults to ``False``
        :type ret_extract_dir: bool
        :param verbose: whether to print relevant information in console, defaults to ``False``
        :type verbose: bool | int
        :param raise_error: Whether to raise the provided exception;
            if ``raise_error=False`` (default), the error will be suppressed.
        :type raise_error: bool
        :return: the path to the directory of extracted files when ``ret_extract_dir=True``
        :rtype: str

        **Examples**::

            >>> from pydriosm.reader import SHP
            >>> from pydriosm.downloader import GeofabrikDownloader
            >>> from pyhelpers.dirs import cd, delete_dir
            >>> import os

            >>> # Download the shapefile data of London as an example
            >>> subrgn_name = 'london'
            >>> file_format = ".shp"
            >>> dwnld_dir = "tests\\osm_data"

            >>> gfd = GeofabrikDownloader()

            >>> gfd.download_data(subrgn_name, file_format, dwnld_dir, verbose=True)
            To download .shp.zip data of the following geographic (sub)region(s):
                Greater London
            ? [No]|Yes: yes
            Downloading "greater-london-latest-free.shp.zip"
                to "tests\\osm_data\\greater-london\\" ... Done.

            >>> path_to_shp_zip = gfd.data_paths[0]
            >>> os.path.relpath(path_to_shp_zip)
            'tests\\osm_data\\greater-london\\greater-london-latest-free.shp.zip'

            >>> # To extract data of a specific layer 'railways'
            >>> london_railways_dir = SHP.unzip_shp_zip(
            ...     path_to_shp_zip, layer_names='railways', verbose=True, ret_extract_dir=True)
            Extracting the following layer(s):
                'railways'
                from "tests\\osm_data\\greater-london\\greater-london-latest-free.shp.zip"
                  to "tests\\osm_data\\greater-london\\greater-london-latest-free-shp\\" ... Done.

            >>> os.path.relpath(london_railways_dir)  # Check the directory
            'tests\\osm_data\\greater-london\\greater-london-latest-free-shp'

            >>> # When multiple layer names are specified, the extracted files for each of the
            >>> # layers can be put into a separate subdirectory by setting `separate=True`:
            >>> lyr_names = ['railways', 'transport', 'traffic']
            >>> dirs_of_layers = SHP.unzip_shp_zip(
            ...     path_to_shp_zip, layer_names=lyr_names, separate=True, verbose=2,
            ...     ret_extract_dir=True)
            Extracting the following layer(s):
                'railways'
                'transport'
                'traffic'
                from "tests\\osm_data\\greater-london\\greater-london-latest-free.shp.zip"
                  to "tests\\osm_data\\greater-london\\greater-london-latest-free-shp\\" ... Done.
            Grouping files by layers ...
                railways ... Done.
                transport_a ... Done.
                transport ... Done.
                traffic_a ... Done.
                traffic ... Done.
            Done.

            >>> len(dirs_of_layers) == 3
            True
            >>> os.path.relpath(os.path.commonpath(dirs_of_layers))
            'tests\\osm_data\\greater-london\\greater-london-latest-free-shp'
            >>> set(map(os.path.basename, dirs_of_layers))
            {'railways', 'traffic', 'transport'}

            >>> # Remove the subdirectories
            >>> delete_dir(dirs_of_layers, confirmation_required=False)

            >>> # To extract all (without specifying `layer_names`
            >>> london_shp_dir = SHP.unzip_shp_zip(
            ...     path_to_shp_zip, verbose=True, ret_extract_dir=True)
            Extracting "tests\\osm_data\\greater-london\\greater-london-latest-free.shp.zip"
                to "tests\\osm_data\\greater-london\\greater-london-latest-free-shp\\" ... Done.

            >>> # Check the directory
            >>> os.path.relpath(london_shp_dir)
            'tests\\osm_data\\greater-london\\greater-london-latest-free-shp'
            >>> len(os.listdir(london_shp_dir))
            91
            >>> # Get the names of all available layers
            >>> set(filter(None, map(SHP.get_layer_name, os.listdir(london_shp_dir))))
            {'buildings',
             'landuse',
             'natural',
             'places',
             'pofw',
             'pois',
             'railways',
             'roads',
             'traffic',
             'transport',
             'water',
             'waterways'}

            >>> # Delete the download/data directory
            >>> delete_dir(gfd.download_dir, verbose=True)
            To delete the directory "./tests/osm_data/" (Not empty)
            ? [No]|Yes: yes
            Deleting "./tests/osm_data/" ... Done.
        """

        extract_dir, layer_names_ = _unzip_prep(
            shp_zip_pathname=shp_zip_pathname, extract_to=extract_to, layer_names=layer_names,
            verbose=verbose)

        try:
            with zipfile.ZipFile(file=shp_zip_pathname, mode='r') as sz:
                if layer_names_:
                    extract_files = [
                        f.filename for f in sz.filelist
                        if any(x in f.filename for x in layer_names_)]
                else:
                    extract_files = None
                sz.extractall(extract_dir, members=extract_files)

            if verbose:
                if isinstance(extract_files, list) and len(extract_files) == 0:
                    print("\n\tThe specified layer does not exist. No data has been extracted.")
                else:
                    print("Done.")

            if separate:
                if verbose:
                    print("Grouping files by layers ... ", end="\n" if verbose == 2 else "")

                extract_dir = _unzip_trail(
                    extract_dir=extract_dir, extract_files=extract_files, verbose=verbose)

                if verbose:
                    print("Done.")

        except Exception as e:
            _print_failure_message(
                e, prefix="Failed. Error:", verbose=verbose, raise_error=raise_error)

        if ret_extract_dir:
            return extract_dir

    @classmethod
    def _covert_to_geometry(cls, x):
        """Convert the ``(shape_type, coordinates)`` of a feature to a ``shapely.geometry`` object.

        :param x: a feature (i.e. one row data) in a shapefile parsed by pyShp.
        :return: the corresponding ``shapely.geometry`` object
        """

        coordinates, geom_func = x['coordinates'], cls.SHAPE_TYPE_GEOM[x['shape_type']]

        if geom_func.__name__ == 'Point' and len(coordinates) == 1:
            coordinates = coordinates[0]

        y = geom_func(coordinates)

        return y

    @classmethod
    def read_shp(cls, shp_pathname, engine='pyshp', emulate_gpd=False, **kwargs):
        """
        Read a shapefile.

        :param shp_pathname: pathname of a shape format file (.shp)
        :type shp_pathname: str
        :param engine: method used to read shapefiles;
            options include: ``'pyshp'`` (default) and ``'geopandas'`` (or ``'gpd'``)
            this function by default relies on `shapefile.reader()`_;
            when ``engine='geopandas'`` (or ``engine='gpd'``),
            it relies on `geopandas.read_file()`_;
        :type engine: str
        :param emulate_gpd: whether to emulate the data format produced by `geopandas.read_file()`_
            when ``engine='pyshp'``.
        :type emulate_gpd: bool
        :param kwargs: [optional] parameters of the function
            `geopandas.read_file()`_ or `shapefile.reader()`_
        :return: data frame of the shapefile data
        :rtype: pandas.DataFrame | geopandas.GeoDataFrame

        .. _`shapefile.reader()`: https://github.com/GeospatialPython/pyshp#reading-shapefiles
        .. _`geopandas.read_file()`: https://geopandas.org/reference/geopandas.read_file.html

        .. note::

            - If ``engine`` is set to be ``'geopandas'`` (or ``'gpd'``), it requires that
                `GeoPandas <https://geopandas.org/>`_ is installed.

        **Examples**::

            >>> from pydriosm.reader import SHP
            >>> from pydriosm.downloader import GeofabrikDownloader
            >>> from pyhelpers.dirs import cd, delete_dir
            >>> import os
            >>> import glob

            >>> # Download the shapefile data of London as an example
            >>> subrgn_name = 'london'
            >>> file_format = ".shp"
            >>> dwnld_dir = "tests\\osm_data"

            >>> gfd = GeofabrikDownloader()

            >>> gfd.download_data(subrgn_name, file_format, dwnld_dir, verbose=True)
            To download .shp.zip data of the following geographic (sub)region(s):
                Greater London
            ? [No]|Yes: yes
            Downloading "greater-london-latest-free.shp.zip"
                to "tests\\osm_data\\greater-london\\" ... Done.

            >>> london_shp_zip = gfd.data_paths[0]
            >>> os.path.relpath(london_shp_zip)
            'tests\\osm_data\\greater-london\\greater-london-latest-free.shp.zip'

            >>> # Extract all
            >>> london_shp_dir = SHP.unzip_shp_zip(london_shp_zip, ret_extract_dir=True)

            >>> # Get the pathname of the .shp data of 'railways'
            >>> path_to_railways_shp = glob.glob(cd(london_shp_dir, "*railways*.shp"))[0]
            >>> os.path.relpath(path_to_railways_shp)  # Check the pathname of the .shp file
            'tests\\osm_data\\greater-london\\greater-london-latest-free-shp\\gis_osm_railwa...

            >>> # Read the data of 'railways'
            >>> london_railways = SHP.read_shp(path_to_railways_shp)
            >>> london_railways.head()
               osm_id  code  ...                                        coordinates shape_type
            0   30804  6101  ...  [(0.0048644, 51.6279262), (0.0061979, 51.62926...          3
            1  101298  6103  ...  [(-0.2249906, 51.493682), (-0.2251678, 51.4945...          3
            2  101486  6103  ...  [(-0.2055497, 51.5195429), (-0.2051377, 51.519...          3
            3  101511  6101  ...  [(-0.2119027, 51.5241906), (-0.2108059, 51.523...          3
            4  282898  6103  ...  [(-0.1862586, 51.6159083), (-0.1868721, 51.613...          3
            [5 rows x 9 columns]

            >>> # Set `emulate_gpd=True` to return data of similar format to what GeoPandas does
            >>> london_railways = SHP.read_shp(path_to_railways_shp, emulate_gpd=True)
            >>> london_railways.head()
               osm_id  code  ... tunnel                                           geometry
            0   30804  6101  ...      F  LINESTRING (0.0048644 51.6279262, 0.0061979 51...
            1  101298  6103  ...      F  LINESTRING (-0.2249906 51.493682, -0.2251678 5...
            2  101486  6103  ...      F  LINESTRING (-0.2055497 51.5195429, -0.2051377 ...
            3  101511  6101  ...      F  LINESTRING (-0.2119027 51.5241906, -0.2108059 ...
            4  282898  6103  ...      F  LINESTRING (-0.1862586 51.6159083, -0.1868721 ...
            [5 rows x 8 columns]

            >>> # Alternatively, set `engine` to be 'geopandas' (or 'gpd') to use GeoPandas
            >>> london_railways_ = SHP.read_shp(path_to_railways_shp, engine='geopandas')
            >>> london_railways_.head()
               osm_id  code  ... tunnel                                           geometry
            0   30804  6101  ...      F    LINESTRING (0.00486 51.62793, 0.00620 51.62927)
            1  101298  6103  ...      F  LINESTRING (-0.22499 51.49368, -0.22517 51.494...
            2  101486  6103  ...      F  LINESTRING (-0.20555 51.51954, -0.20514 51.519...
            3  101511  6101  ...      F  LINESTRING (-0.21190 51.52419, -0.21081 51.523...
            4  282898  6103  ...      F  LINESTRING (-0.18626 51.61591, -0.18687 51.61384)
            [5 rows x 8 columns]

            >>> # Check the data types of `london_railways` and `london_railways_`
            >>> railways_data = [london_railways, london_railways_]
            >>> list(map(type, railways_data))
            [pandas.core.frame.DataFrame, geopandas.geodataframe.GeoDataFrame]
            >>> # Check the geometry data of `london_railways` and `london_railways_`
            >>> geom1, geom2 = map(lambda x: x['geometry'].map(lambda y: y.wkt), railways_data)
            >>> geom1.equals(geom2)
            True

            >>> # Delete the download/data directory
            >>> delete_dir(gfd.download_dir, verbose=True)
            To delete the directory "./tests/osm_data/" (Not empty)
            ? [No]|Yes: yes
            Deleting "./tests/osm_data/" ... Done.
        """

        if engine in {'geopandas', 'gpd'}:
            gpd = _check_dependencies('geopandas')
            shp_data = gpd.read_file(shp_pathname, **kwargs)

        else:  # method == 'pyshp':  # default
            # Read .shp file using shapefile.reader()
            with pyshp.Reader(shp_pathname, **kwargs) as f:
                # Transform the data to a DataFrame
                filed_names = [field[0] for field in f.fields[1:]]
                shp_data = pd.DataFrame(data=f.records(), columns=filed_names)

                # shp_data['name'] = shp_data['name'].str.encode('utf-8').str.decode('utf-8')
                shape_geom_colnames = ['coordinates', 'shape_type']
                shape_geom = pd.DataFrame(
                    data=[(s.points, s.shapeType) for s in f.iterShapes()], index=shp_data.index,
                    columns=shape_geom_colnames)

            if emulate_gpd:
                shp_data['geometry'] = shape_geom[shape_geom_colnames].apply(
                    cls._covert_to_geometry, axis=1)
                # shp_data.drop(columns=shape_geom_colnames, inplace=True)
            else:
                shp_data = pd.concat([shp_data, shape_geom], axis=1)

        object_cols = shp_data.select_dtypes(include=['object', 'str']).columns
        shp_data[object_cols] = shp_data[object_cols].replace({np.nan: None})

        return shp_data

    @classmethod
    def _convert_to_coords_and_shape_type(cls, x):
        """Convert a ``shapely.geometry`` object to ``(shape_type, coordinates)``.

        :param x: a ``shapely.geometry`` object
        :return: the corresponding ``(shape_type, coordinates)``
        """

        lookup_dict = {v: k for k, v in cls.SHAPE_TYPE_NAME_LOOKUP.items()}
        lookup_dict.update({'LineString': 3})
        shape_type = lookup_dict[x.geom_type]

        # try:
        #     coordinates = list(x.coords)
        # except NotImplementedError:
        #     coordinates = list(x.exterior.coords)
        coordinates = list(x.exterior.coords) if hasattr(x, 'exterior') else list(x.coords)

        return coordinates, shape_type

    @classmethod
    def _specify_pyshp_fields(cls, data, field_names, decimal_precision):
        """
        Make fields data for writing shapefiles by
        `PyShp <https://github.com/GeospatialPython/pyshp>`_.

        :param data: data of a shapefile
        :type data: pandas.DataFrame
        :param field_names: names of fields to be written as shapefile records
        :type field_names: list | pandas.Index
        :param decimal_precision: decimal precision for writing float records
        :type decimal_precision: int
        :return: list of records in the .shp data
        :rtype: list

        .. seealso::

            - Examples for the method
              :meth:`SHPReadParse.write_to_shapefile()
              <pydriosm.reader.SHPReadParse.write_to_shapefile>`.
        """

        dtype_shp_type = {
            'object': 'C',  # Character
            'str': 'C',
            'int64': 'N',  # Numeric
            'int32': 'N',
            'float64': 'F',  # Float
            'float32': 'F',
            'bool': 'L',  # Logical
            'datetime64': 'D',  # Date
            'datetime64[ns]': 'D',  # Explicit pandas datetime
        }

        fields = []

        for field_name, dtype, in data[field_names].dtypes.items():
            try:
                max_size = data[field_name].map(len).max()
            except TypeError:
                max_size = data[field_name].astype(str).map(len).max()

            shp_type = dtype_shp_type.get(dtype.name, 'C')
            decimal = decimal_precision if 'float' in dtype.name else 0

            fields.append((field_name, shp_type, int(max_size), decimal))

        return fields

    @classmethod
    def write_to_shapefile(cls, data, write_to, shp_filename=None, decimal_precision=5,
                           ret_shp_pathname=False, verbose=False, raise_error=False):
        """
        Save .shp data as a shapefile by `PyShp <https://github.com/GeospatialPython/pyshp>`_.

        :param data: data of a shapefile
        :type data: pandas.DataFrame
        :param write_to: pathname of a directory where the shapefile data is to be saved
        :type write_to: str
        :param shp_filename: filename (or pathname) of the target .shp file, defaults to ``None``;
            when ``shp_filename=None``, it is by default the basename of ``write_to``
        :type shp_filename: str | os.PahtLike[str] | None
        :param decimal_precision: decimal precision for writing float records, defaults to ``5``
        :type decimal_precision: int
        :param ret_shp_pathname: whether to return the pathname of the output .shp file,
            defaults to ``False``
        :type ret_shp_pathname: bool
        :param verbose: whether to print relevant information in console, defaults to ``False``
        :type verbose: bool | int
        :param raise_error: Whether to raise the provided exception;
            if ``raise_error=False`` (default), the error will be suppressed.
        :type raise_error: bool

        **Examples**::

            >>> from pydriosm.reader import SHP
            >>> from pydriosm.downloader import GeofabrikDownloader
            >>> from pyhelpers.dirs import cd, delete_dir
            >>> import os
            >>> import glob

            >>> # Download the shapefile data of London as an example
            >>> subrgn_name = 'london'
            >>> file_format = ".shp"
            >>> dwnld_dir = "tests\\osm_data"

            >>> gfd = GeofabrikDownloader()

            >>> gfd.download_data(subrgn_name, file_format, dwnld_dir, verbose=True)
            To download .shp.zip data of the following geographic (sub)region(s):
                Greater London
            ? [No]|Yes: yes
            Downloading "greater-london-latest-free.shp.zip"
                to "tests\\osm_data\\greater-london\\" ... Done.

            >>> london_shp_zip = gfd.data_paths[0]
            >>> os.path.relpath(london_shp_zip)
            'tests\\osm_data\\greater-london\\greater-london-latest-free.shp.zip'

            >>> # Extract the 'railways' layer of the downloaded .shp.zip file
            >>> lyr_name = 'railways'

            >>> railways_shp_dir = SHP.unzip_shp_zip(
            ...     london_shp_zip, layer_names=lyr_name, verbose=True, ret_extract_dir=True)
            Extracting the following layer(s):
                'railways'
                from "tests\\osm_data\\greater-london\\greater-london-latest-free.shp.zip"
                  to "tests\\osm_data\\greater-london\\greater-london-latest-free-shp\\"
            Done.
            >>> # Check out the output directory
            >>> os.path.relpath(railways_shp_dir)
            'tests\\osm_data\\greater-london\\greater-london-latest-free-shp'

            >>> # Get the pathname of the .shp data of 'railways'
            >>> path_to_railways_shp = glob.glob(cd(railways_shp_dir, f"*{lyr_name}*.shp"))[0]
            >>> os.path.relpath(path_to_railways_shp)  # Check the pathname of the .shp file
            'tests\\osm_data\\greater-london\\greater-london-latest-free-shp\\gis_osm_railwa...

            >>> # Read the .shp file
            >>> london_railways_shp = SHP.read_shp(path_to_railways_shp)

            >>> # Create a new directory for saving the 'railways' data
            >>> railways_subdir = cd(os.path.dirname(railways_shp_dir), lyr_name)
            >>> os.path.relpath(railways_subdir)
            'tests\\osm_data\\greater-london\\railways'

            >>> # Save the data of 'railways' to the new directory
            >>> path_to_railways_shp_ = SHP.write_to_shapefile(
            ...     london_railways_shp, railways_subdir, ret_shp_pathname=True, verbose=True)
            Writing data to "tests\\osm_data\\greater-london\\railways\\railways.*" ... Done.
            >>> os.path.basename(path_to_railways_shp_)
            'railways.shp'

            >>> # If `shp_filename` is specified
            >>> path_to_railways_shp_ = SHP.write_to_shapefile(
            ...     london_railways_shp, railways_subdir, shp_filename="rail_data",
            ...     ret_shp_pathname=True, verbose=True)
            Writing data to "tests\\osm_data\\greater-london\\railways\\rail_data.*" ... Done.
            >>> os.path.basename(path_to_railways_shp_)
            'rail_data.shp'

            >>> # Retrieve the saved the .shp file
            >>> london_railways_shp_ = SHP.read_shp(path_to_railways_shp_)

            >>> # Check if the retrieved .shp data is equal to the original one
            >>> london_railways_shp_.equals(london_railways_shp)
            True

            >>> # Delete the download/data directory
            >>> delete_dir(gfd.download_dir, verbose=True)
            To delete the directory "./tests/osm_data/" (Not empty)
            ? [No]|Yes: yes
            Deleting "./tests/osm_data/" ... Done.
        """

        filename_ = os.path.basename(write_to) if shp_filename is None else copy.copy(shp_filename)
        filename = os.path.splitext(filename_)[0]
        write_to_ = os.path.join(os.path.dirname(write_to), filename)

        if verbose:
            print(f'Writing data to "{check_relative_pathname(write_to_)}.*"', end=" ... ")

        try:
            key_column_names = ['coordinates', 'shape_type']
            dat = data.copy()

            if 'geometry' in data.columns:
                coords_and_shape_type = pd.DataFrame(
                    dat['geometry'].map(cls._convert_to_coords_and_shape_type).to_list(),
                    columns=key_column_names, index=dat.index)
                del dat['geometry']
                dat = pd.concat([dat, coords_and_shape_type], axis=1)

            field_names = [x for x in dat.columns if x not in key_column_names]

            shape_type = dat['shape_type'].unique()[0]

            with pyshp.Writer(target=write_to_, shapeType=shape_type, autoBalance=True) as w:
                field_info_list = cls._specify_pyshp_fields(
                    data=dat, field_names=field_names, decimal_precision=decimal_precision)

                for f in field_info_list:
                    w.field(*f)

                for i in dat.index:
                    rec_list = dat.loc[i, field_names].values.tolist()
                    rec_list = [val.item() if hasattr(val, 'item') else val for val in rec_list]
                    w.record(*rec_list)

                    # s = pyshp.Shape(shapeType=w.shapeType, points=dat.loc[i, 'coordinates'])
                    coordinates = dat.loc[i, 'coordinates']
                    if shape_type == 1:
                        coordinates = coordinates[0]
                    elif shape_type == 5:
                        coordinates = [[list(coords) for coords in coordinates]]
                    s = {'type': cls.SHAPE_TYPE_GEOM_NAME[shape_type], 'coordinates': coordinates}
                    w.shape(s)

            # Write .cpg
            with open(f"{write_to_}.cpg", "w") as cpg_file:
                cpg_file.write(cls.ENCODING)

            # Write .prj
            with open(f"{write_to_}.prj", "w") as prj_file:
                prj_file.write(cls.EPSG4326_WGS84_ESRI_WKT)

            if verbose:
                print("Done.")

            if ret_shp_pathname:
                return f"{write_to_}.shp"

        except Exception as e:
            _print_failure_message(
                e, prefix="Failed. Error:", verbose=verbose, raise_error=raise_error)

    @classmethod
    def _make_feat_shp_pathname(cls, shp_pathname, feature_names_):
        """
        Specify a pathname(s) for saving data of one (or multiple) given feature(s)
        by appending the feature name(s) to the filename of
        its (or their) parent layer's shapefile).

        :param shp_pathname: pathname of a shapefile of a layer
        :type shp_pathname: str | os.PathLike[str]
        :param feature_names_: name (or names) of one (or multiple) feature(s)
            in a shapefile of a layer
        :type feature_names_: list
        :return: pathname(s) of the data of the given ``feature_names``
        :rtype: list

        **Examples**::

            >>> from pydriosm.reader import SHP
            >>> import os

            >>> fn = "gis_osm_railways_free_1.shp"
            >>> feats = ['rail']
            >>> pn = SHP._make_feat_shp_pathname(shp_pathname=fn, feature_names_=feats)
            >>> len(pn)
            1
            >>> os.path.relpath(pn[0])
            'gis_osm_railways_free_1_rail.shp'

            >>> fn = "tests\\osm_data\\greater-london\\gis_osm_transport_free_1.shp"
            >>> feats = ['railway_station', 'bus_stop', 'bus_station']
            >>> pn = SHP._make_feat_shp_pathname(shp_pathname=fn, feature_names_=feats)
            >>> len(pn)
            3
            >>> pn
            ['tests\\osm_data\\greater-london\\gis_osm_transport_a_free_1_railway_station.shp',
             'tests\\osm_data\\greater-london\\gis_osm_transport_a_free_1_bus_stop.shp',
             'tests\\osm_data\\greater-london\\gis_osm_transport_a_free_1_bus_station.shp']
        """

        shp_dir_path, shp_filename_ = os.path.split(shp_pathname)
        shp_filename, ext = os.path.splitext(shp_filename_)

        # # filename_for_dir = re.search('gis_osm_(.*?)_(a_)?', fn_for_dir_).group(1)
        # layer_name = cls.find_shp_layer_name(shp_filename_)

        if len(feature_names_) > 0:
            feat_shp_pathnames = [
                os.path.join(shp_dir_path, f"{shp_filename}_{f}{ext}") for f in feature_names_]
        else:
            feat_shp_pathnames = []

        return feat_shp_pathnames

    @classmethod
    def _write_feat_shp(cls, data, feat_col_name, feat_shp_pathnames_):
        """
        Write the data of selected features of a layer to a shapefile
        (or shapefiles given multiple shape types).

        :param data: data of shapefiles
        :type data: pandas.DataFrame | geopandas.GeoDataFrame
        :param feat_col_name: name of the column that contains feature names;
            valid values can include ``'fclass'`` and ``'type'``
        :type feat_col_name: str
        :param feat_shp_pathnames_: (temporary) pathname for the output shapefile(s)
        :type feat_shp_pathnames_: str
        :return: pathnames of the output shapefiles
        :rtype: list
        """

        feat_shp_pathnames = []

        for feat_name, dat in data.groupby(feat_col_name):
            feat_shp_pathname = [
                x for x in feat_shp_pathnames_ if os.path.splitext(x)[0].endswith(feat_name)][0]

            if isinstance(dat, pd.DataFrame) and not hasattr(dat, 'crs'):
                cls.write_to_shapefile(data=dat, write_to=feat_shp_pathname)
            else:
                gpd = _check_dependencies('geopandas')
                # os.makedirs(os.path.dirname(feat_shp_pathnames), exist_ok=True)
                gpd.GeoDataFrame(dat).to_file(
                    feat_shp_pathname, driver=cls.VECTOR_DRIVER, crs=cls.EPSG4326_WGS84_PROJ4)

            feat_shp_pathnames.append(feat_shp_pathname)

        return feat_shp_pathnames

    @classmethod
    def read_layer_shps(cls, shp_pathnames, feature_names=None, save_feat_shp=False,
                        ret_feat_shp_path=False, **kwargs):
        """
        Read a layer of OSM shapefile data.

        :param shp_pathnames: pathname of a .shp file, or pathnames of multiple shapefiles
        :type shp_pathnames: str | list
        :param feature_names: class name(s) of feature(s), defaults to ``None``
        :type feature_names: str | list | None
        :param save_feat_shp: (when ``fclass`` is not ``None``)
            whether to save data of the ``fclass`` as shapefile, defaults to ``False``
        :type save_feat_shp: bool
        :param ret_feat_shp_path: (when ``save_fclass_shp=True``)
            whether to return the path to the saved data of ``fclass``, defaults to ``False``
        :type ret_feat_shp_path: bool
        :param kwargs: [optional] parameters of the method
            :meth:`SHPReadParse.read_shp()<pydriosm.reader.SHPReadParse.read_shp>`
        :return: parsed shapefile data; and optionally,
            pathnames of the shapefiles of the specified features (when ``ret_feat_shp_path=True``)
        :rtype: pandas.DataFrame | geopandas.GeoDataFrame | tuple

        .. _`geopandas.GeoDataFrame.to_file()`:
            https://geopandas.org/reference.html#geopandas.GeoDataFrame.to_file

        **Examples**::

            >>> from pydriosm.reader import SHP
            >>> from pydriosm.downloader import GeofabrikDownloader
            >>> from pyhelpers.dirs import cd, delete_dir
            >>> import os

            >>> # Download the shapefile data of London as an example
            >>> subrgn_name = 'london'
            >>> file_format = ".shp"
            >>> dwnld_dir = "tests\\osm_data"

            >>> gfd = GeofabrikDownloader()

            >>> gfd.download_data(subrgn_name, file_format, dwnld_dir, verbose=True)
            To download .shp.zip data of the following geographic (sub)region(s):
                Greater London
            ? [No]|Yes: yes
            Downloading "greater-london-latest-free.shp.zip"
                to "tests\\osm_data\\greater-london\\" ... Done.

            >>> london_shp_zip = gfd.data_paths[0]
            >>> os.path.relpath(london_shp_zip)
            'tests\\osm_data\\greater-london\\greater-london-latest-free.shp.zip'

            >>> # Extract the downloaded .shp.zip file
            >>> london_shp_dir = SHP.unzip_shp_zip(
            ...     london_shp_zip, layer_names='railways', ret_extract_dir=True)
            >>> os.listdir(london_shp_dir)
            ['gis_osm_railways_free_1.cpg',
             'gis_osm_railways_free_1.dbf',
             'gis_osm_railways_free_1.prj',
             'gis_osm_railways_free_1.shp',
             'gis_osm_railways_free_1.shx']
            >>> london_railways_shp_path = cd(london_shp_dir, "gis_osm_railways_free_1.shp")

            >>> # Read the 'railways' layer
            >>> london_railways_shp = SHP.read_layer_shps(london_railways_shp_path)
            >>> london_railways_shp.head()
               osm_id  code  ...                                        coordinates shape_type
            0   30804  6101  ...  [(0.0048644, 51.6279262), (0.0061979, 51.62926...          3
            1  101298  6103  ...  [(-0.2249906, 51.493682), (-0.2251678, 51.4945...          3
            2  101486  6103  ...  [(-0.2055497, 51.5195429), (-0.2051377, 51.519...          3
            3  101511  6101  ...  [(-0.2119027, 51.5241906), (-0.2108059, 51.523...          3
            4  282898  6103  ...  [(-0.1862586, 51.6159083), (-0.1868721, 51.613...          3
            [5 rows x 9 columns]

            >>> # Extract only the features labelled 'rail' and save the extracted data to file
            >>> railways_rail_shp, railways_rail_shp_path = SHP.read_layer_shps(
            ...     london_railways_shp_path, feature_names='rail', save_feat_shp=True,
            ...     ret_feat_shp_path=True)
            >>> railways_rail_shp['fclass'].unique()
            array(['rail'], dtype=object)

            >>> type(railways_rail_shp_path)
            list
            >>> len(railways_rail_shp_path)
            1
            >>> os.path.basename(railways_rail_shp_path[0])
            'gis_osm_railways_free_1_rail.shp'

            >>> # Delete the download/data directory
            >>> delete_dir(dwnld_dir, verbose=True)
            To delete the directory "./tests/osm_data/" (Not empty)
            ? [No]|Yes: yes
            Deleting "./tests/osm_data/" ... Done.
        """

        lyr_shp_pathnames = [shp_pathnames] if isinstance(shp_pathnames, str) else shp_pathnames

        feat_shp_pathnames = None

        if len(lyr_shp_pathnames) == 0:
            data = None

        else:
            dat_dict = {
                lyr_shp_pathname: cls.read_shp(shp_pathname=lyr_shp_pathname, **kwargs)
                for lyr_shp_pathname in lyr_shp_pathnames}
            data = pd.concat(dat_dict.values(), axis=0, ignore_index=True)

            if feature_names:
                if isinstance(feature_names, str):
                    feat_names = [feature_names]
                else:
                    feat_names = feature_names
                feat_col_name = [x for x in data.columns if x in {'type', 'fclass'}][0]
                feat_names_ = [
                    find_similar_str(x, data[feat_col_name].unique()) for x in feat_names]

                data = data.query(f'{feat_col_name} in @feat_names_')

                if data.empty:
                    data = None

                elif save_feat_shp:
                    feat_shp_pathnames = []

                    for lyr_shp_pathname in lyr_shp_pathnames:
                        dat = dat_dict[lyr_shp_pathname]
                        valid_feature_names = dat[feat_col_name].unique()
                        feature_names_ = [x for x in feat_names_ if x in valid_feature_names]

                        feat_shp_pathnames_ = cls._make_feat_shp_pathname(
                            shp_pathname=lyr_shp_pathname, feature_names_=feature_names_)

                        feat_shp_pathnames_temp = cls._write_feat_shp(
                            data=dat.query(f'{feat_col_name} in @feature_names_'),
                            feat_col_name=feat_col_name, feat_shp_pathnames_=feat_shp_pathnames_)

                        feat_shp_pathnames += feat_shp_pathnames_temp

        if ret_feat_shp_path:
            data = data, feat_shp_pathnames

        return data

    @classmethod
    def merge_shps(cls, shp_pathnames, path_to_merged_dir, engine='pyshp', **kwargs):
        """
        Merge multiple shapefiles.

        :param shp_pathnames: list of paths to shapefiles (in .shp format)
        :type shp_pathnames: list
        :param path_to_merged_dir: path to a directory where the merged files are to be saved
        :type path_to_merged_dir: str
        :param engine: the open-source package that is used to merge/save shapefiles;
            options include: ``'pyshp'`` (default) and ``'geopandas'`` (or ``'gpd'``)
            when ``engine='geopandas'``,
            this function relies on `geopandas.GeoDataFrame.to_file()`_;
            otherwise, it by default uses `shapefile.Writer()`_
        :type engine: str

        .. _`shapefile.Writer()`:
            https://github.com/GeospatialPython/pyshp#writing-shapefiles
        .. _`geopandas.GeoDataFrame.to_file()`:
            https://geopandas.org/reference.html#geopandas.GeoDataFrame.to_file

        .. note::

            - When ``engine='geopandas'`` (or ``engine='gpd'``), the implementation of this function
              requires that `GeoPandas <https://geopandas.org/>`_ is installed.

        .. seealso::

            - Examples for the function :func:`~pydriosm.reader.SHPReadParse.merge_layer_shps`.
            - Resource: https://github.com/GeospatialPython/pyshp
        """

        if engine in {'geopandas', 'gpd'}:
            gpd = _check_dependencies('geopandas')

            shp_data = collections.defaultdict(list)
            for shp_pathname in shp_pathnames:
                dat = gpd.read_file(shp_pathname)
                geo_typ = dat.geom_type.unique()[0]
                shp_data[geo_typ].append(dat)

            for geo_typ, shp_dat_list in shp_data.items():
                out_fn = os.path.join(path_to_merged_dir, f"{geo_typ.lower()}.shp")
                shp_dat = gpd.GeoDataFrame(pd.concat(shp_dat_list, ignore_index=True))
                shp_dat.to_file(
                    filename=out_fn, driver=cls.VECTOR_DRIVER, crs=cls.EPSG4326_WGS84_PROJ4)

        else:  # method == 'pyshp': (default)
            kwargs.update({'ret_feat_shp_path': False})
            shp_data = cls.read_layer_shps(shp_pathnames, **kwargs)
            if 'geometry' in shp_data.columns:
                k = shp_data['geometry'].map(lambda x: x.geom_type)
            else:
                k = 'shape_type'

            for geo_typ, dat in shp_data.groupby(k):
                if isinstance(k, str):
                    geo_typ = cls.SHAPE_TYPE_GEOM_NAME[geo_typ]
                out_fn = os.path.join(path_to_merged_dir, f"{geo_typ.lower()}.shp")
                cls.write_to_shapefile(data=dat, write_to=out_fn)

                # Write .cpg
                with open(out_fn.replace(".shp", ".cpg"), mode="w") as cpg:
                    cpg.write(cls.ENCODING)
                # Write .prj
                with open(out_fn.replace(".shp", ".prj"), mode="w") as prj:
                    prj.write(cls.EPSG4326_WGS84_ESRI_WKT)

    @classmethod
    def _extract_files(cls, shp_zip_pathnames, layer_name, verbose=False):
        path_to_extract_dirs = []
        for zfp in shp_zip_pathnames:
            extract_dir = cls.unzip_shp_zip(
                shp_zip_pathname=zfp, layer_names=layer_name,
                verbose=True if verbose == 2 else False,
                ret_extract_dir=True)
            path_to_extract_dirs.append(extract_dir)

        return path_to_extract_dirs

    @classmethod
    def _copy_tempfiles(cls, subrgn_names_, layer_name, path_to_extract_dirs,
                        path_to_merged_dir_temp):
        # Copy files into a temp directory
        paths_to_temp_files = []

        for subregion_name, path_to_extract_dir in zip(subrgn_names_, path_to_extract_dirs):
            orig_filename_list = glob.glob(f"*_{layer_name}_*", root_dir=path_to_extract_dir)

            for orig_filename in orig_filename_list:
                orig = os.path.join(path_to_extract_dir, orig_filename)
                dest = os.path.join(
                    path_to_merged_dir_temp,
                    f"{subregion_name.lower().replace(' ', '-')}_{orig_filename}")

                shutil.copyfile(orig, dest)
                paths_to_temp_files.append(dest)

        return paths_to_temp_files

    @classmethod
    def _make_merged_dir(cls, output_dir, path_to_data_dir, merged_dirname_temp, suffix):
        if output_dir:
            path_to_merged_dir = validate_dir(path_to_dir=output_dir)
        else:
            path_to_merged_dir = os.path.join(
                path_to_data_dir, merged_dirname_temp.replace(suffix, "", -1))
        os.makedirs(path_to_merged_dir, exist_ok=True)

        return path_to_merged_dir

    @classmethod
    def _transfer_files(cls, engine, path_to_merged_dir, path_to_merged_dir_temp, prefix, suffix):
        if engine in {'geopandas', 'gpd'}:
            if not os.listdir(path_to_merged_dir):
                temp_path = os.path.join(path_to_merged_dir + "*", f"{prefix}-*")

                temp_dirs = []
                for temp_output_f in glob.glob(temp_path):
                    output_file = path_to_merged_dir_temp.replace(suffix, "")
                    shutil.move(temp_output_f, output_file)
                    temp_dirs.append(os.path.dirname(temp_output_f))

                for temp_dir in set(temp_dirs):
                    shutil.rmtree(temp_dir)

        else:  # engine == 'pyshp': (default)
            temp_dir = os.path.dirname(path_to_merged_dir)
            paths_to_output_files_temp_ = [
                glob.glob(os.path.join(temp_dir, f"{prefix}-*.{ext}"))
                for ext in {"dbf", "shp", "shx"}]
            paths_to_output_files_temp = itertools.chain.from_iterable(paths_to_output_files_temp_)

            for temp_output_f in paths_to_output_files_temp:
                output_file = os.path.join(
                    path_to_merged_dir, os.path.basename(temp_output_f).replace(suffix, ""))
                shutil.move(temp_output_f, output_file)

    @classmethod
    def merge_layers(cls, shp_zip_pathnames, layer_name, engine='pyshp', rm_zip_extracts=True,
                     output_dir=None, rm_shp_temp=True, ret_shp_pathname=False, verbose=False,
                     raise_error=False):
        """
        Merge shapefiles over a layer for multiple geographic regions.

        :param shp_zip_pathnames: list of paths to data of shapefiles (in .shp.zip format)
        :type shp_zip_pathnames: list
        :param layer_name: name of a layer (e.g. 'railways')
        :type layer_name: str
        :param engine: the open-source package used to merge/save shapefiles;
            options include: ``'pyshp'`` (default) and ``'geopandas'`` (or ``'gpd'``)
            if ``engine='geopandas'``, this function relies on `geopandas.GeoDataFrame.to_file()`_;
            otherwise, it by default uses `shapefile.Writer()`_
        :type engine: str
        :param rm_zip_extracts: whether to delete the extracted files, defaults to ``False``
        :type rm_zip_extracts: bool
        :param rm_shp_temp: whether to delete temporary layer files, defaults to ``False``
        :type rm_shp_temp: bool
        :param output_dir: if ``None`` (default), use the layer name as the name of the folder
            where the merged .shp files will be saved
        :type output_dir: str | None
        :param ret_shp_pathname: whether to return the pathname of the merged .shp file,
            defaults to ``False``
        :type ret_shp_pathname: bool
        :param verbose: whether to print relevant information in console, defaults to ``False``
        :type verbose: bool | int
        :param raise_error: Whether to raise the provided exception;
            if ``raise_error=False`` (default), the error will be suppressed.
        :type raise_error: bool
        :return: the path to the merged file when ``ret_merged_shp_path=True``
        :rtype: list

        .. _`geopandas.GeoDataFrame.to_file()`:
            https://geopandas.org/reference.html#geopandas.GeoDataFrame.to_file
        .. _`shapefile.Writer()`:
            https://github.com/GeospatialPython/pyshp#writing-shapefiles

        .. note::

            - This function does not create projection (.prj) for the merged map.
              See also
              [`MMS-1 <https://code.google.com/archive/p/pyshp/wikis/CreatePRJfiles.wiki>`_].
            - For valid ``layer_name``, check the function
              :func:`~pydriosm.utils.valid_shapefile_layer_names`.

        .. _pydriosm-reader-SHPReadParse-merge_layer_shps:

        **Examples**::

            >>> # To merge 'railways' layers of Greater Manchester and West Yorkshire"

            >>> from pydriosm.reader import SHP
            >>> from pydriosm.downloader import GeofabrikDownloader
            >>> from pyhelpers.dirs import delete_dir
            >>> import os

            >>> # Download the .shp.zip file of Manchester and West Yorkshire
            >>> subrgn_names = ['Greater Manchester', 'West Yorkshire']
            >>> file_fmt = ".shp"
            >>> data_dir = "tests\\osm_data"

            >>> gfd = GeofabrikDownloader()

            >>> gfd.download_data(subrgn_names, file_fmt, data_dir, verbose=True)
            To download .shp.zip data of the following geographic (sub)region(s):
                Greater Manchester
                West Yorkshire
            ? [No]|Yes: yes
            Downloading "greater-manchester-latest-free.shp.zip"
                to "tests\\osm_data\\greater-manchester\\" ... Done.
            Downloading "west-yorkshire-latest-free.shp.zip"
                to "tests\\osm_data\\west-yorkshire\\" ... Done.

            >>> os.path.relpath(gfd.download_dir)
            'tests\\osm_data'
            >>> len(gfd.data_paths)
            2

            >>> # Merge the layers of 'railways' of the two subregions
            >>> merged_shp_path = SHP.merge_layers(
            ...     gfd.data_paths, layer_name='railways', verbose=True, ret_shp_pathname=True)
            Merging the following shapefiles:
                "greater-manchester_gis_osm_railways_free_1.shp"
                "west-yorkshire_gis_osm_railways_free_1.shp"
                    In progress ... Done.
                    Find the merged shapefile at "tests\\osm_data\\gre_man-wes_yor-railways\\".

            >>> # Check the pathname of the merged shapefile
            >>> type(merged_shp_path)
            list
            >>> len(merged_shp_path)
            1
            >>> os.path.relpath(merged_shp_path[0])
            'tests\\osm_data\\gre_man-wes_yor-railways\\linestring.shp'

            >>> # Read the merged .shp file
            >>> merged_shp_data = SHP.read_shp(merged_shp_path[0], emulate_gpd=True)
            >>> merged_shp_data.head()
                osm_id  code  ... tunnel                                           geometry
            0   928999  6101  ...      F  LINESTRING (-2.2844621 53.4802635, -2.2851997 ...
            1   929904  6101  ...      F  LINESTRING (-2.2917977 53.4619559, -2.2924877 ...
            2   929905  6102  ...      F  LINESTRING (-2.2794048 53.4605819, -2.2799722 ...
            3  3663332  6102  ...      F  LINESTRING (-2.2382139 53.4817985, -2.2381708 ...
            4  3996086  6101  ...      F  LINESTRING (-2.6003053 53.4604346, -2.6005261 ...
            [5 rows x 8 columns]

            >>> # Delete the test data directory
            >>> delete_dir(gfd.download_dir, verbose=True)
            To delete the directory "./tests/osm_data/" (Not empty)
            ? [No]|Yes: yes
            Deleting "./tests/osm_data/" ... Done.

        .. seealso::

            - Examples for the method
              :meth:`GeofabrikReader.merge_subregion_layer_shp()
              <pydriosm.reader.GeofabrikReader.merge_subregion_layer_shp>`.
        """

        path_to_extract_dirs = cls._extract_files(
            shp_zip_pathnames=shp_zip_pathnames, layer_name=layer_name, verbose=verbose)

        # Specify a directory that stores files for the specific layer
        subrgn_names_ = [
            re.search(r'.*(?=\.shp\.zip)', os.path.basename(x).replace("-latest-free", "")).group(0)
            for x in shp_zip_pathnames]

        suffix = "_temp"
        prefix = "-".join(["_".join([y[:3] for y in re.split(r'[- ]', x)]) for x in subrgn_names_])
        # prefix = "_".join([x.lower().replace(' ', '-') for x in region_names]) + "_"
        path_to_data_dir = os.path.commonpath(shp_zip_pathnames)
        merged_dirname_temp = f"{prefix}-{layer_name}{suffix}"
        path_to_merged_dir_temp = os.path.join(path_to_data_dir, merged_dirname_temp)
        os.makedirs(path_to_merged_dir_temp, exist_ok=True)

        paths_to_temp_files = cls._copy_tempfiles(
            subrgn_names_=subrgn_names_, layer_name=layer_name,
            path_to_extract_dirs=path_to_extract_dirs,
            path_to_merged_dir_temp=path_to_merged_dir_temp)

        # Get the paths to the target .shp files
        paths_to_shp_files = [x for x in paths_to_temp_files if x.endswith(".shp")]

        if verbose:
            print("Merging the following shapefiles:")
            print("\t" + "\n\t".join(f"\"{os.path.basename(f)}\"" for f in paths_to_shp_files))
            print("\t\tIn progress ... ", end="")

        try:
            path_to_merged_dir = cls._make_merged_dir(
                output_dir=output_dir, path_to_data_dir=path_to_data_dir,
                merged_dirname_temp=merged_dirname_temp, suffix=suffix)

            cls.merge_shps(
                shp_pathnames=paths_to_shp_files, path_to_merged_dir=path_to_merged_dir,
                engine=engine)

            cls._transfer_files(
                engine=engine, path_to_merged_dir=path_to_merged_dir,
                path_to_merged_dir_temp=path_to_merged_dir_temp, prefix=prefix, suffix=suffix)

            if verbose:
                print("Done.")

            if rm_zip_extracts:
                for path_to_extract_dir in path_to_extract_dirs:
                    shutil.rmtree(path_to_extract_dir)

            if rm_shp_temp:
                shutil.rmtree(path_to_merged_dir_temp)

            if verbose:
                m_rel_path = check_relative_pathname(path_to_merged_dir)
                print(f"    Find the merged shapefile at \"{m_rel_path}\".")

            if ret_shp_pathname:
                path_to_merged_shp = glob.glob(os.path.join(f"{path_to_merged_dir}*", "*.shp"))
                # if len(path_to_merged_shp) == 1:
                #     path_to_merged_shp = path_to_merged_shp[0]
                return path_to_merged_shp

        except Exception as e:
            _print_failure_message(
                e, prefix="Failed. Error:", verbose=verbose, raise_error=raise_error)
