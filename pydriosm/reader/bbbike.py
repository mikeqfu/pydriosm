"""
Read OpenStreetMap data extracts available from BBBike free download server.
"""

import collections

from pydriosm.downloader import BBBikeDownloader
from pydriosm.reader._reader import _Reader


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

    def __init__(self, data_dir=None, max_tmpfile_size=None):
        """
        :param data_dir: (a path or a name of) a directory where a data file is;
            if ``None`` (default), a folder ``osm_bbbike`` under the current working directory
        :type data_dir: str | None
        :param max_tmpfile_size: defaults to ``None``,
            see also :func:`gdal_configurations<pydriosm.settings.gdal_configurations>`
        :type max_tmpfile_size: int | None

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
            downloader=BBBikeDownloader, data_dir=data_dir, max_tmpfile_size=max_tmpfile_size)

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
        :type data_dir: str | None
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
        :type chunk_size_limit: int | None
        :param verbose: whether to print relevant information in console as the function runs,
            defaults to ``False``
        :type verbose: bool | int
        :param kwargs: [optional] parameters of the method
            :meth:`_Reader.read_osm_pbf()<pydriosm.reader._Reader.read_osm_pbf>`
        :return: dictionary of the .osm.pbf data;
            when ``pickle_it=True``, return a tuple of the dictionary and a path to the pickle file
        :rtype: dict | tuple | None

        .. _`shapely.geometry`:
            https://shapely.readthedocs.io/en/latest/manual.html#geometric-objects
        .. _`dict`:
            https://docs.python.org/3/library/stdtypes.html#dict

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
        :type layer_names: str | list | None
        :param feature_names: name of a feature, e.g. 'rail', or names of multiple features;
            if ``None`` (default), all available features
        :type feature_names: str | list | None
        :param data_dir: directory where the .shp.zip data file is located/saved;
            if ``None``, the default directory
        :type data_dir: str | None
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
        :type verbose: bool | int
        :return: dictionary of the shapefile data, with keys and values being layer names
            and tabular data (in the format of `geopandas.GeoDataFrame`_), respectively;
            when ``pickle_it=True``, return a tuple of the dictionary and a path to the pickle file
        :rtype: dict | collections.OrderedDict | tuple | None

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
        :type data_dir: str | None
        :param download: whether to try to download the requisite data file if it does not exist,
            defaults to ``True``
        :type download: bool
        :param verbose: whether to print relevant information in console as the function runs,
            defaults to ``False``
        :type verbose: bool | int
        :return: tabular data of the .csv.xz file
        :rtype: pandas.DataFrame | None

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
        :type data_dir: str | None
        :param parse_geometry: whether to represent coordinates in a format of a geometric object,
            defaults to ``False``
        :type parse_geometry: bool
        :param download: whether to try to download the requisite data file if it does not exist,
            defaults to ``True``
        :type download: bool
        :param verbose: whether to print relevant information in console as the function runs,
            defaults to ``False``
        :type verbose: bool | int
        :return: tabular data of the .csv.xz file
        :rtype: pandas.DataFrame | None

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
