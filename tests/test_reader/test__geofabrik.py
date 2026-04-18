import pandas as pd
import pytest
from pyhelpers._cache import _check_dependencies

from pydriosm.reader._geofabrik import GeofabrikReader


class TestGeofabrikReader:

    @pytest.fixture(scope='class')
    def gfr(self):
        # gfr = GeofabrikReader()
        return GeofabrikReader()

    @pytest.mark.parametrize('readable', [True, False])
    @pytest.mark.parametrize('parse_geometry', [True, False])
    @pytest.mark.parametrize('parse_properties', [True, False])
    @pytest.mark.parametrize('parse_other_tags', [True, False])
    def test_read_pbf(self, gfr, capfd, tmp_path, readable, parse_geometry, parse_properties,
                      parse_other_tags):
        # import tempfile; tmp_path = tempfile.mkdtemp()
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

        layer_names = {'points', 'lines', 'multilinestrings', 'multipolygons', 'other_relations'}
        assert set(pbf_data.keys()) == layer_names

        test_points = pbf_data.get('points')
        assert isinstance(test_points, (list, pd.Series))
        test_point = test_points[0]

        if readable:
            geom, prop = test_point.get('geometry'), test_point.get('properties')
            assert isinstance(prop, dict)
            other_tags = prop.get('other_tags')

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

    @pytest.mark.parametrize('layer_names', [None, 'railways', ['traffic', 'water']])
    def test_read_gpkg(self, gfr, layer_names, capfd, tmp_path):
        # import tempfile; tmp_path = tempfile.mkdtemp()
        subregion_name = 'rutland'

        gpkg_data = gfr.read_gpkg(
            subregion_name,
            layer_names=layer_names,
            data_dir=tmp_path,
            download=True,
            verbose=True
        )
        out, _ = capfd.readouterr()
        assert "Parsing the data ... Done." in out

        assert isinstance(gpkg_data, dict)

        if layer_names == 'railways':
            assert layer_names in gpkg_data
            assert len(gpkg_data) == 1
        elif layer_names == ['traffic', 'water']:
            assert all(x in gpkg_data.keys() for x in layer_names)


if __name__ == '__main__':
    pytest.main()
