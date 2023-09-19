"""
Provide various helper functions for use across the package.
"""

import importlib.resources
import os
import shutil

from pyhelpers._cache import _check_dependency, _format_err_msg
from pyhelpers.dirs import cd


# ==================================================================================================
# Data directories
# ==================================================================================================


def _cdd(*sub_dir, data_dir="data", mkdir=False, **kwargs):
    """
    Specify (or change to) a directory (or any subdirectories) for backup data of the package.

    :param sub_dir: [optional] name of a directory; names of directories (and/or a filename)
    :type sub_dir: str | os.PathLike[str]
    :param data_dir: name of a directory to store data, defaults to ``"data"``
    :type data_dir: str | os.PathLike[str]
    :param mkdir: whether to create a directory, defaults to ``False``
    :type mkdir: bool
    :param kwargs: [optional] parameters (e.g. ``mode=0o777``) of `os.makedirs`_
    :return: a full pathname of a directory or a file under the specified data directory ``data_dir``
    :rtype: str

    .. _`os.makedirs`: https://docs.python.org/3/library/os.html#os.makedirs

    **Example**::

        >>> from pydriosm.utils import _cdd
        >>> import os

        >>> path_to_dat_dir = _cdd(data_dir="data")
        >>> os.path.relpath(path_to_dat_dir)
        'pydriosm\\data'
    """

    pathname = importlib.resources.files(__package__).joinpath(data_dir)
    for x in sub_dir:
        pathname = os.path.join(pathname, x)

    if mkdir:
        path_to_file, ext = os.path.splitext(pathname)
        if ext == '':
            os.makedirs(path_to_file, exist_ok=True, **kwargs)
        else:
            os.makedirs(os.path.dirname(pathname), exist_ok=True, **kwargs)

    return pathname


def check_relpath(pathname, start=os.curdir):
    """
    Check and return a relative pathname to the given ``pathname``.

    On Windows, when ``pathname`` and ``start`` are on different drives, the function returns
    the given ``pathname``.

    :param pathname: pathname of a file or a directory
    :type pathname: str | os.PathLike[str]
    :param start: optional start directory,
        defaults to ``os.curdir`` (i.e. the current working directory)
    :type start: str | os.PathLike[str]
    :return: relative pathname to the given ``pathname``
    :type: str | os.PathLike[str]
    """

    try:
        relpath = os.path.relpath(pathname, start=start)
    except ValueError:
        relpath = pathname

    return relpath


def cdd_geofabrik(*sub_dir, mkdir=False, default_dir="osm_geofabrik", **kwargs):
    """
    Change directory to ``osm_geofabrik\\`` and its subdirectories within a package.

    :param sub_dir: name of directory; names of directories (and/or a filename)
    :type sub_dir: str | os.PathLike
    :param mkdir: whether to create a directory, defaults to ``False``
    :type mkdir: bool
    :param default_dir: default folder name of the root directory for downloading data from Geofabrik,
        defaults to ``"osm_geofabrik"``
    :type default_dir: str
    :param kwargs: [optional] parameters of `pyhelpers.dir.cd()`_
    :return: an absolute path to a directory (or a file) under ``data_dir``
    :rtype: str | os.PathLike

    .. _`pyhelpers.dir.cd()`:
        https://pyhelpers.readthedocs.io/en/latest/_generated/pyhelpers.dir.cd.html

    **Examples**::

        >>> from pydriosm.utils import cdd_geofabrik
        >>> import os

        >>> os.path.relpath(cdd_geofabrik())
        'osm_geofabrik'
    """

    pathname = cd(default_dir, *sub_dir, mkdir=mkdir, **kwargs)

    return pathname


