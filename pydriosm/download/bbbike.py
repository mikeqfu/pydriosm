""" Download BBBike data extracts

Data source: http://download.bbbike.org/osm/bbbike/
"""

import os
import re
import time
import urllib.parse

import pandas as pd
import requests
from pyhelpers.dir import cd, regulate_input_data_dir
from pyhelpers.ops import confirmed, download_file_from_url, fake_requests_headers
from pyhelpers.store import load_pickle, save_pickle
from pyhelpers.text import find_similar_str

from pydriosm.utils import cd_dat, cd_dat_bbbike


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

            from download.bbbike import BBBike

            bbbike = BBBike()

            update = True
            confirmation_required = True
            verbose = False

            subregion_catalogue = bbbike.get_subregion_catalogue(update, confirmation_required, verbose)
            # To collect BBBike subregion catalogue? [No]|Yes:
            # >? yes

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

            from download.bbbike import BBBike

            bbbike = BBBike()

            update = False
            confirmation_required = True
            verbose = True

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

            from download.bbbike import BBBike

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

            from download.bbbike import BBBike

            bbbike = BBBike()

            confirmation_required = True
            verbose = False

            subregion_name = 'leeds'
            leeds_download_catalogue = bbbike.get_subregion_download_catalogue(subregion_name)
            # To collect the download catalogue for "Leeds" [No]|Yes:
            # >? yes

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

            from download.bbbike import BBBike

            bbbike = BBBike()

            update = False
            confirmation_required = True
            verbose = True

            downloads_dictionary = bbbike.get_download_dictionary(update, confirmation_required, verbose)
            # To collect BBBike download dictionary from the web resource? [No]|Yes:
            # >? yes

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

            from download.bbbike import BBBike

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

            from download.bbbike import BBBike

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

            from download.bbbike import BBBike

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

            from download.bbbike import BBBike

            bbbike = BBBike()

            osm_file_format = 'pbf'
            download_dir = None
            update = False
            confirmation_required = True
            verbose = True

            bbbike.download_osm('leeds', osm_file_format=osm_file_format, verbose=verbose)
            # To download pbf data of Leeds [No]|Yes:
            # >? yes

            bbbike.download_osm('leeds', 'birmingham', osm_file_format=osm_file_format, verbose=verbose)
            # The requested data is already available at dat_BBBike\\Leeds\\Leeds.osm.pbf.
            # To download pbf data of Birmingham [No]|Yes: >? yes
            # >? yes
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

            from download.bbbike import BBBike

            bbbike = BBBike()

            subregion_name = 'leeds'
            download_dir = None
            confirmation_required = True
            verbose = True

            bbbike.download_subregion_data(subregion_name, download_dir, confirmation_required, verbose)
            # To download all available BBBike data for "Leeds"? [No]|Yes:
            # >? yes
            # Downloading BBBike OSM data for "Leeds" ...
            # ...
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
