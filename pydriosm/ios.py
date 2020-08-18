""" Data storage with PostgreSQL """

import gc
import getpass
import math
import os
import tempfile
import time

import ogr
import pandas as pd
import rapidjson
import shapely.wkt
import sqlalchemy
import sqlalchemy.engine.reflection
import sqlalchemy.engine.url
import sqlalchemy_utils
from pyhelpers.dir import regulate_input_data_dir
from pyhelpers.ops import confirmed
from pyhelpers.ops import split_list

from pydriosm.downloader import GeoFabrikDownloader
from pydriosm.utils import remove_subregion_osm_file

geofabrik_downloader = GeoFabrikDownloader()


def regulate_table_name(table_name, subregion_name_as_table_name=True):
    """
    :param table_name:
    :type table_name: str
    :param subregion_name_as_table_name: defaults to ``True``
    :type subregion_name_as_table_name: bool
    :return:
    :rtype: str
    """

    if subregion_name_as_table_name:
        table_name = geofabrik_downloader.regulate_input_subregion_name(table_name)

    table_name_ = table_name[:60] + '..' if len(table_name) >= 63 else table_name
    table_name_ = table_name_.replace("'", "_")

    return table_name_


class PostgresOSM:
    def __init__(self, username='postgres', password=None, host='localhost', port=5432, database_name='postgres',
                 cfm_reqd_cndb=False, verbose=True):
        """
        It requires to be connected to the database server so as to execute the "CREATE DATABASE" command.
        A default database named "postgres" exists already, which is created by the "initdb" command when the data
        storage area is initialised.
        Prior to create a customised database, it requires to connect "postgres" in the first instance.
        """
        self.database_info = {'drivername': 'postgresql+psycopg2',
                              'username': username,  # postgres
                              'password': password if password else getpass.getpass(
                                  "Password ({}@{}:{}): ".format(username, host, port)),
                              'host': host,  # default: localhost
                              'port': port,  # 5432 (default by installation).
                              'database': database_name}

        # The typical form of a database URL is: url = backend+driver://username:password@host:port/database_name
        self.url = sqlalchemy.engine.url.URL(**self.database_info)

        self.dialect = self.url.get_dialect()
        self.backend = self.url.get_backend_name()
        self.driver = self.url.get_driver_name()
        self.user, self.host = self.url.username, self.url.host
        self.port = self.url.port
        self.database_name = self.database_info['database']

        if not sqlalchemy_utils.database_exists(self.url):
            if confirmed("The database \"{}\" does not exist. Proceed by creating it?".format(self.database_name),
                         confirmation_required=cfm_reqd_cndb):
                if verbose:
                    print("Connecting to PostgreSQL database: {}@{}:{} ... ".format(
                        self.database_name, self.host, self.port), end="")
                sqlalchemy_utils.create_database(self.url)
        else:
            if verbose:
                print("Connecting to PostgreSQL database: {}@{}:{} ... ".format(
                    self.database_name, self.host, self.port), end="")
        try:
            # Create a SQLAlchemy connectable
            self.engine = sqlalchemy.create_engine(self.url, isolation_level='AUTOCOMMIT')
            self.connection = self.engine.raw_connection()
            print("Successfully.") if verbose else ""
        except Exception as e:
            print("Failed. CAUSE: \"{}\".".format(e))

    # Check if a database exists
    def database_exists(self, database_name=None):
        """
        :param database_name: [str; None (default)] name of a database
        :return: [bool]
        """
        database_name_ = self.database_name if database_name is None else database_name
        result = self.engine.execute("SELECT EXISTS("
                                     "SELECT datname FROM pg_catalog.pg_database "
                                     "WHERE datname='{}');".format(database_name_))
        return result.fetchone()[0]

    # Establish a connection to the specified database (named e.g. 'OSM_Geofabrik_PBF')
    def connect_database(self, database_name='OSM_Geofabrik_PBF'):
        """
        :param database_name: [str] (default: 'OSM_Geofabrik_PBF') name of a database
        """
        self.database_name = database_name
        self.database_info['database'] = self.database_name
        self.url = sqlalchemy.engine.url.URL(**self.database_info)
        if not sqlalchemy_utils.database_exists(self.url):
            sqlalchemy_utils.create_database(self.url)
        self.engine = sqlalchemy.create_engine(self.url, isolation_level='AUTOCOMMIT')
        self.connection = self.engine.raw_connection()

    # An alternative to sqlalchemy_utils.create_database()
    def create_database(self, database_name='OSM_Geofabrik_PBF', verbose=False):
        """
        :param database_name: [str] (default: 'OSM_Geofabrik_PBF') name of a database
        :param verbose: [bool] (default: False)

        from psycopg2 import OperationalError
        try:
            self.engine.execute('CREATE DATABASE "{}"'.format(database_name))
        except OperationalError:
            self.engine.execute(
                'SELECT *, pg_terminate_backend(pid) FROM pg_stat_activity WHERE username=\'postgres\';')
            self.engine.execute('CREATE DATABASE "{}"'.format(database_name))
        """
        if not self.database_exists(database_name):
            print("Creating a database \"{}\" ... ".format(database_name), end="") if verbose else ""
            self.disconnect_database()
            self.engine.execute('CREATE DATABASE "{}";'.format(database_name))
            print("Done.") if verbose else ""
        else:
            print("The database already exists.") if verbose else ""
        self.connect_database(database_name=database_name)

    # Get size of a database
    def get_database_size(self, database_name=None):
        """
        :param database_name: [str; None (default)] name of a database; if None, the current connected database is used
        :return: [str] size of the database
        """
        db_name = '\'{}\''.format(database_name) if database_name else 'current_database()'
        db_size = self.engine.execute('SELECT pg_size_pretty(pg_database_size({})) AS size;'.format(db_name))
        return db_size.fetchone()[0]

    # Kill the connection to the specified database
    def disconnect_database(self, database_name=None, verbose=False):
        """
        :param database_name: [str; None (default)] name of database to disconnect from
        :param verbose: [bool] (default: False)

        Alternative way:
        SELECT
            pg_terminate_backend(pg_stat_activity.pid)
        FROM
            pg_stat_activity
        WHERE
            pg_stat_activity.datname = database_name AND pid <> pg_backend_pid();
        """
        db_name = self.database_name if database_name is None else database_name
        print("Disconnecting the database \"{}\" ... ".format(db_name), end="") if verbose else ""
        try:
            self.connect_database('postgres')
            self.engine.execute('REVOKE CONNECT ON DATABASE {} FROM PUBLIC, postgres;'.format(db_name))
            self.engine.execute(
                'SELECT pg_terminate_backend(pid) '
                'FROM pg_stat_activity '
                'WHERE datname = \'{}\' AND pid <> pg_backend_pid();'.format(db_name))
            print("Done.") if verbose else ""
        except Exception as e:
            print("Failed. CAUSE: \"{}\"".format(e))

    # Kill connections to all other databases
    def disconnect_all_other_databases(self):
        self.connect_database(database_name='postgres')
        self.engine.execute('SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE pid <> pg_backend_pid();')

    # Drop the specified database
    def drop_database(self, database_name=None, confirmation_required=True, verbose=False):
        """
        :param database_name: [str; None (default)] database to be disconnected; if None, to disconnect the current one
        :param confirmation_required: [bool] (default: True)
        :param verbose: [bool] (default: False)
        """
        db_name = self.database_name if database_name is None else database_name
        if confirmed("Confirmed to drop the database \"{}\" for {}@{}?".format(db_name, self.user, self.host),
                     confirmation_required=confirmation_required):
            self.disconnect_database(db_name)
            try:
                print("Dropping the database \"{}\" ... ".format(db_name), end="") if verbose else ""
                self.engine.execute('DROP DATABASE IF EXISTS "{}"'.format(db_name))
                print("Done.") if verbose else ""
            except Exception as e:
                print("Failed. CAUSE: \"{}\"".format(e))

    # Check if a database exists
    def schema_exists(self, schema_name):
        """
        :param schema_name: [str] name of a schema
        :return: [bool]
        """
        result = self.engine.execute("SELECT EXISTS("
                                     "SELECT schema_name FROM information_schema.schemata "
                                     "WHERE schema_name='{}');".format(schema_name))
        return result.fetchone()[0]

    # Create a new schema in the database being currently connected
    def create_schema(self, schema_name, verbose=False):
        """
        :param schema_name: [str] name of a schema
        :param verbose: [bool] (default: False)
        """
        try:
            print("Creating a schema \"{}\" ... ".format(schema_name), end="") if verbose else ""
            self.engine.execute('CREATE SCHEMA IF NOT EXISTS "{}";'.format(schema_name))
            print("Done.") if verbose else ""
        except Exception as e:
            print("Failed. CAUSE: \"{}\"".format(e))

    # Formulate printing message for multiple names
    def printing_messages_for_multi_names(self, *multi_names, desc='schema'):
        """
        :param multi_names: [str; iterable]
        :param desc: [str] (default: 'schema')
        :return: [tuple] ([tuple, str])
        """
        if multi_names:
            schemas = tuple(schema_name for schema_name in multi_names)
        else:
            schemas = tuple(
                x for x in sqlalchemy.engine.reflection.Inspector.from_engine(self.engine).get_schema_names()
                if x != 'public' and x != 'information_schema')
        print_plural = (("{} " if len(schemas) == 1 else "{}s ").format(desc))
        print_schema = ("\"{}\", " * (len(schemas) - 1) + "\"{}\"").format(*schemas)
        return schemas, print_plural + print_schema

    # Drop a schema in the database being currently connected
    def drop_schema(self, *schema_names, confirmation_required=True, verbose=False):
        """
        :param schema_names: [str] name of one schema, or names of multiple schemas
        :param confirmation_required: [bool] (default: True)
        :param verbose: [bool] (default: False)
        """
        schemas, schemas_msg = self.printing_messages_for_multi_names(*schema_names, desc='schema')
        if confirmed("Confirmed to drop the {} from the database \"{}\"".format(schemas_msg, self.database_name),
                     confirmation_required=confirmation_required):
            try:
                print("Dropping the {} ... ".format(schemas_msg), end="") if verbose else ""
                self.engine.execute(
                    'DROP SCHEMA IF EXISTS ' + ('%s, ' * (len(schemas) - 1) + '%s') % schemas + ' CASCADE;')
                print("Done.") if verbose else ""
            except Exception as e:
                print("Failed. CAUSE: \"{}\"".format(e))

    # Check if a table exists
    def table_exists(self, schema_name, table_name):
        """
        :param table_name: [str] name of a table
        :param schema_name: [str] name of a schema (default: 'public')
        :return: [bool] whether the table already exists
        """
        res = self.engine.execute("SELECT EXISTS("
                                  "SELECT * FROM information_schema.tables "
                                  "WHERE table_schema='{}' "
                                  "AND table_name='{}');".format(schema_name, table_name))
        return res.fetchone()[0]

    # Create a new table
    def create_table(self, schema_name, table_name, column_specs, verbose=False):
        """
        :param table_name: [str] name of a table
        :param schema_name: [str] name of a schema (default: 'public')
        :param column_specs: [str; None (default)]
        :param verbose: [bool] (default: False)

        e.g.
            CREATE TABLE table_name(
               column1 datatype column1_constraint,
               column2 datatype column2_constraint,
               ...
               columnN datatype columnN_constraint,
               PRIMARY KEY( one or more columns )
            );
            # column_specs = 'column_name TYPE column_constraint, ..., table_constraint table_constraint'
            column_specs = 'col_name_1 INT, col_name_2 TEXT'
        """
        table_name_ = '{schema}.\"{table}\"'.format(schema=schema_name, table=table_name)

        if not self.schema_exists(schema_name):
            self.create_schema(schema_name, verbose=False)

        try:
            print("Creating a table '{}' ... ".format(table_name_), end="") if verbose else ""
            self.engine.execute('CREATE TABLE {} ({});'.format(table_name_, column_specs))
            print("Done.") if verbose else ""
        except Exception as e:
            print("Failed. CAUSE: \"{}\"".format(e))

    # Check if a table (for a subregion) exists
    def subregion_table_exists(self, schema_name, table_name, subregion_name_as_table_name=True):
        """
        :param schema_name: [str] name of a schema
        :param table_name: [str] name of a table
        :param subregion_name_as_table_name: [bool] (default: True) whether to use subregion name as table name
        :return: [bool]
        """
        table_name_ = regulate_table_name(table_name, subregion_name_as_table_name)
        res = self.engine.execute("SELECT EXISTS("
                                  "SELECT * FROM information_schema.tables "
                                  "WHERE table_schema='{}' "
                                  "AND table_name='{}');".format(schema_name, table_name_))
        return res.fetchone()[0]

    # Get information about columns
    def get_column_info(self, schema_name, table_name, as_dict=True, subregion_name_as_table_name=True):
        """
        :param table_name: [str] name of a table
        :param schema_name: [str] name of a schema
        :param as_dict: [bool] (default: True)
        :param subregion_name_as_table_name: [bool] (default: True)
        :return: [pd.DataFrame; dict]
        """
        table_name_ = regulate_table_name(table_name, subregion_name_as_table_name)
        column_info = self.engine.execute(
            "SELECT * FROM information_schema.columns "
            "WHERE table_schema='{}' AND table_name='{}';".format(schema_name, table_name_))
        keys, values = column_info.keys(), column_info.fetchall()
        info_tbl = pd.DataFrame(values, index=['column_{}'.format(x) for x in range(len(values))], columns=keys).T
        if as_dict:
            info_tbl = {k: v.to_list() for k, v in info_tbl.iterrows()}
        return info_tbl

    # Remove data from the database being currently connected
    def drop_table(self, schema_name, table_name, confirmation_required=True, subregion_name_as_table_name=True,
                   verbose=False):
        """
        :param table_name: [str] name of a table
        :param schema_name: [str] name of a schema
        :param confirmation_required: [bool] (default: True)
        :param subregion_name_as_table_name: [bool] (default: True)
        :param verbose: [bool] (default: False)
        """
        table_name_ = regulate_table_name(table_name, subregion_name_as_table_name)
        if confirmed("Confirmed to drop the table {}.\"{}\" from the database \"{}\"?".format(
                schema_name, table_name_, self.database_name), confirmation_required=confirmation_required):
            try:
                self.engine.execute('DROP TABLE IF EXISTS {}.\"{}\" CASCADE;'.format(schema_name, table_name_))
                print("The table \"{}\" has been dropped successfully.".format(table_name_)) if verbose else ""
            except Exception as e:
                print("Failed. CAUSE: \"{}\"".format(e))

    # Import data (as a pandas.DataFrame) into the database being currently connected
    def dump_osm_pbf_data_by_layer(self, layer_data, schema_name, table_name, subregion_name_as_table_name=True,
                                   parsed=True, if_exists='replace', chunk_size=None, method='multi', verbose=False,
                                   **kwargs):
        """
        :param layer_data: [pandas.DataFrame] data of one layer
        :param schema_name: [str] name of the layer
        :param table_name: [str] name of the targeted table
        :param subregion_name_as_table_name: [bool] (default: True) whether to use subregion name as table name
        :param parsed: [bool] (default: True) whether 'layer_data' has been parsed
        :param if_exists: [str] 'fail', 'replace' (default), 'append'
        :param chunk_size: [int; None (default)]
        :param method: [str; None; callable] (default: 'multi' - pass multiple values in a single INSERT clause)
        :param verbose: [bool] (default: False)
        """
        if schema_name not in sqlalchemy.engine.reflection.Inspector.from_engine(self.engine).get_schema_names():
            self.create_schema(schema_name)

        table_name_ = regulate_table_name(table_name, subregion_name_as_table_name)

        try:
            print("Dumping the data as a table \"{}\" into {}.\"{}\"@{} ... ".format(
                table_name, schema_name, self.database_name, self.host), end="") if verbose else ""
            if not parsed:
                layer_data.to_sql(table_name_, self.engine, schema_name, if_exists, index=False, chunksize=chunk_size,
                                  dtype={'geometry': sqlalchemy.types.JSON, 'properties': sqlalchemy.types.JSON},
                                  method=method, **kwargs)
            else:
                lyr_dat = layer_data.copy()
                if not layer_data.empty:
                    lyr_dat.coordinates = layer_data.coordinates.map(lambda x: x.wkt)
                    lyr_dat.other_tags = layer_data.other_tags.astype(str)
                    # dtype={'coordinates': types.TEXT, 'other_tags': types.TEXT}
                lyr_dat.to_sql(table_name_, self.engine, schema_name, if_exists, index=False, chunksize=chunk_size,
                               method=method, **kwargs)
            print("Done.") if verbose else ""
        except Exception as e:
            print("Failed. CAUSE: \"{}\"".format(e))

    # Import all data of a given (sub)region
    def dump_osm_pbf_data(self, subregion_data, table_name, parsed=True, if_exists='replace', chunk_size=None,
                          subregion_name_as_table_name=True, verbose=True):
        """
        :param subregion_data: [pd.DataFrame] data of a subregion
        :param table_name: [str] name of a table; e.g. name of the subregion (recommended)
        :param parsed: [bool] (default: True) whether 'subregion_data' has been parsed
        :param if_exists: [str] 'fail', 'replace' (default), or 'append'
        :param chunk_size: [int; None (default)]
        :param subregion_name_as_table_name: [bool] (default: True) whether to use subregion name as table name
        :param verbose: [bool] (default: True)
        """
        if subregion_name_as_table_name:
            table_name = geofabrik_downloader.regulate_input_subregion_name(table_name)

        if verbose:
            print("Dumping \"{}\" to {}@{}:{} ... ".format(table_name, self.database_name, self.host, self.port))
        for geom_type, layer_data in subregion_data.items():
            print("         {} ... ".format(geom_type), end="") if verbose else ""
            if layer_data.empty and self.subregion_table_exists(geom_type, table_name, subregion_name_as_table_name):
                print("The layer is empty. An empty table already exists in the database.") if verbose else ""
                pass
            else:
                try:
                    self.dump_osm_pbf_data_by_layer(layer_data, geom_type, table_name, subregion_name_as_table_name,
                                                    parsed, if_exists, chunk_size)
                    print("Done. Total amount of features: {}".format(len(layer_data))) if verbose else ""
                except Exception as e:
                    print("Failed. CAUSE: \"{}\"".format(e))
            del layer_data
            gc.collect()

    # Read data by SQL query (recommended for large table)
    @staticmethod
    def read_sql_query(cur, sql_query, max_spooled_size=1, delimiter=',', **kwargs):
        """
        :param cur: a cursor
        :param sql_query: [str]
        :param max_spooled_size: [int] (default: 10000, in Gigabyte)
        :param delimiter: [str]
        :return: [pd.DataFrame]

        Alternative method - using io.StringIO:

        import io

        tf_csv = io.StringIO()
        cursor = self.connection.cursor()

        copy_sql = "COPY ({sql_query}) TO STDOUT WITH DELIMITER '{delimiter}' CSV HEADER;".format(
            sql_query=sql_query, delimiter=delimiter)
        # Copy data from the database to a dataframe
        cursor.copy_expert(copy_sql, tf_csv)
        tf_csv.seek(0)  # move back to start of csv data

        table_data = pd.read_csv(tf_csv, dtype=dtype)

        """
        # Specify the SQL query for "COPY"
        copy_sql = "COPY ({query}) TO STDOUT WITH DELIMITER '{delimiter}' CSV HEADER;".format(
            query=sql_query, delimiter=delimiter)
        # Data would be spooled in memory until its size > max_spooled_size
        csv_temp = tempfile.SpooledTemporaryFile(max_size=max_spooled_size * 10 ** 9)  # tempfile.TemporaryFile()
        cur.copy_expert(copy_sql, csv_temp)
        csv_temp.seek(0)  # Rewind the file handle using seek() in order to read the data back from it
        # Read data from temporary csv
        table_data = pd.read_csv(csv_temp, **kwargs)
        return table_data

    # Read data for a given subregion and schema (geom type, e.g. points, lines, ...)
    def read_osm_pbf_data(self, table_name, *schema_names, parsed=True, subregion_name_as_table_name=True,
                          chunk_size=None, method='tempfile', max_spooled_size=1, delimiter=',', sorted_by_id=True,
                          **kwargs):
        """
        :param table_name: [str] name of a table name; 'subregion_name' is recommended when importing the data
        :param schema_names: [str] one or multiple names of layers, e.g. 'points', 'lines'
        :param parsed: [bool] (default: True) whether the table data was parsed before being imported
        :param subregion_name_as_table_name: [bool] (default: True) whether to use subregion name as 'table_name'
        :param chunk_size: [int; None (default)] number of rows to include in each chunk
        :param method: [str; None] (default: 'tempfile')
        :param max_spooled_size: [int; None] (default: 1 gigabyte)
        :param delimiter: [str] (default: ',')
        :param sorted_by_id: [bool] (default: True)
        :return: [dict] e.g. {layer_name_1: layer_data_1, ...}
        """
        table_name_ = regulate_table_name(table_name, subregion_name_as_table_name)

        if schema_names:
            geom_types = [x for x in schema_names]
        else:
            geom_types = [x for x in sqlalchemy.engine.reflection.Inspector.from_engine(self.engine).get_schema_names()
                          if x != 'public' and x != 'information_schema']

        layer_data = []
        for schema_name in geom_types:
            sql_query = 'SELECT * FROM {}."{}";'.format(schema_name, table_name_)
            if method == 'tempfile':
                cur = self.connection.cursor()
                lyr_dat = self.read_sql_query(cur, sql_query, max_spooled_size, delimiter, **kwargs)
                cur.close()
            else:
                lyr_dat = pd.read_sql(sql_query, self.engine, chunksize=chunk_size, **kwargs)
            if sorted_by_id:
                lyr_dat.sort_values('id', inplace=True)
                lyr_dat.index = range(len(lyr_dat))
            if parsed:
                lyr_dat.coordinates = lyr_dat.coordinates.map(shapely.wkt.loads)
                lyr_dat.other_tags = lyr_dat.other_tags.map(eval)
            layer_data.append(lyr_dat)

        return dict(zip(geom_types, layer_data))

    # Remove subregion data from the database being currently connected
    def drop_subregion_data_by_layer(self, table_name, *schema_names, subregion_name_as_table_name=True,
                                     confirmation_required=True, verbose=False):
        """
        :param table_name: [str] name of a subregion
        :param subregion_name_as_table_name: [bool] (default: True) whether to use subregion name as 'table_name'
        :param schema_names: [str] one or multiple names of schemas
        :param confirmation_required: [bool] (default: True)
        :param verbose: [bool] (default: False)
        """
        table_name_ = regulate_table_name(table_name, subregion_name_as_table_name)
        geom_types, schemas_msg = self.printing_messages_for_multi_names(*schema_names, desc='layer')
        if confirmed("Confirmed to drop the {} for \"{}\"".format(schemas_msg, table_name_),
                     confirmation_required=confirmation_required):
            tables = tuple(('{}.\"{}\"'.format(schema_name, table_name_) for schema_name in geom_types))
            if verbose:
                print(("Dropping " + "%s, " * (len(tables) - 2) + "%s and %s" + " ... ") % tables, end="")
            try:
                self.engine.execute(('DROP TABLE IF EXISTS ' + '%s, ' * (len(tables) - 1) + '%s CASCADE;') % tables)
                print("Done.") if verbose else ""
            except Exception as e:
                print("Failed. CAUSE: \"{}\"".format(e))

    # Remove tables from the database being currently connected
    def drop_layer_data_by_subregion(self, schema_name, *table_names, subregion_name_as_table_name=True,
                                     confirmation_required=True, verbose=False):
        """
        :param schema_name: [str] name of a layer name
        :param subregion_name_as_table_name: [bool] (default: True) whether to use subregion name as 'table_name'
        :param table_names: [str] one or multiple names of subregions
        :param confirmation_required: [bool] (default: True)
        :param verbose: [bool] (default: False)
        """
        table_names_ = (regulate_table_name(table_name, subregion_name_as_table_name) for table_name in table_names)
        _, tbls_msg = self.printing_messages_for_multi_names(*table_names, desc='table')
        if confirmed("Confirmed to drop the {} from the database \"{}\"".format(tbls_msg, self.database_name),
                     confirmation_required=confirmation_required):
            tables = tuple(('{}.\"{}\"'.format(schema_name, table_name) for table_name in table_names_))
            if verbose:
                print(("Dropping " + "%s, " * (len(tables) - 2) + "%s and %s" + " ... ") % tables, end="")
            try:
                self.engine.execute(('DROP TABLE IF EXISTS ' + '%s, ' * (len(tables) - 1) + '%s CASCADE;') % tables)
                print("Done.") if verbose else ""
            except Exception as e:
                print("Failed. CAUSE: \"{}\"".format(e))


