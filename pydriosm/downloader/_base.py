"""
Provides a base class for OSM data downloaders.
"""

import contextlib
import copy
import inspect
import io
import os
import re
import string
import time
import urllib.parse

import requests
from pyhelpers._cache import _print_failure_message
from pyhelpers.dirs import add_slashes, cd, check_relative_pathname, validate_dir
from pyhelpers.ops import confirmed, download_file_from_url, is_url
from pyhelpers.store import _check_saving_path, load_data, save_data
from pyhelpers.text import cosine_similarity_between_texts, find_similar_str

from pydriosm.errors import InvalidFileFormatError, InvalidSubregionNameError
from pydriosm.utils import _cdd


class BaseDownloader:
    """
    Initialization of a data downloader.
    """

    #: Name of the free download server.
    NAME: str = 'OSM downloader'
    #: Full name of the data resource.
    LONG_NAME: str = 'OpenStreetMap data downloader'
    #: Default download directory.
    DEFAULT_DOWNLOAD_DIR: str = cd("osm_data")
    #: Valid file formats.
    FILE_FORMATS: set = {
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
        '.osm.pbf',
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

        **Examples**::

            >>> from pydriosm.downloader._base import BaseDownloader
            >>> import os
            >>> _d = BaseDownloader()
            >>> _d.NAME
            'OSM downloader'
            >>> os.path.relpath(_d.download_dir)
            'osm_data'
            >>> os.path.relpath(_d.cdd())
            'osm_data'
            >>> _d.download_dir == _d.cdd()
            True
            >>> _d = BaseDownloader(download_dir="tests/osm_data")
            >>> os.path.relpath(_d.download_dir)  # on Windows
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

        **Examples**::

            >>> from pydriosm.downloader._base import BaseDownloader
            >>> import os
            >>> os.path.relpath(BaseDownloader.cdd())
            'osm_data'
        """

        pathname = cd(cls.DEFAULT_DOWNLOAD_DIR, *sub_dir, mkdir=mkdir, **kwargs)

        return pathname

    @classmethod
    def format_confirmation_prompt(cls, data_name='<data_name>', file_path="<file_path>",
                                   update=False, note=""):
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

        **Examples**::

            >>> from pydriosm.downloader._base import BaseDownloader
            >>> BaseDownloader.format_confirmation_prompt()
            'To compile data of <data_name>\\n?'
            >>> BaseDownloader.format_confirmation_prompt(update=True)
            'To update the data of <data_name>\\n?'
        """

        action = "update the" if (os.path.exists(file_path) or update) else "retrieve/compile"

        prompt = f"To {action} data of {data_name}" + (" " + note if note else "") + "\n?"

        return prompt

    @classmethod
    def print_action_prompt(cls, data_name='<data_name>', verbose=False, confirmation_required=True,
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

        **Examples**::

            >>> from pydriosm.downloader._base import BaseDownloader
            >>> BaseDownloader.print_action_prompt(verbose=False) is None  # Nothing will be printed.
            True
            >>> BaseDownloader.print_action_prompt(verbose=True)
            ... print("Done.")
            Compiling the data ... Done.
            >>> BaseDownloader.print_action_prompt(verbose=True, note="(Some notes)")
            ... print("Done.")
            Compiling the data (Some notes) ... Done.
            >>> BaseDownloader.print_action_prompt(verbose=True, confirmation_required=False)
            ... print("Done.")
            Compiling data of <data_name> ... Done.
        """

        if verbose:
            action = "Retrieving/compiling"
            suffix = "the data" if confirmation_required else f"data of {data_name}"
            print(f"{action} {suffix}" + (" " + note if note else ""), end=end)

    @classmethod
    def print_status(cls, data_name='<data_name>', path_to_file="<file_path>", verbose=False,
                     error_message=None, update=False, raise_error=False):
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
        :param raise_error: Whether to raise the provided exception;
            if ``raise_error=False`` (default), the error will be suppressed.
        :type raise_error: bool

        **Examples**::

            >>> from pydriosm.downloader._base import BaseDownloader
            >>> BaseDownloader.print_status() is None  # Nothing will be printed.
            True
            >>> BaseDownloader.print_status(verbose=True)
            Cancelled.
            >>> BaseDownloader.print_status(verbose=2)
            The collecting of <data_name> is cancelled, or no data is available.
            >>> BaseDownloader.print_status(verbose=True, error_message="Errors.")
            Failed. Errors.
        """

        if error_message is not None:
            _print_failure_message(
                error_message, prefix="Failed.", verbose=verbose, raise_error=raise_error)

        else:
            if verbose == 2:
                action = "updating" if update or os.path.exists(path_to_file) else "collecting"
                print(f"The {action} of {data_name} is cancelled, or no data is available.")

            elif verbose is True or verbose == 1:
                print("Cancelled.")

    @classmethod
    def get_prepacked_data(cls, meth, data_name='<data_name>', ext=".pkl.xz", update=False,
                           confirmation_required=True, dump_backup=True, verbose=False,
                           confirmation_prompt_note="", action_prompt_note="",
                           action_prompt_end=" ... ", ending_message="Done.", raise_error=False,
                           **kwargs):
        # noinspection PyShadowingNames
        """
        Get auxiliary data (that is to be prepacked in the package).

        :param meth: name of a class method for getting (auxiliary) prepacked data
        :type meth: typing.Callable
        :param data_name: name of the prepacked data, defaults to ``'<data_name>'``
        :type data_name: str
        :param ext: File extension of the filename of prepacked data; defaults to ``".pkl"``.
        :type ext: str
        :param update: whether to (check on and) update the prepacked data, defaults to ``False``
        :type update: bool
        :param confirmation_required: whether asking for confirmation to proceed,
            defaults to ``True``
        :type confirmation_required: bool
        :param dump_backup:
        :type dump_backup:
        :param ending_message:
        :type ending_message:
        :param verbose: whether to print relevant information in console, defaults to ``False``
        :type verbose: bool | int
        :param confirmation_prompt_note: additional message for the method
            :meth:`~pydriosm.downloader._Downloader.compose_cfm_msg`, defaults to ``""``
        :type confirmation_prompt_note: str
        :param action_prompt_note: equivalent of the parameter ``note`` of the method
            :meth:`~pydriosm.downloader._Downloader.print_action_msg`, defaults to ``""``
        :type action_prompt_note: str
        :param action_prompt_end: equivalent of the parameter ``end`` of the method
            :meth:`~pydriosm.downloader._Downloader.print_action_msg`, defaults to ``" ... "``
        :type action_prompt_end: str
        :param raise_error: Whether to raise the provided exception;
            if ``raise_error=False`` (default), the error will be suppressed.
        :type raise_error: bool
        :return: auxiliary data
        :rtype: typing.Any

        **Examples**::

            >>> from pydriosm.downloader._base import BaseDownloader
            >>> data = BaseDownloader.get_prepacked_data(callable, verbose=True, raise_error=True)
            To compile data of <data_name>
            ? [No]|Yes: yes
            >>> data is None
            True
        """

        data_name = cls.NAME if data_name is None else data_name

        path_to_file = _cdd(data_name.replace(" ", "-").lower() + ext)

        if os.path.isfile(path_to_file) and not update:
            return load_data(path_to_file, verbose=(verbose == 3 or False))

        else:
            cfm_msg = cls.format_confirmation_prompt(
                data_name=data_name, file_path=path_to_file, update=update,
                note=confirmation_prompt_note)

            if confirmed(cfm_msg, confirmation_required=confirmation_required):
                cls.print_action_prompt(
                    data_name=data_name, verbose=verbose,
                    confirmation_required=confirmation_required, note=action_prompt_note,
                    end=action_prompt_end)

                try:
                    # Build kwargs dynamically based on method signature
                    # for param in set(inspect.signature(cls.get_prepacked_data).parameters):
                    for param in {'verbose', 'raise_error'}:
                        if param in inspect.signature(meth).parameters:
                            kwargs.update({param: locals()[param]})

                    data = meth(**kwargs)

                    if verbose:
                        leading_tabs = len(re.match(r'^\t*', ending_message).group())
                        end = "\n" + "\t" * (leading_tabs + 1) if verbose == 2 else "\n"
                        print(ending_message, end=end)

                    if dump_backup:
                        save_data(data, path_to_file=path_to_file, verbose=(verbose == 2))

                    return data

                except Exception as error_message:
                    cls.print_status(
                        data_name=data_name, path_to_file=path_to_file, verbose=verbose,
                        error_message=error_message, update=update, raise_error=raise_error)

            else:
                cls.print_status(
                    data_name=data_name, path_to_file=path_to_file, verbose=verbose,
                    update=update)

    @classmethod
    def validate_subregion_name(cls, subregion_name, valid_names=None, raise_error=True, **kwargs):
        """
        Validate an input name of a geographic (sub)region.

        The validation is done by matching the input to a name of a geographic (sub)region
        available on a free download server.

        :param subregion_name: name/URL of a (sub)region available on a free download server
        :type subregion_name: str
        :param valid_names: names of all (sub)regions available on a free download server
        :type valid_names: typing.Iterable
        :param raise_error: (if the input fails to match a valid name) whether to raise the error
            :py:class:`pydriosm.downloader.InvalidSubregionName`, defaults to ``True``
        :type raise_error: bool
        :param kwargs: [optional] parameters of `pyhelpers.text.find_similar_str()`_
        :return: valid subregion name that matches (or is the most similar to) the input
        :rtype: str

        .. _`pyhelpers.text.find_similar_str()`:
            https://pyhelpers.readthedocs.io/en/latest/_generated/
            pyhelpers.text.find_similar_str.html

        **Examples**::

            >>> from pydriosm.downloader._base import BaseDownloader

            >>> subrgn_name = 'abc'
            >>> BaseDownloader.validate_subregion_name(subrgn_name)
            Traceback (most recent call last):
              ...
            pydriosm.errors.InvalidSubregionNameError:
              `subregion_name='abc'`
                1) `subregion_name` fails to match any in `<downloader>.valid_subregion_names`; or
                2) The queried (sub)region is not available on the free download server.
            >>> avail_subrgn_names = ['Greater London', 'Great Britain', 'Birmingham', 'Leeds']
            >>> subrgn_name = 'Britain'
            >>> BaseDownloader.validate_subregion_name(subrgn_name, avail_subrgn_names)
            'Great Britain'
            >>> subrgn_name = 'london'
            >>> BaseDownloader.validate_subregion_name(subrgn_name, avail_subrgn_names)
            'Greater London'

        .. seealso::

            - Examples for the methods
              :meth:`GeofabrikDownloader.validate_subregion_name()
              <pydriosm.downloader.GeofabrikDownloader.validate_subregion_name>` and
              :meth:`BBBikeDownloader.validate_subregion_name()
              <pydriosm.downloader.BBBikeDownloader.validate_subregion_name>`.
        """

        if valid_names is None:
            valid_names = []
        if subregion_name in valid_names:
            return subregion_name

        if re.match(r"(?i)^usa?$", subregion_name):  # Handle common shorthand like "USA"
            return "United States of America"

        # Attempt to extract a name from a path or URL
        if os.path.isdir(os.path.dirname(subregion_name)) or is_url(url=subregion_name):
            base_name = os.path.basename(subregion_name).split('.')[0]
            query_name = re.sub(r'-(latest|free)', '', base_name)
        else:
            query_name = subregion_name

        # kwargs.update({'cutoff': 0.6})
        subregion_name_ = find_similar_str(query_name, lookup_list=valid_names, **kwargs)

        if raise_error:
            if subregion_name_ is None:
                raise InvalidSubregionNameError(subregion_name, msg=1)

            elif cosine_similarity_between_texts(subregion_name_, query_name) < 0.4:
                raise InvalidSubregionNameError(subregion_name, msg=2)

        return subregion_name_

    @classmethod
    def validate_file_format(cls, osm_file_format, valid_formats=None, raise_error=True, **kwargs):
        """
        Validate an input file format of OSM data.

        The validation is done by matching the input to a filename extension available on
        a free download server.

        :param osm_file_format: file format/extension of the data
            available on a free download server
        :type osm_file_format: str
        :param valid_formats: fil extensions of the data available on a free download server
        :type valid_formats: typing.Iterable
        :param raise_error: (if the input fails to match a valid name) whether to raise the error
            :py:class:`pydriosm.downloader.InvalidFileFormatError`, defaults to ``True``
        :type raise_error: bool
        :param kwargs: [optional] parameters of `pyhelpers.text.find_similar_str()`_
        :return: validated file format
        :rtype: str

        .. _`pyhelpers.text.find_similar_str()`:
            https://pyhelpers.readthedocs.io/en/latest/_generated/
            pyhelpers.text.find_similar_str.html

        **Examples**::

            >>> from pydriosm.downloader._base import BaseDownloader

            >>> file_fmt = 'abc'
            >>> BaseDownloader.validate_file_format(file_fmt)  # Raise an error
            Traceback (most recent call last):
              ...
            pydriosm.errors.InvalidFileFormatError:
              `osm_file_format='abc'` -> The input `osm_file_format` is unidentifiable.
                Valid options include: {'.garmin-opentopo.zip', '.osm.bz2', '.osm.pbf', '.garmin-...

            >>> avail_file_fmts = ['.osm.pbf', '.shp.zip', '.osm.bz2']

            >>> file_fmt = 'pbf'
            >>> BaseDownloader.validate_file_format(file_fmt, avail_file_fmts)
            '.osm.pbf'

            >>> file_fmt = 'shp'
            >>> BaseDownloader.validate_file_format(file_fmt, avail_file_fmts)
            '.shp.zip'

        .. seealso::

            - Examples for the methods
              :meth:`GeofabrikDownloader.validate_file_format()
              <pydriosm.downloader.GeofabrikDownloader.validate_file_format>` and
              :meth:`BBBikeDownloader.validate_file_format()
              <pydriosm.downloader.BBBikeDownloader.validate_file_format>`.
        """

        if valid_formats is None:
            valid_formats = cls.FILE_FORMATS

        if osm_file_format in valid_formats:
            osm_file_format_ = copy.copy(osm_file_format)

        else:
            osm_file_format_ = find_similar_str(
                osm_file_format, lookup_list=valid_formats, **kwargs)

            if osm_file_format_ is None and raise_error:
                raise InvalidFileFormatError(osm_file_format, set(valid_formats))

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

        **Examples**::

            >>> from pydriosm.downloader._base import BaseDownloader

            >>> subrgn_name_ = 'London'
            >>> dwnld_url = 'https://download.bbbike.org/osm/bbbike/London/London.osm.pbf'

            >>> BaseDownloader.get_default_sub_path(subrgn_name_, dwnld_url)
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

        **Examples**::

            >>> from pydriosm.downloader._base import BaseDownloader
            >>> subrgn_name_ = 'England'
            >>> BaseDownloader.make_subregion_dirname(subrgn_name_)
            'england'
            >>> subrgn_name_ = 'Greater London'
            >>> BaseDownloader.make_subregion_dirname(subrgn_name_)
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

        **Examples**::

            >>> from pydriosm.downloader._base import BaseDownloader
            >>> import os

            >>> d = BaseDownloader()

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

        **Examples**::

            >>> from pydriosm.downloader._base import BaseDownloader
            >>> _d = BaseDownloader()
            >>> _d.file_exists('<subregion_name>', osm_file_format='shp')
            False
            >>> _d.file_exists('rutland', osm_file_format='shp', data_dir="tests\\data")

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
                    osm_file_format=osm_file_format, raise_error=False)
                print(f"{osm_file_format_} data for \"{subregion_name_}\" is not available "
                      f"on {self.NAME} free download server.")
            file_exists = False

        else:
            if os.path.isfile(path_to_file):
                if verbose == 2 and not update:
                    rel_p = check_relative_pathname(os.path.dirname(path_to_file))
                    print(f"\"{default_fn}\" of {subregion_name_} is available at \"{rel_p}\".")

                if ret_file_path:
                    file_exists = path_to_file
                else:
                    file_exists = True

            else:
                file_exists = False

        return file_exists

    def file_exists_and_more(self, subregion_names, osm_file_formats, data_dir=None, update=False,
                             confirmation_required=True, verbose=True, deep=False):
        """
        Check if a requested data file already exists and compile information
        for downloading the data.

        :param subregion_names: name(s) of geographic (sub)region(s)
            available on a free download server
        :type subregion_names: str | list
        :param osm_file_formats: file format of the OSM data available on the free download server
        :type osm_file_formats: str
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

        **Examples**::

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
            >>> gfd.file_exists_and_more(['london', 'rutland'], ["shp", ".pbf"])
            (['Greater London', 'Rutland'],
             ['.shp.zip', '.osm.pbf'],
             True,
             'download',
             ['Greater London', 'Greater London', 'Rutland', 'Rutland'],
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
            subregion_names_ = [subregion_names]
        else:
            subregion_names_ = list(subregion_names)
        subregion_names_ = [self.validate_subregion_name(x) for x in subregion_names_]

        if deep:
            try:
                # noinspection PyUnresolvedReferences
                subregion_names_ = self.get_subregions(*subregion_names_, deep=deep)
            except AttributeError:
                pass

        if osm_file_formats is None:
            file_formats_ = tuple(self.FILE_FORMATS)
            fmt_msg = "data in all available formats"
        else:
            if isinstance(osm_file_formats, str):
                file_formats_ = [osm_file_formats]
            else:
                file_formats_ = list(osm_file_formats)
            file_formats_ = [self.validate_file_format(x) for x in file_formats_]

            fmt_msg_ = f"format '{file_formats_[0]}'" if len(file_formats_) == 1 \
                else f"formats {tuple(file_formats_)}"
            fmt_msg = f"data in the {fmt_msg_}"

        file_paths = []
        existing_file_paths = []  # Paths of existing files
        download_list = [x for x in subregion_names_ for _ in range(len(file_formats_))]
        for subrgn_name_ in subregion_names_:
            for file_fmt in file_formats_:
                path_to_file = self.file_exists(
                    subregion_name=subrgn_name_, osm_file_format=file_fmt, data_dir=data_dir,
                    update=update, ret_file_path=True)

                if isinstance(path_to_file, str):
                    existing_file_paths.append(path_to_file)
                    download_list.remove(subrgn_name_)

                    if verbose:
                        osm_filename = os.path.basename(path_to_file)
                        rel_path = check_relative_pathname(os.path.dirname(path_to_file))
                        print(f'"{osm_filename}" already exists in {add_slashes(rel_path)}.')

                else:
                    _, _, _, path_to_file = self.get_valid_download_info(
                        subrgn_name_, osm_file_format=file_fmt, download_dir=data_dir)

                file_paths.append(path_to_file)

        download_list = list(set(download_list))

        if not download_list:
            if update:
                cfm_req_ = confirmation_required or False
                action_, dwnld_list_, prep = "update the", subregion_names_.copy(), "in"
            else:
                cfm_req_ = False
                action_, dwnld_list_, prep = "", download_list, "to"

        else:
            cfm_req_ = confirmation_required or False
            if len(download_list) == len(subregion_names_) or not update:
                action_, dwnld_list_, prep = "download", download_list, "to"
            else:
                action_, dwnld_list_, prep = "download/update the", subregion_names_.copy(), "to/in"

        print_download_list = "\n\t".join([f'"{x}"' for x in dwnld_list_])

        if any(x is None for x in file_paths):
            download_dir_ = ""
        else:
            if len(file_paths) == 1:
                download_dir_ = os.path.dirname(file_paths[0])
            else:
                download_dir_ = os.path.commonpath(file_paths)
            download_dir_ = f"\n  {prep} {add_slashes(check_relative_pathname(download_dir_))}"

        confirmation_prompt = \
            f"To {action_} {fmt_msg} for the following geographic (sub)region(s): " \
            f"\n\t{print_download_list}{download_dir_}\n?"

        return subregion_names_, file_formats_, cfm_req_, confirmation_prompt, existing_file_paths

    def verify_download_dir(self, download_dir=None, verify_download_dir=True):
        """
        Verify the pathname of the current download directory.

        :param download_dir: directory for saving the downloaded file(s)
        :type download_dir: str | os.PathLike | None
        :param verify_download_dir: whether to verify the pathname of the current download directory
        :type verify_download_dir: bool

        **Examples**::

            >>> from pydriosm.downloader._base import BaseDownloader
            >>> import os
            >>> _d = BaseDownloader()
            >>> os.path.relpath(_d.download_dir)
            'osm_data'
            >>> _d.verify_download_dir(download_dir='tests', verify_download_dir=True)
            >>> os.path.relpath(_d.download_dir)
            'tests'
        """

        if download_dir is not None and verify_download_dir:
            download_dir_ = validate_dir(path_to_dir=download_dir)

            if download_dir_ != self.download_dir:
                self.download_dir = download_dir_

    def _download_data(self, url, path_to_file, interval=0.5, verbose=False, raise_error=False,
                       print_state="Downloading", colour='green', print_wrap_limit=75,
                       verify_download_dir=True, **kwargs):
        # noinspection PyShadowingNames
        """
        Download an OSM data file.

        :param url: a valid URL of an OSM data file
        :type url: str
        :param path_to_file: path where the downloaded OSM data file is saved
        :type path_to_file: str
        :param verbose: whether to print relevant information in console; defaults to ``False``.
        :type verbose: bool | int
        :param colour: Custom colour of the progress bar (e.g. 'green', 'yellow');
            defaults to ``None``.
        :type colour: str | None
        :param raise_error: Whether to raise the provided exception;
            if ``raise_error=False`` (default), the error will be suppressed.
        :type raise_error: bool
        :param kwargs: optional parameters of `pyhelpers.ops.download_file_from_url()`_

        .. _`pyhelpers.ops.download_file_from_url()`:
            https://pyhelpers.readthedocs.io/en/latest/_generated/
            pyhelpers.ops.download_file_from_url.html

        **Examples**::

            >>> from pydriosm.downloader._base import BaseDownloader
            >>> from pyhelpers.dirs import cd, delete_dir
            >>> import os
            >>> _d = BaseDownloader()
            >>> download_dir = "tests/osm_data"
            >>> filename = "rutland-latest.osm.pbf"
            >>> path_to_file = cd(download_dir, filename)
            >>> url = f'https://download.geofabrik.de/europe/united-kingdom/england/{filename}'
            >>> os.path.exists(path_to_file)
            False
            >>> # Download the PBF data of Rutland
            >>> _d._download_data(url, path_to_file, verbose=True)
            Downloading "rutland-latest.osm.pbf" to "./tests/osm_data/" ... Done.
            >>> os.path.isfile(path_to_file)
            True
            >>> # Download the data again
            >>> _d._download_data(url, path_to_file, verbose=True)
            Downloading "rutland-latest.osm.pbf" 100%|██████████| 1.83M/1.83M | 471kB/s ...
                Updating "rutland-latest.osm.pbf" in "./tests/osm_data/" ... Done.
            >>> os.path.isfile(path_to_file)
            True
            >>> os.path.relpath(_d.download_dir)  # (on Windows)
            'tests\\osm_data'
            >>> len(_d.data_paths)
            1
            >>> os.path.relpath(_d.data_paths[0])  # (on Windows)
            'tests\\osm_data\\rutland-latest.osm.pbf'
            >>> delete_dir(_d.download_dir, verbose=True)
            To delete the directory "./tests/osm_data/" (Not empty)
            ? [No]|Yes: yes
            Deleting "./tests/osm_data/" ... Done.
        """

        verbose_ = verbose == 2 or False

        _check_saving_path(
            path_to_file, verbose=verbose_, state_verb=print_state, print_end=" ... ",
            print_wrap_limit=print_wrap_limit)

        try:
            f = io.StringIO()
            with contextlib.redirect_stdout(f):
                download_file_from_url(
                    url=url, path_to_file=path_to_file, verbose=(int(verbose) == 1 or False),
                    print_wrap_limit=print_wrap_limit, colour=colour, **kwargs)

            out = f.getvalue()

            if out:
                if "Failed" in out and raise_error:
                    raise requests.HTTPError(out)
                else:
                    print(out, end="")

            if verbose_:
                time.sleep(0 if interval is None else interval)
                print("Done.")

        except Exception as e:
            if os.path.isfile(path_to_file):
                os.remove(path_to_file)

            _print_failure_message(
                e, prefix="Failed. Error:", verbose=verbose, raise_error=raise_error)

            if not raise_error:
                return None

        if path_to_file not in self.data_paths:
            self.data_paths.append(path_to_file)

        if verify_download_dir:
            self.download_dir = os.path.dirname(path_to_file)
