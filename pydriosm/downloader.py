"""
Download `OpenStreetMap <https://www.openstreetmap.org/>`_ (OSM) data extracts
from the free download servers of
`Geofabrik <https://download.geofabrik.de/>`_ and `BBBike <https://download.bbbike.org/>`_.
"""

import copy
import csv
import io
import os.path
import time
import urllib.error
import urllib.parse
import urllib.request

import bs4
import humanfriendly
import more_itertools
import pandas as pd
import requests
from pyhelpers.dir import validate_input_data_dir
from pyhelpers.ops import confirmed, download_file_from_url, fake_requests_headers, update_nested_dict
from pyhelpers.store import load_pickle, save_pickle

from .utils import *


class InvalidSubregionName(Exception):
    pass


class InvalidFileFormat(Exception):
    pass


def _osm_file_exists(downloader_cls, subregion_name, osm_file_format, data_dir=None, update=False,
                     verbose=False, ret_file_path=False):
    """
    Check if a requested data file of a geographic region already exists locally,
    given its default filename.

    :param downloader_cls: instance of a downloader class
    :type downloader_cls: pydriosm.downloader.GeofabrikDownloader or pydriosm.downloader.BBBikeDownloader
    :param subregion_name: name of a geographic region available on a free download server
    :type subregion_name: str
    :param osm_file_format: file format of the OSM data available on the free download server
    :type osm_file_format: str
    :param data_dir: directory for saving the downloaded file(s);
        if ``None`` (default), the default directory created by the package
    :type data_dir: str or None
    :param update: whether to (check on and) update the data, defaults to ``False``
    :type update: bool
    :param verbose: whether to print relevant information in console, defaults to ``False``
    :type verbose: bool or int
    :param ret_file_path: whether to return the path to the data file (if it exists), defaults to ``False``
    :type ret_file_path: bool
    :return: whether or not the requested data file exists; or the path to the data file
    :rtype: bool or str

    **Test**::

        import os
        from pyhelpers.dir import delete_dir
        from pydriosm.utils import cd_dat_geofabrik
        from pydriosm.downloader import GeofabrikDownloader, BBBikeDownloader, _osm_file_exists

        downloader_cls = GeofabrikDownloader()

        subregion_name = 'london'
        osm_file_format = "pbf"

        downloader_cls.download_osm_data(subregion_name, osm_file_format, verbose=True)
        # Downloading "greater-london-latest.osm.pbf" to "osm_geofabrik\\... ... London\\" ... Done.

        # Check whether the PBF data file exists; `ret_file_path` is by default `False`
        pbf_exists = _osm_file_exists(downloader_cls, subregion_name, osm_file_format)

        type(pbf_exists)
        # bool

        # If the data file exists at the default directory created by the package
        print(pbf_exists)
        # True

        # Set `ret_file_path` to be `True`
        path_to_pbf = _osm_file_exists(downloader_cls, subregion_name, osm_file_format, ret_file_path=True)

        # If the data file exists at the default directory created by the package:
        type(path_to_pbf)
        # str
        print(os.path.relpath(path_to_pbf))
        # osm_geofabrik\\Europe\\Great Britain\\England\\greater-london-latest.osm.pbf

        # Remove the directory or the PBF file and check again:
        delete_dir(cd_dat_geofabrik(), verbose=True)
        The directory "osm_geofabrik\\" is not empty.
        Confirmed to delete it? [No]|Yes: yes
        Deleting "osm_geofabrik\\" ... Done.

        path_to_pbf = _osm_file_exists(downloader_cls, subregion_name, osm_file_format, ret_file_path=True)

        # Since the data file does not exist at the default directory
        type(path_to_pbf)
        # bool

        print(path_to_pbf)
        # False
    """

    subregion_name_ = downloader_cls.validate_input_subregion_name(subregion_name)
    osm_file_format_ = downloader_cls.validate_input_file_format(osm_file_format)

    if downloader_cls.Abbr == 'Geofabrik':  # 'get_default_path_to_osm_file' in dir(downloader_cls):
        default_fn, path_to_file = downloader_cls.get_default_path_to_osm_file(
            subregion_name_, osm_file_format_)
    else:
        _, default_fn, _, path_to_file = downloader_cls.get_valid_download_info(
            subregion_name_, osm_file_format_, data_dir, mkdir=False)

    if default_fn is None:
        if verbose == 2:
            print("{} data for \"{}\" is not available from {} free download server.".format(
                osm_file_format_, subregion_name_, downloader_cls.Abbr))
        file_exists = False

    else:
        if data_dir is not None and downloader_cls.Abbr == 'Geofabrik':
            path_to_file = os.path.join(validate_input_data_dir(data_dir), default_fn)

        if os.path.isfile(path_to_file):
            if verbose == 2 and not update:
                rel_p = os.path.relpath(os.path.dirname(path_to_file))
                print("\"{}\" of {} is available at \"{}\".".format(default_fn, subregion_name_, rel_p))

            if ret_file_path:
                file_exists = path_to_file
            else:
                file_exists = True

        else:
            file_exists = False

    return file_exists


def _file_exists(downloader_cls, subregion_names, osm_file_format, download_dir, update,
                 confirmation_required, verbose):
    """
    Check if a requested data file already exists and compile information for
    :py:meth:`GeofabrikDownloader.download_osm_data()
    <pydriosm.downloader.GeofabrikDownloader.download_osm_data>` and
    :py:meth:`BBBikeDownloader.download_osm_data()
    <pydriosm.downloader.BBBikeDownloader.download_osm_data>`

    :param downloader_cls: instance of a downloader class
    :type downloader_cls: pydriosm.downloader.GeofabrikDownloader or pydriosm.downloader.BBBikeDownloader
    :param subregion_names: name(s) of geographic region(s) available on a free download server
    :type subregion_names: str or list
    :param osm_file_format: file format of the OSM data available on the free download server
    :type osm_file_format: str
    :param download_dir: directory for saving the downloaded file(s)
    :type download_dir: str or None
    :param update: whether to (check on and) update the data
    :type update: bool
    :param verbose: whether to print relevant information in console
    :type verbose: bool or int
    :return: whether or not the requested data file exists; or the path to the data file
    :rtype: tuple

    **Test**::

        from pydriosm.downloader import GeofabrikDownloader, _file_exists

        downloader_cls = GeofabrikDownloader()

        res = _file_exists(
            downloader_cls, subregion_names=['London'], osm_file_format="pbf", download_dir="tests",
            update=False, confirmation_required=True, verbose=True)

        print(res)
        # (['Greater London'], '.osm.pbf', True, 'download', ['Greater London'], [])

        res = _file_exists(
            downloader_cls, subregion_names=['London', 'Rutland'], osm_file_format="pbf",
            download_dir="tests", update=False, confirmation_required=True, verbose=True)

        print(res)
        # (['Greater London', 'Rutland'],
        #  '.osm.pbf',
        #  True,
        #  'download',
        #  ['Greater London', 'Rutland'],
        #  [])
    """

    subregion_names_ = [subregion_names] if isinstance(subregion_names, str) else subregion_names.copy()
    subregion_names_ = [downloader_cls.validate_input_subregion_name(x) for x in subregion_names_]

    osm_file_format_ = downloader_cls.validate_input_file_format(osm_file_format)

    downloads_list_ = subregion_names_.copy()

    existing_file_paths = []  # Paths of existing files

    for subregion_name in subregion_names_:
        path_to_file = _osm_file_exists(
            downloader_cls=downloader_cls, subregion_name=subregion_name, osm_file_format=osm_file_format_,
            data_dir=download_dir, update=update, ret_file_path=True)
        if isinstance(path_to_file, str):
            existing_file_paths.append(path_to_file)
            downloads_list_.remove(subregion_name)
            if verbose:
                osm_filename = os.path.basename(path_to_file)
                rel_path = os.path.relpath(os.path.dirname(path_to_file))
                print("\"{}\" is already available at \"{}\\\".".format(osm_filename, rel_path))

    if not downloads_list_:
        if update:
            confirmation_required_ = True if confirmation_required else False
            update_msg, downloads_list = "update the", subregion_names_.copy()
        else:
            confirmation_required_ = False
            update_msg, downloads_list = "", downloads_list_
    else:
        confirmation_required_ = True if confirmation_required else False
        if len(downloads_list_) == len(subregion_names_) or not update:
            update_msg = "download"
            downloads_list = downloads_list_
        else:
            update_msg = "download/update the"
            downloads_list = subregion_names_.copy()

    ret = (subregion_names_, osm_file_format_, confirmation_required_, update_msg, downloads_list,
           existing_file_paths)

    return ret


def _download_osm_data(download_url, path_to_file, verbose, **kwargs):
    """
    Download an OSM data file.

    :param download_url: a valid URL to an OSM data file
    :type download_url: str
    :param path_to_file: path where the downloaded OSM data file is saved
    :type path_to_file: str
    :param verbose: whether to print relevant information in console
    :type verbose: bool or int
    :param kwargs: optional parameters of `pyhelpers.ops.download_file_from_url()`_

    .. _`pyhelpers.ops.download_file_from_url()`:
        https://pyhelpers.readthedocs.io/en/latest/_generated/pyhelpers.ops.download_file_from_url.html

    **Test**::

        import os
        from pydriosm.downloader import _download_osm_data

        download_url = 'https://download.geofabrik.de/europe/great-britain/england/rutland-latest.osm.pbf'
        path_to_file = "tests\\rutland-latest.osm.pbf"
        verbose = True

        os.path.exists(path_to_file)
        # False

        _download_osm_data(download_url, path_to_file, verbose)
        # Downloading "rutland-latest.osm.pbf" to "tests\" ... Done.

        os.path.isfile(path_to_file)
        # True

        if os.path.isfile(path_to_file):
            os.remove(path_to_file)
    """

    if verbose:
        if os.path.isfile(path_to_file):
            status_msg, prep = "Updating", "at"
        else:
            status_msg, prep = "Downloading", "to"
        rel_path = os.path.relpath(os.path.dirname(path_to_file))
        print("{} \"{}\" {} \"{}\\\"".format(status_msg, os.path.basename(path_to_file), prep, rel_path),
              end="\n" if verbose == 2 else " ... ")

    try:
        download_file_from_url(download_url, path_to_file, verbose=True if verbose == 2 else False, **kwargs)

        if verbose:
            print("Done.")

    except Exception as e:
        if verbose:
            print("Failed. {}.".format(e))


def _download_paths(downloader_cls, download_dir, download_paths):
    """
    Get download path(s).

    :param downloader_cls: instance of a downloader class
    :type downloader_cls: pydriosm.downloader.GeofabrikDownloader or pydriosm.downloader.BBBikeDownloader
    :param downloader_cls:
    :param download_dir: download directory
    :param download_paths: raw path(s) where the download file(s) is (or are)
    :return: path(s) where the download file(s) is (or are)
    :rtype: str or list

    **Test**::

        from pydriosm.downloader import GeofabrikDownloader, _download_paths

        downloader_cls = GeofabrikDownloader()

        download_dir = "tests"

        download_paths = ["tests\\rutland-latest.osm.pbf"]
        _download_paths(downloader_cls, download_dir, download_paths)
        # 'tests\\rutland-latest.osm.pbf'

        download_paths = ["tests\\rutland-latest.osm.pbf", "tests\\greater-london-latest.osm.pbf"]
        _download_paths(downloader_cls, download_dir, download_paths)
        # ['tests\\rutland-latest.osm.pbf', 'tests\\greater-london-latest.osm.pbf']
    """

    if len(download_paths) > 0:
        downloader_cls.DownloadDir = list(dict.fromkeys(os.path.dirname(x) for x in download_paths))
        if len(downloader_cls.DownloadDir) == 1:
            downloader_cls.DownloadDir = downloader_cls.DownloadDir[0]
    else:
        downloader_cls.DownloadDir = validate_input_data_dir(input_data_dir=download_dir)

    if len(download_paths) == 1:
        download_paths = download_paths[0]

    return download_paths


