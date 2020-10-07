"""
Download `Geofabrik <https://download.geofabrik.de/>`_ and
`BBBike <https://download.bbbike.org/osm/>`_ OpenStreetMap (OSM) data extracts.
"""

import copy
import os
import re
import time
import urllib.error
import urllib.parse

import bs4
import more_itertools
import numpy as np
import pandas as pd
import requests
from pyhelpers.dir import cd, validate_input_data_dir
from pyhelpers.ops import confirmed, download_file_from_url, fake_requests_headers, \
    update_nested_dict
from pyhelpers.store import load_pickle, save_pickle
from pyhelpers.text import find_similar_str

from .utils import bbbike_homepage, cd_dat, cd_dat_bbbike, cd_dat_geofabrik, \
    geofabrik_homepage


class GeofabrikDownloader:
    """
    A class representation of a tool for downloading
    `Geofabrik <https://download.geofabrik.de/>`_ OSM data extracts.

    **Example**::

        >>> from pydriosm.downloader import GeofabrikDownloader

        >>> geofabrik_downloader = GeofabrikDownloader()

        >>> print(geofabrik_downloader.Name)
        Geofabrik OpenStreetMap data extracts
    """

    def __init__(self):
        """
        Constructor method.
        """
        self.Name = 'Geofabrik OpenStreetMap data extracts'
        self.URL = geofabrik_homepage()
        self.DownloadIndexURL = urllib.parse.urljoin(self.URL, 'index-v1.json')
        self.ValidFileFormats = [".osm.pbf", ".shp.zip", ".osm.bz2"]
        self.DownloadIndexName = 'Geofabrik index of all downloads'
        self.ContinentSubregionTableName = 'Geofabrik continent subregions'
        self.RegionSubregionTier = 'Geofabrik region-subregion tier'
        self.DownloadsCatalogue = 'Geofabrik downloads catalogue'
        self.SubregionNameList = 'Geofabrik subregion name list'

    @staticmethod
    def get_raw_directory_index(url, verbose=False):
        """
        Get a raw directory index (including logs of older files and their and download URLs).

        :param url: a URL to the web resource
        :type url: str
        :param verbose: whether to print relevant information in console as the function runs,
            defaults to ``False``
        :type verbose: bool or int
        :return: a table of raw directory index
        :rtype: pandas.DataFrame or None

        **Examples**::

            >>> from pydriosm.downloader import GeofabrikDownloader

            >>> geofabrik_downloader = GeofabrikDownloader()

            >>> ex_url = 'https://download.geofabrik.de/europe/great-britain.html'

            >>> raw_dir_idx = geofabrik_downloader.get_raw_directory_index(ex_url)

            >>> print(raw_dir_idx.head())
                                           File  ...                            FileURL
            0             great-britain-updates  ...  https://download.geofabrik.de/...
            1  great-britain-latest.osm.pbf.md5  ...  https://download.geofabrik.de/...
            2  great-britain-200914.osm.pbf.md5  ...  https://download.geofabrik.de/...
            3                 great-britain.kml  ...  https://download.geofabrik.de/...
            4      great-britain-latest.osm.pbf  ...  https://download.geofabrik.de/...
            [5 rows x 4 columns]

            >>> ex_url = 'http://download.geofabrik.de/'

            >>> raw_dir_idx = geofabrik_downloader.get_raw_directory_index(ex_url,
            ...                                                            verbose=True)
            The web page does not have a raw directory index.
        """

        try:
            raw_directory_index = pd.read_html(url, match='file', header=0,
                                               parse_dates=['date'])
            raw_directory_index = pd.concat(raw_directory_index, axis=0, ignore_index=True)
            raw_directory_index.columns = [c.title() for c in raw_directory_index.columns]

            # Clean the DataFrame
            import humanfriendly
            raw_directory_index.Size = \
                raw_directory_index.Size.apply(humanfriendly.format_size)
            raw_directory_index.sort_values('Date', ascending=False, inplace=True)
            raw_directory_index.index = range(len(raw_directory_index))

            raw_directory_index['FileURL'] = raw_directory_index.File.map(
                lambda x: urllib.parse.urljoin(url, x))

        except (urllib.error.HTTPError, TypeError, ValueError):
            if len(urllib.parse.urlparse(url).path) <= 1 and verbose:
                print("The web page does not have a raw directory index.")
            raw_directory_index = None

        return raw_directory_index

    def get_subregion_table(self, url, verbose=False):
        """
        Get a table that contains download information for all geographic regions presented
        on a given web page.

        :param url: URL to the web resource
        :type url: str
        :param verbose: whether to print relevant information in console as the function runs,
            defaults to ``False``
        :type verbose: bool or int
        :return: a table of all available subregions' URLs
        :rtype: pandas.DataFrame or None

        **Example**::

            >>> from pydriosm.downloader import GeofabrikDownloader

            >>> geofabrik_downloader = GeofabrikDownloader()

            >>> ex_url = 'https://download.geofabrik.de/europe/great-britain.html'

            >>> subregion_tbl = geofabrik_downloader.get_subregion_table(ex_url)

            >>> print(subregion_tbl.head())
              Subregion  ...                                           .osm.bz2
            0   England  ...  https://download.geofabrik.de/europe/great-bri...
            1  Scotland  ...  https://download.geofabrik.de/europe/great-bri...
            2     Wales  ...  https://download.geofabrik.de/europe/great-bri...
            [3 rows x 6 columns]
        """

        try:
            subregion_table = pd.read_html(
                url, match=re.compile(r'(Special )?Sub[ \-]Regions?'), encoding='UTF-8')
            subregion_table = pd.concat(subregion_table, axis=0, ignore_index=True)

            # Specify column names
            file_formats = self.ValidFileFormats
            column_names = ['Subregion'] + file_formats
            column_names.insert(2, '.osm.pbf.Size')

            # Add column/names
            if len(subregion_table.columns) == 4:
                subregion_table.insert(2, '.osm.pbf.Size', np.nan)
            subregion_table.columns = column_names

            subregion_table.replace(
                {'.osm.pbf.Size': {re.compile('[()]'): '', re.compile('\xa0'): ' '}},
                inplace=True)

            # Get the URLs
            source = requests.get(url, headers=fake_requests_headers())
            soup = bs4.BeautifulSoup(source.content, 'lxml')
            source.close()

            for file_type in file_formats:
                text = '[{}]'.format(file_type)
                urls = [urllib.parse.urljoin(url, link['href']) for link in
                        soup.find_all(name='a', href=True, text=text)]
                subregion_table.loc[subregion_table[file_type].notnull(), file_type] = urls

            try:
                subregion_urls = [
                    urllib.parse.urljoin(url, soup.find('a', text=text).get('href'))
                    for text in subregion_table.Subregion]
            except (AttributeError, TypeError):
                subregion_urls = [kml['onmouseover']
                                  for kml in soup.find_all('tr', onmouseover=True)]
                subregion_urls = [s[s.find('(') + 1:s.find(')')][1:-1].replace('kml', 'html')
                                  for s in subregion_urls]
                subregion_urls = [urllib.parse.urljoin(url, sub_url)
                                  for sub_url in subregion_urls]
            subregion_table['SubregionURL'] = subregion_urls

            column_names = list(subregion_table.columns)
            column_names.insert(1, column_names.pop(len(column_names) - 1))
            subregion_table = subregion_table[column_names]

            subregion_table['.osm.pbf.Size'] = \
                subregion_table['.osm.pbf.Size'].str.replace('(', '').str.replace(')', '')

            subregion_table = subregion_table.where(pd.notnull(subregion_table), None)

        except (ValueError, TypeError, ConnectionRefusedError, ConnectionError):
            # No more data available for subregions within the region
            if verbose:
                print("Checked out \"{}\".".format(url.split('/')[-1].split('.')[0].title()))
            subregion_table = None

        return subregion_table

    def get_index_of_all_downloads(self, update=False, confirmation_required=True,
                                   verbose=False):
        """
        Get the formal index of all downloads.

        :param update: whether to check on update and proceed to update the package data,
            defaults to ``False``
        :type update: bool
        :param confirmation_required: whether to prompt a message for confirmation to proceed,
            defaults to ``True``
        :type confirmation_required: bool
        :param verbose: whether to print relevant information in console as the function runs,
            defaults to ``False``
        :type verbose: bool or int
        :return: the formal index of all downloads
        :rtype: pandas.DataFrame or None

        **Example**::

            >>> from pydriosm.downloader import GeofabrikDownloader

            >>> geofabrik_downloader = GeofabrikDownloader()

            >>> download_idx = geofabrik_downloader.get_index_of_all_downloads()

            >>> print(download_idx.head())
                        id  ...                                            updates
            0  afghanistan  ...  https://download.geofabrik.de/asia/afghanistan...
            1       africa  ...       https://download.geofabrik.de/africa-updates
            2      albania  ...  https://download.geofabrik.de/europe/albania-u...
            3      alberta  ...  https://download.geofabrik.de/north-america/ca...
            4      algeria  ...  https://download.geofabrik.de/africa/algeria-u...
            [5 rows x 12 columns]
        """

        path_to_download_index = cd_dat(self.DownloadIndexName.replace(" ", "-") + ".pickle")

        if os.path.isfile(path_to_download_index) and not update:
            download_index = load_pickle(path_to_download_index)

        else:
            if confirmed("To get {}?".format(self.DownloadIndexName),
                         confirmation_required=confirmation_required):

                if verbose == 2:
                    print("Collecting {}".format(self.DownloadIndexName), end=" ... ")
                try:
                    import geopandas as gpd
                    download_index_ = gpd.read_file(self.DownloadIndexURL)

                    # Note that '<br />' exists in all the names of the subregions of Poland
                    download_index_.name = download_index_.name.str.replace('<br />', ' ')

                    urls = download_index_.urls.map(
                        lambda x: pd.DataFrame.from_dict(x, 'index').T)
                    urls_ = pd.concat(urls.values, ignore_index=True)
                    download_index = pd.concat([download_index_, urls_], axis=1)

                    print("Done. ") if verbose == 2 else ""

                    save_pickle(download_index, path_to_download_index, verbose=verbose)

                except Exception as e:
                    print("Failed. {}.".format(e))
                    download_index = None

            else:
                download_index = None
                if verbose:
                    print("No data of {} is available.".format(self.DownloadIndexName))

        return download_index

    def get_continents_subregion_tables(self, update=False, confirmation_required=True,
                                        verbose=False):
        """
        Get download information for each continent.

        :param update: whether to check on update and proceed to update the package data,
            defaults to ``False``
        :type update: bool
        :param confirmation_required: whether to prompt a message for confirmation to proceed,
            defaults to ``True``
        :type confirmation_required: bool
        :param verbose: whether to print relevant information in console as the function runs,
            defaults to ``False``
        :type verbose: bool or int
        :return: subregion information for each continent
        :rtype: dict or None

        **Example**::

            >>> from pydriosm.downloader import GeofabrikDownloader

            >>> geofabrik_downloader = GeofabrikDownloader()

            >>> subregion_tbls = geofabrik_downloader.get_continents_subregion_tables()

            >>> print(list(subregion_tbls.keys()))
            ['Africa',
             'Antarctica',
             'Asia',
             'Australia and Oceania',
             'Central America',
             'Europe',
             'North America',
             'South America']
        """

        path_to_pickle = \
            cd_dat(self.ContinentSubregionTableName.replace(" ", "-") + ".pickle")

        if os.path.isfile(path_to_pickle) and not update:
            subregion_tables = load_pickle(path_to_pickle)

        else:
            if confirmed("To collect information of {}?".format(
                    self.ContinentSubregionTableName),
                    confirmation_required=confirmation_required):

                if verbose == 2:
                    print("Collecting a table of {}".format(self.ContinentSubregionTableName),
                          end=" ... ")

                try:
                    # Scan the homepage to collect information of regions for each continent
                    source = requests.get(self.URL, headers=fake_requests_headers())
                    soup = bs4.BeautifulSoup(source.text, 'lxml').find_all(
                        'td', {'class': 'subregion'})
                    source.close()
                    continent_names = [td.a.text for td in soup]
                    continent_links = [urllib.parse.urljoin(self.URL, td.a['href'])
                                       for td in soup]
                    subregion_tables = dict(
                        zip(continent_names,
                            [self.get_subregion_table(url, verbose)
                             for url in continent_links]))

                    print("Done. ") if verbose == 2 else ""

                    save_pickle(subregion_tables, path_to_pickle, verbose=verbose)

                except Exception as e:
                    print("Failed. {}.".format(e))
                    subregion_tables = None

            else:
                subregion_tables = None
                if verbose:
                    print(f"No data of {self.ContinentSubregionTableName} is available.")

        return subregion_tables

    def get_region_subregion_tier(self, update=False, confirmation_required=True,
                                  verbose=False):
        """
        Get a catalogue of region-subregion tier
        (including all geographic regions to which data of subregions is not available).

        :param update: whether to check on update and proceed to update the package data,
            defaults to ``False``
        :type update: bool
        :param confirmation_required: whether to prompt a message for confirmation to proceed,
            defaults to ``True``
        :type confirmation_required: bool
        :param verbose: whether to print relevant information in console as the function runs,
            defaults to ``False``
        :type verbose: bool or int
        :return: region-subregion tier (in ``dict`` type) and all that have no subregions
            (in ``list`` type)
        :rtype: tuple

        .. _`dict`: https://docs.python.org/3/library/stdtypes.html#dict
        .. _`list`: https://docs.python.org/3/library/stdtypes.html#list

        **Example**::

            >>> from pydriosm.downloader import GeofabrikDownloader

            >>> geofabrik_downloader = GeofabrikDownloader()

            >>> rs_tier, ns_list = geofabrik_downloader.get_region_subregion_tier()

            >>> print(list(rs_tier.keys()))
            ['Africa',
             'Antarctica',
             'Asia',
             'Australia and Oceania',
             'Central America',
             'Europe',
             'North America',
             'South America']

            >>> print(ns_list[0:5])
            ['Antarctica', 'Algeria', 'Angola', 'Benin', 'Botswana']
        """

        path_to_file = cd_dat(self.RegionSubregionTier.replace(" ", "-") + ".pickle")

        if os.path.isfile(path_to_file) and not update:
            region_subregion_tier, non_subregions = load_pickle(path_to_file, verbose=verbose)

        else:

            def compile_region_subregion_tier(sub_reg_tbls):
                """
                Find out the all regions and their subregions.

                :param sub_reg_tbls: obtained from get_continents_subregion_tables()
                :type sub_reg_tbls: pandas.DataFrame
                :return: a dictionary of region-subregion, and
                    a list of (sub)regions without subregions
                :rtype: dict

                **Test**::

                    sub_reg_tbls = subregion_tables.copy()
                """

                having_subregions = sub_reg_tbls.copy()
                region_subregion_tiers = having_subregions.copy()

                non_subregions_list = []
                for k, v in sub_reg_tbls.items():
                    if v is not None and isinstance(v, pd.DataFrame):
                        region_subregion_tiers = \
                            update_nested_dict(sub_reg_tbls, {k: set(v.Subregion)})
                    else:
                        non_subregions_list.append(k)

                for x in non_subregions_list:
                    having_subregions.pop(x)

                having_subregions_temp = copy.deepcopy(having_subregions)

                while having_subregions_temp:

                    for region_name, subregion_table in having_subregions.items():
                        subregion_names = subregion_table.Subregion
                        subregion_links = subregion_table.SubregionURL
                        sub_subregion_tables = dict(
                            zip(subregion_names,
                                [self.get_subregion_table(link) for link in subregion_links]))

                        subregion_index, without_subregion_ = \
                            compile_region_subregion_tier(sub_subregion_tables)
                        non_subregions_list += without_subregion_

                        region_subregion_tiers.update({region_name: subregion_index})

                        having_subregions_temp.pop(region_name)

                # Russian Federation in both pages of Asia and Europe,
                # so there are duplicates in non_subregions_list
                non_subregions_list = \
                    list(more_itertools.unique_everseen(non_subregions_list))
                return region_subregion_tiers, non_subregions_list

            if confirmed("To compile {}? (Note this may take up to a few minutes.)".format(
                    self.RegionSubregionTier), confirmation_required=confirmation_required):

                if verbose == 2:
                    print("Compiling {} ... ".format(self.RegionSubregionTier), end="")

                # Scan the downloading pages to collect a catalogue of region-subregion tier
                try:
                    subregion_tables = self.get_continents_subregion_tables(update=update)
                    region_subregion_tier, non_subregions = \
                        compile_region_subregion_tier(subregion_tables)

                    print("Done. ") if verbose == 2 else ""

                    save_pickle((region_subregion_tier, non_subregions), path_to_file,
                                verbose=verbose)

                except Exception as e:
                    print("Failed. {}.".format(e))
                    region_subregion_tier, non_subregions = None, None

            else:
                region_subregion_tier, non_subregions = None, None
                if verbose:
                    print("No data of {} is available.".format(self.RegionSubregionTier))

        return region_subregion_tier, non_subregions

    def get_download_catalogue(self, update=False, confirmation_required=True,
                               verbose=False):
        """
        Get a catalogue of download information. Similar to
        :py:meth:`.get_index_of_all_downloads()
        <pydriosm.downloader.GeofabrikDownloader.get_index_of_all_downloads>`.

        :param update: whether to check on update and proceed to update the package data,
            defaults to ``False``
        :type update: bool
        :param confirmation_required: whether to prompt a message for confirmation to proceed,
            defaults to ``True``
        :type confirmation_required: bool
        :param verbose: whether to print relevant information in console as the function runs,
            defaults to ``False``
        :type verbose: bool or int
        :return: a catalogues for subregion downloads
        :rtype: pandas.DataFrame or None

        **Example**::

            >>> from pydriosm.downloader import GeofabrikDownloader

            >>> geofabrik_downloader = GeofabrikDownloader()

            >>> downloads_catalogue = geofabrik_downloader.get_download_catalogue()

            >>> print(downloads_catalogue.head())
                  Subregion  ...                                           .osm.bz2
            0       Algeria  ...  http://download.geofabrik.de/africa/algeria-la...
            1        Angola  ...  http://download.geofabrik.de/africa/angola-lat...
            2         Benin  ...  http://download.geofabrik.de/africa/benin-late...
            3      Botswana  ...  http://download.geofabrik.de/africa/botswana-l...
            4  Burkina Faso  ...  http://download.geofabrik.de/africa/burkina-fa...
            [5 rows x 6 columns]
        """

        path_to_downloads_catalogue = cd_dat(
            self.DownloadsCatalogue.replace(" ", "-") + ".pickle")

        if os.path.isfile(path_to_downloads_catalogue) and not update:
            subregion_downloads_catalogue = load_pickle(path_to_downloads_catalogue)

        else:
            if confirmed("To collect {}? (Note that it may take a few minutes.)".format(
                    self.DownloadsCatalogue), confirmation_required=confirmation_required):

                if verbose == 2:
                    print("Collecting {}".format(self.DownloadsCatalogue), end=" ... ")
                try:
                    source = requests.get(self.URL, headers=fake_requests_headers())
                    soup = bs4.BeautifulSoup(source.text, 'lxml')
                    source.close()
                    # avail_subregions = \
                    #   [td.a.text for td in soup.find_all('td', {'class': 'subregion'})]
                    subregion_href = soup.find_all('td', {'class': 'subregion'})
                    avail_subregion_urls = (urllib.parse.urljoin(self.URL, td.a['href'])
                                            for td in subregion_href)
                    avail_subregion_url_tables_0 = (self.get_subregion_table(sub_url, verbose)
                                                    for sub_url in avail_subregion_urls)
                    avail_subregion_url_tables = [tbl for tbl in avail_subregion_url_tables_0
                                                  if tbl is not None]

                    subregion_url_tables = list(avail_subregion_url_tables)

                    while subregion_url_tables:

                        subregion_url_tables_ = []

                        for subregion_url_table in subregion_url_tables:
                            # subregions = list(subregion_url_table.Subregion)
                            subregion_urls = list(subregion_url_table.SubregionURL)
                            subregion_url_tables_0 = [
                                self.get_subregion_table(sr_url, verbose)
                                for sr_url in subregion_urls]
                            subregion_url_tables_ += [tbl for tbl in subregion_url_tables_0
                                                      if tbl is not None]

                            # (Note that 'Russian Federation' data is available in both
                            #   'Asia' and 'Europe')
                            # avail_subregions += subregions
                            # avail_subregion_urls += subregion_urls
                            avail_subregion_url_tables += subregion_url_tables_

                        subregion_url_tables = list(subregion_url_tables_)

                    # All available URLs for downloading
                    home_subregion_url_table = self.get_subregion_table(self.URL)
                    avail_subregion_url_tables.append(home_subregion_url_table)
                    subregion_downloads_catalogue = pd.concat(avail_subregion_url_tables,
                                                              ignore_index=True)
                    subregion_downloads_catalogue.drop_duplicates(inplace=True)

                    duplicated = subregion_downloads_catalogue[
                        subregion_downloads_catalogue.Subregion.duplicated(keep=False)]
                    if not duplicated.empty:
                        import humanfriendly
                        for i in range(0, 2, len(duplicated)):
                            temp = duplicated.iloc[i:i + 2]
                            size = temp['.osm.pbf.Size'].map(
                                lambda x: humanfriendly.parse_size(
                                    x.strip('(').strip(')').replace('\xa0', ' ')))
                            idx = size[size == size.min()].index
                            subregion_downloads_catalogue.drop(idx, inplace=True)
                        subregion_downloads_catalogue.index = \
                            range(len(subregion_downloads_catalogue))

                    # Save subregion_index_downloads to local disk
                    save_pickle(subregion_downloads_catalogue, path_to_downloads_catalogue,
                                verbose=verbose)

                except Exception as e:
                    print("Failed. {}.".format(e))
                    subregion_downloads_catalogue = None

            else:
                subregion_downloads_catalogue = None
                if verbose:
                    print("No data of {} is available.".format(self.DownloadsCatalogue))

        return subregion_downloads_catalogue

    def get_subregion_name_list(self, update=False, confirmation_required=True,
                                verbose=False):
        """
        Get a list of names of all geographic regions available on the free download server.

        :param update: whether to check on update and proceed to update the package data,
            defaults to ``False``
        :type update: bool
        :param confirmation_required: whether to prompt a message for confirmation to proceed,
            defaults to ``True``
        :type confirmation_required: bool
        :param verbose: whether to print relevant information in console as the function runs,
            defaults to ``False``
        :type verbose: bool or int
        :return: names of geographic regions available on the free download server
        :rtype: list

        **Example**::

            >>> from pydriosm.downloader import GeofabrikDownloader

            >>> geofabrik_downloader = GeofabrikDownloader()

            >>> sr_name_list = geofabrik_downloader.get_subregion_name_list()

            >>> print(sr_name_list[:5])
            ['Algeria', 'Angola', 'Benin', 'Botswana', 'Burkina Faso']
        """

        path_to_name_list = cd_dat(self.SubregionNameList.replace(" ", "-") + ".pickle")

        if os.path.isfile(path_to_name_list) and not update:
            subregion_name_list = load_pickle(path_to_name_list)

        else:
            if confirmed("To get {}?".format(self.SubregionNameList),
                         confirmation_required=confirmation_required):

                downloads_catalogue = self.get_download_catalogue(
                    update=update, confirmation_required=False)

                subregion_name_list = downloads_catalogue.Subregion.to_list()

                save_pickle(subregion_name_list, path_to_name_list, verbose=verbose)

            else:
                subregion_name_list = []
                if verbose:
                    print("No data of {} is available.".format(self.SubregionNameList))

        return subregion_name_list

    def validate_input_subregion_name(self, subregion_name):
        """
        Validate input subregion name
        (by matching it to a name of an available geographic region).

        :param subregion_name: name of a geographic region (case-insensitive)
        :type subregion_name: str
        :return: valid subregion name that matches, or is the most similar to,
            the input ``subregion_name``
        :rtype: str

        **Examples**::

            >>> from pydriosm.downloader import GeofabrikDownloader

            >>> geofabrik_downloader = GeofabrikDownloader()

            >>> sr_name = 'london'
            >>> sr_name_ = geofabrik_downloader.validate_input_subregion_name(sr_name)

            >>> print(sr_name_)
            Greater London

            >>> sr_name = 'https://download.geofabrik.de/europe/great-britain.html'
            >>> sr_name_ = geofabrik_downloader.validate_input_subregion_name(sr_name)

            >>> print(sr_name_)
            Great Britain
        """

        assert isinstance(subregion_name, str)
        # Get a list of available
        subregion_names = self.get_subregion_name_list()

        if os.path.isdir(os.path.dirname(subregion_name)) or \
                urllib.parse.urlparse(subregion_name).path:
            subregion_name_ = find_similar_str(os.path.basename(subregion_name),
                                               subregion_names)

        else:
            subregion_name_ = find_similar_str(subregion_name, subregion_names)

        if not subregion_name_:
            raise ValueError(
                "The input subregion name is not identified.\n"
                "Check if the required subregion exists in the catalogue and retry.")

        return subregion_name_

    def validate_input_file_format(self, osm_file_format):
        """
        Validate input OSM file format (by matching it to an available filename extension).

        :param osm_file_format: file format of any OSM data extract
        :type osm_file_format: str
        :return: formal file format
        :rtype: str

        **Examples**::

            >>> from pydriosm.downloader import GeofabrikDownloader

            >>> geofabrik_downloader = GeofabrikDownloader()

            >>> file_format = ".pbf"
            >>> file_format_ = geofabrik_downloader.validate_input_file_format(file_format)

            >>> print(file_format_)
            .osm.pbf

            >>> file_format = ".shp"
            >>> file_format_ = geofabrik_downloader.validate_input_file_format(file_format)

            >>> print(file_format_)
            .shp.zip
        """

        osm_file_format_ = find_similar_str(osm_file_format, self.ValidFileFormats)

        assert osm_file_format_ in self.ValidFileFormats, \
            "The input file format must be one from {}.".format(self.ValidFileFormats)

        return osm_file_format_

    def get_subregion_download_url(self, subregion_name, osm_file_format, update=False,
                                   verbose=False):
        """
        Get download URL of a subregion.

        :param subregion_name: name of a geographic region (case-insensitive)
        :type subregion_name: str
        :param osm_file_format: OSM file format available on the free download server;
            valid values include ``".osm.pbf"``, ``".shp.zip"`` and ``".osm.bz2"``
        :type osm_file_format: str
        :param update: whether to check on update and proceed to update the package data,
            defaults to ``False``
        :type update: bool
        :param verbose: whether to print relevant information in console as the function runs,
            defaults to ``False``
        :type verbose: bool or int
        :return: name and URL of the subregion
        :rtype: tuple

        **Examples**::

            >>> from pydriosm.downloader import GeofabrikDownloader

            >>> geofabrik_downloader = GeofabrikDownloader()

            >>> region_name  = 'london'
            >>> file_format = '.pbf'

            >>> formal_name, download_link = geofabrik_downloader.get_subregion_download_url(
            ...     region_name, file_format)

            >>> print(formal_name)
            Greater London
            >>> print(download_link)
            http://download.geofabrik.de/.../greater-london-latest.osm.pbf

            >>> region_name  = 'Great Britain'
            >>> file_format = '.shp'

            >>> formal_name, download_link = geofabrik_downloader.get_subregion_download_url(
            ...     region_name, file_format)

            >>> print(formal_name)
            Greater London
            >>> print(download_link)
            None
        """

        # Get an index of download URLs
        subregion_downloads_index = self.get_download_catalogue(
            update=update, verbose=verbose)
        subregion_downloads_index.set_index('Subregion', inplace=True)

        subregion_name_ = self.validate_input_subregion_name(subregion_name)
        osm_file_format_ = self.validate_input_file_format(osm_file_format)

        # Get the URL
        download_url = subregion_downloads_index.loc[subregion_name_, osm_file_format_]

        return subregion_name_, download_url

    def get_default_osm_filename(self, subregion_name, osm_file_format, update=False):
        """
        get default filename for a given subregion name
        (by parsing the relevant download URL).

        :param subregion_name: name of a geographic region (case-insensitive)
        :type subregion_name: str
        :param osm_file_format: OSM file format; valid values include
            ``".osm.pbf"``, ``".shp.zip"`` and ``".osm.bz2"``
        :type osm_file_format: str
        :param update: whether to check on update and proceed to update the package data,
            defaults to ``False``
        :type update: bool
        :return: default OSM filename for the ``subregion_name``
        :rtype: str

        **Examples**::

            >>> from pydriosm.downloader import GeofabrikDownloader

            >>> geofabrik_downloader = GeofabrikDownloader()

            >>> sr_name = 'london'
            >>> file_format = ".pbf"

            >>> sr_filename = geofabrik_downloader.get_default_osm_filename(sr_name,
            ...                                                             file_format)

            >>> print(sr_filename)
            greater-london-latest.osm.pbf

            >>> sr_name = 'britain'
            >>> file_format = ".shp"

            >>> sr_filename = geofabrik_downloader.get_default_osm_filename(sr_name,
            ...                                                             file_format)
            No .shp.zip data is available to download for Great Britain.

            >>> print(sr_filename)
            None
        """

        subregion_name_ = self.validate_input_subregion_name(subregion_name)
        osm_file_format_ = self.validate_input_file_format(osm_file_format)

        _, download_url = self.get_subregion_download_url(subregion_name_, osm_file_format_,
                                                          update=update)

        if download_url is None:
            print("No {} data is available to download for {}.".format(
                osm_file_format_, subregion_name_))

        else:
            subregion_filename = os.path.split(download_url)[-1]
            return subregion_filename

    def get_default_path_to_osm_file(self, subregion_name, osm_file_format, mkdir=False,
                                     update=False, verbose=False):
        """
        Get default path for storing the downloaded file
        (by parsing the relevant download URL).

        :param subregion_name: name of a geographic region (case-insensitive)
        :type subregion_name: str
        :param osm_file_format: OSM file format; valid values include
            ``".osm.pbf"``, ``".shp.zip"`` and ``".osm.bz2"``
        :type osm_file_format: str
        :param mkdir: whether to create a directory, defaults to ``False``
        :type mkdir: bool
        :param update: whether to check on update and proceed to update the package data,
            defaults to ``False``
        :type update: bool
        :param verbose: whether to print relevant information in console as the function runs,
            defaults to ``False``
        :type verbose: bool or int
        :return: default filename of the subregion and default (absolute) path to the file
        :rtype: tuple

        **Example**::

            >>> import os
            >>> from pydriosm.downloader import GeofabrikDownloader

            >>> geofabrik_downloader = GeofabrikDownloader()

            >>> sr_name = 'london'
            >>> file_format = ".pbf"

            >>> filename, file_path = geofabrik_downloader.get_default_path_to_osm_file(
            ...     sr_name, file_format)

            >>> print(filename)
            greater-london-latest.osm.pbf

            >>> print(os.path.relpath(file_path))
            dat_GeoFabrik\\Europe\\Great Britain\\England\\greater-london-latest.osm.pbf
        """

        subregion_name_ = self.validate_input_subregion_name(subregion_name)
        osm_file_format_ = self.validate_input_file_format(osm_file_format)

        subregion_name_, download_url = self.get_subregion_download_url(
            subregion_name_, osm_file_format_, update=update)

        if download_url is None:
            if verbose:
                print("{} data is not available for {}".format(
                    osm_file_format_, subregion_name_))

            default_filename, default_file_path = None, None

        else:
            parsed_path = urllib.parse.urlparse(download_url).path.lstrip('/').split('/')

            if len(parsed_path) == 1:
                parsed_path = [subregion_name_] + parsed_path

            subregion_names = self.get_subregion_name_list()
            directory = cd_dat_geofabrik(
                *[find_similar_str(x, subregion_names) if x != 'us' else 'United States'
                  for x in parsed_path[0:-1]],
                mkdir=mkdir)

            default_filename = parsed_path[-1]
            default_file_path = os.path.join(directory, default_filename)

        return default_filename, default_file_path

    def retrieve_names_of_subregions(self, *subregion_name, deep=False):
        """
        Retrieve names of all subregions (if any) of the given geographic region(s)
        from the region-subregion tier.

        See also [`RNS-1 <https://stackoverflow.com/questions/9807634/>`_].

        :param subregion_name: name of a geographic region (case-insensitive)
        :type subregion_name: str or None
        :param deep: whether to get subregion names of the subregions, defaults to ``False``
        :type deep: bool
        :return: list of subregions (if any);
            if ``subregion_name=None``, all regions that do have subregions
        :rtype: list

        **Examples**::

            >>> from pydriosm.downloader import GeofabrikDownloader

            >>> geofabrik_downloader = GeofabrikDownloader()

            >>> sr_names = geofabrik_downloader.retrieve_names_of_subregions()
            >>> print(sr_names[:5])
            ['Antarctica', 'Algeria', 'Angola', 'Benin', 'Botswana']

            >>> sr_names = geofabrik_downloader.retrieve_names_of_subregions(
            ...     'england', 'asia', deep=False)
            >>> print(sr_names[:5])
            ['Bedfordshire', 'Berkshire', 'Bristol', 'Buckinghamshire', 'Cambridgeshire']
            >>> print(sr_names[-5:])
            ['Thailand', 'Turkmenistan', 'Uzbekistan', 'Vietnam', 'Yemen']

            >>> sr_names = geofabrik_downloader.retrieve_names_of_subregions(
            ...     'britain', deep=True)
            >>> print(sr_names[:5])
            ['Scotland', 'Wales', 'Bedfordshire', 'Berkshire', 'Bristol']
        """

        region_subregion_tier, non_subregions_list = self.get_region_subregion_tier()

        if not subregion_name:
            subregion_names = non_subregions_list

        else:

            def find_subregions(reg_name, reg_sub_idx):
                """
                :param reg_name: name of a geographic region
                :type reg_name: str
                :param reg_sub_idx:
                :type reg_sub_idx: dict
                :return:
                :rtype: generator object

                **Test**::

                    reg_name = region
                    reg_sub_idx = region_subregion_tier
                """

                for k, v in reg_sub_idx.items():
                    if reg_name == k:
                        if isinstance(v, dict):
                            yield list(v.keys())
                        else:
                            yield [reg_name] if isinstance(reg_name, str) else reg_name
                    elif isinstance(v, dict):
                        for sub in find_subregions(reg_name, v):
                            if isinstance(sub, dict):
                                yield list(sub.keys())
                            else:
                                yield [sub] if isinstance(sub, str) else sub

            res = []
            for region in subregion_name:
                res += list(find_subregions(self.validate_input_subregion_name(region),
                                            region_subregion_tier))[0]

            if not deep:
                subregion_names = res
            else:
                check_list = [x for x in res if x not in non_subregions_list]
                if check_list:
                    res_ = list(set(res) - set(check_list))
                    # for region in check_list:
                    #     res_ += self.retrieve_names_of_subregions_of(region)
                    res_ += self.retrieve_names_of_subregions(*check_list)
                else:
                    res_ = res
                del non_subregions_list, region_subregion_tier, check_list

                subregion_names = list(dict.fromkeys(res_))

        return subregion_names

    def make_default_sub_subregion_download_dir(self, subregion_name, osm_file_format,
                                                download_dir=None, mkdir=False):
        """
        Make a default directory for downloading subregions of a geographic region
        (e.g. in case that the requested file format is unavailable for the region).

        :param subregion_name: name of a geographic region (case-insensitive)
        :type subregion_name: str
        :param osm_file_format: OSM file format; valid values include
            ``".osm.pbf"``, ``".shp.zip"`` and ``".osm.bz2"``
        :type osm_file_format: str
        :param download_dir: directory for saving the downloaded file(s);
            if ``None`` (default), the default directory
        :type download_dir: str or None
        :param mkdir: whether to create a directory, defaults to ``False``
        :type mkdir: bool
        :return: default download directory if the requested data file is not available
        :rtype: str

        **Example**::

            >>> import os
            >>> from pydriosm.downloader import GeofabrikDownloader

            >>> geofabrik_downloader = GeofabrikDownloader()

            >>> sr_name = 'london'
            >>> file_format = ".pbf"

            >>> dwnld_dir = geofabrik_downloader.make_default_sub_subregion_download_dir(
            ...     sr_name, file_format)

            >>> print(os.path.relpath(dwnld_dir))
            # dat_GeoFabrik\\Europe\\Great Britain\\England\\greater-london-latest-osm-pbf

            >>> sr_name = 'britain'
            >>> file_format = ".shp"

            >>> dwnld_dir = geofabrik_downloader.make_default_sub_subregion_download_dir(
            ...     sr_name, file_format, download_dir="tests")

            >>> print(os.path.relpath(dwnld_dir))
            tests\\great-britain-shp-zip
        """

        subregion_name_ = self.validate_input_subregion_name(subregion_name)
        osm_file_format_ = self.validate_input_file_format(osm_file_format)

        default_filename, default_file_path = self.get_default_path_to_osm_file(
            subregion_name_, osm_file_format_)

        if not default_filename:
            default_sub_dir = re.sub(r"[. ]", "-", subregion_name_.lower() + osm_file_format_)
        else:
            default_sub_dir = re.sub(r"[. ]", "-", default_filename).lower()

        if not download_dir:
            default_download_dir = cd_dat_geofabrik(os.path.dirname(default_file_path),
                                                    default_sub_dir, mkdir=mkdir)

        else:
            default_download_dir = cd(validate_input_data_dir(download_dir), default_sub_dir,
                                      mkdir=mkdir)

        return default_download_dir

    def download_osm_data(self, subregion_names, osm_file_format, download_dir=None,
                          update=False, confirmation_required=True, deep_retry=False,
                          interval_sec=None, verbose=False, ret_download_path=False):
        """
        Download Geofabrik OSM data extracts for given geographic region(s) and file format.

        :param subregion_names: name(s) of one (or multiple) geographic region(s)
        :type subregion_names: str or list
        :param osm_file_format: OSM file format; valid values include
            ``".osm.pbf"``, ``".shp.zip"`` and ``".osm.bz2"``
        :type osm_file_format: str
        :param download_dir: directory for saving the downloaded file(s);
            if None (default), use the default directory
        :type download_dir: str or None
        :param update: whether to check on update and proceed to update the package data,
            defaults to ``False``
        :type update: bool
        :param confirmation_required: whether to prompt a message for confirmation to proceed,
            defaults to ``True``
        :type confirmation_required: bool
        :param deep_retry: whether to further check availability of sub-subregions data,
            defaults to ``False``
        :type deep_retry: bool
        :param interval_sec: interval (in sec) between downloading two subregions,
            defaults to ``None``
        :type interval_sec: int or None
        :param verbose: whether to print relevant information in console as the function runs,
            defaults to ``False``
        :type verbose: bool or int
        :param ret_download_path: whether to return the path(s) to the downloaded file(s),
            defaults to ``False``
        :type ret_download_path: bool
        :return: absolute path(s) to the downloaded file(s) when ``ret_download_path=True``
        :rtype: list or str

        **Examples**::

            >>> import os
            >>> import shutil
            >>> from pydriosm.downloader import GeofabrikDownloader, cd_dat_geofabrik

            >>> geofabrik_downloader = GeofabrikDownloader()

            # Download PBF data file of Greater London and Rutland
            >>> sr_names = ['London', 'Rutland']
            >>> file_fmt = ".pbf"

            >>> dwnld_paths = geofabrik_downloader.download_osm_data(sr_names, file_fmt,
            ...                                                      verbose=True,
            ...                                                      ret_download_path=True)
            Confirm to download .osm.pbf data of the following geographic region(s):
                Greater London
                Rutland
            ? [No]|Yes: yes
            Downloading "greater-london-latest.osm.pbf" to "\\dat_GeoFabrik\\...\\England" ...
            Done.
            Downloading "rutland-latest.osm.pbf" to "\\dat_GeoFabrik\\...\\England" ...
            Done.

            >>> for dwnld_path in dwnld_paths: print(os.path.relpath(dwnld_path))
            dat_GeoFabrik\\Europe\\Great Britain\\England\\greater-london-latest.osm.pbf
            dat_GeoFabrik\\Europe\\Great Britain\\England\\rutland-latest.osm.pbf

            # Delete the directory generated above
            >>> shutil.rmtree(cd_dat_geofabrik())

            # Download shapefiles of West Midlands
            >>> sr_name = 'west midlands'
            >>> file_fmt = ".shp"
            >>> dwnld_dir = "tests"

            >>> dwnld_path = geofabrik_downloader.download_osm_data(sr_name, file_fmt,
            ...                                                     dwnld_dir, verbose=True,
            ...                                                     ret_download_path=True)
            Confirm to download .shp.zip data of the following geographic region(s):
                West Midlands
            ? [No]|Yes: yes
            Downloading "west-midlands-latest-free.shp.zip" to "\\tests" ...
            Done.

            >>> print(os.path.relpath(dwnld_path))
            tests\\west-midlands-latest-free.shp.zip

            # Delete the downloaded .shp.zip file
            >>> os.remove(dwnld_path)

            # Download shapefiles of Great Britain
            >>> sr_name = 'Great Britain'
            >>> file_fmt = ".shp"

            >>> dwnld_path = geofabrik_downloader.download_osm_data(sr_name, file_fmt,
            ...                                                     dwnld_dir, deep_retry=True,
            ...                                                     verbose=True,
            ...                                                     ret_download_path=True)
            Confirm to download .shp.zip data of the following geographic region(s):
                Great Britain
            ? [No]|Yes: yes
            The .shp.zip data is not found for "Great Britain".
            Try downloading the data of its subregions instead [No]|Yes: no

            >>> print(dwnld_path)
            []
        """

        subregion_names_ = [subregion_names] if isinstance(subregion_names, str) \
            else subregion_names.copy()
        subregion_names_ = [self.validate_input_subregion_name(x) for x in subregion_names_]

        osm_file_format_ = self.validate_input_file_format(osm_file_format)

        if confirmed(
                "Confirm to download {} data of the following geographic region(s):"
                "\n\t{}\n?".format(osm_file_format_, "\n\t".join(subregion_names_)),
                confirmation_required=confirmation_required):

            download_paths = []

            for sub_reg_name in subregion_names_:

                # Get download URL
                subregion_name_, download_url = self.get_subregion_download_url(
                    sub_reg_name, osm_file_format_)

                if download_url is None:

                    if verbose:
                        print("The {} data is not found for \"{}\".".format(
                            osm_file_format_, subregion_name_))

                    if confirmed("Try downloading the data of its subregions instead",
                                 confirmation_required=confirmation_required):

                        sub_subregions = self.retrieve_names_of_subregions(subregion_name_,
                                                                           deep=deep_retry)

                        if sub_subregions == [subregion_name_]:
                            print("No {} data is available for this geographic region.".format(
                                osm_file_format_))
                            break

                        else:
                            if not download_dir:
                                _, path_to_file_ = self.get_default_path_to_osm_file(
                                    subregion_name_, ".osm.pbf")
                                download_dir = os.path.dirname(path_to_file_)

                            download_dir_ = self.make_default_sub_subregion_download_dir(
                                subregion_name_, osm_file_format_, download_dir)

                            self.download_osm_data(sub_subregions,
                                                   osm_file_format=osm_file_format_,
                                                   download_dir=download_dir_, update=update,
                                                   confirmation_required=False, verbose=verbose,
                                                   ret_download_path=ret_download_path)

                else:
                    if not download_dir:
                        # Download the requested OSM file to default directory
                        osm_filename, path_to_file = self.get_default_path_to_osm_file(
                            subregion_name_, osm_file_format_, mkdir=True)
                    else:
                        download_dir_ = validate_input_data_dir(download_dir)
                        osm_filename = self.get_default_osm_filename(
                            subregion_name_, osm_file_format=osm_file_format_)
                        path_to_file = os.path.join(download_dir_, osm_filename)

                    download_paths.append(path_to_file)

                    if os.path.isfile(path_to_file) and not update:
                        if verbose:
                            print("\"{}\" of {} is already available at \"{}\".".format(
                                os.path.basename(path_to_file), subregion_name_,
                                os.path.relpath(os.path.dirname(path_to_file))))

                    else:
                        if verbose:
                            print("{} \"{}\" to \"\\{}\" ... ".format(
                                "Updating" if os.path.isfile(path_to_file) else "Downloading",
                                osm_filename,
                                os.path.relpath(os.path.dirname(path_to_file))))

                        try:
                            download_file_from_url(download_url, path_to_file)
                            print("Done. ") if verbose else ""

                        except Exception as e:
                            print("Failed. {}.".format(e))

                if interval_sec:
                    time.sleep(interval_sec)

            if ret_download_path:
                if len(download_paths) == 1:
                    download_paths = download_paths[0]

                return download_paths

    def osm_file_exists(self, subregion_name, osm_file_format, data_dir=None,
                        update=False, verbose=False, ret_file_path=False):
        """
        Check if a requested data file of a geographic region already exists locally.

        :param subregion_name: name of a geographic region (case-insensitive)
        :type subregion_name: str
        :param osm_file_format: OSM file format;
            valid values include ``".osm.pbf"``, ``".shp.zip"`` and ``".osm.bz2"``
        :type osm_file_format: str
        :param data_dir: directory for saving the downloaded file(s);
            if None (default), use the default directory
        :type data_dir: str or None
        :param update: whether to check on update and proceed to update the package data,
            defaults to ``False``
        :type update: bool
        :param verbose: whether to print relevant information in console as the function runs,
            defaults to ``False``
        :type verbose: bool or int
        :param ret_file_path: whether to return the path to the data file (if it exists),
            defaults to ``False``
        :type ret_file_path: bool
        :return: whether requested data file exists
        :rtype: bool

        **Examples**::

            >>> from pydriosm.downloader import GeofabrikDownloader

            >>> geofabrik_downloader = GeofabrikDownloader()

            >>> sr_name = 'london'
            >>> file_fmt = ".pbf"

            >>> path_to_pbf = geofabrik_downloader.osm_file_exists(sr_name, file_fmt,
            ...                                                    verbose=True)

            >>> print(path_to_pbf)
            True  # (if the PBF data file exists)

            >>> path_to_pbf = geofabrik_downloader.osm_file_exists(sr_name, file_fmt,
            ...                                                    ret_file_path=True)

            >>> print(os.path.relpath(path_to_pbf))
            # (if the data file exists)
            dat_GeoFabrik\\Europe\\Great Britain\\England\\greater-london-latest.osm.pbf
        """

        subregion_name_ = self.validate_input_subregion_name(subregion_name)
        osm_file_format_ = self.validate_input_file_format(osm_file_format)

        default_filename, path_to_file = self.get_default_path_to_osm_file(subregion_name_,
                                                                           osm_file_format_)

        if data_dir:
            path_to_file = cd(validate_input_data_dir(data_dir), default_filename)

        if os.path.isfile(path_to_file) and not update:
            if verbose == 2:
                print("\"{}\" of {} is available at \"{}\".".format(
                    default_filename, subregion_name_,
                    os.path.relpath(os.path.dirname(path_to_file))))

            if ret_file_path:
                return path_to_file
            else:
                return True

        else:
            return False

    def download_subregion_data(self, subregion_names, osm_file_format, download_dir=None,
                                update=False, verbose=False, ret_download_path=False):
        """
        Download OSM data of one (or multiple) geographic regions and
        all its (or their) subregions.

        :param subregion_names: name(s) of one (or multiple) regions/subregions
        :type subregion_names: str or list
        :param osm_file_format: OSM file format;
            valid values include ``".osm.pbf"``, ``".shp.zip"`` and ``".osm.bz2"``
        :type osm_file_format: str
        :param download_dir: directory for saving the downloaded file(s);
            if None (default), use the default directory
        :type download_dir: str or None
        :param update: whether to check on update and proceed to update the package data,
            defaults to ``False``
        :type update: bool
        :param verbose: whether to print relevant information in console as the function runs,
            defaults to ``False``
        :type verbose: bool or int
        :param ret_download_path: whether to return the path(s) to the downloaded file(s),
            defaults to ``False``
        :type ret_download_path: bool
        :return: the path(s) to the downloaded file(s) when ``ret_download_path=True``
        :rtype: list or str

        **Examples**::

            >>> import os
            >>> from pyhelpers.dir import cd
            >>> from pydriosm.downloader import GeofabrikDownloader

            >>> geofabrik_downloader = GeofabrikDownloader()

            >>> file_fmt = ".pbf"
            >>> dwnld_dir = "tests"

            >>> sr_names = ['rutland', 'west yorkshire']

            >>> geofabrik_downloader.download_subregion_data(sr_names, file_fmt, dwnld_dir,
            ...                                              verbose=True)
            To download .osm.pbf data of the following geographic region(s):
                Rutland
                West Yorkshire
            ? [No]|Yes: yes
            Downloading "rutland-latest.osm.pbf" to "\\tests" ...
            Done.
            Downloading "west-yorkshire-latest.osm.pbf" to "\\tests" ...
            Done.

            >>> os.remove(cd("tests", "rutland-latest.osm.pbf"))

            >>> sr_names = ['west midlands', 'west yorkshire']

            >>> dwnld_paths = geofabrik_downloader.download_subregion_data(
            ...     sr_names, file_fmt, dwnld_dir, verbose=True, ret_download_path=True)
            To download .osm.pbf data of the following geographic region(s):
                West Midlands
            ? [No]|Yes: yes
            Downloading "west-midlands-latest.osm.pbf" to "\\tests" ...
            Done.
            "west-yorkshire-latest.osm.pbf" of West Yorkshire is already available at "tests".

            >>> for dwnld_path in dwnld_paths: print(os.path.relpath(dwnld_path))
            tests\\west-midlands-latest.osm.pbf
            tests\\west-yorkshire-latest.osm.pbf

            >>> for dwnld_path in dwnld_paths: os.remove(dwnld_path)
        """

        subregion_names_ = [subregion_names] if isinstance(subregion_names, str) \
            else subregion_names.copy()
        subregion_names_ = [self.validate_input_subregion_name(x) for x in subregion_names_]
        subregion_names_ = self.retrieve_names_of_subregions(*subregion_names_)

        subregion_name_list = subregion_names_.copy()

        osm_file_format_ = self.validate_input_file_format(osm_file_format)

        for subregion_name in subregion_names_:
            if self.osm_file_exists(subregion_name, osm_file_format_, download_dir, update):
                subregion_name_list.remove(subregion_name)

        confirmation_required_ = False if not subregion_name_list else True

        if confirmed("To download {} data of the following geographic region(s): "
                     "\n\t{}\n?".format(osm_file_format_, "\n\t".join(subregion_name_list)),
                     confirmation_required=confirmation_required_):

            download_paths = self.download_osm_data(subregion_names_,
                                                    osm_file_format=osm_file_format_,
                                                    download_dir=download_dir, update=update,
                                                    confirmation_required=False,
                                                    verbose=verbose,
                                                    ret_download_path=ret_download_path)

            if ret_download_path:
                if len(download_paths) == 1:
                    download_paths = download_paths[0]
                return download_paths


