"""
I/O and storage of OSM data extracts with `PostgreSQL <https://www.postgresql.org/>`_.
"""

import shapely.wkt
import sqlalchemy.engine.reflection
from pyhelpers.sql import PostgreSQL
from pyhelpers.text import remove_punctuation

from .reader import *
from .utils import convert_dtype_dict


def get_default_layer_name(schema_name):
    """
    Get default name of an OSM layer for an input schema name of
    the class :ref:`PostgresOSM()<pydriosm.ios.PostgresOSM>`.
    See, for example,
    the method :ref:`PostgresOSM.import_osm_layer()<pydriosm-PostgresOSM-import_osm_layer>`.

    :param schema_name: name of a schema (or name of an OSM layer)
    :type schema_name: str
    :return: default name of the layer
    :rtype: str

    **Example**::

        >>> from pydriosm.ios import get_default_layer_name

        >>> lyr_name = 'point'
        >>> lyr_name_ = get_default_layer_name(lyr_name)

        >>> print(lyr_name_)
        points
    """

    valid_layer_names = \
        list(get_pbf_layer_feat_types_dict().keys()) + get_valid_shp_layer_names()

    layer_name_ = find_similar_str(schema_name, valid_layer_names)

    return layer_name_


def validate_schema_names(schema_names=None, schema_named_as_layer=False):
    """
    Validate schema names of a `PostgreSQL <https://www.postgresql.org/>`_ database
    for importing OSM data into it.

    :param schema_names: one or multiple names of layers, e.g. 'points', 'lines',
        defaults to ``None``
    :type schema_names: list or None
    :param schema_named_as_layer: whether to use default PBF layer name as the schema name,
        defaults to ``False``
    :type schema_named_as_layer: bool
    :return: valid names of the schemas in the database
    :rtype: list

    **Examples**::

        >>> from pydriosm.ios import validate_schema_names

        >>> schemas_names = validate_schema_names()

        >>> print(schemas_names)
        []

        >>> schemas_names_ = ['point', 'polygon']
        >>> schemas_names = validate_schema_names(schemas_names_)

        >>> print(schemas_names)
        ['point', 'polygon']

        >>> schemas_names = validate_schema_names(schemas_names_, schema_named_as_layer=True)

        >>> print(schemas_names)
        ['points', 'multipolygons']
    """

    if schema_names:
        if isinstance(schema_names, str):
            schema_names_ = [get_default_layer_name(schema_names) if schema_named_as_layer
                             else schema_names]
            # assert schema_names_[0] in valid_layer_names, assertion_msg
        else:  # isinstance(schema_names, list) is True
            schema_names_ = [
                get_default_layer_name(x) for x in schema_names] if schema_named_as_layer \
                else schema_names
    else:
        schema_names_ = []

    return schema_names_


def validate_table_name(table_name, sub_space=''):
    """
    Validate table name for a `PostgreSQL <https://www.postgresql.org/>`_ database.

    :param table_name: name (as input) of a table in a (PostgreSQL) database
    :type table_name: str
    :param sub_space: substitute for space
    :type sub_space: str
    :return: valid name of the table in the database
    :rtype: str

    **Examples**::

        >>> from pydriosm.ios import validate_table_name

        >>> sr_name = 'greater london'
        >>> tbl_name = validate_table_name(sr_name)

        >>> print(tbl_name)
        # greater london

        >>> sr_name = 'Llanfairpwllgwyngyllgogerychwyrndrobwllllantysiliogogogoch, Wales'
        >>> tbl_name = validate_table_name(sr_name, sub_space='_')

        >>> print(tbl_name)
        # Llanfairpwllgwyngyllgogerychwyrndrobwllllantysiliogogogoch_W..
    """

    table_name_ = remove_punctuation(table_name, rm_whitespace=True)

    if sub_space:
        table_name_ = table_name_.replace(' ', sub_space)

    table_name_ = table_name_[:60] + '..' if len(table_name_) >= 63 else table_name_

    return table_name_


