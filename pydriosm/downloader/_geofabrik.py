"""
Downloads OSM data from Geofabrik free download server.
"""

import os
import time
import urllib.parse

from pyhelpers._cache import _print_failure_message
from pyhelpers.dirs import cd, validate_dir
from pyhelpers.ops import confirmed
from pyhelpers.store import save_data

from pydriosm.downloader._base import BaseDownloader
from pydriosm.downloader.web_parser import *
from pydriosm.errors import InvalidFileFormatError, InvalidSubregionNameError


class GeofabrikDownloader(BaseDownloader):
    """
    Download OSM data from `Geofabrik`_ free download server.

    .. _`Geofabrik`: https://download.geofabrik.de/
    """

    #: Name of the free download server.
    NAME: str = 'Geofabrik'
    #: Full name of the data resource.
    LONG_NAME: str = 'Geofabrik OpenStreetMap data extracts'
    #: URL of the homepage to the free download server.
    URL: str = 'https://download.geofabrik.de/'
    #: URL of the official download index.
    DOWNLOAD_INDEX_URL: str = urllib.parse.urljoin(URL, 'index-v1.json')
    #: Default download directory.
    DEFAULT_DOWNLOAD_DIR: str = "osm_data/geofabrik"
    #: Valid file formats.
    FILE_FORMATS: set = {'.osm.pbf', '.shp.zip', '.osm.bz2'}

    # noinspection PyUnresolvedReferences
    def __init__(self, download_dir=None, update=False, **kwargs):
        """
        :param download_dir: name or pathname of a directory for saving downloaded data files,
            defaults to ``None``; when ``download_dir=None``, downloaded data files are saved to a
            folder named 'osm_data' under the current working directory
        :type download_dir: str | os.PathLike | pathlib.Path | None

        :ivar valid_subregion_names: names of (sub)regions available on the free download server
        :vartype valid_subregion_names: set
        :ivar valid_file_formats: filename extensions of the data files available
        :vartype self.valid_file_formats: set
        :ivar download_index: index of downloads for all available (sub)regions
        :vartype self.download_index: pandas.DataFrame
        :ivar dict continent_tables: download catalogues for each continent
        :ivar dict region_subregion_tier: region-subregion tier
        :ivar list having_no_subregions: all (sub)regions that have no subregions
        :ivar pandas.DataFrame catalogue: a catalogue (index) of all available downloads
            (similar to :py:attr:`~pydriosm.downloader.GeofabrikDownloader.download_index`)
        :ivar str | None download_dir: name or pathname of a directory
            for saving downloaded data files
        :ivar list data_pathnames: list of pathnames of all downloaded data files

        **Examples**::

            >>> from pydriosm.downloader import GeofabrikDownloader
            >>> import os
            >>> gfd = GeofabrikDownloader()
            >>> gfd.NAME
            'Geofabrik'
            >>> gfd.URL
            'https://download.geofabrik.de/'
            >>> gfd.DOWNLOAD_INDEX_URL
            'https://download.geofabrik.de/index-v1.json'
            >>> os.path.relpath(gfd.download_dir)
            'osm_data\\geofabrik'
            >>> gfd = GeofabrikDownloader(download_dir="tests/osm_data")
            >>> os.path.relpath(gfd.download_dir)
            'tests\\osm_data'
        """

        super().__init__(download_dir=download_dir)

        kwargs.update({'update': update})

        self.download_index = self.get_download_index(**kwargs)

        self.continent_tables = self.get_continent_tables(**kwargs)

        self.region_subregion_tiers, self.having_no_subregions = \
            self.get_region_subregion_tiers(**kwargs)

        self.catalogue = self.get_catalogue(**kwargs)

        self.valid_subregion_names = self.get_valid_subregion_names(**kwargs)

    @classmethod
    def get_raw_directory_index(cls, url, save_path=None, verbose=False, raise_error=False):
        # noinspection PyShadowingNames
        """
        Get a raw directory index (including download information of older file logs).

        :param url: URL of a web page of a data resource (e.g. a subregion)
        :type url: str
        :param save_path:
        :type save_path: str | pathlib.Path | None
        :param verbose: whether to print relevant information in console, defaults to ``False``
        :type verbose: bool | int
        :param raise_error: Whether to raise the provided exception;
            if ``raise_error=False`` (default), the error will be suppressed.
        :type raise_error: bool
        :return: information of raw directory index
        :rtype: pandas.DataFrame | None

        **Examples**::

            >>> from pydriosm.downloader import GeofabrikDownloader
            >>> gfd = GeofabrikDownloader()
            >>> raw_directory_index = gfd.get_raw_directory_index(gfd.URL, verbose=True)
            Collecting the raw directory index on 'https://download.geofabrik.de/' ... Failed.
            No raw directory index is available on the web page.
            >>> raw_directory_index is None
            True
            >>> url = 'https://download.geofabrik.de/europe/great-britain.html'
            >>> raw_directory_index = gfd.get_raw_directory_index(url)
            >>> type(raw_directory_index)
            pandas.core.frame.DataFrame
            >>> raw_directory_index.columns.tolist()
            ['file', 'date', 'size', 'metric_file_size', 'url']
        """

        if verbose:
            print(f"Collecting the raw directory index on '{url}'", end=" ... ")

        try:
            raw_directory_index = get_geofabrik_raw_directory_index(url)

            if verbose:
                print("Done.")

            if save_path:
                save_data(raw_directory_index, path_to_file=save_path, verbose=(verbose == 2))

            return raw_directory_index

        except Exception as e:
            _print_failure_message(e, prefix="Failed.", verbose=verbose, raise_error=raise_error)

    def get_download_index(self, update=False, confirmation_required=True, verbose=False,
                           raise_error=False, **kwargs):
        # noinspection PyShadowingNames
        """
        Get the official index of downloads for all available geographic (sub)regions.

        Similar to the method :meth:`~pydriosm.downloader.GeofabrikDownloader.get_catalogue`.

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
        :return: the official index of all downloads
        :rtype: pandas.DataFrame | None

        **Examples**::

            >>> from pydriosm.downloader import GeofabrikDownloader
            >>> gfd = GeofabrikDownloader()
            >>> download_index = gfd.get_download_index()
            >>> type(download_index)
            pandas.core.frame.DataFrame
            >>> download_index.head()
                        id  ...                                            updates
            0  afghanistan  ...  https://download.geofabrik.de/asia/afghanistan...
            1       africa  ...       https://download.geofabrik.de/africa-updates
            2      albania  ...  https://download.geofabrik.de/europe/albania-u...
            3      alberta  ...  https://download.geofabrik.de/north-america/ca...
            4      algeria  ...  https://download.geofabrik.de/africa/algeria-u...
            [5 rows x 13 columns]
            >>> download_index.columns.to_list()
            ['id',
             'parent',
             'iso3166-1:alpha2',
             'name',
             'iso3166-2',
             'geometry',
             '.osm.pbf',
             '.osm.bz2',
             '.shp.zip',
             'pbf-internal',
             'history',
             'taginfo',
             'updates']
        """

        data_name = f'{self.NAME} index of subregions'

        download_index = self.get_prepacked_data(
            fetch_geofabrik_download_index, data_name=data_name, update=update,
            confirmation_required=confirmation_required, verbose=verbose, raise_error=raise_error,
            **kwargs)

        if update:
            self.download_index = download_index

        return download_index

    @classmethod
    def get_subregion_table(cls, url, verbose=False, raise_error=False):
        # noinspection PyShadowingNames
        """
        Get download information of all geographic (sub)regions on a web page.

        :param url: URL of a subregion's web page
        :type url: str
        :param verbose: whether to print relevant information in console, defaults to ``False``
        :type verbose: bool | int
        :param raise_error: Whether to raise the provided exception;
            if ``raise_error=False`` (default), the error will be suppressed.
        :type raise_error: bool
        :return: download information of all available subregions on the given ``url``
        :rtype: pandas.DataFrame | None

        **Examples**::

            >>> from pydriosm.downloader import GeofabrikDownloader
            >>> gfd = GeofabrikDownloader()
            >>> # Download information on the homepage
            >>> subregion_table = gfd.get_subregion_table(url=gfd.URL)
            >>> subregion_table
                           subregion  ... .osm.bz2
            0                 Africa  ...     None
            1             Antarctica  ...     None
            2                   Asia  ...     None
            3  Australia and Oceania  ...     None
            4        Central America  ...     None
            5                 Europe  ...     None
            6          North America  ...     None
            7          South America  ...     None
            [8 rows x 6 columns]
            >>> subregion_table.columns.to_list()
            ['subregion',
             'subregion-url',
             '.osm.pbf',
             '.osm.pbf-size',
             '.shp.zip',
             '.osm.bz2']
            >>> # Download information about 'Great Britain'
            >>> url = 'https://download.geofabrik.de/europe/united-kingdom.html'
            >>> subregion_table = gfd.get_subregion_table(url)
            >>> subregion_table
              subregion  ... .osm.bz2
            0   England  ...     None
            1  Scotland  ...     None
            2     Wales  ...     None
            [3 rows x 6 columns]
            >>> # Download information about 'Antarctica'
            >>> url = 'https://download.geofabrik.de/antarctica.html'
            >>> subregion_table = gfd.get_subregion_table(url, verbose=True)
            Compiling a subregion list of "Antarctica" ... Failed.
            >>> subregion_table is None
            True
            >>> # To get more information about the above failure, set `verbose=2`
            >>> subregion_table = gfd.get_subregion_table(url, verbose=2)
            Compiling a subregion list of "Antarctica" ... Failed: No data is available for "Ant...
            >>> subregion_table is None
            True
        """

        region_name = url.split('/')[-1].split('.')[0].replace('-', ' ').title()
        if verbose:
            print('Compiling a subregion list{}'.format(
                f' of "{region_name}"' if region_name else ''), end=" ... ")

        try:
            subregion_table = fetch_geofabrik_subregion_table(url)

            if not subregion_table.empty:
                if verbose:
                    print("Done.")

                return subregion_table

            else:
                if verbose:
                    suffix = f': No data is available for "{region_name}".' if verbose == 2 \
                        else "."
                    print(f"Failed{suffix}")

        except Exception as e:
            _print_failure_message(e, prefix="Failed.", verbose=verbose, raise_error=raise_error)

    def get_continent_tables(self, update=False, confirmation_required=True, verbose=False,
                             raise_error=False, **kwargs):
        """
        Get download catalogues for each continent.

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
        :return: download catalogues for each continent
        :rtype: dict | None

        **Examples**::

            >>> from pydriosm.downloader import GeofabrikDownloader
            >>> gfd = GeofabrikDownloader()
            >>> # Download information of subregions for each continent
            >>> continent_tables = gfd.get_continent_tables()
            >>> type(continent_tables)
            dict
            >>> list(continent_tables.keys())
            ['Africa',
             'Antarctica',
             'Asia',
             'Australia and Oceania',
             'Central America',
             'Europe',
             'North America',
             'South America']
            >>> # Information about the data of subregions in Asia
            >>> asia_table = continent_tables['Asia']
            >>> asia_table.head()
                 subregion  ... .osm.bz2
            0  Afghanistan  ...     None
            1      Armenia  ...     None
            2   Azerbaijan  ...     None
            3   Bangladesh  ...     None
            4       Bhutan  ...     None
            [5 rows x 6 columns]
            >>> asia_table.columns.to_list()
            ['subregion',
             'subregion-url',
             '.osm.pbf',
             '.osm.pbf-size',
             '.shp.zip',
             '.osm.bz2']
        """

        data_name = f'{self.NAME} continent tables'

        continents_subregion_tables = self.get_prepacked_data(
            meth=fetch_geofabrik_continent_tables, url=self.URL, data_name=data_name, update=update,
            confirmation_required=confirmation_required, verbose=verbose, raise_error=raise_error,
            **kwargs)

        return continents_subregion_tables

    def get_region_subregion_tiers(self, update=False, confirmation_required=True, verbose=False,
                                   raise_error=False):
        # noinspection PyShadowingNames
        """
        Get region-subregion tier and all (sub)regions that have no subregions.

        This includes all geographic (sub)regions for which data of subregions is unavailable.

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
        :return: region-subregion tier and all (sub)regions that have no subregions
        :rtype: tuple[dict, list] | tuple[None, None]

        **Examples**::

            >>> from pydriosm.downloader import GeofabrikDownloader
            >>> gfd = GeofabrikDownloader()
            >>> # region-subregion tiers, and all regions that have no subregions
            >>> region_subregion_tiers, having_no_subregions = gfd.get_region_subregion_tiers()
            >>> type(region_subregion_tiers)
            dict
            >>> # Keys of the region-subregion tier
            >>> list(region_subregion_tiers)
            ['Africa',
             'Antarctica',
             'Asia',
             'Australia and Oceania',
             'Central America',
             'Europe',
             'North America',
             'South America']
            >>> type(having_no_subregions)
            list
            >>> # Example: five regions that have no subregions
            >>> having_no_subregions[0:5]
            ['Antarctica', 'Algeria', 'Angola', 'Benin', 'Botswana']
        """

        data_name = f'{self.NAME} region-subregion tiers'

        if update:
            self.continent_tables = self.get_continent_tables(
                update=update, confirmation_required=False, verbose=False)

        note_msg = "(This process may take a few minutes)"

        data = self.get_prepacked_data(
            compile_geofabrik_region_subregion_tiers, data_name=data_name, update=update,
            confirmation_required=confirmation_required, verbose=verbose,
            confirmation_prompt_note=note_msg, action_prompt_note=note_msg,
            subregion_tables=self.continent_tables, starting_message="... ", end_message=" ",
            raise_error=raise_error)

        if data is None:
            region_subregion_tiers, having_no_subregions = None, None

        else:
            region_subregion_tiers, having_no_subregions = data

            if update is True:
                self.region_subregion_tiers = region_subregion_tiers
                self.having_no_subregions = having_no_subregions

        return region_subregion_tiers, having_no_subregions

    def get_catalogue(self, update=False, confirmation_required=True, verbose=False,
                      raise_error=False):
        """
        Get a catalogue (index) of all available downloads.

        Similar to the method :meth:`~pydriosm.downloader.GeofabrikDownloader.get_download_index`.

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
        :return: a catalogue for all subregion downloads
        :rtype: pandas.DataFrame | None

        **Examples**::

            >>> from pydriosm.downloader import GeofabrikDownloader
            >>> gfd = GeofabrikDownloader()
            >>> # A download catalogue for all subregions
            >>> dwnld_catalog = gfd.get_catalogue()
            >>> type(dwnld_catalog)
            pandas.core.frame.DataFrame
            >>> dwnld_catalog.head()
                           subregion  ... .osm.bz2
            0                 Africa  ...     None
            1             Antarctica  ...     None
            2                   Asia  ...     None
            3  Australia and Oceania  ...     None
            4        Central America  ...     None
            [5 rows x 6 columns]
            >>> dwnld_catalog.columns.to_list()
            ['subregion',
             'subregion-url',
             '.osm.pbf',
             '.osm.pbf-size',
             '.shp.zip',
             '.osm.bz2']

        .. note::

            - Information of
              `London/Enfield
              <https://download.geofabrik.de/europe//united-kingdom/england/london/>`_
              is not directly available from the web page of `Greater London
              <https://download.geofabrik.de/europe//united-kingdom/england/greater-london.html>`_.
            - Two subregions have the same name - 'Georgia':
              `Europe/Georgia <https://download.geofabrik.de/europe/georgia.html>`_ and
              `US/Georgia <https://download.geofabrik.de/north-america/us/georgia.html>`_;
              In the latter case, a suffix ' (US)' is appended.
        """

        data_name = f'{self.NAME} datasets catalogue'

        msg_note = "(This process may take a few minutes)"

        catalogue = self.get_prepacked_data(
            fetch_geofabrik_catalogue, data_name=data_name, update=update,
            confirmation_required=confirmation_required, verbose=verbose,
            confirmation_prompt_note=msg_note, action_prompt_note=msg_note, raise_error=raise_error)

        if update is True:
            self.catalogue = catalogue

        return catalogue

    def get_valid_subregion_names(self, update=False, confirmation_required=True, verbose=False):
        """
        Get names of all available geographic (sub)regions.

        :param update: whether to (check on and) update the prepacked data, defaults to ``False``
        :type update: bool
        :param confirmation_required: whether asking for confirmation to proceed,
            defaults to ``True``
        :type confirmation_required: bool
        :param verbose: whether to print relevant information in console, defaults to ``False``
        :type verbose: bool | int
        :return: names of all geographic (sub)regions available on Geofabrik free download server
        :rtype: set | None

        **Examples**::

            >>> from pydriosm.downloader import GeofabrikDownloader
            >>> gfd = GeofabrikDownloader()
            >>> # A list of the names of available geographic (sub)regions
            >>> valid_subrgn_names = gfd.get_valid_subregion_names()
            >>> type(valid_subrgn_names)
            set
        """

        data_name = f'{self.NAME} subregion names'

        if update:
            _ = self.get_download_index(update=update, confirmation_required=False, verbose=False)

        self.valid_subregion_names = self.get_prepacked_data(
            fetch_valid_geofabrik_subregion_names, data_name=data_name, update=update,
            confirmation_required=confirmation_required, verbose=verbose)

        return self.valid_subregion_names

    def validate_subregion_name(self, subregion_name, valid_names=None, raise_error=False,
                                **kwargs):
        # noinspection PyShadowingNames
        """
        Validate an input name of a geographic (sub)region.

        The validation is done by matching the input to a name of a geographic (sub)region
        available on Geofabrik free download server.

        :param subregion_name: name/URL of a (sub)region available on Geofabrik free download server
        :type subregion_name: str
        :param valid_names: names of all (sub)regions available on a free download server
        :type valid_names: typing.Iterable
        :param raise_error: (if the input fails to match a valid name) whether to raise the error
            :py:class:`pydriosm.downloader.InvalidSubregionName`, defaults to ``True``
        :type raise_error: bool
        :param kwargs: [optional] parameters of `pyhelpers.text.find_similar_str()`_
        :return: valid subregion name that matches (or is the most similar to) the input
        :rtype: str

        .. _`pyhelpers.text.find_similar_str()`:
            https://pyhelpers.readthedocs.io/en/latest/_generated/
            pyhelpers.text.find_similar_str.html

        **Examples**::

            >>> from pydriosm.downloader import GeofabrikDownloader
            >>> gfd = GeofabrikDownloader()
            >>> subregion_name = 'london'
            >>> gfd.validate_subregion_name(subregion_name)
            'Greater London'
            >>> subregion_name = 'https://download.geofabrik.de/europe/united-kingdom.html'
            >>> gfd.validate_subregion_name(subregion_name)
            'United Kingdom'
        """

        valid_names_ = self.valid_subregion_names if valid_names is None else valid_names

        subregion_name_ = super().validate_subregion_name(
            subregion_name=subregion_name, valid_names=valid_names_, raise_error=raise_error,
            **kwargs)

        return subregion_name_

    def validate_file_format(self, osm_file_format, valid_formats=None, raise_error=True, **kwargs):
        # noinspection PyShadowingNames
        """
        Validate an input file format of OSM data.

        The validation is done by matching the input to a filename extension available on
        Geofabrik free download server.

        :param osm_file_format: file format/extension of the OSM data on the free download server
        :type osm_file_format: str
        :param valid_formats: fil extensions of the data available on a free download server
        :type valid_formats: typing.Iterable
        :param raise_error: (if the input fails to match a valid name) whether to raise the error
            :py:class:`pydriosm.downloader.InvalidFileFormatError`, defaults to ``True``
        :type raise_error: bool
        :param kwargs: [optional] parameters of `pyhelpers.text.find_similar_str()`_
        :return: formal file format
        :rtype: str

        .. _`pyhelpers.text.find_similar_str()`:
            https://pyhelpers.readthedocs.io/en/latest/_generated/
            pyhelpers.text.find_similar_str.html

        **Examples**::

            >>> from pydriosm.downloader import GeofabrikDownloader
            >>> gfd = GeofabrikDownloader()
            >>> osm_file_format = ".pbf"
            >>> gfd.validate_file_format(osm_file_format)
            '.osm.pbf'
            >>> osm_file_format = "shp"
            >>> gfd.validate_file_format(osm_file_format)
            '.shp.zip'
        """

        if valid_formats is None:
            valid_file_formats_ = self.FILE_FORMATS
        else:
            valid_file_formats_ = valid_formats

        osm_file_format_ = super().validate_file_format(
            osm_file_format=osm_file_format, valid_formats=valid_file_formats_,
            raise_error=raise_error, **kwargs)

        return osm_file_format_

    def get_subregion_download_url(self, subregion_name, osm_file_format, update=False,
                                   verbose=False, raise_error=True):
        # noinspection PyShadowingNames
        """
        Get a download URL of a geographic (sub)region.

        :param subregion_name: name of a (sub)region available on Geofabrik free download server
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
        :return: name and URL of the subregion
        :rtype: tuple

        **Examples**::

            >>> from pydriosm.downloader import GeofabrikDownloader
            >>> gfd = GeofabrikDownloader()
            >>> subregion_name = 'England'
            >>> osm_file_format = ".pbf"
            >>> subregion_name_, download_url = gfd.get_subregion_download_url(
            ...     subregion_name, osm_file_format)
            >>> subregion_name_  # The name of the subregion on the free downloader server
            'England'
            >>> download_url  # The URL of the PBF data file
            'https://download.geofabrik.de/europe/united-kingdom/england-latest.osm.pbf'
            >>> subregion_name = 'britain'
            >>> osm_file_format = ".shp"
            >>> subregion_name_, download_url = gfd.get_subregion_download_url(
            ...     subregion_name, osm_file_format)
            >>> subregion_name_
            'Great Britain'
            >>> download_url is None  # The URL of the shapefile for Great Britain is not available
            True
        """

        # Update the catalogue only if explicitly requested or if it is None
        if update or self.catalogue is None:
            self.get_catalogue(update=True, verbose=verbose, raise_error=raise_error)

        subregion_name_, osm_file_format_ = fallback_output = None, None

        # Validate inputs
        try:
            subregion_name_ = self.validate_subregion_name(subregion_name=subregion_name)
        except InvalidSubregionNameError as e:
            _print_failure_message(e, verbose=verbose, raise_error=raise_error)

        try:
            osm_file_format_ = self.validate_file_format(osm_file_format=osm_file_format)
        except InvalidFileFormatError as e:
            _print_failure_message(e, verbose=verbose, raise_error=raise_error)

        if not subregion_name_ or not osm_file_format_:
            if verbose:
                print(f"Invalid input: subregion='{subregion_name}', format='{osm_file_format}'")
            return fallback_output

        # Fetch the download URL
        try:
            download_url = self.catalogue.set_index("subregion").loc[
                subregion_name_, osm_file_format_]

            return subregion_name_, download_url

        except (KeyError, AttributeError) as e:
            _print_failure_message(e, verbose=verbose, raise_error=raise_error)
            return fallback_output

    def get_default_filename(self, subregion_name, osm_file_format, update=False):
        # noinspection PyShadowingNames
        """
        get a default filename for a geograpic (sub)region.

        The default filename is derived from the download URL of the requested data file.

        :param subregion_name: name of a (sub)region available on Geofabrik free download server
        :type subregion_name: str
        :param osm_file_format: file format/extension of the OSM data
            available on the download server
        :type osm_file_format: str
        :param update: whether to (check on and) update the prepacked data, defaults to ``False``
        :type update: bool
        :return: default OSM filename for the ``subregion_name``
        :rtype: str | None

        **Examples**::

            >>> from pydriosm.downloader import GeofabrikDownloader
            >>> gfd = GeofabrikDownloader()
            >>> # Default filename of the PBF data of London
            >>> gfd.get_default_filename(subregion_name='london', osm_file_format=".pbf")
            'greater-london-latest.osm.pbf'
            >>> # Default filename of the shapefile data of Great Britain
            >>> gfd.get_default_filename(subregion_name='britain', osm_file_format=".shp")
            No ".shp.zip" data is available to download for "Great Britain".
        """

        subregion_name_, download_url = self.get_subregion_download_url(
            subregion_name=subregion_name, osm_file_format=osm_file_format, update=update)

        if download_url is None:
            osm_file_format_ = self.validate_file_format(osm_file_format)
            print(f'No {osm_file_format_} data is available to download for "{subregion_name_}".')
            default_filename = None

        else:
            default_filename = os.path.basename(download_url)

        return default_filename

    def get_default_pathname(self, subregion_name, osm_file_format, mkdir=False, update=False,
                             verbose=False):
        # noinspection PyShadowingNames
        """
        Get the default pathname of a local directory for storing a downloaded data file.

        The default file path is derived from the download URL of the requested data file.

        :param subregion_name: name of a (sub)region available on Geofabrik free download server
        :type subregion_name: str
        :param osm_file_format: file format/extension of the OSM data
            available on the download server
        :type osm_file_format: str
        :param mkdir: whether to create a directory, defaults to ``False``
        :type mkdir: bool
        :param update: whether to (check on and) update the prepacked data, defaults to ``False``
        :type update: bool
        :param verbose: whether to print relevant information in console, defaults to ``False``
        :type verbose: bool | int
        :return: default filename of the subregion and default (absolute) path to the file
        :rtype: typing.Tuple[str, str]

        **Examples**::

            >>> from pydriosm.downloader import GeofabrikDownloader
            >>> import os
            >>> gfd = GeofabrikDownloader()

            >>> # Default filename and download path of the PBF data of London
            >>> subregion_name, osm_file_format = 'london', ".pbf"
            >>> pathname, filename = gfd.get_default_pathname(subregion_name, osm_file_format)
            >>> os.path.relpath(os.path.dirname(pathname))
            'osm_data\\geofabrik\\europe\\great-britain\\england\\greater-london'
            >>> filename
            'greater-london-latest.osm.pbf'
        """

        subregion_name_, download_url = self.get_subregion_download_url(
            subregion_name=subregion_name, osm_file_format=osm_file_format, update=update)

        if download_url is None:  # The requested data may not exist
            if verbose:
                osm_file_format_ = self.validate_file_format(osm_file_format=osm_file_format)
                print(f"No {osm_file_format_} data is available to download for {subregion_name_}.")

            return None, None

        else:
            parsed_path = str(urllib.parse.urlparse(download_url).path).lstrip('/').split('/')

            default_filename = parsed_path[-1]
            sub_dir_ = re.sub(r'-(latest|free)', '', default_filename.split('.')[0])

            sub_dirs_and_filename = parsed_path[:-1] + [sub_dir_, default_filename]

            default_pathname = self.cdd(*sub_dirs_and_filename, mkdir=mkdir)

        return default_pathname, default_filename

    def _find_subregions(self, subregion_name, region_subregion_tiers=None):
        """
        Find subregions of a given geographic (sub)region.

        :param subregion_name: name of a (sub)region available on Geofabrik free download server
        :type subregion_name: str
        :param region_subregion_tiers: region-subregion tier, defaults to ``None``;
            when ``region_subregion_tier=None``,
            it defaults to the dictionary returned by the method
            :meth:`~pydriosm.downloader.GeofabrikDownloader.get_region_subregion_tiers`
        :type region_subregion_tiers: dict
        :return: name(s) of subregion(s) of the given geographic (sub)region
        :rtype: generator object

        **Examples**::

            >>> from pydriosm.downloader import GeofabrikDownloader
            >>> gfd = GeofabrikDownloader()
            >>> gb_subregions = gfd._find_subregions(subregion_name='Great Britain')
            >>> type(gb_subregions)
            generator
            >>> list(gb_subregions)
            [['England', 'Scotland', 'Wales']]
        """

        if region_subregion_tiers is None:
            region_subregion_tiers, _ = self.get_region_subregion_tiers()
        else:
            region_subregion_tiers = region_subregion_tiers.copy()

        for region_name, subregions in region_subregion_tiers.items():
            if subregion_name == region_name:
                if isinstance(subregions, dict):
                    yield list(subregions.keys())
                else:
                    yield [subregion_name] if isinstance(subregion_name, str) else subregion_name
            elif isinstance(subregions, dict):
                for sub_subregion in self._find_subregions(subregion_name, subregions):
                    if isinstance(sub_subregion, dict):
                        yield list(sub_subregion.keys())
                    else:
                        yield [sub_subregion] if isinstance(sub_subregion, str) else sub_subregion

    def get_subregions(self, *subregion_name, deep=False):
        """
        Retrieve names of all subregions (if any) of the given geographic (sub)region(s).

        The returned result is based on the region-subregion tier structured by the method
        :meth:`~pydriosm.downloader.GeofabrikDownloader.get_region_subregion_tiers`.

        See also [`RNS-1 <https://stackoverflow.com/questions/9807634/>`_].

        :param subregion_name: name of a (sub)region, or names of (sub)regions,
            available on Geofabrik free download server
        :type subregion_name: str | None
        :param deep: whether to get subregion names of the subregions, defaults to ``False``
        :type deep: bool
        :return: name(s) of subregion(s) of the given geographic (sub)region or (sub)regions;
            when ``subregion_name=None``, it returns all (sub)regions that have subregions
        :rtype: list

        **Examples**::

            >>> from pydriosm.downloader import GeofabrikDownloader
            >>> gfd = GeofabrikDownloader()

            >>> # Names of all subregions
            >>> all_subrgn_names = gfd.get_subregions()
            >>> type(all_subrgn_names)
            list

            >>> # Names of all subregions of England and North America
            >>> e_na_subrgn_names = gfd.get_subregions('england', 'n america')
            >>> type(e_na_subrgn_names)
            list

            >>> # Names of all subregions of North America
            >>> na_subrgn_names = gfd.get_subregions('n america', deep=True)
            >>> type(na_subrgn_names)
            list

            >>> # Names of subregions of Great Britain
            >>> gb_subrgn_names = gfd.get_subregions('britain')
            >>> len(gb_subrgn_names) == 3
            True

            >>> # Names of all subregions of Great Britain's subregions
            >>> gb_subrgn_names_ = gfd.get_subregions('britain', deep=True)
            >>> len(gb_subrgn_names_) >= len(gb_subrgn_names)
            True
        """

        if not subregion_name:
            subregion_names = self.having_no_subregions

        else:
            rslt = []
            for subrgn_name in subregion_name:
                subrgn_name = self.validate_subregion_name(subrgn_name)
                subrgn_names = self._find_subregions(subrgn_name, self.region_subregion_tiers)
                rslt += list(subrgn_names)[0]

            if not deep:
                subregion_names = rslt

            else:
                check_list = [x for x in rslt if x not in self.having_no_subregions]

                if len(check_list) > 0:
                    rslt_ = list(set(rslt) - set(check_list))
                    rslt_ += self.get_subregions(*check_list)
                else:
                    rslt_ = rslt

                subregion_names = list(dict.fromkeys(rslt_))

        return subregion_names

    def specify_sub_download_dir(self, subregion_name, osm_file_format, download_dir=None,
                                 **kwargs):
        # noinspection PyShadowingNames
        """
        Specify a directory for downloading data of all subregions of a geographic (sub)region.

        This is useful when the specified format of the data of a geographic (sub)region
        is not available at Geofabrik free download server.

        :param subregion_name: name of a (sub)region available on Geofabrik free download server
        :type subregion_name: str
        :param osm_file_format: file format/extension of the OSM data
            available on the download server
        :type osm_file_format: str
        :param download_dir: directory for saving the downloaded file(s), defaults to ``None``;
            when ``download_dir=None``, it refers to the method
            :meth:`~pydriosm.downloader.GeofabrikDownloader.cdd`
        :type download_dir: str | None
        :param kwargs: [optional] parameters of `pyhelpers.dirs.cd()`_,
            including ``mkdir``(default: ``False``)
        :return: pathname of a download directory
            for downloading data of all subregions of the specified (sub)region and format
        :rtype: str

        .. _`pyhelpers.dirs.cd()`:
            https://pyhelpers.readthedocs.io/en/latest/_generated/pyhelpers.dirs.cd.html

        **Examples**::

            >>> from pydriosm.downloader import GeofabrikDownloader
            >>> import os
            >>> gfd = GeofabrikDownloader()
            >>> subregion_name = 'london'
            >>> osm_file_format = ".pbf"

            >>> # Default download directory (if the requested data file is not available)
            >>> download_pathname = gfd.specify_sub_download_dir(subregion_name, osm_file_format)
            >>> os.path.dirname(os.path.relpath(download_pathname))
            'osm_data\\geofabrik\\europe\\united-kingdom\\england\\greater-london'

            >>> # When a download directory is specified
            >>> subregion_name = 'britain'
            >>> osm_file_format = ".shp"
            >>> download_dir = "tests/osm_data"
            >>> download_pathname = gfd.specify_sub_download_dir(
            ...     subregion_name, osm_file_format, download_dir)
            >>> os.path.relpath(download_pathname)
            'tests\\osm_data\\great-britain-shp-zip'

            >>> gfd_ = GeofabrikDownloader(download_dir=download_dir)
            >>> download_pathname = gfd_.specify_sub_download_dir(subregion_name, osm_file_format)
            >>> os.path.relpath(download_pathname)
            'tests\\osm_data\\europe\\great-britain\\great-britain-shp-zip'
        """

        pathname_and_filename = list(self.get_default_pathname(subregion_name, osm_file_format))

        none_count = len([x for x in pathname_and_filename if x is None])

        if none_count == len(pathname_and_filename):  # The required data file is not available
            subregion_name_ = self.validate_subregion_name(subregion_name=subregion_name)
            osm_file_format_ = self.validate_file_format(osm_file_format=osm_file_format)

            _, dwnld_url = self.get_subregion_download_url(subregion_name_, ".osm.pbf")
            sub_path = self.get_default_sub_path(subregion_name_, dwnld_url).lstrip('\\')
            sub_dir = re.sub(r"[. ]", "-", subregion_name_.lower() + osm_file_format_)

        else:
            file_pathname, filename = pathname_and_filename
            sub_path = os.path.dirname(file_pathname)
            sub_dir = re.sub(r"[. ]", "-", filename).lower()

        if download_dir is None:
            if os.path.join(sub_path, sub_dir) in self.download_dir:
                sub_download_dir = self.download_dir
            else:
                sub_download_dir = cd(self.download_dir, sub_path, sub_dir, **kwargs)
        else:
            sub_download_dir = cd(validate_dir(path_to_dir=download_dir), sub_dir, **kwargs)

        return sub_download_dir

    def get_valid_download_info(self, subregion_name, osm_file_format, download_dir=None, **kwargs):
        # noinspection PyShadowingNames
        """
        Get information of downloading (or downloaded) data file.

        The information includes a valid subregion name, a default filename, a URL and
        an absolute path where the data file is (to be) saved locally.

        :param subregion_name: name of a (sub)region available on
            GeofabrikDownloader free download server
        :type subregion_name: str
        :param osm_file_format: file format/extension of the OSM data
            available on the download server
        :type osm_file_format: str
        :param download_dir: directory for saving the downloaded file(s), defaults to ``None``;
            when ``download_dir=None``, it refers to the method
            :meth:`~pydriosm.downloader.GeofabrikDownloader.cdd`
        :type download_dir: str | None
        :param kwargs: [optional] parameters of `pyhelpers.dirs.cd()`_,
            including ``mkdir``(default: ``False``)
        :return: valid subregion name, filename, download url and absolute file path
        :rtype: typing.Tuple[str, str, str, str]

        .. _`pyhelpers.dirs.cd()`:
            https://pyhelpers.readthedocs.io/en/latest/_generated/pyhelpers.dirs.cd.html

        **Examples**::

            >>> from pydriosm.downloader import GeofabrikDownloader
            >>> import os
            >>> gfd = GeofabrikDownloader()

            >>> # valid subregion name, filename, download url and absolute file path
            >>> subregion_name = 'london'
            >>> osm_file_format = "pbf"
            >>> info_1 = gfd.get_valid_download_info(subregion_name, osm_file_format)
            >>> subregion_name_, osm_filename, download_url, file_pathname = info_1
            >>> subregion_name_
            'Greater London'
            >>> osm_filename
            'greater-london-latest.osm.pbf'
            >>> os.path.dirname(download_url)
            'https://download.geofabrik.de/europe/united-kingdom/england'
            >>> os.path.relpath(os.path.dirname(file_pathname))
            'osm_data\\geofabrik\\europe\\united-kingdom\\england\\greater-london'

            >>> # Specify a new directory for downloaded data
            >>> download_dir = "tests/osm_data"
            >>> info_2 = gfd.get_valid_download_info(subregion_name, osm_file_format, download_dir)
            >>> _, _, _, file_pathname2 = info_2
            >>> os.path.relpath(os.path.dirname(file_pathname2))
            'tests\\osm_data\\greater-london'

            >>> gfd_ = GeofabrikDownloader(download_dir=download_dir)
            >>> info_3 = gfd_.get_valid_download_info(subregion_name, osm_file_format)
            >>> _, _, _, file_pathname3 = info_3
            >>> os.path.relpath(os.path.dirname(file_pathname3))
            'tests\\osm_data\\europe\\united-kingdom\\england\\greater-london'
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
        Check whether a data file of a geographic (sub)region already exists locally,
        given its default filename.

        :param subregion_name: name of a (sub)region available on Geofabrik free download server
        :type subregion_name: str
        :param osm_file_format: file format/extension of the OSM data
            available on the download server
        :type osm_file_format: str
        :param data_dir: directory where the data file (or files) is (or are) stored,
            defaults to ``None``; when ``data_dir=None``, it refers to the method
            :meth:`~pydriosm.downloader.GeofabrikDownloader.cdd`
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

            >>> from pydriosm.downloader import GeofabrikDownloader
            >>> from pyhelpers.dirs import delete_dir
            >>> import os
            >>> gfd = GeofabrikDownloader(download_dir="tests/osm_data")

            >>> # Download the PBF data of London (to the default directory)
            >>> subregion_name = 'london'
            >>> osm_file_format = ".pbf"
            >>> gfd.download_data(subregion_name, osm_file_format, verbose=True)
            To download .osm.pbf data of the following geographic (sub)region(s):
                Greater London
            ? [No]|Yes: yes
            Downloading "greater-london-latest.osm.pbf" ...
                to "./tests/osm_data/europe/united-kingdom/england/greater-london/" ... Done.

            >>> # Check whether the PBF data file exists; `ret_file_path` is by default `False`
            >>> pbf_exists = gfd.file_exists(subregion_name, osm_file_format)
            >>> pbf_exists  # If the data file exists at the default directory
            True

            >>> # Set `ret_file_path=True`
            >>> path_to_pbf = gfd.file_exists(subregion_name, osm_file_format, ret_file_path=True)
            >>> os.path.relpath(path_to_pbf)  # If the data file exists at the default directory
            'tests\\osm_data\\europe\\united-kingdom\\england\\greater-london\\greater-london-...

            >>> # Remove the download directory:
            >>> delete_dir(gfd.download_dir, verbose=True)
            To delete the directory "./tests/osm_data/" (Not empty)
            ? [No]|Yes: yes
            Deleting "./tests/osm_data/" ... Done.

            >>> # Check if the data file still exists at the specified download directory
            >>> gfd.file_exists(subregion_name, osm_file_format)
            False
        """

        file_exists = super().file_exists(
            subregion_name=subregion_name, osm_file_format=osm_file_format, data_dir=data_dir,
            update=update, verbose=verbose, ret_file_path=ret_file_path)

        return file_exists

    def download_data(self, subregion_names, osm_file_formats, download_dir=None, update=False,
                      confirmation_required=True, deep=False, interval=None,
                      verify_download_dir=True, verbose=False, ret_download_path=False,
                      **kwargs):
        # noinspection PyShadowingNames
        """
        Download OSM data (in a specific format) of one (or multiple) geographic (sub)region(s).

        :param subregion_names: name of a geographic (sub)region
            (or names of multiple geographic (sub)regions) available on Geofabrik.
        :type subregion_names: str | list
        :param osm_file_formats: file format/extension of the OSM data
            available on the download server
        :type osm_file_formats: str | list
        :param download_dir: directory for saving the downloaded file(s), defaults to ``None``;
            when ``download_dir=None``, it refers to the method
            :meth:`~pydriosm.downloader.GeofabrikDownloader.cdd`
        :type download_dir: str | None
        :param update: whether to update the data if it already exists, defaults to ``False``
        :type update: bool
        :param confirmation_required: whether asking for confirmation to proceed,
            defaults to ``True``
        :type confirmation_required: bool
        :param deep: whether to further check availability of sub-subregions data,
            defaults to ``False``
        :type deep: bool
        :param interval: interval (in sec) between downloading two subregions, defaults to ``None``
        :type interval: int | float | None
        :param verify_download_dir: whether to verify the pathname of
            the current download directory, defaults to ``True``
        :type verify_download_dir: bool
        :param verbose: whether to print relevant information in console, defaults to ``False``
        :type verbose: bool | int
        :param ret_download_path: whether to return the path(s) to the downloaded file(s),
            defaults to ``False``
        :type ret_download_path: bool
        :param kwargs: optional parameters of `pyhelpers.ops.download_file_from_url()`_
        :return: absolute path(s) to downloaded file(s) when ``ret_download_path`` is ``True``
        :rtype: list | str

        .. _`pyhelpers.ops.download_file_from_url()`:
            https://pyhelpers.readthedocs.io/en/latest/_generated/
            pyhelpers.ops.download_file_from_url.html

        **Examples**::

            >>> from pydriosm.downloader import GeofabrikDownloader
            >>> from pyhelpers.dirs import delete_dir
            >>> import os

        ***Example 1***::

            >>> gfd = GeofabrikDownloader()
            >>> # Download PBF data file of 'Greater London' and 'Rutland'
            >>> subregion_names = ['Isle of Wight', 'rutland']  # Case-insensitive
            >>> osm_file_format = ".pbf"
            >>> gfd.download_data(subregion_names, osm_file_format, verbose=True)
            To download .osm.pbf data of the following geographic (sub)region(s):
                "Isle of Wight"
                "Rutland"
            ? [No]|Yes: yes
            Downloading "isle-of-wight-latest.osm.pbf" 100%|██████████| 8.30M/8.30M | 343...
                Saving "isle-of-wight-latest.osm.pbf" ...
                    to "./osm_data/geofabrik/europe/united-kingdom/england/isle-of-wight/" ... Done.
            Downloading "rutland-latest.osm.pbf" 100%|██████████| 1.83M/1.83M | 4.05MB/s ...
                Saving "rutland-latest.osm.pbf" ...
                    to "./osm_data/geofabrik/europe/united-kingdom/england/rutland/" ... Done.
            >>> len(gfd.data_paths)
            2
            >>> for file_path in gfd.data_paths: print(os.path.basename(file_path))
            isle-of-wight-latest.osm.pbf
            rutland-latest.osm.pbf
            >>> # Since `download_dir` was not specified when instantiating the class,
            >>> #   the data is now in the default download directory
            >>> os.path.relpath(gfd.download_dir)  # (on Windows)
            'osm_data\\geofabrik'
            >>> download_dir_ = os.path.dirname(gfd.download_dir)

            >>> # Download shapefiles of West Midlands (to a given directory "tests/osm_data")
            >>> subregion_name = 'west midlands'  # Case-insensitive
            >>> osm_file_format = [".shp", "pbf"]
            >>> download_dir = "tests/osm_data"
            >>> gfd.download_data(subregion_name, osm_file_format, download_dir, verbose=True)
            To download ('.shp.zip', '.osm.pbf') data of the following geographic (sub)region(s):
                "West Midlands"
            ? [No]|Yes: yes
            Downloading "west-midlands-latest-free.shp.zip" 100%|██████████| 97.3M/97.3M ...
                Saving "west-midlands-latest-free.shp.zip" ...
                    to "./tests/osm_data/west-midlands/" ... Done.
            Downloading "west-midlands-latest.osm.pbf" 100%|██████████| 54.5M/54.5M | 918...
                Saving "west-midlands-latest.osm.pbf" to "./tests/osm_data/west-midlands/" ... ...
            >>> len(gfd.data_paths)
            4
            >>> os.path.relpath(gfd.data_paths[-1])  # (on Windows)
            'tests\\osm_data\\west-midlands\\west-midlands-latest.osm.pbf'
            >>> # Now the `.download_dir` variable has changed to the given one `download_dir`
            >>> os.path.relpath(gfd.download_dir)  # (on Windows)
            'tests\\osm_data'
            >>> # while `.cdd()` remains the default one
            >>> os.path.relpath(gfd.cdd())  # (on Windows)
            'osm_data\\geofabrik'
            >>> # Delete the above downloaded directories
            >>> delete_dir([download_dir_, gfd.download_dir], verbose=True)
            To delete the following directories:
                "./osm_data/" (Not empty)
                "./tests/osm_data/" (Not empty)
            ? [No]|Yes: yes
            Deleting "./osm_data/" ... Done.
            Deleting "./tests/osm_data/" ... Done.

        ***Example 2***::

            >>> # Create a new instance with a pre-specified download directory
            >>> gfd = GeofabrikDownloader(download_dir="tests/osm_data")
            >>> os.path.relpath(gfd.download_dir)  # (on Windows)
            'tests\\osm_data'
            >>> # Download shapefiles of UK (to the directory specified by instantiation)
            >>> # (Note that .shp.zip data is not available for "United Kingdom".)
            >>> subregion_name = 'United Kingdom'  # Case-insensitive
            >>> osm_file_format = ".shp"
            >>> # By default, `deep_retry=False`
            >>> gfd.download_data(subregion_name, osm_file_format, verbose=True)
            To download .shp.zip data of the following geographic (sub)region(s):
                "United Kingdom"
            ? [No]|Yes: yes
            No '.shp.zip' data is available for "United Kingdom".
            Try to download the data of its subregions instead
            ? [No]|Yes: yes
            Downloading "england-latest-free.shp.zip" 100%|██████████| 2.59G/2.59G | 315kB/...
                Saving "england-latest-free.shp.zip"
                    to "./tests/osm_data/europe/great-britain/great-britain-shp-zip/" ... Done.
            Downloading "scotland-latest-free.shp.zip" 100%|██████████| 513M/513M | 275kB/s...
                Saving "scotland-latest-free.shp.zip" ...
                    to "./tests/osm_data/europe/united-kingdom/united-kingdom-shp-zip/" ... Done.
            Downloading "wales-latest-free.shp.zip" 100%|██████████| 230M/230M | 116kB/s | ...
                Saving "wales-latest-free.shp.zip" ...
                    to "./tests/osm_data/europe/united-kingdom/united-kingdom-shp-zip/" ... Done.
            >>> len(gfd.data_paths)
            3
            >>> # Now set `deep_retry=True`
            >>> gfd.download_data(subregion_name, osm_file_format, verbose=1, deep_retry=True)
            To download .shp.zip data of the following geographic (sub)region(s):
                "United Kingdom"
            ? [No]|Yes: yes
            No '.shp.zip' data is available for "United Kingdom".
            Try to download the data of its subregions instead
            ? [No]|Yes: yes
            "wales-latest-free.shp.zip" already exists in "./tests/osm_data/europe/united-kingdom...
            "scotland-latest-free.shp.zip" already exists in "./tests/osm_data/europe/united-king...
            Downloading "bedfordshire-latest.osm.pbf" 100%|██████████| 11.6M/11.6M | 209kB/...
                Saving "bedfordshire-latest.osm.pbf" to "./tests/osm_data/bedfordshire/" ... Done.
            ...
                ...
            Downloading "rutland-latest.osm.pbf" 100%|██████████| 1.83M/1.83M | 354kB/s | E...
                Updating "rutland-latest.osm.pbf" in "./tests/osm_data/rutland/" ... Done.
            ...
                ...
            Downloading "west-yorkshire-latest.osm.pbf" 100%|██████████| 45.2M/45.2M | 110k...
                Updating "west-yorkshire-latest.osm.pbf" ...
                    in "./tests/osm_data/west-yorkshire/" ... Done.
            Downloading "wiltshire-latest.osm.pbf" 100%|██████████| 28.5M/28.5M | 241kB/s |...
                Saving "wiltshire-latest.osm.pbf" to "./tests/osm_data/wiltshire/" ... Done.
            Downloading "worcestershire-latest.osm.pbf" 100%|██████████| 18.5M/18.5M | 220k...
                Saving "worcestershire-latest.osm.pbf" ...
                    to "./tests/osm_data/worcestershire/" ... Done.
            >>> # Check the file paths
            >>> len(gfd.data_paths)
            50
            >>> # Check the current default `download_dir`
            >>> os.path.relpath(gfd.download_dir)  # (on Windows)
            'tests\\osm_data'
            >>> os.path.relpath(os.path.commonpath(gfd.data_paths))  # (on Windows)
            'tests\\osm_data\\europe\\united-kingdom\\united-kingdom-shp-zip'
            >>> # Delete all the downloaded files
            >>> delete_dir(gfd.download_dir, verbose=True)
            To delete the directory "./tests/osm_data/" (Not empty)
            ? [No]|Yes: yes
            Deleting "./tests/osm_data/" ... Done.
        """

        subrgn_names_, file_formats_, cfm_req, confirmation_prompt, existing_file_pathnames = \
            self.file_exists_and_more(
                subregion_names=subregion_names, osm_file_formats=osm_file_formats,
                data_dir=download_dir, update=update, confirmation_required=confirmation_required,
                verbose=verbose, deep=deep)

        if confirmed(confirmation_prompt, confirmation_required=cfm_req and confirmation_required):

            download_paths = []

            for subrgn_name_ in subrgn_names_:
                for file_fmt_ in file_formats_:
                    subregion_name_, _, download_url, file_pathname = self.get_valid_download_info(
                        subregion_name=subrgn_name_, osm_file_format=file_fmt_,
                        download_dir=download_dir)

                    if download_url is None:
                        if verbose:
                            print(f'No \'{file_fmt_}\' data is available for "{subregion_name_}".')

                        cfm_msg_ = "Try to download the data of its subregions instead\n?"
                        if confirmed(prompt=cfm_msg_, confirmation_required=confirmation_required):
                            sub_subregions = self.get_subregions(subregion_name_, deep=deep)

                            if sub_subregions == [subregion_name_]:
                                pass

                            else:
                                dwnld_dir_ = self.specify_sub_download_dir(
                                    subregion_name=subregion_name_, osm_file_format=file_fmt_,
                                    download_dir=download_dir)

                                download_paths_ = self.download_data(
                                    subregion_names=sub_subregions, osm_file_formats=file_fmt_,
                                    download_dir=dwnld_dir_, update=update,
                                    confirmation_required=False, verify_download_dir=False,
                                    verbose=verbose, ret_download_path=True)

                                if isinstance(download_paths_, list):
                                    download_paths += download_paths_

                    else:
                        if not os.path.isfile(file_pathname) or update:
                            self._download_data(
                                url=download_url, path_to_file=file_pathname, verbose=verbose,
                                verify_download_dir=False, **kwargs)

                        if os.path.isfile(file_pathname):
                            download_paths.append(file_pathname)

                    if isinstance(interval, (int, float)):
                        time.sleep(interval)

            self.verify_download_dir(download_dir, verify_download_dir=verify_download_dir)

        else:
            print("Cancelled.")

            download_paths = existing_file_pathnames

        self.data_paths = list(collections.OrderedDict.fromkeys(self.data_paths + download_paths))

        if ret_download_path:
            return download_paths