class BBBikeDownloader:
    """
    A class representation of a tool for downloading
    `BBBike <https://download.bbbike.org/osm/>`_ data extracts.

    **Example**::

        >>> from pydriosm.downloader import BBBikeDownloader

        >>> bbbike_downloader = BBBikeDownloader()

        >>> print(bbbike_downloader.Name)
        BBBike OpenStreetMap data extracts
    """

    def __init__(self):
        """
        Constructor method.
        """
        self.Name = 'BBBike OpenStreetMap data extracts'
        self.URL = bbbike_homepage()
        self.URLCities = \
            'https://raw.githubusercontent.com/wosch/bbbike-world/world/etc/cities.txt'
        self.CitiesNames = 'BBBike cities'
        self.URLCitiesCoordinates = \
            'https://raw.githubusercontent.com/wosch/bbbike-world/world/etc/cities.csv'
        self.CitiesCoordinates = 'BBBike cities coordinates'
        self.SubregionCatalogue = 'BBBike subregion catalogue'
        self.SubregionNameList = 'BBBike subregion name list'
        self.DownloadDictName = 'BBBike download dictionary'

    def get_list_of_cities(self, update=False, confirmation_required=True, verbose=False):
        """
        Get a list of names of BBBike cities.

        :param update: whether to check on update and proceed to update the package data,
            defaults to ``False``
        :type update: bool
        :param confirmation_required: whether to prompt a message for confirmation to proceed,
            defaults to ``True``
        :type confirmation_required: bool
        :param verbose: whether to print relevant information in console as the function runs,
            defaults to ``False``
        :type verbose: bool or int
        :return: catalogue for subregions of BBBike data
        :rtype: pandas.DataFrame or None

        **Example**::

            >>> from pydriosm.downloader import BBBikeDownloader

            >>> bbbike_downloader = BBBikeDownloader()

            >>> names_of_cities = bbbike_downloader.get_list_of_cities()

            >>> print(names_of_cities[:5])
            ['Heilbronn', 'Emden', 'Bremerhaven', 'Paris', 'Ostrava']
        """

        path_to_pickle = cd_dat(self.CitiesNames.replace(" ", "-") + ".pickle")

        if os.path.isfile(path_to_pickle) and not update:
            cities_names = load_pickle(path_to_pickle)

        else:
            if confirmed("To collect {}?".format(self.CitiesNames),
                         confirmation_required=confirmation_required):

                try:
                    cities_names_ = pd.read_csv(self.URLCities, header=None)
                    cities_names = list(cities_names_.values.flatten())

                    save_pickle(cities_names, path_to_pickle, verbose=verbose)

                except Exception as e:
                    print("Failed. {}.".format(e))
                    cities_names = None

            else:
                if verbose:
                    print("No data of \"{}\" is available.".format(self.CitiesNames))
                cities_names = None

        return cities_names

    def get_cities_coordinates(self, update=False, confirmation_required=True,
                               verbose=False):
        """
        Get location information of BBBike cities.

        :param update: whether to check on update and proceed to update the package data,
            defaults to ``False``
        :type update: bool
        :param confirmation_required: whether to prompt a message for confirmation to proceed,
            defaults to ``True``
        :type confirmation_required: bool
        :param verbose: whether to print relevant information in console as the function runs,
            defaults to ``False``
        :type verbose: bool or int
        :return: location information of BBBike cities
        :rtype: pandas.DataFrame or None

        **Example**::

            >>> from pydriosm.downloader import BBBikeDownloader

            >>> bbbike_downloader = BBBikeDownloader()

            >>> coords_of_cities = bbbike_downloader.get_cities_coordinates()

            >>> print(coords_of_cities.tail())
                      City            Real name  ... ur_longitude ur_latitude
            233     Zagreb   de!Agram,en!Zagreb  ...       16.291       45.94
            234    Zuerich  de!Zürich,en!Zurich  ...         8.87       47.58
            238     bbbike                       ...    14.249353   52.355108
            240      dummy                       ...      44.5259     33.4238
            241  Finowfurt                       ...      13.8591     52.8787
            [5 rows x 13 columns]
        """

        path_to_pickle = cd_dat(self.CitiesCoordinates.replace(" ", "-") + ".pickle")

        if os.path.isfile(path_to_pickle) and not update:
            cities_coordinates = load_pickle(path_to_pickle)

        else:
            if confirmed("To collect {}?".format(self.CitiesCoordinates),
                         confirmation_required=confirmation_required):

                try:
                    import urllib.request
                    import csv
                    import io

                    csv_temp = urllib.request.urlopen(self.URLCitiesCoordinates)
                    csv_file = list(
                        csv.reader(io.StringIO(csv_temp.read().decode('utf-8')),
                                   delimiter=':'))

                    csv_data = [[x.strip().strip('\u200e').replace('#', '') for x in row]
                                for row in csv_file[5:-1]]
                    column_names = [x.replace('#', '').strip().capitalize()
                                    for x in csv_file[0]]
                    cities_coords = pd.DataFrame(csv_data, columns=column_names)

                    coordinates = cities_coords.Coord.str.split(' ').apply(pd.Series)
                    coords_cols = ['ll_longitude', 'll_latitude1',
                                   'ur_longitude', 'ur_latitude']
                    coordinates.columns = coords_cols

                    cities_coords.drop(['Coord'], axis=1, inplace=True)

                    cities_coordinates = pd.concat([cities_coords, coordinates], axis=1)

                    cities_coordinates.dropna(subset=coords_cols, inplace=True)

                    save_pickle(cities_coordinates, path_to_pickle, verbose=verbose)

                except Exception as e:
                    print("Failed. {}.".format(e))
                    cities_coordinates = None

            else:
                if verbose:
                    print("No data of \"{}\" is available.".format(self.CitiesCoordinates))
                cities_coordinates = None

        return cities_coordinates

    def get_subregion_catalogue(self, update=False, confirmation_required=True,
                                verbose=False):
        """
        Get catalogue for subregions of BBBike data.

        :param update: whether to check on update and proceed to update the package data,
            defaults to ``False``
        :type update: bool
        :param confirmation_required: whether to prompt a message for confirmation to proceed,
            defaults to ``True``
        :type confirmation_required: bool
        :param verbose: whether to print relevant information in console as the function runs,
            defaults to ``False``
        :type verbose: bool or int
        :return: catalogue for subregions of BBBike data
        :rtype: pandas.DataFrame or None

        **Example**::

            >>> from pydriosm.downloader import BBBikeDownloader

            >>> bbbike_downloader = BBBikeDownloader()

            >>> subregion_catalog = bbbike_downloader.get_subregion_catalogue()

            >>> print(subregion_catalog.head())
                      Name  ...                                                URL
            1       Aachen  ...      http://download.bbbike.org/osm/bbbike/Aachen/
            2       Aarhus  ...      http://download.bbbike.org/osm/bbbike/Aarhus/
            3     Adelaide  ...    http://download.bbbike.org/osm/bbbike/Adelaide/
            4  Albuquerque  ...  http://download.bbbike.org/osm/bbbike/Albuquer...
            5   Alexandria  ...  http://download.bbbike.org/osm/bbbike/Alexandria/
            [5 rows x 3 columns]
        """

        path_to_pickle = cd_dat(self.SubregionCatalogue.replace(" ", "-") + ".pickle")

        if os.path.isfile(path_to_pickle) and not update:
            subregion_catalogue = load_pickle(path_to_pickle)

        else:
            if confirmed("To collect {}?".format(self.SubregionCatalogue),
                         confirmation_required=confirmation_required):

                try:
                    bbbike_subregion_catalogue_ = pd.read_html(self.URL, header=0,
                                                               parse_dates=['Last Modified'])
                    subregion_catalogue = \
                        bbbike_subregion_catalogue_[0].drop(0).drop(['Size', 'Type'], axis=1)
                    subregion_catalogue.Name = subregion_catalogue.Name.map(
                        lambda x: x.strip('/'))

                    source = requests.get(self.URL, headers=fake_requests_headers())
                    table_soup = bs4.BeautifulSoup(source.text, 'lxml').find('table')
                    urls = [urllib.parse.urljoin(self.URL, x.get('href'))
                            for x in table_soup.find_all('a')[1:]]

                    subregion_catalogue['URL'] = urls

                    save_pickle(subregion_catalogue, path_to_pickle, verbose=verbose)

                except Exception as e:
                    print("Failed. {}.".format(e))
                    subregion_catalogue = None

            else:
                if verbose:
                    print("No data of \"{}\" is available.".format(self.SubregionCatalogue))
                subregion_catalogue = None

        return subregion_catalogue

    def get_subregion_name_list(self, update=False, confirmation_required=True,
                                verbose=False):
        """
        Get a list of names of all geographic regions available on
        the free BBBike download server.

        :param update: whether to check on update and proceed to update the package data,
            defaults to ``False``
        :type update: bool
        :param confirmation_required: whether to prompt a message for confirmation to proceed,
            defaults to ``True``
        :type confirmation_required: bool
        :param verbose: whether to print relevant information in console as the function runs,
            defaults to ``False``
        :type verbose: bool or int
        :return: a list of geographic region names available on the free BBBike download server
        :rtype: list

        **Example**::

            >>> from pydriosm.downloader import BBBikeDownloader

            >>> bbbike_downloader = BBBikeDownloader()

            >>> sr_name_list = bbbike_downloader.get_subregion_name_list()

            >>> print(sr_name_list[:5])
            ['Aachen', 'Aarhus', 'Adelaide', 'Albuquerque', 'Alexandria']
        """

        path_to_name_list = cd_dat(self.SubregionNameList.replace(" ", "-") + ".pickle")

        if os.path.isfile(path_to_name_list) and not update:
            subregion_name_list = load_pickle(path_to_name_list)

        else:
            if confirmed("To get {}?".format(self.SubregionNameList),
                         confirmation_required=confirmation_required):

                subregion_catalogue = self.get_subregion_catalogue(
                    update, confirmation_required=False, verbose=verbose)

                subregion_name_list = subregion_catalogue.Name.to_list()

                save_pickle(subregion_name_list, path_to_name_list, verbose=verbose)

            else:
                subregion_name_list = []
                if verbose:
                    print("No data of {} is available.".format(self.SubregionNameList))

        return subregion_name_list

    def validate_input_subregion_name(self, subregion_name):
        """
        Validate input subregion name
        (by matching it to a name of an available geographic region).

        :param subregion_name: name of a geographic region (case-insensitive)
        :type subregion_name: str
        :return: valid subregion name that matches, or is the most similar to,
            the input ``subregion_name``
        :rtype: str

        **Example**::

            >>> from pydriosm.downloader import BBBikeDownloader

            >>> bbbike_downloader = BBBikeDownloader()

            >>> sr_name = 'leeds'

            >>> sr_name_ = bbbike_downloader.validate_input_subregion_name(sr_name)

            >>> print(sr_name_)
            Leeds
        """

        assert isinstance(subregion_name, str)

        bbbike_subregion_names = self.get_subregion_name_list()

        subregion_name_ = find_similar_str(subregion_name, bbbike_subregion_names)

        return subregion_name_

    def get_subregion_download_catalogue(self, subregion_name, confirmation_required=True,
                                         verbose=False):
        """
        Get a catalogue of BBBike OSM data extracts available to download
        for a geographic region.

        :param subregion_name: name of a geographic region (case-insensitive)
        :type subregion_name: str
        :param confirmation_required: whether to prompt a message for confirmation to proceed,
            defaults to ``True``
        :type confirmation_required: bool
        :param verbose: whether to print relevant information in console as the function runs,
            defaults to ``False``
        :type verbose: bool or int
        :return: a catalogues for subregion downloads
        :rtype: pandas.DataFrame or None

        **Example**::

            >>> from pydriosm.downloader import BBBikeDownloader

            >>> bbbike_downloader = BBBikeDownloader()

            >>> sr_name = 'leeds'

            >>> leeds_download_catalogue = bbbike_downloader.get_subregion_download_catalogue(
            ...     subregion_name=sr_name, verbose=True)
            Confirm to collect the download catalogue for Leeds? [No]|Yes: yes
            In progress ... Done.

            >>> print(leeds_download_catalogue.head())
                                         Filename  ...          LastUpdate
            0                       Leeds.osm.pbf  ... 2020-09-25 10:04:25
            1                        Leeds.osm.gz  ... 2020-09-25 15:11:49
            2                   Leeds.osm.shp.zip  ... 2020-09-25 15:33:10
            3  Leeds.osm.garmin-onroad-latin1.zip  ... 2020-09-25 17:49:15
            4         Leeds.osm.garmin-onroad.zip  ... 2020-09-25 17:49:04
            [5 rows x 5 columns]
        """

        subregion_name_ = self.validate_input_subregion_name(subregion_name)

        if confirmed("Confirm to collect the download catalogue for {}?".format(
                subregion_name_), confirmation_required=confirmation_required):

            try:
                if confirmation_required:
                    print("In progress", end=" ... ") if verbose else ""
                else:
                    print(f"  {subregion_name_}", end=" ... ") if verbose else ""

                url = urllib.parse.urljoin(self.URL, subregion_name_ + '/')

                source = requests.get(url, headers=fake_requests_headers())

                import bs4
                source_soup = bs4.BeautifulSoup(source.text, 'lxml')
                download_links_class = source_soup.find_all(
                    name='a', attrs={'class': ['download_link', 'small']})

                def parse_dlc(dlc):
                    dlc_href = dlc.get('href')  # URL
                    filename = os.path.basename(dlc_href)
                    download_url = urllib.parse.urljoin(url, dlc_href)
                    if not dlc.has_attr('title'):
                        file_format, file_size, last_update = 'Poly', None, None
                    else:
                        if len(dlc.contents) < 3:
                            file_format, file_size = 'Txt', None
                        else:
                            file_format, file_size, _ = dlc.contents  # File type and size
                            file_format, file_size = file_format.strip(), file_size.text
                        last_update = pd.to_datetime(dlc.get('title'))  # Date and time
                    parsed_dat = [filename, download_url, file_format, file_size, last_update]
                    return parsed_dat

                subregion_download_catalogue = pd.DataFrame(
                    parse_dlc(x) for x in download_links_class)
                subregion_download_catalogue.columns = ['Filename', 'URL', 'DataType', 'Size',
                                                        'LastUpdate']

                # path_to_file = cd_dat_bbbike(
                #   subregion_name_, subregion_name_ + "-download-catalogue.pickle")
                # save_pickle(subregion_downloads_catalogue, path_to_file, verbose=verbose)
                print("Done. ") if verbose else ""

            except Exception as e:
                subregion_download_catalogue = None
                print("Failed. {}".format(subregion_name_, e)) if verbose else ""

            return subregion_download_catalogue

    def get_download_dictionary(self, update=False, confirmation_required=True,
                                verbose=False):
        """
        Get a dictionary of available formats, data types and a download catalogue for
        BBBike data extracts.

        :param update: whether to check on update and proceed to update the package data,
            defaults to ``False``
        :type update: bool
        :param confirmation_required: whether to prompt a message for confirmation to proceed,
            defaults to ``True``
        :type confirmation_required: bool
        :param verbose: whether to print relevant information in console as the function runs,
            defaults to ``False``
        :type verbose: bool or int
        :return: a list of available formats, a list of available data types and
            a dictionary of download catalogue
        :rtype: dict

        **Examples**::

            >>> from pydriosm.downloader import BBBikeDownloader

            >>> bbbike_downloader = BBBikeDownloader()

            >>> dwnld_dict = bbbike_downloader.get_download_dictionary()

            >>> print(list(dwnld_dict.keys()))
            ['FileFormat', 'DataType', 'Catalogue']

            >>> print(dwnld_dict['Catalogue']['Leeds'].head())
                                         Filename  ...          LastUpdate
            0                       Leeds.osm.pbf  ... 2020-08-14 18:10:47
            1                        Leeds.osm.gz  ... 2020-08-14 23:26:15
            2                   Leeds.osm.shp.zip  ... 2020-08-14 23:48:29
            3  Leeds.osm.garmin-onroad-latin1.zip  ... 2020-08-15 01:59:13
            4         Leeds.osm.garmin-onroad.zip  ... 2020-08-15 01:59:02
            [5 rows x 5 columns]
        """

        path_to_pickle = cd_dat(self.DownloadDictName.replace(" ", "-") + ".pickle")

        if os.path.isfile(path_to_pickle) and not update:
            download_dictionary = load_pickle(path_to_pickle)

        else:
            if confirmed("To collect {} from the free BBBike download server?".format(
                    self.DownloadDictName), confirmation_required=confirmation_required):

                try:
                    bbbike_subregion_names = \
                        self.get_subregion_catalogue(verbose=verbose).Name.to_list()

                    if verbose:
                        print("Collecting {} ... ".format(self.DownloadDictName))

                    download_catalogue = [
                        self.get_subregion_download_catalogue(subregion_name,
                                                              confirmation_required=False,
                                                              verbose=verbose)
                        for subregion_name in bbbike_subregion_names]

                    sr_name = bbbike_subregion_names[0]
                    sr_download_catalogue = download_catalogue[0]

                    # Available file formats
                    file_fmt = [re.sub('{}|CHECKSUM'.format(sr_name), '', f)
                                for f in sr_download_catalogue.Filename]

                    # Available data types
                    data_typ = sr_download_catalogue.DataType.tolist()

                    download_dictionary = {
                        'FileFormat': [x.replace(".osm", "", 1) for x in file_fmt[:-2]],
                        'DataType': data_typ[:-2],
                        'Catalogue': dict(zip(bbbike_subregion_names, download_catalogue))}

                    print("Finished. ") if verbose else ""

                    save_pickle(download_dictionary, path_to_pickle, verbose=verbose)

                except Exception as e:
                    print("Failed. {}".format(e))
                    download_dictionary = None

            else:
                if verbose:
                    print("No data of \"{}\" is available.".format(self.DownloadDictName))
                download_dictionary = None

        return download_dictionary

    def get_osm_file_formats(self):
        """
        Get a list of valid OSM file formats available on the free BBBike download server.

        :return: valid BBBike OSM file formats
        :rtype: list

        **Example**::

            >>> from pydriosm.downloader import BBBikeDownloader

            >>> bbbike_downloader = BBBikeDownloader()

            >>> file_fmts = bbbike_downloader.get_osm_file_formats()

            >>> for file_fmt in file_fmts: print(file_fmt)
            .pbf
            .gz
            .shp.zip
            .garmin-onroad-latin1.zip
            .garmin-onroad.zip
            .garmin-opentopo.zip
            .garmin-osm.zip
            .geojson.xz
            .svg-osm.zip
            .mapsforge-osm.zip
            .navit.zip
            .csv.xz
        """

        osm_file_formats = self.get_download_dictionary()['FileFormat']

        return osm_file_formats

    def validate_input_osm_file_format(self, osm_file_format):
        """
        Validate input OSM file format (by matching it to an available filename extension).

        :param osm_file_format: format (file extension) of an OSM data extract
        :type osm_file_format: str
        :return: valid file format (file extension)
        :rtype: str

        **Example**::

            >>> from pydriosm.downloader import BBBikeDownloader

            >>> bbbike_downloader = BBBikeDownloader()

            >>> file_fmt = 'PBF'

            >>> file_fmt_ = bbbike_downloader.validate_input_osm_file_format(file_fmt)

            >>> print(file_fmt_)
            .pbf
        """

        assert isinstance(osm_file_format, str)
        bbbike_osm_file_formats = self.get_osm_file_formats()

        try:
            osm_file_format_ = find_similar_str(osm_file_format, bbbike_osm_file_formats)

            if osm_file_format_:
                return osm_file_format_

            else:
                print("The input file format must be one of the following: \n  \"{}\".".format(
                    "\",\n  \"".join(bbbike_osm_file_formats)))

        except Exception as e:
            print(e)

    def get_download_url(self, subregion_name, osm_file_format):
        """
        Get valid URL for downloading data of the given subregion and file format.

        :param subregion_name: name of a geographic region (case-insensitive)
        :type subregion_name: str
        :param osm_file_format: format (file extension) of an OSM data
        :type osm_file_format: str
        :return: a valid name of ``subregion_name`` and
            a download URL for the given ``osm_file_format``
        :rtype: tuple

        **Examples**::

            >>> from pydriosm.downloader import BBBikeDownloader

            >>> bbbike_downloader = BBBikeDownloader()

            >>> sr_name = 'leeds'
            >>> file_fmt = 'pbf'

            >>> sr_name_, sr_url = bbbike_downloader.get_download_url(sr_name, file_fmt)

            >>> print(sr_name_)
            Leeds
            >>> print(sr_url)
            http://download.bbbike.org/osm/bbbike/Leeds/Leeds.osm.pbf

            >>> file_fmt = 'csv.xz'
            >>> sr_name_, sr_url = bbbike_downloader.get_download_url(sr_name, file_fmt)

            >>> print(sr_name_)
            Leeds
            >>> print(sr_url)
            http://download.bbbike.org/osm/bbbike/Leeds/Leeds.osm.csv.xz
        """

        subregion_name_ = self.validate_input_subregion_name(subregion_name)
        osm_file_format_ = ".osm" + self.validate_input_osm_file_format(osm_file_format)

        bbbike_download_dictionary = self.get_download_dictionary()['Catalogue']
        sub_download_catalogue = bbbike_download_dictionary[subregion_name_]

        url = sub_download_catalogue[
            sub_download_catalogue.Filename == subregion_name_ + osm_file_format_].URL.iloc[0]

        return subregion_name_, url

    def get_valid_download_info(self, subregion_name, osm_file_format, download_dir=None):
        """
        Get a valid subregion name, filename, a URL and a absolute path for downloading data.

        :param subregion_name: name of a geographic region (case-insensitive)
        :type subregion_name: str
        :param osm_file_format: format (file extension) of an OSM data
        :type osm_file_format: str
        :param download_dir: directory where downloaded OSM file is saved;
            if ``None`` (default), package data directory
        :type download_dir: str or None
        :return: valid subregion name, filename, download url and absolute file path
        :rtype: tuple

        **Examples**::

            >>> import os
            >>> from pydriosm.downloader import BBBikeDownloader

            >>> bbbike_downloader = BBBikeDownloader()

            >>> sr_name = 'leeds'
            >>> file_fmt = 'pbf'

            >>> info = bbbike_downloader.get_valid_download_info(sr_name, file_fmt)
            >>> sr_name_, pbf_filename, dwnld_url, path_to_pbf = info

            >>> print(sr_name_)
            Leeds
            >>> print(pbf_filename)
            Leeds.osm.pbf
            >>> print(dwnld_url)
            http://download.bbbike.org/osm/bbbike/Leeds/Leeds.osm.pbf
            >>> print(os.path.relpath(path_to_pbf))
            dat_BBBike\\Leeds\\Leeds.osm.pbf
        """

        subregion_name_, download_url = self.get_download_url(subregion_name, osm_file_format)
        osm_filename = os.path.basename(download_url)

        if download_dir:
            path_to_file = cd(validate_input_data_dir(download_dir), osm_filename, mkdir=True)
        else:
            # default directory of package data
            path_to_file = cd_dat_bbbike(subregion_name_, osm_filename, mkdir=True)

        return subregion_name_, osm_filename, download_url, path_to_file

    def download_osm_data(self, subregion_names, osm_file_format, download_dir=None,
                          update=False, confirmation_required=True, interval_sec=1,
                          verbose=False, ret_download_path=False):
        """
        Download BBBike OSM data of a given format of one (or multiple) geographic region(s).

        :param subregion_names: name(s) of one (or multiple) geographic region(s)
        :type subregion_names: str or list
        :param osm_file_format: format (file extension) of an OSM data
        :type osm_file_format: str
        :param download_dir: directory where downloaded OSM file is saved;
            if ``None`` (default), package data directory
        :type download_dir: str or None
        :param update: whether to check on update and proceed to update the package data,
            defaults to ``False``
        :type update: bool
        :param confirmation_required: whether to prompt a message for confirmation to proceed,
            defaults to ``True``
        :type confirmation_required: bool
        :param interval_sec: interval (in sec) between downloading two subregions,
            defaults to ``1``
        :type interval_sec: int
        :param verbose: whether to print relevant information in console as the function runs,
            defaults to ``False``
        :type verbose: bool or int
        :param ret_download_path: whether to return the path(s) to the downloaded file(s),
            defaults to ``False``
        :type ret_download_path: bool
        :return: the path(s) to the downloaded file(s) when ``ret_download_path=True``
        :rtype: list or str

        **Examples**::

            >>> import os
            >>> import shutil
            >>> from pydriosm.downloader import BBBikeDownloader, cd_dat_bbbike

            >>> bbbike_downloader = BBBikeDownloader()

            >>> sr_names = 'London'
            >>> file_fmt = 'pbf'

            >>> bbbike_downloader.download_osm_data(sr_names, file_fmt, verbose=True)
            Confirm to download .pbf data of the following geographic region(s):
                London
            ? [No]|Yes: yes
            Downloading "London.osm.pbf" to "\\dat_BBBike\\London" ...
            Done.

            # Delete the directory generated above
            >>> shutil.rmtree(cd_dat_bbbike())

            >>> sr_names = ['leeds', 'birmingham']
            >>> dwnld_dir = "tests"

            >>> dwnld_paths = bbbike_downloader.download_osm_data(sr_names, file_fmt,
            ...                                                   dwnld_dir, verbose=True,
            ...                                                   ret_download_path=True)
            Confirm to download .pbf data of the following geographic region(s):
                Leeds
                Birmingham
            ? [No]|Yes: yes
            Downloading "Leeds.osm.pbf" to "\\tests" ...
            Done.
            Downloading "Birmingham.osm.pbf" to "\\tests" ...
            Done.

            >>> for dwnld_path in dwnld_paths: print(os.path.relpath(dwnld_path))
            tests\\Leeds.osm.pbf
            tests\\Birmingham.osm.pbf

            # Delete the above downloaded data files
            >>> for dwnld_path in dwnld_paths: os.remove(dwnld_path)
        """

        subregion_names_ = [subregion_names] if isinstance(subregion_names, str) \
            else subregion_names.copy()
        subregion_names_ = [self.validate_input_subregion_name(x) for x in subregion_names_]

        osm_file_format_ = self.validate_input_osm_file_format(osm_file_format)

        download_path = []

        if confirmed("Confirm to download {} data of the following geographic region(s):"
                     "\n\t{}\n?".format(osm_file_format_, "\n\t".join(subregion_names_)),
                     confirmation_required=confirmation_required):

            for sub_reg_name in subregion_names_:
                subregion_name_, osm_filename, download_url, path_to_file = \
                    self.get_valid_download_info(sub_reg_name, osm_file_format_, download_dir)

                if os.path.isfile(path_to_file) and not update:
                    if verbose:
                        print("The {} data of {} is already available at {}.".format(
                            osm_file_format_, subregion_name_, os.path.relpath(path_to_file)))

                    download_path.append(path_to_file)

                else:
                    try:
                        if verbose:
                            print("{} \"{}\" to \"\\{}\" ... ".format(
                                "Updating" if os.path.isfile(path_to_file) else "Downloading",
                                osm_filename,
                                os.path.relpath(os.path.dirname(path_to_file))))

                        download_file_from_url(download_url, path_to_file)

                        print("Done. ") if verbose else ""

                        download_path.append(path_to_file)

                        if os.path.getsize(path_to_file) / (1024 ** 2) <= 5:
                            time.sleep(interval_sec)

                    except Exception as e:
                        print("Failed. {}.".format(e))

            if ret_download_path:
                if len(download_path) == 1:
                    download_path = download_path[0]

                return download_path

    def download_subregion_data(self, subregion_name, download_dir=None, update=False,
                                confirmation_required=True, verbose=False,
                                ret_download_path=False):
        """
        Download BBBike OSM data of all available formats for a geographic region.

        :param subregion_name: name of a geographic region (case-insensitive)
        :type subregion_name: str
        :param download_dir: directory where the downloaded file is saved, defaults to ``None``
        :type download_dir: str or None
        :param update: whether to check on update and proceed to update the package data,
            defaults to ``False``
        :type update: bool
        :param confirmation_required: whether to prompt a message for confirmation to proceed,
            defaults to ``True``
        :type confirmation_required: bool
        :param verbose: whether to print relevant information in console as the function runs,
            defaults to ``False``
        :type verbose: bool or int
        :param ret_download_path: whether to return the path(s) to the downloaded file(s),
            defaults to ``False``
        :type ret_download_path: bool
        :return: the path(s) to the downloaded file(s) when ``ret_download_path=True``
        :rtype: list or str

        **Example**::

            >>> import os
            >>> import shutil
            >>> from pydriosm.downloader import BBBikeDownloader, cd_dat_bbbike

            >>> bbbike_downloader = BBBikeDownloader()

            >>> sr_name = 'london'

            >>> bbbike_downloader.download_subregion_data(sr_name, verbose=True)
            Confirm to download all available BBBike OSM data of London? [No]|Yes: yes
            Downloading in progress London ...
                London.osm.pbf ...
                London.osm.gz ...
                London.osm.shp.zip ...
                London.osm.garmin-onroad-latin1.zip ...
                London.osm.garmin-onroad.zip ...
                London.osm.garmin-opentopo.zip ...
                London.osm.garmin-osm.zip ...
                London.osm.geojson.xz ...
                London.osm.svg-osm.zip ...
                London.osm.mapsforge-osm.zip ...
                London.osm.navit.zip ...
                London.osm.csv.xz ...
                London.poly ...
                CHECKSUM.txt ...
            Done. Check out the requested OSM data at dat_BBBike\\London.

            # Delete the download directory generated above
            >>> shutil.rmtree(cd_dat_bbbike())

            >>> sr_name = 'leeds'
            >>> dwnld_dir = "tests"

            >>> dwnld_paths = bbbike_downloader.download_subregion_data(sr_name, dwnld_dir,
            ...                                                         verbose=True,
            ...                                                         ret_download_path=True)
            Confirm to download all available BBBike OSM data of Leeds? [No]|Yes: yes
            Downloading in progress Leeds ...
                Leeds.osm.pbf ...
                Leeds.osm.gz ...
                Leeds.osm.shp.zip ...
                Leeds.osm.garmin-onroad-latin1.zip ...
                Leeds.osm.garmin-onroad.zip ...
                Leeds.osm.garmin-opentopo.zip ...
                Leeds.osm.garmin-osm.zip ...
                Leeds.osm.geojson.xz ...
                Leeds.osm.svg-osm.zip ...
                Leeds.osm.mapsforge-osm.zip ...
                Leeds.osm.navit.zip ...
                Leeds.osm.csv.xz ...
                Leeds.poly ...
                CHECKSUM.txt ...
            Done. Check out the requested OSM data at tests\\Leeds.

            >>> for dwnld_path in dwnld_paths: print(os.path.relpath(dwnld_path))
            tests\\Leeds\\Leeds.osm.pbf
            tests\\Leeds\\Leeds.osm.gz
            tests\\Leeds\\Leeds.osm.shp.zip
            tests\\Leeds\\Leeds.osm.garmin-onroad-latin1.zip
            tests\\Leeds\\Leeds.osm.garmin-onroad.zip
            tests\\Leeds\\Leeds.osm.garmin-opentopo.zip
            tests\\Leeds\\Leeds.osm.garmin-osm.zip
            tests\\Leeds\\Leeds.osm.geojson.xz
            tests\\Leeds\\Leeds.osm.svg-osm.zip
            tests\\Leeds\\Leeds.osm.mapsforge-osm.zip
            tests\\Leeds\\Leeds.osm.navit.zip
            tests\\Leeds\\Leeds.osm.csv.xz
            tests\\Leeds\\Leeds.poly
            tests\\Leeds\\CHECKSUM.txt

            # Delete the download directory generated above
            >>> shutil.rmtree(os.path.dirname(dwnld_path))
        """

        subregion_name_ = self.validate_input_subregion_name(subregion_name)
        bbbike_download_dictionary = self.get_download_dictionary()['Catalogue']
        sub_download_catalogue = bbbike_download_dictionary[subregion_name_]

        data_dir = validate_input_data_dir(download_dir) if download_dir \
            else cd_dat_bbbike(subregion_name_, mkdir=True)

        if confirmed("Confirm to download all available BBBike OSM data of {}?".format(
                subregion_name_), confirmation_required=confirmation_required):

            if verbose:
                print("Downloading in progress {} ... ".format(subregion_name_))

            download_paths = []

            for download_url, osm_filename in zip(sub_download_catalogue.URL,
                                                  sub_download_catalogue.Filename):
                try:
                    path_to_file = os.path.join(
                        data_dir, "" if not download_dir else subregion_name_, osm_filename)

                    if os.path.isfile(path_to_file) and not update:
                        if verbose:
                            print("\t\"{}\" is already available.".format(
                                os.path.basename(path_to_file)))

                    else:
                        print("\t{} ... ".format(osm_filename)) if verbose else ""

                        download_file_from_url(download_url, path_to_file)

                        # if os.path.getsize(path_to_file) / (1024 ** 2) <= 5:
                        #     time.sleep(5)

                    download_paths.append(path_to_file)

                except Exception as e:
                    print("Failed. {}.".format(e))

            if verbose and download_paths:
                print("Done. Check out the requested OSM data at {}.".format(
                    os.path.relpath(os.path.dirname(download_paths[0]))))

            if ret_download_path:
                return download_paths
