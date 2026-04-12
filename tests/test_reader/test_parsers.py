"""
Tests the submodule: :py:mod:`pydriosm.reader.parser`.
"""

import glob
import os

import pandas as pd
import pytest
from pyhelpers.dirs import delete_dir
from pyhelpers.store import load_data

from pydriosm.reader._pbf import PBF
from pydriosm.reader._shp import SHP


class TestPBF:

    @pytest.fixture(scope='class')
    def path_to_pbf(self):
        return "tests/data/rutland/rutland-latest.osm.pbf"

    @staticmethod
    def test_get_layer_geom_types():
        pbf_layer_geom_dict = PBF.get_layer_geom_types(shape_name=True)
        assert pbf_layer_geom_dict == {
            'points': 'Point',
            'lines': 'LineString',
            'multilinestrings': 'MultiLineString',
            'multipolygons': 'MultiPolygon',
            'other_relations': 'GeometryCollection'}

    @staticmethod
    @pytest.mark.parametrize('layer_name', ['points', 'other_relations'])
    @pytest.mark.parametrize('dat_id', [1, 2])
    @pytest.mark.parametrize('parse_geometry', [True, False])
    @pytest.mark.parametrize('parse_properties', [True, False])
    @pytest.mark.parametrize('parse_other_tags', [True, False])
    def test_transform_pbf_layer_field(layer_name, dat_id, parse_geometry, parse_properties,
                                       parse_other_tags):
        path_to_file = f"tests/data/rutland/{layer_name}_{dat_id}.pkl"
        layer_data = load_data(path_to_file)
        lyr_dat = PBF.transform_pbf_layer_field(layer_data=layer_data, layer_name=layer_name)

        assert isinstance(lyr_dat, (pd.Series, pd.DataFrame))

    @pytest.mark.parametrize('readable', [False, True])
    @pytest.mark.parametrize('expand', [False, True])
    @pytest.mark.parametrize('number_of_chunks', [None, 5])
    def test_read_pbf(self, path_to_pbf, readable, expand, number_of_chunks):
        rutland_pbf = PBF.read_pbf(
            path_to_file=path_to_pbf,
            readable=readable,
            expand=expand,
            number_of_chunks=number_of_chunks)

        assert isinstance(rutland_pbf, dict)
        assert set(rutland_pbf.keys()) == {
            'points',
            'lines',
            'multilinestrings',
            'multipolygons',
            'other_relations'
        }


class TestSHP:

    @pytest.fixture(scope='class')
    def path_to_shp_zip(self):
        return "tests/data/rutland/rutland-latest-free.shp.zip"

    @staticmethod
    def test_validate_layer_names():
        assert SHP.validate_layer_names(None) == []
        assert SHP.validate_layer_names('point') == ['points']
        assert SHP.validate_layer_names(['point', 'land']) == ['points', 'landuse']
        assert len(SHP.validate_layer_names('all')) >= 13

    @staticmethod
    def test_get_layer_name():
        assert SHP.get_layer_name("") is None
        assert SHP.get_layer_name("gis_osm_railways_free_1.shp") == 'railways'
        assert SHP.get_layer_name("gis_osm_transport_a_free_1.shp") == 'transport'

    def test_unzip_shp_zip(self, path_to_shp_zip, tmp_path):
        rutland_shp_dir = SHP.unzip_shp_zip(
            path_to_shp_zip, extract_to=tmp_path, layer_names='railways',
            verbose=True, ret_extract_dir=True)
        assert os.path.normpath(rutland_shp_dir) == str(tmp_path)

        lyr_names = ['railways', 'transport', 'traffic']
        dirs_of_layers = SHP.unzip_shp_zip(
            path_to_shp_zip, extract_to=tmp_path, layer_names=lyr_names,
            separate=True, verbose=2, ret_extract_dir=True)
        assert os.path.normpath(os.path.commonpath(dirs_of_layers)) == str(tmp_path)
        assert all(x in lyr_names for x in map(os.path.basename, dirs_of_layers))

        rutland_shp_dir = SHP.unzip_shp_zip(
            path_to_shp_zip, extract_to=tmp_path, ret_extract_dir=True, verbose=True)
        layer_names = set(
            filter(None, map(SHP.get_layer_name, os.listdir(rutland_shp_dir))))
        assert all(x in SHP.LAYER_NAMES for x in layer_names)

    def test_read_shp(self, path_to_shp_zip, tmp_path):
        rutland_shp_dir = SHP.unzip_shp_zip(
            path_to_shp_zip, extract_to=tmp_path, ret_extract_dir=True)
        path_to_railways_shp = glob.glob(os.path.join(rutland_shp_dir, "*railways*.shp"))[0]

        rutland_railways = SHP.read_shp(path_to_railways_shp)
        assert isinstance(rutland_railways, pd.DataFrame)

        rutland_railways = SHP.read_shp(path_to_railways_shp, emulate_gpd=True)
        assert isinstance(rutland_railways, pd.DataFrame)

        rutland_railways_ = SHP.read_shp(path_to_railways_shp, engine='geopandas')

        railways_data = [rutland_railways, rutland_railways_]
        geom1, geom2 = map(lambda x: x['geometry'].map(lambda y: y.wkt), railways_data)
        assert geom1.equals(geom2)

    def test_read_layer_shps(self, path_to_shp_zip, tmp_path):
        rutland_shp_dir = SHP.unzip_shp_zip(
            path_to_shp_zip, extract_to=tmp_path, ret_extract_dir=True)
        rutland_railways_shp_path = os.path.join(rutland_shp_dir, "gis_osm_railways_free_1.shp")

        london_railways_shp = SHP.read_layer_shps(shp_pathnames=rutland_railways_shp_path)
        assert isinstance(london_railways_shp, pd.DataFrame)

        railways_rail_shp, railways_rail_shp_path = SHP.read_layer_shps(
            rutland_railways_shp_path, feature_names='rail', save_feat_shp=True,
            ret_feat_shp_path=True)
        assert isinstance(railways_rail_shp, pd.DataFrame)
        assert all(os.path.isfile(x) for x in railways_rail_shp_path)

        delete_dir(tmp_path, confirmation_required=False)


if __name__ == '__main__':
    pytest.main()
