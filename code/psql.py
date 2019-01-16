""" Data storage with PostgreSQL """

from geoalchemy2 import types
from sqlalchemy import create_engine
from sqlalchemy.engine.reflection import Inspector
from sqlalchemy.engine.url import URL
from sqlalchemy_utils import create_database, database_exists

from utils import confirmed


class OSM:
    def __init__(self):
        """
        We need to be connected to the database server in order to execute the "CREATE DATABASE" command. There is a 
        database called "postgres" created by the "initdb" command when the data storage area is initialised. If we 
        need to create the first of our own database, we can set up a connection to "postgres" in the first instance.
        """
        self.database_info = {'drivername': 'postgresql+psycopg2',
                              'username': str(input('PostgreSQL username: ')),
                              'password': int(input('PostgreSQL password: ')),
                              'host': 'localhost',
                              'port': 5432,
                              'database': 'postgres'}

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
        :return:
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
        :param database_name: [str]
        :return:

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
        db_name = self.database_name if database_name is None else database_name
        self.disconnect(db_name)
        if confirmed("Confirmed to drop the database \"{}\"?".format(db_name)):
            self.engine.execute('DROP DATABASE "{}"'.format(db_name))
        else:
            pass

    # Create a new schema in the database being currently connected
    def create_schema(self, schema_name):
        self.engine.execute('CREATE SCHEMA IF NOT EXISTS "{}";'.format(schema_name))

    # Drop a schema in the database being currently connected
    def drop_schema(self, schema_name):
        self.engine.execute('DROP SCHEMA IF EXISTS "{}";'.format(schema_name))

    # Import data (as a pandas.DataFrame) into the database being currently connected
    def import_data(self, data, table_name, schema_name='public', parsed=False):
        """
        :param data: [pandas.DataFrame]
        :param table_name: [str]
        :param schema_name: [str] 'public' (default)
        :param parsed: [bool] whether 'data' has been parsed; False (default)
        :return:
        """
        schemas = Inspector.from_engine(self.engine)
        if schema_name not in schemas.get_table_names():
            self.create_schema(schema_name)
        if not parsed:
            data.to_sql(table_name, self.engine, schema=schema_name, if_exists='replace', index=False,
                        dtype={'geometry': types.postgresql.JSON, 'properties': types.postgresql.JSON})
        else:  # There is an error. To be fixed...
            data.to_sql(table_name, self.engine, schema=schema_name, if_exists='replace', index=False,
                        dtype={'other_tags': types.postgresql.JSON, 'coordinates': types.postgresql.ARRAY})

    # Remove tables from the database being currently connected
    def drop_table(self, schema_name, *table_names):
        t_names = tuple(('{}.{}'.format(schema_name, t) for t in table_names))
        self.engine.execute(('DROP TABLE IF EXISTS ' + '%s, '*(len(t_names) - 1) + '%s;') % t_names)
