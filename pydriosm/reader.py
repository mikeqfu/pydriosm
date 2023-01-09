"""Read the `OSM <https://www.openstreetmap.org/>`_ data extracts in various file formats."""

import collections
import copy
import glob
import itertools
import lzma
import multiprocessing
import os
import re
import shutil
import warnings
import zipfile

import pandas as pd
import shapefile as pyshp
import shapely.errors
import shapely.geometry
from pyhelpers._cache import _check_dependency
from pyhelpers.dirs import cd, validate_dir
from pyhelpers.ops import get_number_of_chunks, split_list, update_dict
from pyhelpers.settings import gdal_configurations
from pyhelpers.store import load_pickle, save_pickle
from pyhelpers.text import find_similar_str

from pydriosm.downloader import BBBikeDownloader, GeofabrikDownloader, _Downloader
from pydriosm.errors import OtherTagsReformatError
from pydriosm.utils import check_json_engine, remove_osm_file


# == Parsing / transforming data ===================================================================

class Transformer:
    """
    Transform / reformat data.

    **Examples**::

        >>> from pydriosm.reader import Transformer

        >>> geometry = {'type': 'Point', 'coordinates': [-0.5134241, 52.6555853]}
        >>> geometry_ = Transformer.transform_unitary_geometry(geometry)
        >>> type(geometry_)
        shapely.geometry.point.Point
        >>> geometry_.wkt
        'POINT (-0.5134241 52.6555853)'
    """

    @classmethod
    def point_as_polygon(cls, multi_poly_coords):
        """
        Make the coordinates of a single 'Point' (in a 'MultiPolygon') be reformatted to
        a 'Polygon'-like coordinates.

        The list of coordinates of some 'MultiPolygon' features may contain single points.
        In order to reformat such multipart geometry (from dict into `shapely.geometry`_ type),
        there is a need to ensure each of the constituent parts is a `shapely.geometry.Polygon`_.

        :param multi_poly_coords: original data of coordinates of a
            `shapely.geometry.MultiPolygon`_ feature
        :type multi_poly_coords: list
        :return: coordinates that are reformatted as appropriate
        :rtype: list

        .. _`shapely.geometry`:
            https://shapely.readthedocs.io/en/latest/manual.html#geometric-objects
        .. _`shapely.geometry.Polygon`:
            https://shapely.readthedocs.io/en/stable/manual.html#Polygon
        .. _`shapely.geometry.MultiPolygon`:
            https://shapely.readthedocs.io/en/stable/manual.html#MultiPolygon

        **Examples**::

            >>> from pydriosm.reader import Transformer

            >>> geometry = {
            ...     'type': 'MultiPolygon',
            ...     'coordinates': [[[[-0.6920145, 52.6753268], [-0.6920145, 52.6753268]]]]
            ... }
            >>> mp_coords = geometry['coordinates']

            >>> mp_coords_ = Transformer.point_as_polygon(mp_coords)
            >>> mp_coords_
            [[[[-0.6920145, 52.6753268],
               [-0.6920145, 52.6753268],
               [-0.6920145, 52.6753268]]]]
        """

        coords = multi_poly_coords.copy()
        temp = coords[0][0]

        if len(temp) == 2 and temp[0] == temp[1]:
            coords[0][0] += [temp[0]]

        return coords

    @classmethod
    def transform_unitary_geometry(cls, geometry, mode=1, to_wkt=False):
        """
        Transform a unitary geometry from dict into a `shapely.geometry`_ object.

        :param geometry: geometry data for a feature of one of the geometry types including
            ``'Point'``, ``'LineString'``, ``'MultiLineString'`` and ``'MultiPolygon'``
        :type geometry: dict or pandas.DataFrame
        :param mode: indicate the way of parsing the input;

            - when ``mode=1`` **(default)**, the input ``geometry`` should be directly accessible and
              would be in the format of ``{'type': <shape type>, 'coordinates': <coordinates>}`` or
              as a row of a `pandas.DataFrame`_;
            - when ``mode=2``, the input ``geometry`` is in the `GeoJSON`_ format

        :type mode: int
        :param to_wkt: whether to represent the geometry in the WKT (well-known text) format,
            defaults to ``False``
        :type to_wkt: bool
        :return: reformatted geometry data
        :rtype: shapely.geometry.Point or dict or str

        .. _`shapely.geometry`: https://shapely.readthedocs.io/en/latest/manual.html#geometric-objects
        .. _`pandas.DataFrame`: https://pandas.pydata.org/docs/reference/api/pandas.DataFrame.html
        .. _`GeoJSON`: https://geojson.org/

        **Examples**::

            >>> from pydriosm.reader import PBFReadParse

            >>> g1_dat = {'type': 'Point', 'coordinates': [-0.5134241, 52.6555853]}
            >>> g1_data = PBFReadParse.transform_unitary_geometry(g1_dat)
            >>> type(g1_data)
            shapely.geometry.point.Point
            >>> g1_data.wkt
            'POINT (-0.5134241 52.6555853)'

            >>> g2_dat = {
            ...     'type': 'Feature',
            ...     'geometry': {
            ...         'type': 'Point',
            ...         'coordinates': [-0.5134241, 52.6555853]
            ...     },
            ...     'properties': {
            ...         'osm_id': '488432',
            ...         'name': None,
            ...         'barrier': None,
            ...         'highway': None,
            ...         'ref': None,
            ...         'address': None,
            ...         'is_in': None,
            ...         'place': None,
            ...         'man_made': None,
            ...         'other_tags': '"odbl"=>"clean"'
            ...     },
            ...     'id': 488432
            ... }
            >>> g2_data = PBFReadParse.transform_unitary_geometry(g2_dat, mode=2)
            >>> type(g2_data)
            dict
            >>> list(g2_data.keys())
            ['type', 'geometry', 'properties', 'id']
            >>> g2_data['geometry']
            'POINT (-0.5134241 52.6555853)'
        """

        if mode == 1:
            geom_type, coords = geometry['type'], geometry['coordinates']
            geom_func = getattr(shapely.geometry, geom_type)

            if geom_type == 'MultiPolygon':
                geom = geom_func(
                    shapely.geometry.Polygon(y) for x in cls.point_as_polygon(coords) for y in x)
                geom_data = geom.wkt if to_wkt else geom.geoms

            else:
                geom_data = geom_func(coords)
                if to_wkt:
                    geom_data = geom_data.wkt
                elif 'Multi' in geom_type:
                    geom_data = geom_data.geoms

        else:
            geom_data = geometry.copy()
            geom_data.update(
                {'geometry': cls.transform_unitary_geometry(geometry['geometry'], mode=1, to_wkt=True)})

        return geom_data

    @classmethod
    def transform_geometry_collection(cls, geometry, mode=1, to_wkt=False):
        """
        Transform a collection of geometry from dict into a `shapely.geometry`_ object.

        :param geometry: geometry data for a feature of ``GeometryCollection``
        :type geometry: list or dict
        :param mode: indicate the way of parsing the input;

            - when ``mode=1`` **(default)**, the input ``geometry`` should be directly accessible and
              would be in the format of ``{'type': <shape type>, 'coordinates': <coordinates>}`` or
              as a row of a `pandas.DataFrame`_;
            - when ``mode=2``, the input ``geometry`` is in the `GeoJSON`_ format

        :type mode: int
        :param to_wkt: whether to represent the geometry in the WKT (well-known text) format,
            defaults to ``False``
        :type to_wkt: bool
        :return: reformatted geometry data
        :rtype: shapely.geometry.base.HeterogeneousGeometrySequence or dict or str

        .. _`shapely.geometry`: https://shapely.readthedocs.io/en/latest/manual.html#geometric-objects
        .. _`pandas.DataFrame`: https://pandas.pydata.org/docs/reference/api/pandas.DataFrame.html
        .. _`GeoJSON`: https://geojson.org/

        **Examples**::

            >>> from pydriosm.reader import PBFReadParse
            >>> from shapely.geometry import GeometryCollection

            >>> g1_dat_ = {
            ...     'type': 'GeometryCollection',
            ...     'geometries': [
            ...         {'type': 'Point', 'coordinates': [-0.5096176, 52.6605168]},
            ...         {'type': 'Point', 'coordinates': [-0.5097337, 52.6605812]}
            ...     ]
            ... }
            >>> g1_dat = g1_dat_['geometries']
            >>> g1_data = PBFReadParse.transform_geometry_collection(g1_dat)
            >>> type(g1_data)
            shapely.geometry.base.HeterogeneousGeometrySequence
            >>> GeometryCollection(list(g1_data)).wkt
            'GEOMETRYCOLLECTION (POINT (-0.5096176 52.6605168), POINT (-0.5097337 52.6605812))'

            >>> g2_dat = {
            ...     'type': 'Feature',
            ...     'geometry': {
            ...         'type': 'GeometryCollection',
            ...         'geometries': [
            ...             {'type': 'Point', 'coordinates': [-0.5096176, 52.6605168]},
            ...             {'type': 'Point', 'coordinates': [-0.5097337, 52.6605812]}]
            ...      },
            ...     'properties': {
            ...         'osm_id': '256254',
            ...         'name': 'Fife Close',
            ...         'type': 'site',
            ...         'other_tags': '"naptan:StopAreaCode"=>"270G02701525"'
            ...     },
            ...     'id': 256254
            ... }
            >>> g2_data = PBFReadParse.transform_geometry_collection(g2_dat, mode=2)
            >>> type(g2_data)
            dict
            >>> list(g2_data.keys())
            ['type', 'geometry', 'properties', 'id']
            >>> g2_data['geometry']
            'GEOMETRYCOLLECTION (POINT (-0.5096176 52.6605168), POINT (-0.5097337 52.6605812))'
        """

        if mode == 1:
            geometry_collection = []

            for geom_type, coords in zip(*zip(*map(dict.values, geometry))):
                geom_func = getattr(shapely.geometry, geom_type)
                if 'Polygon' not in geom_type:
                    geometry_collection.append(geom_func(coords))
                else:
                    geometry_collection.append(geom_func(pt for pts in coords for pt in pts))

            if to_wkt:
                geome_data = shapely.geometry.GeometryCollection(geometry_collection).wkt
            else:
                geome_data = shapely.geometry.GeometryCollection(geometry_collection).geoms

        else:
            geome_data = geometry.copy()
            geometries = geome_data['geometry']['geometries']
            geome_data.update(
                {'geometry': cls.transform_geometry_collection(geometries, mode=1, to_wkt=True)})

        return geome_data

    @classmethod
    def transform_geometry(cls, layer_data, layer_name):
        """
        Reformat the field of ``'geometry'`` into
        `shapely.geometry <https://shapely.readthedocs.io/en/latest/manual.html#geometric-objects>`_
        object.

        :param layer_data: dataframe of a specific layer of PBF data
        :type layer_data: pandas.DataFrame or pandas.Series
        :param layer_name: name (geometric type) of the PBF layer
        :type layer_name: str
        :return: (OSM feature with) reformatted geometry field
        :rtype: pandas.DataFrame or pandas.Series

        **Examples**::

            >>> from pydriosm.reader import Transformer

            >>> # An example of points layer data
            >>> lyr_name = 'points'
            >>> dat_ = {
            ...     'type': 'Feature',
            ...     'geometry': {
            ...         'type': 'Point',
            ...         'coordinates': [-0.5134241, 52.6555853]
            ...     },
            ...     'properties': {
            ...         'osm_id': '488432',
            ...         'name': None,
            ...         'barrier': None,
            ...         'highway': None,
            ...         'ref': None,
            ...         'address': None,
            ...         'is_in': None,
            ...         'place': None,
            ...         'man_made': None,
            ...         'other_tags': '"odbl"=>"clean"'
            ...     },
            ...     'id': 488432
            ... }
            >>> lyr_data = pd.DataFrame.from_dict(dat_, orient='index').T

            >>> geom_dat = Transformer.transform_geometry(layer_data=lyr_data, layer_name=lyr_name)
            >>> geom_dat
            0    POINT (-0.5134241 52.6555853)
            Name: geometry, dtype: object

        .. seealso::

            - Examples for the method
              :meth:`PBFReadParse.read_pbf()<pydriosm.reader.PBFReadParse.read_pbf>`.
        """

        geom_col_name = 'geometry'

        if layer_name == 'other_relations':
            if isinstance(layer_data, pd.DataFrame):  # geom_col_name in layer_data.columns:
                geometries = pd.DataFrame(list(layer_data[geom_col_name]))['geometries']
                geom_data = geometries.map(cls.transform_geometry_collection)
                geom_data.name = geom_col_name
            else:
                geom_data = layer_data.map(lambda x: cls.transform_geometry_collection(x, mode=2))

        else:  # `layer_data` can be 'points', 'lines', 'multilinestrings' or 'multipolygons'
            if isinstance(layer_data, pd.DataFrame):  # geom_col_name in layer_data.columns:
                geom_data = layer_data[geom_col_name].map(cls.transform_unitary_geometry)
            else:
                geom_data = layer_data.map(lambda x: cls.transform_unitary_geometry(x, mode=2))

        return geom_data

    @classmethod
    def transform_other_tags(cls, other_tags):
        """
        Reformat a ``'other_tags'`` from string into dictionary type.

        :param other_tags: data of ``'other_tags'`` of a single feature in a PBF data file
        :type other_tags: str or None
        :return: reformatted data of ``'other_tags'``
        :rtype: dict or None

        **Examples**::

            >>> from pydriosm.reader import Transformer

            >>> other_tags_dat = Transformer.transform_other_tags(other_tags='"odbl"=>"clean"')
            >>> other_tags_dat
            {'odbl': 'clean'}

        .. seealso::

            - Examples for the method
              :meth:`PBFReadParse.read_pbf()<pydriosm.reader.PBFReadParse.read_pbf>`.
        """

        if other_tags:
            tags = [re.sub(r'^"|"$', '', x) for x in re.split('(?<="),(?=")', other_tags)]
            try:
                fltr = (re.split(r'"=>"?', x, maxsplit=1) for x in filter(None, tags))
            except OtherTagsReformatError:
                fltr = filter(lambda x: len(x) == 2, (re.split(r'"=>"?', x) for x in filter(None, tags)))
            other_tags_ = {k: v.replace('<br>', ' ') for k, v in fltr}

        else:  # e.g. the data of 'other_tags' is None
            other_tags_ = other_tags

        return other_tags_

    @classmethod
    def update_other_tags(cls, prop_or_feat, mode=1):
        """
        Update the original data of ``'other_tags'`` with parsed data.

        :param prop_or_feat: original data of a feature or a ``'properties'`` field
        :type prop_or_feat: dict
        :param mode: options include ``{1, 2}`` indicating what action to take;
            when ``mode=1`` (default), ``prop_or_feat`` should be data of a feature;
            when ``mode=2``, ``prop_or_feat`` should be data of a ``'properties'`` field
        :type mode: int
        :return: updated data of a feature or a 'properties' field
        :rtype: dict

        **Examples**::

            >>> from pydriosm.reader import Transformer

            >>> prop_dat = {
            ...     'properties': {
            ...         'osm_id': '488432',
            ...         'name': None,
            ...         'barrier': None,
            ...         'highway': None,
            ...         'ref': None,
            ...         'address': None,
            ...         'is_in': None,
            ...         'place': None,
            ...         'man_made': None,
            ...         'other_tags': '"odbl"=>"clean"'
            ...     },
            ... }

            >>> prop_dat_ = Transformer.update_other_tags(prop_dat['properties'])
            >>> prop_dat_
            {'osm_id': '488432',
             'name': None,
             'barrier': None,
             'highway': None,
             'ref': None,
             'address': None,
             'is_in': None,
             'place': None,
             'man_made': None,
             'other_tags': {'odbl': 'clean'}}

        .. seealso::

            - Examples for the method
              :meth:`PBFReadParse.read_pbf()<pydriosm.reader.PBFReadParse.read_pbf>`.
        """

        if mode == 1:
            properties = prop_or_feat.copy()
            properties.update({'other_tags': cls.transform_other_tags(properties['other_tags'])})

            return properties

        else:
            feat = prop_or_feat.copy()
            other_tags = copy.copy(feat['properties']['other_tags'])

            feat_ = update_dict(
                feat, {'properties': {'other_tags': cls.transform_other_tags(other_tags)}})
            # feat['properties'].update({'other_tags': transform_other_tags(other_tags)})

            return feat_