class PostgresOSM:
    """
    A class representation of a tool for I/O and storage of
    `OSM <https://www.openstreetmap.org/>`_ data extracts with
    `PostgreSQL <https://www.postgresql.org/>`_.

    :param host: host address, defaults to ``'localhost'`` (or ``'127.0.0.1'``)
    :type host: str or None
    :param port: port, defaults to ``5432``
    :type port: int, None
    :param username: database username, defaults to ``'postgres'``
    :type username: str or None
    :param password: database password, defaults to ``None``
    :type password: str or int or None
    :param database_name: database name, defaults to ``'postgres'``
    :type database_name: str
    :param confirm_new_db: whether to impose a confirmation to create a new database,
        defaults to ``False``
    :type confirm_new_db: bool
    :param data_source: source of data extracts, incl. 'Geofabrik' and 'BBBike',
        defaults to ``'Geofabrik'``
    :type data_source: str
    :param verbose: whether to print relevant information in console as the function runs,
        defaults to ``True``
    :type verbose: bool

    **Example**::

        >>> from pydriosm.ios import PostgresOSM

        >>> database_name = 'osmdb_test'

        >>> osmdb_test = PostgresOSM(database_name=database_name)
        Password (postgres@localhost:5432): ***
        Connecting postgres:***@localhost:5432/osmdb_test ... Successfully.

        >>> print(osmdb_test.DataSource)
        Geofabrik
        >>> print(osmdb_test.Downloader)
        <pydriosm.downloader.GeofabrikDownloader object at ...>

        >>> # Change the data source:
        >>> osmdb_test.DataSource = 'BBBike'
        >>> print(osmdb_test.Downloader)
        <pydriosm.downloader.BBBikeDownloader object at ...>
    """

    def __init__(self, host='localhost', port=5432, username='postgres', password=None,
                 database_name='postgres', confirm_new_db=False, data_source='Geofabrik',
                 verbose=True):
        """
        Constructor method.
        """

        self.ValidDataSources = ('Geofabrik', 'BBBike')
        assert data_source in self.ValidDataSources, \
            "The argument `method` must be '%s' or '%s'." % self.ValidDataSources

        self.PostgreSQL = PostgreSQL(host=host, port=port, username=username,
                                     password=password, database_name=database_name,
                                     confirm_new_db=confirm_new_db, verbose=verbose)

        self.Downloaders = dict(
            zip(self.ValidDataSources, [GeofabrikDownloader(), BBBikeDownloader()]))
        self.Readers = dict(
            zip(self.ValidDataSources, [GeofabrikReader(), BBBikeReader()]))

        self.DataSource = data_source

    @property
    def Downloader(self):
        assert self.DataSource in self.ValidDataSources, \
            "`.DataSource` must be '%s' or '%s'." % self.ValidDataSources
        return self.Downloaders[self.DataSource]

    @property
    def Name(self):
        return copy.copy(self.Downloader.Name)

    @property
    def URL(self):
        return copy.copy(self.Downloader.URL)

    @property
    def Reader(self):
        assert self.DataSource in self.ValidDataSources, \
            "`.DataSource` must be '%s' or '%s'." % self.ValidDataSources
        return self.Readers[self.DataSource]

    def get_table_name_for_subregion(self, subregion_name,
                                     table_named_as_subregion=False):
        """
        Get the default table name in PostgreSQL database for a specific geographic region.

        :param subregion_name: name of a geographic region, which acts as a table name
        :type subregion_name: str
        :param table_named_as_subregion: whether to use subregion name as table name,
            defaults to ``False``
        :type table_named_as_subregion: bool
        :return: default table name for storing the subregion data into the database
        :rtype: str

        **Examples**::

            >>> from pydriosm.ios import PostgresOSM

            >>> osmdb_test = PostgresOSM(database_name='osmdb_test')
            Password (postgres@localhost:5432): ***
            Connecting postgres:***@localhost:5432/osmdb_test ... Successfully.

            >>> sr_name = 'rutland'

            >>> tbl_name = osmdb_test.get_table_name_for_subregion(sr_name)

            >>> print(tbl_name)
            rutland

            >>> tbl_name = osmdb_test.get_table_name_for_subregion(
            ...     sr_name, table_named_as_subregion=True)

            >>> print(tbl_name)
            # Rutland

        .. note::

            In the examples above, the default data source is 'Geofabrik'.
            Changing it to 'BBBike', the function may possibly produce a different output
            for the same input, as a geographic region that is included in one data source
            may not always be available from the other.
        """

        if table_named_as_subregion:
            if self.DataSource == 'Geofabrik':
                subregion_name_ = \
                    self.Downloader.validate_input_subregion_name(subregion_name)
            else:  # self.DataSource == 'BBBike':
                subregion_name_, _, _, _ = self.Downloader.get_valid_download_info(
                    subregion_name, osm_file_format='')
        else:
            subregion_name_ = subregion_name

        table_name = validate_table_name(subregion_name_)

        return table_name

    def subregion_table_exists(self, subregion_name, layer_name,
                               table_named_as_subregion=False, schema_named_as_layer=False):
        """
        Check if a table (for a geographic region) exists in the
        PostgreSQL database being connected.

        :param subregion_name: name of a geographic region, which acts as a table name
        :type subregion_name: str
        :param layer_name: name of an OSM layer (e.g. 'points', 'railways', ...),
            which acts as a schema name
        :type layer_name: str
        :param table_named_as_subregion: whether to use subregion name as table name,
            defaults to ``False``
        :type table_named_as_subregion: bool
        :param schema_named_as_layer: whether a schema is named as a layer name,
            defaults to ``False``
        :type schema_named_as_layer: bool
        :return: ``True`` if the table exists, ``False`` otherwise
        :rtype: bool

        **Examples**::

            >>> from pydriosm.ios import PostgresOSM

            >>> osmdb_test = PostgresOSM(database_name='osmdb_test')
            Password (postgres@localhost:5432): ***
            Connecting postgres:***@localhost:5432/osmdb_test ... Successfully.

            >>> sr_name = 'rutland'
            >>> lyr_name = 'pt'

            >>> # (If the table, pt."rutland", does not exist)
            >>> osmdb_test.subregion_table_exists(sr_name, lyr_name)
            False

            # (If the table, points.'Rutland', does not exist)
            >>> osmdb_test.subregion_table_exists(sr_name, lyr_name,
            ...                                   table_named_as_subregion=True,
            ...                                   schema_named_as_layer=True)
            False
        """

        table_name_ = self.get_table_name_for_subregion(
            subregion_name, table_named_as_subregion)
        schema_name_ = get_default_layer_name(layer_name) if schema_named_as_layer \
            else layer_name

        res = self.PostgreSQL.table_exists(table_name_, schema_name_)

        return res

    def get_subregion_table_column_info(self, subregion_name, layer_name, as_dict=False,
                                        table_named_as_subregion=False,
                                        schema_named_as_layer=False):
        """
        Get information about columns of a specific schema and table data of
        a geographic region.

        :param subregion_name: name of a geographic region, which acts as a table name
        :type subregion_name: str
        :param layer_name: name of an OSM layer (e.g. 'points', 'railways', ...),
            which acts as a schema name
        :type layer_name: str
        :param as_dict: whether to return the column information as a dictionary,
            defaults to ``True``
        :type as_dict: bool
        :param table_named_as_subregion: whether to use subregion name as table name,
            defaults to ``False``
        :type table_named_as_subregion: bool
        :param schema_named_as_layer: whether a schema is named as a layer name,
            defaults to ``False``
        :type schema_named_as_layer: bool
        :return: information about each column of the given table
        :rtype: pandas.DataFrame or dict

        **Examples**::

            >>> from pydriosm.ios import PostgresOSM

            >>> osmdb_test = PostgresOSM(database_name='osmdb_test')
            Password (postgres@localhost:5432): ***
            Connecting postgres:***@localhost:5432/osmdb_test ... Successfully.

            >>> sr_name = 'rutland'
            >>> lyr_name = 'points'

            >>> column_info_table = osmdb_test.get_subregion_table_column_info(
            ...     sr_name, lyr_name)

            >>> type(column_info_table)
            <class 'pandas.core.frame.DataFrame'>
            >>> print(column_info_table.index.to_list()[:5])
            ['table_catalog',
             'table_schema',
             'table_name',
             'column_name',
             'ordinal_position']

            >>> column_info_dict = osmdb_test.get_subregion_table_column_info(
            ...     sr_name, lyr_name, as_dict=True, table_named_as_subregion=True,
            ...     schema_named_as_layer=True)

            >>> type(column_info_dict)
            <class 'dict'>
            >>> print(list(column_info_dict.keys())[:5])
            ['table_catalog',
             'table_schema',
             'table_name',
             'column_name',
             'ordinal_position']
        """

        table_name_ = \
            self.get_table_name_for_subregion(subregion_name, table_named_as_subregion)

        schema_name_ = get_default_layer_name(layer_name) if schema_named_as_layer \
            else layer_name

        column_info = self.PostgreSQL.get_column_info(table_name=table_name_,
                                                      schema_name=schema_name_,
                                                      as_dict=as_dict)

        return column_info

    def import_osm_layer(self, osm_layer_data, table_name, schema_name,
                         table_named_as_subregion=False, schema_named_as_layer=False,
                         if_exists='replace', force_replace=False, chunk_size=None,
                         verbose=False, **kwargs):
        """
        Import one layer of OSM data into the database being connected.

        :param osm_layer_data: one layer of OSM data
        :type osm_layer_data: pandas.DataFrame or geopandas.GeoDataFrame
        :param schema_name: name of a schema (or name of a PBF layer)
        :type schema_name: str
        :param table_name: name of a table
        :type table_name: str
        :param table_named_as_subregion: whether to use subregion name to be a table name,
            defaults to ``False``
        :type table_named_as_subregion: bool
        :param schema_named_as_layer: whether a schema is named as a layer name,
            defaults to ``False``
        :type schema_named_as_layer: bool
        :param if_exists: if the table already exists,
            to ``'replace'`` (default), ``'append'`` or ``'fail'``
        :type if_exists: str
        :param force_replace: whether to force to replace existing table,
            defaults to ``False``
        :type force_replace: bool
        :param chunk_size: the number of rows in each batch to be written at a time,
            defaults to ``None``
        :type chunk_size: int, None
        :param verbose: whether to print relevant information in console
            as the function runs, defaults to ``False``
        :type verbose: bool
        :param kwargs: optional parameters of `pyhelpers.sql.PostgreSQL.dump_data`_

        .. _`pyhelpers.sql.PostgreSQL.dump_data`:
            https://pyhelpers.readthedocs.io/en/latest/sql.html#sql-postgresql-dump-data

        .. _pydriosm-PostgresOSM-import_osm_layer:

        **Examples**::

            >>> import os
            >>> from pyhelpers.dir import cd
            >>> from pydriosm.ios import PostgresOSM

            >>> osmdb_test = PostgresOSM(database_name='osmdb_test')
            Password (postgres@localhost:5432): ***
            Connecting postgres:***@localhost:5432/osmdb_test ... Successfully.

            >>> sr_name = 'Rutland'
            >>> dat_dir = "tests"

            >>> # Import PBF data of Rutland

            >>> rutland_pbf_raw = osmdb_test.Reader.read_osm_pbf(sr_name, dat_dir,
            ...                                                  verbose=True)
            Confirm to download .osm.pbf data of the following geographic region(s):
                Rutland
            ? [No]|Yes: yes

            >>> tbl_name = sr_name
            >>> schema = list(rutland_pbf_raw.keys())[0]  # 'points'

            >>> rutland_pbf_raw_points = rutland_pbf_raw[schema]
            >>> print(rutland_pbf_raw_points.head())
                                                          points
            0  {"type": "Feature", "geometry": {"type": "Poin...
            1  {"type": "Feature", "geometry": {"type": "Poin...
            2  {"type": "Feature", "geometry": {"type": "Poin...
            3  {"type": "Feature", "geometry": {"type": "Poin...
            4  {"type": "Feature", "geometry": {"type": "Poin...

            >>> osmdb_test.import_osm_layer(rutland_pbf_raw_points, tbl_name, schema,
            ...                             verbose=True)
            Creating a schema "points" ... Done.
            Importing data into "points"."Rutland" at postgres:***@ ... Done.

            >>> column_info = osmdb_test.get_subregion_table_column_info(tbl_name, schema)
            >>> print(column_info.head())
                                column_0
            table_catalog     osmdb_test
            table_schema          points
            table_name           Rutland
            column_name           points
            ordinal_position           1

            >>> rutland_pbf = osmdb_test.Reader.read_osm_pbf(sr_name, dat_dir,
            ...                                              parse_raw_feat=True,
            ...                                              transform_geom=True)

            >>> rutland_pbf_points = rutland_pbf[schema]
            >>> print(rutland_pbf_points.head())
                     id  ...                    other_tags
            0    488432  ...               "odbl"=>"clean"
            1    488658  ...                          None
            2  13883868  ...                          None
            3  14049101  ...  "traffic_calming"=>"cushion"
            4  14558402  ...      "direction"=>"clockwise"
            [5 rows x 12 columns]

            >>> osmdb_test.import_osm_layer(rutland_pbf_points, tbl_name, schema,
            ...                             verbose=True)
            The table points."Rutland" already exists and is replaced ...
            Importing data into "points"."Rutland" at postgres:***@ ... Done.

            >>> # Delete the downloaded PBF data file
            >>> os.remove(cd(dat_dir, "rutland-latest.osm.pbf"))

            >>> # Import shapefile data of Rutland

            >>> lyr_name = 'railways'
            >>> rutland_railways_shp = osmdb_test.Reader.read_shp_zip(
            ...     sr_name, lyr_name, data_dir=dat_dir, rm_extracts=True, rm_shp_zip=True,
            ...     verbose=True)
            Confirm to download .shp.zip data of the following geographic region(s):
                Rutland
            ? [No]|Yes: yes
            Downloading "rutland-latest-free.shp.zip" to "\\tests" ...
            Done.
            Extracting from "rutland-latest-free.shp.zip" the following layer(s):
                'railways'
            to "\\tests\\rutland-latest-free-shp" ...
            In progress ... Done.
            Deleting the extracts "\\tests\\rutland-latest-free-shp"  ... Done.
            Deleting "tests\\rutland-latest-free.shp.zip" ... Done.

            >>> type(rutland_railways_shp)
            <class 'dict'>
            >>> print(list(rutland_railways_shp.keys()))
            # ['railways']

            >>> rutland_railways_shp_ = rutland_railways_shp[lyr_name]

            >>> osmdb_test.import_osm_layer(rutland_railways_shp_, table_name=sr_name,
            ...                             schema_name=lyr_name, verbose=True)
            Creating a schema "railways" ... Done.
            Importing data into "railways"."Rutland" at postgres:***@ ... Done.

            >>> column_info_ = osmdb_test.get_subregion_table_column_info(tbl_name, lyr_name)
            >>> print(column_info_.head())
                                column_0    column_1  ...    column_6    column_7
            table_catalog     osmdb_test  osmdb_test  ...  osmdb_test  osmdb_test
            table_schema        railways    railways  ...    railways    railways
            table_name           Rutland     Rutland  ...     Rutland     Rutland
            column_name           osm_id        code  ...      tunnel    geometry
            ordinal_position           1           2  ...           7           8
            [5 rows x 8 columns]
        """

        table_name_ = self.get_table_name_for_subregion(table_name, table_named_as_subregion)

        schema_name_ = get_default_layer_name(schema_name) if schema_named_as_layer \
            else schema_name

        if osm_layer_data.empty:
            self.PostgreSQL.import_data(osm_layer_data, table_name=table_name_,
                                        schema_name=schema_name_, if_exists=if_exists,
                                        force_replace=force_replace, verbose=verbose,
                                        method=self.PostgreSQL.psql_insert_copy, **kwargs)

        else:
            lyr_dat = osm_layer_data.copy()

            if lyr_dat.shape[1] == 1:
                col_type = {lyr_dat.columns[0]: sqlalchemy.types.JSON}
            else:
                col_type = None
                if 'coordinates' in lyr_dat.columns:
                    if not isinstance(lyr_dat.coordinates[0], list):
                        lyr_dat.coordinates = lyr_dat.coordinates.map(lambda x: x.wkt)

            if isinstance(lyr_dat, gpd.GeoDataFrame):
                lyr_dat = pd.DataFrame(lyr_dat)
                data_types = lyr_dat.dtypes
                if 'geometry' in [x.name for x in data_types]:
                    geom_col_name = data_types[data_types == 'geometry'].index[0]
                    lyr_dat[geom_col_name] = lyr_dat[geom_col_name].map(lambda x: x.wkt)

            self.PostgreSQL.import_data(lyr_dat, table_name=table_name_,
                                        schema_name=schema_name_, if_exists=if_exists,
                                        force_replace=force_replace, chunk_size=chunk_size,
                                        col_type=col_type,
                                        method=self.PostgreSQL.psql_insert_copy,
                                        verbose=verbose, **kwargs)

    def import_osm_data(self, osm_data, table_name, schema_names=None,
                        table_named_as_subregion=False, schema_named_as_layer=False,
                        if_exists='replace', force_replace=False, chunk_size=None,
                        verbose=False, **kwargs):
        """
        Import OSM data into the database being connected.

        :param osm_data: OSM data of a geographic region
        :type osm_data: dict
        :param table_name: name of a table
        :type table_name: str
        :param schema_names: names of schemas for each layer of the PBF data,
            if ``None`` (default), use the default layer names as schema names
        :type schema_names: list or None
        :param table_named_as_subregion: whether to use subregion name to be a table name,
            defaults to ``False``
        :type table_named_as_subregion: bool
        :param schema_named_as_layer: whether a schema is named as a layer name,
            defaults to ``False``
        :type schema_named_as_layer: bool
        :param if_exists: if the table already exists,
            to ``'replace'`` (default), ``'append'`` or ``'fail'``
        :type if_exists: str
        :param force_replace: whether to force to replace existing table,
            defaults to ``False``
        :type force_replace: bool
        :param chunk_size: the number of rows in each batch to be written at a time,
            defaults to ``None``
        :type chunk_size: int, None
        :param verbose: whether to print relevant information in console
            as the function runs, defaults to ``False``
        :type verbose: bool
        :param kwargs: optional parameters of ``.import_osm_pbf_layer()``

        **Examples**::

            >>> import os
            >>> from pyhelpers.dir import cd
            >>> from pydriosm.ios import PostgresOSM

            >>> osmdb_test = PostgresOSM(database_name='osmdb_test')
            Password (postgres@localhost:5432): ***
            Connecting postgres:***@localhost:5432/osmdb_test ... Successfully.

            >>> sr_name = 'Rutland'
            >>> dat_dir = "tests"

            >>> rutland_pbf_raw = osmdb_test.Reader.read_osm_pbf(sr_name, dat_dir,
            ...                                                  verbose=True)
            Confirm to download .osm.pbf data of the following geographic region(s):
                Rutland
            ? [No]|Yes: yes

            >>> # Import all layers of the raw PBF data of Rutland

            >>> osmdb_test.import_osm_data(rutland_pbf_raw, table_name=sr_name, verbose=True)
            Importing data into "Rutland" at postgres:***@localhost:5432/osmdb_test ...
                points ... done: <total of rows> features.
                lines ... done: <total of rows> features.
                multilinestrings ... done: <total of rows> features.
                multipolygons ... done: <total of rows> features.
                other_relations ... done: <total of rows> features.

            >>> rutland_pbf = osmdb_test.Reader.read_osm_pbf(sr_name, dat_dir,
            ...                                              parse_raw_feat=True,
            ...                                              transform_geom=True,
            ...                                              transform_other_tags=True)

            >>> # Import data into specific schemas
            >>> schemas = {'schema_0': 'lines',
            ...            'schema_1': 'points',
            ...            'schema_2': 'multipolygons'}

            >>> osmdb_test.import_osm_data(rutland_pbf, table_name=sr_name,
            ...                            schema_names=schemas, verbose=True)
            Importing data into "Rutland" at postgres:***@localhost:5432/osmdb_test ...
                schema_0 ... done: <total of rows> features.
                schema_1 ... done: <total of rows> features.
                schema_2 ... done: <total of rows> features.

            >>> # To drop the schemas starting with 'schema_'
            >>> osmdb_test.PostgreSQL.drop_schema(*schemas.keys(), verbose=True)
            Confirmed to drop the schemas "schema_0", "schema_1" and "schema_2"
                from postgres:***@localhost:5432/osmdb_test? [No]|Yes: yes
            Dropping the schemas "schema_0", "schema_1" and "schema_2" ... Done.

            >>> # Delete the downloaded PBF data file
            >>> os.remove(cd(dat_dir, "rutland-latest.osm.pbf"))

            >>> rutland_shp = osmdb_test.Reader.read_shp_zip(sr_name, data_dir=dat_dir,
            ...                                              rm_extracts=True,
            ...                                              rm_shp_zip=True, verbose=True)
            Confirm to download .shp.zip data of the following geographic region(s):
                Rutland
            ? [No]|Yes: yes
            Downloading "rutland-latest-free.shp.zip" to "\\tests" ...
            Done.
            Extracting all of "rutland-latest-free.shp.zip" to "..." ...
            In progress ... Done.

            >>> # Import all layers of the shapefile data of Rutland

            >>> osmdb_test.import_osm_data(rutland_shp, table_name=sr_name, verbose=True)
            Importing data into "Rutland" at postgres:***@localhost:5432/osmdb_test ...
                water ... done: <total of rows> features.
                pofw ... done: <total of rows> features.
                buildings ... done: <total of rows> features.
                natural ... done: <total of rows> features.
                places ... done: <total of rows> features.
                landuse ... done: <total of rows> features.
                railways ... done: <total of rows> features.
                waterways ... done: <total of rows> features.
                traffic ... done: <total of rows> features.
                transport ... done: <total of rows> features.
                roads ... done: <total of rows> features.
                pois ... done: <total of rows> features.

            >>> # Import BBBike shapefile data

            >>> osmdb_test.DataSource = 'BBBike'
            >>> sr_name = 'Leeds'

            >>> leeds_shp = osmdb_test.Reader.read_shp_zip(sr_name, data_dir=dat_dir,
            ...                                            rm_extracts=True, rm_shp_zip=True,
            ...                                            verbose=True)
            Confirm to download .shp.zip data of the following geographic region(s):
                Leeds
            ? [No]|Yes: yes
            Downloading "Leeds.osm.shp.zip" to "\\tests" ...
            Done.
            Extracting all of "Leeds.osm.shp.zip" to "\\tests" ...
            In progress ... Done.
            Parsing "\\tests\\Leeds-shp\\shape" ... Done.
            Deleting the extracts "\\tests\\Leeds-shp" ... Done.
            Deleting "tests\\Leeds.osm.shp.zip" ... Done.

            >>> osmdb_test.import_osm_data(leeds_shp, table_name=sr_name, verbose=True)
            Importing data into "Leeds" at postgres:***@localhost:5432/osmdb_test ...
                buildings ... done: <total of rows> features.
                points ... done: <total of rows> features.
                natural ... done: <total of rows> features.
                places ... done: <total of rows> features.
                landuse ... done: <total of rows> features.
                railways ... done: <total of rows> features.
                waterways ... done: <total of rows> features.
                roads ... done: <total of rows> features.
        """

        if isinstance(schema_names, list):
            schema_names_ = validate_schema_names(schema_names, schema_named_as_layer=True)
            assert all(x in osm_data.keys() for x in schema_names)
            data_items = zip(schema_names_, (osm_data[x] for x in schema_names_))

        elif isinstance(schema_names, dict):
            # e.g. schema_names = {'schema_0': 'lines', 'schema_1': 'points'}
            schema_names_ = validate_schema_names(schema_names.values(),
                                                  schema_named_as_layer=True)
            assert all(x in osm_data.keys() for x in schema_names_)
            data_items = zip(schema_names.keys(), (osm_data[x] for x in schema_names_))

        else:
            data_items = osm_data.items()

        table_name_ = self.get_table_name_for_subregion(table_name, table_named_as_subregion)

        if verbose:
            print("Importing data into \"{}\" at {} ... ".format(
                table_name_, self.PostgreSQL.address))
        for geom_type, osm_layer in data_items:

            print("\t{}".format(geom_type), end=" ... ") if verbose else ""

            if osm_layer.empty:
                if verbose:
                    print("The layer is empty. "
                          "The corresponding table in the database is thus empty.")

            try:
                self.import_osm_layer(osm_layer,
                                      schema_name=geom_type, table_name=table_name_,
                                      table_named_as_subregion=table_named_as_subregion,
                                      schema_named_as_layer=schema_named_as_layer,
                                      if_exists=if_exists, force_replace=force_replace,
                                      chunk_size=chunk_size, verbose=False, **kwargs)
                print("done: {} features.".format(len(osm_layer))) if verbose else ""

            except Exception as e:
                print("failed. {}".format(e))

            del osm_layer
            gc.collect()

    def import_subregion_osm_pbf(self, subregion_names, data_dir=None,
                                 update_osm_pbf=False, if_exists='replace',
                                 chunk_size_limit=50, parse_raw_feat=False,
                                 transform_geom=False, transform_other_tags=False,
                                 pickle_pbf_file=False, rm_osm_pbf=False,
                                 confirmation_required=True, verbose=False, **kwargs):
        """
        Import data of geographic region(s) that do not have (sub-)subregions into
        the database being connected.

        :param subregion_names: name(s) of geographic region(s)
        :type subregion_names: str or list or None
        :param data_dir: directory where the .osm.pbf data file is located/saved;
            if ``None``, the default directory
        :type data_dir: str or None
        :param update_osm_pbf: whether to check to update .osm.pbf data file (if available),
            defaults to ``False``
        :type update_osm_pbf: bool
        :param if_exists: if the table already exists,
            to ``'replace'`` (default), ``'append'`` or ``'fail'``
        :type if_exists: str
        :param chunk_size_limit: threshold (in MB) that triggers the use of chunk parser,
            defaults to ``50``; if the size of the .osm.pbf file (in MB) is greater than
            ``chunk_size_limit``, it will be parsed in a chunk-wise way
        :type chunk_size_limit: int
        :param parse_raw_feat: whether to parse each feature in the raw data,
            defaults to ``False``
        :type parse_raw_feat: bool
        :param transform_geom: whether to transform a single coordinate
            (or a collection of coordinates) into a geometric object,
            defaults to ``False``
        :type transform_geom: bool
        :param transform_other_tags: whether to transform a ``'other_tags'`` into
            a dictionary, defaults to ``False``
        :type transform_other_tags: bool
        :param pickle_pbf_file: whether to save the .pbf data as a .pickle file,
            defaults to ``False``
        :type pickle_pbf_file: bool
        :param rm_osm_pbf: whether to delete the downloaded .osm.pbf file,
            defaults to ``False``
        :type rm_osm_pbf: bool
        :param confirmation_required: whether to prompt a message
            for confirmation to proceed, defaults to ``True``
        :type confirmation_required: bool
        :param verbose: whether to print relevant information in console
            as the function runs, defaults to ``False``
        :type verbose: bool or int
        :param kwargs: optional parameters of ``.import_osm_pbf_layer()``

        **Examples**::

            >>> import os
            >>> from pyhelpers.dir import cd
            >>> from pyhelpers.store import load_pickle
            >>> from pydriosm.ios import PostgresOSM

            >>> osmdb_test = PostgresOSM(database_name='osmdb_test', data_source='Geofabrik')
            Password (postgres@localhost:5432): ***
            Connecting postgres:***@localhost:5432/osmdb_test ... Successfully.

            >>> dat_dir = "tests"

            >>> sr_name = 'Rutland'

            >>> osmdb_test.import_subregion_osm_pbf(sr_name, dat_dir, rm_osm_pbf=True,
            ...                                     verbose=True)
            To import Geofabrik OSM data of the following geographic region(s) into ...:
                Rutland
            ? [No]|Yes: yes
            Downloading "rutland-latest.osm.pbf" to "\\tests" ...
            Done.
            Importing data into "Rutland" at postgres:***@localhost:5432/osmdb_test ...
                points ... done: <total of rows> features.
                lines ... done: <total of rows> features.
                multilinestrings ... done: <total of rows> features.
                multipolygons ... done: <total of rows> features.
                other_relations ... done: <total of rows> features.
            Deleting "tests\\rutland-latest.osm.pbf" ... Done.

            >>> # Import free BBBike PBF data of Victoria and Waterloo
            >>> osmdb_test.DataSource = 'BBBike'
            >>> sr_names = ['Victoria', 'Waterloo']

            >>> # Note this may take a few minutes or even longer
            >>> osmdb_test.import_subregion_osm_pbf(sr_names, dat_dir, parse_raw_feat=True,
            ...                                     transform_geom=True,
            ...                                     transform_other_tags=True,
            ...                                     pickle_pbf_file=True, rm_osm_pbf=True,
            ...                                     verbose=True)
            To import BBBike OSM data of the following geographic region(s) into ...:
                Victoria,
                Waterloo
            ? [No]|Yes: yes
            Downloading "Victoria.osm.pbf" to "\tests" ...
            Done.
            Parsing "\\tests\\Victoria.osm.pbf" ... Done.
            Importing data into "Victoria" at postgres:***@localhost:5432/osmdb_test ...
                points ... done: <total of rows> features.
                lines ... done: <total of rows> features.
                multilinestrings ... done: <total of rows> features.
                multipolygons ... done: <total of rows> features.
                other_relations ... done: <total of rows> features.
            Saving "Victoria-pbf.pickle" to "\\tests" ... Done.
            Deleting "tests\\Victoria.osm.pbf" ... Done.
            Downloading "Waterloo.osm.pbf" to "\\tests" ...
            Done.
            Parsing "\\tests\\Waterloo.osm.pbf" ... Done.
            Importing data into "Waterloo" at postgres:***@localhost:5432/osmdb_test ...
                points ... done: <total of rows> features.
                lines ... done: <total of rows> features.
                multilinestrings ... done: <total of rows> features.
                multipolygons ... done: <total of rows> features.
                other_relations ... done: <total of rows> features.
            Saving "Waterloo-pbf.pickle" to "\\tests" ... Done.
            Deleting "tests\\Waterloo.osm.pbf" ... Done.

            >>> # The PBF data have also been saved as Pickle files
            >>> victoria_pbf = load_pickle(cd(dat_dir, "Victoria-pbf.pickle"))
            >>> print(victoria_pbf['points'].head())
                     id                      coordinates  ... man_made other_tags
            0  25832817  POINT (-123.3102145 48.4351935)  ...     None       None
            1  25832953  POINT (-123.3157486 48.4309841)  ...     None       None
            2  25832954  POINT (-123.3209612 48.4323984)  ...     None       None
            3  25832995  POINT (-123.3224238 48.4321706)  ...     None       None
            4  25833001  POINT (-123.3202181 48.4297225)  ...     None       None
            [5 rows x 12 columns]

            >>> waterloo_pbf = load_pickle(cd(dat_dir, "Waterloo-pbf.pickle"))
            >>> print(waterloo_pbf['points'].head())
                     id  ...                                 other_tags
            0  10782939  ...                                       None
            1  10782965  ...                                       None
            2  14509209  ...                                       None
            3  14657092  ...  {'traffic_signals:direction': 'backward'}
            4  14657140  ...                                       None
            [5 rows x 12 columns]

            >>> # Delete the Pickle files
            >>> os.remove(cd(dat_dir, "Victoria-pbf.pickle"))
            >>> os.remove(cd(dat_dir, "Waterloo-pbf.pickle"))
        """

        osm_file_format = ".osm.pbf"

        if subregion_names is None:
            subregion_names_ = self.Downloader.get_subregion_name_list()
            confirm_msg = \
                "To import {} OSM PBF data of all geographic regions into {}?".format(
                    self.DataSource, self.PostgreSQL.address)

        else:
            subregion_names_ = [subregion_names] if isinstance(subregion_names, str) \
                else subregion_names.copy()
            subregion_names_ = [self.Downloader.validate_input_subregion_name(x)
                                for x in subregion_names_]

            if self.DataSource == 'Geofabrik':
                subregion_names_ = \
                    self.Downloader.retrieve_names_of_subregions(*subregion_names_)

            confirm_msg = \
                "To import {} OSM data of the following geographic region(s) into {}:" \
                "\n\t{}\n?".format(
                    self.DataSource, self.PostgreSQL.address, ",\n\t".join(subregion_names_))

        if confirmed(confirm_msg, confirmation_required=confirmation_required):

            err_subregion_names = []
            for subregion_name in subregion_names_:
                path_to_osm_pbf = self.Downloader.download_osm_data(
                    subregion_name, osm_file_format, download_dir=data_dir,
                    update=update_osm_pbf, confirmation_required=False, verbose=verbose,
                    ret_download_path=True)

                file_size_in_mb = round(os.path.getsize(path_to_osm_pbf) / (1024 ** 2), 1)

                try:
                    if file_size_in_mb <= chunk_size_limit:
                        number_of_chunks = \
                            get_number_of_chunks(path_to_osm_pbf, chunk_size_limit)

                        if verbose and parse_raw_feat:
                            print("Parsing \"\\{}\"".format(os.path.relpath(path_to_osm_pbf)),
                                  end=" ... ")

                        subregion_osm_pbf = parse_osm_pbf(
                            path_to_osm_pbf, number_of_chunks, parse_raw_feat=parse_raw_feat,
                            transform_geom=transform_geom,
                            transform_other_tags=transform_other_tags)

                        print("Done. ") if verbose and parse_raw_feat else ""

                        if subregion_osm_pbf is not None:
                            self.import_osm_data(osm_data=subregion_osm_pbf,
                                                 table_name=subregion_name,
                                                 if_exists=if_exists, verbose=verbose,
                                                 **kwargs)

                            if pickle_pbf_file:
                                path_to_pickle = path_to_osm_pbf.replace(
                                    osm_file_format, "-pbf.pickle")
                                save_pickle(subregion_osm_pbf, path_to_pickle, verbose=verbose)

                            del subregion_osm_pbf
                            gc.collect()

                    else:
                        if verbose:
                            print(
                                "Parsing and importing the data of \"{}\" feature-wisely "
                                "into {} ... ".format(
                                    subregion_name, self.PostgreSQL.address))

                        # Reference: https://gdal.org/python/osgeo.ogr.Feature-class.html
                        raw_osm_pbf = ogr.Open(path_to_osm_pbf)
                        layer_count = raw_osm_pbf.GetLayerCount()

                        layer_names, all_layer_data, layer_data = [], [], None

                        for i in range(layer_count):
                            layer = raw_osm_pbf.GetLayerByIndex(i)  # Hold the i-th layer
                            layer_name = layer.GetName()

                            if pickle_pbf_file:
                                layer_names.append(layer_name)

                            if verbose:
                                print("                       {}".format(layer_name),
                                      end=" ... ")
                            try:
                                features = [feature for _, feature in enumerate(layer)]
                                feats_no = len(features)
                                chunks_no = math.ceil(file_size_in_mb / chunk_size_limit)
                                feats = split_list(lst=features, num_of_sub=chunks_no)

                                del features
                                gc.collect()

                                if self.subregion_table_exists(subregion_name, layer_name) \
                                        and if_exists == 'replace':
                                    self.drop_subregion_table(subregion_name, layer_name,
                                                              confirmation_required=False)

                                all_lyr_dat = []
                                # Loop through all available features
                                for feat in feats:
                                    if parse_raw_feat:
                                        lyr_dat = pd.DataFrame(
                                            f.ExportToJson(as_object=True) for f in feat)
                                        lyr_dat = parse_osm_pbf_layer(
                                            pbf_layer_data=lyr_dat, geo_typ=layer_name,
                                            transform_geom=transform_geom,
                                            transform_other_tags=transform_other_tags)

                                    else:
                                        lyr_dat = pd.DataFrame(f.ExportToJson() for f in feat)
                                        lyr_dat.columns = ['{}_data'.format(layer_name)]

                                    if_exists_ = if_exists if if_exists == 'fail' \
                                        else 'append'
                                    self.import_osm_layer(osm_layer_data=lyr_dat,
                                                          table_name=subregion_name,
                                                          schema_name=layer_name,
                                                          if_exists=if_exists_)

                                    if pickle_pbf_file:
                                        all_lyr_dat.append(lyr_dat)

                                    del lyr_dat
                                    gc.collect()

                                if pickle_pbf_file:
                                    all_layer_data.append(
                                        pd.concat(all_lyr_dat, ignore_index=True, sort=False))

                                if verbose:
                                    print("done: {} features.".format(feats_no))

                            except Exception as e:
                                print("failed. {}".format(e))

                        raw_osm_pbf.Release()

                        del raw_osm_pbf
                        gc.collect()

                        if pickle_pbf_file:
                            save_pickle(
                                dict(zip(layer_names, all_layer_data)),
                                path_to_osm_pbf.replace(osm_file_format, "-pbf.pickle"),
                                verbose=verbose)

                    if rm_osm_pbf:
                        remove_subregion_osm_file(path_to_osm_pbf, verbose=verbose)

                except Exception as e:
                    print(e)
                    err_subregion_names.append(subregion_name)

            if len(err_subregion_names) > 0:
                print("Errors occurred when parsing data of the following subregion(s):")
                print(*err_subregion_names, sep=", ")

    def fetch_osm_data(self, subregion_name, layer_names=None,
                       table_named_as_subregion=False, schema_named_as_layer=False,
                       chunk_size=None, method='spooled_tempfile', max_size_spooled=1,
                       decode_geojson=False, decode_wkt=False, decode_other_tags=False,
                       parse_geojson=False, sort_by='id', **kwargs):
        """
        Fetch OSM data (of one or multiple layers) of a geographic region.

        See also [`ROP-1
        <https://pyhelpers.readthedocs.io/en/latest/sql.html#sql-postgresql-read-sql-query>`_]

        :param subregion_name: name of a geographic region (or the corresponding table)
        :type subregion_name: str
        :param layer_names: names of schemas for each layer of the PBF data,
            if ``None`` (default), use the default layer names as schema names
        :type layer_names: list or None
        :param table_named_as_subregion: whether to use subregion name to be a table name,
            defaults to ``False``
        :type table_named_as_subregion: bool
        :param schema_named_as_layer: whether a schema is named as a layer name,
            defaults to ``False``
        :type schema_named_as_layer: bool
        :param chunk_size: the number of rows in each batch to be written at a time,
            defaults to ``None``
        :type chunk_size: int, None
        :param method: method to be used for buffering temporary data,
            defaults to ``'spooled_tempfile'``
        :type method: str or None
        :param max_size_spooled: ``max_size_spooled`` of
            `pyhelpers.sql.PostgreSQL.read_sql_query`_, defaults to ``1`` (in gigabyte)
        :type max_size_spooled: int, float
        :param decode_geojson: whether to decode textual GeoJSON, defaults to ``False``
        :type decode_geojson: bool
        :param decode_wkt: whether to decode ``'coordinates'`` (if available and)
            if it is a wkt, defaults to ``False``
        :type decode_wkt: bool
        :param decode_other_tags: whether to decode ``'other_tags'`` (if available),
            defaults to ``False``
        :type decode_other_tags: bool
        :param parse_geojson: whether to parse raw GeoJSON (as it is raw feature data),
            defaults to ``False``
        :type parse_geojson: bool
        :param sort_by: column name(s) by which the data (fetched from PostgreSQL) is sorted,
            defaults to ``None``
        :type sort_by: str or list
        :return: PBF (.osm.pbf) data
        :rtype: dict

        .. _`pyhelpers.sql.PostgreSQL.read_sql_query`:
            https://pyhelpers.readthedocs.io/en/latest/sql.html#sql-postgresql-read-sql-query

        **Example**::

            >>> from pydriosm.ios import PostgresOSM

            >>> osmdb_test = PostgresOSM(database_name='osmdb_test')
            Password (postgres@localhost:5432): ***
            Connecting postgres:***@localhost:5432/osmdb_test ... Successfully.

            >>> sr_name = 'Rutland'

            >>> # With all the examples for
            >>> # `.import_osm_data()` and  `.import_subregion_osm_pbf()`,
            >>> # fetch data of all available layers
            >>> rutland_pbf = osmdb_test.fetch_osm_data(sr_name,
            ...                                         table_named_as_subregion=True)

            >>> type(rutland_pbf)
            <class 'dict'>
            >>> print(list(rutland_pbf.keys()))
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

            >>> # Fetch data of specific layers

            >>> lyr_names = ['points', 'multipolygons']

            >>> rutland_pbf = osmdb_test.fetch_osm_data(sr_name, lyr_names, sort_by='id')

            >>> type(rutland_pbf)
            <class 'dict'>
            >>> print(list(rutland_pbf.keys()))
            # ['points', 'multipolygons']

            >>> rutland_pbf_points = rutland_pbf['points']
            >>> print(rutland_pbf_points.head())
                                                          points
            0  {"type": "Feature", "geometry": {"type": "Poin...
            1  {"type": "Feature", "geometry": {"type": "Poin...
            2  {"type": "Feature", "geometry": {"type": "Poin...
            3  {"type": "Feature", "geometry": {"type": "Poin...
            4  {"type": "Feature", "geometry": {"type": "Poin...

            >>> rutland_pbf_ = osmdb_test.fetch_osm_data(sr_name, lyr_names,
            ...                                          decode_geojson=True, decode_wkt=True,
            ...                                          decode_other_tags=True, sort_by='id')

            >>> rutland_pbf_points_ = rutland_pbf_['points']
            >>> print(rutland_pbf_points_.head())
                     id  ...                      other_tags
            0    488432  ...               {'odbl': 'clean'}
            1    488658  ...                            None
            2  13883868  ...                            None
            3  14049101  ...  {'traffic_calming': 'cushion'}
            4  14558402  ...      {'direction': 'clockwise'}
            [5 rows x 12 columns]

        .. seealso::

            The examples about
            :ref:`fetching data from the database<qs-fetch-data-from-the-database>`
            provided in :ref:`Quick start<pydriosm-quick-start>`.
        """

        def decode_osm_pbf_layer(lyr_dat_):
            """
            Process raw data of a PBF layer retrieved from database.
            """

            lyr_dat_.replace({np.nan: None}, inplace=True)

            if lyr_dat_.shape[1] == 1:
                geo_typ = lyr_dat_.columns[0]

                if decode_geojson:
                    lyr_dat_ = lyr_dat_[geo_typ].map(rapidjson.loads).to_frame(name=geo_typ)

                if decode_wkt or decode_other_tags:
                    lyr_dat_ = pd.DataFrame.from_records(
                        lyr_dat_[geo_typ] if decode_geojson
                        else lyr_dat_[geo_typ].map(rapidjson.loads))
                    lyr_dat_ = parse_osm_pbf_layer(pbf_layer_data=lyr_dat_, geo_typ=geo_typ,
                                                   transform_geom=decode_wkt,
                                                   transform_other_tags=decode_other_tags)

                elif parse_geojson:
                    lyr_dat_ = \
                        pd.DataFrame.from_records(lyr_dat_[geo_typ].map(rapidjson.loads))

            else:
                if decode_wkt:
                    if 'coordinates' in lyr_dat_.columns:
                        try:
                            lyr_dat_.coordinates = lyr_dat_.coordinates.map(eval)
                        except SyntaxError:
                            lyr_dat_.coordinates = lyr_dat_.coordinates.map(shapely.wkt.loads)
                    elif 'geometries' in lyr_dat_.columns:
                        lyr_dat_.geometries = lyr_dat_.geometries.map(lambda x: eval(x))
                    elif 'geometry' in lyr_dat_.columns:
                        lyr_dat_.geometry = lyr_dat_.geometry.map(shapely.wkt.loads)

                if decode_other_tags and 'other_tags' in lyr_dat_:
                    try:
                        lyr_dat_.other_tags = lyr_dat_.other_tags.map(
                            lambda x: x if x is None else eval(x))
                    except SyntaxError:
                        pass

            return lyr_dat_

        table_name_ = self.get_table_name_for_subregion(subregion_name,
                                                        table_named_as_subregion)

        schema_names_ = validate_schema_names(layer_names, schema_named_as_layer)

        if not schema_names_:
            schema_names_ = \
                list(get_pbf_layer_feat_types_dict().keys()) + get_valid_shp_layer_names()

        avail_schemas, layer_data = schema_names_.copy(), []

        for schema_name_ in schema_names_:

            if self.subregion_table_exists(table_name_, schema_name_):

                table = '"{schema}"."{table}"'.format(schema=schema_name_, table=table_name_)
                sql_query = 'SELECT * FROM {}'.format(table)

                if method:
                    column_info_table = self.PostgreSQL.get_column_info(
                        table_name_, schema_name=schema_name_)

                    repl = convert_dtype_dict()
                    dtype_ = column_info_table['data_type']
                    dtype = dict(
                        zip(column_info_table['column_name'], map(repl.get, dtype_, dtype_)))

                    lyr_dat = self.PostgreSQL.read_sql_query(
                        sql_query=sql_query, method=method, max_size_spooled=max_size_spooled,
                        chunksize=chunk_size, dtype=dtype, **kwargs)
                else:
                    lyr_dat = pd.read_sql(sql_query, con=self.PostgreSQL.engine,
                                          chunksize=chunk_size, **kwargs)

                if isinstance(lyr_dat, pd.DataFrame):
                    lyr_dat = decode_osm_pbf_layer(lyr_dat)
                else:
                    lyr_dat_temp = [decode_osm_pbf_layer(lyr_dat_) for lyr_dat_ in lyr_dat]
                    lyr_dat = pd.concat(lyr_dat_temp, ignore_index=True)

                if sort_by:
                    sort_by_ = [sort_by] if isinstance(sort_by, str) else copy.copy(sort_by)
                    if all(x in lyr_dat.columns for x in sort_by_):
                        lyr_dat.sort_values(sort_by, inplace=True)
                        lyr_dat.index = range(len(lyr_dat))

                layer_data.append(lyr_dat)

            else:
                avail_schemas.remove(schema_name_)

        osm_pbf_data = dict(zip(avail_schemas, layer_data))

        return osm_pbf_data

    def drop_subregion_table(self, subregion_table_names, schema_names=None,
                             table_named_as_subregion=False, schema_named_as_layer=False,
                             confirmation_required=True, verbose=False):
        """
        Delete all or specific schemas/layers of subregion data
        from the database being connected.

        :param subregion_table_names: name of table for a subregion (or name of a subregion)
        :type subregion_table_names: str
        :param schema_names: names of schemas for each layer of the PBF data,
            if ``None`` (default), use the default layer names as schema names
        :type schema_names: list or None
        :param table_named_as_subregion: whether to use subregion name to be a table name,
            defaults to ``False``
        :type table_named_as_subregion: bool
        :param schema_named_as_layer: whether a schema is named as a layer name,
            defaults to ``False``
        :type schema_named_as_layer: bool
        :param confirmation_required: whether to prompt a message
            for confirmation to proceed, defaults to ``True``
        :type confirmation_required: bool
        :param verbose: whether to print relevant information in console
            as the function runs, defaults to ``False``
        :type verbose: bool or int

        **Examples**::

            >>> from pydriosm.ios import PostgresOSM

            >>> osmdb_test = PostgresOSM(database_name='osmdb_test')
            Password (postgres@localhost:5432): ***
            Connecting postgres:***@localhost:5432/osmdb_test ... Successfully.

            >>> # With all the examples for
            >>> # `.import_osm_data()` and `.import_subregion_osm_pbf()`,
            >>> # delete all data of Rutland and Leeds

            >>> subregion_tbl_names = ['Rutland', 'Leeds']

            >>> osmdb_test.drop_subregion_table(subregion_tbl_names, verbose=True)
            Confirmed to drop the following tables:
                "Leeds" and
                "Rutland"
              from the following schemas:
                "multipolygons",
                "water",
                "multilinestrings",
                "points",
                "buildings",
                "natural",
                "roads",
                "other_relations",
                "pois",
                "traffic",
                "transport",
                "pofw",
                "landuse",
                "railways",
                "waterways",
                "lines" and
                "places"
              at postgres:***@localhost:5432/osmdb_test
            ? [No]|Yes: yes
            Dropping ...
                "multipolygons"."Rutland" ... Done.
                "water"."Rutland" ... Done.
                "multilinestrings"."Rutland" ... Done.
                "points"."Leeds" ... Done.
                "points"."Rutland" ... Done.
                "buildings"."Leeds" ... Done.
                "buildings"."Rutland" ... Done.
                "natural"."Leeds" ... Done.
                "natural"."Rutland" ... Done.
                "roads"."Leeds" ... Done.
                "roads"."Rutland" ... Done.
                "other_relations"."Rutland" ... Done.
                "pois"."Rutland" ... Done.
                "traffic"."Rutland" ... Done.
                "transport"."Rutland" ... Done.
                "pofw"."Rutland" ... Done.
                "landuse"."Leeds" ... Done.
                "landuse"."Rutland" ... Done.
                "railways"."Leeds" ... Done.
                "railways"."Rutland" ... Done.
                "waterways"."Leeds" ... Done.
                "waterways"."Rutland" ... Done.
                "lines"."Rutland" ... Done.
                "places"."Leeds" ... Done.
                "places"."Rutland" ... Done.

            >>> # Delete 'points' and 'other_relations' of Waterloo and Victoria

            >>> subregion_tbl_names = ['Waterloo', 'Victoria']
            >>> lyr_schema_names = ['points', 'other_relations']

            >>> osmdb_test.drop_subregion_table(subregion_tbl_names, lyr_schema_names,
            ...                                 verbose=True)
            Confirmed to drop the following tables:
                "Waterloo" and
                "Victoria"
              from the following schemas:
                "points" and
                "other_relations"
              at postgres:***@localhost:5432/osmdb_test
            ? [No]|Yes: yes
            Dropping ...
                "points"."Victoria" ... Done.
                "points"."Waterloo" ... Done.
                "other_relations"."Victoria" ... Done.
                "other_relations"."Waterloo" ... Done.

            >>> # Delete the database 'osmdb_test'
            >>> osmdb_test.PostgreSQL.drop_database(verbose=True)
            Confirmed to drop the database "osmdb_test" from postgres:***@...?
             [No]|Yes: yes
            Dropping the database "osmdb_test" ... Done.
        """

        existing_schemas = [
            x for x in sqlalchemy.engine.reflection.Inspector.from_engine(
                self.PostgreSQL.engine).get_schema_names()
            if x != 'public' and x != 'information_schema']
        # existing_schemas.sort()

        table_names_ = [
            self.get_table_name_for_subregion(tbl_name, table_named_as_subregion)
            for tbl_name in (
                [subregion_table_names] if isinstance(subregion_table_names, str)
                else subregion_table_names)]
        table_names_.sort()

        schema_names_ = validate_schema_names(schema_names, schema_named_as_layer)
        schema_names_.sort()
        if not schema_names_:
            table_list = list(itertools.product(existing_schemas, table_names_))
            schema_names_ = list(set(
                s for s, t in table_list
                if self.subregion_table_exists(
                    t, s, table_named_as_subregion, schema_named_as_layer)))

        if not schema_names_:
            print("None of the data exists.")

        else:
            _, schemas_msg = self.PostgreSQL.printing_messages_for_multi_names(
                *schema_names_, desc='schema')

            _, tbls_msg = self.PostgreSQL.printing_messages_for_multi_names(
                *table_names_, desc='table')

            if confirmed("Confirmed to drop the following {}  "
                         "from the following {}  at {}\n?".format(
                    tbls_msg, schemas_msg, self.PostgreSQL.address),
                    confirmation_required=confirmation_required):

                table_list_ = list(itertools.product(schema_names_, table_names_))

                print("Dropping ... ") if verbose else ""
                for schema, table in table_list_:
                    table_ = f'"{schema}"."{table}"'
                    if not self.PostgreSQL.table_exists(table, schema):
                        # schema.table does not exist
                        print(f"\t{table_} does not exist. ") if verbose == 2 else ""
                    else:
                        print(f"\t{table_}", end=" ... ") if verbose else ""
                        try:
                            self.PostgreSQL.engine.execute(
                                'DROP TABLE IF EXISTS {} CASCADE;'.format(table_))
                            print("Done. ") if verbose else ""
                        except Exception as e:
                            print("Failed. {}".format(e))


# class GeoFabrikIOS:
#     """
#     A class representation of a tool for storage of Geofabrik data extracts with PostgreSQL.
#     """
#
#     def __init__(self):
#         """
#         Constructor method.
#         """
#         self.Downloader = GeofabrikDownloader()
#         self.Reader = GeofabrikReader()
#         self.Name = copy.copy(self.Downloader.Name)
#         self.URL = copy.copy(self.Downloader.URL)
#
#
# class BBBikeIOS:
#     """
#     A class representation of a tool for storage of BBBike data extracts with PostgreSQL.
#     """
#
#     def __init__(self):
#         """
#         Constructor method.
#         """
#         self.Downloader = BBBikeDownloader()
#         self.Reader = BBBikeReader()
#         self.Name = copy.copy(self.Downloader.Name)
#         self.URL = copy.copy(self.Downloader.URL)
