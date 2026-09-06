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
        :return: ``None``.
        :rtype: None

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

        if verbose:
            action = "Retrieving/compiling"
            suffix = "the data" if confirmation_required else f"data of {data_name}"
            note_str = f" {note}" if note else ""
            print(f"{action} {suffix}{note_str}", end=end, flush=True)

    @classmethod
    def print_status(cls, data_name="<data_name>", path_to_file="<file_path>", verbose=False,
                     error_message=None, update=False, raise_error=False):
        # noinspection PyNoneFunctionAssignment
        """
        Print a cancellation or failure status message.

        Outputs relevant feedback when an operation is canceled or encounters an error.
        If an error message is provided, it delegates printing to failure handling utilities.

        :param data_name: Name of the prepacked data. Defaults to ``"<data_name>"``.
        :type data_name: str
        :param path_to_file: File path of the prepacked data. Defaults to ``"<file_path>"``.
        :type path_to_file: str | pathlib.Path | os.PathLike
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
        :return: ``None``.
        :rtype: None

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
            _print_failure_message(
                error_message, prefix="Failed.", verbose=verbose, raise_error=raise_error)

        else:
            if verbose == 2:
                path = Path(path_to_file) if not isinstance(path_to_file, Path) else path_to_file
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

        path_to_file = _cdd((file_stem or data_name.replace(" ", "-").lower()) + ext)

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
                        indent_ = re.match(r'^ *', ending_message)
                        indent = len(indent_.group()) if indent_ else 0
                        end = "\n  " + " " * indent if verbose == 2 else "\n"
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
                return None

    @classmethod
    def validate_subregion_name(cls, subregion_name, valid_names=None, raise_error=True, **kwargs):
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

            >>> file_fmt = 'abc'
            >>> BaseDownloader.validate_file_format(file_fmt)  # Raise an error
            Traceback (most recent call last):
              ...
            pydriosm.errors.InvalidFileFormatError:
              `osm_file_format='abc'` -> The input `osm_file_format` is unidentifiable.
                Valid options include: {'.csv.xz', '.osm.bz2', '.garmin-onroad-latin1.zip', '.s...

            >>> file_fmt = 'pbf'
            >>> BaseDownloader.validate_file_format(file_fmt)
            '.osm.pbf'

            >>> file_fmt = 'shp'
            >>> BaseDownloader.validate_file_format(file_fmt)
            '.shp.zip'

            >>> file_fmt = 'geopackage'
            >>> BaseDownloader.validate_file_format(file_fmt)
            '.gpkg.zip'

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

    @classmethod
    def get_subregion_download_url(cls, subregion_name, osm_file_format, update=False,
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

        subregion_name_, default_fn, _, path_to_file = self.get_valid_download_info(
            subregion_name=subregion_name, osm_file_format=osm_file_format, download_dir=data_dir)

        if default_fn is None or path_to_file is None:
            if verbose == 2:
                osm_file_format_ = self.validate_file_format(
                    osm_file_format=osm_file_format, raise_error=False)
                print(f"{osm_file_format_} data for \"{subregion_name_}\" is not available "
                      f"on {self.NAME} free download server.")
            return False

        file_path = Path(path_to_file)
        if file_path.is_file():
            if verbose == 2 and not update:
                rel_file_path_str = get_relative_path(file_path.parent, as_str=True, quoted=True)
                print(f"\"{default_fn}\" of {subregion_name_} is available at {rel_file_path_str}.")

            return str(file_path) if ret_file_path else True

        return False

    def _prep_subregion_names(self, subregion_names, deep):
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

        return subregion_names_

    def _prep_osm_file_formats(self, osm_file_formats):
        if osm_file_formats is None:
            file_formats_ = tuple(self.FILE_FORMATS)
            file_fmt_msg = "data in all available formats"
        else:
            if isinstance(osm_file_formats, str):
                file_formats_ = [osm_file_formats]
            else:
                file_formats_ = list(osm_file_formats)
            file_formats_ = [self.validate_file_format(x) for x in file_formats_]

            fmt_msg_ = f"format '{file_formats_[0]}'" if len(file_formats_) == 1 \
                else f"formats {tuple(file_formats_)}"
            file_fmt_msg = f"data in the {fmt_msg_}"

        return file_formats_, file_fmt_msg

    def _prep_file_paths(self, subregion_names_, file_formats_, data_dir, update, verbose):
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
                        rel_path_str = get_relative_path(
                            os.path.dirname(path_to_file), as_str=True, quoted=True)
                        print(f'"{osm_filename}" already exists in {rel_path_str}.')

                else:
                    _, _, _, path_to_file = self.get_valid_download_info(
                        subrgn_name_, osm_file_format=file_fmt, download_dir=data_dir)

                file_paths.append(path_to_file)

        download_list = list(set(download_list))

        return file_paths, existing_file_paths, download_list

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
        :param deep: whether to further check availability of sub-subregions data,
            defaults to ``False``
        :type deep: bool
        :return: whether the requested data file exists; or the path to the data file
        :rtype: tuple

        **Examples**::

            >>> from pydriosm.downloader import GeofabrikDownloader, BBBikeDownloader
            >>> gfd = GeofabrikDownloader()
            >>> gfd.file_exists_and_more('London', ".pbf")
            (['Greater London'],
             ['.osm.pbf'],
             True,
             'Proceed to download data in the format \'.osm.pbf\' for the following geographic ...
             [])
            >>> gfd.file_exists_and_more(['london', 'rutland'], ".pbf")
            (['Greater London', 'Rutland'],
             ['.osm.pbf'],
             True,
             'Proceed to download data in the format \'.osm.pbf\' for the following geographic ...
             [])
            >>> gfd.file_exists_and_more(['london', 'rutland'], ["shp", ".pbf"])
            (['Greater London', 'Rutland'],
             ['.shp.zip', '.osm.pbf'],
             True,
             'Proceed to download data in the formats (\'.shp.zip\', \'.osm.pbf\') for the foll...
             [])
            >>> bbd = BBBikeDownloader()
            >>> bbd.file_exists_and_more('London', ".pbf")
            (['London'],
             ['.pbf'],
             True,
             'Proceed to download data in the format \'.pbf\' for the following geographic (sub...
             [])
            >>> bbd.file_exists_and_more(['birmingham', 'leeds'], ".pbf")
            (['Birmingham', 'Leeds'],
             ['.pbf'],
             True,
             'Proceed to download data in the format \'.pbf\' for the following geographic (sub...
             [])
        """

        subregion_names_ = self._prep_subregion_names(subregion_names=subregion_names, deep=deep)

        file_formats_, file_fmt_msg = self._prep_osm_file_formats(osm_file_formats=osm_file_formats)

        file_paths, existing_file_paths, download_list = self._prep_file_paths(
            subregion_names_=subregion_names_, file_formats_=file_formats_, data_dir=data_dir,
            update=update, verbose=verbose)

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
            rel_download_dir_str = get_relative_path(download_dir_, as_str=True, quoted=True)
            download_dir_ = f"\n  {prep} {rel_download_dir_str}"

        confirmation_prompt = \
            f"Proceed to {action_} {file_fmt_msg} for the following geographic (sub)region(s): " \
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

            >>> from pydriosm.downloader import BaseDownloader
            >>> import os
            >>> bdl = BaseDownloader()
            >>> os.path.relpath(bdl.download_dir)
            'osm_data'
            >>> bdl.verify_download_dir(download_dir='tests', verify_download_dir=True)
            >>> os.path.relpath(bdl.download_dir)
            'tests'
        """

        if download_dir is not None and verify_download_dir:
            download_dir_ = resolve_dir_path(download_dir)

            if download_dir_ != self.download_dir:
                self.download_dir = download_dir_

    def download_data(self, url, path_to_file, interval=0.5, verbose=False, raise_error=False,
                      print_state="Downloading", pbar_color='green', msg_wrap_limit=None,
                      verify_download_dir=True, **kwargs):
        # noinspection PyShadowingNames
        """
        Download an OSM data file from a URL.

        :param url: Valid URL of the OSM data file.
        :type url: str
        :param path_to_file: Destination path for the downloaded file.
        :type path_to_file: str
        :param interval: Sleep interval (seconds) after a successful download. Defaults to ``0.5``.
        :type interval: float | int
        :param verbose: Whether to print progress; ``2`` for higher verbosity.
            Defaults to ``False``.
        :type verbose: bool | int
        :param raise_error: Whether to raise exceptions on failure. Defaults to ``False``.
        :type raise_error: bool
        :param print_state: Prefix text for the status message. Defaults to ``"Downloading"``.
        :type print_state: str
        :param pbar_color: Color of the progress bar. Defaults to ``'green'``.
        :type pbar_color: str
        :param msg_wrap_limit: Maximum character length for printed messages. Defaults to ``None``.
        :type msg_wrap_limit: int | None
        :param verify_download_dir: Whether to update the instance's download directory.
            Defaults to ``True``.
        :type verify_download_dir: bool
        :param kwargs: Optional parameters for `pyhelpers.ops.download_file_from_url`_.

        .. _`pyhelpers.ops.download_file_from_url()`:
            https://pyhelpers.readthedocs.io/en/latest/_generated/
            pyhelpers.ops.download_file_from_url.html

        **Examples**::

            >>> from pydriosm.downloader import BaseDownloader
            >>> from pyhelpers.dirs import cd, delete_dir
            >>> import os
            >>> bdl = BaseDownloader()
            >>> download_dir = "tests/osm_data"
            >>> filename = "rutland-latest.osm.pbf"
            >>> path_to_file = cd(download_dir, filename)
            >>> url = f'https://download.geofabrik.de/europe/united-kingdom/england/{filename}'
            >>> os.path.exists(path_to_file)
            False
            >>> # Download the PBF data of Rutland
            >>> bdl.download_data(url, path_to_file, verbose=True)
            Downloading "rutland-latest.osm.pbf" 100%|██████████| 1.89M/1.89M | 5.64MB/s ...
              Saving "rutland-latest.osm.pbf" to "./tests/osm_data/" ... Done.
            >>> os.path.isfile(path_to_file)
            True
            >>> # Download the data again
            >>> bdl.download_data(url, path_to_file, verbose=True)
            Downloading "rutland-latest.osm.pbf" 100%|██████████| 1.89M/1.89M | 4.91MB/s ...
              Updating "rutland-latest.osm.pbf" in "./tests/osm_data/" ... Done.
            >>> os.path.isfile(path_to_file)
            True
            >>> os.path.relpath(bdl.download_dir)  # (on Windows)
            'tests\\osm_data'
            >>> len(bdl.data_paths)
            1
            >>> os.path.relpath(bdl.data_paths[0])  # (on Windows)
            'tests\\osm_data\\rutland-latest.osm.pbf'
            >>> delete_dir(bdl.download_dir, verbose=True)
            To delete the directory "./tests/osm_data/" (Not empty)
            ? [No]|Yes: yes
            Deleting "./tests/osm_data/" ... Done.
        """

        # Normalize verbosity
        verbose1 = int(verbose) == 1
        verbose2 = int(verbose) == 2

        # Track if file existed before download to prevent deleting existing data on failure
        file_existed = os.path.isfile(path_to_file)

        _check_saving_path(
            path=path_to_file, verbose=verbose2, state_verb=print_state, end=" ... ",
            msg_wrap_limit=msg_wrap_limit)

        try:
            f = io.StringIO()
            with contextlib.redirect_stdout(f):
                download_file_from_url(
                    url=url, path_to_file=path_to_file, verbose=verbose1,
                    print_wrap_limit=msg_wrap_limit, pbar_color=pbar_color, **kwargs)

            out = f.getvalue()

            if out:
                if "Failed" in out and raise_error:
                    raise requests.HTTPError(out)
                else:
                    print(out, end="")

            if verbose2:
                time.sleep(0 if interval is None else interval)
                print("Done.")

        except Exception as e:
            # Only remove if we created it during this failed attempt
            if not file_existed and os.path.isfile(path_to_file):
                os.remove(path_to_file)

            _print_failure_message(
                e, prefix="Failed. Error:", verbose=verbose1, raise_error=raise_error)

            if not raise_error:
                return None

        if path_to_file not in self.data_paths:
            self.data_paths.append(path_to_file)

        if verify_download_dir:
            self.download_dir = os.path.dirname(path_to_file)
        return None
