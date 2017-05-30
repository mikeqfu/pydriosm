""" Data storage with PostgreSQL """

from sqlalchemy import create_engine
from sqlalchemy.engine.url import URL, make_url
from sqlalchemy_utils import database_exists, create_database, drop_database


def kill_extra_sessions():
    engine = create_engine('postgresql+psycopg2://postgres:123@localhost:5432/postgres')
    engine.execute('SELECT pg_terminate_backend(pid) FROM pg_stat_activity '
                   'WHERE datname = current_database() AND pid <> pg_backend_pid();')
    engine.dispose()


class OSM:
    def __init__(self):
        """
        We need to be connected to the database server in order to execute the "CREATE DATABASE" command. There is a 
        database called "postgres" created by the "initdb" command when the data storage area is initialised. If we 
        need to create the first of our own database, we can set up a connection to "postgres" in the first instance.
        """
        database_info = {'drivername': 'postgresql+psycopg2',
                         'username': str(input('Username: ')),
                         'password': int(input('Password: ')),
                         'host': 'localhost',
                         'port': 5432,
                         'database': 'postgres'}
        # The typical form of a database URL is: url = backend+driver://username:password@host:port/database
        self.url = URL(**database_info)
        self.dialect = self.url.get_dialect()
        self.backend = self.url.get_backend_name()
        self.driver = self.url.get_driver_name()
        self.user = self.url.username
        self.host = self.url.host
        self.port = self.url.port
        self.database_name = database_info['database']

        # Create a sqlalchemy connectable
        self.engine = create_engine(self.url, isolation_level='AUTOCOMMIT')
        if not database_exists(self.engine.url):
            create_database(self.engine.url)

        self.connection = self.engine.connect()

    #
    def create_database(self, database_name):
        """
        :param database_name: [str] default 'OpenStreetMap'
        """
        engine = create_engine(self.url)
        engine.execute('CREATE DATABASE {}'.format(database_name))

    #
    def kill_session(self):
        engine = create_engine('postgresql+psycopg2://postgres:123@localhost:5432/postgres')
        engine.execute('SELECT pg_terminate_backend(pg_stat_activity.pid) '
                       'FROM pg_stat_activity '
                       'WHERE pg_stat_activity.datname = \'{}\';'.format(self.database_name))
        engine.dispose()

    @staticmethod
    def kill_sessions():
        engine = create_engine('postgresql+psycopg2://postgres:123@localhost:5432/postgres')
        engine.execute('SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE pid <> pg_backend_pid();')
        engine.dispose()

    #
    def drop(self):
        drop_database(self.url)
        OSM.kill_sessions()
        del self

    # def create_schema(self):

    #
    def import_dataframe(self, data, table_name):
        data.to_sql(table_name, self.engine)
        OSM.table_name = table_name

    #
    def drop_table(self, table_name):
        self.connection('DROP TABLE {}'.format(table_name))


# Create a PostgreSQL database (using SQLAlchemy)
def connect_psql_osm_database(database_name='OpenStreetMap'):
    url = make_url('postgresql+psycopg2://postgres:123@localhost:5432/{}'.format(database_name))
    engine = create_engine(url, isolation_level='AUTOCOMMIT')
    if not database_exists(engine.url):
        create_database(engine.url)
    connection = engine.connect()
    return connection
