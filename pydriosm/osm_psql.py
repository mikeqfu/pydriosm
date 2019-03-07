""" Data storage with PostgreSQL """

from getpass import getpass

from fuzzywuzzy.process import extractOne
from pandas import read_sql
from psycopg2 import DatabaseError
from sqlalchemy import create_engine, types
from sqlalchemy.engine.reflection import Inspector
from sqlalchemy.engine.url import URL
from sqlalchemy_utils import create_database, database_exists

from pydriosm.download_GeoFabrik import get_subregion_info_index
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
                              'password': getpass('PostgreSQL password: '),
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
    def connect_db(self, database_name='osm_extracts'):
        """
        :param database_name: [str] default as 'osm_extracts'; alternatives such as 'OpenStreetMap', ...
        """
        self.database_name = database_name
        self.database_info['database'] = self.database_name
        self.url = URL(**self.database_info)
        if not database_exists(self.url):
            create_database(self.url)
        self.engine = create_engine(self.url, isolation_level='AUTOCOMMIT')
        self.connection = self.engine.connect()

    # An alternative to sqlalchemy_utils.create_database()
    def create_db(self, database_name='osm_extracts'):
        """
        :param database_name: [str] default as 'osm_extracts'; alternatives such as 'OpenStreetMap', ...

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

    # Kill the connection to the specified database
    def disconnect(self, database_name=None):
        """
        :param database_name: [str] Name of database to disconnect from； None (default) to disconnect the current one

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
        :param database_name: [str] Name of database to disconnect from, or None (default) to disconnect the current one
        """
        db_name = self.database_name if database_name is None else database_name
        self.disconnect(db_name)
        if confirmed("Confirmed to drop the database \"{}\"?".format(db_name)):
            self.engine.execute('DROP DATABASE "{}"'.format(db_name))
        else:
            pass

    # Create a new schema in the database being currently connected
    def create_schema(self, schema_name):
        """
        :param schema_name: [str] Schema name
        """
        self.engine.execute('CREATE SCHEMA IF NOT EXISTS "{}";'.format(schema_name))

    # Drop a schema in the database being currently connected
    def drop_schema(self, schema_name):
        """
        :param schema_name: [str] Schema name (default layer name)
        """
        self.engine.execute('DROP SCHEMA IF EXISTS "{}";'.format(schema_name))

    # Check if a table exists
    def table_exists(self, schema_name, table_name):
        """
        :param schema_name: [str] e.g. 'public'
        :param table_name: [str] table name
        :return: [bool]
        """
        res = self.engine.execute("SELECT EXISTS("
                                  "SELECT * FROM information_schema.tables "
                                  "WHERE table_schema='{}' "
                                  "AND table_name='{}');".format(schema_name, table_name))
        return res.fetchone()[0]

    # Insert a value to database
    def insert_dat(self, dat, schema_name, table_name, col_name):
        """ insert a new vendor into the vendors table """
        schemas = Inspector.from_engine(self.engine)
        if schema_name not in schemas.get_table_names():
            self.create_schema(schema_name)
        sql_command = "INSERT INTO %s(%s) VALUES(%s);"
        try:
            # execute the INSERT statement
            self.engine.execute(sql_command, (table_name, col_name, dat))
        except (Exception, DatabaseError) as e:
            print(e)
        finally:
            if self.connection is not None:
                self.connection.close()

    # Import data (as a pandas.DataFrame) into the database being currently connected
    def dump_layer_data(self, dat, schema_name, table_name, if_exists='replace', parsed=False):
        """
        :param dat: [pandas.DataFrame]
        :param schema_name: [str] e.g. 'public'
        :param table_name: [str] table name
        :param if_exists: [str] 'fail', 'replace', or 'append'; default 'fail'
        :param parsed: [bool] Whether 'data' has been parsed; False (default)
        """
        if schema_name not in Inspector.from_engine(self.engine).get_schema_names():
            self.create_schema(schema_name)
        if not parsed:
            dat.to_sql(table_name, self.engine, schema=schema_name, if_exists=if_exists, index=False,
                       dtype={'geometry': types.JSON, 'properties': types.JSON})
        else:  # There is an error. To be fixed...
            dat.to_sql(table_name, self.engine, schema=schema_name, if_exists=if_exists, index=False,
                       dtype={'other_tags': types.JSON, 'coordinates': types.ARRAY})

    # Import all data of a given (sub)region
    def dump_data(self, subregion_data, table_name, parsed=False, subregion_name_as_table_name=True):
        """
        :param subregion_data: [pandas.DataFrame]
        :param table_name: [str] (Recommended to be) 'subregion_name'
        :param parsed: [bool] Whether 'data' has been parsed; False (default)
        :param subregion_name_as_table_name: [bool] Whether to use subregion name as table name; True (default)
        """
        if subregion_name_as_table_name:
            subregion_names = get_subregion_info_index('GeoFabrik-subregion-name-list')
            table_name = extractOne(table_name, subregion_names, score_cutoff=10)[0]
        print("Dumping \"{}\" to PostgreSQL ... ".format(table_name))
        for data_type, data in subregion_data.items():
            print("         {} ... ".format(data_type), end="")
            try:
                if data.empty and self.table_exists(schema_name=data_type, table_name=table_name):
                    print("The layer is empty. Table (probably empty) already exists in the database.")
                    pass
                else:
                    self.dump_layer_data(data, schema_name=data_type, table_name=table_name, parsed=parsed)
                    print("Done.")
            except Exception as e:
                print("Failed. {}".format(e))

    # Read data for a given subregion and schema (geom type, e.g. points, lines, ...)
    def read_table(self, table_name, *schema_names, subregion_name_as_table_name=True, chunk_size=None):
        """
        :param table_name: [str] Table name; 'subregion_name' is recommended to be used when importing the data
        :param schema_names: [iterable] Layer name, or a list of layer names, e.g. ['points', 'lines']
        :param subregion_name_as_table_name: [bool] Whether to use subregion name as table name; True (default)
        :param chunk_size: [int] or None (default); number of rows to include in each chunk
        :return: [dict]
        """
        if subregion_name_as_table_name:
            subregion_names = get_subregion_info_index('GeoFabrik-subregion-name-list')
            table_name = extractOne(table_name, subregion_names, score_cutoff=10)[0]

        if schema_names:
            geom_types = [x for x in schema_names]
        else:
            geom_types = [x for x in Inspector.from_engine(self.engine).get_schema_names()
                          if x != 'public' and x != 'information_schema']

        layer_data = []
        for schema_name in geom_types:
            sql_query = 'SELECT * FROM {}."{}";'.format(schema_name, table_name)
            layer_data.append(read_sql(sql=sql_query, con=self.engine, chunksize=chunk_size))

        return dict(zip(geom_types, layer_data))

    # Remove tables from the database being currently connected
    def drop_table(self, schema_name, *table_names):
        """
        :param schema_name: [str] Schema name (default layer name)
        :param table_names: [iterable] Table name, or a list of table names, e.g. a list of subregion names
        """
        t_names = tuple(('{}.{}'.format(schema_name, t) for t in table_names))
        self.engine.execute(('DROP TABLE IF EXISTS ' + '%s, '*(len(t_names) - 1) + '%s;') % t_names)
