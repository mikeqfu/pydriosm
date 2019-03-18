""" BBBike downloads http://download.bbbike.org/osm/bbbike/ """

import os
import re
import time
import urllib.parse
import urllib.request

import bs4
import fuzzywuzzy.process
import pandas as pd

from pydriosm.utils import cd_dat, cd_dat_bbbike, load_pickle, save_pickle
from pydriosm.utils import confirmed, download, regulate_input_data_dir


#
def collect_bbbike_subregion_catalogue(confirmation_required=True):
    """
    :param confirmation_required:
    """
    if confirmed("To collect BBBike subregion catalogue? ", confirmation_required=confirmation_required):
        try:
            home_url = 'http://download.bbbike.org/osm/bbbike/'
            bbbike_subregion_catalogue = pd.read_html(home_url, header=0, parse_dates=['Last Modified'])[0].drop(0)
            bbbike_subregion_catalogue.Name = bbbike_subregion_catalogue.Name.map(lambda x: x.strip('/'))

            save_pickle(bbbike_subregion_catalogue, cd_dat("BBBike-subregion-catalogue.pickle"))

            bbbike_subregion_names = bbbike_subregion_catalogue.Name.tolist()
            save_pickle(bbbike_subregion_names, cd_dat("BBBike-subregion-name-list.pickle"))

        except Exception as e:
            print("Failed to get the required information ... {}.".format(e))
    else:
        print("The information collection process was not activated. The existing local copy will be loaded instead.")


#
def fetch_bbbike_subregion_catalogue(catalogue_name, update=False):
    """
    :param catalogue_name: [str]
    :param update: [bool]
    :return: [pandas.DataFrame]
    """
    available_catalogue = ("BBBike-subregion-catalogue", "BBBike-subregion-name-list")
    assert catalogue_name in available_catalogue, \
        "'catalogue_name' must be one of the following: \n  \"{}\".".format("\",\n  \"".join(available_catalogue))

    path_to_pickle = cd_dat(catalogue_name + ".pickle")
    if not os.path.isfile(path_to_pickle) or update:
        collect_bbbike_subregion_catalogue(confirmation_required=False)
    try:
        bbbike_subregion_catalogue = load_pickle(path_to_pickle)
        return bbbike_subregion_catalogue
    except Exception as e:
        print(e)


#
def regulate_bbbike_input_subregion_name(subregion_name):
    """
    :param subregion_name: [str]
    :return: [str]
    """
    assert isinstance(subregion_name, str)
    bbbike_subregion_names = fetch_bbbike_subregion_catalogue("BBBike-subregion-name-list")
    subregion_name_, _ = fuzzywuzzy.process.extractOne(subregion_name, bbbike_subregion_names, score_cutoff=50)
    return subregion_name_


#
def collect_bbbike_subregion_download_catalogue(subregion_name, confirmation_required=True):

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

    subregion_name_ = regulate_bbbike_input_subregion_name(subregion_name)
    #
    if confirmed("To collect BBBike download catalogue for \"{}\"? ".format(subregion_name_),
                 confirmation_required=confirmation_required):

        try:
            url = 'https://download.bbbike.org/osm/bbbike/{}/'.format(subregion_name_)

            source = urllib.request.urlopen(url)
            source_soup = bs4.BeautifulSoup(source, 'lxml')
            download_links_class = source_soup.find_all(name='a', attrs={'class': ['download_link', 'small']})

            subregion_downloads_catalogue = pd.DataFrame(parse_dlc(x) for x in download_links_class)
            subregion_downloads_catalogue.columns = ['Filename', 'URL', 'DataType', 'Size', 'LastUpdate']

            path_to_file = cd_dat_bbbike(subregion_name_, subregion_name_ + "-download-catalogue.pickle")
            save_pickle(subregion_downloads_catalogue, path_to_file)

        except Exception as e:
            print("Failed to collect download catalogue for \"{}\". {}".format(subregion_name_, e))
    else:
        print("The information collection process was not activated. The existing local copy will be loaded instead.")


