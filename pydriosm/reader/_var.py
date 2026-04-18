import lzma
import multiprocessing

import numpy as np
import pandas as pd

from pydriosm.reader.formatter import convert_simplex_geometry
from pydriosm.utils import check_json_engine


class VAR:
    """
    Read/parse OSM data of various formats (other than PBF and Shapefile).
    """

    # == .osm.bz2 / .bz2 =========================================================================

    @classmethod
    def _read_osm_bz2(cls, bz2_pathname):
        """
        (To be developed...)

        :param bz2_pathname:
        :return:
        """
        import bz2
        # import xml.etree.ElementTree

        bz2_file = open(bz2_pathname, 'rb')

        bz2d = bz2.BZ2Decompressor()
        raw = b'' + bz2d.decompress(bz2_file.read())
        data = raw.split(b'\n')

        return data

    # == .csv.xz =================================================================================

    @classmethod
    def _prep_csv_xz(cls, x):
        y = x.rstrip('\t\n').split('\t')
        return y

    @classmethod
    def read_csv_xz(cls, path_to_file, col_names=None):
        """
        Read/parse a compressed CSV (.csv.xz) data file.

        :param path_to_file: path to a .csv.xz data file
        :type path_to_file: str
        :param col_names: column names of .csv.xz data, defaults to ``None``
        :type col_names: list | None
        :return: tabular data of the CSV file
        :rtype: pandas.DataFrame

        See examples for the method
        :meth:`BBBikeReader.read_csv_xz()<pydriosm.reader.BBBikeReader.read_csv_xz>`.
        """

        if col_names is None:
            col_names = ['type', 'id', 'feature', 'note']

        with lzma.open(path_to_file, mode='rt', encoding='utf-8') as f:
            with multiprocessing.Pool(processes=multiprocessing.cpu_count() - 1) as p:
                csv_xz = pd.DataFrame.from_records(
                    p.map(cls._prep_csv_xz, f.readlines()), columns=col_names)

        object_cols = csv_xz.select_dtypes(include=['object', 'string']).columns
        csv_xz[object_cols] = csv_xz[object_cols].replace({np.nan: None})

        return csv_xz

    # == .geojson.xz =============================================================================

    @classmethod
    def read_geojson_xz(cls, path_to_file, engine=None, parse_geometry=False):
        """
        Read/parse a compressed Osmium GeoJSON (.geojson.xz) data file.

        :param path_to_file: path to a .geojson.xz data file
        :type path_to_file: str
        :param engine: an open-source Python package for JSON serialization, defaults to ``None``;
            when ``engine=None``, it refers to the built-in `json`_ module;
            otherwise options include: ``'ujson'`` (for `UltraJSON`_),
            ``'orjson'`` (for `orjson`_) and ``'rapidjson'`` (for `python-rapidjson`_)
        :type engine: str | None
        :param parse_geometry: whether to reformat coordinates into a geometric object,
            defaults to ``False``
        :type parse_geometry: bool
        :return: tabular data of the Osmium GeoJSON file
        :rtype: pandas.DataFrame

        .. _`json`: https://docs.python.org/3/library/json.html#module-json
        .. _`UltraJSON`: https://pypi.org/project/ujson/
        .. _`orjson`: https://pypi.org/project/orjson/
        .. _`python-rapidjson`: https://pypi.org/project/python-rapidjson/

        .. seealso::

            - Examples for the method
              :meth:`BBBikeReader.read_geojson_xz()<pydriosm.reader.BBBikeReader.read_geojson_xz>`.
        """

        engine_ = check_json_engine(engine=engine)

        with lzma.open(path_to_file, mode='rt', encoding='utf-8') as f:
            raw_data = engine_.loads(f.read())

        data = pd.DataFrame.from_dict(raw_data['features'])

        if 'type' in data.columns:
            if data['type'].nunique() == 1:
                del data['type']

        if parse_geometry:
            # data['geometry'] = data['geometry'].map(cls.transform_unitary_geometry)
            with multiprocessing.Pool(processes=multiprocessing.cpu_count() - 1) as p:
                geom_data = p.map(convert_simplex_geometry, data['geometry'])

            data.loc[:, 'geometry'] = pd.Series(geom_data)

        object_cols = data.select_dtypes(include=['object', 'string']).columns
        data[object_cols] = data[object_cols].replace({np.nan: None})

        return data
