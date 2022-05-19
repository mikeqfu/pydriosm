"""
Download `OpenStreetMap <https://www.openstreetmap.org/>`_ (OSM) data from free download servers:
`Geofabrik <https://download.geofabrik.de/>`_ and `BBBike <https://download.bbbike.org/>`_.
"""

import collections
import copy
import csv
import io
import json
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request

import bs4
import pandas as pd
import requests
import shapely.geometry
from pyhelpers.dir import cd, validate_dir
from pyhelpers.ops import confirmed, download_file_from_url, fake_requests_headers, is_url, \
    parse_size, update_dict
from pyhelpers.store import load_pickle, save_pickle
from pyhelpers.text import find_similar_str
from pyrcs.parser import parse_tr

from pydriosm.utils import cd_data, unique_everseen


# == Specify assistant functions/classes ===========================================================


def _get_valid_download_info(cls, subregion_name, osm_file_format, download_dir=None, **kwargs):
    """
    Get information of downloading (or downloaded) data file.

    The information includes a valid subregion name, a default filename, a URL and
    an absolute path where the data file is (to be) saved locally.

    :param subregion_name: name of a (sub)region available on BBBike free download server
    :type subregion_name: str
    :param osm_file_format: file format/extension of the OSM data available on the download server
    :type osm_file_format: str
    :param download_dir: directory for saving the downloaded file(s), defaults to ``None``;
        when ``download_dir=None``, it refers to the method
        :py:meth:`~pydriosm.downloader.BBBike.cd`
    :type download_dir: str or None
    :param kwargs: [optional] parameters of `pyhelpers.dir.cd()`_,
        including ``mkdir``(default: ``False``)
    :return: valid subregion name, filename, download url and absolute file path
    :rtype: tuple

    .. _`pyhelpers.dir.cd()`:
        https://pyhelpers.readthedocs.io/en/latest/_generated/pyhelpers.dir.cd.html

    **Examples**::

        >>> from pydriosm.downloader import _get_valid_download_info, GeofabrikDownloader
        >>> import os

        >>> gfd = GeofabrikDownloader()

        >>> subrgn_name = 'london'
        >>> file_format = "pbf"
        >>> dwnld_dir = 'osm_test'

        >>> # valid subregion name, filename, download url and absolute file path
        >>> info = _get_valid_download_info(gfd, subrgn_name, file_format, dwnld_dir)
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

    subregion_name_, download_url = cls.get_subregion_download_url(
        subregion_name=subregion_name, osm_file_format=osm_file_format)
    osm_filename = os.path.basename(download_url)

    if download_dir is None:
        # default directory of package data
        path_to_file = cls.cdd(subregion_name_, osm_filename, **kwargs)
    else:
        download_dir_ = validate_dir(path_to_dir=download_dir)
        path_to_file = cd(download_dir_, osm_filename, **kwargs)

    return subregion_name_, osm_filename, download_url, path_to_file


def _if_osm_file_exists(cls, subregion_name, osm_file_format, data_dir=None, update=False,
                        verbose=False, ret_file_path=False):
    """
    Check if the data file of a queried geographic (sub)region already exists locally,
    given its default filename.

    :param cls: instance of a downloader class
    :type cls: pydriosm.downloader.GeofabrikDownloader or pydriosm.downloader.BBBikeDownloader
    :param subregion_name: name of a (sub)region available on a free download server
    :type subregion_name: str
    :param osm_file_format: file format/extension of OSM the data available on the free download server
    :type osm_file_format: str
    :param data_dir: directory for saving the downloaded file(s), defaults to ``None``;
        when ``data_dir=None``, it refers to the method
        :py:meth:`~pydriosm.downloader.GeofabrikDownloader.cdd`
    :type data_dir: str or None
    :param update: whether to (check and) update the data, defaults to ``False``
    :type update: bool
    :param verbose: whether to print relevant information in console, defaults to ``False``
    :type verbose: bool or int
    :param ret_file_path: whether to return the pathname of the data file (if it exists),
        defaults to ``False``
    :type ret_file_path: bool
    :return: whether the requested data file exists; or the path to the data file
    :rtype: bool or str

    **Test**::

        >>> from pydriosm.downloader import GeofabrikDownloader, BBBikeDownloader, _if_osm_file_exists
        >>> from pyhelpers.dir import delete_dir
        >>> import os

        >>> gfd = GeofabrikDownloader()
        >>> subrgn_name = 'london'  # subregion_name = subrgn_name
        >>> file_format = "pbf"  # osm_file_format = file_format

        >>> gfd.download_osm_data(subrgn_name, file_format, verbose=True)
        Downloading "greater-london-latest.osm.pbf" to "osm_geofabrik\\... ... London\\" ... Done.

        >>> # Check whether the PBF data file exists; `ret_file_path` is by default `False`
        >>> pbf_exists = _if_osm_file_exists(gfd, subrgn_name, file_format)

        >>> type(pbf_exists)
        bool

        >>> # If the data file exists at the default directory created by the package
        >>> print(pbf_exists)
        True

        >>> # Set `ret_file_path` to be `True`
        >>> path_to_pbf = _if_osm_file_exists(gfd, subrgn_name, file_format, ret_file_path=True)

        >>> # If the data file exists at the default directory created by the package:
        >>> type(path_to_pbf)
        str
        >>> print(os.path.relpath(path_to_pbf))
        osm_geofabrik\\Europe\\Great Britain\\England\\greater-london-latest.osm.pbf

        >>> # Remove the directory or the PBF file and check again:
        >>> delete_dir(gfd.cdd(), verbose=True)
        The directory "osm_geofabrik\\" is not empty.
        Confirmed to delete it? [No]|Yes: yes
        Deleting "osm_geofabrik\\" ... Done.

        >>> path_to_pbf = _if_osm_file_exists(gfd, subrgn_name, file_format, ret_file_path=True)

        >>> # Since the data file does not exist at the default directory
        >>> type(path_to_pbf)
        bool

        >>> print(path_to_pbf)
        False
    """

    subregion_name_ = cls.validate_subregion_name(subregion_name=subregion_name)
    osm_file_format_ = cls.validate_file_format(osm_file_format=osm_file_format)

    if getattr(cls, 'NAME') == 'Geofabrik':
        # 'get_default_path_to_osm_file' in dir(downloader_cls):
        default_fn, path_to_file = cls.get_default_path_to_osm_file(
            subregion_name=subregion_name_, osm_file_format=osm_file_format_)
    else:
        assert getattr(cls, 'NAME') == 'BBBike'
        _, default_fn, _, path_to_file = cls.get_valid_download_info(
            subregion_name_, osm_file_format_, data_dir, mkdir=False)

    if default_fn is None:
        if verbose == 2:
            print("{} data for \"{}\" is not available from {} free download server.".format(
                osm_file_format_, subregion_name_, getattr(cls, 'NAME')))
        file_exists = False

    else:
        if data_dir is not None and getattr(cls, 'NAME') == 'Geofabrik':
            path_to_file = os.path.join(validate_dir(data_dir), default_fn)

        if os.path.exists(path_to_file):
            if verbose == 2 and not update:
                rel_p = os.path.relpath(os.path.dirname(path_to_file))
                print(f"\"{default_fn}\" of {subregion_name_} is available at \"{rel_p}\".")

            if ret_file_path:
                file_exists = path_to_file
            else:
                file_exists = True

        else:
            file_exists = False

    return file_exists


def _file_exists(cls, subregion_names, osm_file_format, download_dir, update, confirmation_required,
                 verbose):
    """
    Check if a requested data file already exists and compile information for
    :py:meth:`GeofabrikDownloader.download_osm_data()
    <pydriosm.downloader.GeofabrikDownloader.download_osm_data>` and
    :py:meth:`BBBikeDownloader.download_osm_data()
    <pydriosm.downloader.BBBikeDownloader.download_osm_data>`

    :param cls: instance of a downloader class
    :type cls: pydriosm.downloader.GeofabrikDownloader or pydriosm.downloader.BBBikeDownloader
    :param subregion_names: name(s) of geographic (sub)region(s) available on a free download server
    :type subregion_names: str or list
    :param osm_file_format: file format of the OSM data available on the free download server
    :type osm_file_format: str
    :param download_dir: directory for saving the downloaded file(s)
    :type download_dir: str or None
    :param update: whether to (check on and) update the data
    :type update: bool
    :param verbose: whether to print relevant information in console
    :type verbose: bool or int
    :return: whether the requested data file exists; or the path to the data file
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
    subregion_names_ = [cls.validate_subregion_name(x) for x in subregion_names_]

    osm_file_format_ = cls.validate_file_format(osm_file_format)

    downloads_list_ = subregion_names_.copy()

    existing_file_paths = []  # Paths of existing files

    for subregion_name in subregion_names_:
        path_to_file = _if_osm_file_exists(
            cls=cls, subregion_name=subregion_name,
            osm_file_format=osm_file_format_, data_dir=download_dir, update=update,
            ret_file_path=True)

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

    rslt = (subregion_names_, osm_file_format_, confirmation_required_, update_msg, downloads_list,
            existing_file_paths)

    return rslt


class InvalidSubregionName(Exception):
    pass


class InvalidFileFormat(Exception):
    pass


class _Downloader:
    """
    Initialization of a downloader.
    """

    #: Name of the free download server
    NAME = None
    #: Full name of the data resource
    LONG_NAME = None
    #: URL of the homepage to the free download server
    URL = None
    #: URL of the official download index
    DOWNLOAD_INDEX_URL = None
    #: Filename extensions of the data files available from Geofabrik download server
    FILE_FORMATS = []
    #: Default download directory
    DEFAULT_DOWNLOAD_DIR = 'osm'

    def __init__(self, download_dir=None):

        self.valid_file_formats = self.FILE_FORMATS.copy()

        if download_dir is None:
            self.download_dir = self.cdd()  # cd(self.DEFAULT_DOWNLOAD_DIR)
        else:
            self.download_dir = validate_dir(path_to_dir=download_dir)

        self.subregion_names = None
        self.file_formats = None
        self.download_paths = None

    def cdd(self, *sub_dir, mkdir=False, **kwargs):
        """
        Change directory to default data directory and its subdirectories or a specific file.

        :param sub_dir: name of directory; names of directories (and/or a filename)
        :type sub_dir: str or os.PathLike[str]
        :param mkdir: whether to create a directory, defaults to ``False``
        :type mkdir: bool
        :param kwargs: [optional] parameters of `pyhelpers.dir.cd()`_
        :return: an absolute pathname to a directory (or a file)
        :rtype: str or os.PathLike[str]

        .. _`pyhelpers.dir.cd()`:
            https://pyhelpers.readthedocs.io/en/latest/_generated/pyhelpers.dir.cd.html

        **Examples**::

            >>> from pydriosm.downloader import GeofabrikDownloader
            >>> import os

            >>> gfd = GeofabrikDownloader()

            >>> os.path.relpath(gfd.cdd())
            'osm_geofabrik'

            >>> os.path.exists(gfd.cdd())
            False
        """

        pathname = cd(self.DEFAULT_DOWNLOAD_DIR, *sub_dir, mkdir=mkdir, **kwargs)

        return pathname

    @staticmethod
    def _cfm_msg(update, path_to_pickle, dat_name, note=""):
        """

        :param update:
        :param path_to_pickle:
        :param dat_name:
        :param note:
        :return:

        from pydriosm.downloader import _cfm_msg

        _cfm_msg

        """
        cfm_status = "update the" if (os.path.exists(path_to_pickle) or update) else "compile"
        cfm_msg = f"To {cfm_status} data of {dat_name}" + (" " + note if note else "") + "\n?"

        return cfm_msg

    @staticmethod
    def _status_msg(verbose, confirmation_required, dat_name, note="", end=" ... "):
        """

        :param verbose:
        :param confirmation_required:
        :param dat_name:
        :param note:
        :param end:
        :return:
        """

        if verbose:
            status = "Compiling"
            suffix = "the data" if confirmation_required else f"data of {dat_name}"
            status_msg = " ".join([status, suffix]) + (" " + note if note else "")
            print(status_msg, end=end)

    @staticmethod
    def _otherwise_msg(verbose, update, path_to_pickle, dat_name, err=None):
        verbose_ = verbose is True or verbose == 1

        if err is not None:
            if verbose_:
                print(f"Failed. {err}")
        else:
            if verbose == 2:
                status = "updating" if update or os.path.exists(path_to_pickle) else "collecting"
                print(f"The {status} of {dat_name} is cancelled, or no data is available.")
            # elif verbose_:
            #     print(f"No data of {dat_name} is available.")

    def _get_auxiliary_data(self, func, dat_name, update, confirmation_required, verbose,
                            cfm_msg_note="", status_msg_note="", status_msg_end=" ... "):
        if dat_name is None:
            dat_name = self.NAME

        path_to_pickle = cd_data(dat_name.replace(" ", "_").lower() + ".pickle")

        if os.path.isfile(path_to_pickle) and not update:
            data = load_pickle(path_to_pickle)

        else:
            data = None

            cfm_msg = self._cfm_msg(
                update=update, path_to_pickle=path_to_pickle, dat_name=dat_name, note=cfm_msg_note)

            if confirmed(cfm_msg, confirmation_required=confirmation_required):
                self._status_msg(
                    verbose=verbose, confirmation_required=confirmation_required, dat_name=dat_name,
                    note=status_msg_note, end=status_msg_end)

                try:
                    data = func(path_to_pickle, verbose)

                except Exception as e:
                    self._otherwise_msg(
                        verbose=verbose, update=update, path_to_pickle=path_to_pickle,
                        dat_name=dat_name, err=e)

            else:
                self._otherwise_msg(
                    verbose=verbose, update=update, path_to_pickle=path_to_pickle, dat_name=dat_name)

        return data

    @staticmethod
    def _download_osm_data(download_url, path_to_file, verbose, **kwargs):
        """
        Download an OSM data file.

        :param download_url: a valid URL of an OSM data file
        :type download_url: str
        :param path_to_file: path where the downloaded OSM data file is saved
        :type path_to_file: str
        :param verbose: whether to print relevant information in console
        :type verbose: bool or int
        :param kwargs: optional parameters of `pyhelpers.ops.download_file_from_url()`_

        .. _`pyhelpers.ops.download_file_from_url()`:
            https://pyhelpers.readthedocs.io/en/latest/_generated/
            pyhelpers.ops.download_file_from_url.html

        **Test**::

            import os
            from pydriosm.downloader import _download_osm_data

            filename = 'rutland-latest.osm.pbf'
            download_url = f'https://download.geofabrik.de/europe/great-britain/england/{filename}'
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

            print(f"{status_msg} \"{os.path.basename(path_to_file)}\" {prep} \"{rel_path}\\\"",
                  end="\n" if verbose == 2 else " ... ")

        try:
            download_file_from_url(
                url=download_url, path_to_file=path_to_file, verbose=True if verbose == 2 else False,
                **kwargs)

            if verbose:
                print("Done.")

        except Exception as e:
            if verbose:
                print("Failed. {}".format(e))

    def _download_paths(self, download_dir, download_paths):
        """
        Get download path(s).

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
            self.download_dir = list(dict.fromkeys(os.path.dirname(x) for x in download_paths))
            if len(self.download_dir) == 1:
                self.download_dir = self.download_dir[0]
        else:
            self.download_dir = validate_dir(path_to_dir=download_dir)

        if len(download_paths) == 1:
            download_paths = download_paths[0]

        return download_paths