class PBFReadParse(Transformer):
    """
    Read/parse `PBF <https://wiki.openstreetmap.org/wiki/PBF_Format>`_ data.

    **Examples**::

        >>> from pydriosm.reader import PBFReadParse

        >>> PBFReadParse.LAYER_GEOM
        {'points': shapely.geometry.point.Point,
         'lines': shapely.geometry.linestring.LineString,
         'multilinestrings': shapely.geometry.multilinestring.MultiLineString,
         'multipolygons': shapely.geometry.multipolygon.MultiPolygon,
         'other_relations': shapely.geometry.collection.GeometryCollection}
    """

    #: dict: Layer names of an OSM PBF file and their corresponding
    #: `geometric objects <https://shapely.readthedocs.io/en/latest/manual.html#geometric-objects>`_
    #: defined in `Shapely <https://pypi.org/project/Shapely/>`_.
    LAYER_GEOM = {
        'points': shapely.geometry.Point,
        'lines': shapely.geometry.LineString,
        'multilinestrings': shapely.geometry.MultiLineString,
        'multipolygons': shapely.geometry.MultiPolygon,
        'other_relations': shapely.geometry.GeometryCollection,
    }

    @classmethod
    def get_pbf_layer_geom_types(cls, shape_name=False):
        """
        A dictionary cross-referencing the names of PBF layers and their corresponding
        `geometric objects <https://shapely.readthedocs.io/en/latest/manual.html#geometric-objects>`_
        defined in `Shapely <https://pypi.org/project/Shapely/>`_, or names.

        :param shape_name: whether to return the names of geometry shapes, defaults to ``False``
        :type shape_name: bool
        :return: a dictionary with keys and values being, respectively,
            PBF layers and their corresponding `geometric objects`_ defined in `Shapely`_
        :rtype: dict

        .. _`geometric objects`: https://shapely.readthedocs.io/en/latest/manual.html#geometric-objects
        .. _`Shapely`: https://pypi.org/project/Shapely/

        **Examples**::

            >>> from pydriosm.reader import PBFReadParse

            >>> PBFReadParse.get_pbf_layer_geom_types()
            {'points': shapely.geometry.point.Point,
             'lines': shapely.geometry.linestring.LineString,
             'multilinestrings': shapely.geometry.multilinestring.MultiLineString,
             'multipolygons': shapely.geometry.multipolygon.MultiPolygon,
             'other_relations': shapely.geometry.collection.GeometryCollection}

            >>> PBFReadParse.get_pbf_layer_geom_types(shape_name=True)
            {'points': 'Point',
             'lines': 'LineString',
             'multilinestrings': 'MultiLineString',
             'multipolygons': 'MultiPolygon',
             'other_relations': 'GeometryCollection'}
        """

        pbf_layer_geom_dict = cls.LAYER_GEOM.copy()

        if shape_name:
            pbf_layer_geom_dict = {k: v.__name__ for k, v in pbf_layer_geom_dict.items()}

        return pbf_layer_geom_dict

    @classmethod
    def get_pbf_layer_names(cls, pbf_pathname, verbose=False):
        """
        Get names (and indices) of all available layers in a PBF data file.

        :param pbf_pathname: path to a PBF data file
        :type pbf_pathname: str or os.PathLike[str]
        :param verbose: whether to print relevant information in console, defaults to ``False``
        :type verbose: bool or int
        :return: indices and names of each layer of the PBF data file
        :rtype: dict

        **Examples**::

            >>> from pydriosm.reader import PBFReadParse
            >>> from pydriosm.downloader import GeofabrikDownloader
            >>> from pyhelpers.dirs import delete_dir
            >>> import os

            >>> # Download the PBF data file of London as an example
            >>> subrgn_name = 'london'
            >>> file_format = ".pbf"
            >>> dwnld_dir = "tests\\osm_data"

            >>> gfd = GeofabrikDownloader()

            >>> gfd.download_osm_data(subrgn_name, file_format, dwnld_dir, verbose=True)
            To download .osm.pbf data of the following geographic (sub)region(s):
                Greater London
            ? [No]|Yes: yes
            Downloading "greater-london-latest.osm.pbf"
                to "tests\\osm_data\\greater-london\\" ... Done.

            >>> london_pbf_pathname = gfd.data_paths[0]
            >>> os.path.relpath(london_pbf_pathname)
            'tests\\osm_data\\greater-london\\greater-london-latest.osm.pbf'

            >>> # Get indices and names of all layers in the downloaded PBF data file
            >>> pbf_layer_idx_names = PBFReadParse.get_pbf_layer_names(london_pbf_pathname)
            >>> type(pbf_layer_idx_names)
            dict
            >>> pbf_layer_idx_names
            {0: 'points',
             1: 'lines',
             2: 'multilinestrings',
             3: 'multipolygons',
             4: 'other_relations'}

            >>> # Delete the download directory (and the downloaded PBF data file)
            >>> delete_dir(gfd.download_dir, verbose=True)
            To delete the directory "tests\\osm_data\\" (Not empty)
            ? [No]|Yes: yes
            Deleting "tests\\osm_data\\" ... Done.
        """

        if verbose:
            print(f"Getting the layer names of \"{os.path.relpath(pbf_pathname)}\"", end=" ... ")

        try:
            osgeo_ogr = _check_dependency(name='osgeo.ogr')

            f = osgeo_ogr.Open(pbf_pathname)

            layer_count = f.GetLayerCount()
            layer_names = [f.GetLayerByIndex(i).GetName() for i in range(layer_count)]

            layer_idx_names = dict(zip(range(layer_count), layer_names))

            if verbose:
                print("Done.")

            return layer_idx_names

        except Exception as e:
            print(f"Failed. {e}")

    @classmethod
    def transform_pbf_layer_field(cls, layer_data, layer_name, parse_geometry=False,
                                  parse_properties=False, parse_other_tags=False):
        """
        Parse data of a layer of PBF data.

        :param layer_data: dataframe of a specific layer of PBF data
        :type layer_data: pandas.DataFrame or pandas.Series
        :param layer_name: name (geometric type) of the PBF layer
        :type layer_name: str
        :param parse_geometry: whether to represent the ``'geometry'`` field
            in a `shapely.geometry`_ format, defaults to ``False``
        :type parse_geometry: bool
        :param parse_properties: whether to represent the ``'properties'`` field
            in a tabular format, defaults to ``False``
        :type parse_properties: bool
        :param parse_other_tags: whether to represent a ``'other_tags'`` (of ``'properties'``)
            in a `dict`_ format, defaults to ``False``
        :type parse_other_tags: bool
        :return: readable data of the given PBF layer
        :rtype: pandas.DataFrame or pandas.Series

        .. _`shapely.geometry`: https://shapely.readthedocs.io/en/latest/manual.html#geometric-objects
        .. _`dict`: https://docs.python.org/3/library/stdtypes.html#dict

        See examples for the method
        :meth:`PBFReadParse.read_pbf()<pydriosm.reader.PBFReadParse.read_pbf>`.
        """

        if not layer_data.empty:
            lyr_dat = layer_data.copy()

            if isinstance(lyr_dat, pd.Series):
                if parse_geometry:  # Reformat the geometry
                    lyr_dat = cls.transform_geometry(layer_data=lyr_dat, layer_name=layer_name)

                if parse_other_tags:  # Reformat the 'other_tags' of properties
                    lyr_dat = lyr_dat.map(lambda x: cls.update_other_tags(x, mode=2))

            else:
                # Whether to reformat the 'geometry'
                if parse_geometry:
                    geom_data = cls.transform_geometry(layer_data=lyr_dat, layer_name=layer_name)
                else:
                    geom_data = lyr_dat['geometry']

                # Whether to reformat the 'properties'
                prop_data, prop_col_name, ot_name = None, 'properties', 'other_tags'
                if parse_properties:  # Expand the dict-type 'properties'
                    prop_data = pd.DataFrame(list(lyr_dat[prop_col_name]))
                    if 'osm_id' in prop_data.columns:
                        # if layer_data['id'].equals(prop_data['osm_id'].astype(np.int64))
                        del prop_data['osm_id']
                    if parse_other_tags:
                        # Reformat the properties
                        prop_data.loc[:, ot_name] = prop_data[ot_name].map(cls.transform_other_tags)
                else:
                    # Whether to reformat 'other_tags'
                    if parse_other_tags:
                        prop_data = lyr_dat[prop_col_name].map(cls.update_other_tags)
                    else:
                        prop_data = lyr_dat[prop_col_name]

                lyr_dat = pd.concat([lyr_dat[['id']], geom_data, prop_data], axis=1)

        else:
            lyr_dat = layer_data

            if isinstance(lyr_dat, pd.DataFrame):
                if 'type' in lyr_dat.columns:
                    if 'Feature' in lyr_dat['type'].unique() and lyr_dat['type'].nunique() == 1:
                        del lyr_dat['type']

        if isinstance(lyr_dat, pd.DataFrame):
            if 'id' in lyr_dat.columns:
                lyr_dat.sort_values('id', ignore_index=True, inplace=True)

        return lyr_dat

    @classmethod
    def _read_pbf_layer(cls, layer, readable, expand, parse_geometry, parse_properties,
                        parse_other_tags):
        """
        Parse a layer of a PBF data file.

        :param layer: a layer of a PBF data file, loaded by `GDAL/OGR <https://gdal.org>`_
        :type layer: osgeo.ogr.Layer or list
        :param readable: whether to parse each feature in the raw data, defaults to ``False``
        :type readable: bool
        :param expand: whether to expand dict-like data into separate columns, defaults to ``False``
        :type expand: bool
        :param parse_geometry: whether to represent the ``'geometry'`` field
            in a `shapely.geometry`_ format
        :type parse_geometry: bool
        :param parse_properties: whether to represent the ``'properties'`` field
            in a tabular format
        :type parse_properties: bool
        :param parse_other_tags: whether to represent the ``'other_tags'`` (of ``'properties'``)
            in a `dict`_ format
        :type parse_other_tags: bool
        :return: data of the given layer of the given OSM PBF layer
        :rtype: pandas.DataFrame or list

        .. _`shapely.geometry`: https://shapely.readthedocs.io/en/latest/manual.html#geometric-objects
        .. _`dict`: https://docs.python.org/3/library/stdtypes.html#dict

        See examples for the method
        :meth:`PBFReadParse.read_pbf()<pydriosm.reader.PBFReadParse.read_pbf>`.
        """

        if readable or expand:
            # Replaced: readable = True if parse_geometry or parse_other_tags else readable
            if isinstance(layer, list):
                layer_name = layer[-1]
                del layer[-1]
            else:
                layer_name = layer.GetName()

            dat = [f.ExportToJson(as_object=True) for f in layer]

            if expand:
                lyr_dat = pd.DataFrame(dat)
            else:
                lyr_dat = pd.Series(data=dat, name=layer_name)

            layer_data = cls.transform_pbf_layer_field(
                layer_data=lyr_dat, layer_name=layer_name, parse_geometry=parse_geometry,
                parse_properties=parse_properties, parse_other_tags=parse_other_tags)

        else:
            if isinstance(layer, list):
                del layer[-1]

            layer_data = [f for f in layer]
            # layer_data = pd.Series(data=layer_data, name=layer_name)

        return layer_data

    @classmethod
    def _read_pbf_layer_chunkwise(cls, layer, number_of_chunks, **kwargs):
        """
        Parse a layer of a PBF data file chunk-wisely.

        :param layer: a layer of a PBF data file, loaded by `GDAL/OGR <https://gdal.org>`_
        :type layer: osgeo.ogr.Layer
        :param number_of_chunks: number of chunks
        :type number_of_chunks: int
        :param kwargs: [optional] parameters of the method
            :meth:`PBFReadParse._read_pbf_layer()<pydriosm.reader.PBFReadParse._read_pbf_layer>`
        :return: data of the given layer of the given OSM PBF layer
        :rtype: pandas.DataFrame or list

        See examples for the method
        :meth:`PBFReadParse.read_pbf()<pydriosm.reader.PBFReadParse.read_pbf>`.
        """

        layer_name = layer.GetName()
        layer_chunks = split_list(lst=[f for f in layer], num_of_sub=number_of_chunks)

        list_of_layer_dat = [cls._read_pbf_layer(lyr + [layer_name], **kwargs) for lyr in layer_chunks]

        if kwargs['readable']:
            layer_data = pd.concat(objs=list_of_layer_dat, axis=0, ignore_index=True)
        else:
            layer_data = [dat for chunk in list_of_layer_dat for dat in chunk]

        return layer_data

    @classmethod
    def read_pbf_layer(cls, layer, readable=True, expand=False, parse_geometry=False,
                       parse_properties=False, parse_other_tags=False, number_of_chunks=None):
        """
        Parse a layer of a PBF data file.

        :param layer: a layer of a PBF data file, loaded by `GDAL/OGR <https://gdal.org>`_
        :type layer: osgeo.ogr.Layer
        :param readable: whether to parse each feature in the raw data, defaults to ``False``
        :type readable: bool
        :param expand: whether to expand dict-like data into separate columns, defaults to ``False``
        :type expand: bool
        :param parse_geometry: whether to represent the ``'geometry'`` field
            in a `shapely.geometry`_ format, defaults to ``False``
        :type parse_geometry: bool
        :param parse_properties: whether to represent the ``'properties'`` field
            in a tabular format, defaults to ``False``
        :type parse_properties: bool
        :param parse_other_tags: whether to represent a ``'other_tags'`` (of ``'properties'``)
            in a `dict`_ format, defaults to ``False``
        :type parse_other_tags: bool
        :param number_of_chunks: number of chunks, defaults to ``None``
        :type number_of_chunks: int or None
        :return: parsed data of the given OSM PBF layer
        :rtype: dict

        .. _`shapely.geometry`: https://shapely.readthedocs.io/en/latest/manual.html#geometric-objects
        .. _`dict`: https://docs.python.org/3/library/stdtypes.html#dict

        See examples for the method
        :meth:`PBFReadParse.read_pbf()<pydriosm.reader.PBFReadParse.read_pbf>`.
        """

        layer_name = layer.GetName()  # Get the name of the i-th layer

        func_args = {
            'readable': readable,
            'expand': expand,
            'parse_geometry': parse_geometry,
            'parse_properties': parse_properties,
            'parse_other_tags': parse_other_tags,
        }

        if number_of_chunks in {None, 0, 1}:
            layer_data = cls._read_pbf_layer(layer=layer, **func_args)
        else:
            layer_data = cls._read_pbf_layer_chunkwise(
                layer=layer, number_of_chunks=number_of_chunks, **func_args)

        data = {layer_name: layer_data}

        return data

    @classmethod
    def read_pbf(cls, pbf_pathname, readable=True, expand=False, parse_geometry=False,
                 parse_properties=False, parse_other_tags=False, number_of_chunks=None,
                 max_tmpfile_size=5000, **kwargs):
        """
        Parse a PBF data file (by `GDAL <https://pypi.org/project/GDAL/>`_).

        :param pbf_pathname: pathname of a PBF data file
        :type pbf_pathname: str
        :param readable: whether to parse each feature in the raw data, defaults to ``False``
        :type readable: bool
        :param expand: whether to expand dict-like data into separate columns, defaults to ``False``
        :type expand: bool
        :param parse_geometry: whether to represent the ``'geometry'`` field
            in a `shapely.geometry`_ format, defaults to ``False``
        :type parse_geometry: bool
        :param parse_properties: whether to represent the ``'properties'`` field
            in a tabular format, defaults to ``False``
        :type parse_properties: bool
        :param parse_other_tags: whether to represent a ``'other_tags'`` (of ``'properties'``)
            in a `dict`_ format, defaults to ``False``
        :type parse_other_tags: bool
        :param number_of_chunks: number of chunks, defaults to ``None``
        :type number_of_chunks: int or None
        :param max_tmpfile_size: maximum size of the temporary file, defaults to ``None``;
            when ``max_tmpfile_size=None``, it defaults to ``5000``
        :type max_tmpfile_size: int or None
        :param kwargs: [optional] parameters of the function `pyhelpers.settings.gdal_configurations()`_
        :return: parsed OSM PBF data
        :rtype: dict

        .. _`shapely.geometry`:
            https://shapely.readthedocs.io/en/latest/manual.html#geometric-objects
        .. _`dict`:
            https://docs.python.org/3/library/stdtypes.html#dict
        .. _`pyhelpers.settings.gdal_configurations()`:
            https://pyhelpers.readthedocs.io/en/latest/_generated/
            pyhelpers.settings.gdal_configurations.html

        .. note::

            The `GDAL/OGR <https://gdal.org>`_ drivers categorizes the features of OSM PBF data into
            five layers:

            - **0: 'points'** - "node" features having significant tags attached
            - **1: 'lines'** - "way" features being recognized as non-area
            - **2: 'multilinestrings'** - "relation" features forming a multilinestring
              (type='multilinestring' / type='route')
            - **3: 'multipolygons'** - "relation" features forming a multipolygon
              (type='multipolygon' / type='boundary'), and "way" features being recognized as area
            - **4: 'other_relations'** - "relation" features not belonging to the above 2 layers

            For more information, please refer to
            `OSM - OpenStreetMap XML and PBF <https://gdal.org/drivers/vector/osm.html>`_.

        .. warning::

            - **Parsing large PBF data files (e.g. > 50MB) can be time-consuming!**
            - The function :func:`~pydriosm.reader.read_osm_pbf` may require fairly high amount of
              physical memory to parse large files, in which case it would be recommended that
              ``number_of_chunks`` is set to be a reasonable value.

        .. _pydriosm-reader-PBFReadParse-read_osm_pbf:

        **Examples**::

            >>> from pydriosm.reader import PBFReadParse
            >>> from pydriosm.downloader import GeofabrikDownloader
            >>> from pyhelpers.dirs import delete_dir
            >>> import os

            >>> # Download the PBF data file of 'Rutland' as an example
            >>> subrgn_name = 'rutland'
            >>> file_format = ".pbf"
            >>> dwnld_dir = "tests\\osm_data"

            >>> gfd = GeofabrikDownloader()

            >>> gfd.download_osm_data(subrgn_name, file_format, dwnld_dir, verbose=True)
            To download .osm.pbf data of the following geographic (sub)region(s):
                Rutland
            ? [No]|Yes: yes
            Downloading "rutland-latest.osm.pbf"
                to "tests\\osm_data\\rutland\\" ... Done.

            >>> rutland_pbf_path = gfd.data_paths[0]
            >>> os.path.relpath(rutland_pbf_path)
            'tests\\osm_data\\rutland\\rutland-latest.osm.pbf'

            >>> # Read the downloaded PBF data
            >>> rutland_pbf = PBFReadParse.read_pbf(rutland_pbf_path)
            >>> type(rutland_pbf)
            dict
            >>> list(rutland_pbf.keys())
            ['points', 'lines', 'multilinestrings', 'multipolygons', 'other_relations']

            >>> rutland_pbf_points = rutland_pbf['points']
            >>> rutland_pbf_points.head()
            0    {'type': 'Feature', 'geometry': {'type': 'Poin...
            1    {'type': 'Feature', 'geometry': {'type': 'Poin...
            2    {'type': 'Feature', 'geometry': {'type': 'Poin...
            3    {'type': 'Feature', 'geometry': {'type': 'Poin...
            4    {'type': 'Feature', 'geometry': {'type': 'Poin...
            Name: points, dtype: object

            >>> # Set `expand` to be `True`
            >>> pbf_0 = PBFReadParse.read_pbf(rutland_pbf_path, expand=True)
            >>> type(pbf_0)
            dict
            >>> list(pbf_0.keys())
            ['points', 'lines', 'multilinestrings', 'multipolygons', 'other_relations']
            >>> pbf_0_points = pbf_0['points']
            >>> pbf_0_points.head()
                     id  ...                                         properties
            0    488432  ...  {'osm_id': '488432', 'name': None, 'barrier': ...
            1    488658  ...  {'osm_id': '488658', 'name': 'Tickencote Inter...
            2  13883868  ...  {'osm_id': '13883868', 'name': None, 'barrier'...
            3  14049101  ...  {'osm_id': '14049101', 'name': None, 'barrier'...
            4  14558402  ...  {'osm_id': '14558402', 'name': None, 'barrier'...
            [5 rows x 3 columns]

            >>> pbf_0_points['geometry'].head()
            0    {'type': 'Point', 'coordinates': [-0.5134241, ...
            1    {'type': 'Point', 'coordinates': [-0.5313354, ...
            2    {'type': 'Point', 'coordinates': [-0.7229332, ...
            3    {'type': 'Point', 'coordinates': [-0.7249816, ...
            4    {'type': 'Point', 'coordinates': [-0.7266581, ...
            Name: geometry, dtype: object

            >>> # Set both `expand` and `parse_geometry` to be `True`
            >>> pbf_1 = PBFReadParse.read_pbf(rutland_pbf_path, expand=True, parse_geometry=True)
            >>> pbf_1_points = pbf_1['points']
            >>> # Check the difference in 'geometry' column, compared to `pbf_0_points`
            >>> pbf_1_points['geometry'].head()
            0    POINT (-0.5134241 52.6555853)
            1    POINT (-0.5313354 52.6737716)
            2    POINT (-0.7229332 52.5889864)
            3    POINT (-0.7249816 52.6748426)
            4    POINT (-0.7266581 52.6695058)
            Name: geometry, dtype: object

            >>> # Set both `expand` and `parse_properties` to be `True`
            >>> pbf_2 = PBFReadParse.read_pbf(rutland_pbf_path, expand=True, parse_properties=True)
            >>> pbf_2_points = pbf_2['points']
            >>> pbf_2_points['other_tags'].head()
            0                 "odbl"=>"clean"
            1                            None
            2                            None
            3    "traffic_calming"=>"cushion"
            4        "direction"=>"clockwise"
            Name: other_tags, dtype: object

            >>> # Set both `expand` and `parse_other_tags` to be `True`
            >>> pbf_3 = PBFReadParse.read_pbf(rutland_pbf_path, expand=True, parse_properties=True,
            ...                               parse_other_tags=True)
            >>> pbf_3_points = pbf_3['points']
            >>> # Check the difference in 'other_tags', compared to ``pbf_2_points``
            >>> pbf_3_points['other_tags'].head()
            0                 {'odbl': 'clean'}
            1                              None
            2                              None
            3    {'traffic_calming': 'cushion'}
            4        {'direction': 'clockwise'}
            Name: other_tags, dtype: object

            >>> # Delete the downloaded PBF data file
            >>> delete_dir(gfd.download_dir, verbose=True)
            To delete the directory "tests\\osm_data\\" (Not empty)
            ? [No]|Yes: yes
            Deleting "tests\\osm_data\\" ... Done.

        .. seealso::

            - Examples for the methods:
              :meth:`GeofabrikReader.read_osm_pbf()<pydriosm.reader.GeofabrikReader.read_osm_pbf>`
              and :meth:`BBBikeReader.read_osm_pbf()<pydriosm.reader.BBBikeReader.read_osm_pbf>`.
        """

        osgeo_ogr, osgeo_gdal = map(_check_dependency, ['osgeo.ogr', 'osgeo.gdal'])

        gdal_configurations(max_tmpfile_size=max_tmpfile_size, **kwargs)

        # Reference: https://gis.stackexchange.com/questions/332327/
        # Stop GDAL printing both warnings and errors to STDERR
        osgeo_gdal.PushErrorHandler('CPLQuietErrorHandler')
        # Make GDAL raise python exceptions for errors (warnings won't raise an exception)
        osgeo_gdal.UseExceptions()

        func_args = {
            'readable': readable,
            'expand': expand,
            'parse_geometry': parse_geometry,
            'parse_properties': parse_properties,
            'parse_other_tags': parse_other_tags,
            'number_of_chunks': number_of_chunks,
        }

        f = osgeo_ogr.Open(pbf_pathname)

        # Get a collection of parsed layer data
        collection_of_layer_data = [
            cls.read_pbf_layer(f.GetLayerByIndex(i), **func_args) for i in range(f.GetLayerCount())]

        # Make the output in a dictionary form: {Layer1 name: Layer1 data, Layer2 name: Layer2 data, ...}
        data = dict(collections.ChainMap(*reversed(collection_of_layer_data)))

        return data


