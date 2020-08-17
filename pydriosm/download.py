""" Download Geofabrik and BBBike data extracts

Data source:

    - Geofabrik: http://download.geofabrik.de/
    - BBBike: http://download.bbbike.org/osm/bbbike/
"""

import copy
import os
import re
import time
import urllib.error
import urllib.parse
import warnings

import bs4
import more_itertools
import numpy as np
import pandas as pd
import requests
from pyhelpers.dir import cd, regulate_input_data_dir
from pyhelpers.ops import confirmed, download_file_from_url, fake_requests_headers, update_nested_dict
from pyhelpers.store import load_pickle, save_pickle
from pyhelpers.text import find_similar_str

from pydriosm.utils import cd_dat, cd_dat_bbbike, cd_dat_geofabrik


class GeoFabrik:

    def __init__(self):
        self.Name = 'OpenStreetMap Data Extracts'
        self.URL = 'http://download.geofabrik.de/'
        self.DownloadIndexURL = urllib.parse.urljoin(self.URL, 'index-v1.json')
        self.ValidFileFormats = [".osm.pbf", ".shp.zip", ".osm.bz2"]
        self.DownloadIndexName = 'GeoFabrik index of all downloads'
        self.SubregionNameList = 'GeoFabrik subregion name list'
        self.ContinentSubregionTableName = 'GeoFabrik continent subregions'
        self.RegionSubregionTier = 'GeoFabrik region-subregion tier'
        self.DownloadCatalogue = 'GeoFabrik downloads catalogue'

    @staticmethod
    def get_subregion_table(url, verbose=False):
        """
        Get a table containing all available URLs for downloading each subregion's OSM data.

        :param url: URL to the web resource
        :type url: str
        :param verbose: whether to print relevant information in console as the function runs, defaults to ``False``
        :type verbose: bool, int
        :return: a table of all available subregions' URLs
        :rtype: pandas.DataFrame, None

        **Example**::

            from download import GeoFabrik

            geofabrik = GeoFabrik()

            verbose = True
            url = 'https://download.geofabrik.de/europe/great-britain.html'

            subregion_table = geofabrik.get_subregion_table(url, verbose)
            print(subregion_table)
        """

        try:
            subregion_table = pd.read_html(url, match=re.compile(r'(Special )?Sub[ \-]Regions?'), encoding='UTF-8')
            subregion_table = pd.DataFrame(pd.concat(subregion_table, axis=0, ignore_index=True))

            # Specify column names
            file_types = ['.osm.pbf', '.shp.zip', '.osm.bz2']
            column_names = ['Subregion'] + file_types
            column_names.insert(2, '.osm.pbf.Size')

            # Add column/names
            if len(subregion_table.columns) == 4:
                subregion_table.insert(2, '.osm.pbf.Size', np.nan)
            subregion_table.columns = column_names

            subregion_table.replace({'.osm.pbf.Size': {re.compile('[()]'): '', re.compile('\xa0'): ' '}}, inplace=True)

            # Get the URLs
            source = requests.get(url, headers=fake_requests_headers())
            soup = bs4.BeautifulSoup(source.content, 'lxml')
            source.close()

            for file_type in file_types:
                text = '[{}]'.format(file_type)
                urls = [urllib.parse.urljoin(url, link['href']) for link in
                        soup.find_all(name='a', href=True, text=text)]
                subregion_table.loc[subregion_table[file_type].notnull(), file_type] = urls

            try:
                subregion_urls = [urllib.parse.urljoin(url, soup.find('a', text=text).get('href')) for text in
                                  subregion_table.Subregion]
            except (AttributeError, TypeError):
                subregion_urls = [kml['onmouseover'] for kml in soup.find_all('tr', onmouseover=True)]
                subregion_urls = [s[s.find('(') + 1:s.find(')')][1:-1].replace('kml', 'html') for s in subregion_urls]
                subregion_urls = [urllib.parse.urljoin(url, sub_url) for sub_url in subregion_urls]
            subregion_table['SubregionURL'] = subregion_urls

            column_names = list(subregion_table.columns)
            column_names.insert(1, column_names.pop(len(column_names) - 1))
            subregion_table = subregion_table[column_names]

            subregion_table['.osm.pbf.Size'] = \
                subregion_table['.osm.pbf.Size'].str.replace('(', '').str.replace(')', '')

            subregion_table = subregion_table.where(pd.notnull(subregion_table), None)

        except (ValueError, TypeError, ConnectionRefusedError, ConnectionError):
            # No more data available for subregions within the region
            print("Checked out \"{}\".".format(url.split('/')[-1].split('.')[0].title())) if verbose else ""
            subregion_table = None

        return subregion_table

    @staticmethod
    def get_raw_directory_index(url, verbose=False):
        """
        Get a raw directory index (allowing to check logs of older files and their and download links).

        :param url: a URL to the web resource
        :type url: str
        :param verbose: whether to print relevant information in console as the function runs, defaults to ``False``
        :type verbose: bool, int
        :return: a table of raw directory index
        :rtype: pandas.DataFrame, None

        **Examples**::

            from download import GeoFabrik

            geofabrik = GeoFabrik()

            verbose = True

            url = 'https://download.geofabrik.de/europe/great-britain.html'
            raw_directory_index = geofabrik.get_raw_directory_index(url, verbose)
            print(raw_directory_index)

            url = 'http://download.geofabrik.de/'
            raw_directory_index = geofabrik.get_raw_directory_index(url, verbose)
            # The web page does not have a raw directory index.
        """

        try:
            raw_directory_index = pd.read_html(url, match='file', header=0, parse_dates=['date'])
            raw_directory_index = pd.DataFrame(pd.concat(raw_directory_index, axis=0, ignore_index=True))
            raw_directory_index.columns = [c.title() for c in raw_directory_index.columns]

            # Clean the DataFrame
            import humanfriendly
            raw_directory_index.Size = raw_directory_index.Size.apply(humanfriendly.format_size)
            raw_directory_index.sort_values('Date', ascending=False, inplace=True)
            raw_directory_index.index = range(len(raw_directory_index))

            raw_directory_index['FileURL'] = raw_directory_index.File.map(lambda x: urllib.parse.urljoin(url, x))

        except (urllib.error.HTTPError, TypeError, ValueError):
            if len(urllib.parse.urlparse(url).path) <= 1 and verbose:
                print("The web page does not have a raw directory index.")
            raw_directory_index = None

        return raw_directory_index

    def get_index_of_all_downloads(self, update=False, confirmation_required=True, verbose=False):
        """
        Get the JSON index of all downloads.

        :param update: whether to check on update and proceed to update the package data, defaults to ``False``
        :type update: bool
        :param confirmation_required: whether to prompt a message for confirmation to proceed, defaults to ``True``
        :type confirmation_required: bool
        :param verbose: whether to print relevant information in console as the function runs, defaults to ``False``
        :type verbose: bool, int
        :return: index of all downloads
        :rtype: pandas.DataFrame, None

        **Example**::

            from download import GeoFabrik

            geofabrik = GeoFabrik()

            update = False
            confirmation_required = True
            verbose = False

            download_index = geofabrik.get_index_of_all_downloads()
            print(download_index)
        """

        path_to_download_index = cd_dat(self.DownloadIndexName.replace(" ", "-") + ".pickle")

        if os.path.isfile(path_to_download_index) and not update:
            download_index = load_pickle(path_to_download_index)

        else:
            if confirmed("To get {}?".format(self.DownloadIndexName), confirmation_required=confirmation_required):

                print("Collecting {}".format(self.DownloadIndexName), end=" ... ") if verbose == 2 else ""
                try:
                    import geopandas as gpd
                    download_index_ = gpd.read_file(self.DownloadIndexURL)

                    # Note that '<br />' is contained in all the names of the subregions of Poland
                    download_index_.name = download_index_.name.str.replace('<br />', ' ')

                    urls = download_index_.urls.map(lambda x: pd.DataFrame.from_dict(x, 'index').T)
                    urls_ = pd.concat(urls.values, ignore_index=True)
                    download_index = pd.concat([download_index_, urls_], axis=1)

                    print("Done. ") if verbose == 2 else ""

                    save_pickle(download_index, path_to_download_index, verbose=verbose)

                except Exception as e:
                    print("Failed. {}.".format(e))
                    download_index = None

            else:
                download_index = None
                print("No data of {} is available.".format(self.DownloadIndexName)) if verbose else ""

        return download_index

    def get_continents_subregion_tables(self, update=False, confirmation_required=True, verbose=False):
        """
        Get subregion information for each continent.

        :param update: whether to check on update and proceed to update the package data, defaults to ``False``
        :type update: bool
        :param confirmation_required: whether to prompt a message for confirmation to proceed, defaults to ``True``
        :type confirmation_required: bool
        :param verbose: whether to print relevant information in console as the function runs, defaults to ``False``
        :type verbose: bool, int
        :return: subregion information for each continent
        :rtype: dict, None

        **Example**::

            from download import GeoFabrik

            geofabrik = GeoFabrik()

            update = False
            confirmation_required = True
            verbose = False

            subregion_tables = geofabrik.get_continents_subregion_tables()
            print(subregion_tables)
            # {'Africa': <data>,
            #  'Antarctica': None,
            #  'Asia': <data>,
            #  'Australia and Oceania': <data>,
            #  'Central America': <data>,
            #  'Europe': <data>,
            #  'North America': <data>,
            #  'South America': <data>}
        """

        path_to_pickle = cd_dat(self.ContinentSubregionTableName.replace(" ", "-") + ".pickle")

        if os.path.isfile(path_to_pickle) and not update:
            subregion_tables = load_pickle(path_to_pickle)

        else:
            if confirmed("To collect information of {}?".format(self.ContinentSubregionTableName),
                         confirmation_required=confirmation_required):

                if verbose == 2:
                    print("Collecting a table of {}".format(self.ContinentSubregionTableName), end=" ... ")

                try:
                    # Scan the homepage to collect information about subregions for each continent
                    source = requests.get(self.URL, headers=fake_requests_headers())
                    soup = bs4.BeautifulSoup(source.text, 'lxml').find_all('td', {'class': 'subregion'})
                    source.close()
                    continent_names = [td.a.text for td in soup]
                    continent_links = [urllib.parse.urljoin(self.URL, td.a['href']) for td in soup]
                    subregion_tables = dict(
                        zip(continent_names, [self.get_subregion_table(url, verbose) for url in continent_links]))

                    print("Done. ") if verbose == 2 else ""

                    save_pickle(subregion_tables, path_to_pickle, verbose=verbose)

                except Exception as e:
                    print("Failed. {}.".format(e))
                    subregion_tables = None

            else:
                subregion_tables = None
                if verbose:
                    print("No data of {} is available.".format(self.ContinentSubregionTableName))

        return subregion_tables

    def get_region_subregion_tier(self, update=False, confirmation_required=True, verbose=False):
        """
        Get a catalogue of region-subregion tier (incl. all regions having no subregions).

        :param update: whether to check on update and proceed to update the package data, defaults to ``False``
        :type update: bool
        :param confirmation_required: whether to prompt a message for confirmation to proceed, defaults to ``True``
        :type confirmation_required: bool
        :param verbose: whether to print relevant information in console as the function runs, defaults to ``False``
        :type verbose: bool, int
        :return: region-subregion tier (as a dict) and all that have no subregions (as a list)
        :rtype: tuple

        **Example**::

            from download import GeoFabrik

            geofabrik = GeoFabrik()

            update = False
            confirmation_required = True
            verbose = False

            region_subregion_tier, non_subregions_list = geofabrik.get_region_subregion_tier()
            print(region_subregion_tier)
            # <dict of region-subregion tier>
            print(non_subregions_list)
            # <list of all that have no subregions>
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
                :return: a dictionary of region-subregion, and a list of (sub)regions without subregions
                :rtype: dict

                **Example**::

                    sub_reg_tbls = subregion_tables.copy()
                """

                having_subregions = sub_reg_tbls.copy()
                region_subregion_tiers = having_subregions.copy()

                non_subregions_list = []
                for k, v in sub_reg_tbls.items():
                    if v is not None and isinstance(v, pd.DataFrame):
                        region_subregion_tiers = update_nested_dict(sub_reg_tbls, {k: set(v.Subregion)})
                    else:
                        non_subregions_list.append(k)

                for x in non_subregions_list:
                    having_subregions.pop(x)

                having_subregions_temp = copy.deepcopy(having_subregions)

                while having_subregions_temp:

                    for region_name, subregion_table in having_subregions.items():
                        subregion_names, subregion_links = subregion_table.Subregion, subregion_table.SubregionURL
                        sub_subregion_tables = dict(
                            zip(subregion_names, [self.get_subregion_table(link) for link in subregion_links]))

                        subregion_index, without_subregion_ = compile_region_subregion_tier(sub_subregion_tables)
                        non_subregions_list += without_subregion_

                        region_subregion_tiers.update({region_name: subregion_index})

                        having_subregions_temp.pop(region_name)

                # Russian Federation in both pages of Asia and Europe, so there are duplicates in non_subregions_list
                non_subregions_list = list(more_itertools.unique_everseen(non_subregions_list))
                return region_subregion_tiers, non_subregions_list

            if confirmed("To compile {}? (Note this may take up to a few minutes.)".format(self.RegionSubregionTier),
                         confirmation_required=confirmation_required):

                print("Compiling {} ... ".format(self.RegionSubregionTier), end="") if verbose == 2 else ""

                # Scan the downloading pages to collect a catalogue of region-subregion tier
                try:
                    subregion_tables = self.get_continents_subregion_tables(update=update)
                    region_subregion_tier, non_subregions = compile_region_subregion_tier(subregion_tables)

                    print("Done. ") if verbose == 2 else ""

                    save_pickle((region_subregion_tier, non_subregions), path_to_file, verbose=verbose)

                except Exception as e:
                    print("Failed. {}.".format(e))
                    region_subregion_tier, non_subregions = None, None

            else:
                region_subregion_tier, non_subregions = None, None
                print("No data of {} is available.".format(self.RegionSubregionTier)) if verbose else ""

        return region_subregion_tier, non_subregions

    def get_subregion_downloads_catalogue(self, update=False, confirmation_required=True, verbose=False):
        """
        Get a catalogues for subregion downloads.

        :param update: whether to check on update and proceed to update the package data, defaults to ``False``
        :type update: bool
        :param confirmation_required: whether to prompt a message for confirmation to proceed, defaults to ``True``
        :type confirmation_required: bool
        :param verbose: whether to print relevant information in console as the function runs, defaults to ``False``
        :type verbose: bool, int
        :return: a catalogues for subregion downloads
        :rtype: pandas.DataFrame, None

        **Example**::

            from download import GeoFabrik

            geofabrik = GeoFabrik()

            update = False
            confirmation_required = True
            verbose = False

            subregion_downloads_catalogue = geofabrik.get_subregion_downloads_catalogue()
            print(subregion_downloads_catalogue)
        """

        path_to_downloads_catalogue = cd_dat(self.DownloadCatalogue.replace(" ", "-") + ".pickle")

        if os.path.isfile(path_to_downloads_catalogue) and not update:
            subregion_downloads_catalogue = load_pickle(path_to_downloads_catalogue)

        else:
            if confirmed("To collect {}? (Note that it may take a few minutes.)".format(self.DownloadCatalogue),
                         confirmation_required=confirmation_required):

                print("Collecting {}".format(self.DownloadCatalogue), end=" ... ") if verbose == 2 else ""
                try:
                    source = requests.get(self.URL, headers=fake_requests_headers())
                    soup = bs4.BeautifulSoup(source.text, 'lxml')
                    source.close()
                    # avail_subregions = [td.a.text for td in soup.find_all('td', {'class': 'subregion'})]
                    subregion_href = soup.find_all('td', {'class': 'subregion'})
                    avail_subregion_urls = (urllib.parse.urljoin(self.URL, td.a['href']) for td in subregion_href)
                    avail_subregion_url_tables_0 = (self.get_subregion_table(sub_url, verbose) for sub_url in
                                                    avail_subregion_urls)
                    avail_subregion_url_tables = [tbl for tbl in avail_subregion_url_tables_0 if tbl is not None]

                    subregion_url_tables = list(avail_subregion_url_tables)

                    while subregion_url_tables:

                        subregion_url_tables_ = []

                        for subregion_url_table in subregion_url_tables:
                            # subregions = list(subregion_url_table.Subregion)
                            subregion_urls = list(subregion_url_table.SubregionURL)
                            subregion_url_tables_0 = [self.get_subregion_table(sr_url, verbose)
                                                      for sr_url in subregion_urls]
                            subregion_url_tables_ += [tbl for tbl in subregion_url_tables_0 if tbl is not None]

                            # (Note that 'Russian Federation' data is available in both 'Asia' and 'Europe')
                            # avail_subregions += subregions
                            # avail_subregion_urls += subregion_urls
                            avail_subregion_url_tables += subregion_url_tables_

                        subregion_url_tables = list(subregion_url_tables_)

                    # All available URLs for downloading
                    home_subregion_url_table = self.get_subregion_table(self.URL)
                    avail_subregion_url_tables.append(home_subregion_url_table)
                    subregion_downloads_catalogue = pd.concat(avail_subregion_url_tables, ignore_index=True)
                    subregion_downloads_catalogue.drop_duplicates(inplace=True)

                    duplicated = subregion_downloads_catalogue[
                        subregion_downloads_catalogue.Subregion.duplicated(keep=False)]
                    if not duplicated.empty:
                        import humanfriendly
                        for i in range(0, 2, len(duplicated)):
                            temp = duplicated.iloc[i:i + 2]
                            size = temp['.osm.pbf.Size'].map(
                                lambda x: humanfriendly.parse_size(x.strip('(').strip(')').replace('\xa0', ' ')))
                            idx = size[size == size.min()].index
                            subregion_downloads_catalogue.drop(idx, inplace=True)
                        subregion_downloads_catalogue.index = range(len(subregion_downloads_catalogue))

                    # Save subregion_index_downloads to local disk
                    save_pickle(subregion_downloads_catalogue, path_to_downloads_catalogue, verbose=verbose)

                except Exception as e:
                    print("Failed. {}.".format(e))
                    subregion_downloads_catalogue = None

            else:
                subregion_downloads_catalogue = None
                print("No data of {} is available.".format(self.DownloadCatalogue)) if verbose else ""

        return subregion_downloads_catalogue

    def get_subregion_name_list(self, update=False, confirmation_required=True, verbose=False):
        """
        Get all region/subregion names.

        :param update: whether to check on update and proceed to update the package data, defaults to ``False``
        :type update: bool
        :param confirmation_required: whether to prompt a message for confirmation to proceed, defaults to ``True``
        :type confirmation_required: bool
        :param verbose: whether to print relevant information in console as the function runs, defaults to ``False``
        :type verbose: bool, int
        :return: region/subregion names
        :rtype: list

        **Example**::

            from download import GeoFabrik

            geofabrik = GeoFabrik()

            update = False
            confirmation_required = True
            verbose = False

            subregion_name_list = geofabrik.get_subregion_name_list()
            print(subregion_name_list)
        """

        path_to_name_list = cd_dat(self.SubregionNameList.replace(" ", "-") + ".pickle")

        if os.path.isfile(path_to_name_list) and not update:
            subregion_name_list = load_pickle(path_to_name_list)

        else:
            if confirmed("To get {}?".format(self.SubregionNameList), confirmation_required=confirmation_required):

                downloads_catalogue = self.get_subregion_downloads_catalogue(update, confirmation_required=False)

                subregion_name_list = downloads_catalogue.Subregion.to_list()

                save_pickle(subregion_name_list, path_to_name_list, verbose=verbose)

            else:
                subregion_name_list = []
                print("No data of {} is available.".format(self.SubregionNameList)) if verbose else ""

        return subregion_name_list

    def regulate_input_subregion_name(self, subregion_name):
        """
        Rectify the input subregion name in order to make it match the available subregion name.

        :param subregion_name: subregion name
        :type subregion_name: str
        :return: default subregion name that matches, or is the most similar to, the input ``subregion_name``
        :rtype: str

        **Examples**::

            from download import GeoFabrik

            geofabrik = GeoFabrik()

            subregion_name = 'london'
            subregion_name_ = geofabrik.regulate_input_subregion_name(subregion_name)
            print(subregion_name_)  # Greater London

            subregion_name = 'https://download.geofabrik.de/europe/great-britain.html'
            subregion_name_ = geofabrik.regulate_input_subregion_name(subregion_name)
            print(subregion_name_)  # Great Britain
        """

        assert isinstance(subregion_name, str)
        # Get a list of available
        subregion_names = self.get_subregion_name_list()
        if os.path.isdir(os.path.dirname(subregion_name)) or urllib.parse.urlparse(subregion_name).path:
            subregion_name_ = find_similar_str(os.path.basename(subregion_name), subregion_names)
        else:
            subregion_name_ = find_similar_str(subregion_name, subregion_names)
        return subregion_name_

    def get_subregion_download_url(self, subregion_name, osm_file_format, update=False, verbose=False):
        """
        Get download URL of a subregion.

        :param subregion_name: name of a subregion (case-insensitive)
        :type subregion_name: str
        :param osm_file_format: file format; valid values include ``".osm.pbf"``, ``".shp.zip"`` and ``".osm.bz2"``
        :type osm_file_format: str
        :param update: whether to check on update and proceed to update the package data, defaults to ``False``
        :type update: bool
        :param verbose: whether to print relevant information in console as the function runs, defaults to ``False``
        :type verbose: bool, int
        :return: name and URL of the subregion
        :rtype: tuple

        **Examples**::

            from download import GeoFabrik

            geofabrik = GeoFabrik()

            update = False
            verbose = False

            subregion_name  = 'london'
            osm_file_format = '.pbf'
            subregion_name_, download_url = geofabrik.get_subregion_download_url(
                subregion_name, osm_file_format)
            print(subregion_name_)
            # Greater London
            print(download_url)
            # http://download.geofabrik.de/europe/great-britain/england/greater-london-latest.osm.pbf

            subregion_name  = 'Great Britain'
            osm_file_format = '.shp'
            subregion_name_, download_url = geofabrik.get_subregion_download_url(subregion_name,
                                                                                 osm_file_format)
            print(subregion_name_)
            # Greater London
            print(download_url)
            # None
        """

        file_format_ = find_similar_str(osm_file_format, self.ValidFileFormats)
        assert file_format_ in self.ValidFileFormats, "'file_format' must be one from {}.".format(self.ValidFileFormats)

        # Get an index of download URLs
        subregion_downloads_index = self.get_subregion_downloads_catalogue(update=update, verbose=verbose)
        subregion_downloads_index.set_index('Subregion', inplace=True)

        subregion_name_ = self.regulate_input_subregion_name(subregion_name)
        if not subregion_name_:
            raise ValueError("The input 'subregion_name' is not identified.\n"
                             "Check if the required subregion exists in the catalogue and retry.")
        else:
            download_url = subregion_downloads_index.loc[subregion_name_, file_format_]  # Get the URL
            return subregion_name_, download_url

    def get_default_osm_filename(self, subregion_name, osm_file_format, update=False):
        """
        Parse the download URL to get default filename for the given subregion name.

        :param subregion_name: name of a subregion (case-insensitive)
        :type subregion_name: str
        :param osm_file_format: file format; valid values include ``".osm.pbf"``, ``".shp.zip"`` and ``".osm.bz2"``
        :type osm_file_format: str
        :param update: whether to check on update and proceed to update the package data, defaults to ``False``
        :type update: bool
        :return: default OSM filename for the ``subregion_name``
        :rtype: str

        **Examples**::

            from download import GeoFabrik

            geofabrik = GeoFabrik()

            update = False
            verbose = False

            subregion_name = 'london'
            osm_file_format = ".osm.pbf"
            subregion_filename = geofabrik.get_default_osm_filename(subregion_name, osm_file_format)
            print(subregion_filename)
            # greater-london-latest.osm.pbf

            subregion_name = 'great britain'
            osm_file_format = ".shp.zip"
            subregion_filename = geofabrik.get_default_osm_filename(subregion_name, osm_file_format)
            # UserWarning: No data of "great-britain.shp.zip" is available for download.
            print(subregion_filename)
            # great-britain.shp.zip
        """

        _, download_url = self.get_subregion_download_url(subregion_name, osm_file_format, update=update)

        if download_url is None:
            subregion_filename = subregion_name.replace(" ", "-").lower() + osm_file_format
            warnings.warn("No data of \"{}\" is available for download.".format(subregion_filename))

        else:
            subregion_filename = os.path.split(download_url)[-1]

        return subregion_filename

    def get_default_path_to_osm_file(self, subregion_name, osm_file_format, mkdir=False, update=False, verbose=False):
        """
        Parse the download URL to specify a path for storing the downloaded file.

        :param subregion_name: name of a subregion (case-insensitive)
        :type subregion_name: str
        :param osm_file_format: file format; valid values include ``".osm.pbf"``, ``".shp.zip"`` and ``".osm.bz2"``
        :type osm_file_format: str
        :param mkdir: whether to create a directory, defaults to ``False``
        :type mkdir: bool
        :param update: whether to check on update and proceed to update the package data, defaults to ``False``
        :type update: bool
        :param verbose: whether to print relevant information in console as the function runs, defaults to ``False``
        :type verbose: bool, int
        :return: default filename of the subregion and default path to the file
        :rtype: tuple

        **Example**::

            from download import GeoFabrik

            geofabrik = GeoFabrik()

            mkdir = False
            update = False
            verbose = False

            subregion_name = 'london'
            osm_file_format = ".osm.pbf"

            default_filename, default_file_path = geofabrik.get_default_path_to_osm_file(subregion_name,
                                                                                         osm_file_format)

            print(default_filename)
            # greater-london-latest.osm.pbf
            print(default_file_path)
            # <pkg dir>\\dat_GeoFabrik\\Europe\\Great Britain\\England\\greater-london-latest.osm.pbf
            """

        subregion_name_, download_url = self.get_subregion_download_url(subregion_name, osm_file_format, update=update)

        if download_url is None:
            if verbose:
                print("{} data is not available for \"{}\"".format(osm_file_format, subregion_name_))

            default_filename, default_file_path = None, None

        else:
            parsed_path = urllib.parse.urlparse(download_url).path.lstrip('/').split('/')

            if len(parsed_path) == 1:
                parsed_path = [subregion_name_] + parsed_path

            subregion_names = self.get_subregion_name_list()
            directory = cd_dat_geofabrik(
                *[find_similar_str(x, subregion_names) if x != 'us' else 'United States' for x in parsed_path[0:-1]],
                mkdir=mkdir)

            default_filename = parsed_path[-1]
            default_file_path = os.path.join(directory, default_filename)

        return default_filename, default_file_path

    def retrieve_names_of_subregions_of(self, *subregion_name, deep=False):
        """
        Retrieve names of all subregions (if available) from the catalogue of region-subregion tier.
        See also [`RNS-1 <https://stackoverflow.com/questions/9807634/>`_].

        :param subregion_name: name of a subregion (case-insensitive)
        :type subregion_name: str, None
        :param deep: whether to get subregion names of the subregions, defaults to ``False``
        :type deep: bool
        :return: list of subregions (if available); if ``subregion_name=None``, all regions that do have subregions
        :rtype: list

        **Examples**::

            from download import GeoFabrik

            geofabrik = GeoFabrik()

            subregion_names = geofabrik.retrieve_names_of_subregions_of()
            print(subregion_names)

            subregion_names = geofabrik.retrieve_names_of_subregions_of('great britain', 'north america')
            print(subregion_names)

            deep = True
            subregion_names = geofabrik.retrieve_names_of_subregions_of('great britain', deep=deep)
            print(subregion_names)
        """

        region_subregion_tier, non_subregions_list = self.get_region_subregion_tier()

        if not subregion_name:
            subregion_names = non_subregions_list

        else:

            def find_subregions(reg_name, reg_sub_idx):
                """
                :param reg_name: name of a region/subregion
                :type reg_name: str
                :param reg_sub_idx:
                :type reg_sub_idx: dict
                :return:
                :rtype: generator object

                **Example**::

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
                res += list(find_subregions(self.regulate_input_subregion_name(region), region_subregion_tier))[0]

            if not deep:
                subregion_names = res
            else:
                check_list = [x for x in res if x not in non_subregions_list]
                if check_list:
                    res_ = list(set(res) - set(check_list))
                    for region in check_list:
                        res_ += self.retrieve_names_of_subregions_of(region)
                else:
                    res_ = res
                del non_subregions_list, region_subregion_tier, check_list

                subregion_names = list(dict.fromkeys(res_))

        return subregion_names

    def make_default_sub_subregion_download_dir(self, subregion_name, osm_file_format, download_dir=None):
        """
        Make a default download directory if the requested data file is not available.

        :param subregion_name: name of a subregion (case-insensitive)
        :type subregion_name: str
        :param osm_file_format: file format; valid values include ``".osm.pbf"``, ``".shp.zip"`` and ``".osm.bz2"``
        :type osm_file_format: str
        :param download_dir: directory for saving the downloaded file(s); if None (default), use the default directory
        :type download_dir: str, None
        :return: default download directory if the requested data file is not available
        :rtype: str

        **Example**::

            from download import GeoFabrik

            geofabrik = GeoFabrik()

            subregion_name = 'great britain'
            osm_file_format = ".shp.zip"
            download_dir = None

            default_download_dir = geofabrik.make_default_sub_subregion_download_dir(subregion_name,
                                                                                     osm_file_format,
                                                                                     download_dir)
            print(default_download_dir)
            # <cwd>\\dat_GeoFabrik\\Europe\\great-britain.shp
        """

        if download_dir is None:
            _, path_to_file_ = self.get_default_path_to_osm_file(subregion_name, osm_file_format=".osm.pbf")
            download_dir = os.path.dirname(path_to_file_)
        else:
            download_dir = ""

        default_sub_dir = subregion_name.replace(" ", "-").lower() + os.path.splitext(osm_file_format)[0]

        default_download_dir = cd_dat_geofabrik(download_dir, default_sub_dir)

        return default_download_dir

    def download_subregion_osm_file(self, *subregion_name, osm_file_format, download_dir=None, update=False,
                                    confirmation_required=True, deep_retry=False, interval_sec=2, verbose=False):
        """
        Download OSM data files.

        :param subregion_name: name of a subregion (case-insensitive)
        :type subregion_name: str
        :param osm_file_format: file format; valid values include ``".osm.pbf"``, ``".shp.zip"`` and ``".osm.bz2"``
        :type osm_file_format: str
        :param download_dir: directory for saving the downloaded file(s); if None (default), use the default directory
        :type download_dir: str, None
        :param update: whether to check on update and proceed to update the package data, defaults to ``False``
        :type update: bool
        :param confirmation_required: whether to prompt a message for confirmation to proceed, defaults to ``True``
        :type confirmation_required: bool
        :param deep_retry: defaults to ``False``
        :type deep_retry: bool
        :param interval_sec: interval (in sec) between downloading two subregions, defaults to ``2``
        :type interval_sec: int, None
        :param verbose: whether to print relevant information in console as the function runs, defaults to ``False``
        :type verbose: bool, int

        **Examples**::

            from download import GeoFabrik

            geofabrik = GeoFabrik()

            download_dir = None
            update = False
            confirmation_required = True
            deep_retry = False
            interval_sec = 5
            verbose = True

            subregion_name = 'rutland'
            osm_file_format = ".osm.pbf"
            geofabrik.download_subregion_osm_file(subregion_name, osm_file_format=osm_file_format,
                                                  verbose=verbose)

            subregion_name = 'great britain'
            osm_file_format = ".shp.zip"
            # (Note this may take a few minutes)
            geofabrik.download_subregion_osm_file(subregion_name, osm_file_format=osm_file_format,
                                                  verbose=verbose)

            subregion_name = 'guernsey-jersey'
            osm_file_format = ".shp.zip"
            geofabrik.download_subregion_osm_file(subregion_name, osm_file_format=osm_file_format,
                                                  verbose=verbose)
        """

        for sub_reg_name in subregion_name:

            # Get download URL
            subregion_name_, download_url = self.get_subregion_download_url(sub_reg_name, osm_file_format)

            if download_url is None:

                if verbose:
                    print("{} data is not available for \"{}\".\nTry downloading "
                          "the data of its subregions instead ...".format(osm_file_format, subregion_name_))

                sub_subregions = self.retrieve_names_of_subregions_of(subregion_name_, deep=deep_retry)

                if sub_subregions == [subregion_name_]:
                    print("No {} data is available for this region/subregion.".format(osm_file_format, subregion_name_))
                    break

                else:
                    if not download_dir:
                        _, path_to_file_ = self.get_default_path_to_osm_file(subregion_name_, ".osm.pbf")
                        download_dir = os.path.dirname(path_to_file_)

                    download_dir_ = self.make_default_sub_subregion_download_dir(subregion_name_, osm_file_format,
                                                                                 download_dir)

                    self.download_subregion_osm_file(*sub_subregions, osm_file_format=osm_file_format,
                                                     download_dir=download_dir_, update=update,
                                                     confirmation_required=confirmation_required, verbose=verbose)
            else:

                if not download_dir:
                    # Download the requested OSM file to default directory
                    osm_filename, path_to_file = self.get_default_path_to_osm_file(subregion_name_, osm_file_format,
                                                                                   mkdir=True)
                else:
                    regulated_dir = regulate_input_data_dir(download_dir)
                    osm_filename = self.get_default_osm_filename(subregion_name_, osm_file_format=osm_file_format)
                    path_to_file = os.path.join(regulated_dir, osm_filename)

                if os.path.isfile(path_to_file) and not update:
                    print("\n\"{}\" for \"{}\" is already available: \"{}\".".format(
                        osm_filename, subregion_name_, os.path.relpath(path_to_file))) if verbose else ""

                else:
                    op = "Updating" if os.path.isfile(path_to_file) else "Downloading"

                    if confirmed("Confirm to download the {} data of \"{}\"?".format(osm_file_format, subregion_name_),
                                 confirmation_required=confirmation_required):

                        print("{} \"{}\"".format(op, osm_filename), end=" ... ") if verbose else ""
                        try:
                            download_file_from_url(download_url, path_to_file)
                            print("Done. ") if verbose else ""
                        except Exception as e:
                            print("Failed. {}.\n".format(e))

                    else:
                        if verbose == 2:
                            print("The {} of \"{}\" has been cancelled.\n".format(op.lower(), osm_filename))

            if interval_sec:
                time.sleep(interval_sec)

    def download_sub_subregion_osm_file(self, *subregion_name, osm_file_format, download_dir=None, update=False,
                                        confirmation_required=True, verbose=False):
        """
        Download OSM data of one (or a sequence of) regions and all its (or their) subregions.

        :param subregion_name: name of a subregion (case-insensitive)
        :type subregion_name: str
        :param osm_file_format: file format; valid values include ``".osm.pbf"``, ``".shp.zip"`` and ``".osm.bz2"``
        :type osm_file_format: str
        :param download_dir: directory for saving the downloaded file(s); if None (default), use the default directory
        :type download_dir: str, None
        :param update: whether to check on update and proceed to update the package data, defaults to ``False``
        :type update: bool
        :param confirmation_required: whether to prompt a message for confirmation to proceed, defaults to ``True``
        :type confirmation_required: bool
        :param verbose: whether to print relevant information in console as the function runs, defaults to ``False``
        :type verbose: bool, int

        **Example**::

            from download import GeoFabrik

            geofabrik = GeoFabrik()

            download_dir = None
            update = False
            confirmation_required = True
            verbose = True

            osm_file_format = ".osm.pbf"
            geofabrik.download_sub_subregion_osm_file('bedfordshire', 'rutland',
                                                      osm_file_format=osm_file_format,
                                                      download_dir=download_dir, update=update,
                                                      confirmation_required=confirmation_required,
                                                      verbose=verbose)
        """

        subregions = self.retrieve_names_of_subregions_of(*subregion_name)

        if confirmed("\nTo download {} data for all the following subregions: \n{}?\n".format(
                osm_file_format, "\n".join(subregions)), confirmation_required=confirmation_required):
            self.download_subregion_osm_file(*subregions, osm_file_format=osm_file_format, download_dir=download_dir,
                                             update=update, confirmation_required=False, verbose=verbose)


class BBBike:

    def __init__(self):
        self.Name = 'BBBike'
        self.URL = 'http://download.bbbike.org/osm/bbbike/'
        self.CatalogueName = 'BBBike subregion catalogue'
        self.SubregionNameList = 'BBBike subregion name list'
        self.DownloadDictName = 'BBBike download dictionary'

    def get_subregion_catalogue(self, update=False, confirmation_required=True, verbose=False):
        """
        Get catalogue for subregions of BBBike data.

        :param update: whether to check on update and proceed to update the package data, defaults to ``False``
        :type update: bool
        :param confirmation_required: whether to prompt a message for confirmation to proceed, defaults to ``True``
        :type confirmation_required: bool
        :param verbose: whether to print relevant information in console as the function runs, defaults to ``False``
        :type verbose: bool, int
        :return: catalogue for subregions of BBBike data
        :rtype: pandas.DataFrame

        **Example**::

            from download import BBBike

            bbbike = BBBike()

            update = False
            confirmation_required = True
            verbose = True

            subregion_catalogue = bbbike.get_subregion_catalogue(update, confirmation_required, verbose)

            print(subregion_catalogue)
        """

        path_to_pickle = cd_dat(self.CatalogueName.replace(" ", "-") + ".pickle")

        if os.path.isfile(path_to_pickle) and not update:
            subregion_catalogue = load_pickle(path_to_pickle)

        else:
            if confirmed("To collect {}?".format(self.CatalogueName), confirmation_required=confirmation_required):

                try:
                    bbbike_subregion_catalogue_ = pd.read_html(self.URL, header=0, parse_dates=['Last Modified'])
                    subregion_catalogue = bbbike_subregion_catalogue_[0].drop(0)
                    subregion_catalogue.Name = subregion_catalogue.Name.map(lambda x: x.strip('/'))

                    save_pickle(subregion_catalogue, path_to_pickle, verbose=verbose)

                except Exception as e:
                    print("Failed. {}.".format(e))
                    subregion_catalogue = None

            else:
                print("No data of \"{}\" is available.".format(self.CatalogueName)) if verbose else ""
                subregion_catalogue = None

        return subregion_catalogue

    def get_subregion_name_list(self, update=False, confirmation_required=True, verbose=False):
        """
        Get all region/subregion names.

        :param update: whether to check on update and proceed to update the package data, defaults to ``False``
        :type update: bool
        :param confirmation_required: whether to prompt a message for confirmation to proceed, defaults to ``True``
        :type confirmation_required: bool
        :param verbose: whether to print relevant information in console as the function runs, defaults to ``False``
        :type verbose: bool, int
        :return: region/subregion names
        :rtype: list

        **Example**::

            from download import BBBike

            bbbike = BBBike()

            update = False
            confirmation_required = True
            verbose = False

            bbbike_subregion_names = bbbike.get_subregion_name_list()
            print(bbbike_subregion_names)
        """

        path_to_name_list = cd_dat(self.SubregionNameList.replace(" ", "-") + ".pickle")

        if os.path.isfile(path_to_name_list) and not update:
            bbbike_subregion_names = load_pickle(path_to_name_list)

        else:
            if confirmed("To get {}?".format(self.SubregionNameList), confirmation_required=confirmation_required):

                subregion_catalogue = self.get_subregion_catalogue(update, confirmation_required=False, verbose=verbose)

                bbbike_subregion_names = subregion_catalogue.Name.to_list()

                save_pickle(bbbike_subregion_names, path_to_name_list, verbose=verbose)

            else:
                bbbike_subregion_names = []
                print("No data of {} is available.".format(self.SubregionNameList)) if verbose else ""

        return bbbike_subregion_names

    def regulate_input_subregion_name(self, subregion_name):
        """
        Regulate input of any ``subregion_name``.

        :param subregion_name: name of a region/subregion
        :type subregion_name: str
        :return: regulated ``subregion_name``
        :rtype: str

        **Example**::

            from download import BBBike

            bbbike = BBBike()

            subregion_name = 'leeds'

            subregion_name_ = bbbike.regulate_input_subregion_name(subregion_name)
            print(subregion_name_)
            # Leeds
        """

        assert isinstance(subregion_name, str)
        bbbike_subregion_names = self.get_subregion_name_list()
        subregion_name_ = find_similar_str(subregion_name, bbbike_subregion_names)
        return subregion_name_

    def get_subregion_download_catalogue(self, subregion_name, confirmation_required=True, verbose=False):
        """
        :param subregion_name: name of a region/subregion
        :type subregion_name: str
        :param confirmation_required: whether to prompt a message for confirmation to proceed, defaults to ``True``
        :type confirmation_required: bool
        :param verbose: whether to print relevant information in console as the function runs, defaults to ``False``
        :type verbose: bool, int

        **Example**::

            from download import BBBike

            bbbike = BBBike()

            confirmation_required = True
            verbose = True

            subregion_name = 'leeds'
            leeds_download_catalogue = bbbike.get_subregion_download_catalogue(subregion_name, verbose=verbose)
            # To collect the download catalogue for "Leeds" [No]|Yes: >? yes
            #     "Leeds" ... Done.

            print(leeds_download_catalogue)
        """

        subregion_name_ = self.regulate_input_subregion_name(subregion_name)

        if confirmed("To collect the download catalogue for \"{}\"".format(subregion_name_),
                     confirmation_required=confirmation_required):

            try:
                print("\t\"{}\" ... ".format(subregion_name_), end="") if verbose else ""

                url = urllib.parse.urljoin(self.URL, subregion_name_ + '/')

                source = requests.get(url, headers=fake_requests_headers())

                import bs4
                source_soup = bs4.BeautifulSoup(source.text, 'lxml')
                download_links_class = source_soup.find_all(name='a', attrs={'class': ['download_link', 'small']})

                def parse_dlc(dlc):
                    dlc_href = dlc.get('href')  # URL
                    filename, download_url = os.path.basename(dlc_href), urllib.parse.urljoin(url, dlc_href)
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

                subregion_download_catalogue = pd.DataFrame(parse_dlc(x) for x in download_links_class)
                subregion_download_catalogue.columns = ['Filename', 'URL', 'DataType', 'Size', 'LastUpdate']

                # path_to_file = cd_dat_bbbike(subregion_name_, subregion_name_ + "-download-catalogue.pickle")
                # save_pickle(subregion_downloads_catalogue, path_to_file, verbose=verbose)
                print("Done. ") if verbose else ""

            except Exception as e_:
                subregion_download_catalogue = None
                print("Failed. {}".format(subregion_name_, e_)) if verbose else ""

            return subregion_download_catalogue

    def get_download_dictionary(self, update=False, confirmation_required=True, verbose=False):
        """
        :param update: whether to check on update and proceed to update the package data, defaults to ``False``
        :type update: bool
        :param confirmation_required: whether to prompt a message for confirmation to proceed, defaults to ``True``
        :type confirmation_required: bool
        :param verbose: whether to print relevant information in console as the function runs, defaults to ``False``
        :type verbose: bool, int
        :return: a list of available formats, a list of available data types and a dictionary of download catalogue
        :rtype: dict

        **Examples**::

            from download import BBBike

            bbbike = BBBike()

            update = False
            confirmation_required = True
            verbose = True

            downloads_dictionary = bbbike.get_download_dictionary(update, confirmation_required, verbose)

            print(downloads_dictionary)
            # {'FileFormat': <list of available formats>,
            #  'DataType': <list of available data types>,
            #  'Catalogue': <dictionary of download catalogue>}
        """

        path_to_pickle = cd_dat(self.DownloadDictName.replace(" ", "-") + ".pickle")

        if os.path.isfile(path_to_pickle) and not update:
            downloads_dictionary = load_pickle(path_to_pickle)

        else:
            if confirmed("To collect {} from the web resource?".format(self.DownloadDictName),
                         confirmation_required=confirmation_required):

                try:
                    bbbike_subregion_names = self.get_subregion_catalogue(verbose=verbose).Name.to_list()

                    print("Collecting {} ... ".format(self.DownloadDictName)) if verbose else ""

                    download_catalogue = [
                        self.get_subregion_download_catalogue(subregion_name, confirmation_required=False,
                                                              verbose=verbose)
                        for subregion_name in bbbike_subregion_names]

                    sr_name, sr_download_catalogue = bbbike_subregion_names[0], download_catalogue[0]

                    # Available file formats
                    file_fmt = [re.sub('{}|CHECKSUM'.format(sr_name), '', f) for f in sr_download_catalogue.Filename]

                    # Available data types
                    data_typ = sr_download_catalogue.DataType.tolist()

                    downloads_dictionary = {'FileFormat': file_fmt[:-2],
                                            'DataType': data_typ[:-2],
                                            'Catalogue': dict(zip(bbbike_subregion_names, download_catalogue))}

                    print("Finished. ") if verbose else ""

                    save_pickle(downloads_dictionary, path_to_pickle, verbose=verbose)

                except Exception as e:
                    print("Failed. {}".format(e))
                    downloads_dictionary = None

            else:
                if verbose:
                    print("No data of \"{}\" is available.".format(self.DownloadDictName))
                downloads_dictionary = None

        return downloads_dictionary

    def regulate_input_osm_file_format(self, osm_file_format):
        """
        :param osm_file_format: format (file extension) of an OSM data
        :type osm_file_format: str
        :return: one of the formats in get_download_dictionary("BBBike-osm-file-formats")
        :rtype: str

        **Example**::

            from download import BBBike

            bbbike = BBBike()

            osm_file_format = 'pbf'

            osm_file_format_ = bbbike.regulate_input_osm_file_format(osm_file_format)

            print(osm_file_format_)
            # .osm.pbf
        """

        assert isinstance(osm_file_format, str)
        bbbike_osm_file_formats = self.get_download_dictionary()['FileFormat']

        try:
            osm_file_format_ = find_similar_str(osm_file_format, bbbike_osm_file_formats)

            if osm_file_format_:
                return osm_file_format_

            else:
                print("The input 'osm_file_format' is too vague. It must be one of the following: \n  \"{}\".".format(
                    "\",\n  \"".join(bbbike_osm_file_formats)))

        except Exception as e:
            print(e)

    def get_download_url(self, subregion_name, osm_file_format):
        """
        :param subregion_name: name of a region/subregion
        :type subregion_name: str
        :param osm_file_format: format (file extension) of an OSM data
        :type osm_file_format: str
        :return: a valid name of ``subregion_name`` and a download URL for the given ``osm_file_format``
        :rtype: tuple

        **Examples**::

            from download import BBBike

            bbbike = BBBike()

            subregion_name = 'leeds'

            osm_file_format = 'pbf'
            subregion_name_, url = bbbike.get_download_url(subregion_name, osm_file_format)
            print(subregion_name_)
            # Leeds
            print(url)
            # http://download.bbbike.org/osm/bbbike/Leeds/Leeds.osm.pbf

            osm_file_format = 'csv.xz'
            subregion_name_, url = bbbike.get_download_url(subregion_name, osm_file_format)
            print(subregion_name_)
            # Leeds
            print(url)
            # http://download.bbbike.org/osm/bbbike/Leeds/Leeds.osm.csv.xz
        """

        subregion_name_ = self.regulate_input_subregion_name(subregion_name)
        osm_file_format_ = self.regulate_input_osm_file_format(osm_file_format)
        bbbike_download_dictionary = self.get_download_dictionary()['Catalogue']
        sub_download_catalogue = bbbike_download_dictionary[subregion_name_]

        url = sub_download_catalogue[sub_download_catalogue.Filename == subregion_name_ + osm_file_format_].URL.iloc[0]

        return subregion_name_, url

    def validate_download_info(self, subregion_name, osm_file_format, download_dir=None):
        """
        :param subregion_name: name of a region/subregion
        :type subregion_name: str
        :param osm_file_format: format (file extension) of an OSM data
        :type osm_file_format: str
        :param download_dir: directory where downloaded OSM file is saved; if ``None`` (default), package data directory
        :type download_dir: str, None
        :return: [tuple] of length 4 ([str], [str], [str], [str]) subregion name, filename, download url and file path

        **Examples**::

            from download import BBBike

            bbbike = BBBike()

            subregion_name = 'leeds'
            osm_file_format = 'pbf'
            download_dir = None

            subregion_name_, osm_filename, download_url, path_to_file = bbbike.validate_download_info(
                subregion_name, osm_file_format, download_dir)

            print(subregion_name_)
            # Leeds

            print(osm_filename)
            # Leeds.osm.pbf

            print(download_url)
            # http://download.bbbike.org/osm/bbbike/Leeds/Leeds.osm.pbf

            print(path_to_file)
            # <working directory>\\dat_BBBike\\Leeds\\Leeds.osm.pbf
        """

        subregion_name_, download_url = self.get_download_url(subregion_name, osm_file_format)
        osm_filename = os.path.basename(download_url)

        if download_dir:
            path_to_file = cd(regulate_input_data_dir(download_dir), osm_filename, mkdir=True)
        else:
            path_to_file = cd_dat_bbbike(subregion_name_, osm_filename)  # default directory of package data

        return subregion_name_, osm_filename, download_url, path_to_file

    def download_osm(self, *subregion_name, osm_file_format, download_dir=None, update=False,
                     confirmation_required=True, verbose=False):
        """
        Download BBBike OSM data of a given format for a sequence of regions/subregions.

        :param subregion_name: name of a region/subregion
        :type subregion_name: str
        :param osm_file_format: format (file extension) of an OSM data
        :type osm_file_format: str
        :param download_dir: directory where downloaded OSM file is saved; if ``None`` (default), package data directory
        :type download_dir: str, None
        :param update: whether to check on update and proceed to update the package data, defaults to ``False``
        :type update: bool
        :param confirmation_required: whether to prompt a message for confirmation to proceed, defaults to ``True``
        :type confirmation_required: bool
        :param verbose:

        **Examples**::

            from download import BBBike

            bbbike = BBBike()

            osm_file_format = 'pbf'
            download_dir = None
            update = False
            confirmation_required = True
            verbose = True

            bbbike.download_osm('leeds', osm_file_format=osm_file_format, verbose=verbose)
            # To download pbf data of Leeds [No]|Yes: >? yes
            # Done.

            bbbike.download_osm('leeds', 'birmingham', osm_file_format=osm_file_format, verbose=verbose)
            # The requested data is already available at dat_BBBike\\Leeds\\Leeds.osm.pbf.
            # To download pbf data of Birmingham [No]|Yes: >? yes
            # Done.
        """

        for sub_reg_name in subregion_name:
            subregion_name_, osm_filename, download_url, path_to_file = self.validate_download_info(
                sub_reg_name, osm_file_format, download_dir)

            if os.path.isfile(path_to_file) and not update:
                if verbose:
                    print("The requested data is already available at {}.".format(os.path.relpath(path_to_file)))

            else:
                if confirmed("To download {} data of {}".format(osm_file_format, subregion_name_),
                             confirmation_required=confirmation_required):
                    try:
                        if verbose:
                            print("Downloading \"{}\" to {}".format(osm_filename, os.path.relpath(path_to_file)),
                                  end=" ... ")

                        download_file_from_url(download_url, path_to_file)

                        print("Done. ") if verbose else ""

                        if os.path.getsize(path_to_file) / (1024 ** 2) <= 5:
                            time.sleep(5)

                    except Exception as e:
                        print("Failed. {}.".format(e))

                else:
                    print("The downloading process was not activated.") if verbose else ""

    def download_subregion_data(self, subregion_name, download_dir=None, confirmation_required=True, verbose=False):
        """
        Download all available BBBike OSM data (of all available formats) for a region/subregion.

        :param subregion_name: name of a region/subregion
        :type subregion_name: str
        :param download_dir: directory where the downloaded file is saved, defaults to ``None``
        :type download_dir: str, None
        :param confirmation_required: whether to prompt a message for confirmation to proceed, defaults to ``True``
        :type confirmation_required: bool
        :param verbose:

        **Example**::

            from download import BBBike

            bbbike = BBBike()

            subregion_name = 'leeds'
            download_dir = None
            confirmation_required = True
            verbose = True

            bbbike.download_subregion_data(subregion_name, download_dir, confirmation_required, verbose)
            # To download all available BBBike data for "Leeds"? [No]|Yes: >? yes
            # Downloading BBBike OSM data for "Leeds" ...
            #   ...
            # Finished. Check out the downloaded OSM data at dat_BBBike\\Leeds.
        """

        subregion_name_ = self.regulate_input_subregion_name(subregion_name)
        bbbike_download_dictionary = self.get_download_dictionary()['Catalogue']
        sub_download_catalogue = bbbike_download_dictionary[subregion_name_]

        data_dir = regulate_input_data_dir(download_dir) if download_dir else cd_dat_bbbike(subregion_name_)

        if confirmed("To download all available BBBike data for \"{}\"?".format(subregion_name_),
                     confirmation_required=confirmation_required):

            if verbose:
                print("Downloading BBBike OSM data for \"{}\" ... ".format(subregion_name_))

            for download_url, osm_filename in zip(sub_download_catalogue.URL, sub_download_catalogue.Filename):
                try:
                    path_to_file = os.path.join(data_dir, "" if not download_dir else subregion_name_, osm_filename)
                    download_file_from_url(download_url, path_to_file)
                    print("\t{} ... Done.".format(osm_filename)) if verbose else ""
                    # if os.path.getsize(path_to_file) / (1024 ** 2) <= 5:
                    #     time.sleep(5)
                except Exception as e:
                    print("Failed. {}.".format(e)) if verbose else ""

            if verbose:
                print("Finished. Check out the downloaded OSM data at {}.".format(os.path.relpath(cd(data_dir))))

        else:
            print("The downloading process was not activated.") if verbose else ""
