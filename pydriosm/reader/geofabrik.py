"""
Read OpenStreetMap data extracts available from Geofabrik free download server.
"""

import os

from pyhelpers.text import find_similar_str

from pydriosm.downloader import GeofabrikDownloader
from pydriosm.reader._reader import PBFReadParse, _Reader


class GeofabrikReader(_Reader):
    """
    Read `Geofabrik <https://download.geofabrik.de/>`_ OpenStreetMap data extracts.
    """

    #: str: Default download directory.
    DEFAULT_DATA_DIR = "osm_data\\geofabrik"
    #: set: Valid file formats.
    FILE_FORMATS = {'.osm.pbf', '.shp.zip', '.osm.bz2'}

    def __init__(self, data_dir=None, max_tmpfile_size=None):
        """
        :param max_tmpfile_size: defaults to ``None``,
            see also the function `pyhelpers.settings.gdal_configurations()`_
        :type max_tmpfile_size: int | None
        :param data_dir: (a path or a name of) a directory where a data file is,
            defaults to ``None``;
            when ``data_dir=None``, it refers to a folder named ``osm_geofabrik``
            under the current working directory
        :type data_dir: str | None

        :ivar GeofabrikDownloader downloader: instance of the class
            :py:class:`~pydriosm.downloader.GeofabrikDownloader`
        :ivar str name: name of the data resource
        :ivar str url: url of the homepage to the Geofabrik free download server

        .. _`pyhelpers.settings.gdal_configurations()`:
            https://pyhelpers.readthedocs.io/en/latest/_generated/
            pyhelpers.settings.gdal_configurations.html

        **Examples**::

            >>> from pydriosm.reader import GeofabrikReader

            >>> gfr = GeofabrikReader()

            >>> gfr.NAME
            'Geofabrik'
        """

        super().__init__(
            downloader=GeofabrikDownloader, data_dir=data_dir, max_tmpfile_size=max_tmpfile_size)

    def get_file_path(self, subregion_name, osm_file_format, data_dir=None):
        """
        Get the local path to an OSM data file of a geographic (sub)region.

        :param subregion_name: name of a geographic (sub)region (case-insensitive)
            that is available on Geofabrik free download server
        :type subregion_name: str
        :param osm_file_format: file format of the OSM data available on the free download server
        :type osm_file_format: str
        :param data_dir: directory where the data file of the ``subregion_name`` is located/saved;
            if ``None`` (default), the default local directory
        :type data_dir: str | None
        :return: path to PBF (.osm.pbf) file
        :rtype: str | None

        **Examples**::

            >>> from pydriosm.reader import GeofabrikReader
            >>> from pyhelpers.dirs import delete_dir
            >>> import os

            >>> gfr = GeofabrikReader()

            >>> subrgn_name = 'rutland'
            >>> file_format = ".pbf"
            >>> dat_dir = "tests\\osm_data"

            >>> path_to_rutland_pbf = gfr.get_file_path(subrgn_name, file_format, data_dir=dat_dir)

            >>> # When "rutland-latest.osm.pbf" is unavailable at the package data directory
            >>> os.path.isfile(path_to_rutland_pbf)
            False

            >>> # Download the PBF data file of Rutland to "tests\\osm_data\\"
            >>> gfr.downloader.download_osm_data(subrgn_name, file_format, dat_dir, verbose=True)
            To download .osm.pbf data of the following geographic (sub)region(s):
                Rutland
            ? [No]|Yes: yes
            Downloading "rutland-latest.osm.pbf"
                to "tests\\osm_data\\rutland\\" ... Done.

            >>> # Check again
            >>> path_to_rutland_pbf = gfr.get_file_path(subrgn_name, file_format, data_dir=dat_dir)
            >>> os.path.relpath(path_to_rutland_pbf)
            'tests\\osm_data\\rutland\\rutland-latest.osm.pbf'
            >>> os.path.isfile(path_to_rutland_pbf)
            True

            >>> # Delete the test data directory
            >>> delete_dir(dat_dir, verbose=True)
            To delete the directory "tests\\osm_data\\" (Not empty)
            ? [No]|Yes: yes
            Deleting "tests\\osm_data\\" ... Done.
        """

        path_to_file = super().get_file_path(
            subregion_name=subregion_name, osm_file_format=osm_file_format, data_dir=data_dir)

        return path_to_file

    def get_pbf_layer_names(self, subregion_name, data_dir=None):
        """
        Get indices and names of all layers in the PBF data file of a given (sub)region.

        :param subregion_name: name of a geographic (sub)region (case-insensitive)
            that is available on Geofabrik free download server
        :type subregion_name: str
        :param data_dir:
        :type data_dir:
        :return: indices and names of each layer of the PBF data file
        :rtype: dict

        **Examples**::

            >>> from pydriosm.reader import GeofabrikReader
            >>> from pyhelpers.dirs import delete_dir
            >>> import os

            >>> gfr = GeofabrikReader()

            >>> # Download the .shp.zip file of Rutland as an example
            >>> subrgn_name = 'london'
            >>> file_format = ".pbf"
            >>> dat_dir = "tests\\osm_data"

            >>> gfr.downloader.download_osm_data(subrgn_name, file_format, dat_dir, verbose=True)
            To download .osm.pbf data of the following geographic (sub)region(s):
                Greater London
            ? [No]|Yes: yes
            Downloading "greater-london-latest.osm.pbf"
                to "tests\\osm_data\\greater-london\\" ... Done.

            >>> london_pbf_path = gfr.data_paths[0]
            >>> os.path.relpath(london_pbf_path)
            'tests\\osm_data\\greater-london\\greater-london-latest.osm.pbf'

            >>> lyr_idx_names = gfr.get_pbf_layer_names(london_pbf_path)
            >>> lyr_idx_names
            {0: 'points',
             1: 'lines',
             2: 'multilinestrings',
             3: 'multipolygons',
             4: 'other_relations'}

            >>> # Delete the example data and the test data directory
            >>> delete_dir(dat_dir, verbose=True)
            To delete the directory "tests\\osm_data\\" (Not empty)
            ? [No]|Yes: yes
            Deleting "tests\\osm_data\\" ... Done.
        """

        data_dir_ = self.data_dir if data_dir is None else data_dir

        path_to_osm_pbf = self.get_file_path(
            subregion_name=subregion_name, osm_file_format=".osm.pbf", data_dir=data_dir_)

        layer_idx_names = PBFReadParse.get_pbf_layer_names(path_to_osm_pbf)

        return layer_idx_names

    def read_osm_pbf(self, subregion_name, data_dir=None, readable=False, expand=False,
                     parse_geometry=False, parse_properties=False, parse_other_tags=False,
                     update=False, download=True, pickle_it=False, ret_pickle_path=False,
                     rm_pbf_file=False, chunk_size_limit=50, verbose=False, **kwargs):
        """
        Read a PBF (.osm.pbf) data file of a geographic (sub)region.

        :param subregion_name: name of a geographic (sub)region (case-insensitive)
            that is available on Geofabrik free download server
        :type subregion_name: str
        :param data_dir: directory where the .osm.pbf data file is located/saved;
            if ``None``, the default local directory
        :type data_dir: str | None
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
        :param download: whether to download/update the PBF data file of the given subregion,
            if it is not available at the specified path, defaults to ``True``
        :type download: bool
        :param update: whether to check to update pickle backup (if available), defaults to ``False``
        :type update: bool
        :param pickle_it: whether to save the .pbf data as a pickle file, defaults to ``False``
        :type pickle_it: bool
        :param ret_pickle_path: (when ``pickle_it=True``)
            whether to return a path to the saved pickle file
        :type ret_pickle_path: bool
        :param rm_pbf_file: whether to delete the downloaded .osm.pbf file, defaults to ``False``
        :type rm_pbf_file: bool
        :param chunk_size_limit: threshold (in MB) that triggers the use of chunk parser,
            defaults to ``50``;
            if the size of the .osm.pbf file (in MB) is greater than ``chunk_size_limit``,
            it will be parsed in a chunk-wise way
        :type chunk_size_limit: int | None
        :param verbose: whether to print relevant information in console as the function runs,
            defaults to ``False``
        :type verbose: bool | int
        :param kwargs: [optional] parameters of the method
            :meth:`PBFReadParse.read_pbf()<pydriosm.reader.PBFReadParse.read_pbf>`
        :return: dictionary of the .osm.pbf data;
            when ``pickle_it=True``, return a tuple of the dictionary and a path to the pickle file
        :rtype: dict | tuple | None

        .. _`shapely.geometry`:
            https://shapely.readthedocs.io/en/latest/manual.html#geometric-objects
        .. _`dict`:
            https://docs.python.org/3/library/stdtypes.html#dict

        .. _pydriosm-reader-GeofabrikReader-read_osm_pbf:

        **Examples**::

            >>> from pydriosm.reader import GeofabrikReader
            >>> from pyhelpers.dirs import delete_dir

            >>> gfr = GeofabrikReader()

            >>> subrgn_name = 'rutland'
            >>> dat_dir = "tests\\osm_data"

            >>> # If the PBF data of Rutland is not available at the specified data directory,
            >>> # the function can download the latest data by setting `download=True` (default)
            >>> pbf_raw = gfr.read_osm_pbf(subrgn_name, data_dir=dat_dir, verbose=True)
            Downloading "rutland-latest.osm.pbf"
                to "tests\\osm_data\\rutland\\" ... Done.
            Reading "tests\\osm_data\\rutland\\rutland-latest.osm.pbf" ... Done.
            >>> type(pbf_raw)
            dict
            >>> list(pbf_raw.keys())
            ['points', 'lines', 'multilinestrings', 'multipolygons', 'other_relations']

            >>> pbf_raw_points = pbf_raw['points']
            >>> type(pbf_raw_points)
            list
            >>> type(pbf_raw_points[0])
            osgeo.ogr.Feature

            >>> # Set `readable=True`
            >>> pbf_parsed = gfr.read_osm_pbf(subrgn_name, dat_dir, readable=True, verbose=True)
            Parsing "tests\\osm_data\\rutland\\rutland-latest.osm.pbf" ... Done.
            >>> pbf_parsed_points = pbf_parsed['points']
            >>> pbf_parsed_points.head()
            0    {'type': 'Feature', 'geometry': {'type': 'Poin...
            1    {'type': 'Feature', 'geometry': {'type': 'Poin...
            2    {'type': 'Feature', 'geometry': {'type': 'Poin...
            3    {'type': 'Feature', 'geometry': {'type': 'Poin...
            4    {'type': 'Feature', 'geometry': {'type': 'Poin...
            Name: points, dtype: object

            >>> # Set `expand=True`, which would force `readable=True`
            >>> pbf_parsed_ = gfr.read_osm_pbf(subrgn_name, dat_dir, expand=True, verbose=True)
            Parsing "tests\\osm_data\\rutland\\rutland-latest.osm.pbf" ... Done.
            >>> pbf_parsed_points_ = pbf_parsed_['points']
            >>> pbf_parsed_points_.head()
                     id  ...                                         properties
            0    488432  ...  {'osm_id': '488432', 'name': None, 'barrier': ...
            1    488658  ...  {'osm_id': '488658', 'name': 'Tickencote Inter...
            2  13883868  ...  {'osm_id': '13883868', 'name': None, 'barrier'...
            3  14049101  ...  {'osm_id': '14049101', 'name': None, 'barrier'...
            4  14558402  ...  {'osm_id': '14558402', 'name': None, 'barrier'...
            [5 rows x 3 columns]

            >>> # Set `readable` and `parse_geometry` to be `True`
            >>> pbf_parsed_1 = gfr.read_osm_pbf(subrgn_name, dat_dir, readable=True,
            ...                                 parse_geometry=True)
            >>> pbf_parsed_1_point = pbf_parsed_1['points'][0]
            >>> pbf_parsed_1_point['geometry']
            'POINT (-0.5134241 52.6555853)'
            >>> pbf_parsed_1_point['properties']['other_tags']
            '"odbl"=>"clean"'

            >>> # Set `readable` and `parse_other_tags` to be `True`
            >>> pbf_parsed_2 = gfr.read_osm_pbf(subrgn_name, dat_dir, readable=True,
            ...                                 parse_other_tags=True)
            >>> pbf_parsed_2_point = pbf_parsed_2['points'][0]
            >>> pbf_parsed_2_point['geometry']
            {'type': 'Point', 'coordinates': [-0.5134241, 52.6555853]}
            >>> pbf_parsed_2_point['properties']['other_tags']
            {'odbl': 'clean'}

            >>> # Set `readable`, `parse_geometry` and `parse_other_tags` to be `True`
            >>> pbf_parsed_3 = gfr.read_osm_pbf(subrgn_name, dat_dir, readable=True,
            ...                                 parse_geometry=True, parse_other_tags=True)
            >>> pbf_parsed_3_point = pbf_parsed_3['points'][0]
            >>> pbf_parsed_3_point['geometry']
            'POINT (-0.5134241 52.6555853)'
            >>> pbf_parsed_3_point['properties']['other_tags']
            {'odbl': 'clean'}

            >>> # Delete the example data and the test data directory
            >>> delete_dir(dat_dir, verbose=True)
            To delete the directory "tests\\osm_data\\" (Not empty)
            ? [No]|Yes: yes
            Deleting "tests\\osm_data\\" ... Done.
        """

        osm_pbf_data = super().read_osm_pbf(
            subregion_name=subregion_name, data_dir=data_dir, readable=readable, expand=expand,
            parse_geometry=parse_geometry, parse_properties=parse_properties,
            parse_other_tags=parse_other_tags,
            update=update, download=download, pickle_it=pickle_it, ret_pickle_path=ret_pickle_path,
            rm_pbf_file=rm_pbf_file, chunk_size_limit=chunk_size_limit, verbose=verbose,
            **kwargs)

        return osm_pbf_data

    def get_shp_pathname(self, subregion_name, layer_name=None, feature_name=None, data_dir=None):
        """
        Get path(s) to .shp file(s) for a geographic (sub)region
        (by searching a local data directory).

        :param subregion_name: name of a geographic (sub)region (case-insensitive)
            that is available on Geofabrik free download server
        :type subregion_name: str
        :param layer_name: name of a .shp layer (e.g. ``'railways'``), defaults to ``None``
        :type layer_name: str | None
        :param feature_name: name of a feature (e.g. ``'rail'``);
            if ``None`` (default), all available features included
        :type feature_name: str | None
        :param data_dir: directory where the search is conducted; if ``None`` (default),
            the default directory
        :type data_dir: str | None
        :return: path(s) to .shp file(s)
        :rtype: list

        **Examples**::

            >>> from pydriosm.reader import GeofabrikReader
            >>> from pyhelpers.dirs import delete_dir
            >>> import os

            >>> gfr = GeofabrikReader()

            >>> subrgn_name = 'london'
            >>> file_format = ".shp"
            >>> dat_dir = "tests\\osm_data"

            >>> # Try to get the shapefiles' pathnames
            >>> london_shp_path = gfr.get_shp_pathname(subrgn_name, data_dir=dat_dir)
            >>> london_shp_path  # An empty list if no data is available
            []

            >>> # Download the shapefiles of London
            >>> path_to_london_shp_zip = gfr.downloader.download_osm_data(
            ...     subrgn_name, file_format, dat_dir, verbose=True, ret_download_path=True)
            To download .shp.zip data of the following geographic (sub)region(s):
                Greater London
            ? [No]|Yes: yes
            Downloading "greater-london-latest-free.shp.zip"
                to "tests\\osm_data\\greater-london\\" ... Done.

            >>> type(path_to_london_shp_zip)
            list
            >>> len(path_to_london_shp_zip)
            1

            >>> # Extract the downloaded .zip file
            >>> gfr.SHP.unzip_shp_zip(path_to_london_shp_zip[0], verbose=True)
            Extracting "tests\\osm_data\\greater-london\\greater-london-latest-free.shp.zip"
                to "tests\\osm_data\\greater-london\\greater-london-latest-free-shp\\" ... Done.

            >>> # Try again to get the shapefiles' pathnames
            >>> london_shp_path = gfr.get_shp_pathname(subrgn_name, data_dir=dat_dir)
            >>> len(london_shp_path) > 1
            True

            >>> # Get the file path of 'railways' shapefile
            >>> lyr_name = 'railways'
            >>> railways_shp_path = gfr.get_shp_pathname(subrgn_name, lyr_name, data_dir=dat_dir)
            >>> len(railways_shp_path)
            1
            >>> railways_shp_path = railways_shp_path[0]
            >>> os.path.relpath(railways_shp_path)
            'tests\\osm_data\\greater-london\\greater-london-latest-free-shp\\gis_osm_railways_fr...

            >>> # Get/save shapefile data of features labelled 'rail' only
            >>> feat_name = 'rail'
            >>> railways_shp = gfr.SHP.read_layer_shps(
            ...     railways_shp_path, feature_names=feat_name, save_feat_shp=True)
            >>> railways_shp.head()
                osm_id  code  ...                                        coordinates shape_type
            0    30804  6101  ...  [(0.0048644, 51.6279262), (0.0061979, 51.62926...          3
            3   101511  6101  ...  [(-0.2119027, 51.5241906), (-0.2108059, 51.523...          3
            5   361978  6101  ...  [(-0.0298545, 51.6619398), (-0.0302322, 51.659...          3
            6  2370155  6101  ...  [(-0.3379005, 51.5937776), (-0.3367807, 51.593...          3
            7  2526598  6101  ...  [(-0.1886021, 51.3602632), (-0.1884216, 51.360...          3
            [5 rows x 9 columns]

            >>> # Get the file path to the data of 'rail'
            >>> rail_shp_path = gfr.get_shp_pathname(subrgn_name, lyr_name, feat_name, dat_dir)
            >>> len(rail_shp_path)
            1
            >>> rail_shp_path = rail_shp_path[0]
            >>> os.path.relpath(rail_shp_path)
            'tests\\osm_data\\greater-london\\greater-london-latest-free-shp\\railways\\rail.shp'

            >>> # Retrieve the data of 'rail' feature
            >>> railways_rail_shp = gfr.SHP.read_layer_shps(rail_shp_path)
            >>> railways_rail_shp.head()
                osm_id  code  ...                                        coordinates shape_type
            0    30804  6101  ...  [(0.0048644, 51.6279262), (0.0061979, 51.62926...          3
            1   101511  6101  ...  [(-0.2119027, 51.5241906), (-0.2108059, 51.523...          3
            2   361978  6101  ...  [(-0.0298545, 51.6619398), (-0.0302322, 51.659...          3
            3  2370155  6101  ...  [(-0.3379005, 51.5937776), (-0.3367807, 51.593...          3
            4  2526598  6101  ...  [(-0.1886021, 51.3602632), (-0.1884216, 51.360...          3
            [5 rows x 9 columns]

            >>> # Delete the example data and the test data directory
            >>> delete_dir(dat_dir, verbose=True)
            To delete the directory "tests\\osm_data\\" (Not empty)
            ? [No]|Yes: yes
            Deleting "tests\\osm_data\\" ... Done.
        """

        path_to_osm_shp_file = super().get_shp_pathname(
            subregion_name=subregion_name, layer_name=layer_name, feature_name=feature_name,
            data_dir=data_dir)

        return path_to_osm_shp_file

    def merge_subregion_layer_shp(self, subregion_names, layer_name, data_dir=None, engine='pyshp',
                                  update=False, download=True, rm_zip_extracts=True,
                                  merged_shp_dir=None, rm_shp_temp=True, verbose=False,
                                  ret_merged_shp_path=False):
        """
        Merge shapefiles for a specific layer of two or multiple geographic regions.

        :param subregion_names: names of geographic region (case-insensitive)
            that is available on Geofabrik free download server
        :type subregion_names: list
        :param layer_name: name of a layer (e.g. 'railways')
        :type layer_name: str
        :param engine: the method used to merge/save shapefiles;
            options include: ``'pyshp'`` (default) and ``'geopandas'`` (or ``'gpd'``)
            if ``engine='geopandas'``, this function relies on `geopandas.GeoDataFrame.to_file()`_;
            otherwise, it by default uses `shapefile.Writer()`_
        :type engine: str
        :param update: whether to update the source .shp.zip files, defaults to ``False``
        :type update: bool
        :param download: whether to ask for confirmation
            before starting to download a file, defaults to ``True``
        :type download: bool
        :param data_dir: directory where the .shp.zip data files are located/saved;
            if ``None`` (default), the default directory
        :type data_dir: str | None
        :param rm_zip_extracts: whether to delete the extracted files, defaults to ``False``
        :type rm_zip_extracts: bool
        :param rm_shp_temp: whether to delete temporary layer files, defaults to ``False``
        :type rm_shp_temp: bool
        :param merged_shp_dir: if ``None`` (default), use the layer name
            as the name of the folder where the merged .shp files will be saved
        :type merged_shp_dir: str | None
        :param verbose: whether to print relevant information in console, defaults to ``False``
        :type verbose: bool | int
        :param ret_merged_shp_path: whether to return the path to the merged .shp file,
            defaults to ``False``
        :type ret_merged_shp_path: bool
        :return: the path to the merged file when ``ret_merged_shp_path=True``
        :rtype: list | str

        .. _`geopandas.GeoDataFrame.to_file()`:
            https://geopandas.org/reference.html#geopandas.GeoDataFrame.to_file
        .. _`shapefile.Writer()`:
            https://github.com/GeospatialPython/pyshp#writing-shapefiles

        .. _pydriosm-GeofabrikReader-merge_subregion_layer_shp:

        **Examples**::

            >>> from pydriosm.reader import GeofabrikReader
            >>> from pyhelpers.dirs import cd, delete_dir
            >>> import os

            >>> gfr = GeofabrikReader()

        **Example 1**::

            >>> # To merge 'railways' of Greater Manchester and West Yorkshire
            >>> subrgn_name = ['Manchester', 'West Yorkshire']
            >>> lyr_name = 'railways'
            >>> dat_dir = "tests\\osm_data"

            >>> path_to_merged_shp_file = gfr.merge_subregion_layer_shp(
            ...     subrgn_name, lyr_name, dat_dir, verbose=True, ret_merged_shp_path=True)
            To download .shp.zip data of the following geographic (sub)region(s):
                Greater Manchester
                West Yorkshire
            ? [No]|Yes: yes
            Downloading "greater-manchester-latest-free.shp.zip"
                to "tests\\osm_data\\greater-manchester\\" ... Done.
            Downloading "west-yorkshire-latest-free.shp.zip"
                to "tests\\osm_data\\west-yorkshire\\" ... Done.
            Merging the following shapefiles:
                "greater-manchester_gis_osm_railways_free_1.shp"
                "west-yorkshire_gis_osm_railways_free_1.shp"
                    In progress ... Done.
                    Find the merged shapefile at "tests\\osm_data\\gre_man-wes_yor-railways\\".

            >>> os.path.relpath(path_to_merged_shp_file)
            'tests\\osm_data\\gre_man-wes_yor-railways\\linestring.shp'

            >>> # Read the merged data
            >>> manchester_yorkshire_railways_shp = gfr.SHP.read_shp(path_to_merged_shp_file)
            >>> manchester_yorkshire_railways_shp.head()
                osm_id  code  ...                                        coordinates shape_type
            0   928999  6101  ...  [(-2.2844621, 53.4802635), (-2.2949851, 53.481...          3
            1   929904  6101  ...  [(-2.2917977, 53.4619559), (-2.2924877, 53.461...          3
            2   929905  6102  ...  [(-2.2794048, 53.4605819), (-2.2799722, 53.460...          3
            3  3663332  6102  ...  [(-2.2382139, 53.4817985), (-2.2381708, 53.481...          3
            4  3996086  6101  ...  [(-2.6003053, 53.4604346), (-2.6005261, 53.460...          3
            [5 rows x 9 columns]

            >>> # Delete the merged files
            >>> delete_dir(os.path.dirname(path_to_merged_shp_file), verbose=True)
            To delete the directory "tests\\osm_data\\gre_man-wes_yor-railways\\" (Not empty)
            ? [No]|Yes: yes
            Deleting "tests\\osm_data\\gre_man-wes_yor-railways\\" ... Done.

            >>> # Delete the downloaded .shp.zip data files
            >>> delete_dir(list(map(os.path.dirname, gfr.downloader.data_paths)), verbose=True)
            To delete the following directories:
                "tests\\osm_data\\greater-manchester\\" (Not empty)
                "tests\\osm_data\\west-yorkshire\\" (Not empty)
            ? [No]|Yes: yes
            Deleting "tests\\osm_data\\greater-manchester\\" ... Done.
            Deleting "tests\\osm_data\\west-yorkshire\\" ... Done.

        **Example 2**::

            >>> # To merge 'transport' of Greater London, Kent and Surrey

            >>> subrgn_name = ['London', 'Kent', 'Surrey']
            >>> lyr_name = 'transport'

            >>> path_to_merged_shp_file = gfr.merge_subregion_layer_shp(
            ...     subrgn_name, lyr_name, dat_dir, verbose=True, ret_merged_shp_path=True)
            To download .shp.zip data of the following geographic (sub)region(s):
                Greater London
                Kent
                Surrey
            ? [No]|Yes: yes
            Downloading "greater-london-latest-free.shp.zip"
                to "tests\\osm_data\\greater-london\\" ... Done.
            Downloading "kent-latest-free.shp.zip"
                to "tests\\osm_data\\kent\\" ... Done.
            Downloading "surrey-latest-free.shp.zip"
                to "tests\\osm_data\\surrey\\" ... Done.
            Merging the following shapefiles:
                "greater-london_gis_osm_transport_a_free_1.shp"
                "greater-london_gis_osm_transport_free_1.shp"
                "kent_gis_osm_transport_a_free_1.shp"
                "kent_gis_osm_transport_free_1.shp"
                "surrey_gis_osm_transport_a_free_1.shp"
                "surrey_gis_osm_transport_free_1.shp"
                    In progress ... Done.
                    Find the merged shapefile at "tests\\osm_data\\gre_lon-ken-sur-transport\\".

            >>> type(path_to_merged_shp_file)
            list
            >>> len(path_to_merged_shp_file)
            2
            >>> os.path.relpath(path_to_merged_shp_file[0])
            'tests\\osm_data\\gre-lon_ken_sur_transport\\point.shp'
            >>> os.path.relpath(path_to_merged_shp_file[1])
            'tests\\osm_data\\gre-lon_ken_sur_transport\\polygon.shp'

            >>> # Read the merged shapefile
            >>> merged_transport_shp_1 = gfr.SHP.read_shp(path_to_merged_shp_file[1])
            >>> merged_transport_shp_1.head()
                 osm_id  ...  shape_type
            0   5077928  ...           5
            1   8610280  ...           5
            2  15705264  ...           5
            3  23077379  ...           5
            4  24016945  ...           5
            [5 rows x 6 columns]

            >>> # Delete the merged files
            >>> delete_dir(os.path.commonpath(path_to_merged_shp_file), verbose=True)
            To delete the directory "tests\\osm_data\\gre_lon-ken-sur-transport\\" (Not empty)
            ? [No]|Yes: yes
            Deleting "tests\\osm_data\\gre_lon-ken-sur-transport\\" ... Done.

            >>> # Delete the example data and the test data directory
            >>> delete_dir(dat_dir, verbose=True)
            To delete the directory "tests\\osm_data\\" (Not empty)
            ? [No]|Yes: yes
            Deleting "tests\\osm_data\\" ... Done.
        """

        # Make sure all the required shape files are ready
        layer_name_ = find_similar_str(x=layer_name, lookup_list=self.SHP.LAYER_NAMES)
        subregion_names_ = [self.downloader.validate_subregion_name(x) for x in subregion_names]

        osm_file_format = ".shp.zip"

        # Download the files if not available
        paths_to_shp_zip_files = self.downloader.download_osm_data(
            subregion_names_, osm_file_format=osm_file_format, download_dir=data_dir,
            update=update, confirmation_required=False if download else True,
            deep_retry=True, interval=1, verbose=verbose, ret_download_path=True)

        if all(os.path.isfile(shp_zip_path_file) for shp_zip_path_file in paths_to_shp_zip_files):
            path_to_merged_shp = self.SHP.merge_layer_shps(
                shp_zip_pathnames=paths_to_shp_zip_files, layer_name=layer_name_, engine=engine,
                rm_zip_extracts=rm_zip_extracts, output_dir=merged_shp_dir, rm_shp_temp=rm_shp_temp,
                verbose=verbose, ret_shp_pathname=ret_merged_shp_path)

            if ret_merged_shp_path:
                return path_to_merged_shp

    def read_shp_zip(self, subregion_name, layer_names=None, feature_names=None, data_dir=None,
                     update=False, download=True, pickle_it=False, ret_pickle_path=False,
                     rm_extracts=False, rm_shp_zip=False, verbose=False, **kwargs):
        """
        Read a .shp.zip data file of a geographic (sub)region.

        :param subregion_name: name of a geographic (sub)region (case-insensitive)
            that is available on Geofabrik free download server
        :type subregion_name: str
        :param layer_names: name of a .shp layer, e.g. 'railways', or names of multiple layers;
            if ``None`` (default), all available layers
        :type layer_names: str | list | None
        :param feature_names: name of a feature, e.g. 'rail', or names of multiple features;
            if ``None`` (default), all available features
        :type feature_names: str | list | None
        :param data_dir: directory where the .shp.zip data file is located/saved;
            if ``None``, the default directory
        :type data_dir: str | None
        :param update: whether to check to update pickle backup (if available), defaults to ``False``
        :type update: bool
        :param download: whether to ask for confirmation
            before starting to download a file, defaults to ``True``
        :type download: bool
        :param pickle_it: whether to save the .shp data as a pickle file, defaults to ``False``
        :type pickle_it: bool
        :param ret_pickle_path: (when ``pickle_it=True``)
            whether to return a path to the saved pickle file
        :type ret_pickle_path: bool
        :param rm_extracts: whether to delete extracted files from the .shp.zip file,
            defaults to ``False``
        :type rm_extracts: bool
        :param rm_shp_zip: whether to delete the downloaded .shp.zip file, defaults to ``False``
        :type rm_shp_zip: bool
        :param verbose: whether to print relevant information in console as the function runs,
            defaults to ``False``
        :type verbose: bool | int
        :return: dictionary of the shapefile data,
            with keys and values being layer names and tabular data
            (in the format of `geopandas.GeoDataFrame`_), respectively
        :rtype: dict | collections.OrderedDict | None

        .. _`geopandas.GeoDataFrame`: https://geopandas.org/reference.html#geodataframe

        **Examples**::

            >>> from pydriosm.reader import GeofabrikReader
            >>> from pyhelpers.dirs import delete_dir

            >>> gfr = GeofabrikReader()

            >>> subrgn_name = 'London'
            >>> dat_dir = "tests\\osm_data"

            >>> london_shp_data = gfr.read_shp_zip(
            ...     subregion_name=subrgn_name, data_dir=dat_dir, download=False, verbose=True)
            The .shp.zip file for "Greater London" is not found.

            >>> # Set `download=True`
            >>> london_shp_data = gfr.read_shp_zip(
            ...     subregion_name=subrgn_name, data_dir=dat_dir, download=True, verbose=True)
            Downloading "greater-london-latest-free.shp.zip"
                to "tests\\osm_data\\greater-london\\" ... Done.
            Extracting "tests\\osm_data\\greater-london\\greater-london-latest-free.shp.zip"
                to "tests\\osm_data\\greater-london\\greater-london-latest-free-shp\\" ... Done.
            Reading the shapefile(s) at
                "tests\\osm_data\\greater-london\\greater-london-latest-free-shp\\" ... Done.
            >>> type(london_shp_data)
            collections.OrderedDict
            >>> list(london_shp_data.keys())
            ['buildings',
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
             'waterways']

            >>> # Data of the 'railways' layer
            >>> london_shp_railways = london_shp_data['railways']
            >>> london_shp_railways.head()
               osm_id  code  ...                                        coordinates shape_type
            0   30804  6101  ...  [(0.0048644, 51.6279262), (0.0061979, 51.62926...          3
            1  101298  6103  ...  [(-0.2249906, 51.493682), (-0.2251678, 51.4945...          3
            2  101486  6103  ...  [(-0.2055497, 51.5195429), (-0.2051377, 51.519...          3
            3  101511  6101  ...  [(-0.2119027, 51.5241906), (-0.2108059, 51.523...          3
            4  282898  6103  ...  [(-0.1862586, 51.6159083), (-0.1868721, 51.613...          3
            [5 rows x 9 columns]

            >>> # Read data of the 'transport' layer only from the original .shp.zip file
            >>> # (and delete any extracts)
            >>> subrgn_layer = 'transport'

            >>> # Set `rm_extracts=True` to remove the extracts
            >>> london_shp_transport = gfr.read_shp_zip(
            ...     subregion_name=subrgn_name, layer_names=subrgn_layer, data_dir=dat_dir,
            ...     rm_extracts=True, verbose=True)
            Reading the shapefile(s) at
                "tests\\osm_data\\greater-london\\greater-london-latest-free-shp\\" ... Done.
            Deleting the extracts "tests\\osm_data\\greater-london\\greater-london-latest-free-sh...
            >>> type(london_shp_transport)
            collections.OrderedDict
            >>> list(london_shp_transport.keys())
            ['transport']
            >>> london_shp_transport_ = london_shp_transport['transport']
            >>> london_shp_transport_.head()
                 osm_id  ...  shape_type
            0   5077928  ...           5
            1   8610280  ...           5
            2  15705264  ...           5
            3  23077379  ...           5
            4  24016945  ...           5
            [5 rows x 6 columns]

            >>> # Read data of only the 'bus_stop' feature (in the 'transport' layer)
            >>> # from the original .shp.zip file (and delete any extracts)
            >>> feat_name = 'bus_stop'
            >>> london_bus_stop = gfr.read_shp_zip(
            ...     subregion_name=subrgn_name, layer_names=subrgn_layer, feature_names=feat_name,
            ...     data_dir=dat_dir, rm_extracts=True, verbose=True)
            Extracting the following layer(s):
                'transport'
                from "tests\\osm_data\\greater-london\\greater-london-latest-free.shp.zip"
                  to "tests\\osm_data\\greater-london\\greater-london-latest-free-shp\\" ... Done.
            Reading the shapefile(s) at
                "tests\\osm_data\\greater-london\\greater-london-latest-free-shp\\" ... Done.
            Deleting the extracts "tests\\osm_data\\greater-london\\greater-london-latest-free-sh...
            >>> type(london_bus_stop)
            collections.OrderedDict
            >>> list(london_bus_stop.keys())
            ['transport']

            >>> fclass = london_bus_stop['transport'].fclass.unique()
            >>> fclass
            array(['bus_stop'], dtype=object)

            >>> # Read multiple features of multiple layers
            >>> # (and delete both the original .shp.zip file and extracts)
            >>> subrgn_layers = ['traffic', 'roads']
            >>> feat_names = ['parking', 'trunk']
            >>> london_shp_tra_roa_par_tru = gfr.read_shp_zip(
            ...     subregion_name=subrgn_name, layer_names=subrgn_layers, feature_names=feat_names,
            ...     data_dir=dat_dir, rm_extracts=True, rm_shp_zip=True, verbose=True)
            Extracting the following layer(s):
                'traffic'
                'roads'
                from "tests\\osm_data\\greater-london\\greater-london-latest-free.shp.zip"
                  to "tests\\osm_data\\greater-london\\greater-london-latest-free-shp\\" ... Done.
            Reading the shapefile(s) at
                "tests\\osm_data\\greater-london\\greater-london-latest-free-shp\\" ... Done.
            Deleting the extracts "tests\\osm_data\\greater-london\\greater-london-latest-free-sh...
            Deleting "tests\\osm_data\\greater-london\\greater-london-latest-free.shp.zip" ... Done.
            >>> type(london_shp_tra_roa_par_tru)
            collections.OrderedDict
            >>> list(london_shp_tra_roa_par_tru.keys())
            ['traffic', 'roads']

            >>> # Data of the 'traffic' layer
            >>> london_shp_tra_roa_par_tru['traffic'].head()
                osm_id  code  ...                                        coordinates shape_type
            0  2956081  5260  ...  [(-0.0218269, 51.4369515), (-0.020097, 51.4372...          5
            1  2956183  5260  ...  [(-0.0224697, 51.4452646), (-0.0223272, 51.445...          5
            2  2956184  5260  ...  [(-0.0186703, 51.444221), (-0.0185442, 51.4447...          5
            3  2956185  5260  ...  [(-0.0189846, 51.4481958), (-0.0189417, 51.448...          5
            4  2956473  5260  ...  [(-0.0059602, 51.4579088), (-0.0058695, 51.457...          5
            [5 rows x 6 columns]

            >>> # Data of the 'roads' layer
            >>> london_shp_tra_roa_par_tru['roads'].head()
               osm_id  code  ...                                        coordinates shape_type
            7    1200  5112  ...  [(-0.2916285, 51.5160418), (-0.2915517, 51.516...          3
            8    1201  5112  ...  [(-0.2925582, 51.5300857), (-0.2925916, 51.529...          3
            9    1202  5112  ...  [(-0.2230893, 51.5735075), (-0.2228416, 51.573...          3
            10   1203  5112  ...  [(-0.139105, 51.6101568), (-0.1395372, 51.6100...          3
            11   1208  5112  ...  [(-0.1176027, 51.6124616), (-0.1169584, 51.612...          3
            [5 rows x 12 columns]

            >>> # Delete the example data and the test data directory
            >>> delete_dir(dat_dir, verbose=True)
            To delete the directory "tests\\osm_data\\" (Not empty)
            ? [No]|Yes: yes
            Deleting "tests\\osm_data\\" ... Done.
        """

        shp_data = super().read_shp_zip(
            subregion_name=subregion_name, layer_names=layer_names, feature_names=feature_names,
            data_dir=data_dir, update=update, download=download, pickle_it=pickle_it,
            ret_pickle_path=ret_pickle_path, rm_extracts=rm_extracts, rm_shp_zip=rm_shp_zip,
            verbose=verbose, **kwargs)

        return shp_data
