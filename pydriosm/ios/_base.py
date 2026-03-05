"""
Base class.
"""

import ast
import gc
import itertools

import numpy as np
import shapely.wkt
import sqlalchemy
from pyhelpers._cache import _print_failure_message
from pyhelpers.dbms import PostgreSQL
from pyhelpers.ops import confirmed
from pyhelpers.text import find_similar_str

from pydriosm.downloader._wrapper import Downloader
from pydriosm.ios.utils import get_default_layer_name, make_data_items, preprocess_pdf_layer, \
    validate_schema_names, validate_table_name
from pydriosm.reader._wrapper import Reader


class BaseIOS(PostgreSQL):
    """
    Implement storage I/O of `OpenStreetMap <https://www.openstreetmap.org/>`_ data
    with `PostgreSQL`_.

    .. _`PostgreSQL`: https://www.postgresql.org/
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
        :param host: host name/address of a PostgreSQL server,
            e.g. ``'localhost'`` or ``'127.0.0.1'`` (default by installation of PostgreSQL);
            when ``host=None`` (default), it is initialized as ``'localhost'``
        :type host: str | None
        :param port: listening port used by PostgreSQL; when ``port=None`` (default),
            it is initialized as ``5432`` (default by installation of PostgreSQL)
        :type port: int | None
        :param username: username of a PostgreSQL server; when ``username=None`` (default),
            it is initialized as ``'postgres'`` (default by installation of PostgreSQL)
        :type username: str | None
        :param password: user password; when ``password=None`` (default),
            it is required to mannually type in the correct password to connect the PostgreSQL server
        :type password: str | int | None
        :param database_name: name of a database; when ``database=None`` (default),
            it is initialized as ``'postgres'`` (default by installation of PostgreSQL)
        :type database_name: str | None
        :param confirm_db_creation: whether to prompt a confirmation before creating a new database
            (if the specified database does not exist), defaults to ``False``
        :param data_source: name of data source, defaults to ``'Geofabrik'``;
            options include ``{'Geofabrik', 'BBBike'}``
        :type data_source: str
        :param max_tmpfile_size: defaults to ``None``,
            see also the function `pyhelpers.settings.gdal_configurations()`_
        :type max_tmpfile_size: int | None
        :param data_dir: directory where the data file is located/saved, defaults to ``None``;
            when ``data_dir=None``, it should be the same as the directory specified by
            the corresponding
            :attr:`~pydriosm.ios.PostgresOSM.downloader`/:attr:`~pydriosm.ios.PostgresOSM.reader`
        :type data_dir: str | None
        :param kwargs: [optional] parameters of the class `pyhelpers.sql.PostgreSQL`_

        :ivar str data_source: name of data sources, options include ``{'Geofabrik', 'BBBike'}``

        .. _`pyhelpers.settings.gdal_configurations()`:
            https://pyhelpers.readthedocs.io/en/latest/_generated/
            pyhelpers.settings.gdal_configurations.html
        .. _`pyhelpers.sql.PostgreSQL`:
            https://pyhelpers.readthedocs.io/en/latest/_generated/pyhelpers.sql.PostgreSQL.html

        **Examples**::

            >>> from pydriosm.ios._base import BaseIOS
            >>> osmdb = BaseIOS(database_name='osmdb_test')
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
            To drop the database "osmdb_test" from postgres:***@localhost:5432
            ? [No]|Yes: yes
            Dropping "osmdb_test" ... Done.
        """

        # valid_source_names = set(self.DATA_SOURCES).union({s.lower() for s in self.DATA_SOURCES})
        # assert data_source in valid_source_names, \
        #     f"`data_source` must be one of {valid_source_names}."
        self.data_source = find_similar_str(data_source, self.DATA_SOURCES)

        super().__init__(
            host=host, port=port, username=username, password=password, database_name=database_name,
            **kwargs)

        self.data_dir = data_dir
        setattr(self, 'data_dir', self.downloader.download_dir)

        self.max_tmpfile_size = max_tmpfile_size
        setattr(self, 'max_tmpfile_size', self.reader.max_tmpfile_size)

    @property
    def downloader(self, *args, **kwargs):
        """
        Instance of either the class :class:`~pydriosm.downloader.GeofabrikDownloader` or
        :class:`~pydriosm.downloader.BBBikeDownloader`, depending on the specified ``data_source``
        for creating an instance of the class :class:`~pydriosm.ios.PostgresOSM`.

        **Examples**::

            >>> from pydriosm.ios._base import BaseIOS

            >>> osmdb = BaseIOS(database_name='osmdb_test')
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

        return Downloader(data_source=self.data_source, download_dir=self.data_dir, *args, **kwargs)

    @property
    def NAME(self):
        """
        Name of the current property :attr:`~pydriosm.ios.PostgresOSM.downloader`.

        **Examples**::

            >>> from pydriosm.ios._base import BaseIOS

            >>> osmdb = BaseIOS(database_name='osmdb_test')
            Password (postgres@localhost:5432): ***
            Creating a database: "osmdb_test" ... Done.
            Connecting postgres:***@localhost:5432/osmdb_test ... Successfully.

            >>> osmdb.data_source
            'Geofabrik'
            >>> osmdb.NAME
            'Geofabrik OpenStreetMap data extracts'

            >>> # Change the data source
            >>> osmdb.data_source = 'BBBike'
            >>> osmdb.NAME
            'BBBike exports of OpenStreetMap data'

            >>> # Delete the database 'osmdb_test'
            >>> osmdb.drop_database(verbose=True)
            To drop the database "osmdb_test" from postgres:***@localhost:5432
            ? [No]|Yes: yes
            Dropping "osmdb_test" ... Done.
        """

        return self.downloader.NAME

    @property
    def LONG_NAME(self):
        """
        Name of the current property :attr:`~pydriosm.ios.PostgresOSM.downloader`.

        **Examples**::

            >>> from pydriosm.ios._base import BaseIOS

            >>> osmdb = BaseIOS(database_name='osmdb_test')
            Password (postgres@localhost:5432): ***
            Creating a database: "osmdb_test" ... Done.
            Connecting postgres:***@localhost:5432/osmdb_test ... Successfully.

            >>> osmdb.data_source
            'Geofabrik'
            >>> osmdb.LONG_NAME
            'Geofabrik OpenStreetMap data extracts'

            >>> # Change the data source
            >>> osmdb.data_source = 'BBBike'
            >>> osmdb.LONG_NAME
            'BBBike exports of OpenStreetMap data'

            >>> # Delete the database 'osmdb_test'
            >>> osmdb.drop_database(verbose=True)
            To drop the database "osmdb_test" from postgres:***@localhost:5432
            ? [No]|Yes: yes
            Dropping "osmdb_test" ... Done.
        """

        return self.downloader.LONG_NAME

    @property
    def URL(self):
        """
        Homepage URL of data resource for current property
        :attr:`~pydriosm.ios.PostgresOSM.downloader`.

        **Examples**::

            >>> from pydriosm.ios._base import BaseIOS

            >>> osmdb = BaseIOS(database_name='osmdb_test')
            Password (postgres@localhost:5432): ***
            Creating a database: "osmdb_test" ... Done.
            Connecting postgres:***@localhost:5432/osmdb_test ... Successfully.

            >>> osmdb.URL
            'https://download.geofabrik.de/'

            >>> # Change the data source
            >>> osmdb.data_source = 'BBBike'
            >>> osmdb.URL
            'https://download.bbbike.org/osm/bbbike/'

            >>> # Delete the database 'osmdb_test'
            >>> osmdb.drop_database(verbose=True)
            To drop the database "osmdb_test" from postgres:***@localhost:5432
            ? [No]|Yes: yes
            Dropping "osmdb_test" ... Done.
        """

        return self.downloader.URL

    @property
    def reader(self, **kwargs):
        """
        Instance of either :class:`~pydriosm.reader.GeofabrikReader` or
        :class:`~pydriosm.reader.BBBikeReader`, depending on the specified ``data_source``
        for creating an instance of the calss :class:`~pydriosm.ios.PostgresOSM`.

        **Examples**::

            >>> from pydriosm.ios._base import BaseIOS

            >>> osmdb = BaseIOS(database_name='osmdb_test')
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
            max_tmpfile_size=self.max_tmpfile_size, **kwargs)

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
        :param schema_named_as_layer: whether a schema is named as a layer name, defaults to ``False``
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
        """
        Get information about columns of a specific schema and table data of a geographic (sub)region.

        :param subregion_name: name of a geographic (sub)region, which acts as a table name
        :type subregion_name: str
        :param layer_name: name of an OSM layer (e.g. 'points', 'railways', ...),
            which acts as a schema name
        :type layer_name: str
        :param as_dict: whether to return the column information as a dictionary, defaults to ``True``
        :type as_dict: bool
        :param table_named_as_subregion: whether to use subregion name as table name,
            defaults to ``False``
        :type table_named_as_subregion: bool
        :param schema_named_as_layer: whether a schema is named as a layer name, defaults to ``False``
        :type schema_named_as_layer: bool
        :return: information about each column of the given table
        :rtype: pandas.DataFrame | dict

        **Examples**::

            >>> from pydriosm.ios._base import BaseIOS

            >>> osmdb = BaseIOS(database_name='osmdb_test')
            Password (postgres@localhost:5432): ***
            Creating a database: "osmdb_test" ... Done.
            Connecting postgres:***@localhost:5432/osmdb_test ... Successfully.

            >>> subrgn_name = 'London'
            >>> lyr_name = 'points'

            >>> # Take for example a table named "points"."London"
            >>> tbl_col_info = osmdb.get_table_column_info(subrgn_name, lyr_name)
            >>> type(tbl_col_info)
            pandas.core.frame.DataFrame
            >>> tbl_col_info.index.to_list()[:5]
            ['table_catalog',
             'table_schema',
             'table_name',
             'column_name',
             'ordinal_position']

            >>> # Another example of a table named "points"."Greater London"
            >>> tbl_col_info_dict = osmdb.get_table_column_info(
            ...     subrgn_name, lyr_name, as_dict=True, table_named_as_subregion=True,
            ...     schema_named_as_layer=True)
            >>> type(tbl_col_info_dict)
            dict
            >>> list(tbl_col_info_dict.keys())[:5]
            ['table_catalog',
             'table_schema',
             'table_name',
             'column_name',
             'ordinal_position']

            >>> # Delete the database 'osmdb_test'
            >>> osmdb.drop_database(verbose=True)
            To drop the database "osmdb_test" from postgres:***@localhost:5432
            ? [No]|Yes: yes
            Dropping "osmdb_test" ... Done.
        """

        table_name_ = self.get_table_name(subregion_name, table_named_as_subregion)
        schema_name_ = get_default_layer_name(layer_name) if schema_named_as_layer else layer_name

        column_info = self.get_column_info(
            table_name=table_name_, schema_name=schema_name_, as_dict=as_dict)

        return column_info

    def import_osm_layer(self, layer_data, table_name, schema_name,
                         table_named_as_subregion=False, schema_named_as_layer=False,
                         if_exists='fail', force_replace=False, chunk_size=None,
                         confirmation_required=True, verbose=False, **kwargs):
        """
        Import one layer of OSM data into a table.

        :param layer_data: one layer of OSM data
        :type layer_data: pandas.DataFrame | geopandas.GeoDataFrame
        :param schema_name: name of a schema (or name of a PBF layer)
        :type schema_name: str
        :param table_name: name of a table
        :type table_name: str
        :param table_named_as_subregion: whether to use subregion name as a table name,
            defaults to ``False``
        :type table_named_as_subregion: bool
        :param schema_named_as_layer: whether a schema is named as a layer name,
            defaults to ``False``
        :type schema_named_as_layer: bool
        :param if_exists: if the table already exists, defaults to ``'fail'``;
            valid options include ``{'replace', 'append', 'fail'}``
        :type if_exists: str
        :param force_replace: whether to force to replace existing table, defaults to ``False``
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
        :param kwargs: [optional] parameters of `pyhelpers.sql.PostgreSQL.dump_data()`_

        .. _`pyhelpers.sql.PostgreSQL.dump_data()`:
            https://pyhelpers.readthedocs.io/en/latest/sql.html#sql-postgresql-dump-data

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
            ...     parse_geometry=True)
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
            ...     verbose=True, if_exists='replace')
            Proceed to import data into "points"."Rutland" at postgres:***@localhost:5432/osmdb_test
            ? [No]|Yes: yes
            The table "points"."Rutland" already exists and is replaced.
            Importing the data into the table "points"."Rutland" ... Done.

            >>> # Get the information of the table "points"."Rutland"
            >>> tbl_col_info = osmdb.get_table_column_info(subrgn_name, points_key)
            >>> tbl_col_info.head()
                                column_0    column_1    column_2
            table_catalog     osmdb_test  osmdb_test  osmdb_test
            table_schema          points      points      points
            table_name           Rutland     Rutland     Rutland
            column_name               id    geometry  properties
            ordinal_position           1           2           3

        *Example 2* - Import data of the 'railways' layer of a shapefile*::

            >>> # Read the data of 'railways' layer and delete the extracts
            >>> lyr_name = 'railways'
            >>> rutland_railways_shp = osmdb.reader.read_shp(
            ...     subregion_name=subrgn_name, layer_names=lyr_name, data_dir=dat_dir,
            ...     download=True, rm_extracts=True, verbose=True)
            Downloading "rutland-latest-free.shp.zip" 100%|██████████| 2.71M/2.71M | 7.07...
              Saving "rutland-latest-free.shp.zip" to "./tests/osm_data/rutland/" ... Done.
            Extracting the following layer(s):
                'railways'
              from: "./tests/osm_data/rutland/rutland-latest-free.shp.zip" ...
                to: "./tests/osm_data/rutland/rutland-latest-free-shp/" ... Done.
            Reading "./tests/osm_data/rutland/rutland-latest-free-shp/gis_osm_railways_free_1.s...
            Deleting the extracts "./tests/osm_data/rutland/rutland-latest-free-shp/" ... Done.
            >>> type(rutland_railways_shp)
            dict
            >>> list(rutland_railways_shp.keys())
            ['railways']

            >>> # Get the data of 'railways' layer
            >>> rutland_railways_shp_ = rutland_railways_shp[lyr_name]
            >>> rutland_railways_shp_.head()
                osm_id  code  ...                                        coordinates shape_type
            0  2162114  6101  ...  [(-0.4644873, 52.7104315), (-0.4611095, 52.706...          3
            1  3681043  6101  ...  [(-0.6531215, 52.5730787), (-0.6531793, 52.572...          3
            2  3693985  6101  ...  [(-0.7220263, 52.696584), (-0.7218164, 52.6973...          3
            3  3693986  6101  ...  [(-0.6173072, 52.6132317), (-0.6241869, 52.614...          3
            4  8044108  6101  ...  [(-0.6978245, 52.6285831), (-0.7027126, 52.633...          3
            [5 rows x 9 columns]

            >>> # Import the 'railways' data into the PostgreSQL database
            >>> osmdb.import_osm_layer(
            ...     layer_data=rutland_railways_shp_, table_name=subrgn_name, schema_name=lyr_name,
            ...     verbose=True)
            Proceed to import data into "railways"."Rutland" at postgres:***@localhost:5432/osmdb_test
            ? [No]|Yes: yes
            Creating a schema: "railways" ... Done.
            Importing the data into the table "railways"."Rutland" ... Done.

            >>> # Get the information of the table "railways"."Rutland"
            >>> tbl_col_info = osmdb.get_table_column_info(subrgn_name, lyr_name)
            >>> tbl_col_info.head()
                                column_0    column_1  ...     column_7    column_8
            table_catalog     osmdb_test  osmdb_test  ...   osmdb_test  osmdb_test
            table_schema        railways    railways  ...     railways    railways
            table_name           Rutland     Rutland  ...      Rutland     Rutland
            column_name           osm_id        code  ...  coordinates  shape_type
            ordinal_position           1           2  ...            8           9
            [5 rows x 9 columns]

        Delete the test database and downloaded data files::

            >>> # Delete the database 'osmdb_test'
            >>> osmdb.drop_database(verbose=True)
            To drop the database "osmdb_test" from postgres:***@localhost:5432
            ? [No]|Yes: yes
            Dropping "osmdb_test" ... Done.

            >>> # Delete the downloaded data files
            >>> delete_dir(dat_dir, verbose=True)
            To delete the directory "./tests/osm_data/" (Not empty)
            ? [No]|Yes: yes
            Deleting "./tests/osm_data/" ... Done.
        """

        table_name_ = self.get_table_name(table_name, table_named_as_subregion)

        schema_name_ = get_default_layer_name(schema_name) if schema_named_as_layer else schema_name

        import_args = {
            'table_name': table_name_,
            'schema_name': schema_name_,
            'if_exists': if_exists,
            'force_replace': force_replace,
            'method': self.psql_insert_copy,
            'confirmation_required': confirmation_required,
            'verbose': 2 if verbose else False,
        }

        lyr_dat = preprocess_pdf_layer(layer_data=layer_data, layer_name=schema_name_)

        import_args.update({'data': lyr_dat, 'chunk_size': chunk_size})

        kwargs.update(import_args)
        self.import_data(**kwargs)

    def import_osm_data(self, osm_data, table_name, schema_names=None,
                        table_named_as_subregion=False, schema_named_as_layer=False,
                        if_exists='fail', force_replace=False, chunk_size=None,
                        confirmation_required=True, verbose=False, raise_error=True, **kwargs):
        """
        Import OSM data into a database.

        :param osm_data: OSM data of a geographic (sub)region
        :type osm_data: dict
        :param table_name: name of a table
        :type table_name: str
        :param schema_names: names of schemas for each layer of the PBF data, defaults to ``None``;
            when ``schema_names=None``, the default layer names as schema names
        :type schema_names: list | dict | None
        :param table_named_as_subregion: whether to use subregion name as a table name,
            defaults to ``False``
        :type table_named_as_subregion: bool
        :param schema_named_as_layer: whether a schema is named as a layer name,
            defaults to ``False``
        :type schema_named_as_layer: bool
        :param if_exists: if the table already exists, defaults to ``'fail'``;
            valid options include ``{'replace', 'append', 'fail'}``
        :type if_exists: str
        :param force_replace: whether to force to replace existing table, defaults to ``False``
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
        :param raise_error: Whether to raise the provided exception; defaults to ``True``;
            if ``raise_error=False``, the error will be suppressed.
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

            >>> subrgn_name = 'Rutland'  # name of a subregion
            >>> dat_dir = "tests/osm_data"  # name of a data directory where the subregion data is

        *Example 1* - Import data of a PBF file::

            >>> # First, read the PBF data of Rutland
            >>> # (If the data file is not available, it'll be downloaded by confirmation)
            >>> raw_rutland_pbf = osmdb.reader.read_pbf(
            ...     subrgn_name, dat_dir, download=True, verbose=True)
            Downloading "rutland-latest.osm.pbf" 100%|██████████| 1.89M/1.89M | 7.41MB/s ...
              Saving "rutland-latest.osm.pbf" to "./tests/osm_data/rutland/" ... Done.
            Reading "./tests/osm_data/rutland/rutland-latest.osm.pbf" ... Done.
            >>> type(raw_rutland_pbf)
            dict
            >>> list(raw_rutland_pbf.keys())
            ['points', 'lines', 'multilinestrings', 'multipolygons', 'other_relations']

            >>> # Import all layers of the raw PBF data of Rutland
            >>> osmdb.import_osm_data(raw_rutland_pbf, table_name=subrgn_name, verbose=True)
            Proceed to import data into table "Rutland" at postgres:***@localhost:5432/osmdb_test
            ? [No]|Yes: yes
            Importing the data ...
              "points" ... Done. (<total of rows> features)
              "lines" ... Done. (<total of rows> features)
              "multilinestrings" ... Done. (<total of rows> features)
              "multipolygons" ... Done. (<total of rows> features)
              "other_relations" ... Done. (<total of rows> features)

            >>> # Get parsed PBF data
            >>> parsed_rutland_pbf = osmdb.reader.read_pbf(
            ...     subregion_name=subrgn_name, data_dir=dat_dir, expand=True, parse_geometry=True,
            ...     parse_other_tags=True, verbose=True)
            Parsing "./tests/osm_data/rutland/rutland-latest.osm.pbf" ... Done.
            >>> type(parsed_rutland_pbf)
            dict
            >>> list(parsed_rutland_pbf.keys())
            ['points', 'lines', 'multilinestrings', 'multipolygons', 'other_relations']

            >>> # Import data of selected layers into specific schemas
            >>> schemas = {
            ...     "schema_0": 'lines',
            ...     "schema_1": 'points',
            ...     "schema_2": 'multipolygons',
            ... }
            >>> osmdb.import_osm_data(parsed_rutland_pbf, subrgn_name, schemas, verbose=True)
            Proceed to import data into table "Rutland" at postgres:***@localhost:5432/osmdb_test
            ? [No]|Yes: yes
            Importing the data ...
              "schema_0" ... Done. (<total of rows> features)
              "schema_1" ... Done. (<total of rows> features)
              "schema_2" ... Done. (<total of rows> features)

            >>> # To drop the schemas "schema_0", "schema_1" and "schema_2"
            >>> osmdb.drop_schema(schemas.keys(), confirmation_required=False, verbose=True)
            Dropping the following schemas from postgres:***@localhost:5432/osmdb_test:
              "schema_0" ... Done.
              "schema_1" ... Done.
              "schema_2" ... Done.

        *Example 2* - Import data of a shapefile::

            >>> # Read shapefile data of Rutland
            >>> rutland_shp = osmdb.reader.read_shp(
            ...     subregion_name=subrgn_name, data_dir=dat_dir, download=True,
            ...     rm_extracts=True, verbose=True)
            Downloading "rutland-latest-free.shp.zip" 100%|██████████| 2.71M/2.71M | 4.81...
              Saving "rutland-latest-free.shp.zip" to "./tests/osm_data/rutland/" ... Done.
            Extracting "./tests/osm_data/rutland/rutland-latest-free.shp.zip"
              to "./tests/osm_data/rutland/rutland-latest-free-shp/" ... Done.
            Reading the shapefile(s) at "./tests/osm_data/rutland/rutland-latest-free-shp/" ......
            Deleting the extracts "./tests/osm_data/rutland/rutland-latest-free-shp/" ... Done.
            >>> type(rutland_shp)
            dict
            >>> list(rutland_shp.keys())
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

            >>> # Import all layers of the shapefile data of Rutland
            >>> osmdb.import_osm_data(osm_data=rutland_shp, table_name=subrgn_name, verbose=True)
            Proceed to import data into table "Rutland" at postgres:***@localhost:5432/osmdb_test
            ? [No]|Yes: yes
            Importing the data ...
              "buildings" ... Done. (<total of rows> features)
              "landuse" ... Done. (<total of rows> features)
              "natural" ... Done. (<total of rows> features)
              "places" ... Done. (<total of rows> features)
              "pofw" ... Done. (<total of rows> features)
              "pois" ... Done. (<total of rows> features)
              "railways" ... Done. (<total of rows> features)
              "roads" ... Done. (<total of rows> features)
              "traffic" ... Done. (<total of rows> features)
              "transport" ... Done. (<total of rows> features)
              "water" ... Done. (<total of rows> features)
              "waterways" ... Done. (<total of rows> features)

        *Example 3* - Import BBBike shapefile data file of Leeds::

            >>> # Change the data source
            >>> osmdb.data_source = 'BBBike'
            >>> subrgn_name = 'Leeds'

            >>> # Read shapefile data of Leeds
            >>> leeds_shp = osmdb.reader.read_shp(
            ...     subregion_name=subrgn_name, data_dir=dat_dir, download=True, rm_extracts=True,
            ...     verbose=True)
            Downloading "Leeds.osm.shp.zip" 100%|██████████| 57.7M/57.7M | 20.6MB/s | ETA...
              Saving "Leeds.osm.shp.zip" to "./tests/osm_data/leeds/" ... Done.
            Extracting "./tests/osm_data/leeds/Leeds.osm.shp.zip"
              to "./tests/osm_data/leeds/" ... Done.
            Reading the shapefile(s) at "./tests/osm_data/leeds/Leeds-shp/shape/" ... Done.
            Deleting the extracts "./tests/osm_data/leeds/Leeds-shp/" ... Done.
            >>> type(leeds_shp)
            dict
            >>> list(leeds_shp.keys())
            ['buildings',
             'landuse',
             'natural',
             'places',
             'points',
             'railways',
             'roads',
             'waterways']

            >>> # Import all layers of the shapefile data of Leeds
            >>> osmdb.import_osm_data(osm_data=leeds_shp, table_name=subrgn_name, verbose=True)
            Proceed to import data into table "Leeds" at postgres:***@localhost:5432/osmdb_test
            ? [No]|Yes: yes
            Importing the data ...
              "buildings" ... Done. (<total of rows> features)
              "landuse" ... Done. (<total of rows> features)
              "natural" ... Done. (<total of rows> features)
              "places" ... Done. (<total of rows> features)
              "points" ... Done. (<total of rows> features)
              "railways" ... Done. (<total of rows> features)
              "roads" ... Done. (<total of rows> features)
              "waterways" ... Done. (<total of rows> features)

        Delete the test database and downloaded data files::

            >>> # Delete the database 'osmdb_test'
            >>> osmdb.drop_database(verbose=True)
            To drop the database "osmdb_test" from postgres:***@localhost:5432
            ? [No]|Yes: yes
            Dropping "osmdb_test" ... Done.

            >>> # Delete the downloaded data files
            >>> delete_dir(dat_dir, verbose=True)
            To delete the directory "./tests/osm_data/" (Not empty)
            ? [No]|Yes: yes
            Deleting "./tests/osm_data/" ... Done.
        """

        data_items = make_data_items(osm_data=osm_data, schema_names=schema_names)

        table_name_ = self.get_table_name(
            subregion_name=table_name, table_named_as_subregion=table_named_as_subregion)
        tbl_name = f'"{table_name_}"'

        if confirmed(f"Proceed to import data into the table {tbl_name} at {self.address}\n?",
                     confirmation_required=confirmation_required):

            if verbose:
                status_msg = "Importing the data"
                if not confirmation_required:
                    status_msg += f" into the table {tbl_name}"
                    if verbose != 2:
                        status_msg += f" at {self.address}"
                print(status_msg, end=" ... \n")

            for geom_type, osm_layer in data_items:
                if verbose:
                    print(f'  "{geom_type}"', end=" ... ")

                    if len(osm_layer) == 0:
                        print("The layer is empty. "
                              "The corresponding table in the database is thus empty.")

                try:
                    import_args = {
                        'layer_data': osm_layer,
                        'schema_name': geom_type,
                        'table_name': table_name_,
                        'table_named_as_subregion': table_named_as_subregion,
                        'schema_named_as_layer': schema_named_as_layer,
                        'if_exists': if_exists,
                        'force_replace': force_replace,
                        'chunk_size': chunk_size,
                        'confirmation_required': False,
                        'verbose': False,
                    }
                    kwargs.update(import_args)
                    self.import_osm_layer(**kwargs)

                    if verbose:
                        print(f"Done. ({len(osm_layer)} features)")

                except Exception as e:
                    _print_failure_message(
                        e, prefix=f'Failed on the layer "{geom_type}"', verbose=verbose,
                        raise_error=raise_error)

                del osm_layer
                gc.collect()

    @staticmethod
    def _decode_layer_dat(dat, possible_col_names):
        col_names = [x for x in possible_col_names if x in dat.columns]

        if len(col_names) > 0:
            for col_name in col_names:
                try:
                    dat[col_name] = dat[col_name].map(ast.literal_eval)
                except (SyntaxError, TypeError, ValueError, shapely.errors.GEOSException):
                    pass

                try:
                    dat[col_name] = dat[col_name].map(shapely.wkt.loads)
                except (SyntaxError, TypeError, ValueError, shapely.errors.GEOSException):
                    pass

    def _get_dtype(self, table_name_, schema_name_):
        column_info_table = self.get_column_info(table_name=table_name_, schema_name=schema_name_)

        dtype_ = column_info_table['data_type']
        dtype = dict(zip(column_info_table['column_name'], map(self.DATA_TYPES.get, dtype_)))

        return dtype

    def _check_schema_and_table_names(self, subregion_names, schema_names=None,
                                      table_named_as_subregion=False, schema_named_as_layer=False):
        table_names = self.reader.validate_dtype(subregion_names)
        table_names_ = sorted([self.get_table_name(x, table_named_as_subregion) for x in table_names])

        # Validate the input `schema_names`
        if schema_names is None:
            inspector = sqlalchemy.inspection.inspect(self.engine)
            schema_names_ = [
                x for x in inspector.get_schema_names()
                if x not in {'public', 'information_schema'}]
        else:
            schema_names_ = validate_schema_names(
                schema_names=schema_names, schema_named_as_layer=schema_named_as_layer)

        if len(schema_names_) > 0:
            existing_schema_names_ = list(set(
                schema_name
                for schema_name, table_name in itertools.product(schema_names_, table_names_)
                if self.subregion_table_exists(
                    subregion_name=table_name, layer_name=schema_name,
                    table_named_as_subregion=table_named_as_subregion,
                    schema_named_as_layer=schema_named_as_layer)))
        else:
            existing_schema_names_ = schema_names_

        return existing_schema_names_, table_names_

    def _get_table_list_and_confirmation_prompt(self, existing_schema_names_, table_names_):
        # existing_schema_names_.sort()
        _, schema_pl, prt_schema, _ = self._msg_for_multi_items(
            existing_schema_names_, desc='schema', fmt='"{}"', indent=4)
        _, tbl_pl, prt_tbl, _ = self._msg_for_multi_items(
            table_names_, desc='table', fmt='"{}"', indent=4)

        table_list = list(itertools.product(existing_schema_names_, table_names_))

        if len(table_list) == 1:
            confirmation_prompt = f'Proceed to drop {tbl_pl} {prt_schema}.{prt_tbl}\n' \
                                  f'  from {self.address}\n?'
        else:
            confirmation_prompt = f'Proceed to drop {tbl_pl} from {self.address}: {prt_tbl}\n' \
                                  f'  under the {schema_pl}: {prt_schema}\n?'

        return table_list, confirmation_prompt

    def _drop_subregion_table(self, connection, schema, table, verbose=False, raise_error=True):
        schema_table = f'"{schema}"."{table}"'

        if self.table_exists(table_name=table, schema_name=schema):
            if verbose:
                print(f"  {schema_table}", end=" ... ")

            try:
                query = f'DROP TABLE IF EXISTS {schema_table} CASCADE;'
                connection.execute(sqlalchemy.text(query))
                if verbose:
                    print("Done.")
            except Exception as e:
                _print_failure_message(
                    e=e, prefix="Failed. Error:", verbose=verbose, raise_error=raise_error)

        else:  # The table doesn't exist
            if verbose == 2:
                print(f"  {schema_table} does not exist.")

    def drop_subregion_tables(self, subregion_names, schema_names=None,
                              table_named_as_subregion=False, schema_named_as_layer=False,
                              confirmation_required=True, verbose=False, raise_error=False):
        """
        Delete all or specific schemas/layers of subregion data from the database being connected.

        :param subregion_names: name of table for a subregion (or name of a subregion)
        :type subregion_names: str | list
        :param schema_names: names of schemas for each layer of the PBF data,
            if ``None`` (default), the default layer names as schema names
        :type schema_names: str | list | None
        :param table_named_as_subregion: whether to use subregion name as a table name,
            defaults to ``False``
        :type table_named_as_subregion: bool
        :param schema_named_as_layer: whether a schema is named as a layer name,
            defaults to ``False``
        :type schema_named_as_layer: bool
        :param confirmation_required: whether to ask for confirmation to proceed,
            defaults to ``True``
        :type confirmation_required: bool
        :param verbose: whether to print relevant information in console, defaults to ``False``
        :type verbose: bool | int
        :param raise_error: Whether to raise the provided exception;
            if ``raise_error=False`` (default), the error will be suppressed.
        :type raise_error: bool

        .. seealso::

            Examples of the :meth:`PostgresOSM.drop_subregion_tables
            <pydriosm.ios.PostgresOSM.drop_subregion_tables>` method.
        """

        existing_schema_names_, table_names_ = self._check_schema_and_table_names(
            subregion_names=subregion_names, schema_names=schema_names,
            table_named_as_subregion=table_named_as_subregion,
            schema_named_as_layer=schema_named_as_layer)

        if not existing_schema_names_:
            print("None of the data exists.")

        else:
            table_list, confirm_msg = self._get_table_list_and_confirmation_prompt(
                existing_schema_names_=existing_schema_names_, table_names_=table_names_)

            if confirmed(confirm_msg, confirmation_required=confirmation_required):
                if_tables_exist = any(
                    self.table_exists(table_name=table, schema_name=schema)
                    for schema, table in table_list)

                if if_tables_exist:
                    if verbose:
                        drop_msg = "table" if len(table_list) == 1 else "tables"
                        print(f"Dropping the {drop_msg} ... ")

                    with self.engine.connect() as connection:
                        for schema, table in table_list:
                            self._drop_subregion_table(
                                connection=connection, schema=schema, table=table, verbose=verbose,
                                raise_error=raise_error)
