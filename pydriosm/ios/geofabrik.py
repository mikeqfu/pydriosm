"""
Implement storage I/O of (parsed) OSM data extracts (available from Geofabrik free download server)
with `PostgreSQL <https://www.postgresql.org/>`_.
"""

from pydriosm.ios._ios import PostgresOSM


class GeofabrikIOS:
    """
    Implement storage I/O of `Geofabrik OpenStreetMap data extracts <https://download.geofabrik.de/>`_
    with `PostgreSQL <https://www.postgresql.org/>`_.
    """

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

            >>> gfi = GeofabrikIOS(database_name='osmdb_test')
            Password (postgres@localhost:5432): ***
            Creating a database: "osmdb_test" ... Done.
            Connecting postgres:***@localhost:5432/osmdb_test ... Successfully.

            >>> type(gfi.dbms)
            pydriosm.ios.PostgresOSM

            >>> gfi.dbms.name
            'Geofabrik OpenStreetMap data extracts'

        .. seealso::

            - Examples for all the methods of the class :class:`~pydriosm.ios.PostgresOSM`.
        """

        kwargs.update({'data_source': 'Geofabrik'})
        self.dbms = PostgresOSM(**kwargs)
