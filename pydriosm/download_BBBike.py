""" BBBike downloads http://download.bbbike.org/osm/bbbike/ """

import os
import re
import urllib.parse
import urllib.request

import bs4
import fuzzywuzzy.process
import pandas as pd

from pydriosm.utils import cd_dat, cd_dat_bbbike, confirmed, load_pickle, save_pickle


#
def get_bbbike_subregion_index(update=False):
    """
    :param update: [bool]
    :return: [pandas.DataFrame]
    """
    home_url = 'http://download.bbbike.org/osm/bbbike/'
    path_to_file = cd_dat("BBBike-subregion-index.pickle")
    if os.path.isfile(path_to_file) and not update:
        bbbike_subregion_index = load_pickle(path_to_file)
    else:
        try:
            bbbike_subregion_index = pd.read_html(home_url, header=0, parse_dates=['Last Modified'])[0].drop(0)
            bbbike_subregion_index.Name = bbbike_subregion_index.Name.map(lambda x: x.strip('/'))
            save_pickle(bbbike_subregion_index, path_to_file)
        except Exception as e:
            print("Failed to get BBBike directory index. {}".format(e))
            bbbike_subregion_index = None
    return bbbike_subregion_index


#
def get_bbbike_subregion_downloads_index(subregion_name, update=False, verbose=True):
    """
    :param subregion_name: [str]
    :param update: [bool]
    :param verbose: [bool]
    :return: 
    """
    bbbike_subregion_index = get_bbbike_subregion_index(update=False)
    subregion_name_ = fuzzywuzzy.process.extractOne(subregion_name, bbbike_subregion_index.Name)[0]

    if verbose:
        if subregion_name != subregion_name_:
            print("\"{}\" is not found. \n".format(subregion_name))
        print("Trying to get downloads index for \"{}\" ... ".format(subregion_name_), end="")

    path_to_file = cd_dat_bbbike(subregion_name_, subregion_name_ + "-url-index.pickle")
    if os.path.isfile(path_to_file) and not update:
        subregion_downloads_index = load_pickle(path_to_file)
        if verbose:
            print("Done.")
    else:
        try:
            url = 'https://download.bbbike.org/osm/bbbike/{}/'.format(subregion_name_)

            source = urllib.request.urlopen(url)
            source_soup = bs4.BeautifulSoup(source, 'lxml')
            download_links_class = source_soup.find_all(name='a', attrs={'class': ['download_link', 'small']})

            def parse_dlc(dlc):
                dlc_href = dlc.get('href')  # URL
                filename, download_url = dlc_href.strip('./'), urllib.parse.urljoin(url, dlc_href)
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

            parsed_dlc = [parse_dlc(x) for x in download_links_class]

            col_names = ['File_name', 'Download_URL', 'File_format', 'File_size', 'Last_update']
            subregion_downloads_index = pd.DataFrame(parsed_dlc, columns=col_names)

            if verbose:
                print("Done.")
            save_pickle(subregion_downloads_index, path_to_file)

        except Exception as e:
            print("Failed. \"{}\"".format(subregion_name_, e))
            subregion_downloads_index = None

    return subregion_downloads_index


#
def get_bbbike_downloads_dictionary(update=False):
    path_to_file = cd_dat("BBBike-downloads-dictionary.pickle")
    if os.path.isfile(path_to_file) and not update:
        downloads_dictionary = load_pickle(path_to_file)
    else:
        bbbike_subregion_index = get_bbbike_subregion_index(update=update)
        downloads_index = [get_bbbike_subregion_downloads_index(s, update, verbose=False)
                           for s in bbbike_subregion_index.Name]
        downloads_dictionary = dict(zip(bbbike_subregion_index.Name, downloads_index))
        save_pickle(downloads_dictionary, path_to_file)
    return downloads_dictionary


#
def download_bbbike_subregion_osm_file(subregion_name, file_format=".osm.pbf", update=False):
    bbbike_downloads_dict = get_bbbike_downloads_dictionary(update=False)
    bbbike_subregion_index = get_bbbike_subregion_index(update=False)
    subregion_name_ = fuzzywuzzy.process.extractOne(subregion_name, bbbike_subregion_index.Name, score_cutoff=10)[0]

    subregion_downloads = bbbike_downloads_dict[subregion_name_]

    available_formats = [re.sub('{}|CHECKSUM'.format(subregion_name_), '', f) for f in subregion_downloads.File_name]

    file_fmt, _ = fuzzywuzzy.process.extractOne(file_format, available_formats)
    filename, _, idx = fuzzywuzzy.process.extractOne(file_fmt, subregion_downloads.File_name)
    url, path_to_file = subregion_downloads.Download_URL[idx], cd_dat_bbbike(subregion_name_, filename)

    if os.path.isfile(path_to_file) and not update:
        print("\"{}\" is already available for \"{}\".".format(filename, subregion_name_))
    else:
        if confirmed(prompt="Confirm to download \"{}\"?".format(filename)):
            try:
                urllib.request.urlretrieve(url, path_to_file)
                print("\"{}\" successfully downloaded.".format(filename))
                print("File has been saved to \"{}\"".format(path_to_file))
            except Exception as e:
                print("Downloading \"{}\" failed due to \"{}\".".format(filename, e))


#
def download_bbbike_subregion_osm_all_files(subregion_name):
    bbbike_downloads_dict = get_bbbike_downloads_dictionary(update=False)
    bbbike_subregion_index = get_bbbike_subregion_index(update=False)
    subregion_name_ = fuzzywuzzy.process.extractOne(subregion_name, bbbike_subregion_index.Name, score_cutoff=10)[0]

    subregion_downloads = bbbike_downloads_dict[subregion_name_]

    if confirmed(prompt="Confirm to download all available BBBike files for \"{}\"?".format(subregion_name_)):
        for url, filename in zip(subregion_downloads.Download_URL, subregion_downloads.File_name):
            try:
                print("\"{}\" successfully downloaded.".format(filename))
                urllib.request.urlretrieve(url, cd_dat_bbbike(subregion_name_, filename))
            except Exception as e:
                print("Downloading \"{}\" failed due to \"{}\".".format(filename, e))
        print("All the downloaded files have been saved to \"{}\".".format(cd_dat_bbbike(subregion_name_)))
    else:
        for url, filename in zip(subregion_downloads.Download_URL, subregion_downloads.File_name):
            if confirmed(prompt="Download \"{}\"?".format(filename)):
                try:
                    print("\"{}\" successfully downloaded.".format(filename))
                    urllib.request.urlretrieve(url, cd_dat_bbbike(subregion_name_, filename))
                    print("\"{}\" saved to \"{}\".".format(filename, cd_dat_bbbike(subregion_name_)))
                except Exception as e:
                    print("Downloading \"{}\" failed due to \"{}\".".format(filename, e))
