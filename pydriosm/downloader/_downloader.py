"""
Base downloader.
"""

import copy
import os
import re
import string
import time
import urllib.parse

from pyhelpers._cache import _format_err_msg
from pyhelpers.dirs import cd, validate_dir
from pyhelpers.ops import confirmed, download_file_from_url, is_url
from pyhelpers.store import load_pickle
from pyhelpers.text import cosine_similarity_between_texts, find_similar_str

from pydriosm.errors import InvalidFileFormatError, InvalidSubregionNameError
from pydriosm.utils import _cdd, check_relpath


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
        :type download_dir: str | os.PathLike[str] | None

        :ivar str | None download_dir: name or pathname of a directory
            for saving downloaded data files
        :ivar list data_paths: pathnames of all downloaded data files

        **Tests**::

            >>> from pydriosm.downloader._downloader import _Downloader
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
        :type sub_dir: str | os.PathLike[str]
        :param mkdir: whether to create a directory, defaults to ``False``
        :type mkdir: bool
        :param kwargs: [optional] parameters of `pyhelpers.dirs.cd()`_
        :return: an absolute pathname to a directory (or a file)
        :rtype: str | os.PathLike[str]

        .. _`pyhelpers.dirs.cd()`:
            https://pyhelpers.readthedocs.io/en/latest/_generated/pyhelpers.dirs.cd.html

        **Tests**::

            >>> from pydriosm.downloader._downloader import _Downloader
            >>> import os

            >>> os.path.relpath(_Downloader.cdd())
            'osm_data'
        """

        pathname = cd(cls.DEFAULT_DOWNLOAD_DIR, *sub_dir, mkdir=mkdir, **kwargs)

        return pathname

    @classmethod
    def compose_cfm_msg(cls, data_name='<data_name>', file_path="<file_path>", update=False,
                        note=""):
        """
        Compose a short message to be printed for confirmation.

        :param data_name: name of the prepacked data, defaults to ``'<data_name>'``
        :type data_name: str
        :param file_path: pathname of the prepacked data file, defaults to ``"<file_path>"``
        :type file_path: str | os.PathLike[str]
        :param update: whether to (check on and) update the prepacked data, defaults to ``False``
        :type update: bool
        :param note: additional message, defaults to ``""``
        :type note: str
        :return: a short message to be printed for confirmation
        :rtype: str

        **Tests**::

            >>> from pydriosm.downloader._downloader import _Downloader

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
        :type verbose: bool | int
        :param confirmation_required: whether asking for confirmation to proceed,
            defaults to ``True``
        :type confirmation_required: bool
        :param note: additional message, defaults to ``""``
        :type note: str
        :param end: end string after printing the status message, defaults to ``" ... "``
        :type end: str

        **Tests**::

            >>> from pydriosm.downloader._downloader import _Downloader

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
        :type path_to_file: str | os.PathLike[str]
        :param verbose: whether to print relevant information in console, defaults to ``False``
        :type verbose: bool | int
        :param error_message: message of an error detected during execution of a function,
            defaults to ``None``
        :type error_message: Exception | str | None
        :param update: whether to (check on and) update the prepacked data, defaults to ``False``
        :type update: bool

        **Tests**::

            >>> from pydriosm.downloader._downloader import _Downloader

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
                print("Cancelled.")

    @classmethod
    def get_prepacked_data(cls, meth, data_name='<data_name>', update=False,
                           confirmation_required=True, verbose=False, cfm_msg_note="",
                           act_msg_note="", act_msg_end=" ... "):
        """
        Get auxiliary data (that is to be prepacked in the package).

        :param meth: name of a class method for getting (auxiliary) prepacked data
        :type meth: typing.Callable
        :param data_name: name of the prepacked data, defaults to ``'<data_name>'``
        :type data_name: str
        :param update: whether to (check on and) update the prepacked data, defaults to ``False``
        :type update: bool
        :param confirmation_required: whether asking for confirmation to proceed,
            defaults to ``True``
        :type confirmation_required: bool
        :param verbose: whether to print relevant information in console, defaults to ``False``
        :type verbose: bool | int
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

            >>> from pydriosm.downloader._downloader import _Downloader

            >>> _Downloader.get_prepacked_data(callable, confirmation_required=False) is None
            True
        """

        if data_name is None:
            data_name = cls.NAME

        path_to_pickle = _cdd(data_name.replace(" ", "_").lower() + ".pkl")

        if os.path.isfile(path_to_pickle) and not update:
            data = load_pickle(path_to_pickle)

        else:
            data = None

            cfm_msg = cls.compose_cfm_msg(
                data_name=data_name, file_path=path_to_pickle, update=update, note=cfm_msg_note)

            if confirmed(cfm_msg, confirmation_required=confirmation_required):
                cls.print_act_msg(
                    data_name=data_name, verbose=verbose,
                    confirmation_required=confirmation_required, note=act_msg_note, end=act_msg_end)

                try:
                    data = meth(path_to_pickle, verbose)

                except Exception as error_message:
                    cls.print_otw_msg(
                        data_name=data_name, path_to_file=path_to_pickle, verbose=verbose,
                        error_message=error_message, update=update)

            else:
                cls.print_otw_msg(
                    data_name=data_name, path_to_file=path_to_pickle, verbose=verbose,
                    update=update)

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
            https://pyhelpers.readthedocs.io/en/latest/_generated/
            pyhelpers.text.find_similar_str.html

        **Tests**::

            >>> from pydriosm.downloader._downloader import _Downloader

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
            subregion_name_ = find_similar_str(
                x=subrgn_name_, lookup_list=valid_subregion_names, **kwargs)

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

        :param osm_file_format: file format/extension of the data
            available on a free download server
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
            https://pyhelpers.readthedocs.io/en/latest/_generated/
            pyhelpers.text.find_similar_str.html

        **Tests**::

            >>> from pydriosm.downloader._downloader import _Downloader

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
        :rtype: str | os.PathLike[str]

        **Tests**::

            >>> from pydriosm.downloader._downloader import _Downloader

            >>> subrgn_name_ = 'London'
            >>> dwnld_url = 'https://download.bbbike.org/osm/bbbike/London/London.osm.pbf'

            >>> _Downloader.get_default_sub_path(subrgn_name_, dwnld_url)
            '\\london'
        """

        sub_pathname, folder_name = "", "\\" + subregion_name_.lower().replace(" ", "-")

        if cls.NAME == 'Geofabrik':
            sub_pathname = os.path.dirname(
                urllib.parse.urlparse(download_url).path.replace("/", "\\"))

        sub_pathname += folder_name

        return sub_pathname

    @classmethod
    def make_subregion_dirname(cls, subregion_name_):
        """
        Make the name of the directory one level up
        from an OSM data file of a geographic (sub)region.

        :param subregion_name_: validated name of a (sub)region available on a free download server
        :type subregion_name_: str
        :return: name of the directory one level up from a downloaded OSM data file
        :rtype: str

        **Tests**::

            >>> from pydriosm.downloader._downloader import _Downloader

            >>> subrgn_name_ = 'England'
            >>> _Downloader.make_subregion_dirname(subrgn_name_)
            'england'

            >>> subrgn_name_ = 'Greater London'
            >>> _Downloader.make_subregion_dirname(subrgn_name_)
            'greater-london'
        """

        # # Method 1:
        # sub_dirname = '-'.join(
        #     re.findall('[A-Z][^A-Z]*', subregion_name_.replace(' ', ''))).lower()

        # # Method 2:
        # sub_dirname = '-'.join(subregion_name_.split()).lower()

        # Method 3:
        sub_dirname = '-'.join(
            [x.strip(string.punctuation) for x in subregion_name_.split()]).lower()

        return sub_dirname

    @classmethod
    def get_subregion_download_url(cls, subregion_name, osm_file_format, *args, **kwargs):
        """
        Get a download URL of a geographic (sub)region.

        :param subregion_name: name of a (sub)region available on a free download server
        :type subregion_name: str | None
        :param osm_file_format: file format/extension of the OSM data
            available on the download server
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
        :param osm_file_format: file format/extension of the OSM data
            available on the download server
        :type osm_file_format: str
        :param download_dir: directory for saving the downloaded file(s), defaults to ``None``;
            when ``download_dir=None``, it refers to the method
            :meth:`~pydriosm.downloader.BBBike.cdd`
        :type download_dir: str | None
        :param kwargs: [optional] parameters of `pyhelpers.dirs.cd()`_,
            including ``mkdir``(default: ``False``)
        :return: valid subregion name, filename, download url and absolute file path
        :rtype: tuple

        .. _`pyhelpers.dirs.cd()`:
            https://pyhelpers.readthedocs.io/en/latest/_generated/pyhelpers.dirs.cd.html

        **Tests**::

            >>> from pydriosm.downloader._downloader import _Downloader
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

            - Examples for the methods:
              :meth:`GeofabrikDownloader.get_valid_download_info()
              <pydriosm.downloader.GeofabrikDownloader.get_valid_download_info>` and
              :meth:`BBBikeDownloader.get_valid_download_info()
              <pydriosm.downloader.BBBikeDownloader.get_valid_download_info>`.
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

    def file_exists(self, subregion_name, osm_file_format, data_dir=None, update=False,
                    verbose=True, ret_file_path=False):
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
        :type data_dir: str | None
        :param update: whether to (check and) update the data, defaults to ``False``
        :type update: bool
        :param verbose: whether to print relevant information in console, defaults to ``True``
        :type verbose: bool | int
        :param ret_file_path: whether to return the pathname of the data file (if it exists),
            defaults to ``False``
        :type ret_file_path: bool
        :return: whether the requested data file exists; or the path to the data file
        :rtype: bool | str

        **Tests**::

            >>> from pydriosm.downloader._downloader import _Downloader

            >>> d = _Downloader()

            >>> d.file_exists('<subregion_name>', osm_file_format='shp')
            False

            >>> d.file_exists('rutland', osm_file_format='shp', data_dir="tests\\data")


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
                    rel_p = check_relpath(os.path.dirname(path_to_file))
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
        Check if a requested data file already exists and compile information
        for downloading the data.

        :param subregion_names: name(s) of geographic (sub)region(s)
            available on a free download server
        :type subregion_names: str | list
        :param osm_file_format: file format of the OSM data available on the free download server
        :type osm_file_format: str
        :param data_dir: directory where the data file (or files) is (or are) stored,
            defaults to ``None``
        :type data_dir: str | None
        :param update: whether to (check on and) update the data, defaults to ``False``
        :type update: bool
        :param confirmation_required: whether asking for confirmation to proceed,
            defaults to ``True``
        :type confirmation_required: bool
        :param verbose: whether to print relevant information in console, defaults to ``True``
        :type verbose: bool | int
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
                    rel_path = check_relpath(os.path.dirname(path_to_file))
                    print(f'"{osm_filename}" is already available\n\tat "{rel_path}\\".')

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

        return subrgn_names_, file_fmt_, cfm_req_, action_, dwnld_list_, existing_file_paths

    def verify_download_dir(self, download_dir, verify_download_dir):
        """
        Verify the pathname of the current download directory.

        :param download_dir: directory for saving the downloaded file(s)
        :type download_dir: str | os.PathLike[str] | None
        :param verify_download_dir: whether to verify the pathname of the current download directory
        :type verify_download_dir: bool

        **Tests**::

            >>> from pydriosm.downloader._downloader import _Downloader
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
        :type verbose: bool | int
        :param kwargs: optional parameters of `pyhelpers.ops.download_file_from_url()`_

        .. _`pyhelpers.ops.download_file_from_url()`:
            https://pyhelpers.readthedocs.io/en/latest/_generated/
            pyhelpers.ops.download_file_from_url.html

        **Tests**::

            >>> from pydriosm.downloader._downloader import _Downloader
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
            rel_path = check_relpath(os.path.dirname(file_pathname))

            prt_msg = \
                f"{status_msg} \"{os.path.basename(file_pathname)}\"\n\t{prep} \"{rel_path}\\\""
            print(prt_msg, end=" ... \n" if verbose == 2 else " ... ")

        try:
            verbose_ = True if verbose == 2 else False
            download_file_from_url(
                url=download_url, path_to_file=file_pathname, verbose=verbose_, **kwargs)

            if verbose:
                time.sleep(0.5)
                print("Done.")

        except Exception as e:
            print(f"Failed. {_format_err_msg(e)}")

        if file_pathname not in self.data_paths:
            self.data_paths.append(file_pathname)

        if verify_download_dir:
            self.download_dir = os.path.dirname(file_pathname)
