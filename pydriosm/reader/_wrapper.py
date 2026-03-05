from pydriosm.errors import MethodNotAvailableError
from pydriosm.reader._base import BaseReader
from pydriosm.reader._bbbike import BBBikeReader
from pydriosm.reader._geofabrik import GeofabrikReader


class Reader(BaseReader):
    """
    A wrapper of :class:`~pydriosm.reader.GeofabrikReader` and
    :class:`~pydriosm.reader.BBBikeReader`.
    """

    #: A dictionary of reader classes.
    SOURCES: dict = {
        "geofabrik": GeofabrikReader,
        "bbbike": BBBikeReader,
    }

    def __init__(self, data_source='geofabrik', data_dir=None, max_tmpfile_size=None, **kwargs):
        # noinspection PyShadowingNames
        """

        :param data_source:
        :type data_source: str

        :ivar reader:
        :vartype reader: BaseReader | GeofabrikReader | BBBikeReader | None
        :ivar data_source:
        :vartype data_source: str

        **Examples**::

            >>> from pydriosm.reader import Reader
            >>> import os
            >>> reader = Reader()
            >>> subregion_name = 'rutland'
            >>> osm_file_format = ".shp"
            >>> data_dir = "tests/osm_data"
            >>> path_to_file = reader.get_file_path(subregion_name, osm_file_format, data_dir)
            >>> os.path.relpath(path_to_file)  # (on Windows)
            'tests\\osm_data\\rutland\\rutland-latest-free.shp.zip'

            >>> reader.set_source('bbbike')
            >>> path_to_file = reader.get_file_path(subregion_name, osm_file_format, data_dir)
            Traceback (most recent call last):
                ...
            pydriosm.errors.InvalidSubregionNameError:
              `subregion_name='rutland'` -> The input of `subregion_name` is not recognizable.
              Check the `.data_source`, or try another one instead.
            >>> subregion_name = 'Birmingham'
            >>> path_to_file = reader.get_file_path(subregion_name, osm_file_format, data_dir)
            >>> os.path.relpath(path_to_file)  # (on Windows)
            'tests\\osm_data\\birmingham\\Birmingham.osm.shp.zip'
        """

        # Ensure base class initialization
        super().__init__(
            data_source=data_source, data_dir=data_dir, max_tmpfile_size=max_tmpfile_size, **kwargs)

        # Predefine attributes to avoid linter warnings
        self.reader = None
        self.data_source = data_source

        self.set_source(
            data_source=data_source, data_dir=data_dir, max_tmpfile_size=max_tmpfile_size, **kwargs)

    def set_source(self, data_source, data_dir=None, max_tmpfile_size=None, **kwargs):
        """
        Specify which source to be used.

        :param data_source: Name of data source.
        :type data_source: str
        :param data_dir: The path to a directory for storing data files.
        :type data_dir: str | None
        :param max_tmpfile_size: maximum size of the temporary file, defaults to ``None``;
            when ``max_tmpfile_size=None``, it defaults to ``5000``
        :type max_tmpfile_size: int | None

        **Examples**::

            >>> from pydriosm.reader import Reader
            >>> reader = Reader()
        """

        try:
            if self.reader is not None:
                var_dict = self.reader.__class__.__annotations__ | self.reader.__dict__
                for var_name in var_dict:
                    delattr(self, var_name)

            self.data_source = data_source.lower()

            self.reader = self.SOURCES[self.data_source](
                data_dir=data_dir, max_tmpfile_size=max_tmpfile_size, **kwargs)

            for var_name in self.reader.__class__.__annotations__ | self.reader.__dict__:
                setattr(self, var_name, self.reader.__getattribute__(var_name))

        except KeyError:
            raise ValueError(f'Unsupported source: "{data_source}".')

    def _raise_unavailable_method_error(self, method_name, raise_error=True):
        if raise_error:
            raise MethodNotAvailableError(method_name, self.reader)

    def get_file_path(self, subregion_name, osm_file_format, data_dir=None, raise_error=True):
        # noinspection PyShadowingNames
        """
        Get the local path to an OSM data file of a geographic (sub)region.

        :param subregion_name: name of a geographic (sub)region (case-insensitive)
            that is available on Geofabrik free download server
        :type subregion_name: str
        :param osm_file_format: file format of the OSM data available on the free download server
        :type osm_file_format: str
        :param data_dir: directory where the data file of the ``subregion_name`` is located/saved;
            if ``None`` (default), the default local directory
        :type data_dir: str | None
        :param raise_error: Whether to raise the provided exception;
            if ``raise_error=True`` (default), the error will be suppressed.
        :type raise_error: bool
        :return: path to PBF (.osm.pbf) file
        :rtype: str | None

        **Examples**::

            >>> from pydriosm.reader import Reader
            >>> from pyhelpers.dirs import delete_dir
            >>> import os
            >>> reader = Reader()
            >>> subregion_name = 'rutland'
            >>> osm_file_format = ".pbf"
            >>> data_dir = "tests/osm_data"
            >>> path_to_file = reader.get_file_path(subregion_name, osm_file_format, data_dir)
            >>> # When "rutland-latest.osm.pbf" is unavailable at the package data directory
            >>> os.path.isfile(path_to_file)
            False
            >>> # Download the PBF data file of Rutland to "./tests/osm_data/"
            >>> reader.downloader.download_data(
            ...     subregion_name, osm_file_format, data_dir, verbose=True)
            Proceed to download data in the format '.osm.pbf' for the following geographic (sub...
              "Rutland"
              to "./tests/osm_data/rutland/"
            ? [No]|Yes: yes
            Downloading "rutland-latest.osm.pbf" 100%|██████████| 1.89M/1.89M | 6.64MB/s ...
              Saving "rutland-latest.osm.pbf" to "./tests/osm_data/rutland/" ... Done.
            >>> # Check again
            >>> path_to_file = reader.get_file_path(subregion_name, osm_file_format, data_dir)
            >>> os.path.isfile(path_to_file)
            True
            >>> os.path.relpath(path_to_file)  # (on Windows)
            'tests\\osm_data\\rutland\\rutland-latest.osm.pbf'
            >>> # Delete the test data directory
            >>> delete_dir(data_dir, verbose=True)
            To delete the directory "./tests/osm_data/" (Not empty)
            ? [No]|Yes: yes
            Deleting "./tests/osm_data/" ... Done.
        """

        method_name = self.get_file_path.__name__

        if hasattr(self.reader, method_name):
            return self.reader.get_file_path(
                subregion_name=subregion_name,
                osm_file_format=osm_file_format,
                data_dir=data_dir
            )

        else:
            self._raise_unavailable_method_error(method_name=method_name, raise_error=raise_error)

    def get_pbf_layer_names(self, subregion_name, data_dir=None, raise_error=True):
        """
        Get indices and names of all layers in the PBF data file of a given (sub)region.

        :param subregion_name: name of a geographic (sub)region (case-insensitive)
            that is available on Geofabrik free download server
        :type subregion_name: str
        :param data_dir:
        :type data_dir:
        :param raise_error: Whether to raise the provided exception;
            if ``raise_error=True`` (default), the error will be suppressed.
        :type raise_error: bool
        :return: indices and names of each layer of the PBF data file
        :rtype: dict

        **Examples**::

            >>> from pydriosm.reader import Reader
            >>> from pyhelpers.dirs import delete_dir
            >>> import os

            >>> reader = Reader()

            >>> # Download the .shp.zip file of Rutland as an example
            >>> subrgn_name = 'london'
            >>> file_format = ".pbf"
            >>> dat_dir = "tests\\osm_data"
            >>> reader.downloader.download_data(subrgn_name, file_format, dat_dir, verbose=True)
            Proceed to download data in the format '.osm.pbf' for the following geographic (sub...
              "Greater London"
              to "./tests/osm_data/greater-london/"
            ? [No]|Yes: yes
            Downloading "greater-london-latest.osm.pbf" 100%|██████████| 123M/123M | 11.4...
              Saving "greater-london-latest.osm.pbf" ...
                  to "./tests/osm_data/greater-london/" ... Done.

            >>> london_pbf_path = reader.data_paths[0]
            >>> os.path.relpath(london_pbf_path)
            'tests\\osm_data\\greater-london\\greater-london-latest.osm.pbf'

            >>> lyr_idx_names = reader.get_pbf_layer_names(london_pbf_path)
            >>> lyr_idx_names
            {0: 'points',
             1: 'lines',
             2: 'multilinestrings',
             3: 'multipolygons',
             4: 'other_relations'}

            >>> # Delete the example data and the test data directory
            >>> delete_dir(dat_dir, verbose=True)
            To delete the directory "./tests/osm_data/" (Not empty)
            ? [No]|Yes: yes
            Deleting "./tests/osm_data/" ... Done.
        """

        method_name = self.get_pbf_layer_names.__name__

        if hasattr(self.reader, method_name):
            return self.reader.get_pbf_layer_names(subregion_name=subregion_name, data_dir=data_dir)

        else:
            self._raise_unavailable_method_error(method_name=method_name, raise_error=raise_error)

    def get_shp_pathname(self, subregion_name, layer_name=None, feature_name=None, data_dir=None,
                         raise_error=True):
        """
        Get path(s) to .shp file(s) for a geographic (sub)region
        (by searching a local data directory).

        :param subregion_name: name of a geographic (sub)region (case-insensitive)
            that is available on Geofabrik free download server
        :type subregion_name: str
        :param layer_name: name of a .shp layer (e.g. ``'railways'``), defaults to ``None``
        :type layer_name: str | None
        :param feature_name: name of a feature (e.g. ``'rail'``);
            if ``None`` (default), all available features included
        :type feature_name: str | None
        :param data_dir: directory where the search is conducted; if ``None`` (default),
            the default directory
        :type data_dir: str | None
        :param raise_error: If ``True``, raise the error if any.
        :type raise_error: bool
        :return: path(s) to .shp file(s)
        :rtype: list

        **Examples**::

            >>> from pydriosm.reader import Reader
            >>> from pyhelpers.dirs import delete_dir
            >>> import os

            >>> reader = Reader()

            >>> subrgn_name = 'london'
            >>> file_format = ".shp"
            >>> dat_dir = "tests\\osm_data"

            >>> # Try to get the shapefiles' pathnames
            >>> london_shp_path = reader.get_shp_pathname(subrgn_name, data_dir=dat_dir)
            >>> london_shp_path  # An empty list if no data is available
            []

            >>> # Download the shapefiles of London
            >>> path_to_london_shp_zip = reader.downloader.download_data(
            ...     subrgn_name, file_format, dat_dir, verbose=True, ret_download_path=True)
            Proceed to download data in the format '.shp.zip' for the following geographic (sub...
              "Greater London"
              to "./tests/osm_data/greater-london/"
            ? [No]|Yes: yes
            Downloading "greater-london-latest-free.shp.zip" 100%|██████████| 196M/196M |...
              Saving "greater-london-latest-free.shp.zip" ...
                  to "./tests/osm_data/greater-london/" ... Done.

            >>> type(path_to_london_shp_zip)
            list
            >>> len(path_to_london_shp_zip)
            1

            >>> # Extract the downloaded .zip file
            >>> reader.SHP.unzip_shp_zip(path_to_london_shp_zip[0], verbose=True)
            Extracting "./tests/osm_data/greater-london/greater-london-latest-free.shp.zip"
                to "./tests/osm_data/greater-london/greater-london-latest-free-shp/" ... Done.

            >>> # Try again to get the shapefiles' pathnames
            >>> london_shp_path = reader.get_shp_pathname(subrgn_name, data_dir=dat_dir)
            >>> len(london_shp_path) > 1
            True

            >>> # Get the file path of 'railways' shapefile
            >>> lyr_name = 'railways'
            >>> railways_shp_path = reader.get_shp_pathname(subrgn_name, lyr_name, data_dir=dat_dir)
            >>> len(railways_shp_path)
            1
            >>> railways_shp_path = railways_shp_path[0]
            >>> os.path.relpath(railways_shp_path)
            'tests\\osm_data\\greater-london\\greater-london-latest-free-shp\\gis_osm_railways_...

            >>> # Get/save shapefile data of features labelled 'rail' only
            >>> feat_name = 'rail'
            >>> railways_shp = reader.SHP.read_layer_shps(
            ...     railways_shp_path, feature_names=feat_name, save_feat_shp=True)
            >>> railways_shp.shape
            (11110, 9)
            >>> railways_shp.head()
                osm_id  code  ...                                        coordinates shape_type
            0    30804  6101  ...  [(0.0048644, 51.6279262), (0.0061979, 51.62926...          3
            3   101511  6101  ...  [(-0.2119027, 51.5241906), (-0.2108059, 51.523...          3
            5   361978  6101  ...  [(-0.0298545, 51.6619398), (-0.0302322, 51.659...          3
            6  2370155  6101  ...  [(-0.3379005, 51.5937776), (-0.3367807, 51.593...          3
            7  2526598  6101  ...  [(-0.1886021, 51.3602632), (-0.1884216, 51.360...          3
            [5 rows x 9 columns]

            >>> # Get the file path to the data of 'rail'
            >>> rail_shp_path = reader.get_shp_pathname(subrgn_name, lyr_name, feat_name, dat_dir)
            >>> len(rail_shp_path)
            1
            >>> rail_shp_path = rail_shp_path[0]
            >>> os.path.relpath(rail_shp_path)
            'tests\\osm_data\\greater-london\\greater-london-latest-free-shp\\gis_osm_railways_...

            >>> # Retrieve the data of 'rail' feature
            >>> railways_rail_shp = reader.SHP.read_layer_shps(rail_shp_path)
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
            To delete the directory "./tests/osm_data/" (Not empty)
            ? [No]|Yes: yes
            Deleting "./tests/osm_data/" ... Done.
        """

        method_name = self.get_shp_pathname.__name__

        if hasattr(self.reader, method_name):
            return self.reader.get_shp_pathname(
                subregion_name=subregion_name,
                layer_name=layer_name,
                feature_name=feature_name,
                data_dir=data_dir,
            )

        else:
            self._raise_unavailable_method_error(method_name=method_name, raise_error=raise_error)

    def read_pbf(self, subregion_name, data_dir=None, readable=False, expand=False,
                 parse_geometry=False, parse_properties=False, parse_other_tags=False,
                 update=False, download=False, pickle_it=False, ret_pickle_path=False,
                 rm_pbf_file=False, chunk_size_limit=50, verbose=False, raise_error=True,
                 **kwargs):
        # noinspection PyShadowingNames
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
            if it is not available at the specified path, defaults to ``False``
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
        :param raise_error: If ``True``, raise the error if any.
        :type raise_error: bool
        :param kwargs: [optional] parameters of the method
            :meth:`PBFReadParse.read_pbf()<pydriosm.reader.PBFReadParse.read_pbf>`
        :return: dictionary of the .osm.pbf data;
            when ``pickle_it=True``, return a tuple of the dictionary and a path to the pickle file
        :rtype: dict | tuple | None

        .. _`shapely.geometry`:
            https://shapely.readthedocs.io/en/latest/manual.html#geometric-objects
        .. _`dict`:
            https://docs.python.org/3/library/stdtypes.html#dict

        .. _pydriosm-reader-GeofabrikReader-read_osm_pbf:

        **Examples**::

            >>> from pydriosm.reader import Reader
            >>> from pyhelpers.dirs import delete_dir
            >>> reader = Reader()
            >>> subregion_name = 'rutland'
            >>> data_dir = "tests/osm_data"
            >>> # If the PBF data of Rutland is not available at the specified data directory,
            >>> # the function can download the latest data by setting `download=True` (default)
            >>> pbf_raw = reader.read_pbf(subregion_name, data_dir=data_dir, verbose=True)
            Downloading "rutland-latest.osm.pbf" 100%|██████████| 1.83M/1.83M | 5.63MB/s ...
                Saving "rutland-latest.osm.pbf" to "./tests/osm_data/rutland/" ... Done.
            Reading "./tests/osm_data/rutland/rutland-latest.osm.pbf" ... Done.
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
            >>> pbf_parsed = reader.read_pbf(subregion_name, data_dir, readable=True, verbose=True)
            Parsing "./tests/osm_data/rutland/rutland-latest.osm.pbf" ... Done.
            >>> pbf_parsed_points = pbf_parsed['points']
            >>> pbf_parsed_points.head()
            0    {'type': 'Feature', 'geometry': {'type': 'Poin...
            1    {'type': 'Feature', 'geometry': {'type': 'Poin...
            2    {'type': 'Feature', 'geometry': {'type': 'Poin...
            3    {'type': 'Feature', 'geometry': {'type': 'Poin...
            4    {'type': 'Feature', 'geometry': {'type': 'Poin...
            Name: points, dtype: object
            >>> # Set `expand=True`, which would force `readable=True`
            >>> pbf_parsed_ = reader.read_pbf(subregion_name, data_dir, expand=True, verbose=True)
            Parsing "./tests/osm_data/rutland/rutland-latest.osm.pbf" ... Done.
            >>> pbf_parsed_points_ = pbf_parsed_['points']
            >>> pbf_parsed_points_.head()
                     id  ...                                         properties
            0    488658  ...  {'osm_id': '488658', 'name': 'Tickencote Inter...
            1  13883868  ...  {'osm_id': '13883868', 'name': None, 'barrier'...
            2  14049101  ...  {'osm_id': '14049101', 'name': None, 'barrier'...
            3  14558402  ...  {'osm_id': '14558402', 'name': None, 'barrier'...
            4  14558409  ...  {'osm_id': '14558409', 'name': None, 'barrier'...
            [5 rows x 3 columns]
            >>> # Set `readable` and `parse_geometry` to be `True`
            >>> pbf_parsed_1 = reader.read_pbf(
            ...     subregion_name, data_dir, readable=True, parse_geometry=True)
            >>> pbf_parsed_1_point = pbf_parsed_1['points'][0]
            >>> pbf_parsed_1_point['geometry']
            'POINT (-0.5313354 52.6737716)'
            >>> pbf_parsed_1_point['properties']['highway']
            'motorway_junction'

            >>> # Set `readable` and `parse_other_tags` to be `True`
            >>> pbf_parsed_2 = reader.read_pbf(
            ...     subregion_name, data_dir, readable=True, parse_other_tags=True)
            >>> pbf_parsed_2_point = pbf_parsed_2['points'][0]
            >>> pbf_parsed_2_point['geometry']
            {'type': 'Point', 'coordinates': [-0.5313354, 52.6737716]}
            >>> pbf_parsed_2_point['properties']['highway']
            'motorway_junction'
            >>> # Set `readable`, `parse_geometry` and `parse_other_tags` to be `True`
            >>> pbf_parsed_3 = reader.read_pbf(
            ...     subregion_name, data_dir, readable=True, parse_geometry=True,
            ...     parse_other_tags=True)
            >>> pbf_parsed_3_point = pbf_parsed_3['points'][0]
            >>> pbf_parsed_3_point['geometry']
            'POINT (-0.5313354 52.6737716)'
            >>> pbf_parsed_3_point['properties']['highway']
            'motorway_junction'
            >>> # Delete the example data and the test data directory
            >>> delete_dir(data_dir, verbose=True)
            To delete the directory "./tests/osm_data/" (Not empty)
            ? [No]|Yes: yes
            Deleting "./tests/osm_data/" ... Done.
        """

        method_name = self.read_pbf.__name__

        if hasattr(self.reader, method_name):
            return self.reader.read_pbf(
                subregion_name=subregion_name,
                data_dir=data_dir,
                readable=readable,
                expand=expand,
                parse_geometry=parse_geometry,
                parse_properties=parse_properties,
                parse_other_tags=parse_other_tags,
                update=update,
                download=download,
                pickle_it=pickle_it,
                ret_pickle_path=ret_pickle_path,
                rm_pbf_file=rm_pbf_file,
                chunk_size_limit=chunk_size_limit,
                verbose=verbose,
                **kwargs
            )

        else:
            self._raise_unavailable_method_error(method_name=method_name, raise_error=raise_error)

    def read_shp(self, subregion_name, layer_names=None, feature_names=None, data_dir=None,
                 update=False, download=False, pickle_it=False, ret_pickle_path=False,
                 rm_extracts=False, rm_shp_zip=False, verbose=False, raise_error=True, **kwargs):
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
            before starting to download a file, defaults to ``False``
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
        :param raise_error: If ``True``, raise the error if any.
        :type raise_error: bool
        :return: dictionary of the shapefile data, with keys and values being layer names
            and tabular data (in the format of `geopandas.GeoDataFrame`_), respectively;
            when ``pickle_it=True``, return a tuple of the dictionary and a path to the pickle file
        :rtype: dict | tuple | None

        .. _`geopandas.GeoDataFrame`: https://geopandas.org/reference.html#geodataframe

        **Examples**::

            >>> from pydriosm.reader import Reader
            >>> from pyhelpers.dirs import delete_dir
            >>> import os

            >>> reader = Reader(data_source='bbbike')

            >>> subrgn_name = 'Birmingham'
            >>> dat_dir = "tests/osm_data"

            >>> bham_shp = reader.read_shp(
            ...     subregion_name=subrgn_name, data_dir=dat_dir, download=False, verbose=True)
            The .shp.zip file for "Birmingham" is not found.

            >>> # Set `download=True`
            >>> bham_shp = reader.read_shp(
            ...     subregion_name=subrgn_name, data_dir=dat_dir, download=True, verbose=True)
            Downloading "Birmingham.osm.shp.zip" 100%|██████████| 79.0M/79.0M | 28.5MB/s ...
              Saving "Birmingham.osm.shp.zip" to "./tests/osm_data/birmingham/" ... Done.
            Extracting "./tests/osm_data/birmingham/Birmingham.osm.shp.zip"
              to "./tests/osm_data/birmingham/" ... Done.
            Reading the shapefile(s) at "./tests/osm_data/birmingham/Birmingham-shp/shape/" ......
            >>> type(bham_shp)
            dict
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
            >>> bham_railways_shp.shape
            (3994, 5)
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
            >>> bham_roads_shp = reader.read_shp(
            ...     subregion_name=subrgn_name, layer_names=lyr_name, data_dir=dat_dir,
            ...     rm_extracts=True, verbose=True)
            Reading "./tests/osm_data/birmingham/Birmingham-shp/shape/roads.shp" ... Done.
            Deleting the extracts "./tests/osm_data/birmingham/Birmingham-shp/" ... Done.
            >>> type(bham_roads_shp)
            dict
            >>> list(bham_roads_shp.keys())
            ['roads']
            >>> bham_roads_shp[lyr_name].shape
            (170370, 9)
            >>> bham_roads_shp[lyr_name].head()
               osm_id  ... shape_type
            0      37  ...          3
            1      38  ...          3
            2      41  ...          3
            3      42  ...          3
            4      45  ...          3
            [5 rows x 9 columns]

            >>> # Read data of multiple layers and features from the original .shp.zip file
            >>> # (and delete all extracts)
            >>> lyr_names = ['railways', 'waterways']
            >>> feat_names = ['rail', 'canal']
            >>> bham_rw_rc_shp = reader.read_shp(
            ...     subregion_name=subrgn_name, layer_names=lyr_names, feature_names=feat_names,
            ...     data_dir=dat_dir, rm_extracts=True, rm_shp_zip=True, verbose=True)
            Extracting the following layer(s):
              'railways'
              'waterways'
                from "./tests/osm_data/birmingham/Birmingham.osm.shp.zip" ...
                  to "./tests/osm_data/birmingham/" ... Done.
            Reading the shapefile(s) at "./tests/osm_data/birmingham/Birmingham-shp/shape/" ......
            Deleting the extracts "./tests/osm_data/birmingham/Birmingham-shp/" ... Done.
            Deleting "tests/osm_data/birmingham/Birmingham.osm.shp.zip" ... Done.
            >>> type(bham_rw_rc_shp)
            dict
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
                 type                          name
            2   canal  Birmingham and Fazeley Canal
            9   canal  Birmingham and Fazeley Canal
            10  canal      Icknield Port Loop Canal
            11  canal     Oozells Street Loop Canal
            12  canal  Worcester & Birmingham Canal

            >>> # Delete the example data and the test data directory
            >>> delete_dir(dat_dir, verbose=True)
            To delete the directory "./tests/osm_data/" (Not empty)
            ? [No]|Yes: yes
            Deleting "./tests/osm_data/" ... Done.
        """

        method_name = self.read_shp.__name__

        if hasattr(self.reader, method_name):
            return self.reader.read_shp(
                subregion_name=subregion_name,
                layer_names=layer_names,
                feature_names=feature_names,
                data_dir=data_dir,
                update=update,
                download=download,
                pickle_it=pickle_it,
                ret_pickle_path=ret_pickle_path,
                rm_extracts=rm_extracts,
                rm_shp_zip=rm_shp_zip,
                verbose=verbose,
                **kwargs
            )

        else:
            self._raise_unavailable_method_error(method_name=method_name, raise_error=raise_error)

    def merge_layers(self, shp_zip_pathnames, layer_name, engine='pyshp', rm_zip_extracts=True,
                     output_dir=None, rm_shp_temp=True, ret_shp_pathname=False, verbose=False,
                     raise_error=False):
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
        :type output_dir: str | None
        :param ret_shp_pathname: whether to return the pathname of the merged .shp file,
            defaults to ``False``
        :type ret_shp_pathname: bool
        :param verbose: whether to print relevant information in console, defaults to ``False``
        :type verbose: bool | int
        :param raise_error: Whether to raise the provided exception;
            if ``raise_error=False`` (default), the error will be suppressed.
        :type raise_error: bool
        :return: the path to the merged file when ``ret_merged_shp_path=True``
        :rtype: list

        .. _`geopandas.GeoDataFrame.to_file()`:
            https://geopandas.org/reference.html#geopandas.GeoDataFrame.to_file
        .. _`shapefile.Writer()`:
            https://github.com/GeospatialPython/pyshp#writing-shapefiles

        .. note::

            - This function does not create projection (.prj) for the merged map.
              See also
              [`MMS-1 <https://code.google.com/archive/p/pyshp/wikis/CreatePRJfiles.wiki>`_].
            - For valid ``layer_name``, check the function
              :func:`~pydriosm.utils.valid_shapefile_layer_names`.

        .. _pydriosm-reader-SHPReadParse-merge_layer_shps:

        **Examples**::

            >>> # To merge 'railways' layers of Greater Manchester and West Yorkshire"

            >>> from pydriosm.reader import Reader
            >>> from pyhelpers.dirs import delete_dir
            >>> import os

            >>> reader = Reader()

            >>> # Download the .shp.zip file of Manchester and West Yorkshire
            >>> subrgn_names = ['Greater Manchester', 'West Yorkshire']
            >>> file_fmt = ".shp"
            >>> data_dir = "tests\\osm_data"

            >>> reader.downloader.download_data(subrgn_names, file_fmt, data_dir, verbose=True)
            Proceed to download data in the format '.shp.zip' for the following geographic (sub...
              "Greater Manchester"
              "West Yorkshire"
              to "./tests/osm_data/"
            ? [No]|Yes: yes
            Downloading "greater-manchester-latest-free.shp.zip" 100%|██████████| 87.5M/8...
              Saving "greater-manchester-latest-free.shp.zip" ...
                to "./tests/osm_data/greater-manchester/" ... Done.
            Downloading "west-yorkshire-latest-free.shp.zip" 100%|██████████| 87.3M/87.3M...
              Saving "west-yorkshire-latest-free.shp.zip" ...
                to "./tests/osm_data/west-yorkshire/" ... Done.

            >>> os.path.relpath(reader.downloader.download_dir)
            'tests\\osm_data'
            >>> len(reader.data_paths)
            2

            >>> # Merge the layers of 'railways' of the two subregions
            >>> merged_shp_path = reader.merge_layers(
            ...     reader.data_paths, layer_name='railways', verbose=True, ret_shp_pathname=True)
            Merging the following shapefiles:
              "greater-manchester_gis_osm_railways_free_1.shp"
              "west-yorkshire_gis_osm_railways_free_1.shp"
                In progress ... Done.
              Find the merged shapefile at "tests/osm_data/gre_man-wes_yor-railways".

            >>> # Check the pathname of the merged shapefile
            >>> type(merged_shp_path)
            list
            >>> len(merged_shp_path)
            1
            >>> os.path.relpath(merged_shp_path[0])
            'tests\\osm_data\\gre_man-wes_yor-railways\\linestring.shp'

            >>> # Read the merged .shp file
            >>> merged_shp_data = reader.SHP.read_shp(merged_shp_path[0], emulate_gpd=True)
            >>> merged_shp_data.head()
                osm_id  code  ... tunnel                                           geometry
            0   928999  6101  ...      F  LINESTRING (-2.2844621 53.4802635, -2.2851997 ...
            1   929904  6101  ...      F  LINESTRING (-2.2917977 53.4619559, -2.2924877 ...
            2   929905  6102  ...      F  LINESTRING (-2.2794048 53.4605819, -2.2799722 ...
            3  3663332  6102  ...      F  LINESTRING (-2.2382139 53.4817985, -2.2381708 ...
            4  3996086  6101  ...      F  LINESTRING (-2.6003053 53.4604346, -2.6005261 ...
            [5 rows x 8 columns]

            >>> # Delete the test data directory
            >>> delete_dir(reader.downloader.download_dir, verbose=True)
            To delete the directory "./tests/osm_data/" (Not empty)
            ? [No]|Yes: yes
            Deleting "./tests/osm_data/" ... Done.

        .. seealso::

            - Examples for the method
              :meth:`GeofabrikReader.merge_subregion_layer_shp()
              <pydriosm.reader.GeofabrikReader.merge_subregion_layer_shp>`.
        """

        method_name = self.merge_layers.__name__

        if hasattr(self.reader, method_name):
            return self.SHP.merge_layers(
                shp_zip_pathnames=shp_zip_pathnames,
                layer_name=layer_name,
                engine=engine,
                rm_zip_extracts=rm_zip_extracts,
                output_dir=output_dir,
                rm_shp_temp=rm_shp_temp,
                verbose=verbose,
                ret_shp_pathname=ret_shp_pathname,
                raise_error=raise_error
            )

        else:
            self._raise_unavailable_method_error(method_name=method_name, raise_error=raise_error)

    def read_csv_xz(self, subregion_name, data_dir=None, download=False, verbose=False,
                    raise_error=True, **kwargs):
        # noinspection PyShadowingNames
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
        :param raise_error: Whether to raise the provided exception;
            if ``raise_error=False`` (default), the error will be suppressed.
        :type raise_error: bool
        :return: tabular data of the .csv.xz file
        :rtype: pandas.DataFrame | None

        .. _pydriosm-BBBikeReader-read_csv_xz:

        **Examples**::

            >>> from pydriosm.reader import Reader
            >>> from pyhelpers.dirs import cd, delete_dir
            >>> reader = Reader()
            >>> subregion_name = 'Leeds'
            >>> data_dir = "tests/osm_data"
            >>> leeds_csv_xz = reader.read_csv_xz(subregion_name, data_dir, verbose=True)
            The requisite data file "./tests/osm_data/leeds/Leeds.osm.csv.xz" does not exist.
            >>> leeds_csv_xz = reader.read_csv_xz(
            ...     subregion_name, data_dir=data_dir, verbose=True, download=True)
            Downloading "Leeds.osm.csv.xz" 100%|██████████| 4.08M/4.08M | 17.5MB/s | ETA:...
              Saving "Leeds.osm.csv.xz" to "./tests/osm_data/leeds/" ... Done.
            Parsing the data ... Done.
            >>> leeds_csv_xz.head()
               type      id feature  note
            0  node  154915    None  None
            1  node  154916    None  None
            2  node  154919    None  None
            3  node  154921    None  None
            4  node  154922    None  None
            >>> delete_dir(data_dir, verbose=True)  # Delete the downloaded .csv.xz data file
            To delete the directory "./tests/osm_data/" (Not empty)
            ? [No]|Yes: yes
            Deleting "./tests/osm_data/" ... Done.
        """

        method_name = self.read_csv_xz.__name__

        if hasattr(self.reader, method_name):
            return self.reader.read_csv_xz(
                subregion_name=subregion_name,
                data_dir=data_dir,
                download=download,
                verbose=verbose,
                **kwargs
            )

        else:
            self._raise_unavailable_method_error(method_name=method_name, raise_error=raise_error)

    def read_geojson_xz(self, subregion_name, data_dir=None, parse_geometry=False, download=False,
                        verbose=False, raise_error=True, **kwargs):
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
        :param raise_error: Whether to raise the provided exception;
            if ``raise_error=False`` (default), the error will be suppressed.
        :type raise_error: bool
        :return: tabular data of the .csv.xz file
        :rtype: pandas.DataFrame | None

        .. _pydriosm-BBBikeReader-read_geojson_xz:

        **Examples**::

            >>> from pydriosm.reader import Reader
            >>> from pyhelpers.dirs import cd, delete_dir
            >>> import os

            >>> reader = Reader()

            >>> subrgn_name = 'Leeds'
            >>> dat_dir = "tests\\osm_data"

            >>> leeds_geoj = reader.read_geojson_xz(subrgn_name, dat_dir, verbose=True)
            The requisite data file "./tests/osm_data/leeds/Leeds.osm.geojson.xz" does not exist.

            >>> # Set `try_download=True`
            >>> leeds_geoj = reader.read_geojson_xz(
            ...     subrgn_name, dat_dir, verbose=True, download=True)
            Downloading "Leeds.osm.geojson.xz" 100%|██████████| 60.4M/60.4M | 20.7MB/s | ...
              Saving "Leeds.osm.geojson.xz" to "./tests/osm_data/leeds/" ... Done.
            Parsing the data ... Done.
            >>> leeds_geoj.head()
                                            geometry                                    properties
            0  {'type': 'Point', 'coordinates': [...  {'highway': 'motorway_junction', 'name': ...
            1  {'type': 'Point', 'coordinates': [...  {'highway': 'motorway_junction', 'name': ...
            2  {'type': 'Point', 'coordinates': [...  {'highway': 'motorway_junction', 'name': ...
            3  {'type': 'Point', 'coordinates': [...  {'highway': 'motorway_junction', 'name': ...
            4  {'type': 'Point', 'coordinates': [...  {'highway': 'motorway_junction', 'name': ...

            >>> # Set `parse_geometry` to be True
            >>> leeds_geoj_ = reader.read_geojson_xz(
            ...     subrgn_name, dat_dir, parse_geometry=True, verbose=True)
            Parsing "./tests/osm_data/leeds/Leeds.osm.geojson.xz" ... Done.
            >>> leeds_geoj_['geometry'].head()
            0    POINT (-1.5560511 53.6879848)
            1       POINT (-1.34293 53.844618)
            2     POINT (-1.517335 53.7499667)
            3     POINT (-1.514175 53.7418444)
            4     POINT (-1.516511 53.7256632)
            Name: geometry, dtype: object

            >>> # Delete the download directory
            >>> delete_dir(dat_dir, verbose=True)
            To delete the directory "./tests/osm_data/" (Not empty)
            ? [No]|Yes: yes
            Deleting "./tests/osm_data/" ... Done.
        """

        method_name = self.read_geojson_xz.__name__

        if hasattr(self.reader, method_name):
            return self.reader.read_geojson_xz(
                subregion_name=subregion_name,
                data_dir=data_dir,
                parse_geometry=parse_geometry,
                download=download,
                verbose=verbose,
                **kwargs
            )

        else:
            self._raise_unavailable_method_error(method_name=method_name, raise_error=raise_error)
