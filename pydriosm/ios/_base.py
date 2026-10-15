"""
Base class.
"""

import ast
import gc
import itertools

import numpy as np
import shapely.wkb
import sqlalchemy
from pyhelpers._cache import _print_failure_message
from pyhelpers.dbms import PostgreSQL
from pyhelpers.ops import confirmed
from pyhelpers.text import find_similar_str

from pydriosm.downloader._wrapper import Downloader
from pydriosm.ios.utils import get_default_layer_name, make_data_items, preprocess_osm_layer, \
    validate_schema_names, validate_table_name
from pydriosm.reader._wrapper import Reader


class BaseIOS(PostgreSQL):
    """
    Implement storage I/O of `OpenStreetMap <https://www.openstreetmap.org/>`_ data
    with `PostgreSQL`_.

    .. _`PostgreSQL`: https://www.postgresql.org/

    This class provides high-level database operations for OpenStreetMap data extracts,
    integrating PostgreSQL storage with custom reader and downloader utilities.
    """

    #: Specify a `data-type <https://www.postgresql.org/docs/current/datatype.html>`_
    #: dictionary for data or columns corresponding to
    #: `Pandas <https://pandas.pydata.org/docs/user_guide/basics.html#basics-dtypes>`_.
    DATA_TYPES: dict = {
        'text': str,
        'bigint': np.int64,
        'json': str,
    }

    #: Names of the data sources.
    DATA_SOURCES: list = ['Geofabrik', 'BBBike']

    def __init__(self, host=None, port=None, username=None, password=None, database_name=None,
                 data_source='Geofabrik', max_tmpfile_size=None, data_dir=None, **kwargs):
        """
        Initialize a base OpenStreetMap I/O handler for PostgreSQL.

        :param host: Host name or address of a PostgreSQL server, e.g. ``'localhost'``
            or ``'127.0.0.1'``. When ``host=None`` (default), it initializes as ``'localhost'``.
        :type host: str | None
        :param port: Listening port used by PostgreSQL. When ``port=None`` (default),
            it initializes as ``5432``.
        :type port: int | None
        :param username: Username for the PostgreSQL server. When ``username=None`` (default),
            it initializes as ``'postgres'``.
        :type username: str | None
        :param password: User password. When ``password=None`` (default), manual password entry
            is required to connect to the PostgreSQL server.
        :type password: str | int | None
        :param database_name: Name of a database. When ``database_name=None`` (default),
            it initializes as ``'postgres'``.
        :type database_name: str | None
        :param confirm_db_creation: Whether to prompt for confirmation
            before creating a new database. Defaults to ``False``.
        :type confirm_db_creation: bool
        :param data_source: Name of data source. Valid options include ``'Geofabrik'``
            and ``'BBBike'``. Defaults to ``'Geofabrik'``.
        :type data_source: str
        :param max_tmpfile_size: Maximum temporary file size setting for GDAL configurations.
            Defaults to ``None``.
        :type max_tmpfile_size: int | None
        :param data_dir: Directory where data files are located or saved. When ``data_dir=None``,
            it falls back to the default download directory of the downloader.
        :type data_dir: str | None
        :param kwargs: Optional parameters passed to ``pyhelpers.sql.PostgreSQL``.

        :ivar str data_source: name of data sources, options include ``{'Geofabrik', 'BBBike'}``

        .. _`pyhelpers.settings.gdal_configurations()`:
            https://pyhelpers.readthedocs.io/en/latest/_generated/
            pyhelpers.settings.gdal_configurations.html
        .. _`pyhelpers.sql.PostgreSQL`:
            https://pyhelpers.readthedocs.io/en/latest/_generated/pyhelpers.sql.PostgreSQL.html

        **Examples**::

            >>> from pydriosm.ios._base import BaseIOS
            >>> osmdb = BaseIOS(database_name='osmdb_test', verbose=True)
            Password (postgres@localhost:5432): ***
            Creating a database: "osmdb_test" ... Done.
            Connecting postgres:***@localhost:5432/osmdb_test ... Successfully.

            >>> osmdb.data_source
            'Geofabrik'
            >>> type(osmdb.downloader)
            pydriosm.downloader.GeofabrikDownloader
            >>> type(osmdb.reader)
            pydriosm.reader.GeofabrikReader

            >>> # Change the data source
            >>> osmdb.data_source = 'BBBike'
            >>> type(osmdb.downloader)
            pydriosm.downloader.BBBikeDownloader
            >>> type(osmdb.reader)
            pydriosm.reader.BBBikeReader

            >>> # Delete the database 'osmdb_test'
            >>> osmdb.drop_database(verbose=True)
            Drop the database "osmdb_test" from postgres:***@localhost:5432?
             [No]|Yes: yes
            Dropping "osmdb_test" ... Done.
        """

        self.data_source = find_similar_str(data_source, self.DATA_SOURCES)

        super().__init__(
            host=host,
            port=port,
            username=username,
            password=password,
            database_name=database_name,
            **kwargs
        )

        self.data_dir = data_dir
        setattr(self, 'data_dir', self.downloader.download_dir)

        self.max_tmpfile_size = max_tmpfile_size
        setattr(self, 'max_tmpfile_size', self.reader.max_tmpfile_size)

    @property
    def downloader(self):
        """
        Instance of downloader corresponding to the configured data source.

        :return: An instance of either :class:`~pydriosm.downloader.GeofabrikDownloader` or
            :class:`~pydriosm.downloader.BBBikeDownloader`, depending on the specified
            ``data_source`` for creating an instance of the :class:`~pydriosm.ios.PostgresOSM`
            class.
        :rtype: pydriosm.downloader.GeofabrikDownloader | pydriosm.downloader.BBBikeDownloader

        **Examples**::

            >>> from pydriosm.ios._base import BaseIOS

            >>> osmdb = BaseIOS(database_name='osmdb_test', verbose=True)
            Password (postgres@localhost:5432): ***
            Creating a database: "osmdb_test" ... Done.
            Connecting postgres:***@localhost:5432/osmdb_test ... Successfully.

            >>> osmdb.data_source
            'Geofabrik'
            >>> type(osmdb.downloader)
            pydriosm.downloader.GeofabrikDownloader

            >>> # Change the data source
            >>> osmdb.data_source = 'BBBike'
            >>> type(osmdb.downloader)
            pydriosm.downloader.BBBikeDownloader

            >>> # Delete the database 'osmdb_test'
            >>> osmdb.drop_database(verbose=True)
            To drop the database "osmdb_test" from postgres:***@localhost:5432
            ? [No]|Yes: yes
            Dropping "osmdb_test" ... Done.
        """

        return Downloader(data_source=self.data_source, download_dir=self.data_dir)

    def get_downloader(self, *args, **kwargs):
        """
        Create a custom downloader instance with additional arguments.

        :param args: Positional arguments passed to the downloader constructor.
        :param kwargs: Keyword arguments passed to the downloader constructor.
        :return: Downloader instance configured with custom arguments.
        :rtype: pydriosm.downloader.GeofabrikDownloader | pydriosm.downloader.BBBikeDownloader
        """

        return Downloader(data_source=self.data_source, download_dir=self.data_dir, *args, **kwargs)

    @property
    def reader(self):
        """
        Instance of reader corresponding to the configured data source.

        :return: An instance of either :class:`~pydriosm.reader.GeofabrikReader` or
            :class:`~pydriosm.reader.BBBikeReader`, depending on the specified ``data_source``
            for creating an instance of the :class:`~pydriosm.ios.PostgresOSM` class.
        :rtype: pydriosm.reader.GeofabrikReader | pydriosm.reader.BBBikeReader

        **Examples**::

            >>> from pydriosm.ios._base import BaseIOS

            >>> osmdb = BaseIOS(database_name='osmdb_test', verbose=True)
            Password (postgres@localhost:5432): ***
            Creating a database: "osmdb_test" ... Done.
            Connecting postgres:***@localhost:5432/osmdb_test ... Successfully.

            >>> type(osmdb.reader)
            pydriosm.reader.GeofabrikReader

            >>> # Change the data source
            >>> osmdb.data_source = 'BBBike'
            >>> type(osmdb.reader)
            pydriosm.reader.BBBikeReader

            >>> # Delete the database 'osmdb_test'
            >>> osmdb.drop_database(verbose=True)
            To drop the database "osmdb_test" from postgres:***@localhost:5432
            ? [No]|Yes: yes
            Dropping "osmdb_test" ... Done.
        """

        return Reader(
            data_source=self.data_source,
            data_dir=self.downloader.download_dir,
            max_tmpfile_size=self.max_tmpfile_size
        )

    def get_reader(self, **kwargs):
        """
        Create a custom reader instance with additional keyword arguments.

        :param kwargs: Keyword arguments passed to the reader constructor.
        :return: Reader instance configured with custom arguments.
        :rtype: pydriosm.reader.GeofabrikReader | pydriosm.reader.BBBikeReader
        """

        return Reader(
            data_source=self.data_source,
            data_dir=self.downloader.download_dir,
            max_tmpfile_size=self.max_tmpfile_size,
            **kwargs,
        )

    @property
    def name(self):
        """
        Name of the data source of the active downloader.

        **Examples**::

            >>> from pydriosm.ios._base import BaseIOS

            >>> osmdb = BaseIOS(database_name='osmdb_test', verbose=True)
            Password (postgres@localhost:5432): ***
            Creating a database: "osmdb_test" ... Done.
            Connecting postgres:***@localhost:5432/osmdb_test ... Successfully.

            >>> osmdb.data_source
            'Geofabrik'
            >>> osmdb.name
            'Geofabrik OpenStreetMap data extracts'

            >>> # Change the data source
            >>> osmdb.data_source = 'BBBike'
            >>> osmdb.name
            'BBBike exports of OpenStreetMap data'

            >>> # Delete the database 'osmdb_test'
            >>> osmdb.drop_database(verbose=True)
            To drop the database "osmdb_test" from postgres:***@localhost:5432
            ? [No]|Yes: yes
            Dropping "osmdb_test" ... Done.
        """

        return self.downloader.NAME

    @property
    def long_name(self):
        """
        Full descriptive name of the active downloader.

        **Examples**::

            >>> from pydriosm.ios._base import BaseIOS

            >>> osmdb = BaseIOS(database_name='osmdb_test')
            Password (postgres@localhost:5432): ***
            Creating a database: "osmdb_test" ... Done.
            Connecting postgres:***@localhost:5432/osmdb_test ... Successfully.

            >>> osmdb.data_source
            'Geofabrik'
            >>> osmdb.long_name
            'Geofabrik OpenStreetMap data extracts'

            >>> # Change the data source
            >>> osmdb.data_source = 'BBBike'
            >>> osmdb.long_name
            'BBBike exports of OpenStreetMap data'

            >>> # Delete the database 'osmdb_test'
            >>> osmdb.drop_database(verbose=True)
            To drop the database "osmdb_test" from postgres:***@localhost:5432
            ? [No]|Yes: yes
            Dropping "osmdb_test" ... Done.
        """

        return self.downloader.LONG_NAME

    @property
    def url(self):
        """
        Homepage URL of the active downloader.

        **Examples**::

            >>> from pydriosm.ios._base import BaseIOS

            >>> osmdb = BaseIOS(database_name='osmdb_test')
            Password (postgres@localhost:5432): ***
            Creating a database: "osmdb_test" ... Done.
            Connecting postgres:***@localhost:5432/osmdb_test ... Successfully.

            >>> osmdb.url
            'https://download.geofabrik.de/'

            >>> # Change the data source
            >>> osmdb.data_source = 'BBBike'
            >>> osmdb.url
            'https://download.bbbike.org/osm/bbbike/'

            >>> # Delete the database 'osmdb_test'
            >>> osmdb.drop_database(verbose=True)
            To drop the database "osmdb_test" from postgres:***@localhost:5432
            ? [No]|Yes: yes
            Dropping "osmdb_test" ... Done.
        """

        return self.downloader.URL

    def get_table_name(self, subregion_name, table_named_as_subregion=False):
        """
        Get the default table name for a specific geographic (sub)region.

        :param subregion_name: name of a geographic (sub)region, which acts as a table name
        :type subregion_name: str
        :param table_named_as_subregion: whether to use subregion name as table name,
            defaults to ``False``
        :type table_named_as_subregion: bool
        :return: default table name for storing the subregion data into the database
        :rtype: str

        **Examples**::

            >>> from pydriosm.ios._base import BaseIOS

            >>> osmdb = BaseIOS(database_name='osmdb_test')
            Password (postgres@localhost:5432): ***
            Creating a database: "osmdb_test" ... Done.
            Connecting postgres:***@localhost:5432/osmdb_test ... Successfully.

            >>> subrgn_name = 'london'

            >>> tbl_name = osmdb.get_table_name(subrgn_name)
            >>> tbl_name
            'london'

            >>> tbl_name = osmdb.get_table_name(subrgn_name, table_named_as_subregion=True)
            >>> tbl_name
            'Greater London'

            >>> # Change the data source
            >>> osmdb.data_source = 'BBBike'
            >>> tbl_name = osmdb.get_table_name(subrgn_name, table_named_as_subregion=True)
            >>> tbl_name
            'London'

            >>> # Delete the database 'osmdb_test'
            >>> osmdb.drop_database(verbose=True)
            To drop the database "osmdb_test" from postgres:***@localhost:5432
            ? [No]|Yes: yes
            Dropping "osmdb_test" ... Done.

        .. note::

            In the examples above, the default data source is 'Geofabrik'.
            Changing it to 'BBBike', the function may produce a different output for the same input,
            as a geographic (sub)region that is included in one data source may not always be
            available from the other.
        """

        if table_named_as_subregion:
            subregion_name_ = self.downloader.validate_subregion_name(subregion_name)
        else:
            subregion_name_ = subregion_name

        table_name = validate_table_name(subregion_name_)

        return table_name

    def subregion_table_exists(self, subregion_name, layer_name, table_named_as_subregion=False,
                               schema_named_as_layer=False):
        """
        Check if a table (for a geographic (sub)region) exists.

        :param subregion_name: name of a geographic (sub)region, which acts as a table name
        :type subregion_name: str
        :param layer_name: name of an OSM layer (e.g. 'points', 'railways', ...),
            which acts as a schema name
        :type layer_name: str
        :param table_named_as_subregion: whether to use subregion name as table name,
            defaults to ``False``
        :type table_named_as_subregion: bool
        :param schema_named_as_layer: whether a schema is named as a layer name.
            Defaults to ``False``.
        :type schema_named_as_layer: bool
        :return: ``True`` if the table exists, ``False`` otherwise
        :rtype: bool

        **Examples**::

            >>> from pydriosm.ios._base import BaseIOS

            >>> osmdb = BaseIOS(database_name='osmdb_test')
            Password (postgres@localhost:5432): ***
            Creating a database: "osmdb_test" ... Done.
            Connecting postgres:***@localhost:5432/osmdb_test ... Successfully.

            >>> subrgn_name = 'London'
            >>> lyr_name = 'pt'

            >>> # Check whether the table "pt"."london" is available
            >>> osmdb.subregion_table_exists(subregion_name=subrgn_name, layer_name=lyr_name)
            False

            >>> # Check whether the table "points"."greater_london" is available
            >>> osmdb.subregion_table_exists(
            ...     subregion_name=subrgn_name, layer_name=lyr_name, table_named_as_subregion=True,
            ...     schema_named_as_layer=True)
            False

            >>> # Delete the database 'osmdb_test'
            >>> osmdb.drop_database(verbose=True)
            To drop the database "osmdb_test" from postgres:***@localhost:5432
            ? [No]|Yes: yes
            Dropping "osmdb_test" ... Done.
        """

        table_name_ = self.get_table_name(subregion_name, table_named_as_subregion)
        schema_name_ = get_default_layer_name(layer_name) if schema_named_as_layer else layer_name

        res = self.table_exists(table_name=table_name_, schema_name=schema_name_)

        return res

    def get_table_column_info(self, subregion_name, layer_name, as_dict=False,
                              table_named_as_subregion=False, schema_named_as_layer=False):
        # noinspection PyUnresolvedReferences,shadowing-names
        """
        Get information about columns of a specific schema and table data
        for a geographic (sub)region.

        :param subregion_name: name of a geographic (sub)region, which acts as a table name.
        :type subregion_name: str
        :param layer_name: name of an OSM layer (e.g. 'points', 'railways', ...),
            which acts as a schema name.
        :type layer_name: str
        :param as_dict: whether to return the column information as a dictionary.
            Defaults to ``True``.
        :type as_dict: bool
        :param table_named_as_subregion: whether to use subregion name as table name,
            defaults to ``False``
        :type table_named_as_subregion: bool
        :param schema_named_as_layer: whether a schema is named as a layer name.
            Defaults to ``False``.
        :type schema_named_as_layer: bool
        :return: information about each column of the given table
        :rtype: pandas.DataFrame | dict

        **Examples**::

            >>> from pydriosm.ios._base import BaseIOS

            >>> osmdb = BaseIOS(database_name='osmdb_test', verbose=True)
            Password (postgres@localhost:5432): ***
            Creating a database: "osmdb_test" ... Done.
            Connecting postgres:***@localhost:5432/osmdb_test ... Successfully.

            >>> subregion_name = 'London'
            >>> layer_name = 'points'

            >>> # Take for example a table named "points"."London"
            >>> tbl_col_info = osmdb.get_table_column_info(subregion_name, layer_name)
            >>> type(tbl_col_info)
            pandas.DataFrame
            >>> tbl_col_info.index.to_list()[:5]
            ['table_catalog',
             'table_schema',
             'table_name',
             'column_name',
             'ordinal_position']

            >>> # Another example of a table named "points"."Greater London"
            >>> tbl_col_info_dict = osmdb.get_table_column_info(
            ...     subregion_name=subregion_name,
            ...     layer_name=layer_name,
            ...     as_dict=True,
            ...     table_named_as_subregion=True,
            ...     schema_named_as_layer=True
            ... )
            >>> type(tbl_col_info_dict)
            dict
            >>> list(tbl_col_info_dict)[:5]
            ['table_catalog',
             'table_schema',
             'table_name',
             'column_name',
             'ordinal_position']

            >>> # Delete the database 'osmdb_test'
            >>> osmdb.drop_database(verbose=True)
            Drop the database "osmdb_test" from postgres:***@localhost:5432?
             [No]|Yes: yes
            Dropping "osmdb_test" ... Done.
        """

        table_name_ = self.get_table_name(subregion_name, table_named_as_subregion)
        schema_name_ = get_default_layer_name(layer_name) if schema_named_as_layer else layer_name

        column_info = self.get_column_info(
            table_name=table_name_,
            schema_name=schema_name_,
            as_dict=as_dict
        )

        return column_info

    def import_osm_layer(self, layer_data, table_name, schema_name,
                         table_named_as_subregion=False, schema_named_as_layer=False,
                         if_exists='fail', chunk_size=None, confirmation_required=True,
                         verbose=False, raise_error=True, **kwargs):
        # noinspection PyUnresolvedReferences
        """
        Import one layer of OSM data into a table.

        :param layer_data: one layer of OSM data
        :type layer_data: pandas.DataFrame | geopandas.GeoDataFrame
        :param schema_name: name of a schema (or name of a PBF layer)
        :type schema_name: str
        :param table_name: name of a table
        :type table_name: str
        :param table_named_as_subregion: whether to use subregion name as a table name.
            Defaults to ``False``.
        :type table_named_as_subregion: bool
        :param schema_named_as_layer: whether a schema is named as a layer name.
            Defaults to ``False``.
        :type schema_named_as_layer: bool
        :param if_exists: if the table already exists.
            Valid options include ``{'replace', 'append', 'fail'}``. Defaults to ``'fail'``.
        :type if_exists: str
        :param chunk_size: the number of rows in each batch to be written at a time.
            Defaults to ``None``.
        :type chunk_size: int | None
        :param confirmation_required: whether to prompt a message for confirmation to proceed.
            Defaults to ``True``.
        :type confirmation_required: bool
        :param verbose: whether to print relevant information in console as the function runs.
            Defaults to ``False``.
        :type verbose: bool
        :param raise_error: Whether to raise the provided exception.
            If ``raise_error=False``, the error will be suppressed. Defaults to ``True``.
        :type raise_error: bool
        :param kwargs: Optional parameters of `pyhelpers.dbms.PostgreSQL.import_data`_.

        .. _`pyhelpers.dbms.PostgreSQL.import_data`:
            https://pyhelpers.readthedocs.io/en/stable/_generated/
            pyhelpers.dbms.PostgreSQL.import_data.html

        .. _pydriosm-PostgresOSM-import_osm_layer:

        **Examples**::

            >>> from pydriosm.ios._base import BaseIOS
            >>> from pyhelpers.dirs import delete_dir

            >>> osmdb = BaseIOS(database_name='osmdb_test', verbose=True)
            Password (postgres@localhost:5432): ***
            Creating a database: "osmdb_test" ... Done.
            Connecting postgres:***@localhost:5432/osmdb_test ... Successfully.

            >>> subrgn_name = 'Rutland'  # name of a subregion
            >>> dat_dir = "tests/osm_data"  # name of a data directory where the subregion data is

        *Example 1* - Import data of the 'points' layer of a PBF file::

            >>> # First, read the PBF data of Rutland (from Geofabrik free download server)
            >>> # (If the data file is not available, it'll be downloaded by confirmation)
            >>> raw_pbf = osmdb.reader.read_pbf(
            ...     subrgn_name, data_dir=dat_dir, download=True, verbose=True)
            Downloading "rutland-latest.osm.pbf" 100%|██████████| 1.89M/1.89M | 5.76MB/s ...
              Saving "rutland-latest.osm.pbf" to "./tests/osm_data/rutland/" ... Done.
            Reading "./tests/osm_data/rutland/rutland-latest.osm.pbf" ... Done.
            >>> type(raw_pbf)
            dict
            >>> list(raw_pbf.keys())
            ['points', 'lines', 'multilinestrings', 'multipolygons', 'other_relations']

            >>> # Get the data of 'points' layer
            >>> points_key = 'points'
            >>> raw_pbf_points = raw_pbf[points_key]
            >>> type(raw_pbf_points)
            list
            >>> type(raw_pbf_points[0])
            osgeo.ogr.Feature

            >>> # Now import the data of 'points' into the PostgreSQL server
            >>> osmdb.import_osm_layer(
            ...     layer_data=raw_pbf_points, table_name=subrgn_name, schema_name=points_key,
            ...     verbose=True)
            To import data into the table "points"."Rutland" at postgres:***@localhost:5432/osm...
            ? [No]|Yes: yes
            Creating a schema: "points" ... Done.
            Importing the data into "points"."Rutland" ... Done.

            >>> tbl_col_info = osmdb.get_table_column_info(subrgn_name, points_key)
            >>> tbl_col_info.head()
                                column_0
            table_catalog     osmdb_test
            table_schema          points
            table_name           Rutland
            column_name           points
            ordinal_position           1

            >>> # Parse the 'geometry' of the PBF data of Rutland
            >>> parsed_pbf = osmdb.reader.read_pbf(
            ...     subregion_name=subrgn_name, data_dir=dat_dir, expand=True,
            ...     parse_geometry=True, verbose=True)
            >>> type(parsed_pbf)
            dict
            >>> list(parsed_pbf.keys())
            ['points', 'lines', 'multilinestrings', 'multipolygons', 'other_relations']
            >>> # Get the parsed data of 'points' layer
            >>> parsed_pbf_points = parsed_pbf[points_key]
            >>> type(parsed_pbf_points)
            pandas.DataFrame
            >>> parsed_pbf_points.head()
                     id  ...                                         properties
            0    488658  ...  {'osm_id': '488658', 'name': 'Tickencote Inter...
            1  13883868  ...  {'osm_id': '13883868', 'name': None, 'barrier'...
            2  14049101  ...  {'osm_id': '14049101', 'name': None, 'barrier'...
            3  14558402  ...  {'osm_id': '14558402', 'name': None, 'barrier'...
            4  14558409  ...  {'osm_id': '14558409', 'name': None, 'barrier'...
            [5 rows x 3 columns]

            >>> # Import the parsed 'points' data into the PostgreSQL database
            >>> osmdb.import_osm_layer(
            ...     layer_data=parsed_pbf_points, table_name=subrgn_name, schema_name=points_key,
            ...     if_exists='replace', verbose=True)
            Import data into "points"."Rutland" at postgres:***@localhost:5432/osmdb_test?
             [No]|Yes: yes
            Importing the data ... Done.

            >>> # Get the information of the table "points"."Rutland"
            >>> tbl_col_info = osmdb.get_table_column_info(subrgn_name, points_key)
            >>> tbl_col_info.head()
                                column_0    column_1    column_2
            table_catalog     osmdb_test  osmdb_test  osmdb_test
            table_schema          points      points      points
            table_name           Rutland     Rutland     Rutland
            column_name               id    geometry  properties
            ordinal_position           1           2           3

        *Example 2* - Import data of the 'railways' layer of a GeoPackage*::

            >>> # Read the data of 'railways' layer and delete the extracts
            >>> lyr_name = 'railways'
            >>> rutland_railways_gpkg = osmdb.reader.read_gpkg(
            ...     subregion_name=subrgn_name, layer_names=lyr_name, data_dir=dat_dir,
            ...     download=True, verbose=True)
            Downloading "rutland-latest-free.gpkg.zip" 100%|██████████| 3.30M/3.30M | 3.6...
              Saving "rutland-latest-free.gpkg.zip" to "./tests/osm_data/rutland/" ... Done.
            Parsing the data ... Done.
            >>> type(rutland_railways_gpkg)
            dict
            >>> list(rutland_railways_gpkg.keys())
            ['railways']

            >>> # Get the data of 'railways' layer
            >>> rutland_railways_gpkg_ = rutland_railways_gpkg[lyr_name]
            >>> rutland_railways_gpkg_.head()
                osm_id  code  ... tunnel                                           geometry
            0  2162114  6101  ...      F  LINESTRING (-0.46449 52.71043, -0.46111 52.706...
            1  3681043  6101  ...      F  LINESTRING (-0.65312 52.57308, -0.65318 52.572...
            2  3693985  6101  ...      F  LINESTRING (-0.72203 52.69658, -0.72182 52.697...
            3  3693986  6101  ...      F  LINESTRING (-0.61731 52.61323, -0.62419 52.614...
            4  8044108  6101  ...      T  LINESTRING (-0.69782 52.62858, -0.70271 52.63395)
            [5 rows x 8 columns]

            >>> # Import the 'railways' data into the PostgreSQL database
            >>> osmdb.import_osm_layer(
            ...     rutland_railways_gpkg_, table_name=subrgn_name, schema_name=lyr_name,
            ...     verbose=True)
            Import data into "railways"."Rutland" at postgres:***@localhost:5432/osmdb_test?
             [No]|Yes: yes
            Creating a schema: "railways" ... Done.
            Importing the data ... Done.

            >>> # Get the information of the table "railways"."Rutland"
            >>> tbl_col_info = osmdb.get_table_column_info(subrgn_name, lyr_name)
            >>> tbl_col_info.head()
                                column_0    column_1  ...    column_6    column_7
            table_catalog     osmdb_test  osmdb_test  ...  osmdb_test  osmdb_test
            table_schema        railways    railways  ...    railways    railways
            table_name           Rutland     Rutland  ...     Rutland     Rutland
            column_name           osm_id        code  ...      tunnel    geometry
            ordinal_position           1           2  ...           7           8
            [5 rows x 8 columns]

        Delete the test database and downloaded data files::

            >>> # Delete the database 'osmdb_test'
            >>> osmdb.drop_database(verbose=True)
            Drop the database "osmdb_test" from postgres:***@localhost:5432?
             [No]|Yes: yes
            Dropping "osmdb_test" ... Done.

            >>> # Delete the downloaded data files
            >>> delete_dir(dat_dir, verbose=True)
            To delete the directory "./tests/osm_data/" (Not empty)
            ? [No]|Yes: yes
            Deleting "./tests/osm_data/" ... Done.
        """

        table_name_ = self.get_table_name(table_name, table_named_as_subregion)

        schema_name_ = get_default_layer_name(schema_name) if schema_named_as_layer else schema_name

        table_exists = self.table_exists(table_name=table_name_, schema_name=schema_name_)
        if table_exists and if_exists == 'fail':
            msg = [
                f'The table "{schema_name_}"."{table_name_}" already exists.',
                "Use `if_exists='replace'` or drop the table first."
            ]
            if raise_error:
                raise ValueError(f"{msg[0]} (Use `if_exists='replace'`)")
            elif verbose:
                print("\n  ".join(msg))

        else:
            lyr_dat = preprocess_osm_layer(layer_data=layer_data, layer_name=schema_name_)

            kwargs.setdefault('method', self.psql_insert_copy)

            self.import_data(
                data=lyr_dat, table_name=table_name_, schema_name=schema_name_, if_exists=if_exists,
                chunk_size=chunk_size, confirmation_required=confirmation_required,
                verbose=2 if verbose else False,
                **kwargs
            )

    def import_osm_data(self, osm_data, table_name, schema_names=None,
                        table_named_as_subregion=False, schema_named_as_layer=False,
                        if_exists='fail', force_replace=False, chunk_size=None,
                        confirmation_required=True, verbose=False, raise_error=False, **kwargs):
        # noinspection PyUnresolvedReferences
        """
        Import OSM data into a database.

        :param osm_data: OSM data of a geographic (sub)region
        :type osm_data: dict
        :param table_name: name of a table
        :type table_name: str
        :param schema_names: names of schemas for each layer of the PBF data. Defaults to ``None``;
            when ``schema_names=None``, the default layer names as schema names
        :type schema_names: list | dict | None
        :param table_named_as_subregion: whether to use subregion name as a table name,
            defaults to ``False``
        :type table_named_as_subregion: bool
        :param schema_named_as_layer: whether a schema is named as a layer name,
            defaults to ``False``
        :type schema_named_as_layer: bool
        :param if_exists: if the table already exists. Defaults to ``'fail'``;
            valid options include ``{'replace', 'append', 'fail'}``
        :type if_exists: str
        :param force_replace: whether to force to replace existing table. Defaults to ``False``
        :type force_replace: bool
        :param chunk_size: the number of rows in each batch to be written at a time,
            defaults to ``None``
        :type chunk_size: int | None
        :param confirmation_required: whether to prompt a message for confirmation to proceed,
            defaults to ``True``
        :type confirmation_required: bool
        :param verbose: whether to print relevant information in console as the function runs,
            defaults to ``False``
        :type verbose: bool
        :param raise_error: Whether to raise the provided exception.
            If ``raise_error=False`` (default), the error will not be raised.
        :type raise_error: bool
        :param kwargs: [optional] parameters of the method
            :meth:`~pydriosm.ios.PostgresOSM.import_osm_layer`

        **Examples**::

            >>> from pydriosm.ios._base import BaseIOS
            >>> from pyhelpers.dirs import delete_dir

            >>> osmdb = BaseIOS(database_name='osmdb_test', verbose=True)
            Password (postgres@localhost:5432): ***
            Creating a database: "osmdb_test" ... Done.
            Connecting postgres:***@localhost:5432/osmdb_test ... Successfully.

            >>> subregion_name = 'Rutland'  # name of a subregion
            >>> data_dir = "tests/osm_data"  # name of a data directory where subregion data is

        *Example 1* - Import data of a PBF file::

            >>> # First, read the PBF data of Rutland
            >>> # (If the data file is not available, it'll be downloaded by confirmation)
            >>> raw_rutland_pbf = osmdb.reader.read_pbf(
            ...     subregion_name, data_dir, download=True, verbose=True
            ... )
            Downloading "rutland-latest.osm.pbf" 100%|██████████| 1.94M/1.94M | 4.88MB/s ...
              Saving "rutland-latest.osm.pbf" to "tests/osm_data/rutland/" ... Done.
            Reading "tests/osm_data/rutland/rutland-latest.osm.pbf" ... Done.
            >>> type(raw_rutland_pbf)
            dict
            >>> list(raw_rutland_pbf)
            ['points', 'lines', 'multilinestrings', 'multipolygons', 'other_relations']

            >>> # Import all layers of the raw PBF data of Rutland
            >>> osmdb.import_osm_data(raw_rutland_pbf, table_name=subregion_name, verbose=True)
            Proceed to import data into the table "Rutland" at postgres:***@localhost:5432/osmd...
             [No]|Yes: yes
            Importing the data ...
              "points" ... Done. (6578 features)
              "lines" ... Done. (11231 features)
              "multilinestrings" ... Done. (70 features)
              "multipolygons" ... Done. (9466 features)
              "other_relations" ... Done. (33 features)

            >>> # Get parsed PBF data
            >>> parsed_rutland_pbf = osmdb.reader.read_pbf(
            ...     subregion_name=subregion_name,
            ...     data_dir=data_dir,
            ...     expand=True,
            ...     parse_geometry=True,
            ...     parse_other_tags=True,
            ...     verbose=True
            ... )
            Parsing "tests/osm_data/rutland/rutland-latest.osm.pbf" ... Done.
            >>> type(parsed_rutland_pbf)
            dict
            >>> list(parsed_rutland_pbf)
            ['points', 'lines', 'multilinestrings', 'multipolygons', 'other_relations']

            >>> # Import data of selected layers into specific schemas
            >>> schemas = {
            ...     "schema_0": 'lines',
            ...     "schema_1": 'points',
            ...     "schema_2": 'multipolygons',
            ... }
            >>> osmdb.import_osm_data(parsed_rutland_pbf, subregion_name, schemas, verbose=True)
            Proceed to import data into the table "Rutland" at postgres:***@localhost:5432/osmd...
             [No]|Yes: yes
            Importing the data ...
              "schema_0" ... Done. (11231 features)
              "schema_1" ... Done. (6578 features)
              "schema_2" ... Done. (9466 features)

            >>> # To drop the schemas "schema_0", "schema_1" and "schema_2"
            >>> osmdb.drop_schema(schemas, confirmation_required=False, verbose=True)
            Dropping the following schemas from postgres:***@localhost:5432/osmdb_test:
              "schema_0" ... Done.
              "schema_1" ... Done.
              "schema_2" ... Done.

        *Example 2* - Import OSM GeoPackage data::

            >>> # Read GeoPackage data of Rutland
            >>> rutland_gpkg = osmdb.reader.read_gpkg(
            ...     subregion_name=subregion_name,
            ...     data_dir=data_dir,
            ...     download=True,
            ...     verbose=True
            ... )
            Downloading "rutland-latest-free.gpkg.zip" 100%|██████████| 3.32M/3.32M | 5.0...
              Saving "rutland-latest-free.gpkg.zip" to "tests/osm_data/rutland/" ... Done.
            Parsing the data ... Done.
            >>> type(rutland_gpkg)
            dict
            >>> list(rutland_gpkg)
            ['traffic',
             'places',
             'pois',
             'transport',
             'pofw',
             'natural',
             'railways',
             'roads',
             'waterways',
             'protected_areas',
             'water',
             'landuse',
             'buildings',
             'adminareas']

            >>> # Import all layers of the shapefile data of Rutland
            >>> osmdb.import_osm_data(
            ...     osm_data=rutland_gpkg,
            ...     table_name=subregion_name,
            ...     verbose=True
            ... )
            Proceed to import data into table "Rutland" at postgres:***@localhost:5432/osmdb_test?
             [No]|Yes: yes
            Importing the data ...
              "traffic" ... Done. (589 features)
              "places" ... Done. (300 features)
              "pois" ... Done. (1107 features)
              "transport" ... Done. (65 features)
              "pofw" ... Done. (65 features)
              "natural" ... Done. (666 features)
              "railways" ... Done. (141 features)
              "roads" ... Done. (7425 features)
              "waterways" ... Done. (379 features)
              "protected_areas" ... Done. (20 features)
              "water" ... Done. (234 features)
              "landuse" ... Done. (2465 features)
              "buildings" ... Done. (5743 features)
              "adminareas" ... Done. (58 features)

        *Example 3* - Import BBBike shapefile data file of Leeds::

            >>> # Change the data source
            >>> osmdb.data_source = 'BBBike'
            >>> subregion_name = 'Leeds'

            >>> # Read shapefile data of Leeds
            >>> leeds_shp = osmdb.reader.read_shp(
            ...     subregion_name=subregion_name,
            ...     data_dir=data_dir,
            ...     download=True,
            ...     rm_extracts=True,
            ...     verbose=True
            ... )
            Downloading "Leeds.osm.shp.zip" 100%|██████████| 61.1M/61.1M | 2.33MB/s | Ela...
              Saving "Leeds.osm.shp.zip" to "tests/osm_data/leeds/" ... Done.
            Extracting "tests/osm_data/leeds/Leeds.osm.shp.zip"
              to "tests/osm_data/leeds/" ... Done.
            Reading the shapefile(s) at "tests/osm_data/leeds/Leeds-shp/shape/" ... Done.
            Deleting the extracts "tests/osm_data/leeds/Leeds-shp/" ... Done.
            >>> type(leeds_shp)
            dict
            >>> list(leeds_shp)
            ['buildings',
             'landuse',
             'natural',
             'places',
             'points',
             'railways',
             'roads',
             'waterways']

            >>> # Import all layers of the shapefile data of Leeds
            >>> osmdb.import_osm_data(osm_data=leeds_shp, table_name=subregion_name, verbose=True)
            Proceed to import data into table "Leeds" at postgres:***@localhost:5432/osmdb_test?
             [No]|Yes: yes
            Importing the data ...
              "buildings" ... Done. (465126 features)
              "landuse" ... Done. (23742 features)
              "natural" ... Done. (8087 features)
              "places" ... Done. (916 features)
              "points" ... Done. (50399 features)
              "railways" ... Done. (2909 features)
              "roads" ... Done. (158803 features)
              "waterways" ... Done. (3629 features)

        Delete the test database and downloaded data files::

            >>> # Delete the database 'osmdb_test'
            >>> osmdb.drop_database(verbose=True)
            Drop the database "osmdb_test" from postgres:***@localhost:5432?
             [No]|Yes: yes
            Dropping "osmdb_test" ... Done.

            >>> # Delete the downloaded data files
            >>> delete_dir(data_dir, verbose=True)
            Confirm deletion of the directory "tests/osm_data/" (Not empty)?
             [No]|Yes: yes
            Deleting "tests/osm_data/" ... Done.
        """

        data_items = make_data_items(osm_data=osm_data, schema_names=schema_names)

        table_name_ = self.get_table_name(
            subregion_name=table_name, table_named_as_subregion=table_named_as_subregion)
        tbl_name = f'"{table_name_}"'

        if not confirmed(f"Proceed to import data into the table {tbl_name} at {self.address}?\n",
                         confirmation_required=confirmation_required):
            if verbose:
                print("Canceled.")
            return None

        if verbose:
            status_msg = "Importing the data"
            if not confirmation_required:
                status_msg += f" into the table {tbl_name}"
                if verbose != 2:
                    status_msg += f" at {self.address}"
            print(status_msg, end=" ... \n")

        for geom_type, osm_layer in data_items:
            if verbose:
                print(f'  "{geom_type}"', end=" ... ", flush=True)

                if osm_layer is None or len(osm_layer) == 0:
                    print("Skipped (Empty).")
                    continue

            try:
                self.import_osm_layer(
                    layer_data=osm_layer, table_name=table_name_, schema_name=geom_type,
                    table_named_as_subregion=table_named_as_subregion,
                    schema_named_as_layer=schema_named_as_layer,
                    if_exists=if_exists, force_replace=force_replace, chunk_size=chunk_size,
                    confirmation_required=False, verbose=False, raise_error=True,
                    **kwargs
                )

                if verbose:
                    print(f"Done. ({len(osm_layer)} features)")

            except Exception as e:
                _print_failure_message(
                    e, prefix="Failed.", verbose=verbose, raise_error=raise_error)

            del osm_layer
            gc.collect()
        return None

    @staticmethod
    def _decode_layer_data(data, possible_col_names):
        """
        Decode encoded column data in a layer DataFrame.

        This method parses string-encoded Python literals or binary WKB geometries
        within the specified columns of the given DataFrame.

        :param data: Layer data containing spatial or attribute columns.
        :type data: pandas.DataFrame
        :param possible_col_names: Sequence of column names to attempt decoding on.
        :type possible_col_names: list | tuple | set
        :return: Decoded DataFrame with transformed columns.
        :rtype: pandas.DataFrame
        """

        col_names = [x for x in possible_col_names if x in data.columns]

        for col_name in col_names:
            try:
                data[col_name] = data[col_name].map(ast.literal_eval)
            except (SyntaxError, TypeError, ValueError, shapely.errors.GEOSException):
                pass

            try:
                data[col_name] = data[col_name].map(shapely.wkb.loads)
            except (SyntaxError, TypeError, ValueError, shapely.errors.GEOSException):
                pass

        return data

    def _get_column_dtypes(self, table_name_, schema_name_):
        """
        Retrieve mapped Pandas data types for columns in a database table.

        This method queries column information for the specified schema and table name, then maps
        PostgreSQL data types to corresponding Pandas data types.

        :param table_name_: Name of the database table.
        :type table_name_: str
        :param schema_name_: Name of the database schema.
        :type schema_name_: str
        :return: Dictionary mapping column names to Pandas data types.
        :rtype: dict
        """

        column_info_table = self.get_column_info(table_name=table_name_, schema_name=schema_name_)

        dtypes = column_info_table['data_type']
        return dict(
            zip(column_info_table['column_name'], map(self.DATA_TYPES.get, dtypes))
        )

    def _resolve_schema_and_table_names(self, subregion_names, schema_names=None,
                                        table_named_as_subregion=False,
                                        schema_named_as_layer=False):
        """
        Validate and resolve existing database schemas and table names for subregions.

        This method checks database metadata to determine existing schema and table pairs
        corresponding to the requested subregions.

        :param subregion_names: Name or list of names of subregions.
        :type subregion_names: str | list
        :param schema_names: Schema names to check. If ``None``, inspects all non-system schemas.
        :type schema_names: str | list | None
        :param table_named_as_subregion: Whether tables are named directly after subregions.
            Defaults to ``False``.
        :type table_named_as_subregion: bool
        :param schema_named_as_layer: Whether schemas are named directly after layers.
            Defaults to ``False``.
        :type schema_named_as_layer: bool
        :return: Tuple containing sorted lists of existing schema names and validated table names.
        :rtype: tuple[list, list]
        """

        table_names = self.reader.validate_dtype(subregion_names)
        table_names_ = sorted(
            [self.get_table_name(x, table_named_as_subregion) for x in table_names]
        )

        # Validate the input `schema_names`
        if schema_names is None:
            inspector = sqlalchemy.inspection.inspect(self.engine)
            # noinspection PyUnresolvedReferences
            schema_names_ = [
                x for x in inspector.get_schema_names()
                if x not in {'public', 'information_schema', 'pg_catalog'}
            ]
        else:
            schema_names_ = validate_schema_names(
                schema_names=schema_names,
                schema_named_as_layer=schema_named_as_layer
            )

        if schema_names_:
            prod = itertools.product(schema_names_, table_names_)
            existing_schema_names_ = set(
                schema_name
                for schema_name, table_name in prod
                if self.subregion_table_exists(
                    subregion_name=table_name,
                    layer_name=schema_name,
                    table_named_as_subregion=table_named_as_subregion,
                    schema_named_as_layer=schema_named_as_layer
                )
            )
            existing_schema_names_ = list(existing_schema_names_)
        else:
            existing_schema_names_ = schema_names_

        return existing_schema_names_, table_names_

    def _build_drop_confirmation_prompt(self, existing_schema_names_, table_names_):
        """
        Construct table combination pairs and a user confirmation message for deletion.

        This method formats the affected schemas and tables into a human-readable prompt string.

        :param existing_schema_names_: List of existing database schema names.
        :type existing_schema_names_: list
        :param table_names_: List of database table names.
        :type table_names_: list
        :return: Tuple containing the product list of schema-table pairs and the prompt string.
        :rtype: tuple[list[tuple[str, str]], str]
        """

        # existing_schema_names_.sort()
        _, schema_pl, prt_schema, _ = self._msg_for_multi_items(
            existing_schema_names_, desc='schema', fmt='"{}"', indent=4)
        _, tbl_pl, prt_tbl, _ = self._msg_for_multi_items(
            table_names_, desc='table', fmt='"{}"', indent=4)

        table_list = list(
            itertools.product(existing_schema_names_, table_names_)
        )

        if len(table_list) == 1:
            confirmation_prompt = (
                f"Proceed to drop {tbl_pl} {prt_schema}.{prt_tbl} from {self.address}?\n"
            )
        else:
            confirmation_prompt = (
                f'Proceed to drop {tbl_pl} from {self.address}: {prt_tbl}\n'
                f'  under the {schema_pl}: {prt_schema}\n?'
            )

        return table_list, confirmation_prompt

    def _drop_subregion_table(self, connection, schema, table, verbose=False, raise_error=True):
        """
        Drop a specific subregion database table within an active connection context.

        This method executes a ``DROP TABLE IF EXISTS ... CASCADE`` query
        for the specified schema and table.

        :param connection: Active SQLAlchemy database connection instance.
        :type connection: sqlalchemy.engine.Connection
        :param schema: Name of the schema containing the table.
        :type schema: str
        :param table: Name of the table to drop.
        :type table: str
        :param verbose: Whether to print progress messages. Defaults to ``False``.
        :type verbose: bool | int
        :param raise_error: Whether to raise exceptions upon query failure. Defaults to ``True``.
        :type raise_error: bool
        """

        schema_table = f'"{schema}"."{table}"'

        if self.table_exists(table_name=table, schema_name=schema):
            if verbose:
                print(f"  {schema_table}", end=" ... ")

            try:
                query = f"DROP TABLE IF EXISTS {schema_table} CASCADE;"
                connection.execute(sqlalchemy.text(query))
                if verbose:
                    print("Done.")
            except Exception as e:
                _print_failure_message(
                    e, "Failed. Error:", verbose=verbose, raise_error=raise_error
                )

        else:  # The table doesn't exist
            if verbose == 2:
                print(f"  {schema_table} does not exist.")

    def drop_subregion_tables(self, subregion_names, schema_names=None,
                              table_named_as_subregion=False, schema_named_as_layer=False,
                              confirmation_required=True, verbose=False, raise_error=False):
        """
        Delete specified subregion tables across schemas from the connected database.

        This method resolves target schema and table combinations,
        prompts for user confirmation if required, and
        drops matching tables within an explicit transaction.

        :param subregion_names: Subregion name or sequence of subregion names.
        :type subregion_names: str | list
        :param schema_names: Schema names corresponding to layers. If ``None``, defaults
            to layer names as schemas.
        :type schema_names: str | list | None
        :param table_named_as_subregion: Whether tables are named as subregions.
            Defaults to ``False``.
        :type table_named_as_subregion: bool
        :param schema_named_as_layer: Whether schemas are named as layers. Defaults to ``False``.
        :type schema_named_as_layer: bool
        :param confirmation_required: Whether to prompt for confirmation before dropping.
            Defaults to ``True``.
        :type confirmation_required: bool
        :param verbose: Verbosity level for console output. Defaults to ``False``.
        :type verbose: bool | int
        :param raise_error: Whether to raise exceptions on failure. Defaults to ``False``.
        :type raise_error: bool

        .. seealso::

            Examples of the :meth:`PostgresOSM.drop_subregion_tables
            <pydriosm.ios.PostgresOSM.drop_subregion_tables>` method.
        """

        existing_schema_names_, table_names_ = self._resolve_schema_and_table_names(
            subregion_names=subregion_names,
            schema_names=schema_names,
            table_named_as_subregion=table_named_as_subregion,
            schema_named_as_layer=schema_named_as_layer
        )

        if not existing_schema_names_:
            print("None of the data exists.")

        else:
            table_list, confirm_msg = self._build_drop_confirmation_prompt(
                existing_schema_names_=existing_schema_names_, table_names_=table_names_
            )

            if confirmed(confirm_msg, confirmation_required=confirmation_required):
                if_tables_exist = any(
                    self.table_exists(table_name=table, schema_name=schema)
                    for schema, table in table_list)

                if if_tables_exist:
                    if verbose:
                        drop_msg = "table" if len(table_list) == 1 else "tables"
                        print(f"Dropping the {drop_msg} ... ")

                    with self.engine.begin() as connection:
                        for schema, table in table_list:
                            self._drop_subregion_table(
                                connection=connection,
                                schema=schema,
                                table=table,
                                verbose=verbose,
                                raise_error=raise_error
                            )
