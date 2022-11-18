"""Test the module :py:mod:`pydriosm.reader`."""

import glob
import os
import shutil

import pandas as pd
import pytest
import shapely.geometry
from pyhelpers.store import load_pickle

from pydriosm.reader import PBFReadParse, SHPReadParse, Transformer, _Reader


class TestTransformer:
    test_point_1 = {
        'type': 'Point',
        'coordinates': [-0.5134241, 52.6555853]
    }

    test_point_2 = {
        'type': 'Feature',
        'geometry': {
            'type': 'Point',
            'coordinates': [-0.5134241, 52.6555853]
        },
        'properties': {
            'osm_id': '488432',
            'name': None,
            'barrier': None,
            'highway': None,
            'ref': None,
            'address': None,
            'is_in': None,
            'place': None,
            'man_made': None,
            'other_tags': '"odbl"=>"clean"'
        },
        'id': 488432
    }

    test_collection_1 = {
        'type': 'GeometryCollection',
        'geometries': [
            {'type': 'Point', 'coordinates': [-0.5096176, 52.6605168]},
            {'type': 'Point', 'coordinates': [-0.5097337, 52.6605812]}
        ]
    }

    test_collection_2 = {
        'type': 'Feature',
        'geometry': {
            'type': 'GeometryCollection',
            'geometries': [
                {'type': 'Point', 'coordinates': [-0.5096176, 52.6605168]},
                {'type': 'Point', 'coordinates': [-0.5097337, 52.6605812]}]
        },
        'properties': {
            'osm_id': '256254',
            'name': 'Fife Close',
            'type': 'site',
            'other_tags': '"naptan:StopAreaCode"=>"270G02701525"'
        },
        'id': 256254
    }

    def test_point_as_polygon(self):
        geometry = {
            'type': 'MultiPolygon',
            'coordinates': [[[[-0.6920145, 52.6753268], [-0.6920145, 52.6753268]]]]
        }
        mp_coords = geometry['coordinates']

        mp_coords_ = Transformer.point_as_polygon(mp_coords)
        assert mp_coords_ == [
            [[[-0.6920145, 52.6753268],
              [-0.6920145, 52.6753268],
              [-0.6920145, 52.6753268]]]]

    def test_transform_unitary_geometry(self):
        g1_dat = self.test_point_1.copy()
        g1_data = Transformer.transform_unitary_geometry(g1_dat)
        assert type(g1_data) == shapely.geometry.Point
        assert g1_data.wkt == 'POINT (-0.5134241 52.6555853)'

        g2_dat = self.test_point_2.copy()
        g2_data = Transformer.transform_unitary_geometry(g2_dat, mode=2)

        assert type(g2_data) == dict

        assert list(g2_data.keys()) == ['type', 'geometry', 'properties', 'id']
        assert g2_data['geometry'] == 'POINT (-0.5134241 52.6555853)'

    def test_transform_geometry_collection(self):
        g1_dat_ = self.test_collection_1.copy()
        g1_dat = g1_dat_['geometries']
        g1_data = Transformer.transform_geometry_collection(g1_dat)
        assert type(g1_data) == shapely.geometry.base.HeterogeneousGeometrySequence
        assert shapely.geometry.GeometryCollection(list(g1_data)).wkt == \
               'GEOMETRYCOLLECTION (POINT (-0.5096176 52.6605168), POINT (-0.5097337 52.6605812))'

        g2_dat = self.test_collection_2.copy()
        g2_data = Transformer.transform_geometry_collection(g2_dat, mode=2)
        assert type(g2_data) == dict
        assert list(g2_data.keys()) == ['type', 'geometry', 'properties', 'id']
        assert g2_data['geometry'] == \
               'GEOMETRYCOLLECTION (POINT (-0.5096176 52.6605168), POINT (-0.5097337 52.6605812))'

    def test_transform_geometry(self):
        lyr_name = 'points'
        dat_ = self.test_point_2.copy()

        lyr_data = pd.DataFrame.from_dict(dat_, orient='index').T

        geom_dat = Transformer.transform_geometry(layer_data=lyr_data, layer_name=lyr_name)
        assert isinstance(geom_dat, pd.Series)
        assert geom_dat.values[0].wkt == 'POINT (-0.5134241 52.6555853)'

    def test_transform_other_tags(self):
        other_tags_dat = Transformer.transform_other_tags(other_tags='"odbl"=>"clean"')
        assert other_tags_dat == {'odbl': 'clean'}

    def test_update_other_tags(self):
        prop_dat = {
            'properties': {
                'osm_id': '488432',
                'name': None,
                'barrier': None,
                'highway': None,
                'ref': None,
                'address': None,
                'is_in': None,
                'place': None,
                'man_made': None,
                'other_tags': '"odbl"=>"clean"'
            },
        }
        prop_dat_ = Transformer.update_other_tags(prop_dat['properties'])
        assert prop_dat_ == {
            'osm_id': '488432',
            'name': None,
            'barrier': None,
            'highway': None,
            'ref': None,
            'address': None,
            'is_in': None,
            'place': None,
            'man_made': None,
            'other_tags': {'odbl': 'clean'}
        }


