"""
Parsing the OSM data extracts of various file formats.
"""

import collections
import copy
import glob
import itertools
import lzma
import multiprocessing
import os
import re
import shutil
import zipfile

import pandas as pd
import shapefile as pyshp
import shapely.geometry
from pyhelpers._cache import _check_dependency, _format_err_msg
from pyhelpers.dirs import cd, validate_dir
from pyhelpers.ops import split_list
from pyhelpers.settings import gdal_configurations
from pyhelpers.text import find_similar_str

from pydriosm.downloader import GeofabrikDownloader
from pydriosm.reader.transformer import Transformer
from pydriosm.utils import check_json_engine, check_relpath


class SHPReadParse:
    """
    Read/parse `Shapefile <https://wiki.openstreetmap.org/wiki/Shapefiles>`_ data.

    **Examples**::

        >>> from pydriosm.reader import SHPReadParse

        >>> SHPReadParse.EPSG4326_WGS84_PROJ4
        '+proj=longlat +ellps=WGS84 +datum=WGS84 +no_defs'

        >>> SHPReadParse.EPSG4326_WGS84_PROJ4_
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

    #: dict: Shape type codes of shapefiles and their corresponding geometry object names
    SHAPE_TYPE_GEOM_NAME = {k: v.__name__ for k, v in SHAPE_TYPE_GEOM.items()}

    #: dict: Shape type codes of shapefiles and their corresponding names for an OSM shapefile.
    SHAPE_TYPE_NAME_LOOKUP = {
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

    #: str: The encoding method applied to create an OSM shapefile.
    #: This is for writing .cpg (code page) file.
    ENCODING = 'UTF-8'  # 'ISO-8859-1'

    #: str: The metadata associated with the shapefiles coordinate and projection system.
    #: `ESRI WKT <https://spatialreference.org/ref/epsg/4326/esriwkt/>`_ of
    #: EPSG Projection 4326 - WGS 84 (`EPSG:4326 <https://spatialreference.org/ref/epsg/wgs-84/>`_)
    #: for shapefile data.
    EPSG4326_WGS84_ESRI_WKT = \
        'GEOGCS["GCS_WGS_1984",DATUM["D_WGS_1984",SPHEROID["WGS_1984",6378137.0,298.257223563]],' \
        'PRIMEM["Greenwich",0.0],' \
        'UNIT["Degree",0.017453292519943295]]'

    #: str: `Proj4 <https://spatialreference.org/ref/epsg/wgs-84/proj4/>`_ of
    #: EPSG Projection 4326 - WGS 84 (`EPSG:4326 <https://spatialreference.org/ref/epsg/wgs-84/>`_)
    #: for the setting of `CRS <https://en.wikipedia.org/wiki/Spatial_reference_system>`_
    #: for shapefile data.
    EPSG4326_WGS84_PROJ4 = '+proj=longlat +ellps=WGS84 +datum=WGS84 +no_defs'

    #: dict: A dict-type representation of EPSG Projection 4326 - WGS 84
    #: (`EPSG:4326 <https://spatialreference.org/ref/epsg/wgs-84/>`_) for the setting of
    #: `CRS <https://en.wikipedia.org/wiki/Spatial_reference_system>`_ for shapefile data.
    EPSG4326_WGS84_PROJ4_ = {
        'proj': 'longlat',
        'ellps': 'WGS84',
        'datum': 'WGS84',
        'no_defs': True,
    }

    #: set: Valid layer names for an OSM shapefile.
    LAYER_NAMES = {
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
    VECTOR_DRIVER = 'ESRI Shapefile'

    @classmethod
    def validate_shp_layer_names(cls, layer_names):
        """
        Validate the input of layer name(s) for reading shapefiles.

        :param layer_names: name of a shapefile layer, e.g. 'railways',
            or names of multiple layers; if ``None`` (default), returns an empty list;
            if ``layer_names='all'``, the function returns a list of all available layers
        :type layer_names: str | list | None
        :return: valid layer names to be input
        :rtype: list

        **Examples**::

            >>> from pydriosm.reader import SHPReadParse

            >>> SHPReadParse.validate_shp_layer_names(None)
            []

            >>> SHPReadParse.validate_shp_layer_names('point')
            ['points']

            >>> SHPReadParse.validate_shp_layer_names(['point', 'land'])
            ['points', 'landuse']

            >>> SHPReadParse.validate_shp_layer_names('all')
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
    def find_shp_layer_name(cls, shp_filename):
        """
        Find the layer name of OSM shapefile given its filename.

        :param shp_filename: filename of a shapefile (.shp)
        :type shp_filename: str
        :return: layer name of the shapefile
        :rtype: str

        **Examples**::

            >>> from pydriosm.reader import SHPReadParse

            >>> SHPReadParse.find_shp_layer_name("") is None
            True

            >>> SHPReadParse.find_shp_layer_name("gis_osm_railways_free_1.shp")
            'railways'

            >>> SHPReadParse.find_shp_layer_name("gis_osm_transport_a_free_1.shp")
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

    @classmethod
    def unzip_shp_zip(cls, shp_zip_pathname, extract_to=None, layer_names=None, separate=False,
                      ret_extract_dir=False, verbose=False):
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
        :return: the path to the directory of extracted files when ``ret_extract_dir=True``
        :rtype: str

        **Examples**::

            >>> from pydriosm.reader import SHPReadParse
            >>> from pydriosm.downloader import GeofabrikDownloader
            >>> from pyhelpers.dirs import cd, delete_dir
            >>> import os

            >>> # Download the shapefile data of London as an example
            >>> subrgn_name = 'london'
            >>> file_format = ".shp"
            >>> dwnld_dir = "tests\\osm_data"

            >>> gfd = GeofabrikDownloader()

            >>> gfd.download_osm_data(subrgn_name, file_format, dwnld_dir, verbose=True)
            To download .shp.zip data of the following geographic (sub)region(s):
                Greater London
            ? [No]|Yes: yes
            Downloading "greater-london-latest-free.shp.zip"
                to "tests\\osm_data\\greater-london\\" ... Done.

            >>> path_to_shp_zip = gfd.data_paths[0]
            >>> os.path.relpath(path_to_shp_zip)
            'tests\\osm_data\\greater-london\\greater-london-latest-free.shp.zip'

            >>> # To extract data of a specific layer 'railways'
            >>> london_railways_dir = SHPReadParse.unzip_shp_zip(
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
            >>> dirs_of_layers = SHPReadParse.unzip_shp_zip(
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
            >>> london_shp_dir = SHPReadParse.unzip_shp_zip(
            ...     path_to_shp_zip, verbose=True, ret_extract_dir=True)
            Extracting "tests\\osm_data\\greater-london\\greater-london-latest-free.shp.zip"
                to "tests\\osm_data\\greater-london\\greater-london-latest-free-shp\\" ... Done.

            >>> # Check the directory
            >>> os.path.relpath(london_shp_dir)
            'tests\\osm_data\\greater-london\\greater-london-latest-free-shp'
            >>> len(os.listdir(london_shp_dir))
            91
            >>> # Get the names of all available layers
            >>> set(filter(None, map(SHPReadParse.find_shp_layer_name, os.listdir(london_shp_dir))))
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
            To delete the directory "tests\\osm_data\\" (Not empty)
            ? [No]|Yes: yes
            Deleting "tests\\osm_data\\" ... Done.
        """

        if extract_to:
            extract_dir = extract_to
        else:
            extract_dir = os.path.splitext(shp_zip_pathname)[0].replace(".", "-")

        shp_zip_rel_path, extrdir_rel_path = map(check_relpath, [shp_zip_pathname, extract_dir])

        if not layer_names:
            layer_names_ = layer_names
            if verbose:
                print(
                    f"Extracting \"{shp_zip_rel_path}\"\n\tto \"{extrdir_rel_path}\\\"",
                    end=" ... ")
        else:
            layer_names_ = [layer_names] if isinstance(layer_names, str) else layer_names.copy()
            if verbose:
                layer_name_list = "\t" + "\n\t".join([f"'{x}'" for x in layer_names_])
                print(f"Extracting the following layer(s):\n{layer_name_list}")
                print(
                    f"\tfrom \"{shp_zip_rel_path}\"\n\t  to \"{extrdir_rel_path}\\\"", end=" ... ")

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

                file_list = extract_files if extract_files else os.listdir(extract_dir)
                if 'README' in file_list:
                    file_list.remove('README')

                filenames, exts = map(
                    lambda x: list(set(x)), zip(*map(os.path.splitext, file_list)))

                layer_names_ = [cls.find_shp_layer_name(f) for f in filenames]

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

                if verbose:
                    print("Done.")

        except Exception as e:
            print(f"Failed. {_format_err_msg(e)}")

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

            >>> from pydriosm.reader import SHPReadParse
            >>> from pydriosm.downloader import GeofabrikDownloader
            >>> from pyhelpers.dirs import cd, delete_dir
            >>> import os
            >>> import glob

            >>> # Download the shapefile data of London as an example
            >>> subrgn_name = 'london'
            >>> file_format = ".shp"
            >>> dwnld_dir = "tests\\osm_data"

            >>> gfd = GeofabrikDownloader()

            >>> gfd.download_osm_data(subrgn_name, file_format, dwnld_dir, verbose=True)
            To download .shp.zip data of the following geographic (sub)region(s):
                Greater London
            ? [No]|Yes: yes
            Downloading "greater-london-latest-free.shp.zip"
                to "tests\\osm_data\\greater-london\\" ... Done.

            >>> london_shp_zip = gfd.data_paths[0]
            >>> os.path.relpath(london_shp_zip)
            'tests\\osm_data\\greater-london\\greater-london-latest-free.shp.zip'

            >>> # Extract all
            >>> london_shp_dir = SHPReadParse.unzip_shp_zip(london_shp_zip, ret_extract_dir=True)

            >>> # Get the pathname of the .shp data of 'railways'
            >>> path_to_railways_shp = glob.glob(cd(london_shp_dir, "*railways*.shp"))[0]
            >>> os.path.relpath(path_to_railways_shp)  # Check the pathname of the .shp file
            'tests\\osm_data\\greater-london\\greater-london-latest-free-shp\\gis_osm_railwa...

            >>> # Read the data of 'railways'
            >>> london_railways = SHPReadParse.read_shp(path_to_railways_shp)
            >>> london_railways.head()
               osm_id  code  ...                                        coordinates shape_type
            0   30804  6101  ...  [(0.0048644, 51.6279262), (0.0061979, 51.62926...          3
            1  101298  6103  ...  [(-0.2249906, 51.493682), (-0.2251678, 51.4945...          3
            2  101486  6103  ...  [(-0.2055497, 51.5195429), (-0.2051377, 51.519...          3
            3  101511  6101  ...  [(-0.2119027, 51.5241906), (-0.2108059, 51.523...          3
            4  282898  6103  ...  [(-0.1862586, 51.6159083), (-0.1868721, 51.613...          3
            [5 rows x 9 columns]

            >>> # Set `emulate_gpd=True` to return data of similar format to what GeoPandas does
            >>> london_railways = SHPReadParse.read_shp(path_to_railways_shp, emulate_gpd=True)
            >>> london_railways.head()
               osm_id  code  ... tunnel                                           geometry
            0   30804  6101  ...      F  LINESTRING (0.0048644 51.6279262, 0.0061979 51...
            1  101298  6103  ...      F  LINESTRING (-0.2249906 51.493682, -0.2251678 5...
            2  101486  6103  ...      F  LINESTRING (-0.2055497 51.5195429, -0.2051377 ...
            3  101511  6101  ...      F  LINESTRING (-0.2119027 51.5241906, -0.2108059 ...
            4  282898  6103  ...      F  LINESTRING (-0.1862586 51.6159083, -0.1868721 ...
            [5 rows x 8 columns]

            >>> # Alternatively, set `engine` to be 'geopandas' (or 'gpd') to use GeoPandas
            >>> london_railways_ = SHPReadParse.read_shp(path_to_railways_shp, engine='geopandas')
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
            To delete the directory "tests\\osm_data\\" (Not empty)
            ? [No]|Yes: yes
            Deleting "tests\\osm_data\\" ... Done.
        """

        if engine in {'geopandas', 'gpd'}:
            gpd = _check_dependency(name='geopandas')
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

        return shp_data

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
            'object': 'C',
            'int64': 'N',
            'int32': 'N',
            'float64': 'F',
            'float32': 'F',
            'bool': 'L',
            'datetime64': 'D',
        }

        fields = []

        for field_name, dtype, in data[field_names].dtypes.items():
            try:
                max_size = data[field_name].map(len).max()
            except TypeError:
                max_size = data[field_name].astype(str).map(len).max()

            if 'float' in dtype.name:
                decimal = decimal_precision
            else:
                decimal = 0

            fields.append((field_name, dtype_shp_type[dtype.name], max_size, decimal))

        return fields

    @classmethod
    def write_to_shapefile(cls, data, write_to, shp_filename=None, decimal_precision=5,
                           ret_shp_pathname=False, verbose=False):
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

        **Examples**::

            >>> from pydriosm.reader import SHPReadParse
            >>> from pydriosm.downloader import GeofabrikDownloader
            >>> from pyhelpers.dirs import cd, delete_dir
            >>> import os
            >>> import glob

            >>> # Download the shapefile data of London as an example
            >>> subrgn_name = 'london'
            >>> file_format = ".shp"
            >>> dwnld_dir = "tests\\osm_data"

            >>> gfd = GeofabrikDownloader()

            >>> gfd.download_osm_data(subrgn_name, file_format, dwnld_dir, verbose=True)
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

            >>> railways_shp_dir = SHPReadParse.unzip_shp_zip(
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
            >>> london_railways_shp = SHPReadParse.read_shp(path_to_railways_shp)

            >>> # Create a new directory for saving the 'railways' data
            >>> railways_subdir = cd(os.path.dirname(railways_shp_dir), lyr_name)
            >>> os.path.relpath(railways_subdir)
            'tests\\osm_data\\greater-london\\railways'

            >>> # Save the data of 'railways' to the new directory
            >>> path_to_railways_shp_ = SHPReadParse.write_to_shapefile(
            ...     london_railways_shp, railways_subdir, ret_shp_pathname=True, verbose=True)
            Writing data to "tests\\osm_data\\greater-london\\railways\\railways.*" ... Done.
            >>> os.path.basename(path_to_railways_shp_)
            'railways.shp'

            >>> # If `shp_filename` is specified
            >>> path_to_railways_shp_ = SHPReadParse.write_to_shapefile(
            ...     london_railways_shp, railways_subdir, shp_filename="rail_data",
            ...     ret_shp_pathname=True, verbose=True)
            Writing data to "tests\\osm_data\\greater-london\\railways\\rail_data.*" ... Done.
            >>> os.path.basename(path_to_railways_shp_)
            'rail_data.shp'

            >>> # Retrieve the saved the .shp file
            >>> london_railways_shp_ = SHPReadParse.read_shp(path_to_railways_shp_)

            >>> # Check if the retrieved .shp data is equal to the original one
            >>> london_railways_shp_.equals(london_railways_shp)
            True

            >>> # Delete the download/data directory
            >>> delete_dir(gfd.download_dir, verbose=True)
            To delete the directory "tests\\osm_data\\" (Not empty)
            ? [No]|Yes: yes
            Deleting "tests\\osm_data\\" ... Done.
        """

        filename_ = os.path.basename(write_to) if shp_filename is None else copy.copy(shp_filename)
        filename = os.path.splitext(filename_)[0]
        write_to_ = os.path.join(os.path.dirname(write_to), filename)

        if verbose:
            print(f'Writing data to "{check_relpath(write_to_)}.*"', end=" ... ")

        try:
            key_column_names = ['coordinates', 'shape_type']
            dat = data.copy()

            if 'geometry' in data:
                coords_and_shape_type = pd.DataFrame(
                    dat['geometry'].map(cls._convert_to_coords_and_shape_type).to_list(),
                    columns=key_column_names, index=dat.index)
                del dat['geometry']
                dat = pd.concat([dat, coords_and_shape_type], axis=1)

            field_names = [x for x in dat.columns if x not in key_column_names]

            shape_type = dat['shape_type'].unique()[0]

            with pyshp.Writer(target=write_to_, shapeType=shape_type, autoBalance=True) as w:
                w.fields = cls._specify_pyshp_fields(
                    data=dat, field_names=field_names, decimal_precision=decimal_precision)

                for i in dat.index:
                    w.record(*dat.loc[i, field_names].to_list())

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
            print(f"Failed. {_format_err_msg(e)}")

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

            >>> from pydriosm.reader import SHPReadParse
            >>> import os

            >>> fn = "gis_osm_railways_free_1.shp"
            >>> feats = ['rail']
            >>> pn = SHPReadParse._make_feat_shp_pathname(shp_pathname=fn, feature_names_=feats)
            >>> len(pn)
            1
            >>> os.path.relpath(pn[0])
            'gis_osm_railways_free_1_rail.shp'

            >>> fn = "tests\\osm_data\\greater-london\\gis_osm_transport_free_1.shp"
            >>> feats = ['railway_station', 'bus_stop', 'bus_station']
            >>> pn = SHPReadParse._make_feat_shp_pathname(shp_pathname=fn, feature_names_=feats)
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
                gpd = _check_dependency('geopandas')
                assert isinstance(dat, gpd.GeoDataFrame)
                # os.makedirs(os.path.dirname(feat_shp_pathnames), exist_ok=True)
                dat.to_file(
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

            >>> from pydriosm.reader import SHPReadParse
            >>> from pydriosm.downloader import GeofabrikDownloader
            >>> from pyhelpers.dirs import cd, delete_dir
            >>> import os

            >>> # Download the shapefile data of London as an example
            >>> subrgn_name = 'london'
            >>> file_format = ".shp"
            >>> dwnld_dir = "tests\\osm_data"

            >>> gfd = GeofabrikDownloader()

            >>> gfd.download_osm_data(subrgn_name, file_format, dwnld_dir, verbose=True)
            To download .shp.zip data of the following geographic (sub)region(s):
                Greater London
            ? [No]|Yes: yes
            Downloading "greater-london-latest-free.shp.zip"
                to "tests\\osm_data\\greater-london\\" ... Done.

            >>> london_shp_zip = gfd.data_paths[0]
            >>> os.path.relpath(london_shp_zip)
            'tests\\osm_data\\greater-london\\greater-london-latest-free.shp.zip'

            >>> # Extract the downloaded .shp.zip file
            >>> london_shp_dir = SHPReadParse.unzip_shp_zip(
            ...     london_shp_zip, layer_names='railways', ret_extract_dir=True)
            >>> os.listdir(london_shp_dir)
            ['gis_osm_railways_free_1.cpg',
             'gis_osm_railways_free_1.dbf',
             'gis_osm_railways_free_1.prj',
             'gis_osm_railways_free_1.shp',
             'gis_osm_railways_free_1.shx']
            >>> london_railways_shp_path = cd(london_shp_dir, "gis_osm_railways_free_1.shp")

            >>> # Read the 'railways' layer
            >>> london_railways_shp = SHPReadParse.read_layer_shps(london_railways_shp_path)
            >>> london_railways_shp.head()
               osm_id  code  ...                                        coordinates shape_type
            0   30804  6101  ...  [(0.0048644, 51.6279262), (0.0061979, 51.62926...          3
            1  101298  6103  ...  [(-0.2249906, 51.493682), (-0.2251678, 51.4945...          3
            2  101486  6103  ...  [(-0.2055497, 51.5195429), (-0.2051377, 51.519...          3
            3  101511  6101  ...  [(-0.2119027, 51.5241906), (-0.2108059, 51.523...          3
            4  282898  6103  ...  [(-0.1862586, 51.6159083), (-0.1868721, 51.613...          3
            [5 rows x 9 columns]

            >>> # Extract only the features labelled 'rail' and save the extracted data to file
            >>> railways_rail_shp, railways_rail_shp_path = SHPReadParse.read_layer_shps(
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
            To delete the directory "tests\\osm_data\\" (Not empty)
            ? [No]|Yes: yes
            Deleting "tests\\osm_data\\" ... Done.
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
            gpd = _check_dependency(name='geopandas')

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
            orig_filename_list = glob.glob1(path_to_extract_dir, f"*_{layer_name}_*")

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
    def merge_layer_shps(cls, shp_zip_pathnames, layer_name, engine='pyshp', rm_zip_extracts=True,
                         output_dir=None, rm_shp_temp=True, ret_shp_pathname=False, verbose=False):
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

            >>> from pydriosm.reader import SHPReadParse
            >>> from pydriosm.downloader import GeofabrikDownloader
            >>> from pyhelpers.dirs import delete_dir
            >>> import os

            >>> # Download the .shp.zip file of Manchester and West Yorkshire
            >>> subrgn_names = ['Greater Manchester', 'West Yorkshire']
            >>> file_fmt = ".shp"
            >>> data_dir = "tests\\osm_data"

            >>> gfd = GeofabrikDownloader()

            >>> gfd.download_osm_data(subrgn_names, file_fmt, data_dir, verbose=True)
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
            >>> merged_shp_path = SHPReadParse.merge_layer_shps(
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
            >>> merged_shp_data = SHPReadParse.read_shp(merged_shp_path[0], emulate_gpd=True)
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
            To delete the directory "tests\\osm_data\\" (Not empty)
            ? [No]|Yes: yes
            Deleting "tests\\osm_data\\" ... Done.

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
                m_rel_path = check_relpath(path_to_merged_dir)
                print(f"\t\tFind the merged shapefile at \"{m_rel_path}\\\".")

            if ret_shp_pathname:
                path_to_merged_shp = glob.glob(os.path.join(f"{path_to_merged_dir}*", "*.shp"))
                # if len(path_to_merged_shp) == 1:
                #     path_to_merged_shp = path_to_merged_shp[0]
                return path_to_merged_shp

        except Exception as e:
            print(f"Failed. {_format_err_msg(e)}")


class PBFReadParse(Transformer):
    """
    Read/parse `PBF <https://wiki.openstreetmap.org/wiki/PBF_Format>`_ data.

    **Examples**::

        >>> from pydriosm.reader import PBFReadParse

        >>> PBFReadParse.LAYER_GEOM
        {'points': shapely.geometry.point.Point,
         'lines': shapely.geometry.linestring.LineString,
         'multilinestrings': shapely.geometry.multilinestring.MultiLineString,
         'multipolygons': shapely.geometry.multipolygon.MultiPolygon,
         'other_relations': shapely.geometry.collection.GeometryCollection}
    """

    #: dict: Layer names of an OSM PBF file and their corresponding
    #: `geometric objects <https://shapely.readthedocs.io/en/latest/manual.html#geometric-objects>`_
    #: defined in `Shapely <https://pypi.org/project/Shapely/>`_.
    LAYER_GEOM = {
        'points': shapely.geometry.Point,
        'lines': shapely.geometry.LineString,
        'multilinestrings': shapely.geometry.MultiLineString,
        'multipolygons': shapely.geometry.MultiPolygon,
        'other_relations': shapely.geometry.GeometryCollection,
    }

    @classmethod
    def get_pbf_layer_geom_types(cls, shape_name=False):
        """
        A dictionary cross-referencing the names of PBF layers and their corresponding
        `geometric objects`_ defined in `Shapely`_, or names.

        :param shape_name: whether to return the names of geometry shapes, defaults to ``False``
        :type shape_name: bool
        :return: a dictionary with keys and values being, respectively,
            PBF layers and their corresponding `geometric objects`_ defined in `Shapely`_
        :rtype: dict

        .. _`geometric objects`:
            https://shapely.readthedocs.io/en/latest/manual.html#geometric-objects
        .. _`Shapely`:
            https://pypi.org/project/Shapely/

        **Examples**::

            >>> from pydriosm.reader import PBFReadParse

            >>> PBFReadParse.get_pbf_layer_geom_types()
            {'points': shapely.geometry.point.Point,
             'lines': shapely.geometry.linestring.LineString,
             'multilinestrings': shapely.geometry.multilinestring.MultiLineString,
             'multipolygons': shapely.geometry.multipolygon.MultiPolygon,
             'other_relations': shapely.geometry.collection.GeometryCollection}

            >>> PBFReadParse.get_pbf_layer_geom_types(shape_name=True)
            {'points': 'Point',
             'lines': 'LineString',
             'multilinestrings': 'MultiLineString',
             'multipolygons': 'MultiPolygon',
             'other_relations': 'GeometryCollection'}
        """

        pbf_layer_geom_dict = cls.LAYER_GEOM.copy()

        if shape_name:
            pbf_layer_geom_dict = {k: v.__name__ for k, v in pbf_layer_geom_dict.items()}

        return pbf_layer_geom_dict

    @classmethod
    def get_pbf_layer_names(cls, pbf_pathname, verbose=False):
        """
        Get names (and indices) of all available layers in a PBF data file.

        :param pbf_pathname: path to a PBF data file
        :type pbf_pathname: str | os.PathLike[str]
        :param verbose: whether to print relevant information in console, defaults to ``False``
        :type verbose: bool | int
        :return: indices and names of each layer of the PBF data file
        :rtype: dict

        **Examples**::

            >>> from pydriosm.reader import PBFReadParse
            >>> from pydriosm.downloader import GeofabrikDownloader
            >>> from pyhelpers.dirs import delete_dir
            >>> import os

            >>> # Download the PBF data file of London as an example
            >>> subrgn_name = 'london'
            >>> file_format = ".pbf"
            >>> dwnld_dir = "tests\\osm_data"

            >>> gfd = GeofabrikDownloader()

            >>> gfd.download_osm_data(subrgn_name, file_format, dwnld_dir, verbose=True)
            To download .osm.pbf data of the following geographic (sub)region(s):
                Greater London
            ? [No]|Yes: yes
            Downloading "greater-london-latest.osm.pbf"
                to "tests\\osm_data\\greater-london\\" ... Done.

            >>> london_pbf_pathname = gfd.data_paths[0]
            >>> os.path.relpath(london_pbf_pathname)
            'tests\\osm_data\\greater-london\\greater-london-latest.osm.pbf'

            >>> # Get indices and names of all layers in the downloaded PBF data file
            >>> pbf_layer_idx_names = PBFReadParse.get_pbf_layer_names(london_pbf_pathname)
            >>> type(pbf_layer_idx_names)
            dict
            >>> pbf_layer_idx_names
            {0: 'points',
             1: 'lines',
             2: 'multilinestrings',
             3: 'multipolygons',
             4: 'other_relations'}

            >>> # Delete the download directory (and the downloaded PBF data file)
            >>> delete_dir(gfd.download_dir, verbose=True)
            To delete the directory "tests\\osm_data\\" (Not empty)
            ? [No]|Yes: yes
            Deleting "tests\\osm_data\\" ... Done.
        """

        if verbose:
            print(f"Getting the layer names of \"{check_relpath(pbf_pathname)}\"", end=" ... ")

        try:
            osgeo_ogr = _check_dependency(name='osgeo.ogr')

            f = osgeo_ogr.Open(pbf_pathname)

            layer_count = f.GetLayerCount()
            layer_names = [f.GetLayerByIndex(i).GetName() for i in range(layer_count)]

            layer_idx_names = dict(zip(range(layer_count), layer_names))

            if verbose:
                print("Done.")

            return layer_idx_names

        except Exception as e:
            print(f"Failed. {_format_err_msg(e)}")

    @classmethod
    def transform_pbf_layer_field(cls, layer_data, layer_name, parse_geometry=False,
                                  parse_properties=False, parse_other_tags=False):
        """
        Parse data of a layer of PBF data.

        :param layer_data: dataframe of a specific layer of PBF data
        :type layer_data: pandas.DataFrame | pandas.Series
        :param layer_name: name (geometric type) of the PBF layer
        :type layer_name: str
        :param parse_geometry: whether to represent the ``'geometry'`` field
            in a `shapely.geometry`_ format, defaults to ``False``
        :type parse_geometry: bool
        :param parse_properties: whether to represent the ``'properties'`` field
            in a tabular format, defaults to ``False``
        :type parse_properties: bool
        :param parse_other_tags: whether to represent a ``'other_tags'`` (of ``'properties'``)
            in a `dict`_ format, defaults to ``False``
        :type parse_other_tags: bool
        :return: readable data of the given PBF layer
        :rtype: pandas.DataFrame | pandas.Series

        .. _`shapely.geometry`:
            https://shapely.readthedocs.io/en/latest/manual.html#geometric-objects
        .. _`dict`:
            https://docs.python.org/3/library/stdtypes.html#dict

        See examples for the method
        :meth:`PBFReadParse.read_pbf()<pydriosm.reader.PBFReadParse.read_pbf>`.
        """

        if not layer_data.empty:
            lyr_dat = layer_data.copy()

            if isinstance(lyr_dat, pd.Series):
                if parse_geometry:  # Reformat the geometry
                    lyr_dat = cls.transform_geometry(layer_data=lyr_dat, layer_name=layer_name)

                if parse_other_tags:  # Reformat the 'other_tags' of properties
                    lyr_dat = lyr_dat.map(lambda x: cls.update_other_tags(x, mode=2))

            else:
                # Whether to reformat the 'geometry'
                if parse_geometry:
                    geom_data = cls.transform_geometry(layer_data=lyr_dat, layer_name=layer_name)
                else:
                    geom_data = lyr_dat['geometry']

                # Whether to reformat the 'properties'
                prop_data, prop_col_name, ot_name = None, 'properties', 'other_tags'
                if parse_properties:  # Expand the dict-type 'properties'
                    prop_data = pd.DataFrame(list(lyr_dat[prop_col_name]))
                    if 'osm_id' in prop_data.columns:
                        # if layer_data['id'].equals(prop_data['osm_id'].astype(np.int64))
                        del prop_data['osm_id']
                    if parse_other_tags:
                        # Reformat the properties
                        prop_data.loc[:, ot_name] = prop_data[ot_name].map(cls.transform_other_tags)
                else:
                    # Whether to reformat 'other_tags'
                    if parse_other_tags:
                        prop_data = lyr_dat[prop_col_name].map(cls.update_other_tags)
                    else:
                        prop_data = lyr_dat[prop_col_name]

                lyr_dat = pd.concat([lyr_dat[['id']], geom_data, prop_data], axis=1)

        else:
            lyr_dat = layer_data

            if isinstance(lyr_dat, pd.DataFrame):
                if 'type' in lyr_dat.columns:
                    if 'Feature' in lyr_dat['type'].unique() and lyr_dat['type'].nunique() == 1:
                        del lyr_dat['type']

        if isinstance(lyr_dat, pd.DataFrame):
            if 'id' in lyr_dat.columns:
                lyr_dat.sort_values('id', ignore_index=True, inplace=True)

        return lyr_dat

    @classmethod
    def _read_pbf_layer(cls, layer, readable, expand, parse_geometry, parse_properties,
                        parse_other_tags):
        """
        Parse a layer of a PBF data file.

        :param layer: a layer of a PBF data file, loaded by `GDAL/OGR`_
        :type layer: osgeo.ogr.Layer | list
        :param readable: whether to parse each feature in the raw data, defaults to ``False``
        :type readable: bool
        :param expand: whether to expand dict-like data into separate columns, defaults to ``False``
        :type expand: bool
        :param parse_geometry: whether to represent the ``'geometry'`` field
            in a `shapely.geometry`_ format
        :type parse_geometry: bool
        :param parse_properties: whether to represent the ``'properties'`` field
            in a tabular format
        :type parse_properties: bool
        :param parse_other_tags: whether to represent the ``'other_tags'`` (of ``'properties'``)
            in a `dict`_ format
        :type parse_other_tags: bool
        :return: data of the given layer of the given OSM PBF layer
        :rtype: pandas.DataFrame | list

        .. _`GDAL/OGR`:
            https://gdal.org
        .. _`shapely.geometry`:
            https://shapely.readthedocs.io/en/latest/manual.html#geometric-objects
        .. _`dict`:
            https://docs.python.org/3/library/stdtypes.html#dict

        See examples for the method
        :meth:`PBFReadParse.read_pbf()<pydriosm.reader.PBFReadParse.read_pbf>`.
        """

        if readable or expand:
            # Replaced: readable = True if parse_geometry or parse_other_tags else readable
            if isinstance(layer, list):
                layer_name = layer[-1]
                del layer[-1]
            else:
                layer_name = layer.GetName()

            dat = [f.ExportToJson(as_object=True) for f in layer]

            if expand:
                lyr_dat = pd.DataFrame(dat)
            else:
                lyr_dat = pd.Series(data=dat, name=layer_name)

            layer_data = cls.transform_pbf_layer_field(
                layer_data=lyr_dat, layer_name=layer_name, parse_geometry=parse_geometry,
                parse_properties=parse_properties, parse_other_tags=parse_other_tags)

        else:
            if isinstance(layer, list):
                del layer[-1]

            layer_data = [f for f in layer]
            # layer_data = pd.Series(data=layer_data, name=layer_name)

        return layer_data

    @classmethod
    def _read_pbf_layer_chunkwise(cls, layer, number_of_chunks, **kwargs):
        """
        Parse a layer of a PBF data file chunk-wisely.

        :param layer: a layer of a PBF data file, loaded by `GDAL/OGR <https://gdal.org>`_
        :type layer: osgeo.ogr.Layer
        :param number_of_chunks: number of chunks
        :type number_of_chunks: int
        :param kwargs: [optional] parameters of the method
            :meth:`PBFReadParse._read_pbf_layer()<pydriosm.reader.PBFReadParse._read_pbf_layer>`
        :return: data of the given layer of the given OSM PBF layer
        :rtype: pandas.DataFrame | list

        See examples for the method
        :meth:`PBFReadParse.read_pbf()<pydriosm.reader.PBFReadParse.read_pbf>`.
        """

        layer_name = layer.GetName()
        layer_chunks = split_list(lst=[f for f in layer], num_of_sub=number_of_chunks)

        list_of_layer_dat = [
            cls._read_pbf_layer(lyr + [layer_name], **kwargs) for lyr in layer_chunks]

        if kwargs['readable']:
            layer_data = pd.concat(objs=list_of_layer_dat, axis=0, ignore_index=True)
        else:
            layer_data = [dat for chunk in list_of_layer_dat for dat in chunk]

        return layer_data

    @classmethod
    def read_pbf_layer(cls, layer, readable=True, expand=False, parse_geometry=False,
                       parse_properties=False, parse_other_tags=False, number_of_chunks=None):
        """
        Parse a layer of a PBF data file.

        :param layer: a layer of a PBF data file, loaded by `GDAL/OGR <https://gdal.org>`_
        :type layer: osgeo.ogr.Layer
        :param readable: whether to parse each feature in the raw data, defaults to ``False``
        :type readable: bool
        :param expand: whether to expand dict-like data into separate columns, defaults to ``False``
        :type expand: bool
        :param parse_geometry: whether to represent the ``'geometry'`` field
            in a `shapely.geometry`_ format, defaults to ``False``
        :type parse_geometry: bool
        :param parse_properties: whether to represent the ``'properties'`` field
            in a tabular format, defaults to ``False``
        :type parse_properties: bool
        :param parse_other_tags: whether to represent a ``'other_tags'`` (of ``'properties'``)
            in a `dict`_ format, defaults to ``False``
        :type parse_other_tags: bool
        :param number_of_chunks: number of chunks, defaults to ``None``
        :type number_of_chunks: int | None
        :return: parsed data of the given OSM PBF layer
        :rtype: dict

        .. _`shapely.geometry`:
            https://shapely.readthedocs.io/en/latest/manual.html#geometric-objects
        .. _`dict`:
            https://docs.python.org/3/library/stdtypes.html#dict

        .. seealso::

            - Examples for the method
              :meth:`PBFReadParse.read_pbf()<pydriosm.reader.PBFReadParse.read_pbf>`.
        """

        layer_name = layer.GetName()  # Get the name of the i-th layer

        func_args = {
            'readable': readable,
            'expand': expand,
            'parse_geometry': parse_geometry,
            'parse_properties': parse_properties,
            'parse_other_tags': parse_other_tags,
        }

        if number_of_chunks in {None, 0, 1}:
            layer_data = cls._read_pbf_layer(layer=layer, **func_args)
        else:
            layer_data = cls._read_pbf_layer_chunkwise(
                layer=layer, number_of_chunks=number_of_chunks, **func_args)

        data = {layer_name: layer_data}

        return data

    @classmethod
    def read_pbf(cls, pbf_pathname, readable=True, expand=False, parse_geometry=False,
                 parse_properties=False, parse_other_tags=False, number_of_chunks=None,
                 max_tmpfile_size=5000, **kwargs):
        """
        Parse a PBF data file (by `GDAL <https://pypi.org/project/GDAL/>`_).

        :param pbf_pathname: pathname of a PBF data file
        :type pbf_pathname: str
        :param readable: whether to parse each feature in the raw data, defaults to ``False``
        :type readable: bool
        :param expand: whether to expand dict-like data into separate columns, defaults to ``False``
        :type expand: bool
        :param parse_geometry: whether to represent the ``'geometry'`` field
            in a `shapely.geometry`_ format, defaults to ``False``
        :type parse_geometry: bool
        :param parse_properties: whether to represent the ``'properties'`` field
            in a tabular format, defaults to ``False``
        :type parse_properties: bool
        :param parse_other_tags: whether to represent a ``'other_tags'`` (of ``'properties'``)
            in a `dict`_ format, defaults to ``False``
        :type parse_other_tags: bool
        :param number_of_chunks: number of chunks, defaults to ``None``
        :type number_of_chunks: int | None
        :param max_tmpfile_size: maximum size of the temporary file, defaults to ``None``;
            when ``max_tmpfile_size=None``, it defaults to ``5000``
        :type max_tmpfile_size: int | None
        :param kwargs: [optional] parameters of the function
            `pyhelpers.settings.gdal_configurations()`_
        :return: parsed OSM PBF data
        :rtype: dict

        .. _`shapely.geometry`:
            https://shapely.readthedocs.io/en/latest/manual.html#geometric-objects
        .. _`dict`:
            https://docs.python.org/3/library/stdtypes.html#dict
        .. _`pyhelpers.settings.gdal_configurations()`:
            https://pyhelpers.readthedocs.io/en/latest/_generated/
            pyhelpers.settings.gdal_configurations.html

        .. note::

            The `GDAL/OGR <https://gdal.org>`_ drivers categorizes the features of OSM PBF data into
            five layers:

            - **0: 'points'** - "node" features having significant tags attached
            - **1: 'lines'** - "way" features being recognized as non-area
            - **2: 'multilinestrings'** - "relation" features forming a multilinestring
              (type='multilinestring' / type='route')
            - **3: 'multipolygons'** - "relation" features forming a multipolygon
              (type='multipolygon' / type='boundary'), and "way" features being recognized as area
            - **4: 'other_relations'** - "relation" features not belonging to the above 2 layers

            For more information, please refer to
            `OpenStreetMap XML and PBF <https://gdal.org/drivers/vector/osm.html>`_.

        .. warning::

            - **Parsing large PBF data files (e.g. > 50MB) can be time-consuming!**
            - The function :func:`~pydriosm.reader.read_osm_pbf` may require fairly high amount of
              physical memory to parse large files, in which case it would be recommended that
              ``number_of_chunks`` is set to be a reasonable value.

        .. _pydriosm-reader-PBFReadParse-read_osm_pbf:

        **Examples**::

            >>> from pydriosm.reader import PBFReadParse
            >>> from pydriosm.downloader import GeofabrikDownloader
            >>> from pyhelpers.dirs import delete_dir
            >>> import os

            >>> # Download the PBF data file of 'Rutland' as an example
            >>> subrgn_name = 'rutland'
            >>> file_format = ".pbf"
            >>> dwnld_dir = "tests\\osm_data"

            >>> gfd = GeofabrikDownloader()

            >>> gfd.download_osm_data(subrgn_name, file_format, dwnld_dir, verbose=True)
            To download .osm.pbf data of the following geographic (sub)region(s):
                Rutland
            ? [No]|Yes: yes
            Downloading "rutland-latest.osm.pbf"
                to "tests\\osm_data\\rutland\\" ... Done.

            >>> rutland_pbf_path = gfd.data_paths[0]
            >>> os.path.relpath(rutland_pbf_path)
            'tests\\osm_data\\rutland\\rutland-latest.osm.pbf'

            >>> # Read the downloaded PBF data
            >>> rutland_pbf = PBFReadParse.read_pbf(rutland_pbf_path)
            >>> type(rutland_pbf)
            dict
            >>> list(rutland_pbf.keys())
            ['points', 'lines', 'multilinestrings', 'multipolygons', 'other_relations']

            >>> rutland_pbf_points = rutland_pbf['points']
            >>> rutland_pbf_points.head()
            0    {'type': 'Feature', 'geometry': {'type': 'Poin...
            1    {'type': 'Feature', 'geometry': {'type': 'Poin...
            2    {'type': 'Feature', 'geometry': {'type': 'Poin...
            3    {'type': 'Feature', 'geometry': {'type': 'Poin...
            4    {'type': 'Feature', 'geometry': {'type': 'Poin...
            Name: points, dtype: object

            >>> # Set `expand` to be `True`
            >>> pbf_0 = PBFReadParse.read_pbf(rutland_pbf_path, expand=True)
            >>> type(pbf_0)
            dict
            >>> list(pbf_0.keys())
            ['points', 'lines', 'multilinestrings', 'multipolygons', 'other_relations']
            >>> pbf_0_points = pbf_0['points']
            >>> pbf_0_points.head()
                     id  ...                                         properties
            0    488432  ...  {'osm_id': '488432', 'name': None, 'barrier': ...
            1    488658  ...  {'osm_id': '488658', 'name': 'Tickencote Inter...
            2  13883868  ...  {'osm_id': '13883868', 'name': None, 'barrier'...
            3  14049101  ...  {'osm_id': '14049101', 'name': None, 'barrier'...
            4  14558402  ...  {'osm_id': '14558402', 'name': None, 'barrier'...
            [5 rows x 3 columns]

            >>> pbf_0_points['geometry'].head()
            0    {'type': 'Point', 'coordinates': [-0.5134241, ...
            1    {'type': 'Point', 'coordinates': [-0.5313354, ...
            2    {'type': 'Point', 'coordinates': [-0.7229332, ...
            3    {'type': 'Point', 'coordinates': [-0.7249816, ...
            4    {'type': 'Point', 'coordinates': [-0.7266581, ...
            Name: geometry, dtype: object

            >>> # Set both `expand` and `parse_geometry` to be `True`
            >>> pbf_1 = PBFReadParse.read_pbf(rutland_pbf_path, expand=True, parse_geometry=True)
            >>> pbf_1_points = pbf_1['points']
            >>> # Check the difference in 'geometry' column, compared to `pbf_0_points`
            >>> pbf_1_points['geometry'].head()
            0    POINT (-0.5134241 52.6555853)
            1    POINT (-0.5313354 52.6737716)
            2    POINT (-0.7229332 52.5889864)
            3    POINT (-0.7249816 52.6748426)
            4    POINT (-0.7266581 52.6695058)
            Name: geometry, dtype: object

            >>> # Set both `expand` and `parse_properties` to be `True`
            >>> pbf_2 = PBFReadParse.read_pbf(rutland_pbf_path, expand=True, parse_properties=True)
            >>> pbf_2_points = pbf_2['points']
            >>> pbf_2_points['other_tags'].head()
            0                 "odbl"=>"clean"
            1                            None
            2                            None
            3    "traffic_calming"=>"cushion"
            4        "direction"=>"clockwise"
            Name: other_tags, dtype: object

            >>> # Set both `expand` and `parse_other_tags` to be `True`
            >>> pbf_3 = PBFReadParse.read_pbf(rutland_pbf_path, expand=True, parse_properties=True,
            ...                               parse_other_tags=True)
            >>> pbf_3_points = pbf_3['points']
            >>> # Check the difference in 'other_tags', compared to ``pbf_2_points``
            >>> pbf_3_points['other_tags'].head()
            0                 {'odbl': 'clean'}
            1                              None
            2                              None
            3    {'traffic_calming': 'cushion'}
            4        {'direction': 'clockwise'}
            Name: other_tags, dtype: object

            >>> # Delete the downloaded PBF data file
            >>> delete_dir(gfd.download_dir, verbose=True)
            To delete the directory "tests\\osm_data\\" (Not empty)
            ? [No]|Yes: yes
            Deleting "tests\\osm_data\\" ... Done.

        .. seealso::

            - Examples for the methods:
              :meth:`GeofabrikReader.read_osm_pbf()<pydriosm.reader.GeofabrikReader.read_osm_pbf>`
              and :meth:`BBBikeReader.read_osm_pbf()<pydriosm.reader.BBBikeReader.read_osm_pbf>`.
        """

        osgeo_ogr, osgeo_gdal = map(_check_dependency, ['osgeo.ogr', 'osgeo.gdal'])

        # Reference: https://gis.stackexchange.com/questions/332327/
        # Stop GDAL printing both warnings and errors to STDERR
        osgeo_gdal.PushErrorHandler('CPLQuietErrorHandler')
        # Make GDAL raise python exceptions for errors (warnings won't raise an exception)
        osgeo_gdal.UseExceptions()

        kwargs.update({'max_tmpfile_size': max_tmpfile_size})
        gdal_configurations(**kwargs)

        func_args = {
            'readable': readable,
            'expand': expand,
            'parse_geometry': parse_geometry,
            'parse_properties': parse_properties,
            'parse_other_tags': parse_other_tags,
            'number_of_chunks': number_of_chunks,
        }

        f = osgeo_ogr.Open(pbf_pathname)

        # Get a collection of parsed layer data
        collection_of_layer_data = [
            cls.read_pbf_layer(f.GetLayerByIndex(i), **func_args) for i in range(f.GetLayerCount())]

        # Make the output in a dictionary form:
        # {Layer1 name: Layer1 data, Layer2 name: Layer2 data, ...}
        data = dict(collections.ChainMap(*reversed(collection_of_layer_data)))

        return data


class VarReadParse(Transformer):
    """
    Read/parse OSM data of various formats (other than PBF and Shapefile).
    """

    #: set: Valid file formats.
    FILE_FORMATS = {'.csv.xz', 'geojson.xz'}

    # == .osm.bz2 / .bz2 =========================================================================

    @classmethod
    def _read_osm_bz2(cls, bz2_pathname):
        """
        (To be developed...)

        :param bz2_pathname:
        :return:
        """
        import bz2
        # import xml.etree.ElementTree

        bz2_file = open(bz2_pathname, 'rb')

        bz2d = bz2.BZ2Decompressor()
        raw = b'' + bz2d.decompress(bz2_file.read())
        data = raw.split(b'\n')

        return data

    # == .csv.xz =================================================================================

    @classmethod
    def _prep_csv_xz(cls, x):
        y = x.rstrip('\t\n').split('\t')
        return y

    @classmethod
    def read_csv_xz(cls, csv_xz_pathname, col_names=None):
        """
        Read/parse a compressed CSV (.csv.xz) data file.

        :param csv_xz_pathname: path to a .csv.xz data file
        :type csv_xz_pathname: str
        :param col_names: column names of .csv.xz data, defaults to ``None``
        :type col_names: list | None
        :return: tabular data of the CSV file
        :rtype: pandas.DataFrame

        See examples for the method
        :meth:`BBBikeReader.read_csv_xz()<pydriosm.reader.BBBikeReader.read_csv_xz>`.
        """

        if col_names is None:
            col_names = ['type', 'id', 'feature', 'note']

        with lzma.open(csv_xz_pathname, mode='rt', encoding='utf-8') as f:
            with multiprocessing.Pool(processes=os.cpu_count() - 1) as p:
                csv_xz = pd.DataFrame.from_records(
                    p.map(cls._prep_csv_xz, f.readlines()), columns=col_names)

        return csv_xz

    # == .geojson.xz =============================================================================

    @classmethod
    def read_geojson_xz(cls, geojson_xz_pathname, engine=None, parse_geometry=False):
        """
        Read/parse a compressed Osmium GeoJSON (.geojson.xz) data file.

        :param geojson_xz_pathname: path to a .geojson.xz data file
        :type geojson_xz_pathname: str
        :param engine: an open-source Python package for JSON serialization, defaults to ``None``;
            when ``engine=None``, it refers to the built-in `json`_ module;
            otherwise options include: ``'ujson'`` (for `UltraJSON`_),
            ``'orjson'`` (for `orjson`_) and ``'rapidjson'`` (for `python-rapidjson`_)
        :type engine: str | None
        :param parse_geometry: whether to reformat coordinates into a geometric object,
            defaults to ``False``
        :type parse_geometry: bool
        :return: tabular data of the Osmium GeoJSON file
        :rtype: pandas.DataFrame

        .. _`json`: https://docs.python.org/3/library/json.html#module-json
        .. _`UltraJSON`: https://pypi.org/project/ujson/
        .. _`orjson`: https://pypi.org/project/orjson/
        .. _`python-rapidjson`: https://pypi.org/project/python-rapidjson/

        .. seealso::

            - Examples for the method
              :meth:`BBBikeReader.read_geojson_xz()<pydriosm.reader.BBBikeReader.read_geojson_xz>`.
        """

        engine_ = check_json_engine(engine=engine)

        with lzma.open(filename=geojson_xz_pathname, mode='rt', encoding='utf-8') as f:
            raw_data = engine_.loads(f.read())

        data = pd.DataFrame.from_dict(raw_data['features'])

        if 'type' in data.columns:
            if data['type'].nunique() == 1:
                del data['type']

        if parse_geometry:
            # data['geometry'] = data['geometry'].map(cls.transform_unitary_geometry)
            with multiprocessing.Pool(processes=os.cpu_count() - 1) as p:
                geom_data = p.map(cls.transform_unitary_geometry, data['geometry'])

            data.loc[:, 'geometry'] = pd.Series(geom_data)

        return data
