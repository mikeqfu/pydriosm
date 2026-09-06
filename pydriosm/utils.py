"""
Provide various helper functions for use across the package.
"""

import importlib.resources
import os
import re
import shutil
import typing
from pathlib import Path

import pandas as pd
from pyhelpers._cache import _check_dependencies, _get_relative_path, _print_failure_message
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
    # noinspection unresolved-references
    """
    Remove a downloaded OpenStreetMap (OSM) data file or directory.

    This function deletes a specified file or directory if it exists on disk.
    When verbosity is enabled, progress and completion status are printed.

    :param path_to_file: Absolute or relative path to an OSM data file or directory.
    :type path_to_file: str | pathlib.Path
    :param verbose: Whether to print progress messages. Defaults to ``True``.
    :type verbose: bool | int
    :return: ``None``
    :rtype: None

    **Examples**::

        >>> from pydriosm.utils import remove_osm_file
        >>> from pyhelpers.dirs import cd

        >>> pseudo_pbf_file_path = cd('tests', 'pseudo.osm.pbf')

        >>> try:
        ...     pseudo_pbf_file_path.touch(exist_ok=True)
        ... except OSError:
        ...     print('Failed to create the file.')
        ... else:
        ...     print('File created successfully.')
        File created successfully.

        >>> pseudo_pbf_file_path.is_file()
        True

        >>> remove_osm_file(pseudo_pbf_file_path, verbose=True)
        Deleting "tests/pseudo.osm.pbf" ... Done.

        >>> pseudo_pbf_file_path.is_file()
        False
    """

    path = Path(path_to_file) if not isinstance(path_to_file, Path) else path_to_file

    if not path.exists():
        if verbose:
            print(f'The file "{path.name}" was not found at "{path.parent}".')
        return

    if verbose:
        rel_file_path_str = _get_relative_path(path, as_str=True, quoted=True)
        print(f"Deleting {rel_file_path_str}", end=" ... ")

    try:
        if path.is_file() or path.is_symlink():
            path.unlink()
            if verbose:
                print("Done.")

        elif path.is_dir():
            shutil.rmtree(path)
            if verbose:
                print("Done.")

    except Exception as e:
        _print_failure_message(e, prefix="Failed. Error:")


# ==================================================================================================
# Data directories
# ==================================================================================================

def _cdd(*sub_dir, data_dir="data", mkdir=False, **kwargs):
    """
    Construct a path to a directory or file within the package data directory.

    This function automatically suffixes pickle file names based on the installed
    Pandas major version to prevent binary incompatibility across major releases.

    :param sub_dir: Directory or file path components relative to ``data_dir``.
    :type sub_dir: str | pathlib.Path | os.PathLike
    :param data_dir: Name of the root data directory. Defaults to ``"data"``.
    :type data_dir: str | pathlib.Path | os.PathLike
    :param mkdir: Whether to create the target directory on disk. Defaults to ``False``.
    :type mkdir: bool
    :param kwargs: Optional keyword arguments passed to ``pathlib.Path.mkdir``.
    :type kwargs: Any
    :return: Absolute path to the specified directory or file under ``data_dir``.
    :rtype: pathlib.Path

    .. _`pathlib.Path.mkdir`: https://docs.python.org/3/library/pathlib.html#pathlib.Path.mkdir

    **Example**::

        >>> from pydriosm.utils import _cdd
        >>> from pyhelpers.dirs import get_relative_path

        >>> dat_dir_path = _cdd(data_dir="data")
        >>> get_relative_path(dat_dir_path, as_str=True)
        'pydriosm/data'
    """

    # Initialize base path
    top_package = __package__.split('.')[0] if __package__ else 'pydriosm'
    traversable_pkg = importlib.resources.files(top_package)
    base_path = Path(traversable_pkg).joinpath(data_dir)

    # Build the full path
    full_path = base_path.joinpath(*sub_dir)

    # Add Pandas version suffix to the filename if it is a file
    if full_path.suffix:
        ext = "".join(full_path.suffixes)
        file_stem = full_path.name.removesuffix(ext)

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

    return full_path


def cdd_geofabrik(*sub_dir, mkdir=False, default_dir="osm_geofabrik", **kwargs):
    """
    Construct a path to the Geofabrik data directory or its subdirectories.

    This function resolves directory and file paths within the designated Geofabrik
    data storage location, creating directories on disk when requested.

    :param sub_dir: Subdirectory names or filename relative to ``default_dir``.
    :type sub_dir: str | pathlib.Path | os.PathLike
    :param mkdir: Whether to create the target directory on disk. Defaults to ``False``.
    :type mkdir: bool
    :param default_dir: Name of the root directory for Geofabrik downloads.
        Defaults to ``"osm_geofabrik"``.
    :type default_dir: str | pathlib.Path | os.PathLike
    :param kwargs: Optional keyword arguments passed to ``pyhelpers.dir.cd()``.
    :type kwargs: Any
    :return: Absolute path to the directory or file under ``default_dir``.
    :rtype: pathlib.Path

    .. _`pyhelpers.dir.cd()`:
        https://pyhelpers.readthedocs.io/en/latest/_generated/pyhelpers.dir.cd.html

    **Examples**::

        >>> from pydriosm.utils import cdd_geofabrik

        >>> path = cdd_geofabrik()
        >>> path.name
        'osm_geofabrik'
    """

    return cd(default_dir, *sub_dir, mkdir=mkdir, **kwargs)


def cdd_bbbike(*sub_dir, mkdir=False, default_dir="osm_bbbike", **kwargs):
    """
    Construct a path to the BBBike data directory or its subdirectories.

    This function resolves directory and file paths within the designated BBBike
    data storage location, creating directories on disk when requested.

    :param sub_dir: Subdirectory names or filename relative to ``default_dir``.
    :type sub_dir: str | pathlib.Path | os.PathLike
    :param mkdir: Whether to create the target directory on disk. Defaults to ``False``.
    :type mkdir: bool
    :param default_dir: Name of the root directory for BBBike downloads.
        Defaults to ``"osm_bbbike"``.
    :type default_dir: str | pathlib.Path | os.PathLike
    :param kwargs: Optional keyword arguments passed to ``pyhelpers.dir.cd()``.
    :type kwargs: Any
    :return: Absolute path to the directory or file under ``default_dir``.
    :rtype: pathlib.Path

    .. _`pyhelpers.dir.cd()`:
        https://pyhelpers.readthedocs.io/en/latest/_generated/pyhelpers.dir.cd.html

    **Examples**::

        >>> from pydriosm.utils import cdd_bbbike

        >>> path = cdd_bbbike()
        >>> path.name
        'osm_bbbike'
    """

    return cd(default_dir, *sub_dir, mkdir=mkdir, **kwargs)


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
    core_pattern = re.compile(r"(?:gis_osm_)?(\w+?)(?:_[asn])?(?:_free.*)?$", re.I)

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
    # noinspection PyShadowingNames,stub-packages-advertiser
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
