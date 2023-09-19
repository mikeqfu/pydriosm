import ast
import collections
import copy
import gc
import itertools
import os

import numpy as np
import pandas as pd
import shapely.wkt
import sqlalchemy
from pyhelpers._cache import _check_dependency, _format_err_msg
from pyhelpers.dbms import PostgreSQL
from pyhelpers.ops import confirmed, get_number_of_chunks, split_list
from pyhelpers.store import save_pickle

from pydriosm.downloader import BBBikeDownloader, GeofabrikDownloader
from pydriosm.ios.utils import *
from pydriosm.reader import BBBikeReader, GeofabrikReader
from pydriosm.utils import check_relpath, remove_osm_file


class PostgresOSM(PostgreSQL):
    """
    Implement storage I/O of `OpenStreetMap <https://www.openstreetmap.org/>`_ data
    with `PostgreSQL`_.

    .. _`PostgreSQL`: https://www.postgresql.org/
    """

    #: dict: Specify a `data-type <https://www.postgresql.org/docs/current/datatype.html>`_
    #: dictionary for data or columns corresponding to
    #: `Pandas <https://pandas.pydata.org/docs/user_guide/basics.html#basics-dtypes>`_.
    DATA_TYPES = {
        'text': str,
        'bigint': np.int64,
        'json': str,
    }

    #: list: Names of the data sources.
    DATA_SOURCES = ['Geofabrik', 'BBBike']

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

            >>> from pydriosm.ios import PostgresOSM

            >>> osmdb = PostgresOSM(database_name='osmdb_test')
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
    def downloader(self):
        """
        Instance of either the class :class:`~pydriosm.downloader.GeofabrikDownloader` or
        :class:`~pydriosm.downloader.BBBikeDownloader`, depending on the specified ``data_source``
        for creating an instance of the class :class:`~pydriosm.ios.PostgresOSM`.

        **Examples**::

            >>> from pydriosm.ios import PostgresOSM

            >>> osmdb = PostgresOSM(database_name='osmdb_test')
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

        downloader_args = {'download_dir': self.data_dir}

        if self.data_source.lower() == 'geofabrik':
            downloader_ = GeofabrikDownloader(**downloader_args)
        else:  # self.data_source.lower() == 'bbbike':
            downloader_ = BBBikeDownloader(**downloader_args)

        return downloader_

    @property
    def name(self):
        """
        Name of the current property :attr:`~pydriosm.ios.PostgresOSM.downloader`.

        **Examples**::

            >>> from pydriosm.ios import PostgresOSM

            >>> osmdb = PostgresOSM(database_name='osmdb_test')
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

        return self.downloader.LONG_NAME

    @property
    def url(self):
        """
        Homepage URL of data resource for current property
        :attr:`~pydriosm.ios.PostgresOSM.downloader`.

        **Examples**::

            >>> from pydriosm.ios import PostgresOSM

            >>> osmdb = PostgresOSM(database_name='osmdb_test')
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

    @property
    def reader(self):
        """
        Instance of either :class:`~pydriosm.reader.GeofabrikReader` or
        :class:`~pydriosm.reader.BBBikeReader`, depending on the specified ``data_source``
        for creating an instance of the calss :class:`~pydriosm.ios.PostgresOSM`.

        **Examples**::

            >>> from pydriosm.ios import PostgresOSM

            >>> osmdb = PostgresOSM(database_name='osmdb_test')
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

        reader_args = {
            'max_tmpfile_size': self.max_tmpfile_size,
            'data_dir': self.downloader.download_dir,
        }

        if self.data_source.lower() == 'geofabrik':
            reader_ = GeofabrikReader(**reader_args)
        else:
            reader_ = BBBikeReader(**reader_args)

        return reader_

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

            >>> from pydriosm.ios import PostgresOSM

            >>> osmdb = PostgresOSM(database_name='osmdb_test')
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

            >>> from pydriosm.ios import PostgresOSM

            >>> osmdb = PostgresOSM(database_name='osmdb_test')
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

            >>> from pydriosm.ios import PostgresOSM

            >>> osmdb = PostgresOSM(database_name='osmdb_test')
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

    @classmethod
    def _preprocess_layer_data(cls, layer_data, layer_name):
        if isinstance(layer_data, list):
            # osgeo_ogr = _check_dependency('osgeo.ogr')
            # if all(isinstance(f, osgeo_ogr.Feature) for f in layer_data):
            lyr_dat = pd.DataFrame([f.ExportToJson() for f in layer_data], columns=[layer_name])

        else:
            lyr_dat = layer_data.copy()
            if isinstance(lyr_dat, pd.Series):
                lyr_dat = pd.DataFrame(lyr_dat)

            if 'coordinates' in lyr_dat.columns:
                if not isinstance(lyr_dat.coordinates[0], list):
                    lyr_dat.coordinates = lyr_dat.coordinates.map(lambda x: x.wkt)

            if 'geometry' in [x.name for x in lyr_dat.dtypes]:
                geom_col_name = lyr_dat.dtypes[lyr_dat.dtypes == 'geometry'].index[0]
                lyr_dat[geom_col_name] = lyr_dat[geom_col_name].map(lambda x: x.wkt)

        return lyr_dat

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

            >>> from pydriosm.ios import PostgresOSM
            >>> from pyhelpers.dirs import delete_dir

            >>> osmdb = PostgresOSM(database_name='osmdb_test')
            Password (postgres@localhost:5432): ***
            Creating a database: "osmdb_test" ... Done.
            Connecting postgres:***@localhost:5432/osmdb_test ... Successfully.

            >>> subrgn_name = 'Rutland'  # name of a subregion
            >>> dat_dir = "tests\\osm_data"  # name of a data directory where the subregion data is

        *Example 1* - Import data of the 'points' layer of a PBF file::

            >>> # First, read the PBF data of Rutland (from Geofabrik free download server)
            >>> # (If the data file is not available, it'll be downloaded by confirmation)
            >>> raw_pbf = osmdb.reader.read_osm_pbf(subrgn_name, data_dir=dat_dir, verbose=True)
            Downloading "rutland-latest.osm.pbf"
                to "tests\\osm_data\\rutland\\" ... Done.
            Reading "tests\\osm_data\\rutland\\rutland-latest.osm.pbf" ... Done.
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
            To import data into "points"."Rutland" at postgres:***@localhost:5432/osmdb_test
            ? [No]|Yes: yes
            Creating a schema: "points" ... Done.
            Importing the data into the table "points"."Rutland" ... Done.

            >>> tbl_col_info = osmdb.get_table_column_info(subrgn_name, points_key)
            >>> tbl_col_info.head()
                                column_0
            table_catalog     osmdb_test
            table_schema          points
            table_name           Rutland
            column_name           points
            ordinal_position           1

            >>> # Parse the 'geometry' of the PBF data of Rutland
            >>> parsed_pbf = osmdb.reader.read_osm_pbf(
            ...     subregion_name=subrgn_name, data_dir=dat_dir, expand=True, parse_geometry=True)
            >>> type(parsed_pbf)
            dict
            >>> list(parsed_pbf.keys())
            ['points', 'lines', 'multilinestrings', 'multipolygons', 'other_relations']
            >>> parsed_pbf_points = parsed_pbf[points_key]  # Get the parsed data of 'points' layer
            >>> type(parsed_pbf_points)
            pandas.core.series.Series
            >>> parsed_pbf_points.head()
                     id  ...                                         properties
            0    488432  ...  {'osm_id': '488432', 'name': None, 'barrier': ...
            1    488658  ...  {'osm_id': '488658', 'name': 'Tickencote Inter...
            2  13883868  ...  {'osm_id': '13883868', 'name': None, 'barrier'...
            3  14049101  ...  {'osm_id': '14049101', 'name': None, 'barrier'...
            4  14558402  ...  {'osm_id': '14558402', 'name': None, 'barrier'...
            [5 rows x 3 columns]

            >>> # Import the parsed 'points' data into the PostgreSQL database
            >>> osmdb.import_osm_layer(
            ...     layer_data=parsed_pbf_points, table_name=subrgn_name, schema_name=points_key,
            ...     verbose=True, if_exists='replace')
            To import data into "points"."Rutland" at postgres:***@localhost:5432/osmdb_test
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
            >>> rutland_railways_shp = osmdb.reader.read_shp_zip(
            ...     subregion_name=subrgn_name, layer_names=lyr_name, data_dir=dat_dir,
            ...     rm_extracts=True, verbose=True)
            Downloading "rutland-latest-free.shp.zip"
                to "tests\\osm_data\\rutland\\" ... Done.
            Extracting the following layer(s):
                'railways'
                from "tests\\osm_data\\rutland\\rutland-latest-free.shp.zip"
                  to "tests\\osm_data\\rutland\\rutland-latest-free-shp\\" ... Done.
            Reading "tests\\osm_data\\rutland\\rutland-latest-free-shp\\gis_osm_railways_free_1.s...
            Deleting the extracts "tests\\osm_data\\rutland\\rutland-latest-free-shp\\" ... Done.
            >>> type(rutland_railways_shp)
            collections.OrderedDict
            >>> list(rutland_railways_shp.keys())
            ['railways']

            >>> # Get the data of 'railways' layer
            >>> rutland_railways_shp_ = rutland_railways_shp[lyr_name]
            >>> rutland_railways_shp_.head()
                osm_id  code  ...                                        coordinates shape_type
            0  2162114  6101  ...  [(-0.4528083, 52.6993402), (-0.4521571, 52.698...          3
            1  3681043  6101  ...  [(-0.6531215, 52.5730787), (-0.6531793, 52.572...          3
            2  3693985  6101  ...  [(-0.7323403, 52.6782102), (-0.7319059, 52.678...          3
            3  3693986  6101  ...  [(-0.6173072, 52.6132317), (-0.6241869, 52.614...          3
            4  4806329  6101  ...  [(-0.4576926, 52.7035194), (-0.4565358, 52.702...          3
            [5 rows x 9 columns]

            >>> # Import the 'railways' data into the PostgreSQL database
            >>> osmdb.import_osm_layer(
            ...     layer_data=rutland_railways_shp_, table_name=subrgn_name, schema_name=lyr_name,
            ...     verbose=True)
            To import data into "railways"."Rutland" at postgres:***@localhost:5432/osmdb_test
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
            To delete the directory "tests\\osm_data\\" (Not empty)
            ? [No]|Yes: yes
            Deleting "tests\\osm_data\\" ... Done.
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

        lyr_dat = self._preprocess_layer_data(layer_data=layer_data, layer_name=schema_name_)

        import_args.update({'data': lyr_dat, 'chunk_size': chunk_size})

        kwargs.update(import_args)
        self.import_data(**kwargs)

    @classmethod
    def _make_data_items(cls, osm_data, schema_names):
        if isinstance(schema_names, list):
            schema_names_ = validate_schema_names(
                schema_names=schema_names, schema_named_as_layer=True)
            assert all(x in osm_data.keys() for x in schema_names)
            data_items = zip(schema_names_, (osm_data[x] for x in schema_names_))

        elif isinstance(schema_names, dict):
            # e.g. schema_names = {'schema_0': 'lines', 'schema_1': 'points'}
            schema_names_ = validate_schema_names(
                schema_names=schema_names.values(), schema_named_as_layer=True)
            assert all(x in osm_data.keys() for x in schema_names_)
            data_items = zip(schema_names.keys(), (osm_data[x] for x in schema_names_))

        else:
            data_items = osm_data.items()

        return data_items

    def import_osm_data(self, osm_data, table_name, schema_names=None,
                        table_named_as_subregion=False, schema_named_as_layer=False,
                        if_exists='fail', force_replace=False, chunk_size=None,
                        confirmation_required=True, verbose=False, **kwargs):
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
        :param kwargs: [optional] parameters of the method
            :meth:`~pydriosm.ios.PostgresOSM.import_osm_layer`

        **Examples**::

            >>> from pydriosm.ios import PostgresOSM
            >>> from pyhelpers.dirs import delete_dir

            >>> osmdb = PostgresOSM(database_name='osmdb_test')
            Password (postgres@localhost:5432): ***
            Creating a database: "osmdb_test" ... Done.
            Connecting postgres:***@localhost:5432/osmdb_test ... Successfully.

            >>> subrgn_name = 'Rutland'  # name of a subregion
            >>> dat_dir = "tests\\osm_data"  # name of a data directory where the subregion data is

        *Example 1* - Import data of a PBF file::

            >>> # First, read the PBF data of Rutland
            >>> # (If the data file is not available, it'll be downloaded by confirmation)
            >>> raw_rutland_pbf = osmdb.reader.read_osm_pbf(subrgn_name, dat_dir, verbose=True)
            Downloading "rutland-latest.osm.pbf"
                to "tests\\osm_data\\rutland\\" ... Done.
            Reading "tests\\osm_data\\rutland\\rutland-latest.osm.pbf" ... Done.
            >>> type(raw_rutland_pbf)
            dict
            >>> list(raw_rutland_pbf.keys())
            ['points', 'lines', 'multilinestrings', 'multipolygons', 'other_relations']

            >>> # Import all layers of the raw PBF data of Rutland
            >>> osmdb.import_osm_data(raw_rutland_pbf, table_name=subrgn_name, verbose=True)
            To import data into table "Rutland" at postgres:***@localhost:5432/osmdb_test
            ? [No]|Yes: yes
            Importing the data ...
                "points" ... Done. (<total of rows> features)
                "lines" ... Done. (<total of rows> features)
                "multilinestrings" ... Done. (<total of rows> features)
                "multipolygons" ... Done. (<total of rows> features)
                "other_relations" ... Done. (<total of rows> features)

            >>> # Get parsed PBF data
            >>> parsed_rutland_pbf = osmdb.reader.read_osm_pbf(
            ...     subregion_name=subrgn_name, data_dir=dat_dir, expand=True, parse_geometry=True,
            ...     parse_other_tags=True, verbose=True)
            Parsing "tests\\osm_data\\rutland\\rutland-latest.osm.pbf" ... Done.
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
            To import data into table "Rutland" at postgres:***@localhost:5432/osmdb_test
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
            >>> rutland_shp = osmdb.reader.read_shp_zip(
            ...     subregion_name=subrgn_name, data_dir=dat_dir, rm_extracts=True, verbose=True)
            Downloading "rutland-latest-free.shp.zip"
                to "tests\\osm_data\\rutland\\" ... Done.
            Extracting "tests\\osm_data\\rutland\\rutland-latest-free.shp.zip"
                to "tests\\osm_data\\rutland\\rutland-latest-free-shp\\" ... Done.
            Reading the shapefile(s) at
                "tests\\osm_data\\rutland\\rutland-latest-free-shp\\" ... Done.
            Deleting the extracts "tests\\osm_data\\rutland\\rutland-latest-free-shp\\" ... Done.
            >>> type(rutland_shp)
            collections.OrderedDict
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
            To import data into table "Rutland" at postgres:***@localhost:5432/osmdb_test
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
            >>> leeds_shp = osmdb.reader.read_shp_zip(
            ...     subregion_name=subrgn_name, data_dir=dat_dir, rm_extracts=True, verbose=True)
            Downloading "Leeds.osm.shp.zip"
                to "tests\\osm_data\\leeds\\" ... Done.
            Extracting "tests\\osm_data\\leeds\\Leeds.osm.shp.zip"
                to "tests\\osm_data\\leeds\\" ... Done.
            Reading the shapefile(s) at
                "tests\\osm_data\\leeds\\Leeds-shp\\shape\\" ... Done.
            Deleting the extracts "tests\\osm_data\\leeds\\Leeds-shp\\" ... Done.
            >>> type(leeds_shp)
            collections.OrderedDict
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
            To import data into table "Leeds" at postgres:***@localhost:5432/osmdb_test
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
            To delete the directory "tests\\osm_data\\" (Not empty)
            ? [No]|Yes: yes
            Deleting "tests\\osm_data\\" ... Done.
        """

        data_items = self._make_data_items(osm_data=osm_data, schema_names=schema_names)

        table_name_ = self.get_table_name(
            subregion_name=table_name, table_named_as_subregion=table_named_as_subregion)
        tbl_name = f'"{table_name_}"'

        if confirmed(f"To import data into table {tbl_name} at {self.address}\n?",
                     confirmation_required=confirmation_required):

            if verbose:
                status_msg = "Importing the data"
                if not confirmation_required:
                    status_msg += f" into table {tbl_name}"
                    if verbose != 2:
                        status_msg += f" at {self.address}"
                print(status_msg, end=" ... \n")

            for geom_type, osm_layer in data_items:
                if verbose:
                    print(f"\t\"{geom_type}\"", end=" ... ")

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
                    if verbose:
                        fail_msg = f"Failed. {e}"
                    else:
                        fail_msg = f"Failed on the layer \"{geom_type}\". {e}"
                    print(fail_msg)

                del osm_layer
                gc.collect()

    def _import_subregion_osm_pbf(self, subregion_name_, osm_file_format, path_to_osm_pbf,
                                  chunk_size_limit, expand, parse_geometry, parse_properties,
                                  parse_other_tags, if_exists, pickle_pbf_file, verbose,
                                  **kwargs):
        number_of_chunks = get_number_of_chunks(path_to_osm_pbf, chunk_size_limit)

        if verbose:
            print(f"Reading \"{check_relpath(path_to_osm_pbf)}\"", end=" ... ")

        osm_pbf_data = PBFReadParse.read_pbf(
            pbf_pathname=path_to_osm_pbf, number_of_chunks=number_of_chunks, expand=expand,
            parse_geometry=parse_geometry, parse_properties=parse_properties,
            parse_other_tags=parse_other_tags)

        if verbose:
            print("Done.")

        if osm_pbf_data is not None:
            import_args = {
                'osm_data': osm_pbf_data,
                'table_name': subregion_name_,
                'if_exists': if_exists,
                'confirmation_required': False,
                'verbose': 2 if verbose else False,
            }
            kwargs.update(import_args)
            self.import_osm_data(**kwargs)

            if pickle_pbf_file:
                path_to_pickle = path_to_osm_pbf.replace(osm_file_format, "-pbf.pickle")
                save_pickle(osm_pbf_data, path_to_pickle, verbose=verbose)

        del osm_pbf_data
        gc.collect()

    def _import_pbf_layer_chunk_wisely(self, layer, layer_name, subregion_name_, number_of_chunks,
                                       expand, parse_geometry, parse_properties, parse_other_tags,
                                       pickle_pbf_file, verbose, **kwargs):
        if verbose:
            print(f'\t"{layer_name}"', end=" ... ")

        features = [feat for feat in layer]
        count_of_features = len(features)

        list_of_chunks = split_list(lst=features, num_of_sub=number_of_chunks)

        del features
        gc.collect()

        layer_dat_list = []
        try:
            for chunk in list_of_chunks:  # Loop through all chunks
                if expand:
                    lyr_dat = pd.DataFrame(f.ExportToJson(as_object=True) for f in chunk)
                else:
                    lyr_dat = pd.DataFrame([f.ExportToJson() for f in chunk], columns=[layer_name])

                layer_dat = PBFReadParse.transform_pbf_layer_field(
                    layer_data=lyr_dat, layer_name=layer_name, parse_geometry=parse_geometry,
                    parse_properties=parse_properties, parse_other_tags=parse_other_tags)

                import_args = {
                    'layer_data': layer_dat,
                    'table_name': subregion_name_,
                    'schema_name': layer_name,
                    'if_exists': 'append',  # if_exists if if_exists == 'fail' else 'append'
                    'confirmation_required': False,
                }
                kwargs.update(import_args)
                self.import_osm_layer(**kwargs)

                if pickle_pbf_file:
                    layer_dat_list.append(layer_dat)

                del layer_dat
                gc.collect()

            if verbose:
                print(f"Done. ({count_of_features} features)")

        except Exception as e:
            print(f"Failed. {_format_err_msg(e)}")

        return layer_dat_list

    def _import_subregion_osm_pbf_chunk_wisely(self, subregion_name_, osm_file_format,
                                               path_to_osm_pbf, chunk_size_limit, expand,
                                               parse_geometry, parse_properties, parse_other_tags,
                                               if_exists, pickle_pbf_file, verbose, **kwargs):
        # Reference: https://gdal.org/python/osgeo.ogr.Feature-class.html

        if verbose:
            print(f'Importing the data of "{subregion_name_}" chunk-wisely\n'
                  f'  into {self.address} ... ')

        osgeo_ogr = _check_dependency(name='osgeo.ogr')
        raw_osm_pbf = osgeo_ogr.Open(path_to_osm_pbf)
        layer_count = raw_osm_pbf.GetLayerCount()

        number_of_chunks = get_number_of_chunks(
            file_or_obj=path_to_osm_pbf, chunk_size_limit=chunk_size_limit)

        layer_names, layer_data_list = [], []
        for i in range(layer_count):
            layer = raw_osm_pbf.GetLayerByIndex(i)  # Hold the i-th layer
            layer_name = layer.GetName()

            tbl_exists = self.subregion_table_exists(
                subregion_name=subregion_name_, layer_name=layer_name)

            if tbl_exists:
                if if_exists == 'fail':
                    if verbose:
                        print(f'\tTable "{subregion_name_}" already exists.')

                    lyr_dat = PBFReadParse._read_pbf_layer_chunkwise(
                        layer, number_of_chunks=number_of_chunks, readable=True, expand=expand,
                        parse_geometry=parse_geometry, parse_properties=parse_properties,
                        parse_other_tags=parse_other_tags)

                    if pickle_pbf_file:
                        layer_names.append(layer_name)
                        layer_data_list.append(lyr_dat)

                    continue

                elif if_exists == 'replace':
                    self.drop_subregion_tables(
                        subregion_names=subregion_name_, schema_names=layer_name,
                        confirmation_required=False)

            layer_dat_list = self._import_pbf_layer_chunk_wisely(
                layer=layer, layer_name=layer_name, subregion_name_=subregion_name_,
                number_of_chunks=number_of_chunks, expand=expand, parse_geometry=parse_geometry,
                parse_properties=parse_properties, parse_other_tags=parse_other_tags,
                pickle_pbf_file=pickle_pbf_file, verbose=verbose, **kwargs)

            if pickle_pbf_file:
                layer_names.append(layer_name)
                layer_data_list.append(pd.concat(layer_dat_list, axis=0, ignore_index=True))

        raw_osm_pbf.Release()

        del raw_osm_pbf
        gc.collect()

        if pickle_pbf_file:
            osm_pbf_data = dict(zip(layer_names, layer_data_list))
            path_to_pickle = path_to_osm_pbf.replace(osm_file_format, "-pbf.pickle")
            save_pickle(osm_pbf_data, path_to_pickle, verbose=verbose)

        del osm_pbf_data
        gc.collect()

    def import_subregion_osm_pbf(self, subregion_names, data_dir=None, update_osm_pbf=False,
                                 if_exists='fail', chunk_size_limit=50, expand=False,
                                 parse_geometry=False, parse_properties=False,
                                 parse_other_tags=False, pickle_pbf_file=False, rm_pbf_file=False,
                                 confirmation_required=True, verbose=False, **kwargs):
        """
        Import data of geographic (sub)region(s) that do not have (sub-)subregions into a database.

        :param subregion_names: name(s) of geographic (sub)region(s)
        :type subregion_names: str | list | None
        :param data_dir: directory where the PBF data file is located/saved;
            if ``None`` (default), the default directory
        :type data_dir: str | None
        :param update_osm_pbf: whether to update .osm.pbf data file (if available),
            defaults to ``False``
        :type update_osm_pbf: bool
        :param if_exists: if the table already exists, defaults to ``'fail'``;
            valid options include ``{'replace', 'append', 'fail'}``
        :type if_exists: str
        :param chunk_size_limit: threshold (in MB) that triggers the use of chunk parser,
            defaults to ``50``;
            if the size of the .osm.pbf file (in MB) is greater than ``chunk_size_limit``,
            it will be parsed in a chunk-wise way
        :type chunk_size_limit: int
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
        :param pickle_pbf_file: whether to save the .pbf data as a .pickle file,
            defaults to ``False``
        :type pickle_pbf_file: bool
        :param rm_pbf_file: whether to delete the downloaded .osm.pbf file, defaults to ``False``
        :type rm_pbf_file: bool
        :param confirmation_required: whether to ask for confirmation to proceed,
            defaults to ``True``
        :type confirmation_required: bool
        :param verbose: whether to print relevant information in console, defaults to ``False``
        :type verbose: bool | int
        :param kwargs: [optional] parameters of the method
            :meth:`~pydriosm.ios.PostgresOSM._import_subregion_osm_pbf` or
            :meth:`~pydriosm.ios.PostgresOSM._import_subregion_osm_pbf_chunk_wisely`

        .. _`shapely.geometry`:
            https://shapely.readthedocs.io/en/latest/manual.html#geometric-objects
        .. _`dict`:
            https://docs.python.org/3/library/stdtypes.html#dict

        **Examples**::

            >>> from pydriosm.ios import PostgresOSM
            >>> from pyhelpers.dirs import cd, delete_dir
            >>> from pyhelpers.store import load_pickle

            >>> osmdb = PostgresOSM(database_name='osmdb_test')
            Password (postgres@localhost:5432): ***
            Creating a database: "osmdb_test" ... Done.
            Connecting postgres:***@localhost:5432/osmdb_test ... Successfully.

        *Example 1* - Import PBF data of Rutland::

            >>> subrgn_name = 'Rutland'  # name of a subregion
            >>> dat_dir = "tests\\osm_data"  # name of a data directory where the subregion data is

            >>> osmdb.import_subregion_osm_pbf(subrgn_name, data_dir=dat_dir, verbose=True)
            To import .osm.pbf data of the following geographic (sub)region(s):
                "Rutland"
              into postgres:***@localhost:5432/osmdb_test
            ? [No]|Yes: yes
            Downloading "rutland-latest.osm.pbf"
                to "tests\\osm_data\\rutland\" ... Done.
            Reading "tests\\osm_data\\rutland\\rutland-latest.osm.pbf" ... Done.
            Importing the data into table "Rutland" ...
                "points" ... Done. (<total of rows> features)
                "lines" ... Done. (<total of rows> features)
                "multilinestrings" ... Done. (<total of rows> features)
                "multipolygons" ... Done. (<total of rows> features)
                "other_relations" ... Done. (<total of rows> features)

        *Example 2* - Import PBF data of Leeds and London::

            >>> # Change the data source
            >>> osmdb.data_source = 'BBBike'
            >>> subrgn_names = ['Leeds', 'London']

            >>> # Note this may take a few minutes (or longer)
            >>> osmdb.import_subregion_osm_pbf(
            ...     subregion_names=subrgn_names, data_dir=dat_dir, expand=True,
            ...     parse_geometry=True, parse_properties=True, parse_other_tags=True,
            ...     pickle_pbf_file=True, rm_pbf_file=True, verbose=True)
            To import .osm.pbf data of the following geographic (sub)region(s):
                "Leeds"
                "London"
              into postgres:***@localhost:5432/osmdb_test
            ? [No]|Yes: yes
            Downloading "Leeds.osm.pbf"
                to "tests\\osm_data\\leeds\\" ... Done.
            Reading "tests\\osm_data\\leeds\\Leeds.osm.pbf" ... Done.
            Importing the data into table "Leeds" ...
                "points" ... Done. (82137 features)
                "lines" ... Done. (164411 features)
                "multilinestrings" ... Done. (390 features)
                "multipolygons" ... Done. (439144 features)
                "other_relations" ... Done. (6938 features)
            Saving "Leeds-pbf.pickle" to "tests\\osm_data\\leeds\\" ... Done.
            Deleting "tests\\osm_data\\leeds\\Leeds.osm.pbf" ... Done.
            Downloading "London.osm.pbf"
                to "tests\\osm_data\\london\\" ... Done.
            Importing the data of "London" chunk-wisely
              into postgres:***@localhost:5432/osmdb_test ...
                "points" ... Done. (654517 features)
                "lines" ... Done. (769631 features)
                "multilinestrings" ... Done. (7241 features)
                "multipolygons" ... Done. (5432 features)
                "other_relations" ... Done. (21792 features)
            Saving "London-pbf.pickle" to "tests\\osm_data\\london\\" ... Done.
            Deleting "tests\\osm_data\\london\\London.osm.pbf" ... Done.

            >>> # As `pickle_pbf_file=True`, the parsed PBF data have been saved as pickle files

            >>> # Data of Leeds
            >>> leeds_pbf = load_pickle(cd(dat_dir, "leeds", "Leeds-pbf.pickle"))
            >>> type(leeds_pbf)
            dict
            >>> list(leeds_pbf.keys())
            ['points', 'lines', 'multilinestrings', 'multipolygons', 'other_relations']
            >>> # Data of the 'points' layer of Leeds
            >>> leeds_pbf_points = leeds_pbf['points']
            >>> leeds_pbf_points.head()
                   id                       geometry  ... man_made             other_tags
            0  154941  POINT (-1.5560511 53.6879848)  ...     None                   None
            1  154962     POINT (-1.34293 53.844618)  ...     None  {'name:signed': 'no'}
            2  155014   POINT (-1.517335 53.7499667)  ...     None  {'name:signed': 'no'}
            3  155023   POINT (-1.514124 53.7416937)  ...     None  {'name:signed': 'no'}
            4  155035   POINT (-1.516511 53.7256632)  ...     None  {'name:signed': 'no'}
            [5 rows x 11 columns]

            >>> # Data of London
            >>> london_pbf = load_pickle(cd(dat_dir, "london", "London-pbf.pickle"))
            >>> type(london_pbf)
            dict
            >>> list(london_pbf.keys())
            ['points', 'lines', 'multilinestrings', 'multipolygons', 'other_relations']
            >>> # Data of the 'points' layer of London
            >>> london_pbf_points = london_pbf['points']
            >>> london_pbf_points.head()
                  id  ...                                         other_tags
            0  99878  ...  {'access': 'permissive', 'bicycle': 'no', 'mot...
            1  99880  ...  {'crossing': 'unmarked', 'crossing:island': 'n...
            2  99884  ...                        {'amenity': 'waste_basket'}
            3  99918  ...                         {'emergency': 'life_ring'}
            4  99939  ...           {'traffic_signals:direction': 'forward'}
            [5 rows x 11 columns]

        Delete the test database and downloaded data files::

            >>> # Delete the database 'osmdb_test'
            >>> osmdb.drop_database(verbose=True)
            To drop the database "osmdb_test" from postgres:***@localhost:5432
            ? [No]|Yes: yes
            Dropping "osmdb_test" ... Done.

            >>> # Delete the downloaded data files
            >>> delete_dir(dat_dir, verbose=True)
            To delete the directory "tests\\osm_data\\" (Not empty)
            ? [No]|Yes: yes
            Deleting "tests\\osm_data\\" ... Done.
        """

        osm_file_format = ".osm.pbf"

        if subregion_names is None:
            subregion_names_ = self.downloader.get_valid_subregion_names()
            confirm_msg = \
                f"To import all {osm_file_format} data available on {self.data_source} " \
                f"  into {self.address}\n?"

        else:
            subregion_names_ = [
                self.downloader.validate_subregion_name(x)
                for x in self.reader.validate_input_dtype(subregion_names)]

            if self.data_source == 'Geofabrik':
                subregion_names_ = self.downloader.get_subregions(*subregion_names_)

            subrgn_names_msg = '"\n\t"'.join(subregion_names_)
            confirm_msg = \
                f"To import {osm_file_format} data of the following geographic (sub)region(s):\n" \
                f"\t\"{subrgn_names_msg}\"\n" \
                f"  into {self.address}\n?"

        if confirmed(confirm_msg, confirmation_required=confirmation_required):
            err_subregion_names = []

            for subregion_name_ in subregion_names_:
                path_to_osm_pbf_ = self.downloader.download_osm_data(
                    subregion_names=subregion_name_, osm_file_format=osm_file_format,
                    download_dir=data_dir, update=update_osm_pbf, confirmation_required=False,
                    verbose=verbose, ret_download_path=True)
                path_to_osm_pbf = path_to_osm_pbf_[0]

                try:
                    read_pbf_args = {
                        'expand': expand,
                        'parse_geometry': parse_geometry,
                        'parse_properties': parse_properties,
                        'parse_other_tags': parse_other_tags,
                    }
                    import_args = {
                        'subregion_name_': subregion_name_,
                        'osm_file_format': osm_file_format,
                        'path_to_osm_pbf': path_to_osm_pbf,
                        'chunk_size_limit': chunk_size_limit,
                        'pickle_pbf_file': pickle_pbf_file,
                        'verbose': verbose,
                        # 'if_exists': if_exists,
                    }
                    import_args.update(read_pbf_args)

                    file_size_in_mb = round(os.path.getsize(path_to_osm_pbf) / (1024 ** 2), 1)
                    if file_size_in_mb <= chunk_size_limit:
                        import_args.update({'if_exists': if_exists})
                        self._import_subregion_osm_pbf(**import_args, **kwargs)
                    else:
                        import_args.update({'if_exists': 'append'})
                        self._import_subregion_osm_pbf_chunk_wisely(**import_args, **kwargs)

                    if rm_pbf_file:
                        remove_osm_file(path_to_file=path_to_osm_pbf, verbose=verbose)

                except Exception as e:
                    print(e)
                    err_subregion_names.append(subregion_name_)

            if len(err_subregion_names) > 0:
                print(
                    "Errors occurred when parsing data of the following subregion(s):", end="\n\t")
                print('"' + '"\n\t"'.join(err_subregion_names) + '"')

    @staticmethod
    def _decode_layer_dat(dat, possible_col_names):
        col_names = [x for x in possible_col_names if x in dat.columns]
        if len(col_names) >= 1:
            # noinspection PyBroadException
            try:
                dat[col_names] = dat[col_names].applymap(ast.literal_eval)
            except Exception:  # SyntaxError
                dat[col_names] = dat[col_names].applymap(shapely.wkt.loads)

    def decode_pbf_layer(self, layer_dat, decode_geojson=True):
        """
        Process raw data of a PBF layer retrieved from database.

        .. seealso::

            - Examples of the method :meth:`~pydriosm.ios.PostgresOSM.fetch_osm_data`.
        """

        # if engine:
        #     valid_methods = {'ujson', 'orjson', 'rapidjson', 'json'}
        #     assert engine in valid_methods, f"`method` must be on one of {valid_methods}."
        #     json_mod_name = engine
        # else:
        #     json_mod_name = 'json'
        # json_mod = _check_dependency(name=json_mod_name)

        layer_dat_ = layer_dat.replace({np.nan: None})

        if decode_geojson:
            if layer_dat_.shape[1] == 1:
                col_name = layer_dat_.columns[0]
                temp = layer_dat_[col_name]

                if temp.map(type).eq(str).any():
                    temp = temp.map(ast.literal_eval)

                layer_dat_ = temp.to_frame(name=col_name)

            else:
                possible_col_names = {
                    'coordinates', 'geometries', 'geometry', 'other_tags', 'properties'}
                self._decode_layer_dat(layer_dat_, possible_col_names=possible_col_names)

        return layer_dat_

    def fetch_osm_data(self, subregion_name, layer_names=None, chunk_size=None, method='tempfile',
                       max_size_spooled=1, decode_geojson=True, sort_by='id',
                       table_named_as_subregion=False, schema_named_as_layer=False, verbose=False,
                       **kwargs):
        """
        Fetch OSM data (of one or multiple layers) of a geographic (sub)region.

        See also
        [`ROP-1 <https://pyhelpers.readthedocs.io/en/latest/sql.html#sql-postgresql-read-sql-query>`_].

        :param subregion_name: name of a geographic (sub)region (or the corresponding table)
        :type subregion_name: str
        :param layer_names: names of schemas for each layer of the PBF data,
            if ``None`` (default), the default layer names as schema names
        :type layer_names: list | None
        :param chunk_size: the number of rows in each batch to be written at a time,
            defaults to ``None``
        :type chunk_size: int | None
        :param method: method to be used for buffering temporary data, defaults to ``'tempfile'``
        :type method: str | None
        :param max_size_spooled: see `pyhelpers.sql.PostgreSQL.read_sql_query()`_,
            defaults to ``1`` (in GB)
        :type max_size_spooled: int, float
        :param decode_geojson: whether to decode string GeoJSON data, defaults to ``True``
        :type decode_geojson: bool
        :param sort_by: column name(s) by which the data (fetched from PostgreSQL) is sorted,
            defaults to ``'id'``
        :type sort_by: str | list
        :param table_named_as_subregion: whether to use subregion name as a table name,
            defaults to ``False``
        :type table_named_as_subregion: bool
        :param schema_named_as_layer: whether a schema is named as a layer name,
            defaults to ``False``
        :type schema_named_as_layer: bool
        :param verbose: whether to print relevant information in console, defaults to ``False``
        :type verbose: bool | int
        :return: PBF (.osm.pbf) data
        :rtype: dict | collections.OrderedDict

        .. _`pyhelpers.sql.PostgreSQL.read_sql_query()`:
            https://pyhelpers.readthedocs.io/en/latest/sql.html#sql-postgresql-read-sql-query

        **Examples**::

            >>> from pydriosm.ios import PostgresOSM
            >>> from pyhelpers.dirs import delete_dir

            >>> osmdb = PostgresOSM(database_name='osmdb_test')
            Password (postgres@localhost:5432): ***
            Creating a database: "osmdb_test" ... Done.
            Connecting postgres:***@localhost:5432/osmdb_test ... Successfully.

            >>> subrgn_name = 'Rutland'  # name of a subregion
            >>> dat_dir = "tests\\osm_data"  # name of a data directory where the subregion data is

            >>> # Import PBF data of Rutland
            >>> osmdb.import_subregion_osm_pbf(subrgn_name, data_dir=dat_dir, verbose=True)
            To import .osm.pbf data of the following geographic (sub)region(s):
                "Rutland"
              into postgres:***@localhost:5432/osmdb_test
            ? [No]|Yes: yes
            Downloading "rutland-latest.osm.pbf"
                to "tests\\osm_data\\rutland\\" ... Done.
            Reading "tests\\osm_data\\rutland\\rutland-latest.osm.pbf" ... Done.
            Importing the data into table "Rutland" ...
                "points" ... Done. (<total of rows> features)
                "lines" ... Done. (<total of rows> features)
                "multilinestrings" ... Done. (<total of rows> features)
                "multipolygons" ... Done. (<total of rows> features)
                "other_relations" ... Done. (<total of rows> features)

            >>> # Import shapefile data of Rutland
            >>> rutland_shp = osmdb.reader.read_shp_zip(
            ...     subrgn_name, data_dir=dat_dir, rm_extracts=True, verbose=True)
            Downloading "rutland-latest-free.shp.zip"
                to "tests\\osm_data\\rutland\\" ... Done.
            Extracting "tests\\osm_data\\rutland\\rutland-latest-free.shp.zip"
                to "tests\\osm_data\\rutland\\rutland-latest-free-shp\\" ... Done.
            Reading the shapefile(s) at
                "tests\\osm_data\\rutland\\rutland-latest-free-shp\\" ... Done.
            Deleting the extracts "tests\\osm_data\\rutland\\rutland-latest-free-shp\\" ... Done.
            >>> osmdb.import_osm_data(rutland_shp, table_name=subrgn_name, verbose=True)
            To import data into table "Rutland" at postgres:***@localhost:5432/osmdb_test
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

            >>> # Retrieve the data of specific layers
            >>> lyr_names = ['points', 'multipolygons']
            >>> rutland_data_ = osmdb.fetch_osm_data(subrgn_name, lyr_names, verbose=True)
            Fetching the data of "Rutland" ...
                "points" ... Done.
                "multipolygons" ... Done.
            >>> type(rutland_data_)
            collections.OrderedDict
            >>> list(rutland_data_.keys())
            ['points', 'multipolygons']

            >>> # Data of the 'points' layer
            >>> rutland_points = rutland_data_['points']
            >>> rutland_points.head()
                                                          points
            0  {'type': 'Feature', 'geometry': {'type': 'Poin...
            1  {'type': 'Feature', 'geometry': {'type': 'Poin...
            2  {'type': 'Feature', 'geometry': {'type': 'Poin...
            3  {'type': 'Feature', 'geometry': {'type': 'Poin...
            4  {'type': 'Feature', 'geometry': {'type': 'Poin...

            >>> # Retrieve the data of all the layers from the database
            >>> rutland_data = osmdb.fetch_osm_data(subrgn_name, layer_names=None, verbose=True)
            Fetching the data of "Rutland" ...
                "points" ... Done.
                "lines" ... Done.
                "multilinestrings" ... Done.
                "multipolygons" ... Done.
                "other_relations" ... Done.
                "buildings" ... Done.
                "landuse" ... Done.
                "natural" ... Done.
                "places" ... Done.
                "pofw" ... Done.
                "pois" ... Done.
                "railways" ... Done.
                "roads" ... Done.
                "traffic" ... Done.
                "transport" ... Done.
                "water" ... Done.
                "waterways" ... Done.
            >>> type(rutland_data)
            collections.OrderedDict
            >>> list(rutland_data.keys())
            ['points',
             'lines',
             'multilinestrings',
             'multipolygons',
             'other_relations',
             'buildings',
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

            >>> # Data of the 'waterways' layer
            >>> rutland_waterways = rutland_data['waterways']
            >>> rutland_waterways.head()
                osm_id  code  ...                                        coordinates  shape_type
            0  3701346  8102  ...  [(-0.7536654, 52.6495358), (-0.7536236, 52.649...           3
            1  3701347  8102  ...  [(-0.7948821, 52.6569468), (-0.7946128, 52.656...           3
            2  3707149  8103  ...  [(-0.7262381, 52.6790459), (-0.7258244, 52.680...           3
            3  3707303  8102  ...  [(-0.7213277, 52.6765954), (-0.7206778, 52.676...           3
            4  4470795  8101  ...  [(-0.4995349, 52.6418825), (-0.4984075, 52.642...           3
            [5 rows x 7 columns]

        Delete the test database and downloaded data files::

            >>> # Delete the database 'osmdb_test'
            >>> osmdb.drop_database(verbose=True)
            To drop the database "osmdb_test" from postgres:***@localhost:5432
            ? [No]|Yes: yes
            Dropping "osmdb_test" ... Done.

            >>> # Delete the downloaded data files
            >>> delete_dir(dat_dir, verbose=True)
            To delete the directory "tests\\osm_data\\" (Not empty)
            ? [No]|Yes: yes
            Deleting "tests\\osm_data\\" ... Done.

        .. seealso::

            - More details of the above data can be found in the examples for the methods
              :meth:`~pydriosm.ios.PostgresOSM.import_osm_data`
              and :meth:`~pydriosm.ios.PostgresOSM.import_subregion_osm_pbf`.
            - Similar examples about
              :ref:`fetching data from the database<quickstart-ios-fetch-data>`
              are available in :doc:`../quick-start`.
        """

        table_name_ = self.get_table_name(subregion_name, table_named_as_subregion)
        schema_names_ = validate_schema_names(layer_names, schema_named_as_layer)

        if not schema_names_:
            schema_names_ = list(dict.fromkeys(
                list(PBFReadParse.LAYER_GEOM.keys()) + sorted(list(SHPReadParse.LAYER_NAMES))))

        if any(self.subregion_table_exists(table_name_, x) for x in schema_names_):

            if verbose:
                print(f'Fetching the data of "{table_name_}" ... ')

            existing_schemas, layer_data = schema_names_.copy(), []

            for schema_name_ in schema_names_:
                if self.subregion_table_exists(table_name_, schema_name_):
                    tbl_name = f'"{schema_name_}"."{table_name_}"'
                    sql_query = f'SELECT * FROM {tbl_name}'

                    if verbose:
                        print(f'\t"{schema_name_}"', end=" ... ")

                    try:
                        if method is not None:
                            column_info_table = self.get_column_info(
                                table_name=table_name_, schema_name=schema_name_)

                            dtype_ = column_info_table['data_type']
                            dtype = dict(
                                zip(column_info_table['column_name'],
                                    map(self.DATA_TYPES.get, dtype_)))

                            layer_dat = self.read_sql_query(
                                sql_query=sql_query, method=method,
                                max_size_spooled=max_size_spooled, chunksize=chunk_size,
                                dtype=dtype, **kwargs)

                        else:
                            with self.engine.connect() as connection:
                                sql_query_ = sqlalchemy.text(sql_query)
                                layer_dat = pd.read_sql(
                                    sql_query_, con=connection, chunksize=chunk_size, **kwargs)

                        if isinstance(layer_dat, pd.DataFrame):
                            layer_dat = self.decode_pbf_layer(
                                layer_dat=layer_dat, decode_geojson=decode_geojson)

                        else:
                            lyr_dat_ = [
                                self.decode_pbf_layer(layer_dat=dat, decode_geojson=decode_geojson)
                                for dat in layer_dat]
                            layer_dat = pd.concat(lyr_dat_, ignore_index=True)

                        if sort_by:
                            sort_by_ = [sort_by] if isinstance(sort_by, str) else copy.copy(sort_by)
                            if all(x in layer_dat.columns for x in sort_by_):
                                layer_dat.sort_values(sort_by, ignore_index=True, inplace=True)

                        if verbose:
                            print("Done.")

                        layer_data.append(layer_dat)

                    except Exception as e:
                        print(f"Failed. {_format_err_msg(e)}")

                else:
                    existing_schemas.remove(schema_name_)

            osm_data = collections.OrderedDict(zip(existing_schemas, layer_data))

        else:
            if verbose:
                print("No data is available for the given input `subregion_name`.")
            osm_data = None

        return osm_data

    def drop_subregion_tables(self, subregion_names, schema_names=None,
                              table_named_as_subregion=False, schema_named_as_layer=False,
                              confirmation_required=True, verbose=False):
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

        **Examples**::

            >>> from pydriosm.ios import PostgresOSM
            >>> from pyhelpers.dirs import delete_dir

            >>> osmdb = PostgresOSM(database_name='osmdb_test')
            Password (postgres@localhost:5432): ***
            Creating a database: "osmdb_test" ... Done.
            Connecting postgres:***@localhost:5432/osmdb_test ... Successfully.

        Import example data into the database::

            >>> dat_dir = "tests\\osm_data"  # Specify a temporary data directory

            >>> # Import PBF data of 'Rutland' and 'Isle of Wight'
            >>> subrgn_name_1 = ['Rutland', 'Isle of Wight']
            >>> osmdb.import_subregion_osm_pbf(
            ...     subrgn_name_1, data_dir=dat_dir, expand=True, parse_geometry=True,
            ...     parse_properties=True, parse_other_tags=True, verbose=True)
            To import .osm.pbf data of the following geographic (sub)region(s):
                "Rutland"
                "Isle of Wight"
              into postgres:***@localhost:5432/osmdb_test
            ? [No]|Yes: yes
            Downloading "rutland-latest.osm.pbf"
                to "tests\\osm_data\\rutland\\" ... Done.
            Reading "tests\\osm_data\\rutland\\rutland-latest.osm.pbf" ... Done.
            Importing the data into table "Rutland" ...
                "points" ... Done. (<total of rows> features)
                "lines" ... Done. (<total of rows> features)
                "multilinestrings" ... Done. (<total of rows> features)
                "multipolygons" ... Done. (<total of rows> features)
                "other_relations" ... Done. (<total of rows> features)
            Downloading "isle-of-wight-latest.osm.pbf"
                to "tests\\osm_data\\isle-of-wight\\" ... Done.
            Reading "tests\\osm_data\\isle-of-wight\\isle-of-wight-latest.osm.pbf" ... Done.
            Importing the data into table "Isle of Wight" ...
                "points" ... Done. (<total of rows> features)
                "lines" ... Done. (<total of rows> features)
                "multilinestrings" ... Done. (<total of rows> features)
                "multipolygons" ... Done. (<total of rows> features)
                "other_relations" ... Done. (<total of rows> features)

            >>> # Change the data source
            >>> osmdb.data_source = 'BBBike'
            >>> subrgn_name_2 = 'London'

            >>> # An alternative way to import the shapefile data of 'London'
            >>> london_shp = osmdb.reader.read_shp_zip(
            ...     subrgn_name_2, data_dir=dat_dir, rm_extracts=True, download=True, verbose=True)
            Downloading "London.osm.shp.zip"
                to "tests\\osm_data\\london\\" ... Done.
            Extracting "tests\\osm_data\\london\\London.osm.shp.zip"
                to "tests\\osm_data\\london\\" ... Done.
            Reading the shapefile(s) at
                "tests\\osm_data\\london\\London-shp\\shape\\" ... Done.
            Deleting the extracts "tests\\osm_data\\london\\London-shp\\" ... Done.
            >>> osmdb.import_osm_data(london_shp, table_name=subrgn_name_2, verbose=True)
            To import data into table "London" at postgres:***@localhost:5432/osmdb_test
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

        Delete data of 'Rutland'::

            >>> subrgn_name = 'Rutland'

            >>> # Delete data of Rutland under the schemas 'buildings' and 'landuse'
            >>> lyr_name = ['buildings', 'landuse']
            >>> osmdb.drop_subregion_tables(subrgn_name, lyr_name, verbose=True)
            None of the data exists.

            >>> # Delete 'points' layer data of Rutland
            >>> lyr_name = 'points'
            >>> osmdb.drop_subregion_tables(subrgn_name, lyr_name, verbose=True)
            To drop table "points"."Rutland"
              from postgres:***@localhost:5432/osmdb_test
            ? [No]|Yes: yes
            Dropping the table ...
                "points"."Rutland" ... Done.

            >>> # Delete all available tables of Rutland
            >>> osmdb.drop_subregion_tables(subrgn_name, verbose=True)
            To drop table from postgres:***@localhost:5432/osmdb_test: "Rutland"
              under the schemas:
                "lines"
                "multilinestrings"
                "multipolygons"
                "other_relations"
            ? [No]|Yes: yes
            Dropping the tables ...
                "lines"."Rutland" ... Done.
                "multilinestrings"."Rutland" ... Done.
                "multipolygons"."Rutland" ... Done.
                "other_relations"."Rutland" ... Done.

        Delete 'buildings' and 'points' data of London and Isle of Wight::

            >>> # Delete 'buildings' and 'points' layers of London and Isle of Wight
            >>> subrgn_names = ['London', 'Isle of Wight']
            >>> lyr_names = ['buildings', 'points']
            >>> osmdb.drop_subregion_tables(subrgn_names, schema_names=lyr_names, verbose=True)
            To drop tables from postgres:***@localhost:5432/osmdb_test:
                "Isle of Wight"
                "London"
              under the schemas:
                "points"
                "buildings"
            ? [No]|Yes: yes
            Dropping the tables ...
                "points"."Isle of Wight" ... Done.
                "points"."London" ... Done.
                "buildings"."London" ... Done.

            >>> # Delete the rest of the data of London and Isle of Wight
            >>> osmdb.drop_subregion_tables(subrgn_names, verbose=True)
            To drop tables from postgres:***@localhost:5432/osmdb_test:
                "Isle of Wight"
                "London"
              under the schemas:
                "railways"
                "landuse"
                "other_relations"
                "lines"
                "multilinestrings"
                "waterways"
                "roads"
                "multipolygons"
                "natural"
                "places"
            ? [No]|Yes: yes
            Dropping the tables ...
                "railways"."London" ... Done.
                "landuse"."London" ... Done.
                "other_relations"."Isle of Wight" ... Done.
                "lines"."Isle of Wight" ... Done.
                "multilinestrings"."Isle of Wight" ... Done.
                "waterways"."London" ... Done.
                "roads"."London" ... Done.
                "multipolygons"."Isle of Wight" ... Done.
                "natural"."London" ... Done.
                "places"."London" ... Done.

        Delete the test database and downloaded data files::

            >>> # Delete the database 'osmdb_test'
            >>> osmdb.drop_database(verbose=True)
            To drop the database "osmdb_test" from postgres:***@localhost:5432
            ? [No]|Yes: yes
            Dropping "osmdb_test" ... Done.

            >>> # Delete the downloaded data files
            >>> delete_dir(dat_dir, verbose=True)
            To delete the directory "tests\\osm_data\\" (Not empty)
            ? [No]|Yes: yes
            Deleting "tests\\osm_data\\" ... Done.
        """

        table_names = self.reader.validate_input_dtype(subregion_names)
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

        if not existing_schema_names_:
            print("None of the data exists.")

        else:
            # existing_schema_names_.sort()
            _, schema_pl, prt_schema = self._msg_for_multi_items(
                existing_schema_names_, desc='schema', fmt='"{}"')
            _, tbl_pl, prt_tbl = self._msg_for_multi_items(table_names_, desc='table', fmt='"{}"')

            table_list = list(itertools.product(existing_schema_names_, table_names_))

            if len(table_list) == 1:
                cfm_msg = f'To drop {tbl_pl} {prt_schema}.{prt_tbl}\n' \
                          f'  from {self.address}\n?'
            else:
                cfm_msg = f'To drop {tbl_pl} from {self.address}: {prt_tbl}\n' \
                          f'  under the {schema_pl}: {prt_schema}\n?'

            if confirmed(cfm_msg, confirmation_required=confirmation_required):
                if_tables_exist = any(
                    self.table_exists(table_name=table, schema_name=schema)
                    for schema, table in table_list)

                if if_tables_exist:
                    if verbose:
                        drop_msg = "table" if len(table_list) == 1 else "tables"
                        print(f"Dropping the {drop_msg} ... ")

                    for schema, table in table_list:
                        schema_table = f'"{schema}"."{table}"'

                        if self.table_exists(table_name=table, schema_name=schema):
                            if verbose:
                                print(f"\t{schema_table}", end=" ... ")

                            try:
                                with self.engine.connect() as connection:
                                    query = sqlalchemy.text(
                                        f'DROP TABLE IF EXISTS {schema_table} CASCADE;')
                                    connection.execute(query)
                                if verbose:
                                    print("Done.")
                            except Exception as e:
                                print(f"Failed. {_format_err_msg(e)}")

                        else:  # The table doesn't exist
                            if verbose == 2:
                                print(f"\t{schema_table} does not exist.")
