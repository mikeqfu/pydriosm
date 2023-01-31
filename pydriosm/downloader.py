"""Download `OpenStreetMap <https://www.openstreetmap.org/>`_ (OSM) data from free download servers:
`Geofabrik <https://download.geofabrik.de/>`_ and `BBBike <https://download.bbbike.org/>`_.
"""

import collections
import copy
import csv
import importlib
import json
import os
import re
import string
import time
import urllib.parse
import warnings

import pandas as pd
import requests
import shapely.geometry
from pyhelpers.dirs import cd, validate_dir
from pyhelpers.ops import confirmed, download_file_from_url, fake_requests_headers, is_url, \
    parse_size, update_dict
from pyhelpers.store import load_pickle, save_pickle
from pyhelpers.text import cosine_similarity_between_texts, find_similar_str
from pyrcs.parser import parse_tr

from pydriosm.errors import InvalidFileFormatError, InvalidSubregionNameError
from pydriosm.utils import _cdd, first_unique


# == Downloading data ==============================================================================

class _Downloader:
    """
    Initialization of a data downloader.
    """

    #: str: Name of the free download server.
    NAME = 'OSM Downloader'
    #: str: Full name of the data resource.
    LONG_NAME = 'OpenStreetMap data downloader'
    #: str: Default download directory.
    DEFAULT_DOWNLOAD_DIR = cd("osm_data")
    #: set: Valid subregion names.
    VALID_SUBREGION_NAMES = {}
    #: set: Valid file formats.
    FILE_FORMATS = {
        '.csv.xz',
        '.garmin-onroad-latin1.zip',
        '.garmin-onroad.zip',
        '.garmin-opentopo.zip',
        '.garmin-osm.zip',
        '.geojson.xz',
        '.gz',
        '.mapsforge-osm.zip',
        '.osm.bz2',
        '.osm.pbf',
        '.pbf',
        '.shp.zip',
        '.svg-osm.zip',
    }

    def __init__(self, download_dir=None):
        """
        :param download_dir: name or pathname of a directory for saving downloaded data files,
            defaults to ``None``; when ``download_dir=None``, downloaded data files are saved to a
            folder named 'osm_data' under the current working directory
        :type download_dir: str or os.PathLike[str] or None

        :ivar str or None download_dir: name or pathname of a directory for saving downloaded data files
        :ivar list data_paths: pathnames of all downloaded data files

        **Tests**::

            >>> from pydriosm.downloader import _Downloader
            >>> import os

            >>> d = _Downloader()

            >>> d.NAME
            'OSM Downloader'

            >>> os.path.relpath(d.download_dir)
            'osm_data'

            >>> os.path.relpath(d.cdd())
            'osm_data'

            >>> d.download_dir == d.cdd()
            True

            >>> d = _Downloader(download_dir="tests\\osm_data")
            >>> os.path.relpath(d.download_dir)
            'tests\\osm_data'
        """

        self.download_dir = self.cdd() if download_dir is None else validate_dir(download_dir)
        self.data_paths = []

    @classmethod
    def cdd(cls, *sub_dir, mkdir=False, **kwargs):
        """
        Change directory to default download directory and its subdirectories or a specific file.

        :param sub_dir: name of directory; names of directories (and/or a filename)
        :type sub_dir: str or os.PathLike[str]
        :param mkdir: whether to create a directory, defaults to ``False``
        :type mkdir: bool
        :param kwargs: [optional] parameters of `pyhelpers.dirs.cd()`_
        :return: an absolute pathname to a directory (or a file)
        :rtype: str or os.PathLike[str]

        .. _`pyhelpers.dirs.cd()`:
            https://pyhelpers.readthedocs.io/en/latest/_generated/pyhelpers.dirs.cd.html

        **Tests**::

            >>> from pydriosm.downloader import _Downloader
            >>> import os

            >>> os.path.relpath(_Downloader.cdd())
            'osm_data'
        """

        pathname = cd(cls.DEFAULT_DOWNLOAD_DIR, *sub_dir, mkdir=mkdir, **kwargs)

        return pathname

    @classmethod
    def compose_cfm_msg(cls, data_name='<data_name>', file_path="<file_path>", update=False, note=""):
        """
        Compose a short message to be printed for confirmation.

        :param data_name: name of the prepacked data, defaults to ``'<data_name>'``
        :type data_name: str
        :param file_path: pathname of the prepacked data file, defaults to ``"<file_path>"``
        :type file_path: str or os.PathLike[str]
        :param update: whether to (check on and) update the prepacked data, defaults to ``False``
        :type update: bool
        :param note: additional message, defaults to ``""``
        :type note: str
        :return: a short message to be printed for confirmation
        :rtype: str

        **Tests**::

            >>> from pydriosm.downloader import _Downloader

            >>> _Downloader.compose_cfm_msg()
            'To compile data of <data_name>\\n?'

            >>> _Downloader.compose_cfm_msg(update=True)
            'To update the data of <data_name>\\n?'
        """

        action = "update the" if (os.path.exists(file_path) or update) else "compile"
        cfm_msg = f"To {action} data of {data_name}" + (" " + note if note else "") + "\n?"

        return cfm_msg

    @classmethod
    def print_act_msg(cls, data_name='<data_name>', verbose=False, confirmation_required=True,
                      note="", end=" ... "):
        """
        Print a short message showing the action as a function runs.

        :param data_name: name of the prepacked data, defaults to ``'<data_name>'``
        :type data_name: str
        :param verbose: whether to print relevant information in console, defaults to ``False``
        :type verbose: bool or int
        :param confirmation_required: whether asking for confirmation to proceed, defaults to ``True``
        :type confirmation_required: bool
        :param note: additional message, defaults to ``""``
        :type note: str
        :param end: end string after printing the status message, defaults to ``" ... "``
        :type end: str

        **Tests**::

            >>> from pydriosm.downloader import _Downloader

            >>> _Downloader.print_act_msg(verbose=False) is None  # Nothing will be printed.
            True

            >>> _Downloader.print_act_msg(verbose=True); print("Done.")
            Compiling the data ... Done.

            >>> _Downloader.print_act_msg(verbose=True, note="(Some notes here.)"); print("Done.")
            Compiling the data (Some notes here.) ... Done.

            >>> _Downloader.print_act_msg(verbose=True, confirmation_required=False); print("Done.")
            Compiling data of <data_name> ... Done.
        """

        if verbose:
            action = "Compiling"
            suffix = "the data" if confirmation_required else f"data of {data_name}"
            action_msg = " ".join([action, suffix]) + (" " + note if note else "")
            print(action_msg, end=end)

    @classmethod
    def print_otw_msg(cls, data_name='<data_name>', path_to_file="<file_path>", verbose=False,
                      error_message=None, update=False):
        """
        Print a short message for an otherwise situation.

        :param data_name: name of the prepacked data, defaults to ``'<name_of_data>'``
        :type data_name: str
        :param path_to_file: pathname of the prepacked data file, defaults to ``"<file_path>"``
        :type path_to_file: str or os.PathLike[str]
        :param verbose: whether to print relevant information in console, defaults to ``False``
        :type verbose: bool or int
        :param error_message: message of an error detected during execution of a function,
            defaults to ``None``
        :type error_message: Exception or str or None
        :param update: whether to (check on and) update the prepacked data, defaults to ``False``
        :type update: bool

        **Tests**::

            >>> from pydriosm.downloader import _Downloader

            >>> _Downloader.print_otw_msg() is None  # Nothing will be printed.
            True

            >>> _Downloader.print_otw_msg(verbose=True)
            Cancelled.

            >>> _Downloader.print_otw_msg(verbose=2)
            The collecting of <data_name> is cancelled, or no data is available.

            >>> _Downloader.print_otw_msg(verbose=True, error_message="Errors.")
            Failed. Errors.
        """

        verbose_ = verbose is True or verbose == 1

        if error_message is not None:
            if verbose_:
                print(f"Failed. {error_message}")
        else:
            if verbose == 2:
                action = "updating" if update or os.path.exists(path_to_file) else "collecting"
                print(f"The {action} of {data_name} is cancelled, or no data is available.")
            elif verbose_:
                print(f"Cancelled.")

    @classmethod
    def get_prepacked_data(cls, meth, data_name='<data_name>', update=False, confirmation_required=True,
                           verbose=False, cfm_msg_note="", act_msg_note="", act_msg_end=" ... "):
        """
        Get auxiliary data (that is to be prepacked in the package).

        :param meth: name of a class method for getting (auxiliary) prepacked data
        :type meth: typing.Callable
        :param data_name: name of the prepacked data, defaults to ``'<data_name>'``
        :type data_name: str
        :param update: whether to (check on and) update the prepacked data, defaults to ``False``
        :type update: bool
        :param confirmation_required: whether asking for confirmation to proceed, defaults to ``True``
        :type confirmation_required: bool
        :param verbose: whether to print relevant information in console, defaults to ``False``
        :type verbose: bool or int
        :param cfm_msg_note: additional message for the method
            :meth:`~pydriosm.downloader._Downloader.compose_cfm_msg`, defaults to ``""``
        :type cfm_msg_note: str
        :param act_msg_note: equivalent of the parameter ``note`` of the method
            :meth:`~pydriosm.downloader._Downloader.print_action_msg`, defaults to ``""``
        :type act_msg_note: str
        :param act_msg_end: equivalent of the parameter ``end`` of the method
            :meth:`~pydriosm.downloader._Downloader.print_action_msg`, defaults to ``" ... "``
        :type act_msg_end: str
        :return: auxiliary data
        :rtype: typing.Any

        **Tests**::

            >>> from pydriosm.downloader import _Downloader

            >>> _Downloader.get_prepacked_data(callable, confirmation_required=False) is None
            True
        """

        if data_name is None:
            data_name = cls.NAME

        path_to_pickle = _cdd(data_name.replace(" ", "_").lower() + ".pickle")

        if os.path.isfile(path_to_pickle) and not update:
            data = load_pickle(path_to_pickle)

        else:
            data = None

            cfm_msg = cls.compose_cfm_msg(
                data_name=data_name, file_path=path_to_pickle, update=update, note=cfm_msg_note)

            if confirmed(cfm_msg, confirmation_required=confirmation_required):
                cls.print_act_msg(
                    data_name=data_name, verbose=verbose, confirmation_required=confirmation_required,
                    note=act_msg_note, end=act_msg_end)

                try:
                    data = meth(path_to_pickle, verbose)

                except Exception as error_message:
                    cls.print_otw_msg(
                        data_name=data_name, path_to_file=path_to_pickle, verbose=verbose,
                        error_message=error_message, update=update)

            else:
                cls.print_otw_msg(
                    data_name=data_name, path_to_file=path_to_pickle, verbose=verbose, update=update)

        return data

    @classmethod
    def validate_subregion_name(cls, subregion_name, valid_subregion_names=None, raise_err=True,
                                **kwargs):
        """
        Validate an input name of a geographic (sub)region.

        The validation is done by matching the input to a name of a geographic (sub)region
        available on a free download server.

        :param subregion_name: name/URL of a (sub)region available on a free download server
        :type subregion_name: str
        :param valid_subregion_names: names of all (sub)regions available on a free download server
        :type valid_subregion_names: typing.Iterable
        :param raise_err: (if the input fails to match a valid name) whether to raise the error
            :py:class:`pydriosm.downloader.InvalidSubregionName`, defaults to ``True``
        :type raise_err: bool
        :param kwargs: [optional] parameters of `pyhelpers.text.find_similar_str()`_
        :return: valid subregion name that matches (or is the most similar to) the input
        :rtype: str

        .. _`pyhelpers.text.find_similar_str()`:
            https://pyhelpers.readthedocs.io/en/latest/_generated/pyhelpers.text.find_similar_str.html

        **Tests**::

            >>> from pydriosm.downloader import _Downloader

            >>> subrgn_name = 'abc'
            >>> _Downloader.validate_subregion_name(subrgn_name)
            Traceback (most recent call last):
              ...
            pydriosm.errors.InvalidSubregionNameError:
              `subregion_name='abc'`
                1) `subregion_name` fails to match any in `<downloader>.valid_subregion_names`; or
                2) The queried (sub)region is not available on the free download server.

            >>> avail_subrgn_names = ['Greater London', 'Great Britain', 'Birmingham', 'Leeds']

            >>> subrgn_name = 'Britain'
            >>> _Downloader.validate_subregion_name(subrgn_name, avail_subrgn_names)
            'Great Britain'

            >>> subrgn_name = 'london'
            >>> _Downloader.validate_subregion_name(subrgn_name, avail_subrgn_names)
            'Greater London'

        .. seealso::

            - Examples for the methods
              :meth:`GeofabrikDownloader.validate_subregion_name()
              <pydriosm.downloader.GeofabrikDownloader.validate_subregion_name>` and
              :meth:`BBBikeDownloader.validate_subregion_name()
              <pydriosm.downloader.BBBikeDownloader.validate_subregion_name>`.
        """

        if valid_subregion_names is None:
            valid_subregion_names = cls.VALID_SUBREGION_NAMES

        if subregion_name in valid_subregion_names:
            subregion_name_ = subregion_name

        elif re.match(r'[Uu][Ss][Aa]?', subregion_name):
            subregion_name_ = 'United States of America'

        else:
            if os.path.isdir(os.path.dirname(subregion_name)) or is_url(url=subregion_name):
                base_name = os.path.basename(subregion_name).split('.')[0]
                subrgn_name_ = re.sub(r'-(latest|free)', '', base_name)
            else:
                subrgn_name_ = subregion_name

            # kwargs.update({'cutoff': 0.6})
            subregion_name_ = find_similar_str(subrgn_name_, lookup_list=valid_subregion_names, **kwargs)

            if raise_err:
                if subregion_name_ is None:
                    raise InvalidSubregionNameError(subregion_name, msg=1)

                elif cosine_similarity_between_texts(subregion_name_, subrgn_name_) < 0.4:
                    raise InvalidSubregionNameError(subregion_name, msg=2)

        return subregion_name_

    @classmethod
    def validate_file_format(cls, osm_file_format, valid_file_formats=None, raise_err=True,
                             **kwargs):
        """
        Validate an input file format of OSM data.

        The validation is done by matching the input to a filename extension available on
        a free download server.

        :param osm_file_format: file format/extension of the data available on a free download server
        :type osm_file_format: str
        :param valid_file_formats: fil extensions of the data available on a free download server
        :type valid_file_formats: typing.Iterable
        :param raise_err: (if the input fails to match a valid name) whether to raise the error
            :py:class:`pydriosm.downloader.InvalidFileFormatError`, defaults to ``True``
        :type raise_err: bool
        :param kwargs: [optional] parameters of `pyhelpers.text.find_similar_str()`_
        :return: validated file format
        :rtype: str

        .. _`pyhelpers.text.find_similar_str()`:
            https://pyhelpers.readthedocs.io/en/latest/_generated/pyhelpers.text.find_similar_str.html

        **Tests**::

            >>> from pydriosm.downloader import _Downloader

            >>> file_fmt = 'abc'
            >>> _Downloader.validate_file_format(file_fmt)  # Raise an error
            Traceback (most recent call last):
              ...
            pydriosm.errors.InvalidFileFormatError:
              `osm_file_format='abc'` -> The input `osm_file_format` is unidentifiable.
                Valid options include: {'.garmin-opentopo.zip', '.osm.bz2', '.osm.pbf', '.garmin-...

            >>> avail_file_fmts = ['.osm.pbf', '.shp.zip', '.osm.bz2']

            >>> file_fmt = 'pbf'
            >>> _Downloader.validate_file_format(file_fmt, avail_file_fmts)
            '.osm.pbf'

            >>> file_fmt = 'shp'
            >>> _Downloader.validate_file_format(file_fmt, avail_file_fmts)
            '.shp.zip'

        .. seealso::

            - Examples for the methods
              :meth:`GeofabrikDownloader.validate_file_format()
              <pydriosm.downloader.GeofabrikDownloader.validate_file_format>` and
              :meth:`BBBikeDownloader.validate_file_format()
              <pydriosm.downloader.BBBikeDownloader.validate_file_format>`.
        """

        if valid_file_formats is None:
            valid_file_formats = cls.FILE_FORMATS

        if osm_file_format in valid_file_formats:
            osm_file_format_ = copy.copy(osm_file_format)

        else:
            osm_file_format_ = find_similar_str(
                x=osm_file_format, lookup_list=valid_file_formats, **kwargs)

            if osm_file_format_ is None and raise_err:
                raise InvalidFileFormatError(osm_file_format, set(valid_file_formats))

        return osm_file_format_

    @classmethod
    def get_default_sub_path(cls, subregion_name_, download_url):
        """
        Get default sub path for saving OSM data file of a geographic (sub)region.

        :param subregion_name_: validated name of a (sub)region available on a free download server
        :type subregion_name_: str
        :param download_url: download URL of a geographic (sub)region
        :type download_url: str
        :return: default sub path
        :rtype: str or os.PathLike[str]

        **Tests**::

            >>> from pydriosm.downloader import _Downloader

            >>> subrgn_name_ = 'London'
            >>> dwnld_url = 'https://download.bbbike.org/osm/bbbike/London/London.osm.pbf'

            >>> _Downloader.get_default_sub_path(subrgn_name_, dwnld_url)
            '\\london'
        """

        sub_pathname, folder_name = "", "\\" + subregion_name_.lower().replace(" ", "-")

        if cls.NAME == 'Geofabrik':
            sub_pathname = os.path.dirname(urllib.parse.urlparse(download_url).path.replace("/", "\\"))

        sub_pathname += folder_name

        return sub_pathname

    @classmethod
    def make_subregion_dirname(cls, subregion_name_):
        """
        Make the name of the directory one level up from an OSM data file of a geographic (sub)region.

        :param subregion_name_: validated name of a (sub)region available on a free download server
        :type subregion_name_: str
        :return: name of the directory one level up from a downloaded OSM data file
        :rtype: str

        **Tests**::

            >>> from pydriosm.downloader import _Downloader

            >>> subrgn_name_ = 'England'
            >>> _Downloader.make_subregion_dirname(subrgn_name_)
            'england'

            >>> subrgn_name_ = 'Greater London'
            >>> _Downloader.make_subregion_dirname(subrgn_name_)
            'greater-london'
        """

        # Method 1:
        # sub_dirname = '-'.join(re.findall('[A-Z][^A-Z]*', subregion_name_.replace(' ', ''))).lower()

        # Method 2:
        # sub_dirname = '-'.join(subregion_name_.split()).lower()

        # Method 3:
        sub_dirname = '-'.join([x.strip(string.punctuation) for x in subregion_name_.split()]).lower()

        return sub_dirname

    @classmethod
    def get_subregion_download_url(cls, subregion_name, osm_file_format):
        """
        Get a download URL of a geographic (sub)region.

        :param subregion_name: name of a (sub)region available on a free download server
        :type subregion_name: str or None
        :param osm_file_format: file format/extension of the OSM data available on the download server
        :type osm_file_format: str
        :return: validated subregion name and the corresponding download URL
        :rtype: tuple

        See Examples for the methods
        :meth:`GeofabrikDownloader.get_subregion_download_url()
        <pydriosm.downloader.GeofabrikDownloader.get_subregion_download_url>` and
        :meth:`BBBikeDownloader.get_subregion_download_url()
        <pydriosm.downloader.BBBikeDownloader.get_subregion_download_url>`.
        """

        if not subregion_name and not osm_file_format:
            subregion_name_, download_url = None, None
        else:
            subregion_name_, download_url = '<subregion_name_>', '<download_url>'

        return subregion_name_, download_url

    def get_valid_download_info(self, subregion_name, osm_file_format, download_dir=None, **kwargs):
        """
        Get information of downloading (or downloaded) data file.

        The information includes a valid subregion name, a default filename, a URL and
        an absolute path where the data file is (to be) saved locally.

        :param subregion_name: name of a (sub)region available on a free download server
        :type subregion_name: str
        :param osm_file_format: file format/extension of the OSM data available on the download server
        :type osm_file_format: str
        :param download_dir: directory for saving the downloaded file(s), defaults to ``None``;
            when ``download_dir=None``, it refers to the method
            :meth:`~pydriosm.downloader.BBBike.cdd`
        :type download_dir: str or None
        :param kwargs: [optional] parameters of `pyhelpers.dirs.cd()`_,
            including ``mkdir``(default: ``False``)
        :return: valid subregion name, filename, download url and absolute file path
        :rtype: tuple

        .. _`pyhelpers.dirs.cd()`:
            https://pyhelpers.readthedocs.io/en/latest/_generated/pyhelpers.dirs.cd.html

        **Tests**::

            >>> from pydriosm.downloader import _Downloader
            >>> import os

            >>> d = _Downloader()

            >>> valid_dwnld_info = d.get_valid_download_info('subregion_name', 'osm_file_format')
            >>> valid_dwnld_info[0] == '<subregion_name_>'
            True
            >>> valid_dwnld_info[1] == '<download_url>'
            True
            >>> valid_dwnld_info[2] == '<download_url>'
            True
            >>> os.path.relpath(valid_dwnld_info[3])
            'osm_data\\<subregion_name_>\\<download_url>'

        .. seealso::

            Examples for the methods:

                - :meth:`GeofabrikDownloader.get_valid_download_info()
                  <pydriosm.downloader.GeofabrikDownloader.get_valid_download_info>`
                - :meth:`BBBikeDownloader.get_valid_download_info()
                  <pydriosm.downloader.BBBikeDownloader.get_valid_download_info>`
        """

        subregion_name_, download_url = self.get_subregion_download_url(
            subregion_name=subregion_name, osm_file_format=osm_file_format)

        if download_url:
            osm_filename = os.path.basename(download_url)

            if download_dir is None:  # Specify a default directory
                sub_path = self.get_default_sub_path(subregion_name_, download_url=download_url)

                if sub_path in self.download_dir:
                    file_pathname = cd(self.download_dir, osm_filename, **kwargs)
                else:
                    file_pathname = cd(self.download_dir + sub_path, osm_filename, **kwargs)

            else:
                download_dir_ = validate_dir(path_to_dir=download_dir)

                file_fmts_ = [y.replace('.', '-') for y in self.FILE_FORMATS]
                if any(download_dir_.endswith(x) for x in file_fmts_):
                    file_pathname = cd(download_dir_, osm_filename, **kwargs)
                else:
                    subrgn_dirname = self.make_subregion_dirname(subregion_name_)
                    file_pathname = cd(download_dir_, subrgn_dirname, osm_filename, **kwargs)

        else:
            osm_filename, file_pathname = None, None

        return subregion_name_, osm_filename, download_url, file_pathname

    def file_exists(self, subregion_name, osm_file_format, data_dir=None, update=False, verbose=True,
                    ret_file_path=False):
        """
        Check if the data file of a queried geographic (sub)region already exists locally,
        given its default filename.

        :param subregion_name: name of a (sub)region available on a free download server
        :type subregion_name: str
        :param osm_file_format: file format of the OSM data available on a free download server
        :type osm_file_format: str
        :param data_dir: directory where the data file (or files) is (or are) stored,
            defaults to ``None``; when ``data_dir=None``, it refers to the method
            :meth:`~pydriosm.downloader._Downloader.cdd`
        :type data_dir: str or None
        :param update: whether to (check and) update the data, defaults to ``False``
        :type update: bool
        :param verbose: whether to print relevant information in console, defaults to ``True``
        :type verbose: bool or int
        :param ret_file_path: whether to return the pathname of the data file (if it exists),
            defaults to ``False``
        :type ret_file_path: bool
        :return: whether the requested data file exists; or the path to the data file
        :rtype: bool or str

        **Tests**::

            >>> from pydriosm.downloader import _Downloader

            >>> d = _Downloader()

            >>> d.file_exists('<subregion_name>', 'shp')
            False

        .. seealso::

            - Examples for the methods :meth:`GeofabrikDownloader.file_exists()
              <pydriosm.downloader.GeofabrikDownloader.file_exists>` and
              :meth:`BBBikeDownloader.file_exists()
              <pydriosm.downloader.BBBikeDownloader.file_exists>`
        """

        subregion_name_, default_fn, _, path_to_file = self.get_valid_download_info(
            subregion_name=subregion_name, osm_file_format=osm_file_format, download_dir=data_dir,
            mkdir=False)

        if default_fn is None:
            if verbose == 2:
                osm_file_format_ = self.validate_file_format(
                    osm_file_format=osm_file_format, raise_err=False)
                print(f"{osm_file_format_} data for \"{subregion_name_}\" is not available "
                      f"on {self.NAME} free download server.")
            file_exists = False

        else:
            if os.path.isfile(path_to_file):
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

    def file_exists_and_more(self, subregion_names, osm_file_format, data_dir=None, update=False,
                             confirmation_required=True, verbose=True):
        """
        Check if a requested data file already exists and compile information for downloading the data.

        :param subregion_names: name(s) of geographic (sub)region(s) available on a free download server
        :type subregion_names: str or list
        :param osm_file_format: file format of the OSM data available on the free download server
        :type osm_file_format: str
        :param data_dir: directory where the data file (or files) is (or are) stored,
            defaults to ``None``
        :type data_dir: str or None
        :param update: whether to (check on and) update the data, defaults to ``False``
        :type update: bool
        :param confirmation_required: whether asking for confirmation to proceed, defaults to ``True``
        :type confirmation_required: bool
        :param verbose: whether to print relevant information in console, defaults to ``True``
        :type verbose: bool or int
        :return: whether the requested data file exists; or the path to the data file
        :rtype: tuple

        **Tests**::

            >>> from pydriosm.downloader import GeofabrikDownloader, BBBikeDownloader

            >>> gfd = GeofabrikDownloader()

            >>> gfd.file_exists_and_more('London', ".pbf")
            (['Greater London'], '.osm.pbf', True, 'download', ['Greater London'], [])

            >>> gfd.file_exists_and_more(['london', 'rutland'], ".pbf")
            (['Greater London', 'Rutland'],
             '.osm.pbf',
             True,
             'download',
             ['Greater London', 'Rutland'],
             [])

            >>> bbd = BBBikeDownloader()

            >>> bbd.file_exists_and_more('London', ".pbf")
            (['London'], '.pbf', True, 'download', ['London'], [])

            >>> bbd.file_exists_and_more(['birmingham', 'leeds'], ".pbf")
            (['Birmingham', 'Leeds'],
             '.pbf',
             True,
             'download',
             ['Birmingham', 'Leeds'],
             [])
        """

        if isinstance(subregion_names, str):
            subrgn_names_ = [subregion_names]
        else:
            subrgn_names_ = list(subregion_names)
        subrgn_names_ = [self.validate_subregion_name(x) for x in subrgn_names_]

        file_fmt_ = self.validate_file_format(osm_file_format)

        dwnld_list = subrgn_names_.copy()

        existing_file_paths = []  # Paths of existing files

        for subrgn_name_ in subrgn_names_:
            path_to_file = self.file_exists(
                subregion_name=subrgn_name_, osm_file_format=file_fmt_, data_dir=data_dir,
                update=update, ret_file_path=True)

            if isinstance(path_to_file, str):
                existing_file_paths.append(path_to_file)
                dwnld_list.remove(subrgn_name_)

                if verbose:
                    osm_filename = os.path.basename(path_to_file)
                    rel_path = os.path.relpath(os.path.dirname(path_to_file))
                    print("\"{}\" is already available\n\tat \"{}\\\".".format(osm_filename, rel_path))

        if not dwnld_list:
            if update:
                cfm_req_ = True if confirmation_required else False
                action_, dwnld_list_ = "update the", subrgn_names_.copy()
            else:
                cfm_req_ = False
                action_, dwnld_list_ = "", dwnld_list

        else:
            cfm_req_ = True if confirmation_required else False
            if len(dwnld_list) == len(subrgn_names_) or not update:
                action_ = "download"
                dwnld_list_ = dwnld_list
            else:
                action_ = "download/update the"
                dwnld_list_ = subrgn_names_.copy()

        # result = {
        #     'subregion_names': subregion_names_,
        #     'osm_file_format': file_fmt_,
        #     'confirmation_required': cfm_req_,
        #     'update_msg': action_,
        #     'downloads_list': downloads_list,
        #     'existing_file_paths': existing_file_paths,
        # }

        return subrgn_names_, file_fmt_, cfm_req_, action_, dwnld_list_, existing_file_paths

    def verify_download_dir(self, download_dir, verify_download_dir):
        """
        Verify the pathname of the current download directory.

        :param download_dir: directory for saving the downloaded file(s)
        :type download_dir: str or os.PathLike[str] or None
        :param verify_download_dir: whether to verify the pathname of the current download directory
        :type verify_download_dir: bool

        **Tests**::

            >>> from pydriosm.downloader import _Downloader
            >>> import os

            >>> d = _Downloader()

            >>> os.path.relpath(d.download_dir)
            'osm_data'

            >>> d.verify_download_dir(download_dir='tests', verify_download_dir=True)
            >>> os.path.relpath(d.download_dir)
            'tests'
        """

        if download_dir is not None and verify_download_dir:
            download_dir_ = validate_dir(path_to_dir=download_dir)

            if download_dir_ != self.download_dir:
                self.download_dir = download_dir_

    def _download_osm_data(self, download_url, file_pathname, verbose, verify_download_dir=True,
                           **kwargs):
        """
        Download an OSM data file.

        :param download_url: a valid URL of an OSM data file
        :type download_url: str
        :param file_pathname: path where the downloaded OSM data file is saved
        :type file_pathname: str
        :param verbose: whether to print relevant information in console
        :type verbose: bool or int
        :param kwargs: optional parameters of `pyhelpers.ops.download_file_from_url()`_

        .. _`pyhelpers.ops.download_file_from_url()`:
            https://pyhelpers.readthedocs.io/en/latest/_generated/
            pyhelpers.ops.download_file_from_url.html

        **Tests**::

            >>> from pydriosm.downloader import _Downloader
            >>> from pyhelpers.dirs import cd, delete_dir
            >>> import os

            >>> d = _Downloader()

            >>> dwnld_dir = "tests\\osm_data"
            >>> filename = "rutland-latest.osm.pbf"
            >>> pathname = cd(dwnld_dir, filename)

            >>> dwnld_url = f'https://download.geofabrik.de/europe/great-britain/england/{filename}'

            >>> os.path.exists(pathname)
            False

            >>> # Download the PBF data of Rutland
            >>> d._download_osm_data(download_url=dwnld_url, file_pathname=pathname, verbose=2)
            Downloading "rutland-latest.osm.pbf"
                to "tests\\osm_data\\"
            "tests\\osm_data\\rutland-latest.osm.pbf": 1.54MB [00:00, 4.65MB/s]
            Done.

            >>> os.path.isfile(pathname)
            True
            >>> os.path.relpath(d.download_dir)
            'tests\\osm_data'
            >>> len(d.data_paths)
            1
            >>> os.path.relpath(d.data_paths[0])
            'tests\\osm_data\\rutland-latest.osm.pbf'

            >>> delete_dir(d.download_dir, verbose=True)
            To delete the directory "tests\\osm_data\\" (Not empty)
            ? [No]|Yes: yes
            Deleting "tests\\osm_data\\" ... Done.
        """

        if verbose:
            if os.path.isfile(file_pathname):
                status_msg, prep = "Updating", "at"
            else:
                status_msg, prep = "Downloading", "to"
            rel_path = os.path.relpath(os.path.dirname(file_pathname))

            prt_msg = f"{status_msg} \"{os.path.basename(file_pathname)}\"\n\t{prep} \"{rel_path}\\\""
            print(prt_msg, end=" ... \n" if verbose == 2 else " ... ")

        try:
            verbose_ = True if verbose == 2 else False
            download_file_from_url(download_url, path_to_file=file_pathname, verbose=verbose_, **kwargs)

            if verbose:
                time.sleep(0.5)
                print("Done.")

        except Exception as e:
            print(f"Failed. {e}")

        if file_pathname not in self.data_paths:
            self.data_paths.append(file_pathname)

        if verify_download_dir:
            self.download_dir = os.path.dirname(file_pathname)


