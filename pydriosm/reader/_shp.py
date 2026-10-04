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
import shapely.geometry
from pyhelpers._cache import _check_dependencies, _print_failure_message
from pyhelpers.dirs import cd, get_relative_path, is_dir_path, resolve_dir_path
from pyhelpers.text import find_similar_str


def get_layer_name(shp_filename):
    """
    Find the layer name of an OSM shapefile given its filename.

    :param shp_filename: Filename of a shapefile (e.g. ".shp").
    :type shp_filename: str | pathlib.Path | os.PathLike | None
    :return: Layer name extracted from the shapefile name, or ``None`` if invalid.
    :rtype: str | None

    **Examples**::

        >>> from pydriosm.reader._shp import get_layer_name

        >>> get_layer_name("") is None
        True

        >>> get_layer_name("gis_osm_railways_free_1.shp")
        'railways'

        >>> get_layer_name("gis_osm_transport_a_free_1.shp")
        'transport'

        >>> get_layer_name("gis_osm_protected_areas_a_free_1.shp")
        'protected_areas'
    """

    if not shp_filename:
        return None

    shp_filename_str = str(shp_filename)

    if (
            not shp_filename_str.startswith("gis_osm_") and
            "a_free" not in shp_filename_str and
            "README" not in shp_filename_str
    ):
        return os.path.splitext(shp_filename_str)[0]

    # The pattern captures everything between "gis_osm_" and the suffix,
    # then specifically strips the "_a" if it is present.
    pattern = re.compile(r"^gis_osm_(.*?)(?=_?a?_free)(_1)?", re.IGNORECASE)
    match = re.search(pattern, shp_filename_str)

    if match:
        return match.group(1)

    return None


def _prepare_unzip_args(shp_zip_pathname, extract_to=None, layer_names=None, verbose=False):
    """
    Prepare the directory path and standardize layer names for shapefile extraction.

    This function determines the destination directory and standardizes the format of the provided
    layer names. It also outputs extraction information if verbose mode is enabled.

    :param shp_zip_pathname: Path to the zipped shapefile data.
    :type shp_zip_pathname: str | pathlib.Path | os.PathLike
    :param extract_to: Path to a directory where extracted files will be saved.
        If ``None``, defaults to the directory of the zipped file.
    :type extract_to: str | pathlib.Path | os.PathLike | None
    :param layer_names: Name of a shapefile layer (e.g. "railways") or multiple layers.
        If ``None``, all available layers are considered.
    :type layer_names: str | list | tuple | None
    :param verbose: Whether to print relevant information to the console. Defaults to ``False``.
    :type verbose: bool | int
    :return: A tuple containing the extraction directory and the standardized list of layer names.
    :rtype: tuple
    """

    extract_dir = extract_to or os.path.splitext(shp_zip_pathname)[0].replace(".", "-")

    rel_shp_zip_path = get_relative_path(shp_zip_pathname, as_str=True, quoted=True)
    rel_extrdir_path = get_relative_path(extract_dir, as_str=True, quoted=True)

    if not layer_names:
        layer_names_ = None
        if verbose:
            print(f"Extracting {rel_shp_zip_path}\n  to {rel_extrdir_path}", end=" ... ")
    else:
        layer_names_ = [layer_names] if isinstance(layer_names, str) else list(layer_names)
        if verbose:
            layer_name_list = "  " + "\n  ".join([f"'{x}'" for x in layer_names_])
            print(f"Extracting the following layer(s):\n{layer_name_list}")
            print(f"  from: {rel_shp_zip_path} ... \n    to: {rel_extrdir_path}", end=" ... ")

    return extract_dir, layer_names_


def _group_extracted_files(extract_dir, extract_files, verbose):
    """
    Group extracted shapefile components into respective layer-specific subdirectories.

    This function iterates through the extracted files and moves them into individual
    directories named after their corresponding layers.

    :param extract_dir: Path to the directory containing the extracted files.
    :type extract_dir: str | pathlib.Path | os.PathLike
    :param extract_files: A list of extracted file names. If ``None``, the directory contents
        are read automatically.
    :type extract_files: list | None
    :param verbose: Verbosity level for printing grouping progress. Defaults to ``False``.
    :type verbose: bool | int
    :return: A list of paths to the newly created layer subdirectories.
    :rtype: list
    """

    file_list = extract_files or os.listdir(extract_dir)

    layer_files = {}
    for f in file_list:
        if f == "README":
            continue

        fn_base = os.path.splitext(f)[0]
        lyr = os.path.basename(fn_base) if is_dir_path(f) else get_layer_name(fn_base)
        layer_files.setdefault(lyr, []).append(f)

    extract_dirs = set()
    for lyr, files in layer_files.items():
        extract_dir_ = cd(extract_dir, lyr, mkdir=True)
        if verbose == 2:
            lyr_display = lyr + "_a" if any('_a_' in fn for fn in files) else lyr
            print(f"  {lyr_display}", end=" ... ")

        for f in files:
            orig = cd(extract_dir, f)
            dest = cd(extract_dir_, os.path.basename(f))
            shutil.move(orig, dest)

        if verbose == 2:
            print("Done.")

        extract_dirs.add(extract_dir_)

    return list(extract_dirs)


def _specify_pyshp_fields(data, field_names, decimal_precision):
    """
    Generate field data specifications for writing shapefiles via
    `PyShp <https://github.com/GeospatialPython/pyshp>`_.

    :param data: Data table destined for a shapefile.
    :type data: pandas.DataFrame
    :param field_names: Names of fields to be written as shapefile records.
    :type field_names: list | pandas.Index
    :param decimal_precision: Decimal precision for writing float records.
    :type decimal_precision: int
    :return: List of record field definitions for the .shp data.
    :rtype: list

    .. seealso::

        - Examples for
          :meth:`SHP.write_to_shapefile()<pydriosm.reader._shp.SHP.write_to_shapefile>`.
    """

    dtype_shp_type = {
        'object': 'C',  # Character
        'str': 'C',
        'string': 'C',
        'int64': 'N',  # Numeric
        'int32': 'N',
        'float64': 'F',  # Float
        'float32': 'F',
        'bool': 'L',  # Logical
        'datetime64': 'D',  # Date
        'datetime64[ns]': 'D',  # Explicit pandas datetime
    }

    fields = []

    for field_name, dtype in data[field_names].dtypes.items():
        # Utilize the vectorized string accessor for performance on modern Pandas
        max_size = data[field_name].fillna('None').astype(str).str.len().max()

        shp_type = dtype_shp_type.get(dtype.name, 'C')
        decimal = decimal_precision if 'float' in dtype.name else 0

        fields.append((field_name, shp_type, int(max_size), decimal))

    return fields


