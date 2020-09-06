""" A module for I/O and storage of OSM data extracts with PostgreSQL. """

import math

import shapely.wkt
import sqlalchemy.engine.reflection
from pyhelpers.sql import PostgreSQL
from pyhelpers.text import remove_punctuation

from pydriosm.reader import *


def validate_table_name(table_name):
    """
    Validate name of a table in (PostgreSQL) database.

    :param table_name: name (as input) of a table in a (PostgreSQL) database
    :type table_name: str
    :return: valid name of the table in the database
    :rtype: str

    **Examples**::

        from pydriosm.ios import validate_table_name

        subregion_name = 'rutland'
        table_name_ = validate_table_name(subregion_name)
        print(table_name_)
        # rutland

        subregion_name = 'Llanfairpwllgwyngyllgogerychwyrndrobwllllantysiliogogogoch, Wales'
        table_name_ = validate_table_name(subregion_name)
        print(table_name_)
        # Llanfairpwllgwyngyllgogerychwyrndrobwllllantysiliogogogoch_W..
    """

    table_name_ = remove_punctuation(table_name, rm_whitespace=True).replace(' ', '_')
    table_name_ = table_name_[:60] + '..' if len(table_name_) >= 63 else table_name_

    return table_name_


def get_default_pbf_layer_name(layer_name):
    """
    Validate name of a layer (as an input).

    :param layer_name: name of a layer (as an input)
    :type layer_name: str
    :return: valid name of the layer
    :rtype: str

    **Example**::

        from pydriosm.ios import get_default_pbf_layer_name

        layer_name = 'point'
        layer_name_ = get_default_pbf_layer_name(layer_name)

        print(layer_name_)
        # points
    """

    valid_layer_names = list(pbf_layer_feat_types_dict().keys())
    layer_name_ = find_similar_str(layer_name, valid_layer_names)

    return layer_name_


def validate_schema_names(schema_names=None, schema_named_as_pbf_layer=False):
    """
    Validate names of schemas in (PostgreSQL) database.

    :param schema_names: one or multiple names of layers, e.g. 'points', 'lines'
    :type schema_names: None, list
    :param schema_named_as_pbf_layer: whether to use default PBF layer name as the schema name, defaults to ``False``
    :type schema_named_as_pbf_layer: bool
    :return: valid names of the schemas in the database
    :rtype: list

    **Examples**::

        from pydriosm.ios import validate_schema_names

        schema_names_ = validate_schema_names()
        print(schema_names_)
        # ['points', 'lines', 'multilinestrings', 'multipolygons', 'other_relations']

        schema_names = ['point', 'polygon']
        schema_names_ = validate_schema_names(schema_names)
        print(schema_names_)
        # ['point', 'polygon']

        schema_named_as_pbf_layer = True
        schema_names_ = validate_schema_names(schema_names, schema_named_as_pbf_layer)
        print(schema_names_)
        # ['points', 'multipolygons']
    """

    valid_layer_names = list(pbf_layer_feat_types_dict().keys())

    if schema_names:
        # assertion_msg = "The argument `schema_names` could be one or a subset of {}.".format(valid_layer_names)
        if isinstance(schema_names, str):
            schema_names_ = [get_default_pbf_layer_name(schema_names) if schema_named_as_pbf_layer else schema_names]
            # assert schema_names_[0] in valid_layer_names, assertion_msg
        else:  # isinstance(schema_names, list) is True
            assert isinstance(schema_names, list)
            schema_names_ = [get_default_pbf_layer_name(x) for x in schema_names] if schema_named_as_pbf_layer \
                else schema_names
            # assert all(x in valid_layer_names for x in schema_names_), assertion_msg
    else:
        schema_names_ = valid_layer_names

    return schema_names_