def cdd_bbbike(*sub_dir, mkdir=False, default_dir="osm_bbbike", **kwargs):
    """
    Change directory to ``osm_bbbike\\`` and its subdirectories.

    :param sub_dir: name of directory; names of directories (and/or a filename)
    :type sub_dir: str
    :param mkdir: whether to create a directory, defaults to ``False``
    :type mkdir: bool
    :param default_dir: default folder name of the root directory for downloading data from BBBike,
        defaults to ``"osm_bbbike"``
    :type default_dir: str
    :param kwargs: [optional] parameters of `pyhelpers.dir.cd()`_
    :return: an absolute path to a directory (or a file) under ``data_dir``
    :rtype: str

    .. _`pyhelpers.dir.cd()`:
        https://pyhelpers.readthedocs.io/en/latest/_generated/pyhelpers.dir.cd.html

    **Examples**::

        >>> from pydriosm.utils import cdd_bbbike
        >>> import os

        >>> os.path.relpath(cdd_bbbike())
        'osm_bbbike'
    """

    pathname = cd(default_dir, *sub_dir, mkdir=mkdir, **kwargs)

    return pathname


# ==================================================================================================
# General utilities
# ==================================================================================================


def first_unique(iterable):
    """
    Return unique items in an input iterable variable given the same order of presence.

    :param iterable: iterable variable
    :type iterable: typing.Iterable
    :return: unique items in the same order of presence as in the input
    :rtype: typing.Generator[list]

    **Examples**::

        >>> from pydriosm.utils import first_unique

        >>> list_example1 = [1, 2, 2, 3, 4, 5, 6, 6, 2, 3, 1, 6]
        >>> list(first_unique(list_example1))
        [1, 2, 3, 4, 5, 6]

        >>> list_example2 = [6, 1, 2, 2, 3, 4, 5, 6, 6, 2, 3, 1]
        >>> list(first_unique(list_example2))
        [6, 1, 2, 3, 4, 5]
    """

    checked_list = []

    for x in iterable:
        if x not in checked_list:
            checked_list.append(x)
            yield x


def check_json_engine(engine=None):
    """
    Check an available module used for loading JSON data.

    :param engine: name of a module for loading JSON data;
        when ``engine=None`` (default), use the built-in
        `json <https://docs.python.org/3/library/json.html>`_ module;
    :type engine: str | None
    :return: the module for loading JSON data
    :type: types.ModuleType | None

    **Examples**::

        >>> from pydriosm.utils import check_json_engine
        >>> import types

        >>> result = check_json_engine()

        >>> isinstance(result, types.ModuleType)
        True
        >>> result.__name__ == 'json'
        True
    """

    if engine is not None:
        valid_mod_names = {'ujson', 'orjson', 'rapidjson', 'json'}
        assert engine in valid_mod_names, f"`engine` must be on one of {valid_mod_names}."
        engine_ = _check_dependency(name=engine)

    else:
        engine_ = _check_dependency(name='json')

    return engine_


def remove_osm_file(path_to_file, verbose=True):
    """
    Remove a downloaded OSM data file.

    :param path_to_file: absolute path to a downloaded OSM data file
    :type path_to_file: str
    :param verbose: defaults to ``True``
    :type verbose: bool

    **Examples**::

        >>> from pydriosm.utils import remove_osm_file
        >>> from pyhelpers.dirs import cd
        >>> import os

        >>> path_to_pseudo_pbf_file = cd('tests\\pseudo.osm.pbf')
        >>> try:
        ...     open(path_to_pseudo_pbf_file, 'a').close()
        ... except OSError:
        ...     print('Failed to create the file.')
        ... else:
        ...     print('File created successfully.')
        File created successfully.

        >>> os.path.exists(path_to_pseudo_pbf_file)
        True

        >>> remove_osm_file(path_to_pseudo_pbf_file, verbose=True)
        Deleting "tests\\pseudo.osm.pbf" ... Done.

        >>> os.path.exists(path_to_pseudo_pbf_file)
        False
    """

    if not os.path.exists(path_to_file):
        if verbose:
            print("The file \"{}\" is not found at {}.".format(*os.path.split(path_to_file)[::-1]))

    else:
        if verbose:
            print(f"Deleting \"{check_relpath(path_to_file)}\"", end=" ... ")

        try:
            if os.path.isfile(path_to_file):
                os.remove(path_to_file)
                if verbose:
                    print("Done.")

            elif os.path.isdir(path_to_file):
                shutil.rmtree(path_to_file)
                if verbose:
                    print("Done.")

        except Exception as e:
            print(f"Failed. {_format_err_msg(e)}")