# == Download OSM data =============================================================================


class GeofabrikDownloader(_Downloader):
    """
    Download OSM data from `Geofabrik`_ free download server.

    .. _`Geofabrik`: https://download.geofabrik.de/
    """

    #: Name of the free download server
    NAME = 'Geofabrik'
    #: Full name of the data resource
    LONG_NAME = 'Geofabrik OpenStreetMap data extracts'
    #: URL of the homepage to the free download server
    URL = 'https://download.geofabrik.de/'
    #: URL of the official download index
    DOWNLOAD_INDEX_URL = urllib.parse.urljoin(URL, 'index-v1.json')
    #: Filename extensions of the data files available from Geofabrik download server
    FILE_FORMATS = ['.osm.pbf', '.shp.zip', '.osm.bz2']
    #: Default download directory
    DEFAULT_DOWNLOAD_DIR = "osm_geofabrik"

    def __init__(self, download_dir=None):
        """
        :param download_dir: name or pathname of a directory for saving downloaded data files,
            defaults to ``None``; when ``download_dir=None``, downloaded data files are saved to a
            folder named 'osm_geofabrik' under the current working directory
        :type download_dir: str or os.PathLike[str] or None

        :ivar list valid_file_formats: file formats (or filename extensions) of the data files
            available from Geofabrik download server
        :ivar str or list or None download_dir: (in accordance with the parameter ``download_dir``)

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
            'osm_geofabrik'
        """

        super().__init__(download_dir=download_dir)

    @staticmethod
    def get_raw_directory_index(url, verbose=False):
        """
        Get a raw directory index (including download information of older file logs).

        :param url: URL of a web page of a data resource (e.g. a subregion)
        :type url: str
        :param verbose: whether to print relevant information in console, defaults to ``False``
        :type verbose: bool or int
        :return: information of raw directory index
        :rtype: pandas.DataFrame or None

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
            >>> raw_index.head()
                                           file  ...                                             url
            0      great-britain-140101.osm.pbf  ...  https://download.geofabrik.de/europe/great-...
            1  great-britain-140101.osm.pbf.md5  ...  https://download.geofabrik.de/europe/great-...
            2      great-britain-150101.osm.pbf  ...  https://download.geofabrik.de/europe/great-...
            3  great-britain-150101.osm.pbf.md5  ...  https://download.geofabrik.de/europe/great-...
            4      great-britain-160101.osm.pbf  ...  https://download.geofabrik.de/europe/great-...

            [5 rows x 5 columns]
        """

        if verbose:
            print(f"Collecting the raw directory index on '{url}'", end=" ... ")

        try:
            source = requests.get(url=url, headers=fake_requests_headers())
            soup = bs4.BeautifulSoup(markup=source.content, features='html.parser')

            source.close()

            cold_soup = soup.find(name='div', attrs={'id': 'details'})
            ths, tds = [], []
            for tr in cold_soup.find_all(name='tr'):
                if len(tr.find_all('th')) > 0:
                    ths = [x.get_text(strip=True) for x in tr.find_all(name='th')]
                else:
                    tds.append([x.get_text(strip=True) for x in tr.find_all(name='td')])

            raw_directory_index = pd.DataFrame(data=tds, columns=ths)
            raw_directory_index.loc[:, 'date'] = pd.to_datetime(raw_directory_index['date'])
            raw_directory_index.loc[:, 'size'] = raw_directory_index['size'].astype('int64')

            raw_directory_index['metric_file_size'] = raw_directory_index['size'].map(
                lambda x: parse_size(x, binary=False, precision=0 if (x <= 1000) else 1))

            raw_directory_index['url'] = raw_directory_index['file'].map(
                lambda x: urllib.parse.urljoin(url, x))

            if verbose:
                print("Done.")

        except (urllib.error.HTTPError, AttributeError, TypeError, ValueError):
            if verbose:
                print("Failed.")

                if len(urllib.parse.urlparse(url).path) <= 1:
                    print("No raw directory index is available on the web page.")

            raw_directory_index = None

        return raw_directory_index

    @staticmethod
    def _parse_download_index_urls(urls):
        """
        Parse the dictionary of download URLs in the (original) dataframe of download index.

        :param urls: (original) series of the URLs provided in the official download index
        :type urls: pandas.Series
        :return: download index with parsed data of the URLs for downloading data
        :rtype: pandas.DataFrame
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

    def _download_index(self, path_to_pickle, verbose):
        # import geopandas as gpd
        # download_index = pd.DataFrame(gpd.read_file(filename=self.DOWNLOAD_INDEX_URL)))

        raw_data_ = requests.get(self.DOWNLOAD_INDEX_URL)
        raw_data = pd.DataFrame(json.loads(raw_data_.content)['features'])

        # properties
        properties_ = pd.DataFrame(raw_data['properties'].to_list())
        properties = properties_.where(properties_.notnull(), None)

        # geometry
        geometry_ = pd.DataFrame(raw_data['geometry'].to_list())
        geometry = geometry_.apply(
            lambda x: getattr(shapely.geometry, x['type'])(
                [shapely.geometry.Polygon(x['coordinates'][0][0])]).geoms, axis=1)
        geometry = pd.DataFrame(geometry, columns=['geometry'])

        dwnld_idx = pd.concat(objs=[properties, geometry], axis=1)

        # name
        temp_names = dwnld_idx['name'].str.strip().str.replace('<br />', ' ')
        dwnld_idx.loc[:, 'name'] = temp_names.map(
            lambda x: x.replace('us/', '').title() if x.startswith('us/') else x)

        temp = (k for k, v in collections.Counter(dwnld_idx.name).items() if v > 1)
        duplicates = {i: x for k in temp for i, x in enumerate(dwnld_idx.name) if x == k}

        for dk in duplicates.keys():
            if dwnld_idx.loc[dk, 'id'].startswith('us/'):
                dwnld_idx.loc[dk, 'name'] += ' (US)'

        # urls
        urls_column_name = 'urls'

        urls = self._parse_download_index_urls(dwnld_idx[urls_column_name])
        del dwnld_idx[urls_column_name]

        download_index = pd.concat(objs=[dwnld_idx, urls], axis=1)

        if verbose:
            print("Done.")

        save_pickle(download_index, path_to_pickle=path_to_pickle, verbose=verbose)

        return download_index

    def get_download_index(self, update=False, confirmation_required=True, verbose=False):
        """
        Get the official index of downloads for all available geographic (sub)regions.

        :param update: whether to (check on and) update the package data, defaults to ``False``
        :type update: bool
        :param confirmation_required: whether asking for confirmation to proceed, defaults to ``True``
        :type confirmation_required: bool
        :param verbose: whether to print relevant information in console, defaults to ``False``
        :type verbose: bool or int
        :return: the official index of all downloads
        :rtype: pandas.DataFrame or None

        **Examples**::

            >>> from pydriosm.downloader import GeofabrikDownloader

            >>> gfd = GeofabrikDownloader()

            >>> # Official index of all available downloads
            >>> geofabrik_dwnld_idx = gfd.get_download_index()
            >>> len(geofabrik_dwnld_idx) >= 475
            True
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

        dat_name = ' '.join([self.NAME, 'index of all downloads'])

        download_index = self._get_auxiliary_data(
            self._download_index, dat_name, update, confirmation_required, verbose)

        return download_index

    @staticmethod
    def _parse_subregion_table_tr(tr, url):
        """
        Parse a <tr> tag under a <table> tag of the HTML data of a (sub)region.

        :param tr: <tr> tag under a <table> tag of a subregion's HTML data
        :type tr: bs4.element.Tag
        :param url: URL of a subregion's web page
        :type url: str
        :return: data contained in the <tr> tag
        :rtype: list
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

    def get_subregion_table(self, url, verbose=False):
        """
        Get download information of all geographic (sub)regions on a web page.

        :param url: URL of a subregion's web page
        :type url: str
        :param verbose: whether to print relevant information in console, defaults to ``False``
        :type verbose: bool or int
        :return: download information of all available subregions on the given ``url``
        :rtype: pandas.DataFrame or None

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
            Collecting information about subregions of "Antarctica" ... Failed.
            >>> antarctica is None
            True

            >>> # To get more information about the above failure, set `verbose=2`
            >>> antarctica = gfd.get_subregion_table(antarctica_url, verbose=2)
            Collecting information about subregions of "Antarctica" ... Failed.
            No subregion data is available for "Antarctica" on Geofabrik's free download server.
            >>> antarctica is None
            True
        """

        region_name = url.split('/')[-1].split('.')[0].replace('-', ' ').title()
        if verbose:
            print("Collecting information about subregions of \"{}\"".format(region_name), end=" ... ")

        try:
            # Specify column names
            column_names = ['subregion', 'subregion-url'] + self.valid_file_formats
            column_names.insert(3, '.osm.pbf-size')
            # column_names == [
            #     'subregion', 'subregion-url', '.osm.pbf', '.osm.pbf-size', '.shp.zip', '.osm.bz2']

            source = requests.get(url=url, headers=fake_requests_headers())
            soup = bs4.BeautifulSoup(markup=source.content, features='html.parser')
            source.close()

            tr_data = []

            h3_tags = soup.find_all(name='h3', text=re.compile(r'(Special )?Sub[ \-]Regions?'))
            if len(h3_tags) > 0:
                for h3_tag in h3_tags:
                    table = h3_tag.find_next(
                        name='table', attrs={'id': re.compile(r'(special)?subregions')})
                    trs = table.findChildren(name='tr', onmouseover=True)
                    tr_data += [self._parse_subregion_table_tr(tr=tr, url=url) for tr in trs]
            else:
                table_tags = soup.find_all(
                    name='table', attrs={'id': re.compile(r'(special)?subregions')})
                for table_tag in table_tags:
                    trs = table_tag.findChildren(name='tr', onmouseover=True)
                    tr_data += [self._parse_subregion_table_tr(tr=tr, url=url) for tr in trs]

            tbl = pd.DataFrame(data=tr_data, columns=column_names)
            table = tbl.where(pd.notnull(tbl), None)

            if verbose:
                print("Done.")

        except (AttributeError, ValueError, TypeError):
            if verbose:
                print(f"Failed.")
                if verbose == 2:
                    print(f"No subregion data is available for \"{region_name}\" "
                          f"on {self.NAME}'s free download server.")

            table = None

        except (ConnectionRefusedError, ConnectionError):
            if verbose:
                print("Failed.")
                if verbose == 2:
                    print(f"Errors occurred when trying to connect {self.NAME}'s free download server.")

            table = None

        return table

    def _continents_subregion_tables(self, path_to_pickle, verbose):
        # Scan the homepage to collect info of regions for each continent
        source = requests.get(url=self.URL, headers=fake_requests_headers())
        soup = bs4.BeautifulSoup(markup=source.content, features='html.parser')
        source.close()

        tds = soup.find_all(name='td', attrs={'class': 'subregion'})
        continent_names = [td.a.text for td in tds]

        continent_links = [urllib.parse.urljoin(self.URL, url=td.a['href']) for td in tds]
        continent_links_dat = [self.get_subregion_table(url=url) for url in continent_links]
        continents_subregion_tables = dict(zip(continent_names, continent_links_dat))

        if verbose:
            print("Done.")

        save_pickle(continents_subregion_tables, path_to_pickle=path_to_pickle, verbose=verbose)

        return continents_subregion_tables

    def get_continents_subregion_tables(self, update=False, confirmation_required=True, verbose=False):
        """
        Get download information of continents.

        :param update: whether to (check on and) update the package data, defaults to ``False``
        :type update: bool
        :param confirmation_required: whether asking for confirmation to proceed, defaults to ``True``
        :type confirmation_required: bool
        :param verbose: whether to print relevant information in console, defaults to ``False``
        :type verbose: bool or int
        :return: download information about available subregions of each continent
        :rtype: dict or None

        **Examples**::

            >>> from pydriosm.downloader import GeofabrikDownloader

            >>> gfd = GeofabrikDownloader()

            >>> # Download information of subregions for each continent
            >>> continent_tables = gfd.get_continents_subregion_tables()

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

        dat_name = ' '.join([self.NAME, 'continent subregions'])

        continents_subregion_tables = self._get_auxiliary_data(
            self._continents_subregion_tables, dat_name, update, confirmation_required, verbose)

        return continents_subregion_tables

    def _compile_region_subregion_tier(self, subregion_tables):
        """
        Find out the all (sub)regions and their subregions.

        :param subregion_tables: download URLs of subregions;
            see examples of the methods
            :py:meth:`~pydriosm.downloader.GeofabrikDownloader.get_subregion_table` and
            :py:meth:`~pydriosm.downloader.GeofabrikDownloader.get_continents_subregion_tables`
        :type subregion_tables: dict
        :return: a dictionary of region-subregion, and a list of (sub)regions without subregions
        :rtype: typing.Tuple[dict, list]
        """

        having_subregions = subregion_tables.copy()
        region_subregion_tier = having_subregions.copy()

        having_no_subregions = []
        for k, v in subregion_tables.items():
            if isinstance(v, pd.DataFrame):  # and v is not None
                update_dict(
                    dictionary=region_subregion_tier, updates={k: set(v['subregion'])}, inplace=True)
            else:
                having_no_subregions.append(k)
                having_subregions.pop(k)

        having_subregions_temp = having_subregions.copy()

        while having_subregions_temp:
            for region_name, subregion_table in having_subregions.items():
                subregion_tbls = [
                    self.get_subregion_table(url=url) for url in subregion_table['subregion-url']]
                sub_subregion_tables = dict(zip(subregion_table['subregion'], subregion_tbls))

                region_subregion_tiers_, having_no_subregions_ = self._compile_region_subregion_tier(
                    subregion_tables=sub_subregion_tables)

                having_no_subregions += having_no_subregions_

                region_subregion_tier.update({region_name: region_subregion_tiers_})
                having_subregions_temp.pop(region_name)

        having_no_subregions = list(unique_everseen(having_no_subregions))

        return region_subregion_tier, having_no_subregions

    def _region_subregion_tier(self, path_to_pickle, verbose):
        continents_subregion_tables = self.get_continents_subregion_tables(
            update=False, confirmation_required=False, verbose=False)

        tiers, having_no_subregions = self._compile_region_subregion_tier(
            subregion_tables=continents_subregion_tables)

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

        save_pickle((tiers, having_no_subregions), path_to_pickle=path_to_pickle, verbose=verbose)

        return tiers, having_no_subregions

    def get_region_subregion_tier(self, update=False, confirmation_required=True, verbose=False):
        """
        Get region-subregion tier.

        This includes all geographic (sub)regions for which data of subregions is unavailable.

        :param update: whether to (check on and) update the package data, defaults to ``False``
        :type update: bool
        :param confirmation_required: whether asking for confirmation to proceed, defaults to ``True``
        :type confirmation_required: bool
        :param verbose: whether to print relevant information in console, defaults to ``False``
        :type verbose: bool or int
        :return: region-subregion tier and all that have no subregions
        :rtype: tuple[dict, list]

        .. _`dict`: https://docs.python.org/3/library/stdtypes.html#dict
        .. _`list`: https://docs.python.org/3/library/stdtypes.html#list

        **Examples**::

            >>> from pydriosm.downloader import GeofabrikDownloader

            >>> gfd = GeofabrikDownloader()

            >>> # region-subregion tier, and all regions that have no subregions
            >>> rgn_subrgn_tier, no_subrgn_list = gfd.get_region_subregion_tier()

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

            >>> len(no_subrgn_list) >= 448
            True
            >>> # Example: five regions that have no subregions
            >>> no_subrgn_list[0:5]
            ['Antarctica', 'Algeria', 'Angola', 'Benin', 'Botswana']
        """

        dat_name = ' '.join([self.NAME, 'region-subregion tier'])

        if update:
            _ = self.get_continents_subregion_tables(
                update=update, confirmation_required=False, verbose=False)

        note_msg = "(Note that this process may take a few minutes)"

        data = self._get_auxiliary_data(
            self._region_subregion_tier, dat_name, update, confirmation_required, verbose,
            cfm_msg_note=note_msg, status_msg_note="" if confirmation_required else note_msg)

        if data is None:
            tiers, having_no_subregions = None, None
        else:
            tiers, having_no_subregions = data

        return tiers, having_no_subregions

    def _catalogue(self, path_to_pickle, verbose):
        source = requests.get(url=self.URL, headers=fake_requests_headers())
        soup = bs4.BeautifulSoup(markup=source.content, features='html.parser')
        source.close()

        # Home table
        home_tr_data = []
        table_tags = soup.find_all(
            name='table', attrs={'id': re.compile(r'(special)?subregions')})
        for table_tag in table_tags:
            trs = table_tag.findChildren(name='tr', onmouseover=True)
            home_tr_data += [
                self._parse_subregion_table_tr(tr=tr, url=self.URL) for tr in trs]

        column_names = ['subregion', 'subregion-url'] + self.valid_file_formats
        column_names.insert(3, '.osm.pbf-size')

        home_subregion_table = pd.DataFrame(data=home_tr_data, columns=column_names)

        # Subregions' tables
        cont_tds = soup.find_all(name='td', attrs={'class': 'subregion'})
        cont_urls = [
            urllib.parse.urljoin(base=self.URL, url=td.a.get('href')) for td in cont_tds]
        continent_tbls = [
            self.get_subregion_table(url=url, verbose=False) for url in cont_urls]
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

        temp = (
            k for k, v in collections.Counter(downloads_catalogue.subregion).items()
            if v > 1)
        duplicates = {
            i: x for k in temp for i, x in enumerate(downloads_catalogue.subregion)
            if x == k}

        for dk in duplicates.keys():
            if os.path.dirname(downloads_catalogue.loc[dk, 'subregion-url']).endswith('us'):
                downloads_catalogue.loc[dk, 'subregion'] += ' (US)'

        if verbose:
            print("Done.")

        save_pickle(downloads_catalogue, path_to_pickle=path_to_pickle, verbose=verbose)

        return downloads_catalogue

    def get_catalogue(self, update=False, confirmation_required=True, verbose=False):
        """
        Get a catalogue of download information.

        Similar to the method :py:meth:`~pydriosm.downloader.GeofabrikDownloader.get_catalogue`.

        :param update: whether to (check on and) update the package data, defaults to ``False``
        :type update: bool
        :param confirmation_required: whether asking for confirmation to proceed, defaults to ``True``
        :type confirmation_required: bool
        :param verbose: whether to print relevant information in console, defaults to ``False``
        :type verbose: bool or int
        :return: a catalogue for all subregion downloads
        :rtype: pandas.DataFrame or None

        **Examples**::

            >>> from pydriosm.downloader import GeofabrikDownloader

            >>> gfd = GeofabrikDownloader()

            >>> # A download catalogue for all subregions
            >>> dwnld_catalog = gfd.get_catalogue()

            >>> type(dwnld_catalog)
            pandas.core.frame.DataFrame
            >>> len(dwnld_catalog) >= 474
            True
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
              `London\\Enfield <https://download.geofabrik.de/europe/great-britain/england/london/>`_
              is not directly available from the web page of `Greater London
              <https://download.geofabrik.de/europe/great-britain/england/greater-london.html>`_.
            - There are two subregions sharing the same name 'Georgia':
              `Europe\\Georgia <https://download.geofabrik.de/europe/georgia.html>`_ and
              `US\\Georgia <https://download.geofabrik.de/north-america/us/georgia.html>`_.
        """

        dat_name = ' '.join([self.NAME, 'downloads catalogue'])

        note_msg = "(Note that this process may take a few minutes)"

        downloads_catalogue = self._get_auxiliary_data(
            self._catalogue, dat_name, update, confirmation_required, verbose,
            cfm_msg_note=note_msg, status_msg_note="" if confirmation_required else note_msg)

        return downloads_catalogue

    def _list_of_subregion_names(self, path_to_pickle, verbose):
        dwnld_index = self.get_download_index(update=False, confirmation_required=False, verbose=False)

        list_of_subregion_names = dwnld_index['name'].to_list()

        if verbose:
            print("Done.")

        save_pickle(list_of_subregion_names, path_to_pickle=path_to_pickle, verbose=verbose)

        return list_of_subregion_names

    def get_list_of_subregion_names(self, update=False, confirmation_required=True, verbose=False):
        """
        Get a list of names of all available geographic (sub)regions.

        :param update: whether to (check on and) update the package data, defaults to ``False``
        :type update: bool
        :param confirmation_required: whether asking for confirmation to proceed, defaults to ``True``
        :type confirmation_required: bool
        :param verbose: whether to print relevant information in console, defaults to ``False``
        :type verbose: bool or int
        :return: names of geographic (sub)regions available on the free download server
        :rtype: typing.List[str] or None

        **Examples**::

            >>> from pydriosm.downloader import GeofabrikDownloader

            >>> gfd = GeofabrikDownloader()

            >>> # A list of the names of available geographic (sub)regions
            >>> subrgn_name_list = gfd.get_list_of_subregion_names()
            >>> len(subrgn_name_list) >= 475
            True
            >>> subrgn_name_list[:5]
            ['Afghanistan', 'Africa', 'Albania', 'Alberta', 'Algeria']
        """

        dat_name = ' '.join([self.NAME, 'subregion name list'])

        if update:
            _ = self.get_download_index(update=update, confirmation_required=False, verbose=False)

        list_of_subregion_names = self._get_auxiliary_data(
            self._list_of_subregion_names, dat_name, update, confirmation_required, verbose)

        return list_of_subregion_names

    def validate_subregion_name(self, subregion_name, **kwargs):
        """
        Validate an input name of a geographic (sub)region.

        The validation is done by matching the input to a name of a geographic (sub)region
        available on Geofabrik free download server.

        :param subregion_name: name/URL of a (sub)region available on Geofabrik free download server
        :type subregion_name: str
        :param kwargs: [optional] parameters of `pyhelpers.text.find_similar_str()`_
        :return: valid subregion name that matches (or is the most similar to) the input
        :rtype: str

        .. _`pyhelpers.text.find_similar_str()`:
            https://pyhelpers.readthedocs.io/en/latest/_generated/pyhelpers.text.find_similar_str.html

        **Examples**::

            >>> from pydriosm.downloader import GeofabrikDownloader

            >>> gfd = GeofabrikDownloader()

            >>> input_subrgn_name = 'london'
            >>> valid_subrgn_name = gfd.validate_subregion_name(input_subrgn_name)
            >>> valid_subrgn_name
            'Greater London'

            >>> input_subrgn_name = 'https://download.geofabrik.de/europe/great-britain.html'
            >>> valid_subrgn_name = gfd.validate_subregion_name(input_subrgn_name)
            >>> valid_subrgn_name
            'Great Britain'
        """

        subregion_names = self.get_list_of_subregion_names()  # Get a list of available

        if subregion_name in subregion_names:
            subregion_name_ = copy.copy(subregion_name)
        elif re.match(r'[Uu][Ss][Aa]?', subregion_name):
            subregion_name_ = 'United States of America'
        elif os.path.isdir(os.path.dirname(subregion_name)) or is_url(url=subregion_name):
            temp_name = os.path.basename(subregion_name)
            subregion_name_ = find_similar_str(x=temp_name, lookup_list=subregion_names, **kwargs)
        else:
            subregion_name_ = find_similar_str(x=subregion_name, lookup_list=subregion_names, **kwargs)

        if subregion_name_ is None:
            raise InvalidSubregionName(
                "The input `subregion_name` is unidentifiable. "
                "Check if the geographic (sub)region exists in the index and retry.")
        else:
            return subregion_name_

    def validate_file_format(self, osm_file_format, **kwargs):
        """
        Validate an input file format of OSM data.

        The validation is done by matching the input to a filename extension available on
        Geofabrik free download server.

        :param osm_file_format: file format/extension of the OSM data
            available on Geofabrik free download server
        :type osm_file_format: str
        :param kwargs: [optional] parameters of `pyhelpers.text.find_similar_str()`_
        :return: formal file format
        :rtype: str

        .. _`pyhelpers.text.find_similar_str()`:
            https://pyhelpers.readthedocs.io/en/latest/_generated/pyhelpers.text.find_similar_str.html

        **Examples**::

            >>> from pydriosm.downloader import GeofabrikDownloader

            >>> gfd = GeofabrikDownloader()

            >>> input_file_format = ".pbf"
            >>> valid_file_format = gfd.validate_file_format(input_file_format)
            >>> valid_file_format
            '.osm.pbf'

            >>> input_file_format = "shp"
            >>> valid_file_format = gfd.validate_file_format(input_file_format)
            >>> valid_file_format
            '.shp.zip'
        """

        if osm_file_format in self.valid_file_formats:
            osm_file_format_ = copy.copy(osm_file_format)
        else:
            osm_file_format_ = find_similar_str(
                x=osm_file_format, lookup_list=self.valid_file_formats, **kwargs)

        if osm_file_format_ not in self.valid_file_formats:
            err_msg = "The input `osm_file_format` should be one of \"{}\".".format(
                '" and "'.join('", "'.join(self.valid_file_formats).rsplit('", "', 1)))
            raise InvalidFileFormat(err_msg)
        else:
            return osm_file_format_

    def get_subregion_download_url(self, subregion_name, osm_file_format, update=False, verbose=False):
        """
        Get a download URL of a geographic (sub)region.

        :param subregion_name: name of a (sub)region available on Geofabrik free download server
        :type subregion_name: str
        :param osm_file_format: file format/extension of the OSM data available on the download server
        :type osm_file_format: str
        :param update: whether to (check on and) update the package data, defaults to ``False``
        :type update: bool
        :param verbose: whether to print relevant information in console, defaults to ``False``
        :type verbose: bool or int
        :return: name and URL of the subregion
        :rtype: typing.Tuple[str, str or None]

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

        # Get an index of download URLs
        subregion_downloads_index = self.get_catalogue(update=update, verbose=verbose)
        subregion_downloads_index.set_index(keys='subregion', inplace=True)

        subregion_name_ = self.validate_subregion_name(subregion_name=subregion_name)
        osm_file_format_ = self.validate_file_format(osm_file_format=osm_file_format)

        # Get the URL
        download_url = subregion_downloads_index.loc[subregion_name_, osm_file_format_]

        return subregion_name_, download_url

    def get_default_osm_filename(self, subregion_name, osm_file_format, update=False):
        """
        get a default filename for a geograpic (sub)region.

        The default filename is derived from the download URL of the requested data file.

        :param subregion_name: name of a (sub)region available on Geofabrik free download server
        :type subregion_name: str
        :param osm_file_format: file format/extension of the OSM data available on the download server
        :type osm_file_format: str
        :param update: whether to (check on and) update the package data, defaults to ``False``
        :type update: bool
        :return: default OSM filename for the ``subregion_name``
        :rtype: str or None

        **Examples**::

            >>> from pydriosm.downloader import GeofabrikDownloader

            >>> gfd = GeofabrikDownloader()

            >>> # Default filename of the PBF data of London
            >>> subrgn_name, file_format = 'london', ".pbf"
            >>> default_fn = gfd.get_default_osm_filename(subrgn_name, file_format)
            >>> default_fn
            'greater-london-latest.osm.pbf'

            >>> # Default filename of the shapefile data of Great Britain
            >>> subrgn_name, file_format = 'britain', ".shp"
            >>> default_fn = gfd.get_default_osm_filename(subrgn_name, file_format)
            No .shp.zip data for Great Britain is available to download.
            >>> default_fn is None
            True
        """

        subregion_name_ = self.validate_subregion_name(subregion_name=subregion_name)
        osm_file_format_ = self.validate_file_format(osm_file_format=osm_file_format)

        _, download_url = self.get_subregion_download_url(
            subregion_name=subregion_name_, osm_file_format=osm_file_format_, update=update)

        if download_url is None:
            print(f"No {osm_file_format_} data for {subregion_name_} is available to download.")
            osm_filename = None

        else:
            osm_filename = os.path.split(download_url)[-1]

        return osm_filename

    def get_default_path_to_osm_file(self, subregion_name, osm_file_format, mkdir=False, update=False,
                                     verbose=False):
        """
        Get a default path to a local directory for storing a downloaded data file.

        The default file path is derived from the download URL of the requested data file.

        :param subregion_name: name of a (sub)region available on Geofabrik free download server
        :type subregion_name: str
        :param osm_file_format: file format/extension of the OSM data available on the download server
        :type osm_file_format: str
        :param mkdir: whether to create a directory, defaults to ``False``
        :type mkdir: bool
        :param update: whether to (check on and) update the package data, defaults to ``False``
        :type update: bool
        :param verbose: whether to print relevant information in console, defaults to ``False``
        :type verbose: bool or int
        :return: default filename of the subregion and default (absolute) path to the file
        :rtype: typing.Tuple[str, str]

        **Examples**::

            >>> from pydriosm.downloader import GeofabrikDownloader
            >>> import os

            >>> gfd = GeofabrikDownloader()

            >>> # Default filename and download path of the PBF data of London
            >>> subrgn_name, file_format = 'london', ".pbf"

            >>> filename, pathname = gfd.get_default_path_to_osm_file(subrgn_name, file_format)
            >>> filename
            'greater-london-latest.osm.pbf'
            >>> os.path.relpath(pathname)
            'osm_geofabrik\\Europe\\Great Britain\\England\\Greater London\\greater-london-latest...
        """

        subregion_name_ = self.validate_subregion_name(subregion_name=subregion_name)
        osm_file_format_ = self.validate_file_format(osm_file_format=osm_file_format)

        subregion_name_, download_url = self.get_subregion_download_url(
            subregion_name=subregion_name_, osm_file_format=osm_file_format_, update=update)

        if download_url is None:
            if verbose:
                print(f"{osm_file_format_} data is not available for {subregion_name_}.")

            # The requested data may not exist
            default_filename, default_file_path = None, None

        else:
            parsed_path = str(urllib.parse.urlparse(download_url).path).lstrip('/').split('/')

            if len(parsed_path) == 1:
                parsed_path = [subregion_name_] + parsed_path

            subregion_names = self.get_list_of_subregion_names()

            sub_dirs = [
                find_similar_str(
                    x=x.split('.')[0].replace('-latest', '').replace('-free', ''),
                    lookup_list=subregion_names)
                if x != 'us' else 'United States of America'
                for x in parsed_path]  # re.split(r'[.-]', x)
            directory = self.cdd(*sub_dirs, mkdir=mkdir)

            default_filename = parsed_path[-1]
            default_file_path = os.path.join(directory, default_filename)

        return default_filename, default_file_path

    def _find_subregions(self, subregion_name, region_subregion_tier=None):
        """
        Find subregions of a given geographic (sub)region.

        :param subregion_name: name of a (sub)region available on Geofabrik free download server
        :type subregion_name: str
        :param region_subregion_tier: region-subregion tier, defaults to ``None``;
            when ``region_subregion_tier=None``, it defaults to the dictionary returned by the method
            :py:meth:`~pydriosm.downloader.GeofabrikDownloader.get_region_subregion_tier`
        :type region_subregion_tier: dict
        :return: name(s) of subregion(s) of the given geographic (sub)region
        :rtype: generator object

        **Examples**::

            >>> from pydriosm.downloader import GeofabrikDownloader

            >>> gfd = GeofabrikDownloader()

            >>> gb_subregions = gfd._find_subregions('Great Britain')
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
                for subrgn in self._find_subregions(subregion_name, v):
                    if isinstance(subrgn, dict):
                        yield list(subrgn.keys())
                    else:
                        yield [subrgn] if isinstance(subrgn, str) else subrgn

    def get_subregions(self, *subregion_name, deep=False):
        """
        Retrieve names of all subregions (if any) of the given geographic (sub)region(s).

        The returned result is based on the region-subregion tier structured by the method
        :py:meth:`~pydriosm.downloader.GeofabrikDownloader.get_region_subregion_tier`.

        See also [`RNS-1 <https://stackoverflow.com/questions/9807634/>`_].

        :param subregion_name: name of a (sub)region, or names of (sub)regions,
            available on Geofabrik free download server
        :type subregion_name: str or None
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
            >>> len(all_subrgn_names) >= 448
            True

            >>> # Names of all subregions of England and North America
            >>> e_na_subrgn_names = gfd.get_subregions('england', 'n america')
            >>> len(e_na_subrgn_names) >= 56
            True
            >>> e_na_subrgn_names[:5]
            ['Bedfordshire', 'Berkshire', 'Bristol', 'Buckinghamshire', 'Cambridgeshire']
            >>> e_na_subrgn_names[-5:]
            ['US Midwest', 'US Northeast', 'US Pacific', 'US South', 'US West']

            >>> # Names of all subregions of North America
            >>> na_subrgn_names = gfd.get_subregions('n america', deep=True)
            >>> len(na_subrgn_names) >= 73
            True

            >>> # Names of subregions of Great Britain
            >>> gb_subrgn_names = gfd.get_subregions('britain')
            >>> gb_subrgn_names
            ['England', 'Scotland', 'Wales']

            >>> # Names of all subregions of Great Britain's subregions
            >>> gb_subrgn_names_ = gfd.get_subregions('britain', deep=True)
            >>> len(gb_subrgn_names_) >= 49
            True
            >>> gb_subrgn_names_[:5]
            ['Scotland', 'Wales', 'Bedfordshire', 'Berkshire', 'Bristol']
        """

        region_subregion_tier, non_subregions_list = self.get_region_subregion_tier()

        if not subregion_name:
            subregion_names = non_subregions_list

        else:
            rslt = []
            for subrgn_name in subregion_name:
                subrgn_name = self.validate_subregion_name(subrgn_name)
                subrgn_names = self._find_subregions(subrgn_name, region_subregion_tier)
                rslt += list(subrgn_names)[0]

            if not deep:
                subregion_names = rslt

            else:
                check_list = [x for x in rslt if x not in non_subregions_list]

                if check_list:
                    rslt_ = list(set(rslt) - set(check_list))
                    rslt_ += self.get_subregions(*check_list)
                else:
                    rslt_ = rslt

                del non_subregions_list, region_subregion_tier, check_list

                subregion_names = list(dict.fromkeys(rslt_))

        return subregion_names

    def specify_sub_download_dir(self, subregion_name, osm_file_format, download_dir=None, **kwargs):
        """
        Specify a directory for downloading data of all subregions of a geographic (sub)region.

        This is useful when the specified format of the data of a geographic (sub)region
        is not available at Geofabrik free download server.

        :param subregion_name: name of a (sub)region available on Geofabrik free download server
        :type subregion_name: str
        :param osm_file_format: file format/extension of the OSM data available on the download server
        :type osm_file_format: str
        :param download_dir: directory for saving the downloaded file(s), defaults to ``None``;
            when ``download_dir=None``, it refers to the method
            :py:meth:`~pydriosm.downloader.GeofabrikDownloader.cdd`
        :type download_dir: str or None
        :param kwargs: [optional] parameters of `pyhelpers.dir.cd()`_,
            including ``mkdir``(default: ``False``)
        :return: pathname of a download directory
            for downloading data of all subregions of the specified (sub)region and format
        :rtype: str

        .. _`pyhelpers.dir.cd()`:
            https://pyhelpers.readthedocs.io/en/latest/_generated/pyhelpers.dir.cd.html

        **Examples**::

            >>> from pydriosm.downloader import GeofabrikDownloader
            >>> import os

            >>> gfd = GeofabrikDownloader()

            >>> subrgn_name = 'london'
            >>> file_format = ".pbf"

            >>> # Default download directory (if the requested data file is not available)
            >>> dwnld_dir = gfd.specify_sub_download_dir(subrgn_name, file_format)
            >>> os.path.relpath(dwnld_dir)
            'osm_geofabrik\\Europe\\Great Britain\\England\\Greater London\\greater-london-latest...

            >>> # When a download directory is specified
            >>> dwnld_dir = "osm_downloads"
            >>> subrgn_name = 'britain'
            >>> file_format = ".shp"

            >>> dwnld_pathname = gfd.specify_sub_download_dir(subrgn_name, file_format, dwnld_dir)
            >>> os.path.relpath(dwnld_pathname)
            'osm_downloads\\great-britain-shp-zip'
        """

        subregion_name_ = self.validate_subregion_name(subregion_name=subregion_name)
        osm_file_format_ = self.validate_file_format(osm_file_format=osm_file_format)

        default_filename_and_file_path = list(self.get_default_path_to_osm_file(
            subregion_name=subregion_name_, osm_file_format=osm_file_format_))

        none_count = len([x for x in default_filename_and_file_path if x is None])
        if none_count == len(default_filename_and_file_path):
            # The required data file is not available
            default_sub_dir = re.sub(r"[. ]", "-", subregion_name_.lower() + osm_file_format_)
            default_file_path = ""  # or, subregion_name_ + "\\"
        else:
            default_filename, default_file_path = default_filename_and_file_path
            default_sub_dir = re.sub(r"[. ]", "-", default_filename).lower()

        if download_dir is None:
            default_download_dir = self.cdd(
                os.path.dirname(default_file_path), default_sub_dir, **kwargs)

        else:
            download_dir_ = validate_dir(path_to_dir=download_dir)
            default_download_dir = cd(download_dir_, default_sub_dir, **kwargs)

        return default_download_dir

    def get_valid_download_info(self, subregion_name, osm_file_format, download_dir=None, **kwargs):
        """
        Get information of downloading (or downloaded) data file.

        The information includes a valid subregion name, a default filename, a URL and
        an absolute path where the data file is (to be) saved locally.

        :param subregion_name: name of a (sub)region available on BBBike free download server
        :type subregion_name: str
        :param osm_file_format: file format/extension of the OSM data available on the download server
        :type osm_file_format: str
        :param download_dir: directory for saving the downloaded file(s), defaults to ``None``;
            when ``download_dir=None``, it refers to the method
            :py:meth:`~pydriosm.downloader.BBBike.cd`
        :type download_dir: str or None
        :param kwargs: [optional] parameters of `pyhelpers.dir.cd()`_,
            including ``mkdir``(default: ``False``)
        :return: valid subregion name, filename, download url and absolute file path
        :rtype: typing.Tuple[str, str, str, str]

        .. _`pyhelpers.dir.cd()`:
            https://pyhelpers.readthedocs.io/en/latest/_generated/pyhelpers.dir.cd.html

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
            >>> dwnld_url
            'https://download.geofabrik.de/europe/great-britain/england/greater-london-latest.osm...
            >>> os.path.relpath(path_to_pbf)
            'osm_geofabrik\\Greater London\\greater-london-latest.osm.pbf'

            >>> # Specify a new directory for downloaded data
            >>> dwnld_dir = "osm_downloads"

            >>> info2 = gfd.get_valid_download_info(subrgn_name, file_format, dwnld_dir)
            >>> _, _, _, path_to_pbf = info2

            >>> os.path.relpath(path_to_pbf)
            'osm_downloads\\greater-london-latest.osm.pbf'
        """

        subregion_name_, osm_filename, download_url, path_to_file = _get_valid_download_info(
            self, subregion_name=subregion_name, osm_file_format=osm_file_format,
            download_dir=download_dir, **kwargs)

        return subregion_name_, osm_filename, download_url, path_to_file

    def file_exists(self, subregion_name, osm_file_format, data_dir=None, update=False, verbose=False,
                    ret_file_path=False):
        """
        Check whether a data file of a geographic (sub)region already exists locally,
        given its default filename.

        :param subregion_name: name of a (sub)region available on Geofabrik free download server
        :type subregion_name: str
        :param osm_file_format: file format/extension of the OSM data available on the download server
        :type osm_file_format: str
        :param data_dir: directory for saving the downloaded file(s), defaults to ``None``;
            when ``data_dir=None``, it refers to the method
            :py:meth:`~pydriosm.downloader.GeofabrikDownloader.cdd`
        :type data_dir: str or None
        :param update: whether to (check and) update the data, defaults to ``False``
        :type update: bool
        :param verbose: whether to print relevant information in console, defaults to ``False``
        :type verbose: bool or int
        :param ret_file_path: whether to return the path to the data file (if it exists),
            defaults to ``False``
        :type ret_file_path: bool
        :return: whether the requested data file exists; or the path to the data file
        :rtype: bool or str

        **Examples**::

            >>> from pydriosm.downloader import GeofabrikDownloader
            >>> from pyhelpers.dir import delete_dir
            >>> import os

            >>> gfd = GeofabrikDownloader()

            >>> subrgn_name = 'london'
            >>> file_format = ".pbf"

            >>> # Download the PBF data of London (to the default directory)
            >>> gfd.download_osm_data(subrgn_name, file_format, verbose=True)
            To download .osm.pbf data of the following geographic (sub)region(s):
                Greater London
            ? [No]|Yes: yes
            Downloading "greater-london-latest.osm.pbf" to "osm_geofabrik\\Europe\\Gre..." ... Done.

            >>> # Check whether the PBF data file exists; `ret_file_path` is by default `False`
            >>> pbf_exists = gfd.file_exists(subrgn_name, file_format)
            >>> pbf_exists  # If the data file exists at the default directory
            True

            >>> # Set `ret_file_path=True`
            >>> path_to_pbf = gfd.file_exists(subrgn_name, file_format, ret_file_path=True)

            >>> os.path.relpath(path_to_pbf)  # If the data file exists at the default directory
            'osm_geofabrik\\Europe\\Great Britain\\England\\Greater London\\greater-london-latest...

            >>> dwnld_dir = gfd.cdd()

            >>> # Remove the directory or the PBF file and check again:
            >>> delete_dir(dwnld_dir, confirmation_required=False, verbose=True)
            Deleting "osm_geofabrik\\" ... Done.

            >>> # Since the data file does not exist at the default directory
            >>> path_to_pbf = gfd.file_exists(subrgn_name, file_format, ret_file_path=True)
            >>> path_to_pbf
            False
        """

        file_exists = _if_osm_file_exists(
            self, subregion_name=subregion_name, osm_file_format=osm_file_format, data_dir=data_dir,
            update=update, verbose=verbose, ret_file_path=ret_file_path)

        return file_exists

    def download_osm_data(self, subregion_names, osm_file_format, download_dir=None, update=False,
                          confirmation_required=True, deep_retry=False, interval=None, verbose=False,
                          ret_download_path=False, **kwargs):
        """
        Download OSM data (in a specific format) of one (or multiple) geographic (sub)region(s).

        :param subregion_names: name of a geographic (sub)region
            (or names of multiple geographic (sub)regions) available on Geofabrik free download server
        :type subregion_names: str or list
        :param osm_file_format: file format/extension of the OSM data available on the download server
        :type osm_file_format: str
        :param download_dir: directory for saving the downloaded file(s), defaults to ``None``;
            when ``download_dir=None``, it refers to the method
            :py:meth:`~pydriosm.downloader.GeofabrikDownloader.cdd`
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
            https://pyhelpers.readthedocs.io/en/latest/_generated/
            pyhelpers.ops.download_file_from_url.html

        **Examples**::

            >>> from pydriosm.downloader import GeofabrikDownloader
            >>> from pyhelpers.dir import delete_dir
            >>> import os

            >>> gfd = GeofabrikDownloader()

            >>> # Download PBF data file of Greater London and Rutland
            >>> subrgn_names = ['London', 'Rutland']  # Case-insensitive
            >>> file_format = ".pbf"

            >>> dwnld_file_pathnames = gfd.download_osm_data(
            ...     subregion_names=subrgn_names, osm_file_format=file_format, verbose=True,
            ...     ret_download_path=True)
            To download .osm.pbf data of the following geographic (sub)region(s):
                Greater London
                Rutland
            ? [No]|Yes: yes
            Downloading "greater-london-latest.osm.pbf" to "osm_geofabrik\\Europe\\Great Britain...
            Downloading "rutland-latest.osm.pbf" to "osm_geofabrik\\Europe\\Great Britain\\Engla...

            >>> for dwnld_file_pathname in dwnld_file_pathnames:
            ...     print(os.path.relpath(dwnld_file_pathname))
            osm_geofabrik\\Europe\\Great Britain\\England\\Greater London\\greater-london-latest....
            osm_geofabrik\\Europe\\Great Britain\\England\\Rutland\\rutland-latest.osm.pbf
            >>> len(gfd.download_dir)
            2
            >>> # Since `download_dir` was not specified, the data is now in the default directory
            >>> default_download_dir = gfd.cdd()
            >>> os.path.relpath(default_download_dir)
            'osm_geofabrik'

            >>> # Delete the directory generated above
            >>> delete_dir(default_download_dir, verbose=True)
            To delete the directory "osm_geofabrik\\" (Not empty)
            ? [No]|Yes: yes
            Deleting "osm_geofabrik\\" ... Done.

            >>> # Download shapefiles of West Midlands (to a given directory "osm_downloads")
            >>> region_name = 'west midlands'  # Case-insensitive
            >>> file_format = ".shp"
            >>> dwnld_dir = "osm_downloads"

            >>> dwnld_file_pathname = gfd.download_osm_data(
            ...     subregion_names=region_name, osm_file_format=file_format,
            ...     download_dir=dwnld_dir, verbose=2, ret_download_path=True)
            To download .shp.zip data of the following geographic (sub)region(s):
                West Midlands
            ? [No]|Yes: yes
            Downloading "west-midlands-latest-free.shp.zip" to "osm_downloads\\"
            "osm_downloads\\west-midlands-latest-free.shp.zip": 83.6MB [00:10, 8.02MB/s]
            Done.
            >>> os.path.relpath(dwnld_file_pathname)
            'osm_downloads\\west-midlands-latest-free.shp.zip'

            >>> # Delete the downloaded .shp.zip file
            >>> os.remove(dwnld_file_pathname)

            >>> # Download shapefiles of Great Britain
            >>> region_name = 'Great Britain'  # Case-insensitive
            >>> file_format = ".shp"

            >>> # By default, `deep_retry=False`
            >>> dwnld_path = gfd.download_osm_data(
            ...     subregion_names=region_name, osm_file_format=file_format,
            ...     download_dir=dwnld_dir, verbose=True, ret_download_path=True)
            To download .shp.zip data of the following geographic (sub)region(s):
                Great Britain
            ? [No]|Yes: yes
            No .shp.zip data is found for "Great Britain".
            Try to download the data of its subregions instead
            ? [No]|Yes: yes
            Downloading "england-latest-free.shp.zip" to "osm_downloads\\great-britain-... ... Done.
            Downloading "scotland-latest-free.shp.zip" to "osm_downloads\\great-britain... ... Done.
            Downloading "wales-latest-free.shp.zip" to "osm_downloads\\great-britain-sh... ... Done.

            >>> # Now set `deep_retry=True`
            >>> dwnld_file_pathnames = gfd.download_osm_data(
            ...     subregion_names=region_name, osm_file_format=file_format,
            ...     download_dir=dwnld_dir, verbose=True, ret_download_path=True,
            ...     deep_retry=True)
            To download .shp.zip data of the following geographic (sub)region(s):
                Great Britain
            ? [No]|Yes: yes
            No .shp.zip data is found for "Great Britain".
            Try to download the data of its subregions instead
            ? [No]|Yes: yes
            "wales-latest-free.shp.zip" is already available at "osm_downloads\\great-britain-shp...
            "scotland-latest-free.shp.zip" is already available at "osm_downloads\\great-britain-...
            Downloading "bedfordshire-latest-free.shp.zip" to "osm_downloads\\great-bri... ... Done.
            ... ...
            Downloading "west-yorkshire-latest-free.shp.zip" to "osm_downloads\\great-b... ... Done.
            Downloading "wiltshire-latest-free.shp.zip" to "osm_downloads\\great-britai... ... Done.
            Downloading "worcestershire-latest-free.shp.zip" to "osm_downloads\\great-b... ... Done.

            >>> # Check the file paths
            >>> len(dwnld_file_pathnames)
            49
            >>> # Check the current default `download_dir`
            >>> os.path.relpath(gfd.download_dir)
            'osm_downloads\\great-britain-shp-zip'
            >>> os.path.commonpath(dwnld_file_pathnames) == gfd.download_dir
            True

            >>> # Delete all the downloaded files
            >>> delete_dir(dwnld_dir, verbose=True)
            To delete the directory "osm_downloads\\" (Not empty)
            ? [No]|Yes: yes
            Deleting "osm_downloads\\" ... Done.
        """

        info = _file_exists(
            self, subregion_names=subregion_names, osm_file_format=osm_file_format,
            download_dir=download_dir, update=update, confirmation_required=confirmation_required,
            verbose=verbose)

        (subregion_names_, osm_file_format_, confirmation_required_, update_msg, downloads_list,
         existing_file_paths) = info

        confirmation_required_ = confirmation_required_ and confirmation_required

        if confirmed("To {} {} data of the following geographic (sub)region(s):"
                     "\n\t{}\n?".format(update_msg, osm_file_format_, "\n\t".join(downloads_list)),
                     confirmation_required=confirmation_required_):

            download_paths = []

            for subrgn_name_ in subregion_names_:

                # Get download URL
                subregion_name_, download_url = self.get_subregion_download_url(
                    subregion_name=subrgn_name_, osm_file_format=osm_file_format_)

                if download_url is None:

                    if verbose:
                        print(f"No {osm_file_format_} data is found for \"{subregion_name_}\".")

                    cfm_msg = "Try to download the data of its subregions instead\n?"
                    if confirmed(prompt=cfm_msg, confirmation_required=confirmation_required):
                        sub_subregions = self.get_subregions(subregion_name_, deep=deep_retry)

                        if sub_subregions == [subregion_name_]:
                            print(f"{osm_file_format_} data is unavailable for {subregion_name_}.")
                            # break

                        else:
                            if download_dir is None:
                                _, path_to_file_ = self.get_default_path_to_osm_file(
                                    subregion_name=subregion_name_, osm_file_format=".osm.pbf")
                                download_dir = os.path.dirname(path_to_file_)

                            download_dir_ = self.specify_sub_download_dir(
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
                        download_dir_ = cd(validate_dir(path_to_dir=download_dir), mkdir=True)
                        osm_filename = self.get_default_osm_filename(
                            subregion_name=subregion_name_, osm_file_format=osm_file_format_)
                        path_to_file = os.path.join(download_dir_, osm_filename)

                    if not os.path.isfile(path_to_file) or update:
                        self._download_osm_data(
                            download_url=download_url, path_to_file=path_to_file, verbose=verbose,
                            **kwargs)

                    if os.path.isfile(path_to_file):
                        download_paths.append(path_to_file)

                if isinstance(interval, int):
                    time.sleep(secs=interval)

        else:
            download_paths = existing_file_paths

        download_paths_ = self._download_paths(download_dir=download_dir, download_paths=download_paths)

        if ret_download_path:
            return download_paths_

    def download_subregion_data(self, subregion_names, osm_file_format, download_dir=None, deep=False,
                                ret_download_path=False, **kwargs):
        """
        Download OSM data (in a specific file format) of all subregions (if available) for
        one (or multiple) geographic (sub)region(s).

        If no subregion data is available for the region(s) specified by ``subregion_names``,
        then the data of ``subregion_names`` would be downloaded only.

        :param subregion_names: name of a geographic (sub)region
            (or names of multiple geographic (sub)regions) available on Geofabrik free download server
        :type subregion_names: str or list
        :param osm_file_format: file format/extension of the OSM data available on the download server
        :type osm_file_format: str
        :param download_dir: directory for saving the downloaded file(s), defaults to ``None``;
            when ``download_dir=None``, it refers to the method
            :py:meth:`~pydriosm.downloader.GeofabrikDownloader.cdd`
        :type download_dir: str or None
        :param deep: whether to try to search for subregions of subregion(s), defaults to ``False``
        :type deep: bool
        :param ret_download_path: whether to return the path(s) to the downloaded file(s),
            defaults to ``False``
        :type ret_download_path: bool
        :param kwargs: optional parameters of `pydriosm.GeofabrikDownloader.download_osm_data()`_
        :return: the path(s) to the downloaded file(s) when ``ret_download_path=True``
        :rtype: list or str

        .. _`pydriosm.GeofabrikDownloader.download_osm_data()`:
            https://pydriosm.readthedocs.io/en/latest/
            _generated/pydriosm.downloader.GeofabrikDownloader.download_osm_data.html

        **Examples**::

            >>> from pydriosm.downloader import GeofabrikDownloader
            >>> from pyhelpers.dir import cd, delete_dir
            >>> import os

            >>> gfd = GeofabrikDownloader()

            >>> subrgn_names = ['rutland', 'west yorkshire']
            >>> file_format = ".pbf"
            >>> dwnld_dir = "osm_downloads"

            >>> gfd.download_subregion_data(subrgn_names, file_format, dwnld_dir, verbose=True)
            To download .osm.pbf data of the following geographic (sub)region(s):
                Rutland
                West Yorkshire
            ? [No]|Yes: yes
            Downloading "rutland-latest.osm.pbf" to "osm_downloads\\" ... Done.
            Downloading "west-yorkshire-latest.osm.pbf" to "osm_downloads\\" ... Done.

            >>> # Delete "osm_downloads\\rutland-latest.osm.pbf"
            >>> os.remove(cd(dwnld_dir, "rutland-latest.osm.pbf"))

            >>> # Try to download data given another list which also includes 'West Yorkshire'
            >>> subrgn_names = ['west midlands', 'west yorkshire']

            >>> dwnld_file_pathnames = gfd.download_subregion_data(
            ...     subrgn_names, file_format, dwnld_dir, verbose=True, ret_download_path=True)
            "west-yorkshire-latest.osm.pbf" is already available at "osm_downloads\\".
            To download .osm.pbf data of the following geographic (sub)region(s):
                Rutland
            ? [No]|Yes: yes
            Downloading "rutland-latest.osm.pbf" to "osm_downloads\\" ... Done.

            >>> for file_pathname in dwnld_file_pathnames:
            ...     print(os.path.relpath(file_pathname))
            osm_downloads\\rutland-latest.osm.pbf
            osm_downloads\\west-yorkshire-latest.osm.pbf

            >>> # Update (or re-download) the existing data file by setting `update=True`
            >>> dwnld_file_pathnames = gfd.download_subregion_data(
            ...     subrgn_names, file_format, download_dir=dwnld_dir, update=True, verbose=True,
            ...     ret_download_path=True)
            "west-yorkshire-latest.osm.pbf" is already available at "osm_downloads\\".
            To download/update the .osm.pbf data of the following geographic (sub)region(s):
                West Midlands
                West Yorkshire
            ? [No]|Yes: yes
            Downloading "west-midlands-latest.osm.pbf" to "osm_downloads\\" ... Done.
            Updating "west-yorkshire-latest.osm.pbf" at "osm_downloads\\" ... Done.

            >>> # To download the PBF data of England
            >>> subrgn_name = 'England'

            >>> dwnld_file_pathnames = gfd.download_subregion_data(
            ...     subrgn_name, file_format, download_dir=dwnld_dir, update=True, verbose=True,
            ...     ret_download_path=True)
            "west-midlands-latest.osm.pbf" is already available at "osm_downloads\\".
            "west-yorkshire-latest.osm.pbf" is already available at "osm_downloads\\".
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
            Downloading "bedfordshire-latest.osm.pbf" to "osm_downloads\\" ... Done.
            Downloading "berkshire-latest.osm.pbf" to "osm_downloads\\" ... Done.
            ...
            Updating "west-midlands-latest.osm.pbf" at "osm_downloads\\" ... Done.
            ...
            Updating "west-yorkshire-latest.osm.pbf" at "osm_downloads\\" ... Done.
            Downloading "wiltshire-latest.osm.pbf" to "osm_downloads\\" ... Done.
            Downloading "worcestershire-latest.osm.pbf" to "osm_downloads\\" ... Done.

            >>> len(dwnld_file_pathnames)
            47

            >>> # Delete the downloaded files
            >>> delete_dir(os.path.commonpath(dwnld_file_pathnames), verbose=True)
            To delete the directory "osm_downloads\\" (Not empty)
            ? [No]|Yes: yes
            Deleting "osm_downloads\\" ... Done.
        """

        sr_names_ = [subregion_names] if isinstance(subregion_names, str) else subregion_names.copy()
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


class BBBikeDownloader(_Downloader):
    """
    Download OSM data from `BBBike`_ free download server.

    .. _`BBBike`: https://download.bbbike.org/
    """

    #: Name of the free downloader server
    NAME = 'BBBike'
    #: Full name of the data resource
    LONG_NAME = 'BBBike exports of OpenStreetMap data'
    #: URL of the homepage to the free download server
    URL = 'https://download.bbbike.org/osm/bbbike/'
    #: URL of a list of cities that are available on the free download server
    CITIES_URL = 'https://raw.githubusercontent.com/wosch/bbbike-world/world/etc/cities.txt'
    #: URL of coordinates of all the available cities
    CITIES_COORDS_URL = 'https://raw.githubusercontent.com/wosch/bbbike-world/world/etc/cities.csv'
    #: Filename extensions of the data files that are available from the free download server
    FILE_FORMATS = [
        '.pbf',
        '.gz',
        '.shp.zip',
        '.garmin-onroad-latin1.zip',
        '.garmin-onroad.zip',
        '.garmin-opentopo.zip',
        '.garmin-osm.zip',
        '.geojson.xz',
        '.svg-osm.zip',
        '.mapsforge-osm.zip',
        '.csv.xz',
    ]
    #: Default download directory
    DEFAULT_DOWNLOAD_DIR = "osm_bbbike"

    def __init__(self, download_dir=None):
        """
        :param download_dir: (a path or a name of) a directory for saving downloaded data files;
            if ``download_dir=None`` (default), the downloaded data files are saved into a folder
            named ``'osm_bbbike'`` under the current working directory
        :type download_dir: str or None

        :ivar list valid_file_formats: file formats (or filename extensions) of the data files
            available from BBBike download server
        :ivar str or list or None download_dir: (in accordance with the parameter ``download_dir``)

        **Examples**::

            >>> from pydriosm.downloader import BBBikeDownloader

            >>> bbd = BBBikeDownloader()

            >>> bbd.NAME
            'BBBike'

            >>> bbd.LONG_NAME
            'BBBike exports of OpenStreetMap data'

            >>> bbd.URL
            'https://download.bbbike.org/osm/bbbike/'
        """

        super().__init__(download_dir=download_dir)

    def _list_of_cities(self, path_to_pickle, verbose):
        cities_names_ = pd.read_csv(self.CITIES_URL, header=None)
        cities_names = list(cities_names_.values.flatten())

        if verbose:
            print("Done.")

        save_pickle(cities_names, path_to_pickle=path_to_pickle, verbose=verbose)

        return cities_names

    def get_list_of_cities(self, update=False, confirmation_required=True, verbose=False):
        """
        Get a list of names of cities.

        This can be an alternative to the method
        :py:meth:`~pydriosm.downloader.BBBikeDownloader.get_list_of_subregion_names`.

        :param update: whether to (check on and) update the package data, defaults to ``False``
        :type update: bool
        :param confirmation_required: whether asking for confirmation to proceed, defaults to ``True``
        :type confirmation_required: bool
        :param verbose: whether to print relevant information in console, defaults to ``False``
        :type verbose: bool or int
        :return: list of names of cities available on BBBike free download server
        :rtype: list or None

        **Examples**::

            >>> from pydriosm.downloader import BBBikeDownloader

            >>> bbd = BBBikeDownloader()

            >>> # A list of BBBike cities' names
            >>> bbbike_cities = bbd.get_list_of_cities()

            >>> len(bbbike_cities) >= 236
            True
            >>> bbbike_cities[:5]
            ['Heilbronn', 'Emden', 'Bremerhaven', 'Paris', 'Ostrava']
            >>> bbbike_cities[-5:]
            ['UlanBator', 'LaPaz', 'Sucre', 'Cusco', 'LaPlata']
        """

        dat_name = ' '.join([self.NAME, 'cities'])

        cities_names = self._get_auxiliary_data(
            self._list_of_cities, dat_name, update, confirmation_required, verbose)

        return cities_names

    def _coordinates_of_cities(self, path_to_pickle, verbose):
        csv_temp = urllib.request.urlopen(self.CITIES_COORDS_URL)
        csv_file = list(
            csv.reader(io.StringIO(csv_temp.read().decode('utf-8')), delimiter=':'))

        csv_data = [
            [x.strip().strip('\u200e').replace('#', '') for x in row]
            for row in csv_file[5:-1]]
        column_names = [x.replace('#', '').strip().capitalize() for x in csv_file[0]]
        cities_coords = pd.DataFrame(csv_data, columns=column_names)

        coordinates = cities_coords.Coord.str.split(' ').apply(pd.Series)
        coords_cols = ['ll_longitude', 'll_latitude', 'ur_longitude', 'ur_latitude']
        coordinates.columns = coords_cols

        cities_coords.drop(['Coord'], axis=1, inplace=True)

        cities_coords = pd.concat([cities_coords, coordinates], axis=1)

        cities_coords.dropna(subset=coords_cols, inplace=True)

        cities_coords['Real name'] = cities_coords['Real name'].str.split(r'[!,]').map(
            lambda x: None if x[0] == '' else dict(zip(x[::2], x[1::2])))

        if verbose:
            print("Done.")

        save_pickle(cities_coords, path_to_pickle, verbose=verbose)

        return cities_coords

    def get_coordinates_of_cities(self, update=False, confirmation_required=True, verbose=False):
        """
        Get location information of cities (geographic (sub)regions).

        :param update: whether to (check on and) update the package data, defaults to ``False``
        :type update: bool
        :param confirmation_required: whether asking for confirmation to proceed, defaults to ``True``
        :type confirmation_required: bool
        :param verbose: whether to print relevant information in console, defaults to ``False``
        :type verbose: bool or int
        :return: location information of BBBike cities
        :rtype: pandas.DataFrame or None

        **Examples**::

            >>> from pydriosm.downloader import BBBikeDownloader

            >>> bbd = BBBikeDownloader()

            >>> # Location information of BBBike cities
            >>> coords_of_cities = bbd.get_coordinates_of_cities()

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

            >>> coords_of_cities.columns.to_list()
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

        dat_name = ' '.join([self.NAME, 'cities coordinates'])

        cities_coords = self._get_auxiliary_data(
            self._coordinates_of_cities, dat_name, update, confirmation_required, verbose)

        return cities_coords

    def _subregion_index(self, path_to_pickle, verbose):
        source = requests.get(url=self.URL, headers=fake_requests_headers())
        soup = bs4.BeautifulSoup(markup=source.content, features='html.parser')

        thead, tbody = soup.find(name='thead'), soup.find(name='tbody')

        ths = [th.text.strip().lower().replace(' ', '_') for th in thead.find_all(name='th')]
        trs = tbody.find_all(name='tr')
        dat = parse_tr(trs=trs, ths=ths, as_dataframe=True).drop(index=0)
        dat.index = range(len(dat))

        for col in ['size', 'type']:
            if dat[col].nunique() == 1:
                del dat[col]

        subregion_catalogue = dat.copy()

        subregion_catalogue.loc[:, 'name'] = subregion_catalogue['name'].map(lambda x: x.rstrip('/'))

        subregion_catalogue.loc[:, 'last_modified'] = pd.to_datetime(subregion_catalogue.last_modified)

        subregion_catalogue.loc[:, 'url'] = [
            urllib.parse.urljoin(self.URL, x.get('href')) for x in soup.find_all('a')[1:]]

        if verbose:
            print("Done.")

        save_pickle(subregion_catalogue, path_to_pickle, verbose=verbose)

        return subregion_catalogue

    def get_subregion_index(self, update=False, confirmation_required=True, verbose=False):
        """
        Get a catalogue for geographic (sub)regions.

        :param update: whether to (check on and) update the package data, defaults to ``False``
        :type update: bool
        :param confirmation_required: whether asking for confirmation to proceed, defaults to ``True``
        :type confirmation_required: bool
        :param verbose: whether to print relevant information in console, defaults to ``False``
        :type verbose: bool or int
        :return: catalogue for subregions of BBBike data
        :rtype: pandas.DataFrame or None

        **Examples**::

            >>> from pydriosm.downloader import BBBikeDownloader

            >>> bbd = BBBikeDownloader()

            >>> # A BBBike catalogue of geographic (sub)regions
            >>> subregion_catalog = bbd.get_subregion_index()

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

        dat_name = ' '.join([self.NAME, 'subregion catalogue'])

        subregion_catalogue = self._get_auxiliary_data(
            self._subregion_index, dat_name, update, confirmation_required, verbose)

        return subregion_catalogue

    def _list_of_subregion_names(self, path_to_pickle, verbose):

        subregion_catalogue = self.get_subregion_index(confirmation_required=False, verbose=False)

        subregion_names = subregion_catalogue['name'].to_list()

        if verbose:
            print("Done.")

        save_pickle(subregion_names, path_to_pickle=path_to_pickle, verbose=verbose)

        return subregion_names

    def get_list_of_subregion_names(self, update=False, confirmation_required=True, verbose=False):
        """
        Get a list of names of all geographic (sub)regions.

        This can be an alternative to the method
        :py:meth:`~pydriosm.downloader.BBBikeDownloader.get_list_of_cities`.

        :param update: whether to (check on and) update the package data, defaults to ``False``
        :type update: bool
        :param confirmation_required: whether asking for confirmation to proceed, defaults to ``True``
        :type confirmation_required: bool
        :param verbose: whether to print relevant information in console, defaults to ``False``
        :type verbose: bool or int
        :return: a list of geographic (sub)region names available on BBBike free download server
        :rtype: list

        **Examples**::

            >>> from pydriosm.downloader import BBBikeDownloader

            >>> bbd = BBBikeDownloader()

            >>> # A list of names of all BBBike geographic (sub)regions
            >>> subrgn_names = bbd.get_list_of_subregion_names()

            >>> len(subrgn_names) >= 236
            True
            >>> subrgn_names[:5]
            ['Aachen', 'Aarhus', 'Adelaide', 'Albuquerque', 'Alexandria']
            >>> subrgn_names[-5:]
            ['Wroclaw', 'Wuerzburg', 'Wuppertal', 'Zagreb', 'Zuerich']
        """

        dat_name = ' '.join([self.NAME, 'subregion name list'])

        if update:
            _ = self.get_subregion_index(update=update, confirmation_required=False, verbose=False)

        subregion_names = self._get_auxiliary_data(
            self._list_of_subregion_names, dat_name, update, confirmation_required, verbose)

        return subregion_names

    def validate_subregion_name(self, subregion_name):
        """
        Validate an input name of a geographic (sub)region.

        The validation is done by matching the input ``subregion_name`` to
        a name of a geographic (sub)region available on BBBike free download server.

        :param subregion_name: name of a (sub)region available on BBBike free download server
        :type subregion_name: str
        :return: valid (sub)region name that matches, or is the most similar to, the input
        :rtype: str

        **Examples**::

            >>> from pydriosm.downloader import BBBikeDownloader

            >>> bbd = BBBikeDownloader()

            >>> valid_name = bbd.validate_subregion_name(subregion_name='leeds')
            >>> valid_name
            'Leeds'
        """

        bbbike_subregion_names = self.get_list_of_subregion_names()

        if subregion_name in bbbike_subregion_names:
            subregion_name_ = subregion_name

        elif os.path.isdir(os.path.dirname(subregion_name)) or \
                urllib.parse.urlparse(subregion_name).path:
            subregion_name_ = find_similar_str(
                os.path.basename(subregion_name), lookup_list=bbbike_subregion_names)

        else:
            subregion_name_ = find_similar_str(x=subregion_name, lookup_list=bbbike_subregion_names)

        if subregion_name_ is None:
            raise InvalidSubregionName(
                "`subregion_name` is unidentifiable. "
                "Check if the geographic (sub)region exists in the catalogue and retry.")

        return subregion_name_

    @staticmethod
    def _parse_download_link_class(x, url):
        x_href = x.get('href')  # URL
        filename = os.path.basename(x_href)
        download_url = urllib.parse.urljoin(url, x_href)

        if not x.has_attr('title'):
            file_format, file_size, last_update = 'Poly', None, None

        else:
            if len(x.contents) < 3:
                file_format, file_size = 'Txt', None
            else:
                file_format, file_size, _ = x.contents  # File type and size
                file_format, file_size = file_format.strip(), file_size.text
            last_update = pd.to_datetime(x.get('title'))  # Date and time

        parsed_dat = [filename, download_url, file_format, file_size, last_update]

        return parsed_dat

    def get_subregion_catalogue(self, subregion_name, confirmation_required=True, verbose=False):
        """
        Get a download catalogue of OSM data available for a given geographic (sub)region.

        :param subregion_name: name of a (sub)region available on BBBike free download server
        :type subregion_name: str
        :param confirmation_required: whether asking for confirmation to proceed, defaults to ``True``
        :type confirmation_required: bool
        :param verbose: whether to print relevant information in console, defaults to ``False``
        :type verbose: bool or int
        :return: a catalogues for subregion downloads
        :rtype: pandas.DataFrame or None

        **Examples**::

            >>> from pydriosm.downloader import BBBikeDownloader

            >>> bbd = BBBikeDownloader()

            >>> subrgn_name = 'leeds'

            >>> # A download catalogue for Leeds
            >>> leeds_dwnld_cat = bbd.get_subregion_catalogue(subrgn_name, verbose=True)
            To compile data of a download catalogue for "Leeds"
            ? [No]|Yes: yes
            Compiling the data ... Done.
            >>> leeds_dwnld_cat.head()
                                         Filename  ...          LastUpdate
            0                       Leeds.osm.pbf  ... 2022-05-14 19:01:38
            1                        Leeds.osm.gz  ... 2022-05-15 01:05:33
            2                   Leeds.osm.shp.zip  ... 2022-05-15 01:22:54
            3  Leeds.osm.garmin-onroad-latin1.zip  ... 2022-05-15 02:45:10
            4            Leeds.osm.garmin-osm.zip  ... 2022-05-15 02:46:22

            [5 rows x 5 columns]

            >>> leeds_dwnld_cat.columns.tolist()
            ['Filename', 'URL', 'DataType', 'Size', 'LastUpdate']
        """

        subregion_name_ = self.validate_subregion_name(subregion_name)

        dat_name = f"a download catalogue for \"{subregion_name_}\""

        if confirmed(f"To compile data of {dat_name}\n?", confirmation_required=confirmation_required):
            if verbose:
                if confirmation_required:
                    status_msg = "Compiling the data"
                else:
                    if verbose == 2:
                        status_msg = "\t{}".format(subregion_name_)
                    else:
                        status_msg = "Compiling the data of {}".format(dat_name)
                print(status_msg, end=" ... ")

            try:
                url = urllib.parse.urljoin(self.URL, subregion_name_ + '/')

                source = requests.get(url=url, headers=fake_requests_headers())

                soup = bs4.BeautifulSoup(markup=source.content, features='html.parser')
                download_link_class = soup.find_all('a', attrs={'class': ['download_link', 'small']})

                download_catalogue = pd.DataFrame(
                    self._parse_download_link_class(x=x, url=url) for x in download_link_class)
                download_catalogue.columns = ['Filename', 'URL', 'DataType', 'Size', 'LastUpdate']

                # file_path = cd_dat_bbbike(
                #     subregion_name_, subregion_name_ + "-download-catalogue.pickle")
                # save_pickle(download_catalogue, file_path, verbose=verbose)
                if verbose:
                    print("Done.")

            except Exception as e:
                if verbose:
                    print("Failed. {}".format(e))
                download_catalogue = None

            return download_catalogue

    def _catalogue(self, path_to_pickle, verbose):
        subregion_names = self.get_list_of_subregion_names()

        download_catalogue = []
        for subregion_name in subregion_names:

            subregion_dwnld_cat = self.get_subregion_catalogue(
                subregion_name=subregion_name, confirmation_required=False,
                verbose=2 if verbose == 2 else False)

            if subregion_dwnld_cat is None:
                raise Exception
            else:
                download_catalogue.append(subregion_dwnld_cat)

        subrgn_name = subregion_names[0]
        subrgn_download_catalogue = download_catalogue[0]

        # Available file formats
        file_fmt = [
            re.sub('{}|CHECKSUM'.format(subrgn_name), '', f)
            for f in subrgn_download_catalogue['Filename']]

        # Available data types
        data_typ = subrgn_download_catalogue['DataType'].to_list()

        download_index = {
            'FileFormat': [x.replace(".osm", "", 1) for x in file_fmt[:-2]],
            'DataType': data_typ[:-2],
            'Catalogue': dict(zip(subregion_names, download_catalogue))}

        if verbose is True:
            print("Done.")
        elif verbose == 2:
            print("All done.")

        save_pickle(download_index, path_to_pickle=path_to_pickle, verbose=verbose)

        return download_index

    def get_catalogue(self, update=False, confirmation_required=True, verbose=False):
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

            >>> bbd = BBBikeDownloader()

            >>> # Index for downloading OSM data available on the BBBike free download server
            >>> bbbike_catalogue = bbd.get_catalogue()

            >>> list(bbbike_catalogue.keys())
            ['FileFormat', 'DataType', 'Catalogue']

            >>> catalogue = bbbike_catalogue['Catalogue']
            >>> type(catalogue)
            dict
            >>> len(catalogue.keys()) >= 236
            True
            >>> list(catalogue.keys())[:5]
            ['Aachen', 'Aarhus', 'Adelaide', 'Albuquerque', 'Alexandria']

            >>> leeds_catalogue = catalogue['Leeds']
            >>> type(leeds_catalogue)
            pandas.core.frame.DataFrame
            >>> leeds_catalogue.head()
                                         Filename  ...          LastUpdate
            0                       Leeds.osm.pbf  ... 2022-05-14 19:01:38
            1                        Leeds.osm.gz  ... 2022-05-15 01:05:33
            2                   Leeds.osm.shp.zip  ... 2022-05-15 01:22:54
            3  Leeds.osm.garmin-onroad-latin1.zip  ... 2022-05-15 02:45:10
            4            Leeds.osm.garmin-osm.zip  ... 2022-05-15 02:46:22

            [5 rows x 5 columns]
        """

        dat_name = ' '.join([self.NAME, 'downloads catalogue'])

        download_index = self._get_auxiliary_data(
            self._catalogue, dat_name, update, confirmation_required, verbose,
            status_msg_note="", status_msg_end=": \n" if verbose == 2 else " ... ")

        return download_index

    def get_valid_file_formats(self):
        """
        Get a list of valid OSM data file formats.

        :return: a list of valid BBBike OSM file formats on BBBike free download server
        :rtype: list

        **Examples**::

            >>> from pydriosm.downloader import BBBikeDownloader

            >>> bbd = BBBikeDownloader()

            >>> bbd.get_valid_file_formats()
            ['.pbf',
             '.gz',
             '.shp.zip',
             '.garmin-onroad-latin1.zip',
             '.garmin-osm.zip',
             '.garmin-ontrail-latin1.zip',
             '.geojson.xz',
             '.svg-osm.zip',
             '.mapsforge-osm.zip',
             '.garmin-opentopo-latin1.zip',
             '.mbtiles-openmaptiles.zip',
             '.csv.xz']
        """

        osm_file_formats = self.get_catalogue()['FileFormat']

        # self.__setattr__('valid_file_formats', osm_file_formats)

        return osm_file_formats

    def validate_file_format(self, osm_file_format):
        """
        Validate an input file format of OSM data.

        The validation is done by matching the input ``osm_file_format`` to a filename extension
        available on BBBike free download server.

        :param osm_file_format: file format/extension of the OSM data
            available on BBBike free download server
        :type osm_file_format: str
        :return: valid file format (file extension)
        :rtype: str

        **Examples**::

            >>> from pydriosm.downloader import BBBikeDownloader

            >>> bbd = BBBikeDownloader()

            >>> file_format = 'PBF'

            >>> valid_file_format = bbd.validate_file_format(file_format)
            >>> valid_file_format
            '.pbf'
        """

        if osm_file_format in self.valid_file_formats:
            osm_file_format_ = osm_file_format
        else:
            osm_file_format_ = find_similar_str(osm_file_format, self.valid_file_formats)

        if osm_file_format_ is None:
            raise InvalidFileFormat("`osm_file_format` should be one of: \n  \"{}\".".format(
                "\",\n  \"".join(self.valid_file_formats)))
        else:
            return osm_file_format_

    def get_subregion_download_url(self, subregion_name, osm_file_format):
        """
        Get a valid URL for downloading OSM data of a specific file format for a geographic (sub)region.

        :param subregion_name: name of a (sub)region available on BBBike free download server
        :type subregion_name: str
        :param osm_file_format: file format/extension of the OSM data available on the download server
        :type osm_file_format: str
        :return: a valid name of ``subregion_name`` and a download URL for the given ``osm_file_format``
        :rtype: tuple

        **Examples**::

            >>> from pydriosm.downloader import BBBikeDownloader

            >>> bbd = BBBikeDownloader()

            >>> subrgn_name = 'leeds'
            >>> file_format = "pbf"

            >>> # Get a valid subregion name and its download URL
            >>> subrgn_name_, dwnld_url = bbd.get_subregion_download_url(subrgn_name, file_format)
            >>> subrgn_name_
            'Leeds'
            >>> dwnld_url
            'https://download.bbbike.org/osm/bbbike/Leeds/Leeds.osm.pbf'

            >>> file_format = "csv.xz"
            >>> subrgn_name_, dwnld_url = bbd.get_subregion_download_url(subrgn_name, file_format)

            >>> subrgn_name_
            'Leeds'
            >>> dwnld_url
            'https://download.bbbike.org/osm/bbbike/Leeds/Leeds.osm.csv.xz'
        """

        subregion_name_ = self.validate_subregion_name(subregion_name)
        osm_file_format_ = ".osm" + self.validate_file_format(osm_file_format)

        bbbike_download_dictionary = self.get_catalogue()['Catalogue']
        sub_download_catalogue = bbbike_download_dictionary[subregion_name_]

        tmp = subregion_name_ + osm_file_format_
        url = sub_download_catalogue[sub_download_catalogue.Filename == tmp].URL.iloc[0]

        return subregion_name_, url

    def get_valid_download_info(self, subregion_name, osm_file_format, download_dir=None, **kwargs):
        """
        Get information of downloading (or downloaded) data file.

        The information includes a valid subregion name, a default filename, a URL and
        an absolute path where the data file is (to be) saved locally.

        :param subregion_name: name of a (sub)region available on BBBike free download server
        :type subregion_name: str
        :param osm_file_format: file format/extension of the OSM data available on the download server
        :type osm_file_format: str
        :param download_dir: directory for saving the downloaded file(s), defaults to ``None``;
            when ``download_dir=None``, it refers to the method
            :py:meth:`~pydriosm.downloader.BBBike.cd`
        :type download_dir: str or None
        :param kwargs: [optional] parameters of `pyhelpers.dir.cd()`_,
            including ``mkdir``(default: ``False``)
        :return: valid subregion name, filename, download url and absolute file path
        :rtype: tuple

        .. _`pyhelpers.dir.cd()`:
            https://pyhelpers.readthedocs.io/en/latest/_generated/pyhelpers.dir.cd.html

        **Examples**::

            >>> from pydriosm.downloader import BBBikeDownloader
            >>> import os

            >>> bbd = BBBikeDownloader()

            >>> subrgn_name = 'leeds'
            >>> file_format = "pbf"

            >>> # valid subregion name, filename, download url and absolute file path
            >>> info = bbd.get_valid_download_info(subrgn_name, file_format)
            >>> valid_subrgn_name, pbf_filename, dwnld_url, pbf_pathname = info

            >>> valid_subrgn_name
            'Leeds'
            >>> pbf_filename
            'Leeds.osm.pbf'
            >>> dwnld_url
            'https://download.bbbike.org/osm/bbbike/Leeds/Leeds.osm.pbf'
            >>> os.path.relpath(pbf_pathname)
            'osm_bbbike\\Leeds\\Leeds.osm.pbf'
        """

        subregion_name_, osm_filename, download_url, path_to_file = _get_valid_download_info(
            self, subregion_name=subregion_name, osm_file_format=osm_file_format,
            download_dir=download_dir, **kwargs)

        return subregion_name_, osm_filename, download_url, path_to_file

    def file_exists(self, subregion_name, osm_file_format, data_dir=None, update=False, verbose=False,
                    ret_file_path=False):
        """
        Check if a requested data file of a geographic (sub)region already exists locally,
        given its default filename.

        :param subregion_name: name of a (sub)region available on BBBike free download server
        :type subregion_name: str
        :param osm_file_format: file format/extension of the OSM data available on the download server
        :type osm_file_format: str
        :param data_dir: directory for saving the downloaded file(s), defaults to ``None``;
            when ``data_dir=None``, it refers to the method
            :py:meth:`~pydriosm.downloader.BBBike.cd`
        :type data_dir: str or None
        :param update: whether to (check and) update the data, defaults to ``False``
        :type update: bool
        :param verbose: whether to print relevant information in console, defaults to ``False``
        :type verbose: bool or int
        :param ret_file_path: whether to return the path to the data file (if it exists),
            defaults to ``False``
        :type ret_file_path: bool
        :return: whether the requested data file exists; or the path to the data file
        :rtype: bool or str

        **Examples**::

            >>> from pydriosm.downloader import BBBikeDownloader
            >>> from pyhelpers.dir import delete_dir
            >>> import os

            >>> bbd = BBBikeDownloader()

            >>> subrgn_name = 'leeds'
            >>> file_format = ".pbf"

            >>> # Download the PBF data of London (to the default directory)
            >>> bbd.download_osm_data(subrgn_name, file_format, verbose=True)
            To download .pbf data of the following geographic (sub)region(s):
                Leeds
            ? [No]|Yes: yes
            Downloading "Leeds.osm.pbf" to "osm_bbbike\\Leeds\\" ... Done.

            >>> # Check whether the PBF data file exists; `ret_file_path` is by default `False`
            >>> pbf_exists = bbd.file_exists(subrgn_name, file_format)
            >>> pbf_exists
            True

            >>> # Set `ret_file_path=True`
            >>> pbf_pathname = bbd.file_exists(subrgn_name, file_format, ret_file_path=True)
            >>> os.path.relpath(pbf_pathname)
            'osm_bbbike\\Leeds\\Leeds.osm.pbf'

            >>> default_dwnld_dir = bbd.cdd()
            >>> os.path.relpath(default_dwnld_dir)
            'osm_bbbike'

            >>> # Remove the directory or the PBF file and check again:
            >>> delete_dir(default_dwnld_dir, verbose=True)
            To delete the directory "osm_bbbike\\" (Not empty)
            ? [No]|Yes: yes
            Deleting "osm_bbbike\\" ... Done.
            >>> pbf_pathname = bbd.file_exists(subrgn_name, file_format, ret_file_path=True)
            >>> # Since the default download directory has been deleted
            >>> pbf_pathname
            False
        """

        file_exists = _if_osm_file_exists(
            self, subregion_name=subregion_name, osm_file_format=osm_file_format, data_dir=data_dir,
            update=update, verbose=verbose, ret_file_path=ret_file_path)

        return file_exists

    def download_subregion_data(self, subregion_name, download_dir=None, update=False,
                                confirmation_required=True, interval=None, verbose=False,
                                ret_download_path=False, **kwargs):
        """
        Download OSM data of all available formats for a geographic (sub)region.

        :param subregion_name: name of a (sub)region available on BBBike free download server
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
            https://pyhelpers.readthedocs.io/en/latest/_generated/
            pyhelpers.ops.download_file_from_url.html

        **Examples**::

            >>> from pydriosm.downloader import BBBikeDownloader
            >>> from pyhelpers.dir import delete_dir
            >>> import os

            >>> bbd = BBBikeDownloader()

            >>> # Download the BBBike OSM data of London
            >>> subrgn_name = 'london'

            >>> bbd.download_subregion_data(subrgn_name, verbose=True)
            To download all available BBBike OSM data of London
            ? [No]|Yes: yes
            Downloading:
                London.osm.pbf ... Done.
                London.osm.gz ... Done.
                London.osm.shp.zip ... Done.
                London.osm.garmin-onroad-latin1.zip ... Done.
                London.osm.garmin-osm.zip ... Done.
                London.osm.garmin-ontrail-latin1.zip ... Done.
                London.osm.geojson.xz ... Done.
                London.osm.svg-osm.zip ... Done.
                London.osm.mapsforge-osm.zip ... Done.
                London.osm.garmin-opentopo-latin1.zip ... Done.
                London.osm.mbtiles-openmaptiles.zip ... Done.
                London.osm.csv.xz ... Done.
                London.poly ... Done.
                CHECKSUM.txt ... Done.
            Check out the downloaded OSM data at "osm_bbbike\\London\\".

            >>> # Delete the download directory
            >>> delete_dir(bbd.cdd(), verbose=True)
            To delete the directory "osm_bbbike\\" (Not empty)
            ? [No]|Yes: yes
            Deleting "osm_bbbike\\" ... Done.

            >>> # Download the BBBike OSM data of Leeds
            >>> subrgn_name = 'leeds'
            >>> dwnld_dir = "osm_downloads"

            >>> dwnld_paths = bbd.download_subregion_data(
            ...     subrgn_name, dwnld_dir, confirmation_required=False, verbose=True,
            ...     ret_download_path=True)
            Downloading all available BBBike OSM data of Leeds:
                Leeds.osm.pbf ... Done.
                Leeds.osm.gz ... Done.
                Leeds.osm.shp.zip ... Done.
                Leeds.osm.garmin-onroad-latin1.zip ... Done.
                Leeds.osm.garmin-osm.zip ... Done.
                Leeds.osm.garmin-ontrail-latin1.zip ... Done.
                Leeds.osm.geojson.xz ... Done.
                Leeds.osm.svg-osm.zip ... Done.
                Leeds.osm.mapsforge-osm.zip ... Done.
                Leeds.osm.garmin-opentopo-latin1.zip ... Done.
                Leeds.osm.mbtiles-openmaptiles.zip ... Done.
                Leeds.osm.csv.xz ... Done.
                Leeds.poly ... Done.
                CHECKSUM.txt ... Done.
            Check out the downloaded OSM data at "osm_downloads\\Leeds\\".

            >>> len(dwnld_paths)
            14
            >>> os.path.relpath(os.path.commonpath(dwnld_paths))
            'osm_downloads\\Leeds'
            >>> os.path.relpath(dwnld_paths[0])
            'osm_downloads\\Leeds\\Leeds.osm.pbf'

            >>> # Delete the download directory
            >>> delete_dir(dwnld_dir, verbose=True)
            To delete the directory "osm_downloads\\" (Not empty)
            ? [No]|Yes: yes
            Deleting "osm_downloads\\" ... Done.
        """

        bbbike_catalogue = self.get_catalogue()['Catalogue']

        subregion_name_ = self.validate_subregion_name(subregion_name)
        subrgn_cat = bbbike_catalogue[subregion_name_]

        if download_dir is None:
            data_dir = self.cdd(subregion_name_, mkdir=True)
        else:
            data_dir = os.path.join(validate_dir(path_to_dir=download_dir), subregion_name_)
            if not os.path.exists(data_dir):
                os.makedirs(data_dir)

        cfm_dat = f"all available BBBike OSM data of {subregion_name_}"

        if confirmed(f"To download {cfm_dat}\n?", confirmation_required=confirmation_required):
            if verbose:
                print("Downloading: ") if confirmation_required else print(f"Downloading {cfm_dat}: ")

            download_paths = []

            for download_url, osm_filename in zip(subrgn_cat['URL'], subrgn_cat['Filename']):
                try:
                    path_to_file = os.path.join(data_dir, osm_filename)

                    if os.path.isfile(path_to_file) and not update:
                        if verbose:
                            print(f"\t\"{osm_filename}\" (Already available)")

                    else:
                        if verbose:
                            print(f"\t{osm_filename} ... ", end="\n" if verbose == 2 else "")

                        download_file_from_url(
                            url=download_url, path_to_file=path_to_file,
                            verbose=True if verbose == 2 else False, **kwargs)

                        if verbose and verbose != 2:
                            print("Done.")

                        if isinstance(interval, int):  # os.path.getsize(path_to_file)/(1024**2)<=5:
                            time.sleep(secs=interval)

                    if os.path.isfile(path_to_file):
                        download_paths.append(path_to_file)

                except Exception as e:
                    if verbose:
                        print("Failed. {}".format(e))

            if verbose and len(download_paths) > 1:
                rel_path = os.path.relpath(os.path.commonpath(download_paths))
                if verbose == 2:
                    print("All done.")

                print("Check out the downloaded OSM data at \"{}\\\".".format(rel_path))

            download_paths_ = self._download_paths(
                download_dir=download_dir, download_paths=download_paths)

            if ret_download_path:
                return download_paths_

    def download_osm_data(self, subregion_names, osm_file_format, download_dir=None, update=False,
                          confirmation_required=True, interval=None, verbose=False,
                          ret_download_path=False, **kwargs):
        """
        Download OSM data (in a specific file format) of one (or multiple) geographic (sub)region(s).

        :param subregion_names: name of a geographic (sub)region
            (or names of multiple geographic (sub)regions) available on BBBike free download server
        :type subregion_names: str or list
        :param osm_file_format: file format/extension of the OSM data available on the download server
        :type osm_file_format: str
        :param download_dir: directory for saving the downloaded file(s), defaults to ``None``;
            when ``download_dir=None``, it refers to the method
            :py:meth:`~pydriosm.downloader.BBBike.cd`
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

            >>> from pydriosm.downloader import BBBikeDownloader
            >>> from pyhelpers.dir import delete_dir
            >>> import os

            >>> bbd = BBBikeDownloader()

            >>> # Download PBF data of London
            >>> subrgn_name = 'London'
            >>> file_format = "pbf"

            >>> bbd.download_osm_data(subrgn_name, file_format, verbose=True)
            To download .pbf data of the following geographic (sub)region(s):
                London
            ? [No]|Yes: yes
            Downloading "London.osm.pbf" to "osm_bbbike\\London\\" ... Done.

            >>> # Delete the created directory "London"
            >>> delete_dir(bbd.download_dir, verbose=True)
            To delete the directory "osm_bbbike\\London\\" (Not empty)
            ? [No]|Yes: yes
            Deleting "osm_bbbike\\London\\" ... Done.

            >>> # Download PBF data of Leeds and Birmingham to a custom directory "osm_downloads\\"
            >>> subrgn_names = ['leeds', 'birmingham']
            >>> dwnld_dir = "osm_downloads"

            >>> dwnld_paths = bbd.download_osm_data(
            ...     subrgn_names, file_format, dwnld_dir, verbose=True, ret_download_path=True)
            To download .pbf data of the following geographic (sub)region(s):
                Leeds
                Birmingham
            ? [No]|Yes: yes
            Downloading "Leeds.osm.pbf" to "osm_downloads\" ... Done.
            Downloading "Birmingham.osm.pbf" to "osm_downloads\" ... Done.
            >>> len(dwnld_paths)
            2
            >>> os.path.relpath(os.path.commonpath(dwnld_paths))
            'osm_downloads'
            >>> os.path.relpath(dwnld_paths[0])
            'osm_downloads\\Leeds.osm.pbf'

            >>> # Delete the above download directories
            >>> delete_dir([bbd.cdd(), dwnld_dir], verbose=True)
            To delete the following directories:
                "osm_bbbike\\"
                "osm_downloads\\" (Not empty)
            ? [No]|Yes: yes
            Deleting "osm_bbbike\\" ... Done.
            Deleting "osm_downloads\\" ... Done.
        """

        info = _file_exists(
            self, subregion_names=subregion_names, osm_file_format=osm_file_format,
            download_dir=download_dir, update=update, confirmation_required=confirmation_required,
            verbose=verbose)

        (subregion_names_, osm_file_format_, confirmation_required_, update_msg, downloads_list,
         existing_file_paths) = info

        confirmation_required_ = confirmation_required_ and confirmation_required

        if confirmed("To {} {} data of the following geographic (sub)region(s):"
                     "\n\t{}\n?".format(update_msg, osm_file_format_, "\n\t".join(downloads_list)),
                     confirmation_required=confirmation_required_):

            download_paths = []

            for sub_reg_name in subregion_names_:

                # Get essential information for the download
                _, _, download_url, path_to_file = self.get_valid_download_info(
                    subregion_name=sub_reg_name, osm_file_format=osm_file_format_,
                    download_dir=download_dir, mkdir=True)

                if not os.path.isfile(path_to_file) or update:
                    self._download_osm_data(
                        download_url=download_url, path_to_file=path_to_file, verbose=verbose,
                        **kwargs)

                if os.path.isfile(path_to_file):
                    download_paths.append(path_to_file)

                if isinstance(interval, int):  # or os.path.getsize(path_to_file) / (1024 ** 2) <= 5:
                    time.sleep(secs=interval)

        else:
            download_paths = existing_file_paths

        download_paths_ = self._download_paths(download_dir=download_dir, download_paths=download_paths)

        if ret_download_path:
            return download_paths_


# == Update package data ===========================================================================


def _update_package_data(confirmation_required=True, interval_sec=5, verbose=True):
    """
    Update package data used by the downloader classes.

    :param confirmation_required: whether asking for confirmation to proceed, defaults to ``True``
    :type confirmation_required: bool
    :param interval_sec: time gap (in seconds) between the updating of different classes,
        defaults to ``5``
    :type interval_sec: int
    :param verbose: whether to print relevant information in console, defaults to ``True``
    :type verbose: bool or int

    **Examples**::

        >>> from pydriosm.downloader import _update_package_data

        >>> _update_package_data(confirmation_required=True, verbose=True)
        To update resources (which may take a few minutes)
        ? [No]|Yes: no
    """

    if confirmed("To update resources (which may take a few minutes)\n?"):

        update = True

        # -- Geofabrik -----------------------------------------------------------------------------
        gfd = GeofabrikDownloader()

        _ = gfd.get_download_index(
            update=update, confirmation_required=confirmation_required, verbose=verbose)

        time.sleep(interval_sec)

        _ = gfd.get_continents_subregion_tables(
            update=update, confirmation_required=confirmation_required, verbose=verbose)

        time.sleep(interval_sec)

        _ = gfd.get_region_subregion_tier(
            update=update, confirmation_required=confirmation_required, verbose=verbose)

        time.sleep(interval_sec)

        _ = gfd.get_catalogue(
            update=update, confirmation_required=confirmation_required, verbose=verbose)

        time.sleep(interval_sec)

        _ = gfd.get_list_of_subregion_names(
            update=update, confirmation_required=confirmation_required, verbose=verbose)

        time.sleep(interval_sec)

        # -- BBBike --------------------------------------------------------------------------------
        bbd = BBBikeDownloader()

        _ = bbd.get_list_of_cities(
            update=update, confirmation_required=confirmation_required, verbose=verbose)

        time.sleep(interval_sec)

        _ = bbd.get_coordinates_of_cities(
            update=update, confirmation_required=confirmation_required, verbose=verbose)

        time.sleep(interval_sec)

        _ = bbd.get_subregion_index(
            update=update, confirmation_required=confirmation_required, verbose=verbose)

        time.sleep(interval_sec)

        _ = bbd.get_list_of_subregion_names(
            update=update, confirmation_required=confirmation_required, verbose=verbose)

        time.sleep(interval_sec)

        _ = bbd.get_catalogue(
            update=update, confirmation_required=confirmation_required, verbose=verbose)

        if verbose:
            print("\nUpdate finished.")
