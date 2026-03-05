"""
Implement storage I/O of OSM data extracts (available from Geofabrik free download server)
with `PostgreSQL <https://www.postgresql.org/>`_.
"""

from pydriosm.ios._pgsql_osm import PostgresOSM


class GeofabrikIOS(PostgresOSM):
    """
    Implement storage I/O of `Geofabrik OpenStreetMap data extracts <https://download.geofabrik.de/>`_
    with `PostgreSQL <https://www.postgresql.org/>`_.
    """

    #: Data source.
    DATA_SOURCES: list = ['Geofabrik']

    def __init__(self, **kwargs):
        """
        :param kwargs: [optional] parameters of the class :class:`~pydriosm.downloader.PostgresOSM`

        :ivar PostgresOSM postgres: instance of the class :class:`~pydriosm.downloader.PostgresOSM`
        :ivar GeofabrikDownloader downloader: instance of the class
            :class:`~pydriosm.downloader.GeofabrikDownloader`
        :ivar GeofabrikReader reader: instance of the class
            :class:`~pydriosm.downloader.GeofabrikReader`

        **Examples**::

            >>> from pydriosm.ios import GeofabrikIOS
            >>> gfi = GeofabrikIOS(database_name='osmdb_test', verbose=True)
            Password (postgres@localhost:5432): ***
            Creating a database: "osmdb_test" ... Done.
            Connecting postgres:***@localhost:5432/osmdb_test ... Successfully.
            >>> type(gfi.downloader)
            pydriosm.downloader._wrapper.Downloader
            >>> type(gfi.reader)
            pydriosm.reader._wrapper.Reader

        .. seealso::

            - Examples for all the methods of the class :class:`~pydriosm.ios.PostgresOSM`.
        """

        kwargs['data_source'] = self.DATA_SOURCES[0]
        super().__init__(**kwargs)
