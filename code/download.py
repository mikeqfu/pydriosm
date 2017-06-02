""" Geofabrik Downloads """

import os
import re
from urllib.error import HTTPError
from urllib.request import urlretrieve, urljoin, urlparse

import bs4
import fuzzywuzzy.process
import humanfriendly
import numpy as np
import pandas as pd
import progressbar
import requests

from utils import cdd_osm_dat, save_pickle, load_pickle, save_json


# Get raw directory index (allowing us to see and download older files) ==============================================
def get_raw_directory_index(url):
    """
    :param url: 
    :return: 
    """
    try:
        raw_directory_index = pd.read_html(url, match='file', header=0, parse_dates=['date'])
        raw_directory_index = pd.DataFrame(pd.concat(raw_directory_index, axis=0, ignore_index=True))
        raw_directory_index.columns = [c.title() for c in raw_directory_index.columns]

        # Clean the DataFrame a little bit
        raw_directory_index.Size = raw_directory_index.Size.apply(humanfriendly.format_size)
        raw_directory_index.sort_values('Date', ascending=False, inplace=True)
        raw_directory_index.index = range(len(raw_directory_index))

        raw_directory_index['FileURL'] = raw_directory_index.File.map(lambda x: urljoin(url, x))

    except (HTTPError, TypeError, ValueError):
        raw_directory_index = None
        if len(urlparse(url).path) <= 1:
            print("The home page does not have a raw directory index.")

    return raw_directory_index


# Get a table for a given URL, which contains all available URLs for each subregion and its file downloading =========
def get_subregion_url_table(url):
    """
    :param url: 
    :return: 
    """
    try:
        subregion_table = pd.read_html(url, match=re.compile('(Special )?Sub[ \-]Regions?'), skiprows=[0, 1],
                                       encoding='UTF-8')
        subregion_table = pd.DataFrame(pd.concat(subregion_table, axis=0, ignore_index=True))

        # Specify column names
        file_types = ['.osm.pbf', '.shp.zip', '.osm.bz2']
        column_names = ['Subregion'] + file_types
        column_names.insert(2, '.osm.pbf_Size')

        # Add column/names
        if len(subregion_table.columns) == 4:
            subregion_table.insert(2, '.osm.pbf_Size', np.nan)
        subregion_table.columns = column_names

        subregion_table.replace({'.osm.pbf_Size': {re.compile('[()]'): '', re.compile('\xa0'): ' '}}, inplace=True)

        # Get the URLs
        source = requests.get(url)
        soup = bs4.BeautifulSoup(source.text, 'lxml')
        source.close()

        for file_type in file_types:
            text = '[{}]'.format(file_type)
            urls = [urljoin(url, link['href']) for link in soup.find_all(name='a', href=True, text=text)]
            subregion_table.loc[subregion_table[file_type].notnull(), file_type] = urls

        try:
            subregion_urls = [urljoin(url, soup.find('a', text=text)['href']) for text in subregion_table.Subregion]
        except TypeError:
            subregion_urls = [kml['onmouseover'] for kml in soup.find_all('tr', onmouseover=True)]
            subregion_urls = [s[s.find('(') + 1:s.find(')')][1:-1].replace('kml', 'html') for s in subregion_urls]
            subregion_urls = [urljoin(url, sub_url) for sub_url in subregion_urls]
        subregion_table['SubregionURL'] = subregion_urls

        column_names = list(subregion_table.columns)
        column_names.insert(1, column_names.pop(len(column_names) - 1))
        subregion_table = subregion_table[column_names]  # .fillna(value='')

    except (ValueError, TypeError, ConnectionRefusedError, ConnectionError):
        # No more data available for subregions within the region
        print("Checked out \"{}\".".format(url.split('/')[-1].split('.')[0].title()))
        subregion_table = None

    return subregion_table


# Scan through the downloading pages to get a list of available subregion names ======================================
def scrape_available_subregion_indices():
    home_url = 'http://download.geofabrik.de/'

    try:
        source = requests.get(home_url)
        soup = bs4.BeautifulSoup(source.text, 'lxml')
        avail_subregions = [td.a.text for td in soup.find_all('td', {'class': 'subregion'})]
        avail_subregion_urls = [urljoin(home_url, td.a['href']) for td in soup.find_all('td', {'class': 'subregion'})]
        avail_subregion_url_tables = [get_subregion_url_table(sub_url) for sub_url in avail_subregion_urls]
        avail_subregion_url_tables = [tbl for tbl in avail_subregion_url_tables if tbl is not None]

        subregion_url_tables = list(avail_subregion_url_tables)

        while subregion_url_tables:

            subregion_url_tables_1 = []

            for subregion_url_table in subregion_url_tables:
                subregions = list(subregion_url_table.Subregion)
                subregion_urls = list(subregion_url_table.SubregionURL)
                subregion_url_tables_0 = [get_subregion_url_table(subregion_url) for subregion_url in subregion_urls]
                subregion_url_tables_1 += [tbl for tbl in subregion_url_tables_0 if tbl is not None]

                # (Note that 'Russian Federation' data is available in both 'Asia' and 'Europe')
                avail_subregions += subregions
                avail_subregion_urls += subregion_urls
                avail_subregion_url_tables += subregion_url_tables_1

            subregion_url_tables = list(subregion_url_tables_1)

        # Save a list of available subregions locally
        save_pickle(avail_subregions, cdd_osm_dat("subregion-index.pickle"))

        # Subregion index - {Subregion: URL}
        subregion_url_index = dict(zip(avail_subregions, avail_subregion_urls))
        # Save subregion_index to local disk
        save_pickle(subregion_url_index, cdd_osm_dat("subregion-url-index.pickle"))
        save_json(subregion_url_index, cdd_osm_dat("subregion-url-index.json"))

        # All available URLs for downloading
        home_subregion_url_table = get_subregion_url_table(home_url)
        avail_subregion_url_tables.append(home_subregion_url_table)
        subregion_downloads_index = pd.DataFrame(pd.concat(avail_subregion_url_tables, ignore_index=True))
        subregion_downloads_index.drop_duplicates(inplace=True)

        # Save subregion_index_downloads to loacal disk
        save_pickle(subregion_downloads_index, cdd_osm_dat("subregion-downloads-index.pickle"))
        subregion_downloads_index.set_index('Subregion').to_json(cdd_osm_dat("subregion-downloads-index.json"))

    except Exception as e:
        print(e)