#
def fetch_bbbike_subregion_download_catalogue(subregion_name, update=False, confirmation_required=True):
    """
    :param subregion_name: [str]
    :param update: [bool]
    :param confirmation_required: [bool]
    :return: [pandas.DataFrame] or null
    """
    subregion_name_ = regulate_bbbike_input_subregion_name(subregion_name)
    path_to_file = cd_dat_bbbike(subregion_name_, subregion_name_ + "-download-catalogue.pickle")
    if not os.path.isfile(path_to_file) or update:
        collect_bbbike_subregion_download_catalogue(subregion_name, confirmation_required=confirmation_required)
    try:
        subregion_download_catalogue = load_pickle(path_to_file)
        return subregion_download_catalogue
    except Exception as e:
        print(e)


#
def collect_bbbike_download_catalogue(confirmation_required=True):
    """
    :param confirmation_required: [bool]
    """
    if confirmed("To collect BBBike download dictionary? ", confirmation_required=confirmation_required):
        try:
            bbbike_subregion_names = fetch_bbbike_subregion_catalogue("BBBike-subregion-name-list", update=True)
            download_catalogue = [
                fetch_bbbike_subregion_download_catalogue(subregion_name, update=True, confirmation_required=False)
                for subregion_name in bbbike_subregion_names]

            subregion_name, subregion_download_catalogue = bbbike_subregion_names[0], download_catalogue[0]

            # Available file formats
            file_fmt = [re.sub('{}|CHECKSUM'.format(subregion_name), '', f)
                        for f in subregion_download_catalogue.Filename]
            save_pickle(file_fmt[:-2], cd_dat("BBBike-osm-file-formats.pickle"))

            # Available data types
            data_typ = subregion_download_catalogue.DataType.tolist()
            save_pickle(data_typ[:-2], cd_dat("BBBike-osm-data-types.pickle"))

            # available_file_formats = dict(zip(file_fmt, file_ext))

            downloads_dictionary = dict(zip(bbbike_subregion_names, download_catalogue))
            save_pickle(downloads_dictionary, cd_dat("BBBike-download-catalogue.pickle"))
        except Exception as e:
            print("Failed to collect BBBike download dictionary. {}".format(e))
    else:
        print("The information collection process was not activated. The existing local copy will be loaded instead.")


#
def fetch_bbbike_download_catalogue(catalogue_name, update=False):
    """
    :param catalogue_name [str]
    :param update: [bool]
    :return: [dict] or null
    """
    available_catalogue = ("BBBike-download-catalogue", "BBBike-osm-file-formats", "BBBike-osm-data-types")
    assert catalogue_name in available_catalogue, \
        "'catalogue_name' must be one of the following: \n  \"{}\".".format("\",\n  \"".join(available_catalogue))

    path_to_file = cd_dat(catalogue_name + ".pickle")
    if not os.path.isfile(path_to_file) or update:
        collect_bbbike_download_catalogue(confirmation_required=True)
    try:
        bbbike_downloads_dictionary = load_pickle(path_to_file)
        return bbbike_downloads_dictionary
    except Exception as e:
        print(e)


def regulate_bbbike_input_osm_file_format(osm_file_format):
    """
    :param osm_file_format: [str]
    :return: [str]
    """
    assert isinstance(osm_file_format, str)
    bbbike_osm_file_formats = fetch_bbbike_download_catalogue("BBBike-osm-file-formats")
    try:
        osm_file_format_ = fuzzywuzzy.process.extractOne(osm_file_format, bbbike_osm_file_formats, score_cutoff=90)
        if not osm_file_format_:
            print("The input 'osm_file_format' was too vague. ", end="")
            print("It must be one of the following: \n  \"{}\".".format("\",\n  \"".join(bbbike_osm_file_formats)))
        else:
            return osm_file_format_[0]
    except Exception as e:
        print(e)


