"""
Implement storage I/O of (parsed) OSM data extracts (available from BBBike free download server)
with `PostgreSQL <https://www.postgresql.org/>`_.
"""

from pydriosm.ios._ios import PostgresOSM


class BBBikeIOS:
    """
    Implement storage I/O of `BBBike exports of OpenStreetMap data <https://download.bbbike.org/>`_
    with PostgreSQL.
    """

    def __init__(self, **kwargs):
        """
        :param kwargs: [optional] parameters of the class :class:`~pydriosm.downloader.PostgresOSM`

        :ivar BBBikeDownloader downloader: instance of the class
            :class:`~pydriosm.downloader.BBBikeDownloader`
        :ivar BBBikeReader reader: instance of the class
            :class:`~pydriosm.downloader.BBBikeReader`

        **Examples**::

            >>> from pydriosm.ios import BBBikeIOS

            >>> bbi = BBBikeIOS(database_name='osmdb_test')
            Password (postgres@localhost:5432): ***
            Creating a database: "osmdb_test" ... Done.
            Connecting postgres:***@localhost:5432/osmdb_test ... Successfully.

            >>> type(bbi.dbms)
            pydriosm.ios.PostgresOSM

            >>> bbi.dbms.name
            'BBBike exports of OpenStreetMap data'

        .. seealso::

            - Examples for all the methods of the class :class:`~pydriosm.ios.PostgresOSM`.
        """

        kwargs.update({'data_source': 'BBBike'})
        self.dbms = PostgresOSM(**kwargs)