class SHPReadParse:
    """
    Read/parse `Shapefile <https://wiki.openstreetmap.org/wiki/Shapefiles>`_ data.

    **Examples**::

        >>> from pydriosm.reader import SHPReadParse

        >>> SHPReadParse.EPSG4326_WGS84_PROJ4
        '+proj=longlat +ellps=WGS84 +datum=WGS84 +no_defs'

        >>> SHPReadParse.EPSG4326_WGS84_PROJ4_
        {'proj': 'longlat', 'ellps': 'WGS84', 'datum': 'WGS84', 'no_defs': True}
    """

    #: dict: Shape type codes of shapefiles and their corresponding
    #: `geometric objects <https://shapely.readthedocs.io/en/latest/manual.html#geometric-objects>`_
    #: defined in `Shapely <https://pypi.org/project/Shapely/>`_.
    SHAPE_TYPE_GEOM = {
        1: shapely.geometry.Point,
        3: shapely.geometry.LineString,
        5: shapely.geometry.Polygon,
        8: shapely.geometry.MultiPoint,
    }

    #: dict: Shape type codes of shapefiles and their corresponding geometry object names
    SHAPE_TYPE_GEOM_NAME = {k: v.__name__ for k, v in SHAPE_TYPE_GEOM.items()}

    #: dict: Shape type codes of shapefiles and their corresponding names for an OSM shapefile.
    SHAPE_TYPE_NAME_LOOKUP = {
        0: None,
        1: 'Point',  # shapely.geometry.Point
        3: 'Polyline',  # shapely.geometry.LineString
        5: 'Polygon',  # shapely.geometry.Polygon
        8: 'MultiPoint',  # shapely.geometry.MultiPoint
        11: 'PointZ',
        13: 'PolylineZ',
        15: 'PolygonZ',
        18: 'MultiPointZ',
        21: 'PointM',
        23: 'PolylineM',
        25: 'PolygonM',
        28: 'MultiPointM',
        31: 'MultiPatch',
    }

    #: str: The encoding method applied to create an OSM shapefile.
    #: This is for writing .cpg (code page) file.
    ENCODING = 'UTF-8'  # 'ISO-8859-1'

    #: str: The metadata associated with the shapefiles coordinate and projection system.
    #: `ESRI WKT <https://spatialreference.org/ref/epsg/4326/esriwkt/>`_ of
    #: EPSG Projection 4326 - WGS 84 (`EPSG:4326 <https://spatialreference.org/ref/epsg/wgs-84/>`_)
    #: for shapefile data.
    EPSG4326_WGS84_ESRI_WKT = \
        'GEOGCS["GCS_WGS_1984",DATUM["D_WGS_1984",SPHEROID["WGS_1984",6378137.0,298.257223563]],' \
        'PRIMEM["Greenwich",0.0],' \
        'UNIT["Degree",0.017453292519943295]]'

    #: str: `Proj4 <https://spatialreference.org/ref/epsg/wgs-84/proj4/>`_ of
    #: EPSG Projection 4326 - WGS 84 (`EPSG:4326 <https://spatialreference.org/ref/epsg/wgs-84/>`_)
    #: for the setting of `CRS <https://en.wikipedia.org/wiki/Spatial_reference_system>`_
    #: for shapefile data.
    EPSG4326_WGS84_PROJ4 = '+proj=longlat +ellps=WGS84 +datum=WGS84 +no_defs'

    #: dict: A dict-type representation of EPSG Projection 4326 - WGS 84
    #: (`EPSG:4326 <https://spatialreference.org/ref/epsg/wgs-84/>`_) for the setting of
    #: `CRS <https://en.wikipedia.org/wiki/Spatial_reference_system>`_ for shapefile data.
    EPSG4326_WGS84_PROJ4_ = {
        'proj': 'longlat',
        'ellps': 'WGS84',
        'datum': 'WGS84',
        'no_defs': True,
    }

    #: set: Valid layer names for an OSM shapefile.
    LAYER_NAMES = {
        'buildings',
        'landuse',
        'natural',
        'places',
        'points',
        'pofw',
        'pois',
        'railways',
        'roads',
        'traffic',
        'transport',
        'water',
        'waterways',
    }

    #: Name of the vector driver for writing shapefile data;
    #: see also the parameter ``driver`` of
    #: `geopandas.GeoDataFrame.to_file()
    #: <https://geopandas.org/reference.html#geopandas.GeoDataFrame.to_file>`_.
    VECTOR_DRIVER = 'ESRI Shapefile'

    @classmethod
    def validate_shp_layer_names(cls, layer_names):
        """
        Validate the input of layer name(s) for reading shapefiles.

        :param layer_names: name of a shapefile layer, e.g. 'railways',
            or names of multiple layers; if ``None`` (default), returns an empty list;
            if ``layer_names='all'``, the function returns a list of all available layers
        :type layer_names: str or list or None
        :return: valid layer names to be input
        :rtype: list

        **Examples**::

            >>> from pydriosm.reader import SHPReadParse

            >>> SHPReadParse.validate_shp_layer_names(None)
            []

            >>> SHPReadParse.validate_shp_layer_names('point')
            ['points']

            >>> SHPReadParse.validate_shp_layer_names(['point', 'land'])
            ['points', 'landuse']

            >>> SHPReadParse.validate_shp_layer_names('all')
            ['buildings',
             'landuse',
             'natural',
             'places',
             'pofw',
             'points',
             'pois',
             'railways',
             'roads',
             'traffic',
             'transport',
             'water',
             'waterways']
        """

        if layer_names:
            if layer_names == 'all':
                layer_names_ = sorted(list(cls.LAYER_NAMES))
            else:
                lyr_names_ = [layer_names] if isinstance(layer_names, str) else layer_names
                layer_names_ = [find_similar_str(x, cls.LAYER_NAMES) for x in lyr_names_]

        else:
            layer_names_ = []

        return layer_names_

    @classmethod
    def find_shp_layer_name(cls, shp_filename):
        """
        Find the layer name of OSM shapefile given its filename.

        :param shp_filename: filename of a shapefile (.shp)
        :type shp_filename: str
        :return: layer name of the shapefile
        :rtype: str

        **Examples**::

            >>> from pydriosm.reader import SHPReadParse

            >>> SHPReadParse.find_shp_layer_name("") is None
            True

            >>> SHPReadParse.find_shp_layer_name("gis_osm_railways_free_1.shp")
            'railways'

            >>> SHPReadParse.find_shp_layer_name("gis_osm_transport_a_free_1.shp")
            'transport'
        """

        try:
            pattern = re.compile(r'(?<=gis_osm_)\w+(?=(_a)?_free_1)')
            layer_name = re.search(pattern=pattern, string=shp_filename)

        except AttributeError:
            pattern = re.compile(r'(?<=(\\shape)\\)\w+(?=\.*)')
            layer_name = re.search(pattern=pattern, string=shp_filename)

        if layer_name:
            layer_name = layer_name.group(0).replace("_a", "")

        return layer_name

    @classmethod
    def unzip_shp_zip(cls, shp_zip_pathname, extract_to=None, layer_names=None, separate=False,
                      ret_extract_dir=False, verbose=False):
        """
        Unzip a zipped shapefile.

        :param shp_zip_pathname: path to a zipped shapefile data (.shp.zip)
        :type shp_zip_pathname: str or os.PathLike[str]
        :param extract_to: path to a directory where extracted files will be saved;
            when ``extract_to=None`` (default), the same directory where the .shp.zip file is saved
        :type extract_to: str or None
        :param layer_names: name of a .shp layer, e.g. 'railways', or names of multiple layers;
            when ``layer_names=None`` (default), all available layers
        :type layer_names: str or list or None
        :param separate: whether to put the data files of different layer in respective folders,
            defaults to ``False``
        :type separate: bool
        :param ret_extract_dir: whether to return the pathname of the directory
            where extracted files are saved, defaults to ``False``
        :type ret_extract_dir: bool
        :param verbose: whether to print relevant information in console, defaults to ``False``
        :type verbose: bool or int
        :return: the path to the directory of extracted files when ``ret_extract_dir=True``
        :rtype: str

        **Examples**::

            >>> from pydriosm.reader import SHPReadParse
            >>> from pydriosm.downloader import GeofabrikDownloader
            >>> from pyhelpers.dirs import cd, delete_dir
            >>> import os

            >>> # Download the shapefile data of London as an example
            >>> subrgn_name = 'london'
            >>> file_format = ".shp"
            >>> dwnld_dir = "tests\\osm_data"

            >>> gfd = GeofabrikDownloader()

            >>> gfd.download_osm_data(subrgn_name, file_format, dwnld_dir, verbose=True)
            To download .shp.zip data of the following geographic (sub)region(s):
                Greater London
            ? [No]|Yes: yes
            Downloading "greater-london-latest-free.shp.zip"
                to "tests\\osm_data\\greater-london\\" ... Done.

            >>> path_to_shp_zip = gfd.data_paths[0]
            >>> os.path.relpath(path_to_shp_zip)
            'tests\\osm_data\\greater-london\\greater-london-latest-free.shp.zip'

            >>> # To extract data of a specific layer 'railways'
            >>> london_railways_dir = SHPReadParse.unzip_shp_zip(
            ...     path_to_shp_zip, layer_names='railways', verbose=True, ret_extract_dir=True)
            Extracting the following layer(s):
                'railways'
                from "tests\\osm_data\\greater-london\\greater-london-latest-free.shp.zip"
                  to "tests\\osm_data\\greater-london\\greater-london-latest-free-shp\\" ... Done.

            >>> os.path.relpath(london_railways_dir)  # Check the directory
            'tests\\osm_data\\greater-london\\greater-london-latest-free-shp'

            >>> # When multiple layer names are specified, the extracted files for each of the
            >>> # layers can be put into a separate subdirectory by setting `separate=True`:
            >>> lyr_names = ['railways', 'transport', 'traffic']
            >>> dirs_of_layers = SHPReadParse.unzip_shp_zip(
            ...     path_to_shp_zip, layer_names=lyr_names, separate=True, verbose=2,
            ...     ret_extract_dir=True)
            Extracting the following layer(s):
                'railways'
                'transport'
                'traffic'
                from "tests\\osm_data\\greater-london\\greater-london-latest-free.shp.zip"
                  to "tests\\osm_data\\greater-london\\greater-london-latest-free-shp\\" ... Done.
            Grouping files by layers ...
                railways ... Done.
                transport_a ... Done.
                transport ... Done.
                traffic_a ... Done.
                traffic ... Done.
            Done.

            >>> len(dirs_of_layers) == 3
            True
            >>> os.path.relpath(os.path.commonpath(dirs_of_layers))
            'tests\\osm_data\\greater-london\\greater-london-latest-free-shp'
            >>> set(map(os.path.basename, dirs_of_layers))
            {'railways', 'traffic', 'transport'}

            >>> # Remove the subdirectories
            >>> delete_dir(dirs_of_layers, confirmation_required=False)

            >>> # To extract all (without specifying `layer_names`
            >>> london_shp_dir = SHPReadParse.unzip_shp_zip(
            ...     path_to_shp_zip, verbose=True, ret_extract_dir=True)
            Extracting "tests\\osm_data\\greater-london\\greater-london-latest-free.shp.zip"
                to "tests\\osm_data\\greater-london\\greater-london-latest-free-shp\\" ... Done.

            >>> # Check the directory
            >>> os.path.relpath(london_shp_dir)
            'tests\\osm_data\\greater-london\\greater-london-latest-free-shp'
            >>> len(os.listdir(london_shp_dir))
            91
            >>> # Get the names of all available layers
            >>> set(filter(None, map(SHPReadParse.find_shp_layer_name, os.listdir(london_shp_dir))))
            {'buildings',
             'landuse',
             'natural',
             'places',
             'pofw',
             'pois',
             'railways',
             'roads',
             'traffic',
             'transport',
             'water',
             'waterways'}

            >>> # Delete the download/data directory
            >>> delete_dir(gfd.download_dir, verbose=True)
            To delete the directory "tests\\osm_data\\" (Not empty)
            ? [No]|Yes: yes
            Deleting "tests\\osm_data\\" ... Done.
        """

        if extract_to:
            extract_dir = extract_to
        else:
            extract_dir = os.path.splitext(shp_zip_pathname)[0].replace(".", "-")

        shp_zip_rel_path, extrdir_rel_path = map(os.path.relpath, [shp_zip_pathname, extract_dir])

        if not layer_names:
            layer_names_ = layer_names
            if verbose:
                print(f"Extracting \"{shp_zip_rel_path}\"\n\tto \"{extrdir_rel_path}\\\"", end=" ... ")
        else:
            layer_names_ = [layer_names] if isinstance(layer_names, str) else layer_names.copy()
            if verbose:
                layer_name_list = "\t{}".format("\n\t".join([f"'{x}'" for x in layer_names_]))
                print(f"Extracting the following layer(s):\n{layer_name_list}")
                print(f"\tfrom \"{shp_zip_rel_path}\"\n\t  to \"{extrdir_rel_path}\\\"", end=" ... ")

        try:
            with zipfile.ZipFile(file=shp_zip_pathname, mode='r') as sz:
                if layer_names_:
                    extract_files = [
                        f.filename for f in sz.filelist if any(x in f.filename for x in layer_names_)]
                else:
                    extract_files = None
                sz.extractall(extract_dir, members=extract_files)

            if verbose:
                if isinstance(extract_files, list) and len(extract_files) == 0:
                    print("\n\tThe specified layer does not exist. No data has been extracted.")
                else:
                    print("Done.")

            if separate:
                if verbose:
                    print("Grouping files by layers ... ", end="\n" if verbose == 2 else "")

                file_list = extract_files if extract_files else os.listdir(extract_dir)
                if 'README' in file_list:
                    file_list.remove('README')

                filenames, exts = map(lambda x: list(set(x)), zip(*map(os.path.splitext, file_list)))

                layer_names_ = [cls.find_shp_layer_name(f) for f in filenames]

                extract_dirs = []
                for lyr, fn in zip(layer_names_, filenames):
                    extract_dir_ = os.path.join(extract_dir, lyr)
                    if verbose == 2:
                        print("\t{}".format(lyr if '_a_' not in fn else lyr + '_a'), end=" ... ")

                    for ext in exts:
                        filename = fn + ext
                        orig = cd(extract_dir, filename, mkdir=True)
                        dest = cd(extract_dir_, filename, mkdir=True)
                        shutil.copyfile(orig, dest)
                        os.remove(orig)

                    if verbose == 2:
                        print("Done.")

                    extract_dirs.append(extract_dir_)

                extract_dir = list(set(extract_dirs))

                if verbose:
                    print("Done.")

        except Exception as e:
            print(f"Failed. {e}")

        if ret_extract_dir:
            return extract_dir

    @classmethod
    def _covert_to_geometry(cls, x):
        """Convert the ``(shape_type, coordinates)`` of a feature to a ``shapely.geometry`` object.

        :param x: a feature (i.e. one row data) in a shapefile parsed by pyShp.
        :return: the corresponding ``shapely.geometry`` object
        """
        coordinates, geom_func = x['coordinates'], cls.SHAPE_TYPE_GEOM[x['shape_type']]

        if geom_func.__name__ == 'Point' and len(coordinates) == 1:
            coordinates = coordinates[0]

        y = geom_func(coordinates)

        return y

    @classmethod
    def _convert_to_coords_and_shape_type(cls, x):
        """Convert a ``shapely.geometry`` object to ``(shape_type, coordinates)``.

        :param x: a ``shapely.geometry`` object
        :return: the corresponding ``(shape_type, coordinates)``
        """

        lookup_dict = {v: k for k, v in cls.SHAPE_TYPE_NAME_LOOKUP.items()}
        lookup_dict.update({'LineString': 3})
        shape_type = lookup_dict[x.geom_type]

        # try:
        #     coordinates = list(x.coords)
        # except NotImplementedError:
        #     coordinates = list(x.exterior.coords)
        coordinates = list(x.exterior.coords) if hasattr(x, 'exterior') else list(x.coords)

        return coordinates, shape_type

    @classmethod
    def read_shp(cls, shp_pathname, engine='pyshp', emulate_gpd=False, **kwargs):
        """
        Read a shapefile.

        :param shp_pathname: pathname of a shape format file (.shp)
        :type shp_pathname: str
        :param engine: method used to read shapefiles;
            options include: ``'pyshp'`` (default) and ``'geopandas'`` (or ``'gpd'``)
            this function by default relies on `shapefile.reader()`_;
            when ``engine='geopandas'`` (or ``engine='gpd'``), it relies on `geopandas.read_file()`_;
        :type engine: str
        :param emulate_gpd: whether to emulate the data format produced by `geopandas.read_file()`_
            when ``engine='pyshp'``.
        :type emulate_gpd: bool
        :param kwargs: [optional] parameters of the function
            `geopandas.read_file()`_ or `shapefile.reader()`_
        :return: data frame of the shapefile data
        :rtype: pandas.DataFrame or geopandas.GeoDataFrame

        .. _`shapefile.reader()`: https://github.com/GeospatialPython/pyshp#reading-shapefiles
        .. _`geopandas.read_file()`: https://geopandas.org/reference/geopandas.read_file.html

        .. note::

            - If ``engine`` is set to be ``'geopandas'`` (or ``'gpd'``), it requires that
              `GeoPandas <https://geopandas.org/>`_ is installed.

        **Examples**::

            >>> from pydriosm.reader import SHPReadParse
            >>> from pydriosm.downloader import GeofabrikDownloader
            >>> from pyhelpers.dirs import cd, delete_dir
            >>> import os
            >>> import glob

            >>> # Download the shapefile data of London as an example
            >>> subrgn_name = 'london'
            >>> file_format = ".shp"
            >>> dwnld_dir = "tests\\osm_data"

            >>> gfd = GeofabrikDownloader()

            >>> gfd.download_osm_data(subrgn_name, file_format, dwnld_dir, verbose=True)
            To download .shp.zip data of the following geographic (sub)region(s):
                Greater London
            ? [No]|Yes: yes
            Downloading "greater-london-latest-free.shp.zip"
                to "tests\\osm_data\\greater-london\\" ... Done.

            >>> london_shp_zip = gfd.data_paths[0]
            >>> os.path.relpath(london_shp_zip)
            'tests\\osm_data\\greater-london\\greater-london-latest-free.shp.zip'

            >>> # Extract all
            >>> london_shp_dir = SHPReadParse.unzip_shp_zip(london_shp_zip, ret_extract_dir=True)

            >>> # Get the pathname of the .shp data of 'railways'
            >>> path_to_railways_shp = glob.glob(cd(london_shp_dir, "*railways*.shp"))[0]
            >>> os.path.relpath(path_to_railways_shp)  # Check the pathname of the .shp file
            'tests\\osm_data\\greater-london\\greater-london-latest-free-shp\\gis_osm_railwa...

            >>> # Read the data of 'railways'
            >>> london_railways = SHPReadParse.read_shp(path_to_railways_shp)
            >>> london_railways.head()
               osm_id  code  ...                                        coordinates shape_type
            0   30804  6101  ...  [(0.0048644, 51.6279262), (0.0061979, 51.62926...          3
            1  101298  6103  ...  [(-0.2249906, 51.493682), (-0.2251678, 51.4945...          3
            2  101486  6103  ...  [(-0.2055497, 51.5195429), (-0.2051377, 51.519...          3
            3  101511  6101  ...  [(-0.2119027, 51.5241906), (-0.2108059, 51.523...          3
            4  282898  6103  ...  [(-0.1862586, 51.6159083), (-0.1868721, 51.613...          3
            [5 rows x 9 columns]

            >>> # Set `emulate_gpd=True` to return data of similar format to what GeoPandas does
            >>> london_railways = SHPReadParse.read_shp(path_to_railways_shp, emulate_gpd=True)
            >>> london_railways.head()
               osm_id  code  ... tunnel                                           geometry
            0   30804  6101  ...      F  LINESTRING (0.0048644 51.6279262, 0.0061979 51...
            1  101298  6103  ...      F  LINESTRING (-0.2249906 51.493682, -0.2251678 5...
            2  101486  6103  ...      F  LINESTRING (-0.2055497 51.5195429, -0.2051377 ...
            3  101511  6101  ...      F  LINESTRING (-0.2119027 51.5241906, -0.2108059 ...
            4  282898  6103  ...      F  LINESTRING (-0.1862586 51.6159083, -0.1868721 ...
            [5 rows x 8 columns]

            >>> # Alternatively, set `engine` to be 'geopandas' (or 'gpd') to use GeoPandas
            >>> london_railways_ = SHPReadParse.read_shp(path_to_railways_shp, engine='geopandas')
            >>> london_railways_.head()
               osm_id  code  ... tunnel                                           geometry
            0   30804  6101  ...      F    LINESTRING (0.00486 51.62793, 0.00620 51.62927)
            1  101298  6103  ...      F  LINESTRING (-0.22499 51.49368, -0.22517 51.494...
            2  101486  6103  ...      F  LINESTRING (-0.20555 51.51954, -0.20514 51.519...
            3  101511  6101  ...      F  LINESTRING (-0.21190 51.52419, -0.21081 51.523...
            4  282898  6103  ...      F  LINESTRING (-0.18626 51.61591, -0.18687 51.61384)
            [5 rows x 8 columns]

            >>> # Check the data types of `london_railways` and `london_railways_`
            >>> railways_data = [london_railways, london_railways_]
            >>> list(map(type, railways_data))
            [pandas.core.frame.DataFrame, geopandas.geodataframe.GeoDataFrame]
            >>> # Check the geometry data of `london_railways` and `london_railways_`
            >>> geom1, geom2 = map(lambda x: x['geometry'].map(lambda y: y.wkt), railways_data)
            >>> geom1.equals(geom2)
            True

            >>> # Delete the download/data directory
            >>> delete_dir(gfd.download_dir, verbose=True)
            To delete the directory "tests\\osm_data\\" (Not empty)
            ? [No]|Yes: yes
            Deleting "tests\\osm_data\\" ... Done.
        """

        if engine in {'geopandas', 'gpd'}:
            gpd = _check_dependency(name='geopandas')
            shp_data = gpd.read_file(shp_pathname, **kwargs)

        else:  # method == 'pyshp':  # default
            with pyshp.Reader(shp_pathname, **kwargs) as f:  # Read .shp file using shapefile.reader()
                # Transform the data to a DataFrame
                filed_names = [field[0] for field in f.fields[1:]]
                shp_data = pd.DataFrame(data=f.records(), columns=filed_names)

                # shp_data['name'] = shp_data['name'].str.encode('utf-8').str.decode('utf-8')
                shape_geom_colnames = ['coordinates', 'shape_type']
                shape_geom = pd.DataFrame(
                    data=[(s.points, s.shapeType) for s in f.iterShapes()], index=shp_data.index,
                    columns=shape_geom_colnames)

            if emulate_gpd:
                with warnings.catch_warnings():
                    warnings.filterwarnings("ignore", category=shapely.errors.ShapelyDeprecationWarning)

                    shp_data['geometry'] = shape_geom[shape_geom_colnames].apply(
                        cls._covert_to_geometry, axis=1)
                    # shp_data.drop(columns=shape_geom_colnames, inplace=True)

            else:
                shp_data = pd.concat([shp_data, shape_geom], axis=1)

        return shp_data

    @classmethod
    def _specify_pyshp_fields(cls, data, field_names, decimal_precision):
        """
        Make fields data for writing shapefiles by `PyShp <https://github.com/GeospatialPython/pyshp>`_.

        :param data: data of a shapefile
        :type data: pandas.DataFrame
        :param field_names: names of fields to be written as shapefile records
        :type field_names: list or pandas.Index
        :param decimal_precision: decimal precision for writing float records
        :type decimal_precision: int
        :return: list of records in the .shp data
        :rtype: list

        See examples for the method
        :meth:`SHPReadParse.write_to_shapefile()<pydriosm.reader.SHPReadParse.write_to_shapefile>`.
        """

        dtype_shp_type = {
            'object': 'C',
            'int64': 'N',
            'int32': 'N',
            'float64': 'F',
            'float32': 'F',
            'bool': 'L',
            'datetime64': 'D',
        }

        fields = []

        for field_name, dtype, in data[field_names].dtypes.items():
            try:
                max_size = data[field_name].map(len).max()
            except TypeError:
                max_size = data[field_name].astype(str).map(len).max()

            if 'float' in dtype.name:
                decimal = decimal_precision
            else:
                decimal = 0

            fields.append((field_name, dtype_shp_type[dtype.name], max_size, decimal))

        return fields

    @classmethod
    def write_to_shapefile(cls, data, write_to, shp_filename=None, decimal_precision=5,
                           ret_shp_pathname=False, verbose=False):
        """
        Save .shp data as a shapefile by `PyShp <https://github.com/GeospatialPython/pyshp>`_.

        :param data: data of a shapefile
        :type data: pandas.DataFrame
        :param write_to: pathname of a directory where the shapefile data is to be saved
        :type write_to: str
        :param shp_filename: filename (or pathname) of the target .shp file, defaults to ``None``;
            when ``shp_filename=None``, it is by default the basename of ``write_to``
        :type shp_filename: str or os.PahtLike[str] or None
        :param decimal_precision: decimal precision for writing float records, defaults to ``5``
        :type decimal_precision: int
        :param ret_shp_pathname: whether to return the pathname of the output .shp file,
            defaults to ``False``
        :type ret_shp_pathname: bool
        :param verbose: whether to print relevant information in console, defaults to ``False``
        :type verbose: bool or int

        **Examples**::

            >>> from pydriosm.reader import SHPReadParse
            >>> from pydriosm.downloader import GeofabrikDownloader
            >>> from pyhelpers.dirs import cd, delete_dir
            >>> import os
            >>> import glob

            >>> # Download the shapefile data of London as an example
            >>> subrgn_name = 'london'
            >>> file_format = ".shp"
            >>> dwnld_dir = "tests\\osm_data"

            >>> gfd = GeofabrikDownloader()

            >>> gfd.download_osm_data(subrgn_name, file_format, dwnld_dir, verbose=True)
            To download .shp.zip data of the following geographic (sub)region(s):
                Greater London
            ? [No]|Yes: yes
            Downloading "greater-london-latest-free.shp.zip"
                to "tests\\osm_data\\greater-london\\" ... Done.

            >>> london_shp_zip = gfd.data_paths[0]
            >>> os.path.relpath(london_shp_zip)
            'tests\\osm_data\\greater-london\\greater-london-latest-free.shp.zip'

            >>> # Extract the 'railways' layer of the downloaded .shp.zip file
            >>> lyr_name = 'railways'

            >>> railways_shp_dir = SHPReadParse.unzip_shp_zip(
            ...     london_shp_zip, layer_names=lyr_name, verbose=True, ret_extract_dir=True)
            Extracting the following layer(s):
                'railways'
                from "tests\\osm_data\\greater-london\\greater-london-latest-free.shp.zip"
                  to "tests\\osm_data\\greater-london\\greater-london-latest-free-shp\\"
            Done.
            >>> # Check out the output directory
            >>> os.path.relpath(railways_shp_dir)
            'tests\\osm_data\\greater-london\\greater-london-latest-free-shp'

            >>> # Get the pathname of the .shp data of 'railways'
            >>> path_to_railways_shp = glob.glob(cd(railways_shp_dir, f"*{lyr_name}*.shp"))[0]
            >>> os.path.relpath(path_to_railways_shp)  # Check the pathname of the .shp file
            'tests\\osm_data\\greater-london\\greater-london-latest-free-shp\\gis_osm_railwa...

            >>> # Read the .shp file
            >>> london_railways_shp = SHPReadParse.read_shp(path_to_railways_shp)

            >>> # Create a new directory for saving the 'railways' data
            >>> railways_subdir = cd(os.path.dirname(railways_shp_dir), lyr_name)
            >>> os.path.relpath(railways_subdir)
            'tests\\osm_data\\greater-london\\railways'

            >>> # Save the data of 'railways' to the new directory
            >>> path_to_railways_shp_ = SHPReadParse.write_to_shapefile(
            ...     london_railways_shp, railways_subdir, ret_shp_pathname=True, verbose=True)
            Writing data to "tests\\osm_data\\greater-london\\railways\\railways.*" ... Done.
            >>> os.path.basename(path_to_railways_shp_)
            'railways.shp'

            >>> # If `shp_filename` is specified
            >>> path_to_railways_shp_ = SHPReadParse.write_to_shapefile(
            ...     london_railways_shp, railways_subdir, shp_filename="rail_data",
            ...     ret_shp_pathname=True, verbose=True)
            Writing data to "tests\\osm_data\\greater-london\\railways\\rail_data.*" ... Done.
            >>> os.path.basename(path_to_railways_shp_)
            'rail_data.shp'

            >>> # Retrieve the saved the .shp file
            >>> london_railways_shp_ = SHPReadParse.read_shp(path_to_railways_shp_)

            >>> # Check if the retrieved .shp data is equal to the original one
            >>> london_railways_shp_.equals(london_railways_shp)
            True

            >>> # Delete the download/data directory
            >>> delete_dir(gfd.download_dir, verbose=True)
            To delete the directory "tests\\osm_data\\" (Not empty)
            ? [No]|Yes: yes
            Deleting "tests\\osm_data\\" ... Done.
        """

        filename_ = os.path.basename(write_to) if shp_filename is None else copy.copy(shp_filename)
        filename = os.path.splitext(filename_)[0]
        write_to_ = os.path.join(os.path.dirname(write_to), filename)

        if verbose:
            print(f'Writing data to "{os.path.relpath(write_to_)}.*"', end=" ... ")

        try:
            key_column_names = ['coordinates', 'shape_type']
            dat = data.copy()

            if 'geometry' in data:
                coords_and_shape_type = pd.DataFrame(
                    dat['geometry'].map(cls._convert_to_coords_and_shape_type).to_list(),
                    columns=key_column_names, index=dat.index)
                del dat['geometry']
                dat = pd.concat([dat, coords_and_shape_type], axis=1)

            field_names = [x for x in dat.columns if x not in key_column_names]

            shape_type = dat['shape_type'].unique()[0]

            with pyshp.Writer(target=write_to_, shapeType=shape_type, autoBalance=True) as w:
                w.fields = cls._specify_pyshp_fields(
                    data=dat, field_names=field_names, decimal_precision=decimal_precision)

                for i in dat.index:
                    w.record(*dat.loc[i, field_names].to_list())

                    # s = pyshp.Shape(shapeType=w.shapeType, points=dat.loc[i, 'coordinates'])
                    coordinates = dat.loc[i, 'coordinates']
                    if shape_type == 1:
                        coordinates = coordinates[0]
                    elif shape_type == 5:
                        coordinates = [[list(coords) for coords in coordinates]]
                    s = {'type': cls.SHAPE_TYPE_GEOM_NAME[shape_type], 'coordinates': coordinates}
                    w.shape(s)

            # Write .cpg
            with open(f"{write_to_}.cpg", "w") as cpg_file:
                cpg_file.write(cls.ENCODING)

            # Write .prj
            with open(f"{write_to_}.prj", "w") as prj_file:
                prj_file.write(cls.EPSG4326_WGS84_ESRI_WKT)

            if verbose:
                print("Done.")

            if ret_shp_pathname:
                return f"{write_to_}.shp"

        except Exception as e:
            print(f"Failed. {e}")

    @classmethod
    def _make_feat_shp_pathname(cls, shp_pathname, feature_names_):
        """
        Specify a pathname(s) for saving data of one (or multiple) given feature(s)
        by appending the feature name(s) to the filename of its (or their) parent layer's shapefile).

        :param shp_pathname: pathname of a shapefile of a layer
        :type shp_pathname: str or os.PathLike[str]
        :param feature_names_: name (or names) of one (or multiple) feature(s) in a shapefile of a layer
        :type feature_names_: list
        :return: pathname(s) of the data of the given ``feature_names``
        :rtype: list

        **Examples**::

            >>> from pydriosm.reader import SHPReadParse
            >>> import os

            >>> fn = "gis_osm_railways_free_1.shp"
            >>> feats = ['rail']
            >>> pn = SHPReadParse._make_feat_shp_pathname(shp_pathname=fn, feature_names_=feats)
            >>> len(pn)
            1
            >>> os.path.relpath(pn[0])
            'gis_osm_railways_free_1_rail.shp'

            >>> fn = "tests\\osm_data\\greater-london\\gis_osm_transport_free_1.shp"
            >>> feats = ['railway_station', 'bus_stop', 'bus_station']
            >>> pn = SHPReadParse._make_feat_shp_pathname(shp_pathname=fn, feature_names_=feats)
            >>> len(pn)
            3
            >>> pn
            ['tests\\osm_data\\greater-london\\gis_osm_transport_a_free_1_railway_station.shp',
             'tests\\osm_data\\greater-london\\gis_osm_transport_a_free_1_bus_stop.shp',
             'tests\\osm_data\\greater-london\\gis_osm_transport_a_free_1_bus_station.shp']
        """

        shp_dir_path, shp_filename_ = os.path.split(shp_pathname)
        shp_filename, ext = os.path.splitext(shp_filename_)

        # # filename_for_dir = re.search('gis_osm_(.*?)_(a_)?', fn_for_dir_).group(1)
        # layer_name = cls.find_shp_layer_name(shp_filename_)

        if len(feature_names_) > 0:
            feat_shp_pathnames = [
                os.path.join(shp_dir_path, f"{shp_filename}_{f}{ext}") for f in feature_names_]
        else:
            feat_shp_pathnames = []

        return feat_shp_pathnames

    @classmethod
    def _write_feat_shp(cls, data, feat_col_name, feat_shp_pathnames_):
        """
        Write the data of selected features of a layer to a shapefile
        (or shapefiles given multiple shape types).

        :param data: data of shapefiles
        :type data: pandas.DataFrame or geopandas.GeoDataFrame
        :param feat_col_name: name of the column that contains feature names;
            valid values can include ``'fclass'`` and ``'type'``
        :type feat_col_name: str
        :param feat_shp_pathnames_: (temporary) pathname for the output shapefile(s)
        :type feat_shp_pathnames_: str
        :return: pathnames of the output shapefiles
        :rtype: list
        """

        # if hasattr(data, 'geom_type'):
        #     type_col_name = data.geom_type
        # else:
        #     if 'geometry' in data.columns:
        #         type_col_name = data['geometry'].map(lambda x: x.geom_type)
        #     else:
        #         type_col_name = 'shape_type'

        feat_shp_pathnames = []

        for feat_name, dat in data.groupby(feat_col_name):
            feat_shp_pathname = [
                x for x in feat_shp_pathnames_ if os.path.splitext(x)[0].endswith(feat_name)][0]
            # feat_shp_pathname_, ext = os.path.splitext(feat_shp_pathname)
            # shape_type_ = cls.SHAPE_TYPE_GEOM_NAME[shape_type].lower()
            # feat_shp_pathname = f"{feat_shp_pathname_}-{shape_type_}{ext}"

            if isinstance(dat, pd.DataFrame) and not hasattr(dat, 'crs'):
                cls.write_to_shapefile(data=dat, write_to=feat_shp_pathname)
            else:
                gpd = _check_dependency('geopandas')
                assert isinstance(dat, gpd.GeoDataFrame)
                # os.makedirs(os.path.dirname(feat_shp_pathnames), exist_ok=True)
                dat.to_file(feat_shp_pathname, driver=cls.VECTOR_DRIVER, crs=cls.EPSG4326_WGS84_PROJ4)

            feat_shp_pathnames.append(feat_shp_pathname)

        return feat_shp_pathnames

    @classmethod
    def read_layer_shps(cls, shp_pathnames, feature_names=None, save_feat_shp=False,
                        ret_feat_shp_path=False, **kwargs):
        """
        Read a layer of OSM shapefile data.

        :param shp_pathnames: pathname of a .shp file, or pathnames of multiple shapefiles
        :type shp_pathnames: str or list
        :param feature_names: class name(s) of feature(s), defaults to ``None``
        :type feature_names: str or list or None
        :param save_feat_shp: (when ``fclass`` is not ``None``)
            whether to save data of the ``fclass`` as shapefile, defaults to ``False``
        :type save_feat_shp: bool
        :param ret_feat_shp_path: (when ``save_fclass_shp=True``)
            whether to return the path to the saved data of ``fclass``, defaults to ``False``
        :type ret_feat_shp_path: bool
        :param kwargs: [optional] parameters of the method
            :meth:`SHPReadParse.read_shp()<pydriosm.reader.SHPReadParse.read_shp>`
        :return: parsed shapefile data; and optionally,
            pathnames of the shapefiles of the specified features (when ``ret_feat_shp_path=True``)
        :rtype: pandas.DataFrame or geopandas.GeoDataFrame or tuple

        .. _`geopandas.GeoDataFrame.to_file()`:
            https://geopandas.org/reference.html#geopandas.GeoDataFrame.to_file

        **Examples**::

            >>> from pydriosm.reader import SHPReadParse
            >>> from pydriosm.downloader import GeofabrikDownloader
            >>> from pyhelpers.dirs import cd, delete_dir
            >>> import os

            >>> # Download the shapefile data of London as an example
            >>> subrgn_name = 'london'
            >>> file_format = ".shp"
            >>> dwnld_dir = "tests\\osm_data"

            >>> gfd = GeofabrikDownloader()

            >>> gfd.download_osm_data(subrgn_name, file_format, dwnld_dir, verbose=True)
            To download .shp.zip data of the following geographic (sub)region(s):
                Greater London
            ? [No]|Yes: yes
            Downloading "greater-london-latest-free.shp.zip"
                to "tests\\osm_data\\greater-london\\" ... Done.

            >>> london_shp_zip = gfd.data_paths[0]
            >>> os.path.relpath(london_shp_zip)
            'tests\\osm_data\\greater-london\\greater-london-latest-free.shp.zip'

            >>> # Extract the downloaded .shp.zip file
            >>> london_shp_dir = SHPReadParse.unzip_shp_zip(
            ...     london_shp_zip, layer_names='railways', ret_extract_dir=True)
            >>> os.listdir(london_shp_dir)
            ['gis_osm_railways_free_1.cpg',
             'gis_osm_railways_free_1.dbf',
             'gis_osm_railways_free_1.prj',
             'gis_osm_railways_free_1.shp',
             'gis_osm_railways_free_1.shx']
            >>> london_railways_shp_path = cd(london_shp_dir, "gis_osm_railways_free_1.shp")

            >>> # Read the 'railways' layer
            >>> london_railways_shp = SHPReadParse.read_layer_shps(london_railways_shp_path)
            >>> london_railways_shp.head()
               osm_id  code  ...                                        coordinates shape_type
            0   30804  6101  ...  [(0.0048644, 51.6279262), (0.0061979, 51.62926...          3
            1  101298  6103  ...  [(-0.2249906, 51.493682), (-0.2251678, 51.4945...          3
            2  101486  6103  ...  [(-0.2055497, 51.5195429), (-0.2051377, 51.519...          3
            3  101511  6101  ...  [(-0.2119027, 51.5241906), (-0.2108059, 51.523...          3
            4  282898  6103  ...  [(-0.1862586, 51.6159083), (-0.1868721, 51.613...          3
            [5 rows x 9 columns]

            >>> # Extract only the features labelled 'rail' and save the extracted data to file
            >>> railways_rail_shp, railways_rail_shp_path = SHPReadParse.read_layer_shps(
            ...     london_railways_shp_path, feature_names='rail', save_feat_shp=True,
            ...     ret_feat_shp_path=True)
            >>> railways_rail_shp['fclass'].unique()
            array(['rail'], dtype=object)

            >>> type(railways_rail_shp_path)
            list
            >>> len(railways_rail_shp_path)
            1
            >>> os.path.basename(railways_rail_shp_path[0])
            'gis_osm_railways_free_1_rail.shp'

            >>> # Delete the download/data directory
            >>> delete_dir(dwnld_dir, verbose=True)
            To delete the directory "tests\\osm_data\\" (Not empty)
            ? [No]|Yes: yes
            Deleting "tests\\osm_data\\" ... Done.
        """

        lyr_shp_pathnames = [shp_pathnames] if isinstance(shp_pathnames, str) else shp_pathnames

        feat_shp_pathnames = None

        if len(lyr_shp_pathnames) == 0:
            data = None

        else:
            dat_dict = {
                lyr_shp_pathname: cls.read_shp(shp_pathname=lyr_shp_pathname, **kwargs)
                for lyr_shp_pathname in lyr_shp_pathnames}
            data = pd.concat(dat_dict.values(), axis=0, ignore_index=True)

            if feature_names:
                feat_names = [feature_names] if isinstance(feature_names, str) else feature_names
                feat_col_name = [x for x in data.columns if x in {'type', 'fclass'}][0]
                feat_names_ = [find_similar_str(x, data[feat_col_name].unique()) for x in feat_names]

                data = data.query(f'{feat_col_name} in @feat_names_')

                if data.empty:
                    data = None

                elif save_feat_shp:
                    feat_shp_pathnames = []

                    for lyr_shp_pathname in lyr_shp_pathnames:
                        dat = dat_dict[lyr_shp_pathname]
                        valid_feature_names = dat[feat_col_name].unique()
                        feature_names_ = [x for x in feat_names_ if x in valid_feature_names]

                        feat_shp_pathnames_ = cls._make_feat_shp_pathname(
                            shp_pathname=lyr_shp_pathname, feature_names_=feature_names_)

                        feat_shp_pathnames_temp = cls._write_feat_shp(
                            data=dat.query(f'{feat_col_name} in @feature_names_'),
                            feat_col_name=feat_col_name, feat_shp_pathnames_=feat_shp_pathnames_)

                        feat_shp_pathnames += feat_shp_pathnames_temp

        if ret_feat_shp_path:
            data = data, feat_shp_pathnames

        return data

    @classmethod
    def merge_shps(cls, shp_pathnames, path_to_merged_dir, engine='pyshp', **kwargs):
        """
        Merge multiple shapefiles.

        :param shp_pathnames: list of paths to shapefiles (in .shp format)
        :type shp_pathnames: list
        :param path_to_merged_dir: path to a directory where the merged files are to be saved
        :type path_to_merged_dir: str
        :param engine: the open-source package that is used to merge/save shapefiles;
            options include: ``'pyshp'`` (default) and ``'geopandas'`` (or ``'gpd'``)
            when ``engine='geopandas'``, this function relies on `geopandas.GeoDataFrame.to_file()`_;
            otherwise, it by default uses `shapefile.Writer()`_
        :type engine: str

        .. _`shapefile.Writer()`:
            https://github.com/GeospatialPython/pyshp#writing-shapefiles
        .. _`geopandas.GeoDataFrame.to_file()`:
            https://geopandas.org/reference.html#geopandas.GeoDataFrame.to_file

        .. note::

            - When ``engine='geopandas'`` (or ``engine='gpd'``), the implementation of this function
              requires that `GeoPandas <https://geopandas.org/>`_ is installed.

        .. seealso::

            - Examples for the function :func:`~pydriosm.reader.SHPReadParse.merge_layer_shps`.
            - Resource: https://github.com/GeospatialPython/pyshp
        """

        if engine in {'geopandas', 'gpd'}:
            gpd = _check_dependency(name='geopandas')

            shp_data = collections.defaultdict(list)
            for shp_pathname in shp_pathnames:
                dat = gpd.read_file(shp_pathname)
                geo_typ = dat.geom_type.unique()[0]
                shp_data[geo_typ].append(dat)

            for geo_typ, shp_dat_list in shp_data.items():
                out_fn = os.path.join(path_to_merged_dir, f"{geo_typ.lower()}.shp")
                shp_dat = gpd.GeoDataFrame(pd.concat(shp_dat_list, ignore_index=True))
                shp_dat.to_file(filename=out_fn, driver=cls.VECTOR_DRIVER, crs=cls.EPSG4326_WGS84_PROJ4)

        else:  # method == 'pyshp': (default)
            # with pyshp.Writer(path_to_merged_dir) as w:
            #     for f in shp_pathnames:
            #         with pyshp.Reader(f) as r:
            #             w.fields = r.fields[1:]  # skip first deletion field
            #             w.shapeType = r.shapeType
            #             for shaperec in r.iterShapeRecords():
            #                 w.record(*shaperec.record)
            #                 w.shape(shaperec.shape)

            kwargs.update({'ret_feat_shp_path': False})
            shp_data = cls.read_layer_shps(shp_pathnames, **kwargs)
            if 'geometry' in shp_data.columns:
                k = shp_data['geometry'].map(lambda x: x.geom_type)
            else:
                k = 'shape_type'

            for geo_typ, dat in shp_data.groupby(k):
                if isinstance(k, str):
                    geo_typ = cls.SHAPE_TYPE_GEOM_NAME[geo_typ]
                out_fn = os.path.join(path_to_merged_dir, f"{geo_typ.lower()}.shp")
                cls.write_to_shapefile(data=dat, write_to=out_fn)

                # Write .cpg
                with open(out_fn.replace(".shp", ".cpg"), mode="w") as cpg:
                    cpg.write(cls.ENCODING)
                # Write .prj
                with open(out_fn.replace(".shp", ".prj"), mode="w") as prj:
                    prj.write(cls.EPSG4326_WGS84_ESRI_WKT)

    @classmethod
    def _extract_files(cls, shp_zip_pathnames, layer_name, verbose=False):
        path_to_extract_dirs = []
        for zfp in shp_zip_pathnames:
            extract_dir = cls.unzip_shp_zip(
                shp_zip_pathname=zfp, layer_names=layer_name, verbose=True if verbose == 2 else False,
                ret_extract_dir=True)
            path_to_extract_dirs.append(extract_dir)

        return path_to_extract_dirs

    @classmethod
    def _copy_tempfiles(cls, subrgn_names_, layer_name, path_to_extract_dirs, path_to_merged_dir_temp):
        # Copy files into a temp directory
        paths_to_temp_files = []
        for subregion_name, path_to_extract_dir in zip(subrgn_names_, path_to_extract_dirs):
            orig_filename_list = glob.glob1(path_to_extract_dir, f"*{layer_name}*")
            for orig_filename in orig_filename_list:
                orig = os.path.join(path_to_extract_dir, orig_filename)
                dest = os.path.join(
                    path_to_merged_dir_temp,
                    f"{subregion_name.lower().replace(' ', '-')}_{orig_filename}")
                shutil.copyfile(orig, dest)
                paths_to_temp_files.append(dest)

        return paths_to_temp_files

    @classmethod
    def _make_merged_dir(cls, output_dir, path_to_data_dir, merged_dirname_temp, suffix):
        if output_dir:
            path_to_merged_dir = validate_dir(path_to_dir=output_dir)
        else:
            path_to_merged_dir = os.path.join(
                path_to_data_dir, merged_dirname_temp.replace(suffix, "", -1))
        os.makedirs(path_to_merged_dir, exist_ok=True)

        return path_to_merged_dir

    @classmethod
    def _transfer_files(cls, engine, path_to_merged_dir, path_to_merged_dir_temp, prefix, suffix):
        if engine in {'geopandas', 'gpd'}:
            if not os.listdir(path_to_merged_dir):
                temp_dirs = []
                for temp_output_f in glob.glob(os.path.join(path_to_merged_dir + "*", f"{prefix}-*")):
                    output_file = path_to_merged_dir_temp.replace(suffix, "")
                    shutil.move(temp_output_f, output_file)
                    temp_dirs.append(os.path.dirname(temp_output_f))

                for temp_dir in set(temp_dirs):
                    shutil.rmtree(temp_dir)

        else:  # engine == 'pyshp': (default)
            temp_dir = os.path.dirname(path_to_merged_dir)
            paths_to_output_files_temp_ = [
                glob.glob(os.path.join(temp_dir, f"{prefix}-*.{ext}")) for ext in {"dbf", "shp", "shx"}]
            paths_to_output_files_temp = itertools.chain.from_iterable(paths_to_output_files_temp_)

            for temp_output_f in paths_to_output_files_temp:
                output_file = os.path.join(
                    path_to_merged_dir, os.path.basename(temp_output_f).replace(suffix, ""))
                shutil.move(temp_output_f, output_file)

    @classmethod
    def merge_layer_shps(cls, shp_zip_pathnames, layer_name, engine='pyshp', rm_zip_extracts=True,
                         output_dir=None, rm_shp_temp=True, ret_shp_pathname=False, verbose=False):
        """
        Merge shapefiles over a layer for multiple geographic regions.

        :param shp_zip_pathnames: list of paths to data of shapefiles (in .shp.zip format)
        :type shp_zip_pathnames: list
        :param layer_name: name of a layer (e.g. 'railways')
        :type layer_name: str
        :param engine: the open-source package used to merge/save shapefiles;
            options include: ``'pyshp'`` (default) and ``'geopandas'`` (or ``'gpd'``)
            if ``engine='geopandas'``, this function relies on `geopandas.GeoDataFrame.to_file()`_;
            otherwise, it by default uses `shapefile.Writer()`_
        :type engine: str
        :param rm_zip_extracts: whether to delete the extracted files, defaults to ``False``
        :type rm_zip_extracts: bool
        :param rm_shp_temp: whether to delete temporary layer files, defaults to ``False``
        :type rm_shp_temp: bool
        :param output_dir: if ``None`` (default), use the layer name as the name of the folder
            where the merged .shp files will be saved
        :type output_dir: str or None
        :param ret_shp_pathname: whether to return the pathname of the merged .shp file,
            defaults to ``False``
        :type ret_shp_pathname: bool
        :param verbose: whether to print relevant information in console, defaults to ``False``
        :type verbose: bool or int
        :return: the path to the merged file when ``ret_merged_shp_path=True``
        :rtype: list

        .. _`geopandas.GeoDataFrame.to_file()`:
            https://geopandas.org/reference.html#geopandas.GeoDataFrame.to_file
        .. _`shapefile.Writer()`:
            https://github.com/GeospatialPython/pyshp#writing-shapefiles

        .. note::

            - This function does not create projection (.prj) for the merged map.
              See also [`MMS-1 <https://code.google.com/archive/p/pyshp/wikis/CreatePRJfiles.wiki>`_].
            - For valid ``layer_name``, check the function
              :func:`~pydriosm.utils.valid_shapefile_layer_names`.

        .. _pydriosm-reader-SHPReadParse-merge_layer_shps:

        **Examples**::

            >>> # To merge 'railways' layers of Greater Manchester and West Yorkshire"

            >>> from pydriosm.reader import SHPReadParse
            >>> from pydriosm.downloader import GeofabrikDownloader
            >>> from pyhelpers.dirs import delete_dir
            >>> import os

            >>> # Download the .shp.zip file of Manchester and West Yorkshire
            >>> subrgn_names = ['Greater Manchester', 'West Yorkshire']
            >>> file_fmt = ".shp"
            >>> data_dir = "tests\\osm_data"

            >>> gfd = GeofabrikDownloader()

            >>> gfd.download_osm_data(subrgn_names, file_fmt, data_dir, verbose=True)
            To download .shp.zip data of the following geographic (sub)region(s):
                Greater Manchester
                West Yorkshire
            ? [No]|Yes: yes
            Downloading "greater-manchester-latest-free.shp.zip"
                to "tests\\osm_data\\greater-manchester\\" ... Done.
            Downloading "west-yorkshire-latest-free.shp.zip"
                to "tests\\osm_data\\west-yorkshire\\" ... Done.

            >>> os.path.relpath(gfd.download_dir)
            'tests\\osm_data'
            >>> len(gfd.data_paths)
            2

            >>> # Merge the layers of 'railways' of the two subregions
            >>> merged_shp_path = SHPReadParse.merge_layer_shps(
            ...     gfd.data_paths, layer_name='railways', verbose=True, ret_shp_pathname=True)
            Merging the following shapefiles:
                "greater-manchester_gis_osm_railways_free_1.shp"
                "west-yorkshire_gis_osm_railways_free_1.shp"
                    In progress ... Done.
                    Find the merged shapefile at "tests\\osm_data\\gre_man-wes_yor-railways\\".

            >>> # Check the pathname of the merged shapefile
            >>> type(merged_shp_path)
            list
            >>> len(merged_shp_path)
            1
            >>> os.path.relpath(merged_shp_path[0])
            'tests\\osm_data\\gre_man-wes_yor-railways\\linestring.shp'

            >>> # Read the merged .shp file
            >>> merged_shp_data = SHPReadParse.read_shp(merged_shp_path[0], emulate_gpd=True)
            >>> merged_shp_data.head()
                osm_id  code  ... tunnel                                           geometry
            0   928999  6101  ...      F  LINESTRING (-2.2844621 53.4802635, -2.2851997 ...
            1   929904  6101  ...      F  LINESTRING (-2.2917977 53.4619559, -2.2924877 ...
            2   929905  6102  ...      F  LINESTRING (-2.2794048 53.4605819, -2.2799722 ...
            3  3663332  6102  ...      F  LINESTRING (-2.2382139 53.4817985, -2.2381708 ...
            4  3996086  6101  ...      F  LINESTRING (-2.6003053 53.4604346, -2.6005261 ...
            [5 rows x 8 columns]

            >>> # Delete the test data directory
            >>> delete_dir(gfd.download_dir, verbose=True)
            To delete the directory "tests\\osm_data\\" (Not empty)
            ? [No]|Yes: yes
            Deleting "tests\\osm_data\\" ... Done.

        .. seealso::

            - Examples for the method
              :meth:`GeofabrikReader.merge_subregion_layer_shp()
              <pydriosm.reader.GeofabrikReader.merge_subregion_layer_shp>`.
        """

        path_to_extract_dirs = cls._extract_files(
            shp_zip_pathnames=shp_zip_pathnames, layer_name=layer_name, verbose=verbose)

        # Specify a directory that stores files for the specific layer
        subrgn_names_ = [
            re.search(r'.*(?=\.shp\.zip)', os.path.basename(x).replace("-latest-free", "")).group(0)
            for x in shp_zip_pathnames]

        suffix = "_temp"
        prefix = "-".join(["_".join([y[:3] for y in re.split(r'[- ]', x)]) for x in subrgn_names_])
        # prefix = "_".join([x.lower().replace(' ', '-') for x in region_names]) + "_"
        path_to_data_dir = os.path.commonpath(shp_zip_pathnames)
        merged_dirname_temp = f"{prefix}-{layer_name}{suffix}"
        path_to_merged_dir_temp = os.path.join(path_to_data_dir, merged_dirname_temp)
        os.makedirs(path_to_merged_dir_temp, exist_ok=True)

        paths_to_temp_files = cls._copy_tempfiles(
            subrgn_names_=subrgn_names_, layer_name=layer_name,
            path_to_extract_dirs=path_to_extract_dirs, path_to_merged_dir_temp=path_to_merged_dir_temp)

        # Get the paths to the target .shp files
        paths_to_shp_files = [x for x in paths_to_temp_files if x.endswith(".shp")]

        if verbose:
            print("Merging the following shapefiles:")
            print("\t{}".format("\n\t".join(f"\"{os.path.basename(f)}\"" for f in paths_to_shp_files)))
            print("\t\tIn progress ... ", end="")

        try:
            path_to_merged_dir = cls._make_merged_dir(
                output_dir=output_dir, path_to_data_dir=path_to_data_dir,
                merged_dirname_temp=merged_dirname_temp, suffix=suffix)

            cls.merge_shps(
                shp_pathnames=paths_to_shp_files, path_to_merged_dir=path_to_merged_dir, engine=engine)

            cls._transfer_files(
                engine=engine, path_to_merged_dir=path_to_merged_dir,
                path_to_merged_dir_temp=path_to_merged_dir_temp, prefix=prefix, suffix=suffix)

            if verbose:
                print("Done.")

            if rm_zip_extracts:
                for path_to_extract_dir in path_to_extract_dirs:
                    shutil.rmtree(path_to_extract_dir)

            if rm_shp_temp:
                shutil.rmtree(path_to_merged_dir_temp)

            if verbose:
                print(f"\t\tFind the merged shapefile at \"{os.path.relpath(path_to_merged_dir)}\\\".")

            if ret_shp_pathname:
                path_to_merged_shp = glob.glob(os.path.join(f"{path_to_merged_dir}*", "*.shp"))
                # if len(path_to_merged_shp) == 1:
                #     path_to_merged_shp = path_to_merged_shp[0]
                return path_to_merged_shp

        except Exception as e:
            print(f"Failed. {e}")