def _make_feat_shp_pathnames(shp_pathname, feature_names_):
    """
    Specify pathnames for saving data of one or multiple given features.

    This function constructs target file paths by appending the feature name(s) to the
    filename of their parent layer's shapefile.

    :param shp_pathname: Pathname of a shapefile of a layer.
    :type shp_pathname: str | pathlib.Path | os.PathLike
    :param feature_names_: Name or names of one or multiple features in a shapefile layer.
    :type feature_names_: list | tuple
    :return: Pathnames corresponding to the provided ``feature_names_``.
    :rtype: list

    **Examples**::

        >>> from pydriosm.reader._shp import _make_feat_shp_pathnames
        >>> import os

        >>> fn = "gis_osm_railways_free_1.shp"
        >>> feats = ['rail']
        >>> pn = _make_feat_shp_pathnames(shp_pathname=fn, feature_names_=feats)
        >>> len(pn)
        1
        >>> os.path.relpath(pn[0])
        'gis_osm_railways_free_1_rail.shp'

        >>> fn = "tests\\osm_data\\greater-london\\gis_osm_transport_free_1.shp"
        >>> feats = ['railway_station', 'bus_stop', 'bus_station']
        >>> pn = _make_feat_shp_pathnames(shp_pathname=fn, feature_names_=feats)
        >>> len(pn)
        3
        >>> pn
        ['tests\\osm_data\\greater-london\\gis_osm_transport_a_free_1_railway_station.shp',
         'tests\\osm_data\\greater-london\\gis_osm_transport_a_free_1_bus_stop.shp',
         'tests\\osm_data\\greater-london\\gis_osm_transport_a_free_1_bus_station.shp']
    """

    shp_dir_path, shp_filename_ = os.path.split(str(shp_pathname))
    shp_filename, ext = os.path.splitext(shp_filename_)

    if len(feature_names_) > 0:
        feat_shp_pathnames = [
            os.path.join(shp_dir_path, f"{shp_filename}_{f}{ext}") for f in feature_names_
        ]
    else:
        feat_shp_pathnames = []

    return feat_shp_pathnames


def _copy_temp_files(subregion_names, layer_name, path_to_extract_dirs, path_to_merged_dir_temp):
    """
    Copy extracted shapefile components into a temporary directory.

    This function iterates over a list of extraction directories, finds files matching the
    specified layer name and copies them to a designated temporary folder. The destination
    filenames are prefixed with the formatted subregion name.

    :param subregion_names: List of geographic subregion names.
    :type subregion_names: list | tuple
    :param layer_name: Name of the shapefile layer (e.g. "railways").
    :type layer_name: str
    :param path_to_extract_dirs: List of paths to the directories containing extracted files.
    :type path_to_extract_dirs: list | tuple
    :param path_to_merged_dir_temp: Path to the temporary directory for storing merged files.
    :type path_to_merged_dir_temp: str | pathlib.Path | os.PathLike
    :return: List of destination paths for the copied temporary files.
    :rtype: list
    """

    paths_to_temp_files = []
    path_to_merged_dir_temp_str = str(path_to_merged_dir_temp)

    for subregion_name, path_to_extract_dir in zip(subregion_names, path_to_extract_dirs):
        orig_file_list = glob.glob(
            os.path.join(str(path_to_extract_dir), "**", f"*{layer_name}*"), recursive=True
        )

        for orig_file in orig_file_list:
            fn = os.path.basename(orig_file)
            prefix = subregion_name.lower().replace(" ", "-")
            dest = os.path.join(path_to_merged_dir_temp_str, f"{prefix}_{fn}")

            shutil.copyfile(orig_file, dest)
            paths_to_temp_files.append(dest)

    return paths_to_temp_files


