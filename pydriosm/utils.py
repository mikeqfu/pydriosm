"""
Provide various helper functions for use across the package.
"""

import importlib.resources
import os
import re
import shutil
from pathlib import Path

import pandas as pd
from pyhelpers._cache import _check_dependencies, _check_relative_pathname, _print_failure_message
from pyhelpers.dirs import cd
from pyhelpers.text import find_similar_str


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
        if engine not in valid_mod_names:
            raise ValueError(f"`engine` must be on one of {valid_mod_names}.")
        engine_ = _check_dependencies(engine)

    else:
        engine_ = _check_dependencies('json')

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

        >>> path_to_pseudo_pbf_file = cd('tests/pseudo.osm.pbf')
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
            print('The file "{}" is not found at {}.'.format(*os.path.split(path_to_file)[::-1]))

    else:
        if verbose:
            print(f'Deleting "{_check_relative_pathname(path_to_file)}"', end=" ... ")

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
            _print_failure_message(e, prefix="Failed. Error:")


# ==================================================================================================
# Data directories
# ==================================================================================================

def _cdd(*sub_dir, data_dir="data", mkdir=False, **kwargs):
    """
    Specifies a directory or file path within the package's data directory.

    This function automatically suffixes filenames based on the installed Pandas major version.

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

    # Initialize base path
    base_path = Path(str(importlib.resources.files(__package__).joinpath(data_dir)))

    # Build the full path
    full_path = base_path.joinpath(*sub_dir)

    # Add Pandas version suffix to the filename if it is a file
    if full_path.suffix:
        ext = "".join(full_path.suffixes)
        file_stem = full_path.name.replace(ext, '')

        if ext.startswith((".pkl", ".pickle")):
            pandas_major = pd.__version__.split(".")[0]
            suffix = f"-v{pandas_major}"
        else:
            suffix = ""

        # Insert suffix before the extension (e.g., 'cities.pkl' -> 'cities_v3.pkl')
        full_path = full_path.with_name(f"{file_stem}{suffix}{ext}")

    # Handle directory creation
    if mkdir:
        target_dir = full_path.parent if full_path.suffix else full_path
        target_dir.mkdir(parents=True, exist_ok=True, **kwargs)

    return str(full_path)


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
# Data processing utilities
# ==================================================================================================

def get_layer_name(stem):
    """
    Extract the core OSM layer name from a file stem or layer string.

    Uses a regular expression to strip Geofabrik-specific prefixes (``gis_osm_``)
    and suffixes (``_a_free_1``, ``_free``) to return a clean category name.

    :param stem: File stem of a shapefile or a raw layer name from a GeoPackage.
    :type stem: str
    :return: The cleaned layer name (e.g., 'waterways'), or ``None`` if no match is found.
    :rtype: str | None

    **Examples**::

        >>> from pydriosm.utils import get_layer_name
        >>> get_layer_name("") is None
        True
        >>> get_layer_name("gis_osm_railways_free_1.shp")
        'railways'
        >>> get_layer_name("gis_osm_transport_a_free_1")
        'transport'
        >>> get_layer_name("gis_osm_protected_areas_a_free")
        'protected_areas'
        >>> get_layer_name("gis_osm_water_a_free")
        'water'
    """

    if not stem:
        return None

    # The pattern captures everything between 'gis_osm_' and the suffix,
    # then specifically strips the '_a' if it is there.
    # pattern = re.compile(r'gis_osm_(.*?)_?a?_free_1(?:\.[a-z0-9]+)?$', re.IGNORECASE)
    pattern = re.compile(r'^gis_osm_(.*?)(?=_?a?_free)(_1)?', re.IGNORECASE)
    match = re.search(pattern, stem)

    if match:
        return match.group(1)

    return None


def find_matched_layer_names(layer_names, available_layer_names, cutoff=0.4):
    """
    Find corresponding OSM layer names by identifying common semantic roots.

    This function attempts to match input strings to a list of available layer names
    by extracting the core "root" of the word (e.g., stripping Geofabrik prefixes
    and plural suffixes). If no direct root match is found, it falls back to
    fuzzy string matching.

    :param layer_names: One or more layer names to search for.
    :type layer_names: str | list
    :param available_layer_names: A list of valid layer names (e.g., from a GeoPackage).
    :type available_layer_names: list | collections.abc.Iterable
    :param cutoff: Similarity threshold for the fuzzy match fallback; defaults to ``0.4``.
    :type cutoff: float
    :return: A list of unique matched layer names.
    :rtype: list

    **Examples**::

        >>> from pydriosm.utils import find_matched_layer_names
        >>> layers = ['gis_osm_water_a_free_1', 'gis_osm_roads_free_1', 'pois']
        >>> find_matched_layer_names('water', layers)
        ['gis_osm_water_a_free_1']
        >>> find_matched_layer_names(['road', 'water'], layers)
        ['gis_osm_roads_free_1', 'gis_osm_water_a_free_1']
    """

    if not layer_names:
        return []

    input_list = [layer_names] if isinstance(layer_names, str) else list(layer_names)
    results = []

    # Regex to extract the core name (e.g., 'gis_osm_waterways_free_1' -> 'waterways')
    # This also helps strip 'gis_osm_' and '_free' from available layers for better comparison
    core_pattern = re.compile(r"(?:gis_osm_)?([\w]+?)(?:_[asn])?(?:_free.*)?$", re.I)

    def get_root(s):
        match = core_pattern.search(s)
        # We strip the trailing 's' or 'way/ways' to find the common 'water' root
        root = match.group(1).lower() if match else s.lower()
        return re.sub(r'(ways?|s)$', '', root)

    for item in input_list:
        item_root = get_root(item)

        # Match if the item root is in the layer root or vice versa
        matches = [
            layer for layer in available_layer_names
            if item_root in get_root(layer) or get_root(layer) in item_root
        ]

        if matches:
            results.extend(matches)
        else:
            # Fallback to standard fuzzy match for totally different spellings
            fuzzy = find_similar_str(
                item, available_layer_names, n=len(available_layer_names), cutoff=cutoff)
            if fuzzy:
                results.extend([fuzzy] if isinstance(fuzzy, str) else fuzzy)

    return list(dict.fromkeys(results))


def merge_dicts_by_values(data_dict, mapping_dict):
    # noinspection PyShadowingNames
    """
    Group and concatenate DataFrames from a dictionary based on a mapping.

    This utility takes a dictionary of data (e.g., raw layers) and a mapping
    dictionary that defines categories. All DataFrames belonging to the same
    category are concatenated into a single GeoDataFrame/DataFrame.

    :param data_dict: A dictionary where keys match those in ``mapping_dict``
        and values are pandas/geopandas objects.
    :type data_dict: dict
    :param mapping_dict: A dictionary mapping data keys to target category names.
    :type mapping_dict: dict
    :return: A dictionary where keys are categories and values are concatenated
        DataFrames.
    :rtype: dict

    **Examples**::

        >>> from pydriosm.utils import merge_dicts_by_values
        >>> import pandas as pd
        >>> d1 = {'a': pd.DataFrame([1]), 'b': pd.DataFrame([2]), 'c': pd.DataFrame([3])}
        >>> m1 = {'a': 'group_1', 'b': 'group_1', 'c': 'group_2'}
        >>> merged = merge_dicts_by_values(d1, m1)
        >>> merged['group_1']
           0
        0  1
        1  2
    """
    temp_storage = {}

    # Iterate through the mapping
    for key, category in mapping_dict.items():
        if category not in temp_storage:
            temp_storage[category] = []

        # Append the dataframe to the list for that category
        if key in data_dict:
            temp_storage[category].append(data_dict[key])

    # Concatenate the lists of dataframes
    return {
        category: pd.concat(dfs, ignore_index=True) if len(dfs) > 1 else dfs[0]
        for category, dfs in temp_storage.items()
    }
