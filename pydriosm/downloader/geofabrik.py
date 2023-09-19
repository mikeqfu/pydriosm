import collections
import importlib
import json
import os
import re
import time
import urllib.parse

import pandas as pd
import requests
import shapely.geometry
from pyhelpers.dirs import cd, validate_dir
from pyhelpers.ops import confirmed, fake_requests_headers, parse_size, update_dict
from pyhelpers.store import save_pickle

from pydriosm.downloader._downloader import _Downloader
from pydriosm.errors import InvalidFileFormatError, InvalidSubregionNameError
from pydriosm.utils import first_unique


class GeofabrikDownloader(_Downloader):
    """
    Download OSM data from `Geofabrik`_ free download server.

    .. _`Geofabrik`: https://download.geofabrik.de/
    """

    #: Name of the free download server.
    NAME = 'Geofabrik'
    #: Full name of the data resource.
    LONG_NAME = 'Geofabrik OpenStreetMap data extracts'
    #: URL of the homepage to the free download server.
    URL = 'https://download.geofabrik.de/'
    #: URL of the official download index.
    DOWNLOAD_INDEX_URL = urllib.parse.urljoin(URL, 'index-v1.json')
    #: Default download directory.
    DEFAULT_DOWNLOAD_DIR = "osm_data\\geofabrik"
    #: Valid file formats.
    FILE_FORMATS = {'.osm.pbf', '.shp.zip', '.osm.bz2'}

    def __init__(self, download_dir=None):
        """
        :param download_dir: name or pathname of a directory for saving downloaded data files,
            defaults to ``None``; when ``download_dir=None``, downloaded data files are saved to a
            folder named 'osm_data' under the current working directory
        :type download_dir: str | os.PathLike[str] | None

        :ivar set valid_subregion_names: names of (sub)regions available on the free download server
        :ivar set valid_file_formats: filename extensions of the data files available
        :ivar pandas.DataFrame download_index: index of downloads for all available (sub)regions
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

            >>> gfd = GeofabrikDownloader(download_dir="tests\\osm_data")
            >>> os.path.relpath(gfd.download_dir)
            'tests\\osm_data'
        """

        super().__init__(download_dir=download_dir)

        self.download_index = self.get_download_index()

        self.continent_tables = self.get_continent_tables()

        self.region_subregion_tier, self.having_no_subregions = self.get_region_subregion_tier()

        self.catalogue = self.get_catalogue()

        self.valid_subregion_names = self.get_valid_subregion_names()

    @classmethod
    def get_raw_directory_index(cls, url, verbose=False):
        """
        Get a raw directory index (including download information of older file logs).

        :param url: URL of a web page of a data resource (e.g. a subregion)
        :type url: str
        :param verbose: whether to print relevant information in console, defaults to ``False``
        :type verbose: bool | int
        :return: information of raw directory index
        :rtype: pandas.DataFrame | None

        **Examples**::

            >>> from pydriosm.downloader import GeofabrikDownloader

            >>> gfd = GeofabrikDownloader()

            >>> homepage_url = gfd.URL
            >>> homepage_url
            'https://download.geofabrik.de/'
            >>> raw_index = gfd.get_raw_directory_index(homepage_url, verbose=True)
            Collecting the raw directory index on 'https://download.geofabrik.de/' ... Failed.
            No raw directory index is available on the web page.
            >>> raw_index is None
            True

            >>> great_britain_url = 'https://download.geofabrik.de/europe/great-britain.html'
            >>> raw_index = gfd.get_raw_directory_index(great_britain_url)
            >>> type(raw_index)
            pandas.core.frame.DataFrame
            >>> raw_index.columns.tolist()
            ['file', 'date', 'size', 'metric_file_size', 'url']
        """

        if verbose:
            print(f"Collecting the raw directory index on '{url}'", end=" ... ")

        bs4_ = importlib.import_module(name='bs4')
        urllib_error = importlib.import_module(name='urllib.error')

        try:
            with requests.get(url=url, headers=fake_requests_headers()) as response:
                soup = bs4_.BeautifulSoup(markup=response.content, features='html.parser')

            cold_soup = soup.find(name='div', attrs={'id': 'details'})
            ths, tds = [], []
            for tr in cold_soup.find_all(name='tr'):
                if len(tr.find_all('th')) > 0:
                    ths = [x.get_text(strip=True) for x in tr.find_all(name='th')]
                else:
                    tds.append([x.get_text(strip=True) for x in tr.find_all(name='td')])

            raw_directory_index = pd.DataFrame(data=tds, columns=ths)

            # raw_directory_index.loc[:, 'date'] = pd.to_datetime(raw_directory_index['date'])
            raw_directory_index['date'] = pd.to_datetime(raw_directory_index['date'])
            # raw_directory_index.loc[:, 'size'] = raw_directory_index['size'].astype('int64')
            raw_directory_index['size'] = raw_directory_index['size'].astype('int64')

            raw_directory_index['metric_file_size'] = raw_directory_index['size'].map(
                lambda x: parse_size(x, binary=False, precision=0 if (x <= 1000) else 1))

            raw_directory_index['url'] = raw_directory_index['file'].map(
                lambda x: urllib.parse.urljoin(url, x))

            if verbose:
                print("Done.")

        except (urllib_error.HTTPError, AttributeError, TypeError, ValueError):
            print("Failed.")

            if verbose and len(urllib.parse.urlparse(url).path) <= 1:
                print("No raw directory index is available on the web page.")

            raw_directory_index = None

        return raw_directory_index

    @classmethod
    def _parse_download_index_urls(cls, urls):
        """
        Parse the dictionary of download URLs in the (original) dataframe of download index.

        :param urls: (original) series of the URLs provided in the official download index
        :type urls: pandas.Series
        :return: download index with parsed data of the URLs for downloading data
        :rtype: pandas.DataFrame

        .. seealso::

            - Examples for the method
              :meth:`~pydriosm.downloader.GeofabrikDownloader.get_download_index`.
        """

        temp = urls.map(lambda x: pd.DataFrame.from_dict(data=x, orient='index').T)

        urls_ = pd.concat(objs=temp.values, ignore_index=True)

        col_names = {
            'pbf': '.osm.pbf',
            'shp': '.shp.zip',
            'bz2': '.osm.bz2',
        }
        urls_.rename(columns=col_names, inplace=True)

        urls_ = urls_.where(pd.notnull(urls_), None)

        return urls_

    @classmethod
    def _download_index(cls, path_to_pickle=None, verbose=False):
        """
        Get the official index of downloads for all available geographic (sub)regions.

        :param path_to_pickle: pathname of the prepacked pickle file, defaults to ``None``
        :type path_to_pickle: str | os.PathLike[str] | None
        :param verbose: whether to print relevant information in console, defaults to ``False``
        :type verbose: bool | int
        :return: the official index of all downloads
        :rtype: pandas.DataFrame

        **Examples**::

            >>> from pydriosm.downloader import GeofabrikDownloader

            >>> gfd = GeofabrikDownloader()

            >>> gfd._download_index()

        .. seealso::

            - Examples for the method
              :meth:`~pydriosm.downloader.GeofabrikDownloader.get_download_index`.
        """

        with requests.get(url=cls.DOWNLOAD_INDEX_URL, headers=fake_requests_headers()) as response:
            raw_data = pd.DataFrame(json.loads(response.content)['features'])

        # Process 'properties'
        properties_ = pd.DataFrame(raw_data['properties'].to_list())
        properties = properties_.where(properties_.notnull(), None)

        # Process 'geometry'
        geometry_ = pd.DataFrame(raw_data['geometry'].to_list())
        geometry = geometry_.apply(
            lambda x: getattr(shapely.geometry, x['type'])(
                [shapely.geometry.Polygon(x['coordinates'][0][0])]), axis=1)
        geometry = pd.DataFrame(geometry, columns=['geometry'])

        dwnld_idx = pd.concat(objs=[properties, geometry], axis=1)

        # Process 'name'
        temp_names = dwnld_idx['name'].str.strip().str.replace('<br />', ' ')
        dwnld_idx.loc[:, 'name'] = temp_names.map(
            lambda x: x.replace('us/', '').title() if x.startswith('us/') else x)

        temp = (k for k, v in collections.Counter(dwnld_idx.name).items() if v > 1)
        duplicates = {i: x for k in temp for i, x in enumerate(dwnld_idx.name) if x == k}

        for dk in duplicates.keys():
            if dwnld_idx.loc[dk, 'id'].startswith('us/'):
                dwnld_idx.loc[dk, 'name'] += ' (US)'

        # Process 'urls'
        urls_column_name = 'urls'

        urls = cls._parse_download_index_urls(dwnld_idx[urls_column_name])
        del dwnld_idx[urls_column_name]

        # Put all together
        download_index = pd.concat(objs=[dwnld_idx, urls], axis=1)

        if verbose:
            print("Done.")

        if path_to_pickle:
            save_pickle(download_index, path_to_file=path_to_pickle, verbose=verbose)

        return download_index

    def get_download_index(self, update=False, confirmation_required=True, verbose=False):
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
        :return: the official index of all downloads
        :rtype: pandas.DataFrame | None

        **Examples**::

            >>> from pydriosm.downloader import GeofabrikDownloader

            >>> gfd = GeofabrikDownloader()

            >>> # Official index of all available downloads
            >>> geofabrik_dwnld_idx = gfd.get_download_index()
            >>> type(geofabrik_dwnld_idx)
            pandas.core.frame.DataFrame
            >>> geofabrik_dwnld_idx.head()
                        id  ...                                            updates
            0  afghanistan  ...  https://download.geofabrik.de/asia/afghanistan...
            1       africa  ...       https://download.geofabrik.de/africa-updates
            2      albania  ...  https://download.geofabrik.de/europe/albania-u...
            3      alberta  ...  https://download.geofabrik.de/north-america/ca...
            4      algeria  ...  https://download.geofabrik.de/africa/algeria-u...
            [5 rows x 13 columns]

            >>> geofabrik_dwnld_idx.columns.to_list()
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
            self._download_index, data_name=data_name, update=update,
            confirmation_required=confirmation_required, verbose=verbose)

        if update is True:
            self.download_index = download_index

        return download_index

    @classmethod
    def _parse_subregion_table_tr(cls, tr, url):
        """
        Parse a <tr> tag under a <table> tag of the HTML data of a (sub)region.

        :param tr: <tr> tag under a <table> tag of a subregion's HTML data
        :type tr: bs4.element.Tag
        :param url: URL of a subregion's web page
        :type url: str
        :return: data contained in the <tr> tag
        :rtype: list

        .. seealso::

            - Examples for the method
              :meth:`~pydriosm.downloader.GeofabrikDownloader.get_subregion_table`.
        """

        td_data = []

        tds = tr.findChildren(name='td')

        for td in tds:
            if td.has_attr('class'):
                td_text = td.get_text(separator=' ', strip=True)
                td_data += [td_text, urllib.parse.urljoin(base=url, url=td.a['href'])]

            else:
                td_link = urllib.parse.urljoin(base=url, url=td.a['href']) if td.a else None

                if td.has_attr('style'):
                    if td.get('style').startswith('border-right'):
                        td_data.append(td_link)
                    elif td.get('style').startswith('border-left'):
                        td_data.append(re.sub(r'[()]', '', td.text.strip().replace('\xa0', ' ')))
                else:
                    td_data.append(td_link)

        return td_data

    @classmethod
    def get_subregion_table(cls, url, verbose=False):
        """
        Get download information of all geographic (sub)regions on a web page.

        :param url: URL of a subregion's web page
        :type url: str
        :param verbose: whether to print relevant information in console, defaults to ``False``
        :type verbose: bool | int
        :return: download information of all available subregions on the given ``url``
        :rtype: pandas.DataFrame | None

        **Examples**::

            >>> from pydriosm.downloader import GeofabrikDownloader

            >>> gfd = GeofabrikDownloader()

            >>> # Download information on the homepage
            >>> homepage = gfd.get_subregion_table(url=gfd.URL)
            >>> homepage
                           subregion  ...                                           .osm.bz2
            0                 Africa  ...  https://download.geofabrik.de/africa-latest.os...
            1             Antarctica  ...  https://download.geofabrik.de/antarctica-lates...
            2                   Asia  ...  https://download.geofabrik.de/asia-latest.osm.bz2
            3  Australia and Oceania  ...  https://download.geofabrik.de/australia-oceani...
            4        Central America  ...  https://download.geofabrik.de/central-america-...
            5                 Europe  ...  https://download.geofabrik.de/europe-latest.os...
            6          North America  ...  https://download.geofabrik.de/north-america-la...
            7          South America  ...  https://download.geofabrik.de/south-america-la...
            [8 rows x 6 columns]

            >>> homepage.columns.to_list()
            ['subregion',
             'subregion-url',
             '.osm.pbf',
             '.osm.pbf-size',
             '.shp.zip',
             '.osm.bz2']

            >>> # Download information about 'Great Britain'
            >>> great_britain_url = 'https://download.geofabrik.de/europe/great-britain.html'
            >>> great_britain = gfd.get_subregion_table(great_britain_url)
            >>> great_britain
              subregion  ...                                           .osm.bz2
            0   England  ...  https://download.geofabrik.de/europe/great-bri...
            1  Scotland  ...  https://download.geofabrik.de/europe/great-bri...
            2     Wales  ...  https://download.geofabrik.de/europe/great-bri...
            [3 rows x 6 columns]

            >>> # Download information about 'Antarctica'
            >>> antarctica_url = 'https://download.geofabrik.de/antarctica.html'
            >>> antarctica = gfd.get_subregion_table(antarctica_url, verbose=True)
            Compiling information about subregions of "Antarctica" ... Failed.
            >>> antarctica is None
            True

            >>> # To get more information about the above failure, set `verbose=2`
            >>> antarctica2 = gfd.get_subregion_table(antarctica_url, verbose=2)
            Compiling information about subregions of "Antarctica" ... Failed.
            No subregion data is available for "Antarctica" on Geofabrik's free download server.
            >>> antarctica2 is None
            True
        """

        region_name = url.split('/')[-1].split('.')[0].replace('-', ' ').title()
        if verbose:
            print(f"Compiling information about subregions of \"{region_name}\"", end=" ... ")

        try:
            bs4_ = importlib.import_module('bs4')

            with requests.get(url=url, headers=fake_requests_headers()) as response:
                soup = bs4_.BeautifulSoup(markup=response.content, features='html.parser')

            tr_data = []

            h3_tags = soup.find_all(name='h3', string=re.compile(r'(Special )?Sub[ \-]Regions?'))
            if len(h3_tags) > 0:
                for h3_tag in h3_tags:
                    table = h3_tag.find_next(
                        name='table', attrs={'id': re.compile(r'(special)?subregions')})
                    trs = table.findChildren(name='tr', onmouseover=True)
                    tr_data += [cls._parse_subregion_table_tr(tr=tr, url=url) for tr in trs]
            else:
                table_tags = soup.find_all(
                    name='table', attrs={'id': re.compile(r'(special)?subregions')})
                for table_tag in table_tags:
                    trs = table_tag.findChildren(name='tr', onmouseover=True)
                    tr_data += [cls._parse_subregion_table_tr(tr=tr, url=url) for tr in trs]

            column_names = [  # Specify column names
                'subregion', 'subregion-url', '.osm.pbf', '.osm.pbf-size', '.shp.zip', '.osm.bz2']

            tbl = pd.DataFrame(data=tr_data, columns=column_names)
            table = tbl.where(pd.notnull(tbl), None)

            if verbose:
                print("Done.")

        except (AttributeError, ValueError, TypeError):
            if verbose:
                print("Failed.")
                if verbose == 2:
                    print(f"No subregion data is available for \"{region_name}\" "
                          f"on {cls.NAME}'s free download server.")

            table = None

        except (ConnectionRefusedError, ConnectionError):
            print("Failed.")

            if verbose == 2:
                print(f"Errors occurred when trying to connect {cls.NAME}'s free download server.")

            table = None

        return table

    @classmethod
    def _continent_tables(cls, path_to_pickle=None, verbose=False):
        """
        Get download catalogues for each continent.

        :param path_to_pickle: pathname of the prepacked pickle file, defaults to ``None``
        :type path_to_pickle: str | os.PathLike[str] | None
        :param verbose: whether to print relevant information in console, defaults to ``False``
        :type verbose: bool | int
        :return: download catalogues for each continent
        :rtype: dict

        .. seealso::

            - Examples for the method
              :meth:`~pydriosm.downloader.GeofabrikDownloader.get_continent_tables`.
        """

        bs4_ = importlib.import_module('bs4')

        with requests.get(url=cls.URL, headers=fake_requests_headers()) as response:
            soup = bs4_.BeautifulSoup(markup=response.content, features='html.parser')

        # Scan the homepage to collect info of regions for each continent
        tds = soup.find_all(name='td', attrs={'class': 'subregion'})
        continent_names = [td.a.text for td in tds]

        continent_links = [urllib.parse.urljoin(cls.URL, url=td.a['href']) for td in tds]
        continent_links_dat = [cls.get_subregion_table(url=url) for url in continent_links]
        continent_tables = dict(zip(continent_names, continent_links_dat))

        if verbose:
            print("Done.")

        if path_to_pickle:
            save_pickle(continent_tables, path_to_file=path_to_pickle, verbose=verbose)

        return continent_tables

    def get_continent_tables(self, update=False, confirmation_required=True, verbose=False):
        """
        Get download catalogues for each continent.

        :param update: whether to (check on and) update the prepacked data, defaults to ``False``
        :type update: bool
        :param confirmation_required: whether asking for confirmation to proceed,
            defaults to ``True``
        :type confirmation_required: bool
        :param verbose: whether to print relevant information in console, defaults to ``False``
        :type verbose: bool | int
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
            >>> len(asia_table) >= 39
            True
            >>> asia_table.head()
                 subregion  ...                                           .osm.bz2
            0  Afghanistan  ...  https://download.geofabrik.de/asia/afghanistan...
            1      Armenia  ...  https://download.geofabrik.de/asia/armenia-lat...
            2   Azerbaijan  ...  https://download.geofabrik.de/asia/azerbaijan-...
            3   Bangladesh  ...  https://download.geofabrik.de/asia/bangladesh-...
            4       Bhutan  ...  https://download.geofabrik.de/asia/bhutan-late...
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
            meth=self._continent_tables, data_name=data_name, update=update,
            confirmation_required=confirmation_required, verbose=verbose)

        return continents_subregion_tables

    @classmethod
    def _compile_region_subregion_tier(cls, subregion_tables):
        """
        Find out the all (sub)regions and their subregions.

        :param subregion_tables: download URLs of subregions;
            see examples of the methods
            :meth:`~pydriosm.downloader.GeofabrikDownloader.get_subregion_table` and
            :meth:`~pydriosm.downloader.GeofabrikDownloader.get_continent_tables`
        :type subregion_tables: dict
        :return: a dictionary of region-subregion, and a list of (sub)regions without subregions
        :rtype: tuple[dict, list]

        .. seealso::

            - Examples for the method
              :meth:`~pydriosm.downloader.GeofabrikDownloader.get_region_subregion_tier`.
        """

        having_subregions = subregion_tables.copy()
        region_subregion_tier = having_subregions.copy()

        having_no_subregions = []
        for k, v in subregion_tables.items():
            if isinstance(v, pd.DataFrame):  # and v is not None
                update_dict(
                    dictionary=region_subregion_tier, updates={k: set(v['subregion'])},
                    inplace=True)
            else:
                having_no_subregions.append(k)
                having_subregions.pop(k)

        having_subregions_temp = having_subregions.copy()

        while having_subregions_temp:
            for region_name, subregion_table in having_subregions.items():
                subregion_tbls = [
                    cls.get_subregion_table(url=url) for url in subregion_table['subregion-url']]
                sub_subregion_tables = dict(zip(subregion_table['subregion'], subregion_tbls))

                region_subregion_tiers_, having_no_subregions_ = \
                    cls._compile_region_subregion_tier(subregion_tables=sub_subregion_tables)

                having_no_subregions += having_no_subregions_

                region_subregion_tier.update({region_name: region_subregion_tiers_})
                having_subregions_temp.pop(region_name)

        having_no_subregions = list(first_unique(having_no_subregions))

        return region_subregion_tier, having_no_subregions

    def _region_subregion_tier(self, path_to_pickle=None, verbose=False):
        """
        Get region-subregion tier.

        :param path_to_pickle: pathname of the prepacked pickle file, defaults to ``None``
        :type path_to_pickle: str | os.PathLike[str] | None
        :param verbose: whether to print relevant information in console, defaults to ``False``
        :type verbose: bool | int
        :return: region-subregion tier and all that have no subregions
        :rtype: tuple[dict, list]

        .. seealso::

            - Examples for the method
              :meth:`~pydriosm.downloader.GeofabrikDownloader.get_region_subregion_tier`.
        """

        tiers, having_no_subregions = self._compile_region_subregion_tier(self.continent_tables)

        try:
            georgia = 'Georgia'
            georgia_us = georgia + ' (US)'
            # region-subregion tiers
            tiers['North America']['United States of America'][georgia_us] = \
                tiers['North America']['United States of America'].pop(georgia)
            having_no_subregions.append(georgia_us)
            # having_no_subregions.sort()
        except KeyError:
            pass

        if verbose:
            print("Done.")

        if path_to_pickle:
            save_pickle((tiers, having_no_subregions), path_to_file=path_to_pickle, verbose=verbose)

        return tiers, having_no_subregions

    def get_region_subregion_tier(self, update=False, confirmation_required=True, verbose=False):
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
        :return: region-subregion tier and all (sub)regions that have no subregions
        :rtype: tuple[dict, list] | tuple[None, None]

        **Examples**::

            >>> from pydriosm.downloader import GeofabrikDownloader

            >>> gfd = GeofabrikDownloader()

            >>> # region-subregion tier, and all regions that have no subregions
            >>> rgn_subrgn_tier, no_subrgn_list = gfd.get_region_subregion_tier()
            >>> type(rgn_subrgn_tier)
            dict
            >>> # Keys of the region-subregion tier
            >>> list(rgn_subrgn_tier.keys())
            ['Africa',
             'Antarctica',
             'Asia',
             'Australia and Oceania',
             'Central America',
             'Europe',
             'North America',
             'South America']

            >>> type(no_subrgn_list)
            list
            >>> # Example: five regions that have no subregions
            >>> no_subrgn_list[0:5]
            ['Antarctica', 'Algeria', 'Angola', 'Benin', 'Botswana']
        """

        data_name = f'{self.NAME} region-subregion tier'

        if update:
            self.continent_tables = self.get_continent_tables(
                update=update, confirmation_required=False, verbose=False)

        note_msg = "(Note that this process may take a few minutes)"

        data = self.get_prepacked_data(
            self._region_subregion_tier, data_name=data_name, update=update,
            confirmation_required=confirmation_required, verbose=verbose, cfm_msg_note=note_msg,
            act_msg_note="" if confirmation_required else note_msg)

        if data is None:
            tiers, having_no_subregions = None, None
        else:
            tiers, having_no_subregions = data
            if update is True:
                self.region_subregion_tier = tiers
                self.having_no_subregions = having_no_subregions

        return tiers, having_no_subregions

    def _catalogue(self, path_to_pickle=None, verbose=False):
        """
        Get a catalogue (index) of all available downloads.

        :param path_to_pickle: pathname of the prepacked pickle file, defaults to ``None``
        :type path_to_pickle: str | os.PathLike[str] | None
        :param verbose: whether to print relevant information in console, defaults to ``False``
        :type verbose: bool | int
        :return: a catalogue for all subregion downloads
        :rtype: pandas.DataFrame

        .. seealso::

            - Examples for the method
              :meth:`~pydriosm.downloader.GeofabrikDownloader.get_catalogue`.
        """

        bs4_ = importlib.import_module('bs4')

        with requests.get(url=self.URL, headers=fake_requests_headers()) as response:
            soup = bs4_.BeautifulSoup(markup=response.content, features='html.parser')

        # Home table
        home_tr_data = []
        table_tags = soup.find_all(name='table', attrs={'id': re.compile(r'(special)?subregions')})
        for table_tag in table_tags:
            trs = table_tag.findChildren(name='tr', onmouseover=True)
            home_tr_data += [self._parse_subregion_table_tr(tr=tr, url=self.URL) for tr in trs]

        column_names = ['subregion', 'subregion-url', '.osm.pbf', '.shp.zip', '.osm.bz2']
        column_names.insert(3, '.osm.pbf-size')

        home_subregion_table = pd.DataFrame(data=home_tr_data, columns=column_names)

        # Subregions' tables
        cont_tds = soup.find_all(name='td', attrs={'class': 'subregion'})
        cont_urls = [urllib.parse.urljoin(base=self.URL, url=td.a.get('href')) for td in cont_tds]
        continent_tbls = [self.get_subregion_table(url=url, verbose=False) for url in cont_urls]
        avail_subregion_tables = [tbl for tbl in continent_tbls if tbl is not None]

        subregion_tables = avail_subregion_tables.copy()

        while subregion_tables:

            subregion_tables_ = []
            for subregion_table in subregion_tables:
                urls = subregion_table['subregion-url']
                temp = [self.get_subregion_table(url=x, verbose=False) for x in urls]
                subregion_tables_ += [tbl for tbl in temp if tbl is not None]
                avail_subregion_tables += subregion_tables_

            subregion_tables = subregion_tables_.copy()

        # All available URLs for downloading data
        all_tables = [home_subregion_table] + avail_subregion_tables

        downloads_catalogue = pd.concat(objs=all_tables, axis=0, ignore_index=True)
        downloads_catalogue.drop_duplicates(inplace=True, ignore_index=True)

        temp = (k for k, v in collections.Counter(downloads_catalogue.subregion).items() if v > 1)
        duplicates = {
            i: x for k in temp for i, x in enumerate(downloads_catalogue.subregion) if x == k}

        for dk in duplicates.keys():
            if os.path.dirname(downloads_catalogue.loc[dk, 'subregion-url']).endswith('us'):
                downloads_catalogue.loc[dk, 'subregion'] += ' (US)'

        if verbose:
            print("Done.")

        if path_to_pickle:
            save_pickle(downloads_catalogue, path_to_file=path_to_pickle, verbose=verbose)

        return downloads_catalogue

    def get_catalogue(self, update=False, confirmation_required=True, verbose=False):
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
                           subregion  ...                                           .osm.bz2
            0                 Africa  ...  https://download.geofabrik.de/africa-latest.os...
            1             Antarctica  ...  https://download.geofabrik.de/antarctica-lates...
            2                   Asia  ...  https://download.geofabrik.de/asia-latest.osm.bz2
            3  Australia and Oceania  ...  https://download.geofabrik.de/australia-oceani...
            4        Central America  ...  https://download.geofabrik.de/central-america-...
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
              `London\\Enfield
              <https://download.geofabrik.de/europe/great-britain/england/london/>`_
              is not directly available from the web page of `Greater London
              <https://download.geofabrik.de/europe/great-britain/england/greater-london.html>`_.
            - Two subregions have the same name 'Georgia':
              `Europe\\Georgia <https://download.geofabrik.de/europe/georgia.html>`_ and
              `US\\Georgia <https://download.geofabrik.de/north-america/us/georgia.html>`_;
              In the latter case, a suffix ' (US)' is appended to the name in the table.
        """

        data_name = f'{self.NAME} downloads catalogue'

        msg_note = "(Note that this process may take a few minutes)"

        downloads_catalogue = self.get_prepacked_data(
            self._catalogue, data_name=data_name, update=update,
            confirmation_required=confirmation_required, verbose=verbose, cfm_msg_note=msg_note,
            act_msg_note="" if confirmation_required else msg_note)

        if update is True:
            self.catalogue = downloads_catalogue

        return downloads_catalogue

    def _valid_subregion_names(self, path_to_pickle=None, verbose=False):
        """
        Get names of all available geographic (sub)regions.

        :param path_to_pickle: pathname of the prepacked pickle file, defaults to ``None``
        :type path_to_pickle: str | os.PathLike[str] | None
        :param verbose: whether to print relevant information in console, defaults to ``False``
        :type verbose: bool | int
        :return: names of all geographic (sub)regions available on Geofabrik free download server
        :rtype: set

        .. seealso::

            - Examples for the method
              :meth:`~pydriosm.downloader.GeofabrikDownloader.get_valid_subregion_names`.
        """

        dwnld_index = self.get_download_index(
            update=False, confirmation_required=False, verbose=False)

        valid_subregion_names = set(dwnld_index['name'])

        if verbose:
            print("Done.")

        if path_to_pickle:
            save_pickle(valid_subregion_names, path_to_file=path_to_pickle, verbose=verbose)

        return valid_subregion_names

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
            meth=self._valid_subregion_names, data_name=data_name, update=update,
            confirmation_required=confirmation_required, verbose=verbose)

        return self.valid_subregion_names

    def validate_subregion_name(self, subregion_name, valid_subregion_names=None, raise_err=True,
                                **kwargs):
        """
        Validate an input name of a geographic (sub)region.

        The validation is done by matching the input to a name of a geographic (sub)region
        available on Geofabrik free download server.

        :param subregion_name: name/URL of a (sub)region available on Geofabrik free download server
        :type subregion_name: str
        :param valid_subregion_names: names of all (sub)regions available on a free download server
        :type valid_subregion_names: typing.Iterable
        :param raise_err: (if the input fails to match a valid name) whether to raise the error
            :py:class:`pydriosm.downloader.InvalidSubregionName`, defaults to ``True``
        :type raise_err: bool
        :param kwargs: [optional] parameters of `pyhelpers.text.find_similar_str()`_
        :return: valid subregion name that matches (or is the most similar to) the input
        :rtype: str

        .. _`pyhelpers.text.find_similar_str()`:
            https://pyhelpers.readthedocs.io/en/latest/_generated/
            pyhelpers.text.find_similar_str.html

        **Examples**::

            >>> from pydriosm.downloader import GeofabrikDownloader

            >>> gfd = GeofabrikDownloader()

            >>> input_subrgn_name = 'london'
            >>> valid_subrgn_name = gfd.validate_subregion_name(subregion_name=input_subrgn_name)
            >>> valid_subrgn_name
            'Greater London'

            >>> input_subrgn_name = 'https://download.geofabrik.de/europe/great-britain.html'
            >>> valid_subrgn_name = gfd.validate_subregion_name(subregion_name=input_subrgn_name)
            >>> valid_subrgn_name
            'Great Britain'
        """

        if valid_subregion_names is None:
            valid_subregion_names_ = self.valid_subregion_names
        else:
            valid_subregion_names_ = valid_subregion_names

        subregion_name_ = super().validate_subregion_name(
            subregion_name=subregion_name, valid_subregion_names=valid_subregion_names_,
            raise_err=raise_err, **kwargs)

        return subregion_name_

    def validate_file_format(self, osm_file_format, valid_file_formats=None, raise_err=True,
                             **kwargs):
        """
        Validate an input file format of OSM data.

        The validation is done by matching the input to a filename extension available on
        Geofabrik free download server.

        :param osm_file_format: file format/extension of the OSM data on the free download server
        :type osm_file_format: str
        :param valid_file_formats: fil extensions of the data available on a free download server
        :type valid_file_formats: typing.Iterable
        :param raise_err: (if the input fails to match a valid name) whether to raise the error
            :py:class:`pydriosm.downloader.InvalidFileFormatError`, defaults to ``True``
        :type raise_err: bool
        :param kwargs: [optional] parameters of `pyhelpers.text.find_similar_str()`_
        :return: formal file format
        :rtype: str

        .. _`pyhelpers.text.find_similar_str()`:
            https://pyhelpers.readthedocs.io/en/latest/_generated/
            pyhelpers.text.find_similar_str.html

        **Examples**::

            >>> from pydriosm.downloader import GeofabrikDownloader

            >>> gfd = GeofabrikDownloader()

            >>> input_file_format = ".pbf"
            >>> valid_file_format = gfd.validate_file_format(osm_file_format=input_file_format)
            >>> valid_file_format
            '.osm.pbf'

            >>> input_file_format = "shp"
            >>> valid_file_format = gfd.validate_file_format(osm_file_format=input_file_format)
            >>> valid_file_format
            '.shp.zip'
        """

        if valid_file_formats is None:
            valid_file_formats_ = self.FILE_FORMATS
        else:
            valid_file_formats_ = valid_file_formats

        osm_file_format_ = super().validate_file_format(
            osm_file_format=osm_file_format, valid_file_formats=valid_file_formats_,
            raise_err=raise_err, **kwargs)

        return osm_file_format_

    def get_subregion_download_url(self, subregion_name, osm_file_format, update=False,
                                   verbose=False):
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
        :return: name and URL of the subregion
        :rtype: typing.Tuple[str, str | None]

        **Examples**::

            >>> from pydriosm.downloader import GeofabrikDownloader

            >>> gfd = GeofabrikDownloader()

            >>> subrgn_name = 'England'
            >>> file_format = ".pbf"
            >>> valid_name, dwnld_link = gfd.get_subregion_download_url(subrgn_name, file_format)
            >>> valid_name  # The name of the subregion on the free downloader server
            'England'
            >>> dwnld_link  # The URL of the PBF data file
            'https://download.geofabrik.de/europe/great-britain/england-latest.osm.pbf'

            >>> subrgn_name = 'britain'
            >>> file_format = ".shp"
            >>> valid_name, dwnld_link = gfd.get_subregion_download_url(subrgn_name, file_format)
            >>> valid_name
            'Great Britain'
            >>> dwnld_link is None  # The URL of the shapefile for Great Britain is not available
            True
        """

        if update:  # Update the download catalogue (including download URLs)
            _ = self.get_catalogue(update=update, verbose=verbose)

        subrgn_dwnld_cat = self.catalogue.set_index(keys='subregion')

        try:
            subregion_name_ = self.validate_subregion_name(subregion_name=subregion_name)
            osm_file_format_ = self.validate_file_format(osm_file_format=osm_file_format)

            # Get the URL
            download_url = subrgn_dwnld_cat.loc[subregion_name_, osm_file_format_]

        except (InvalidSubregionNameError, InvalidFileFormatError):
            subregion_name_, download_url = None, None

        return subregion_name_, download_url

    def get_default_filename(self, subregion_name, osm_file_format, update=False):
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
            >>> subrgn_name, file_format = 'london', ".pbf"
            >>> default_fn = gfd.get_default_filename(subrgn_name, file_format)
            >>> default_fn
            'greater-london-latest.osm.pbf'

            >>> # Default filename of the shapefile data of Great Britain
            >>> subrgn_name, file_format = 'britain', ".shp"
            >>> default_fn = gfd.get_default_filename(subrgn_name, file_format)
            No .shp.zip data is available to download for Great Britain.
            >>> default_fn is None
            True
        """

        subregion_name_, download_url = self.get_subregion_download_url(
            subregion_name=subregion_name, osm_file_format=osm_file_format, update=update)

        if download_url is None:
            osm_file_format_ = self.validate_file_format(osm_file_format=osm_file_format)
            print(f"No {osm_file_format_} data is available to download for {subregion_name_}.")
            default_filename = None

        else:
            default_filename = os.path.basename(download_url)

        return default_filename

    def _default_pathname(self, download_url, mkdir=False):
        """
        Get the default pathname of a local directory for storing a downloaded data file,
        given its URL.

        :param download_url: URL for downloading a data file
        :type download_url: str
        :param mkdir: whether to create the directory (and subdirectories) if not available,
            defaults to ``False``
        :type mkdir: bool
        :return: efault filename of the subregion and default (absolute) path to the file
        :rtype: tuple[str, str]

        .. seealso::

            - Examples for the method
              :meth:`~pydriosm.downloader.GeofabrikDownloader.get_default_file_path`.
        """

        parsed_path = str(urllib.parse.urlparse(download_url).path).lstrip('/').split('/')

        default_filename = parsed_path[-1]
        sub_dir_ = re.sub(r'-(latest|free)', '', default_filename.split('.')[0])

        sub_dirs_and_filename = parsed_path[:-1] + [sub_dir_, default_filename]

        # sub_dirs = [
        #     find_similar_str(
        #         re.sub(r'-(latest|free)', '', x.split('.')[0]), self.valid_subregion_names)
        #     if x != 'us' else 'United States of America' for x in parsed_path]
        # directory = self.cdd(*sub_dirs, mkdir=mkdir)
        # default_file_path = os.path.join(directory, default_filename)

        default_pathname = self.cdd(*sub_dirs_and_filename, mkdir=mkdir)

        return default_pathname, default_filename

    def get_default_pathname(self, subregion_name, osm_file_format, mkdir=False, update=False,
                             verbose=False):
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
            >>> subrgn_name, file_format = 'london', ".pbf"

            >>> pathname, filename = gfd.get_default_pathname(subrgn_name, file_format)
            >>> os.path.relpath(os.path.dirname(pathname))
            'osm_data\\geofabrik\\europe\\great-britain\\england\\greater-london'
            >>> filename
            'greater-london-latest.osm.pbf'
        """

        subregion_name_, download_url = self.get_subregion_download_url(
            subregion_name=subregion_name, osm_file_format=osm_file_format, update=update)

        if download_url is None:  # The requested data may not exist
            if verbose:
                # osm_file_format_ = re.search(
                #     r'\.\w{3}\.\w{3}', os.path.basename(download_url)).group()
                osm_file_format_ = self.validate_file_format(osm_file_format=osm_file_format)
                print(f"No {osm_file_format_} data is available to download for {subregion_name_}.")
            default_pathname, default_filename = None, None

        else:
            default_pathname, default_filename = self._default_pathname(
                download_url=download_url, mkdir=mkdir)

        return default_pathname, default_filename

    def _enumerate_subregions(self, subregion_name, region_subregion_tier=None):
        """
        Find subregions of a given geographic (sub)region.

        :param subregion_name: name of a (sub)region available on Geofabrik free download server
        :type subregion_name: str
        :param region_subregion_tier: region-subregion tier, defaults to ``None``;
            when ``region_subregion_tier=None``,
            it defaults to the dictionary returned by the method
            :meth:`~pydriosm.downloader.GeofabrikDownloader.get_region_subregion_tier`
        :type region_subregion_tier: dict
        :return: name(s) of subregion(s) of the given geographic (sub)region
        :rtype: generator object

        **Examples**::

            >>> from pydriosm.downloader import GeofabrikDownloader

            >>> gfd = GeofabrikDownloader()

            >>> gb_subregions = gfd._enumerate_subregions(subregion_name='Great Britain')
            >>> type(gb_subregions)
            generator
            >>> list(gb_subregions)
            [['England', 'Scotland', 'Wales']]
        """

        if region_subregion_tier is None:
            rgn_subrgn_tier, _ = self.get_region_subregion_tier()
        else:
            rgn_subrgn_tier = region_subregion_tier.copy()

        for k, v in rgn_subrgn_tier.items():
            if subregion_name == k:
                if isinstance(v, dict):
                    yield list(v.keys())
                else:
                    yield [subregion_name] if isinstance(subregion_name, str) else subregion_name
            elif isinstance(v, dict):
                for subrgn in self._enumerate_subregions(subregion_name, v):
                    if isinstance(subrgn, dict):
                        yield list(subrgn.keys())
                    else:
                        yield [subrgn] if isinstance(subrgn, str) else subrgn

    def get_subregions(self, *subregion_name, deep=False):
        """
        Retrieve names of all subregions (if any) of the given geographic (sub)region(s).

        The returned result is based on the region-subregion tier structured by the method
        :meth:`~pydriosm.downloader.GeofabrikDownloader.get_region_subregion_tier`.

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
                subrgn_names = self._enumerate_subregions(subrgn_name, self.region_subregion_tier)
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

            >>> subrgn_name = 'london'
            >>> file_format = ".pbf"

            >>> # Default download directory (if the requested data file is not available)
            >>> dwnld_dir = gfd.specify_sub_download_dir(subrgn_name, file_format)
            >>> os.path.dirname(os.path.relpath(dwnld_dir))
            'osm_data\\geofabrik\\europe\\great-britain\\england\\greater-london'

            >>> # When a download directory is specified
            >>> dwnld_dir = "tests\\osm_data"

            >>> subrgn_name = 'britain'
            >>> file_format = ".shp"

            >>> dwnld_pathname = gfd.specify_sub_download_dir(subrgn_name, file_format, dwnld_dir)
            >>> os.path.relpath(dwnld_pathname)
            'tests\\osm_data\\great-britain-shp-zip'

            >>> gfd_ = GeofabrikDownloader(download_dir=dwnld_dir)
            >>> dwnld_pathname_ = gfd_.specify_sub_download_dir(subrgn_name, file_format)
            >>> os.path.relpath(dwnld_pathname_)
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
            if sub_path + "\\" + sub_dir in self.download_dir:
                sub_dwnld_dir = self.download_dir
            else:
                sub_dwnld_dir = cd(self.download_dir, sub_path, sub_dir, **kwargs)
        else:
            sub_dwnld_dir = cd(validate_dir(path_to_dir=download_dir), sub_dir, **kwargs)

        return sub_dwnld_dir

    def get_valid_download_info(self, subregion_name, osm_file_format, download_dir=None, **kwargs):
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

            >>> subrgn_name = 'london'
            >>> file_format = "pbf"

            >>> # valid subregion name, filename, download url and absolute file path
            >>> info1 = gfd.get_valid_download_info(subrgn_name, file_format)
            >>> valid_subrgn_name, pbf_filename, dwnld_url, path_to_pbf = info1

            >>> valid_subrgn_name
            'Greater London'
            >>> pbf_filename
            'greater-london-latest.osm.pbf'
            >>> os.path.dirname(dwnld_url)
            'https://download.geofabrik.de/europe/great-britain/england'
            >>> os.path.relpath(os.path.dirname(path_to_pbf))
            'osm_data\\geofabrik\\europe\\great-britain\\england\\greater-london'

            >>> # Specify a new directory for downloaded data
            >>> dwnld_dir = "tests\\osm_data"

            >>> info2 = gfd.get_valid_download_info(subrgn_name, file_format, dwnld_dir)
            >>> _, _, _, path_to_pbf2 = info2

            >>> os.path.relpath(os.path.dirname(path_to_pbf2))
            'tests\\osm_data\\greater-london'

            >>> gfd_ = GeofabrikDownloader(download_dir=dwnld_dir)

            >>> info3 = gfd_.get_valid_download_info(subrgn_name, file_format)
            >>> _, _, _, path_to_pbf3 = info3

            >>> os.path.relpath(os.path.dirname(path_to_pbf3))
            'tests\\osm_data\\europe\\great-britain\\england\\greater-london'
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

            >>> # Specify a download directory
            >>> dwnld_dir = "tests\\osm_data"

            >>> gfd = GeofabrikDownloader(download_dir=dwnld_dir)

            >>> subregion_name = 'london'
            >>> osm_file_format = ".pbf"

            >>> # Download the PBF data of London (to the default directory)
            >>> gfd.download_osm_data(subregion_name, osm_file_format, verbose=True)
            To download .osm.pbf data of the following geographic (sub)region(s):
                Greater London
            ? [No]|Yes: yes
            Downloading "greater-london-latest.osm.pbf"
                to "tests\\osm_data\\europe\\great-britain\\england\\greater-london\\"...Done.

            >>> # Check whether the PBF data file exists; `ret_file_path` is by default `False`
            >>> pbf_exists = gfd.file_exists(subregion_name, osm_file_format)
            >>> pbf_exists  # If the data file exists at the default directory
            True

            >>> # Set `ret_file_path=True`
            >>> path_to_pbf = gfd.file_exists(subregion_name, osm_file_format, ret_file_path=True)
            >>> os.path.relpath(path_to_pbf)  # If the data file exists at the default directory
            'tests\\osm_data\\europe\\great-britain\\england\\greater-london\\greater-londo...'

            >>> # Remove the download directory:
            >>> delete_dir(dwnld_dir, verbose=True)
            To delete the directory "tests\\osm_data\\" (Not empty)
            ? [No]|Yes: yes
            Deleting "tests\\osm_data\\" ... Done.

            >>> # Check if the data file still exists at the specified download directory
            >>> gfd.file_exists(subregion_name, osm_file_format)
            False
        """

        file_exists = super().file_exists(
            subregion_name=subregion_name, osm_file_format=osm_file_format, data_dir=data_dir,
            update=update, verbose=verbose, ret_file_path=ret_file_path)

        return file_exists

    def download_osm_data(self, subregion_names, osm_file_format, download_dir=None, update=False,
                          confirmation_required=True, deep_retry=False, interval=None,
                          verify_download_dir=True, verbose=False, ret_download_path=False,
                          **kwargs):
        """
        Download OSM data (in a specific format) of one (or multiple) geographic (sub)region(s).

        :param subregion_names: name of a geographic (sub)region
            (or names of multiple geographic (sub)regions)
            available on Geofabrik free download server
        :type subregion_names: str | list
        :param osm_file_format: file format/extension of the OSM data
            available on the download server
        :type osm_file_format: str
        :param download_dir: directory for saving the downloaded file(s), defaults to ``None``;
            when ``download_dir=None``, it refers to the method
            :meth:`~pydriosm.downloader.GeofabrikDownloader.cdd`
        :type download_dir: str | None
        :param update: whether to update the data if it already exists, defaults to ``False``
        :type update: bool
        :param confirmation_required: whether asking for confirmation to proceed,
            defaults to ``True``
        :type confirmation_required: bool
        :param deep_retry: whether to further check availability of sub-subregions data,
            defaults to ``False``
        :type deep_retry: bool
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
            >>> subrgn_names = ['london', 'rutland']  # Case-insensitive
            >>> file_format = ".pbf"

            >>> gfd.download_osm_data(subrgn_names, file_format, verbose=True)
            To download .osm.pbf data of the following geographic (sub)region(s):
                Greater London
                Rutland
            ? [No]|Yes: yes
            Downloading "greater-london-latest.osm.pbf"
                to "osm_data\\geofabrik\\europe\\great-britain\\england\\greater-london\\" ... Done.
            Downloading "rutland-latest.osm.pbf"
                to "osm_data\\geofabrik\\europe\\great-britain\\england\\rutland\\" ... Done.

            >>> len(gfd.data_paths)
            2
            >>> for fp in gfd.data_paths: print(os.path.basename(fp))
            greater-london-latest.osm.pbf
            rutland-latest.osm.pbf

            >>> # Since `download_dir` was not specified when instantiating the class,
            >>> #   the data is now in the default download directory
            >>> os.path.relpath(gfd.download_dir)
            'osm_data\\geofabrik'
            >>> dwnld_dir = os.path.dirname(gfd.download_dir)

            >>> # Download shapefiles of West Midlands (to a given directory "tests\\osm_data")
            >>> region_name = 'west midlands'  # Case-insensitive
            >>> file_format = ".shp"
            >>> new_dwnld_dir = "tests\\osm_data"

            >>> gfd.download_osm_data(region_name, file_format, new_dwnld_dir, verbose=True)
            To download .shp.zip data of the following geographic (sub)region(s):
                West Midlands
            ? [No]|Yes: yes
            Downloading "west-midlands-latest-free.shp.zip"
                to "tests\\osm_data\\west-midlands\\" ... Done.
            >>> len(gfd.data_paths)
            3
            >>> os.path.relpath(gfd.data_paths[-1])
            'tests\\osm_data\\west-midlands\\west-midlands-latest-free.shp.zip'

            >>> # Now the `.download_dir` variable has changed to the given one
            >>> os.path.relpath(gfd.download_dir) == new_dwnld_dir
            True
            >>> # while the `.cdd()` remains the default one
            >>> os.path.relpath(gfd.cdd())
            'osm_data\\geofabrik'

            >>> # Delete the above downloaded directories
            >>> delete_dir([dwnld_dir, new_dwnld_dir], verbose=True)
            To delete the following directories:
                "osm_data\\" (Not empty)
                "tests\\osm_data\\" (Not empty)
            ? [No]|Yes: yes
            Deleting "osm_data\\" ... Done.
            Deleting "tests\\osm_data\\" ... Done.

        ***Example 2***::

            >>> # Create a new instance with a pre-specified download directory
            >>> gfd = GeofabrikDownloader(download_dir="tests\\osm_data")

            >>> os.path.relpath(gfd.download_dir)
            'tests\\osm_data'

            >>> # Download shapefiles of Great Britain (to the directory specified by instantiation)
            >>> # (Note that .shp.zip data is not available for "Great Britain" for free download.)
            >>> region_name = 'Great Britain'  # Case-insensitive
            >>> file_format = ".shp"

            >>> # By default, `deep_retry=False`
            >>> gfd.download_osm_data(region_name, osm_file_format=file_format, verbose=True)
            To download .shp.zip data of the following geographic (sub)region(s):
                Great Britain
            ? [No]|Yes: yes
            No .shp.zip data is found for "Great Britain".
            Try to download the data of its subregions instead
            ? [No]|Yes: yes
            Downloading "england-latest-free.shp.zip"
                to "tests\\osm_data\\europe\\great-britain\\great-britain-shp-zip\\" ... Done.
            Downloading "scotland-latest-free.shp.zip"
                to "tests\\osm_data\\europe\\great-britain\\great-britain-shp-zip\\" ... Done.
            Downloading "wales-latest-free.shp.zip"
                to "tests\\osm_data\\europe\\great-britain\\great-britain-shp-zip\\" ... Done.

            >>> len(gfd.data_paths)
            3

            >>> # Now set `deep_retry=True`
            >>> gfd.download_osm_data(region_name, file_format, verbose=True, deep_retry=True)
            To download .shp.zip data of the following geographic (sub)region(s):
                Great Britain
            ? [No]|Yes: yes
            No .shp.zip data is found for "Great Britain".
            Try to download the data of its subregions instead
            ? [No]|Yes: yes
            "scotland-latest-free.shp.zip" is already available at "tests\\osm_data\\europ...".
            "wales-latest-free.shp.zip" is already available at "tests\\osm_data\\europe\\...".
            Downloading "bedfordshire-latest-free.shp.zip"
                to "tests\\osm_data\\europe\\great-britain\\great-britain-shp-zip\\" ... Done.
            ...     ...
            Downloading "west-yorkshire-latest-free.shp.zip"
                to "tests\\osm_data\\europe\\great-britain\\great-britain-shp-zip\\" ... Done.
            Downloading "wiltshire-latest-free.shp.zip"
                to "tests\\osm_data\\europe\\great-britain\\great-britain-shp-zip\\" ... Done.
            Downloading "worcestershire-latest-free.shp.zip"
                to "tests\\osm_data\\europe\\great-britain\\great-britain-shp-zip\\" ... Done.

            >>> # Check the file paths
            >>> len(gfd.data_paths)
            50
            >>> # Check the current default `download_dir`
            >>> os.path.relpath(gfd.download_dir)
            'tests\\osm_data'
            >>> os.path.relpath(os.path.commonpath(gfd.data_paths))
            'tests\\osm_data\\europe\\great-britain\\great-britain-shp-zip'

            >>> # Delete all the downloaded files
            >>> delete_dir(gfd.download_dir, verbose=True)
            To delete the directory "tests\\osm_data\\" (Not empty)
            ? [No]|Yes: yes
            Deleting "tests\\osm_data\\" ... Done.
        """

        subrgn_names_, file_fmt_, cfm_req, action_, dwnld_list_, existing_file_pathnames = \
            self.file_exists_and_more(
                subregion_names=subregion_names, osm_file_format=osm_file_format,
                data_dir=download_dir, update=update, confirmation_required=confirmation_required,
                verbose=verbose)

        cfm_msg = "To {} {} data of the following geographic (sub)region(s):" \
                  "\n\t{}\n?".format(action_, file_fmt_, "\n\t".join(dwnld_list_))

        if confirmed(cfm_msg, confirmation_required=cfm_req and confirmation_required):

            download_paths = []

            for subrgn_name_ in subrgn_names_:
                # subregion_name_, download_url = self.get_subregion_download_url(
                #     subregion_name=subrgn_name_, osm_file_format=file_fmt_)
                subregion_name_, _, download_url, file_pathname = self.get_valid_download_info(
                    subregion_name=subrgn_name_, osm_file_format=file_fmt_,
                    download_dir=download_dir)

                if download_url is None:
                    if verbose:
                        print(f"No {file_fmt_} data is found for \"{subregion_name_}\".")

                    cfm_msg_ = "Try to download the data of its subregions instead\n?"
                    if confirmed(prompt=cfm_msg_, confirmation_required=confirmation_required):
                        sub_subregions = self.get_subregions(subregion_name_, deep=deep_retry)

                        if sub_subregions == [subregion_name_]:
                            print(f"{file_fmt_} data is unavailable for {subregion_name_}.")

                        else:
                            dwnld_dir_ = self.specify_sub_download_dir(
                                subregion_name=subregion_name_, osm_file_format=file_fmt_,
                                download_dir=download_dir)

                            download_paths_ = self.download_osm_data(
                                subregion_names=sub_subregions, osm_file_format=file_fmt_,
                                download_dir=dwnld_dir_, update=update, confirmation_required=False,
                                verify_download_dir=False, verbose=verbose,
                                ret_download_path=ret_download_path)

                            if isinstance(download_paths_, list):
                                download_paths += download_paths_

                else:
                    if not os.path.isfile(file_pathname) or update:
                        self._download_osm_data(
                            download_url=download_url, file_pathname=file_pathname, verbose=verbose,
                            verify_download_dir=False, **kwargs)

                    if os.path.isfile(file_pathname):
                        download_paths.append(file_pathname)

                if isinstance(interval, (int, float)):
                    time.sleep(interval)

            self.verify_download_dir(
                download_dir=download_dir, verify_download_dir=verify_download_dir)

        else:
            print("Cancelled.")

            download_paths = existing_file_pathnames

        self.data_paths = list(collections.OrderedDict.fromkeys(self.data_paths + download_paths))

        if ret_download_path:
            return download_paths

    def download_subregion_data(self, subregion_names, osm_file_format, download_dir=None,
                                deep=False, ret_download_path=False, **kwargs):
        """
        Download OSM data (in a specific file format) of all subregions (if available) for
        one (or multiple) geographic (sub)region(s).

        If no subregion data is available for the region(s) specified by ``subregion_names``,
        then the data of ``subregion_names`` would be downloaded only.

        :param subregion_names: name of a geographic (sub)region
            (or names of multiple geographic (sub)regions)
            available on Geofabrik free download server
        :type subregion_names: str | list
        :param osm_file_format: file format/extension of the OSM data
            available on the download server
        :type osm_file_format: str
        :param download_dir: directory for saving the downloaded file(s), defaults to ``None``;
            when ``download_dir=None``, it refers to the method
            :meth:`~pydriosm.downloader.GeofabrikDownloader.cdd`
        :type download_dir: str | None
        :param deep: whether to try to search for subregions of subregion(s), defaults to ``False``
        :type deep: bool
        :param ret_download_path: whether to return the path(s) to the downloaded file(s),
            defaults to ``False``
        :type ret_download_path: bool
        :param kwargs: optional parameters of `pydriosm.GeofabrikDownloader.download_osm_data()`_
        :return: the path(s) to the downloaded file(s) when ``ret_download_path=True``
        :rtype: list | str

        .. _`pydriosm.GeofabrikDownloader.download_osm_data()`:
            https://pydriosm.readthedocs.io/en/latest/
            _generated/pydriosm.downloader.GeofabrikDownloader.download_osm_data.html

        **Examples**::

            >>> from pydriosm.downloader import GeofabrikDownloader
            >>> from pyhelpers.dirs import cd, delete_dir
            >>> import os

            >>> gfd = GeofabrikDownloader()

            >>> subrgn_names = ['rutland', 'west yorkshire']
            >>> file_format = ".pbf"
            >>> dwnld_dir = "tests\\osm_data"

            >>> gfd.download_subregion_data(subrgn_names, file_format, dwnld_dir, verbose=True)
            To download .osm.pbf data of the following geographic (sub)region(s):
                Rutland
                West Yorkshire
            ? [No]|Yes: yes
            Downloading "rutland-latest.osm.pbf"
                to "tests\\osm_data\\rutland\\" ... Done.
            Downloading "west-yorkshire-latest.osm.pbf"
                to "tests\\osm_data\\west-yorkshire\\" ... Done.

            >>> len(gfd.data_paths)
            2
            >>> for fp in gfd.data_paths: print(os.path.relpath(fp))
            tests\\osm_data\\rutland\\rutland-latest.osm.pbf
            tests\\osm_data\\west-yorkshire\\west-yorkshire-latest.osm.pbf

            >>> # Delete "tests\\osm_data\\rutland-latest.osm.pbf"
            >>> rutland_dir = os.path.dirname(gfd.data_paths[0])
            >>> delete_dir(rutland_dir, confirmation_required=False, verbose=True)
            Deleting "tests\\osm_data\\rutland\\" ... Done.

            >>> # Try to download data given another list which also includes 'West Yorkshire'
            >>> subrgn_names = ['west midlands', 'west yorkshire']

            >>> # Set `ret_download_path=True`
            >>> dwnld_file_pathnames = gfd.download_subregion_data(
            ...     subrgn_names, file_format, dwnld_dir, verbose=True, ret_download_path=True)
            "west-midlands-latest.osm.pbf" is already available
                at "tests\\osm_data\\west-midlands\\".
            To download .osm.pbf data of the following geographic (sub)region(s):
                West Midlands
            ? [No]|Yes: yes
            Downloading "west-midlands-latest.osm.pbf"
                to "tests\\osm_data\\west-midlands\\" ... Done.

            >>> len(gfd.data_paths)  # The pathname of the newly downloaded file is added
            3
            >>> len(dwnld_file_pathnames)
            2
            >>> for fp in dwnld_file_pathnames: print(os.path.relpath(fp))
            tests\\osm_data\\west-midlands\\west-midlands-latest.osm.pbf
            tests\\osm_data\\west-yorkshire\\west-yorkshire-latest.osm.pbf

            >>> # Update (or re-download) the existing data file by setting `update=True`
            >>> gfd.download_subregion_data(
            ...     subrgn_names, file_format, download_dir=dwnld_dir, update=True, verbose=True)
            "west-midlands-latest.osm.pbf" is already available
                at "tests\\osm_data\\west-midlands\\".
            "west-yorkshire-latest.osm.pbf" is already available
                at "tests\\osm_data\\west-yorkshire\\".
            To update the .osm.pbf data of the following geographic (sub)region(s):
                West Midlands
                West Yorkshire
            ? [No]|Yes: yes
            Updating "west-midlands-latest.osm.pbf"
                at "tests\\osm_data\\west-midlands\\" ... Done.
            Updating "west-yorkshire-latest.osm.pbf"
                at "tests\\osm_data\\west-yorkshire\\" ... Done.

            >>> # To download the PBF data of all available subregions of England
            >>> subrgn_name = 'England'

            >>> dwnld_file_pathnames = gfd.download_subregion_data(
            ...     subrgn_name, file_format, download_dir=dwnld_dir, update=True, verbose=True,
            ...     ret_download_path=True)
            "west-midlands-latest.osm.pbf" is already available
                at "tests\\osm_data\\west-midlands\\".
            "west-yorkshire-latest.osm.pbf" is already available
                at "tests\\osm_data\\west-yorkshire\\".
            To download/update the .osm.pbf data of the following geographic (sub)region(s):
                Bedfordshire
                Berkshire
                Bristol
                ...
                West Midlands
                ...
                West Yorkshire
                Wiltshire
                Worcestershire
            ? [No]|Yes: yes
            Downloading "bedfordshire-latest.osm.pbf"
                to "tests\\osm_data\\bedfordshire\\" ... Done.
            Downloading "berkshire-latest.osm.pbf"
                to "tests\\osm_data\\berkshire\\" ... Done.
            Downloading "bristol-latest.osm.pbf"
                to "tests\\osm_data\\bristol\\" ... Done.
            ...
                ...
            Updating "west-midlands-latest.osm.pbf"
                at "tests\\osm_data\\west-midlands\\" ... Done.
            ...
                ...
            Updating "west-yorkshire-latest.osm.pbf"
                at "tests\\osm_data\\west-yorkshire\\" ... Done.
            Downloading "wiltshire-latest.osm.pbf"
                to "tests\\osm_data\\wiltshire\\" ... Done.
            Downloading "worcestershire-latest.osm.pbf"
                to "tests\\osm_data\\worcestershire\\" ... Done.

            >>> len(dwnld_file_pathnames)
            47
            >>> os.path.commonpath(dwnld_file_pathnames) == gfd.download_dir
            True

            >>> # Delete the download directory and the downloaded files
            >>> delete_dir(gfd.download_dir, verbose=True)
            To delete the directory "tests\\osm_data\\" (Not empty)
            ? [No]|Yes: yes
            Deleting "tests\\osm_data\\" ... Done.
        """

        if isinstance(subregion_names, str):
            sr_names_ = [subregion_names]
        else:
            sr_names_ = subregion_names.copy()
        sr_names_ = [self.validate_subregion_name(x) for x in sr_names_]
        subregion_names_ = self.get_subregions(*sr_names_, deep=deep)

        osm_file_format_ = self.validate_file_format(osm_file_format)

        kwargs.update({'download_dir': download_dir, 'ret_download_path': True})
        download_paths = self.download_osm_data(
            subregion_names=subregion_names_, osm_file_format=osm_file_format_, **kwargs)

        if ret_download_path:
            if isinstance(download_paths, list) and len(download_paths) == 1:
                download_paths = download_paths[0]

            return download_paths