class VarReadParse(Transformer):
    """
    Read/parse `OSM`_ data of various formats (other than PBF and Shapefile).

    .. _`OSM`: https://www.openstreetmap.org/
    """

    #: set: Valid file formats.
    FILE_FORMATS = {'.csv.xz', 'geojson.xz'}

    # == .osm.bz2 / .bz2 ===========================================================================

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

    # == .csv.xz ===================================================================================

    @classmethod
    def _prep_csv_xz(cls, x):
        y = x.rstrip('\t\n').split('\t')
        return y

    @classmethod
    def read_csv_xz(cls, csv_xz_pathname, col_names=None):
        """
        Read/parse a compressed CSV (.csv.xz) data file.

        :param csv_xz_pathname: path to a .csv.xz data file
        :type csv_xz_pathname: str
        :param col_names: column names of .csv.xz data, defaults to ``None``
        :type col_names: list or None
        :return: tabular data of the CSV file
        :rtype: pandas.DataFrame

        See examples for the method
        :meth:`BBBikeReader.read_csv_xz()<pydriosm.reader.BBBikeReader.read_csv_xz>`.
        """

        if col_names is None:
            col_names = ['type', 'id', 'feature', 'note']

        with lzma.open(csv_xz_pathname, mode='rt', encoding='utf-8') as f:
            with multiprocessing.Pool(processes=os.cpu_count() - 1) as p:
                csv_xz = pd.DataFrame.from_records(
                    p.map(cls._prep_csv_xz, f.readlines()), columns=col_names)

        return csv_xz

    # == .geojson.xz ===============================================================================

    @classmethod
    def read_geojson_xz(cls, geojson_xz_pathname, engine=None, parse_geometry=False):
        """
        Read/parse a compressed Osmium GeoJSON (.geojson.xz) data file.

        :param geojson_xz_pathname: path to a .geojson.xz data file
        :type geojson_xz_pathname: str
        :param engine: an open-source Python package for JSON serialization, defaults to ``None``;
            when ``engine=None``, it refers to the built-in `json`_ module; otherwise options include:
            ``'ujson'`` (for `UltraJSON`_), ``'orjson'`` (for `orjson`_) and
            ``'rapidjson'`` (for `python-rapidjson`_)
        :type engine: str or None
        :param parse_geometry: whether to reformat coordinates into a geometric object,
            defaults to ``False``
        :type parse_geometry: bool
        :return: tabular data of the Osmium GeoJSON file
        :rtype: pandas.DataFrame

        .. _`json`: https://docs.python.org/3/library/json.html#module-json
        .. _`UltraJSON`: https://pypi.org/project/ujson/
        .. _`orjson`: https://pypi.org/project/orjson/
        .. _`python-rapidjson`: https://pypi.org/project/python-rapidjson/

        See examples for the method
        :meth:`BBBikeReader.read_geojson_xz()<pydriosm.reader.BBBikeReader.read_geojson_xz>`.
        """

        engine_ = check_json_engine(engine=engine)

        with lzma.open(filename=geojson_xz_pathname, mode='rt', encoding='utf-8') as f:
            raw_data = engine_.loads(f.read())

        data = pd.DataFrame.from_dict(raw_data['features'])

        if 'type' in data.columns:
            if data['type'].nunique() == 1:
                del data['type']

        if parse_geometry:
            # data['geometry'] = data['geometry'].map(cls.transform_unitary_geometry)
            with warnings.catch_warnings():
                warnings.filterwarnings("ignore", category=shapely.errors.ShapelyDeprecationWarning)

                with multiprocessing.Pool(processes=os.cpu_count() - 1) as p:
                    geom_data = p.map(cls.transform_unitary_geometry, data['geometry'])

                data.loc[:, 'geometry'] = pd.Series(geom_data)

        return data


# == Reading data ==================================================================================

