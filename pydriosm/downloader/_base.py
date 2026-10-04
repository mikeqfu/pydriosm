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
from pathlib import Path, PurePosixPath

import requests
from pyhelpers._cache import _print_failure_message
from pyhelpers.dirs import cd, get_relative_path, resolve_dir_path
from pyhelpers.ops import confirmed, download_file_from_url, is_url
from pyhelpers.store import _check_saving_path, load_data, save_data
from pyhelpers.text import cosine_similarity_between_texts, find_similar_str

from ..errors import InvalidFileFormatError, InvalidSubregionNameError
from ..utils import _cdd


class BaseDownloader:
    """
    Base class for OpenStreetMap data downloaders.

    Provides core directory resolution, file format definitions, and user interaction
    prompt formatting across downloader implementations.
    """

    #: Name of the free download server.
    NAME: str = "OSM downloader"

    #: Full name of the data resource.
    LONG_NAME: str = "OpenStreetMap data downloader"

    #: Homepage URL.
    URL: str = 'https://www.openstreetmap.org/'

    #: Default download directory name.
    DEFAULT_DOWNLOAD_DIR: str = "osm_data"

    #: Valid data file formats and extensions.
    FILE_FORMATS: set = {
        ".csv.xz",
        ".garmin-onroad-latin1.zip",
        ".garmin-onroad.zip",
        ".garmin-opentopo.zip",
        ".garmin-osm.zip",
        ".geojson.xz",
        ".gpkg.zip",
        ".gz",
        ".mapsforge-osm.zip",
        ".osm.bz2",
        ".osm.pbf",
        ".shp.zip",
        ".svg-osm.zip",
    }

    def __init__(self, download_dir=None):
        """
        Initialize a new base downloader instance.

        Sets up the default target directory for data downloads and initializes an empty
        tracked list of downloaded file paths.

        :param download_dir: Name or path of the directory for saving downloaded data files.
            Defaults to ``None``. When ``download_dir=None``, files are saved under a folder
            named "osm_data" in the current working directory.
        :type download_dir: str | pathlib.Path | os.PathLike | None

        :ivar pathlib.Path download_dir: Resolved target directory path for downloads.
        :ivar list[pathlib.Path] data_paths: Collection of paths to downloaded data files.

        **Examples**::

            >>> from pydriosm.downloader import BaseDownloader
            >>> from pyhelpers.dirs import get_relative_path

            >>> bdl = BaseDownloader()

            >>> bdl.NAME
            'OSM downloader'

            >>> bdl.download_dir.name
            'osm_data'

            >>> bdl.cdd().name
            'osm_data'

            >>> bdl.download_dir == bdl.cdd()
            True

            >>> bdl = BaseDownloader(download_dir="tests/osm_data")
            >>> get_relative_path(bdl.download_dir, as_str=True)
            'tests/osm_data'
        """

        self.download_dir = self.cdd() if download_dir is None else resolve_dir_path(download_dir)

        self.data_paths = []

    @classmethod
    def cdd(cls, *sub_dir, mkdir=False, **kwargs):
        """
        Construct a path to the download directory or its subdirectories.

        Resolves directory and file paths within the designated download folder, creating
        directories on disk when requested.

        :param sub_dir: Subdirectory names or a filename relative to the download directory.
        :type sub_dir: str | pathlib.Path | os.PathLike
        :param mkdir: Whether to create the directory on disk. Defaults to ``False``.
        :type mkdir: bool
        :param kwargs: Optional keyword arguments passed to ``pyhelpers.dirs.cd()``.
        :type kwargs: Any
        :return: Absolute path to the resolved directory or file.
        :rtype: pathlib.Path

        .. _`pyhelpers.dirs.cd()`:
            https://pyhelpers.readthedocs.io/en/latest/_generated/pyhelpers.dirs.cd.html

        **Examples**::

            >>> from pydriosm.downloader import BaseDownloader

            >>> path = BaseDownloader.cdd()
            >>> path.name
            'osm_data'
        """

        return cd(cls.DEFAULT_DOWNLOAD_DIR, *sub_dir, mkdir=mkdir, **kwargs)

    @classmethod
    def format_confirmation_prompt(cls, data_name="<data_name>", file_path="<file_path>",
                                   update=False, note=""):
        """
        Format a user confirmation prompt for downloading or updating data.

        Generates a standardized user output string indicating whether target data will
        be compiled or updated.

        :param data_name: Name of the target dataset. Defaults to ``"<data_name>"``.
        :type data_name: str
        :param file_path: File path of the target dataset. Defaults to ``"<file_path>"``.
        :type file_path: str | pathlib.Path | os.PathLike
        :param update: Whether to force an update prompt. Defaults to ``False``.
        :type update: bool
        :param note: Additional message text to append to the prompt. Defaults to ``""``.
        :type note: str
        :return: Formatted confirmation prompt ending with a newline.
        :rtype: str

        **Examples**::

            >>> from pydriosm.downloader import BaseDownloader

            >>> BaseDownloader.format_confirmation_prompt()
            'Proceed with retrieving/compiling data of <data_name>?\\n'

            >>> BaseDownloader.format_confirmation_prompt(update=True)
            'Proceed with updating the data of <data_name>?\\n'
        """

        path = Path(file_path) if not isinstance(file_path, Path) else file_path
        action = "updating the" if (update or path.exists()) else "retrieving/compiling"
        note_text = f" {note}" if note else ""

        return f"Proceed with {action} data of {data_name}{note_text}?\n"

    @classmethod
    def print_action_prompt(cls, data_name='<data_name>', verbose=False, confirmation_required=True,
                            note="", end=" ... "):
        # noinspection PyNoneFunctionAssignment
        """
        Print an action status message before executing a data operation.

        Displays progress feedback when verbosity is enabled. The message adapts
        based on whether user confirmation was required prior to execution.

        :param data_name: Name of the prepacked data. Defaults to ``"<data_name>"``.
        :type data_name: str
        :param verbose: Verbosity level for console output. Defaults to ``False``.
        :type verbose: bool | int
        :param confirmation_required: Whether user confirmation was required to proceed.
            Defaults to ``True``.
        :type confirmation_required: bool
        :param note: Additional message text to append. Defaults to ``""``.
        :type note: str
        :param end: Trailing string appended after the status message. Defaults to ``" ... "``.
        :type end: str

        **Examples**::

            >>> from pydriosm.downloader import BaseDownloader

            >>> BaseDownloader.print_action_prompt(verbose=False) is None
            True

            >>> BaseDownloader.print_action_prompt(verbose=True)
            ... print("Done.")
            Retrieving/compiling the data ... Done.

            >>> BaseDownloader.print_action_prompt(verbose=True, note="(Some notes)")
            ... print("Done.")
            Retrieving/compiling the data (Some notes) ... Done.

            >>> BaseDownloader.print_action_prompt(verbose=True, confirmation_required=False)
            ... print("Done.")
            Retrieving/compiling data of <data_name> ... Done.
        """

        if not verbose:
            return

        suffix = "the data" if confirmation_required else f"data of {data_name}"
        note_str = f" {note}" if note else ""

        print(f"Retrieving/compiling {suffix}{note_str}", end=end, flush=True)

    @classmethod
    def print_status(cls, data_name="<data_name>", file_path="<file_path>", verbose=False,
                     error_message=None, update=False, raise_error=False):
        # noinspection PyNoneFunctionAssignment
        """
        Print a cancellation or failure status message.

        Outputs relevant feedback when an operation is canceled or encounters an error.
        If an error message is provided, it delegates printing to failure handling utilities.

        :param data_name: Name of the prepacked data. Defaults to ``"<data_name>"``.
        :type data_name: str
        :param file_path: File path of the prepacked data. Defaults to ``"<file_path>"``.
        :type file_path: str | pathlib.Path | os.PathLike
        :param verbose: Verbosity level for console output. Defaults to ``False``.
        :type verbose: bool | int
        :param error_message: Error message or exception detected during execution.
            Defaults to ``None``.
        :type error_message: Exception | str | None
        :param update: Whether data was being updated rather than collected.
            Defaults to ``False``.
        :type update: bool
        :param raise_error: Whether to raise the provided exception after printing.
            Defaults to ``False``.
        :type raise_error: bool

        **Examples**::

            >>> from pydriosm.downloader import BaseDownloader

            >>> BaseDownloader.print_status() is None  # Nothing will be printed.
            True

            >>> BaseDownloader.print_status(verbose=True)
            Canceled.

            >>> BaseDownloader.print_status(verbose=2)
            The collecting of <data_name> is canceled, or no data is available.

            >>> BaseDownloader.print_status(verbose=True, error_message="Errors")
            Failed. Errors.
        """

        if error_message is not None:
            _print_failure_message(error_message, "Failed.", verbose, raise_error)

        else:
            if verbose == 2:
                path = Path(file_path)
                action = "updating" if (update or path.exists()) else "collecting"
                print(f"The {action} of {data_name} is canceled, or no data is available.")

            elif verbose in {True, 1}:
                print("Canceled.")

        return None

    @classmethod
    def get_prepacked_data(cls, meth, data_name='<data_name>', file_stem=None, ext=".pkl.xz",
                           update=False, confirmation_required=True, dump_backup=True,
                           verbose=False, confirmation_prompt_note="", action_prompt_note="",
                           action_prompt_end=" ... ", ending_message="Done.", raise_error=False,
                           **kwargs):
        # noinspection PyShadowingNames
        """
        Get auxiliary data (that is to be prepacked in the package).

        :param meth: name of a class method for getting (auxiliary) prepacked data
        :type meth: typing.Callable
        :param data_name: name of the prepacked data, defaults to ``'<data_name>'``
        :type data_name: str
        :param file_stem: The filename (without file extension) that overrides ``data_name``
            for determining file path. Defaults to ``None``.
        :type file_stem:
        :param ext: File extension of the filename of prepacked data; defaults to ``".pkl"``.
        :type ext: str
        :param update: whether to (check on and) update the prepacked data, defaults to ``False``
        :type update: bool
        :param confirmation_required: whether asking for confirmation to proceed,
            defaults to ``True``
        :type confirmation_required: bool
        :param dump_backup: If ``True``, save a cached data file.
        :type dump_backup: bool
        :param ending_message: The ending message to print.
        :type ending_message: str
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

            >>> from pydriosm.downloader import BaseDownloader

            >>> data = BaseDownloader.get_prepacked_data(print, verbose=True, raise_error=True)
            Proceed with retrieving/compiling data of <data_name>?
             [No]|Yes: yes
            Retrieving/compiling the data ...
            Done.

            >>> data is None
            True
        """

        data_name = cls.NAME if data_name is None else data_name

        file_path = _cdd((file_stem or data_name.replace(" ", "-").lower()) + ext)

        if os.path.isfile(file_path) and not update:
            return load_data(file_path, verbose=(verbose == 3 or False))

        else:
            cfm_msg = cls.format_confirmation_prompt(
                data_name=data_name, file_path=file_path, update=update,
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
                        indent_ = re.match(r'^ *', ending_message)
                        indent = len(indent_.group()) if indent_ else 0
                        end = "\n  " + " " * indent if verbose == 2 else "\n"
                        print(ending_message, end=end)

                    if dump_backup:
                        save_data(data, file_path, verbose=(verbose == 2))

                    return data

                except Exception as error_message:
                    cls.print_status(
                        data_name=data_name, file_path=file_path, verbose=verbose,
                        error_message=error_message, update=update, raise_error=raise_error)

            else:
                cls.print_status(
                    data_name=data_name, file_path=file_path, verbose=verbose,
                    update=update)
                return None

    def validate_subregion_name(self, subregion_name, valid_names=None, raise_error=True, **kwargs):
        """
        Validate an input name of a geographic (sub)region.

        The validation is done by matching the input to a name of a geographic (sub)region
        available on a free download server.

        :param subregion_name: name/URL of a (sub)region available on a free download server
        :type subregion_name: str
        :param valid_names: names of all (sub)regions available on a free download server
        :type valid_names: typing.Collection | None
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

            >>> from pydriosm.downloader import BaseDownloader

            >>> bdl = BaseDownloader()

            >>> subrgn_name = 'abc'
            >>> bdl.validate_subregion_name(subrgn_name)
            Traceback (most recent call last):
              ...
            pydriosm.errors.InvalidSubregionNameError:
              `subregion_name='abc'`
                1) `subregion_name` fails to match any in `<downloader>.valid_subregion_names`; or
                2) The queried (sub)region is not available on the free download server.

            >>> avail_subrgn_names = ['Greater London', 'Great Britain', 'Birmingham', 'Leeds']
            >>> subrgn_name = 'Britain'
            >>> bdl.validate_subregion_name(subrgn_name, avail_subrgn_names)
            'Great Britain'

            >>> subrgn_name = 'london'
            >>> bdl.validate_subregion_name(subrgn_name, avail_subrgn_names)
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

    def validate_file_format(self, osm_file_format, valid_formats=None, raise_error=True, **kwargs):
        # noinspection PyShadowingNames
        """
        Validate an input file format of OSM data.

        The validation is done by matching the input to a filename extension available on
        a free download server.

        :param osm_file_format: file format/extension of the data
            available on a free download server
        :type osm_file_format: str
        :param valid_formats: fil extensions of the data available on a free download server
        :type valid_formats: typing.Collection | None
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

            >>> from pydriosm.downloader import BaseDownloader

            >>> bdl = BaseDownloader()

            >>> file_fmt = 'abc'
            >>> bdl.validate_file_format(file_fmt)  # Raise an error
            Traceback (most recent call last):
              ...
            pydriosm.errors.InvalidFileFormatError:
              `osm_file_format='abc'` -> The input `osm_file_format` is unidentifiable.
                Valid options include: {'.csv.xz', '.osm.bz2', '.garmin-onroad-latin1.zip', '.s...

            >>> file_fmt = 'pbf'
            >>> bdl.validate_file_format(file_fmt)
            '.osm.pbf'

            >>> file_fmt = 'shp'
            >>> bdl.validate_file_format(file_fmt)
            '.shp.zip'

            >>> file_fmt = 'geopackage'
            >>> bdl.validate_file_format(file_fmt)
            '.gpkg.zip'

        .. seealso::

            - Examples for the methods
              :meth:`GeofabrikDownloader.validate_file_format()
              <pydriosm.downloader.GeofabrikDownloader.validate_file_format>` and
              :meth:`BBBikeDownloader.validate_file_format()
              <pydriosm.downloader.BBBikeDownloader.validate_file_format>`.
        """

        if valid_formats is None:
            valid_formats = self.FILE_FORMATS

        if osm_file_format in valid_formats:
            osm_file_format_ = copy.copy(osm_file_format)

        else:
            file_fmt = osm_file_format.lower()
            if file_fmt.endswith('geopackage'):
                file_fmt = '.gpkg.zip'
            if file_fmt.endswith('shapefile'):
                file_fmt = '.shp.zip'
            osm_file_format_ = find_similar_str(file_fmt, lookup_list=valid_formats, **kwargs)

            if osm_file_format_ is None and raise_error:
                raise InvalidFileFormatError(osm_file_format, set(valid_formats))

        return osm_file_format_

    @classmethod
    def make_subregion_dirname(cls, subregion_name_):
        """
        Generate a normalized directory name for a geographic subregion.

        Strips punctuation marks and replaces whitespace separators with hyphens to produce
        a clean, lowercase directory name suitable for filesystem storage.

        :param subregion_name_: Validated name of a subregion available on a download server.
        :type subregion_name_: str
        :return: Normalized directory name for the subregion.
        :rtype: str

        **Examples**::

            >>> from pydriosm.downloader import BaseDownloader

            >>> BaseDownloader.make_subregion_dirname('England')
            'england'

            >>> BaseDownloader.make_subregion_dirname('Greater London')
            'greater-london'
        """

        words = [
            cleaned
            for x in subregion_name_.split()
            if (cleaned := x.strip(string.punctuation))
        ]

        return '-'.join(words).lower()

    @classmethod
    def get_default_sub_path(cls, subregion_name_, download_url):
        """
        Get the default subpath for saving an OSM data file of a geographic subregion.

        Resolves relative subdirectory paths based on the download server type and subregion
        name, returning a clean ``pathlib.Path`` object for directory organization.

        :param subregion_name_: Validated name of a subregion available on a download server.
        :type subregion_name_: str
        :param download_url: Download URL of a geographic subregion.
        :type download_url: str
        :return: Default relative subpath for storing downloaded data.
        :rtype: pathlib.Path

        **Examples**::

            >>> from pydriosm.downloader import BaseDownloader

            >>> subrgn_name_ = 'London'
            >>> dwnld_url = 'https://download.bbbike.org/osm/bbbike/London/London.osm.pbf'
            >>> BaseDownloader.get_default_sub_path(subrgn_name_, dwnld_url).name
            'london'
        """

        folder_name = cls.make_subregion_dirname(subregion_name_)

        if cls.NAME == 'Geofabrik':
            url_path = urllib.parse.urlparse(download_url).path
            parent_path = PurePosixPath(url_path).parent
            rel_parent = Path(*parent_path.parts[1:]) if parent_path.is_absolute() else Path(parent_path)
            return rel_parent / folder_name

        return Path(folder_name)

    def get_subregion_download_url(self, subregion_name, osm_file_format, update=False,
                                   verbose=False, raise_error=True):
        """
        Get the download URL for a geographic subregion.

        Retrieves or constructs the download URL and validated subregion name for a specified
        OSM file format on the download server.

        :param subregion_name: Name of a subregion available on the download server.
        :type subregion_name: str
        :param osm_file_format: File format or extension of the OSM data.
        :type osm_file_format: str
        :param update: Whether to force an update check. Defaults to ``False``.
        :type update: bool
        :param verbose: Verbosity level for console output. Defaults to ``False``.
        :type verbose: bool | int
        :param raise_error: Whether to raise an exception on error. Defaults to ``True``.
        :type raise_error: bool
        :return: Tuple containing the validated subregion name and download URL.
        :rtype: tuple

        .. seealso::

            - Examples for the methods
              :meth:`GeofabrikDownloader.get_subregion_download_url()
              <pydriosm.downloader.GeofabrikDownloader.get_subregion_download_url>` and
              :meth:`BBBikeDownloader.get_subregion_download_url()
              <pydriosm.downloader.BBBikeDownloader.get_subregion_download_url>`.
        """

        if not subregion_name or not osm_file_format or (update and verbose and raise_error):
            return None, None

        return "<subregion_name_>", "<download_url>"

    def get_valid_download_info(self, subregion_name, osm_file_format, download_dir=None, **kwargs):
        """
        Get information for downloading or reading a subregion data file.

        Resolves the validated subregion name, default filename, download URL and local file path.

        :param subregion_name: Name of a subregion available on the download server.
        :type subregion_name: str
        :param osm_file_format: File format or extension of the OSM data.
        :type osm_file_format: str
        :param download_dir: Directory for saving downloaded files. Defaults to ``None``.
        :type download_dir: str | pathlib.Path | None
        :param kwargs: Optional keyword arguments passed to ``get_subregion_download_url``.
        :type kwargs: dict
        :return: Validated subregion name, filename, download URL and absolute file path.
        :rtype: tuple

        .. _`pyhelpers.dirs.cd()`:
            https://pyhelpers.readthedocs.io/en/latest/_generated/pyhelpers.dirs.cd.html

        **Examples**::

            >>> from pydriosm.downloader import BaseDownloader
            >>> from pyhelpers.dirs import get_relative_path

            >>> bdl = BaseDownloader()

            >>> valid_dwnld_info = bdl.get_valid_download_info(
            ...     subregion_name='subregion_name', osm_file_format='osm_file_format'
            ... )

            >>> valid_dwnld_info[0]
            '<subregion_name_>'

            >>> valid_dwnld_info[1]
            '<download_url>'

            >>> valid_dwnld_info[2]
            '<download_url>'

            >>> get_relative_path(valid_dwnld_info[3], as_str=True)
            'osm_data/subregion_name/<download_url>'

        .. seealso::

            - Examples for the methods:
              :meth:`GeofabrikDownloader.get_valid_download_info()
              <pydriosm.downloader.GeofabrikDownloader.get_valid_download_info>` and
              :meth:`BBBikeDownloader.get_valid_download_info()
              <pydriosm.downloader.BBBikeDownloader.get_valid_download_info>`.
        """

        subregion_name_, download_url = self.get_subregion_download_url(
            subregion_name=subregion_name, osm_file_format=osm_file_format, **kwargs
        )

        if not download_url:
            return subregion_name_, None, None, None

        osm_filename = Path(download_url).name

        if download_dir is None:  # Specify a default directory
            sub_path = self.get_default_sub_path(subregion_name_, download_url=download_url)
            base_dir = Path(self.download_dir)

            if str(sub_path) in str(base_dir):
                file_path = base_dir / osm_filename
            else:
                file_path = base_dir / sub_path / osm_filename

        else:
            download_dir_ = resolve_dir_path(download_dir)
            download_path = Path(download_dir_)

            file_fmts_ = [y.replace('.', '-') for y in self.FILE_FORMATS]
            if any(str(download_path).endswith(x) for x in file_fmts_):
                file_path = download_path / osm_filename
            else:
                subrgn_dirname = self.make_subregion_dirname(subregion_name_)
                file_path = download_path / subrgn_dirname / osm_filename

        return subregion_name_, osm_filename, download_url, file_path

    def file_exists(self, subregion_name, osm_file_format, data_dir=None, update=False,
                    verbose=True, ret_file_path=False):
        """
        Check whether a data file for a geographic subregion exists locally.

        Verifies local file existence based on the default filename and storage directory.

        :param subregion_name: Name of a subregion available on the download server.
        :type subregion_name: str
        :param osm_file_format: File format of the OSM data available on the server.
        :type osm_file_format: str
        :param data_dir: Directory where data files are stored. Defaults to ``None``.
        :type data_dir: str | pathlib.Path | None
        :param update: Whether to check for updates. Defaults to ``False``.
        :type update: bool
        :param verbose: Verbosity level for console output. Defaults to ``True``.
        :type verbose: bool | int
        :param ret_file_path: Whether to return the file path if it exists. Defaults to ``False``.
        :type ret_file_path: bool
        :return: ``True`` if the file exists, the file path if ``ret_file_path=True``, or ``False``.
        :rtype: bool | str

        **Examples**::

            >>> from pydriosm.downloader import BaseDownloader

            >>> bdl = BaseDownloader()

            >>> bdl.file_exists('<subregion_name>', osm_file_format='shp')
            False

            >>> bdl.file_exists('rutland', osm_file_format='shp', data_dir="tests/data")
            False

        .. seealso::

            - Examples for the methods :meth:`GeofabrikDownloader.file_exists()
              <pydriosm.downloader.GeofabrikDownloader.file_exists>` and
              :meth:`BBBikeDownloader.file_exists()
              <pydriosm.downloader.BBBikeDownloader.file_exists>`
        """

        subregion_name_, default_fn, _, file_path = self.get_valid_download_info(
            subregion_name=subregion_name, osm_file_format=osm_file_format, download_dir=data_dir)

        if default_fn is None or file_path is None:
            if verbose == 2:
                osm_file_format_ = self.validate_file_format(
                    osm_file_format=osm_file_format, raise_error=False)
                print(f"{osm_file_format_} data for \"{subregion_name_}\" is not available "
                      f"on {self.NAME} free download server.")
            return False

        if file_path.is_file():
            if verbose == 2 and not update:
                rel_dir_path_str = get_relative_path(file_path.parent, as_str=True, quoted=True)
                print(f"\"{default_fn}\" of {subregion_name_} is available at {rel_dir_path_str}.")

            return str(file_path) if ret_file_path else True

        return False

    def _prepare_subregion_names(self, subregion_names, deep):
        """
        Prepare and validate a sequence of subregion names.

        Normalizes input subregion names into a list of validated names, optionally
        fetching nested subregion names when deep traversal is enabled.

        :param subregion_names: Single subregion name or sequence of subregion names.
        :type subregion_names: str | typing.Iterable[str]
        :param deep: Whether to recursively retrieve nested subregions.
        :type deep: bool
        :return: List of validated subregion names.
        :rtype: list[str]

        **Examples**::

            >>> from pydriosm.downloader import BaseDownloader

            >>> bdl = BaseDownloader()

            >>> bdl._prepare_subregion_names('London', deep=False)
            ['London']
        """

        if isinstance(subregion_names, str):
            names = [subregion_names]
        else:
            names = list(subregion_names)

        validated_names = [self.validate_subregion_name(x) for x in names]

        if deep and hasattr(self, 'get_subregions'):
            validated_names = self.get_subregions(*validated_names, deep=deep)

        return validated_names

    def _prepare_osm_file_formats(self, osm_file_formats):
        # noinspection shadowing-names
        """
        Prepare and validate OSM file formats alongside a status message.

        Normalizes file formats into a list of validated format strings and constructs
        a user-friendly description of the requested formats.

        :param osm_file_formats: Single file format, sequence of formats, or ``None``
            for all formats.
        :type osm_file_formats: str | typing.Iterable[str] | None
        :return: Tuple containing validated file formats and a descriptive message.
        :rtype: tuple[list[str], str]

        **Examples**::

            >>> from pydriosm.downloader import BaseDownloader

            >>> bdl = BaseDownloader()

            >>> formats, msg = bdl._prepare_osm_file_formats('pbf')
            >>> formats
            ['.osm.pbf']

            >>> msg
            'data in the format ".osm.pbf"'
        """

        if osm_file_formats is None:
            validated_formats = list(self.FILE_FORMATS)
            file_fmt_msg = "data in all available formats"
        else:
            if isinstance(osm_file_formats, str):
                formats = [osm_file_formats]
            else:
                formats = list(osm_file_formats)

            validated_formats = [self.validate_file_format(x) for x in formats]

            if len(validated_formats) == 1:
                fmt_msg = f"format \"{validated_formats[0]}\""
            else:
                fmt_msg = f"formats {tuple(validated_formats)}"

            file_fmt_msg = f"data in the {fmt_msg}"

        return validated_formats, file_fmt_msg

    def _prepare_file_paths(self, subregion_names_, file_formats_, data_dir, update, verbose):
        """
        Prepare target file paths and identify files requiring download.

        Checks local storage for existing files across specified subregions and formats,
        compiling lists of target paths, existing paths and subregions needing download.

        :param subregion_names_: Sequence of validated subregion names.
        :type subregion_names_: typing.Iterable[str]
        :param file_formats_: Sequence of validated OSM file formats.
        :type file_formats_: typing.Iterable[str]
        :param data_dir: Directory where data files are stored.
        :type data_dir: str | pathlib.Path | None
        :param update: Whether to check and force data updates.
        :type update: bool
        :param verbose: Verbosity level for console output.
        :type verbose: bool | int
        :return: Tuple containing target paths, existing paths, and subregions to download.
        :rtype: tuple[list[pathlib.Path], list[pathlib.Path], list[str]]

        **Examples**::

            >>> from pydriosm.downloader import BaseDownloader

            >>> bdl = BaseDownloader()

            >>> paths, existing, to_download = bdl._prepare_file_paths(
            ...     ['London'], ['.pbf'], data_dir="tests/data", update=False, verbose=False
            ... )
        """

        file_paths = []
        existing_file_paths = []  # Paths of existing files
        to_download_set = set()

        for subrgn_name_ in subregion_names_:
            for file_fmt in file_formats_:
                file_path_info = self.file_exists(
                    subregion_name=subrgn_name_,
                    osm_file_format=file_fmt,
                    data_dir=data_dir,
                    update=update,
                    ret_file_path=True,
                )

                if isinstance(file_path_info, (str, Path)):
                    path_obj = Path(file_path_info)
                    existing_file_paths.append(path_obj)
                    file_paths.append(path_obj)

                    if verbose:
                        osm_filename = path_obj.name
                        rel_path_str = get_relative_path(path_obj.parent, as_str=True, quoted=True)
                        print(f"\"{osm_filename}\" already exists in {rel_path_str}.")
                else:
                    to_download_set.add(subrgn_name_)
                    _, _, _, target_path = self.get_valid_download_info(
                        subrgn_name_, osm_file_format=file_fmt, download_dir=data_dir
                    )
                    file_paths.append(Path(target_path) if target_path else None)

        download_list = [x for x in subregion_names_ if x in to_download_set]

        return file_paths, existing_file_paths, download_list

    def check_download_status(self, subregion_names, osm_file_formats, data_dir=None, update=False,
                              confirmation_required=True, verbose=True, deep=False):
        """
        Check local data file existence and compile download confirmation details.

        Evaluates existing files for the requested subregions and formats, determines
        whether download or update actions are necessary, and constructs a user prompt.

        :param subregion_names: Name or sequence of names of geographic subregions.
        :type subregion_names: str | typing.Iterable[str]
        :param osm_file_formats: File format or sequence of formats for OSM data.
        :type osm_file_formats: str | typing.Iterable[str] | None
        :param data_dir: Storage directory for the data files. Defaults to ``None``.
        :type data_dir: str | pathlib.Path | None
        :param update: Whether to check for and update existing data. Defaults to ``False``.
        :type update: bool
        :param confirmation_required: Whether user confirmation is required. Defaults to ``True``.
        :type confirmation_required: bool
        :param verbose: Verbosity level for console output. Defaults to ``True``.
        :type verbose: bool | int
        :param deep: Whether to recursively check nested subregions. Defaults to ``False``.
        :type deep: bool
        :return: Tuple containing prepared subregion names, file formats, confirmation flag,
            prompt string, and existing file paths.
        :rtype: tuple[list[str], list[str], bool, str, list[pathlib.Path]]

        **Examples**::

            >>> from pydriosm.downloader import GeofabrikDownloader, BBBikeDownloader

            >>> gfd = GeofabrikDownloader()

            >>> gfd.check_download_status('London', ".pbf")
            (['Greater London'],
             ['.osm.pbf'],
             True,
             'Proceed with downloading data in the format ".osm.pbf" for the following geograph...
             [])

            >>> gfd.check_download_status(['london', 'rutland'], ".pbf")
            (['Greater London', 'Rutland'],
             ['.osm.pbf'],
             True,
             'Proceed with downloading data in the format ".osm.pbf" for the following geograph...
             [])

            >>> gfd.check_download_status(['london', 'rutland'], ["shp", ".pbf"])
            (['Greater London', 'Rutland'],
             ['.shp.zip', '.osm.pbf'],
             True,
             'Proceed with downloading data in the formats (\'.shp.zip\', \'.osm.pbf\') for the...
             [])

            >>> bbd = BBBikeDownloader()

            >>> bbd.check_download_status('London', ".pbf")
            (['London'],
             ['.pbf'],
             True,
             'Proceed with downloading data in the format ".pbf" for the following geographic (...
             [])

            >>> bbd.check_download_status(['birmingham', 'leeds'], ".pbf")
            (['Birmingham', 'Leeds'],
             ['.pbf'],
             True,
             'Proceed with downloading data in the format ".pbf" for the following geographic (...
             [])
        """

        subregion_names_ = self._prepare_subregion_names(subregion_names, deep)
        file_formats_, file_fmt_msg = self._prepare_osm_file_formats(osm_file_formats)

        file_paths, existing_file_paths, download_list = self._prepare_file_paths(
            subregion_names_=subregion_names_,
            file_formats_=file_formats_,
            data_dir=data_dir,
            update=update,
            verbose=verbose,
        )

        if not download_list:
            if update:
                cfm_req_ = bool(confirmation_required)
                action_ = "updating the"
                dwnld_list_ = subregion_names_.copy()
                prep = "in"
            else:
                cfm_req_ = False
                action_ = ""
                dwnld_list_ = download_list
                prep = "to"

        else:
            cfm_req_ = bool(confirmation_required)
            if len(download_list) == len(subregion_names_) or not update:
                action_ = "downloading"
                dwnld_list_ = download_list
                prep = "to"
            else:
                action_ = "downloading/updating the"
                dwnld_list_ = subregion_names_.copy()
                prep = "to/in"

        print_download_list = '\n\t'.join([f"\"{x}\"" for x in dwnld_list_])

        valid_paths = [p for p in file_paths if p is not None]
        if not valid_paths:
            download_dir_prompt = ""
        else:
            if len(valid_paths) == 1:
                target_dir = Path(valid_paths[0]).parent
            else:
                target_dir = Path(os.path.commonpath([str(p) for p in valid_paths]))

            rel_dir_str = get_relative_path(target_dir, as_str=True, quoted=True)
            download_dir_prompt = f"\n  {prep} {rel_dir_str}"

        confirmation_prompt = (
            f"Proceed with {action_} {file_fmt_msg} for the following geographic (sub)region(s): "
            f"\n\t{print_download_list}{download_dir_prompt}\n?"
        )

        return subregion_names_, file_formats_, cfm_req_, confirmation_prompt, existing_file_paths

    def update_download_dir(self, download_dir=None, verify_download_dir=True):
        """
        Verify and update the current download directory path.

        Resolves the provided directory path and updates the instance attribute if it differs
        from the current download directory.

        :param download_dir: Target download directory path. Defaults to ``None``.
        :type download_dir: str | pathlib.Path | None
        :param verify_download_dir: Whether to verify and update the directory path.
            Defaults to ``True``.
        :type verify_download_dir: bool
        :return: ``None``.
        :rtype: None

        **Examples**::

            >>> from pydriosm.downloader import BaseDownloader

            >>> bdl = BaseDownloader()

            >>> bdl.download_dir.name
            'osm_data'

            >>> bdl.update_download_dir(download_dir='tests', verify_download_dir=True)
            >>> bdl.download_dir.name
            'tests'
        """

        if download_dir is not None and verify_download_dir:
            resolved_dir = resolve_dir_path(download_dir)

            if resolved_dir != self.download_dir:
                self.download_dir = resolved_dir

    @classmethod
    def _execute_file_download(cls, url, target_path, verbose_level, pbar_color, msg_wrap_limit,
                               raise_error, **kwargs):
        """
        Execute URL file retrieval while redirecting output and validating result.

        :param url: Web address of remote dataset.
        :type url: str
        :param target_path: Storage destination on local file system.
        :type target_path: pathlib.Path
        :param verbose_level: Integer verbosity flag.
        :type verbose_level: int
        :param pbar_color: Progress bar display color.
        :type pbar_color: str
        :param msg_wrap_limit: Maximum line length for message wrapping.
        :type msg_wrap_limit: int | None
        :param raise_error: Whether to raise an exception on download failure.
        :type raise_error: bool
        :param kwargs: Additional arguments passed to ``download_file_from_url``.
        :type kwargs: dict[str, Any]
        :raises requests.HTTPError: If HTTP transfer fails and ``raise_error=True``.
        """

        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer):
            download_file_from_url(
                url,
                target_path,
                verbose=verbose_level == 1,
                print_wrap_limit=msg_wrap_limit,
                pbar_color=pbar_color,
                **kwargs,
            )

        output = buffer.getvalue()
        if output:
            if "Failed" in output and raise_error:
                raise requests.HTTPError(output)
            print(output, end="")

    def _record_download_state(self, target_path, verify_download_dir= True):
        """
        Register downloaded file path and update target directory configuration.

        :param target_path: Destination file path of completed download.
        :type target_path: pathlib.Path
        :param verify_download_dir: Whether to update class directory reference. Defaults to ``True``.
        :type verify_download_dir: bool

        **Examples**::

            >>> self._record_download_state(Path('data/file.pbf'))
        """

        if target_path not in self.data_paths:
            self.data_paths.append(target_path)

        if verify_download_dir:
            if hasattr(self, "update_download_dir"):
                self.update_download_dir(download_dir=target_path.parent, verify_download_dir=True)
            else:
                self.download_dir = target_path.parent

    def _download_data(self, url=None, file_path=None, interval=0.5, verbose=False,
                       raise_error=False, print_state="Downloading", pbar_color='green',
                       msg_wrap_limit=None, verify_download_dir=True, **kwargs):
        # noinspection PyShadowingNames,unresolved-references
        """
        Download an OSM data file from a specified URL.

        Saves remote file to designated target path, updates tracking attributes and handles
        progress output and cleanup upon error.

        :param url: Valid URL of OSM data file. Defaults to ``None``.
        :type url: str | None
        :param file_path: Storage destination path for downloaded file. Defaults to ``None``.
        :type file_path: pathlib.Path | str | None
        :param interval: Delay in seconds following successful download. Defaults to ``0.5``.
        :type interval: float | int
        :param verbose: Verbosity level for console output. Defaults to ``False``.
        :type verbose: bool | int
        :param raise_error: Whether to raise exceptions on failure. Defaults to ``False``.
        :type raise_error: bool
        :param print_state: State message prefix during progress display.
            Defaults to ``"Downloading"``.
        :type print_state: str
        :param pbar_color: Progress bar display color. Defaults to ``'green'``.
        :type pbar_color: str
        :param msg_wrap_limit: Maximum character length for output line wrapping.
            Defaults to ``None``.
        :type msg_wrap_limit: int | None
        :param verify_download_dir: Whether to update download directory attribute.
            Defaults to ``True``.
        :type verify_download_dir: bool
        :param kwargs: Optional parameters for ``pyhelpers.ops.download_file_from_url``.
        :type kwargs: dict[str, Any]
        :return: ``None``.
        :rtype: None
        :raises requests.HTTPError: If download fails and ``raise_error=True``.

        .. _`pyhelpers.ops.download_file_from_url()`:
            https://pyhelpers.readthedocs.io/en/latest/_generated/
            pyhelpers.ops.download_file_from_url.html

        **Examples**::

            >>> from pydriosm.downloader import BaseDownloader
            >>> from pyhelpers.dirs import cd, delete_dir
            >>> from pyhelpers.dirs import get_relative_path

            >>> bdl = BaseDownloader()

            >>> download_dir = "tests/osm_data"
            >>> filename = "rutland-latest.osm.pbf"
            >>> file_path = cd(download_dir, filename)
            >>> url = f'https://download.geofabrik.de/europe/united-kingdom/england/{filename}'

            >>> file_path.exists()
            False

            >>> # Download the PBF data of Rutland
            >>> bdl.download_data(url, file_path, verbose=True)
            Downloading "rutland-latest.osm.pbf" 100%|██████████| 1.93M/1.93M | 5.84MB/s ...
              Saving "rutland-latest.osm.pbf" to "tests/osm_data/" ... Done.

            >>> file_path.is_file()
            True
            >>> file_path.name
            'rutland-latest.osm.pbf'

            >>> # Download the data again
            >>> bdl.download_data(url, file_path, verbose=True)
            Downloading "rutland-latest.osm.pbf" 100%|██████████| 1.93M/1.93M | 5.70MB/s ...
              Updating "rutland-latest.osm.pbf" in "tests/osm_data/" ... Done.

            >>> file_path.is_file()
            True
            >>> get_relative_path(bdl.download_dir, as_str=True)
            'tests/osm_data'
            >>> len(bdl.data_paths)
            1
            >>> get_relative_path(bdl.data_paths[0], as_str=True)
            'tests/osm_data/rutland-latest.osm.pbf'

            >>> delete_dir(bdl.download_dir, verbose=True)
            Confirm deletion of the directory "tests/osm_data/" (Not empty)?
             [No]|Yes: yes
            Deleting "tests/osm_data/" ... Done.
        """

        if url is None or file_path is None:
            return None

        target_path = Path(file_path)

        # Normalize verbosity
        verbose_level = int(verbose) if isinstance(verbose, (bool, int)) else 0
        verbose1 = verbose_level == 1
        verbose2 = verbose_level == 2

        # Track if file existed before download to prevent deleting existing data on failure
        file_existed = target_path.is_file()

        _check_saving_path(
            path=target_path,
            verbose=verbose2,
            state_verb=print_state,
            end=" ... ",
            msg_wrap_limit=msg_wrap_limit,
        )

        try:
            self._execute_file_download(
                url=url,
                target_path=target_path,
                verbose_level=verbose_level,
                pbar_color=pbar_color,
                msg_wrap_limit=msg_wrap_limit,
                raise_error=raise_error,
                **kwargs,
            )

            if verbose_level == 2:
                if isinstance(interval, (int, float)) and interval > 0:
                    time.sleep(interval)
                print("Done.")

        except Exception as e:
            # Only remove if we created it during this failed attempt
            if not file_existed and target_path.is_file():
                target_path.unlink(missing_ok=True)

            _print_failure_message(e, "Failed. Error:", verbose=verbose1, raise_error=raise_error)

            if raise_error:
                raise
            return None

        self._record_download_state(target_path, verify_download_dir=verify_download_dir)
        return None

    def _fetch_file_if_needed(self, url, file_path, update=False, interval=None, verbose=False,
                              **kwargs):
        """
        Download a file if it does not exist locally or if an update is requested.

        This method explicitly invokes ``BaseDownloader.download_data`` to avoid
        unintended dynamic dispatch to subclass overrides.

        :param url: Web address of the remote dataset.
        :type url: str | None
        :param file_path: Local target storage path.
        :type file_path: pathlib.Path
        :param update: Whether to re-download existing files. Defaults to ``False``.
        :type update: bool
        :param interval: Pause duration in seconds after download. Defaults to ``None``.
        :type interval: int | float | None
        :param verbose: Verbosity level for log output. Defaults to ``False``.
        :type verbose: bool | int
        :param kwargs: Additional options passed to ``BaseDownloader.download_data``.
        :type kwargs: dict[str, Any]
        :return: Destination path if the file exists on disk; otherwise ``None``.
        :rtype: pathlib.Path | None

        **Examples**::

            >>> path = self._fetch_file_if_needed('https://example.com/data.pbf', Path('data.pbf'))
        """

        if not url:
            return None

        file_path.parent.mkdir(parents=True, exist_ok=True)

        if not file_path.is_file() or update:
            BaseDownloader._download_data(
                self,
                url=url,
                file_path=file_path,
                verbose=verbose,
                verify_download_dir=False,
                **kwargs,
            )

        if isinstance(interval, (int, float)) and interval > 0:
            time.sleep(interval)

        return file_path if file_path.is_file() else None

    def _run_download_workflow(self, subregion_names, osm_file_formats, download_dir, update,
                               confirmation_required, interval, verify_download_dir, verbose,
                               ret_download_path, url, file_path, download_item_func,
                               extra_check_kwargs=None, **kwargs):
        """
        Execute standard validation, user confirmation and download result aggregation.

        :param subregion_names: Name or names of geographic subregions.
        :type subregion_names: str | list[str] | None
        :param osm_file_formats: File format or extension of OSM data.
        :type osm_file_formats: str | list[str] | None
        :param download_dir: Save directory path. Defaults to ``None``.
        :type download_dir: str | None
        :param update: Whether to overwrite existing files. Defaults to ``False``.
        :type update: bool
        :param confirmation_required: Prompt before downloading. Defaults to ``True``.
        :type confirmation_required: bool
        :param interval: Pause duration in seconds between downloads. Defaults to ``None``.
        :type interval: int | float | None
        :param verify_download_dir: Whether to verify output directory path. Defaults to ``True``.
        :type verify_download_dir: bool
        :param verbose: Verbosity level for standard logs. Defaults to ``False``.
        :type verbose: bool | int
        :param ret_download_path: Whether to return downloaded file paths. Defaults to ``False``.
        :type ret_download_path: bool
        :param url: Direct URL override. Defaults to ``None``.
        :type url: str | None
        :param file_path: Storage destination override. Defaults to ``None``.
        :type file_path: Any | None
        :param download_item_func: Downloader-specific loop strategy.
        :type download_item_func: Callable[[list[str], list[str]], list[pathlib.Path]]
        :param extra_check_kwargs: Extra keyword arguments passed to status checker.
            Defaults to ``None``.
        :type extra_check_kwargs: dict[str, Any] | None
        :return: List of file paths if ``ret_download_path=True``; otherwise ``None``.
        :rtype: list[pathlib.Path] | None
        :raises ValueError: If neither direct URL/path nor subregion/format parameters are provided.
        """

        if url is not None and file_path is not None:
            BaseDownloader._download_data(
                self,
                url=url,
                file_path=file_path,
                interval=interval,
                verify_download_dir=verify_download_dir,
                verbose=verbose,
                **kwargs,
            )
            return [file_path] if ret_download_path else None

        if subregion_names is None or osm_file_formats is None:
            raise ValueError(
                "You must provide either 'subregion_names' and 'osm_file_formats', "
                "or 'url' and 'file_path'."
            )

        check_kwargs = {
            "subregion_names": subregion_names,
            "osm_file_formats": osm_file_formats,
            "data_dir": download_dir,
            "update": update,
            "confirmation_required": confirmation_required,
            "verbose": verbose,
        }
        if extra_check_kwargs:
            check_kwargs.update(extra_check_kwargs)

        (
            subregion_names_,
            osm_file_formats_,
            confirmation_required_,
            confirmation_prompt,
            existing_file_paths,
        ) = self.check_download_status(**check_kwargs)

        is_confirmed = confirmation_required_ and confirmation_required
        if not confirmed(confirmation_prompt, confirmation_required=is_confirmed):
            print("Canceled.")
            self.data_paths = list(dict.fromkeys(self.data_paths + existing_file_paths))
            return existing_file_paths if ret_download_path else None

        download_paths = download_item_func(subregion_names_, osm_file_formats_)
        self.update_download_dir(download_dir=download_dir, verify_download_dir=verify_download_dir)
        self.data_paths = list(dict.fromkeys(self.data_paths + download_paths))

        return download_paths if ret_download_path else None
