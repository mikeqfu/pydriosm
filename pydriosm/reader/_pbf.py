
import collections
import os
import warnings

import pandas as pd
import shapely.geometry
from pyhelpers._cache import _check_dependency, _print_failure_message
from pyhelpers.dirs import check_relative_pathname
from pyhelpers.ops import split_list
from pyhelpers.settings import gdal_configurations

from pydriosm.reader.formatter import process_geometry_layer, reformat_other_tags, \
    refresh_other_tags


class PBF:
    """
    Read/parse `PBF <https://wiki.openstreetmap.org/wiki/PBF_Format>`_ data.

    **Examples**::

        >>> from pydriosm.reader import PBF

        >>> PBF.LAYER_GEOM
        {'points': shapely.geometry.point.Point,
         'lines': shapely.geometry.linestring.LineString,
         'multilinestrings': shapely.geometry.multilinestring.MultiLineString,
         'multipolygons': shapely.geometry.multipolygon.MultiPolygon,
         'other_relations': shapely.geometry.collection.GeometryCollection}
    """

    #: Layer names of an OSM PBF file and their corresponding
    #: `geometric objects <https://shapely.readthedocs.io/en/latest/manual.html#geometric-objects>`_
    #: defined in `Shapely <https://pypi.org/project/Shapely/>`_.
    LAYER_GEOM: dict = {
        'points': shapely.geometry.Point,
        'lines': shapely.geometry.LineString,
        'multilinestrings': shapely.geometry.MultiLineString,
        'multipolygons': shapely.geometry.MultiPolygon,
        'other_relations': shapely.geometry.GeometryCollection,
    }

    @classmethod
    def get_layer_geom_types(cls, shape_name=False):
        """
        A dictionary cross-referencing the names of PBF layers and their corresponding
        `geometric objects`_ defined in `Shapely`_, or names.

        :param shape_name: whether to return the names of geometry shapes, defaults to ``False``
        :type shape_name: bool
        :return: a dictionary with keys and values being, respectively,
            PBF layers and their corresponding `geometric objects`_ defined in `Shapely`_
        :rtype: dict

        .. _`geometric objects`:
            https://shapely.readthedocs.io/en/latest/manual.html#geometric-objects
        .. _`Shapely`:
            https://pypi.org/project/Shapely/

        **Examples**::

            >>> from pydriosm.reader import PBF

            >>> PBF.get_layer_geom_types()
            {'points': shapely.geometry.point.Point,
             'lines': shapely.geometry.linestring.LineString,
             'multilinestrings': shapely.geometry.multilinestring.MultiLineString,
             'multipolygons': shapely.geometry.multipolygon.MultiPolygon,
             'other_relations': shapely.geometry.collection.GeometryCollection}

            >>> PBF.get_layer_geom_types(shape_name=True)
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
    def get_layer_names(cls, path_to_file, verbose=False, raise_error=False):
        """
        Get names (and indices) of all available layers in a PBF data file.

        :param path_to_file: path to a PBF data file
        :type path_to_file: str | os.PathLike[str]
        :param verbose: whether to print relevant information in console, defaults to ``False``
        :type verbose: bool | int
        :param raise_error: Whether to raise the provided exception;
            if ``raise_error=False`` (default), the error will be suppressed.
        :type raise_error: bool
        :return: indices and names of each layer of the PBF data file
        :rtype: dict

        **Examples**::

            >>> from pydriosm.reader import PBF
            >>> from pydriosm.downloader import GeofabrikDownloader
            >>> from pyhelpers.dirs import delete_dir
            >>> import os

            >>> # Download the PBF data file of London as an example
            >>> subrgn_name = 'london'
            >>> file_format = ".pbf"
            >>> dwnld_dir = "tests/osm_data"

            >>> gfd = GeofabrikDownloader()

            >>> gfd.download_data(subrgn_name, file_format, dwnld_dir, verbose=True)
            To download .osm.pbf data of the following geographic (sub)region(s):
                Greater London
            ? [No]|Yes: yes
            Downloading "greater-london-latest.osm.pbf"
                to "tests\\osm_data\\greater-london\\" ... Done.

            >>> london_pbf_pathname = gfd.data_paths[0]
            >>> os.path.relpath(london_pbf_pathname)
            'tests\\osm_data\\greater-london\\greater-london-latest.osm.pbf'

            >>> # Get indices and names of all layers in the downloaded PBF data file
            >>> pbf_layer_idx_names = PBF.get_layer_names(london_pbf_pathname)
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

            print(
                f"Getting the layer names of \"{check_relative_pathname(path_to_file)}\"",
                end=" ... ")

        try:
            osgeo_ogr = _check_dependency(name='osgeo.ogr')

            with warnings.catch_warnings(action='ignore', category=FutureWarning):
                f = osgeo_ogr.Open(path_to_file)

                layer_count = f.GetLayerCount()
                layer_names = [f.GetLayerByIndex(i).GetName() for i in range(layer_count)]

            layer_idx_names = dict(zip(range(layer_count), layer_names))

            if verbose:
                print("Done.")

            return layer_idx_names

        except Exception as e:
            _print_failure_message(
                e, prefix="Failed. Error:", verbose=verbose, raise_error=raise_error)

    @classmethod
    def transform_pbf_layer_field(cls, layer_data, layer_name, parse_geometry=False,
                                  parse_properties=False, parse_other_tags=False):
        """
        Parse data of a layer of PBF data.

        :param layer_data: dataframe of a specific layer of PBF data
        :type layer_data: pandas.DataFrame | pandas.Series
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
        :rtype: pandas.DataFrame | pandas.Series

        .. _`shapely.geometry`:
            https://shapely.readthedocs.io/en/latest/manual.html#geometric-objects
        .. _`dict`:
            https://docs.python.org/3/library/stdtypes.html#dict

        See examples for the method
        :meth:`PBFReadParse.read_pbf()<pydriosm.reader.PBFReadParse.read_pbf>`.
        """

        if not layer_data.empty:
            lyr_dat = layer_data.copy()

            if isinstance(lyr_dat, pd.Series):
                if parse_geometry:  # Reformat the geometry
                    lyr_dat = process_geometry_layer(layer_data=lyr_dat, layer_name=layer_name)

                if parse_other_tags:  # Reformat the 'other_tags' of properties
                    lyr_dat = lyr_dat.map(lambda x: refresh_other_tags(x, mode=2))

            else:
                # Whether to reformat the 'geometry'
                if parse_geometry:
                    geom_data = process_geometry_layer(layer_data=lyr_dat, layer_name=layer_name)
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
                        prop_data.loc[:, ot_name] = prop_data[ot_name].map(reformat_other_tags)
                else:
                    # Whether to reformat 'other_tags'
                    if parse_other_tags:
                        prop_data = lyr_dat[prop_col_name].map(refresh_other_tags)
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
    def _read_layer(cls, layer, readable, expand, parse_geometry, parse_properties,
                    parse_other_tags):
        """
        Parse a layer of a PBF data file.

        :param layer: a layer of a PBF data file, loaded by `GDAL/OGR`_
        :type layer: osgeo.ogr.Layer | list
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
        :rtype: pandas.DataFrame | list

        .. _`GDAL/OGR`:
            https://gdal.org
        .. _`shapely.geometry`:
            https://shapely.readthedocs.io/en/latest/manual.html#geometric-objects
        .. _`dict`:
            https://docs.python.org/3/library/stdtypes.html#dict

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

            lyr_dat = pd.DataFrame(dat) if expand else pd.Series(data=dat, name=layer_name)

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
    def _read_layer_chunkwise(cls, layer, number_of_chunks, **kwargs):
        """
        Parse a layer of a PBF data file chunk-wisely.

        :param layer: a layer of a PBF data file, loaded by `GDAL/OGR <https://gdal.org>`_
        :type layer: osgeo.ogr.Layer
        :param number_of_chunks: number of chunks
        :type number_of_chunks: int
        :param kwargs: [optional] parameters of the method
            :meth:`PBFReadParse._read_pbf_layer()<pydriosm.reader.PBFReadParse._read_pbf_layer>`
        :return: data of the given layer of the given OSM PBF layer
        :rtype: pandas.DataFrame | list

        See examples for the method
        :meth:`PBFReadParse.read_pbf()<pydriosm.reader.PBFReadParse.read_pbf>`.
        """

        layer_name = layer.GetName()
        layer_chunks = split_list(lst=[f for f in layer], num_of_sub=number_of_chunks)

        list_of_layer_dat = [
            cls._read_layer(lyr + [layer_name], **kwargs) for lyr in layer_chunks]

        if kwargs['readable']:
            layer_data = pd.concat(objs=list_of_layer_dat, axis=0, ignore_index=True)
        else:
            layer_data = [dat for chunk in list_of_layer_dat for dat in chunk]

        return layer_data

    @classmethod
    def read_layer(cls, layer, readable=True, expand=False, parse_geometry=False,
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
        :type number_of_chunks: int | None
        :return: parsed data of the given OSM PBF layer
        :rtype: dict

        .. _`shapely.geometry`:
            https://shapely.readthedocs.io/en/latest/manual.html#geometric-objects
        .. _`dict`:
            https://docs.python.org/3/library/stdtypes.html#dict

        .. seealso::

            - Examples for the method
              :meth:`PBFReadParse.read_pbf()<pydriosm.reader.PBFReadParse.read_pbf>`.
        """

        layer_name = layer.GetName()  # Get the name of the i-th layer

        func_args = dict(
            readable=readable,
            expand=expand,
            parse_geometry=parse_geometry,
            parse_properties=parse_properties,
            parse_other_tags=parse_other_tags
        )

        if number_of_chunks in {None, 0, 1}:
            layer_data = cls._read_layer(layer=layer, **func_args)
        else:
            layer_data = cls._read_layer_chunkwise(
                layer=layer, number_of_chunks=number_of_chunks, **func_args)

        data = {layer_name: layer_data}

        return data

    @classmethod
    def read_pbf(cls, path_to_file, readable=True, expand=False, parse_geometry=False,
                 parse_properties=False, parse_other_tags=False, number_of_chunks=None,
                 max_tmpfile_size=5000, **kwargs):
        # noinspection PyShadowingNames
        """
        Parse a PBF data file (by `GDAL <https://pypi.org/project/GDAL/>`_).

        :param path_to_file: pathname of a PBF data file
        :type path_to_file: str
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
        :type number_of_chunks: int | None
        :param max_tmpfile_size: maximum size of the temporary file, defaults to ``None``;
            when ``max_tmpfile_size=None``, it defaults to ``5000``
        :type max_tmpfile_size: int | None
        :param kwargs: [optional] parameters of the function
            `pyhelpers.settings.gdal_configurations()`_
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
            `OpenStreetMap XML and PBF <https://gdal.org/drivers/vector/osm.html>`_.

        .. warning::

            - **Parsing large PBF data files (e.g. > 50MB) can be time-consuming!**
            - The function :func:`~pydriosm.reader.read_osm_pbf` may require fairly high amount of
              physical memory to parse large files, in which case it would be recommended that
              ``number_of_chunks`` is set to be a reasonable value.

        .. _pydriosm-reader-PBFReadParse-read_osm_pbf:

        **Examples**::

            >>> from pydriosm.reader import PBF
            >>> from pydriosm.downloader import Downloader
            >>> from pyhelpers.dirs import delete_dir
            >>> import os

            >>> # Download the PBF data file of 'Rutland' as an example
            >>> subregion_name = 'rutland'
            >>> osm_file_format = ".pbf"
            >>> download_dir = "tests/osm_data"

            >>> dl = Downloader()

            >>> dl.download_data(subregion_name, osm_file_format, download_dir, verbose=True)
            To download data in the format '.osm.pbf' for the following geographic (sub)region(s):
                "Rutland"
              to "./tests/osm_data/rutland/"
            ? [No]|Yes: >? yes
            Downloading "rutland-latest.osm.pbf" 100%|██████████| 1.83M/1.83M | 5.74MB/s ...
                Saving "rutland-latest.osm.pbf" to "./tests/osm_data/rutland/" ... Done.

            >>> path_to_file = dl.data_paths[0]
            >>> os.path.relpath(path_to_file)
            'tests\\osm_data\\rutland\\rutland-latest.osm.pbf'

            >>> # Read the downloaded PBF data
            >>> rutland_pbf = PBF.read_pbf(path_to_file)
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
            >>> pbf_0 = PBF.read_pbf(path_to_file, expand=True)
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
            >>> pbf_1 = PBF.read_pbf(path_to_file, expand=True, parse_geometry=True)
            >>> pbf_1_points = pbf_1['points']
            >>> # Check the difference in 'geometry' column, compared to `pbf_0_points`
            >>> pbf_1_points['geometry'].head()
            0    POINT (-0.5134241 52.6555853)
            1    POINT (-0.5313354 52.6737716)
            2    POINT (-0.7229332 52.5889864)
            3    POINT (-0.7249816 52.6748426)
            4     POINT (-0.7266543 52.669517)
            Name: geometry, dtype: object

            >>> # Set both `expand` and `parse_properties` to be `True`
            >>> pbf_2 = PBF.read_pbf(path_to_file, expand=True, parse_properties=True)
            >>> pbf_2_points = pbf_2['points']
            >>> pbf_2_points['other_tags'].head()
            0                 "odbl"=>"clean"
            1                            None
            2                            None
            3    "traffic_calming"=>"cushion"
            4        "direction"=>"clockwise"
            Name: other_tags, dtype: object

            >>> # Set both `expand` and `parse_other_tags` to be `True`
            >>> pbf_3 = PBF.read_pbf(path_to_file, expand=True, parse_properties=True,
            ...     parse_other_tags=True)
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
            >>> delete_dir(dl.download_dir, verbose=True)
            To delete the directory "./tests/osm_data/" (Not empty)
            ? [No]|Yes: yes
            Deleting "./tests/osm_data/" ... Done.

        .. seealso::

            - Examples for the methods:
              :meth:`GeofabrikReader.read_osm_pbf()<pydriosm.reader.GeofabrikReader.read_osm_pbf>`
              and :meth:`BBBikeReader.read_osm_pbf()<pydriosm.reader.BBBikeReader.read_osm_pbf>`.
        """

        osgeo_ogr, osgeo_gdal = map(_check_dependency, ['osgeo.ogr', 'osgeo.gdal'])

        # Reference: https://gis.stackexchange.com/questions/332327/
        # Stop GDAL printing both warnings and errors to STDERR
        osgeo_gdal.PushErrorHandler('CPLQuietErrorHandler')

        # # Make GDAL raise python exceptions for errors (warnings won't raise an exception)
        # osgeo_gdal.UseExceptions()
        # # osgeo_gdal.DontUseExceptions()

        kwargs.update({'max_tmpfile_size': max_tmpfile_size})
        gdal_configurations(**kwargs)

        with warnings.catch_warnings(action="ignore", category=FutureWarning):
            f = osgeo_ogr.Open(path_to_file)

            # Get a collection of parsed layer data
            collection_of_layer_data = [
                cls.read_layer(
                    layer=f.GetLayerByIndex(i),
                    readable=readable,
                    expand=expand,
                    parse_geometry=parse_geometry,
                    parse_properties=parse_properties,
                    parse_other_tags=parse_other_tags,
                    number_of_chunks=number_of_chunks
                )
                for i in range(f.GetLayerCount())
            ]

        # Make the output in a dictionary form:
        # {Layer1 name: Layer1 data, Layer2 name: Layer2 data, ...}
        data = dict(collections.ChainMap(*reversed(collection_of_layer_data)))

        return data