class GeofabrikDownloader:
    """
    Download OSM data from `Geofabrik <https://download.geofabrik.de/>`_ free download server.

    :param download_dir: (a path or a name of) a directory for saving downloaded data files;
        if ``None`` (default), a folder ``osm_geofabrik`` under the current working directory

    :ivar str Name: name of data
    :ivar str Abbr: short name of the data
    :ivar str URL: URL of the homepage to the free download server
    :ivar str DownloadIndexURL: URL of the official download index
    :ivar list ValidFileFormats: valid file formats available on the free download server

    **Example**::

        >>> from pydriosm.downloader import GeofabrikDownloader

        >>> geofabrik_downloader = GeofabrikDownloader()

        >>> print(geofabrik_downloader.Name)
        Geofabrik OpenStreetMap data extracts

        >>> print(geofabrik_downloader.URL)
        https://download.geofabrik.de/
    """

    def __init__(self, download_dir=None):
        """
        Constructor method.
        """
        self.Name = 'Geofabrik OpenStreetMap data extracts'
        self.Abbr = 'Geofabrik'

        self.URL = geofabrik_homepage()

        self.DownloadIndexURL = urllib.parse.urljoin(self.URL, 'index-v1.json')

        self.ValidFileFormats = [".osm.pbf", ".shp.zip", ".osm.bz2"]

        if download_dir is None:
            self.DownloadDir = cd_dat_geofabrik()
        else:
            self.DownloadDir = validate_input_data_dir(input_data_dir=download_dir)

    @staticmethod
    def get_raw_directory_index(url, verbose=False):
        """
        Get a raw directory index.

        This includes logs of older files and their and download URLs.

        :param url: URL to the web page of the homepage or any subregion
        :type url: str
        :param verbose: whether to print relevant information in console, defaults to ``False``
        :type verbose: bool or int
        :return: data of raw directory index
        :rtype: pandas.DataFrame or None

        **Examples**::

            >>> from pydriosm.downloader import GeofabrikDownloader

            >>> geofabrik_downloader = GeofabrikDownloader()

            >>> gb_url = 'https://download.geofabrik.de/europe/great-britain.html'

            >>> raw_dir_idx = geofabrik_downloader.get_raw_directory_index(gb_url)

            >>> type(raw_dir_idx)
            pandas.core.frame.DataFrame
            >>> raw_dir_idx.head()
                                           File  ...                                     FileURL
            0             great-britain-updates  ...  https://download.geofabrik.de/europe/gr...
            1  great-britain-210412.osm.pbf.md5  ...  https://download.geofabrik.de/europe/gr...
            2  great-britain-latest.osm.pbf.md5  ...  https://download.geofabrik.de/europe/gr...
            3                 great-britain.kml  ...  https://download.geofabrik.de/europe/gr...
            4      great-britain-latest.osm.pbf  ...  https://download.geofabrik.de/europe/gr...
            [5 rows x 4 columns]

            >>> gf_url = 'https://download.geofabrik.de/'

            >>> raw_dir_idx = geofabrik_downloader.get_raw_directory_index(gf_url, verbose=True)
            Collecting the raw directory index for the page 'https://download.ge...' ... Failed.
            The web page does not have any raw directory index.
            >>> type(raw_dir_idx)
            NoneType
        """

        if verbose:
            print("Collecting the raw directory index for the page '{}'".format(url), end=" ... ")

        try:
            # noinspection PyTypeChecker
            raw_directory_index = pd.read_html(io=url, match='file', header=0, parse_dates=['date'])
            raw_directory_index = pd.concat(objs=raw_directory_index, ignore_index=True)
            raw_directory_index.columns = [c.title() for c in raw_directory_index.columns]

            # Clean the DataFrame
            raw_directory_index.Size = raw_directory_index.Size.apply(humanfriendly.format_size)
            raw_directory_index.sort_values('Date', ascending=False, inplace=True)
            raw_directory_index.index = range(len(raw_directory_index))

            raw_directory_index['FileURL'] = \
                raw_directory_index.File.map(lambda x: urllib.parse.urljoin(url, x))

            if verbose:
                print("Done.")

        except (urllib.error.HTTPError, TypeError, ValueError):
            if verbose:
                print("Failed.")
                if len(urllib.parse.urlparse(url).path) <= 1:
                    print("The web page does not have any raw directory index.")

            raw_directory_index = None

        return raw_directory_index

    def get_subregion_table(self, url, verbose=False):
        """
        Get download information for all geographic regions on a web page.

        :param url: URL to the web resource
        :type url: str
        :param verbose: whether to print relevant information in console, defaults to ``False``
        :type verbose: bool or int
        :return: a table of all available subregions' URLs
        :rtype: pandas.DataFrame or None

        **Example**::

            >>> from pydriosm.downloader import GeofabrikDownloader

            >>> geofabrik_downloader = GeofabrikDownloader()

            >>> gb_url = 'https://download.geofabrik.de/europe/great-britain.html'

            >>> subregion_tbl = geofabrik_downloader.get_subregion_table(gb_url)

            >>> type(subregion_tbl)
            pandas.core.frame.DataFrame

            >>> subregion_tbl.columns.tolist()
            ['Subregion',
             'SubregionURL',
             '.osm.pbf',
             '.osm.pbf.Size',
             '.shp.zip',
             '.osm.bz2']

            >>> subregion_tbl.head()
              Subregion  ...                                           .osm.bz2
            0   England  ...  https://download.geofabrik.de/europe/great-bri...
            1  Scotland  ...  https://download.geofabrik.de/europe/great-bri...
            2     Wales  ...  https://download.geofabrik.de/europe/great-bri...
            [3 rows x 6 columns]

            >>> a_url = 'https://download.geofabrik.de/antarctica.html'

            >>> subregion_tbl = geofabrik_downloader.get_subregion_table(a_url, verbose=True)
            Collecting download information for "Antarctica" ... Checked out.
            No more subregion data is available on the page 'https://download.geofabrik.de/...'.

            >>> type(subregion_tbl)
            NoneType
        """

        if verbose:
            region_name = url.split('/')[-1].split('.')[0].replace('-', ' ').title()
            print("Collecting download information for \"{}\"".format(region_name), end=" ... ")

        try:
            subregion_table = pd.read_html(
                io=url, match=re.compile(r'(Special )?Sub[ \-]Regions?'), encoding='UTF-8')
            subregion_table = pd.concat(subregion_table, axis=0, ignore_index=True)

            # Specify column names
            column_names = ['Subregion'] + self.ValidFileFormats
            column_names.insert(2, '.osm.pbf.Size')

            # Add column/names
            if len(subregion_table.columns) == 4:
                subregion_table.insert(2, '.osm.pbf.Size', np.nan)

            subregion_table.columns = column_names

            subregion_table.replace(
                {'.osm.pbf.Size': {re.compile('[()]'): '', re.compile('\xa0'): ' '}}, inplace=True)

            # Get the URLs
            source = requests.get(url=url, headers=fake_requests_headers())
            soup = bs4.BeautifulSoup(source.content, 'lxml')
            source.close()

            for file_type in self.ValidFileFormats:
                text = '[{}]'.format(file_type)
                urls = [
                    urllib.parse.urljoin(url, link['href'])
                    for link in soup.find_all(name='a', href=True, text=text)]
                subregion_table.loc[subregion_table[file_type].notnull(), file_type] = urls

            try:
                subregion_urls = [
                    urllib.parse.urljoin(url, soup.find('a', text=text).get('href'))
                    for text in subregion_table.Subregion]

            except (AttributeError, TypeError):
                subregion_urls = [kml['onmouseover'] for kml in soup.find_all('tr', onmouseover=True)]
                subregion_urls = [
                    s[s.find('(') + 1:s.find(')')][1:-1].replace('kml', 'html') for s in subregion_urls]
                subregion_urls = [urllib.parse.urljoin(url, sub_url) for sub_url in subregion_urls]

            subregion_table['SubregionURL'] = subregion_urls

            column_names = list(subregion_table.columns)
            column_names.insert(1, column_names.pop(len(column_names) - 1))
            subregion_table = subregion_table[column_names]

            subregion_table['.osm.pbf.Size'] = \
                subregion_table['.osm.pbf.Size'].str.replace(r'\(|\)', '', regex=True)

            subregion_table = subregion_table.where(pd.notnull(subregion_table), None)

            if verbose:
                print("Done.")

        except (ValueError, TypeError, ConnectionRefusedError, ConnectionError):
            if verbose:
                print("Checked out.")
                print("No more subregion data is available on the page '{}'.".format(url))

            subregion_table = None

        return subregion_table

    def get_download_index(self, update=False, confirmation_required=True, verbose=False):
        """
        Get the formal index of all available downloads.

        :param update: whether to (check on and) update the package data, defaults to ``False``
        :type update: bool
        :param confirmation_required: whether asking for confirmation to proceed, defaults to ``True``
        :type confirmation_required: bool
        :param verbose: whether to print relevant information in console, defaults to ``False``
        :type verbose: bool or int
        :return: the formal index of all downloads
        :rtype: pandas.DataFrame or None

        **Example**::

            >>> from pydriosm.downloader import GeofabrikDownloader

            >>> geofabrik_downloader = GeofabrikDownloader()

            >>> # The formal index of all available downloads
            >>> download_idx = geofabrik_downloader.get_download_index()

            >>> type(download_idx)
            pandas.core.frame.DataFrame

            >>> download_idx.columns.tolist()
            ['id',
             'parent',
             'name',
             'urls',
             'geometry',
             'pbf',
             'bz2',
             'shp',
             'pbf-internal',
             'history',
             'taginfo',
             'updates']

            >>> download_idx.head()
                        id  ...                                            updates
            0  afghanistan  ...  https://download.geofabrik.de/asia/afghanistan...
            1       africa  ...       https://download.geofabrik.de/africa-updates
            2      albania  ...  https://download.geofabrik.de/europe/albania-u...
            3      alberta  ...  https://download.geofabrik.de/north-america/ca...
            4      algeria  ...  https://download.geofabrik.de/africa/algeria-u...
            [5 rows x 12 columns]
        """

        dat_name = ' '.join([self.Abbr, 'index of all downloads'])

        path_to_pickle = cd_dat(dat_name.replace(" ", "-") + ".pickle")

        if os.path.isfile(path_to_pickle) and not update:
            download_index = load_pickle(path_to_pickle)

        else:
            status = ("update the" if os.path.exists(path_to_pickle) else "collect") if update else "collect"

            if confirmed("To {} data of {}\n?".format(status, dat_name),
                         confirmation_required=confirmation_required):

                if verbose:
                    if confirmation_required:
                        status_msg = "Collecting the data"
                    else:
                        status_msg = "Collecting the data of {}".format(dat_name)
                    print(status_msg, end=" ... ")

                try:
                    import geopandas as gpd

                    download_index_ = gpd.read_file(self.DownloadIndexURL)

                    # Note that '<br />' may exist in all the names of Poland' subregions
                    download_index_.name = download_index_.name.str.replace('<br />', ' ')

                    urls = download_index_.urls.map(lambda x: pd.DataFrame.from_dict(x, 'index').T)
                    urls_ = pd.concat(urls.values, ignore_index=True)
                    download_index = pd.concat([download_index_, urls_], axis=1)

                    print("Done.") if verbose else ""

                    save_pickle(download_index, path_to_pickle, verbose=verbose)

                except Exception as e:
                    if verbose:
                        print("Failed. {}.".format(e))
                    download_index = None

            else:
                if verbose == 2:
                    print("No data of {} is available.".format(dat_name))

                download_index = None

        return download_index

    def get_continents_subregion_tables(self, update=False, confirmation_required=True, verbose=False):
        """
        Get download information for continents.

        :param update: whether to (check on and) update the package data, defaults to ``False``
        :type update: bool
        :param confirmation_required: whether asking for confirmation to proceed, defaults to ``True``
        :type confirmation_required: bool
        :param verbose: whether to print relevant information in console, defaults to ``False``
        :type verbose: bool or int
        :return: subregion information for each continent
        :rtype: dict or None

        **Example**::

            >>> from pydriosm.downloader import GeofabrikDownloader

            >>> geofabrik_downloader = GeofabrikDownloader()

            >>> # Information of subregions for each continent
            >>> subregion_tbls = geofabrik_downloader.get_continents_subregion_tables()

            >>> type(subregion_tbls)
            dict

            >>> list(subregion_tbls.keys())
            ['Africa',
             'Antarctica',
             'Asia',
             'Australia and Oceania',
             'Central America',
             'Europe',
             'North America',
             'South America']

            >>> # Information about the data of subregions in Asia
            >>> asia_tbl = subregion_tbls['Asia']

            >>> type(asia_tbl)
            pandas.core.frame.DataFrame

            >>> asia_tbl.head()
                 Subregion  ...                                           .osm.bz2
            0  Afghanistan  ...  https://download.geofabrik.de/asia/afghanistan...
            1      Armenia  ...  https://download.geofabrik.de/asia/armenia-lat...
            2   Azerbaijan  ...  https://download.geofabrik.de/asia/azerbaijan-...
            3   Bangladesh  ...  https://download.geofabrik.de/asia/bangladesh-...
            4       Bhutan  ...  https://download.geofabrik.de/asia/bhutan-late...
            [5 rows x 6 columns]

            >>> asia_tbl.columns.tolist()
            ['Subregion',
             'SubregionURL',
             '.osm.pbf',
             '.osm.pbf.Size',
             '.shp.zip',
             '.osm.bz2']
        """

        dat_name = ' '.join([self.Abbr, 'continent subregions'])

        path_to_pickle = cd_dat(dat_name.replace(" ", "-") + ".pickle")

        if os.path.isfile(path_to_pickle) and not update:
            subregion_tables = load_pickle(path_to_pickle)

        else:
            status = ("update the" if os.path.exists(path_to_pickle) else "collect") if update else "collect"

            if confirmed("To {} data of {}\n?".format(status, dat_name),
                         confirmation_required=confirmation_required):

                if verbose:
                    if confirmation_required:
                        status_msg = "Collecting the data"
                    else:
                        status_msg = "Collecting the data of {}".format(dat_name)
                    print(status_msg, end=" ... ")

                try:
                    # Scan the homepage to collect info of regions for each continent
                    source = requests.get(self.URL, headers=fake_requests_headers())
                    soup = bs4.BeautifulSoup(source.text, 'lxml')
                    tds = soup.find_all('td', {'class': 'subregion'})
                    source.close()
                    continent_names = [td.a.text for td in tds]
                    continent_links = [urllib.parse.urljoin(self.URL, td.a['href']) for td in tds]
                    subregion_tables = dict(zip(
                        continent_names, [self.get_subregion_table(url) for url in continent_links]))

                    if verbose:
                        print("Done.")

                    save_pickle(subregion_tables, path_to_pickle, verbose=verbose)

                except Exception as e:
                    if verbose:
                        print("Failed. {}.".format(e))
                    subregion_tables = None

            else:
                if verbose:
                    print("No data of {} is available.".format(dat_name))

                subregion_tables = None

        return subregion_tables

    def get_region_subregion_tier(self, update=False, confirmation_required=True, verbose=False):
        """
        Get a catalogue of region-subregion tier.

        This includes all geographic regions to which data of subregions is unavailable.

        :param update: whether to (check on and) update the package data, defaults to ``False``
        :type update: bool
        :param confirmation_required: whether asking for confirmation to proceed, defaults to ``True``
        :type confirmation_required: bool
        :param verbose: whether to print relevant information in console, defaults to ``False``
        :type verbose: bool or int
        :return: region-subregion tier (in ``dict`` type) and all that have no subregions (in ``list`` type)
        :rtype: tuple

        .. _`dict`: https://docs.python.org/3/library/stdtypes.html#dict
        .. _`list`: https://docs.python.org/3/library/stdtypes.html#list

        **Example**::

            >>> from pydriosm.downloader import GeofabrikDownloader

            >>> geofabrik_downloader = GeofabrikDownloader()

            >>> # region-subregion tier, and all regions that have no subregions
            >>> rs_tier, ns_list = geofabrik_downloader.get_region_subregion_tier()

            >>> # Keys of the region-subregion tier
            >>> list(rs_tier.keys())
            ['Africa',
             'Antarctica',
             'Asia',
             'Australia and Oceania',
             'Central America',
             'Europe',
             'North America',
             'South America']

            >>> # A sample of five regions that have no subregions
            >>> ns_list[0:5]
            ['Antarctica', 'Algeria', 'Angola', 'Benin', 'Botswana']
        """

        dat_name = ' '.join([self.Abbr, 'region-subregion tier'])

        path_to_pickle = cd_dat(dat_name.replace(" ", "-") + ".pickle")

        if os.path.isfile(path_to_pickle) and not update:
            region_subregion_tier, non_subregions = load_pickle(path_to_pickle, verbose=verbose)

        else:

            def compile_region_subregion_tier(sub_reg_tbls):
                """
                Find out the all regions and their subregions.

                :param sub_reg_tbls: obtained from get_continents_subregion_tables()
                :type sub_reg_tbls: dict
                :return: a dictionary of region-subregion, and a list of (sub)regions without subregions
                :rtype: dict

                **Test**::

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
                        subregion_names = subregion_table.Subregion
                        subregion_links = subregion_table.SubregionURL
                        sub_subregion_tables = dict(zip(
                            subregion_names, [self.get_subregion_table(link) for link in subregion_links]))

                        subregion_index, without_subregion_ = compile_region_subregion_tier(
                            sub_subregion_tables)
                        non_subregions_list += without_subregion_

                        region_subregion_tiers.update({region_name: subregion_index})

                        having_subregions_temp.pop(region_name)

                # Russian Federation in both pages of Asia and Europe,
                # so there are duplicates in non_subregions_list

                non_subregions_list = list(more_itertools.unique_everseen(non_subregions_list))

                return region_subregion_tiers, non_subregions_list

            status = ("update the" if os.path.exists(path_to_pickle) else "compile") if update else "compile"

            if confirmed("To {} {} (Note that this may take up to a few minutes)\n".format(status, dat_name),
                         confirmation_required=confirmation_required):

                if verbose:
                    if confirmation_required:
                        status_msg = "Collecting/compiling the information"
                    else:
                        status_msg = "Collecting/compiling the information of {} " \
                                     "(Note that this may take up to a few minutes)".format(dat_name)
                    print(status_msg, end=" ... ")

                # Scan the download pages to collect a catalogue of region-subregion tier
                try:
                    subregion_tables = self.get_continents_subregion_tables(
                        update=update, confirmation_required=False, verbose=False)
                    region_subregion_tier, non_subregions = compile_region_subregion_tier(subregion_tables)

                    if verbose:
                        print("Done.")

                    save_pickle((region_subregion_tier, non_subregions), path_to_pickle, verbose=verbose)

                except Exception as e:
                    if verbose:
                        print("Failed. {}.".format(e))
                    region_subregion_tier, non_subregions = None, None

            else:
                if verbose:
                    print("No data of {} is available.".format(dat_name))

                region_subregion_tier, non_subregions = None, None

        return region_subregion_tier, non_subregions

    def get_download_catalogue(self, update=False, confirmation_required=True, verbose=False):
        """
        Get a catalogue of download information.

        Similar to the method
        :py:meth:`.get_download_index()<pydriosm.downloader.GeofabrikDownloader.get_download_index>`.

        :param update: whether to (check on and) update the package data, defaults to ``False``
        :type update: bool
        :param confirmation_required: whether asking for confirmation to proceed, defaults to ``True``
        :type confirmation_required: bool
        :param verbose: whether to print relevant information in console, defaults to ``False``
        :type verbose: bool or int
        :return: a catalogue for all subregion downloads
        :rtype: pandas.DataFrame or None

        **Example**::

            >>> from pydriosm.downloader import GeofabrikDownloader

            >>> geofabrik_downloader = GeofabrikDownloader()

            >>> # A download catalogue for all subregions
            >>> downloads_catalogue = geofabrik_downloader.get_download_catalogue()

            >>> type(downloads_catalogue)
            pandas.core.frame.DataFrame

            >>> downloads_catalogue.head()
                  Subregion  ...                                           .osm.bz2
            0       Algeria  ...  https://download.geofabrik.de/africa/algeria-l...
            1        Angola  ...  https://download.geofabrik.de/africa/angola-la...
            2         Benin  ...  https://download.geofabrik.de/africa/benin-lat...
            3      Botswana  ...  https://download.geofabrik.de/africa/botswana-...
            4  Burkina Faso  ...  https://download.geofabrik.de/africa/burkina-f...
            [5 rows x 6 columns]

            >>> downloads_catalogue.columns.tolist()
            ['Subregion',
             'SubregionURL',
             '.osm.pbf',
             '.osm.pbf.Size',
             '.shp.zip',
             '.osm.bz2']
        """

        dat_name = ' '.join([self.Abbr, 'downloads catalogue'])

        path_to_pickle = cd_dat(dat_name.replace(" ", "-") + ".pickle")

        if os.path.isfile(path_to_pickle) and not update:
            subregion_downloads_catalogue = load_pickle(path_to_pickle)

        else:
            status = ("update the" if os.path.exists(path_to_pickle) else "compile") if update else "compile"

            if confirmed("To {} {} (Note that this may take up to a few minutes)\n?".format(status, dat_name),
                         confirmation_required=confirmation_required):

                if verbose:
                    if confirmation_required:
                        status_msg = "Collecting/compiling the information"
                    else:
                        status_msg = "Collecting/compiling the information of {} " \
                                     "(Note that this may take up to a few minutes))".format(dat_name)
                    print(status_msg, end=" ... ")

                try:
                    source = requests.get(self.URL, headers=fake_requests_headers())
                    soup = bs4.BeautifulSoup(source.text, 'lxml')
                    source.close()

                    # avail_subregions = [td.a.text for td in soup.find_all('td', {'class': 'subregion'})]

                    subregion_href = soup.find_all('td', {'class': 'subregion'})

                    avail_subregion_urls = (
                        urllib.parse.urljoin(self.URL, td.a['href']) for td in subregion_href)
                    avail_subregion_url_tables_0 = (
                        self.get_subregion_table(sub_url, verbose=False) for sub_url in avail_subregion_urls)
                    avail_subregion_url_tables = [
                        tbl for tbl in avail_subregion_url_tables_0 if tbl is not None]

                    subregion_url_tables = list(avail_subregion_url_tables)

                    while subregion_url_tables:

                        subregion_url_tables_ = []

                        for subregion_url_table in subregion_url_tables:
                            # subregions = list(subregion_url_table.Subregion)
                            subregion_urls = list(subregion_url_table.SubregionURL)

                            subregion_url_tables_0 = [
                                self.get_subregion_table(sr_url, verbose=False) for sr_url in subregion_urls]

                            subregion_url_tables_ += [
                                tbl for tbl in subregion_url_tables_0 if tbl is not None]

                            # (Note that 'Russian Federation' data is available in both 'Asia' and 'Europe')
                            # avail_subregions += subregions
                            # avail_subregion_urls += subregion_urls
                            avail_subregion_url_tables += subregion_url_tables_

                        subregion_url_tables = list(subregion_url_tables_)

                    # All available URLs for downloading
                    home_subregion_url_table = self.get_subregion_table(self.URL, verbose=False)

                    avail_subregion_url_tables.append(home_subregion_url_table)

                    subregion_downloads_catalogue = pd.concat(avail_subregion_url_tables, ignore_index=True)
                    subregion_downloads_catalogue.drop_duplicates(inplace=True)

                    duplicated = subregion_downloads_catalogue[
                        subregion_downloads_catalogue.Subregion.duplicated(keep=False)]
                    if not duplicated.empty:
                        for i in range(0, 2, len(duplicated)):
                            temp = duplicated.iloc[i:i + 2]

                            size = temp['.osm.pbf.Size'].map(lambda x: humanfriendly.parse_size(
                                x.strip('(').strip(')').replace('\xa0', ' ')))

                            idx = size[size == size.min()].index

                            subregion_downloads_catalogue.drop(idx, inplace=True)

                        subregion_downloads_catalogue.index = range(len(subregion_downloads_catalogue))

                    if verbose:
                        print("Done.")

                    # Save subregion_index_downloads to local disk
                    save_pickle(subregion_downloads_catalogue, path_to_pickle, verbose=verbose)

                except Exception as e:
                    if verbose:
                        print("Failed. {}.".format(e))
                    subregion_downloads_catalogue = None

            else:
                if verbose:
                    print("No data of {} is available.".format(dat_name))

                subregion_downloads_catalogue = None

        return subregion_downloads_catalogue

    def get_list_of_subregion_names(self, update=False, confirmation_required=True, verbose=False):
        """
        Get a list of names of all available geographic regions.

        :param update: whether to (check on and) update the package data, defaults to ``False``
        :type update: bool
        :param confirmation_required: whether asking for confirmation to proceed, defaults to ``True``
        :type confirmation_required: bool
        :param verbose: whether to print relevant information in console, defaults to ``False``
        :type verbose: bool or int
        :return: names of geographic regions available on the free download server
        :rtype: list

        **Example**::

            >>> from pydriosm.downloader import GeofabrikDownloader

            >>> geofabrik_downloader = GeofabrikDownloader()

            >>> # A list of the names of available geographic regions
            >>> geo_region_name_list = geofabrik_downloader.get_list_of_subregion_names()

            >>> geo_region_name_list[:5]
            ['Algeria', 'Angola', 'Benin', 'Botswana', 'Burkina Faso']
        """

        dat_name = ' '.join([self.Abbr, 'subregion name list'])

        path_to_pickle = cd_dat(dat_name.replace(" ", "-") + ".pickle")

        if os.path.isfile(path_to_pickle) and not update:
            subregion_name_list = load_pickle(path_to_pickle)

        else:
            status = ("update the" if os.path.exists(path_to_pickle) else "collect") if update else "collect"

            if confirmed("To {} data of {}\n?".format(status, dat_name),
                         confirmation_required=confirmation_required):

                if verbose:
                    if confirmation_required:
                        status_msg = "Collecting the data"
                    else:
                        status_msg = "To collect data of {}".format(dat_name)
                    print(status_msg, end=" ... ")

                downloads_catalogue = self.get_download_catalogue(
                    update=update, confirmation_required=False, verbose=False)

                subregion_name_list = downloads_catalogue.Subregion.to_list()

                if verbose:
                    print("Done.")

                save_pickle(subregion_name_list, path_to_pickle, verbose=verbose)

            else:
                if verbose:
                    print("No data of {} is available.".format(dat_name))

                subregion_name_list = []

        return subregion_name_list

    def validate_input_subregion_name(self, subregion_name):
        """
        Validate an input name of a geographic region.

        The validation is done by matching the input ``subregion_name`` to a name of a geographic region
        available on Geofabrik free download server.

        :param subregion_name: name (or URL) of a geographic region
        :type subregion_name: str
        :return: valid subregion name that matches, or is the most similar to, the input ``subregion_name``
        :rtype: str

        **Examples**::

            >>> from pydriosm.downloader import GeofabrikDownloader

            >>> geofabrik_downloader = GeofabrikDownloader()

            >>> geo_region_name = 'london'

            >>> valid_name = geofabrik_downloader.validate_input_subregion_name(geo_region_name)
            >>> print(valid_name)
            Greater London

            >>> geo_region_name = 'https://download.geofabrik.de/europe/great-britain.html'

            >>> valid_name = geofabrik_downloader.validate_input_subregion_name(geo_region_name)
            >>> print(valid_name)
            Great Britain
        """

        assert isinstance(subregion_name, str)

        geofabrik_subregion_names = self.get_list_of_subregion_names()  # Get a list of available

        if subregion_name in geofabrik_subregion_names:
            subregion_name_ = subregion_name
        elif os.path.isdir(os.path.dirname(subregion_name)) or urllib.parse.urlparse(subregion_name).path:
            subregion_name_ = find_similar_str(
                os.path.basename(subregion_name), lookup_list=geofabrik_subregion_names)
        else:
            subregion_name_ = find_similar_str(subregion_name, lookup_list=geofabrik_subregion_names)

        if subregion_name_ is None:
            raise InvalidSubregionName(
                "The input `subregion_name` is unidentifiable. "
                "Check if the geographic region exists in the catalogue and retry.")
        else:
            return subregion_name_

    def validate_input_file_format(self, osm_file_format):
        """
        Validate an input file format of OSM data.

        The validation is done by matching the input ``osm_file_format`` to a filename extension
        available on Geofabrik free download server.

        :param osm_file_format: filename extension of OSM data
        :type osm_file_format: str
        :return: formal file format
        :rtype: str

        **Examples**::

            >>> from pydriosm.downloader import GeofabrikDownloader

            >>> geofabrik_downloader = GeofabrikDownloader()

            >>> file_format = ".pbf"

            >>> valid_file_format = geofabrik_downloader.validate_input_file_format(file_format)
            >>> print(valid_file_format)
            .osm.pbf

            >>> file_format = "shp"

            >>> valid_file_format = geofabrik_downloader.validate_input_file_format(file_format)
            >>> print(valid_file_format)
            .shp.zip
        """

        if osm_file_format in self.ValidFileFormats:
            osm_file_format_ = osm_file_format
        else:
            osm_file_format_ = find_similar_str(osm_file_format, self.ValidFileFormats)

        if osm_file_format_ not in self.ValidFileFormats:
            raise InvalidFileFormat("The input `osm_file_format` should be one of \"{}.".format(
                '", "'.join(self.ValidFileFormats[:-1]) + "\" and \"{}\"".format(self.ValidFileFormats[-1])))
        else:
            return osm_file_format_

    def get_subregion_download_url(self, subregion_name, osm_file_format, update=False, verbose=False):
        """
        Get a download URL of a geographic region.

        :param subregion_name: name of a geographic region available on Geofabrik free download server
        :type subregion_name: str
        :param osm_file_format: file format of the OSM data available on the free download server
        :type osm_file_format: str
        :param update: whether to (check on and) update the package data, defaults to ``False``
        :type update: bool
        :param verbose: whether to print relevant information in console, defaults to ``False``
        :type verbose: bool or int
        :return: name and URL of the subregion
        :rtype: tuple

        **Examples**::

            >>> from pydriosm.downloader import GeofabrikDownloader

            >>> geofabrik_downloader = GeofabrikDownloader()

            >>> geo_region_name = 'England'
            >>> osm_file_fmt = ".pbf"

            >>> fml_name, dwnld_link = geofabrik_downloader.get_subregion_download_url(
            ...     subregion_name=geo_region_name, osm_file_format=osm_file_fmt)

            >>> print(fml_name)  # The name of the subregion on the free downloader server
            England
            >>> print(dwnld_link)  # The URL to the PBF data file
            https://download.geofabrik.de/europe/great-britain/england-latest.osm.pbf

            >>> geo_region_name = 'Britain'
            >>> osm_file_fmt = ".shp"

            >>> fml_name, dwnld_link = geofabrik_downloader.get_subregion_download_url(
            ...     subregion_name=geo_region_name, osm_file_format=osm_file_fmt)

            >>> print(fml_name)
            Great Britain
            >>> print(dwnld_link)
            None
        """

        # Get an index of download URLs
        subregion_downloads_index = self.get_download_catalogue(update=update, verbose=verbose)
        subregion_downloads_index.set_index('Subregion', inplace=True)

        subregion_name_ = self.validate_input_subregion_name(subregion_name)
        osm_file_format_ = self.validate_input_file_format(osm_file_format)

        # Get the URL
        download_url = subregion_downloads_index.loc[subregion_name_, osm_file_format_]

        return subregion_name_, download_url

    def get_default_osm_filename(self, subregion_name, osm_file_format, update=False):
        """
        get a default filename for a geograpic region.

        The default filename is derived from the relevant download URL for the requested data file.

        :param subregion_name: name of a geographic region available on Geofabrik free download server
        :type subregion_name: str
        :param osm_file_format: file format of the OSM data available on the free download server
        :type osm_file_format: str
        :param update: whether to (check on and) update the package data, defaults to ``False``
        :type update: bool
        :return: default OSM filename for the ``subregion_name``
        :rtype: str or None

        **Examples**::

            >>> from pydriosm.downloader import GeofabrikDownloader

            >>> geofabrik_downloader = GeofabrikDownloader()

            >>> geo_region_name = 'london'
            >>> file_format = ".pbf"

            >>> # Default filename of the PBF data of London
            >>> fn = geofabrik_downloader.get_default_osm_filename(geo_region_name, file_format)

            >>> print(fn)
            greater-london-latest.osm.pbf

            >>> geo_region_name = 'britain'
            >>> file_format = ".shp"

            >>> # Default filename of the shapefile data of Great Britain
            >>> fn = geofabrik_downloader.get_default_osm_filename(geo_region_name, file_format)
            No .shp.zip data for Great Britain is available to download.

            >>> print(fn)
            None
        """

        subregion_name_ = self.validate_input_subregion_name(subregion_name)
        osm_file_format_ = self.validate_input_file_format(osm_file_format)

        _, download_url = self.get_subregion_download_url(subregion_name_, osm_file_format_, update=update)

        if download_url is None:
            print("No {} data for {} is available to download.".format(osm_file_format_, subregion_name_))
            osm_filename = None

        else:
            osm_filename = os.path.split(download_url)[-1]

        return osm_filename

    def get_default_path_to_osm_file(self, subregion_name, osm_file_format, mkdir=False, update=False,
                                     verbose=False):
        """
        Get a default path to a local directory for storing a downloaded data file.

        The default file path is derived from the relevant download URL for the requested data file.

        :param subregion_name: name of a geographic region available on Geofabrik free download server
        :type subregion_name: str
        :param osm_file_format: file format of the OSM data available on the free download server
        :type osm_file_format: str
        :param mkdir: whether to create a directory, defaults to ``False``
        :type mkdir: bool
        :param update: whether to (check on and) update the package data, defaults to ``False``
        :type update: bool
        :param verbose: whether to print relevant information in console, defaults to ``False``
        :type verbose: bool or int
        :return: default filename of the subregion and default (absolute) path to the file
        :rtype: tuple

        **Example**::

            >>> import os
            >>> from pydriosm.downloader import GeofabrikDownloader

            >>> geofabrik_downloader = GeofabrikDownloader()

            >>> # Default filename and download path of the PBF data of London
            >>> filename, file_path = geofabrik_downloader.get_default_path_to_osm_file(
            ...     subregion_name='London', osm_file_format=".pbf")

            >>> print(filename)
            greater-london-latest.osm.pbf

            >>> print(os.path.relpath(file_path))
            osm_geofabrik\\Europe\\Great Britain\\England\\Greater London\\greater-lond...
        """

        subregion_name_ = self.validate_input_subregion_name(subregion_name)
        osm_file_format_ = self.validate_input_file_format(osm_file_format)

        subregion_name_, download_url = self.get_subregion_download_url(
            subregion_name_, osm_file_format_, update=update)

        if download_url is None:
            if verbose:
                print("{} data is not available for {}".format(osm_file_format_, subregion_name_))

            default_filename, default_file_path = None, None

        else:
            parsed_path = urllib.parse.urlparse(download_url).path.lstrip('/').split('/')

            if len(parsed_path) == 1:
                parsed_path = [subregion_name_] + parsed_path

            subregion_names = self.get_list_of_subregion_names()

            # noinspection PyTypeChecker
            sub_dirs = [
                find_similar_str(x, subregion_names) if x != 'us' else 'United States'
                for x in parsed_path]
            directory = cd_dat_geofabrik(*sub_dirs, mkdir=mkdir)

            default_filename = parsed_path[-1]
            default_file_path = os.path.join(directory, default_filename)

        return default_filename, default_file_path

    def search_for_subregions(self, *subregion_name, deep=False):
        """
        Retrieve names of all subregions (if any) of the given geographic region(s).

        The is based on the region-subregion tier.

        See also [`RNS-1 <https://stackoverflow.com/questions/9807634/>`_].

        :param subregion_name: name of a geographic region available on Geofabrik free download server
        :type subregion_name: str or None
        :param deep: whether to get subregion names of the subregions, defaults to ``False``
        :type deep: bool
        :return: list of subregions (if any); if ``subregion_name=None``, all regions that do have subregions
        :rtype: list

        **Examples**::

            >>> from pydriosm.downloader import GeofabrikDownloader

            >>> geofabrik_downloader = GeofabrikDownloader()

            >>> # Names of all (sub)regions
            >>> region_names = geofabrik_downloader.search_for_subregions()

            >>> len(region_names) > 400
            True
            >>> region_names[:5]
            ['Antarctica', 'Algeria', 'Angola', 'Benin', 'Botswana']
            >>> region_names[-5:]
            ['centro-oeste', 'nordeste', 'norte', 'sudeste', 'sul']

            >>> # Names of all subregions of England and North America
            >>> region_names = geofabrik_downloader.search_for_subregions('england', 'n america')

            >>> len(region_names)
            99
            >>> region_names[:5]
            ['Bedfordshire', 'Berkshire', 'Bristol', 'Buckinghamshire', 'Cambridgeshire']
            >>> region_names[-5:]
            ['Virginia', 'Washington', 'West Virginia', 'Wisconsin', 'Wyoming']

            >>> # Names of subregions of Great Britain
            >>> region_names = geofabrik_downloader.search_for_subregions('britain')
            >>> len(region_names)
            3
            >>> region_names
            ['England', 'Scotland', 'Wales']

            >>> # Names of all subregions of Great Britain's subregions
            >>> region_names = geofabrik_downloader.search_for_subregions('britain', deep=True)
            >>> len(region_names)
            49
            >>> region_names[:5]
            ['Scotland', 'Wales', 'Bedfordshire', 'Berkshire', 'Bristol']
            >>> region_names[-5:]
            ['West Midlands', 'West Sussex', 'West Yorkshire', 'Wiltshire', 'Worcestershire']
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
                res += list(find_subregions(
                    self.validate_input_subregion_name(region), region_subregion_tier))[0]

            if not deep:
                subregion_names = res

            else:
                check_list = [x for x in res if x not in non_subregions_list]

                if check_list:
                    res_ = list(set(res) - set(check_list))
                    res_ += self.search_for_subregions(*check_list)
                else:
                    res_ = res

                del non_subregions_list, region_subregion_tier, check_list

                subregion_names = list(dict.fromkeys(res_))

        return subregion_names

    def make_sub_download_dir(self, subregion_name, osm_file_format, download_dir=None, mkdir=False):
        """
        Make a default directory for downloading data of a geographic region's subregions.

        This is particularly useful when data of a geographic region and requested file format is unavailable.

        :param subregion_name: name of a geographic region available on Geofabrik free download server
        :type subregion_name: str
        :param osm_file_format: file format of the OSM data available on the free download server
        :type osm_file_format: str
        :param download_dir: directory for saving the downloaded file(s);
            if ``None`` (default), the default directory created by the package
        :type download_dir: str or None
        :param mkdir: whether to create a directory, defaults to ``False``
        :type mkdir: bool
        :return: default download directory if the requested data file is not available
        :rtype: str

        **Example**::

            >>> import os
            >>> from pydriosm.downloader import GeofabrikDownloader

            >>> geofabrik_downloader = GeofabrikDownloader()

            >>> region_name = 'london'
            >>> file_format = ".pbf"

            >>> # Default download directory (if the requested data file is not available)
            >>> dwnld_dir = geofabrik_downloader.make_sub_download_dir(region_name, file_format)

            >>> print(os.path.relpath(dwnld_dir))
            osm_geofabrik\\Europe\\Great Britain\\England\\Greater London\\greater-lond...

            >>> region_name = 'britain'
            >>> file_format = ".shp"

            >>> # Default download directory (if the requested data file is not available)
            >>> dwnld_dir = geofabrik_downloader.make_sub_download_dir(region_name, file_format,
            ...                                                        download_dir="tests")

            >>> print(os.path.relpath(dwnld_dir))
            tests\\Great Britain\\great-britain-shp-zip
        """

        subregion_name_ = self.validate_input_subregion_name(subregion_name)
        osm_file_format_ = self.validate_input_file_format(osm_file_format)

        default_filename, default_file_path = self.get_default_path_to_osm_file(
            subregion_name=subregion_name_, osm_file_format=osm_file_format_)

        if not default_filename:
            default_sub_dir = re.sub(r"[. ]", "-", subregion_name_.lower() + osm_file_format_)
        else:
            default_sub_dir = re.sub(r"[. ]", "-", default_filename).lower()

        if download_dir is None:
            default_download_dir = cd_dat_geofabrik(
                os.path.dirname(default_file_path), default_sub_dir, mkdir=mkdir)

        else:
            download_dir_ = validate_input_data_dir(download_dir)
            default_download_dir = cd(download_dir_, default_sub_dir, mkdir=mkdir)

        return default_download_dir

    def file_exists(self, subregion_name, osm_file_format, data_dir=None, update=False, verbose=False,
                    ret_file_path=False):
        """
        Check if a requested data file of a geographic region already exists locally,
        given its default filename.

        :param subregion_name: name of a geographic region available on Geofabrik free download server
        :type subregion_name: str
        :param osm_file_format: file format of the OSM data available on the free download server
        :type osm_file_format: str
        :param data_dir: directory for saving the downloaded file(s);
            if ``None`` (default), the default directory created by the package
        :type data_dir: str or None
        :param update: whether to (check on and) update the data, defaults to ``False``
        :type update: bool
        :param verbose: whether to print relevant information in console, defaults to ``False``
        :type verbose: bool or int
        :param ret_file_path: whether to return the path to the data file (if it exists),
            defaults to ``False``
        :type ret_file_path: bool
        :return: whether or not the requested data file exists; or the path to the data file
        :rtype: bool or str

        **Examples**::

            >>> import os
            >>> from pyhelpers.dir import delete_dir
            >>> from pydriosm.downloader import GeofabrikDownloader, cd_dat_geofabrik

            >>> geofabrik_downloader = GeofabrikDownloader()

            >>> region_name = 'london'
            >>> file_format = ".pbf"

            >>> # Download the PBF data of London (to the default directory)
            >>> geofabrik_downloader.download_osm_data(region_name, file_format, verbose=True)
            To download .osm.pbf data of the following geographic region(s):
                Greater London
            ? [No]|Yes: yes
            Downloading "greater-london-latest.osm.pbf" to "downloads_G\\...\\England" ... Done.

            >>> # Check whether the PBF data file exists; `ret_file_path` is by default `False`
            >>> pbf_exists = geofabrik_downloader.file_exists(region_name, file_format)

            >>> type(pbf_exists)
            bool
            >>> # If the data file exists at the default directory created by the package
            >>> print(pbf_exists)
            True

            >>> # Set `ret_file_path` to be `True`
            >>> path_to_pbf = geofabrik_downloader.file_exists(
            ...     subregion_name=region_name, osm_file_format=file_format, ret_file_path=True)

            >>> # If the data file exists at the default directory created by the package:
            >>> type(path_to_pbf)
            str
            >>> print(os.path.relpath(path_to_pbf))
            osm_geofabrik\\Europe\\Great Britain\\England\\greater-london-latest.osm.pbf

            >>> # Remove the directory or the PBF file and check again:
            >>> delete_dir(cd_dat_geofabrik(), confirmation_required=False, verbose=True)
            Deleting "osm_geofabrik" ... Done.
            >>> path_to_pbf = geofabrik_downloader.file_exists(
            ...     subregion_name=region_name, osm_file_format=file_format, ret_file_path=True)

            >>> # Since the data file does not exist at the default directory
            >>> type(path_to_pbf)
            bool
            >>> print(path_to_pbf)
            False
        """

        file_exists = _osm_file_exists(
            self, subregion_name=subregion_name, osm_file_format=osm_file_format, data_dir=data_dir,
            update=update, verbose=verbose, ret_file_path=ret_file_path)

        return file_exists

    def download_osm_data(self, subregion_names, osm_file_format, download_dir=None, update=False,
                          confirmation_required=True, deep_retry=False, interval=None, verbose=False,
                          ret_download_path=False, **kwargs):
        """
        Download OSM data (in a specific format) of one (or multiple) geographic region(s).

        :param subregion_names: name of a geographic region (or names of multiple geographic regions)
            available on Geofabrik free download server
        :type subregion_names: str or list
        :param osm_file_format: file format of the OSM data available on the free download server
        :type osm_file_format: str
        :param download_dir: directory for saving the downloaded file(s);
            if ``None`` (default), the default directory created by the package
        :type download_dir: str or None
        :param update: whether to update the data if it already exists, defaults to ``False``
        :type update: bool
        :param confirmation_required: whether asking for confirmation to proceed, defaults to ``True``
        :type confirmation_required: bool
        :param deep_retry: whether to further check availability of sub-subregions data,
            defaults to ``False``
        :type deep_retry: bool
        :param interval: interval (in sec) between downloading two subregions, defaults to ``None``
        :type interval: int or None
        :param verbose: whether to print relevant information in console, defaults to ``False``
        :type verbose: bool or int
        :param ret_download_path: whether to return the path(s) to the downloaded file(s),
            defaults to ``False``
        :type ret_download_path: bool
        :param kwargs: optional parameters of `pyhelpers.ops.download_file_from_url()`_
        :return: absolute path(s) to downloaded file(s) when ``ret_download_path`` is ``True``
        :rtype: list or str

        .. _`pyhelpers.ops.download_file_from_url()`:
            https://pyhelpers.readthedocs.io/en/latest/_generated/pyhelpers.ops.download_file_from_url.html

        **Examples**::

            >>> import os
            >>> from pyhelpers.dir import delete_dir
            >>> from pydriosm.downloader import GeofabrikDownloader, cd_dat_geofabrik

            >>> geofabrik_downloader = GeofabrikDownloader()

            >>> # Download PBF data file of Greater London and Rutland
            >>> region_names = ['London', 'Rutland']  # Case-insensitive
            >>> file_format = ".pbf"

            >>> dwnld_paths = geofabrik_downloader.download_osm_data(region_names, file_format,
            ...                                                      verbose=True,
            ...                                                      ret_download_path=True)
            To download .osm.pbf data of the following geographic region(s):
                Greater London
                Rutland
            ? [No]|Yes: yes
            Downloading "greater-london-latest.osm.pbf" to "... ...\\Greater London\\" ... Done.
            Downloading "rutland-latest.osm.pbf" to "... ...\\Rutland\\" ... Done.

            >>> for dwnld_path in dwnld_paths:
            ...     print(os.path.relpath(dwnld_path))
            osm_geofabrik\\Europe\\Great Britain\\England\\Greater London\\greater-lond...
            osm_geofabrik\\Europe\\Great Britain\\England\\Rutland\\rutland-latest.osm.pbf

            >>> # Delete the directory generated above
            >>> delete_dir(cd_dat_geofabrik(), verbose=True)
            The directory "osm_geofabrik\\" is not empty.
            Confirmed to delete it? [No]|Yes: yes
            Deleting "osm_geofabrik\\" ... Done.

            >>> # Download shapefiles of West Midlands
            >>> region_name = 'west midlands'  # Case-insensitive
            >>> file_format = ".shp"
            >>> dwnld_dir = "tests"

            >>> dwnld_path = geofabrik_downloader.download_osm_data(region_name, file_format,
            ...                                                     dwnld_dir, verbose=True,
            ...                                                     ret_download_path=True)
            To download .shp.zip data of the following geographic region(s):
                West Midlands
            ? [No]|Yes: yes
            Downloading "west-midlands-latest-free.shp.zip" to "tests\\" ... Done.

            >>> print(os.path.relpath(dwnld_path))
            tests\\west-midlands-latest-free.shp.zip

            >>> # Delete the downloaded .shp.zip file
            >>> os.remove(dwnld_path)

            >>> # Download shapefiles of Great Britain
            >>> region_name = 'Great Britain'  # Case-insensitive
            >>> file_format = ".shp"

            >>> # By default, `deep_retry` is `False`
            >>> dwnld_path = geofabrik_downloader.download_osm_data(region_name, file_format,
            ...                                                     dwnld_dir, verbose=True,
            ...                                                     ret_download_path=True)
            To download .shp.zip data of the following geographic region(s):
                Great Britain
            ? [No]|Yes: yes
            No .shp.zip data is found for "Great Britain".
            Try to download the data of its subregions instead
            ? [No]|Yes: yes
            Downloading "england-latest-free.shp.zip" to "tests\\great-britain-sh...\\ ... Done.
            Downloading "scotland-latest-free.shp.zip" to "tests\\great-britain-s...\\ ... Done.
            Downloading "wales-latest-free.shp.zip" to "tests\\great-britain-shp-zip\\ ... Done.

            >>> # Set `deep_retry` to `True`
            >>> dwnld_path = geofabrik_downloader.download_osm_data(region_name, file_format,
            ...                                                     dwnld_dir, deep_retry=True,
            ...                                                     verbose=True,
            ...                                                     ret_download_path=True)
            To download .shp.zip data of the following geographic region(s):
                Great Britain
            ? [No]|Yes: yes
            No .shp.zip data is found for "Great Britain".
            Try to download the data of its subregions instead
            ? [No]|Yes: yes
            "scotland-latest-free.shp.zip" is already available at "tests\\great-britain-...\\".
            "wales-latest-free.shp.zip" is already available at "tests\\great-britain-shp...\\".
            Downloading "bedfordshire-latest-free.shp.zip" to "tests\\great-britain-\\ ... Done.
            ... ...
            Downloading "west-yorkshire-latest-free.shp.zip" to "tests\\great-bri...\\ ... Done.
            Downloading "wiltshire-latest-free.shp.zip" to "tests\\great-britain-...\\ ... Done.
            Downloading "worcestershire-latest-free.shp.zip" to "tests\\great-bri...\\ ... Done.

            >>> # Check the file paths
            >>> len(dwnld_path)
            49
            >>> os.path.commonpath(dwnld_path) == geofabrik_downloader.DownloadDir
            True
            >>> print(os.path.relpath(geofabrik_downloader.DownloadDir))
            tests\\great-britain-shp-zip

            >>> # Delete the downloaded files
            >>> delete_dir(geofabrik_downloader.DownloadDir, verbose=True)
            The directory "tests\\great-britain-shp-zip\\" is not empty.
            Confirmed to delete it? [No]|Yes: yes
            Deleting "tests\\great-britain-shp-zip\\" ... Done.
        """

        info = _file_exists(
            self, subregion_names=subregion_names, osm_file_format=osm_file_format, download_dir=download_dir,
            update=update, confirmation_required=confirmation_required, verbose=verbose)

        (subregion_names_, osm_file_format_, confirmation_required_, update_msg, downloads_list,
         existing_file_paths) = info

        confirmation_required_ = confirmation_required_ and confirmation_required

        if confirmed("To {} {} data of the following geographic region(s):"
                     "\n\t{}\n?".format(update_msg, osm_file_format_, "\n\t".join(downloads_list)),
                     confirmation_required=confirmation_required_):

            download_paths = []

            for sub_reg_name in subregion_names_:

                # Get download URL
                subregion_name_, download_url = self.get_subregion_download_url(
                    subregion_name=sub_reg_name, osm_file_format=osm_file_format_)

                if download_url is None:

                    if verbose:
                        print("No {} data is found for \"{}\".".format(osm_file_format_, subregion_name_))

                    if confirmed("Try to download the data of its subregions instead\n?",
                                 confirmation_required=confirmation_required):

                        sub_subregions = self.search_for_subregions(subregion_name_, deep=deep_retry)

                        if sub_subregions == [subregion_name_]:
                            print("{} data is unavailable for {}.".format(osm_file_format_, subregion_name_))
                            # break

                        else:
                            if download_dir is None:
                                _, path_to_file_ = self.get_default_path_to_osm_file(
                                    subregion_name=subregion_name_, osm_file_format=".osm.pbf")
                                download_dir = os.path.dirname(path_to_file_)

                            download_dir_ = self.make_sub_download_dir(
                                subregion_name=subregion_name_, osm_file_format=osm_file_format_,
                                download_dir=download_dir)

                            download_paths_ = self.download_osm_data(
                                subregion_names=sub_subregions, osm_file_format=osm_file_format_,
                                download_dir=download_dir_, update=update, confirmation_required=False,
                                verbose=verbose, ret_download_path=ret_download_path)

                            download_paths += download_paths_

                else:
                    if download_dir is None:
                        # Download the requested OSM file to default directory
                        osm_filename, path_to_file = self.get_default_path_to_osm_file(
                            subregion_name=subregion_name_, osm_file_format=osm_file_format_, mkdir=True)

                    else:
                        download_dir_ = cd(validate_input_data_dir(input_data_dir=download_dir), mkdir=True)
                        osm_filename = self.get_default_osm_filename(
                            subregion_name=subregion_name_, osm_file_format=osm_file_format_)
                        path_to_file = os.path.join(download_dir_, osm_filename)

                    if not os.path.isfile(path_to_file) or update:
                        _download_osm_data(download_url=download_url, path_to_file=path_to_file,
                                           verbose=verbose, **kwargs)

                    if os.path.isfile(path_to_file):
                        download_paths.append(path_to_file)

                if isinstance(interval, int):
                    time.sleep(secs=interval)

        else:
            download_paths = existing_file_paths

        download_paths_ = _download_paths(self, download_dir=download_dir, download_paths=download_paths)

        if ret_download_path:
            return download_paths_

    def download_subregion_data(self, subregion_names, osm_file_format, download_dir=None, deep=False,
                                update=False, confirmation_required=True, interval=None, verbose=False,
                                ret_download_path=False, **kwargs):
        """
        Download OSM data (in a specific file format) of all subregions (if available) for
        one (or multiple) geographic region(s).

        If no subregion data is available for the region(s) specified by ``subregion_names``,
        then the data of ``subregion_names`` would be downloaded only.

        :param subregion_names: name of a geographic region (or names of multiple geographic regions)
            available on Geofabrik free download server
        :type subregion_names: str or list
        :param osm_file_format: file format of the OSM data available on the free download server
        :type osm_file_format: str
        :param download_dir: directory for saving the downloaded file(s);
            if ``None`` (default), the default directory created by the package
        :type download_dir: str or None
        :param deep: whether to try to search for subregions of subregion(s), defaults to ``False``
        :type deep: bool
        :param update: whether to update the data if it already exists, defaults to ``False``
        :type update: bool
        :param confirmation_required: whether asking for confirmation to proceed, defaults to ``True``
        :type confirmation_required: bool
        :param interval: interval (in second) between downloading two subregions, defaults to ``None``
        :type interval: int or None
        :param verbose: whether to print relevant information in console, defaults to ``False``
        :type verbose: bool or int
        :param ret_download_path: whether to return the path(s) to the downloaded file(s),
            defaults to ``False``
        :type ret_download_path: bool
        :param kwargs: optional parameters of `pydriosm.GeofabrikDownloader.download_osm_data()`_
        :return: the path(s) to the downloaded file(s) when ``ret_download_path`` is ``True``
        :rtype: list or str

        .. _`pydriosm.GeofabrikDownloader.download_osm_data()`:
            https://pydriosm.readthedocs.io/en/latest/
            _generated/pydriosm.downloader.GeofabrikDownloader.download_osm_data.html

        **Examples**::

            >>> import os
            >>> from pyhelpers.dir import cd
            >>> from pydriosm.downloader import GeofabrikDownloader

            >>> geofabrik_downloader = GeofabrikDownloader()

            >>> region_names = ['rutland', 'west yorkshire']
            >>> file_format = ".pbf"
            >>> dwnld_dir = "tests"

            >>> geofabrik_downloader.download_subregion_data(
            ...     region_names, file_format, dwnld_dir, verbose=True)
            To download .osm.pbf data of the following geographic region(s):
                Rutland
                West Yorkshire
            ? [No]|Yes: yes
            Downloading "rutland-latest.osm.pbf" to "tests\\" ... Done.
            Downloading "west-yorkshire-latest.osm.pbf" to "tests\\" ... Done.

            >>> # Delete "tests\\rutland-latest.osm.pbf"
            >>> os.remove(cd(dwnld_dir, "rutland-latest.osm.pbf"))

            >>> # Try to download data given another list which also includes 'West Yorkshire'
            >>> region_names = ['west midlands', 'west yorkshire']

            >>> dwnld_paths = geofabrik_downloader.download_subregion_data(
            ...     region_names, file_format, dwnld_dir, verbose=True, ret_download_path=True)
            "west-yorkshire-latest.osm.pbf" is already available at "tests\\".
            To download .osm.pbf data of the following geographic region(s):
                West Midlands
            ? [No]|Yes: yes
            Downloading "west-midlands-latest.osm.pbf" to "tests\\" ... Done.

            >>> for dwnld_path in dwnld_paths:
            ...     print(os.path.relpath(dwnld_path))
            tests\\west-midlands-latest.osm.pbf
            tests\\west-yorkshire-latest.osm.pbf

            >>> # Update (or re-download) the existing data file
            >>> dwnld_paths = geofabrik_downloader.download_subregion_data(
            ...     region_names, file_format, dwnld_dir, update=True, verbose=True,
            ...     ret_download_path=True)
            "west-midlands-latest.osm.pbf" is already available at "tests\\".
            "west-yorkshire-latest.osm.pbf" is already available at "tests\\".
            To update the .osm.pbf data of the following geographic region(s):
                West Midlands
                West Yorkshire
            ? [No]|Yes: yes
            Updating "west-midlands-latest.osm.pbf" at "tests\\" ... Done.
            Updating "west-yorkshire-latest.osm.pbf" at "tests\\" ... Done.

            >>> # To download the PBF data of England
            >>> region_names = 'England'

            >>> dwnld_paths = geofabrik_downloader.download_subregion_data(
            ...     region_names, file_format, dwnld_dir, update=True, verbose=True,
            ...     ret_download_path=True)
            "west-midlands-latest.osm.pbf" is already available at "tests\\".
            "west-yorkshire-latest.osm.pbf" is already available at "tests\\".
            To download/update the .osm.pbf data of the following geographic region(s):
                Bedfordshire
                Berkshire
                ...
                West Midlands
                ...
                West Yorkshire
                Wiltshire
                Worcestershire
            ? [No]|Yes: yes
            Downloading "bedfordshire-latest.osm.pbf" to "tests\\" ... Done.
            Downloading "berkshire-latest.osm.pbf" to "tests\\" ... Done.
            ...
            Updating "west-midlands-latest.osm.pbf" at "tests\\" ... Done.
            ...
            Updating "west-yorkshire-latest.osm.pbf" at "tests\\" ... Done.
            Downloading "wiltshire-latest.osm.pbf" to "tests\\" ... Done.
            Downloading "worcestershire-latest.osm.pbf" to "tests\\" ... Done.

            >>> len(dwnld_paths)
            47

            >>> # Delete the downloaded files
            >>> for dwnld_path in dwnld_paths:
            ...     os.remove(dwnld_path)
        """

        sr_names_ = [subregion_names] if isinstance(subregion_names, str) else subregion_names.copy()
        sr_names_ = [self.validate_input_subregion_name(x) for x in sr_names_]

        osm_file_format_ = self.validate_input_file_format(osm_file_format)

        subregion_names_ = self.search_for_subregions(*sr_names_, deep=deep)

        download_paths = self.download_osm_data(
            subregion_names=subregion_names_, osm_file_format=osm_file_format_,
            download_dir=download_dir, update=update, confirmation_required=confirmation_required,
            interval=interval, verbose=verbose, ret_download_path=True, **kwargs)

        if ret_download_path:
            if isinstance(download_paths, list) and len(download_paths) == 1:
                download_paths = download_paths[0]

            return download_paths


