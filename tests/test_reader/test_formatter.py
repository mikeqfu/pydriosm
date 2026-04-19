import pandas as pd
import pytest
import shapely.geometry
import shapely.wkb

from pydriosm.reader.formatter import convert_geometry_collection, convert_simplex_geometry, \
    process_geometry_layer, reformat_multipolygon_point, reformat_other_tags, refresh_other_tags

TEST_POINT_1 = {
    'type': 'Point',
    'coordinates': [-0.5134241, 52.6555853]
}

TEST_POINT_2 = {
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

TEST_COLLECTION_1 = {
    'type': 'GeometryCollection',
    'geometries': [
        {'type': 'Point', 'coordinates': [-0.5096176, 52.6605168]},
        {'type': 'Point', 'coordinates': [-0.5097337, 52.6605812]}
    ]
}

TEST_COLLECTION_2 = {
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


def test_point_as_polygon():
    geometry = {
        'type': 'MultiPolygon',
        'coordinates': [[[[-0.6920145, 52.6753268], [-0.6920145, 52.6753268]]]]
    }
    mp_coords = geometry['coordinates']

    mp_coords_ = reformat_multipolygon_point(mp_coords)
    assert mp_coords_ == [
        [[[-0.6920145, 52.6753268],
          [-0.6920145, 52.6753268],
          [-0.6920145, 52.6753268]]]]


def test_transform_unitary_geometry():
    g1_dat = TEST_POINT_1.copy()
    g1_data = convert_simplex_geometry(g1_dat)
    assert isinstance(g1_data, shapely.geometry.Point)
    assert g1_data.wkt == 'POINT (-0.5134241 52.6555853)'

    g2_dat = TEST_POINT_2.copy()
    g2_data = convert_simplex_geometry(g2_dat, mode=2)

    assert isinstance(g2_data, dict)
    assert set(g2_data.keys()) == {'type', 'geometry', 'properties', 'id'}
    assert isinstance(g2_data['geometry'], bytes)
    assert shapely.wkb.loads(g2_data['geometry']).wkt == 'POINT (-0.5134241 52.6555853)'


def test_transform_geometry_collection():
    g1_dat_ = TEST_COLLECTION_1.copy()
    g1_dat = g1_dat_['geometries']
    g1_data = convert_geometry_collection(g1_dat)
    assert isinstance(g1_data, shapely.geometry.base.BaseGeometry)
    assert (g1_data.wkt ==
            'GEOMETRYCOLLECTION (POINT (-0.5096176 52.6605168), POINT (-0.5097337 52.6605812))')

    g2_dat = TEST_COLLECTION_2.copy()
    g2_data = convert_geometry_collection(g2_dat, mode=2)
    assert isinstance(g2_data, dict)
    assert set(g2_data.keys()) == {'type', 'geometry', 'properties', 'id'}
    assert isinstance(g2_data['geometry'], bytes)
    assert (shapely.wkb.loads(g2_data['geometry']).wkt ==
            'GEOMETRYCOLLECTION (POINT (-0.5096176 52.6605168), POINT (-0.5097337 52.6605812))')


def test_transform_geometry():
    lyr_name = 'points'
    dat_ = TEST_POINT_2.copy()

    lyr_data = pd.DataFrame.from_dict(dat_, orient='index').T

    geom_dat = process_geometry_layer(layer_data=lyr_data, layer_name=lyr_name)
    assert isinstance(geom_dat, pd.Series)
    assert geom_dat.values[0].wkt == 'POINT (-0.5134241 52.6555853)'


def test_transform_other_tags():
    other_tags_dat = reformat_other_tags(other_tags='"odbl"=>"clean"')
    assert other_tags_dat == {'odbl': 'clean'}


def test_update_other_tags():
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
    prop_dat_ = refresh_other_tags(prop_dat['properties'])
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


if __name__ == '__main__':
    pytest.main()
