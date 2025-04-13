import pytest
from pyhelpers._cache import _check_dependency

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
        assert list(pbf_data.keys()) == [
            'points', 'lines', 'multilinestrings', 'multipolygons', 'other_relations']

        if readable:
            assert isinstance(pbf_data['points'][0], dict)

            if parse_geometry:
                assert pbf_data['points'][0]['geometry'] == 'POINT (-0.5134241 52.6555853)'
                if not parse_other_tags:
                    assert pbf_data['points'][0]['properties']['other_tags'] == '"odbl"=>"clean"'

            elif parse_other_tags:
                assert isinstance(pbf_data['points'][0]['geometry'], dict)
                assert isinstance(pbf_data['points'][0]['properties']['other_tags'], dict)

        else:
            if not (parse_geometry or parse_properties or parse_other_tags):
                osgeo_ogr = _check_dependency('osgeo.ogr')
                assert isinstance(pbf_data['points'][0], osgeo_ogr.Feature)


if __name__ == '__main__':
    pytest.main()