class BBBikeDownloader:
    """
    Download OSM data from `BBBike <https://download.bbbike.org/>`_ free download server.

    :param download_dir: directory path to the downloaded file(s);
        if ``None`` (default), the current working directory

    :ivar str Name: name of data
    :ivar str Abbr: short name of the data
    :ivar str URL: URL of the homepage to the free download server
    :ivar str URLCities: URL of a list of cities available on the free download server
    :ivar str URLCitiesCoords: URL of coordinates of all the available cities
    :ivar list ValidFileFormats: valid file formats available on the free download server

    **Example**::

        >>> from pydriosm.downloader import BBBikeDownloader

        >>> bbbike_downloader = BBBikeDownloader()

        >>> print(bbbike_downloader.Name)
        BBBike OpenStreetMap data extracts

        >>> print(bbbike_downloader.URL)
        https://download.bbbike.org/osm/bbbike/
    """

    def __init__(self, download_dir=None):
        """
        Constructor method.
        """
        self.Name = 'BBBike OpenStreetMap data extracts'
        self.Abbr = 'BBBike'

        self.URL = bbbike_homepage()

        self.URLCities = 'https://raw.githubusercontent.com/wosch/bbbike-world/world/etc/cities.txt'
        self.URLCitiesCoords = 'https://raw.githubusercontent.com/wosch/bbbike-world/world/etc/cities.csv'

        self.ValidFileFormats = [
            '.pbf', '.gz', '.shp.zip',
            '.garmin-onroad-latin1.zip', '.garmin-onroad.zip', '.garmin-opentopo.zip', '.garmin-osm.zip',
            '.geojson.xz', '.svg-osm.zip', '.mapsforge-osm.zip', '.csv.xz']

        if download_dir is None:
            self.DownloadDir = cd_dat_bbbike()
        else:
            self.DownloadDir = validate_input_data_dir(input_data_dir=download_dir)

    def get_list_of_cities(self, update=False, confirmation_required=True, verbose=False):
        """
        Get a list of names of cities.

        This is an alternative to
        :py:meth:`.get_list_of_subregion_names()
        <pydriosm.downloader.BBBikeDownloader.get_list_of_subregion_names>`.

        :param update: whether to (check on and) update the package data, defaults to ``False``
        :type update: bool
        :param confirmation_required: whether asking for confirmation to proceed, defaults to ``True``
        :type confirmation_required: bool
        :param verbose: whether to print relevant information in console, defaults to ``False``
        :type verbose: bool or int
        :return: list of names of cities available on the BBBike free download server
        :rtype: list or None

        **Example**::

            >>> from pydriosm.downloader import BBBikeDownloader

            >>> bbbike_downloader = BBBikeDownloader()

            >>> # A list of BBBike cities' names
            >>> names_of_cities = bbbike_downloader.get_list_of_cities()

            >>> len(names_of_cities) > 200
            True

            >>> names_of_cities[:5]
            ['Heilbronn', 'Emden', 'Bremerhaven', 'Paris', 'Ostrava']

            >>> names_of_cities[-5:]
            ['UlanBator', 'LaPaz', 'Sucre', 'Cusco', 'LaPlata']
        """

        dat_name = ' '.join([self.Abbr, 'cities'])

        path_to_pickle = cd_dat(dat_name.replace(" ", "-") + ".pickle")

        if os.path.isfile(path_to_pickle) and not update:
            cities_names = load_pickle(path_to_pickle)

        else:
            status = ("update the" if os.path.exists(path_to_pickle) else "collect") if update else "collect"

            if confirmed("To {} data of {}\n?".format(status, dat_name),
                         confirmation_required=confirmation_required):

                if verbose:
                    if confirmation_required:
                        status_msg = "Collecting the data"
                    else:
                        status_msg = "Collecting the data of {}".format(dat_name)
                    print(status_msg, end=" ... ")

                try:
                    cities_names_ = pd.read_csv(self.URLCities, header=None)
                    cities_names = list(cities_names_.values.flatten())

                    if verbose:
                        print("Done.")

                    save_pickle(cities_names, path_to_pickle, verbose=verbose)

                except Exception as e:
                    if verbose:
                        print("Failed. {}.".format(e))
                    cities_names = None

            else:
                if verbose:
                    print("No data of {} is available.".format(dat_name))
                cities_names = None

        return cities_names

    def get_coordinates_of_cities(self, update=False, confirmation_required=True, verbose=False):
        """
        Get location information of cities (geographic regions).

        :param update: whether to (check on and) update the package data, defaults to ``False``
        :type update: bool
        :param confirmation_required: whether asking for confirmation to proceed, defaults to ``True``
        :type confirmation_required: bool
        :param verbose: whether to print relevant information in console, defaults to ``False``
        :type verbose: bool or int
        :return: location information of BBBike cities
        :rtype: pandas.DataFrame or None

        **Example**::

            >>> from pydriosm.downloader import BBBikeDownloader

            >>> bbbike_downloader = BBBikeDownloader()

            >>> # Location information of BBBike cities
            >>> coords_of_cities = bbbike_downloader.get_coordinates_of_cities()

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

            >>> coords_of_cities.columns.tolist()
            ['City',
             'Real name',
             'Pref. language',
             'Local language',
             'Country',
             'Area/continent',
             'Population',
             'Step?',
             'Other cities',
             'll_longitude',
             'll_latitude',
             'ur_longitude',
             'ur_latitude']
        """

        dat_name = ' '.join([self.Abbr, 'cities coordinates'])

        path_to_pickle = cd_dat(dat_name.replace(" ", "-") + ".pickle")

        if os.path.isfile(path_to_pickle) and not update:
            cities_coordinates = load_pickle(path_to_pickle)

        else:
            status = ("update the" if os.path.exists(path_to_pickle) else "collect") if update else "collect"

            if confirmed("To {} data of {}\n?".format(status, dat_name),
                         confirmation_required=confirmation_required):

                if verbose:
                    if confirmation_required:
                        status_msg = "Collecting the data"
                    else:
                        status_msg = "Collecting the data of {}".format(dat_name)
                    print(status_msg, end=" ... ")

                try:
                    csv_temp = urllib.request.urlopen(self.URLCitiesCoords)
                    csv_file = list(csv.reader(io.StringIO(csv_temp.read().decode('utf-8')), delimiter=':'))

                    csv_data = [
                        [x.strip().strip('\u200e').replace('#', '') for x in row] for row in csv_file[5:-1]]
                    column_names = [x.replace('#', '').strip().capitalize() for x in csv_file[0]]
                    cities_coords = pd.DataFrame(csv_data, columns=column_names)

                    coordinates = cities_coords.Coord.str.split(' ').apply(pd.Series)
                    coords_cols = ['ll_longitude', 'll_latitude', 'ur_longitude', 'ur_latitude']
                    coordinates.columns = coords_cols

                    cities_coords.drop(['Coord'], axis=1, inplace=True)

                    cities_coordinates = pd.concat([cities_coords, coordinates], axis=1)

                    cities_coordinates.dropna(subset=coords_cols, inplace=True)

                    cities_coordinates['Real name'] = cities_coordinates['Real name'].str.split(r'[!,]').map(
                        lambda x: None if x[0] == '' else dict(zip(x[::2], x[1::2])))

                    if verbose:
                        print("Done.")

                    save_pickle(cities_coordinates, path_to_pickle, verbose=verbose)

                except Exception as e:
                    if verbose:
                        print("Failed. {}.".format(e))
                    cities_coordinates = None

            else:
                if verbose:
                    print("No data of {} is available.".format(dat_name))
                cities_coordinates = None

        return cities_coordinates

    def get_subregion_catalogue(self, update=False, confirmation_required=True, verbose=False):
        """
        Get a catalogue for geographic regions.

        :param update: whether to (check on and) update the package data, defaults to ``False``
        :type update: bool
        :param confirmation_required: whether asking for confirmation to proceed, defaults to ``True``
        :type confirmation_required: bool
        :param verbose: whether to print relevant information in console, defaults to ``False``
        :type verbose: bool or int
        :return: catalogue for subregions of BBBike data
        :rtype: pandas.DataFrame or None

        **Example**::

            >>> from pydriosm.downloader import BBBikeDownloader

            >>> bbbike_downloader = BBBikeDownloader()

            >>> # A BBBike catalogue of geographic regions
            >>> subregion_catalog = bbbike_downloader.get_subregion_catalogue()

            >>> type(subregion_catalog)
            pandas.core.frame.DataFrame

            >>> subregion_catalog.head()
                      Name  ...                                                URL
            1       Aachen  ...     https://download.bbbike.org/osm/bbbike/Aachen/
            2       Aarhus  ...     https://download.bbbike.org/osm/bbbike/Aarhus/
            3     Adelaide  ...   https://download.bbbike.org/osm/bbbike/Adelaide/
            4  Albuquerque  ...  https://download.bbbike.org/osm/bbbike/Albuque...
            5   Alexandria  ...  https://download.bbbike.org/osm/bbbike/Alexand...
            [5 rows x 3 columns]

            >>> subregion_catalog.columns.to_list()
            ['Name', 'Last Modified', 'URL']
        """

        dat_name = ' '.join([self.Abbr, 'subregion catalogue'])

        path_to_pickle = cd_dat(dat_name.replace(" ", "-") + ".pickle")

        if os.path.isfile(path_to_pickle) and not update:
            subregion_catalogue = load_pickle(path_to_pickle)

        else:
            status = ("update the" if os.path.exists(path_to_pickle) else "collect") if update else "collect"

            if confirmed("To {} data of {}\n?".format(status, dat_name),
                         confirmation_required=confirmation_required):

                if verbose:
                    if confirmation_required:
                        status_msg = "Collecting the data"
                    else:
                        status_msg = "Collecting the data of {}".format(dat_name)
                    print(status_msg, end=" ... ")

                try:
                    # noinspection PyTypeChecker
                    bbbike_subregion_cat = pd.read_html(self.URL, header=0, parse_dates=['Last Modified'])
                    subregion_catalogue = bbbike_subregion_cat[0].drop(0).drop(['Size', 'Type'], axis=1)
                    subregion_catalogue.Name = subregion_catalogue.Name.map(lambda x: x.strip('/'))

                    source = requests.get(self.URL, headers=fake_requests_headers())
                    tbl_soup = bs4.BeautifulSoup(source.text, 'lxml').find('table')

                    subregion_catalogue['URL'] = [
                        urllib.parse.urljoin(self.URL, x.get('href')) for x in tbl_soup.find_all('a')[1:]]

                    if verbose:
                        print("Done.")

                    save_pickle(subregion_catalogue, path_to_pickle, verbose=verbose)

                except Exception as e:
                    if verbose:
                        print("Failed. {}.".format(e))
                    subregion_catalogue = None

            else:
                if verbose:
                    print("No data of {} is available.".format(dat_name))
                subregion_catalogue = None

        return subregion_catalogue

    def get_list_of_subregion_names(self, update=False, confirmation_required=True, verbose=False):
        """
        Get a list of names of all geographic regions.

        This is an alternative to
        :py:meth:`.get_list_of_cities()<pydriosm.downloader.BBBikeDownloader.get_list_of_cities>`.

        :param update: whether to (check on and) update the package data, defaults to ``False``
        :type update: bool
        :param confirmation_required: whether asking for confirmation to proceed, defaults to ``True``
        :type confirmation_required: bool
        :param verbose: whether to print relevant information in console, defaults to ``False``
        :type verbose: bool or int
        :return: a list of geographic region names available on BBBike free download server
        :rtype: list

        **Example**::

            >>> from pydriosm.downloader import BBBikeDownloader

            >>> bbbike_downloader = BBBikeDownloader()

            >>> # A list of names of all BBBike geographic regions
            >>> region_name_list = bbbike_downloader.get_list_of_subregion_names()

            >>> len(region_name_list) > 200
            True

            >>> region_name_list[:5]
            ['Aachen', 'Aarhus', 'Adelaide', 'Albuquerque', 'Alexandria']

            >>> region_name_list[-5:]
            ['Wroclaw', 'Wuerzburg', 'Wuppertal', 'Zagreb', 'Zuerich']
        """

        dat_name = ' '.join([self.Abbr, 'subregion name list'])

        path_to_pickle = cd_dat(dat_name.replace(" ", "-") + ".pickle")

        if os.path.isfile(path_to_pickle) and not update:
            subregion_name_list = load_pickle(path_to_pickle)

        else:
            status = ("update the" if os.path.exists(path_to_pickle) else "collect") if update else "collect"

            if confirmed("To {} data of {}\n?".format(status, dat_name),
                         confirmation_required=confirmation_required):

                if verbose:
                    if confirmation_required:
                        status_msg = "Collecting the data"
                    else:
                        status_msg = "Collecting the data of {}".format(dat_name)
                    print(status_msg, end=" ... ")

                subregion_catalogue = self.get_subregion_catalogue(
                    update=update, confirmation_required=False, verbose=False)

                subregion_name_list = subregion_catalogue.Name.to_list()

                if verbose:
                    print("Done.")

                save_pickle(subregion_name_list, path_to_pickle, verbose=verbose)

            else:
                subregion_name_list = []
                if verbose:
                    print("No data of {} is available.".format(dat_name))

        return subregion_name_list

    def validate_input_subregion_name(self, subregion_name):
        """
        Validate an input name of a geographic region.

        The validation is done by matching the input ``subregion_name`` to a name of a geographic region
        available on BBBike free download server.

        :param subregion_name: name of a geographic region (case-insensitive)
        :type subregion_name: str
        :return: valid subregion name that matches, or is the most similar to, the input ``subregion_name``
        :rtype: str

        **Example**::

            >>> from pydriosm.downloader import BBBikeDownloader

            >>> bbbike_downloader = BBBikeDownloader()

            >>> region_name = 'leeds'

            >>> valid_name = bbbike_downloader.validate_input_subregion_name(region_name)

            >>> print(valid_name)
            Leeds
        """

        assert isinstance(subregion_name, str)

        bbbike_subregion_names = self.get_list_of_subregion_names()

        if subregion_name in bbbike_subregion_names:
            subregion_name_ = subregion_name

        elif os.path.isdir(os.path.dirname(subregion_name)) or urllib.parse.urlparse(subregion_name).path:
            subregion_name_ = find_similar_str(
                os.path.basename(subregion_name), lookup_list=bbbike_subregion_names)

        else:
            subregion_name_ = find_similar_str(subregion_name, lookup_list=bbbike_subregion_names)

        if subregion_name_ is None:
            raise InvalidSubregionName(
                "`subregion_name` is unidentifiable. "
                "Check if the geographic region exists in the catalogue and retry.")

        return subregion_name_

    def get_subregion_download_catalogue(self, subregion_name, confirmation_required=True, verbose=False):
        """
        Get a download catalogue of OSM data available for a geographic region.

        :param subregion_name: name of a geographic region available on BBBike free download server
        :type subregion_name: str
        :param confirmation_required: whether asking for confirmation to proceed, defaults to ``True``
        :type confirmation_required: bool
        :param verbose: whether to print relevant information in console, defaults to ``False``
        :type verbose: bool or int
        :return: a catalogues for subregion downloads
        :rtype: pandas.DataFrame or None

        **Example**::

            >>> from pydriosm.downloader import BBBikeDownloader

            >>> bbbike_downloader = BBBikeDownloader()

            >>> region_name = 'leeds'

            >>> # A download catalogue for Leeds
            >>> leeds_dwnld_cat = bbbike_downloader.get_subregion_download_catalogue(
            ...     subregion_name=region_name, verbose=True)
            To collect the download catalogue for "Leeds"
            ? [No]|Yes: yes
            Collecting the data ... Done.

            >>> leeds_dwnld_cat.head()
                                         Filename  ...          LastUpdate
            0                       Leeds.osm.pbf  ... 2020-09-25 10:04:25
            1                        Leeds.osm.gz  ... 2020-09-25 15:11:49
            2                   Leeds.osm.shp.zip  ... 2020-09-25 15:33:10
            3  Leeds.osm.garmin-onroad-latin1.zip  ... 2020-09-25 17:49:15
            4         Leeds.osm.garmin-onroad.zip  ... 2020-09-25 17:49:04
            [5 rows x 5 columns]

            >>> leeds_dwnld_cat.columns.tolist()
            ['Filename', 'URL', 'DataType', 'Size', 'LastUpdate']
        """

        subregion_name_ = self.validate_input_subregion_name(subregion_name)

        dat_name = "a download catalogue for \"{}\"".format(subregion_name_)

        if confirmed("To collect data of {}\n?".format(dat_name),
                     confirmation_required=confirmation_required):

            if verbose:
                if confirmation_required:
                    status_msg = "Collecting the data"
                else:
                    if verbose == 2:
                        status_msg = "\t{}".format(subregion_name_)
                    else:
                        status_msg = "Collecting the data of {}".format(dat_name)
                print(status_msg, end=" ... ")

            try:
                url = urllib.parse.urljoin(self.URL, subregion_name_ + '/')

                source = requests.get(url, headers=fake_requests_headers())

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

                subregion_download_catalogue = pd.DataFrame(parse_dlc(x) for x in download_links_class)
                subregion_download_catalogue.columns = ['Filename', 'URL', 'DataType', 'Size', 'LastUpdate']

                # file_path = cd_dat_bbbike(subregion_name_, subregion_name_ + "-download-catalogue.pickle")
                # save_pickle(subregion_downloads_catalogue, file_path, verbose=verbose)
                if verbose:
                    print("Done.")

            except Exception as e:
                if verbose:
                    print("Failed. {}".format(e))
                subregion_download_catalogue = None

            return subregion_download_catalogue

    def get_download_index(self, update=False, confirmation_required=True, verbose=False):
        """
        Get a dict-type index of available formats, data types and a download catalogue.

        :param update: whether to (check on and) update the package data, defaults to ``False``
        :type update: bool
        :param confirmation_required: whether asking for confirmation to proceed, defaults to ``True``
        :type confirmation_required: bool
        :param verbose: whether to print relevant information in console, defaults to ``False``
        :type verbose: bool or int
        :return: a list of available formats, a list of available data types and
            a dictionary of download catalogue
        :rtype: dict

        **Examples**::

            >>> from pydriosm.downloader import BBBikeDownloader

            >>> bbbike_downloader = BBBikeDownloader()

            >>> # Index for downloading OSM data available on the BBBike free download server
            >>> dwnld_dict = bbbike_downloader.get_download_index()

            >>> list(dwnld_dict.keys())
            ['FileFormat', 'DataType', 'Catalogue']

            >>> catalogue = dwnld_dict['Catalogue']
            >>> type(catalogue)
            dict
            >>> list(catalogue.keys())[:5]
            ['Aachen', 'Aarhus', 'Adelaide', 'Albuquerque', 'Alexandria']

            >>> catalogue_leeds = catalogue['Leeds']
            >>> type(catalogue_leeds)
            pandas.core.frame.DataFrame
            >>> catalogue_leeds.head()
                                         Filename  ...          LastUpdate
            0                       Leeds.osm.pbf  ... 2021-03-27 19:42:55
            1                        Leeds.osm.gz  ... 2021-03-27 23:54:36
            2                   Leeds.osm.shp.zip  ... 2021-03-28 00:08:26
            3  Leeds.osm.garmin-onroad-latin1.zip  ... 2021-03-28 01:12:19
            4         Leeds.osm.garmin-onroad.zip  ... 2021-03-28 01:11:50
            [5 rows x 5 columns]
        """

        dat_name = ' '.join([self.Abbr, 'download dictionary'])

        path_to_pickle = cd_dat(dat_name.replace(" ", "-") + ".pickle")

        if os.path.isfile(path_to_pickle) and not update:
            download_dictionary = load_pickle(path_to_pickle)

        else:
            status = ("update the" if os.path.exists(path_to_pickle) else "collect") if update else "collect"

            if confirmed("To {} data of {}\n?".format(status, dat_name),
                         confirmation_required=confirmation_required):

                if verbose:
                    if confirmation_required:
                        status_msg = "Collecting the data"
                    else:
                        status_msg = "Collecting the data of {}".format(dat_name)
                    print(status_msg, end=": \n" if verbose == 2 else " ... ")

                try:
                    bbbike_subregion_names = self.get_subregion_catalogue(verbose=False).Name.to_list()

                    download_catalogue = []
                    for subregion_name in bbbike_subregion_names:

                        subregion_dwnld_cat = self.get_subregion_download_catalogue(
                            subregion_name=subregion_name, confirmation_required=False,
                            verbose=2 if verbose == 2 else False)

                        if subregion_dwnld_cat is None:
                            raise Exception
                        else:
                            download_catalogue.append(subregion_dwnld_cat)

                    sr_name = bbbike_subregion_names[0]
                    sr_download_catalogue = download_catalogue[0]

                    # Available file formats
                    file_fmt = [
                        re.sub('{}|CHECKSUM'.format(sr_name), '', f) for f in sr_download_catalogue.Filename]

                    # Available data types
                    data_typ = sr_download_catalogue.DataType.tolist()

                    download_dictionary = {
                        'FileFormat': [x.replace(".osm", "", 1) for x in file_fmt[:-2]],
                        'DataType': data_typ[:-2],
                        'Catalogue': dict(zip(bbbike_subregion_names, download_catalogue))}

                    if verbose is True:
                        print("Done.")
                    elif verbose == 2:
                        print("All done.")

                    save_pickle(download_dictionary, path_to_pickle, verbose=verbose)

                except Exception as e:
                    if verbose:
                        print("Failed. {}".format(e))
                    download_dictionary = None

            else:
                if verbose:
                    print("No data of {} is available.".format(dat_name))
                download_dictionary = None

        return download_dictionary

    def get_valid_file_formats(self):
        """
        Get a list of valid OSM data file formats.

        :return: a list of valid BBBike OSM file formats on BBBike free download server
        :rtype: list

        **Example**::

            >>> from pydriosm.downloader import BBBikeDownloader

            >>> bbbike_downloader = BBBikeDownloader()

            >>> file_formats = bbbike_downloader.get_valid_file_formats()

            >>> for file_format in file_formats:
            ...     print(file_format)
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

        osm_file_formats = self.get_download_index()['FileFormat']

        # self.__setattr__('ValidFileFormats', osm_file_formats)

        return osm_file_formats

    def validate_input_file_format(self, osm_file_format):
        """
        Validate an input file format of OSM data.

        The validation is done by matching the input ``osm_file_format`` to a filename extension
        available on BBBike free download server.

        :param osm_file_format: file extension of an OSM data extract
        :type osm_file_format: str
        :return: valid file format (file extension)
        :rtype: str

        **Example**::

            >>> from pydriosm.downloader import BBBikeDownloader

            >>> bbbike_downloader = BBBikeDownloader()

            >>> file_format = 'PBF'

            >>> valid_file_format = bbbike_downloader.validate_input_file_format(file_format)

            >>> print(valid_file_format)
            .pbf
        """

        assert isinstance(osm_file_format, str)
        # bbbike_osm_file_formats = self.get_valid_file_formats()

        if osm_file_format in self.ValidFileFormats:
            osm_file_format_ = osm_file_format
        else:
            osm_file_format_ = find_similar_str(osm_file_format, self.ValidFileFormats)

        if osm_file_format_ is None:
            raise InvalidFileFormat("`osm_file_format` should be one of: \n  \"{}\".".format(
                "\",\n  \"".join(self.ValidFileFormats)))
        else:
            return osm_file_format_

    def get_subregion_download_url(self, subregion_name, osm_file_format):
        """
        Get a valid URL for downloading OSM data of a specific file format for a geographic region.

        :param subregion_name: name of a geographic region available on BBBike free download server
        :type subregion_name: str
        :param osm_file_format: format (file extension) of an OSM data
        :type osm_file_format: str
        :return: a valid name of ``subregion_name`` and a download URL for the given ``osm_file_format``
        :rtype: tuple

        **Examples**::

            >>> from pydriosm.downloader import BBBikeDownloader

            >>> bbbike_downloader = BBBikeDownloader()

            >>> region_name = 'leeds'
            >>> file_format = 'pbf'

            >>> # Get a valid subregion name and its download URL
            >>> rn, dl = bbbike_downloader.get_subregion_download_url(region_name, file_format)

            >>> print(rn)
            Leeds
            >>> print(dl)
            https://download.bbbike.org/osm/bbbike/Leeds/Leeds.osm.pbf

            >>> file_format = 'csv.xz'
            >>> rn, dl = bbbike_downloader.get_subregion_download_url(region_name, file_format)

            >>> print(rn)
            Leeds
            >>> print(dl)
            https://download.bbbike.org/osm/bbbike/Leeds/Leeds.osm.csv.xz
        """

        subregion_name_ = self.validate_input_subregion_name(subregion_name)
        osm_file_format_ = ".osm" + self.validate_input_file_format(osm_file_format)

        bbbike_download_dictionary = self.get_download_index()['Catalogue']
        sub_download_catalogue = bbbike_download_dictionary[subregion_name_]

        tmp = subregion_name_ + osm_file_format_
        url = sub_download_catalogue[sub_download_catalogue.Filename == tmp].URL.iloc[0]

        return subregion_name_, url

    def get_valid_download_info(self, subregion_name, osm_file_format, download_dir=None, mkdir=False):
        """
        Get information of downloading (or downloaded) data file.

        The information includes a valid subregion name, a default filename, a URL and
        an absolute path where the data file is (to be) saved locally.

        :param subregion_name: name of a geographic region (case-insensitive)
        :type subregion_name: str
        :param osm_file_format: format (file extension) of an OSM data
        :type osm_file_format: str
        :param download_dir: directory where downloaded OSM file is saved;
            if ``None`` (default), the default directory created by the package
        :type download_dir: str or None
        :param mkdir: whether to create a directory, defaults to ``False``
        :type mkdir: bool
        :return: valid subregion name, filename, download url and absolute file path
        :rtype: tuple

        **Examples**::

            >>> import os
            >>> from pydriosm.downloader import BBBikeDownloader

            >>> bbbike_downloader = BBBikeDownloader()

            >>> region_name = 'leeds'
            >>> file_format = 'pbf'

            >>> # valid subregion name, filename, download url and absolute file path
            >>> info = bbbike_downloader.get_valid_download_info(region_name, file_format)
            >>> sub_reg_name, pbf_filename, dwnld_url, path_to_pbf = info

            >>> print(sub_reg_name)
            Leeds
            >>> print(pbf_filename)
            Leeds.osm.pbf
            >>> print(dwnld_url)
            https://download.bbbike.org/osm/bbbike/Leeds/Leeds.osm.pbf
            >>> print(os.path.relpath(path_to_pbf))
            osm_bbbike\\Leeds\\Leeds.osm.pbf
        """

        subregion_name_, download_url = self.get_subregion_download_url(
            subregion_name=subregion_name, osm_file_format=osm_file_format)
        osm_filename = os.path.basename(download_url)

        if download_dir is None:
            # default directory of package data
            path_to_file = cd_dat_bbbike(subregion_name_, osm_filename, mkdir=mkdir)
        else:
            download_dir_ = validate_input_data_dir(download_dir)
            path_to_file = cd(download_dir_, osm_filename, mkdir=mkdir)

        return subregion_name_, osm_filename, download_url, path_to_file

    def file_exists(self, subregion_name, osm_file_format, data_dir=None, update=False, verbose=False,
                    ret_file_path=False):
        """
        Check if a requested data file of a geographic region already exists locally,
        given its default filename.

        :param subregion_name: name of a geographic region available on BBBike free download server
        :type subregion_name: str
        :param osm_file_format: file format of the OSM data available on the free download server
        :type osm_file_format: str
        :param data_dir: directory for saving the downloaded file(s);
            if ``None`` (default), the default directory created by the package
        :type data_dir: str or None
        :param update: whether to (check on and) update the data, defaults to ``False``
        :type update: bool
        :param verbose: whether to print relevant information in console, defaults to ``False``
        :type verbose: bool or int
        :param ret_file_path: whether to return the path to the data file (if it exists),
            defaults to ``False``
        :type ret_file_path: bool
        :return: whether or not the requested data file exists; or the path to the data file
        :rtype: bool or str

        **Examples**::

            >>> import os
            >>> from pyhelpers.dir import delete_dir
            >>> from pydriosm.downloader import BBBikeDownloader, cd_dat_bbbike

            >>> bbbike_downloader = BBBikeDownloader()

            >>> region_name = 'leeds'
            >>> file_format = ".pbf"

            >>> # Download the PBF data of London (to the default directory)
            >>> bbbike_downloader.download_osm_data(region_name, file_format, verbose=True)
            To download .pbf data of the following geographic region(s):
                Leeds
            ? [No]|Yes: yes
            Downloading "Leeds.osm.pbf" to "osm_bbbike\\Leeds\\" ... Done.

            >>> # Check whether the PBF data file exists; `ret_file_path` is by default `False`
            >>> pbf_exists = bbbike_downloader.file_exists(region_name, file_format)

            >>> type(pbf_exists)
            bool
            >>> # If the data file exists at the default directory created by the package
            >>> print(pbf_exists)
            True

            >>> # Set `ret_file_path` to be `True`
            >>> path_to_pbf = bbbike_downloader.file_exists(
            ...     subregion_name=region_name, osm_file_format=file_format, ret_file_path=True)

            >>> # If the data file exists at the default directory created by the package:
            >>> type(path_to_pbf)
            str
            >>> print(os.path.relpath(path_to_pbf))
            osm_bbbike\\Leeds\\Leeds.osm.pbf

            >>> # Remove the directory or the PBF file and check again:
            >>> delete_dir(cd_dat_bbbike(), confirmation_required=False, verbose=True)
            Deleting "osm_bbbike\\" ... Done.
            >>> path_to_pbf = bbbike_downloader.file_exists(
            ...     subregion_name=region_name, osm_file_format=file_format, ret_file_path=True)

            >>> # Since the data file does not exist at the default directory
            >>> type(path_to_pbf)
            bool
            >>> print(path_to_pbf)
            False
        """

        file_exists = _osm_file_exists(
            self, subregion_name=subregion_name, osm_file_format=osm_file_format, data_dir=data_dir,
            update=update, verbose=verbose, ret_file_path=ret_file_path)

        return file_exists

    def download_subregion_data(self, subregion_name, download_dir=None, update=False,
                                confirmation_required=True, interval=None, verbose=False,
                                ret_download_path=False, **kwargs):
        """
        Download OSM data of all available formats for a geographic region.

        :param subregion_name: name of a geographic region available on BBBike free download server
        :type subregion_name: str
        :param download_dir: directory where the downloaded file is saved, defaults to ``None``
        :type download_dir: str or None
        :param update: whether to update the data if it already exists, defaults to ``False``
        :type update: bool
        :param confirmation_required: whether asking for confirmation to proceed, defaults to ``True``
        :type confirmation_required: bool
        :param interval: interval (in second) between downloading two subregions, defaults to ``None``
        :type interval: int or None
        :param verbose: whether to print relevant information in console, defaults to ``False``
        :type verbose: bool or int
        :param ret_download_path: whether to return the path(s) to the downloaded file(s),
            defaults to ``False``
        :type ret_download_path: bool
        :param kwargs: optional parameters of `pyhelpers.ops.download_file_from_url()`_
        :return: the path(s) to the downloaded file(s) when ``ret_download_path`` is ``True``
        :rtype: list or str

        .. _`pyhelpers.ops.download_file_from_url()`:
            https://pyhelpers.readthedocs.io/en/latest/_generated/pyhelpers.ops.download_file_from_url.html

        **Example**::

            >>> import os
            >>> from pyhelpers.dir import delete_dir
            >>> from pydriosm.downloader import BBBikeDownloader, cd_dat_bbbike

            >>> bbbike_downloader = BBBikeDownloader()

            >>> # Download the BBBike OSM data of London
            >>> region_name = 'london'

            >>> bbbike_downloader.download_subregion_data(region_name, verbose=True)
            To download all available BBBike OSM data of London
            ? [No]|Yes: yes
            Downloading:
                London.osm.pbf ... Done.
                London.osm.gz ... Done.
                London.osm.shp.zip ... Done.
                London.osm.garmin-onroad-latin1.zip ... Done.
                London.osm.garmin-onroad.zip ... Done.
                London.osm.garmin-opentopo.zip ... Done.
                London.osm.garmin-osm.zip ... Done.
                London.osm.geojson.xz ... Done.
                London.osm.svg-osm.zip ... Done.
                London.osm.mapsforge-osm.zip ... Done.
                London.osm.navit.zip ... Done.
                London.osm.csv.xz ... Done.
                London.poly ... Done.
                CHECKSUM.txt ... Done.
            Check out the downloaded OSM data at "osm_bbbike\\London\\".

            >>> # Delete the download directory generated above
            >>> delete_dir(cd_dat_bbbike(), verbose=True)
            The directory "osm_bbbike\\" is not empty.
            Confirmed to delete it? [No]|Yes: yes
            Deleting "osm_bbbike\\" ... Done.

            >>> # Download the BBBike OSM data of Leeds
            >>> region_name = 'leeds'
            >>> dwnld_dir = "tests"

            >>> dwnld_paths = bbbike_downloader.download_subregion_data(
            ...     region_name, dwnld_dir, confirmation_required=False, verbose=True,
            ...     ret_download_path=True)
            Downloading all available BBBike OSM data of Leeds:
                Leeds.osm.pbf ... Done.
                Leeds.osm.gz ... Done.
                Leeds.osm.shp.zip ... Done.
                Leeds.osm.garmin-onroad-latin1.zip ... Done.
                Leeds.osm.garmin-onroad.zip ... Done.
                Leeds.osm.garmin-opentopo.zip ... Done.
                Leeds.osm.garmin-osm.zip ... Done.
                Leeds.osm.geojson.xz ... Done.
                Leeds.osm.svg-osm.zip ... Done.
                Leeds.osm.mapsforge-osm.zip ... Done.
                Leeds.osm.navit.zip ... Done.
                Leeds.osm.csv.xz ... Done.
                Leeds.poly ... Done.
                CHECKSUM.txt ... Done.
            Check out the downloaded OSM data at "tests\\Leeds\\".

            >>> for dwnld_path in dwnld_paths:
            ...     print(os.path.relpath(dwnld_path))
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

            >>> # Delete the download directory generated above
            >>> delete_dir(os.path.commonpath(dwnld_paths), verbose=True)
            The directory "tests\\Leeds\\" is not empty.
            Confirmed to delete it? [No]|Yes: yes
            Deleting "tests\\Leeds\\" ... Done.
        """

        subregion_name_ = self.validate_input_subregion_name(subregion_name)
        bbbike_download_dictionary = self.get_download_index()['Catalogue']

        sub_download_cat = bbbike_download_dictionary[subregion_name_]

        if download_dir is None:
            data_dir = cd_dat_bbbike(subregion_name_, mkdir=True)
        else:
            data_dir_ = validate_input_data_dir(download_dir)
            data_dir = os.path.join(data_dir_, subregion_name_)
            if not os.path.exists(data_dir):
                os.makedirs(data_dir)

        if confirmed("To download all available BBBike OSM data of {}\n?".format(subregion_name_),
                     confirmation_required=confirmation_required):

            if verbose:
                if confirmation_required:
                    print("Downloading: ")
                else:
                    print("Downloading all available BBBike OSM data of {}: ".format(subregion_name_))

            download_paths = []

            for download_url, osm_filename in zip(sub_download_cat.URL, sub_download_cat.Filename):
                try:
                    path_to_file = os.path.join(data_dir, osm_filename)

                    if os.path.isfile(path_to_file) and not update:
                        if verbose:
                            print("\t\"{}\" (Already available)".format(os.path.basename(path_to_file)))

                    else:
                        if verbose:
                            print("\t{} ... ".format(osm_filename), end="\n" if verbose == 2 else "")

                        verbose_ = True if verbose == 2 else False

                        download_file_from_url(
                            url=download_url, path_to_file=path_to_file, verbose=verbose_, **kwargs)

                        if verbose and verbose != 2:
                            print("Done.")

                        if isinstance(interval, int):  # or os.path.getsize(path_to_file) / (1024 ** 2) <= 5:
                            time.sleep(secs=interval)

                    if os.path.isfile(path_to_file):
                        download_paths.append(path_to_file)

                except Exception as e:
                    if verbose:
                        print("Failed. {}.".format(e))

            if verbose and len(download_paths) > 1:
                rel_path = os.path.relpath(os.path.commonpath(download_paths))
                if verbose == 2:
                    print("All done.")

                print("Check out the downloaded OSM data at \"{}\\\".".format(rel_path))

            download_paths_ = _download_paths(self, download_dir=download_dir, download_paths=download_paths)

            if ret_download_path:
                return download_paths_

    def download_osm_data(self, subregion_names, osm_file_format, download_dir=None, update=False,
                          confirmation_required=True, interval=None, verbose=False,
                          ret_download_path=False, **kwargs):
        """
        Download OSM data (in a specific file format) of one (or multiple) geographic region(s).

        :param subregion_names: name of a geographic region (or names of multiple geographic regions)
            available on BBBike free download server
        :type subregion_names: str or list
        :param osm_file_format: format (file extension) of an OSM data
        :type osm_file_format: str
        :param download_dir: directory where downloaded OSM file is saved;
            if ``None`` (default), the default directory created by the package
        :type download_dir: str or None
        :param update: whether to update the data if it already exists, defaults to ``False``
        :type update: bool
        :param confirmation_required: whether asking for confirmation to proceed, defaults to ``True``
        :type confirmation_required: bool
        :param interval: interval (in second) between downloading two subregions, defaults to ``None``
        :type interval: int or None
        :param verbose: whether to print relevant information in console, defaults to ``False``
        :type verbose: bool or int
        :param ret_download_path: whether to return the path(s) to the downloaded file(s),
            defaults to ``False``
        :type ret_download_path: bool
        :return: the path(s) to the downloaded file(s) when ``ret_download_path`` is ``True``
        :rtype: list or str

        **Examples**::

            >>> import os
            >>> from pyhelpers.dir import delete_dir
            >>> from pydriosm.downloader import BBBikeDownloader, cd_dat_bbbike

            >>> bbbike_downloader = BBBikeDownloader()

            >>> region_names = 'London'
            >>> file_format = 'pbf'

            >>> bbbike_downloader.download_osm_data(region_names, file_format, verbose=True)
            To download .pbf data of the following geographic region(s):
                London
            ? [No]|Yes: yes
            Downloading "London.osm.pbf" to "osm_bbbike\\London\\" ... Done.

            >>> # Delete the created directory "osm_bbbike"
            >>> delete_dir(cd_dat_bbbike(), verbose=True)
            The directory "osm_bbbike\\" is not empty.
            Confirmed to delete it? [No]|Yes: yes
            Deleting "osm_bbbike\\" ... Done.

            >>> region_names = ['leeds', 'birmingham']
            >>> dwnld_dir = "tests"

            >>> dwnld_paths = bbbike_downloader.download_osm_data(region_names, file_format,
            ...                                                   dwnld_dir, verbose=True,
            ...                                                   ret_download_path=True)
            To download .pbf data of the following geographic region(s):
                Leeds
                Birmingham
            ? [No]|Yes: yes
            Downloading "Leeds.osm.pbf" to "tests\\" ... Done.
            Downloading "Birmingham.osm.pbf" to "tests\\" ... Done.

            >>> for dwnld_path in dwnld_paths:
            ...     print(os.path.relpath(dwnld_path))
            tests\\Leeds.osm.pbf
            tests\\Birmingham.osm.pbf

            >>> # Delete the above downloaded data files
            >>> for dwnld_path in dwnld_paths:
            ...     os.remove(dwnld_path)
        """

        info = _file_exists(
            self, subregion_names=subregion_names, osm_file_format=osm_file_format, download_dir=download_dir,
            update=update, confirmation_required=confirmation_required, verbose=verbose)

        (subregion_names_, osm_file_format_, confirmation_required_, update_msg, downloads_list,
         existing_file_paths) = info

        confirmation_required_ = confirmation_required_ and confirmation_required

        if confirmed("To {} {} data of the following geographic region(s):"
                     "\n\t{}\n?".format(update_msg, osm_file_format_, "\n\t".join(downloads_list)),
                     confirmation_required=confirmation_required_):

            download_paths = []

            for sub_reg_name in subregion_names_:

                # Get essential information for the download
                subregion_name_, osm_filename, download_url, path_to_file = self.get_valid_download_info(
                    subregion_name=sub_reg_name, osm_file_format=osm_file_format_, download_dir=download_dir,
                    mkdir=True)

                if not os.path.isfile(path_to_file) or update:
                    _download_osm_data(
                        download_url=download_url, path_to_file=path_to_file, verbose=verbose, **kwargs)

                if os.path.isfile(path_to_file):
                    download_paths.append(path_to_file)

                if isinstance(interval, int):  # or os.path.getsize(path_to_file) / (1024 ** 2) <= 5:
                    time.sleep(secs=interval)

        else:
            download_paths = existing_file_paths

        download_paths_ = _download_paths(self, download_dir=download_dir, download_paths=download_paths)

        if ret_download_path:
            return download_paths_