class SHP:
    """
    Read/parse `Shapefile <https://wiki.openstreetmap.org/wiki/Shapefiles>`_ data.

    **Examples**::

        >>> from pydriosm.reader._shp import SHP

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
        'adminareas',
        'buildings',
        'landuse',
        'natural',
        'places',
        'points',
        'pofw',
        'pois',
        'protected_areas',
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

            >>> from pydriosm.reader._shp import SHP

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

            >>> from pydriosm.reader._shp import SHP

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
                      return_extract_dir=False, verbose=False, raise_error=False):
        # noinspection shadowing-names,unresolved-references
        """
        Unzip a zipped shapefile and optionally separate layers into individual directories.

        This method extracts files from a zipped shapefile archive. It allows targeted extraction
        by layer names and can automatically group the resulting files into separate directories
        based on their layer names.

        :param shp_zip_pathname: Path to the zipped shapefile data (e.g. ".shp.zip").
        :type shp_zip_pathname: str | pathlib.Path | os.PathLike
        :param extract_to: Path to a directory where extracted files will be saved.
            When ``None``, defaults to the same directory where the zip file is located.
        :type extract_to: str | pathlib.Path | os.PathLike | None
        :param layer_names: Name of a shapefile layer (e.g. "railways") or names of multiple layers.
            When ``None``, all available layers are extracted.
        :type layer_names: str | list | tuple | None
        :param separate: Whether to put the data files of different layers into respective folders.
            Defaults to ``False``.
        :type separate: bool
        :param return_extract_dir: Whether to return the pathname(s) of the extraction directory.
            Defaults to ``False``.
        :type return_extract_dir: bool
        :param verbose: Whether to print relevant information to the console. Defaults to ``False``.
        :type verbose: bool | int
        :param raise_error: Whether to raise the provided exception upon failure.
            If ``False``, the error will be suppressed.
        :type raise_error: bool
        :return: The path(s) to the directory of extracted files when ``return_extract_dir=True``.
            Returns ``None`` if extraction is aborted.
        :rtype: str | pathlib.Path | os.PathLike | list | None

        **Examples**::

            >>> from pydriosm.reader._shp import SHP
            >>> from pydriosm.downloader import BBBikeDownloader
            >>> from pyhelpers.dirs import cd, delete_dir, get_relative_path
            >>> import os

            >>> # Download the shapefile data of London as an example
            >>> subregion_name = 'birmingham'
            >>> file_format = ".shp"
            >>> download_dir = "tests/osm_data"

            >>> bbd = BBBikeDownloader()

            >>> bbd.download_data(subregion_name, file_format, download_dir, verbose=True)
            Proceed with downloading data in the format ".shp.zip" for the following geographic...
                "Birmingham"
              to "tests/osm_data/birmingham/"
            ? [No]|Yes: >? yes
            Downloading "Birmingham.osm.shp.zip" 100%|██████████| 79.9M/79.9M | 14.1MB/s ...
              Saving "Birmingham.osm.shp.zip" to "tests/osm_data/birmingham/" ... Done.

            >>> shp_zip_file_path = bbd.data_paths[0]
            >>> get_relative_path(shp_zip_file_path, as_str=True)
            'tests/osm_data/birmingham/Birmingham.osm.shp.zip'

            >>> # To extract data of a specific layer 'railways'
            >>> bham_railways_dir = SHP.unzip_shp_zip(
            ...     shp_zip_file_path,
            ...     layer_names='railways',
            ...     verbose=True,
            ...     return_extract_dir=True
            ... )
            Extracting the following layer(s):
              'railways'
              from: "tests/osm_data/birmingham/Birmingham.osm.shp.zip" ...
                to: "tests/osm_data/birmingham/Birmingham-osm-shp/" ... Done.

            >>> get_relative_path(bham_railways_dir, as_str=True)  # Check the directory
            'tests/osm_data/birmingham/Birmingham-osm-shp'

            >>> # When multiple layer names are specified, the extracted files for each of the
            >>> # layers can be put into a separate subdirectory by setting `separate=True`:
            >>> layer_names = ['railways', 'landuse']
            >>> dirs_of_layers = SHP.unzip_shp_zip(
            ...     shp_zip_pathname=shp_zip_file_path,
            ...     layer_names=layer_names,
            ...     separate=True,
            ...     verbose=2,
            ...     return_extract_dir=True
            ... )
            Extracting the following layer(s):
              'railways'
              'landuse'
              from: "tests/osm_data/birmingham/Birmingham.osm.shp.zip" ...
                to: "tests/osm_data/birmingham/Birmingham-osm-shp/" ... Done.
            Grouping files by layers ...
              Birmingham-shp/shape/landuse ... Done.
              Birmingham-shp/shape/railways ... Done.
            Done.

            >>> len(dirs_of_layers) == 2
            True
            >>> get_relative_path(os.path.commonpath(dirs_of_layers), as_str=True)
            'tests/osm_data/birmingham/Birmingham-osm-shp/Birmingham-shp/shape'
            >>> set(map(os.path.basename, dirs_of_layers))
            {'landuse', 'railways'}

            >>> # Remove the subdirectories
            >>> delete_dir(dirs_of_layers, confirmation_required=False)

            >>> # To extract all (without specifying `layer_names`
            >>> bham_shp_dir = SHP.unzip_shp_zip(
            ...     shp_zip_file_path,
            ...     verbose=True,
            ...     return_extract_dir=True
            ... )
            Extracting "tests/osm_data/birmingham/Birmingham.osm.shp.zip"
              to "tests/osm_data/birmingham/Birmingham-osm-shp/" ... Done.

            >>> # Check the directory
            >>> get_relative_path(bham_shp_dir, as_str=True)
            'tests/osm_data/birmingham/Birmingham-osm-shp'
            >>> list_of_files = list(cd(bham_shp_dir, "Birmingham-shp/shape").iterdir())
            >>> len(list_of_files)
            40
            >>> # Get the names of all available layers
            >>> set(filter(None, map(SHP.get_layer_name, list_of_files)))
            {'buildings',
             'landuse',
             'natural',
             'places',
             'points',
             'railways',
             'roads',
             'waterways'}

            >>> # Delete the download/data directory
            >>> delete_dir(bbd.download_dir, verbose=True)
            Confirm deletion of the directory "tests/osm_data/" (Not empty)?
             [No]|Yes: yes
            Deleting "tests/osm_data/" ... Done.
        """

        extract_dir, layer_names_ = _prepare_unzip_args(
            shp_zip_pathname=shp_zip_pathname,
            extract_to=extract_to,
            layer_names=layer_names,
            verbose=verbose,
        )

        try:
            with zipfile.ZipFile(file=shp_zip_pathname, mode='r') as sz:
                if layer_names_:
                    extract_files = [
                        f.filename for f in sz.filelist
                        if any(x in f.filename for x in layer_names_)
                    ]
                else:
                    extract_files = None

                # Abort extraction early if specific layers were requested but none were found
                if isinstance(extract_files, list) and not extract_files:
                    if verbose:
                        print("\n  The specified layer does not exist. No data has been extracted.")
                    return extract_dir if return_extract_dir else None

                sz.extractall(extract_dir, members=extract_files)

            if verbose:
                print("Done.")

            if not separate and return_extract_dir:
                return extract_dir

            if separate:
                if verbose:
                    print("Grouping files by layers ... ", end="\n" if verbose == 2 else "")

                extract_dir_list = _group_extracted_files(
                    extract_dir=extract_dir,
                    extract_files=extract_files,
                    verbose=verbose
                )

                if verbose:
                    print("Done.")

                if return_extract_dir:
                    return extract_dir_list

        except Exception as e:
            _print_failure_message(e, "Failed. Error:", verbose=verbose, raise_error=raise_error)

    @classmethod
    def _covert_to_geometry(cls, x):
        """
        Convert the ``(shape_type, coordinates)`` of a feature to a ``shapely.geometry`` object.

        :param x: a feature (i.e. one row data) in a shapefile parsed by pyShp.
        :return: the corresponding ``shapely.geometry`` object
        """

        coordinates, geom_func = x['coordinates'], cls.SHAPE_TYPE_GEOM[x['shape_type']]

        if geom_func.__name__ == 'Point' and len(coordinates) == 1:
            coordinates = coordinates[0]

        y = geom_func(coordinates)

        return y

    @classmethod
    def read_shp(cls, shp_pathname, engine='geopandas', emulate_gpd=False, **kwargs):
        """
        Read a shapefile.

        :param shp_pathname: pathname of a shape format file (.shp)
        :type shp_pathname: str
        :param engine: method used to read shapefiles;
            options include: ``'pyshp'`` and ``'geopandas'`` (default) (or ``'gpd'``)
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

            >>> from pydriosm.reader._shp import SHP
            >>> from pydriosm.downloader import BBBikeDownloader
            >>> from pyhelpers.dirs import cd, delete_dir
            >>> import os
            >>> import glob

            >>> # Download the shapefile data of London as an example
            >>> subregion_name = 'birmingham'
            >>> osm_file_format = ".shp"
            >>> download_dir = "tests/osm_data"

            >>> bbd = BBBikeDownloader()

            >>> bbd.download_data(subregion_name, osm_file_format, download_dir, verbose=True)
            Proceed to download data in the format '.shp.zip' for the following geographic (sub...
                "Birmingham"
              to "./tests/osm_data/birmingham/"
            ? [No]|Yes: yes
            Downloading "Birmingham.osm.shp.zip" 100%|██████████| 79.1M/79.1M | 17.4MB/s ...
              Saving "Birmingham.osm.shp.zip" to "./tests/osm_data/birmingham/" ... Done.

            >>> bham_shp_zip = bbd.data_paths[0]
            >>> os.path.relpath(bham_shp_zip)
            'tests\\osm_data\\birmingham\\Birmingham.osm.shp.zip'

            >>> # Extract all
            >>> bham_shp_dir = SHP.unzip_shp_zip(bham_shp_zip, return_extract_dir=True)

            >>> # Get the pathname of the .shp data of 'railways'
            >>> path_to_railways_shp = glob.glob(
            ...     cd(bham_shp_dir, "Birmingham-shp", "shape", "*railways*.shp"))[0]
            >>> os.path.relpath(path_to_railways_shp)  # Check the pathname of the .shp file
            'tests\\osm_data\\birmingham\\Birmingham-osm-shp\\Birmingham-shp\\shape\\railways.shp'

            >>> # Read the data of 'railways'
            >>> bham_railways = SHP.read_shp(path_to_railways_shp)
            >>> bham_railways.head()
                osm_id  ...                                           geometry
            0      740  ...  LINESTRING (-1.81789 52.5701, -1.81793 52.5698...
            1     2148  ...  LINESTRING (-1.87303 52.50542, -1.8727 52.5051...
            2  2950000  ...  LINESTRING (-1.87933 52.48138, -1.87962 52.481...
            3  3491845  ...  LINESTRING (-1.7406 52.51858, -1.73942 52.5186...
            4  3981454  ...  LINESTRING (-1.77412 52.52249, -1.77376 52.522...
            [5 rows x 4 columns]

            >>> # Set `emulate_gpd=True` to return data of similar format to what GeoPandas does
            >>> bham_railways_ = SHP.read_shp(
            ...     path_to_railways_shp, engine='pyshp', emulate_gpd=True)
            >>> bham_railways_.head()
                osm_id  ...                                           geometry
            0      740  ...  LINESTRING (-1.8178905 52.5700974, -1.8179287 ...
            1     2148  ...  LINESTRING (-1.873028 52.5054182, -1.8726964 5...
            2  2950000  ...  LINESTRING (-1.8793303 52.4813778, -1.8796237 ...
            3  3491845  ...  LINESTRING (-1.7406017 52.5185831, -1.7394216 ...
            4  3981454  ...  LINESTRING (-1.7741212 52.5224935, -1.7737563 ...
            [5 rows x 4 columns]

            >>> # Check the data types of `london_railways` and `london_railways_`
            >>> railways_data = [bham_railways, bham_railways_]
            >>> list(map(type, railways_data))
            [geopandas.geodataframe.GeoDataFrame, pandas.DataFrame]
            >>> # Check the geometry data of `london_railways` and `london_railways_`
            >>> geom1, geom2 = map(lambda x: x['geometry'].map(lambda y: y.wkb), railways_data)
            >>> geom1.equals(geom2)
            True

            >>> # Delete the download/data directory
            >>> delete_dir(bbd.download_dir, verbose=True)
            To delete the directory "./tests/osm_data/" (Not empty)
            ? [No]|Yes: yes
            Deleting "./tests/osm_data/" ... Done.
        """

        if engine in {'geopandas', 'gpd'}:
            gpd = _check_dependencies('geopandas')
            shp_data = gpd.read_file(shp_pathname, **kwargs)

        else:  # method == 'pyshp':  # default
            pyshp = _check_dependencies('shapefile')

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

        object_cols = shp_data.select_dtypes(include=['object', 'string']).columns
        shp_data[object_cols] = shp_data[object_cols].replace(
            {np.nan: None, 'None': None, '': None})

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
    def write_to_shapefile(cls, data, write_to, shp_filename=None, decimal_precision=5,
                           return_shp_path=False, verbose=False, raise_error=False):
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
        :param return_shp_path: whether to return the pathname of the output .shp file,
            defaults to ``False``
        :type return_shp_path: bool
        :param verbose: whether to print relevant information in console, defaults to ``False``
        :type verbose: bool | int
        :param raise_error: Whether to raise the provided exception;
            if ``raise_error=False`` (default), the error will be suppressed.
        :type raise_error: bool

        **Examples**::

            >>> from pydriosm.reader._shp import SHP
            >>> from pydriosm.downloader import BBBikeDownloader
            >>> from pyhelpers.dirs import cd, delete_dir
            >>> import os
            >>> import glob

            >>> # Download the shapefile data of London as an example
            >>> subrgn_name = 'Birmingham'
            >>> file_format = ".shp"
            >>> dwnld_dir = "tests/osm_data"

            >>> bbd = BBBikeDownloader()

            >>> bbd.download_data(subrgn_name, file_format, dwnld_dir, verbose=True)
            Proceed to download data in the format '.shp.zip' for the following geographic (sub...
                "Birmingham"
              to "./tests/osm_data/birmingham/"
            ? [No]|Yes: yes
            Downloading "Birmingham.osm.shp.zip" 100%|██████████| 79.1M/79.1M | 18.1MB/s ...
              Saving "Birmingham.osm.shp.zip" to "./tests/osm_data/birmingham/" ... Done.

            >>> bham_shp_zip = bbd.data_paths[0]
            >>> os.path.relpath(bham_shp_zip)
            'tests\\osm_data\\birmingham\\Birmingham.osm.shp.zip'

            >>> # Extract the 'railways' layer of the downloaded .shp.zip file
            >>> lyr_name = 'railways'

            >>> railways_shp_dir = SHP.unzip_shp_zip(
            ...     bham_shp_zip, layer_names=lyr_name, verbose=True, return_extract_dir=True)
            Extracting the following layer(s):
              'railways'
              from: "./tests/osm_data/birmingham/Birmingham.osm.shp.zip" ...
                to: "./tests/osm_data/birmingham/Birmingham-osm-shp/" ... Done.
            >>> # Check out the output directory
            >>> os.path.relpath(railways_shp_dir)
            'tests\\osm_data\\birmingham\\Birmingham-osm-shp'

            >>> # Get the pathname of the .shp data of 'railways'
            >>> path_to_railways_shp = glob.glob(
            ...     cd(railways_shp_dir, "Birmingham-shp", "shape", f"*{lyr_name}*.shp"))[0]
            >>> os.path.relpath(path_to_railways_shp)  # Check the pathname of the .shp file
            'tests\\osm_data\\birmingham\\Birmingham-osm-shp\\Birmingham-shp\\shape\\railways.shp'

            >>> # Read the .shp file
            >>> bham_railways_shp = SHP.read_shp(path_to_railways_shp)

            >>> # Create a new directory for saving the 'railways' data
            >>> railways_subdir = cd(os.path.dirname(railways_shp_dir), lyr_name)
            >>> os.path.relpath(railways_subdir)
            'tests\\osm_data\\birmingham\\railways'

            >>> # Save the data of 'railways' to the new directory
            >>> path_to_railways_shp_ = SHP.write_to_shapefile(
            ...     bham_railways_shp, railways_subdir, return_shp_path=True, verbose=True)
            Writing data to "tests/osm_data/birmingham/railways.*" ... Done.
            >>> os.path.basename(path_to_railways_shp_)
            'railways.shp'

            >>> # If `shp_filename` is specified
            >>> path_to_railways_shp_ = SHP.write_to_shapefile(
            ...     bham_railways_shp, railways_subdir, shp_filename="rail_data",
            ...     return_shp_path=True, verbose=True)
            Writing data to "tests/osm_data/birmingham/rail_data.*" ... Done.
            >>> os.path.basename(path_to_railways_shp_)
            'rail_data.shp'

            >>> # Retrieve the saved the .shp file
            >>> bham_railways_shp_ = SHP.read_shp(path_to_railways_shp_)
            >>> # Check if the retrieved .shp data is equal to the original one
            >>> bham_railways_shp_.equals(bham_railways_shp)
            True

            >>> # Delete the download/data directory
            >>> delete_dir(bbd.download_dir, verbose=True)
            To delete the directory "./tests/osm_data/" (Not empty)
            ? [No]|Yes: yes
            Deleting "./tests/osm_data/" ... Done.
        """

        pyshp = _check_dependencies('shapefile')

        filename_ = os.path.basename(write_to) if shp_filename is None else copy.copy(shp_filename)
        filename = os.path.splitext(filename_)[0]
        write_to_ = os.path.join(os.path.dirname(write_to), filename)

        if verbose:
            rel_write_to_ = get_relative_path(write_to_, as_str=True)
            print(f'Writing data to "{rel_write_to_}.*"', end=" ... ")

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
                field_info_list = _specify_pyshp_fields(
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

            if return_shp_path:
                return f"{write_to_}.shp"

        except Exception as e:
            _print_failure_message(
                e, prefix="Failed. Error:", verbose=verbose, raise_error=raise_error)

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
                gpd.GeoDataFrame(dat).to_crs(cls.EPSG4326_WGS84_PROJ4).to_file(
                    feat_shp_pathname, driver=cls.VECTOR_DRIVER)

            feat_shp_pathnames.append(feat_shp_pathname)

        return feat_shp_pathnames

    @classmethod
    def read_layer_shps(cls, shp_pathnames, feature_names=None, save_feat_shp=False,
                        ret_feat_shp_path=False, **kwargs):
        # noinspection PyUnresolvedReferences
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
            :meth:`SHP.read_shp()<pydriosm.reader._shp.SHP.read_shp>`
        :return: parsed shapefile data; and optionally,
            pathnames of the shapefiles of the specified features (when ``ret_feat_shp_path=True``)
        :rtype: pandas.DataFrame | geopandas.GeoDataFrame | tuple

        .. _`geopandas.GeoDataFrame.to_file()`:
            https://geopandas.org/reference.html#geopandas.GeoDataFrame.to_file

        **Examples**::

            >>> from pydriosm.reader._shp import SHP
            >>> from pydriosm.downloader import BBBikeDownloader
            >>> from pyhelpers.dirs import cd, delete_dir
            >>> import os

            >>> # Download the shapefile data of London as an example
            >>> subrgn_name = 'Birmingham'
            >>> file_format = ".shp"
            >>> dwnld_dir = "tests/osm_data"

            >>> bbd = BBBikeDownloader()

            >>> bbd.download_data(subrgn_name, file_format, dwnld_dir, verbose=True)
            Proceed to download data in the format '.shp.zip' for the following geographic (sub...
                "Birmingham"
              to "./tests/osm_data/birmingham/"
            ? [No]|Yes: >? yes
            Downloading "Birmingham.osm.shp.zip" 100%|██████████| 79.1M/79.1M | 17.7MB/s ...
              Saving "Birmingham.osm.shp.zip" to "./tests/osm_data/birmingham/" ... Done.

            >>> bham_shp_zip = bbd.data_paths[0]
            >>> os.path.relpath(bham_shp_zip)
            'tests\\osm_data\\birmingham\\Birmingham.osm.shp.zip'

            >>> # Extract the downloaded .shp.zip file
            >>> bham_shp_dir = SHP.unzip_shp_zip(
            ...     bham_shp_zip, layer_names='railways', return_extract_dir=True)
            >>> os.listdir(cd(bham_shp_dir, "Birmingham-shp/shape"))
            ['railways.cpg',
             'railways.dbf',
             'railways.prj',
             'railways.shp',
             'railways.shx']
            >>> bham_railways_shp_path = cd(bham_shp_dir, "Birmingham-shp/shape", "railways.shp")

            >>> # Read the 'railways' layer
            >>> bham_railways_shp = SHP.read_layer_shps(bham_railways_shp_path)
            >>> bham_railways_shp.head()
                osm_id  ...                                           geometry
            0      740  ...  LINESTRING (-1.81789 52.5701, -1.81793 52.5698...
            1     2148  ...  LINESTRING (-1.87303 52.50542, -1.8727 52.5051...
            2  2950000  ...  LINESTRING (-1.87933 52.48138, -1.87962 52.481...
            3  3491845  ...  LINESTRING (-1.7406 52.51858, -1.73942 52.5186...
            4  3981454  ...  LINESTRING (-1.77412 52.52249, -1.77376 52.522...
            [5 rows x 4 columns]

            >>> # Extract only the features labeled 'rail' and save the extracted data to file
            >>> railways_rail_shp, railways_rail_shp_path = SHP.read_layer_shps(
            ...     bham_railways_shp_path, feature_names='rail', save_feat_shp=True,
            ...     ret_feat_shp_path=True)
            >>> railways_rail_shp['type'].unique()
            <StringArray>
            ['rail']
            Length: 1, dtype: str

            >>> type(railways_rail_shp_path)
            list
            >>> len(railways_rail_shp_path)
            1
            >>> os.path.basename(railways_rail_shp_path[0])
            'railways_rail.shp'

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
                feat_names = [feature_names] if isinstance(feature_names, str) else feature_names
                feat_col_name = [x for x in data.columns if x in {'type', 'fclass'}][0]
                feat_names_ = [
                    find_similar_str(x, set(data[feat_col_name].unique())) for x in feat_names]

                data = data.query(f'{feat_col_name} in @feat_names_')

                if data.empty:
                    data = None

                elif save_feat_shp:
                    feat_shp_pathnames = []

                    for lyr_shp_pathname in lyr_shp_pathnames:
                        dat = dat_dict[lyr_shp_pathname]
                        valid_feature_names = dat[feat_col_name].unique()
                        feature_names_ = [x for x in feat_names_ if x in valid_feature_names]

                        feat_shp_pathnames_ = _make_feat_shp_pathnames(
                            shp_pathname=lyr_shp_pathname, feature_names_=feature_names_)

                        feat_shp_pathnames_temp = cls._write_feat_shp(
                            data=dat.query(f'{feat_col_name} in @feature_names_'),
                            feat_col_name=feat_col_name, feat_shp_pathnames_=feat_shp_pathnames_)

                        feat_shp_pathnames += feat_shp_pathnames_temp

        if ret_feat_shp_path:
            data = data, feat_shp_pathnames

        return data

    @classmethod
    def merge_shps(cls, shp_pathnames, merged_dir, engine='geopandas', **kwargs):
        """
        Merge multiple shapefiles.

        :param shp_pathnames: list of paths to shapefiles (in .shp format)
        :type shp_pathnames: list
        :param merged_dir: path to a directory where the merged files are to be saved
        :type merged_dir: str
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

            - Examples for :meth:`~pydriosm.reader._shp.SHP.merge_layers`.
            - Resource: https://github.com/GeospatialPython/pyshp
        """

        file_stem = os.path.basename(merged_dir).lower()
        shp_filename = f"{file_stem}.shp"

        out_file_path = os.path.join(merged_dir, shp_filename)

        if engine in {'geopandas', 'gpd'}:
            gpd = _check_dependencies('geopandas')

            shp_data = collections.defaultdict(list)
            for shp_pathname in shp_pathnames:
                dat = gpd.read_file(shp_pathname)
                geo_typ = dat.geom_type.unique()[0]
                shp_data[geo_typ].append(dat)

            for geo_typ, shp_dat_list in shp_data.items():

                shp_dat = gpd.GeoDataFrame(pd.concat(shp_dat_list, ignore_index=True))
                shp_dat.to_crs(cls.EPSG4326_WGS84_PROJ4).to_file(
                    filename=out_file_path, driver=cls.VECTOR_DRIVER)

        else:  # method == 'pyshp': (default)
            kwargs.setdefault('ret_feat_shp_path', False)
            shp_data = cls.read_layer_shps(shp_pathnames, **kwargs)

            if isinstance(shp_data, pd.DataFrame):
                if 'geometry' in shp_data.columns:
                    k = shp_data['geometry'].map(lambda x: x.geom_type)
                else:
                    k = 'shape_type'

                for geo_typ, dat in shp_data.groupby(k):
                    # if isinstance(k, str):
                    #     geo_typ = cls.SHAPE_TYPE_GEOM_NAME[geo_typ]
                    cls.write_to_shapefile(data=dat, write_to=out_file_path)

                    # Write .cpg
                    with open(out_file_path.replace(".shp", ".cpg"), mode="w") as cpg:
                        cpg.write(cls.ENCODING)
                    # Write .prj
                    with open(out_file_path.replace(".shp", ".prj"), mode="w") as prj:
                        prj.write(cls.EPSG4326_WGS84_ESRI_WKT)

    @classmethod
    def _extract_files(cls, shp_zip_file_paths, layer_name, verbose=False):
        """
        Extract specific layer files from multiple zipped shapefile archives.

        :param shp_zip_file_paths: Collection of paths to zipped shapefile archives.
        :type shp_zip_file_paths: list | tuple | set
        :param layer_name: Name of the shapefile layer to extract (e.g. "railways").
        :type layer_name: str | list
        :param verbose: Verbosity level for printing output. Prints extraction details
            when set to ``2``. Defaults to ``False``.
        :type verbose: bool | int
        :return: A list of paths to the directories containing the extracted files.
        :rtype: list
        """

        path_to_extract_dirs = []

        for zfp in shp_zip_file_paths:
            extract_dir = cls.unzip_shp_zip(
                shp_zip_pathname=str(zfp),
                layer_names=layer_name,
                verbose=True if verbose == 2 else False,
                return_extract_dir=True,
            )
            path_to_extract_dirs.append(extract_dir)

        return path_to_extract_dirs

    @classmethod
    def _make_merged_dir(cls, output_dir, data_dir, temp_merged_dir, suffix):
        """
        Create a directory for storing merged shapefile data.

        :param output_dir: Explicit path for the output directory. If ``None``, a path
            is constructed automatically based on the data directory.
        :type output_dir: str | pathlib.Path | os.PathLike | None
        :param data_dir: Base directory containing the initial data files.
        :type data_dir: str | pathlib.Path | os.PathLike
        :param temp_merged_dir: Temporary directory name to be appended and cleaned.
        :type temp_merged_dir: str
        :param suffix: Suffix to strip from the ``merged_dirname_temp``.
        :type suffix: str
        :return: Path to the newly created merged data directory.
        :rtype: str
        """

        if output_dir:
            # Assumes pyhelpers.dirs.resolve_dir_path is imported and handles PathLike objects
            merged_dir_path = resolve_dir_path(path_to_dir=str(output_dir))
        else:
            merged_dir_path = os.path.join(
                str(data_dir), str(temp_merged_dir).replace(suffix, "", -1)
            )

        os.makedirs(merged_dir_path, exist_ok=True)

        return merged_dir_path

    @classmethod
    def _transfer_files(cls, engine, merged_dir, temp_merged_dir, prefix, suffix):
        """
        Move temporary output files to the final merged directory.

        This method transfers shapefiles (and their associated components) from a temporary
        location to the finalized destination and cleans up the temporary directories.

        :param engine: The engine used to process the files (e.g. 'geopandas', 'gpd' or 'pyshp').
        :type engine: str
        :param merged_dir: Destination directory path for the merged output files.
        :type merged_dir: str | pathlib.Path | os.PathLike
        :param temp_merged_dir: Pathname of the temporary file or directory.
        :type temp_merged_dir: str | pathlib.Path | os.PathLike
        :param prefix: The prefix of the temporary files to match.
        :type prefix: str
        :param suffix: The suffix to strip when establishing the final output file name.
        :type suffix: str
        """

        merged_dir_path = str(merged_dir)
        temp_merged_dir_path = str(temp_merged_dir)

        if engine in {'geopandas', 'gpd'}:
            if not os.listdir(merged_dir_path):
                temp_path = os.path.join(merged_dir_path + "*", f"{prefix}-*")

                temp_dirs = []
                for temp_output_f in glob.glob(temp_path):
                    output_file = temp_merged_dir_path.replace(suffix, "")
                    shutil.move(temp_output_f, output_file)
                    temp_dirs.append(os.path.dirname(temp_output_f))

                for temp_dir in set(temp_dirs):
                    shutil.rmtree(temp_dir)

        else:  # engine == 'pyshp' (default)
            temp_dir = os.path.dirname(merged_dir_path)
            paths_to_output_files_temp_ = [
                glob.glob(os.path.join(temp_dir, f"{prefix}-*.{ext}"))
                for ext in {"dbf", "shp", "shx"}
            ]
            paths_to_output_files_temp = itertools.chain.from_iterable(paths_to_output_files_temp_)

            for temp_output_f in paths_to_output_files_temp:
                output_file = os.path.join(
                    merged_dir_path, os.path.basename(temp_output_f).replace(suffix, "")
                )
                shutil.move(temp_output_f, output_file)

    @classmethod
    def merge_layers(cls, shp_zip_pathnames, layer_name, engine='geopandas', rm_zip_extracts=True,
                     output_dir=None, rm_shp_temp=True, return_shp_pathname=False, verbose=False,
                     raise_error=False):
        # noinspection shadowing-names,unresolved-references
        """
        Merge shapefiles over a specific layer for multiple geographic regions.

        :param shp_zip_pathnames: List of paths to zipped shapefile archives (e.g. ".shp.zip").
        :type shp_zip_pathnames: list | tuple
        :param layer_name: Name of a shapefile layer (e.g. "railways").
        :type layer_name: str
        :param engine: The open-source package used to merge and save shapefiles. Options
            include ``'pyshp'``, ``'geopandas'`` and ``'gpd'``. Defaults to ``'geopandas'``.
            If ``engine='geopandas'``, this function relies on `geopandas.GeoDataFrame.to_file()`_;
            otherwise it uses `shapefile.Writer()`_ by default.
        :type engine: str
        :param rm_zip_extracts: Whether to delete the extracted files. Defaults to ``True``.
        :type rm_zip_extracts: bool
        :param output_dir: Directory where the merged ".shp" files will be saved.
            If ``None``, the layer name is used as the folder name. Defaults to ``None``.
        :type output_dir: str | pathlib.Path | os.PathLike | None
        :param rm_shp_temp: Whether to delete temporary layer files. Defaults to ``True``.
        :type rm_shp_temp: bool
        :param return_shp_pathname: Whether to return the pathname of the merged ".shp" file.
            Defaults to ``False``.
        :type return_shp_pathname: bool
        :param verbose: Whether to print relevant information to the console. Defaults to ``False``.
        :type verbose: bool | int
        :param raise_error: Whether to raise an exception upon failure. If ``False``, the error
            will be suppressed. Defaults to ``False``.
        :type raise_error: bool
        :return: A list containing the path(s) to the merged file when
            ``return_shp_pathname=True``. Returns ``None`` otherwise.
        :rtype: list | None

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

        .. _pydriosm-reader-SHP-merge_layer_shps:

        **Examples**::

            >>> # Merge 'railways' layers of Greater Manchester and West Yorkshire"

            >>> from pydriosm.reader._shp import SHP
            >>> from pydriosm.downloader import BBBikeDownloader
            >>> from pyhelpers.dirs import delete_dir, get_relative_path
            >>> import os

            >>> # Download the .shp.zip file of Manchester and West Yorkshire
            >>> subregion_names = ['London', 'Birmingham']
            >>> osm_file_format = ".shp"
            >>> data_dir = "tests/osm_data"

            >>> bbd = BBBikeDownloader()

            >>> bbd.download_data(subregion_names, osm_file_format, data_dir, verbose=True)
            Proceed with downloading data in the format ".shp.zip" for the following geographic...
                "London"
                "Birmingham"
              to "tests/osm_data/"
            ? [No]|Yes: yes
            Downloading "London.osm.shp.zip" 100%|██████████| 261M/261M | 15.4MB/s | Ela...
              Saving "London.osm.shp.zip" to "tests/osm_data/london/" ... Done.
            Downloading "Birmingham.osm.shp.zip" 100%|██████████| 79.9M/79.9M | 16.6MB/s...
              Saving "Birmingham.osm.shp.zip" to "tests/osm_data/birmingham/" ... Done.

            >>> get_relative_path(bbd.download_dir, as_str=True)
            'tests/osm_data'
            >>> len(bbd.data_paths)
            2

            >>> # Merge the layers of 'railways' of the two subregions
            >>> merged_shp_path = SHP.merge_layers(
            ...     bbd.data_paths,
            ...     layer_name='railways',
            ...     verbose=True,
            ...     return_shp_pathname=True
            ... )
            Merging the following shapefiles:
              "london_railways.shp"
              "birmingham_railways.shp"
              In progress ... Done.
                Find the merged shapefile in "tests/osm_data/lon-bir-railways/".

            >>> # Check the pathname of the merged shapefile
            >>> type(merged_shp_path)
            list
            >>> len(merged_shp_path)
            1
            >>> merged_shp_path = merged_shp_path[0]
            >>> get_relative_path(merged_shp_path, as_str=True)
            'tests/osm_data/lon-bir-railways/lon-bir-railways.shp'

            >>> # Read the merged .shp file
            >>> merged_shp_data = SHP.read_shp(merged_shp_path)
            >>> merged_shp_data.head()
               osm_id  ...                                           geometry
            0   30804  ...     LINESTRING (0.00486 51.62793, 0.0062 51.62927)
            1  101298  ...  LINESTRING (-0.22499 51.4937, -0.22516 51.4945...
            2  101486  ...  LINESTRING (-0.20555 51.51954, -0.20514 51.519...
            3  101511  ...  LINESTRING (-0.2119 51.52419, -0.21081 51.5239...
            4  282898  ...   LINESTRING (-0.1862 51.61592, -0.18687 51.61386)
            [5 rows x 4 columns]

            >>> # Delete the test data directory
            >>> delete_dir(bbd.download_dir, verbose=True)
            Confirm deletion of the directory "tests/osm_data/" (Not empty)?
             [No]|Yes: yes
            Deleting "tests/osm_data/" ... Done.

        .. seealso::

            - Examples for the method
              :meth:`GeofabrikReader.merge_shp_layers()
              <pydriosm.reader.GeofabrikReader.merge_shp_layers>`.
        """

        extract_dir_path = cls._extract_files(
            shp_zip_file_paths=shp_zip_pathnames, layer_name=layer_name, verbose=verbose
        )

        # Specify a directory that stores files for the specific layer securely
        # by removing potential suffixes from the base filename.
        subregion_names = [
            re.sub(r'\.shp\.zip$', '', os.path.basename(str(x)), flags=re.IGNORECASE)
            .replace("-latest-free", "")
            .replace(".osm", "")
            .lower()
            for x in shp_zip_pathnames
        ]

        suffix = "_temp"
        prefix = "-".join([
            "_".join([y[:3] for y in re.split(r'[- ]', x) if y]) for x in subregion_names
        ])
        path_to_data_dir = os.path.commonpath([str(p) for p in shp_zip_pathnames])
        merged_dirname_temp = f"{prefix}-{layer_name}{suffix}"
        path_to_merged_dir_temp = os.path.join(path_to_data_dir, merged_dirname_temp)
        os.makedirs(path_to_merged_dir_temp, exist_ok=True)

        temp_file_paths = _copy_temp_files(
            subregion_names=subregion_names,
            layer_name=layer_name,
            path_to_extract_dirs=extract_dir_path,
            path_to_merged_dir_temp=path_to_merged_dir_temp,
        )

        # Get the paths to the target .shp files
        shp_file_paths = [x for x in temp_file_paths if x.endswith(".shp")]

        if verbose:
            print("Merging the following shapefiles:")
            print("  " + "\n  ".join(f'"{os.path.basename(f)}"' for f in shp_file_paths))
            print("  In progress ... ", flush=True, end="")

        try:
            path_to_merged_dir = cls._make_merged_dir(
                output_dir=output_dir,
                data_dir=path_to_data_dir,
                temp_merged_dir=merged_dirname_temp,
                suffix=suffix,
            )

            cls.merge_shps(
                shp_pathnames=shp_file_paths,
                merged_dir=path_to_merged_dir,
                engine=engine,
            )

            cls._transfer_files(
                engine=engine,
                merged_dir=path_to_merged_dir,
                temp_merged_dir=path_to_merged_dir_temp,
                prefix=prefix,
                suffix=suffix,
            )

            if verbose:
                print("Done.")

            if rm_zip_extracts:
                for path_to_extract_dir in extract_dir_path:
                    shutil.rmtree(path_to_extract_dir)

            if rm_shp_temp:
                shutil.rmtree(path_to_merged_dir_temp)

            if verbose:
                rel_m_path_str = get_relative_path(path_to_merged_dir, as_str=True, quoted=True)
                print(f"    Find the merged shapefile in {rel_m_path_str}.")

            if return_shp_pathname:
                merged_shp_file_path = glob.glob(
                    os.path.join(str(path_to_merged_dir), "**", "*.shp"), recursive=True
                )
                return merged_shp_file_path

            return None

        except Exception as e:
            _print_failure_message(e, "Failed. Error:", verbose=verbose, raise_error=raise_error)
            return None