class _Reader:
    """
    Initialization of a data reader.
    """

    #: str: Name of the free download server.
    NAME = 'OSM Reader'
    #: str: Full name of the data resource.
    LONG_NAME = 'OpenStreetMap data reader and parser'
    #: str: Default data directory.
    DEFAULT_DATA_DIR = 'osm_data'

    #: PBFReadParse: Read/parse `PBF <https://wiki.openstreetmap.org/wiki/PBF_Format>`_ data.
    PBF = PBFReadParse
    #: SHPReadParse: Read/parse `Shapefile <https://wiki.openstreetmap.org/wiki/Shapefiles>`_ data.
    SHP = SHPReadParse
    #: VarReadParse: Read/parse `OSM`_ data of various formats (other than PBF and Shapefile).
    VAR = VarReadParse

    def __init__(self, max_tmpfile_size=None, data_dir=None, downloader=None, **kwargs):
        """
        :param max_tmpfile_size: defaults to ``None``,
            see also the function `pyhelpers.settings.gdal_configurations()`_
        :type max_tmpfile_size: int or None
        :param data_dir: directory where the data file is located/saved, defaults to ``None``;
            when ``data_dir=None``, it refers to the directory specified by the corresponding downloader
        :type data_dir: str or None
        :param downloader: class of a downloader, valid options include
            :class:`~pydriosm.downloader.GeofabrikDownloader` and
            :class:`~pydriosm.downloader.BBBikeDownloader`
        :type downloader: GeofabrikDownloader or BBBikeDownloader or None
        :param kwargs: [optional] parameters of the function `pyhelpers.settings.gdal_configurations()`_

        :ivar GeofabrikDownloader or BBBikeDownloader or None downloader:
            instance of the class :class:`~pydriosm.downloader.GeofabrikDownloader` or
            :class:`~pydriosm.downloader.BBBikeDownloader`

        .. _`pyhelpers.settings.gdal_configurations()`:
            https://pyhelpers.readthedocs.io/en/latest/_generated/
            pyhelpers.settings.gdal_configurations.html

        **Tests**::

            >>> from pydriosm.reader import _Reader

            >>> r = _Reader()

            >>> r.NAME
            'OSM Reader'

            >>> r.SHP
            pydriosm.reader.SHPReadParse
        """

        self.max_tmpfile_size = 5000 if max_tmpfile_size is None else max_tmpfile_size
        kwargs.update({'max_tmpfile_size': self.max_tmpfile_size})
        gdal_configurations(**kwargs)

        if downloader is None:
            self.downloader = _Downloader
        else:
            assert downloader in {GeofabrikDownloader, BBBikeDownloader}
            # noinspection PyCallingNonCallable
            self.downloader = downloader(download_dir=data_dir)
            for x in {'NAME', 'LONG_NAME', 'FILE_FORMATS'}:
                setattr(self, x, getattr(self.downloader, x))

    @classmethod
    def cdd(cls, *sub_dir, mkdir=False, **kwargs):
        """
        Change directory to default data directory and its subdirectories or a specific file.

        :param sub_dir: name of directory; names of directories (and/or a filename)
        :type sub_dir: str or os.PathLike[str]
        :param mkdir: whether to create a directory, defaults to ``False``
        :type mkdir: bool
        :param kwargs: [optional] parameters of the function `pyhelpers.dir.cd()`_
        :return: an absolute pathname to a directory (or a file)
        :rtype: str or os.PathLike[str]

        .. _`pyhelpers.dir.cd()`:
            https://pyhelpers.readthedocs.io/en/latest/_generated/pyhelpers.dir.cd.html

        **Tests**::

            >>> from pydriosm.reader import _Reader
            >>> import os

            >>> os.path.relpath(_Reader.cdd())
            'osm_data'

            >>> os.path.exists(_Reader.cdd())
            False
        """

        pathname = cd(cls.DEFAULT_DATA_DIR, *sub_dir, mkdir=mkdir, **kwargs)

        return pathname

    # noinspection PyTypeChecker
    @property
    def data_dir(self):
        """
        Name or pathname of a data directory.

        :return: name or pathname of a directory for saving downloaded data files
        :rtype: str or None

        **Tests**::

            >>> from pydriosm.reader import _Reader
            >>> from pydriosm.downloader import GeofabrikDownloader, BBBikeDownloader
            >>> import os

            >>> r = _Reader()
            >>> os.path.relpath(r.data_dir)
            'osm_data'

            >>> r = _Reader(downloader=GeofabrikDownloader)
            >>> os.path.relpath(r.data_dir)
            'osm_data\\geofabrik'

            >>> r = _Reader(downloader=BBBikeDownloader)
            >>> os.path.relpath(r.data_dir)
            'osm_data\\bbbike'
        """

        if hasattr(self.downloader, 'download_dir'):
            _data_dir = getattr(self.downloader, 'download_dir')
        else:
            _data_dir = validate_dir(self.downloader.DEFAULT_DOWNLOAD_DIR)

        return _data_dir

    @property
    def data_paths(self):
        """
        Pathnames of all data files.

        :return: pathnames of all data files
        :rtype: list

        **Tests**::

            >>> from pydriosm.reader import _Reader

            >>> r = _Reader()
            >>> r.data_paths
            []
        """

        if hasattr(self.downloader, 'download_dir'):
            _data_paths = getattr(self.downloader, 'data_paths')
        else:
            _data_paths = []

        return _data_paths

    # noinspection PyTypeChecker
    def get_file_path(self, subregion_name, osm_file_format, data_dir=None):
        """
        Get the path to an OSM data file (if available) of a specific file format
        for a geographic (sub)region.

        :param subregion_name: name of a geographic (sub)region (case-insensitive)
            that is available on a free download server
        :type subregion_name: str
        :param osm_file_format: format (file extension) of OSM data
        :type osm_file_format: str
        :param data_dir: directory where the data file is located/saved, defaults to ``None``;
            when ``data_dir=None``, it refers to the directory specified by the corresponding downloader
        :type data_dir: str or None
        :return: path to the data file
        :rtype: str or None

        **Tests**::

            >>> from pydriosm.reader import _Reader
            >>> from pydriosm.downloader import GeofabrikDownloader, BBBikeDownloader
            >>> import os

            >>> r = _Reader(downloader=GeofabrikDownloader)

            >>> subrgn_name = 'rutland'
            >>> file_format = ".pbf"
            >>> dat_dir = "tests\\osm_data"

            >>> path_to_rutland_pbf = r.get_file_path(subrgn_name, file_format, dat_dir)
            >>> os.path.relpath(path_to_rutland_pbf)
            'tests\\osm_data\\rutland\\rutland-latest.osm.pbf'
            >>> os.path.isfile(path_to_rutland_pbf)
            False

            >>> subrgn_name = 'leeds'
            >>> path_to_leeds_pbf = r.get_file_path(subrgn_name, file_format, dat_dir)
            >>> path_to_leeds_pbf is None
            True

            >>> # Change the `downloader` to `BBBikeDownloader`
            >>> r = _Reader(downloader=BBBikeDownloader)
            >>> path_to_leeds_pbf = r.get_file_path(subrgn_name, file_format, dat_dir)
            >>> os.path.relpath(path_to_leeds_pbf)
            'tests\\osm_data\\leeds\\Leeds.osm.pbf'
        """

        _, _, _, path_to_file = self.downloader.get_valid_download_info(
            subregion_name=subregion_name, osm_file_format=osm_file_format, download_dir=data_dir)

        # if path_to_file is None:
        #     raise InvalidSubregionNameError(subregion_name=subregion_name, msg=1)

        return path_to_file

    @classmethod
    def validate_file_path(cls, path_to_osm_file, osm_filename=None, data_dir=None):
        """
        Validate the pathname of an OSM data file.

        :param path_to_osm_file: pathname of an OSM data file
        :type path_to_osm_file: str or os.PathLike[str]
        :param osm_filename: filename of the OSM data file
        :type osm_filename: str
        :param data_dir: name or pathname of the data directory
        :type data_dir: str or os.PathLike[str]
        :return: validated pathname of the specified OSM data file
        :rtype: str

        **Tests**::

            >>> from pydriosm.reader import _Reader
            >>> import os

            >>> file_path = _Reader.validate_file_path("a\\b\\c.osm.pbf")
            >>> file_path
            'a\\b\\c.osm.pbf'
            >>> file_path = _Reader.validate_file_path("a\\b\\c.osm.pbf", "x.y.z", data_dir="a\\b")
            >>> os.path.relpath(file_path)
            'a\\b\\x.y.z'
        """

        if not data_dir:  # Go to default file path
            valid_file_path = path_to_osm_file

        else:
            osm_pbf_dir = validate_dir(path_to_dir=data_dir)
            osm_filename_ = os.path.basename(path_to_osm_file) if osm_filename is None else osm_filename
            valid_file_path = os.path.join(osm_pbf_dir, osm_filename_)

        return valid_file_path

    @classmethod
    def remove_extracts(cls, path_to_extract_dir, verbose):
        """
        Remove data extracts.

        :param path_to_extract_dir: pathname of the directory where data extracts are stored
        :type path_to_extract_dir: str or os.PathLike[str]
        :param verbose: whether to print relevant information in console as the function runs,
            defaults to ``False``
        :type verbose: bool or int

        See examples for the methods
        :meth:`GeofabrikReader.read_shp_zip()<pydriosm.reader.GeofabrikReader.read_shp_zip>` and
        :meth:`BBBikeReader.read_shp_zip()<pydriosm.reader.BBBikeReader.read_shp_zip>`.
        """

        if verbose:
            print(f"Deleting the extracts \"{os.path.relpath(path_to_extract_dir)}\\\"", end=" ... ")

        try:
            # for f in glob.glob(os.path.join(extract_dir, "gis_osm*")):
            #     # if layer not in f:
            #     os.remove(f)
            shutil.rmtree(path_to_extract_dir)

            if verbose:
                print("Done.")

        except Exception as e:
            print(f"Failed. {e}")

    @classmethod
    def validate_input_dtype(cls, var_input):
        """
        Validate the data type of the input variable.

        :param var_input: a variable
        :type var_input: str or list or None
        :return: validated input
        :rtype: list

        **Tests**::

            >>> from pydriosm.reader import _Reader

            >>> _Reader.validate_input_dtype(var_input=None)
            []

            >>> _Reader.validate_input_dtype(var_input='str')
            ['str']

            >>> _Reader.validate_input_dtype(var_input=['str'])
            ['str']
        """

        if var_input:
            var_input_ = [var_input] if isinstance(var_input, str) else var_input.copy()
        else:
            var_input_ = []

        return var_input_

    def _read_osm_pbf(self, pbf_pathname, chunk_size_limit, readable, expand, pickle_it,
                      path_to_pickle, ret_pickle_path, rm_pbf_file, verbose, **kwargs):
        if verbose:
            action_msg = "Parsing" if readable or expand else "Reading"
            print(f"{action_msg} \"{os.path.relpath(pbf_pathname)}\"", end=" ... ")

        try:
            number_of_chunks = get_number_of_chunks(
                file_or_obj=pbf_pathname, chunk_size_limit=chunk_size_limit)

            data = self.PBF.read_pbf(
                pbf_pathname=pbf_pathname, readable=readable, expand=expand,
                number_of_chunks=number_of_chunks, **kwargs)

            if verbose:
                print("Done.")

            if pickle_it and (readable or expand):
                save_pickle(data, path_to_pickle, verbose=verbose)

                if ret_pickle_path:
                    data = data, path_to_pickle

            if rm_pbf_file:
                remove_osm_file(pbf_pathname, verbose=verbose)

        except Exception as e:
            print(f"Failed. {e}")

            data = None

        return data

    def read_osm_pbf(self, subregion_name, data_dir=None, readable=False, expand=False,
                     parse_geometry=False, parse_properties=False, parse_other_tags=False,
                     update=False, download=True, pickle_it=False, ret_pickle_path=False,
                     rm_pbf_file=False, chunk_size_limit=50, verbose=False, **kwargs):
        """
        Read a PBF (.osm.pbf) data file of a geographic (sub)region.

        :param subregion_name: name of a geographic (sub)region (case-insensitive)
            that is available on Geofabrik free download server
        :type subregion_name: str
        :param data_dir: directory where the .osm.pbf data file is located/saved;
            if ``None``, the default local directory
        :type data_dir: str or None
        :param readable: whether to parse each feature in the raw data, defaults to ``False``
        :type readable: bool
        :param expand: whether to expand dict-like data into separate columns, defaults to ``False``
        :type expand: bool
        :param parse_geometry: whether to represent the ``'geometry'`` field
            in a `shapely.geometry`_ format, defaults to ``False``
        :type parse_geometry: bool
        :param parse_properties: whether to represent the ``'properties'`` field
            in a tabular format, defaults to ``False``
        :type parse_properties: bool
        :param parse_other_tags: whether to represent a ``'other_tags'`` (of ``'properties'``)
            in a `dict`_ format, defaults to ``False``
        :type parse_other_tags: bool
        :param download: whether to download/update the PBF data file of the given subregion,
            if it is not available at the specified path, defaults to ``True``
        :type download: bool
        :param update: whether to check to update pickle backup (if available), defaults to ``False``
        :type update: bool
        :param pickle_it: whether to save the .pbf data as a pickle file, defaults to ``False``
        :type pickle_it: bool
        :param ret_pickle_path: (when ``pickle_it=True``)
            whether to return a path to the saved pickle file
        :type ret_pickle_path: bool
        :param rm_pbf_file: whether to delete the downloaded .osm.pbf file, defaults to ``False``
        :type rm_pbf_file: bool
        :param chunk_size_limit: threshold (in MB) that triggers the use of chunk parser,
            defaults to ``50``;
            if the size of the .osm.pbf file (in MB) is greater than ``chunk_size_limit``,
            it will be parsed in a chunk-wise way
        :type chunk_size_limit: int or None
        :param verbose: whether to print relevant information in console as the function runs,
            defaults to ``False``
        :type verbose: bool or int
        :param kwargs: [optional] parameters of the method
            :meth:`PBFReadParse.read_pbf()<pydriosm.reader.PBFReadParse.read_pbf>`
        :return: dictionary of the .osm.pbf data;
            when ``pickle_it=True``, return a tuple of the dictionary and a path to the pickle file
        :rtype: dict or tuple or None

        .. _`shapely.geometry`: https://shapely.readthedocs.io/en/latest/manual.html#geometric-objects
        .. _`dict`: https://docs.python.org/3/library/stdtypes.html#dict

        See examples for the methods
        :meth:`GeofabrikReader.read_osm_pbf()<pydriosm.reader.GeofabrikReader.read_osm_pbf>` and
        :meth:`BBBikeReader.read_osm_pbf()<pydriosm.reader.BBBikeReader.read_osm_pbf>`.
        """

        osm_file_format = ".osm.pbf"

        subregion_name_, osm_pbf_filename, _, path_to_osm_pbf = \
            self.downloader.get_valid_download_info(
                subregion_name=subregion_name, osm_file_format=osm_file_format, download_dir=data_dir)

        if path_to_osm_pbf is not None:
            suffix = "-pbf.pkl" if readable else "-raw.pkl"
            path_to_pickle = path_to_osm_pbf.replace(osm_file_format, suffix)

            if os.path.isfile(path_to_pickle) and not update:
                osm_pbf_data = load_pickle(path_to_pickle)

                if ret_pickle_path:
                    osm_pbf_data = osm_pbf_data, path_to_pickle

            else:  # If the target file is not available, try downloading it:
                if (not os.path.exists(path_to_osm_pbf) or update) and download:
                    self.downloader.download_osm_data(
                        subregion_names=subregion_name, osm_file_format=osm_file_format,
                        download_dir=data_dir, update=update, confirmation_required=False,
                        verbose=verbose)

                if os.path.isfile(path_to_osm_pbf):
                    osm_pbf_data = self._read_osm_pbf(
                        pbf_pathname=path_to_osm_pbf, chunk_size_limit=chunk_size_limit,
                        readable=readable, expand=expand, parse_geometry=parse_geometry,
                        parse_properties=parse_properties, parse_other_tags=parse_other_tags,
                        pickle_it=pickle_it, path_to_pickle=path_to_pickle,
                        ret_pickle_path=ret_pickle_path, rm_pbf_file=rm_pbf_file, verbose=verbose,
                        **kwargs)

                else:
                    osm_pbf_data = None
                    if verbose:
                        print(f"The {osm_file_format} file for \"{subregion_name_}\" is not found.")

            return osm_pbf_data

    def get_shp_pathname(self, subregion_name, layer_name=None, feature_name=None, data_dir=None):
        """
        Get path(s) to shapefile(s) for a geographic (sub)region (by searching a local data directory).

        :param subregion_name: name of a geographic (sub)region (case-insensitive)
            that is available on Geofabrik free download server
        :type subregion_name: str
        :param layer_name: name of a .shp layer (e.g. ``'railways'``), defaults to ``None``
        :type layer_name: str or None
        :param feature_name: name of a feature (e.g. ``'rail'``);
            if ``None`` (default), all available features included
        :type feature_name: str or None
        :param data_dir: directory where the search is conducted; if ``None`` (default),
            the default directory
        :type data_dir: str or None
        :return: path(s) to shapefile(s)
        :rtype: list

        **Examples**::

            >>> from pydriosm.reader import GeofabrikReader
            >>> from pyhelpers.dirs import delete_dir
            >>> import os

            >>> gfr = GeofabrikReader()

            >>> subrgn_name = 'london'
            >>> file_format = ".shp"
            >>> dat_dir = "tests\\osm_data"

            >>> # Try to get the shapefiles' pathnames
            >>> london_shp_path = gfr.get_shp_pathname(subregion_name=subrgn_name, data_dir=dat_dir)
            >>> london_shp_path  # An empty list if no data is available
            []

            >>> # Download the shapefiles of London
            >>> path_to_london_shp_zip = gfr.downloader.download_osm_data(
            ...     subrgn_name, file_format, dat_dir, verbose=True, ret_download_path=True)
            To download .shp.zip data of the following geographic (sub)region(s):
                Greater London
            ? [No]|Yes: yes
            Downloading "greater-london-latest-free.shp.zip"
                to "tests\\osm_data\\greater-london\\" ... Done.

            >>> # Extract the downloaded .zip file
            >>> gfr.SHP.unzip_shp_zip(path_to_london_shp_zip[0], verbose=True)
            Extracting "tests\\osm_data\\greater-london\\greater-london-latest-free.shp.zip"
                to "tests\\osm_data\\greater-london\\greater-london-latest-free-shp\\" ... Done.

            >>> # Try again to get the shapefiles' pathnames
            >>> london_shp_path = gfr.get_shp_pathname(subrgn_name, data_dir=dat_dir)
            >>> len(london_shp_path) > 1
            True

            >>> # Get the file path of 'railways' shapefile
            >>> lyr_name = 'railways'
            >>> railways_shp_path = gfr.get_shp_pathname(subrgn_name, lyr_name, data_dir=dat_dir)
            >>> len(railways_shp_path)
            1
            >>> railways_shp_path = railways_shp_path[0]
            >>> os.path.relpath(railways_shp_path)
            'tests\\osm_data\\greater-london\\greater-london-latest-free-shp\\gis_osm_railways_fr...

            >>> # Get/save shapefile data of features labelled 'rail' only
            >>> feat_name = 'rail'
            >>> railways_shp = gfr.SHP.read_layer_shps(
            ...     railways_shp_path, feature_names=feat_name, save_feat_shp=True)
            >>> railways_shp.head()
                osm_id  code  ...                                        coordinates shape_type
            0    30804  6101  ...  [(0.0048644, 51.6279262), (0.0061979, 51.62926...          3
            3   101511  6101  ...  [(-0.2119027, 51.5241906), (-0.2108059, 51.523...          3
            5   361978  6101  ...  [(-0.0298545, 51.6619398), (-0.0302322, 51.659...          3
            6  2370155  6101  ...  [(-0.3379005, 51.5937776), (-0.3367807, 51.593...          3
            7  2526598  6101  ...  [(-0.1886021, 51.3602632), (-0.1884216, 51.360...          3
            [5 rows x 9 columns]

            >>> # Get the file path to the data of 'rail'
            >>> rail_shp_path = gfr.get_shp_pathname(subrgn_name, lyr_name, feat_name, dat_dir)
            >>> len(rail_shp_path)
            1
            >>> rail_shp_path = rail_shp_path[0]
            >>> os.path.relpath(rail_shp_path)
            'tests\\osm_data\\greater-london\\greater-london-latest-free-shp\\railways\\rail.shp'

            >>> # Retrieve the data of 'rail' feature
            >>> railways_rail_shp = gfr.SHP.read_layer_shps(rail_shp_path)
            >>> railways_rail_shp.head()
                osm_id  code  ...                                        coordinates shape_type
            0    30804  6101  ...  [(0.0048644, 51.6279262), (0.0061979, 51.62926...          3
            1   101511  6101  ...  [(-0.2119027, 51.5241906), (-0.2108059, 51.523...          3
            2   361978  6101  ...  [(-0.0298545, 51.6619398), (-0.0302322, 51.659...          3
            3  2370155  6101  ...  [(-0.3379005, 51.5937776), (-0.3367807, 51.593...          3
            4  2526598  6101  ...  [(-0.1886021, 51.3602632), (-0.1884216, 51.360...          3
            [5 rows x 9 columns]

            >>> # Delete the example data and the test data directory
            >>> delete_dir(dat_dir, verbose=True)
            To delete the directory "tests\\osm_data\\" (Not empty)
            ? [No]|Yes: yes
            Deleting "tests\\osm_data\\" ... Done.
        """

        osm_file_format, shp_file_ext = ".shp.zip", ".shp"

        path_to_shp_zip = self.get_file_path(
            subregion_name=subregion_name, osm_file_format=osm_file_format, data_dir=data_dir)
        shp_dir = os.path.splitext(path_to_shp_zip)[0].replace(".", "-")

        available_pathnames = glob.glob(os.path.join(shp_dir, f"*{shp_file_ext}"))
        if not available_pathnames:
            available_pathnames = glob.glob(os.path.join(shp_dir, "*", f"*{shp_file_ext}"))

        if layer_name is None:
            path_to_osm_shp_file = available_pathnames

        else:
            layer_name_ = find_similar_str(x=layer_name, lookup_list=self.SHP.LAYER_NAMES)

            pat_ = f'gis_osm_{layer_name_}(_a)?(_free)?(_1)?'
            if feature_name is None:
                pat = re.compile(f"{pat_}{shp_file_ext}")
                lookup = available_pathnames
            else:
                ft_name = feature_name if isinstance(feature_name, str) else "_".join(list(feature_name))
                pat = re.compile(f"{pat_}_{ft_name}{shp_file_ext}")
                lookup = glob.glob(os.path.join(shp_dir, layer_name_, f"*{shp_file_ext}"))

            path_to_osm_shp_file = [f for f in lookup if re.search(pat, f)]

        # if not path_to_osm_shp_file: print("The required file is not found.")
        # if len(path_to_osm_shp_file) == 1: path_to_osm_shp_file = path_to_osm_shp_file[0]

        return path_to_osm_shp_file

    @classmethod
    def make_shp_pkl_pathname(cls, shp_zip_filename, extract_dir, layer_names_, feature_names_):
        """
        Make a pathname of a pickle file for saving shapefile data.

        :param shp_zip_filename: filename of a .shp.zip file
        :type shp_zip_filename: str
        :param extract_dir: pathname of a directory to which the .shp.zip file is extracted
        :type extract_dir: str
        :param layer_names_: names of shapefile layers
        :type layer_names_: list
        :param feature_names_: names of shapefile features
        :type feature_names_: list
        :return: pathname of a pickle file for saving data of the specified shapefile
        :rtype: str

        See examples for the methods
        :meth:`GeofabrikReader.read_shp_zip()<pydriosm.reader.GeofabrikReader.read_shp_zip>` and
        :meth:`BBBikeReader.read_shp_zip()<pydriosm.reader.BBBikeReader.read_shp_zip>`.
        """

        if layer_names_:  # layer is not None
            temp = layer_names_ + (feature_names_ if feature_names_ else [])
            # Make a local path for saving a pickle file for .shp data
            if cls.NAME == 'Geofabrik':
                filename_ = shp_zip_filename.replace("-latest-free.shp.zip", "")
                sub_fname = "-".join(x[:3] for x in [filename_] + temp if x)
            else:
                filename_ = shp_zip_filename.replace(".osm.shp.zip", "").lower()
                sub_fname = "-".join(x for x in [filename_] + temp if x)
            path_to_shp_pickle = os.path.join(os.path.dirname(extract_dir), sub_fname + "-shp.pkl")

        else:  # len(layer_names_) >= 12
            if cls.NAME == 'Geofabrik':
                path_to_shp_pickle = extract_dir.replace("-latest-free-shp", "-shp.pkl")
            else:
                path_to_shp_pickle = extract_dir + ".pkl"

        return path_to_shp_pickle

    def _get_shp_layer_names(self, extract_dir_):
        if self.NAME == 'Geofabrik':
            lyr_names_ = [
                self.SHP.find_shp_layer_name(x) for x in os.listdir(extract_dir_) if x != 'README']
        else:
            lyr_names_ = [x.rsplit(".", 1)[0] for x in os.listdir(os.path.join(extract_dir_, "shape"))]

        return lyr_names_

    def validate_shp_layer_names(self, layer_names_, extract_dir, shp_zip_pathname, subregion_name,
                                 osm_file_format, data_dir, update, download, verbose):
        """
        Validate the input of layer name(s) for reading shapefiles.

        :param layer_names_: names of shapefile layers
        :type layer_names_: list
        :param extract_dir: pathname of a directory to which the .shp.zip file is extracted
        :type extract_dir: str
        :param shp_zip_pathname: pathname of a .shp.zip file
        :type shp_zip_pathname: str
        :param subregion_name: name of a geographic (sub)region (case-insensitive)
            that is available on Geofabrik free download server
        :type subregion_name: str
        :param osm_file_format: format (file extension) of OSM data
        :type osm_file_format: str
        :param data_dir: name or pathname of the data directory
        :type data_dir: str or os.PathLike[str]
        :param update: whether to check to update pickle backup (if available), defaults to ``False``
        :type update: bool
        :param download: whether to download/update the PBF data file of the given subregion,
            if it is not available at the specified path, defaults to ``True``
        :type download: bool
        :param verbose: whether to print relevant information in console as the function runs,
            defaults to ``False``
        :type verbose: bool or int
        :return: validated shapefile layer names
        :rtype: list

        See examples for the methods
        :meth:`GeofabrikReader.read_shp_zip()<pydriosm.reader.GeofabrikReader.read_shp_zip>` and
        :meth:`BBBikeReader.read_shp_zip()<pydriosm.reader.BBBikeReader.read_shp_zip>`.
        """

        if self.NAME == 'Geofabrik':
            extract_dir_ = path_to_extract_dir = extract_dir
        else:
            path_to_extract_dir = os.path.dirname(shp_zip_pathname)
            extract_dir_ = os.path.splitext(shp_zip_pathname)[0].replace(".osm.", "-")

        download_args = {
            'subregion_names': subregion_name,
            'osm_file_format': osm_file_format,
            'download_dir': data_dir,
            'update': update,
            'confirmation_required': False,
            'verbose': verbose,
            # 'ret_download_path': True,
        }

        layer_name_list = [find_similar_str(x, self.SHP.LAYER_NAMES) for x in layer_names_]

        if not os.path.exists(extract_dir_):
            if (not os.path.exists(shp_zip_pathname) or update) and download:
                self.downloader.download_osm_data(**download_args)  # Download the requested OSM file

            if os.path.isfile(shp_zip_pathname):  # and shp_zip_pathname in self.downloader.data_paths:
                self.SHP.unzip_shp_zip(
                    shp_zip_pathname=shp_zip_pathname, extract_to=path_to_extract_dir,
                    layer_names=layer_names_, verbose=verbose)

                if not layer_names_:
                    lyr_names_ = self._get_shp_layer_names(extract_dir_=extract_dir_)
                    layer_name_list = sorted(list(set(lyr_names_)))

        else:
            unavailable_layers = []

            layer_names_temp_ = self._get_shp_layer_names(extract_dir_=extract_dir_)
            layer_names_temp = sorted(list(set(layer_name_list + layer_names_temp_)))

            for layer_name in layer_names_temp:
                if self.NAME == 'Geofabrik':
                    shp_filename = self.get_shp_pathname(
                        subregion_name=subregion_name, layer_name=layer_name, data_dir=data_dir)
                    if not shp_filename:
                        unavailable_layers.append(layer_name)
                else:
                    shp_filename = os.path.join(extract_dir_, "shape", f"{layer_name}.shp")
                    if not os.path.isfile(shp_filename):
                        unavailable_layers.append(layer_name)

            if len(unavailable_layers) > 0:
                if not os.path.exists(shp_zip_pathname) and download:
                    self.downloader.download_osm_data(**download_args)

                if os.path.isfile(shp_zip_pathname):
                    self.SHP.unzip_shp_zip(
                        shp_zip_pathname=shp_zip_pathname, extract_to=path_to_extract_dir,
                        layer_names=unavailable_layers, verbose=verbose)

            if not layer_name_list:
                layer_name_list = layer_names_temp

        return layer_name_list

    def _read_shp_zip(self, shp_pathnames, feature_names_, layer_name_list, pickle_it, path_to_pickle,
                      ret_pickle_path, rm_extracts, extract_dir, rm_shp_zip, shp_zip_pathname,
                      verbose, **kwargs):
        if verbose:
            # print(f'Reading the shapefile(s) data', end=" ... ")
            files_dir = os.path.relpath(
                os.path.commonpath(list(itertools.chain.from_iterable(shp_pathnames))))
            msg_ = "the shapefile(s) at\n\t" if os.path.isdir(files_dir) else ""
            print(f'Reading {msg_}"{files_dir}\\"', end=" ... ")

        try:
            kwargs.update({'feature_names': feature_names_, 'ret_feat_shp_path': False})
            shp_dat_list = [self.SHP.read_layer_shps(shp_pathnames=x, **kwargs) for x in shp_pathnames]

            shp_data = collections.OrderedDict(zip(layer_name_list, shp_dat_list))

            if verbose:
                print("Done.")

            if pickle_it:
                save_pickle(shp_data, path_to_pickle, verbose=verbose)

                if ret_pickle_path:
                    shp_data = shp_data, path_to_pickle

            if os.path.exists(extract_dir) and rm_extracts:
                self.remove_extracts(extract_dir, verbose=verbose)

            if os.path.isfile(shp_zip_pathname) and rm_shp_zip:
                remove_osm_file(shp_zip_pathname, verbose=verbose)

        except Exception as e:
            print(f"Failed. {e}")
            shp_data = None

        return shp_data

    def read_shp_zip(self, subregion_name, layer_names=None, feature_names=None, data_dir=None,
                     update=False, download=True, pickle_it=False, ret_pickle_path=False,
                     rm_extracts=False, rm_shp_zip=False, verbose=False, **kwargs):
        """
        Read a .shp.zip data file of a geographic (sub)region.

        :param subregion_name: name of a geographic (sub)region (case-insensitive)
            that is available on Geofabrik free download server
        :type subregion_name: str
        :param layer_names: name of a .shp layer, e.g. 'railways', or names of multiple layers;
            if ``None`` (default), all available layers
        :type layer_names: str or list or None
        :param feature_names: name of a feature, e.g. 'rail', or names of multiple features;
            if ``None`` (default), all available features
        :type feature_names: str or list or None
        :param data_dir: directory where the .shp.zip data file is located/saved;
            if ``None``, the default directory
        :type data_dir: str or None
        :param update: whether to check to update pickle backup (if available), defaults to ``False``
        :type update: bool
        :param download: whether to ask for confirmation
            before starting to download a file, defaults to ``True``
        :type download: bool
        :param pickle_it: whether to save the .shp data as a pickle file, defaults to ``False``
        :type pickle_it: bool
        :param ret_pickle_path: (when ``pickle_it=True``)
            whether to return a path to the saved pickle file
        :type ret_pickle_path: bool
        :param rm_extracts: whether to delete extracted files from the .shp.zip file,
            defaults to ``False``
        :type rm_extracts: bool
        :param rm_shp_zip: whether to delete the downloaded .shp.zip file, defaults to ``False``
        :type rm_shp_zip: bool
        :param verbose: whether to print relevant information in console as the function runs,
            defaults to ``False``
        :type verbose: bool or int
        :param kwargs: [optional] parameters of the method
            :meth:`SHPReadParse.read_shp()<pydriosm.reader.SHPReadParse.read_shp>`
        :return: dictionary of the shapefile data,
            with keys and values being layer names and tabular data
            (in the format of `geopandas.GeoDataFrame`_), respectively
        :rtype: dict or collections.OrderedDict or None

        .. _`geopandas.GeoDataFrame`: https://geopandas.org/reference.html#geodataframe

        See examples for the methods
        :meth:`GeofabrikReader.read_shp_zip()<pydriosm.reader.GeofabrikReader.read_shp_zip>` and
        :meth:`BBBikeReader.read_shp_zip()<pydriosm.reader.BBBikeReader.read_shp_zip>`.
        """

        osm_file_format = ".shp.zip"

        subregion_name_, shp_zip_filename, _, shp_zip_pathname = \
            self.downloader.get_valid_download_info(
                subregion_name=subregion_name, osm_file_format=osm_file_format,
                download_dir=data_dir)

        layer_names_, feature_names_ = map(self.validate_input_dtype, [layer_names, feature_names])

        if all(x is not None for x in {shp_zip_filename, shp_zip_pathname}):
            # The shapefile data of the subregion should be downloadable
            extract_dir_temp = os.path.splitext(shp_zip_pathname)[0]
            if self.NAME == 'Geofabrik':
                extract_dir = extract_dir_temp.replace(".", "-")
                shp_pathname_ = os.path.join(extract_dir, "gis_osm_{}_*.shp")
            else:
                extract_dir = extract_dir_temp.replace(".osm.", "-")
                shp_pathname_ = os.path.join(extract_dir, "shape", "{}.shp")

            path_to_pickle = self.make_shp_pkl_pathname(
                shp_zip_filename=shp_zip_filename, extract_dir=extract_dir,
                layer_names_=layer_names_, feature_names_=feature_names_)

            if os.path.isfile(path_to_pickle) and not update:
                shp_data = load_pickle(path_to_pickle, verbose=verbose)

                if ret_pickle_path:
                    shp_data = shp_data, path_to_pickle

            else:
                layer_name_list = self.validate_shp_layer_names(
                    layer_names_=layer_names_, extract_dir=extract_dir,
                    shp_zip_pathname=shp_zip_pathname, subregion_name=subregion_name_,
                    osm_file_format=osm_file_format, data_dir=data_dir, update=update,
                    download=download, verbose=verbose)

                if len(layer_name_list) > 0:
                    shp_pathnames = [
                        glob.glob(shp_pathname_.format(layer_name))
                        for layer_name in layer_name_list]

                    shp_data = self._read_shp_zip(
                        shp_pathnames=shp_pathnames, feature_names_=feature_names_,
                        layer_name_list=layer_name_list, pickle_it=pickle_it,
                        path_to_pickle=path_to_pickle, ret_pickle_path=ret_pickle_path,
                        rm_extracts=rm_extracts, extract_dir=extract_dir, rm_shp_zip=rm_shp_zip,
                        shp_zip_pathname=shp_zip_pathname, verbose=verbose, **kwargs)

                else:
                    shp_data = None
                    if verbose:
                        print(f"The {osm_file_format} file for \"{subregion_name_}\" is not found.")

            return shp_data

    def read_osm_var(self, meth, subregion_name, osm_file_format, data_dir=None, download=False,
                     verbose=False, **kwargs):
        """
        Read data file of various formats (other than PBF and shapefile) for a geographic (sub)region.

        :param meth: name of a class method for getting (auxiliary) prepacked data
        :type meth: typing.Callable
        :param subregion_name: name of a geographic (sub)region (case-insensitive)
            that is available on a free download server
        :type subregion_name: str
        :param osm_file_format: format (file extension) of OSM data
        :type osm_file_format: str
        :param data_dir: directory where the data file is located/saved, defaults to ``None``;
            when ``data_dir=None``, it refers to the directory specified by the corresponding downloader
        :type data_dir: str or None
        :param download: whether to download/update the PBF data file of the given subregion,
            if it is not available at the specified path, defaults to ``True``
        :type download: bool
        :param verbose: whether to print relevant information in console as the function runs,
            defaults to ``False``
        :type verbose: bool or int
        :param kwargs: [optional] parameters of the method specified by ``meth``
        :return: data of the specified file format
        :rtype: pandas.DataFrame or None

        See examples for the methods
        :meth:`BBBikeReader.read_csv_xz()<pydriosm.reader.BBBikeReader.read_csv_xz>` and
        :meth:`BBBikeReader.read_geojson_xz()<pydriosm.reader.BBBikeReader.read_geojson_xz>`.
        """

        subregion_name_ = self.downloader.validate_subregion_name(subregion_name)

        path_to_osm_var = self.get_file_path(subregion_name_, osm_file_format, data_dir)

        if not os.path.isfile(path_to_osm_var) and download:
            self.downloader.download_osm_data(
                subregion_names=subregion_name_, osm_file_format=osm_file_format, download_dir=data_dir,
                confirmation_required=False, verbose=verbose)
            downloaded = True
        else:
            downloaded = False

        if os.path.isfile(path_to_osm_var):
            if verbose:
                prt_msg = "the data" if downloaded else f'"{os.path.relpath(path_to_osm_var)}"'
                print(f"Parsing {prt_msg}", end=" ... ")

            try:
                # getattr(self.VAR, 'read_...')
                osm_var_data = meth(path_to_osm_var, **kwargs)

                if verbose:
                    print("Done.")

            except Exception as e:
                print(f"Failed. {e}")
                osm_var_data = None

            return osm_var_data

        else:
            print(f'The requisite data file "{os.path.relpath(path_to_osm_var)}" does not exist.')


