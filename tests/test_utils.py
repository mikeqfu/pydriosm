"""
Tests the module: :mod:`pydriosm.utils`.
"""

import shutil
import types

import pandas as pd
import pytest
from pyhelpers.dirs import get_relative_path

from pydriosm.utils import _cdd, cdd_bbbike, cdd_geofabrik, check_json_engine, first_unique, \
    remove_osm_file


@pytest.mark.parametrize('mkdir', [False, True])
def test__cdd(mkdir, tmp_path):
    data_dir = tmp_path / "pydriosm_data"
    pathname = _cdd(data_dir=data_dir, mkdir=mkdir)
    assert pathname.name == data_dir.name
    if mkdir:
        pathname.rmdir()

    data_dir = "pydriosm_data/tests.ext"
    pathname = _cdd(data_dir=data_dir, mkdir=mkdir)
    assert pathname.name == "tests.ext"
    if mkdir:
        shutil.rmtree(pathname.parent)

    test_file_path = "pydriosm_data/tests.pkl"
    pathname = _cdd(data_dir=test_file_path, mkdir=False)
    assert pathname.name == f"tests-v{pd.__version__.split(".")[0]}.pkl"


def test_cdd_geofabrik():
    assert get_relative_path(cdd_geofabrik(), as_str=True) == 'osm_geofabrik'


def test_cdd_bbbike():
    assert get_relative_path(cdd_bbbike(), as_str=True) == 'osm_bbbike'


def test_first_unique():
    list_example1 = [1, 2, 2, 3, 4, 5, 6, 6, 2, 3, 1, 6]
    assert list(first_unique(list_example1)) == [1, 2, 3, 4, 5, 6]

    list_example2 = [6, 1, 2, 2, 3, 4, 5, 6, 6, 2, 3, 1]
    assert list(first_unique(list_example2)) == [6, 1, 2, 3, 4, 5]


@pytest.mark.parametrize('engine', [None, 'ujson', 'orjson', 'rapidjson', 'json'])
def test_check_json_engine(engine):
    result = check_json_engine(engine)
    assert isinstance(result, types.ModuleType)


def test_remove_osm_file(tmp_path, capfd):
    """
    Test removing an OSM file and its containing directory.
    """

    pseudo_pbf_file_path = tmp_path / "pseudo.osm.pbf"

    # A missing file should be handled without raising an exception
    remove_osm_file(pseudo_pbf_file_path, verbose=True)
    out, err = capfd.readouterr()
    assert err == ""
    assert 'The file "pseudo.osm.pbf" was not found' in out
    assert not pseudo_pbf_file_path.exists()

    # Create a temporary pseudo-PBF file
    pseudo_pbf_file_path.touch()
    assert pseudo_pbf_file_path.is_file()

    with pytest.raises(Exception) as e:
        remove_osm_file(pseudo_pbf_file_path)
        assert "Failed." in str(e.value)

    remove_osm_file(pseudo_pbf_file_path, verbose=True)
    out, _ = capfd.readouterr()
    assert "Deleting" in out and "Done." in out
    assert not pseudo_pbf_file_path.exists()

    remove_osm_file(pseudo_pbf_file_path, verbose=True)
    assert "Deleting" in out and "Done." in out
    assert not pseudo_pbf_file_path.exists()


if __name__ == '__main__':
    pytest.main()