class TestPBFReadParse:
    path_to_osm_pbf = "tests\\data\\rutland\\rutland-latest.osm.pbf"

    def test_get_pbf_layer_geom_types(self):
        pbf_layer_geom_dict = PBFReadParse.get_pbf_layer_geom_types(shape_name=True)
        assert pbf_layer_geom_dict == {
            'points': 'Point',
            'lines': 'LineString',
            'multilinestrings': 'MultiLineString',
            'multipolygons': 'MultiPolygon',
            'other_relations': 'GeometryCollection'}

    @pytest.mark.parametrize('layer_name', ['points', 'other_relations'])
    @pytest.mark.parametrize('dat_id', [1, 2])
    @pytest.mark.parametrize('parse_geometry', [True, False])
    @pytest.mark.parametrize('parse_properties', [True, False])
    @pytest.mark.parametrize('parse_other_tags', [True, False])
    def test_transform_pbf_layer_field(self, layer_name, dat_id, parse_geometry, parse_properties,
                                       parse_other_tags):
        layer_data = load_pickle(f"tests\\data\\rutland\\{layer_name}_{dat_id}.pkl")
        lyr_dat = PBFReadParse.transform_pbf_layer_field(layer_data=layer_data, layer_name=layer_name)

        assert isinstance(lyr_dat, (pd.Series, pd.DataFrame))

    @pytest.mark.parametrize('readable', [False, True])
    @pytest.mark.parametrize('expand', [False, True])
    @pytest.mark.parametrize('number_of_chunks', [None, 5])
    def test_read_pbf(self, readable, expand, number_of_chunks):
        rutland_pbf = PBFReadParse.read_pbf(
            pbf_pathname=self.path_to_osm_pbf,
            readable=readable,
            expand=expand,
            number_of_chunks=number_of_chunks)

        assert isinstance(rutland_pbf, dict)
        assert list(rutland_pbf.keys()) == [
            'points', 'lines', 'multilinestrings', 'multipolygons', 'other_relations']


