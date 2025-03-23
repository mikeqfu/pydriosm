"""
Downloads OSM data from BBBike free download server.
"""

from pyhelpers.dirs import add_slashes, cd, check_relative_pathname, normalize_pathname, \
    validate_dir
from pyhelpers.ops import confirmed

from pydriosm.downloader._downloader import _Downloader
from pydriosm.downloader._web_parser import *


class BBBikeDownloader(_Downloader):
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
    #: URL of a list of cities that are available on the free download server.
    CITIES_URL: str = 'https://raw.githubusercontent.com/wosch/bbbike-world/world/etc/cities.txt'
    #: URL of coordinates of all the available cities.
    CITIES_COORDS_URL: str = \
        'https://raw.githubusercontent.com/wosch/bbbike-world/world/etc/cities.csv'
    #: Default download directory.
    DEFAULT_DOWNLOAD_DIR: str = "osm_data\\bbbike"
    #: Valid file formats.
    FILE_FORMATS: set = {
        '.csv.xz',
        '.garmin-onroad-latin1.zip',
        '.garmin-onroad.zip',
        '.garmin-opentopo.zip',
        '.garmin-osm.zip',
        '.geojson.xz',
        '.gz',
        '.mapsforge-osm.zip',
        '.pbf',
        '.shp.zip',
        '.svg-osm.zip',
    }

    def __init__(self, download_dir=None):
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

        self.valid_subregion_names = self.get_bbbike_cities()
        self.subregion_coordinates = self.get_coordinates_of_cities()
        self.subregion_index = self.get_subregion_index()
        self.catalogue = self.get_catalogue()
        # self.valid_file_formats = set(self.catalogue['FileFormat'])

    @classmethod
    def get_bbbike_cities(cls, update=False, confirmation_required=True, verbose=False,
                          raise_error=False):
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

            >>> from pydriosm.downloader import BBBikeDownloader
            >>> bbd = BBBikeDownloader()
            >>> bbbike_cities_names = bbd.get_bbbike_cities()
            >>> type(bbbike_cities_names)
            list
        """

        data_name = f'{cls.NAME} cities'

        cities_names = cls.get_prepacked_data(
            fetch_bbbike_cities, url=cls.CITIES_URL, data_name=data_name, update=update,
            confirmation_required=confirmation_required, verbose=verbose, raise_error=raise_error)

        return cities_names

    @classmethod
    def get_coordinates_of_cities(cls, update=False, confirmation_required=True, verbose=False,
                                  raise_error=False):
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
            >>> # Location information of BBBike cities
            >>> coords_of_cities = bbd.get_coordinates_of_cities()
            >>> type(coords_of_cities)
            pandas.core.frame.DataFrame
            >>> coords_of_cities.head()
                      City  ... ur_latitude
            0       Aachen  ...       50.99
            1       Aarhus  ...      56.287
            2     Adelaide  ...     -34.753
            3  Albuquerque  ...     35.2173
            4   Alexandria  ...       31.34
            [5 rows x 13 columns]
            >>> coords_of_cities.columns.to_list()
            ['city',
             'real_name',
             'pref._language',
             'local_language',
             'country',
             'area_or_continent',
             'population',
             'step',
             'other_cities',
             'll_longitude',
             'll_latitude',
             'ur_longitude',
             'ur_latitude']
        """

        data_name = f'{cls.NAME} cities coordinates'

        cities_coords = cls.get_prepacked_data(
            fetch_bbbike_city_coordinates, url=cls.CITIES_COORDS_URL, raise_error=raise_error,
            data_name=data_name, update=update, confirmation_required=confirmation_required,
            verbose=verbose)

        return cities_coords

    @classmethod
    def get_subregion_index(cls, update=False, confirmation_required=True, verbose=False,
                            raise_error=False):
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

            >>> from pydriosm.downloader import BBBikeDownloader
            >>> bbd = BBBikeDownloader()
            >>> # A BBBike catalogue of geographic (sub)regions
            >>> subregion_index = bbd.get_subregion_index()
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

        This can be an alternative to the method
        :meth:`~pydriosm.downloader.BBBikeDownloader.get_names_of_cities`.

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

    @classmethod
    def validate_subregion_name(cls, subregion_name, valid_names=None, raise_error=True, **kwargs):
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

        valid_names_ = cls.get_valid_subregion_names(raise_error=raise_error) \
            if valid_names is None else valid_names

        subregion_name_ = super().validate_subregion_name(
            subregion_name=subregion_name, valid_names=valid_names_, raise_error=raise_error,
            **kwargs)

        return subregion_name_

    @classmethod
    def get_sub_catalogue(cls, subregion_name, update=False, confirmation_required=True,
                          verbose=False, raise_error=False):
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

            >>> from pydriosm.downloader import BBBikeDownloader
            >>> bbd = BBBikeDownloader()
            >>> subregion_name = 'birmingham'
            >>> # A download catalogue for Leeds
            >>> bham_catalogue = bbd.get_sub_catalogue(subregion_name, verbose=True)
            To retrieve/compile data of a download catalogue for "Birmingham"
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

        subregion_name_ = cls.validate_subregion_name(subregion_name, raise_error=raise_error)

        data_name = f'a download catalogue for "{subregion_name_}"'

        sub_catalogue = cls.get_prepacked_data(
            fetch_bbbike_sub_catalogue, subregion_name=subregion_name_, url=cls.URL,
            raise_error=raise_error,
            data_name=data_name, update=update, confirmation_required=confirmation_required,
            dump_backup=False, verbose=verbose)

        return sub_catalogue

    @classmethod
    def get_catalogue(cls, update=False, confirmation_required=True, verbose=False,
                      raise_error=False):
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
        """

        data_name = f'{cls.NAME} downloads catalogue'

        download_index = cls.get_prepacked_data(
            fetch_bbbike_catalogue, cls_instance=cls, data_name=data_name, update=update,
            confirmation_required=confirmation_required, verbose=verbose, action_prompt_note="",
            action_prompt_end=" ... \n" if verbose == 2 else " ... ",
            ending_message="\t\tFetching completed.", raise_error=raise_error)

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

    def get_subregion_download_url(self, subregion_name, osm_file_format, **kwargs):
        # noinspection PyShadowingNames
        """
        Get a valid URL for downloading OSM data of a specific file format
        for a geographic (sub)region.

        :param subregion_name: name of a (sub)region available on BBBike free download server
        :type subregion_name: str
        :param osm_file_format: file format/extension of the OSM data
            available on the download server
        :type osm_file_format: str
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

        subregion_name_ = self.validate_subregion_name(subregion_name=subregion_name, **kwargs)
        osm_file_format_ = ".osm" + self.validate_file_format(osm_file_format=osm_file_format)

        sub_dwnld_cat = self.catalogue['Catalogue'][subregion_name_]

        filename = subregion_name_ + osm_file_format_
        download_url = sub_dwnld_cat.loc[sub_dwnld_cat['filename'] == filename, 'url'].values[0]

        return subregion_name_, download_url

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
            when ``download_dir=None``,
            it refers to the method :meth:`~pydriosm.downloader.BBBike.cdd`
        :type download_dir: str | None
        :param kwargs: [optional] parameters of `pyhelpers.dirs.cd()`_, including ``mkdir``
        :return: valid subregion name, filename, download url and absolute file path
        :rtype: tuple

        .. _`pyhelpers.dirs.cd()`:
            https://pyhelpers.readthedocs.io/en/latest/_generated/pyhelpers.dirs.cd.html

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
            defaults to ``None``; when ``data_dir=None``, it refers to the method
            :meth:`~pydriosm.downloader.BBBike.cdd`
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
            >>> bbd.download_osm_data(subregion_name, osm_file_format, data_dir, verbose=True)
            To download .pbf data of the following geographic (sub)region(s):
                Birmingham
            ? [No]|Yes: yes
            Downloading "Birmingham.osm.pbf"
                to "tests\\osm_data\\birmingham\\" ... Done.
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
            To delete the directory "tests\\osm_data\\" (Not empty)
            ? [No]|Yes: yes
            Deleting "tests\\osm_data\\" ... Done.
            >>> # Since the default download directory has been deleted
            >>> bbd.file_exists(subregion_name, osm_file_format, data_dir)
            False
        """

        file_exists = super().file_exists(
            subregion_name=subregion_name, osm_file_format=osm_file_format, data_dir=data_dir,
            update=update, verbose=verbose, ret_file_path=ret_file_path)

        return file_exists

    def _prep_download_subregion_data(self, subregion_name, download_dir, verify_download_dir):
        """

        :param subregion_name:
        :param download_dir:
        :param verify_download_dir:
        :return:
        """

        subregion_name_ = self.validate_subregion_name(subregion_name)
        sub_catalogue = self.catalogue['Catalogue'][subregion_name_]

        sub_dirname = self.make_subregion_dirname(subregion_name_)

        if download_dir is None:
            data_dir = cd(self.download_dir, sub_dirname, mkdir=True)

        else:
            download_dir_ = validate_dir(path_to_dir=download_dir)

            data_dir = os.path.join(download_dir_, sub_dirname)
            os.makedirs(data_dir, exist_ok=True)

            if verify_download_dir and download_dir_ != self.download_dir:
                self.download_dir = download_dir_

        prompt_ = f'all available BBBike OSM data of "{subregion_name_}"'

        return sub_catalogue, data_dir, prompt_

    def download_subregion_data(self, subregion_name, download_dir=None, update=False,
                                confirmation_required=True, interval=None, verify_download_dir=True,
                                verbose=False, ret_download_path=False,
                                **kwargs):
        # noinspection PyShadowingNames
        """
        Download OSM data of all available formats for a geographic (sub)region.

        :param subregion_name: name of a (sub)region available on BBBike free download server
        :type subregion_name: str
        :param download_dir: directory where the downloaded file is saved, defaults to ``None``
        :type download_dir: str | None
        :param update: whether to update the data if it already exists, defaults to ``False``
        :type update: bool
        :param confirmation_required: whether asking for confirmation to proceed,
            defaults to ``True``
        :type confirmation_required: bool
        :param interval: interval (in second) between downloading two subregions,
            defaults to ``None``
        :type interval: int | float | None
        :param verify_download_dir: whether to verify the pathname of the
            current download directory, defaults to ``True``
        :type verify_download_dir: bool
        :param verbose: whether to print relevant information in console, defaults to ``False``
        :type verbose: bool | int
        :param ret_download_path: whether to return the path(s) to the downloaded file(s),
            defaults to ``False``
        :type ret_download_path: bool
        :param kwargs: optional parameters of `pyhelpers.ops.download_file_from_url()`_
        :return: the path(s) to the downloaded file(s) when ``ret_download_path`` is ``True``
        :rtype: list | str

        .. _`pyhelpers.ops.download_file_from_url()`:
            https://pyhelpers.readthedocs.io/en/latest/_generated/
            pyhelpers.ops.download_file_from_url.html

        **Examples**::

            >>> from pydriosm.downloader import BBBikeDownloader
            >>> from pyhelpers.dirs import delete_dir
            >>> import os
            >>> bbd = BBBikeDownloader()
            >>> # Download the BBBike OSM data of Birmingham (to the default download directory)
            >>> subregion_name = 'Birmingham'
            >>> bbd.download_subregion_data(subregion_name, verbose=True)
            To download all available BBBike OSM data of "Birmingham"
            ? [No]|Yes: yes
            Downloading in progress:
            Downloading "Birmingham.osm.pbf" 100%|██████████| 42.5M/42.5M | 30.5MB/s | ETA:...
                Saving "Birmingham.osm.pbf" to "./osm_data/bbbike/birmingham/" ... Done.
            Downloading "Birmingham.osm.gz" 100%|██████████| 88.2M/88.2M | 30.7MB/s | ETA: ...
                Saving "Birmingham.osm.gz" to "./osm_data/bbbike/birmingham/" ... Done.
            ...
                ...
            Downloading "Birmingham.osm.csv.xz" 100%|██████████| 5.81M/5.81M | 15.4MB/s | E...
                Saving "Birmingham.osm.csv.xz" to "./osm_data/bbbike/birmingham/" ... Done.
            Downloading "Birmingham.poly" 100%|██████████| 81.0/81.0 | 80.3kB/s | ETA: 00:00
                Saving "Birmingham.poly" to "./osm_data/bbbike/birmingham/" ... Done.
            Downloading "CHECKSUM.txt" 100%|██████████| 648/648 | ?B/s | ETA: ?
                Saving "CHECKSUM.txt" to "./osm_data/bbbike/birmingham/" ... Done.
            Check out the downloaded OSM data in "./osm_data/bbbike/birmingham/".
            >>> len(bbd.data_paths)
            13
            >>> os.path.relpath(os.path.commonpath(bbd.data_paths))  # (on Windows)
            'osm_data\\bbbike\\birmingham'
            >>> os.path.relpath(bbd.download_dir)  # (on Windows)
            'osm_data\\bbbike'
            >>> bham_download_dir = os.path.dirname(bbd.download_dir)

            >>> # Download the BBBike OSM data of Leeds (to a given download directory)
            >>> subregion_name = 'Leeds'
            >>> download_dir = "tests/osm_data"
            >>> download_paths = bbd.download_subregion_data(
            ...     subregion_name, download_dir, verbose=2, ret_download_path=True)
            To download all available BBBike OSM data of Leeds
            ? [No]|Yes: yes
            Downloading:
                "Leeds.osm.pbf" ... Done.
                "Leeds.osm.gz" ... Done.
                "Leeds.osm.shp.zip" ... Done.
                "Leeds.osm.garmin-ontrail-latin1.zip" ... Done.
                "Leeds.osm.garmin-onroad-latin1.zip" ... Done.
                "Leeds.osm.garmin-opentopo-latin1.zip" ... (Done.
                "Leeds.osm.garmin-osm.zip" ... Done.
                "Leeds.osm.geojson.xz" ... Done.
                "Leeds.osm.mapsforge-osm.zip" ... Done.
                "Leeds.osm.mbtiles-openmaptiles.zip" ... Done.
                "Leeds.osm.csv.xz" ... Done.
                "Leeds.poly" ... Done.
                "CHECKSUM.txt" ... Done.
            Check out the downloaded OSM data in "./tests/osm_data/leeds/".
            >>> # Now the variable `.download_dir` has changed to `dwnld_dir`
            >>> leeds_download_dir = bbd.download_dir
            >>> os.path.relpath(leeds_download_dir) == os.path.normpath(download_dir)
            True
            >>> len(download_paths)
            13
            >>> len(bbd.data_paths)  # New pathnames have been added to `.data_paths`
            26
            >>> os.path.relpath(os.path.commonpath(download_paths))  # (on Windows)
            'tests\\osm_data\\leeds'

            >>> # Delete the download directories
            >>> delete_dir([bham_download_dir, leeds_download_dir], verbose=True)
            To delete the following directories:
                "./osm_data/" (Not empty)
                "./tests/osm_data/" (Not empty)
            ? [No]|Yes: >? yes
            Deleting "./osm_data/" ... Done.
            Deleting "./tests/osm_data/" ... Done.
        """

        subrgn_cat, data_dir, prompt_ = self._prep_download_subregion_data(
            subregion_name, download_dir, verify_download_dir)

        if confirmed(f"To download {prompt_}\n?", confirmation_required=confirmation_required):
            if verbose:
                if confirmation_required:
                    print("Downloading: " if verbose == 2 else "Downloading in progress: ")
                else:
                    print(f"Downloading {prompt_}: ")

            download_paths = []

            for download_url, osm_filename in zip(subrgn_cat['url'], subrgn_cat['filename']):
                path_to_file = normalize_pathname(os.path.join(data_dir, osm_filename))

                if os.path.isfile(path_to_file) and not update:
                    if verbose:
                        print(f'\t"{osm_filename}" ... (Already exists).')

                    download_paths.append(path_to_file)

                else:
                    self._download_osm_data(
                        url=download_url, path_to_file=path_to_file, interval=interval,
                        verbose=verbose, print_state="\tDownloading", verify_download_dir=False,
                        **kwargs)

                    if os.path.isfile(path_to_file):
                        download_paths.append(path_to_file)

            if verbose:
                rel_path = check_relative_pathname(os.path.commonpath(download_paths))
                print(f'Check out the downloaded OSM data in {add_slashes(rel_path)}.')

            self.data_paths = list(
                collections.OrderedDict.fromkeys(self.data_paths + download_paths))

            if ret_download_path:
                return download_paths

        else:
            print("Cancelled.")

    def download_osm_data(self, subregion_names, osm_file_format, download_dir=None, update=False,
                          confirmation_required=True, interval=None, verify_download_dir=True,
                          verbose=False, ret_download_path=False, **kwargs):
        # noinspection PyShadowingNames
        """
        Download OSM data (of a specific file format) of
        one (or multiple) geographic (sub)region(s).

        :param subregion_names: name of a geographic (sub)region
            (or names of multiple geographic (sub)regions) available on BBBike free download server
        :type subregion_names: str | list
        :param osm_file_format: file format/extension of the OSM data
            available on the download server
        :type osm_file_format: str
        :param download_dir: directory for saving the downloaded file(s), defaults to ``None``;
            when ``download_dir=None``, it refers to the method
            :meth:`~pydriosm.downloader.BBBike.cdd`
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
            >>> bbd.download_osm_data(subregion_name, osm_file_format, verbose=True)
            To download .pbf data of the following geographic (sub)region(s):
                "London"
            ? [No]|Yes: yes
            Downloading "London.osm.pbf" 100%|██████████| 131M/131M | 36.1MB/s | ETA: 00:00
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
            >>> osm_file_format = 'shp'
            >>> download_dir = "tests/osm_data"
            >>> download_paths = bbd.download_osm_data(
            ...     subregion_names, osm_file_format, download_dir, verbose=2,
            ...     ret_download_path=True)
            To download .shp.zip data of the following geographic (sub)region(s):
                "Leeds"
                "Birmingham"
            ? [No]|Yes: yes
            Downloading "Leeds.osm.shp.zip" to "./tests/osm_data/leeds/" ... Done.
            Downloading "Birmingham.osm.shp.zip" to "./tests/osm_data/birmingham/" ... Done.
            >>> len(download_paths)
            2
            >>> len(bbd.data_paths)
            3
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
            Deleting "./osm_data/" ... Done.
            Deleting "./tests/osm_data/" ... Done.
        """

        (subregion_names_, osm_file_format_, confirmation_required_, update_msg, download_list,
         existing_file_paths) = self.file_exists_and_more(
            subregion_names=subregion_names, osm_file_format=osm_file_format,
            data_dir=download_dir, update=update, confirmation_required=confirmation_required,
            verbose=verbose)

        confirmation_required_ = confirmation_required_ and confirmation_required

        download_list_message = "\n\t".join([f'"{x}"' for x in download_list])
        cfm_msg = f"To {update_msg} {osm_file_format_} data of " \
                  f"the following geographic (sub)region(s):\n\t{download_list_message}\n?"

        if confirmed(cfm_msg, confirmation_required=confirmation_required_):
            download_paths = []

            for sub_reg_name in subregion_names_:
                # Get essential information for the download
                _, _, download_url, file_pathname = self.get_valid_download_info(
                    subregion_name=sub_reg_name, osm_file_format=osm_file_format_,
                    download_dir=download_dir, mkdir=True)

                if not os.path.isfile(file_pathname) or update:
                    kwargs.update({'verify_download_dir': False})
                    self._download_osm_data(
                        url=download_url, path_to_file=file_pathname, interval=interval,
                        verbose=verbose, **kwargs)

                if os.path.isfile(file_pathname):
                    download_paths.append(file_pathname)

            self.verify_download_dir(
                download_dir=download_dir, verify_download_dir=verify_download_dir)

        else:
            print("Cancelled.")

            download_paths = existing_file_paths

        self.data_paths = list(collections.OrderedDict.fromkeys(self.data_paths + download_paths))

        if ret_download_path:
            return download_paths
