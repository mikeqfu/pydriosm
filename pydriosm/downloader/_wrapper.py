"""
Downloads OSM data from free download servers.
"""

from pydriosm.downloader._base import BaseDownloader
from pydriosm.downloader._bbbike import BBBikeDownloader
from pydriosm.downloader._geofabrik import GeofabrikDownloader
from pydriosm.errors import MethodNotAvailableError


class Downloader(BaseDownloader):
    """
    A wrapper of :class:`~pydriosm.downloader.GeofabrikDownloader` and
    :class:`~pydriosm.downloader.BBBikeDownloader`.
    """

    #: A dictionary of downloaders.
    SOURCES: dict = {
        "geofabrik": GeofabrikDownloader,
        "bbbike": BBBikeDownloader,
    }

    #: Homepage URL.
    URL: str = 'https://www.openstreetmap.org/'

    def __init__(self, data_source='geofabrik', download_dir=None, update=False, **kwargs):
        """
        :param data_source: Name of data source.
        :type data_source: str

        :ivar downloader: An instance of source-specific downloader.
        :vartype downloader: BaseDownloader | GeofabrikDownloader | BBBikeDownloader | None
        :ivar data_source: Name of data source.
        :vartype source_name: str

        **Examples**::

            >>> from pydriosm.downloader import Downloader
            >>> downloader = Downloader()
            >>> downloader.get_download_index().head()
                        id  ...                                            updates
            0  afghanistan  ...  https://download.geofabrik.de/asia/afghanistan...
            1       africa  ...       https://download.geofabrik.de/africa-updates
            2      albania  ...  https://download.geofabrik.de/europe/albania-u...
            3      alberta  ...  https://download.geofabrik.de/north-america/ca...
            4      algeria  ...  https://download.geofabrik.de/africa/algeria-u...
            [5 rows x 12 columns]
            >>> downloader.set_source('bbbike')
            >>> downloader.get_download_index()
            Traceback (most recent call last):
                ...
            pydriosm.errors.MethodNotAvailableError:
              The '.get_download_index()' method is not available for 'BBBikeDownloader' (for '...
        """

        super().__init__()  # Ensure base class initialization

        # Predefine attributes to avoid linter warnings
        self.downloader = None
        self.data_source = data_source

        self.set_source(data_source=data_source, download_dir=download_dir, update=update, **kwargs)

    def set_source(self, data_source, download_dir=None, update=False, **kwargs):
        """
        Specify which source to be used.

        :param data_source: Name of data source.
        :type data_source: str
        :param download_dir: The path to a directory for storing the downloaded data files.
        :type download_dir: str | None
        :param update: If ``True``, update the data catalogue for the source-specific downloader
            instance. Defaults to ``False``.
        :type update: bool
        :param kwargs: Additional parameters passed to the source-specific downloader instance.

        **Examples**::

            >>> from pydriosm.downloader import Downloader
            >>> downloader = Downloader()
            >>> downloader.set_source('geofabrik')
            >>> downloader.NAME
            'Geofabrik'
        """

        try:
            if self.downloader is not None:
                var_dict = self.downloader.__class__.__annotations__ | self.downloader.__dict__
                for var_name in var_dict:
                    delattr(self, var_name)

            self.data_source = data_source.lower()

            self.downloader = self.SOURCES.get(self.data_source)(
                download_dir=download_dir, update=update, **kwargs)

            for var_name in self.downloader.__class__.__annotations__ | self.downloader.__dict__:
                setattr(self, var_name, self.downloader.__getattribute__(var_name))

        except KeyError:
            raise ValueError(f'Unsupported source: "{data_source}".')

    def _raise_unavailable_method_error(self, method_name, raise_error=True):
        if raise_error:
            raise MethodNotAvailableError(method_name, self.downloader)

    def get_raw_directory_index(self, url, save_path=None, verbose=False, raise_error=True):
        method_name = self.get_raw_directory_index.__name__

        if hasattr(self.downloader, method_name):
            return self.downloader.get_raw_directory_index(
                url=url,
                save_path=save_path,
                verbose=verbose,
                raise_error=raise_error
            )

        else:
            self._raise_unavailable_method_error(method_name=method_name, raise_error=raise_error)

    def get_download_index(self, update=False, confirmation_required=True, verbose=False,
                           raise_error=True, **kwargs):
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

            >>> from pydriosm.downloader import Downloader
            >>> downloader = Downloader()
            >>> download_index = downloader.get_download_index()
            >>> type(download_index)
            pandas.core.frame.DataFrame
            >>> download_index.shape
            (512, 12)
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

        method_name = self.get_download_index.__name__

        if hasattr(self.downloader, method_name):
            return self.downloader.get_download_index(
                update=update,
                confirmation_required=confirmation_required,
                verbose=verbose,
                raise_error=raise_error,
                **kwargs
            )

        else:
            self._raise_unavailable_method_error(method_name=method_name, raise_error=raise_error)

    def get_subregion_table(self, url, verbose=False, raise_error=True):
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

            >>> from pydriosm.downloader import Downloader
            >>> downloader = Downloader()
            >>> # Download information on the homepage
            >>> subregion_table = downloader.get_subregion_table(url=downloader.URL)
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
            >>> subregion_table = downloader.get_subregion_table(url)
            >>> subregion_table
                      subregion  ... .osm.bz2
            0           Bermuda  ...     None
            1           England  ...     None
            2  Falkland Islands  ...     None
            3          Scotland  ...     None
            4             Wales  ...     None
            [5 rows x 6 columns]
            >>> # Download information about 'Antarctica'
            >>> url = 'https://download.geofabrik.de/antarctica.html'
            >>> subregion_table = downloader.get_subregion_table(url, verbose=True)
            Compiling a subregion list of "Antarctica" ... Failed.
              No data is available for 'Antarctica'.
            >>> subregion_table is None
            True
            >>> # To get more information about the above failure, set `verbose=2`
            >>> subregion_table = downloader.get_subregion_table(url, verbose=2, raise_error=False)
            Compiling a subregion list of "Antarctica" ... Failed.
              No data is available for 'Antarctica'.
              Errors: 'NoneType' object has no attribute 'empty'.
            >>> subregion_table is None
            True
        """
        method_name = self.get_subregion_table.__name__

        if hasattr(self.downloader, method_name):
            return self.downloader.get_subregion_table(
                url=url,
                verbose=verbose,
                raise_error=raise_error
            )

        else:
            self._raise_unavailable_method_error(method_name=method_name, raise_error=raise_error)

    def get_continent_tables(self, update=False, confirmation_required=True, verbose=False,
                             raise_error=True, **kwargs):
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

            >>> from pydriosm.downloader import Downloader
            >>> downloader = Downloader()
            >>> # Download information of subregions for each continent
            >>> continent_tables = downloader.get_continent_tables()
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
            >>> asia_table.shape
            (40, 6)
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

        method_name = self.get_continent_tables.__name__

        if hasattr(self.downloader, method_name):
            return self.downloader.get_continent_tables(
                update=update,
                confirmation_required=confirmation_required,
                verbose=verbose,
                raise_error=raise_error,
                **kwargs
            )

        else:
            self._raise_unavailable_method_error(method_name=method_name, raise_error=raise_error)

    def get_region_subregion_tiers(self, update=False, confirmation_required=True, verbose=False,
                                   raise_error=True):
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

            >>> from pydriosm.downloader import Downloader
            >>> downloader = Downloader()
            >>> # region-subregion tiers, and all regions that have no subregions
            >>> region_subregion_tiers, having_no_subregions = downloader.get_region_subregion_tiers()
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
            >>> len(having_no_subregions)
            484
            >>> # Example: five regions that have no subregions
            >>> having_no_subregions[0:5]
            ['Antarctica', 'Algeria', 'Angola', 'Benin', 'Botswana']
        """

        method_name = self.get_region_subregion_tiers.__name__

        if hasattr(self.downloader, method_name):
            return self.downloader.get_region_subregion_tiers(
                update=update,
                confirmation_required=confirmation_required,
                verbose=verbose,
                raise_error=raise_error
            )

        else:
            self._raise_unavailable_method_error(method_name=method_name, raise_error=raise_error)

    def get_catalogue(self, update=False, confirmation_required=True, verbose=False,
                      raise_error=True):
        """
        Get a catalogue (index) of all available downloads.

        :param update: whether to (check on and) update the prepacked data, defaults to ``False``
        :type update: bool
        :param confirmation_required: whether asking for confirmation to proceed,
            defaults to ``True``
        :type confirmation_required: bool
        :param verbose: whether to print relevant information in console, defaults to ``False``
        :type verbose: bool | int
        :param raise_error: Whether to raise the provided exception;
            if ``raise_error=True`` (default), the error will be suppressed.
        :type raise_error: bool
        :return: a catalogue for all subregion downloads
        :rtype: pandas.DataFrame | None

        **Examples**::

            >>> from pydriosm.downloader import Downloader
            >>> downloader = Downloader()
            >>> # A download catalogue for all subregions
            >>> dwnld_catalog = downloader.get_catalogue()
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
        """

        method_name = self.get_catalogue.__name__

        if hasattr(self.downloader, method_name):
            return self.downloader.get_catalogue(
                update=update,
                confirmation_required=confirmation_required,
                verbose=verbose,
                raise_error=raise_error
            )

        else:
            self._raise_unavailable_method_error(method_name=method_name, raise_error=raise_error)

    def get_valid_subregion_names(self, update=False, confirmation_required=True, verbose=False,
                                  raise_error=True):
        """
        Get names of all available geographic (sub)regions.

        :param update: whether to (check on and) update the prepacked data, defaults to ``False``
        :type update: bool
        :param confirmation_required: whether asking for confirmation to proceed,
            defaults to ``True``
        :type confirmation_required: bool
        :param verbose: whether to print relevant information in console, defaults to ``False``
        :type verbose: bool | int
        :param raise_error: Whether to raise the provided exception;
            if ``raise_error=True`` (default), the error will be suppressed.
        :type raise_error: bool
        :return: names of all geographic (sub)regions available on Geofabrik free download server
        :rtype: set | None

        **Examples**::

            >>> from pydriosm.downloader import Downloader
            >>> downloader = Downloader()
            >>> # A list of the names of available geographic (sub)regions
            >>> valid_subrgn_names = downloader.get_valid_subregion_names()
            >>> type(valid_subrgn_names)
            set
        """

        method_name = self.get_valid_subregion_names.__name__

        if hasattr(self.downloader, method_name):
            return self.downloader.get_valid_subregion_names(
                update=update,
                confirmation_required=confirmation_required,
                verbose=verbose
            )

        else:
            self._raise_unavailable_method_error(method_name=method_name, raise_error=raise_error)

    def validate_subregion_name(self, subregion_name, valid_names=None, raise_error=True,
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

            >>> from pydriosm.downloader import Downloader
            >>> downloader = Downloader()
            >>> subregion_name = 'london'
            >>> downloader.validate_subregion_name(subregion_name)
            'Greater London'
            >>> subregion_name = 'https://download.geofabrik.de/europe/united-kingdom.html'
            >>> downloader.validate_subregion_name(subregion_name)
            'United Kingdom'
        """

        method_name = self.validate_subregion_name.__name__

        if hasattr(self.downloader, method_name):
            return self.downloader.validate_subregion_name(
                subregion_name=subregion_name,
                valid_names=valid_names,
                raise_error=raise_error,
                **kwargs
            )

        else:
            self._raise_unavailable_method_error(method_name=method_name, raise_error=raise_error)

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

            >>> from pydriosm.downloader import Downloader
            >>> downloader = Downloader()
            >>> osm_file_format = ".pbf"
            >>> downloader.validate_file_format(osm_file_format)
            '.osm.pbf'
            >>> osm_file_format = "shp"
            >>> downloader.validate_file_format(osm_file_format)
            '.shp.zip'
        """

        method_name = self.validate_file_format.__name__

        if hasattr(self.downloader, method_name):
            return self.downloader.validate_file_format(
                osm_file_format=osm_file_format,
                valid_formats=valid_formats,
                raise_error=raise_error,
                **kwargs
            )

        else:
            self._raise_unavailable_method_error(method_name=method_name, raise_error=raise_error)

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

            >>> from pydriosm.downloader import Downloader
            >>> downloader = Downloader()
            >>> subregion_name = 'England'
            >>> osm_file_format = ".pbf"
            >>> subregion_name_, download_url = downloader.get_subregion_download_url(
            ...     subregion_name, osm_file_format)
            >>> subregion_name_  # The name of the subregion on the free downloader server
            'England'
            >>> download_url  # The URL of the PBF data file
            'https://download.geofabrik.de/europe/united-kingdom/england-latest.osm.pbf'
            >>> subregion_name = 'britain'
            >>> osm_file_format = ".shp"
            >>> subregion_name_, download_url = downloader.get_subregion_download_url(
            ...     subregion_name, osm_file_format)
            >>> subregion_name_
            'Great Britain'
            >>> download_url is None  # The URL of the shapefile for Great Britain is not available
            True
        """

        method_name = self.get_subregion_download_url.__name__

        if hasattr(self.downloader, method_name):
            return self.downloader.get_subregion_download_url(
                subregion_name=subregion_name,
                osm_file_format=osm_file_format,
                update=update,
                verbose=verbose,
                raise_error=raise_error,
            )

        else:
            self._raise_unavailable_method_error(method_name=method_name, raise_error=raise_error)

    def get_default_filename(self, subregion_name, osm_file_format, update=False,
                             raise_error=True):
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
        :param raise_error: Whether to raise the provided exception;
            if ``raise_error=True`` (default), the error will be suppressed.
        :type raise_error: bool
        :return: default OSM filename for the ``subregion_name``
        :rtype: str | None

        **Examples**::

            >>> from pydriosm.downloader import Downloader
            >>> downloader = Downloader()
            >>> # Default filename of the PBF data of London
            >>> downloader.get_default_filename(subregion_name='london', osm_file_format=".pbf")
            'greater-london-latest.osm.pbf'
            >>> # Default filename of the shapefile data of Great Britain
            >>> downloader.get_default_filename(subregion_name='britain', osm_file_format=".shp")
            No ".shp.zip" data is available to download for "Great Britain".
        """

        method_name = self.get_default_filename.__name__

        if hasattr(self.downloader, method_name):
            return self.downloader.get_default_filename(
                subregion_name=subregion_name,
                osm_file_format=osm_file_format,
                update=update
            )

        else:
            self._raise_unavailable_method_error(method_name=method_name, raise_error=raise_error)

    def get_default_pathname(self, subregion_name, osm_file_format, mkdir=False, update=False,
                             verbose=False, raise_error=True):
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
        :param raise_error: Whether to raise the provided exception;
            if ``raise_error=True`` (default), the error will be suppressed.
        :type raise_error: bool
        :return: default filename of the subregion and default (absolute) path to the file
        :rtype: typing.Tuple[str, str]

        **Examples**::

            >>> from pydriosm.downloader import Downloader
            >>> import os
            >>> downloader = Downloader()
            >>> # Default filename and download path of the PBF data of London
            >>> subregion_name, osm_file_format = 'london', ".pbf"
            >>> pathname, filename = downloader.get_default_pathname(subregion_name, osm_file_format)
            >>> os.path.relpath(os.path.dirname(pathname))
            'osm_data\\geofabrik\\europe\\united-kingdom\\england\\greater-london'
            >>> filename
            'greater-london-latest.osm.pbf'
        """

        method_name = self.get_default_pathname.__name__

        if hasattr(self.downloader, method_name):
            return self.downloader.get_default_pathname(
                subregion_name=subregion_name,
                osm_file_format=osm_file_format,
                mkdir=mkdir,
                update=update,
                verbose=verbose,
            )

        else:
            self._raise_unavailable_method_error(method_name=method_name, raise_error=raise_error)

    def get_subregions(self, *subregion_name, deep=False, raise_error=True):
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
        :param raise_error: Whether to raise the provided exception;
            if ``raise_error=True`` (default), the error will be suppressed.
        :type raise_error: bool
        :return: name(s) of subregion(s) of the given geographic (sub)region or (sub)regions;
            when ``subregion_name=None``, it returns all (sub)regions that have subregions
        :rtype: list

        **Examples**::

            >>> from pydriosm.downloader import Downloader
            >>> downloader = Downloader()
            >>> # Names of all subregions
            >>> all_subrgn_names = downloader.get_subregions()
            >>> type(all_subrgn_names)
            list
            >>> # Names of all subregions of England and North America
            >>> e_na_subrgn_names = downloader.get_subregions('england', 'n america')
            >>> type(e_na_subrgn_names)
            list
            >>> # Names of all subregions of North America
            >>> na_subrgn_names = downloader.get_subregions('n america', deep=True)
            >>> type(na_subrgn_names)
            list
            >>> # Names of subregions of Great Britain
            >>> gb_subrgn_names = downloader.get_subregions('united kingdom')
            >>> len(gb_subrgn_names) == 5
            True
            >>> # Names of all subregions of Great Britain's subregions
            >>> gb_subrgn_names_ = downloader.get_subregions('united kingdom', deep=True)
            >>> len(gb_subrgn_names_) >= len(gb_subrgn_names)
            True
        """

        method_name = self.get_subregions.__name__

        if hasattr(self.downloader, method_name):
            return self.downloader.get_subregions(*subregion_name, deep=deep)

        else:
            self._raise_unavailable_method_error(method_name=method_name, raise_error=raise_error)

    def specify_sub_download_dir(self, subregion_name, osm_file_format, download_dir=None,
                                 raise_error=True, **kwargs):
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
            when ``download_dir=None``, it refers to :func:`~pydriosm.utils.cdd_geofabrik`.
        :type download_dir: str | None
        :param raise_error: Whether to raise the provided exception;
            if ``raise_error=True`` (default), the error will be suppressed.
        :type raise_error: bool
        :param kwargs: [optional] parameters of `pyhelpers.dirs.cd()`_,
            including ``mkdir``(default: ``False``)
        :return: pathname of a download directory
            for downloading data of all subregions of the specified (sub)region and format
        :rtype: str

        .. _`pyhelpers.dirs.cd()`:
            https://pyhelpers.readthedocs.io/en/latest/_generated/pyhelpers.dirs.cd.html

        **Examples**::

            >>> from pydriosm.downloader import Downloader
            >>> import os

            >>> downloader = Downloader()

            >>> subregion_name = 'london'
            >>> osm_file_format = ".pbf"

            >>> # Default download directory (if the requested data file is not available)
            >>> download_pathname = downloader.specify_sub_download_dir(
            ...     subregion_name, osm_file_format)
            >>> os.path.dirname(os.path.relpath(download_pathname))
            'osm_data\\geofabrik\\europe\\united-kingdom\\england\\greater-london'

            >>> # When a download directory is specified
            >>> subregion_name = 'britain'
            >>> osm_file_format = ".shp"
            >>> download_dir = "tests/osm_data"
            >>> download_pathname = downloader.specify_sub_download_dir(
            ...     subregion_name, osm_file_format, download_dir)
            >>> os.path.relpath(download_pathname)
            'tests\\osm_data\\great-britain-shp-zip'

            >>> downloader_ = Downloader(download_dir=download_dir)
            >>> download_pathname = downloader_.specify_sub_download_dir(
            ...     subregion_name, osm_file_format)
            >>> os.path.relpath(download_pathname)
            'tests\\osm_data\\europe\\great-britain\\great-britain-shp-zip'
        """

        method_name = self.specify_sub_download_dir.__name__

        if hasattr(self.downloader, method_name):
            return self.downloader.specify_sub_download_dir(
                subregion_name=subregion_name,
                osm_file_format=osm_file_format,
                download_dir=download_dir,
                **kwargs
            )

        else:
            self._raise_unavailable_method_error(method_name=method_name, raise_error=raise_error)

    def get_valid_download_info(self, subregion_name, osm_file_format, download_dir=None,
                                raise_error=True, **kwargs):
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
            when ``download_dir=None``, it refers to :func:`~pydriosm.utils.cdd_geofabrik`.
        :type download_dir: str | None
        :param raise_error: Whether to raise the provided exception;
            if ``raise_error=True`` (default), the error will be suppressed.
        :type raise_error: bool
        :param kwargs: [optional] parameters of `pyhelpers.dirs.cd()`_,
            including ``mkdir``(default: ``False``)
        :return: valid subregion name, filename, download url and absolute file path
        :rtype: typing.Tuple[str, str, str, str]

        .. _`pyhelpers.dirs.cd()`:
            https://pyhelpers.readthedocs.io/en/latest/_generated/pyhelpers.dirs.cd.html

        **Examples**::

            >>> from pydriosm.downloader import Downloader
            >>> import os

            >>> downloader = Downloader()

            >>> # valid subregion name, filename, download url and absolute file path
            >>> subregion_name = 'london'
            >>> osm_file_format = "pbf"
            >>> info_1 = downloader.get_valid_download_info(subregion_name, osm_file_format)
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
            >>> info_2 = downloader.get_valid_download_info(
            ...     subregion_name, osm_file_format=osm_file_format, download_dir=download_dir)
            >>> _, _, _, file_pathname2 = info_2
            >>> os.path.relpath(os.path.dirname(file_pathname2))
            'tests\\osm_data\\greater-london'

            >>> downloader_ = Downloader(download_dir=download_dir)
            >>> info_3 = downloader_.get_valid_download_info(subregion_name, osm_file_format)
            >>> _, _, _, file_pathname3 = info_3
            >>> os.path.relpath(os.path.dirname(file_pathname3))
            'tests\\osm_data\\europe\\united-kingdom\\england\\greater-london'
        """

        method_name = self.get_valid_download_info.__name__

        if hasattr(self.downloader, method_name):
            return self.downloader.get_valid_download_info(
                subregion_name=subregion_name,
                osm_file_format=osm_file_format,
                download_dir=download_dir,
                **kwargs
            )

        else:
            self._raise_unavailable_method_error(method_name=method_name, raise_error=raise_error)

    def file_exists(self, subregion_name, osm_file_format, data_dir=None, update=False,
                    verbose=False, ret_file_path=False, raise_error=True):
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
            defaults to ``None``; when ``data_dir=None``, it refers to
            :func:`~pydriosm.utils.cdd_geofabrik`.
        :type data_dir: str | None
        :param update: whether to (check and) update the data, defaults to ``False``
        :type update: bool
        :param verbose: whether to print relevant information in console, defaults to ``False``
        :type verbose: bool | int
        :param ret_file_path: whether to return the path to the data file (if it exists),
            defaults to ``False``
        :type ret_file_path: bool
        :param raise_error: Whether to raise the provided exception;
            if ``raise_error=True`` (default), the error will be suppressed.
        :type raise_error: bool
        :return: whether the requested data file exists; or the path to the data file
        :rtype: bool | str

        **Examples**::

            >>> from pydriosm.downloader import Downloader
            >>> from pyhelpers.dirs import delete_dir
            >>> import os

            >>> downloader = Downloader(download_dir="tests/osm_data")

            >>> # Download the PBF data of London (to the default directory)
            >>> subregion_name = 'london'
            >>> osm_file_format = ".pbf"
            >>> downloader.download_data(subregion_name, osm_file_format, verbose=True)
            Proceed to download data in the format '.osm.pbf' for the following geographic (sub...
              "Greater London"
              to "./tests/osm_data/europe/united-kingdom/england/greater-london/"
            ? [No]|Yes: >? yes
            Downloading "greater-london-latest.osm.pbf" 100%|██████████| 123M/123M | 26.8...
              Saving "greater-london-latest.osm.pbf" ...
                to "./tests/osm_data/europe/united-kingdom/england/greater-london/" ... Done.
            >>> # Check whether the PBF data file exists; `ret_file_path` is by default `False`
            >>> pbf_exists = downloader.file_exists(subregion_name, osm_file_format)
            >>> pbf_exists  # If the data file exists at the default directory
            True
            >>> # Set `ret_file_path=True`
            >>> path_to_pbf = downloader.file_exists(
            ...     subregion_name, osm_file_format, ret_file_path=True)
            >>> os.path.relpath(path_to_pbf)  # If the data file exists at the default directory
            'tests\\osm_data\\europe\\united-kingdom\\england\\greater-london\\greater-london-l...

            >>> # Remove the download directory:
            >>> delete_dir(downloader.download_dir, verbose=True)
            To delete the directory "./tests/osm_data/" (Not empty)
            ? [No]|Yes: yes
            Deleting "./tests/osm_data/" ... Done.

            >>> # Check if the data file still exists at the specified download directory
            >>> downloader.file_exists(subregion_name, osm_file_format)
            False
        """

        method_name = self.file_exists.__name__

        if hasattr(self.downloader, method_name):
            return self.downloader.file_exists(
                subregion_name=subregion_name,
                osm_file_format=osm_file_format,
                data_dir=data_dir,
                update=update,
                verbose=verbose,
                ret_file_path=ret_file_path
            )

        else:
            self._raise_unavailable_method_error(method_name=method_name, raise_error=raise_error)

    def get_bbbike_cities(self, update=False, confirmation_required=True, verbose=False,
                          raise_error=True):
        """
        Get the names of all the available cities.

        This can be an alternative to the method
        :meth:`~pydriosm.downloader.BBBikeDownloader.get_valid_subregion_names`.

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

            >>> from pydriosm.downloader import Downloader
            >>> downloader = Downloader(data_source='bbbike')
            >>> bbbike_cities_names = downloader.get_bbbike_cities()
            >>> type(bbbike_cities_names)
            list
        """

        method_name = self.get_bbbike_cities.__name__

        if hasattr(self.downloader, method_name):
            return self.downloader.get_bbbike_cities(
                update=update,
                confirmation_required=confirmation_required,
                verbose=verbose,
                raise_error=raise_error,
            )

        else:
            self._raise_unavailable_method_error(method_name=method_name, raise_error=raise_error)

    def get_bbbike_city_polygons(self, update=False, confirmation_required=True, verbose=False,
                                 raise_error=True):
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

            >>> from pydriosm.downloader import Downloader
            >>> downloader = Downloader(data_source='bbbike')
            >>> # Location information of BBBike cities
            >>> bbbike_city_polygons = downloader.get_bbbike_city_polygons()
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

        method_name = self.get_bbbike_city_polygons.__name__

        if hasattr(self.downloader, method_name):
            return self.downloader.get_bbbike_city_polygons(
                update=update,
                confirmation_required=confirmation_required,
                verbose=verbose,
                raise_error=raise_error,
            )

        else:
            self._raise_unavailable_method_error(method_name=method_name, raise_error=raise_error)

    def get_subregion_index(self, update=False, confirmation_required=True, verbose=False,
                            raise_error=True):
        # noinspection PyShadowingNames
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

            >>> from pydriosm.downloader import Downloader
            >>> downloader = Downloader(data_source='bbbike')
            >>> # A BBBike catalogue of geographic (sub)regions
            >>> subregion_index = downloader.get_subregion_index()
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

        method_name = self.get_subregion_index.__name__

        if hasattr(self.downloader, method_name):
            return self.downloader.get_subregion_index(
                update=update,
                confirmation_required=confirmation_required,
                verbose=verbose,
                raise_error=raise_error,
            )

        else:
            self._raise_unavailable_method_error(method_name=method_name, raise_error=raise_error)

    def get_sub_catalogue(self, subregion_name, update=False, confirmation_required=True,
                          verbose=False, raise_error=True):
        # noinspection PyShadowingNames
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

            >>> from pydriosm.downloader import Downloader
            >>> downloader = Downloader(data_source='bbbike')
            >>> subregion_name = 'birmingham'
            >>> # A download catalogue for Leeds
            >>> bham_catalogue = downloader.get_sub_catalogue(subregion_name, verbose=True)
            Proceed to retrieve/compile data of a download catalogue for "Birmingham"
            ? [No]|Yes: yes
            Retrieving/compiling the data ... Done.
            >>> bham_catalogue.head()
                                               filename  ...                last_update
            0                        Birmingham.osm.pbf  ...  2025-03-15 23:04:23+00:00
            1                         Birmingham.osm.gz  ...  2025-03-16 06:48:42+00:00
            2                    Birmingham.osm.shp.zip  ...  2025-03-16 07:02:01+00:00
            3  Birmingham.osm.garmin-ontrail-latin1.zip  ...  2025-03-16 08:05:24+00:00
            4   Birmingham.osm.garmin-onroad-latin1.zip  ...  2025-03-16 08:05:02+00:00
            [5 rows x 5 columns]
            >>> bham_catalogue.columns.tolist()
            ['filename', 'url', 'data_type', 'size', 'last_update']
        """

        method_name = self.get_sub_catalogue.__name__

        if hasattr(self.downloader, method_name):
            return self.downloader.get_sub_catalogue(
                subregion_name=subregion_name,
                update=update,
                confirmation_required=confirmation_required,
                verbose=verbose,
                raise_error=raise_error,
            )

        else:
            self._raise_unavailable_method_error(method_name=method_name, raise_error=raise_error)

    def download_data(self, subregion_names, osm_file_formats=None, download_dir=None,
                      update=False, confirmation_required=True, interval=None,
                      verify_download_dir=True, verbose=False, ret_download_path=False, deep=False,
                      **kwargs):
        # noinspection PyShadowingNames
        """
        Download OSM data (in a specific file format) of all subregions (if available) for
        one (or multiple) geographic (sub)region(s).

        If no subregion data is available for the region(s) specified by ``subregion_names``,
        then the data of ``subregion_names`` would be downloaded only.

        :param subregion_names: name of a geographic (sub)region
            (or names of multiple geographic (sub)regions) available on Geofabrik.
        :type subregion_names: str | list
        :param osm_file_formats: file format/extension of the OSM data
            available on the download server
        :type osm_file_formats: str | list
        :param download_dir: directory for saving the downloaded file(s), defaults to ``None``;
            when ``download_dir=None``, it refers to :func:`~pydriosm.utils.cdd_geofabrik`.
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

            >>> from pydriosm.downloader import Downloader
            >>> from pyhelpers.dirs import cd, delete_dir
            >>> import os
            >>> downloader = Downloader()

        **Example 1**::

            >>> subregion_names = ['rutland', 'Isle of Wight']
            >>> osm_file_format = ".pbf"
            >>> download_dir = "tests/osm_data"
            >>> downloader.download_data(
            ...     subregion_names, osm_file_format, download_dir, verbose=True)
            Proceed to download data in the format '.osm.pbf' for the following geographic (sub...
              "Isle of Wight"
              "Rutland"
              to "./tests/osm_data/"
            ? [No]|Yes: yes
            Downloading "rutland-latest.osm.pbf" 100%|██████████| 1.89M/1.89M | 5.56MB/s ...
              Saving "rutland-latest.osm.pbf" to "./tests/osm_data/rutland/" ... Done.
            Downloading "isle-of-wight-latest.osm.pbf" 100%|██████████| 8.83M/8.83M | 15....
              Saving "isle-of-wight-latest.osm.pbf" to "./tests/osm_data/isle-of-wight/" ... Done.
            >>> len(downloader.data_paths)
            2
            >>> for fp in downloader.data_paths: print(os.path.relpath(fp))  # (on Windows)
            tests\\osm_data\\rutland\\rutland-latest.osm.pbf
            tests\\osm_data\\isle-of-wight\\isle-of-wight-latest.osm.pbf
            >>> # Try to download data given another list which also includes 'Rutland'
            >>> subregion_names = ['rutland', 'west yorkshire']
            >>> # Set `ret_download_path=True`
            >>> download_paths = downloader.download_data(
            ...     subregion_names, osm_file_format, download_dir, verbose=True,
            ...     ret_download_path=True)
            "rutland-latest.osm.pbf" already exists in "./tests/osm_data/rutland/".
            Proceed to download data in the format '.osm.pbf' for the following geographic (sub...
              "West Yorkshire"
              to "./tests/osm_data/"
            ? [No]|Yes: yes
            Downloading "west-yorkshire-latest.osm.pbf" 100%|██████████| 50.6M/50.6M | 27...
              Saving "west-yorkshire-latest.osm.pbf" ...
                to "./tests/osm_data/west-yorkshire/" ... Done.
            >>> len(downloader.data_paths)  # The pathname of the newly downloaded file is added
            3
            >>> len(download_paths)
            2
            >>> for fp in download_paths: print(os.path.relpath(fp))  # (on Windows)
            tests\\osm_data\\rutland\\rutland-latest.osm.pbf
            tests\\osm_data\\west-yorkshire\\west-yorkshire-latest.osm.pbf
            >>> # Update (or re-download) the existing data file by setting `update=True`
            >>> downloader.download_data(
            ...     subregion_names, osm_file_format, download_dir, update=True, verbose=True)
            "rutland-latest.osm.pbf" already exists in "./tests/osm_data/rutland/".
            "west-yorkshire-latest.osm.pbf" already exists in "./tests/osm_data/west-yorkshire/".
            Proceed to update the data in the format '.osm.pbf' for the following geographic (s...
              "Rutland"
              "West Yorkshire"
              in "./tests/osm_data/"
            ? [No]|Yes: yes
            Downloading "rutland-latest.osm.pbf" 100%|██████████| 1.89M/1.89M | 5.81MB/s ...
              Updating "rutland-latest.osm.pbf" in "./tests/osm_data/rutland/" ... Done.
            Downloading "west-yorkshire-latest.osm.pbf" 100%|██████████| 50.6M/50.6M | 17...
              Updating "west-yorkshire-latest.osm.pbf" ...
                in "./tests/osm_data/west-yorkshire/" ... Done.

        **Example 2**::

            >>> # Download the BBBike OSM data of Leeds (to a given download directory)
            >>> downloader.set_source(data_source='bbbike')
            >>> subregion_names = ['Leeds', 'Birmingham']
            >>> osm_file_formats = ['shp', 'pbf']
            >>> download_paths = downloader.download_data(
            ...     subregion_names, osm_file_formats, download_dir, verbose=2,
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

            >>> # Delete the download directory and the downloaded files
            >>> delete_dir(downloader.download_dir, verbose=True)
            To delete the directory "./tests/osm_data/" (Not empty)
            ? [No]|Yes: yes
            Deleting "./tests/osm_data/" ... Done.

        .. note::

            See also the examples of the methods:
            :meth:`GeofabrikDownloader.download_data()
            <pydriosm.downloader.GeofabrikDownloader.download_data` and
            :meth:`BBBikeDownloader.download_data()
            <pydriosm.downloader.BBBikeDownloader.download_data`.
        """

        args = dict(
            subregion_names=subregion_names,
            osm_file_formats=osm_file_formats,
            download_dir=download_dir,
            update=update,
            confirmation_required=confirmation_required,
            interval=interval,
            verify_download_dir=verify_download_dir,
            verbose=verbose,
            ret_download_path=ret_download_path
        )
        kwargs.update(args)

        if self.data_source == 'geofabrik':
            kwargs.update(dict(deep=deep))
        # elif self.data_source == 'bbbike':
        #     pass

        temp = self.downloader.download_data(**kwargs)

        self.data_paths = self.downloader.data_paths
        self.download_dir = self.downloader.download_dir

        return temp