# Import data of selected or all (sub)regions, which do not have (sub-)subregions, into PostgreSQL server
def psql_osm_pbf_data_extracts(*subregion_name,
                               username='postgres', password=None, host='localhost', port=5432,
                               database_name='OSM_Geofabrik_PBF', data_dir=None,
                               update_osm_pbf=False, if_table_exists='replace', file_size_limit=50, parsed=True,
                               fmt_other_tags=True, fmt_single_geom=True, fmt_multi_geom=True, pickle_raw_file=False,
                               rm_raw_file=False, confirmation_required=True, verbose=False):
    """
    :param subregion_name: [str]
    :param username: [str] (default: 'postgres')
    :param password: [None (default); anything as input]
    :param host: [str] (default: 'localhost')
    :param port: [int] (default: 5432)
    :param database_name: [str] (default: 'OSM_Geofabrik')
    :param data_dir: [str; None (default)]
    :param update_osm_pbf: [bool] (default: False)
    :param if_table_exists: [str] 'replace' (default); 'append'; or 'fail'
    :param file_size_limit: [int] (default: 100)
    :param parsed: [bool] (default: True)
    :param fmt_other_tags: [bool] (default: True)
    :param fmt_single_geom: [bool] (default: True)
    :param fmt_multi_geom: [bool] (default: True)
    :param pickle_raw_file: [bool] (default: False)
    :param rm_raw_file: [bool] (default: False)
    :param confirmation_required: [bool] (default: True)
    :param verbose: [bool] (default: False)

    Example:
        subregions              = retrieve_names_of_subregions_of('England')
        confirmation_required   = True
        username                = 'postgres'
        password                = None
        host                    = 'localhost'
        port                    = 5432
        database_name           = 'geofabrik_osm_pbf'
        data_dir                = cd("test_osm_dump")
        update_osm_pbf          = False
        if_table_exists         = 'replace'
        file_size_limit         = 50
        parsed                  = True
        fmt_other_tags          = True
        fmt_single_geom         = True
        fmt_multi_geom          = True
        pickle_raw_file         = True
        rm_raw_file             = True
        verbose                 = True
        psql_osm_pbf_data_extracts(*subregion_name, database_name='OSM_Geofabrik', data_dir=None,
                                       update_osm_pbf=False, if_table_exists='replace', file_size_limit=50, parsed=True,
                                       fmt_other_tags=True, fmt_single_geom=True, fmt_multi_geom=True,
                                       rm_raw_file=False, verbose=False)
    """

    if not subregion_name:
        subregion_names = geofabrik_downloader.get_subregion_name_list()
        confirm_msg = "To dump GeoFabrik OSM data extracts of all subregions to PostgreSQL? "
    else:
        subregion_names = geofabrik_downloader.retrieve_names_of_subregions_of(*subregion_name)
        confirm_msg = "To dump GeoFabrik OSM data extracts of the following subregions to PostgreSQL? \n{}?\n".format(
            ", ".join(subregion_names))

    if confirmed(confirm_msg, confirmation_required=confirmation_required):

        # Connect to PostgreSQL server
        osmdb = PostgresOSM(username, password, host, port, database_name=database_name)

        err_subregion_names = []
        for subregion_name_ in subregion_names:
            default_pbf_filename, default_path_to_pbf = get_default_path_to_osm_file(subregion_name_, ".osm.pbf")
            if not data_dir:  # Go to default file path
                path_to_osm_pbf = default_path_to_pbf
            else:
                osm_pbf_dir = regulate_input_data_dir(data_dir)
                path_to_osm_pbf = os.path.join(osm_pbf_dir, default_pbf_filename)

            geofabrik_downloader.download_subregion_osm_file(subregion_name_, osm_file_format=".osm.pbf", download_dir=data_dir,
                                                             update=update_osm_pbf, confirmation_required=False, verbose=verbose)

            file_size_in_mb = round(os.path.getsize(path_to_osm_pbf) / (1024 ** 2), 1)

            try:
                if file_size_in_mb <= file_size_limit:

                    subregion_osm_pbf = read_osm_pbf(subregion_name_, data_dir, parsed, file_size_limit,
                                                     fmt_other_tags, fmt_single_geom, fmt_multi_geom,
                                                     update=False, download_confirmation_required=False,
                                                     pickle_it=pickle_raw_file, rm_osm_pbf=False, verbose=verbose)

                    if subregion_osm_pbf is not None:
                        osmdb.dump_osm_pbf_data(subregion_osm_pbf, table_name=subregion_name_,
                                                if_exists=if_table_exists, verbose=verbose)
                        del subregion_osm_pbf
                        gc.collect()

                else:
                    print("\nParsing and importing \"{}\" feature-wisely to PostgreSQL ... ".format(subregion_name_)) \
                        if verbose else ""
                    # Reference: https://gdal.org/python/osgeo.ogr.Feature-class.html
                    raw_osm_pbf = ogr.Open(path_to_osm_pbf)
                    layer_count = raw_osm_pbf.GetLayerCount()
                    for i in range(layer_count):
                        layer = raw_osm_pbf.GetLayerByIndex(i)  # Hold the i-th layer
                        layer_name = layer.GetName()
                        print("                       {} ... ".format(layer_name), end="") if verbose else ""
                        try:
                            features = [feature for _, feature in enumerate(layer)]
                            feats_no, chunks_no = len(features), math.ceil(file_size_in_mb / file_size_limit)
                            feats = split_list(features, chunks_no)

                            del features
                            gc.collect()

                            if osmdb.subregion_table_exists(layer_name, subregion_name_) and \
                                    if_table_exists == 'replace':
                                osmdb.drop_subregion_data_by_layer(subregion_name_, layer_name)

                            # Loop through all available features
                            for feat in feats:
                                lyr_dat = pd.DataFrame(rapidjson.loads(f.ExportToJson()) for f in feat)
                                lyr_dat = parse_osm_pbf_layer_data(lyr_dat, layer_name, fmt_other_tags, fmt_single_geom,
                                                                   fmt_multi_geom)
                                if_exists_ = if_table_exists if if_table_exists == 'fail' else 'append'
                                osmdb.dump_osm_pbf_data_by_layer(lyr_dat, layer_name, subregion_name_,
                                                                 if_exists=if_exists_)
                                del lyr_dat
                                gc.collect()

                            print("Done. Total amount of features: {}".format(feats_no)) if verbose else ""

                        except Exception as e:
                            print("Failed. {}".format(e))

                    raw_osm_pbf.Release()
                    del raw_osm_pbf
                    gc.collect()

                if rm_raw_file:
                    remove_subregion_osm_file(path_to_osm_pbf, verbose=verbose)

            except Exception as e:
                print(e)
                err_subregion_names.append(subregion_name_)

            if subregion_name_ != subregion_names[-1]:
                time.sleep(60)

        if len(err_subregion_names) == 0:
            print("Mission accomplished.\n") if verbose else ""
        else:
            print("Errors occurred when parsing data of the following subregion(s):")
            print(*err_subregion_names, sep=", ")

        osmdb.disconnect_database()
        del osmdb
