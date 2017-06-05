""" Data storage with PostgreSQL """

from sqlalchemy import create_engine
from sqlalchemy.engine.url import URL
from sqlalchemy_utils import database_exists, create_database


class OSM:
    def __init__(self):
        """
        We need to be connected to the database server in order to execute the "CREATE DATABASE" command. There is a 
        database called "postgres" created by the "initdb" command when the data storage area is initialised. If we 
        need to create the first of our own database, we can set up a connection to "postgres" in the first instance.
        """
        self.database_info = {'drivername': 'postgresql+psycopg2',
                              'username': str(input('Username: ')),
                              'password': int(input('Password: ')),
                              'host': 'localhost',
                              'port': 5432,
                              'database': 'postgres'}
        # The typical form of a database URL is: url = backend+driver://username:password@host:port/database
        self.url = URL(**self.database_info)
        self.dialect = self.url.get_dialect()
        self.backend = self.url.get_backend_name()
        self.driver = self.url.get_driver_name()
        self.user = self.url.username
        self.host = self.url.host
        self.port = self.url.port
        self.database_name = self.database_info['database']
        # Create a sqlalchemy connectable
        self.engine = create_engine(self.url, isolation_level='AUTOCOMMIT')
        if not database_exists(self.engine.url):
            create_database(self.engine.url)
        self.connection = self.engine.connect()

    #
    def connect_db(self, database_name):
        self.database_name = database_name
        self.database_info['database'] = self.database_name
        self.url = URL(**self.database_info)
        self.engine = create_engine(self.url, isolation_level='AUTOCOMMIT')
        if database_exists(self.url):
            self.connection = self.engine.connect()
        else:
            create_database(self.engine.url)
        self.connection = self.engine.connect()

    #
    def create_db(self, database_name):
        """
        :param database_name: [str] default 'OpenStreetMap'
        """
        self.engine.execute('CREATE DATABASE "{}"'.format(database_name))

    #
    def kill_session(self, database_name):
        self.engine.execute('SELECT pg_terminate_backend(pg_stat_activity.pid) '
                            'FROM pg_stat_activity '
                            'WHERE pg_stat_activity.pid <> pg_backend_pid() '
                            'AND pg_stat_activity.datname = \'{}\';'.format(database_name))

    #
    def drop(self, database_name):
        self.kill_session(database_name)
        self.engine.execute('DROP DATABASE "{}"'.format(database_name))

    #
    def kill_all_sessions(self):
        self.engine.execute('SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE pid <> pg_backend_pid();')

    #
    def create_schema(self, schema_name):
        self.engine.execute('CREATE SCHEMA "{}"'.format(schema_name))

    #
    def import_data(self, data, schema, table_name):
        if not self.engine.execute("SELECT EXISTS(SELECT schema_name FROM information_schema.schemata "
                                   "WHERE schema_name = '{}')".format(schema)):
            self.create_schema(schema)
        data.to_sql(table_name, self.engine, schema=schema, if_exists='replace', index=False)
        OSM.table_name = table_name

    #
    def drop_table(self, table_name):
        self.engine.execute('DROP TABLE {}'.format(table_name))