class GeofabrikDownloader(_Downloader):
    """
    Download OSM data from `Geofabrik`_ free download server.

    .. _`Geofabrik`: https://download.geofabrik.de/
    """

    #: Name of the free download server.
    NAME = 'Geofabrik'
    #: Full name of the data resource.
    LONG_NAME = 'Geofabrik OpenStreetMap data extracts'
    #: URL of the homepage to the free download server.
    URL = 'https://download.geofabrik.de/'
    #: URL of the official download index.
    DOWNLOAD_INDEX_URL = urllib.parse.urljoin(URL, 'index-v1.json')
    #: Default download directory.
    DEFAULT_DOWNLOAD_DIR = "osm_data\\geofabrik"
    #: Valid file formats.
    FILE_FORMATS = {'.osm.pbf', '.shp.zip', '.osm.bz2'}

    def __init__(self, download_dir=None):
        """
        :param download_dir: name or pathname of a directory for saving downloaded data files,
            defaults to ``None``; when ``download_dir=None``, downloaded data files are saved to a
            folder named 'osm_data' under the current working directory
        :type download_dir: str or os.PathLike[str] or None

        :ivar set valid_subregion_names: names of (sub)regions available on the free download server
        :ivar set valid_file_formats: filename extensions of the data files available
        :ivar pandas.DataFrame download_index: index of downloads for all available (sub)regions
        :ivar dict continent_tables: download catalogues for each continent
        :ivar dict region_subregion_tier: region-subregion tier
        :ivar list having_no_subregions: all (sub)regions that have no subregions
        :ivar pandas.DataFrame catalogue: a catalogue (index) of all available downloads
            (similar to :py:attr:`~pydriosm.downloader.GeofabrikDownloader.download_index`)
        :ivar str or None download_dir: name or pathname of a directory for saving downloaded data files
        :ivar list data_pathnames: list of pathnames of all downloaded data files

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
            'osm_data\\geofabrik'

            >>> gfd = GeofabrikDownloader(download_dir="tests\\osm_data")
            >>> os.path.relpath(gfd.download_dir)
            'tests\\osm_data'
        """

        super().__init__(download_dir=download_dir)

        self.download_index = self.get_download_index()

        self.continent_tables = self.get_continent_tables()

        self.region_subregion_tier, self.having_no_subregions = self.get_region_subregion_tier()

        self.catalogue = self.get_catalogue()

        self.valid_subregion_names = self.get_valid_subregion_names()

    @classmethod
    def get_raw_directory_index(cls, url, verbose=False):
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
            >>> type(raw_index)
            pandas.core.frame.DataFrame
            >>> raw_index.columns.tolist()
            ['file', 'date', 'size', 'metric_file_size', 'url']
        """

        if verbose:
            print(f"Collecting the raw directory index on '{url}'", end=" ... ")

        bs4_ = importlib.import_module(name='bs4')
        urllib_error = importlib.import_module(name='urllib.error')

        try:
            with requests.get(url=url, headers=fake_requests_headers()) as response:
                soup = bs4_.BeautifulSoup(markup=response.content, features='html.parser')

            cold_soup = soup.find(name='div', attrs={'id': 'details'})
            ths, tds = [], []
            for tr in cold_soup.find_all(name='tr'):
                if len(tr.find_all('th')) > 0:
                    ths = [x.get_text(strip=True) for x in tr.find_all(name='th')]
                else:
                    tds.append([x.get_text(strip=True) for x in tr.find_all(name='td')])

            raw_directory_index = pd.DataFrame(data=tds, columns=ths)

            # raw_directory_index.loc[:, 'date'] = pd.to_datetime(raw_directory_index['date'])
            raw_directory_index['date'] = pd.to_datetime(raw_directory_index['date'])
            # raw_directory_index.loc[:, 'size'] = raw_directory_index['size'].astype('int64')
            raw_directory_index['size'] = raw_directory_index['size'].astype('int64')

            raw_directory_index['metric_file_size'] = raw_directory_index['size'].map(
                lambda x: parse_size(x, binary=False, precision=0 if (x <= 1000) else 1))

            raw_directory_index['url'] = raw_directory_index['file'].map(
                lambda x: urllib.parse.urljoin(url, x))

            if verbose:
                print("Done.")

        except (urllib_error.HTTPError, AttributeError, TypeError, ValueError):
            print("Failed.")

            if verbose and len(urllib.parse.urlparse(url).path) <= 1:
                print("No raw directory index is available on the web page.")

            raw_directory_index = None

        return raw_directory_index

    @classmethod
    def _parse_download_index_urls(cls, urls):
        """
        Parse the dictionary of download URLs in the (original) dataframe of download index.

        :param urls: (original) series of the URLs provided in the official download index
        :type urls: pandas.Series
        :return: download index with parsed data of the URLs for downloading data
        :rtype: pandas.DataFrame

        .. seealso::

            - Examples for the method
              :meth:`~pydriosm.downloader.GeofabrikDownloader.get_download_index`.
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

    @classmethod
    def _download_index(cls, path_to_pickle=None, verbose=False):
        """
        Get the official index of downloads for all available geographic (sub)regions.

        :param path_to_pickle: pathname of the prepacked pickle file, defaults to ``None``
        :type path_to_pickle: str or os.PathLike[str] or None
        :param verbose: whether to print relevant information in console, defaults to ``False``
        :type verbose: bool or int
        :return: the official index of all downloads
        :rtype: pandas.DataFrame

        **Examples**::

            >>> from pydriosm.downloader import GeofabrikDownloader

            >>> gfd = GeofabrikDownloader()

            >>> gfd._download_index()

        .. seealso::

            - Examples for the method
              :meth:`~pydriosm.downloader.GeofabrikDownloader.get_download_index`.
        """

        with requests.get(url=cls.DOWNLOAD_INDEX_URL, headers=fake_requests_headers()) as response:
            raw_data = pd.DataFrame(json.loads(response.content)['features'])

        # Process 'properties'
        properties_ = pd.DataFrame(raw_data['properties'].to_list())
        properties = properties_.where(properties_.notnull(), None)

        # Process 'geometry'
        geometry_ = pd.DataFrame(raw_data['geometry'].to_list())
        geometry = geometry_.apply(
            lambda x: getattr(shapely.geometry, x['type'])(
                [shapely.geometry.Polygon(x['coordinates'][0][0])]), axis=1)
        geometry = pd.DataFrame(geometry, columns=['geometry'])

        dwnld_idx = pd.concat(objs=[properties, geometry], axis=1)

        # Process 'name'
        temp_names = dwnld_idx['name'].str.strip().str.replace('<br />', ' ')
        dwnld_idx.loc[:, 'name'] = temp_names.map(
            lambda x: x.replace('us/', '').title() if x.startswith('us/') else x)

        temp = (k for k, v in collections.Counter(dwnld_idx.name).items() if v > 1)
        duplicates = {i: x for k in temp for i, x in enumerate(dwnld_idx.name) if x == k}

        for dk in duplicates.keys():
            if dwnld_idx.loc[dk, 'id'].startswith('us/'):
                dwnld_idx.loc[dk, 'name'] += ' (US)'

        # Process 'urls'
        urls_column_name = 'urls'

        urls = cls._parse_download_index_urls(dwnld_idx[urls_column_name])
        del dwnld_idx[urls_column_name]

        # Put all together
        download_index = pd.concat(objs=[dwnld_idx, urls], axis=1)

        if verbose:
            print("Done.")

        if path_to_pickle:
            save_pickle(download_index, path_to_pickle=path_to_pickle, verbose=verbose)

        return download_index

    def get_download_index(self, update=False, confirmation_required=True, verbose=False):
        """
        Get the official index of downloads for all available geographic (sub)regions.

        Similar to the method :meth:`~pydriosm.downloader.GeofabrikDownloader.get_catalogue`.

        :param update: whether to (check on and) update the prepacked data, defaults to ``False``
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
            >>> type(geofabrik_dwnld_idx)
            pandas.core.frame.DataFrame
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

        data_name = f'{self.NAME} index of subregions'

        download_index = self.get_prepacked_data(
            self._download_index, data_name=data_name, update=update,
            confirmation_required=confirmation_required, verbose=verbose)

        if update is True:
            self.download_index = download_index

        return download_index

    @classmethod
    def _parse_subregion_table_tr(cls, tr, url):
        """
        Parse a <tr> tag under a <table> tag of the HTML data of a (sub)region.

        :param tr: <tr> tag under a <table> tag of a subregion's HTML data
        :type tr: bs4.element.Tag
        :param url: URL of a subregion's web page
        :type url: str
        :return: data contained in the <tr> tag
        :rtype: list

        .. seealso::

            - Examples for the method
              :meth:`~pydriosm.downloader.GeofabrikDownloader.get_subregion_table`.
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

    @classmethod
    def get_subregion_table(cls, url, verbose=False):
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
            Compiling information about subregions of "Antarctica" ... Failed.
            >>> antarctica is None
            True

            >>> # To get more information about the above failure, set `verbose=2`
            >>> antarctica2 = gfd.get_subregion_table(antarctica_url, verbose=2)
            Compiling information about subregions of "Antarctica" ... Failed.
            No subregion data is available for "Antarctica" on Geofabrik's free download server.
            >>> antarctica2 is None
            True
        """

        region_name = url.split('/')[-1].split('.')[0].replace('-', ' ').title()
        if verbose:
            print(f"Compiling information about subregions of \"{region_name}\"", end=" ... ")

        try:
            bs4_ = importlib.import_module('bs4')

            with requests.get(url=url, headers=fake_requests_headers()) as response:
                soup = bs4_.BeautifulSoup(markup=response.content, features='html.parser')

            tr_data = []

            h3_tags = soup.find_all(name='h3', string=re.compile(r'(Special )?Sub[ \-]Regions?'))
            if len(h3_tags) > 0:
                for h3_tag in h3_tags:
                    table = h3_tag.find_next(
                        name='table', attrs={'id': re.compile(r'(special)?subregions')})
                    trs = table.findChildren(name='tr', onmouseover=True)
                    tr_data += [cls._parse_subregion_table_tr(tr=tr, url=url) for tr in trs]
            else:
                table_tags = soup.find_all(
                    name='table', attrs={'id': re.compile(r'(special)?subregions')})
                for table_tag in table_tags:
                    trs = table_tag.findChildren(name='tr', onmouseover=True)
                    tr_data += [cls._parse_subregion_table_tr(tr=tr, url=url) for tr in trs]

            # Specify column names
            column_names = ['subregion', 'subregion-url', '.osm.pbf', '.shp.zip', '.osm.bz2']
            column_names.insert(3, '.osm.pbf-size')
            # column_names == [
            #     'subregion', 'subregion-url', '.osm.pbf', '.osm.pbf-size', '.shp.zip', '.osm.bz2']
            tbl = pd.DataFrame(data=tr_data, columns=column_names)
            table = tbl.where(pd.notnull(tbl), None)

            if verbose:
                print("Done.")

        except (AttributeError, ValueError, TypeError):
            if verbose:
                print(f"Failed.")
                if verbose == 2:
                    print(f"No subregion data is available for \"{region_name}\" "
                          f"on {cls.NAME}'s free download server.")

            table = None

        except (ConnectionRefusedError, ConnectionError):
            print("Failed.")

            if verbose == 2:
                print(f"Errors occurred when trying to connect {cls.NAME}'s free download server.")

            table = None

        return table

    @classmethod
    def _continent_tables(cls, path_to_pickle=None, verbose=False):
        """
        Get download catalogues for each continent.

        :param path_to_pickle: pathname of the prepacked pickle file, defaults to ``None``
        :type path_to_pickle: str or os.PathLike[str] or None
        :param verbose: whether to print relevant information in console, defaults to ``False``
        :type verbose: bool or int
        :return: download catalogues for each continent
        :rtype: dict

        .. seealso::

            - Examples for the method
              :meth:`~pydriosm.downloader.GeofabrikDownloader.get_continent_tables`.
        """

        bs4_ = importlib.import_module('bs4')

        with requests.get(url=cls.URL, headers=fake_requests_headers()) as response:
            soup = bs4_.BeautifulSoup(markup=response.content, features='html.parser')

        # Scan the homepage to collect info of regions for each continent
        tds = soup.find_all(name='td', attrs={'class': 'subregion'})
        continent_names = [td.a.text for td in tds]

        continent_links = [urllib.parse.urljoin(cls.URL, url=td.a['href']) for td in tds]
        continent_links_dat = [cls.get_subregion_table(url=url) for url in continent_links]
        continent_tables = dict(zip(continent_names, continent_links_dat))

        if verbose:
            print("Done.")

        if path_to_pickle:
            save_pickle(continent_tables, path_to_pickle=path_to_pickle, verbose=verbose)

        return continent_tables

    def get_continent_tables(self, update=False, confirmation_required=True, verbose=False):
        """
        Get download catalogues for each continent.

        :param update: whether to (check on and) update the prepacked data, defaults to ``False``
        :type update: bool
        :param confirmation_required: whether asking for confirmation to proceed, defaults to ``True``
        :type confirmation_required: bool
        :param verbose: whether to print relevant information in console, defaults to ``False``
        :type verbose: bool or int
        :return: download catalogues for each continent
        :rtype: dict or None

        **Examples**::

            >>> from pydriosm.downloader import GeofabrikDownloader

            >>> gfd = GeofabrikDownloader()

            >>> # Download information of subregions for each continent
            >>> continent_tables = gfd.get_continent_tables()
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

        data_name = f'{self.NAME} continent tables'

        continents_subregion_tables = self.get_prepacked_data(
            meth=self._continent_tables, data_name=data_name, update=update,
            confirmation_required=confirmation_required, verbose=verbose)

        return continents_subregion_tables

    @classmethod
    def _compile_region_subregion_tier(cls, subregion_tables):
        """
        Find out the all (sub)regions and their subregions.

        :param subregion_tables: download URLs of subregions;
            see examples of the methods
            :meth:`~pydriosm.downloader.GeofabrikDownloader.get_subregion_table` and
            :meth:`~pydriosm.downloader.GeofabrikDownloader.get_continent_tables`
        :type subregion_tables: dict
        :return: a dictionary of region-subregion, and a list of (sub)regions without subregions
        :rtype: tuple[dict, list]

        .. seealso::

            - Examples for the method
              :meth:`~pydriosm.downloader.GeofabrikDownloader.get_region_subregion_tier`.
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
                    cls.get_subregion_table(url=url) for url in subregion_table['subregion-url']]
                sub_subregion_tables = dict(zip(subregion_table['subregion'], subregion_tbls))

                region_subregion_tiers_, having_no_subregions_ = cls._compile_region_subregion_tier(
                    subregion_tables=sub_subregion_tables)

                having_no_subregions += having_no_subregions_

                region_subregion_tier.update({region_name: region_subregion_tiers_})
                having_subregions_temp.pop(region_name)

        having_no_subregions = list(first_unique(having_no_subregions))

        return region_subregion_tier, having_no_subregions

    def _region_subregion_tier(self, path_to_pickle=None, verbose=False):
        """
        Get region-subregion tier.

        :param path_to_pickle: pathname of the prepacked pickle file, defaults to ``None``
        :type path_to_pickle: str or os.PathLike[str] or None
        :param verbose: whether to print relevant information in console, defaults to ``False``
        :type verbose: bool or int
        :return: region-subregion tier and all that have no subregions
        :rtype: tuple[dict, list]

        .. seealso::

            - Examples for the method
              :meth:`~pydriosm.downloader.GeofabrikDownloader.get_region_subregion_tier`.
        """

        tiers, having_no_subregions = self._compile_region_subregion_tier(self.continent_tables)

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

        if path_to_pickle:
            save_pickle((tiers, having_no_subregions), path_to_pickle=path_to_pickle, verbose=verbose)

        return tiers, having_no_subregions

    def get_region_subregion_tier(self, update=False, confirmation_required=True, verbose=False):
        """
        Get region-subregion tier and all (sub)regions that have no subregions.

        This includes all geographic (sub)regions for which data of subregions is unavailable.

        :param update: whether to (check on and) update the prepacked data, defaults to ``False``
        :type update: bool
        :param confirmation_required: whether asking for confirmation to proceed, defaults to ``True``
        :type confirmation_required: bool
        :param verbose: whether to print relevant information in console, defaults to ``False``
        :type verbose: bool or int
        :return: region-subregion tier and all (sub)regions that have no subregions
        :rtype: tuple[dict, list] or tuple[None, None]

        **Examples**::

            >>> from pydriosm.downloader import GeofabrikDownloader

            >>> gfd = GeofabrikDownloader()

            >>> # region-subregion tier, and all regions that have no subregions
            >>> rgn_subrgn_tier, no_subrgn_list = gfd.get_region_subregion_tier()
            >>> type(rgn_subrgn_tier)
            dict
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

            >>> type(no_subrgn_list)
            list
            >>> # Example: five regions that have no subregions
            >>> no_subrgn_list[0:5]
            ['Antarctica', 'Algeria', 'Angola', 'Benin', 'Botswana']
        """

        data_name = f'{self.NAME} region-subregion tier'

        if update:
            self.continent_tables = self.get_continent_tables(
                update=update, confirmation_required=False, verbose=False)

        note_msg = "(Note that this process may take a few minutes)"

        data = self.get_prepacked_data(
            self._region_subregion_tier, data_name=data_name, update=update,
            confirmation_required=confirmation_required, verbose=verbose, cfm_msg_note=note_msg,
            act_msg_note="" if confirmation_required else note_msg)

        if data is None:
            tiers, having_no_subregions = None, None
        else:
            tiers, having_no_subregions = data
            if update is True:
                self.region_subregion_tier = tiers
                self.having_no_subregions = having_no_subregions

        return tiers, having_no_subregions

    def _catalogue(self, path_to_pickle=None, verbose=False):
        """
        Get a catalogue (index) of all available downloads.

        :param path_to_pickle: pathname of the prepacked pickle file, defaults to ``None``
        :type path_to_pickle: str or os.PathLike[str] or None
        :param verbose: whether to print relevant information in console, defaults to ``False``
        :type verbose: bool or int
        :return: a catalogue for all subregion downloads
        :rtype: pandas.DataFrame

        .. seealso::

            - Examples for the method
              :meth:`~pydriosm.downloader.GeofabrikDownloader.get_catalogue`.
        """

        bs4_ = importlib.import_module('bs4')

        with requests.get(url=self.URL, headers=fake_requests_headers()) as response:
            soup = bs4_.BeautifulSoup(markup=response.content, features='html.parser')

        # Home table
        home_tr_data = []
        table_tags = soup.find_all(name='table', attrs={'id': re.compile(r'(special)?subregions')})
        for table_tag in table_tags:
            trs = table_tag.findChildren(name='tr', onmouseover=True)
            home_tr_data += [self._parse_subregion_table_tr(tr=tr, url=self.URL) for tr in trs]

        column_names = ['subregion', 'subregion-url', '.osm.pbf', '.shp.zip', '.osm.bz2']
        column_names.insert(3, '.osm.pbf-size')

        home_subregion_table = pd.DataFrame(data=home_tr_data, columns=column_names)

        # Subregions' tables
        cont_tds = soup.find_all(name='td', attrs={'class': 'subregion'})
        cont_urls = [urllib.parse.urljoin(base=self.URL, url=td.a.get('href')) for td in cont_tds]
        continent_tbls = [self.get_subregion_table(url=url, verbose=False) for url in cont_urls]
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

        temp = (k for k, v in collections.Counter(downloads_catalogue.subregion).items() if v > 1)
        duplicates = {i: x for k in temp for i, x in enumerate(downloads_catalogue.subregion) if x == k}

        for dk in duplicates.keys():
            if os.path.dirname(downloads_catalogue.loc[dk, 'subregion-url']).endswith('us'):
                downloads_catalogue.loc[dk, 'subregion'] += ' (US)'

        if verbose:
            print("Done.")

        if path_to_pickle:
            save_pickle(downloads_catalogue, path_to_pickle=path_to_pickle, verbose=verbose)

        return downloads_catalogue

    def get_catalogue(self, update=False, confirmation_required=True, verbose=False):
        """
        Get a catalogue (index) of all available downloads.

        Similar to the method :meth:`~pydriosm.downloader.GeofabrikDownloader.get_download_index`.

        :param update: whether to (check on and) update the prepacked data, defaults to ``False``
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
            - Two subregions have the same name 'Georgia':
              `Europe\\Georgia <https://download.geofabrik.de/europe/georgia.html>`_ and
              `US\\Georgia <https://download.geofabrik.de/north-america/us/georgia.html>`_;
              In the latter case, a suffix ' (US)' is appended to the name in the table.
        """

        data_name = f'{self.NAME} downloads catalogue'

        msg_note = "(Note that this process may take a few minutes)"

        downloads_catalogue = self.get_prepacked_data(
            self._catalogue, data_name=data_name, update=update,
            confirmation_required=confirmation_required, verbose=verbose, cfm_msg_note=msg_note,
            act_msg_note="" if confirmation_required else msg_note)

        if update is True:
            self.catalogue = downloads_catalogue

        return downloads_catalogue

    def _valid_subregion_names(self, path_to_pickle=None, verbose=False):
        """
        Get names of all available geographic (sub)regions.

        :param path_to_pickle: pathname of the prepacked pickle file, defaults to ``None``
        :type path_to_pickle: str or os.PathLike[str] or None
        :param verbose: whether to print relevant information in console, defaults to ``False``
        :type verbose: bool or int
        :return: names of all geographic (sub)regions available on Geofabrik free download server
        :rtype: set

        .. seealso::

            - Examples for the method
              :meth:`~pydriosm.downloader.GeofabrikDownloader.get_valid_subregion_names`.
        """

        dwnld_index = self.get_download_index(update=False, confirmation_required=False, verbose=False)

        valid_subregion_names = set(dwnld_index['name'])

        if verbose:
            print("Done.")

        if path_to_pickle:
            save_pickle(valid_subregion_names, path_to_pickle=path_to_pickle, verbose=verbose)

        return valid_subregion_names

    def get_valid_subregion_names(self, update=False, confirmation_required=True, verbose=False):
        """
        Get names of all available geographic (sub)regions.

        :param update: whether to (check on and) update the prepacked data, defaults to ``False``
        :type update: bool
        :param confirmation_required: whether asking for confirmation to proceed, defaults to ``True``
        :type confirmation_required: bool
        :param verbose: whether to print relevant information in console, defaults to ``False``
        :type verbose: bool or int
        :return: names of all geographic (sub)regions available on Geofabrik free download server
        :rtype: set or None

        **Examples**::

            >>> from pydriosm.downloader import GeofabrikDownloader

            >>> gfd = GeofabrikDownloader()

            >>> # A list of the names of available geographic (sub)regions
            >>> valid_subrgn_names = gfd.get_valid_subregion_names()
            >>> type(valid_subrgn_names)
            set
        """

        data_name = f'{self.NAME} subregion names'

        if update:
            _ = self.get_download_index(update=update, confirmation_required=False, verbose=False)

        self.valid_subregion_names = self.get_prepacked_data(
            meth=self._valid_subregion_names, data_name=data_name, update=update,
            confirmation_required=confirmation_required, verbose=verbose)

        return self.valid_subregion_names

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
            >>> valid_subrgn_name = gfd.validate_subregion_name(subregion_name=input_subrgn_name)
            >>> valid_subrgn_name
            'Greater London'

            >>> input_subrgn_name = 'https://download.geofabrik.de/europe/great-britain.html'
            >>> valid_subrgn_name = gfd.validate_subregion_name(subregion_name=input_subrgn_name)
            >>> valid_subrgn_name
            'Great Britain'
        """

        subregion_name_ = super().validate_subregion_name(
            subregion_name=subregion_name, valid_subregion_names=self.valid_subregion_names,
            **kwargs)

        return subregion_name_

    def validate_file_format(self, osm_file_format, **kwargs):
        """
        Validate an input file format of OSM data.

        The validation is done by matching the input to a filename extension available on
        Geofabrik free download server.

        :param osm_file_format: file format/extension of the OSM data on the free download server
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
            >>> valid_file_format = gfd.validate_file_format(osm_file_format=input_file_format)
            >>> valid_file_format
            '.osm.pbf'

            >>> input_file_format = "shp"
            >>> valid_file_format = gfd.validate_file_format(osm_file_format=input_file_format)
            >>> valid_file_format
            '.shp.zip'
        """

        osm_file_format_ = super().validate_file_format(
            osm_file_format=osm_file_format, valid_file_formats=self.FILE_FORMATS,
            **kwargs)

        return osm_file_format_

    def get_subregion_download_url(self, subregion_name, osm_file_format, update=False, verbose=False):
        """
        Get a download URL of a geographic (sub)region.

        :param subregion_name: name of a (sub)region available on Geofabrik free download server
        :type subregion_name: str
        :param osm_file_format: file format/extension of the OSM data available on the download server
        :type osm_file_format: str
        :param update: whether to (check on and) update the prepacked data, defaults to ``False``
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

        if update:  # Update the download catalogue (including download URLs)
            _ = self.get_catalogue(update=update, verbose=verbose)

        subrgn_dwnld_cat = self.catalogue.set_index(keys='subregion')

        try:
            subregion_name_ = self.validate_subregion_name(subregion_name=subregion_name)
            osm_file_format_ = self.validate_file_format(osm_file_format=osm_file_format)

            # Get the URL
            download_url = subrgn_dwnld_cat.loc[subregion_name_, osm_file_format_]

        except (InvalidSubregionNameError, InvalidFileFormatError):
            subregion_name_, download_url = None, None

        return subregion_name_, download_url

    def get_default_filename(self, subregion_name, osm_file_format, update=False):
        """
        get a default filename for a geograpic (sub)region.

        The default filename is derived from the download URL of the requested data file.

        :param subregion_name: name of a (sub)region available on Geofabrik free download server
        :type subregion_name: str
        :param osm_file_format: file format/extension of the OSM data available on the download server
        :type osm_file_format: str
        :param update: whether to (check on and) update the prepacked data, defaults to ``False``
        :type update: bool
        :return: default OSM filename for the ``subregion_name``
        :rtype: str or None

        **Examples**::

            >>> from pydriosm.downloader import GeofabrikDownloader

            >>> gfd = GeofabrikDownloader()

            >>> # Default filename of the PBF data of London
            >>> subrgn_name, file_format = 'london', ".pbf"
            >>> default_fn = gfd.get_default_filename(subrgn_name, file_format)
            >>> default_fn
            'greater-london-latest.osm.pbf'

            >>> # Default filename of the shapefile data of Great Britain
            >>> subrgn_name, file_format = 'britain', ".shp"
            >>> default_fn = gfd.get_default_filename(subrgn_name, file_format)
            No .shp.zip data is available to download for Great Britain.
            >>> default_fn is None
            True
        """

        subregion_name_, download_url = self.get_subregion_download_url(
            subregion_name=subregion_name, osm_file_format=osm_file_format, update=update)

        if download_url is None:
            osm_file_format_ = self.validate_file_format(osm_file_format=osm_file_format)
            print(f"No {osm_file_format_} data is available to download for {subregion_name_}.")
            default_filename = None

        else:
            default_filename = os.path.basename(download_url)

        return default_filename

    def _default_pathname(self, download_url, mkdir=False):
        """
        Get the default pathname of a local directory for storing a downloaded data file,
        given its URL.

        :param download_url: URL for downloading a data file
        :type download_url: str
        :param mkdir: whether to create the directory (and subdirectories) if not available,
            defaults to ``False``
        :type mkdir: bool
        :return: efault filename of the subregion and default (absolute) path to the file
        :rtype: tuple[str, str]

        .. seealso::

            - Examples for the method
              :meth:`~pydriosm.downloader.GeofabrikDownloader.get_default_file_path`.
        """

        parsed_path = str(urllib.parse.urlparse(download_url).path).lstrip('/').split('/')

        default_filename = parsed_path[-1]
        sub_dir_ = re.sub(r'-(latest|free)', '', default_filename.split('.')[0])

        sub_dirs_and_filename = parsed_path[:-1] + [sub_dir_, default_filename]

        # sub_dirs = [
        #     find_similar_str(
        #         re.sub(r'-(latest|free)', '', x.split('.')[0]), self.valid_subregion_names)
        #     if x != 'us' else 'United States of America' for x in parsed_path]
        # directory = self.cdd(*sub_dirs, mkdir=mkdir)
        # default_file_path = os.path.join(directory, default_filename)

        default_pathname = self.cdd(*sub_dirs_and_filename, mkdir=mkdir)

        return default_pathname, default_filename

    def get_default_pathname(self, subregion_name, osm_file_format, mkdir=False, update=False,
                             verbose=False):
        """
        Get the default pathname of a local directory for storing a downloaded data file.

        The default file path is derived from the download URL of the requested data file.

        :param subregion_name: name of a (sub)region available on Geofabrik free download server
        :type subregion_name: str
        :param osm_file_format: file format/extension of the OSM data available on the download server
        :type osm_file_format: str
        :param mkdir: whether to create a directory, defaults to ``False``
        :type mkdir: bool
        :param update: whether to (check on and) update the prepacked data, defaults to ``False``
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

            >>> pathname, filename = gfd.get_default_pathname(subrgn_name, file_format)
            >>> os.path.relpath(os.path.dirname(pathname))
            'osm_data\\geofabrik\\europe\\great-britain\\england\\greater-london'
            >>> filename
            'greater-london-latest.osm.pbf'
        """

        subregion_name_, download_url = self.get_subregion_download_url(
            subregion_name=subregion_name, osm_file_format=osm_file_format, update=update)

        if download_url is None:  # The requested data may not exist
            if verbose:
                # osm_file_format_ = re.search(r'\.\w{3}\.\w{3}', os.path.basename(download_url)).group()
                osm_file_format_ = self.validate_file_format(osm_file_format=osm_file_format)
                print(f"No {osm_file_format_} data is available to download for {subregion_name_}.")
            default_pathname, default_filename = None, None

        else:
            default_pathname, default_filename = self._default_pathname(
                download_url=download_url, mkdir=mkdir)

        return default_pathname, default_filename

    def _enumerate_subregions(self, subregion_name, region_subregion_tier=None):
        """
        Find subregions of a given geographic (sub)region.

        :param subregion_name: name of a (sub)region available on Geofabrik free download server
        :type subregion_name: str
        :param region_subregion_tier: region-subregion tier, defaults to ``None``;
            when ``region_subregion_tier=None``, it defaults to the dictionary returned by the method
            :meth:`~pydriosm.downloader.GeofabrikDownloader.get_region_subregion_tier`
        :type region_subregion_tier: dict
        :return: name(s) of subregion(s) of the given geographic (sub)region
        :rtype: generator object

        **Examples**::

            >>> from pydriosm.downloader import GeofabrikDownloader

            >>> gfd = GeofabrikDownloader()

            >>> gb_subregions = gfd._enumerate_subregions(subregion_name='Great Britain')
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
                for subrgn in self._enumerate_subregions(subregion_name, v):
                    if isinstance(subrgn, dict):
                        yield list(subrgn.keys())
                    else:
                        yield [subrgn] if isinstance(subrgn, str) else subrgn

    def get_subregions(self, *subregion_name, deep=False):
        """
        Retrieve names of all subregions (if any) of the given geographic (sub)region(s).

        The returned result is based on the region-subregion tier structured by the method
        :meth:`~pydriosm.downloader.GeofabrikDownloader.get_region_subregion_tier`.

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
            >>> type(all_subrgn_names)
            list

            >>> # Names of all subregions of England and North America
            >>> e_na_subrgn_names = gfd.get_subregions('england', 'n america')
            >>> type(e_na_subrgn_names)
            list

            >>> # Names of all subregions of North America
            >>> na_subrgn_names = gfd.get_subregions('n america', deep=True)
            >>> type(na_subrgn_names)
            list

            >>> # Names of subregions of Great Britain
            >>> gb_subrgn_names = gfd.get_subregions('britain')
            >>> len(gb_subrgn_names) == 3
            True

            >>> # Names of all subregions of Great Britain's subregions
            >>> gb_subrgn_names_ = gfd.get_subregions('britain', deep=True)
            >>> len(gb_subrgn_names_) >= len(gb_subrgn_names)
            True
        """

        if not subregion_name:
            subregion_names = self.having_no_subregions

        else:
            rslt = []
            for subrgn_name in subregion_name:
                subrgn_name = self.validate_subregion_name(subrgn_name)
                subrgn_names = self._enumerate_subregions(subrgn_name, self.region_subregion_tier)
                rslt += list(subrgn_names)[0]

            if not deep:
                subregion_names = rslt

            else:
                check_list = [x for x in rslt if x not in self.having_no_subregions]

                if len(check_list) > 0:
                    rslt_ = list(set(rslt) - set(check_list))
                    rslt_ += self.get_subregions(*check_list)
                else:
                    rslt_ = rslt

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
            :meth:`~pydriosm.downloader.GeofabrikDownloader.cdd`
        :type download_dir: str or None
        :param kwargs: [optional] parameters of `pyhelpers.dirs.cd()`_,
            including ``mkdir``(default: ``False``)
        :return: pathname of a download directory
            for downloading data of all subregions of the specified (sub)region and format
        :rtype: str

        .. _`pyhelpers.dirs.cd()`:
            https://pyhelpers.readthedocs.io/en/latest/_generated/pyhelpers.dirs.cd.html

        **Examples**::

            >>> from pydriosm.downloader import GeofabrikDownloader
            >>> import os

            >>> gfd = GeofabrikDownloader()

            >>> subrgn_name = 'london'
            >>> file_format = ".pbf"

            >>> # Default download directory (if the requested data file is not available)
            >>> dwnld_dir = gfd.specify_sub_download_dir(subrgn_name, file_format)
            >>> os.path.dirname(os.path.relpath(dwnld_dir))
            'osm_data\\geofabrik\\europe\\great-britain\\england\\greater-london'

            >>> # When a download directory is specified
            >>> dwnld_dir = "tests\\osm_data"

            >>> subrgn_name = 'britain'
            >>> file_format = ".shp"

            >>> dwnld_pathname = gfd.specify_sub_download_dir(subrgn_name, file_format, dwnld_dir)
            >>> os.path.relpath(dwnld_pathname)
            'tests\\osm_data\\great-britain-shp-zip'

            >>> gfd_ = GeofabrikDownloader(download_dir=dwnld_dir)
            >>> dwnld_pathname_ = gfd_.specify_sub_download_dir(subrgn_name, file_format)
            >>> os.path.relpath(dwnld_pathname_)
            'tests\\osm_data\\europe\\great-britain\\great-britain-shp-zip'
        """

        pathname_and_filename = list(self.get_default_pathname(subregion_name, osm_file_format))

        none_count = len([x for x in pathname_and_filename if x is None])

        if none_count == len(pathname_and_filename):  # The required data file is not available
            subregion_name_ = self.validate_subregion_name(subregion_name=subregion_name)
            osm_file_format_ = self.validate_file_format(osm_file_format=osm_file_format)

            _, dwnld_url = self.get_subregion_download_url(subregion_name_, ".osm.pbf")
            sub_path = self.get_default_sub_path(subregion_name_, dwnld_url).lstrip('\\')
            sub_dir = re.sub(r"[. ]", "-", subregion_name_.lower() + osm_file_format_)

        else:
            file_pathname, filename = pathname_and_filename
            sub_path, sub_dir = os.path.dirname(file_pathname), re.sub(r"[. ]", "-", filename).lower()

        if download_dir is None:
            if sub_path + "\\" + sub_dir in self.download_dir:
                sub_dwnld_dir = self.download_dir
            else:
                sub_dwnld_dir = cd(self.download_dir, sub_path, sub_dir, **kwargs)
        else:
            sub_dwnld_dir = cd(validate_dir(path_to_dir=download_dir), sub_dir, **kwargs)

        return sub_dwnld_dir

    def get_valid_download_info(self, subregion_name, osm_file_format, download_dir=None, **kwargs):
        """
        Get information of downloading (or downloaded) data file.

        The information includes a valid subregion name, a default filename, a URL and
        an absolute path where the data file is (to be) saved locally.

        :param subregion_name: name of a (sub)region available on
            GeofabrikDownloader free download server
        :type subregion_name: str
        :param osm_file_format: file format/extension of the OSM data available on the download server
        :type osm_file_format: str
        :param download_dir: directory for saving the downloaded file(s), defaults to ``None``;
            when ``download_dir=None``, it refers to the method
            :meth:`~pydriosm.downloader.GeofabrikDownloader.cdd`
        :type download_dir: str or None
        :param kwargs: [optional] parameters of `pyhelpers.dirs.cd()`_,
            including ``mkdir``(default: ``False``)
        :return: valid subregion name, filename, download url and absolute file path
        :rtype: typing.Tuple[str, str, str, str]

        .. _`pyhelpers.dirs.cd()`:
            https://pyhelpers.readthedocs.io/en/latest/_generated/pyhelpers.dirs.cd.html

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
            >>> os.path.dirname(dwnld_url)
            'https://download.geofabrik.de/europe/great-britain/england'
            >>> os.path.relpath(os.path.dirname(path_to_pbf))
            'osm_data\\geofabrik\\europe\\great-britain\\england\\greater-london'

            >>> # Specify a new directory for downloaded data
            >>> dwnld_dir = "tests\\osm_data"

            >>> info2 = gfd.get_valid_download_info(subrgn_name, file_format, dwnld_dir)
            >>> _, _, _, path_to_pbf2 = info2

            >>> os.path.relpath(os.path.dirname(path_to_pbf2))
            'tests\\osm_data\\greater-london'

            >>> gfd_ = GeofabrikDownloader(download_dir=dwnld_dir)

            >>> info3 = gfd_.get_valid_download_info(subrgn_name, file_format)
            >>> _, _, _, path_to_pbf3 = info3

            >>> os.path.relpath(os.path.dirname(path_to_pbf3))
            'tests\\osm_data\\europe\\great-britain\\england\\greater-london'
        """

        subregion_name_, osm_filename, download_url, file_pathname = super().get_valid_download_info(
            subregion_name=subregion_name, osm_file_format=osm_file_format,
            download_dir=download_dir, **kwargs)

        return subregion_name_, osm_filename, download_url, file_pathname

    def file_exists(self, subregion_name, osm_file_format, data_dir=None, update=False, verbose=False,
                    ret_file_path=False):
        """
        Check whether a data file of a geographic (sub)region already exists locally,
        given its default filename.

        :param subregion_name: name of a (sub)region available on Geofabrik free download server
        :type subregion_name: str
        :param osm_file_format: file format/extension of the OSM data available on the download server
        :type osm_file_format: str
        :param data_dir: directory where the data file (or files) is (or are) stored,
            defaults to ``None``; when ``data_dir=None``, it refers to the method
            :meth:`~pydriosm.downloader.GeofabrikDownloader.cdd`
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
            >>> from pyhelpers.dirs import delete_dir
            >>> import os

            >>> # Specify a download directory
            >>> dwnld_dir = "tests\\osm_data"

            >>> gfd = GeofabrikDownloader(download_dir=dwnld_dir)

            >>> subrgn_name = 'london'
            >>> file_format = ".pbf"

            >>> # Download the PBF data of London (to the default directory)
            >>> gfd.download_osm_data(subrgn_name, file_format, verbose=True)
            To download .osm.pbf data of the following geographic (sub)region(s):
                Greater London
            ? [No]|Yes: yes
            Downloading "greater-london-latest.osm.pbf"
                to "tests\\osm_data\\europe\\great-britain\\england\\greater-london\\"...Done.

            >>> # Check whether the PBF data file exists; `ret_file_path` is by default `False`
            >>> pbf_exists = gfd.file_exists(subrgn_name, file_format)
            >>> pbf_exists  # If the data file exists at the default directory
            True

            >>> # Set `ret_file_path=True`
            >>> path_to_pbf = gfd.file_exists(subrgn_name, file_format, ret_file_path=True)
            >>> os.path.relpath(path_to_pbf)  # If the data file exists at the default directory
            'tests\\osm_data\\europe\\great-britain\\england\\greater-london\\greater-londo...'

            >>> # Remove the download directory:
            >>> delete_dir(dwnld_dir, verbose=True)
            To delete the directory "tests\\osm_data\\" (Not empty)
            ? [No]|Yes: yes
            Deleting "tests\\osm_data\\" ... Done.

            >>> # Check if the data file still exists at the specified download directory
            >>> gfd.file_exists(subrgn_name, file_format)
            False
        """

        file_exists = super().file_exists(
            subregion_name=subregion_name, osm_file_format=osm_file_format, data_dir=data_dir,
            update=update, verbose=verbose, ret_file_path=ret_file_path)

        return file_exists

    def download_osm_data(self, subregion_names, osm_file_format, download_dir=None, update=False,
                          confirmation_required=True, deep_retry=False, interval=None,
                          verify_download_dir=True, verbose=False, ret_download_path=False,
                          **kwargs):
        """
        Download OSM data (in a specific format) of one (or multiple) geographic (sub)region(s).

        :param subregion_names: name of a geographic (sub)region
            (or names of multiple geographic (sub)regions) available on Geofabrik free download server
        :type subregion_names: str or list
        :param osm_file_format: file format/extension of the OSM data available on the download server
        :type osm_file_format: str
        :param download_dir: directory for saving the downloaded file(s), defaults to ``None``;
            when ``download_dir=None``, it refers to the method
            :meth:`~pydriosm.downloader.GeofabrikDownloader.cdd`
        :type download_dir: str or None
        :param update: whether to update the data if it already exists, defaults to ``False``
        :type update: bool
        :param confirmation_required: whether asking for confirmation to proceed, defaults to ``True``
        :type confirmation_required: bool
        :param deep_retry: whether to further check availability of sub-subregions data,
            defaults to ``False``
        :type deep_retry: bool
        :param interval: interval (in sec) between downloading two subregions, defaults to ``None``
        :type interval: int or float or None
        :param verify_download_dir: whether to verify the pathname of the current download directory,
            defaults to ``True``
        :type verify_download_dir: bool
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
            >>> from pyhelpers.dirs import delete_dir
            >>> import os

        ***Example 1***::

            >>> gfd = GeofabrikDownloader()

            >>> # Download PBF data file of 'Greater London' and 'Rutland'
            >>> subrgn_names = ['london', 'rutland']  # Case-insensitive
            >>> file_format = ".pbf"

            >>> gfd.download_osm_data(subrgn_names, file_format, verbose=True)
            To download .osm.pbf data of the following geographic (sub)region(s):
                Greater London
                Rutland
            ? [No]|Yes: yes
            Downloading "greater-london-latest.osm.pbf"
                to "osm_data\\geofabrik\\europe\\great-britain\\england\\greater-london\\" ... Done.
            Downloading "rutland-latest.osm.pbf"
                to "osm_data\\geofabrik\\europe\\great-britain\\england\\rutland\\" ... Done.

            >>> len(gfd.data_paths)
            2
            >>> for fp in gfd.data_paths: print(os.path.basename(fp))
            greater-london-latest.osm.pbf
            rutland-latest.osm.pbf

            >>> # Since `download_dir` was not specified when instantiating the class,
            >>> #   the data is now in the default download directory
            >>> os.path.relpath(gfd.download_dir)
            'osm_data\\geofabrik'
            >>> dwnld_dir = os.path.dirname(gfd.download_dir)

            >>> # Download shapefiles of West Midlands (to a given directory "tests\\osm_data")
            >>> region_name = 'west midlands'  # Case-insensitive
            >>> file_format = ".shp"
            >>> new_dwnld_dir = "tests\\osm_data"

            >>> gfd.download_osm_data(region_name, file_format, new_dwnld_dir, verbose=True)
            To download .shp.zip data of the following geographic (sub)region(s):
                West Midlands
            ? [No]|Yes: yes
            Downloading "west-midlands-latest-free.shp.zip"
                to "tests\\osm_data\\west-midlands\\" ... Done.
            >>> len(gfd.data_paths)
            3
            >>> os.path.relpath(gfd.data_paths[-1])
            'tests\\osm_data\\west-midlands\\west-midlands-latest-free.shp.zip'

            >>> # Now the `.download_dir` variable has changed to the given one
            >>> os.path.relpath(gfd.download_dir) == new_dwnld_dir
            True
            >>> # while the `.cdd()` remains the default one
            >>> os.path.relpath(gfd.cdd())
            'osm_data\\geofabrik'

            >>> # Delete the above downloaded directories
            >>> delete_dir([dwnld_dir, new_dwnld_dir], verbose=True)
            To delete the following directories:
                "osm_data\\" (Not empty)
                "tests\\osm_data\\" (Not empty)
            ? [No]|Yes: yes
            Deleting "osm_data\\" ... Done.
            Deleting "tests\\osm_data\\" ... Done.

        ***Example 2***::

            >>> # Create a new instance with a pre-specified download directory
            >>> gfd = GeofabrikDownloader(download_dir="tests\\osm_data")

            >>> os.path.relpath(gfd.download_dir)
            'tests\\osm_data'

            >>> # Download shapefiles of Great Britain (to the directory specified by instantiation)
            >>> # (Note that .shp.zip data is not available for "Great Britain" for free download.)
            >>> region_name = 'Great Britain'  # Case-insensitive
            >>> file_format = ".shp"

            >>> # By default, `deep_retry=False`
            >>> gfd.download_osm_data(region_name, osm_file_format=file_format, verbose=True)
            To download .shp.zip data of the following geographic (sub)region(s):
                Great Britain
            ? [No]|Yes: yes
            No .shp.zip data is found for "Great Britain".
            Try to download the data of its subregions instead
            ? [No]|Yes: yes
            Downloading "england-latest-free.shp.zip"
                to "tests\\osm_data\\europe\\great-britain\\great-britain-shp-zip\\" ... Done.
            Downloading "scotland-latest-free.shp.zip"
                to "tests\\osm_data\\europe\\great-britain\\great-britain-shp-zip\\" ... Done.
            Downloading "wales-latest-free.shp.zip"
                to "tests\\osm_data\\europe\\great-britain\\great-britain-shp-zip\\" ... Done.

            >>> len(gfd.data_paths)
            3

            >>> # Now set `deep_retry=True`
            >>> gfd.download_osm_data(region_name, file_format, verbose=True, deep_retry=True)
            To download .shp.zip data of the following geographic (sub)region(s):
                Great Britain
            ? [No]|Yes: yes
            No .shp.zip data is found for "Great Britain".
            Try to download the data of its subregions instead
            ? [No]|Yes: yes
            "scotland-latest-free.shp.zip" is already available at "tests\\osm_data\\europ...".
            "wales-latest-free.shp.zip" is already available at "tests\\osm_data\\europe\\...".
            Downloading "bedfordshire-latest-free.shp.zip"
                to "tests\\osm_data\\europe\\great-britain\\great-britain-shp-zip\\" ... Done.
            ...     ...
            Downloading "west-yorkshire-latest-free.shp.zip"
                to "tests\\osm_data\\europe\\great-britain\\great-britain-shp-zip\\" ... Done.
            Downloading "wiltshire-latest-free.shp.zip"
                to "tests\\osm_data\\europe\\great-britain\\great-britain-shp-zip\\" ... Done.
            Downloading "worcestershire-latest-free.shp.zip"
                to "tests\\osm_data\\europe\\great-britain\\great-britain-shp-zip\\" ... Done.

            >>> # Check the file paths
            >>> len(gfd.data_paths)
            50
            >>> # Check the current default `download_dir`
            >>> os.path.relpath(gfd.download_dir)
            'tests\\osm_data'
            >>> os.path.relpath(os.path.commonpath(gfd.data_paths))
            'tests\\osm_data\\europe\\great-britain\\great-britain-shp-zip'

            >>> # Delete all the downloaded files
            >>> delete_dir(gfd.download_dir, verbose=True)
            To delete the directory "tests\\osm_data\\" (Not empty)
            ? [No]|Yes: yes
            Deleting "tests\\osm_data\\" ... Done.
        """

        subrgn_names_, file_fmt_, cfm_req, action_, dwnld_list_, existing_file_pathnames = \
            self.file_exists_and_more(
                subregion_names=subregion_names, osm_file_format=osm_file_format,
                data_dir=download_dir, update=update, confirmation_required=confirmation_required,
                verbose=verbose)

        cfm_msg = "To {} {} data of the following geographic (sub)region(s):" \
                  "\n\t{}\n?".format(action_, file_fmt_, "\n\t".join(dwnld_list_))

        if confirmed(cfm_msg, confirmation_required=cfm_req and confirmation_required):

            download_paths = []

            for subrgn_name_ in subrgn_names_:
                # subregion_name_, download_url = self.get_subregion_download_url(
                #     subregion_name=subrgn_name_, osm_file_format=file_fmt_)
                subregion_name_, _, download_url, file_pathname = self.get_valid_download_info(
                    subregion_name=subrgn_name_, osm_file_format=file_fmt_, download_dir=download_dir)

                if download_url is None:
                    if verbose:
                        print(f"No {file_fmt_} data is found for \"{subregion_name_}\".")

                    cfm_msg_ = "Try to download the data of its subregions instead\n?"
                    if confirmed(prompt=cfm_msg_, confirmation_required=confirmation_required):
                        sub_subregions = self.get_subregions(subregion_name_, deep=deep_retry)

                        if sub_subregions == [subregion_name_]:
                            print(f"{file_fmt_} data is unavailable for {subregion_name_}.")

                        else:
                            dwnld_dir_ = self.specify_sub_download_dir(
                                subregion_name=subregion_name_, osm_file_format=file_fmt_,
                                download_dir=download_dir)

                            download_paths_ = self.download_osm_data(
                                subregion_names=sub_subregions, osm_file_format=file_fmt_,
                                download_dir=dwnld_dir_, update=update, confirmation_required=False,
                                verify_download_dir=False, verbose=verbose,
                                ret_download_path=ret_download_path)

                            if isinstance(download_paths_, list):
                                download_paths += download_paths_

                else:
                    if not os.path.isfile(file_pathname) or update:
                        self._download_osm_data(
                            download_url=download_url, file_pathname=file_pathname, verbose=verbose,
                            verify_download_dir=False, **kwargs)

                    if os.path.isfile(file_pathname):
                        download_paths.append(file_pathname)

                if isinstance(interval, (int, float)):
                    time.sleep(interval)

            self.verify_download_dir(download_dir=download_dir, verify_download_dir=verify_download_dir)

        else:
            print("Cancelled.")

            download_paths = existing_file_pathnames

        self.data_paths = list(collections.OrderedDict.fromkeys(self.data_paths + download_paths))

        if ret_download_path:
            return download_paths

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
            :meth:`~pydriosm.downloader.GeofabrikDownloader.cdd`
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
            >>> from pyhelpers.dirs import cd, delete_dir
            >>> import os

            >>> gfd = GeofabrikDownloader()

            >>> subrgn_names = ['rutland', 'west yorkshire']
            >>> file_format = ".pbf"
            >>> dwnld_dir = "tests\\osm_data"

            >>> gfd.download_subregion_data(subrgn_names, file_format, dwnld_dir, verbose=True)
            To download .osm.pbf data of the following geographic (sub)region(s):
                Rutland
                West Yorkshire
            ? [No]|Yes: yes
            Downloading "rutland-latest.osm.pbf"
                to "tests\\osm_data\\rutland\\" ... Done.
            Downloading "west-yorkshire-latest.osm.pbf"
                to "tests\\osm_data\\west-yorkshire\\" ... Done.

            >>> len(gfd.data_paths)
            2
            >>> for fp in gfd.data_paths: print(os.path.relpath(fp))
            tests\\osm_data\\rutland\\rutland-latest.osm.pbf
            tests\\osm_data\\west-yorkshire\\west-yorkshire-latest.osm.pbf

            >>> # Delete "tests\\osm_data\\rutland-latest.osm.pbf"
            >>> rutland_dir = os.path.dirname(gfd.data_paths[0])
            >>> delete_dir(rutland_dir, confirmation_required=False, verbose=True)
            Deleting "tests\\osm_data\\rutland\\" ... Done.

            >>> # Try to download data given another list which also includes 'West Yorkshire'
            >>> subrgn_names = ['west midlands', 'west yorkshire']

            >>> # Set `ret_download_path=True`
            >>> dwnld_file_pathnames = gfd.download_subregion_data(
            ...     subrgn_names, file_format, dwnld_dir, verbose=True, ret_download_path=True)
            "west-midlands-latest.osm.pbf" is already available
                at "tests\\osm_data\\west-midlands\\".
            To download .osm.pbf data of the following geographic (sub)region(s):
                West Midlands
            ? [No]|Yes: yes
            Downloading "west-midlands-latest.osm.pbf"
                to "tests\\osm_data\\west-midlands\\" ... Done.

            >>> len(gfd.data_paths)  # The pathname of the newly downloaded file is added
            3
            >>> len(dwnld_file_pathnames)
            2
            >>> for fp in dwnld_file_pathnames: print(os.path.relpath(fp))
            tests\\osm_data\\west-midlands\\west-midlands-latest.osm.pbf
            tests\\osm_data\\west-yorkshire\\west-yorkshire-latest.osm.pbf

            >>> # Update (or re-download) the existing data file by setting `update=True`
            >>> gfd.download_subregion_data(
            ...     subrgn_names, file_format, download_dir=dwnld_dir, update=True, verbose=True)
            "west-midlands-latest.osm.pbf" is already available
                at "tests\\osm_data\\west-midlands\\".
            "west-yorkshire-latest.osm.pbf" is already available
                at "tests\\osm_data\\west-yorkshire\\".
            To update the .osm.pbf data of the following geographic (sub)region(s):
                West Midlands
                West Yorkshire
            ? [No]|Yes: yes
            Updating "west-midlands-latest.osm.pbf"
                at "tests\\osm_data\\west-midlands\\" ... Done.
            Updating "west-yorkshire-latest.osm.pbf"
                at "tests\\osm_data\\west-yorkshire\\" ... Done.

            >>> # To download the PBF data of all available subregions of England
            >>> subrgn_name = 'England'

            >>> dwnld_file_pathnames = gfd.download_subregion_data(
            ...     subrgn_name, file_format, download_dir=dwnld_dir, update=True, verbose=True,
            ...     ret_download_path=True)
            "west-midlands-latest.osm.pbf" is already available
                at "tests\\osm_data\\west-midlands\\".
            "west-yorkshire-latest.osm.pbf" is already available
                at "tests\\osm_data\\west-yorkshire\\".
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
            Downloading "bedfordshire-latest.osm.pbf"
                to "tests\\osm_data\\bedfordshire\\" ... Done.
            Downloading "berkshire-latest.osm.pbf"
                to "tests\\osm_data\\berkshire\\" ... Done.
            Downloading "bristol-latest.osm.pbf"
                to "tests\\osm_data\\bristol\\" ... Done.
            ...
                ...
            Updating "west-midlands-latest.osm.pbf"
                at "tests\\osm_data\\west-midlands\\" ... Done.
            ...
                ...
            Updating "west-yorkshire-latest.osm.pbf"
                at "tests\\osm_data\\west-yorkshire\\" ... Done.
            Downloading "wiltshire-latest.osm.pbf"
                to "tests\\osm_data\\wiltshire\\" ... Done.
            Downloading "worcestershire-latest.osm.pbf"
                to "tests\\osm_data\\worcestershire\\" ... Done.

            >>> len(dwnld_file_pathnames)
            47
            >>> os.path.commonpath(dwnld_file_pathnames) == gfd.download_dir
            True

            >>> # Delete the download directory and the downloaded files
            >>> delete_dir(gfd.download_dir, verbose=True)
            To delete the directory "tests\\osm_data\\" (Not empty)
            ? [No]|Yes: yes
            Deleting "tests\\osm_data\\" ... Done.
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

    #: Name of the free downloader server.
    NAME = 'BBBike'
    #: Full name of the data resource.
    LONG_NAME = 'BBBike exports of OpenStreetMap data'
    #: URL of the homepage to the free download server.
    URL = 'https://download.bbbike.org/osm/bbbike/'
    #: URL of a list of cities that are available on the free download server.
    CITIES_URL = 'https://raw.githubusercontent.com/wosch/bbbike-world/world/etc/cities.txt'
    #: URL of coordinates of all the available cities.
    CITIES_COORDS_URL = 'https://raw.githubusercontent.com/wosch/bbbike-world/world/etc/cities.csv'
    #: Default download directory.
    DEFAULT_DOWNLOAD_DIR = "osm_data\\bbbike"
    #: Valid file formats.
    FILE_FORMATS = {
        '.csv.xz',
        '.garmin-onroad-latin1.zip',
        '.garmin-onroad.zip',
        '.garmin-opentopo.zip',
        '.garmin-osm.zip',
        '.geojson.xz',
        '.gz',
        '.mapsforge-osm.zip',
        '.pbf',
        '.shp.zip',
        '.svg-osm.zip',
    }

    def __init__(self, download_dir=None):
        """
        :param download_dir: (a path or a name of) a directory for saving downloaded data files;
            if ``download_dir=None`` (default), the downloaded data files are saved into a folder
            named ``'osm_data'`` under the current working directory
        :type download_dir: str or None

        :ivar set valid_subregion_names: names of (sub)regions available on
            BBBike free download server
        :ivar set valid_file_formats: filename extensions of the data files available on
            BBBike free download server
        :ivar pandas.DataFrame subregion_index: index of download pages for all available (sub)regions
        :ivar pandas.DataFrame catalogue: a catalogue (index) of all available BBBike downloads
        :ivar str or None download_dir: name or pathname of a directory for saving downloaded data files
            (in accordance with the parameter ``download_dir``)
        :ivar list data_pathnames: list of pathnames of all downloaded data files

        **Examples**::

            >>> from pydriosm.downloader import BBBikeDownloader
            >>> import os

            >>> bbd = BBBikeDownloader()

            >>> bbd.NAME
            'BBBike'

            >>> bbd.LONG_NAME
            'BBBike exports of OpenStreetMap data'

            >>> bbd.URL
            'https://download.bbbike.org/osm/bbbike/'

            >>> os.path.relpath(bbd.download_dir)
            'osm_data\\bbbike'

            >>> bbd = BBBikeDownloader(download_dir="tests\\osm_data")
            >>> os.path.relpath(bbd.download_dir)
            'tests\\osm_data'
        """

        super().__init__(download_dir=download_dir)

        self.valid_subregion_names = self.get_names_of_cities()
        self.subregion_coordinates = self.get_coordinates_of_cities()
        self.subregion_index = self.get_subregion_index()
        self.catalogue = self.get_catalogue()
        # self.valid_file_formats = set(self.catalogue['FileFormat'])

    @classmethod
    def _names_of_cities(cls, path_to_pickle, verbose):
        """
        Get the names of all the available cities.

        :param path_to_pickle: pathname of the prepacked pickle file, defaults to ``None``
        :type path_to_pickle: str or os.PathLike[str] or None
        :param verbose: whether to print relevant information in console, defaults to ``False``
        :type verbose: bool or int
        :return: list of names of cities available on BBBike free download server
        :rtype: list

        .. seealso::

            - Examples for the method
              :meth:`~pydriosm.downloader.BBBikeDownloader.get_names_of_cities`.
        """

        names_of_cities_ = pd.read_csv(cls.CITIES_URL, header=None)
        names_of_cities = list(names_of_cities_.values.flatten())

        if verbose:
            print("Done.")

        save_pickle(names_of_cities, path_to_pickle=path_to_pickle, verbose=verbose)

        return names_of_cities

    @classmethod
    def get_names_of_cities(cls, update=False, confirmation_required=True, verbose=False):
        """
        Get the names of all the available cities.

        This can be an alternative to the method
        :meth:`~pydriosm.downloader.BBBikeDownloader.get_valid_subregion_names`.

        :param update: whether to (check on and) update the prepacked data, defaults to ``False``
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
            >>> bbbike_cities = bbd.get_names_of_cities()
            >>> type(bbbike_cities)
            list
        """

        data_name = f'{cls.NAME} cities'

        cities_names = cls.get_prepacked_data(
            cls._names_of_cities, data_name=data_name, update=update,
            confirmation_required=confirmation_required, verbose=verbose)

        return cities_names

    @classmethod
    def _coordinates_of_cities(cls, path_to_pickle, verbose):
        """
        Get location information of all cities available on the download server.

        :param path_to_pickle: pathname of the prepacked pickle file, defaults to ``None``
        :type path_to_pickle: str or os.PathLike[str] or None
        :param verbose: whether to print relevant information in console, defaults to ``False``
        :type verbose: bool or int
        :return: location information of BBBike cities, i.e. geographic (sub)regions
        :rtype: pandas.DataFrame

        .. seealso::

            - Examples for the method
              :meth:`~pydriosm.downloader.BBBikeDownloader.get_coordinates_of_cities`.
        """

        with requests.get(url=cls.CITIES_COORDS_URL, headers=fake_requests_headers()) as response:
            csv_data_temp = response.content.decode('utf-8')
            csv_data_ = list(csv.reader(csv_data_temp.splitlines(), delimiter=':'))

        csv_data = [
            [x.strip().strip('\u200e').replace('#', '') for x in row]
            for row in csv_data_[5:-1]]
        column_names = [x.replace('#', '').strip().capitalize() for x in csv_data_[0]]
        cities_coords_ = pd.DataFrame(csv_data, columns=column_names)

        coordinates = cities_coords_.Coord.str.split(' ').apply(pd.Series)
        del cities_coords_['Coord']

        coords_cols = ['ll_longitude', 'll_latitude', 'ur_longitude', 'ur_latitude']
        coordinates.columns = coords_cols

        cities_coords = pd.concat([cities_coords_, coordinates], axis=1).dropna(subset=coords_cols)

        cities_coords['Real name'] = cities_coords['Real name'].str.split(r'[!,]').map(
            lambda x: None if x[0] == '' else dict(zip(x[::2], x[1::2])))

        # Rename columns
        cities_coords.columns = [
            x.replace(' ', '_').replace('/', '_or_').replace('?', '').lower()
            for x in cities_coords.columns]

        if verbose:
            print("Done.")

        save_pickle(cities_coords, path_to_pickle, verbose=verbose)

        return cities_coords

    @classmethod
    def get_coordinates_of_cities(cls, update=False, confirmation_required=True, verbose=False):
        """
        Get location information of all cities available on the download server.

        :param update: whether to (check on and) update the prepacked data, defaults to ``False``
        :type update: bool
        :param confirmation_required: whether asking for confirmation to proceed, defaults to ``True``
        :type confirmation_required: bool
        :param verbose: whether to print relevant information in console, defaults to ``False``
        :type verbose: bool or int
        :return: location information of BBBike cities, i.e. geographic (sub)regions
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
            ['city',
             'real_name',
             'pref._language',
             'local_language',
             'country',
             'area_or_continent',
             'population',
             'step',
             'other_cities',
             'll_longitude',
             'll_latitude',
             'ur_longitude',
             'ur_latitude']
        """

        data_name = f'{cls.NAME} cities coordinates'

        cities_coords = cls.get_prepacked_data(
            cls._coordinates_of_cities, data_name=data_name, update=update,
            confirmation_required=confirmation_required, verbose=verbose)

        return cities_coords

    @classmethod
    def _subregion_index(cls, path_to_pickle, verbose):
        """
        Get a catalogue for geographic (sub)regions.

        :param path_to_pickle: pathname of the prepacked pickle file, defaults to ``None``
        :type path_to_pickle: str or os.PathLike[str] or None
        :param verbose: whether to print relevant information in console, defaults to ``False``
        :type verbose: bool or int
        :return: catalogue for subregions of BBBike data
        :rtype: pandas.DataFrame

        .. seealso::

            - Examples for the method
              :meth:`~pydriosm.downloader.BBBikeDownloader.get_subregion_index`.
        """

        bs4_ = importlib.import_module('bs4')

        with requests.get(url=cls.URL, headers=fake_requests_headers()) as response:
            soup = bs4_.BeautifulSoup(markup=response.content, features='html.parser')

        thead, tbody = soup.find(name='thead'), soup.find(name='tbody')

        ths = [th.text.strip().lower().replace(' ', '_') for th in thead.find_all(name='th')]
        trs = tbody.find_all(name='tr')
        dat = parse_tr(trs=trs, ths=ths, as_dataframe=True).drop(index=0)
        dat.index = range(len(dat))

        for col in ['size', 'type']:
            if dat[col].nunique() == 1:
                del dat[col]

        subregion_index = dat.copy()

        with warnings.catch_warnings():
            warnings.filterwarnings("ignore", category=FutureWarning)
            warnings.filterwarnings("ignore", category=DeprecationWarning)

            subregion_index['name'] = subregion_index['name'].map(lambda x: x.rstrip('/'))
            subregion_index['last_modified'] = pd.to_datetime(subregion_index['last_modified'])
            subregion_index['url'] = [
                urllib.parse.urljoin(cls.URL, x.get('href')) for x in soup.find_all('a')[1:]]

        if verbose:
            print("Done.")

        save_pickle(subregion_index, path_to_pickle, verbose=verbose)

        return subregion_index

    @classmethod
    def get_subregion_index(cls, update=False, confirmation_required=True, verbose=False):
        """
        Get a catalogue for geographic (sub)regions.

        :param update: whether to (check on and) update the prepacked data, defaults to ``False``
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
            >>> subrgn_idx = bbd.get_subregion_index()

            >>> type(subrgn_idx)
            pandas.core.frame.DataFrame
            >>> subrgn_idx.columns.to_list()
            ['name', 'last_modified', 'url']
        """

        data_name = f'{cls.NAME} index of subregions'

        subregion_index = cls.get_prepacked_data(
            cls._subregion_index, data_name=data_name, update=update,
            confirmation_required=confirmation_required, verbose=verbose)

        return subregion_index

    @classmethod
    def _valid_subregion_names(cls, path_to_pickle, verbose):
        """
        Get a list of names of all geographic (sub)regions.

        :param path_to_pickle: pathname of the prepacked pickle file, defaults to ``None``
        :type path_to_pickle: str or os.PathLike[str] or None
        :param verbose: whether to print relevant information in console, defaults to ``False``
        :type verbose: bool or int
        :return: a list of geographic (sub)region names available on BBBike free download server
        :rtype: list
        """
        # subregion_names = list(self.get_names_of_cities())

        subregion_catalogue = cls.get_subregion_index(confirmation_required=False, verbose=False)
        subregion_names = subregion_catalogue['name'].to_list()

        if verbose:
            print("Done.")

        save_pickle(subregion_names, path_to_pickle=path_to_pickle, verbose=verbose)

        return subregion_names

    @classmethod
    def get_valid_subregion_names(cls, update=False, confirmation_required=True, verbose=False):
        """
        Get a list of names of all geographic (sub)regions.

        This can be an alternative to the method
        :meth:`~pydriosm.downloader.BBBikeDownloader.get_names_of_cities`.

        :param update: whether to (check on and) update the prepacked data, defaults to ``False``
        :type update: bool
        :param confirmation_required: whether asking for confirmation to proceed, defaults to ``True``
        :type confirmation_required: bool
        :param verbose: whether to print relevant information in console, defaults to ``False``
        :type verbose: bool or int
        :return: a list of geographic (sub)region names available on BBBike free download server
        :rtype: list or None

        **Examples**::

            >>> from pydriosm.downloader import BBBikeDownloader

            >>> bbd = BBBikeDownloader()

            >>> # A list of names of all BBBike geographic (sub)regions
            >>> subrgn_names = bbd.get_valid_subregion_names()

            >>> type(subrgn_names)
            list
        """

        data_name = f'{cls.NAME} subregion names'

        if update:
            args = {'update': update, 'confirmation_required': False, 'verbose': False}
            _ = cls.get_subregion_index(**args)
            _ = cls.get_names_of_cities(**args)

        subregion_names = cls.get_prepacked_data(
            cls._valid_subregion_names, data_name=data_name, update=update,
            confirmation_required=confirmation_required, verbose=verbose)

        return subregion_names

    def validate_subregion_name(self, subregion_name, **kwargs):
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

            >>> subrgn_name = 'birmingham'

            >>> valid_name = bbd.validate_subregion_name(subregion_name=subrgn_name)
            >>> valid_name
            'Birmingham'
        """

        subregion_name_ = super().validate_subregion_name(
            subregion_name=subregion_name, valid_subregion_names=self.valid_subregion_names,
            **kwargs)

        return subregion_name_

    @classmethod
    def _parse_download_link_a_tags(cls, x, url):
        """
        Parse an <a> tag of a download link.

        :param x: <a> tag of a download link
        :type x: bs4.element.Tag
        :param url: URL of the web page of a subregion
        :type url: str
        :return: data contained in the <a> tag
        :rtype: list
        """

        x_href = x.get('href')  # URL
        filename, download_url = os.path.basename(x_href), urllib.parse.urljoin(url, x_href)

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

            >>> subrgn_name = 'birmingham'

            >>> # A download catalogue for Leeds
            >>> bham_dwnld_cat = bbd.get_subregion_catalogue(subrgn_name, verbose=True)
            To compile data of a download catalogue for "Birmingham"
            ? [No]|Yes: yes
            Compiling the data ... Done.
            >>> type(bham_dwnld_cat)
            pandas.core.frame.DataFrame
            >>> bham_dwnld_cat.columns.tolist()
            ['filename', 'url', 'data_type', 'size', 'last_update']
        """

        subregion_name_ = self.validate_subregion_name(subregion_name)

        dat_name = f"a download catalogue for \"{subregion_name_}\""

        if confirmed(f"To compile data of {dat_name}\n?", confirmation_required=confirmation_required):
            if verbose:
                if confirmation_required:
                    status_msg = "Compiling the data"
                else:
                    if verbose == 2:
                        status_msg = f"\t{subregion_name_}"
                    else:
                        status_msg = f"Compiling the data of {dat_name}"
                print(status_msg, end=" ... ")

            try:
                bs4_ = importlib.import_module('bs4')

                url = urllib.parse.urljoin(self.URL, subregion_name_ + '/')

                with requests.get(url=url, headers=fake_requests_headers()) as response:
                    soup = bs4_.BeautifulSoup(markup=response.content, features='html.parser')

                download_link_a_tags = soup.find_all('a', attrs={'class': ['download_link', 'small']})

                download_catalogue = pd.DataFrame(
                    self._parse_download_link_a_tags(x=x, url=url) for x in download_link_a_tags)
                download_catalogue.columns = ['filename', 'url', 'data_type', 'size', 'last_update']

                # file_path = cd_dat_bbbike(
                #     subregion_name_, subregion_name_ + "-download-catalogue.pickle")
                # save_pickle(download_catalogue, file_path, verbose=verbose)
                if verbose:
                    print("Done.")

            except Exception as e:
                print(f"Failed. {e}")
                download_catalogue = None

            return download_catalogue

    def _catalogue(self, path_to_pickle, verbose):
        """
        Get a dict-type index of available formats, data types and a download catalogue.

        :param path_to_pickle: pathname of the prepacked pickle file, defaults to ``None``
        :type path_to_pickle: str or os.PathLike[str] or None
        :param verbose: whether to print relevant information in console, defaults to ``False``
        :type verbose: bool or int
        :return: a list of available formats, a list of available data types and
            a dictionary of download catalogue
        :rtype: dict
        """

        subregion_names = self.get_valid_subregion_names()

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
        subrgn_catalog = download_catalogue[0]

        # Available file formats
        file_fmt = [re.sub('{}|CHECKSUM'.format(subrgn_name), '', f) for f in subrgn_catalog['filename']]

        # Available data types
        data_typ = subrgn_catalog['data_type'].to_list()

        download_index = {
            'FileFormat': [x.replace(".osm", "", 1) for x in file_fmt[:-2]],
            'DataType': data_typ[:-2],
            'Catalogue': dict(zip(subregion_names, download_catalogue)),
        }

        if verbose is True:
            print("Done.")
        elif verbose == 2:
            print("All done.")

        save_pickle(download_index, path_to_pickle=path_to_pickle, verbose=verbose)

        return download_index

    def get_catalogue(self, update=False, confirmation_required=True, verbose=False):
        """
        Get a dict-type index of available formats, data types and a download catalogue.

        :param update: whether to (check on and) update the prepacked data, defaults to ``False``
        :type update: bool
        :param confirmation_required: whether asking for confirmation to proceed, defaults to ``True``
        :type confirmation_required: bool
        :param verbose: whether to print relevant information in console, defaults to ``False``
        :type verbose: bool or int
        :return: a list of available formats, a list of available data types and
            a dictionary of download catalogue
        :rtype: dict or None

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

            >>> bham_catalogue = catalogue['Birmingham']
            >>> type(bham_catalogue)
            pandas.core.frame.DataFrame
        """

        data_name = f'{self.NAME} downloads catalogue'

        download_index = self.get_prepacked_data(
            self._catalogue, data_name=data_name, update=update,
            confirmation_required=confirmation_required, verbose=verbose, act_msg_note="",
            act_msg_end=": \n" if verbose == 2 else " ... ")

        return download_index

    def validate_file_format(self, osm_file_format, **kwargs):
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

            >>> valid_file_format = bbd.validate_file_format(osm_file_format='PBF')
            >>> valid_file_format
            '.pbf'

            >>> valid_file_format = bbd.validate_file_format(osm_file_format='.osm.pbf')
            >>> valid_file_format
            '.pbf'
        """

        osm_file_format_ = super().validate_file_format(
            osm_file_format=osm_file_format, valid_file_formats=self.FILE_FORMATS,
            **kwargs)

        return osm_file_format_

    def get_subregion_download_url(self, subregion_name, osm_file_format, **kwargs):
        """
        Get a valid URL for downloading OSM data of a specific file format
        for a geographic (sub)region.

        :param subregion_name: name of a (sub)region available on BBBike free download server
        :type subregion_name: str
        :param osm_file_format: file format/extension of the OSM data available on the download server
        :type osm_file_format: str
        :return: a valid name of ``subregion_name`` and a download URL for the given ``osm_file_format``
        :rtype: tuple

        **Examples**::

            >>> from pydriosm.downloader import BBBikeDownloader

            >>> bbd = BBBikeDownloader()

            >>> subrgn_name = 'birmingham'
            >>> file_format = "pbf"

            >>> # Get a valid subregion name and its download URL
            >>> subrgn_name_, dwnld_url = bbd.get_subregion_download_url(subrgn_name, file_format)
            >>> subrgn_name_
            'Birmingham'
            >>> dwnld_url
            'https://download.bbbike.org/osm/bbbike/Birmingham/Birmingham.osm.pbf'

            >>> file_format = "csv.xz"
            >>> subrgn_name_, dwnld_url = bbd.get_subregion_download_url(subrgn_name, file_format)

            >>> subrgn_name_
            'Birmingham'
            >>> dwnld_url
            'https://download.bbbike.org/osm/bbbike/Birmingham/Birmingham.osm.csv.xz'
        """

        subregion_name_ = self.validate_subregion_name(subregion_name=subregion_name, **kwargs)
        osm_file_format_ = ".osm" + self.validate_file_format(osm_file_format=osm_file_format)

        sub_dwnld_cat = self.catalogue['Catalogue'][subregion_name_]

        filename = subregion_name_ + osm_file_format_
        download_url = sub_dwnld_cat.loc[sub_dwnld_cat['filename'] == filename, 'url'].values[0]

        return subregion_name_, download_url

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
            when ``download_dir=None``, it refers to the method :meth:`~pydriosm.downloader.BBBike.cdd`
        :type download_dir: str or None
        :param kwargs: [optional] parameters of `pyhelpers.dirs.cd()`_,
            including ``mkdir``(default: ``False``)
        :return: valid subregion name, filename, download url and absolute file path
        :rtype: tuple

        .. _`pyhelpers.dirs.cd()`:
            https://pyhelpers.readthedocs.io/en/latest/_generated/pyhelpers.dirs.cd.html

        **Examples**::

            >>> from pydriosm.downloader import BBBikeDownloader
            >>> import os

            >>> bbd = BBBikeDownloader()

            >>> subrgn_name = 'birmingham'
            >>> file_format = "pbf"

            >>> # valid subregion name, filename, download url and absolute file path
            >>> info = bbd.get_valid_download_info(subrgn_name, file_format)
            >>> valid_subrgn_name, pbf_filename, dwnld_url, pbf_pathname = info

            >>> valid_subrgn_name
            'Birmingham'
            >>> pbf_filename
            'Birmingham.osm.pbf'
            >>> dwnld_url
            'https://download.bbbike.org/osm/bbbike/Birmingham/Birmingham.osm.pbf'
            >>> os.path.relpath(pbf_pathname)
            'osm_data\\bbbike\\birmingham\\Birmingham.osm.pbf'

            >>> # Create a new instance with a given download directory
            >>> bbd = BBBikeDownloader(download_dir="tests\\osm_data")
            >>> _, _, _, pbf_pathname = bbd.get_valid_download_info(subrgn_name, file_format)

            >>> os.path.relpath(pbf_pathname)
            'tests\\osm_data\\birmingham\\Birmingham.osm.pbf'
        """

        subregion_name_, osm_filename, download_url, file_pathname = super().get_valid_download_info(
            subregion_name=subregion_name, osm_file_format=osm_file_format,
            download_dir=download_dir, **kwargs)

        return subregion_name_, osm_filename, download_url, file_pathname

    def file_exists(self, subregion_name, osm_file_format, data_dir=None, update=False, verbose=False,
                    ret_file_path=False):
        """
        Check if a requested data file of a geographic (sub)region already exists locally,
        given its default filename.

        :param subregion_name: name of a (sub)region available on BBBike free download server
        :type subregion_name: str
        :param osm_file_format: file format/extension of the OSM data available on the download server
        :type osm_file_format: str
        :param data_dir: directory where the data file (or files) is (or are) stored,
            defaults to ``None``; when ``data_dir=None``, it refers to the method
            :meth:`~pydriosm.downloader.BBBike.cdd`
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
            >>> from pyhelpers.dirs import delete_dir
            >>> import os

            >>> bbd = BBBikeDownloader()

            >>> subrgn_name = 'birmingham'
            >>> file_format = ".pbf"
            >>> dwnld_dir = "tests\\osm_data"

            >>> # Check whether the PBF data file exists; `ret_file_path` is by default `False`
            >>> pbf_exists = bbd.file_exists(subrgn_name, file_format, dwnld_dir)
            >>> pbf_exists
            False

            >>> # Download the PBF data of Birmingham (to the default directory)
            >>> bbd.download_osm_data(subrgn_name, file_format, dwnld_dir, verbose=True)
            To download .pbf data of the following geographic (sub)region(s):
                Birmingham
            ? [No]|Yes: yes
            Downloading "Birmingham.osm.pbf"
                to "tests\\osm_data\\birmingham\\" ... Done.

            >>> bbd.file_exists(subrgn_name, file_format, dwnld_dir)
            True

            >>> # Set `ret_file_path=True`
            >>> pbf_pathname = bbd.file_exists(subrgn_name, file_format, ret_file_path=True)
            >>> os.path.relpath(pbf_pathname)
            'tests\\osm_data\\birmingham\\Birmingham.osm.pbf'

            >>> os.path.relpath(dwnld_dir) == os.path.relpath(bbd.download_dir)
            True

            >>> # Remove the directory or the PBF file and check again:
            >>> delete_dir(bbd.download_dir, verbose=True)
            To delete the directory "tests\\osm_data\\" (Not empty)
            ? [No]|Yes: yes
            Deleting "tests\\osm_data\\" ... Done.

            >>> # Since the default download directory has been deleted
            >>> bbd.file_exists(subrgn_name, file_format, dwnld_dir)
            False
        """

        file_exists = super().file_exists(
            subregion_name=subregion_name, osm_file_format=osm_file_format, data_dir=data_dir,
            update=update, verbose=verbose, ret_file_path=ret_file_path)

        return file_exists

    def download_subregion_data(self, subregion_name, download_dir=None, update=False,
                                confirmation_required=True, interval=None, verify_download_dir=True,
                                verbose=False, ret_download_path=False, **kwargs):
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
        :type interval: int or float or None
        :param verify_download_dir: whether to verify the pathname of the current download directory,
            defaults to ``True``
        :type verify_download_dir: bool
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
            >>> from pyhelpers.dirs import delete_dir
            >>> import os

            >>> bbd = BBBikeDownloader()

            >>> # Download the BBBike OSM data of Birmingham (to the default download directory)
            >>> subrgn_name = 'birmingham'

            >>> bbd.download_subregion_data(subrgn_name, verbose=True)
            To download all available BBBike OSM data of Birmingham
            ? [No]|Yes: yes
            Downloading:
                Birmingham.osm.pbf ... Done.
                Birmingham.osm.gz ... Done.
                Birmingham.osm.shp.zip ... Done.
                Birmingham.osm.garmin-onroad-latin1.zip ... Done.
                Birmingham.osm.garmin-osm.zip ... Done.
                Birmingham.osm.garmin-ontrail-latin1.zip ... Done.
                Birmingham.osm.geojson.xz ... Done.
                Birmingham.osm.svg-osm.zip ... Done.
                Birmingham.osm.mapsforge-osm.zip ... Done.
                Birmingham.osm.garmin-opentopo-latin1.zip ... Done.
                Birmingham.osm.mbtiles-openmaptiles.zip ... Done.
                Birmingham.osm.csv.xz ... Done.
                Birmingham.poly ... Done.
                CHECKSUM.txt ... Done.
            Check out the downloaded OSM data at "osm_data\\bbbike\\birmingham\\".

            >>> len(bbd.data_paths)
            14
            >>> os.path.relpath(os.path.commonpath(bbd.data_paths))
            'osm_data\\bbbike\\birmingham'
            >>> os.path.relpath(bbd.download_dir)
            'osm_data\\bbbike'
            >>> bham_dwnld_dir = os.path.dirname(bbd.download_dir)

            >>> # Download the BBBike OSM data of Leeds (to a given download directory)
            >>> subrgn_name = 'leeds'
            >>> dwnld_dir = "tests\\osm_data"

            >>> dwnld_paths = bbd.download_subregion_data(
            ...     subrgn_name, download_dir=dwnld_dir, verbose=True, ret_download_path=True)
            To download all available BBBike OSM data of Leeds
            ? [No]|Yes: yes
            Downloading:
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
            Check out the downloaded OSM data at "tests\\osm_data\\leeds\\".

            >>> # Now the variable `.download_dir` has changed to `dwnld_dir`
            >>> leeds_dwnld_dir = bbd.download_dir
            >>> os.path.relpath(leeds_dwnld_dir) == dwnld_dir
            True

            >>> len(dwnld_paths)
            14
            >>> len(bbd.data_paths)  # New pathnames have been added to `.data_paths`
            28
            >>> os.path.relpath(os.path.commonpath(dwnld_paths))
            'tests\\osm_data\\leeds'

            >>> # Delete the download directories
            >>> delete_dir([bham_dwnld_dir, leeds_dwnld_dir], verbose=True)
            To delete the following directories:
                "osm_data\\" (Not empty)
                "tests\\osm_data\\" (Not empty)
            ? [No]|Yes: yes
            Deleting "osm_data\\" ... Done.
            Deleting "tests\\osm_data\\" ... Done.
        """

        subregion_name_ = self.validate_subregion_name(subregion_name)
        subrgn_cat = self.catalogue['Catalogue'][subregion_name_]

        sub_dirname = self.make_subregion_dirname(subregion_name_)

        if download_dir is None:
            data_dir = cd(self.download_dir, sub_dirname, mkdir=True)

        else:
            download_dir_ = validate_dir(path_to_dir=download_dir)

            data_dir = os.path.join(download_dir_, sub_dirname)
            if not os.path.exists(data_dir):
                os.makedirs(data_dir)

            if verify_download_dir and download_dir_ != self.download_dir:
                self.download_dir = download_dir_

        cfm_dat = f"all available BBBike OSM data of {subregion_name_}"

        if confirmed(f"To download {cfm_dat}\n?", confirmation_required=confirmation_required):
            if verbose:
                print("Downloading: ") if confirmation_required else print(f"Downloading {cfm_dat}: ")

            download_paths = []

            for download_url, osm_filename in zip(subrgn_cat['url'], subrgn_cat['filename']):
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

                        if isinstance(interval, (int, float)):
                            # os.path.getsize(path_to_file)/(1024**2)<=5:
                            time.sleep(interval)

                    if os.path.isfile(path_to_file):
                        download_paths.append(path_to_file)

                except Exception as e:
                    print(f"Failed. {e}")

            if verbose and len(download_paths) > 1:
                rel_path = os.path.relpath(os.path.commonpath(download_paths))
                if verbose == 2:
                    print("All done.")

                print("Check out the downloaded OSM data at \"{}\\\".".format(rel_path))

            self.data_paths = list(collections.OrderedDict.fromkeys(self.data_paths + download_paths))

            if ret_download_path:
                return download_paths

        else:
            print("Cancelled.")

    def download_osm_data(self, subregion_names, osm_file_format, download_dir=None, update=False,
                          confirmation_required=True, interval=None, verify_download_dir=True,
                          verbose=False, ret_download_path=False, **kwargs):
        """
        Download OSM data (of a specific file format) of
        one (or multiple) geographic (sub)region(s).

        :param subregion_names: name of a geographic (sub)region
            (or names of multiple geographic (sub)regions) available on BBBike free download server
        :type subregion_names: str or list
        :param osm_file_format: file format/extension of the OSM data available on the download server
        :type osm_file_format: str
        :param download_dir: directory for saving the downloaded file(s), defaults to ``None``;
            when ``download_dir=None``, it refers to the method
            :meth:`~pydriosm.downloader.BBBike.cdd`
        :type download_dir: str or None
        :param update: whether to update the data if it already exists, defaults to ``False``
        :type update: bool
        :param confirmation_required: whether asking for confirmation to proceed, defaults to ``True``
        :type confirmation_required: bool
        :param interval: interval (in second) between downloading two subregions, defaults to ``None``
        :type interval: int or float or None
        :param verify_download_dir: whether to verify the pathname of the current download directory,
            defaults to ``True``
        :type verify_download_dir: bool
        :param verbose: whether to print relevant information in console, defaults to ``False``
        :type verbose: bool or int
        :param ret_download_path: whether to return the path(s) to the downloaded file(s),
            defaults to ``False``
        :type ret_download_path: bool
        :return: the path(s) to the downloaded file(s) when ``ret_download_path`` is ``True``
        :rtype: list or str

        **Examples**::

            >>> from pydriosm.downloader import BBBikeDownloader
            >>> from pyhelpers.dirs import delete_dir
            >>> import os

            >>> bbd = BBBikeDownloader()

            >>> # Download BBBike PBF data of London
            >>> subrgn_name = 'London'
            >>> file_format = "pbf"

            >>> bbd.download_osm_data(subrgn_name, file_format, verbose=True)
            To download .pbf data of the following geographic (sub)region(s):
                London
            ? [No]|Yes: yes
            Downloading "London.osm.pbf"
                to "osm_data\\bbbike\\london\\" ... Done.

            >>> len(bbd.data_paths)
            1
            >>> os.path.relpath(bbd.data_paths[0])
            'osm_data\\bbbike\\london\\London.osm.pbf'

            >>> london_dwnld_dir = os.path.relpath(bbd.download_dir)
            >>> london_dwnld_dir
            'osm_data\\bbbike'

            >>> # Download PBF data of Leeds and Birmingham to a given directory
            >>> subrgn_names = ['leeds', 'birmingham']
            >>> dwnld_dir = "tests\\osm_data"

            >>> dwnld_paths = bbd.download_osm_data(
            ...     subrgn_names, file_format, dwnld_dir, verbose=True, ret_download_path=True)
            To download .pbf data of the following geographic (sub)region(s):
                Leeds
                Birmingham
            ? [No]|Yes: yes
            Downloading "Leeds.osm.pbf"
                to "tests\\osm_data\\leeds\\" ... Done.
            Downloading "Birmingham.osm.pbf"
                to "tests\\osm_data\\birmingham\\" ... Done.
            >>> len(dwnld_paths)
            2
            >>> len(bbd.data_paths)
            3
            >>> os.path.relpath(bbd.download_dir) == os.path.relpath(dwnld_dir)
            True
            >>> os.path.relpath(os.path.commonpath(dwnld_paths))
            'tests\\osm_data'

            >>> # Delete the above download directories
            >>> delete_dir([os.path.dirname(london_dwnld_dir), dwnld_dir], verbose=True)
            To delete the following directories:
                "osm_data\\" (Not empty)
                "tests\\osm_data\\" (Not empty)
            ? [No]|Yes: yes
            Deleting "osm_data\\" ... Done.
            Deleting "tests\\osm_data\\" ... Done.
        """

        (subregion_names_, osm_file_format_, confirmation_required_, update_msg, downloads_list,
         existing_file_paths) = self.file_exists_and_more(
            subregion_names=subregion_names, osm_file_format=osm_file_format,
            data_dir=download_dir, update=update, confirmation_required=confirmation_required,
            verbose=verbose)

        confirmation_required_ = confirmation_required_ and confirmation_required

        dwnld_list_msg = "\n\t".join(downloads_list)
        cfm_msg = f"To {update_msg} {osm_file_format_} data of " \
                  f"the following geographic (sub)region(s):\n\t{dwnld_list_msg}\n?"

        if confirmed(cfm_msg, confirmation_required=confirmation_required_):
            download_paths = []

            for sub_reg_name in subregion_names_:
                # Get essential information for the download
                _, _, download_url, file_pathname = self.get_valid_download_info(
                    subregion_name=sub_reg_name, osm_file_format=osm_file_format_,
                    download_dir=download_dir, mkdir=True)

                if not os.path.isfile(file_pathname) or update:
                    kwargs.update({'verify_download_dir': False})
                    self._download_osm_data(
                        download_url=download_url, file_pathname=file_pathname, verbose=verbose,
                        **kwargs)

                if os.path.isfile(file_pathname):
                    download_paths.append(file_pathname)

                if isinstance(interval, (int, float)):
                    # or os.path.getsize(path_to_file) / (1024 ** 2) <= 5:
                    time.sleep(interval)

            self.verify_download_dir(download_dir=download_dir, verify_download_dir=verify_download_dir)

        else:
            print("Cancelled.")

            download_paths = existing_file_paths

        self.data_paths = list(collections.OrderedDict.fromkeys(self.data_paths + download_paths))

        if ret_download_path:
            return download_paths
