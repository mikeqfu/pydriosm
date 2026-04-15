"""
Downloads OSM data from BBBike free download server.
"""

import collections
import os

from pyhelpers._cache import _print_failure_message
from pyhelpers.ops import confirmed

from pydriosm.downloader._base import BaseDownloader
from pydriosm.downloader.web_parser import fetch_bbbike_catalogue, fetch_bbbike_cities, \
    fetch_bbbike_city_polygons, fetch_bbbike_sub_catalogue, fetch_bbbike_subregion_index, \
    fetch_bbbike_valid_subregion_names


class BBBikeDownloader(BaseDownloader):
    """
    Download OSM data from `BBBike`_ free download server.

    .. _`BBBike`: https://download.bbbike.org/
    """

    #: Name of the free downloader server.
    NAME: str = 'BBBike'

    #: Full name of the data resource.
    LONG_NAME: str = 'BBBike exports of OpenStreetMap data'

    #: URL of the homepage to the free download server.
    URL: str = 'https://download.bbbike.org/osm/bbbike/'

    #: Default download directory.
    DEFAULT_DOWNLOAD_DIR: str = "osm_data/bbbike"

    #: Valid file formats.
    FILE_FORMATS: set = {
        '.pbf',
        '.gz',
        '.shp.zip',
        '.garmin-ontrail-latin1.zip',
        '.garmin-onroad-latin1.zip',
        '.garmin-opentopo-latin1.zip',
        '.garmin-osm.zip',
        '.geojson.xz',
        '.mapsforge-osm.zip',
        '.mbtiles-openmaptiles.zip',
        '.csv.xz',
    }

    def __init__(self, download_dir=None, update=False, **kwargs):
        """
        :param download_dir: (a path or a name of) a directory for saving downloaded data files;
            if ``download_dir=None`` (default), the downloaded data files are saved into a folder
            named ``'osm_data'`` under the current working directory
        :type download_dir: str | None

        :ivar set valid_subregion_names: names of (sub)regions available on
            BBBike free download server
        :ivar set valid_file_formats: filename extensions of the data files available on
            BBBike free download server
        :ivar pandas.DataFrame subregion_index: index of download pages
            for all available (sub)regions
        :ivar pandas.DataFrame catalogue: a catalogue (index) of all available BBBike downloads
        :ivar str | None download_dir: name or pathname of a directory
            for saving downloaded data files (in accordance with the parameter ``download_dir``)
        :ivar list data_pathnames: list of pathnames of all downloaded data files

        **Examples**::

            >>> from pydriosm.downloader import BBBikeDownloader
            >>> import os
            >>> bbd = BBBikeDownloader()
            >>> bbd.NAME
            'BBBike'
            >>> bbd.LONG_NAME
            'BBBike exports of OpenStreetMap data'
            >>> bbd.URL
            'https://download.bbbike.org/osm/bbbike/'
            >>> os.path.relpath(bbd.download_dir)
            'osm_data\\bbbike'
            >>> bbd = BBBikeDownloader(download_dir="tests\\osm_data")
            >>> os.path.relpath(bbd.download_dir)
            'tests\\osm_data'
        """

        super().__init__(download_dir=download_dir)

        kwargs.update({'update': update})

        self.valid_subregion_names = self.get_bbbike_cities(**kwargs)
        self.subregion_coordinates = self.get_bbbike_city_polygons(**kwargs)
        self.subregion_index = self.get_subregion_index(**kwargs)
        self.catalogue = self.get_catalogue(**kwargs)
        # self.valid_file_formats = set(self.catalogue['FileFormat'])

    @classmethod
    def get_bbbike_cities(cls, update=False, confirmation_required=True, verbose=False,
                          raise_error=False):
        # noinspection PyUnresolvedReferences
        """
        Get the names of all the available cities.

        :param update: whether to (check on and) update the prepacked data, defaults to ``False``
        :type update: bool
        :param confirmation_required: whether asking for confirmation to proceed,
            defaults to ``True``
        :type confirmation_required: bool
        :param verbose: whether to print relevant information in console, defaults to ``False``
        :type verbose: bool | int
        :param raise_error: Whether to raise the provided exception;
            if ``raise_error=False`` (default), the error will be suppressed.
        :type raise_error: bool
        :return: list of names of cities available on BBBike free download server
        :rtype: list | None

        **Examples**::

            >>> from pydriosm.downloader import BBBikeDownloader
            >>> bbd = BBBikeDownloader()
            >>> bbbike_cities = bbd.get_bbbike_cities()
            >>> bbbike_cities[:5]
            ['Aachen', 'Aarhus', 'Adelaide', 'Albuquerque', 'Alexandria']
        """

        data_name = f'{cls.NAME} cities'

        cities = cls.get_prepacked_data(
            fetch_bbbike_cities, url=cls.URL, data_name=data_name, update=update,
            confirmation_required=confirmation_required, verbose=verbose, raise_error=raise_error)

        return cities

    @classmethod
    def get_bbbike_city_polygons(cls, update=False, confirmation_required=True, verbose=False,
                                 raise_error=False):
        # noinspection PyUnresolvedReferences
        """
        Get location information of all cities available on the download server.

        :param update: whether to (check on and) update the prepacked data, defaults to ``False``
        :type update: bool
        :param confirmation_required: whether asking for confirmation to proceed,
            defaults to ``True``
        :type confirmation_required: bool
        :param verbose: whether to print relevant information in console, defaults to ``False``
        :type verbose: bool | int
        :param raise_error: Whether to raise the provided exception;
            if ``raise_error=False`` (default), the error will be suppressed.
        :type raise_error: bool
        :return: location information of BBBike cities, i.e. geographic (sub)regions
        :rtype: pandas.DataFrame | None

        **Examples**::

            >>> from pydriosm.downloader import BBBikeDownloader
            >>> bbd = BBBikeDownloader()
            >>> bbbike_city_polygons = bbd.get_bbbike_city_polygons()
            >>> type(bbbike_city_polygons)
            pandas.DataFrame
            >>> bbbike_city_polygons.shape
            (238, 2)
            >>> bbbike_city_polygons.head()
                      name                                           geometry
            0       Aachen  POLYGON ((5.88 50.6, 6.58 50.6, 6.58 50.99, 5....
            1       Aarhus  POLYGON ((9.82 55.99, 10.37 55.99, 10.37 56.29...
            2     Adelaide  POLYGON ((138.46 -35.03, 138.74 -35.03, 138.74...
            3  Albuquerque  POLYGON ((-106.8 35, -106.47 35, -106.47 35.22...
            4   Alexandria  POLYGON ((29.7 31.02, 30.21 31.02, 30.21 31.34...
        """

        data_name = f'{cls.NAME} cities poly'

        cities_coords = cls.get_prepacked_data(
            fetch_bbbike_city_polygons, url=cls.URL, raise_error=raise_error,
            data_name=data_name, update=update, confirmation_required=confirmation_required,
            verbose=verbose)

        return cities_coords

    @classmethod
    def get_subregion_index(cls, update=False, confirmation_required=True, verbose=False,
                            raise_error=False):
        # noinspection PyShadowingNames,PyUnresolvedReferences
        """
        Get a catalogue for geographic (sub)regions.

        :param update: whether to (check on and) update the prepacked data, defaults to ``False``
        :type update: bool
        :param confirmation_required: whether asking for confirmation to proceed,
            defaults to ``True``
        :type confirmation_required: bool
        :param verbose: whether to print relevant information in console, defaults to ``False``
        :type verbose: bool | int
        :param raise_error: Whether to raise the provided exception;
            if ``raise_error=False`` (default), the error will be suppressed.
        :type raise_error: bool
        :return: catalogue for subregions of BBBike data
        :rtype: pandas.DataFrame | None

        **Examples**::

            >>> from pydriosm.downloader import BBBikeDownloader
            >>> bbd = BBBikeDownloader()
            >>> # A BBBike catalogue of geographic (sub)regions
            >>> subregion_index = bbd.get_subregion_index()
            >>> subregion_index.shape
            (238, 3)
            >>> subregion_index.head()
                      name  ...                                                url
            0       Aachen  ...     https://download.bbbike.org/osm/bbbike/Aachen/
            1       Aarhus  ...     https://download.bbbike.org/osm/bbbike/Aarhus/
            2     Adelaide  ...   https://download.bbbike.org/osm/bbbike/Adelaide/
            3  Albuquerque  ...  https://download.bbbike.org/osm/bbbike/Albuque...
            4   Alexandria  ...  https://download.bbbike.org/osm/bbbike/Alexand...
            [5 rows x 3 columns]
            >>> subregion_index.columns.to_list()
            ['name', 'last_modified', 'url']
        """

        data_name = f'{cls.NAME} index of subregions'

        subregion_index = cls.get_prepacked_data(
            fetch_bbbike_subregion_index, url=cls.URL, data_name=data_name, update=update,
            confirmation_required=confirmation_required, verbose=verbose, raise_error=raise_error)

        return subregion_index

    @classmethod
    def get_valid_subregion_names(cls, update=False, confirmation_required=True, verbose=False,
                                  raise_error=False):
        # noinspection PyShadowingNames
        """
        Get a list of names of all geographic (sub)regions.

        :param update: whether to (check on and) update the prepacked data, defaults to ``False``
        :type update: bool
        :param confirmation_required: whether asking for confirmation to proceed,
            defaults to ``True``
        :type confirmation_required: bool
        :param verbose: whether to print relevant information in console, defaults to ``False``
        :type verbose: bool | int
        :param raise_error: Whether to raise the provided exception;
            if ``raise_error=False`` (default), the error will be suppressed.
        :type raise_error: bool
        :return: a list of geographic (sub)region names available on BBBike free download server
        :rtype: list | None

        **Examples**::

            >>> from pydriosm.downloader import BBBikeDownloader
            >>> bbd = BBBikeDownloader()
            >>> # A list of names of all BBBike geographic (sub)regions
            >>> subregion_names = bbd.get_valid_subregion_names()
            >>> type(subregion_names)
            list
            >>> len(subregion_names)
            237
        """

        data_name = f'{cls.NAME} subregion names'

        if update:
            args = {
                'update': update,
                'confirmation_required': False,
                'verbose': False,
                'raise_error': raise_error,
            }
            _ = cls.get_subregion_index(**args)
            _ = cls.get_bbbike_cities(**args)

        subregion_names = cls.get_prepacked_data(
            fetch_bbbike_valid_subregion_names, cls_instance=cls,
            data_name=data_name, update=update, confirmation_required=confirmation_required,
            verbose=verbose, raise_error=raise_error)

        return subregion_names

    def validate_subregion_name(self, subregion_name, valid_names=None, raise_error=True, **kwargs):
        # noinspection PyShadowingNames
        """
        Validate an input name of a geographic (sub)region.

        The validation is done by matching the input ``subregion_name`` to
        a name of a geographic (sub)region available on BBBike free download server.

        :param subregion_name: name of a (sub)region available on BBBike free download server
        :type subregion_name: str
        :param valid_names: names of all (sub)regions available on a free download server
        :type valid_names: typing.Iterable
        :param raise_error: (if the input fails to match a valid name) whether to raise the error
            :py:class:`pydriosm.downloader.InvalidSubregionName`, defaults to ``True``
        :type raise_error: bool
        :return: valid (sub)region name that matches, or is the most similar to, the input
        :rtype: str

        **Examples**::

            >>> from pydriosm.downloader import BBBikeDownloader
            >>> bbd = BBBikeDownloader()
            >>> subregion_name = 'birmingham'
            >>> subregion_name_ = bbd.validate_subregion_name(subregion_name)
            >>> subregion_name_
            'Birmingham'
        """

        valid_names_ = self.valid_subregion_names if valid_names is None else valid_names

        subregion_name_ = super().validate_subregion_name(
            subregion_name=subregion_name, valid_names=valid_names_, raise_error=raise_error,
            **kwargs)

        return subregion_name_

    def get_sub_catalogue(self, subregion_name, update=False, confirmation_required=True,
                          verbose=False, raise_error=False):
        # noinspection PyShadowingNames,PyUnresolvedReferences
        """
        Get a download catalogue of OSM data available for a given geographic (sub)region.

        :param subregion_name: name of a (sub)region available on BBBike free download server
        :type subregion_name: str
        :param update: whether to (check on and) update the prepacked data, defaults to ``False``
        :type update: bool
        :param confirmation_required: whether asking for confirmation to proceed,
            defaults to ``True``
        :type confirmation_required: bool
        :param verbose: whether to print relevant information in console, defaults to ``False``
        :type verbose: bool | int
        :param raise_error: Whether to raise the provided exception;
            if ``raise_error=False`` (default), the error will be suppressed.
        :type raise_error: bool
        :return: a catalogues for subregion downloads
        :rtype: pandas.DataFrame | None

        **Examples**::

            >>> from pydriosm.downloader import BBBikeDownloader
            >>> bbd = BBBikeDownloader()
            >>> subregion_name = 'birmingham'
            >>> # A download catalogue for Leeds
            >>> bham_catalogue = bbd.get_sub_catalogue(subregion_name, verbose=True)
            To retrieve/compile data of a download catalogue for "Birmingham"
            ? [No]|Yes: yes
            Retrieving/compiling the data ... Done.
            >>> bham_catalogue.shape
            (15, 5)
            >>> bham_catalogue.head()
                                               filename  ...                last_update
            0                        Birmingham.osm.pbf  ...  2026-02-28 18:54:17+00:00
            1                         Birmingham.osm.gz  ...  2026-03-01 04:52:14+00:00
            2                    Birmingham.osm.shp.zip  ...  2026-03-01 05:40:06+00:00
            3  Birmingham.osm.garmin-ontrail-latin1.zip  ...  2026-03-01 06:15:16+00:00
            4   Birmingham.osm.garmin-onroad-latin1.zip  ...  2026-03-01 06:14:56+00:00
            [5 rows x 5 columns]
            >>> bham_catalogue.columns.tolist()
            ['filename', 'url', 'data_type', 'size', 'last_update']
        """

        subregion_name_ = self.validate_subregion_name(subregion_name, raise_error=raise_error)

        data_name = f'a download catalogue for "{subregion_name_}"'

        sub_catalogue = self.get_prepacked_data(
            meth=fetch_bbbike_sub_catalogue, subregion_name=subregion_name_, url=self.URL,
            raise_error=raise_error,
            data_name=data_name, update=update, confirmation_required=confirmation_required,
            dump_backup=False, verbose=verbose)

        return sub_catalogue

    @classmethod
    def get_catalogue(cls, update=False, confirmation_required=True, verbose=False,
                      raise_error=False):
        # noinspection PyUnresolvedReferences
        """
        Get a dict-type index of available formats, data types and a download catalogue.

        :param update: whether to (check on and) update the prepacked data, defaults to ``False``
        :type update: bool
        :param confirmation_required: whether asking for confirmation to proceed,
            defaults to ``True``
        :type confirmation_required: bool
        :param verbose: whether to print relevant information in console, defaults to ``False``
        :type verbose: bool | int
        :param raise_error: Whether to raise the provided exception;
            if ``raise_error=False`` (default), the error will be suppressed.
        :type raise_error: bool
        :return: a list of available formats, a list of available data types and
            a dictionary of download catalogue
        :rtype: dict | None

        **Examples**::

            >>> from pydriosm.downloader import BBBikeDownloader
            >>> bbd = BBBikeDownloader()
            >>> # Index for downloading OSM data available on the BBBike free download server
            >>> bbbike_catalogue = bbd.get_catalogue()
            >>> list(bbbike_catalogue.keys())
            ['FileFormat', 'DataType', 'Catalogue']
            >>> catalogue = bbbike_catalogue['Catalogue']
            >>> type(catalogue)
            dict
            >>> bham_catalogue = catalogue['Birmingham']
            >>> type(bham_catalogue)
            pandas.core.frame.DataFrame
            >>> bham_catalogue.shape
            (13, 5)
            >>> bham_catalogue.head()
                                               filename  ...                last_update
            0                        Birmingham.osm.pbf  ...  2025-09-27 18:51:39+00:00
            1                         Birmingham.osm.gz  ...  2025-09-28 05:37:57+00:00
            2                    Birmingham.osm.shp.zip  ...  2025-09-28 05:54:16+00:00
            3  Birmingham.osm.garmin-ontrail-latin1.zip  ...  2025-09-28 07:05:18+00:00
            4   Birmingham.osm.garmin-onroad-latin1.zip  ...  2025-09-28 07:04:54+00:00
            [5 rows x 5 columns]
        """

        data_name = f'{cls.NAME} downloads catalogue'

        download_index = cls.get_prepacked_data(
            fetch_bbbike_catalogue, cls_instance=cls, data_name=data_name, update=update,
            confirmation_required=confirmation_required, verbose=verbose, action_prompt_note="",
            action_prompt_end=" ... \n" if verbose == 2 else " ... ",
            ending_message="    Fetching completed.", raise_error=raise_error)

        return download_index

    def validate_file_format(self, osm_file_format, valid_formats=None, raise_error=True, **kwargs):
        # noinspection PyShadowingNames
        """
        Validate an input file format of OSM data.

        The validation is done by matching the input ``osm_file_format`` to a filename extension
        available on BBBike free download server.

        :param osm_file_format: file format/extension of the OSM data
            available on BBBike free download server
        :type osm_file_format: str
        :param valid_formats: fil extensions of the data available on a free download server
        :type valid_formats: typing.Iterable
        :param raise_error: (if the input fails to match a valid name) whether to raise the error
            :py:class:`pydriosm.downloader.InvalidFileFormatError`, defaults to ``True``
        :type raise_error: bool
        :return: valid file format (file extension)
        :rtype: str

        **Examples**::

            >>> from pydriosm.downloader import BBBikeDownloader
            >>> bbd = BBBikeDownloader()
            >>> osm_file_format_ = bbd.validate_file_format(osm_file_format='PBF')
            >>> osm_file_format_
            '.pbf'
            >>> osm_file_format_ = bbd.validate_file_format(osm_file_format='.osm.pbf')
            >>> osm_file_format_
            '.pbf'
        """

        valid_formats_ = self.FILE_FORMATS if valid_formats is None else valid_formats

        osm_file_format_ = super().validate_file_format(
            osm_file_format=osm_file_format, valid_formats=valid_formats_, raise_error=raise_error,
            **kwargs)

        return osm_file_format_

    def get_subregion_download_url(self, subregion_name, osm_file_format, update=False,
                                   verbose=False, raise_error=True):
        # noinspection PyShadowingNames
        """
        Get a valid URL for downloading OSM data of a specific file format
        for a geographic (sub)region.

        :param subregion_name: name of a (sub)region available on BBBike free download server
        :type subregion_name: str
        :param osm_file_format: file format/extension of the OSM data
            available on the download server
        :type osm_file_format: str
        :param update: whether to (check on and) update the prepacked data, defaults to ``False``
        :type update: bool
        :param verbose: whether to print relevant information in console, defaults to ``False``
        :type verbose: bool | int
        :param raise_error: (if the input fails to match a valid name) whether to raise an
            :py:class:`pydriosm.errors.InvalidSubregionNameError` or
            :py:class:`~pydriosm.errors.InvalidFileFormatError`; defaults to ``True``
        :type raise_error: bool
        :return: a valid name of ``subregion_name`` and
            a download URL for the given ``osm_file_format``
        :rtype: tuple

        **Examples**::

            >>> from pydriosm.downloader import BBBikeDownloader
            >>> bbd = BBBikeDownloader()
            >>> subregion_name, osm_file_format = 'birmingham', "pbf"
            >>> # Get a valid subregion name and its download URL
            >>> subregion_name_, download_url = bbd.get_subregion_download_url(
            ...     subregion_name, osm_file_format)
            >>> subregion_name_
            'Birmingham'
            >>> download_url
            'https://download.bbbike.org/osm/bbbike/Birmingham/Birmingham.osm.pbf'
            >>> osm_file_format = "csv.xz"
            >>> subregion_name_, download_url = bbd.get_subregion_download_url(
            ...     subregion_name, osm_file_format)
            >>> subregion_name_
            'Birmingham'
            >>> download_url
            'https://download.bbbike.org/osm/bbbike/Birmingham/Birmingham.osm.csv.xz'
        """

        subregion_name_ = self.validate_subregion_name(
            subregion_name=subregion_name, raise_error=raise_error)

        osm_file_format_ = ".osm" + self.validate_file_format(
            osm_file_format=osm_file_format, raise_error=raise_error)

        # Fetch the download URL
        try:
            sub_dwnld_cat = self.catalogue['Catalogue'][subregion_name_]

            filename = subregion_name_ + osm_file_format_

            download_url = sub_dwnld_cat.loc[sub_dwnld_cat['filename'] == filename, 'url'].values[0]

            return subregion_name_, download_url

        except Exception as e:
            _print_failure_message(e, verbose=verbose, raise_error=raise_error)
            return None, None

    def get_valid_download_info(self, subregion_name, osm_file_format, download_dir=None, **kwargs):
        # noinspection PyShadowingNames
        """
        Get information of downloading (or downloaded) data file.

        The information includes a valid subregion name, a default filename, a URL and
        an absolute path where the data file is (to be) saved locally.

        :param subregion_name: name of a (sub)region available on BBBike free download server
        :type subregion_name: str
        :param osm_file_format: file format/extension of the OSM data
            available on the download server
        :type osm_file_format: str
        :param download_dir: directory for saving the downloaded file(s), defaults to ``None``;
            when ``download_dir=None``, it refers to :func:`~pydriosm.utils.cdd_bbbike`.
        :type download_dir: str | None
        :return: valid subregion name, filename, download url and absolute file path
        :rtype: tuple

        **Examples**::

            >>> from pydriosm.downloader import BBBikeDownloader
            >>> import os
            >>> bbd = BBBikeDownloader()
            >>> subregion_name = 'birmingham'
            >>> osm_file_format = "shp"
            >>> # valid subregion name, filename, download url and absolute file path
            >>> subregion_name_, pbf_filename, download_url, pbf_pathname = \
            ...     bbd.get_valid_download_info(subregion_name, osm_file_format)
            >>> subregion_name_
            'Birmingham'
            >>> pbf_filename
            'Birmingham.osm.shp.zip'
            >>> download_url
            'https://download.bbbike.org/osm/bbbike/Birmingham/Birmingham.osm.shp.zip'
            >>> os.path.relpath(pbf_pathname)  # (on Windows)
            'osm_data\\bbbike\\birmingham\\Birmingham.osm.shp.zip'
            >>> # Create a new instance with a given download directory
            >>> bbd = BBBikeDownloader(download_dir="tests/osm_data")
            >>> _, _, _, pbf_pathname = bbd.get_valid_download_info(subregion_name, osm_file_format)
            >>> os.path.relpath(pbf_pathname)  # (Returns the same pathname on Windows)
            'tests\\osm_data\\birmingham\\Birmingham.osm.shp.zip'
        """

        subregion_name_, osm_filename, download_url, file_pathname = \
            super().get_valid_download_info(
                subregion_name=subregion_name, osm_file_format=osm_file_format,
                download_dir=download_dir, **kwargs)

        return subregion_name_, osm_filename, download_url, file_pathname

    def file_exists(self, subregion_name, osm_file_format, data_dir=None, update=False,
                    verbose=False, ret_file_path=False):
        # noinspection PyShadowingNames
        """
        Check if a requested data file of a geographic (sub)region already exists locally,
        given its default filename.

        :param subregion_name: name of a (sub)region available on BBBike free download server
        :type subregion_name: str
        :param osm_file_format: file format/extension of the OSM data
            available on the download server
        :type osm_file_format: str
        :param data_dir: directory where the data file (or files) is (or are) stored,
            defaults to ``None``; when ``data_dir=None``, it refers to
            :func:`~pydriosm.utils.cdd_bbbike`.
        :type data_dir: str | None
        :param update: whether to (check and) update the data, defaults to ``False``
        :type update: bool
        :param verbose: whether to print relevant information in console, defaults to ``False``
        :type verbose: bool | int
        :param ret_file_path: whether to return the path to the data file (if it exists),
            defaults to ``False``
        :type ret_file_path: bool
        :return: whether the requested data file exists; or the path to the data file
        :rtype: bool | str

        **Examples**::

            >>> from pydriosm.downloader import BBBikeDownloader
            >>> from pyhelpers.dirs import delete_dir
            >>> import os
            >>> bbd = BBBikeDownloader()
            >>> subregion_name = 'birmingham'
            >>> osm_file_format = ".shp"
            >>> data_dir = "tests/osm_data"
            >>> # Check whether the PBF data file exists; `ret_file_path` is by default `False`
            >>> pbf_exists = bbd.file_exists(subregion_name, osm_file_format, data_dir)
            >>> pbf_exists
            False
            >>> # Download the PBF data of Birmingham (to the default directory)
            >>> bbd.download_data(subregion_name, osm_file_format, data_dir, verbose=True)
            Proceed to download data in the format '.shp.zip' for the following geographic (sub...
                "Birmingham"
              to "./tests/osm_data/birmingham/"
            ? [No]|Yes: yes
            Downloading "Birmingham.osm.shp.zip" 100%|██████████| 79.0M/79.0M | 949kB/s |...
              Saving "Birmingham.osm.shp.zip" to "./tests/osm_data/birmingham/" ... Done.
            >>> bbd.file_exists(subregion_name, osm_file_format, data_dir)
            True
            >>> # Set `ret_file_path=True`
            >>> pbf_pathname = bbd.file_exists(subregion_name, osm_file_format, ret_file_path=True)
            >>> os.path.relpath(pbf_pathname)
            'tests\\osm_data\\birmingham\\Birmingham.osm.pbf'
            >>> os.path.relpath(data_dir) == os.path.relpath(bbd.download_dir)
            True
            >>> # Remove the directory or the PBF file and check again:
            >>> delete_dir(bbd.download_dir, verbose=True)
            To delete the directory "./tests/osm_data/" (Not empty)
            ? [No]|Yes: yes
            Deleting "./tests/osm_data/" ... Done.
            >>> # Since the default download directory has been deleted
            >>> bbd.file_exists(subregion_name, osm_file_format, data_dir)
            False
        """

        file_exists = super().file_exists(
            subregion_name=subregion_name, osm_file_format=osm_file_format, data_dir=data_dir,
            update=update, verbose=verbose, ret_file_path=ret_file_path)

        return file_exists

    def download_data(self, subregion_names, osm_file_formats, download_dir=None,
                      update=False, confirmation_required=True, interval=None,
                      verify_download_dir=True, verbose=False, ret_download_path=False,
                      **kwargs):
        # noinspection PyShadowingNames
        """
        Download OSM data (of a specific file format) of
        one (or multiple) geographic (sub)region(s).

        :param subregion_names: name of a geographic (sub)region
            (or names of multiple geographic (sub)regions) available on BBBike free download server
        :type subregion_names: str | list
        :param osm_file_formats: file format/extension of the OSM data
            available on the download server
        :type osm_file_formats: str
        :param download_dir: directory for saving the downloaded file(s), defaults to ``None``;
            when ``download_dir=None``, it refers to :func:`~pydriosm.utils.cdd_bbbike`.
        :type download_dir: str | None
        :param update: whether to update the data if it already exists, defaults to ``False``
        :type update: bool
        :param confirmation_required: whether asking for confirmation to proceed,
            defaults to ``True``
        :type confirmation_required: bool
        :param interval: interval (in second) between downloading two subregions,
            defaults to ``None``
        :type interval: int | float | None
        :param verify_download_dir: whether to verify the pathname of the current
            download directory, defaults to ``True``
        :type verify_download_dir: bool
        :param verbose: whether to print relevant information in console, defaults to ``False``
        :type verbose: bool | int
        :param ret_download_path: whether to return the path(s) to the downloaded file(s),
            defaults to ``False``
        :type ret_download_path: bool
        :return: the path(s) to the downloaded file(s) when ``ret_download_path`` is ``True``
        :rtype: list | str

        **Examples**::

            >>> from pydriosm.downloader import BBBikeDownloader
            >>> from pyhelpers.dirs import delete_dir
            >>> import os
            >>> bbd = BBBikeDownloader()
            >>> # Download BBBike PBF data of London
            >>> subregion_name = 'London'
            >>> osm_file_format = "pbf"
            >>> bbd.download_data(subregion_name, osm_file_format, verbose=True)
            Proceed to download data in the format '.pbf' for the following geographic (sub)reg...
                "London"
              to "./osm_data/bbbike/london/"
            ? [No]|Yes: yes
            Downloading "London.osm.pbf" 100%|██████████| 188M/188M | 1.06MB/s | ETA: 00:00
              Saving "London.osm.pbf" to "./osm_data/bbbike/london/" ... Done.
            >>> len(bbd.data_paths)
            1
            >>> os.path.relpath(bbd.data_paths[0])  # (on Windows)
            'osm_data\\bbbike\\london\\London.osm.pbf'
            >>> london_download_dir = os.path.relpath(bbd.download_dir)
            >>> london_download_dir  # (on Windows)
            'osm_data\\bbbike'

            >>> # Download PBF data of Leeds and Birmingham to a given directory
            >>> subregion_names = ['Leeds', 'Birmingham']
            >>> osm_file_format = ['shp', 'pbf']
            >>> download_dir = "tests/osm_data"
            >>> download_paths = bbd.download_data(
            ...     subregion_names, osm_file_format, download_dir, verbose=2,
            ...     ret_download_path=True)
            Proceed to download data in the formats ('.shp.zip', '.pbf') for the following geog...
                "Birmingham"
                "Leeds"
              to "./tests/osm_data/"
            ? [No]|Yes: yes
            Downloading "Leeds.osm.shp.zip" to "./tests/osm_data/leeds/" ... Done.
            Downloading "Leeds.osm.pbf" to "./tests/osm_data/leeds/" ... Done.
            Downloading "Birmingham.osm.shp.zip" to "./tests/osm_data/birmingham/" ... Done.
            Downloading "Birmingham.osm.pbf" to "./tests/osm_data/birmingham/" ... Done.
            >>> len(download_paths)
            4
            >>> len(bbd.data_paths)
            5
            >>> os.path.relpath(bbd.download_dir) == os.path.relpath(download_dir)
            True
            >>> os.path.relpath(os.path.commonpath(download_paths))  # (on Windows)
            'tests\\osm_data'

            >>> # Delete the above download directories
            >>> delete_dir([os.path.dirname(london_download_dir), download_dir], verbose=True)
            To delete the following directories:
              "./osm_data/" (Not empty)
              "./tests/osm_data/" (Not empty)
            ? [No]|Yes: yes
            Deleting:
              "./osm_data/" ... Done.
              "./tests/osm_data/" ... Done.
        """

        (subregion_names_, osm_file_formats_, confirmation_required_, confirmation_prompt,
         existing_file_paths) = self.file_exists_and_more(
            subregion_names=subregion_names, osm_file_formats=osm_file_formats,
            data_dir=download_dir, update=update, confirmation_required=confirmation_required,
            verbose=verbose)

        confirmation_required_ = confirmation_required_ and confirmation_required

        if confirmed(confirmation_prompt, confirmation_required=confirmation_required_):
            download_paths = []

            for sub_reg_name in subregion_names_:
                for osm_file_format_ in osm_file_formats_:
                    # Get essential information for the download
                    _, _, download_url, path_to_file = self.get_valid_download_info(
                        subregion_name=sub_reg_name, osm_file_format=osm_file_format_,
                        download_dir=download_dir)

                    os.makedirs(os.path.dirname(path_to_file), exist_ok=True)

                    if not os.path.isfile(path_to_file) or update:
                        self._download_data(
                            url=download_url, path_to_file=path_to_file, interval=interval,
                            verify_download_dir=False, verbose=verbose, **kwargs)

                    if os.path.isfile(path_to_file):
                        download_paths.append(path_to_file)

            self.verify_download_dir(
                download_dir=download_dir, verify_download_dir=verify_download_dir)

        else:
            print("Cancelled.")

            download_paths = existing_file_paths

        self.data_paths = list(collections.OrderedDict.fromkeys(self.data_paths + download_paths))

        if ret_download_path:
            return download_paths