class PostgresOSM:
    """
    A class representation of a tool for I/O and storage of OSM data extracts with PostgreSQL.

    :param host: host address, defaults to ``'localhost'`` (or ``'127.0.0.1'``)
    :type host: str, None
    :param port: port, defaults to ``5432``
    :type port: int, None
    :param username: database username, defaults to ``'postgres'``
    :type username: str, None
    :param password: database password, defaults to ``None``
    :type password: str, int, None
    :param database_name: database name, defaults to ``'postgres'``
    :type database_name: str
    :param confirm_new_db: whether to impose a confirmation to create a new database, defaults to ``False``
    :type confirm_new_db: bool
    :param data_source: source of data extracts, incl. 'GeoFabrik' and 'BBBike', defaults to ``'GeoFabrik'``
    :type data_source: str
    :param verbose: whether to print relevant information in console as the function runs, defaults to ``True``
    :type verbose: bool

    **Example**::

        from pydriosm.ios import PostgresOSM

        database_name = 'osm_testdb'
        data_source = 'GeoFabrik'

        osmdb = PostgresOSM(database_name=database_name, data_source=data_source)
        # Connecting to PostgreSQL database: postgres:***@localhost:5432/osm_testdb ... Successfully.
    """

    def __init__(self, host='localhost', port=5432, username='postgres', password=None, database_name='postgres',
                 confirm_new_db=False, data_source='GeoFabrik', verbose=True):
        """
        Constructor method.
        """

        valid_data_sources = ('GeoFabrik', 'BBBike')
        assert data_source in valid_data_sources, "The argument `method` must be '%s' or '%s'." % valid_data_sources

        self.PostgreSQL = PostgreSQL(host=host, port=port, username=username, password=password,
                                     database_name=database_name, confirm_new_db=confirm_new_db, verbose=verbose)

        self.database_info = self.PostgreSQL.database_info
        self.url = self.PostgreSQL.url
        self.address = self.PostgreSQL.address
        self.dialect = self.PostgreSQL.dialect
        self.backend = self.PostgreSQL.backend
        self.driver = self.PostgreSQL.driver
        self.user, self.host = self.PostgreSQL.user, self.PostgreSQL.host
        self.port = self.PostgreSQL.port
        self.database_name = self.PostgreSQL.database_name
        self.engine = self.PostgreSQL.engine
        self.connection = self.PostgreSQL.connection

        self.Downloaders = {'GeoFabrik': GeoFabrikDownloader(), 'BBBike': BBBikeDownloader()}
        self.Readers = {'GeoFabrik': GeoFabrikReader(), 'BBBike': BBBikeReader()}

        self.DataSource = data_source
        self.Downloader = self.Downloaders[self.DataSource]
        self.Name = copy.copy(self.Downloader.Name)
        self.URL = copy.copy(self.Downloader.URL)
        self.Reader = self.Readers[self.DataSource]

    def get_table_name_for_subregion(self, subregion_name, table_named_as_subregion=False):
        """
        Get the default table name (in PostgreSQL database) for a specific subregion.

        :param subregion_name: name (as input) of a subregion
        :type subregion_name: str
        :param table_named_as_subregion: whether to use subregion name as table name, defaults to ``False``
        :type table_named_as_subregion: bool
        :return: default name of the table in the database
        :rtype: str

        **Examples**::

            from pydriosm.ios import PostgresOSM

            osmdb = PostgresOSM(database_name='osm_testdb')
            # Connecting to PostgreSQL database: postgres:***@localhost:5432/osm_testdb ... Successfully.

            subregion_name = 'rutland'

            table_named_as_subregion = False
            table_name = osmdb.get_table_name_for_subregion(subregion_name)
            print(table_name)
            # rutland

            table_named_as_subregion = True
            table_name = osmdb.get_table_name_for_subregion(subregion_name, table_named_as_subregion)
            print(table_name)
            # Rutland
        """

        if table_named_as_subregion:
            if self.DataSource == 'GeoFabrik':
                subregion_name_ = self.Downloader.validate_input_subregion_name(subregion_name)
            else:  # self.DataSource == 'BBBike':
                subregion_name_, _, _, _ = self.Downloader.get_valid_download_info(subregion_name)
        else:
            subregion_name_ = subregion_name

        table_name = validate_table_name(subregion_name_)

        return table_name

    def subregion_table_exists(self, subregion_name, schema_name, table_named_as_subregion=False,
                               schema_named_as_pbf_layer=False):
        """
        Check if a table (for a subregion) exists.

        :param subregion_name: name of a subregion
        :type subregion_name: str
        :param schema_name: name of a schema, i.e. name of a PBF layer
        :type schema_name: str
        :param table_named_as_subregion: whether to use subregion name as table name, defaults to ``False``
        :type table_named_as_subregion: bool
        :param schema_named_as_pbf_layer: (for PBF) whether a schema is named as a layer name, defaults to ``False``
        :type schema_named_as_pbf_layer: bool
        :return: ``True`` if the table exists, ``False`` otherwise
        :rtype: bool

        **Examples**::

            from pydriosm.ios import PostgresOSM

            osmdb = PostgresOSM(database_name='osm_testdb')
            # Connecting to PostgreSQL database: postgres:***@localhost:5432/osm_testdb ... Successfully.

            subregion_name = 'rutland'
            schema_name = 'pt'

            schema_named_as_pbf_layer = False
            osmdb.subregion_table_exists(subregion_name, schema_name)
            # False if the table, pt.'Rutland', does not exist, True otherwise

            table_named_as_subregion = True
            schema_named_as_pbf_layer = True
            osmdb.subregion_table_exists(subregion_name, schema_name, table_named_as_subregion,
                                         schema_named_as_pbf_layer)
            # False if the table, points.'Rutland', does not exist, True otherwise
        """

        table_name_ = self.get_table_name_for_subregion(subregion_name, table_named_as_subregion)
        schema_name_ = get_default_pbf_layer_name(schema_name) if schema_named_as_pbf_layer else schema_name

        res = self.PostgreSQL.table_exists(table_name_, schema_name_)

        return res

    def get_subregion_table_column_info(self, subregion_name, schema_name, as_dict=True,
                                        table_named_as_subregion=False, schema_named_as_pbf_layer=False):
        """
        Get information about columns of a specific subregion's schema and table.

        :param schema_name: name of a schema (or name of a PBF layer)
        :type schema_name: str
        :param subregion_name: name of a table
        :type subregion_name: str
        :param as_dict: whether to return the column information as a dictionary, defaults to ``True``
        :type as_dict: bool
        :param table_named_as_subregion: whether to use subregion name as table name, defaults to ``False``
        :type table_named_as_subregion: bool
        :param schema_named_as_pbf_layer: (for PBF) whether a schema is named as a layer name, defaults to ``False``
        :type schema_named_as_pbf_layer: bool
        :return: information about each column of the given table
        :rtype: pandas.DataFrame, dict

        **Examples**::

            from pydriosm.ios import PostgresOSM

            osmdb = PostgresOSM(database_name='osm_testdb')
            # Connecting to PostgreSQL database: postgres:***@localhost:5432/osm_testdb ... Successfully.

            subregion_name = 'rutland'
            schema_name = 'points'

            as_dict = True
            info_tbl = osmdb.get_subregion_table_column_info(subregion_name, schema_name)
            print(info_tbl)
            # <dict>

            as_dict = False
            table_named_as_subregion = True
            schema_named_as_pbf_layer = False
            info_tbl = osmdb.get_subregion_table_column_info(subregion_name, schema_name, as_dict,
                                                             table_named_as_subregion,
                                                             schema_named_as_pbf_layer)
            print(info_tbl)
            # <pandas.DataFrame>
        """

        table_name_ = self.get_table_name_for_subregion(subregion_name, table_named_as_subregion)
        schema_name_ = get_default_pbf_layer_name(schema_name) if schema_named_as_pbf_layer else schema_name

        info_tbl = self.PostgreSQL.get_column_info(table_name=table_name_, schema_name=schema_name_, as_dict=as_dict)

        return info_tbl

    def dump_osm_pbf_layer(self, pbf_layer, table_name, schema_name, table_named_as_subregion=False,
                           schema_named_as_pbf_layer=False, if_exists='replace', force_replace=False, chunk_size=None,
                           verbose=False, **kwargs):
        """
        Import one layer of PBF (.osm.pbf) data into a database (being currently connected).

        :param pbf_layer: one layer of PBF data
        :type pbf_layer: pandas.DataFrame
        :param schema_name: name of a schema (or name of a PBF layer)
        :type schema_name: str
        :param table_name: name of a table
        :type table_name: str
        :param table_named_as_subregion: whether to use subregion name to be a table name, defaults to ``False``
        :type table_named_as_subregion: bool
        :param schema_named_as_pbf_layer: whether a schema is named as a layer name, defaults to ``False``
        :type schema_named_as_pbf_layer: bool
        :param if_exists: if the table already exists, to ``'replace'`` (default), ``'append'`` or ``'fail'``
        :type if_exists: str
        :param force_replace: whether to force to replace existing table, defaults to ``False``
        :type force_replace: bool
        :param chunk_size: the number of rows in each batch to be written at a time, defaults to ``None``
        :type chunk_size: int, None
        :param verbose: whether to print relevant information in console as the function runs, defaults to ``False``
        :type verbose: bool
        :param kwargs: optional parameters of `pyhelpers.sql.PostgreSQL.dump_data`_

        .. _`pyhelpers.sql.PostgreSQL.dump_data`:
            https://pyhelpers.readthedocs.io/en/latest/sql.html#sql-postgresql-dump-data

        **Example**::

            from pydriosm.ios import PostgresOSM

            osmdb = PostgresOSM(database_name='osm_testdb')
            # Connecting to PostgreSQL database: postgres:***@localhost:5432/osm_testdb ... Successfully.

            subregion_name = 'rutland'
            data_dir = "tests"
            verbose = True

            rutland_osm_pbf = osmdb.Reader.read_osm_pbf(subregion_name, data_dir, verbose=verbose)
            # Confirm to download the .osm.pbf data of "Rutland"? [No]|Yes: >? yes

            table_name = subregion_name
            schema_name = list(rutland_osm_pbf.keys())[0]  # 'points'
            table_named_as_subregion = True
            schema_named_as_pbf_layer = True
            if_exists = 'replace'
            chunk_size = None

            rutland_pbf_layer = rutland_osm_pbf[schema_name]
            osmdb.dump_osm_pbf_layer(rutland_pbf_layer, table_name, schema_name, verbose=verbose)
            # Dumping the data to points."rutland" at postgres:***@localhost:5432/osm_testdb ... Done.


            rutland_osm_pbf_ = osmdb.Reader.read_osm_pbf(subregion_name, data_dir=data_dir,
                                                         parse_raw_feat=True, transform_geom=True)
            rutland_pbf_layer_ = rutland_osm_pbf_[schema_name]
            osmdb.dump_osm_pbf_layer(rutland_pbf_layer_, table_name, schema_name, verbose=verbose)
            # The table points."Rutland" already exists and is replaced ...
            # Dumping the data to points."rutland" at postgres:***@localhost:5432/osm_testdb ... Done.
        """

        table_name_ = self.get_table_name_for_subregion(table_name, table_named_as_subregion)
        schema_name_ = get_default_pbf_layer_name(schema_name) if schema_named_as_pbf_layer else schema_name

        if pbf_layer.empty:
            self.PostgreSQL.dump_data(pbf_layer, table_name=table_name_, schema_name=schema_name_, if_exists=if_exists,
                                      force_replace=force_replace, verbose=verbose,
                                      method=self.PostgreSQL.psql_insert_copy, **kwargs)

        else:
            lyr_dat = pbf_layer.copy()

            if lyr_dat.shape[1] == 1:
                col_type = {lyr_dat.columns[0]: sqlalchemy.types.JSON}
            else:
                col_type = None
                if 'coordinates' in lyr_dat.columns:
                    if not isinstance(lyr_dat.coordinates[0], list):
                        lyr_dat.coordinates = lyr_dat.coordinates.map(lambda x: x.wkt)

            self.PostgreSQL.dump_data(lyr_dat, table_name=table_name_, schema_name=schema_name_, if_exists=if_exists,
                                      force_replace=force_replace, chunk_size=chunk_size, col_type=col_type,
                                      method=self.PostgreSQL.psql_insert_copy, verbose=verbose, **kwargs)

    def dump_osm_pbf(self, osm_pbf_data, table_name, schema_names=None, table_named_as_subregion=False,
                     schema_named_as_pbf_layer=False, if_exists='replace', force_replace=False, chunk_size=None,
                     verbose=False, **kwargs):
        """
        Import PBF (.osm.pbf) data into a database (being currently connected).

        :param osm_pbf_data: PBF (.osm.pbf) data of a subregion
        :type osm_pbf_data: dict
        :param table_name: name of a table
        :type table_name: str
        :param schema_names: names of schemas for each layer of the PBF data,
            if ``None`` (default), use the default layer names as schema names
        :type schema_names: None, list
        :param table_named_as_subregion: whether to use subregion name to be a table name, defaults to ``False``
        :type table_named_as_subregion: bool
        :param schema_named_as_pbf_layer: whether a schema is named as a layer name, defaults to ``False``
        :type schema_named_as_pbf_layer: bool
        :param if_exists: if the table already exists, to ``'replace'`` (default), ``'append'`` or ``'fail'``
        :type if_exists: str
        :param force_replace: whether to force to replace existing table, defaults to ``False``
        :type force_replace: bool
        :param chunk_size: the number of rows in each batch to be written at a time, defaults to ``None``
        :type chunk_size: int, None
        :param verbose: whether to print relevant information in console as the function runs, defaults to ``False``
        :type verbose: bool
        :param kwargs: optional parameters of ``.dump_osm_pbf_layer()``

        **Examples**::

            from pydriosm.ios import PostgresOSM

            osmdb = PostgresOSM(database_name='osm_testdb')
            # Connecting to PostgreSQL database: postgres:***@localhost:5432/osm_testdb ... Successfully.

            subregion_name = 'rutland'
            rutland_osm_pbf = osmdb.Reader.read_osm_pbf(subregion_name, data_dir="tests", verbose=True)

            osmdb.dump_osm_pbf(rutland_osm_pbf, table_name=subregion_name, verbose=True)
            # Dumping PBF data of "rutland" to postgres:***@localhost:5432/osm_testdb ...
            #         points ... Done: <total of rows> features.
            #         lines ... Done: <total of rows> features.
            #         multilinestrings ... Done: <total of rows> features.
            #         multipolygons ... Done: <total of rows> features.
            #         other_relations ... Done: <total of rows> features.


            rutland_osm_pbf_ = osmdb.Reader.read_osm_pbf(subregion_name, data_dir="tests",
                                                         parse_raw_feat=True, transform_geom=True,
                                                         transform_other_tags=True)

            schema_names = ['test0', 'test1', 'test2', 'test3', 'test4']
            osmdb.dump_osm_pbf(rutland_osm_pbf_, table_name=subregion_name, schema_names=schema_names,
                               table_named_as_subregion=True, verbose=True)
            # Dumping PBF data of "Rutland" to postgres:***@localhost:5432/osm_testdb ...
            #         test0 ... Done: <total of rows> features.
            #         test1 ... Done: <total of rows> features.
            #         test2 ... Done: <total of rows> features.
            #         test3 ... Done: <total of rows> features.
            #         test4 ... Done: <total of rows> features.

            # To drop all the above "test*" schemas:
            # osmdb.PostgreSQL.drop_schema(*schema_names, verbose=True)
            # Confirmed to drop the schemas "test0", "test1", "test2", "test3" and "test4"
            #   from postgres:***@localhost:5432/osm_testdb? [No]|Yes: >? yes
            # Dropping the schemas "test0", "test1", "test2", "test3" and "test4" ... Done.
        """

        if schema_names:
            assert isinstance(schema_names, list)
            assert len(schema_names) == len(osm_pbf_data.keys())
            data_items = zip(schema_names, osm_pbf_data.values())
        else:
            data_items = osm_pbf_data.items()

        table_name_ = self.get_table_name_for_subregion(table_name, table_named_as_subregion)

        print("Dumping PBF data of \"{}\" to {} ... ".format(table_name_, self.address)) if verbose else ""
        for geom_type, pbf_layer in data_items:

            print("        {}".format(geom_type), end=" ... ") if verbose else ""

            if pbf_layer.empty:
                print("The layer is empty. The corresponding table in the database is thus empty.") if verbose else ""

            try:
                self.dump_osm_pbf_layer(pbf_layer, schema_name=geom_type, table_name=table_name_,
                                        table_named_as_subregion=table_named_as_subregion,
                                        schema_named_as_pbf_layer=schema_named_as_pbf_layer, if_exists=if_exists,
                                        force_replace=force_replace, chunk_size=chunk_size, verbose=False, **kwargs)
                print("Done: {} features.".format(len(pbf_layer))) if verbose else ""

            except Exception as e:
                print("Failed. {}".format(e))

            del pbf_layer
            gc.collect()

    def dump_geofabrik_subregion_osm_pbf(self, subregion_names,
                                         data_dir=None, update_osm_pbf=False, if_exists='replace',
                                         chunk_size_limit=50,
                                         parse_raw_feat=False, transform_geom=False, transform_other_tags=False,
                                         pickle_pbf_file=False, rm_osm_pbf=False, confirmation_required=True,
                                         verbose=False, **kwargs):
        """
        Import data of selected or all (sub)regions, which do not have (sub-)subregions, into database
        (being currently connected).

        :param subregion_names: name(s) of subregion(s)
        :type subregion_names: str, list, None
        :param data_dir: directory where the .osm.pbf data file is located/saved; if ``None``, the default directory
        :type data_dir: str, None
        :param update_osm_pbf: whether to check to update .osm.pbf data file (if available), defaults to ``False``
        :type update_osm_pbf: bool
        :param if_exists: if the table already exists, to ``'replace'`` (default), ``'append'`` or ``'fail'``
        :type if_exists: str
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
        :param pickle_pbf_file: whether to save the .pbf data as a .pickle file, defaults to ``False``
        :type pickle_pbf_file: bool
        :param rm_osm_pbf: whether to delete the downloaded .osm.pbf file, defaults to ``False``
        :type rm_osm_pbf: bool
        :param confirmation_required: whether to prompt a message for confirmation to proceed, defaults to ``True``
        :type confirmation_required: bool
        :param verbose: whether to print relevant information in console as the function runs, defaults to ``False``
        :type verbose: bool, int

        **Examples**:

            from pydriosm.ios import PostgresOSM

            osmdb = PostgresOSM(database_name='osm_testdb')
            # Connecting to PostgreSQL database: postgres:***@localhost:5432/osm_testdb ... Successfully.

            subregion_name = 'rutland'
            pickle_pbf_file = True
            verbose = True
            osmdb.dump_geofabrik_subregion_osm_pbf(subregion_name, data_dir="tests", verbose=verbose)
            # To import GeoFabrik OSM data extracts of the following subregions to PostgreSQL?
            # Rutland?
            #  [No]|Yes: >? yes
            # Dumping PBF data of "Rutland" to postgres:***@localhost:5432/osm_testdb ...
            #         points ... Done: <total of rows> features.
            #         lines ... Done: <total of rows> features.
            #         multilinestrings ... Done: <total of rows> features.
            #         multipolygons ... Done: <total of rows> features.
            #         other_relations ... Done: <total of rows> features.
            # Finished.


            subregion_names = osmdb.Downloader.retrieve_names_of_subregions_of('England')[0:2]
            parse_raw_feat = True
            transform_geom = True
            transform_other_tags = False
            osmdb.dump_geofabrik_subregion_osm_pbf(subregion_names, data_dir="tests",
                                                   parse_raw_feat=True, transform_geom=transform_geom,
                                                   transform_other_tags=transform_other_tags,
                                                   verbose=verbose, pickle_pbf_file=pickle_pbf_file)
            # To import GeoFabrik OSM data extracts of the following subregions to PostgreSQL?
            # Bedfordshire,
            # Berkshire?
            #  [No]|Yes: >? yes
            # Dumping PBF data of "Bedfordshire" to postgres:***@localhost:5432/osm_testdb ...
            #         points ... Done: <total of rows> features.
            #         lines ... Done: <total of rows> features.
            #         multilinestrings ... Done: <total of rows> features.
            #         multipolygons ... Done: <total of rows> features.
            #         other_relations ... Done: <total of rows> features.
            # Saving "bedfordshire-latest.pickle" at "..\\tests" ... Successfully.
            # Dumping PBF data of "Berkshire" to postgres:***@localhost:5432/osm_testdb ...
            #         points ... Done: <total of rows> features.
            #         lines ... Done: <total of rows> features.
            #         multilinestrings ... Done: <total of rows> features.
            #         multipolygons ... Done: <total of rows> features.
            #         other_relations ... Done: <total of rows> features.
            # Saving "berkshire-latest.pickle" at "..\\tests" ... Successfully.
            # Finished.
        """

        if subregion_names is None:
            subregion_names = self.Downloader.get_subregion_name_list()
            confirm_msg = "To import GeoFabrik OSM data extracts of all subregions to PostgreSQL?"
        else:
            if isinstance(subregion_names, str):
                subregion_names = [subregion_names]
            subregion_names = self.Downloader.retrieve_names_of_subregions_of(*subregion_names)
            confirm_msg = \
                "To import GeoFabrik OSM data extracts of the following subregions to PostgreSQL?\n{}?\n".format(
                    ",\n".join(subregion_names))

        if confirmed(confirm_msg, confirmation_required=confirmation_required):

            err_subregion_names = []
            for subregion_name in subregion_names:
                default_pbf_filename, default_path_to_pbf = \
                    self.Downloader.get_default_path_to_osm_file(subregion_name, osm_file_format=".osm.pbf")
                if not data_dir:  # Go to default file path
                    path_to_osm_pbf = default_path_to_pbf
                else:
                    osm_pbf_dir = validate_input_data_dir(data_dir)
                    path_to_osm_pbf = os.path.join(osm_pbf_dir, default_pbf_filename)

                self.Downloader.download_subregion_osm_file(subregion_name, osm_file_format=".osm.pbf",
                                                            download_dir=data_dir,
                                                            update=update_osm_pbf, confirmation_required=False,
                                                            verbose=False)

                file_size_in_mb = round(os.path.getsize(path_to_osm_pbf) / (1024 ** 2), 1)

                try:
                    if file_size_in_mb <= chunk_size_limit:
                        # subregion_osm_pbf = self.Reader.read_osm_pbf(subregion_name, data_dir=data_dir,
                        #                                              chunk_size_limit=chunk_size_limit,
                        #                                              parse_raw_feat=parse_raw_feat,
                        #                                              transform_geom=transform_geom,
                        #                                              transform_other_tags=transform_other_tags,
                        #                                              update=False,
                        #                                              download_confirmation_required=False,
                        #                                              pickle_it=pickle_pbf_file, rm_osm_pbf=False,
                        #                                              verbose=verbose)

                        number_of_chunks = get_number_of_chunks(path_to_osm_pbf, chunk_size_limit)

                        subregion_osm_pbf = parse_osm_pbf(path_to_osm_pbf, number_of_chunks,
                                                          parse_raw_feat=parse_raw_feat, transform_geom=transform_geom,
                                                          transform_other_tags=transform_other_tags)

                        if subregion_osm_pbf is not None:
                            self.dump_osm_pbf(osm_pbf_data=subregion_osm_pbf, table_name=subregion_name,
                                              if_exists=if_exists, verbose=verbose, **kwargs)

                            if pickle_pbf_file:
                                save_pickle(subregion_osm_pbf, path_to_osm_pbf.replace(".osm.pbf", ".pickle"),
                                            verbose=verbose)

                            del subregion_osm_pbf
                            gc.collect()

                    else:
                        if verbose:
                            print("Parsing and importing the data of \"{}\" feature-wisely to {} ... ".format(
                                subregion_name, self.address))

                        # Reference: https://gdal.org/python/osgeo.ogr.Feature-class.html
                        raw_osm_pbf = ogr.Open(path_to_osm_pbf)
                        layer_count = raw_osm_pbf.GetLayerCount()

                        layer_names, all_layer_data, layer_data = [], [], None

                        for i in range(layer_count):
                            layer = raw_osm_pbf.GetLayerByIndex(i)  # Hold the i-th layer
                            layer_name = layer.GetName()

                            if pickle_pbf_file:
                                layer_names.append(layer_name)

                            print("                       {}".format(layer_name), end=" ... ") if verbose else ""
                            try:
                                features = [feature for _, feature in enumerate(layer)]
                                feats_no, chunks_no = len(features), math.ceil(file_size_in_mb / chunk_size_limit)
                                feats = split_list(lst=features, num_of_sub=chunks_no)

                                del features
                                gc.collect()

                                if self.subregion_table_exists(subregion_name, layer_name) and if_exists == 'replace':
                                    self.drop_subregion_osm_pbf_table(subregion_name, layer_name,
                                                                      confirmation_required=False)

                                all_lyr_dat = []
                                # Loop through all available features
                                for feat in feats:
                                    if parse_raw_feat:
                                        lyr_dat = pd.DataFrame(f.ExportToJson(as_object=True) for f in feat)
                                        lyr_dat = parse_osm_pbf_layer(pbf_layer_data=lyr_dat, geo_typ=layer_name,
                                                                      transform_geom=transform_geom,
                                                                      transform_other_tags=transform_other_tags)
                                    else:
                                        lyr_dat = pd.DataFrame(f.ExportToJson() for f in feat)
                                        lyr_dat.columns = ['{}_data'.format(layer_name)]

                                    if_exists_ = if_exists if if_exists == 'fail' else 'append'
                                    self.dump_osm_pbf_layer(pbf_layer=lyr_dat, table_name=subregion_name,
                                                            schema_name=layer_name, if_exists=if_exists_)

                                    if pickle_pbf_file:
                                        all_lyr_dat.append(lyr_dat)

                                    del lyr_dat
                                    gc.collect()

                                if pickle_pbf_file:
                                    all_layer_data.append(pd.concat(all_lyr_dat, ignore_index=True, sort=False))

                                print("Done: {} features.".format(feats_no)) if verbose else ""

                            except Exception as e:
                                print("Failed. {}".format(e))

                        raw_osm_pbf.Release()

                        del raw_osm_pbf
                        gc.collect()

                        if pickle_pbf_file:
                            save_pickle(dict(zip(layer_names, all_layer_data)),
                                        path_to_osm_pbf.replace(".osm.pbf", ".pickle"), verbose=verbose)

                    if rm_osm_pbf:
                        remove_subregion_osm_file(path_to_osm_pbf, verbose=verbose)

                except Exception as e:
                    print(e)
                    err_subregion_names.append(subregion_name)

            if len(err_subregion_names) == 0:
                print("Finished. ") if verbose else ""
            else:
                print("Errors occurred when parsing data of the following subregion(s):")
                print(*err_subregion_names, sep=", ")

    def read_osm_pbf(self, table_name, schema_names=None, table_named_as_subregion=False,
                     schema_named_as_pbf_layer=False, chunk_size=None, method='spooled_tempfile', max_size_spooled=1,
                     decode_json=False, decode_wkt=False, decode_other_tags=False, **kwargs):
        """
        Read PBF (.osm.pbf) data (of one or more layers) of a subregion.

        See also [`ROP-1 <https://pyhelpers.readthedocs.io/en/latest/sql.html#sql-postgresql-read-sql-query>`_]

        :param table_name: name of a table
        :type table_name: str
        :param schema_names: names of schemas for each layer of the PBF data,
            if ``None`` (default), use the default layer names as schema names
        :type schema_names: None, list
        :param table_named_as_subregion: whether to use subregion name to be a table name, defaults to ``False``
        :type table_named_as_subregion: bool
        :param schema_named_as_pbf_layer: whether a schema is named as a layer name, defaults to ``False``
        :type schema_named_as_pbf_layer: bool
        :param chunk_size: the number of rows in each batch to be written at a time, defaults to ``None``
        :type chunk_size: int, None
        :param method: method to be used for buffering temporary data, defaults to ``'spooled_tempfile'``
        :type method: str, None
        :param max_size_spooled: ``max_size_spooled`` of `pyhelpers.sql.PostgreSQL.read_sql_query`_,
            defaults to ``1`` (in gigabyte)
        :type max_size_spooled: int, float
        :param decode_json: whether to decode raw JSON (when it is raw feature data), defaults to ``False``
        :type decode_json: bool
        :param decode_wkt: whether to decode ``'coordinates'`` (if available and) if it is a wkt, defaults to ``False``
        :type decode_wkt: bool
        :param decode_other_tags: whether to decode ``'other_tags'`` (if available), defaults to ``False``
        :type decode_other_tags: bool
        :return: PBF (.osm.pbf) data
        :rtype: dict

        .. _`pyhelpers.sql.PostgreSQL.read_sql_query`:
            https://pyhelpers.readthedocs.io/en/latest/sql.html#sql-postgresql-read-sql-query

        **Example**::

            from pydriosm.ios import PostgresOSM

            osmdb = PostgresOSM(database_name='osm_testdb')
            # Connecting to PostgreSQL database: postgres:***@localhost:5432/osm_testdb ... Successfully.

            table_name = 'rutland'

            chunk_size = None
            table_named_as_subregion = True
            method = 'spooled_tempfile'
            max_size_spooled = 1

            schema_names = None
            decode_json = False
            decode_wkt = False
            decode_other_tags = False
            osm_pbf_data = osmdb.read_osm_pbf(table_name, schema_names)

            print(osm_pbf_data)
            # {'points': <data frame>,
            #  'lines': <data frame>,
            #  'multilinestrings': <data frame>,
            #  'multipolygons': <data frame>,
            #  'other_relations': <data frame>}

            schema_names = ['points', 'multipolygons']
            table_named_as_subregion = True
            schema_named_as_pbf_layer = True
            decode_json = True
            decode_wkt = True
            decode_other_tags = True
            osm_pbf_data = osmdb.read_osm_pbf(table_name, schema_names, table_named_as_subregion,
                                              schema_named_as_pbf_layer, decode_json=decode_json,
                                              decode_wkt=decode_wkt, decode_other_tags=decode_other_tags)

            print(osm_pbf_data)
            # {'points': <data frame>,
            #  'multipolygons': <data frame>}
        """

        table_name_ = self.get_table_name_for_subregion(table_name, table_named_as_subregion)

        schema_names_ = validate_schema_names(schema_names, schema_named_as_pbf_layer)

        layer_data = []
        for schema_name in schema_names_:

            sql_query = 'SELECT * FROM {}."{}"'.format(schema_name, table_name_)
            if method:
                lyr_dat = self.PostgreSQL.read_sql_query(sql_query=sql_query, method=method,
                                                         max_size_spooled=max_size_spooled, **kwargs)
            else:
                lyr_dat = pd.read_sql(sql_query, self.engine, chunksize=chunk_size, **kwargs)

            lyr_dat.replace({np.nan: None}, inplace=True)

            if lyr_dat.shape[1] == 1:
                geo_typ = lyr_dat.columns[0].rstrip('_data')

                if decode_wkt or decode_other_tags:
                    lyr_dat = pd.DataFrame.from_records(lyr_dat.iloc[:, 0].map(rapidjson.loads))
                    lyr_dat = parse_osm_pbf_layer(lyr_dat, geo_typ, decode_wkt, decode_other_tags)
                else:
                    if decode_json:
                        lyr_dat = pd.DataFrame.from_records(lyr_dat.iloc[:, 0].map(rapidjson.loads))

            else:
                if decode_wkt:
                    try:
                        lyr_dat.coordinates = lyr_dat.coordinates.map(eval)
                    except SyntaxError:
                        lyr_dat.coordinates = lyr_dat.coordinates.map(shapely.wkt.loads)

                if decode_other_tags:
                    lyr_dat.other_tags = lyr_dat.other_tags.map(lambda x: x if x is None else eval(x))

            if 'id' in lyr_dat.columns:
                lyr_dat.sort_values('id', inplace=True)
                lyr_dat.index = range(len(lyr_dat))

            layer_data.append(lyr_dat)

        osm_pbf_data = dict(zip(schema_names_, layer_data))

        return osm_pbf_data

    def drop_subregion_osm_pbf_table(self, subregion_table_names, schema_names=None, table_named_as_subregion=False,
                                     schema_named_as_pbf_layer=False, confirmation_required=True, verbose=False):
        """
        Delete all or specific schemas/layers subregion data from the database (being currently connected).

        :param subregion_table_names: name of table for a subregion (or name of a subregion)
        :type subregion_table_names: str
        :param schema_names: names of schemas for each layer of the PBF data,
            if ``None`` (default), use the default layer names as schema names
        :type schema_names: None, list
        :param table_named_as_subregion: whether to use subregion name to be a table name, defaults to ``False``
        :type table_named_as_subregion: bool
        :param schema_named_as_pbf_layer: whether a schema is named as a layer name, defaults to ``False``
        :type schema_named_as_pbf_layer: bool
        :param confirmation_required: whether to prompt a message for confirmation to proceed, defaults to ``True``
        :type confirmation_required: bool
        :param verbose: whether to print relevant information in console as the function runs, defaults to ``False``
        :type verbose: bool, int

        **Examples**::

            from pydriosm.ios import PostgresOSM

            osmdb = PostgresOSM(database_name='osm_testdb')
            # Connecting to PostgreSQL database: postgres:***@localhost:5432/osm_testdb ... Successfully.

            subregion_table_name = 'rutland'
            schema_names = None
            osmdb.drop_subregion_osm_pbf_table(subregion_table_name, verbose=True)
            # Confirmed to drop the schemas "points", "lines", "multilinestrings", "multipolygons" and "other_relations"
            # for table "rutland" at postgres:***@localhost:5432/osm_testdb [No]|Yes: >? yes
            # Dropping points."rutland" ... The table does not exist.
            # Dropping lines."rutland" ... The table does not exist.
            # Dropping multilinestrings."rutland" ... The table does not exist.
            # Dropping multipolygons."rutland" ... The table does not exist.
            # Dropping other_relations."rutland" ... The table does not exist.
            # Finished.


            subregion_table_names = ['rutland', 'berkshire']
            schema_names = ['points', 'other_relations']
            table_named_as_subregion = True
            schema_named_as_pbf_layer = True
            osmdb.drop_subregion_osm_pbf_table(subregion_table_names, schema_names=schema_names,
                                               table_named_as_subregion=table_named_as_subregion,
                                               schema_named_as_pbf_layer=schema_named_as_pbf_layer,
                                               verbose=True)
            # Confirmed to drop the schemas "points" and "other_relations"
            # for tables "Rutland" and "Berkshire" at postgres:***@localhost:5432/osm_testdb [No]|Yes:
            #   >? yes
            # Dropping points."Rutland" ... Done.
            # Dropping other_relations."Rutland" ... Done.
            # Dropping points."Berkshire" ... Done.
            # Dropping other_relations."Berkshire" ... Done.
            # Finished.
        """

        table_names_ = [self.get_table_name_for_subregion(tbl_name, table_named_as_subregion)
                        for tbl_name in
                        ([subregion_table_names] if isinstance(subregion_table_names, str) else subregion_table_names)]
        _, tbls_msg = self.PostgreSQL.printing_messages_for_multi_names(*table_names_, desc='table')

        schema_names_ = validate_schema_names(schema_names, schema_named_as_pbf_layer)
        _, schemas_msg = self.PostgreSQL.printing_messages_for_multi_names(*schema_names_, desc='schema')

        if confirmed("Confirmed to drop the {}\nfor {} at {}".format(schemas_msg, tbls_msg, self.address),
                     confirmation_required=confirmation_required):
            import itertools

            tables_ = ['{}.\"{}\"'.format(s, t) for t, s in list(itertools.product(table_names_, schema_names_))]

            for table_ in tables_:
                print("Dropping {}".format(table_), end=" ... ") if verbose else ""
                if self.subregion_table_exists(table_.split('.')[1], table_.split('.')[0]):
                    try:
                        self.engine.execute('DROP TABLE IF EXISTS {} CASCADE;'.format(table_))
                        print("Done. ") if verbose else ""
                    except Exception as e:
                        print("Failed. {}".format(e))
                else:
                    print("The table does not exist. ") if verbose else ""
            print("Finished. ") if verbose else ""


# class GeoFabrikIOS:
#     """
#     A class representation of a tool for storage of GeoFabrik data extracts with PostgreSQL.
#     """
#
#     def __init__(self):
#         """
#         Constructor method.
#         """
#         self.Downloader = GeoFabrikDownloader()
#         self.Reader = GeoFabrikReader()
#         self.Name = copy.copy(self.Downloader.Name)
#         self.URL = copy.copy(self.Downloader.URL)
#
#
# class BBBikeIOS:
#     """
#     A class representation of a tool for storage of BBBike data extracts with PostgreSQL.
#     """
#
#     def __init__(self):
#         """
#         Constructor method.
#         """
#         self.Downloader = BBBikeDownloader()
#         self.Reader = BBBikeReader()
#         self.Name = copy.copy(self.Downloader.Name)
#         self.URL = copy.copy(self.Downloader.URL)
