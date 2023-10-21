"""
Transform the OSM data.
"""

import copy
import re

import pandas as pd
import shapely.errors
import shapely.geometry
from pyhelpers.ops import update_dict

from pydriosm.errors import OtherTagsReformatError


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
        :type geometry: dict | pandas.DataFrame
        :param mode: indicate the way of parsing the input;

            - when ``mode=1`` **(default)**, the input ``geometry`` should be directly accessible
              and would be in the format of ``{'type': <shape type>, 'coordinates': <coordinates>}``
              or as a row of a `pandas.DataFrame`_;
            - when ``mode=2``, the input ``geometry`` is in the `GeoJSON`_ format

        :type mode: int
        :param to_wkt: whether to represent the geometry in the WKT (well-known text) format,
            defaults to ``False``
        :type to_wkt: bool
        :return: reformatted geometry data
        :rtype: shapely.geometry.Point | dict | str

        .. _`shapely.geometry`:
            https://shapely.readthedocs.io/en/latest/manual.html#geometric-objects
        .. _`pandas.DataFrame`:
            https://pandas.pydata.org/docs/reference/api/pandas.DataFrame.html
        .. _`GeoJSON`:
            https://geojson.org/

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
                geom_data = geom_func(
                    shapely.geometry.Polygon(y) for x in cls.point_as_polygon(coords) for y in x)
                # geom_data = geom.wkt if to_wkt else geom.geoms

            else:
                geom_data = geom_func(coords)
                # if to_wkt:
                #     geom_data = geom_data.wkt
                # elif 'Multi' in geom_type:
                #     geom_data = geom_data.geoms

            if to_wkt:
                geom_data = geom_data.wkt

        else:
            geom_data = geometry.copy()
            dat = cls.transform_unitary_geometry(geometry['geometry'], mode=1, to_wkt=True)
            geom_data.update({'geometry': dat})

        return geom_data

    @classmethod
    def transform_geometry_collection(cls, geometry, mode=1, to_wkt=False):
        """
        Transform a collection of geometry from dict into a `shapely.geometry`_ object.

        :param geometry: geometry data for a feature of ``GeometryCollection``
        :type geometry: list | dict
        :param mode: indicate the way of parsing the input;

            - when ``mode=1`` **(default)**, the input ``geometry`` should be directly accessible
              and would be in the format of ``{'type': <shape type>, 'coordinates': <coordinates>}``
              or as a row of a `pandas.DataFrame`_;
            - when ``mode=2``, the input ``geometry`` is in the `GeoJSON`_ format

        :type mode: int
        :param to_wkt: whether to represent the geometry in the WKT (well-known text) format,
            defaults to ``False``
        :type to_wkt: bool
        :return: reformatted geometry data
        :rtype: shapely.geometry.base.HeterogeneousGeometrySequence | dict | str

        .. _`shapely.geometry`:
            https://shapely.readthedocs.io/en/latest/manual.html#geometric-objects
        .. _`pandas.DataFrame`:
            https://pandas.pydata.org/docs/reference/api/pandas.DataFrame.html
        .. _`GeoJSON`:
            https://geojson.org/

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
            shapely.geometry.collection.GeometryCollection
            >>> g1_data.wkt
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

            geome_data = shapely.geometry.GeometryCollection(geometry_collection)
            if to_wkt:
                geome_data = geome_data.wkt
            # else:
            #     geome_data = shapely.geometry.GeometryCollection(geometry_collection).geoms

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
        :type layer_data: pandas.DataFrame | pandas.Series
        :param layer_name: name (geometric type) of the PBF layer
        :type layer_name: str
        :return: (OSM feature with) reformatted geometry field
        :rtype: pandas.DataFrame | pandas.Series

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
        :type other_tags: str | None
        :return: reformatted data of ``'other_tags'``
        :rtype: dict | None

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
                fltr = filter(
                    lambda x: len(x) == 2, (re.split(r'"=>"?', x) for x in filter(None, tags)))
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
