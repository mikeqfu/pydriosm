""" Geofabrik data extracts http://download.geofabrik.de/ """

import os
import re
import urllib.error
import urllib.parse

import bs4
import fuzzywuzzy.process
import humanfriendly
import numpy as np
import pandas as pd
import requests

from pydriosm.utils import cd_dat, cd_dat_geofabrik, download, load_pickle, save_json, save_pickle


# Get raw directory index (allowing us to see and download older files)
def get_raw_directory_index(url):
    """
    :param url: [str]
    :return: [pandas.DataFrame]
    """
    assert isinstance(url, str)
    if url.endswith('.osm.pbf') or url.endswith('.shp.zip') or url.endswith('.osm.bz2'):
        print("Failed to get the requested information due to invalid input URL.")
        raw_directory_index = None
    else:
        try:
            raw_directory_index = pd.read_html(url, match='file', header=0, parse_dates=['date'])
            raw_directory_index = pd.DataFrame(pd.concat(raw_directory_index, axis=0, ignore_index=True))
            raw_directory_index.columns = [c.title() for c in raw_directory_index.columns]

            # Clean the DataFrame a little bit
            raw_directory_index.Size = raw_directory_index.Size.apply(humanfriendly.format_size)
            raw_directory_index.sort_values('Date', ascending=False, inplace=True)
            raw_directory_index.index = range(len(raw_directory_index))

            raw_directory_index['FileURL'] = raw_directory_index.File.map(lambda x: urllib.parse.urljoin(url, x))

        except (urllib.error.HTTPError, TypeError, ValueError):
            raw_directory_index = None
            if len(urllib.parse.urlparse(url).path) <= 1:
                print("The home page does not have a raw directory index.")

    return raw_directory_index


