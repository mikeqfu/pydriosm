"""Test the module :py:mod:`pydriosm.utils`."""

import os
import shutil
import types

import pytest


@pytest.mark.parametrize('mkdir', [False, True])
def test__cdd(mkdir):
    from pydriosm.utils import _cdd

    data_dir = "pytest_pydriosm_data"
    pathname = _cdd(data_dir=data_dir, mkdir=mkdir)
    assert os.path.basename(pathname) == data_dir
    if mkdir:
        os.rmdir(pathname)

    data_dir = "pytest_pydriosm_data\\tests.ext"
    pathname = _cdd(data_dir=data_dir, mkdir=mkdir)
    assert os.path.basename(pathname) == "tests.ext"
    if mkdir:
        shutil.rmtree(os.path.dirname(pathname))


def test_cdd_geofabrik():
    from pydriosm.utils import cdd_geofabrik

    assert os.path.relpath(cdd_geofabrik()) == 'osm_geofabrik'


def test_cdd_bbbike():
    from pydriosm.utils import cdd_bbbike

    assert os.path.relpath(cdd_bbbike()) == 'osm_bbbike'


def test_first_unique():
    from pydriosm.utils import first_unique

    list_example1 = [1, 2, 2, 3, 4, 5, 6, 6, 2, 3, 1, 6]
    assert list(first_unique(list_example1)) == [1, 2, 3, 4, 5, 6]

    list_example2 = [6, 1, 2, 2, 3, 4, 5, 6, 6, 2, 3, 1]
    assert list(first_unique(list_example2)) == [6, 1, 2, 3, 4, 5]


@pytest.mark.parametrize('engine', [None, 'ujson', 'orjson', 'rapidjson', 'json'])
def test_check_json_engine(engine):
    from pydriosm.utils import check_json_engine

    result = check_json_engine(engine)

    assert isinstance(result, types.ModuleType)


def test_remove_osm_file(capfd):
    from pydriosm.utils import remove_osm_file

    path_to_pseudo_pbf_file = os.path.join("tests\\data\\pseudo\\pseudo.osm.pbf")

    remove_osm_file(path_to_pseudo_pbf_file, verbose=True)
    out, err = capfd.readouterr()
    assert 'The file "pseudo.osm.pbf" is not found' in out

    pseudo_dir = os.path.dirname(path_to_pseudo_pbf_file)
    os.makedirs(pseudo_dir)
    f = open(path_to_pseudo_pbf_file, 'w+')

    with pytest.raises(Exception) as e:
        assert os.path.exists(path_to_pseudo_pbf_file)
        remove_osm_file(path_to_pseudo_pbf_file)
        assert "Failed." in str(e.value)

    f.close()

    remove_osm_file(path_to_pseudo_pbf_file, verbose=True)
    out, err = capfd.readouterr()
    assert "Deleting" in out and path_to_pseudo_pbf_file in out
    assert not os.path.exists(path_to_pseudo_pbf_file)

    remove_osm_file(pseudo_dir, verbose=True)
    assert "Deleting" in out and pseudo_dir in out
    assert not os.path.exists(pseudo_dir)


if __name__ == '__main__':
    pytest.main()
