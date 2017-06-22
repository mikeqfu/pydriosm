""" BBBike downloads http://download.bbbike.org/osm/bbbike/ """

import os
import re
import time
from urllib.request import urljoin, urlretrieve

import fuzzywuzzy.process
import progressbar
import pandas as pd

from utils import cdd_osm_dat0, cdd_dat_bbbike, save_pickle, load_pickle


# =========================================================================================
def get_bbbike_subregion_index(url='http://download.bbbike.org/osm/bbbike/', update=False):
    """
    :param url:
    :param update:
    :return: 
    """
    path_to_file = cdd_osm_dat0('BBBike-subregion-index.pickle')
    if os.path.isfile(path_to_file) and not update:
        subregion_index = load_pickle(path_to_file)
    else:
        try:
            subregion_index = pd.read_html(url, header=0, parse_dates=['Last Modified'])[0].drop(0)
            subregion_index.Name = subregion_index.Name.map(lambda x: x.strip('/'))
            save_pickle(subregion_index, path_to_file)
        except Exception as e:
            print("Getting BBBike directory index ... failed due to '{}'".format(e))
            subregion_index = None
    return subregion_index


# ================================================================
def get_bbbike_subregion_downloads_index(subregion, update=False, verbose=True):
    """
    :param subregion: [str]
    :param update: [bool]
    :param verbose: [bool]
    :return: 
    """
    subregion_name = fuzzywuzzy.process.extractOne(subregion, get_bbbike_subregion_index().Name, score_cutoff=10)[0]

    if verbose:
        if subregion != subregion_name:
            print("'{}' is not found. \n".format(subregion))
        print("Trying to get downloads index for '{}' ... ".format(subregion_name), end="")

    path_to_file = cdd_dat_bbbike(subregion_name, subregion_name + "-url-index.pickle")
    if os.path.isfile(path_to_file) and not update:
        subregion_downloads_index = load_pickle(path_to_file)
        if verbose:
            print("Done.")
    else:
        try:
            url = 'http://download.bbbike.org/osm/bbbike/{}/'.format(subregion_name)
            subregion_downloads_index = pd.read_html(url)[0]
            subregion_downloads_index.columns = ['Filename', 'FileSize']
            subregion_downloads_index['URL'] = [urljoin(url, fname) for fname in subregion_downloads_index.Filename]

            # subregion_downloads_index.Filename.iloc[-1] = \
            #     '.'.join([subregion_name, subregion_downloads_index.Filename.iloc[-1]])
            if verbose:
                print("Done.")
            save_pickle(subregion_downloads_index, path_to_file)
        except Exception as e:
            print("Failed due to '{}'".format(subregion_name, e))
            subregion_downloads_index = None

    return subregion_downloads_index


#
def get_bbbike_downloads_dictionary(update=False):
    path_to_file = cdd_osm_dat0("BBBike-downloads-dictionary.pickle")
    if os.path.isfile(path_to_file) and not update:
        downloads_dictionary = load_pickle(path_to_file)
    else:
        subregion_index = get_bbbike_subregion_index()
        downloads_index = [get_bbbike_subregion_downloads_index(s, update, verbose=False) for s in subregion_index.Name]
        downloads_dictionary = dict(zip(subregion_index.Name, downloads_index))
        save_pickle(downloads_dictionary, path_to_file)
    return downloads_dictionary


#
def download_subregion_osm_file(subregion, file_format=".osm.pbf", update=False):

    bbbike_downloads_dict = get_bbbike_downloads_dictionary(update)
    subregion_name = fuzzywuzzy.process.extractOne(subregion, get_bbbike_subregion_index().Name, score_cutoff=10)[0]

    subregion_downloads = bbbike_downloads_dict[subregion_name]

    available_file_formats = [re.sub('{}|CHECKSUM'.format(subregion_name), '', f) for f in subregion_downloads.Filename]

    file_fmt, _ = fuzzywuzzy.process.extractOne(file_format, available_file_formats)
    filename, _, idx = fuzzywuzzy.process.extractOne(file_fmt, subregion_downloads.Filename)
    url, path_to_file = subregion_downloads.URL[idx], cdd_dat_bbbike(subregion_name, filename)

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

    try:
        urlretrieve(url, path_to_file, reporthook=show_progress)
        pbar.finish()
        time.sleep(0.1)
        print("'{}' successfully downloaded.".format(filename))
        print("File has been saved to '{}'".format(path_to_file))
    except Exception as e:
        print("Downloading '{}' failed due to '{}'.".format(filename, e))


#
def download_subregion_osm_files(subregion, update=False):
    bbbike_downloads_dict = get_bbbike_downloads_dictionary(update)
    subregion_name = fuzzywuzzy.process.extractOne(subregion, get_bbbike_subregion_index().Name, score_cutoff=10)[0]

    subregion_downloads = bbbike_downloads_dict[subregion_name]

    for url, filename in zip(subregion_downloads.URL, subregion_downloads.Filename):
        try:
            print("'{}' successfully downloaded.".format(filename))
            urlretrieve(url, cdd_dat_bbbike(subregion_name, filename))
        except Exception as e:
            print("Downloading '{}' failed due to '{}'.".format(filename, e))

    print("Files saved to '{}'.".format(cdd_dat_bbbike(subregion_name)))
