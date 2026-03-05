import pytest
from pyhelpers._cache import _check_dependencies

from pydriosm.reader._geofabrik import GeofabrikReader


class TestGeofabrikReader:

    @pytest.fixture(scope='class')
    def gfr(self):
        # gfr = GeofabrikReader()
        return GeofabrikReader()

    @pytest.fixture(scope='class')
    def data_dir(self):
        # data_dir = "tests/osm_data"
        return "tests/osm_data"

    @pytest.mark.parametrize('readable', [True, False])
    @pytest.mark.parametrize('expand', [True, False])
    @pytest.mark.parametrize('parse_geometry', [True, False])
    @pytest.mark.parametrize('parse_properties', [True, False])
    @pytest.mark.parametrize('parse_other_tags', [True, False])
    def test_read_pbf(self, gfr, data_dir, capfd, tmp_path, expand, readable, parse_geometry,
                      parse_properties, parse_other_tags):
        # import tempfile
        # tmp_path = tempfile.TemporaryDirectory().name

        subregion_name = 'rutland'

        pbf_data = gfr.read_pbf(
            subregion_name,
            data_dir=tmp_path,
            readable=readable,
            parse_geometry=parse_geometry,
            parse_properties=parse_properties,
            parse_other_tags=parse_other_tags,
            verbose=True
        )

        assert isinstance(pbf_data, dict)

        layer_names = ['points', 'lines', 'multilinestrings', 'multipolygons', 'other_relations']
        assert list(pbf_data.keys()) == layer_names

        test_point = pbf_data.get('points')[0]

        if readable:
            geom, prop = test_point.get('geometry'), test_point.get('properties')
            other_tags = prop.get('other_tags')

            assert isinstance(test_point, dict)

            if parse_geometry:
                assert geom.startswith('POINT')
                if not parse_other_tags:
                    assert other_tags is None or isinstance(other_tags, str)

            elif parse_other_tags:
                assert isinstance(geom, dict)
                assert other_tags is None or isinstance(other_tags, dict)

        else:
            if not (parse_geometry or parse_properties or parse_other_tags):
                osgeo_ogr = _check_dependencies('osgeo.ogr')
                assert isinstance(test_point, osgeo_ogr.Feature)


if __name__ == '__main__':
    pytest.main()
