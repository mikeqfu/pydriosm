"""
Implement storage I/O of (parsed) OSM data extracts (available from BBBike free download server)
with `PostgreSQL <https://www.postgresql.org/>`_.
"""

from pydriosm.ios._pgsql_osm import PostgresOSM


class BBBikeIOS(PostgresOSM):
    """
    Implement storage I/O of `BBBike exports of OpenStreetMap data <https://download.bbbike.org/>`_
    with PostgreSQL.
    """

    #: Data source.
    DATA_SOURCES: list = ['BBBike']

    def __init__(self, **kwargs):
        """
        :param kwargs: [optional] parameters of the class :class:`~pydriosm.downloader.PostgresOSM`

        :ivar BBBikeDownloader downloader: instance of the class
            :class:`~pydriosm.downloader.BBBikeDownloader`
        :ivar BBBikeReader reader: instance of the class
            :class:`~pydriosm.downloader.BBBikeReader`

        **Examples**::

            >>> from pydriosm.ios import BBBikeIOS
            >>> bbi = BBBikeIOS(database_name='osmdb_test', verbose=True)
            Password (postgres@localhost:5432): ***
            Creating a database: "osmdb_test" ... Done.
            Connecting postgres:***@localhost:5432/osmdb_test ... Successfully.
            >>> type(bbi.downloader)
            pydriosm.downloader._wrapper.Downloader
            >>> type(bbi.reader)
            pydriosm.downloader._wrapper.Reader

        .. seealso::

            - Examples for all the methods of the class :class:`~pydriosm.ios.PostgresOSM`.
        """

        kwargs['data_source'] = self.DATA_SOURCES[0]
        super().__init__(**kwargs)