class TestSHPReadParse:
    path_to_shp_zip = "tests\\data\\rutland\\rutland-latest-free.shp.zip"
    extract_to_dir = "tests\\data\\rutland\\temp"

    def test_validate_shp_layer_names(self):
        assert SHPReadParse.validate_shp_layer_names(None) == []
        assert SHPReadParse.validate_shp_layer_names('point') == ['points']
        assert SHPReadParse.validate_shp_layer_names(['point', 'land']) == ['points', 'landuse']
        assert len(SHPReadParse.validate_shp_layer_names('all')) >= 13

    def test_find_shp_layer_name(self):
        assert SHPReadParse.find_shp_layer_name("") is None
        assert SHPReadParse.find_shp_layer_name("gis_osm_railways_free_1.shp") == 'railways'
        assert SHPReadParse.find_shp_layer_name("gis_osm_transport_a_free_1.shp") == 'transport'

    def test_unzip_shp_zip(self):
        rutland_shp_dir = SHPReadParse.unzip_shp_zip(
            self.path_to_shp_zip, extract_to=self.extract_to_dir, layer_names='railways',
            verbose=True, ret_extract_dir=True)
        assert rutland_shp_dir == self.extract_to_dir

        lyr_names = ['railways', 'transport', 'traffic']
        dirs_of_layers = SHPReadParse.unzip_shp_zip(
            self.path_to_shp_zip, extract_to=self.extract_to_dir, layer_names=lyr_names,
            separate=True, verbose=2, ret_extract_dir=True)
        assert os.path.relpath(os.path.commonpath(dirs_of_layers)) == self.extract_to_dir
        assert all(x in lyr_names for x in map(os.path.basename, dirs_of_layers))

        rutland_shp_dir = SHPReadParse.unzip_shp_zip(
            self.path_to_shp_zip, extract_to=self.extract_to_dir, ret_extract_dir=True, verbose=True)
        layer_names = set(
            filter(None, map(SHPReadParse.find_shp_layer_name, os.listdir(rutland_shp_dir))))
        assert all(x in SHPReadParse.LAYER_NAMES for x in layer_names)

    def test_read_shp(self):
        rutland_shp_dir = SHPReadParse.unzip_shp_zip(
            self.path_to_shp_zip, extract_to=self.extract_to_dir, ret_extract_dir=True)
        path_to_railways_shp = glob.glob(os.path.join(rutland_shp_dir, "*railways*.shp"))[0]

        rutland_railways = SHPReadParse.read_shp(path_to_railways_shp)
        assert isinstance(rutland_railways, pd.DataFrame)

        rutland_railways = SHPReadParse.read_shp(path_to_railways_shp, emulate_gpd=True)
        assert isinstance(rutland_railways, pd.DataFrame)

        rutland_railways_ = SHPReadParse.read_shp(path_to_railways_shp, engine='geopandas')

        railways_data = [rutland_railways, rutland_railways_]
        geom1, geom2 = map(lambda x: x['geometry'].map(lambda y: y.wkt), railways_data)
        assert geom1.equals(geom2)

    def test_read_layer_shps(self):
        rutland_shp_dir = SHPReadParse.unzip_shp_zip(
            self.path_to_shp_zip, extract_to=self.extract_to_dir, ret_extract_dir=True)
        rutland_railways_shp_path = os.path.join(rutland_shp_dir, "gis_osm_railways_free_1.shp")

        london_railways_shp = SHPReadParse.read_layer_shps(shp_pathnames=rutland_railways_shp_path)
        assert isinstance(london_railways_shp, pd.DataFrame)

        railways_rail_shp, railways_rail_shp_path = SHPReadParse.read_layer_shps(
            rutland_railways_shp_path, feature_names='rail', save_feat_shp=True,
            ret_feat_shp_path=True)
        assert isinstance(railways_rail_shp, pd.DataFrame)
        assert all(os.path.isfile(x) for x in railways_rail_shp_path)

        shutil.rmtree(self.extract_to_dir)


class TestReader:

    def test_init(self):
        r = _Reader()

        assert r.NAME == 'OSM Reader'
        assert isinstance(r.SHP, type) and r.SHP == SHPReadParse
    
    def test_cdd(self):
        assert os.path.relpath(_Reader.cdd()) == 'osm_data'

    # noinspection PyTypeChecker
    def test_data_dir(self):
        from pydriosm.downloader import GeofabrikDownloader, BBBikeDownloader

        r = _Reader()
        assert os.path.relpath(r.data_dir) == 'osm_data'

        r = _Reader(downloader=GeofabrikDownloader)
        assert os.path.relpath(r.data_dir) == 'osm_data\\geofabrik'

        r = _Reader(downloader=BBBikeDownloader)
        assert os.path.relpath(r.data_dir) == 'osm_data\\bbbike'
        
    def test_data_paths(self):
        r = _Reader()
        assert r.data_paths == []


if __name__ == '__main__':
    pytest.main()