# Get a table for a given URL, which contains all available URLs for each subregion and its file downloading
def get_subregion_table(url):
    """
    :param url: [str]
    :return: [pandas.DataFrame]
    """
    assert isinstance(url, str)
    if url.endswith('.osm.pbf') or url.endswith('.shp.zip') or url.endswith('.osm.bz2'):
        print("Failed to get the requested information due to invalid input URL.")
        subregion_table = None
    else:
        try:
            subregion_table = pd.read_html(url, match=re.compile(r'(Special )?Sub[ \-]Regions?'), skiprows=[0, 1],
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
                urls = [urllib.parse.urljoin(url, link['href']) for link in
                        soup.find_all(name='a', href=True, text=text)]
                subregion_table.loc[subregion_table[file_type].notnull(), file_type] = urls

            try:
                subregion_urls = [urllib.parse.urljoin(url, soup.find('a', text=text)['href']) for text in
                                  subregion_table.Subregion]
            except TypeError:
                subregion_urls = [kml['onmouseover'] for kml in soup.find_all('tr', onmouseover=True)]
                subregion_urls = [s[s.find('(') + 1:s.find(')')][1:-1].replace('kml', 'html') for s in subregion_urls]
                subregion_urls = [urllib.parse.urljoin(url, sub_url) for sub_url in subregion_urls]
            subregion_table['SubregionURL'] = subregion_urls

            column_names = list(subregion_table.columns)
            column_names.insert(1, column_names.pop(len(column_names) - 1))
            subregion_table = subregion_table[column_names]  # .fillna(value='')

        except (ValueError, TypeError, ConnectionRefusedError, ConnectionError):
            # No more data available for subregions within the region
            print("Checked out \"{}\".".format(url.split('/')[-1].split('.')[0].title()))
            subregion_table = None

    return subregion_table


# Scan through the downloading pages to get a list of available subregion names
def scrape_available_subregion_links():
    home_url = 'http://download.geofabrik.de/'
    try:
        source = requests.get(home_url)
        soup = bs4.BeautifulSoup(source.text, 'lxml')
        avail_subregions = [td.a.text for td in soup.find_all('td', {'class': 'subregion'})]
        avail_subregion_urls = [urllib.parse.urljoin(home_url, td.a['href']) for td in
                                soup.find_all('td', {'class': 'subregion'})]
        avail_subregion_url_tables = [get_subregion_table(sub_url) for sub_url in avail_subregion_urls]
        avail_subregion_url_tables = [tbl for tbl in avail_subregion_url_tables if tbl is not None]

        subregion_url_tables = list(avail_subregion_url_tables)

        while subregion_url_tables:

            subregion_url_tables_1 = []

            for subregion_url_table in subregion_url_tables:
                subregions = list(subregion_url_table.Subregion)
                subregion_urls = list(subregion_url_table.SubregionURL)
                subregion_url_tables_0 = [get_subregion_table(subregion_url) for subregion_url in subregion_urls]
                subregion_url_tables_1 += [tbl for tbl in subregion_url_tables_0 if tbl is not None]

                # (Note that 'Russian Federation' data is available in both 'Asia' and 'Europe')
                avail_subregions += subregions
                avail_subregion_urls += subregion_urls
                avail_subregion_url_tables += subregion_url_tables_1

            subregion_url_tables = list(subregion_url_tables_1)

        # Save a list of available subregions locally
        save_pickle(avail_subregions, cd_dat("GeoFabrik-subregion-name-list.pickle"))

        # Subregion index - {Subregion: URL}
        subregion_url_index = dict(zip(avail_subregions, avail_subregion_urls))
        # Save subregion_index to local disk
        save_pickle(subregion_url_index, cd_dat("GeoFabrik-subregion-name-url-dictionary.pickle"))
        save_json(subregion_url_index, cd_dat("GeoFabrik-subregion-name-url-dictionary.json"))

        # All available URLs for downloading
        home_subregion_url_table = get_subregion_table(home_url)
        avail_subregion_url_tables.append(home_subregion_url_table)
        subregion_downloads_index = pd.DataFrame(pd.concat(avail_subregion_url_tables, ignore_index=True))
        subregion_downloads_index.drop_duplicates(inplace=True)

        # Save subregion_index_downloads to local disk
        save_pickle(subregion_downloads_index, cd_dat("GeoFabrik-subregion-downloads-index.pickle"))
        subregion_downloads_index.set_index('Subregion').to_json(cd_dat("GeoFabrik-subregion-downloads-index.json"))

    except Exception as e:
        print(e)


# Get a list of available subregion names
def get_subregion_info_index(index_filename, file_format=".pickle", update=False):
    """
    :param index_filename: [str] e.g. "GeoFabrik-subregion-name-list"
    :param file_format: [str] ".pickle" (default), or ".json"
    :param update: [bool]
    :return: [pickle] or [json]
    """
    available_index = ["GeoFabrik-subregion-name-list",
                       "GeoFabrik-subregion-name-url-dictionary",
                       "GeoFabrik-subregion-downloads-index"]
    assert index_filename in available_index, "'index_filename' must be one of {}.".format(available_index)

    available_fmt = [".pickle", ".json"]
    assert file_format in available_fmt, "'file_format' must be one of {}.".format(available_fmt)

    indices_filename = ["GeoFabrik-subregion-name-list.pickle",
                        "GeoFabrik-subregion-name-url-dictionary.pickle",
                        "GeoFabrik-subregion-name-url-dictionary.json",
                        "GeoFabrik-subregion-downloads-index.pickle",
                        "GeoFabrik-subregion-downloads-index.json"]
    paths_to_files_exist = [os.path.isfile(cd_dat(f)) for f in indices_filename]
    path_to_info_index_file = cd_dat(index_filename + file_format)
    if all(paths_to_files_exist) and not update:
        index_file = load_pickle(path_to_info_index_file)
    else:
        try:
            scrape_available_subregion_links()
            index_file = load_pickle(path_to_info_index_file)
        except Exception as e:
            print("Failed to update. {}. \n...\nThe existing data file would be loaded instead.".format(e))
            index_file = None
    return index_file


# Get download URL
def get_download_url(subregion_name, file_format=".osm.pbf", update=False):
    """
    :param subregion_name: [str] case-insensitive, e.g. 'Greater London'
    :param file_format: [str] ".osm.pbf" (default), ".shp.zip", or ".osm.bz2"
    :param update: [bool]
    :return: [tuple] of length=2
    """
    available_fmt = [".osm.pbf", ".shp.zip", ".osm.bz2"]
    assert file_format in available_fmt, "'file_format' must be one of {}.".format(available_fmt)

    # Get a list of available
    subregion_names = get_subregion_info_index('GeoFabrik-subregion-name-list', update=update)
    subregion_name_ = fuzzywuzzy.process.extractOne(subregion_name, subregion_names, score_cutoff=10)[0]
    # Get an index of download URLs
    subregion_downloads_index = get_subregion_info_index('GeoFabrik-subregion-downloads-index', update=update)
    subregion_downloads_index.set_index('Subregion', inplace=True)
    # Get the URL
    download_url = subregion_downloads_index.loc[subregion_name_, file_format]
    return subregion_name_, download_url


# Parse the download URL so as to get default filename for the given subregion name
def get_default_filename(subregion_name, file_format=".osm.pbf"):
    """
    :param subregion_name: [str] case-insensitive, e.g. 'greater London', 'london'
    :param file_format: [str] ".osm.pbf" (default), ".shp.zip", or ".osm.bz2"
    :return: [str] Filename
    """
    _, download_url = get_download_url(subregion_name, file_format, update=False)
    subregion_filename = os.path.split(download_url)[-1]
    return subregion_filename


# Parse the download URL so as to specify a path for storing the downloaded file
def make_default_file_path(subregion_name, file_format=".osm.pbf"):
    """
    :param subregion_name: [str] case-insensitive, e.g. 'greater London', 'london'
    :param file_format: [str] ".osm.pbf" (default), ".shp.zip", or ".osm.bz2"
    :return: [tuple] of length=2
    """
    _, download_url = get_download_url(subregion_name, file_format, update=False)
    parsed_path = urllib.parse.urlparse(download_url).path.lstrip('/').split('/')

    subregion_names = get_subregion_info_index('GeoFabrik-subregion-name-list')

    directory = cd_dat_geofabrik(*[fuzzywuzzy.process.extractOne(x, subregion_names)[0] for x in parsed_path[0:-1]])
    filename = parsed_path[-1]

    if not os.path.exists(directory):
        os.makedirs(directory)
    file_path = os.path.join(directory, filename)

    return filename, file_path


# Download files
def download_subregion_osm_file(subregion_name, file_format=".osm.pbf", download_path=None, update=False):
    """
    :param subregion_name: [str] Name of (sub)region, or a local path where the (sub)region file will be saved
    :param file_format: [str] ".osm.pbf" (default), ".shp.zip", or ".osm.bz2"
    :param download_path: [str] Full path to save the downloaded file, or None (default, i.e. using default path)
    :param update: [bool]
    :return: None
    """
    # Get download URL
    subregion_name_, download_url = get_download_url(subregion_name, file_format, update=False)

    if download_path is not None and os.path.isabs(download_path):
        assert download_path.endswith(file_format), "'download_path' is not valid."
        filename, path_to_file = os.path.basename(download_path), download_path
    else:
        # Download the requested OSM file
        filename, path_to_file = make_default_file_path(subregion_name_, file_format)

    if os.path.isfile(path_to_file) and not update:
        print("\"{}\" is already available for \"{}\" at: \n{}.\n".format(filename, subregion_name_, path_to_file))
    else:
        try:
            download(download_url, path_to_file)
            print("\n\"{}\" has been downloaded for \"{}\", which is now available at \n{}".format(
                filename, subregion_name_, path_to_file))
        except Exception as e:
            print("\nFailed to download \"{}\". {}.".format(filename, e))


# Remove the downloaded file
def remove_subregion_osm_file(subregion_file_path):
    """
    :param subregion_file_path: [str]
    :return: None
    """
    assert any(subregion_file_path.endswith(ext) for ext in [".osm.pbf", ".shp.zip", ".osm.bz2"]), \
        "'subregion_file_path' is not valid."
    if os.path.isfile(subregion_file_path):
        os.remove(subregion_file_path)
        print("'{}' has been removed.".format(os.path.basename(subregion_file_path)))
    else:
        print("\"{}\" does not exist at \"{}\".\n".format(*os.path.split(subregion_file_path)[::-1]))