class GeofabrikReader(_Reader):
    """
    Read `Geofabrik <https://download.geofabrik.de/>`_ OpenStreetMap data extracts.
    """

    #: str: Default download directory.
    DEFAULT_DATA_DIR = "osm_data\\geofabrik"
    #: set: Valid file formats.
    FILE_FORMATS = {'.osm.pbf', '.shp.zip', '.osm.bz2'}

    def __init__(self, max_tmpfile_size=None, data_dir=None):
        """
        :param max_tmpfile_size: defaults to ``None``,
            see also the function `pyhelpers.settings.gdal_configurations()`_
        :type max_tmpfile_size: int or None
        :param data_dir: (a path or a name of) a directory where a data file is, defaults to ``None``;
            when ``data_dir=None``, it refers to a folder named ``osm_geofabrik``
            under the current working directory
        :type data_dir: str or None

        :ivar GeofabrikDownloader downloader: instance of the class
            :py:class:`~pydriosm.downloader.GeofabrikDownloader`
        :ivar str name: name of the data resource
        :ivar str url: url of the homepage to the Geofabrik free download server

        .. _`pyhelpers.settings.gdal_configurations()`:
            https://pyhelpers.readthedocs.io/en/latest/_generated/
            pyhelpers.settings.gdal_configurations.html

        **Examples**::

            >>> from pydriosm.reader import GeofabrikReader

            >>> gfr = GeofabrikReader()

            >>> gfr.NAME
            'Geofabrik'
        """

        # noinspection PyTypeChecker
        super().__init__(
            max_tmpfile_size=max_tmpfile_size, downloader=GeofabrikDownloader, data_dir=data_dir)

    def get_file_path(self, subregion_name, osm_file_format, data_dir=None):
        """
        Get the local path to an OSM data file of a geographic (sub)region.

        :param subregion_name: name of a geographic (sub)region (case-insensitive)
            that is available on Geofabrik free download server
        :type subregion_name: str
        :param osm_file_format: file format of the OSM data available on the free download server
        :type osm_file_format: str
        :param data_dir: directory where the data file of the ``subregion_name`` is located/saved;
            if ``None`` (default), the default local directory
        :type data_dir: str or None
        :return: path to PBF (.osm.pbf) file
        :rtype: str or None

        **Examples**::

            >>> from pydriosm.reader import GeofabrikReader
            >>> from pyhelpers.dirs import delete_dir
            >>> import os

            >>> gfr = GeofabrikReader()

            >>> subrgn_name = 'rutland'
            >>> file_format = ".pbf"
            >>> dat_dir = "tests\\osm_data"

            >>> path_to_rutland_pbf = gfr.get_file_path(subrgn_name, file_format, data_dir=dat_dir)

            >>> # When "rutland-latest.osm.pbf" is unavailable at the package data directory
            >>> os.path.isfile(path_to_rutland_pbf)
            False

            >>> # Download the PBF data file of Rutland to "tests\\osm_data\\"
            >>> gfr.downloader.download_osm_data(subrgn_name, file_format, dat_dir, verbose=True)
            To download .osm.pbf data of the following geographic (sub)region(s):
                Rutland
            ? [No]|Yes: yes
            Downloading "rutland-latest.osm.pbf"
                to "tests\\osm_data\\rutland\\" ... Done.

            >>> # Check again
            >>> path_to_rutland_pbf = gfr.get_file_path(subrgn_name, file_format, data_dir=dat_dir)
            >>> os.path.relpath(path_to_rutland_pbf)
            'tests\\osm_data\\rutland\\rutland-latest.osm.pbf'
            >>> os.path.isfile(path_to_rutland_pbf)
            True

            >>> # Delete the test data directory
            >>> delete_dir(dat_dir, verbose=True)
            To delete the directory "tests\\osm_data\\" (Not empty)
            ? [No]|Yes: yes
            Deleting "tests\\osm_data\\" ... Done.
        """

        path_to_file = super().get_file_path(
            subregion_name=subregion_name, osm_file_format=osm_file_format, data_dir=data_dir)

        return path_to_file

    def get_pbf_layer_names(self, subregion_name, data_dir=None):
        """
        Get indices and names of all layers in the PBF data file of a given (sub)region.

        :param subregion_name: name of a geographic (sub)region (case-insensitive)
            that is available on Geofabrik free download server
        :type subregion_name: str
        :param data_dir:
        :type data_dir:
        :return: indices and names of each layer of the PBF data file
        :rtype: dict

        **Examples**::

            >>> from pydriosm.reader import GeofabrikReader
            >>> from pyhelpers.dirs import delete_dir
            >>> import os

            >>> gfr = GeofabrikReader()

            >>> # Download the .shp.zip file of Rutland as an example
            >>> subrgn_name = 'london'
            >>> file_format = ".pbf"
            >>> dat_dir = "tests\\osm_data"

            >>> gfr.downloader.download_osm_data(subrgn_name, file_format, dat_dir, verbose=True)
            To download .osm.pbf data of the following geographic (sub)region(s):
                Greater London
            ? [No]|Yes: yes
            Downloading "greater-london-latest.osm.pbf"
                to "tests\\osm_data\\greater-london\\" ... Done.

            >>> london_pbf_path = gfr.data_paths[0]
            >>> os.path.relpath(london_pbf_path)
            'tests\\osm_data\\greater-london\\greater-london-latest.osm.pbf'

            >>> lyr_idx_names = gfr.get_pbf_layer_names(london_pbf_path)
            >>> lyr_idx_names
            {0: 'points',
             1: 'lines',
             2: 'multilinestrings',
             3: 'multipolygons',
             4: 'other_relations'}

            >>> # Delete the example data and the test data directory
            >>> delete_dir(dat_dir, verbose=True)
            To delete the directory "tests\\osm_data\\" (Not empty)
            ? [No]|Yes: yes
            Deleting "tests\\osm_data\\" ... Done.
        """

        data_dir_ = self.data_dir if data_dir is None else data_dir

        path_to_osm_pbf = self.get_file_path(
            subregion_name=subregion_name, osm_file_format=".osm.pbf", data_dir=data_dir_)

        layer_idx_names = PBFReadParse.get_pbf_layer_names(path_to_osm_pbf)

        return layer_idx_names

    def read_osm_pbf(self, subregion_name, data_dir=None, readable=False, expand=False,
                     parse_geometry=False, parse_properties=False, parse_other_tags=False,
                     update=False, download=True, pickle_it=False, ret_pickle_path=False,
                     rm_pbf_file=False, chunk_size_limit=50, verbose=False, **kwargs):
        """
        Read a PBF (.osm.pbf) data file of a geographic (sub)region.

        :param subregion_name: name of a geographic (sub)region (case-insensitive)
            that is available on Geofabrik free download server
        :type subregion_name: str
        :param data_dir: directory where the .osm.pbf data file is located/saved;
            if ``None``, the default local directory
        :type data_dir: str or None
        :param readable: whether to parse each feature in the raw data, defaults to ``False``
        :type readable: bool
        :param expand: whether to expand dict-like data into separate columns, defaults to ``False``
        :type expand: bool
        :param parse_geometry: whether to represent the ``'geometry'`` field
            in a `shapely.geometry`_ format, defaults to ``False``
        :type parse_geometry: bool
        :param parse_properties: whether to represent the ``'properties'`` field
            in a tabular format, defaults to ``False``
        :type parse_properties: bool
        :param parse_other_tags: whether to represent a ``'other_tags'`` (of ``'properties'``)
            in a `dict`_ format, defaults to ``False``
        :type parse_other_tags: bool
        :param download: whether to download/update the PBF data file of the given subregion,
            if it is not available at the specified path, defaults to ``True``
        :type download: bool
        :param update: whether to check to update pickle backup (if available), defaults to ``False``
        :type update: bool
        :param pickle_it: whether to save the .pbf data as a pickle file, defaults to ``False``
        :type pickle_it: bool
        :param ret_pickle_path: (when ``pickle_it=True``)
            whether to return a path to the saved pickle file
        :type ret_pickle_path: bool
        :param rm_pbf_file: whether to delete the downloaded .osm.pbf file, defaults to ``False``
        :type rm_pbf_file: bool
        :param chunk_size_limit: threshold (in MB) that triggers the use of chunk parser,
            defaults to ``50``;
            if the size of the .osm.pbf file (in MB) is greater than ``chunk_size_limit``,
            it will be parsed in a chunk-wise way
        :type chunk_size_limit: int or None
        :param verbose: whether to print relevant information in console as the function runs,
            defaults to ``False``
        :type verbose: bool or int
        :param kwargs: [optional] parameters of the method
            :meth:`_Reader.read_osm_pbf()<pydriosm.reader._Reader.read_osm_pbf>`
        :return: dictionary of the .osm.pbf data;
            when ``pickle_it=True``, return a tuple of the dictionary and a path to the pickle file
        :rtype: dict or tuple or None

        .. _`shapely.geometry`: https://shapely.readthedocs.io/en/latest/manual.html#geometric-objects
        .. _`dict`: https://docs.python.org/3/library/stdtypes.html#dict

        .. _pydriosm-reader-GeofabrikReader-read_osm_pbf:

        **Examples**::

            >>> from pydriosm.reader import GeofabrikReader
            >>> from pyhelpers.dirs import delete_dir

            >>> gfr = GeofabrikReader()

            >>> subrgn_name = 'rutland'
            >>> dat_dir = "tests\\osm_data"

            >>> # If the PBF data of Rutland is not available at the specified data directory,
            >>> # the function can download the latest data by setting `download=True` (default)
            >>> pbf_raw = gfr.read_osm_pbf(subrgn_name, data_dir=dat_dir, verbose=True)
            Downloading "rutland-latest.osm.pbf"
                to "tests\\osm_data\\rutland\\" ... Done.
            Reading "tests\\osm_data\\rutland\\rutland-latest.osm.pbf" ... Done.
            >>> type(pbf_raw)
            dict
            >>> list(pbf_raw.keys())
            ['points', 'lines', 'multilinestrings', 'multipolygons', 'other_relations']

            >>> pbf_raw_points = pbf_raw['points']
            >>> type(pbf_raw_points)
            list
            >>> type(pbf_raw_points[0])
            osgeo.ogr.Feature

            >>> # Set `readable=True`
            >>> pbf_parsed = gfr.read_osm_pbf(subrgn_name, dat_dir, readable=True, verbose=True)
            Parsing "tests\\osm_data\\rutland\\rutland-latest.osm.pbf" ... Done.
            >>> pbf_parsed_points = pbf_parsed['points']
            >>> pbf_parsed_points.head()
            0    {'type': 'Feature', 'geometry': {'type': 'Poin...
            1    {'type': 'Feature', 'geometry': {'type': 'Poin...
            2    {'type': 'Feature', 'geometry': {'type': 'Poin...
            3    {'type': 'Feature', 'geometry': {'type': 'Poin...
            4    {'type': 'Feature', 'geometry': {'type': 'Poin...
            Name: points, dtype: object

            >>> # Set `expand=True`, which would force `readable=True`
            >>> pbf_parsed_ = gfr.read_osm_pbf(subrgn_name, dat_dir, expand=True, verbose=True)
            Parsing "tests\\osm_data\\rutland\\rutland-latest.osm.pbf" ... Done.
            >>> pbf_parsed_points_ = pbf_parsed_['points']
            >>> pbf_parsed_points_.head()
                     id  ...                                         properties
            0    488432  ...  {'osm_id': '488432', 'name': None, 'barrier': ...
            1    488658  ...  {'osm_id': '488658', 'name': 'Tickencote Inter...
            2  13883868  ...  {'osm_id': '13883868', 'name': None, 'barrier'...
            3  14049101  ...  {'osm_id': '14049101', 'name': None, 'barrier'...
            4  14558402  ...  {'osm_id': '14558402', 'name': None, 'barrier'...
            [5 rows x 3 columns]

            >>> # Set `readable` and `parse_geometry` to be `True`
            >>> pbf_parsed_1 = gfr.read_osm_pbf(subrgn_name, dat_dir, readable=True,
            ...                                 parse_geometry=True)
            >>> pbf_parsed_1_point = pbf_parsed_1['points'][0]
            >>> pbf_parsed_1_point['geometry']
            'POINT (-0.5134241 52.6555853)'
            >>> pbf_parsed_1_point['properties']['other_tags']
            '"odbl"=>"clean"'

            >>> # Set `readable` and `parse_other_tags` to be `True`
            >>> pbf_parsed_2 = gfr.read_osm_pbf(subrgn_name, dat_dir, readable=True,
            ...                                 parse_other_tags=True)
            >>> pbf_parsed_2_point = pbf_parsed_2['points'][0]
            >>> pbf_parsed_2_point['geometry']
            {'type': 'Point', 'coordinates': [-0.5134241, 52.6555853]}
            >>> pbf_parsed_2_point['properties']['other_tags']
            {'odbl': 'clean'}

            >>> # Set `readable`, `parse_geometry` and `parse_other_tags` to be `True`
            >>> pbf_parsed_3 = gfr.read_osm_pbf(subrgn_name, dat_dir, readable=True,
            ...                                 parse_geometry=True, parse_other_tags=True)
            >>> pbf_parsed_3_point = pbf_parsed_3['points'][0]
            >>> pbf_parsed_3_point['geometry']
            'POINT (-0.5134241 52.6555853)'
            >>> pbf_parsed_3_point['properties']['other_tags']
            {'odbl': 'clean'}

            >>> # Delete the example data and the test data directory
            >>> delete_dir(dat_dir, verbose=True)
            To delete the directory "tests\\osm_data\\" (Not empty)
            ? [No]|Yes: yes
            Deleting "tests\\osm_data\\" ... Done.
        """

        osm_pbf_data = super().read_osm_pbf(
            subregion_name=subregion_name, data_dir=data_dir, readable=readable, expand=expand,
            parse_geometry=parse_geometry, parse_properties=parse_properties,
            parse_other_tags=parse_other_tags,
            update=update, download=download, pickle_it=pickle_it, ret_pickle_path=ret_pickle_path,
            rm_pbf_file=rm_pbf_file, chunk_size_limit=chunk_size_limit, verbose=verbose, **kwargs)

        return osm_pbf_data

    def get_shp_pathname(self, subregion_name, layer_name=None, feature_name=None, data_dir=None):
        """
        Get path(s) to .shp file(s) for a geographic (sub)region
        (by searching a local data directory).

        :param subregion_name: name of a geographic (sub)region (case-insensitive)
            that is available on Geofabrik free download server
        :type subregion_name: str
        :param layer_name: name of a .shp layer (e.g. ``'railways'``), defaults to ``None``
        :type layer_name: str or None
        :param feature_name: name of a feature (e.g. ``'rail'``);
            if ``None`` (default), all available features included
        :type feature_name: str or None
        :param data_dir: directory where the search is conducted; if ``None`` (default),
            the default directory
        :type data_dir: str or None
        :return: path(s) to .shp file(s)
        :rtype: list

        **Examples**::

            >>> from pydriosm.reader import GeofabrikReader
            >>> from pyhelpers.dirs import delete_dir
            >>> import os

            >>> gfr = GeofabrikReader()

            >>> subrgn_name = 'london'
            >>> file_format = ".shp"
            >>> dat_dir = "tests\\osm_data"

            >>> # Try to get the shapefiles' pathnames
            >>> london_shp_path = gfr.get_shp_pathname(subrgn_name, data_dir=dat_dir)
            >>> london_shp_path  # An empty list if no data is available
            []

            >>> # Download the shapefiles of London
            >>> path_to_london_shp_zip = gfr.downloader.download_osm_data(
            ...     subrgn_name, file_format, dat_dir, verbose=True, ret_download_path=True)
            To download .shp.zip data of the following geographic (sub)region(s):
                Greater London
            ? [No]|Yes: yes
            Downloading "greater-london-latest-free.shp.zip"
                to "tests\\osm_data\\greater-london\\" ... Done.

            >>> type(path_to_london_shp_zip)
            list
            >>> len(path_to_london_shp_zip)
            1

            >>> # Extract the downloaded .zip file
            >>> gfr.SHP.unzip_shp_zip(path_to_london_shp_zip[0], verbose=True)
            Extracting "tests\\osm_data\\greater-london\\greater-london-latest-free.shp.zip"
                to "tests\\osm_data\\greater-london\\greater-london-latest-free-shp\\" ... Done.

            >>> # Try again to get the shapefiles' pathnames
            >>> london_shp_path = gfr.get_shp_pathname(subrgn_name, data_dir=dat_dir)
            >>> len(london_shp_path) > 1
            True

            >>> # Get the file path of 'railways' shapefile
            >>> lyr_name = 'railways'
            >>> railways_shp_path = gfr.get_shp_pathname(subrgn_name, lyr_name, data_dir=dat_dir)
            >>> len(railways_shp_path)
            1
            >>> railways_shp_path = railways_shp_path[0]
            >>> os.path.relpath(railways_shp_path)
            'tests\\osm_data\\greater-london\\greater-london-latest-free-shp\\gis_osm_railways_fr...

            >>> # Get/save shapefile data of features labelled 'rail' only
            >>> feat_name = 'rail'
            >>> railways_shp = gfr.SHP.read_layer_shps(
            ...     railways_shp_path, feature_names=feat_name, save_feat_shp=True)
            >>> railways_shp.head()
                osm_id  code  ...                                        coordinates shape_type
            0    30804  6101  ...  [(0.0048644, 51.6279262), (0.0061979, 51.62926...          3
            3   101511  6101  ...  [(-0.2119027, 51.5241906), (-0.2108059, 51.523...          3
            5   361978  6101  ...  [(-0.0298545, 51.6619398), (-0.0302322, 51.659...          3
            6  2370155  6101  ...  [(-0.3379005, 51.5937776), (-0.3367807, 51.593...          3
            7  2526598  6101  ...  [(-0.1886021, 51.3602632), (-0.1884216, 51.360...          3
            [5 rows x 9 columns]

            >>> # Get the file path to the data of 'rail'
            >>> rail_shp_path = gfr.get_shp_pathname(subrgn_name, lyr_name, feat_name, dat_dir)
            >>> len(rail_shp_path)
            1
            >>> rail_shp_path = rail_shp_path[0]
            >>> os.path.relpath(rail_shp_path)
            'tests\\osm_data\\greater-london\\greater-london-latest-free-shp\\railways\\rail.shp'

            >>> # Retrieve the data of 'rail' feature
            >>> railways_rail_shp = gfr.SHP.read_layer_shps(rail_shp_path)
            >>> railways_rail_shp.head()
                osm_id  code  ...                                        coordinates shape_type
            0    30804  6101  ...  [(0.0048644, 51.6279262), (0.0061979, 51.62926...          3
            1   101511  6101  ...  [(-0.2119027, 51.5241906), (-0.2108059, 51.523...          3
            2   361978  6101  ...  [(-0.0298545, 51.6619398), (-0.0302322, 51.659...          3
            3  2370155  6101  ...  [(-0.3379005, 51.5937776), (-0.3367807, 51.593...          3
            4  2526598  6101  ...  [(-0.1886021, 51.3602632), (-0.1884216, 51.360...          3
            [5 rows x 9 columns]

            >>> # Delete the example data and the test data directory
            >>> delete_dir(dat_dir, verbose=True)
            To delete the directory "tests\\osm_data\\" (Not empty)
            ? [No]|Yes: yes
            Deleting "tests\\osm_data\\" ... Done.
        """

        path_to_osm_shp_file = super().get_shp_pathname(
            subregion_name=subregion_name, layer_name=layer_name, feature_name=feature_name,
            data_dir=data_dir)

        return path_to_osm_shp_file

    def merge_subregion_layer_shp(self, subregion_names, layer_name, data_dir=None, engine='pyshp',
                                  update=False, download=True, rm_zip_extracts=True,
                                  merged_shp_dir=None, rm_shp_temp=True, verbose=False,
                                  ret_merged_shp_path=False):
        """
        Merge shapefiles for a specific layer of two or multiple geographic regions.

        :param subregion_names: names of geographic region (case-insensitive)
            that is available on Geofabrik free download server
        :type subregion_names: list
        :param layer_name: name of a layer (e.g. 'railways')
        :type layer_name: str
        :param engine: the method used to merge/save shapefiles;
            options include: ``'pyshp'`` (default) and ``'geopandas'`` (or ``'gpd'``)
            if ``engine='geopandas'``, this function relies on `geopandas.GeoDataFrame.to_file()`_;
            otherwise, it by default uses `shapefile.Writer()`_
        :type engine: str
        :param update: whether to update the source .shp.zip files, defaults to ``False``
        :type update: bool
        :param download: whether to ask for confirmation
            before starting to download a file, defaults to ``True``
        :type download: bool
        :param data_dir: directory where the .shp.zip data files are located/saved;
            if ``None`` (default), the default directory
        :type data_dir: str or None
        :param rm_zip_extracts: whether to delete the extracted files, defaults to ``False``
        :type rm_zip_extracts: bool
        :param rm_shp_temp: whether to delete temporary layer files, defaults to ``False``
        :type rm_shp_temp: bool
        :param merged_shp_dir: if ``None`` (default), use the layer name
            as the name of the folder where the merged .shp files will be saved
        :type merged_shp_dir: str or None
        :param verbose: whether to print relevant information in console, defaults to ``False``
        :type verbose: bool or int
        :param ret_merged_shp_path: whether to return the path to the merged .shp file,
            defaults to ``False``
        :type ret_merged_shp_path: bool
        :return: the path to the merged file when ``ret_merged_shp_path=True``
        :rtype: list or str

        .. _`geopandas.GeoDataFrame.to_file()`:
            https://geopandas.org/reference.html#geopandas.GeoDataFrame.to_file
        .. _`shapefile.Writer()`:
            https://github.com/GeospatialPython/pyshp#writing-shapefiles

        .. _pydriosm-GeofabrikReader-merge_subregion_layer_shp:

        **Examples**::

            >>> from pydriosm.reader import GeofabrikReader
            >>> from pyhelpers.dirs import cd, delete_dir
            >>> import os

            >>> gfr = GeofabrikReader()

        **Example 1**::

            >>> # To merge 'railways' of Greater Manchester and West Yorkshire
            >>> subrgn_name = ['Manchester', 'West Yorkshire']
            >>> lyr_name = 'railways'
            >>> dat_dir = "tests\\osm_data"

            >>> path_to_merged_shp_file = gfr.merge_subregion_layer_shp(
            ...     subrgn_name, lyr_name, dat_dir, verbose=True, ret_merged_shp_path=True)
            To download .shp.zip data of the following geographic (sub)region(s):
                Greater Manchester
                West Yorkshire
            ? [No]|Yes: yes
            Downloading "greater-manchester-latest-free.shp.zip"
                to "tests\\osm_data\\greater-manchester\\" ... Done.
            Downloading "west-yorkshire-latest-free.shp.zip"
                to "tests\\osm_data\\west-yorkshire\\" ... Done.
            Merging the following shapefiles:
                "greater-manchester_gis_osm_railways_free_1.shp"
                "west-yorkshire_gis_osm_railways_free_1.shp"
                    In progress ... Done.
                    Find the merged shapefile at "tests\\osm_data\\gre_man-wes_yor-railways\\".

            >>> os.path.relpath(path_to_merged_shp_file)
            'tests\\osm_data\\gre_man-wes_yor-railways\\linestring.shp'

            >>> # Read the merged data
            >>> manchester_yorkshire_railways_shp = gfr.SHP.read_shp(path_to_merged_shp_file)
            >>> manchester_yorkshire_railways_shp.head()
                osm_id  code  ...                                        coordinates shape_type
            0   928999  6101  ...  [(-2.2844621, 53.4802635), (-2.2949851, 53.481...          3
            1   929904  6101  ...  [(-2.2917977, 53.4619559), (-2.2924877, 53.461...          3
            2   929905  6102  ...  [(-2.2794048, 53.4605819), (-2.2799722, 53.460...          3
            3  3663332  6102  ...  [(-2.2382139, 53.4817985), (-2.2381708, 53.481...          3
            4  3996086  6101  ...  [(-2.6003053, 53.4604346), (-2.6005261, 53.460...          3
            [5 rows x 9 columns]

            >>> # Delete the merged files
            >>> delete_dir(os.path.dirname(path_to_merged_shp_file), verbose=True)
            To delete the directory "tests\\osm_data\\gre_man-wes_yor-railways\\" (Not empty)
            ? [No]|Yes: yes
            Deleting "tests\\osm_data\\gre_man-wes_yor-railways\\" ... Done.

            >>> # Delete the downloaded .shp.zip data files
            >>> delete_dir(list(map(os.path.dirname, gfr.downloader.data_paths)), verbose=True)
            To delete the following directories:
                "tests\\osm_data\\greater-manchester\\" (Not empty)
                "tests\\osm_data\\west-yorkshire\\" (Not empty)
            ? [No]|Yes: yes
            Deleting "tests\\osm_data\\greater-manchester\\" ... Done.
            Deleting "tests\\osm_data\\west-yorkshire\\" ... Done.

        **Example 2**::

            >>> # To merge 'transport' of Greater London, Kent and Surrey

            >>> subrgn_name = ['London', 'Kent', 'Surrey']
            >>> lyr_name = 'transport'

            >>> path_to_merged_shp_file = gfr.merge_subregion_layer_shp(
            ...     subrgn_name, lyr_name, dat_dir, verbose=True, ret_merged_shp_path=True)
            To download .shp.zip data of the following geographic (sub)region(s):
                Greater London
                Kent
                Surrey
            ? [No]|Yes: yes
            Downloading "greater-london-latest-free.shp.zip"
                to "tests\\osm_data\\greater-london\\" ... Done.
            Downloading "kent-latest-free.shp.zip"
                to "tests\\osm_data\\kent\\" ... Done.
            Downloading "surrey-latest-free.shp.zip"
                to "tests\\osm_data\\surrey\\" ... Done.
            Merging the following shapefiles:
                "greater-london_gis_osm_transport_a_free_1.shp"
                "greater-london_gis_osm_transport_free_1.shp"
                "kent_gis_osm_transport_a_free_1.shp"
                "kent_gis_osm_transport_free_1.shp"
                "surrey_gis_osm_transport_a_free_1.shp"
                "surrey_gis_osm_transport_free_1.shp"
                    In progress ... Done.
                    Find the merged shapefile at "tests\\osm_data\\gre_lon-ken-sur-transport\\".

            >>> type(path_to_merged_shp_file)
            list
            >>> len(path_to_merged_shp_file)
            2
            >>> os.path.relpath(path_to_merged_shp_file[0])
            'tests\\osm_data\\gre-lon_ken_sur_transport\\point.shp'
            >>> os.path.relpath(path_to_merged_shp_file[1])
            'tests\\osm_data\\gre-lon_ken_sur_transport\\polygon.shp'

            >>> # Read the merged shapefile
            >>> merged_transport_shp_1 = gfr.SHP.read_shp(path_to_merged_shp_file[1])
            >>> merged_transport_shp_1.head()
                 osm_id  ...  shape_type
            0   5077928  ...           5
            1   8610280  ...           5
            2  15705264  ...           5
            3  23077379  ...           5
            4  24016945  ...           5
            [5 rows x 6 columns]

            >>> # Delete the merged files
            >>> delete_dir(os.path.commonpath(path_to_merged_shp_file), verbose=True)
            To delete the directory "tests\\osm_data\\gre_lon-ken-sur-transport\\" (Not empty)
            ? [No]|Yes: yes
            Deleting "tests\\osm_data\\gre_lon-ken-sur-transport\\" ... Done.

            >>> # Delete the example data and the test data directory
            >>> delete_dir(dat_dir, verbose=True)
            To delete the directory "tests\\osm_data\\" (Not empty)
            ? [No]|Yes: yes
            Deleting "tests\\osm_data\\" ... Done.
        """

        # Make sure all the required shape files are ready
        layer_name_ = find_similar_str(x=layer_name, lookup_list=self.SHP.LAYER_NAMES)
        subregion_names_ = [self.downloader.validate_subregion_name(x) for x in subregion_names]

        osm_file_format = ".shp.zip"

        # Download the files if not available
        paths_to_shp_zip_files = self.downloader.download_osm_data(
            subregion_names_, osm_file_format=osm_file_format, download_dir=data_dir,
            update=update, confirmation_required=False if download else True,
            deep_retry=True, interval=1, verbose=verbose, ret_download_path=True)

        if all(os.path.isfile(shp_zip_path_file) for shp_zip_path_file in paths_to_shp_zip_files):
            path_to_merged_shp = self.SHP.merge_layer_shps(
                shp_zip_pathnames=paths_to_shp_zip_files, layer_name=layer_name_, engine=engine,
                rm_zip_extracts=rm_zip_extracts, output_dir=merged_shp_dir, rm_shp_temp=rm_shp_temp,
                verbose=verbose, ret_shp_pathname=ret_merged_shp_path)

            if ret_merged_shp_path:
                return path_to_merged_shp

    def read_shp_zip(self, subregion_name, layer_names=None, feature_names=None, data_dir=None,
                     update=False, download=True, pickle_it=False, ret_pickle_path=False,
                     rm_extracts=False, rm_shp_zip=False, verbose=False, **kwargs):
        """
        Read a .shp.zip data file of a geographic (sub)region.

        :param subregion_name: name of a geographic (sub)region (case-insensitive)
            that is available on Geofabrik free download server
        :type subregion_name: str
        :param layer_names: name of a .shp layer, e.g. 'railways', or names of multiple layers;
            if ``None`` (default), all available layers
        :type layer_names: str or list or None
        :param feature_names: name of a feature, e.g. 'rail', or names of multiple features;
            if ``None`` (default), all available features
        :type feature_names: str or list or None
        :param data_dir: directory where the .shp.zip data file is located/saved;
            if ``None``, the default directory
        :type data_dir: str or None
        :param update: whether to check to update pickle backup (if available), defaults to ``False``
        :type update: bool
        :param download: whether to ask for confirmation
            before starting to download a file, defaults to ``True``
        :type download: bool
        :param pickle_it: whether to save the .shp data as a pickle file, defaults to ``False``
        :type pickle_it: bool
        :param ret_pickle_path: (when ``pickle_it=True``)
            whether to return a path to the saved pickle file
        :type ret_pickle_path: bool
        :param rm_extracts: whether to delete extracted files from the .shp.zip file,
            defaults to ``False``
        :type rm_extracts: bool
        :param rm_shp_zip: whether to delete the downloaded .shp.zip file, defaults to ``False``
        :type rm_shp_zip: bool
        :param verbose: whether to print relevant information in console as the function runs,
            defaults to ``False``
        :type verbose: bool or int
        :return: dictionary of the shapefile data,
            with keys and values being layer names and tabular data
            (in the format of `geopandas.GeoDataFrame`_), respectively
        :rtype: dict or collections.OrderedDict or None

        .. _`geopandas.GeoDataFrame`: https://geopandas.org/reference.html#geodataframe

        **Examples**::

            >>> from pydriosm.reader import GeofabrikReader
            >>> from pyhelpers.dirs import delete_dir

            >>> gfr = GeofabrikReader()

            >>> subrgn_name = 'London'
            >>> dat_dir = "tests\\osm_data"

            >>> london_shp_data = gfr.read_shp_zip(
            ...     subregion_name=subrgn_name, data_dir=dat_dir, download=False, verbose=True)
            The .shp.zip file for "Greater London" is not found.

            >>> # Set `download=True`
            >>> london_shp_data = gfr.read_shp_zip(
            ...     subregion_name=subrgn_name, data_dir=dat_dir, download=True, verbose=True)
            Downloading "greater-london-latest-free.shp.zip"
                to "tests\\osm_data\\greater-london\\" ... Done.
            Extracting "tests\\osm_data\\greater-london\\greater-london-latest-free.shp.zip"
                to "tests\\osm_data\\greater-london\\greater-london-latest-free-shp\\" ... Done.
            Reading the shapefile(s) at
                "tests\\osm_data\\greater-london\\greater-london-latest-free-shp\\" ... Done.
            >>> type(london_shp_data)
            collections.OrderedDict
            >>> list(london_shp_data.keys())
            ['buildings',
             'landuse',
             'natural',
             'places',
             'pofw',
             'pois',
             'railways',
             'roads',
             'traffic',
             'transport',
             'water',
             'waterways']

            >>> # Data of the 'railways' layer
            >>> london_shp_railways = london_shp_data['railways']
            >>> london_shp_railways.head()
               osm_id  code  ...                                        coordinates shape_type
            0   30804  6101  ...  [(0.0048644, 51.6279262), (0.0061979, 51.62926...          3
            1  101298  6103  ...  [(-0.2249906, 51.493682), (-0.2251678, 51.4945...          3
            2  101486  6103  ...  [(-0.2055497, 51.5195429), (-0.2051377, 51.519...          3
            3  101511  6101  ...  [(-0.2119027, 51.5241906), (-0.2108059, 51.523...          3
            4  282898  6103  ...  [(-0.1862586, 51.6159083), (-0.1868721, 51.613...          3
            [5 rows x 9 columns]

            >>> # Read data of the 'transport' layer only from the original .shp.zip file
            >>> # (and delete any extracts)
            >>> subrgn_layer = 'transport'

            >>> # Set `rm_extracts=True` to remove the extracts
            >>> london_shp_transport = gfr.read_shp_zip(
            ...     subregion_name=subrgn_name, layer_names=subrgn_layer, data_dir=dat_dir,
            ...     rm_extracts=True, verbose=True)
            Reading the shapefile(s) at
                "tests\\osm_data\\greater-london\\greater-london-latest-free-shp\\" ... Done.
            Deleting the extracts "tests\\osm_data\\greater-london\\greater-london-latest-free-sh...
            >>> type(london_shp_transport)
            collections.OrderedDict
            >>> list(london_shp_transport.keys())
            ['transport']
            >>> london_shp_transport_ = london_shp_transport['transport']
            >>> london_shp_transport_.head()
                 osm_id  ...  shape_type
            0   5077928  ...           5
            1   8610280  ...           5
            2  15705264  ...           5
            3  23077379  ...           5
            4  24016945  ...           5
            [5 rows x 6 columns]

            >>> # Read data of only the 'bus_stop' feature (in the 'transport' layer)
            >>> # from the original .shp.zip file (and delete any extracts)
            >>> feat_name = 'bus_stop'
            >>> london_bus_stop = gfr.read_shp_zip(
            ...     subregion_name=subrgn_name, layer_names=subrgn_layer, feature_names=feat_name,
            ...     data_dir=dat_dir, rm_extracts=True, verbose=True)
            Extracting the following layer(s):
                'transport'
                from "tests\\osm_data\\greater-london\\greater-london-latest-free.shp.zip"
                  to "tests\\osm_data\\greater-london\\greater-london-latest-free-shp\\" ... Done.
            Reading the shapefile(s) at
                "tests\\osm_data\\greater-london\\greater-london-latest-free-shp\\" ... Done.
            Deleting the extracts "tests\\osm_data\\greater-london\\greater-london-latest-free-sh...
            >>> type(london_bus_stop)
            collections.OrderedDict
            >>> list(london_bus_stop.keys())
            ['transport']

            >>> fclass = london_bus_stop['transport'].fclass.unique()
            >>> fclass
            array(['bus_stop'], dtype=object)

            >>> # Read multiple features of multiple layers
            >>> # (and delete both the original .shp.zip file and extracts)
            >>> subrgn_layers = ['traffic', 'roads']
            >>> feat_names = ['parking', 'trunk']
            >>> london_shp_tra_roa_par_tru = gfr.read_shp_zip(
            ...     subregion_name=subrgn_name, layer_names=subrgn_layers, feature_names=feat_names,
            ...     data_dir=dat_dir, rm_extracts=True, rm_shp_zip=True, verbose=True)
            Extracting the following layer(s):
                'traffic'
                'roads'
                from "tests\\osm_data\\greater-london\\greater-london-latest-free.shp.zip"
                  to "tests\\osm_data\\greater-london\\greater-london-latest-free-shp\\" ... Done.
            Reading the shapefile(s) at
                "tests\\osm_data\\greater-london\\greater-london-latest-free-shp\\" ... Done.
            Deleting the extracts "tests\\osm_data\\greater-london\\greater-london-latest-free-sh...
            Deleting "tests\\osm_data\\greater-london\\greater-london-latest-free.shp.zip" ... Done.
            >>> type(london_shp_tra_roa_par_tru)
            collections.OrderedDict
            >>> list(london_shp_tra_roa_par_tru.keys())
            ['traffic', 'roads']

            >>> # Data of the 'traffic' layer
            >>> london_shp_tra_roa_par_tru['traffic'].head()
                osm_id  code  ...                                        coordinates shape_type
            0  2956081  5260  ...  [(-0.0218269, 51.4369515), (-0.020097, 51.4372...          5
            1  2956183  5260  ...  [(-0.0224697, 51.4452646), (-0.0223272, 51.445...          5
            2  2956184  5260  ...  [(-0.0186703, 51.444221), (-0.0185442, 51.4447...          5
            3  2956185  5260  ...  [(-0.0189846, 51.4481958), (-0.0189417, 51.448...          5
            4  2956473  5260  ...  [(-0.0059602, 51.4579088), (-0.0058695, 51.457...          5
            [5 rows x 6 columns]

            >>> # Data of the 'roads' layer
            >>> london_shp_tra_roa_par_tru['roads'].head()
               osm_id  code  ...                                        coordinates shape_type
            7    1200  5112  ...  [(-0.2916285, 51.5160418), (-0.2915517, 51.516...          3
            8    1201  5112  ...  [(-0.2925582, 51.5300857), (-0.2925916, 51.529...          3
            9    1202  5112  ...  [(-0.2230893, 51.5735075), (-0.2228416, 51.573...          3
            10   1203  5112  ...  [(-0.139105, 51.6101568), (-0.1395372, 51.6100...          3
            11   1208  5112  ...  [(-0.1176027, 51.6124616), (-0.1169584, 51.612...          3
            [5 rows x 12 columns]

            >>> # Delete the example data and the test data directory
            >>> delete_dir(dat_dir, verbose=True)
            To delete the directory "tests\\osm_data\\" (Not empty)
            ? [No]|Yes: yes
            Deleting "tests\\osm_data\\" ... Done.
        """

        shp_data = super().read_shp_zip(
            subregion_name=subregion_name, layer_names=layer_names, feature_names=feature_names,
            data_dir=data_dir, update=update, download=download, pickle_it=pickle_it,
            ret_pickle_path=ret_pickle_path, rm_extracts=rm_extracts, rm_shp_zip=rm_shp_zip,
            verbose=verbose, **kwargs)

        return shp_data


