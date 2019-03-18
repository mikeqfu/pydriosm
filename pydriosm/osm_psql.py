""" Data storage with PostgreSQL """

import gc
import getpass

from pandas import read_sql
from shapely import wkt
from sqlalchemy import create_engine, types
from sqlalchemy.engine.reflection import Inspector
from sqlalchemy.engine.url import URL
from sqlalchemy_utils import create_database, database_exists

from pydriosm.download_GeoFabrik import regulate_input_subregion_name
from pydriosm.utils import confirmed


class OSM:
    def __init__(self):
        """
        It requires to be connected to the database server so as to execute the "CREATE DATABASE" command.
        A default database named "postgres" exists already, which is created by the "initdb" command when the data
        storage area is initialised.
        Prior to create a customised database, it requires to connect "postgres" in the first instance.
        """
        self.database_info = {'drivername': 'postgresql+psycopg2',
                              'username': input('PostgreSQL username: '),
                              'password': getpass.getpass('PostgreSQL password: '),
                              'host': input('Host name: '),
                              'port': 5432,  # default by installation
                              'database': input('Database name: ')}

        # The typical form of a database URL is: url = backend+driver://username:password@host:port/database_name
        self.url = URL(**self.database_info)
        self.dialect = self.url.get_dialect()
        self.backend = self.url.get_backend_name()
        self.driver = self.url.get_driver_name()
        self.user, self.host = self.url.username, self.url.host
        self.port = self.url.port
        self.database_name = self.database_info['database']

        # Create a SQLAlchemy connectable
        self.engine = create_engine(self.url, isolation_level='AUTOCOMMIT')
        self.connection = self.engine.connect()

    # Establish a connection to the specified database (named e.g. 'osm_extracts')
    def connect_db(self, database_name='osm_data_extracts'):
        """
        :param database_name: [str; 'osm_data_extracts'(default)] name of a database
        """
        self.database_name = database_name
        self.database_info['database'] = self.database_name
        self.url = URL(**self.database_info)
        if not database_exists(self.url):
            create_database(self.url)
        self.engine = create_engine(self.url, isolation_level='AUTOCOMMIT')
        self.connection = self.engine.connect()

    # An alternative to sqlalchemy_utils.create_database()
    def create_db(self, database_name='osm_data_extracts'):
        """
        :param database_name: [str; 'osm_data_extracts'(default)] name of a database

        from psycopg2 import OperationalError
        try:
            self.engine.execute('CREATE DATABASE "{}"'.format(database_name))
        except OperationalError:
            self.engine.execute(
                'SELECT *, pg_terminate_backend(pid) FROM pg_stat_activity WHERE username=\'postgres\';')
            self.engine.execute('CREATE DATABASE "{}"'.format(database_name))
        """
        self.disconnect()
        self.engine.execute('CREATE DATABASE "{}";'.format(database_name))
        self.connect_db(database_name=database_name)

    # Get size of a database
    def get_db_size(self, database_name=None):
        db_name = '\'{}\''.format(database_name) if database_name else 'current_database()'
        db_size = self.engine.execute('SELECT pg_size_pretty(pg_database_size({})) AS size;'.format(db_name))
        print(db_size.fetchone()[0])

    # Kill the connection to the specified database
    def disconnect(self, database_name=None):
        """
        :param database_name: [str; None(default)] name of database to disconnect from

        Alternative way:
        SELECT
            pg_terminate_backend(pg_stat_activity.pid)
        FROM
            pg_stat_activity
        WHERE
            pg_stat_activity.datname = database_name AND pid <> pg_backend_pid();
        """
        db_name = self.database_name if database_name is None else database_name
        self.connect_db('postgres')
        self.engine.execute('REVOKE CONNECT ON DATABASE {} FROM PUBLIC, postgres;'.format(db_name))
        self.engine.execute(
            'SELECT pg_terminate_backend(pid) '
            'FROM pg_stat_activity '
            'WHERE datname = \'{}\' AND pid <> pg_backend_pid();'.format(db_name))

    # Kill connections to all other databases
    def disconnect_all_others(self):
        self.connect_db('postgres')
        self.engine.execute('SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE pid <> pg_backend_pid();')

    # Drop the specified database
    def drop(self, database_name=None):
        """
        :param database_name: [str] name of database to disconnect from, or None (default) to disconnect the current one
        """
        db_name = self.database_name if database_name is None else database_name
        if confirmed("Confirmed to drop the database \"{}\"?".format(db_name)):
            self.disconnect(db_name)
            self.engine.execute('DROP DATABASE IF EXISTS "{}"'.format(db_name))

    # Create a new schema in the database being currently connected
    def create_schema(self, schema_name):
        """
        :param schema_name: [str] name of a schema
        """
        self.engine.execute('CREATE SCHEMA IF NOT EXISTS "{}";'.format(schema_name))

    # Drop a schema in the database being currently connected
    def drop_schema(self, *schema_names):
        """
        :param schema_names: [str] name of one schema, or names of multiple schemas
        """
        if schema_names:
            schemas = tuple(schema_name for schema_name in schema_names)
        else:
            schemas = tuple(x for x in Inspector.from_engine(self.engine).get_schema_names()
                            if x != 'public' and x != 'information_schema')
        if confirmed("Confirmed to drop the schema(s): {}".format(schemas)):
            self.engine.execute(('DROP SCHEMA IF EXISTS ' + '%s, '*(len(schemas) - 1) + '%s CASCADE;') % schemas)

    # Check if a table exists
    def subregion_table_exists(self, schema_name, table_name):
        """
        :param schema_name: [str] name of a schema
        :param table_name: [str] name of a table
        :return: [bool]
        """
        table_name_ = table_name[:60] + '..' if len(table_name) >= 63 else table_name
        res = self.engine.execute("SELECT EXISTS("
                                  "SELECT * FROM information_schema.tables "
                                  "WHERE table_schema='{}' "
                                  "AND table_name='{}');".format(schema_name, table_name_))
        return res.fetchone()[0]

    # Import data (as a pandas.DataFrame) into the database being currently connected
    def dump_osm_pbf_data_by_layer(self, layer_data, schema_name, table_name,
                                   parsed=True, if_exists='replace', chunk_size=None):
        """
        :param layer_data: [pandas.DataFrame] data of one layer
        :param schema_name: [str] name of the layer
        :param table_name: [str] name of the targeted table
        :param parsed: [bool; True(default)] whether 'layer_data' has been parsed
        :param if_exists: [str] 'fail', 'replace', or 'append'; default 'replace'
        :param chunk_size: [int; None]
        """
        if schema_name not in Inspector.from_engine(self.engine).get_schema_names():
            self.create_schema(schema_name)

        table_name_ = table_name[:60] + '..' if len(table_name) >= 63 else table_name

        if not parsed:
            layer_data.to_sql(table_name_, self.engine, schema=schema_name,
                              if_exists=if_exists, index=False, chunksize=chunk_size,
                              dtype={'geometry': types.JSON, 'properties': types.JSON})
        else:
            lyr_dat = layer_data.copy()
            lyr_dat.coordinates = layer_data.coordinates.map(lambda x: x.wkt)
            lyr_dat.other_tags = layer_data.other_tags.astype(str)
            # dtype={'coordinates': types.TEXT, 'other_tags': types.TEXT}
            lyr_dat.to_sql(table_name_, self.engine, schema=schema_name,
                           if_exists=if_exists, index=False, chunksize=chunk_size)

    # Import all data of a given (sub)region
    def dump_osm_pbf_data(self, subregion_data, table_name, parsed=True, if_exists='replace', chunk_size=None,
                          subregion_name_as_table_name=True):
        """
        :param subregion_data: [pandas.DataFrame] data of a subregion
        :param table_name: [str] name of a table; e.g. name of the subregion (recommended)
        :param parsed: [bool; True(default)] whether 'subregion_data' has been parsed
        :param if_exists: [str; 'replace'(default)] 'fail', 'replace', or 'append'
        :param chunk_size: [int; None]
        :param subregion_name_as_table_name: [bool; True(default)] whether to use subregion name as table name
        """
        if subregion_name_as_table_name:
            table_name = regulate_input_subregion_name(table_name)

        print("Dumping \"{}\" to PostgreSQL ... ".format(table_name))
        for geom_type, layer_data in subregion_data.items():
            print("         {} ... ".format(geom_type), end="")
            if layer_data.empty and self.subregion_table_exists(schema_name=geom_type, table_name=table_name):
                print("The layer is empty. An empty table already exists in the database.")
                pass
            else:
                try:
                    self.dump_osm_pbf_data_by_layer(layer_data, geom_type, table_name, parsed, if_exists, chunk_size)
                    print("Done. Total amount of features: {}".format(len(layer_data)))
                except Exception as e:
                    print("Failed. {}".format(e))
            del layer_data
            gc.collect()

    # Read data for a given subregion and schema (geom type, e.g. points, lines, ...)
    def read_osm_pbf_data(self, table_name, *schema_names, parsed=True, subregion_name_as_table_name=True,
                          chunk_size=None, id_sorted=True):
        """
        :param table_name: [str] name of a table name; 'subregion_name' is recommended when importing the data
        :param schema_names: [str] one or multiple names of layers, e.g. 'points', 'lines'
        :param parsed: [bool; True(default)] whether the table data was parsed before being imported
        :param subregion_name_as_table_name: [bool; True(default)] whether to use subregion name as 'table_name'
        :param chunk_size: [int or None(default)] number of rows to include in each chunk
        :param id_sorted: [bool; True(default)]
        :return: [dict] e.g. {layer_name_1: layer_data_1, ...}
        """
        if subregion_name_as_table_name:
            table_name = regulate_input_subregion_name(table_name)
        table_name_ = table_name[:60] + '..' if len(table_name) >= 63 else table_name

        if schema_names:
            geom_types = [x for x in schema_names]
        else:
            geom_types = [x for x in Inspector.from_engine(self.engine).get_schema_names()
                          if x != 'public' and x != 'information_schema']

        layer_data = []
        for schema_name in geom_types:
            sql_query = 'SELECT * FROM {}."{}";'.format(schema_name, table_name_)
            lyr_dat = read_sql(sql=sql_query, con=self.engine, chunksize=chunk_size)
            if id_sorted:
                lyr_dat.sort_values('id', inplace=True)
                lyr_dat.index = range(len(lyr_dat))
            if parsed:
                lyr_dat.coordinates = lyr_dat.coordinates.map(wkt.loads)
                lyr_dat.other_tags = lyr_dat.other_tags.map(eval)
            layer_data.append(lyr_dat)

        return dict(zip(geom_types, layer_data))

    # Remove subregion data from the database being currently connected
    def drop_subregion_data_by_layer(self, table_name, *schema_names):
        """
        :param schema_names: [str] one or multiple names of schemas
        :param table_name: [str] name of a subregion
        """
        if schema_names:
            geom_types = [x for x in schema_names]
        else:
            geom_types = [x for x in Inspector.from_engine(self.engine).get_schema_names()
                          if x != 'public' and x != 'information_schema']

        table_name = regulate_input_subregion_name(table_name)
        table_name_ = table_name[:60] + '..' if len(table_name) >= 63 else table_name

        tables = tuple(('{}.\"{}\"'.format(schema_name, table_name_) for schema_name in geom_types))
        self.engine.execute(('DROP TABLE IF EXISTS ' + '%s, '*(len(tables) - 1) + '%s CASCADE;') % tables)

    # Remove tables from the database being currently connected
    def drop_layer_data_by_subregion(self, schema_name, *table_names):
        """
        :param schema_name: [str] name of a layer name
        :param table_names: [str] one or multiple names of subregions
        """
        table_names = (regulate_input_subregion_name(table_name) for table_name in table_names)
        table_names_ = (table_name[:60] + '..' if len(table_name) >= 63 else table_name for table_name in table_names)
        tables = tuple(('{}.\"{}\"'.format(schema_name, table_name) for table_name in table_names_))
        self.engine.execute(('DROP TABLE IF EXISTS ' + '%s, '*(len(tables) - 1) + '%s CASCADE;') % tables)