#
def get_bbbike_subregion_download_url(subregion_name, osm_file_format):
    """
    :param subregion_name: [str]
    :param osm_file_format: [str]
    :return: [tuple] ([str], [str])
    """
    subregion_name_ = regulate_bbbike_input_subregion_name(subregion_name)
    osm_file_format_ = regulate_bbbike_input_osm_file_format(osm_file_format)
    bbbike_download_dictionary = fetch_bbbike_download_catalogue("BBBike-download-catalogue")
    sub_download_catalogue = bbbike_download_dictionary[subregion_name_]
    del bbbike_download_dictionary

    url = sub_download_catalogue[sub_download_catalogue.Filename == subregion_name_ + osm_file_format_].URL[0]

    return subregion_name_, url


#
def validate_bbbike_download_info(subregion_name, osm_file_format, download_dir):
    """
    :param subregion_name: [str]
    :param osm_file_format: [str]
    :param download_dir: [str or None]
    :return: [tuple] of length 4 ([str], [str], [str], [str]) subregion name, filename, download url and file path
    """
    subregion_name_, download_url = get_bbbike_subregion_download_url(subregion_name, osm_file_format)
    osm_filename = os.path.basename(download_url)
    if not download_dir:
        # Download the requested OSM file to default directory
        path_to_file = cd_dat_bbbike(subregion_name_, osm_filename)
    else:
        path_to_file = os.path.join(regulate_input_data_dir(download_dir), osm_filename)
    return subregion_name_, osm_filename, download_url, path_to_file


#
def download_bbbike_subregion_osm(*subregion_name, osm_file_format, download_dir=None, update=False,
                                  download_confirmation_required=True):
    """
    :param subregion_name: [str]
    :param osm_file_format: [str]
    :param download_dir: [str or None]
    :param update: [bool]
    :param download_confirmation_required: [bool]
    :return:
    """
    for sub_reg_name in subregion_name:

        subregion_name_, osm_filename, download_url, path_to_file = validate_bbbike_download_info(
            sub_reg_name, osm_file_format, download_dir)

        if os.path.isfile(path_to_file) and not update:
            print("\"{}\" is already available for \"{}\" at: \n\"{}\".\n".format(
                osm_filename, subregion_name_, path_to_file))
        else:
            if confirmed("\nTo download {} data for {}".format(osm_file_format, subregion_name_),
                         confirmation_required=download_confirmation_required):
                try:
                    download(download_url, path_to_file)
                    print("\n\"{}\" has been downloaded for \"{}\", which is now available at \n\"{}\".\n".format(
                        osm_filename, subregion_name_, path_to_file))

                    if os.path.getsize(path_to_file) / (1024 ** 2) <= 5:
                        time.sleep(5)

                except Exception as e:
                    print("\nFailed to download \"{}\". {}.".format(osm_filename, e))
            else:
                print("The downloading process was not activated.")


#
def download_bbbike_subregion_osm_all_files(subregion_name, download_dir=None, download_confirmation_required=True):
    """
    :param subregion_name: [str]
    :param download_dir: [str or None]
    :param download_confirmation_required: [bool]
    """
    subregion_name_ = regulate_bbbike_input_subregion_name(subregion_name)
    bbbike_download_dictionary = fetch_bbbike_download_catalogue("BBBike-download-catalogue")
    sub_download_catalogue = bbbike_download_dictionary[subregion_name_]

    data_dir = cd_dat_bbbike(subregion_name_) if not download_dir else regulate_input_data_dir(download_dir)

    if confirmed("Confirm to download all available BBBike data for \"{}\"?".format(subregion_name_),
                 confirmation_required=download_confirmation_required):
        print("\nStart to download all available OSM data for \"{}\" ... \n".format(subregion_name_))
        for download_url, osm_filename in zip(sub_download_catalogue.URL, sub_download_catalogue.Filename):
            print("\n\n\"{}\" (below): ".format(osm_filename))
            try:
                path_to_file = os.path.join(data_dir, subregion_name_, osm_filename)
                download(download_url, path_to_file)
                # if os.path.getsize(path_to_file) / (1024 ** 2) <= 5:
                #     time.sleep(5)
            except Exception as e:
                print("\nFailed to download \"{}\". {}.".format(osm_filename, e))
        print("\nCheck out the downloaded OSM data for \"{}\" at \"{}\".".format(
            subregion_name_, os.path.join(data_dir, subregion_name_)))
    else:
        print("The downloading process was not activated.")