# Get a list of available subregion names ============================================================================
def get_subregion_index(index_filename="subregion-index", update=False):
    """
    :param index_filename: 
    :param update: 
    :return: 
    """
    available_index = ("subregion-index", "subregion-url-index", "subregion-downloads-index")
    if index_filename not in available_index:
        print("Error: 'index_filename' must be chosen from among {}.".format(available_index))
        index = None
    else:
        indices_filename = ["subregion-index.pickle",
                            "subregion-url-index.pickle", "subregion-url-index.json",
                            "subregion-downloads-index.pickle", "subregion-downloads-index.json"]
        paths_to_files_exist = [os.path.isfile(cdd_osm_dat(f)) for f in indices_filename]
        path_to_index_file = cdd_osm_dat(index_filename + ".pickle")
        if all(paths_to_files_exist) and not update:
            index = load_pickle(path_to_index_file)
        else:
            try:
                scrape_available_subregion_indices()
                index = load_pickle(path_to_index_file)
            except Exception as e:
                print("Update failed due to {}. The existing data file would be loaded instead.".format(e))
                index = None
    return index


# Get download URL ===================================================================================================
def get_download_url(subregion, file_format=".osm.pbf", update=False):
    """
    :param subregion: [str] case-insensitive, e.g. 'Greater London'
    :param file_format: '.osm.pbf', '.shp.zip', '.osm.bz2'
    :param update: [bool]
    :return: 
    """
    # Get a list of available
    subregion_index = get_subregion_index('subregion-index', update=update)
    subregion_name = fuzzywuzzy.process.extractOne(subregion, subregion_index, score_cutoff=10)[0]
    # Get an index of download URLs
    subregion_downloads_index = get_subregion_index('subregion-downloads-index', update=update).set_index('Subregion')
    # Get the URL
    download_url = subregion_downloads_index.loc[subregion_name, file_format]
    return subregion_name, download_url


# Parse the download URL so as to specify a path for storing the downloaded file =====================================
def make_file_path(download_url):
    """
    :param download_url: 
    :return: 
    """
    parsed_path = os.path.normpath(urlparse(download_url).path)
    directory = cdd_osm_dat() + os.path.dirname(parsed_path)  # .title()
    filename = os.path.basename(parsed_path)

    if not os.path.exists(directory):
        os.makedirs(directory)
    file_path = os.path.join(directory, filename)

    return filename, file_path


# Download files =====================================================================================================
def download_subregion_osm_file(subregion, file_format=".osm.pbf", update=False):
    """
    :param subregion: 
    :param file_format: '.osm.pbf', '.shp.zip', '.osm.bz2'
    :param update: 
    :return: 
    """
    available_file_formats = ('.osm.pbf', '.shp.zip', '.osm.bz2')
    if file_format not in available_file_formats:
        print("'file_format' must be chosen from among {}.".format(available_file_formats))
    else:
        # Get download URL
        subregion_name, download_url = get_download_url(subregion, file_format)
        # Download the requested OSM file
        filename, file_path = make_file_path(download_url)

        if os.path.isfile(file_path) and not update:
            print("'{}' is already available for {}.".format(filename, subregion_name))
        else:

            # Make a custom bar to show downloading progress --------------------------
            def make_custom_progressbar():
                widgets = [progressbar.Bar(), ' ', progressbar.Percentage(),
                           ' [', progressbar.Timer(), '] ',
                           progressbar.FileTransferSpeed(),
                           ' (', progressbar.ETA(), ') ']
                progress_bar = progressbar.ProgressBar(widgets=widgets)
                return progress_bar

            pbar = make_custom_progressbar()

            def show_progress(block_count, block_size, total_size):
                if pbar.max_value is None:
                    pbar.max_value = total_size
                    pbar.start()
                pbar.update(min(block_count * block_size, total_size))
            # -------------------------------------------------------------------------

            try:
                urlretrieve(download_url, file_path, reporthook=show_progress)
                pbar.finish()
                # time.sleep(0.1)
                print("\n'{}' is downloaded for {}.".format(filename, subregion_name))
            except Exception as e:
                print("\nDownload failed due to '{}'.".format(e))


# Remove the downloaded file =========================================================================================
def remove_subregion_osm_file(subregion, file_format=".osm.pbf"):
    available_file_formats = ('.osm.pbf', '.shp.zip', '.osm.bz2')
    if file_format not in available_file_formats:
        print("'file_format' must be chosen from among {}.".format(available_file_formats))
    else:
        # Get download URL
        subregion_name, download_url = get_download_url(subregion, file_format)
        # Download the requested OSM file
        filename, file_path = make_file_path(download_url)
        if os.path.isfile(file_path):
            os.remove(file_path)
            print("'{}' has been removed.".format(filename))
        else:
            print("The target file, '{}', does not exist.".format(filename))
