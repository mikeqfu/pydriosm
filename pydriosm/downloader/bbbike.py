"""
Download OSM data from BBBike free download server.
"""

import collections
import csv
import importlib
import os
import re
import time
import urllib.parse

import pandas as pd
import requests
from pyhelpers._cache import _print_failure_msg
from pyhelpers.dirs import cd, validate_dir
from pyhelpers.ops import confirmed, download_file_from_url, fake_requests_headers
from pyhelpers.store import save_data
from pyrcs.parser import parse_tr

from pydriosm.downloader._downloader import _Downloader
from pydriosm.utils import check_relpath


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

        self.valid_subregion_names = self.get_names_of_cities()
        self.subregion_coordinates = self.get_coordinates_of_cities()
        self.subregion_index = self.get_subregion_index()
        self.catalogue = self.get_catalogue()
        # self.valid_file_formats = set(self.catalogue['FileFormat'])

    @classmethod
    def _names_of_cities(cls, path_to_pickle, verbose):
        """
        Get the names of all the available cities.

        :param path_to_pickle: pathname of the prepacked pickle file, defaults to ``None``
        :type path_to_pickle: str | os.PathLike[str] | None
        :param verbose: whether to print relevant information in console, defaults to ``False``
        :type verbose: bool | int
        :return: list of names of cities available on BBBike free download server
        :rtype: list

        .. seealso::

            - Examples for the method
              :meth:`~pydriosm.downloader.BBBikeDownloader.get_names_of_cities`.
        """

        names_of_cities_ = pd.read_csv(cls.CITIES_URL, header=None)
        names_of_cities = list(names_of_cities_.values.flatten())

        if verbose:
            print("Done.")

        save_data(names_of_cities, path_to_pickle, verbose=verbose)

        return names_of_cities

    @classmethod
    def get_names_of_cities(cls, update=False, confirmation_required=True, verbose=False):
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
        :return: list of names of cities available on BBBike free download server
        :rtype: list | None

        **Examples**::

            >>> from pydriosm.downloader import BBBikeDownloader

            >>> bbd = BBBikeDownloader()

            >>> # A list of BBBike cities' names
            >>> bbbike_cities = bbd.get_names_of_cities()
            >>> type(bbbike_cities)
            list
        """

        data_name = f'{cls.NAME} cities'

        cities_names = cls.get_prepacked_data(
            cls._names_of_cities, data_name=data_name, update=update,
            confirmation_required=confirmation_required, verbose=verbose)

        return cities_names

    @classmethod
    def _coordinates_of_cities(cls, path_to_pickle, verbose):
        """
        Get location information of all cities available on the download server.

        :param path_to_pickle: pathname of the prepacked pickle file, defaults to ``None``
        :type path_to_pickle: str | os.PathLike[str] | None
        :param verbose: whether to print relevant information in console, defaults to ``False``
        :type verbose: bool | int
        :return: location information of BBBike cities, i.e. geographic (sub)regions
        :rtype: pandas.DataFrame

        .. seealso::

            - Examples for the method
              :meth:`~pydriosm.downloader.BBBikeDownloader.get_coordinates_of_cities`.
        """

        with requests.get(url=cls.CITIES_COORDS_URL, headers=fake_requests_headers()) as response:
            csv_data_temp = response.content.decode('utf-8')
            csv_data_ = list(csv.reader(csv_data_temp.splitlines(), delimiter=':'))

        csv_data = [
            [x.strip().strip('\u200e').replace('#', '') for x in row]
            for row in csv_data_[5:-1]]
        column_names = [x.replace('#', '').strip().capitalize() for x in csv_data_[0]]
        cities_coords_ = pd.DataFrame(csv_data, columns=column_names)

        coordinates = cities_coords_['Coord'].str.split(' ', expand=True)  # .apply(pd.Series)
        del cities_coords_['Coord']

        coords_cols = ['ll_longitude', 'll_latitude', 'ur_longitude', 'ur_latitude']
        coordinates.columns = coords_cols

        cities_coords = pd.concat([cities_coords_, coordinates], axis=1).dropna(subset=coords_cols)

        cities_coords['Real name'] = cities_coords['Real name'].str.split(r'[!,]').map(
            lambda x: None if x[0] == '' else dict(zip(x[::2], x[1::2])))

        # Rename columns
        cities_coords.columns = [
            x.replace(' ', '_').replace('/', '_or_').replace('?', '').lower()
            for x in cities_coords.columns]

        if verbose:
            print("Done.")

        save_data(cities_coords, path_to_pickle, verbose=verbose)

        return cities_coords

    @classmethod
    def get_coordinates_of_cities(cls, update=False, confirmation_required=True, verbose=False):
        """
        Get location information of all cities available on the download server.

        :param update: whether to (check on and) update the prepacked data, defaults to ``False``
        :type update: bool
        :param confirmation_required: whether asking for confirmation to proceed,
            defaults to ``True``
        :type confirmation_required: bool
        :param verbose: whether to print relevant information in console, defaults to ``False``
        :type verbose: bool | int
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
            cls._coordinates_of_cities, data_name=data_name, update=update,
            confirmation_required=confirmation_required, verbose=verbose)

        return cities_coords

    @classmethod
    def _subregion_index(cls, path_to_pickle, verbose):
        """
        Get a catalogue for geographic (sub)regions.

        :param path_to_pickle: pathname of the prepacked pickle file, defaults to ``None``
        :type path_to_pickle: str | os.PathLike[str] | None
        :param verbose: whether to print relevant information in console, defaults to ``False``
        :type verbose: bool | int
        :return: catalogue for subregions of BBBike data
        :rtype: pandas.DataFrame

        .. seealso::

            - Examples for the method
              :meth:`~pydriosm.downloader.BBBikeDownloader.get_subregion_index`.
        """

        bs4_ = importlib.import_module('bs4')

        with requests.get(url=cls.URL, headers=fake_requests_headers()) as response:
            soup = bs4_.BeautifulSoup(markup=response.content, features='html.parser')

        thead, tbody = soup.find(name='thead'), soup.find(name='tbody')

        ths = [th.text.strip().lower().replace(' ', '_') for th in thead.find_all(name='th')]
        trs = tbody.find_all(name='tr')
        dat = parse_tr(trs=trs, ths=ths, as_dataframe=True).drop(index=0)
        dat.index = range(len(dat))

        for col in ['size', 'type']:
            if dat[col].nunique() == 1:
                del dat[col]

        subregion_index = dat.copy()

        subregion_index['name'] = subregion_index['name'].map(lambda x: x.rstrip('/').strip())
        subregion_index['last_modified'] = pd.to_datetime(subregion_index['last_modified'])
        subregion_index['url'] = [
            urllib.parse.urljoin(cls.URL, x.get('href')) for x in soup.find_all('a')[1:]]

        if verbose:
            print("Done.")

        save_data(subregion_index, path_to_pickle, verbose=verbose)

        return subregion_index

    @classmethod
    def get_subregion_index(cls, update=False, confirmation_required=True, verbose=False):
        """
        Get a catalogue for geographic (sub)regions.

        :param update: whether to (check on and) update the prepacked data, defaults to ``False``
        :type update: bool
        :param confirmation_required: whether asking for confirmation to proceed,
            defaults to ``True``
        :type confirmation_required: bool
        :param verbose: whether to print relevant information in console, defaults to ``False``
        :type verbose: bool | int
        :return: catalogue for subregions of BBBike data
        :rtype: pandas.DataFrame | None

        **Examples**::

            >>> from pydriosm.downloader import BBBikeDownloader

            >>> bbd = BBBikeDownloader()

            >>> # A BBBike catalogue of geographic (sub)regions
            >>> subrgn_idx = bbd.get_subregion_index()

            >>> type(subrgn_idx)
            pandas.core.frame.DataFrame
            >>> subrgn_idx.columns.to_list()
            ['name', 'last_modified', 'url']
        """

        data_name = f'{cls.NAME} index of subregions'

        subregion_index = cls.get_prepacked_data(
            cls._subregion_index, data_name=data_name, update=update,
            confirmation_required=confirmation_required, verbose=verbose)

        return subregion_index

    @classmethod
    def _valid_subregion_names(cls, path_to_pickle, verbose):
        """
        Get a list of names of all geographic (sub)regions.

        :param path_to_pickle: pathname of the prepacked pickle file, defaults to ``None``
        :type path_to_pickle: str | os.PathLike[str] | None
        :param verbose: whether to print relevant information in console, defaults to ``False``
        :type verbose: bool | int
        :return: a list of geographic (sub)region names available on BBBike free download server
        :rtype: list
        """
        # subregion_names = list(self.get_names_of_cities())

        subregion_catalogue = cls.get_subregion_index(confirmation_required=False, verbose=False)
        subregion_names = subregion_catalogue['name'].to_list()

        if verbose:
            print("Done.")

        save_data(subregion_names, path_to_pickle, verbose=verbose)

        return subregion_names

    @classmethod
    def get_valid_subregion_names(cls, update=False, confirmation_required=True, verbose=False):
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
        :return: a list of geographic (sub)region names available on BBBike free download server
        :rtype: list | None

        **Examples**::

            >>> from pydriosm.downloader import BBBikeDownloader

            >>> bbd = BBBikeDownloader()

            >>> # A list of names of all BBBike geographic (sub)regions
            >>> subrgn_names = bbd.get_valid_subregion_names()

            >>> type(subrgn_names)
            list
        """

        data_name = f'{cls.NAME} subregion names'

        if update:
            args = {'update': update, 'confirmation_required': False, 'verbose': False}
            _ = cls.get_subregion_index(**args)
            _ = cls.get_names_of_cities(**args)

        subregion_names = cls.get_prepacked_data(
            cls._valid_subregion_names, data_name=data_name, update=update,
            confirmation_required=confirmation_required, verbose=verbose)

        return subregion_names

    def validate_subregion_name(self, subregion_name, valid_subregion_names=None, raise_err=True,
                                **kwargs):
        """
        Validate an input name of a geographic (sub)region.

        The validation is done by matching the input ``subregion_name`` to
        a name of a geographic (sub)region available on BBBike free download server.

        :param subregion_name: name of a (sub)region available on BBBike free download server
        :type subregion_name: str
        :param valid_subregion_names: names of all (sub)regions available on a free download server
        :type valid_subregion_names: typing.Iterable
        :param raise_err: (if the input fails to match a valid name) whether to raise the error
            :py:class:`pydriosm.downloader.InvalidSubregionName`, defaults to ``True``
        :type raise_err: bool
        :return: valid (sub)region name that matches, or is the most similar to, the input
        :rtype: str

        **Examples**::

            >>> from pydriosm.downloader import BBBikeDownloader

            >>> bbd = BBBikeDownloader()

            >>> subrgn_name = 'birmingham'

            >>> valid_name = bbd.validate_subregion_name(subregion_name=subrgn_name)
            >>> valid_name
            'Birmingham'
        """

        if valid_subregion_names is None:
            valid_subregion_names_ = self.valid_subregion_names
        else:
            valid_subregion_names_ = valid_subregion_names

        subregion_name_ = super().validate_subregion_name(
            subregion_name=subregion_name, valid_subregion_names=valid_subregion_names_,
            raise_err=raise_err, **kwargs)

        return subregion_name_

    @classmethod
    def _parse_download_link_a_tags(cls, x, url):
        """
        Parse an <a> tag of a download link.

        :param x: <a> tag of a download link
        :type x: bs4.element.Tag
        :param url: URL of the web page of a subregion
        :type url: str
        :return: data contained in the <a> tag
        :rtype: list
        """

        x_attrs = x.attrs
        x_href = x_attrs['href']
        filename, download_url = os.path.basename(x_href), urllib.parse.urljoin(url, x_href)

        if not x.has_attr('title'):
            file_format, file_size, last_update = 'Poly', None, None

        else:
            # File type and size
            if x_attrs['class'] == ['download_link']:
                file_format, file_size = [
                    y.strip() if isinstance(y, str) else y.text.strip() for y in x.contents]
            else:
                file_format, file_size = 'Txt', None
            # Date and time
            last_update = pd.to_datetime(re.sub(r'last update: ?', '', x_attrs['title']))

        parsed_dat = [filename, download_url, file_format, file_size, last_update]

        return parsed_dat

    def get_subregion_catalogue(self, subregion_name, confirmation_required=True, verbose=False):
        """
        Get a download catalogue of OSM data available for a given geographic (sub)region.

        :param subregion_name: name of a (sub)region available on BBBike free download server
        :type subregion_name: str
        :param confirmation_required: whether asking for confirmation to proceed,
            defaults to ``True``
        :type confirmation_required: bool
        :param verbose: whether to print relevant information in console, defaults to ``False``
        :type verbose: bool | int
        :return: a catalogues for subregion downloads
        :rtype: pandas.DataFrame | None

        **Examples**::

            >>> from pydriosm.downloader import BBBikeDownloader
            >>> bbd = BBBikeDownloader()
            >>> subrgn_name = 'birmingham'
            >>> # A download catalogue for Leeds
            >>> bham_dwnld_cat = bbd.get_subregion_catalogue(subrgn_name, verbose=True)
            To compile data of a download catalogue for "Birmingham"
            ? [No]|Yes: yes
            Compiling the data ... Done.
            >>> type(bham_dwnld_cat)
            pandas.core.frame.DataFrame
            >>> bham_dwnld_cat.columns.tolist()
            ['filename', 'url', 'data_type', 'size', 'last_update']
        """

        subregion_name_ = self.validate_subregion_name(subregion_name)

        dat_name = f"a download catalogue for \"{subregion_name_}\""

        if confirmed(f"To compile data of {dat_name}\n?", confirmation_required):
            if verbose:
                if confirmation_required:
                    status_msg = "Compiling the data"
                else:
                    if verbose == 2:
                        status_msg = f"\t{subregion_name_}"
                    else:
                        status_msg = f"Compiling the data of {dat_name}"
                print(status_msg, end=" ... ")

            try:
                bs4_ = importlib.import_module('bs4')

                url = urllib.parse.urljoin(self.URL, subregion_name_ + '/')

                with requests.get(url=url, headers=fake_requests_headers()) as response:
                    soup = bs4_.BeautifulSoup(markup=response.content, features='html.parser')

                download_link_a_tags = soup.find_all(
                    'a', attrs={'class': ['download_link', 'small']})

                download_catalogue = pd.DataFrame(
                    self._parse_download_link_a_tags(x=x, url=url) for x in download_link_a_tags)
                download_catalogue.columns = ['filename', 'url', 'data_type', 'size', 'last_update']

                if verbose:
                    print("Done.")

            except Exception as e:
                _print_failure_msg(e, msg="Failed.")
                download_catalogue = None

            return download_catalogue

    def _catalogue(self, path_to_pickle, verbose):
        """
        Get a dict-type index of available formats, data types and a download catalogue.

        :param path_to_pickle: pathname of the prepacked pickle file, defaults to ``None``
        :type path_to_pickle: str | os.PathLike[str] | None
        :param verbose: whether to print relevant information in console, defaults to ``False``
        :type verbose: bool | int
        :return: a list of available formats, a list of available data types and
            a dictionary of download catalogue
        :rtype: dict
        """

        subregion_names = self.get_valid_subregion_names()

        download_catalogue = []
        for subregion_name in subregion_names:

            subregion_dwnld_cat = self.get_subregion_catalogue(
                subregion_name=subregion_name, confirmation_required=False,
                verbose=2 if verbose == 2 else False)

            if subregion_dwnld_cat is None:
                raise Exception
            else:
                download_catalogue.append(subregion_dwnld_cat)

        subrgn_name = subregion_names[0]
        subrgn_catalog = download_catalogue[0]

        # Available file formats
        file_fmt = [
            re.sub('{}|CHECKSUM'.format(subrgn_name), '', f) for f in subrgn_catalog['filename']]

        # Available data types
        data_typ = subrgn_catalog['data_type'].to_list()

        download_index = {
            'FileFormat': [x.replace(".osm", "", 1) for x in file_fmt[:-2]],
            'DataType': data_typ[:-2],
            'Catalogue': dict(zip(subregion_names, download_catalogue)),
        }

        if verbose is True:
            print("Done.")
        elif verbose == 2:
            print("All done.")

        save_data(download_index, path_to_pickle, verbose=verbose)

        return download_index

    def get_catalogue(self, update=False, confirmation_required=True, verbose=False):
        """
        Get a dict-type index of available formats, data types and a download catalogue.

        :param update: whether to (check on and) update the prepacked data, defaults to ``False``
        :type update: bool
        :param confirmation_required: whether asking for confirmation to proceed,
            defaults to ``True``
        :type confirmation_required: bool
        :param verbose: whether to print relevant information in console, defaults to ``False``
        :type verbose: bool | int
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

        data_name = f'{self.NAME} downloads catalogue'

        download_index = self.get_prepacked_data(
            self._catalogue, data_name=data_name, update=update,
            confirmation_required=confirmation_required, verbose=verbose, act_msg_note="",
            act_msg_end=": \n" if verbose == 2 else " ... ")

        return download_index

    def validate_file_format(self, osm_file_format, valid_file_formats=None, raise_err=True,
                             **kwargs):
        """
        Validate an input file format of OSM data.

        The validation is done by matching the input ``osm_file_format`` to a filename extension
        available on BBBike free download server.

        :param osm_file_format: file format/extension of the OSM data
            available on BBBike free download server
        :type osm_file_format: str
        :param valid_file_formats: fil extensions of the data available on a free download server
        :type valid_file_formats: typing.Iterable
        :param raise_err: (if the input fails to match a valid name) whether to raise the error
            :py:class:`pydriosm.downloader.InvalidFileFormatError`, defaults to ``True``
        :type raise_err: bool
        :return: valid file format (file extension)
        :rtype: str

        **Examples**::

            >>> from pydriosm.downloader import BBBikeDownloader

            >>> bbd = BBBikeDownloader()

            >>> valid_file_format = bbd.validate_file_format(osm_file_format='PBF')
            >>> valid_file_format
            '.pbf'

            >>> valid_file_format = bbd.validate_file_format(osm_file_format='.osm.pbf')
            >>> valid_file_format
            '.pbf'
        """

        if valid_file_formats is None:
            valid_file_formats_ = self.FILE_FORMATS
        else:
            valid_file_formats_ = valid_file_formats

        osm_file_format_ = super().validate_file_format(
            osm_file_format=osm_file_format, valid_file_formats=valid_file_formats_,
            raise_err=raise_err, **kwargs)

        return osm_file_format_

    def get_subregion_download_url(self, subregion_name, osm_file_format, **kwargs):
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

            >>> subrgn_name = 'birmingham'
            >>> file_format = "pbf"

            >>> # Get a valid subregion name and its download URL
            >>> subrgn_name_, dwnld_url = bbd.get_subregion_download_url(subrgn_name, file_format)
            >>> subrgn_name_
            'Birmingham'
            >>> dwnld_url
            'https://download.bbbike.org/osm/bbbike/Birmingham/Birmingham.osm.pbf'

            >>> file_format = "csv.xz"
            >>> subrgn_name_, dwnld_url = bbd.get_subregion_download_url(subrgn_name, file_format)

            >>> subrgn_name_
            'Birmingham'
            >>> dwnld_url
            'https://download.bbbike.org/osm/bbbike/Birmingham/Birmingham.osm.csv.xz'
        """

        subregion_name_ = self.validate_subregion_name(subregion_name=subregion_name, **kwargs)
        osm_file_format_ = ".osm" + self.validate_file_format(osm_file_format=osm_file_format)

        sub_dwnld_cat = self.catalogue['Catalogue'][subregion_name_]

        filename = subregion_name_ + osm_file_format_
        download_url = sub_dwnld_cat.loc[sub_dwnld_cat['filename'] == filename, 'url'].values[0]

        return subregion_name_, download_url

    def get_valid_download_info(self, subregion_name, osm_file_format, download_dir=None, **kwargs):
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

            >>> subrgn_name = 'birmingham'
            >>> file_format = "pbf"

            >>> # valid subregion name, filename, download url and absolute file path
            >>> info = bbd.get_valid_download_info(subrgn_name, file_format)
            >>> valid_subrgn_name, pbf_filename, dwnld_url, pbf_pathname = info

            >>> valid_subrgn_name
            'Birmingham'
            >>> pbf_filename
            'Birmingham.osm.pbf'
            >>> dwnld_url
            'https://download.bbbike.org/osm/bbbike/Birmingham/Birmingham.osm.pbf'
            >>> os.path.relpath(pbf_pathname)
            'osm_data\\bbbike\\birmingham\\Birmingham.osm.pbf'

            >>> # Create a new instance with a given download directory
            >>> bbd = BBBikeDownloader(download_dir="tests\\osm_data")
            >>> _, _, _, pbf_pathname = bbd.get_valid_download_info(subrgn_name, file_format)

            >>> os.path.relpath(pbf_pathname)
            'tests\\osm_data\\birmingham\\Birmingham.osm.pbf'
        """

        subregion_name_, osm_filename, download_url, file_pathname = \
            super().get_valid_download_info(
                subregion_name=subregion_name, osm_file_format=osm_file_format,
                download_dir=download_dir, **kwargs)

        return subregion_name_, osm_filename, download_url, file_pathname

    def file_exists(self, subregion_name, osm_file_format, data_dir=None, update=False,
                    verbose=False, ret_file_path=False):
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

            >>> subrgn_name = 'birmingham'
            >>> file_format = ".pbf"
            >>> dwnld_dir = "tests\\osm_data"

            >>> # Check whether the PBF data file exists; `ret_file_path` is by default `False`
            >>> pbf_exists = bbd.file_exists(subrgn_name, file_format, dwnld_dir)
            >>> pbf_exists
            False

            >>> # Download the PBF data of Birmingham (to the default directory)
            >>> bbd.download_osm_data(subrgn_name, file_format, dwnld_dir, verbose=True)
            To download .pbf data of the following geographic (sub)region(s):
                Birmingham
            ? [No]|Yes: yes
            Downloading "Birmingham.osm.pbf"
                to "tests\\osm_data\\birmingham\\" ... Done.

            >>> bbd.file_exists(subrgn_name, file_format, dwnld_dir)
            True

            >>> # Set `ret_file_path=True`
            >>> pbf_pathname = bbd.file_exists(subrgn_name, file_format, ret_file_path=True)
            >>> os.path.relpath(pbf_pathname)
            'tests\\osm_data\\birmingham\\Birmingham.osm.pbf'

            >>> os.path.relpath(dwnld_dir) == os.path.relpath(bbd.download_dir)
            True

            >>> # Remove the directory or the PBF file and check again:
            >>> delete_dir(bbd.download_dir, verbose=True)
            To delete the directory "tests\\osm_data\\" (Not empty)
            ? [No]|Yes: yes
            Deleting "tests\\osm_data\\" ... Done.

            >>> # Since the default download directory has been deleted
            >>> bbd.file_exists(subrgn_name, file_format, dwnld_dir)
            False
        """

        file_exists = super().file_exists(
            subregion_name=subregion_name, osm_file_format=osm_file_format, data_dir=data_dir,
            update=update, verbose=verbose, ret_file_path=ret_file_path)

        return file_exists

    def _prep_download_subregion_data(self, subregion_name, download_dir, verify_download_dir):
        subregion_name_ = self.validate_subregion_name(subregion_name)
        subrgn_cat = self.catalogue['Catalogue'][subregion_name_]

        sub_dirname = self.make_subregion_dirname(subregion_name_)

        if download_dir is None:
            data_dir = cd(self.download_dir, sub_dirname, mkdir=True)

        else:
            download_dir_ = validate_dir(path_to_dir=download_dir)

            data_dir = os.path.join(download_dir_, sub_dirname)
            if not os.path.exists(data_dir):
                os.makedirs(data_dir)

            if verify_download_dir and download_dir_ != self.download_dir:
                self.download_dir = download_dir_

        cfm_dat = f"all available BBBike OSM data of {subregion_name_}"

        return subrgn_cat, data_dir, cfm_dat

    def download_subregion_data(self, subregion_name, download_dir=None, update=False,
                                confirmation_required=True, interval=None, verify_download_dir=True,
                                verbose=False, ret_download_path=False, **kwargs):
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
            >>> subrgn_name = 'birmingham'

            >>> bbd.download_subregion_data(subrgn_name, verbose=True)
            To download all available BBBike OSM data of Birmingham
            ? [No]|Yes: yes
            Downloading:
                Birmingham.osm.pbf ... Done.
                Birmingham.osm.gz ... Done.
                Birmingham.osm.shp.zip ... Done.
                Birmingham.osm.garmin-onroad-latin1.zip ... Done.
                Birmingham.osm.garmin-osm.zip ... Done.
                Birmingham.osm.garmin-ontrail-latin1.zip ... Done.
                Birmingham.osm.geojson.xz ... Done.
                Birmingham.osm.svg-osm.zip ... Done.
                Birmingham.osm.mapsforge-osm.zip ... Done.
                Birmingham.osm.garmin-opentopo-latin1.zip ... Done.
                Birmingham.osm.mbtiles-openmaptiles.zip ... Done.
                Birmingham.osm.csv.xz ... Done.
                Birmingham.poly ... Done.
                CHECKSUM.txt ... Done.
            Check out the downloaded OSM data at "osm_data\\bbbike\\birmingham\\".

            >>> len(bbd.data_paths)
            14
            >>> os.path.relpath(os.path.commonpath(bbd.data_paths))
            'osm_data\\bbbike\\birmingham'
            >>> os.path.relpath(bbd.download_dir)
            'osm_data\\bbbike'
            >>> bham_dwnld_dir = os.path.dirname(bbd.download_dir)

            >>> # Download the BBBike OSM data of Leeds (to a given download directory)
            >>> subrgn_name = 'leeds'
            >>> dwnld_dir = "tests\\osm_data"

            >>> dwnld_paths = bbd.download_subregion_data(
            ...     subrgn_name, download_dir=dwnld_dir, verbose=True, ret_download_path=True)
            To download all available BBBike OSM data of Leeds
            ? [No]|Yes: yes
            Downloading:
                Leeds.osm.pbf ... Done.
                Leeds.osm.gz ... Done.
                Leeds.osm.shp.zip ... Done.
                Leeds.osm.garmin-onroad-latin1.zip ... Done.
                Leeds.osm.garmin-osm.zip ... Done.
                Leeds.osm.garmin-ontrail-latin1.zip ... Done.
                Leeds.osm.geojson.xz ... Done.
                Leeds.osm.svg-osm.zip ... Done.
                Leeds.osm.mapsforge-osm.zip ... Done.
                Leeds.osm.garmin-opentopo-latin1.zip ... Done.
                Leeds.osm.mbtiles-openmaptiles.zip ... Done.
                Leeds.osm.csv.xz ... Done.
                Leeds.poly ... Done.
                CHECKSUM.txt ... Done.
            Check out the downloaded OSM data at "tests\\osm_data\\leeds\\".

            >>> # Now the variable `.download_dir` has changed to `dwnld_dir`
            >>> leeds_dwnld_dir = bbd.download_dir
            >>> os.path.relpath(leeds_dwnld_dir) == dwnld_dir
            True

            >>> len(dwnld_paths)
            14
            >>> len(bbd.data_paths)  # New pathnames have been added to `.data_paths`
            28
            >>> os.path.relpath(os.path.commonpath(dwnld_paths))
            'tests\\osm_data\\leeds'

            >>> # Delete the download directories
            >>> delete_dir([bham_dwnld_dir, leeds_dwnld_dir], verbose=True)
            To delete the following directories:
                "osm_data\\" (Not empty)
                "tests\\osm_data\\" (Not empty)
            ? [No]|Yes: yes
            Deleting "osm_data\\" ... Done.
            Deleting "tests\\osm_data\\" ... Done.
        """

        subrgn_cat, data_dir, cfm_dat = self._prep_download_subregion_data(
            subregion_name, download_dir, verify_download_dir)

        if confirmed(f"To download {cfm_dat}\n?", confirmation_required=confirmation_required):
            if verbose:
                if confirmation_required:
                    print("Downloading: ")
                else:
                    print(f"Downloading {cfm_dat}: ")

            download_paths = []

            for download_url, osm_filename in zip(subrgn_cat['url'], subrgn_cat['filename']):
                try:
                    path_to_file = os.path.join(data_dir, osm_filename)

                    if os.path.isfile(path_to_file) and not update:
                        if verbose:
                            print(f"\t\"{osm_filename}\" (Already available)")

                    else:
                        if verbose:
                            print(f"\t{osm_filename} ... ", end="\n" if verbose == 2 else "")

                        download_file_from_url(
                            url=download_url, path_to_file=path_to_file,
                            verbose=True if verbose == 2 else False, **kwargs)

                        if verbose and verbose != 2:
                            print("Done.")

                        if isinstance(interval, (int, float)):
                            # os.path.getsize(path_to_file)/(1024**2)<=5:
                            time.sleep(interval)

                    if os.path.isfile(path_to_file):
                        download_paths.append(path_to_file)

                except Exception as e:
                    _print_failure_msg(e, msg="Failed.")

            if verbose and len(download_paths) > 1:
                rel_path = check_relpath(os.path.commonpath(download_paths))
                if verbose == 2:
                    print("All done.")

                print(f"Check out the downloaded OSM data at \"{rel_path}\\\".")

            self.data_paths = list(
                collections.OrderedDict.fromkeys(self.data_paths + download_paths))

            if ret_download_path:
                return download_paths

        else:
            print("Cancelled.")

    def download_osm_data(self, subregion_names, osm_file_format, download_dir=None, update=False,
                          confirmation_required=True, interval=None, verify_download_dir=True,
                          verbose=False, ret_download_path=False, **kwargs):
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
            >>> subrgn_name = 'London'
            >>> file_format = "pbf"

            >>> bbd.download_osm_data(subrgn_name, file_format, verbose=True)
            To download .pbf data of the following geographic (sub)region(s):
                London
            ? [No]|Yes: yes
            Downloading "London.osm.pbf"
                to "osm_data\\bbbike\\london\\" ... Done.

            >>> len(bbd.data_paths)
            1
            >>> os.path.relpath(bbd.data_paths[0])
            'osm_data\\bbbike\\london\\London.osm.pbf'

            >>> london_dwnld_dir = os.path.relpath(bbd.download_dir)
            >>> london_dwnld_dir
            'osm_data\\bbbike'

            >>> # Download PBF data of Leeds and Birmingham to a given directory
            >>> subrgn_names = ['leeds', 'birmingham']
            >>> dwnld_dir = "tests\\osm_data"

            >>> dwnld_paths = bbd.download_osm_data(
            ...     subrgn_names, file_format, dwnld_dir, verbose=True, ret_download_path=True)
            To download .pbf data of the following geographic (sub)region(s):
                Leeds
                Birmingham
            ? [No]|Yes: yes
            Downloading "Leeds.osm.pbf"
                to "tests\\osm_data\\leeds\\" ... Done.
            Downloading "Birmingham.osm.pbf"
                to "tests\\osm_data\\birmingham\\" ... Done.
            >>> len(dwnld_paths)
            2
            >>> len(bbd.data_paths)
            3
            >>> os.path.relpath(bbd.download_dir) == os.path.relpath(dwnld_dir)
            True
            >>> os.path.relpath(os.path.commonpath(dwnld_paths))
            'tests\\osm_data'

            >>> # Delete the above download directories
            >>> delete_dir([os.path.dirname(london_dwnld_dir), dwnld_dir], verbose=True)
            To delete the following directories:
                "osm_data\\" (Not empty)
                "tests\\osm_data\\" (Not empty)
            ? [No]|Yes: yes
            Deleting "osm_data\\" ... Done.
            Deleting "tests\\osm_data\\" ... Done.
        """

        (subregion_names_, osm_file_format_, confirmation_required_, update_msg, downloads_list,
         existing_file_paths) = self.file_exists_and_more(
            subregion_names=subregion_names, osm_file_format=osm_file_format,
            data_dir=download_dir, update=update, confirmation_required=confirmation_required,
            verbose=verbose)

        confirmation_required_ = confirmation_required_ and confirmation_required

        dwnld_list_msg = "\n\t".join(downloads_list)
        cfm_msg = f"To {update_msg} {osm_file_format_} data of " \
                  f"the following geographic (sub)region(s):\n\t{dwnld_list_msg}\n?"

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
                        download_url=download_url, file_pathname=file_pathname, verbose=verbose,
                        **kwargs)

                if os.path.isfile(file_pathname):
                    download_paths.append(file_pathname)

                if isinstance(interval, (int, float)):
                    # or os.path.getsize(path_to_file) / (1024 ** 2) <= 5:
                    time.sleep(interval)

            self.verify_download_dir(
                download_dir=download_dir, verify_download_dir=verify_download_dir)

        else:
            print("Cancelled.")

            download_paths = existing_file_paths

        self.data_paths = list(collections.OrderedDict.fromkeys(self.data_paths + download_paths))

        if ret_download_path:
            return download_paths
