"""
`PostgreSQL <https://www.postgresql.org/>`_-specific implementation for OpenStreetMap handling.
"""

import ast
import copy
import os

import numpy as np
import pandas as pd
import sqlalchemy
from pyhelpers._cache import _print_failure_message
from pyhelpers.ops import confirmed
from pyhelpers.text import find_similar_str

from pydriosm.ios._pbf_importer import ImportPBF
from pydriosm.ios.utils import validate_schema_names
from pydriosm.reader import PBF, SHP
from pydriosm.utils import remove_osm_file


class PostgresOSM(ImportPBF):
    """
    Implement storage I/O of `OpenStreetMap <https://www.openstreetmap.org/>`_ data
    with `PostgreSQL`_.

    .. _`PostgreSQL`: https://www.postgresql.org/
    """

    def __init__(self, host=None, port=None, username=None, password=None, database_name=None,
                 data_source='Geofabrik', max_tmpfile_size=None, data_dir=None, **kwargs):
        """
        :param host: host name/address of a PostgreSQL server,
            e.g. ``'localhost'`` or ``'127.0.0.1'`` (default by installation of PostgreSQL);
            when ``host=None`` (default), it is initialized as ``'localhost'``
        :type host: str | None
        :param port: listening port used by PostgreSQL; when ``port=None`` (default),
            it is initialized as ``5432`` (default by installation of PostgreSQL)
        :type port: int | None
        :param username: username of a PostgreSQL server; when ``username=None`` (default),
            it is initialized as ``'postgres'`` (default by installation of PostgreSQL)
        :type username: str | None
        :param password: user password; when ``password=None`` (default),
            it is required to mannually type in the correct password to connect the PostgreSQL server
        :type password: str | int | None
        :param database_name: name of a database; when ``database=None`` (default),
            it is initialized as ``'postgres'`` (default by installation of PostgreSQL)
        :type database_name: str | None
        :param confirm_db_creation: whether to prompt a confirmation before creating a new database
            (if the specified database does not exist), defaults to ``False``
        :param data_source: name of data source, defaults to ``'Geofabrik'``;
            options include ``{'Geofabrik', 'BBBike'}``
        :type data_source: str
        :param max_tmpfile_size: defaults to ``None``,
            see also the function `pyhelpers.settings.gdal_configurations()`_
        :type max_tmpfile_size: int | None
        :param data_dir: directory where the data file is located/saved, defaults to ``None``;
            when ``data_dir=None``, it should be the same as the directory specified by
            the corresponding
            :attr:`~pydriosm.ios.PostgresOSM.downloader`/:attr:`~pydriosm.ios.PostgresOSM.reader`
        :type data_dir: str | None
        :param kwargs: [optional] parameters of the class `pyhelpers.sql.PostgreSQL`_

        :ivar str data_source: name of data sources, options include ``{'Geofabrik', 'BBBike'}``

        .. _`pyhelpers.settings.gdal_configurations()`:
            https://pyhelpers.readthedocs.io/en/latest/_generated/
            pyhelpers.settings.gdal_configurations.html
        .. _`pyhelpers.sql.PostgreSQL`:
            https://pyhelpers.readthedocs.io/en/latest/_generated/pyhelpers.sql.PostgreSQL.html

        **Examples**::

            >>> from pydriosm.ios import PostgresOSM

            >>> osmdb = PostgresOSM(database_name='osmdb_test', verbose=True)
            Password (postgres@localhost:5432): ***
            Creating a database: "osmdb_test" ... Done.
            Connecting postgres:***@localhost:5432/osmdb_test ... Successfully.

            >>> osmdb.data_source
            'Geofabrik'
            >>> type(osmdb.downloader)
            pydriosm.downloader._wrapper.Downloader
            >>> type(osmdb.reader)
            pydriosm.reader._wrapper.Reader

            >>> # Change the data source
            >>> osmdb.data_source = 'BBBike'
            >>> type(osmdb.downloader)
            pydriosm.downloader._wrapper.Downloader
            >>> type(osmdb.reader)
            pydriosm.reader._wrapper.Reader

            >>> # Delete the database 'osmdb_test'
            >>> osmdb.drop_database(verbose=True)
            To drop the database "osmdb_test" from postgres:***@localhost:5432
            ? [No]|Yes: yes
            Dropping "osmdb_test" ... Done.
        """

        # valid_source_names = set(self.DATA_SOURCES).union({s.lower() for s in self.DATA_SOURCES})
        # assert data_source in valid_source_names, \
        #     f"`data_source` must be one of {valid_source_names}."
        self.data_source = find_similar_str(data_source, self.DATA_SOURCES)

        super().__init__(
            host=host,
            port=port,
            username=username,
            password=password,
            database_name=database_name,
            **kwargs
        )

        self.data_dir = data_dir
        setattr(self, 'data_dir', self.downloader.download_dir)

        self.max_tmpfile_size = max_tmpfile_size
        setattr(self, 'max_tmpfile_size', self.reader.max_tmpfile_size)

    def import_osm_pbf(self, subregion_names, data_dir=None, update_osm_pbf=False,
                       if_exists='fail', chunk_size_limit=50, expand=False,
                       parse_geometry=False, parse_properties=False, parse_other_tags=False,
                       pickle_pbf_file=False, rm_pbf_file=False, confirmation_required=True,
                       verbose=False, **kwargs):
        """
        Import data of geographic (sub)region(s) that do not have (sub-)subregions into a database.

        :param subregion_names: name(s) of geographic (sub)region(s)
        :type subregion_names: str | list | None
        :param data_dir: directory where the PBF data file is located/saved;
            if ``None`` (default), the default directory
        :type data_dir: str | None
        :param update_osm_pbf: whether to update .osm.pbf data file (if available),
            defaults to ``False``
        :type update_osm_pbf: bool
        :param if_exists: if the table already exists, defaults to ``'fail'``;
            valid options include ``{'replace', 'append', 'fail'}``
        :type if_exists: str
        :param chunk_size_limit: threshold (in MB) that triggers the use of chunk parser,
            defaults to ``50``;
            if the size of the .osm.pbf file (in MB) is greater than ``chunk_size_limit``,
            it will be parsed in a chunk-wise way
        :type chunk_size_limit: int
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
        :param pickle_pbf_file: whether to save the .pbf data as a .pickle file,
            defaults to ``False``
        :type pickle_pbf_file: bool
        :param rm_pbf_file: whether to delete the downloaded .osm.pbf file, defaults to ``False``
        :type rm_pbf_file: bool
        :param confirmation_required: whether to ask for confirmation to proceed,
            defaults to ``True``
        :type confirmation_required: bool
        :param verbose: whether to print relevant information in console, defaults to ``False``
        :type verbose: bool | int
        :param kwargs: [optional] parameters of the method
            :meth:`~pydriosm.ios.PostgresOSM._import_subregion_osm_pbf` or
            :meth:`~pydriosm.ios.PostgresOSM._import_subregion_osm_pbf_chunk_wisely`

        .. _`shapely.geometry`:
            https://shapely.readthedocs.io/en/latest/manual.html#geometric-objects
        .. _`dict`:
            https://docs.python.org/3/library/stdtypes.html#dict

        **Examples**::

            >>> from pydriosm.ios import PostgresOSM
            >>> from pyhelpers.dirs import cd, delete_dir
            >>> from pyhelpers.store import load_pickle
            >>> osmdb = PostgresOSM(database_name='osmdb_test', verbose=True)
            Password (postgres@localhost:5432): ***
            Creating a database: "osmdb_test" ... Done.
            Connecting postgres:***@localhost:5432/osmdb_test ... Successfully.

        *Example 1* - Import PBF data of Rutland::

            >>> subrgn_name = 'Rutland'  # name of a subregion
            >>> dat_dir = "tests/osm_data"  # name of a data directory where the subregion data is
            >>> osmdb.import_osm_pbf(subrgn_name, data_dir=dat_dir, verbose=True)
            Proceed to import .osm.pbf data of the following geographic (sub)region(s):
                "Rutland"
              into postgres:***@localhost:5432/osmdb_test
            ? [No]|Yes: yes
            Downloading "rutland-latest.osm.pbf" 100%|██████████| 1.89M/1.89M | 6.46MB/s ...
              Saving "rutland-latest.osm.pbf" to "./tests/osm_data/rutland/" ... Done.
            Reading "tests/osm_data/rutland/rutland-latest.osm.pbf" ... Done.
            Importing the data into the table "Rutland" ...
                "points" ... Done. (6420 features)
                "lines" ... Done. (10958 features)
                "multilinestrings" ... Done. (71 features)
                "multipolygons" ... Done. (9194 features)
                "other_relations" ... Done. (33 features)

        *Example 2* - Import PBF data of Leeds and London::

            >>> # Change the data source
            >>> osmdb.data_source = 'BBBike'
            >>> subrgn_names = ['Leeds', 'London']
            >>> # Note this may take a few minutes (or longer)
            >>> osmdb.import_osm_pbf(
            ...     subregion_names=subrgn_names, data_dir=dat_dir, expand=True,
            ...     parse_geometry=True, parse_properties=True, parse_other_tags=True,
            ...     pickle_pbf_file=True, rm_pbf_file=True, verbose=True)
            Proceed to import .osm.pbf data of the following geographic (sub)region(s):
                "Leeds"
                "London"
              into postgres:***@localhost:5432/osmdb_test
            ? [No]|Yes: >? yes
            Downloading "Leeds.osm.pbf" 100%|██████████| 38.1M/38.1M | 7.73MB/s | ETA: 00:00
              Saving "Leeds.osm.pbf" to "./tests/osm_data/leeds/" ... Done.
            Reading "tests/osm_data/leeds/Leeds.osm.pbf" ... Done.
            Importing the data into the table "Leeds" ...
                "points" ... Done. (102238 features)
                "lines" ... Done. (183218 features)
                "multilinestrings" ... Done. (442 features)
                "multipolygons" ... Done. (481516 features)
                "other_relations" ... Done. (7185 features)
            Saving "Leeds-pbf.pickle" to "./tests/osm_data/leeds/" ... Done.
            Deleting "tests/osm_data/leeds/Leeds.osm.pbf" ... Done.
            Downloading "London.osm.pbf" 100%|██████████| 188M/188M | 18.4MB/s | ETA: 00:00
              Saving "London.osm.pbf" to "./tests/osm_data/london/" ... Done.
            Importing the data of "London" chunk-wisely
              into postgres:***@localhost:5432/osmdb_test ...
                "points" ... Done. (972803 features)
                "lines" ... Done. (1053607 features)
                "multilinestrings" ... Done. (1017 features)
                "multipolygons" ... Done. (1976 features)
                "other_relations" ... Done. (22590 features)
            Saving "London-pbf.pickle" to "./tests/osm_data/london/" ... Done.
            Deleting "tests/osm_data/london/London.osm.pbf" ... Done.

            >>> # As `pickle_pbf_file=True`, the parsed PBF data have been saved as pickle files

            >>> # Data of Leeds
            >>> leeds_pbf = load_pickle(cd(dat_dir, "leeds", "Leeds-pbf.pickle"))
            >>> type(leeds_pbf)
            dict
            >>> list(leeds_pbf.keys())
            ['points', 'lines', 'multilinestrings', 'multipolygons', 'other_relations']
            >>> # Data of the 'points' layer of Leeds
            >>> leeds_pbf_points = leeds_pbf['points']
            >>> leeds_pbf_points.head()
                   id                       geometry  ... man_made             other_tags
            0  154941  POINT (-1.5560511 53.6879848)  ...     None  {'name:signed': 'no'}
            1  154962     POINT (-1.34293 53.844618)  ...     None  {'name:signed': 'no'}
            2  155014   POINT (-1.517335 53.7499667)  ...     None  {'name:signed': 'no'}
            3  155023   POINT (-1.514175 53.7418444)  ...     None  {'name:signed': 'no'}
            4  155035   POINT (-1.516511 53.7256632)  ...     None  {'name:signed': 'no'}
            [5 rows x 11 columns]

            >>> # Data of London
            >>> london_pbf = load_pickle(cd(dat_dir, "london", "London-pbf.pickle"))
            >>> type(london_pbf)
            dict
            >>> list(london_pbf.keys())
            ['points', 'lines', 'multilinestrings', 'multipolygons', 'other_relations']
            >>> # Data of the 'points' layer of London
            >>> london_pbf_points = london_pbf['points']
            >>> london_pbf_points.head()
                  id  ...                                         other_tags
            0  99878  ...  {'access': 'permissive', 'bicycle': 'no', 'mot...
            1  99880  ...  {'crossing': 'unmarked', 'crossing:island': 'n...
            2  99884  ...                        {'amenity': 'waste_basket'}
            3  99918  ...                         {'emergency': 'life_ring'}
            4  99939  ...           {'traffic_signals:direction': 'forward'}
            [5 rows x 11 columns]

        Delete the test database and downloaded data files::

            >>> # Delete the database 'osmdb_test'
            >>> osmdb.drop_database(verbose=True)
            Proceed to drop the database "osmdb_test" from postgres:***@localhost:5432
            ? [No]|Yes: yes
            Dropping "osmdb_test" ... Done.

            >>> # Delete the downloaded data files
            >>> delete_dir(dat_dir, verbose=True)
            To delete the directory "./tests/osm_data/" (Not empty)
            ? [No]|Yes: yes
            Deleting "./tests/osm_data/" ... Done.
        """

        osm_file_format = ".osm.pbf"

        if subregion_names is None:
            subregion_names_ = self.downloader.get_valid_subregion_names()
            confirm_msg = \
                f"Proceed to import all {osm_file_format} data available on {self.data_source} " \
                f"  into {self.address}\n?"

        else:
            subregion_names_ = [
                self.downloader.validate_subregion_name(x)
                for x in self.reader.validate_dtype(subregion_names)]

            if self.data_source == 'Geofabrik':
                subregion_names_ = self.downloader.get_subregions(*subregion_names_)

            subrgn_names_msg = '"\n\t"'.join(subregion_names_)
            confirm_msg = \
                (f"Proceed to import {osm_file_format} data of the following geographic "
                 f"(sub)region(s):\n"
                 f"\t\"{subrgn_names_msg}\"\n  into {self.address}\n?")

        if confirmed(confirm_msg, confirmation_required=confirmation_required):
            err_subregion_names = []

            for subregion_name_ in subregion_names_:
                path_to_osm_pbf_ = self.downloader.download_data(
                    subregion_names=subregion_name_, osm_file_formats=osm_file_format,
                    download_dir=data_dir, update=update_osm_pbf, confirmation_required=False,
                    verbose=verbose, ret_download_path=True)
                path_to_osm_pbf = path_to_osm_pbf_[0]

                try:
                    read_pbf_args = {
                        'expand': expand,
                        'parse_geometry': parse_geometry,
                        'parse_properties': parse_properties,
                        'parse_other_tags': parse_other_tags,
                    }
                    import_args = {
                        'subregion_name_': subregion_name_,
                        'osm_file_format': osm_file_format,
                        'path_to_osm_pbf': path_to_osm_pbf,
                        'chunk_size_limit': chunk_size_limit,
                        'pickle_pbf_file': pickle_pbf_file,
                        'verbose': verbose,
                        # 'if_exists': if_exists,
                    }
                    import_args.update(read_pbf_args)

                    file_size_in_mb = round(os.path.getsize(path_to_osm_pbf) / (1024 ** 2), 1)
                    if file_size_in_mb <= chunk_size_limit:
                        import_args.update({'if_exists': if_exists})
                        self._import_pbf(**import_args, **kwargs)
                    else:
                        import_args.update({'if_exists': 'append'})
                        self._import_pbf_chunk_wisely(**import_args, **kwargs)

                    if rm_pbf_file:
                        remove_osm_file(path_to_file=path_to_osm_pbf, verbose=verbose)

                except Exception as e:
                    print(e)
                    err_subregion_names.append(subregion_name_)

            if len(err_subregion_names) > 0:
                print("Errors occurred when parsing data of the following subregion(s):", end="\n\t")
                print('"' + '"\n\t"'.join(err_subregion_names) + '"')

    def decode_pbf_layer(self, layer_dat, decode_geojson=True):
        """
        Process raw data of a PBF layer retrieved from database.

        .. seealso::

            - Examples of the method :meth:`~pydriosm.ios.PostgresOSM.fetch_osm_data`.
        """

        # if engine:
        #     valid_methods = {'ujson', 'orjson', 'rapidjson', 'json'}
        #     assert engine in valid_methods, f"`method` must be on one of {valid_methods}."
        #     json_mod_name = engine
        # else:
        #     json_mod_name = 'json'
        # json_mod = _check_dependency(name=json_mod_name)

        layer_dat_ = layer_dat.replace({np.nan: None})

        if decode_geojson:
            if layer_dat_.shape[1] == 1:
                col_name = layer_dat_.columns[0]
                temp = layer_dat_[col_name]

                if temp.map(type).eq(str).any():
                    temp = temp.map(ast.literal_eval)

                layer_dat_ = temp.to_frame(name=col_name)

            else:
                possible_col_names = {
                    'coordinates',
                    'geometries',
                    'geometry',
                    'other_tags',
                    'properties',
                }
                self._decode_layer_dat(dat=layer_dat_, possible_col_names=possible_col_names)

        return layer_dat_

    def postprocess_pdf_layer(self, layer_dat, decode_geojson=True, sort_by='id'):
        """
        Post-process the data of a specific layer.
        """

        if isinstance(layer_dat, pd.DataFrame):
            layer_dat_ = self.decode_pbf_layer(layer_dat=layer_dat, decode_geojson=decode_geojson)

        else:
            lyr_dat_ = [
                self.decode_pbf_layer(layer_dat=dat, decode_geojson=decode_geojson)
                for dat in layer_dat
            ]
            layer_dat_ = pd.concat(lyr_dat_, ignore_index=True)

        if sort_by:
            sort_by_ = [sort_by] if isinstance(sort_by, str) else copy.copy(sort_by)

            if all(x in layer_dat_.columns for x in sort_by_):
                layer_dat_.sort_values(sort_by, ignore_index=True, inplace=True)

        return layer_dat_

    def _fetch_layer(self, connection, table_name_, schema_name_, method, max_size_spooled,
                     chunk_size, decode_geojson, sort_by, **kwargs):
        sql_query = f'SELECT * FROM "{schema_name_}"."{table_name_}"'

        if method is not None:
            dtype = self._get_dtype(table_name_=table_name_, schema_name_=schema_name_)

            layer_dat = self.read_sql_query(
                sql_query=sql_query, method=method, max_size_spooled=max_size_spooled,
                chunksize=chunk_size, dtype=dtype, **kwargs)

        else:
            layer_dat = pd.read_sql(
                sql=sqlalchemy.text(sql_query), con=connection, chunksize=chunk_size, **kwargs)

        # noinspection PyUnboundLocalVariable
        layer_dat = self.postprocess_pdf_layer(
            layer_dat=layer_dat, decode_geojson=decode_geojson, sort_by=sort_by)

        return layer_dat

    def fetch_data(self, subregion_name, layer_names=None, chunk_size=None, method='tempfile',
                   max_size_spooled=1, decode_geojson=True, sort_by='id',
                   table_named_as_subregion=False, schema_named_as_layer=False, verbose=False,
                   raise_error=False, **kwargs):
        """
        Fetch OSM data (of one or multiple layers) of a geographic (sub)region.

        See also
        [`ROP-1 <https://pyhelpers.readthedocs.io/en/latest/sql.html#sql-postgresql-read-sql-query>`_].

        :param subregion_name: name of a geographic (sub)region (or the corresponding table)
        :type subregion_name: str
        :param layer_names: names of schemas for each layer of the PBF data,
            if ``None`` (default), the default layer names as schema names
        :type layer_names: list | None
        :param chunk_size: the number of rows in each batch to be written at a time,
            defaults to ``None``
        :type chunk_size: int | None
        :param method: method to be used for buffering temporary data, defaults to ``'tempfile'``
        :type method: str | None
        :param max_size_spooled: see `pyhelpers.sql.PostgreSQL.read_sql_query()`_,
            defaults to ``1`` (in GB)
        :type max_size_spooled: int, float
        :param decode_geojson: whether to decode string GeoJSON data, defaults to ``True``
        :type decode_geojson: bool
        :param sort_by: column name(s) by which the data (fetched from PostgreSQL) is sorted,
            defaults to ``'id'``
        :type sort_by: str | list
        :param table_named_as_subregion: whether to use subregion name as a table name,
            defaults to ``False``
        :type table_named_as_subregion: bool
        :param schema_named_as_layer: whether a schema is named as a layer name,
            defaults to ``False``
        :type schema_named_as_layer: bool
        :param verbose: whether to print relevant information in console, defaults to ``False``
        :type verbose: bool | int
        :param raise_error: Whether to raise the provided exception;
            if ``raise_error=False`` (default), the error will be suppressed.
        :type raise_error: bool
        :return: PBF (.osm.pbf) data
        :rtype: dict

        .. _`pyhelpers.sql.PostgreSQL.read_sql_query()`:
            https://pyhelpers.readthedocs.io/en/latest/sql.html#sql-postgresql-read-sql-query

        **Examples**::

            >>> from pydriosm.ios import PostgresOSM
            >>> from pyhelpers.dirs import delete_dir

            >>> osmdb = PostgresOSM(database_name='osmdb_test')
            Password (postgres@localhost:5432): ***
            Creating a database: "osmdb_test" ... Done.
            Connecting postgres:***@localhost:5432/osmdb_test ... Successfully.

            >>> subrgn_name = 'Rutland'  # name of a subregion
            >>> dat_dir = "tests/osm_data"  # name of a data directory where the subregion data is

            >>> # Import PBF data of Rutland
            >>> osmdb.import_osm_pbf(subrgn_name, data_dir=dat_dir, verbose=True)
            Proceed to import .osm.pbf data of the following geographic (sub)region(s):
                "Rutland"
              into postgres:***@localhost:5432/osmdb_test
            ? [No]|Yes: yes
            Downloading "rutland-latest.osm.pbf" 100%|██████████| 1.89M/1.89M | 6.46MB/s ...
              Saving "rutland-latest.osm.pbf" to "./tests/osm_data/rutland/" ... Done.
            Reading "tests/osm_data/rutland/rutland-latest.osm.pbf" ... Done.
            Importing the data into the table "Rutland" ...
                "points" ... Done. (6420 features)
                "lines" ... Done. (10958 features)
                "multilinestrings" ... Done. (71 features)
                "multipolygons" ... Done. (9194 features)
                "other_relations" ... Done. (33 features)

            >>> # Import shapefile data of Rutland
            >>> rutland_shp = osmdb.reader.read_shp(
            ...     subrgn_name, data_dir=dat_dir, rm_extracts=True, verbose=True)
            Downloading "rutland-latest-free.shp.zip" 100%|██████████| 2.71M/2.71M | 7.22...
              Saving "rutland-latest-free.shp.zip" to "./tests/osm_data/rutland/" ... Done.
            Extracting "./tests/osm_data/rutland/rutland-latest-free.shp.zip"
                to "./tests/osm_data/rutland/rutland-latest-free-shp/" ... Done.
            Reading the shapefile(s) at "./tests/osm_data/rutland/rutland-latest-free-shp/" ......
            Deleting the extracts "./tests/osm_data/rutland/rutland-latest-free-shp/" ... Done.
            >>> osmdb.import_osm_data(rutland_shp, table_name=subrgn_name, verbose=True)
            Proceed to import data into the table "Rutland" at postgres:***@localhost:5432/osmdb_test
            ? [No]|Yes: yes
            Importing the data ...
                "buildings" ... Done. (5552 features)
                "landuse" ... Done. (2436 features)
                "natural" ... Done. (664 features)
                "places" ... Done. (301 features)
                "pofw" ... Done. (65 features)
                "pois" ... Done. (1077 features)
                "railways" ... Done. (137 features)
                "roads" ... Done. (7294 features)
                "traffic" ... Done. (537 features)
                "transport" ... Done. (65 features)
                "water" ... Done. (223 features)
                "waterways" ... Done. (379 features)

            >>> # Retrieve the data of specific layers
            >>> lyr_names = ['points', 'multipolygons']
            >>> rutland_data_ = osmdb.fetch_data(subrgn_name, lyr_names, verbose=True)
            Fetching the data of "Rutland" ...
                "points" ... Done.
                "multipolygons" ... Done.
            >>> type(rutland_data_)
            dict
            >>> list(rutland_data_.keys())
            ['points', 'multipolygons']

            >>> # Data of the 'points' layer
            >>> rutland_points = rutland_data_['points']
            >>> rutland_points.head()
                                                          points
            0  {'type': 'Feature', 'geometry': {'type': 'Poin...
            1  {'type': 'Feature', 'geometry': {'type': 'Poin...
            2  {'type': 'Feature', 'geometry': {'type': 'Poin...
            3  {'type': 'Feature', 'geometry': {'type': 'Poin...
            4  {'type': 'Feature', 'geometry': {'type': 'Poin...

            >>> # Retrieve the data of all the layers from the database
            >>> rutland_data = osmdb.fetch_data(subrgn_name, layer_names=None, verbose=True)
            Fetching the data of "Rutland" ...
                "points" ... Done.
                "lines" ... Done.
                "multilinestrings" ... Done.
                "multipolygons" ... Done.
                "other_relations" ... Done.
                "buildings" ... Done.
                "landuse" ... Done.
                "natural" ... Done.
                "places" ... Done.
                "pofw" ... Done.
                "pois" ... Done.
                "railways" ... Done.
                "roads" ... Done.
                "traffic" ... Done.
                "transport" ... Done.
                "water" ... Done.
                "waterways" ... Done.
            >>> type(rutland_data)
            dict
            >>> list(rutland_data.keys())
            ['points',
             'lines',
             'multilinestrings',
             'multipolygons',
             'other_relations',
             'buildings',
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

            >>> # Data of the 'waterways' layer
            >>> rutland_waterways = rutland_data['waterways']
            >>> rutland_waterways.head()
                osm_id  code  ...                                        coordinates  shape_type
            0  3701346  8102  ...  [(-0.7536654, 52.6495358), (-0.7536236, 52.649...           3
            1  3701347  8102  ...  [(-0.7948821, 52.6569468), (-0.7946128, 52.656...           3
            2  3707149  8103  ...  [(-0.7262381, 52.6790459), (-0.7258244, 52.680...           3
            3  3707303  8102  ...  [(-0.7213277, 52.6765954), (-0.7206778, 52.676...           3
            4  4470795  8101  ...  [(-0.4995349, 52.6418825), (-0.4984075, 52.642...           3
            [5 rows x 7 columns]

        Delete the test database and downloaded data files::

            >>> # Delete the database 'osmdb_test'
            >>> osmdb.drop_database(verbose=True)
            Proceed to drop the database "osmdb_test" from postgres:***@localhost:5432
            ? [No]|Yes: yes
            Dropping "osmdb_test" ... Done.

            >>> # Delete the downloaded data files
            >>> delete_dir(dat_dir, verbose=True)
            To delete the directory "./tests/osm_data/" (Not empty)
            ? [No]|Yes: yes
            Deleting "./tests/osm_data/" ... Done.

        .. seealso::

            - More details of the above data can be found in the examples for the methods
              :meth:`~pydriosm.ios.PostgresOSM.import_osm_data`
              and :meth:`~pydriosm.ios.PostgresOSM.import_subregion_osm_pbf`.
            - Similar examples about
              :ref:`fetching data from the database<quickstart-ios-fetch-data>`
              are available in :doc:`../quick-start`.
        """

        table_name_ = self.get_table_name(
            subregion_name=subregion_name, table_named_as_subregion=table_named_as_subregion)
        schema_names_ = validate_schema_names(
            schema_names=layer_names, schema_named_as_layer=schema_named_as_layer)

        if not schema_names_:
            schema_names_ = list(dict.fromkeys(
                list(PBF.LAYER_GEOM.keys()) + sorted(list(SHP.LAYER_NAMES))))

        if any(self.subregion_table_exists(table_name_, x) for x in schema_names_):
            if verbose:
                print(f'Fetching the data of "{table_name_}" ... ')

            existing_schemas, layer_data = schema_names_.copy(), []

            with self.engine.connect() as connection:
                for schema_name_ in schema_names_:
                    if self.subregion_table_exists(table_name_, schema_name_):
                        if verbose:
                            print(f'\t"{schema_name_}"', end=" ... ")

                        try:
                            layer_dat = self._fetch_layer(
                                connection, table_name_=table_name_, schema_name_=schema_name_,
                                method=method, max_size_spooled=max_size_spooled,
                                chunk_size=chunk_size, decode_geojson=decode_geojson,
                                sort_by=sort_by, **kwargs)

                            layer_data.append(layer_dat)

                            if verbose:
                                print("Done.")

                        except Exception as e:
                            _print_failure_message(
                                e=e, prefix="Failed. Error:", verbose=verbose,
                                raise_error=raise_error)

                    else:
                        existing_schemas.remove(schema_name_)

            return dict(zip(existing_schemas, layer_data))

        else:
            if verbose:
                print("No data is available for the given input `subregion_name`.")

    def drop_subregion_tables(self, subregion_names, schema_names=None,
                              table_named_as_subregion=False, schema_named_as_layer=False,
                              confirmation_required=True, verbose=False, raise_error=False):
        """
        Delete all or specific schemas/layers of subregion data from the database being connected.

        :param subregion_names: name of table for a subregion (or name of a subregion)
        :type subregion_names: str | list
        :param schema_names: names of schemas for each layer of the PBF data,
            if ``None`` (default), the default layer names as schema names
        :type schema_names: str | list | None
        :param table_named_as_subregion: whether to use subregion name as a table name,
            defaults to ``False``
        :type table_named_as_subregion: bool
        :param schema_named_as_layer: whether a schema is named as a layer name,
            defaults to ``False``
        :type schema_named_as_layer: bool
        :param confirmation_required: whether to ask for confirmation to proceed,
            defaults to ``True``
        :type confirmation_required: bool
        :param verbose: whether to print relevant information in console, defaults to ``False``
        :type verbose: bool | int
        :param raise_error: Whether to raise the provided exception;
            if ``raise_error=False`` (default), the error will be suppressed.
        :type raise_error: bool

        **Examples**::

            >>> from pydriosm.ios import PostgresOSM
            >>> from pyhelpers.dirs import delete_dir

            >>> osmdb = PostgresOSM(database_name='osmdb_test', verbose=True)
            Password (postgres@localhost:5432): ***
            Creating a database: "osmdb_test" ... Done.
            Connecting postgres:***@localhost:5432/osmdb_test ... Successfully.

        Import example data into the database::

            >>> dat_dir = "tests/osm_data"  # Specify a temporary data directory

            >>> # Import PBF data of 'Rutland' and 'Isle of Wight'
            >>> subrgn_name_1 = ['Rutland', 'Isle of Wight']
            >>> osmdb.import_osm_pbf(
            ...     subrgn_name_1, data_dir=dat_dir, expand=True, parse_geometry=True,
            ...     parse_properties=True, parse_other_tags=True, verbose=True)
            Proceed to import .osm.pbf data of the following geographic (sub)region(s):
                "Rutland"
                "Isle of Wight"
              into postgres:***@localhost:5432/osmdb_test
            ? [No]|Yes: yes
            Downloading "rutland-latest.osm.pbf" 100%|██████████| 1.89M/1.89M | 6.46MB/s ...
              Saving "rutland-latest.osm.pbf" to "./tests/osm_data/rutland/" ... Done.
            Reading "tests/osm_data/rutland/rutland-latest.osm.pbf" ... Done.
            Importing the data into table "Rutland" ...
              "points" ... Done. (<total of rows> features)
              "lines" ... Done. (<total of rows> features)
              "multilinestrings" ... Done. (<total of rows> features)
              "multipolygons" ... Done. (<total of rows> features)
              "other_relations" ... Done. (<total of rows> features)
            Downloading "isle-of-wight-latest.osm.pbf" 100%|██████████| 8.83M/8.83M | 16....
              Saving "isle-of-wight-latest.osm.pbf" to "./tests/osm_data/isle-of-wight/" ... Done.
            Reading "tests/osm_data/isle-of-wight/isle-of-wight-latest.osm.pbf" ... Done.
            Importing the data into table "Isle of Wight" ...
              "points" ... Done. (<total of rows> features)
              "lines" ... Done. (<total of rows> features)
              "multilinestrings" ... Done. (<total of rows> features)
              "multipolygons" ... Done. (<total of rows> features)
              "other_relations" ... Done. (<total of rows> features)

            >>> # Change the data source
            >>> osmdb.data_source = 'BBBike'
            >>> subrgn_name_2 = 'London'

            >>> # An alternative way to import the shapefile data of 'London'
            >>> london_shp = osmdb.reader.read_shp(
            ...     subrgn_name_2, data_dir=dat_dir, rm_extracts=True, download=True, verbose=True)
            Downloading "London.osm.shp.zip" 100%|██████████| 245M/245M | 6.41MB/s | ETA:...
              Saving "London.osm.shp.zip" to "./tests/osm_data/london/" ... Done.
            Extracting "./tests/osm_data/london/London.osm.shp.zip"
              to "./tests/osm_data/london/" ... Done.
            Reading the shapefile(s) at "./tests/osm_data/london/London-shp/shape/" ... Done.
            Deleting the extracts "./tests/osm_data/london/London-shp/" ... Done.
            >>> osmdb.import_osm_data(london_shp, table_name=subrgn_name_2, verbose=True)
            Proceed to import data into table "London" at postgres:***@localhost:5432/osmdb_test
            ? [No]|Yes: yes
            Importing the data ...
              "buildings" ... Done. (<total of rows> features)
              "landuse" ... Done. (<total of rows> features)
              "natural" ... Done. (<total of rows> features)
              "places" ... Done. (<total of rows> features)
              "points" ... Done. (<total of rows> features)
              "railways" ... Done. (<total of rows> features)
              "roads" ... Done. (<total of rows> features)
              "waterways" ... Done. (<total of rows> features)

        Delete data of 'Rutland'::

            >>> subrgn_name = 'Rutland'

            >>> # Delete data of Rutland under the schemas 'buildings' and 'landuse'
            >>> lyr_name = ['buildings', 'landuse']
            >>> osmdb.drop_subregion_tables(subrgn_name, lyr_name, verbose=True)
            None of the data exists.

            >>> # Delete 'points' layer data of Rutland
            >>> lyr_name = 'points'
            >>> osmdb.drop_subregion_tables(subrgn_name, lyr_name, verbose=True)
            Proceed to drop table "points"."Rutland"
              from postgres:***@localhost:5432/osmdb_test
            ? [No]|Yes: yes
            Dropping the table ...
              "points"."Rutland" ... Done.

            >>> # Delete all available tables of Rutland
            >>> osmdb.drop_subregion_tables(subrgn_name, verbose=True)
            Proceed to drop table from postgres:***@localhost:5432/osmdb_test: "Rutland"
              under the schemas:
                "lines"
                "multilinestrings"
                "multipolygons"
                "other_relations"
            ? [No]|Yes: yes
            Dropping the tables ...
              "lines"."Rutland" ... Done.
              "multilinestrings"."Rutland" ... Done.
              "multipolygons"."Rutland" ... Done.
              "other_relations"."Rutland" ... Done.

        Delete 'buildings' and 'points' data of London and Isle of Wight::

            >>> # Delete 'buildings' and 'points' layers of London and Isle of Wight
            >>> subrgn_names = ['London', 'Isle of Wight']
            >>> lyr_names = ['buildings', 'points']
            >>> osmdb.drop_subregion_tables(subrgn_names, schema_names=lyr_names, verbose=True)
            Proceed to drop tables from postgres:***@localhost:5432/osmdb_test:
                "Isle of Wight"
                "London"
              under the schemas:
                "points"
                "buildings"
            ? [No]|Yes: yes
            Dropping the tables ...
              "points"."Isle of Wight" ... Done.
              "points"."London" ... Done.
              "buildings"."London" ... Done.

            >>> # Delete the rest of the data of London and Isle of Wight
            >>> osmdb.drop_subregion_tables(subrgn_names, verbose=True)
            Proceed to drop tables from postgres:***@localhost:5432/osmdb_test:
                "Isle of Wight"
                "London"
              under the schemas:
                "railways"
                "landuse"
                "other_relations"
                "lines"
                "multilinestrings"
                "waterways"
                "roads"
                "multipolygons"
                "natural"
                "places"
            ? [No]|Yes: yes
            Dropping the tables ...
              "railways"."London" ... Done.
              "landuse"."London" ... Done.
              "other_relations"."Isle of Wight" ... Done.
              "lines"."Isle of Wight" ... Done.
              "multilinestrings"."Isle of Wight" ... Done.
              "waterways"."London" ... Done.
              "roads"."London" ... Done.
              "multipolygons"."Isle of Wight" ... Done.
              "natural"."London" ... Done.
              "places"."London" ... Done.

        Delete the test database and downloaded data files::

            >>> # Delete the database 'osmdb_test'
            >>> osmdb.drop_database(verbose=True)
            Procced to drop the database "osmdb_test" from postgres:***@localhost:5432
            ? [No]|Yes: yes
            Dropping "osmdb_test" ... Done.

            >>> # Delete the downloaded data files
            >>> delete_dir(dat_dir, verbose=True)
            To delete the directory "./tests/osm_data/" (Not empty)
            ? [No]|Yes: yes
            Deleting "./tests/osm_data/" ... Done.
        """

        super().drop_subregion_tables(
            subregion_names=subregion_names,
            schema_names=schema_names,
            table_named_as_subregion=table_named_as_subregion,
            schema_named_as_layer=schema_named_as_layer,
            confirmation_required=confirmation_required,
            verbose=verbose,
            raise_error=raise_error,
        )