class BBBikeReader(_Reader):
    """
    Read `BBBike <https://download.bbbike.org/>`_ exports of OpenStreetMap data.
    """

    #: str: Default download directory.
    DEFAULT_DOWNLOAD_DIR = "osm_data\\bbbike"
    #: set: Valid file formats.
    FILE_FORMATS = {
        '.csv.xz',
        '.garmin-onroad-latin1.zip',
        '.garmin-onroad.zip',
        '.garmin-opentopo.zip',
        '.garmin-osm.zip',
        '.geojson.xz',
        '.gz',
        '.mapsforge-osm.zip',
        '.pbf',
        '.shp.zip',
        '.svg-osm.zip',
    }

    def __init__(self, max_tmpfile_size=5000, data_dir=None):
        """
        :param max_tmpfile_size: defaults to ``5000``,
            see also :func:`gdal_configurations<pydriosm.settings.gdal_configurations>`
        :type max_tmpfile_size: int or None
        :param data_dir: (a path or a name of) a directory where a data file is;
            if ``None`` (default), a folder ``osm_bbbike`` under the current working directory
        :type data_dir: str or None

        :ivar BBBikeDownloader downloader: instance of the class
            :py:class:`BBBikeDownloader<pydriosm.downloader.BBBikeDownloader>`
        :ivar str name: name of the data resource
        :ivar str url: url of the homepage to the BBBike free download server

        **Examples**::

            >>> from pydriosm.reader import BBBikeReader

            >>> bbr = BBBikeReader()

            >>> bbr.NAME
            'BBBike'
        """

        # noinspection PyTypeChecker
        super().__init__(
            max_tmpfile_size=max_tmpfile_size, downloader=BBBikeDownloader, data_dir=data_dir)

    def read_osm_pbf(self, subregion_name, data_dir=None, readable=False, expand=False,
                     parse_geometry=False, parse_other_tags=False, parse_properties=False,
                     update=False, download=True, pickle_it=False, ret_pickle_path=False,
                     rm_pbf_file=False, chunk_size_limit=50, verbose=False, **kwargs):
        """
        Read a PBF (.osm.pbf) data file of a geographic (sub)region.

        :param subregion_name: name of a geographic (sub)region (case-insensitive)
            that is available on Geofabrik free download server
        :type subregion_name: str
        :param data_dir: directory where the .osm.pbf data file is located/saved;
            if ``None``, the default local directory
        :type data_dir: str or None
        :param readable: whether to parse each feature in the raw data, defaults to ``False``
        :type readable: bool
        :param expand: whether to expand dict-like data into separate columns, defaults to ``False``
        :type expand: bool
        :param parse_geometry: whether to represent the ``'geometry'`` field
            in a `shapely.geometry`_ format, defaults to ``False``
        :type parse_geometry: bool
        :param parse_properties: whether to represent the ``'properties'`` field
            in a tabular format, defaults to ``False``
        :type parse_properties: bool
        :param parse_other_tags: whether to represent a ``'other_tags'`` (of ``'properties'``)
            in a `dict`_ format, defaults to ``False``
        :type parse_other_tags: bool
        :param download: whether to download/update the PBF data file of the given subregion,
            if it is not available at the specified path, defaults to ``True``
        :type download: bool
        :param update: whether to check to update pickle backup (if available), defaults to ``False``
        :type update: bool
        :param pickle_it: whether to save the .pbf data as a pickle file, defaults to ``False``
        :type pickle_it: bool
        :param ret_pickle_path: (when ``pickle_it=True``)
            whether to return a path to the saved pickle file
        :type ret_pickle_path: bool
        :param rm_pbf_file: whether to delete the downloaded .osm.pbf file, defaults to ``False``
        :type rm_pbf_file: bool
        :param chunk_size_limit: threshold (in MB) that triggers the use of chunk parser,
            defaults to ``50``;
            if the size of the .osm.pbf file (in MB) is greater than ``chunk_size_limit``,
            it will be parsed in a chunk-wise way
        :type chunk_size_limit: int or None
        :param verbose: whether to print relevant information in console as the function runs,
            defaults to ``False``
        :type verbose: bool or int
        :param kwargs: [optional] parameters of the method
            :meth:`_Reader.read_osm_pbf()<pydriosm.reader._Reader.read_osm_pbf>`
        :return: dictionary of the .osm.pbf data;
            when ``pickle_it=True``, return a tuple of the dictionary and a path to the pickle file
        :rtype: dict or tuple or None

        .. _`shapely.geometry`: https://shapely.readthedocs.io/en/latest/manual.html#geometric-objects
        .. _`dict`: https://docs.python.org/3/library/stdtypes.html#dict

        **Examples**::

            >>> from pydriosm.reader import BBBikeReader
            >>> from pyhelpers.dirs import delete_dir

            >>> bbr = BBBikeReader()

            >>> subrgn_name = 'Leeds'
            >>> dat_dir = "tests\\osm_data"

            >>> leeds_pbf_raw = bbr.read_osm_pbf(subrgn_name, data_dir=dat_dir, verbose=True)
            Downloading "Leeds.osm.pbf"
                to "tests\\osm_data\\leeds\\" ... Done.
            Reading "tests\\osm_data\\leeds\\Leeds.osm.pbf" ... Done.
            >>> type(leeds_pbf_raw)
            dict
            >>> list(leeds_pbf_raw.keys())
            ['points', 'lines', 'multilinestrings', 'multipolygons', 'other_relations']

            >>> pbf_raw_points = leeds_pbf_raw['points']
            >>> type(pbf_raw_points)
            list
            >>> type(pbf_raw_points[0])
            osgeo.ogr.Feature

            >>> # (Parsing the data in this example might take up to a few minutes.)
            >>> leeds_pbf_parsed = bbr.read_osm_pbf(
            ...     subrgn_name, data_dir=dat_dir, readable=True, expand=True,
            ...     parse_geometry=True, parse_other_tags=True, parse_properties=True,
            ...     verbose=True)
            Parsing "tests\\osm_data\\leeds\\Leeds.osm.pbf" ... Done.

            >>> list(leeds_pbf_parsed.keys())
            ['points', 'lines', 'multilinestrings', 'multipolygons', 'other_relations']

            >>> # Data of the 'multipolygons' layer
            >>> leeds_pbf_parsed_multipolygons = leeds_pbf_parsed['multipolygons']
            >>> leeds_pbf_parsed_multipolygons.head()
                  id                                           geometry  ... tourism other_tags
            0  10595  (POLYGON ((-1.5030223 53.6725382, -1.5034495 5...  ...    None       None
            1  10600  (POLYGON ((-1.5116994 53.6764287, -1.5099361 5...  ...    None       None
            2  10601  (POLYGON ((-1.5142403 53.6710831, -1.5143686 5...  ...    None       None
            3  10612  (POLYGON ((-1.5129341 53.6704885, -1.5131883 5...  ...    None       None
            4  10776  (POLYGON ((-1.5523801 53.7029081, -1.5524772 5...  ...    None       None
            [5 rows x 26 columns]

            >>> # Delete the example data and the test data directory
            >>> delete_dir(dat_dir, verbose=True)
            To delete the directory "tests\\osm_data\\" (Not empty)
            ? [No]|Yes: yes
            Deleting "tests\\osm_data\\" ... Done.

        .. seealso::

            - Examples for the method
              :meth:`GeofabrikReader.read_osm_pbf()<pydriosm.reader.GeofabrikReader.read_osm_pbf>`.
        """

        osm_pbf_data = super().read_osm_pbf(
            subregion_name=subregion_name, data_dir=data_dir, readable=readable, expand=expand,
            parse_geometry=parse_geometry, parse_properties=parse_properties,
            parse_other_tags=parse_other_tags, update=update, download=download,
            pickle_it=pickle_it, ret_pickle_path=ret_pickle_path, rm_pbf_file=rm_pbf_file,
            chunk_size_limit=chunk_size_limit, verbose=verbose, **kwargs)

        return osm_pbf_data

    def read_shp_zip(self, subregion_name, layer_names=None, feature_names=None, data_dir=None,
                     update=False, download=True, pickle_it=False, ret_pickle_path=False,
                     rm_extracts=False, rm_shp_zip=False, verbose=False, **kwargs):
        """
        Read a shapefile of a geographic (sub)region.

        :param subregion_name: name of a geographic (sub)region (case-insensitive)
            that is available on BBBike free download server
        :type subregion_name: str
        :param layer_names: name of a .shp layer, e.g. 'railways', or names of multiple layers;
            if ``None`` (default), all available layers
        :type layer_names: str or list or None
        :param feature_names: name of a feature, e.g. 'rail', or names of multiple features;
            if ``None`` (default), all available features
        :type feature_names: str or list or None
        :param data_dir: directory where the .shp.zip data file is located/saved;
            if ``None``, the default directory
        :type data_dir: str or None
        :param update: whether to check to update pickle backup (if available), defaults to ``False``
        :type update: bool
        :param download: whether to ask for confirmation
            before starting to download a file, defaults to ``True``
        :type download: bool
        :param pickle_it: whether to save the .shp data as a pickle file, defaults to ``False``
        :type pickle_it: bool
        :param ret_pickle_path: (when ``pickle_it=True``)
            whether to return a path to the saved pickle file
        :type ret_pickle_path: bool
        :param rm_extracts: whether to delete extracted files from the .shp.zip file,
            defaults to ``False``
        :type rm_extracts: bool
        :param rm_shp_zip: whether to delete the downloaded .shp.zip file, defaults to ``False``
        :type rm_shp_zip: bool
        :param verbose: whether to print relevant information in console as the function runs,
            defaults to ``False``
        :type verbose: bool or int
        :return: dictionary of the shapefile data, with keys and values being layer names
            and tabular data (in the format of `geopandas.GeoDataFrame`_), respectively;
            when ``pickle_it=True``, return a tuple of the dictionary and a path to the pickle file
        :rtype: dict or collections.OrderedDict or tuple or None

        .. _`geopandas.GeoDataFrame`: https://geopandas.org/reference.html#geodataframe

        **Examples**::

            >>> from pydriosm.reader import BBBikeReader
            >>> from pyhelpers.dirs import delete_dir
            >>> import os

            >>> bbr = BBBikeReader()

            >>> subrgn_name = 'Birmingham'
            >>> dat_dir = "tests\\osm_data"

            >>> bham_shp = bbr.read_shp_zip(
            ...     subregion_name=subrgn_name, data_dir=dat_dir, download=False, verbose=True)
            The .shp.zip file for "Birmingham" is not found.

            >>> # Set `download=True`
            >>> bham_shp = bbr.read_shp_zip(
            ...     subregion_name=subrgn_name, data_dir=dat_dir, download=True, verbose=True)
            Downloading "Birmingham.osm.shp.zip"
                to "tests\\osm_data\\birmingham\\" ... Done.
            Extracting "tests\\osm_data\\birmingham\\Birmingham.osm.shp.zip"
                to "tests\\osm_data\\birmingham\\" ... Done.
            Reading the shapefile(s) at
                "tests\\osm_data\\birmingham\\Birmingham-shp\\shape\\" ... Done.
            >>> type(bham_shp)
            collections.OrderedDict
            >>> list(bham_shp.keys())
            ['buildings',
             'landuse',
             'natural',
             'places',
             'points',
             'railways',
             'roads',
             'waterways']

            >>> # Data of 'railways' layer
            >>> bham_railways_shp = bham_shp['railways']
            >>> bham_railways_shp.head()
                osm_id  ... shape_type
            0      740  ...          3
            1     2148  ...          3
            2  2950000  ...          3
            3  3491845  ...          3
            4  3981454  ...          3
            [5 rows x 5 columns]

            >>> # Read data of 'road' layer only from the original .shp.zip file
            >>> # (and delete all extracts)
            >>> lyr_name = 'roads'
            >>> bham_roads_shp = bbr.read_shp_zip(
            ...     subregion_name=subrgn_name, layer_names=lyr_name, data_dir=dat_dir,
            ...     rm_extracts=True, verbose=True)
            Reading "tests\\osm_data\\birmingham\\Birmingham-shp\\shape\\roads.shp" ... Done.
            Deleting the extracts "tests\\osm_data\\birmingham\\Birmingham-shp\\"  ... Done.
            >>> type(bham_roads_shp)
            collections.OrderedDict
            >>> list(bham_roads_shp.keys())
            ['roads']
            >>> bham_roads_shp[lyr_name].head()
               osm_id  ... shape_type
            0      37  ...          3
            1      38  ...          3
            2      41  ...          3
            3      45  ...          3
            4      46  ...          3
            [5 rows x 9 columns]

            >>> # Read data of multiple layers and features from the original .shp.zip file
            >>> # (and delete all extracts)
            >>> lyr_names = ['railways', 'waterways']
            >>> feat_names = ['rail', 'canal']
            >>> bham_rw_rc_shp = bbr.read_shp_zip(
            ...     subregion_name=subrgn_name, layer_names=lyr_names, feature_names=feat_names,
            ...     data_dir=dat_dir, rm_extracts=True, rm_shp_zip=True, verbose=True)
            Extracting the following layer(s):
                'railways'
                'waterways'
                from "tests\\osm_data\\birmingham\\Birmingham.osm.shp.zip"
                  to "tests\\osm_data\\birmingham\\" ... Done.
            Reading the data at "tests\\osm_data\\birmingham\\Birmingham-shp\\shape\\" ... Done.
            Deleting the extracts "tests\\osm_data\\birmingham\\Birmingham-shp\\"  ... Done.
            Deleting "tests\\osm_data\\birmingham\\Birmingham.osm.shp.zip" ... Done.
            >>> type(bham_rw_rc_shp)
            collections.OrderedDict
            >>> list(bham_rw_rc_shp.keys())
            ['railways', 'waterways']

            >>> # Data of the 'railways' layer
            >>> bham_rw_rc_shp_railways = bham_rw_rc_shp['railways']
            >>> bham_rw_rc_shp_railways[['type', 'name']].head()
               type                                             name
            0  rail                                  Cross-City Line
            1  rail                                  Cross-City Line
            2  rail  Derby to Birmingham (Proof House Junction) Line
            3  rail                  Birmingham to Peterborough Line
            4  rail          Water Orton to Park Lane Junction Curve

            >>> # Data of the 'waterways' layer
            >>> bham_rw_rc_shp_waterways = bham_rw_rc_shp['waterways']
            >>> bham_rw_rc_shp_waterways[['type', 'name']].head()
                 type                                              name
            2   canal                      Birmingham and Fazeley Canal
            8   canal                      Birmingham and Fazeley Canal
            9   canal  Birmingham Old Line Canal Navigations - Rotton P
            10  canal                               Oozells Street Loop
            11  canal                      Worcester & Birmingham Canal

            >>> # Delete the example data and the test data directory
            >>> delete_dir(dat_dir, verbose=True)
            To delete the directory "tests\\osm_data\\" (Not empty)
            ? [No]|Yes: yes
            Deleting "tests\\osm_data\\" ... Done.
        """

        # osm_file_format = ".shp.zip"
        #
        # subregion_name_, shp_zip_filename, _, shp_zip_pathname = \
        #     self.downloader.get_valid_download_info(
        #         subregion_name=subregion_name, osm_file_format=osm_file_format, download_dir=data_dir)
        #
        # layer_names_, feature_names_ = map(self.validate_input_dtype, [layer_names, feature_names])
        #
        # if all(x is not None for x in {shp_zip_filename, shp_zip_pathname}):
        #     extract_dir = os.path.splitext(shp_zip_pathname)[0].replace(".osm.", "-")
        #
        #     path_to_shp_pickle = self.make_shp_pkl_pathname(
        #         shp_zip_filename=shp_zip_filename, extract_dir=extract_dir, layer_names_=layer_names_,
        #         feature_names_=feature_names_)
        #
        #     if os.path.isfile(path_to_shp_pickle) and not update:
        #         shp_data = load_pickle(path_to_shp_pickle)
        #
        #         if ret_pickle_path:
        #             shp_data = shp_data, path_to_shp_pickle
        #
        #     else:
        #         try:
        #             layer_name_list = self.validate_shp_layer_names(
        #                 layer_names_=layer_names_, extract_dir=extract_dir,
        #                 shp_zip_pathname=shp_zip_pathname, subregion_name=subregion_name_,
        #                 osm_file_format=osm_file_format, data_dir=data_dir, update=update,
        #                 download=download, verbose=verbose)
        #
        #             paths_to_layers_shp = [
        #                 glob.glob(os.path.join(extract_dir, "shape", f"{lyr_name}.shp"))
        #                 for lyr_name in layer_name_list]
        #             paths_to_layers_shp = [x for x in paths_to_layers_shp if x]
        #
        #             if verbose:
        #                 files_dir = os.path.relpath(
        #                     os.path.commonpath(list(itertools.chain.from_iterable(paths_to_layers_shp))))
        #                 msg_ = "the data at" if os.path.isdir(files_dir) else ""
        #                 print(f'Reading {msg_} "{files_dir}\\"', end=" ... ")
        #
        #             shp_dat_list = [
        #                 self.SHP.read_layer_shps(p, feature_names=feature_names_)
        #                 for p in paths_to_layers_shp]
        #
        #             shp_data = collections.OrderedDict(zip(layer_name_list, shp_dat_list))
        #
        #             if verbose:
        #                 print("Done.")
        #
        #             if pickle_it:
        #                 save_pickle(shp_data, path_to_shp_pickle, verbose=verbose)
        #
        #                 if ret_pickle_path:
        #                     shp_data = shp_data, path_to_shp_pickle
        #
        #             if os.path.exists(extract_dir) and rm_extracts:
        #                 self.remove_extracts(extract_dir, verbose=verbose)
        #
        #             if os.path.isfile(shp_zip_pathname) and rm_shp_zip:
        #                 remove_osm_file(shp_zip_pathname, verbose=verbose)
        #
        #         except Exception as e:
        #             print(f"Failed. {e}")
        #             shp_data = None

        shp_data = super().read_shp_zip(
            subregion_name=subregion_name, layer_names=layer_names, feature_names=feature_names,
            data_dir=data_dir, update=update, download=download, pickle_it=pickle_it,
            ret_pickle_path=ret_pickle_path, rm_extracts=rm_extracts, rm_shp_zip=rm_shp_zip,
            verbose=verbose, **kwargs)

        return shp_data

    def read_csv_xz(self, subregion_name, data_dir=None, download=False, verbose=False, **kwargs):
        """
        Read a compressed CSV (.csv.xz) data file of a geographic (sub)region.

        :param subregion_name: name of a geographic (sub)region (case-insensitive)
            that is available on BBBike free download server
        :type subregion_name: str
        :param data_dir: directory where the .csv.xz data file is located/saved;
            if ``None`` (default), the default directory
        :type data_dir: str or None
        :param download: whether to try to download the requisite data file if it does not exist,
            defaults to ``True``
        :type download: bool
        :param verbose: whether to print relevant information in console as the function runs,
            defaults to ``False``
        :type verbose: bool or int
        :return: tabular data of the .csv.xz file
        :rtype: pandas.DataFrame or None

        .. _pydriosm-BBBikeReader-read_csv_xz:

        **Examples**::

            >>> from pydriosm.reader import BBBikeReader
            >>> from pyhelpers.dirs import cd, delete_dir

            >>> bbr = BBBikeReader()

            >>> subrgn_name = 'Leeds'
            >>> dat_dir = "tests\\osm_data"

            >>> leeds_csv_xz = bbr.read_csv_xz(subrgn_name, dat_dir, verbose=True)
            The requisite data file "tests\\osm_data\\leeds\\Leeds.osm.csv.xz" does not exist.

            >>> leeds_csv_xz = bbr.read_csv_xz(subrgn_name, dat_dir, verbose=True, download=True)
            Downloading "Leeds.osm.csv.xz"
                to "tests\\osm_data\\leeds\\" ... Done.
            Parsing the data ... Done.

            >>> leeds_csv_xz.head()
               type      id feature  note
            0  node  154915    None  None
            1  node  154916    None  None
            2  node  154921    None  None
            3  node  154922    None  None
            4  node  154923    None  None

            >>> # Delete the downloaded .csv.xz data file
            >>> delete_dir(dat_dir, verbose=True)
            To delete the directory "tests\\osm_data\\" (Not empty)
            ? [No]|Yes: yes
            Deleting "tests\\osm_data\\" ... Done.
        """

        csv_xz_data = self.read_osm_var(
            self.VAR.read_csv_xz, subregion_name=subregion_name, osm_file_format=".csv.xz",
            data_dir=data_dir, download=download, verbose=verbose, **kwargs)

        return csv_xz_data

    def read_geojson_xz(self, subregion_name, data_dir=None, parse_geometry=False, download=False,
                        verbose=False, **kwargs):
        """
        Read a .geojson.xz data file of a geographic (sub)region.

        :param subregion_name: name of a geographic (sub)region (case-insensitive)
            that is available on BBBike free download server
        :type subregion_name: str
        :param data_dir: directory where the .geojson.xz data file is located/saved;
            if ``None`` (default), the default directory
        :type data_dir: str or None
        :param parse_geometry: whether to represent coordinates in a format of a geometric object,
            defaults to ``False``
        :type parse_geometry: bool
        :param download: whether to try to download the requisite data file if it does not exist,
            defaults to ``True``
        :type download: bool
        :param verbose: whether to print relevant information in console as the function runs,
            defaults to ``False``
        :type verbose: bool or int
        :return: tabular data of the .csv.xz file
        :rtype: pandas.DataFrame or None

        .. _pydriosm-BBBikeReader-read_geojson_xz:

        **Examples**::

            >>> from pydriosm.reader import BBBikeReader
            >>> from pyhelpers.dirs import cd, delete_dir
            >>> import os

            >>> bbr = BBBikeReader()

            >>> subrgn_name = 'Leeds'
            >>> dat_dir = "tests\\osm_data"

            >>> leeds_geoj = bbr.read_geojson_xz(subrgn_name, dat_dir, verbose=True)
            The requisite data file "tests\\osm_data\\leeds\\Leeds.osm.geojson.xz" does not exist.

            >>> # Set `try_download=True`
            >>> leeds_geoj = bbr.read_geojson_xz(subrgn_name, dat_dir, verbose=True, download=True)
            Downloading "Leeds.osm.geojson.xz"
                to "tests\\osm_data\\leeds\\" ... Done.
            Parsing the data ... Done.
            >>> leeds_geoj.head()
                                                        geometry                          properties
            0  {'type': 'Point', 'coordinates': [-1.5558097, ...  {'highway': 'motorway_junction'...
            1  {'type': 'Point', 'coordinates': [-1.34293, 53...  {'highway': 'motorway_junction'...
            2  {'type': 'Point', 'coordinates': [-1.517335, 5...  {'highway': 'motorway_junction'...
            3  {'type': 'Point', 'coordinates': [-1.514124, 5...  {'highway': 'motorway_junction'...
            4  {'type': 'Point', 'coordinates': [-1.516511, 5...  {'highway': 'motorway_junction'...

            >>> # Set `parse_geometry` to be True
            >>> leeds_geoj_ = bbr.read_geojson_xz(subrgn_name, dat_dir, parse_geometry=True,
            ...                                   verbose=True)
            Parsing "tests\\osm_data\\leeds\\Leeds.osm.geojson.xz" ... Done.
            >>> leeds_geoj_['geometry'].head()
            0    POINT (-1.5560511 53.6879848)
            1       POINT (-1.34293 53.844618)
            2     POINT (-1.517335 53.7499667)
            3     POINT (-1.514124 53.7416937)
            4     POINT (-1.516511 53.7256632)
            Name: geometry, dtype: object

            >>> # Delete the download directory
            >>> delete_dir(dat_dir, verbose=True)
        """

        kwargs.update({'parse_geometry': parse_geometry})

        geojson_xz_data = self.read_osm_var(
            self.VAR.read_geojson_xz, subregion_name=subregion_name, osm_file_format=".geojson.xz",
            data_dir=data_dir, download=download, verbose=verbose, **kwargs)

        return geojson_xz_data
