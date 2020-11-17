.. _pydriosm-quick-start:

===========
Quick start
===========

For a demonstration of how how pydriosm works with `OpenStreetMap`_ (OSM) data, this part of the documentation provides a quick guide with some practical examples of using the package to download, parse and store the OSM data.

.. note::

    - All the data for this quick-start tutorial will be downloaded and saved to a directory named "tests" (which will be created if it does not exist) at the current working directory as we move from one code block to another.

    - The downloaded data and those being generated during the tutorial will all be deleted from the "tests" directory; a manual confirmation will be prompted at the end of the tutorial to determine whether the "tests" folder should remain.

|

.. _qs-download-data:

Download data
=============

The current release version of the package works mainly for the OSM data extracts that is available for free download from `Geofabrik`_ and `BBBike`_ download servers.

To start with, we could use the class :py:class:`GeofabrikDownloader<pydriosm.downloader.GeofabrikDownloader>` (see also :ref:`pydriosm.downloader<downloader>`) to get a sample from the free `Geofabrik`_ download server.

.. code-block:: python

    >>> # from pydriosm.downloader import GeofabrikDownloader
    >>> from pydriosm import GeofabrikDownloader

    >>> geofabrik_downloader = GeofabrikDownloader()

To explore what data is available for download, we may check out a download catalogue by using the method :py:meth:`.get_download_catalogue()<pydriosm.downloader.GeofabrikDownloader.get_download_catalogue>` :

.. code-block:: python

    >>> geofabrik_download_catalogue = geofabrik_downloader.get_download_catalogue()

    >>> # Column names
    >>> print(geofabrik_download_catalogue.columns.tolist())
    ['Subregion', 'SubregionURL', '.osm.pbf', '.osm.pbf.Size', '.shp.zip', '.osm.bz2']

    >>> print(geofabrik_download_catalogue.head())
          Subregion  ...                                           .osm.bz2
    0       Algeria  ...  http://download.geofabrik.de/africa/algeria-la...
    1        Angola  ...  http://download.geofabrik.de/africa/angola-lat...
    2         Benin  ...  http://download.geofabrik.de/africa/benin-late...
    3      Botswana  ...  http://download.geofabrik.de/africa/botswana-l...
    4  Burkina Faso  ...  http://download.geofabrik.de/africa/burkina-fa...
    [5 rows x 6 columns]

If we'd like to download say the `protocolbuffer binary format`_ (PBF) data of a specific geographic region, we need to specify the name of the region and the file format (e.g. ``".pbf"``). For example, to download the PBF data of ``'London'`` and save it to a local directory named ``"tests"``:

.. code-block:: python

    >>> subregion_name = 'London'  # case-insensitive
    >>> osm_file_format = ".pbf"  # or ".osm.pbf"
    >>> download_dir = "tests"

    >>> # Download the OSM PBF data of London from Geofabrik
    >>> geofabrik_downloader.download_osm_data(subregion_name, osm_file_format,
    ...                                        download_dir, verbose=True)
    Confirm to download .osm.pbf data of the following geographic region(s):
        Greater London
    ? [No]|Yes: yes
    Downloading "greater-london-latest.osm.pbf" to "\tests" ...
    Done.

.. note::

    - If the data file does not exist at the specific directory, we'll be asked to confirm whether to proceed to download it, as a function parameter ``confirmation_required`` is ``True`` by default. To skip the confirmation, we just need to set it to be ``False``.

    - If the ``download_dir`` is ``None`` by default, the downloaded data file would be saved to a default data directory, which in this case should be ``"\dat_Geofabrik\Europe\Great Britain\England\"``.

Now we should be able to find the downloaded data file at ``<current working directory>\tests\`` and the filename is ``"greater-london-latest.osm.pbf"`` by default.

To retrieve the default filename and the full path to the downloaded file, we could set the parameter ``ret_download_path`` to be ``True`` when executing the method:

.. code-block:: python

    >>> path_to_london_pbf = geofabrik_downloader.download_osm_data(
    ...     subregion_name, osm_file_format, download_dir, confirmation_required=False,
    ...     ret_download_path=True)

    >>> import os

    >>> london_pbf_filename = os.path.basename(path_to_london_pbf)

    >>> print(f"Default filename: '{london_pbf_filename}'")
    Default filename: 'greater-london-latest.osm.pbf'

    >>> print(f"Current (relative) file path: '{os.path.relpath(path_to_london_pbf)}'")
    Current (relative) file path: 'tests\greater-london-latest.osm.pbf'

Alternatively, we could also make use of the method :py:meth:`.get_default_path_to_osm_file()<pydriosm.downloader.GeofabrikDownloader.get_default_path_to_osm_file>` to get the default path to the data file (even when it does not exist):

.. code-block:: python

    >>> london_pbf_filename, default_path_to_london_pbf = \
    ...     geofabrik_downloader.get_default_path_to_osm_file(subregion_name, osm_file_format)

    >>> print(f"Default filename: '{london_pbf_filename}'")
    Default filename: 'greater-london-latest.osm.pbf'

    >>> from pyhelpers.dir import cd

    >>> path_to_london_pbf = cd(download_dir, london_pbf_filename)

    >>> print(f"Current (relative) file path: '{os.path.relpath(path_to_london_pbf)}'")
    Current (relative) file path: tests\greater-london-latest.osm.pbf

In addition, we can also download data of multiple (sub)regions at one go. For example, to download PBF data of three different regions, including ``'Rutland'``, ``'West Yorkshire'`` and ``'West Midlands'`` (where we set ``confirmation_required=False`` to waive the requirement of confirmation to proceed to download the data):

.. code-block:: python

    >>> subregion_names = ['Rutland', 'West Yorkshire', 'West Midlands']

    >>> paths_to_pbf = geofabrik_downloader.download_osm_data(
    ...     subregion_names, osm_file_format, download_dir, ret_download_path=True)
    ...     verbose=True)
    Confirm to download .osm.pbf data of the following geographic region(s):
        Rutland
        West Yorkshire
        West Midlands
    ? [No]|Yes: yes
    Downloading "rutland-latest.osm.pbf" to "\tests" ...
    Done.
    Downloading "west-yorkshire-latest.osm.pbf" to "\tests" ...
    Done.
    Downloading "west-midlands-latest.osm.pbf" to "\tests" ...
    Done.

    >>> type(path_to_pbf)
    <class 'list'>

    >>> for path_to_pbf in paths_to_pbf:
    ...     print(f"'{os.path.relpath(path_to_pbf)}'")
    'tests\rutland-latest.osm.pbf'
    'tests\west-yorkshire-latest.osm.pbf'
    'tests\west-midlands-latest.osm.pbf'

|

.. _qs-read-parse-data:

Read/parse data
===============

To read/parse any of the downloaded data files above, we could use the class :py:class:`GeofabrikReader<pydriosm.reader.GeofabrikReader>` (see also :ref:`pydriosm.reader<reader>`).

.. code-block:: python

    >>> # from pydriosm.reader import GeofabrikReader
    >>> from pydriosm import GeofabrikReader

    >>> geofabrik_reader = GeofabrikReader()

.. _qs-pbf-data:

PBF data (.pbf / .osm.pbf)
--------------------------

To read the PBF data, we can use the method :py:meth:`.read_osm_pbf()<pydriosm.reader.GeofabrikReader.read_osm_pbf>`, whose parser depends largely on `GDAL/OGR <https://pypi.org/project/GDAL/>`_. Also check out the function :py:func:`parse_osm_pbf()<pydriosm.reader.GeofabrikReader.parse_osm_pbf>` for more details.

Now, let's try to read the PBF data of Rutland:

.. code-block:: python

    >>> subregion_name = 'Rutland'
    >>> data_dir = download_dir  # "tests"

    >>> rutland_pbf_raw = geofabrik_reader.read_osm_pbf(subregion_name, data_dir)

    >>> type(rutland_pbf_raw)
    <class 'dict'>

``rutland_pbf_raw`` is in `dict`_ type and has five keys: ``'points'``, ``'lines'``, ``'multilinestrings'``, ``'multipolygons'`` and ``'other_relations'``, corresponding to the names of the five different layers of the PBF data.

Check out the **'points'** layer:

.. code-block:: python


    >>> rutland_pbf_points = rutland_pbf_raw['points']

    >>> print(rutland_points.head())
                                                  points
    0  {"type": "Feature", "geometry": {"type": "Poin...
    1  {"type": "Feature", "geometry": {"type": "Poin...
    2  {"type": "Feature", "geometry": {"type": "Poin...
    3  {"type": "Feature", "geometry": {"type": "Poin...
    4  {"type": "Feature", "geometry": {"type": "Poin...

Each row of ``rutland_pbf_points`` is textual `GeoJSON`_ data, which is a nested dictionary.

.. code-block:: python

    >>> import json

    >>> rutland_pbf_points_0 = rutland_pbf_points['points'][0]
    >>> type(rutland_pbf_points_0)
    <class 'str'>

    >>> rutland_pbf_points_0_ = json.loads(rutland_pbf_points_0)
    >>> type(rutland_pbf_points_0_)
    <class 'dict'>

    >>> print(list(rutland_pbf_points_0_.keys()))
    ['type', 'geometry', 'properties', 'id']

Below are charts (:numref:`points` - :numref:`other_relations`) illustrating the different geometry types and structures (i.e. all keys within the corresponding GeoJSON data) for each layer:

.. figure:: _images/Point.*
    :name: points
    :align: center
    :width: 85%

    Type of the geometry object and keys within the nested dictionary of ``'points'``


.. figure:: _images/LineString.*
    :name: lines
    :align: center
    :width: 85%

    Type of the geometry object and keys within the nested dictionary of ``'lines'``


.. figure:: _images/MultiLineString.*
    :name: multilinestrings
    :align: center
    :width: 85%

    Type of the geometry object and keys within the nested dictionary of ``'multilinestrings'``


.. figure:: _images/MultiPolygon.*
    :name: multipolygons
    :align: center
    :width: 85%

    Type of the geometry object and keys within the nested dictionary of ``'multipolygons'``


.. figure:: _images/GeometryCollection.*
    :name: other_relations
    :align: center
    :width: 85%

    Type of the geometry object and keys within the nested dictionary of ``'other_relations'``


.. _parse_raw_feat:

If we set ``parse_raw_feat`` (which defaults to ``False``) to be ``True`` when reading the PBF data, we can also parse the GeoJSON record to obtain data of 'visually' (though not virtually) higher level of granularity:

.. code-block:: python

    >>> rutland_pbf_parsed = geofabrik_reader.read_osm_pbf(subregion_name, data_dir,
    ...                                                    parse_raw_feat=True)

    >>> rutland_pbf_parsed_points = rutland_pbf_parsed['points']

    >>> print(rutland_pbf_parsed_points.head())
             id               coordinates  ... man_made                    other_tags
    0    488432  [-0.5134241, 52.6555853]  ...     None               "odbl"=>"clean"
    1    488658  [-0.5313354, 52.6737716]  ...     None                          None
    2  13883868  [-0.7229332, 52.5889864]  ...     None                          None
    3  14049101  [-0.7249922, 52.6748223]  ...     None  "traffic_calming"=>"cushion"
    4  14558402  [-0.7266686, 52.6695051]  ...     None      "direction"=>"clockwise"
    [5 rows x 12 columns]

.. note::

    - The data can be further transformed/parsed through two more parameters, ``transform_geom`` and ``transform_other_tags``, both of which default to ``False``.

    - The method :py:meth:`.read_osm_pbf()<pydriosm.reader.GeofabrikReader.read_osm_pbf>` may take dozens of minutes or longer to parse large-size PBF data file. If the size of a data file is greater than a specified ``chunk_size_limit`` (which defaults to ``50`` MB), the data will be parsed in a chunk-wise manner.

    - If only the name of a geographic region is provided, e.g. ``rutland_pbf = geofabrik_reader.read_osm_pbf(subregion_name='London')``, the function will go to look for the data file at the default file path. Otherwise, we must specify ``data_dir`` where the data file is located.

    - If the data file does not exist at the default or a specified directory, the function will try to download it first. By default, a manual confirmation of downloading the data is required. To waive the requirement, set ``download_confirmation_required=False``.

    - If ``pickle_it=True``, the parsed data will be saved as a `Pickle`_ file. The function will try to load the `Pickle`_ file next time when we run it, provided that ``update=False`` (default); if ``update=True``, the function will try to download and parse the latest version of the data file.


.. _qs-shp-zip-data:

Shapefiles (.shp.zip / .shp)
-----------------------------

To read shapefile data, we can use the method :py:meth:`.read_shp_zip()<pydriosm.reader.GeofabrikReader.read_shp_zip>`, which depends largely on `pyshp`_ or `GeoPandas`_.

For example, let's try to read the 'railways' layer of the shapefile data of London:

.. code-block:: python

    >>> subregion_name = 'London'
    >>> layer_name = 'railways'  # if layer_name=None (default), all layers will be included

    >>> london_shp = geofabrik_reader.read_shp_zip(subregion_name, layer_names=layer_name,
    ...                                            feature_names=None, data_dir=data_dir)
    Confirm to download .shp.zip data of the following geographic region(s):
        Greater London
    ? [No]|Yes: yes
    Downloading "greater-london-latest-free.shp.zip" to "\tests" ...
    Done.
    Extracting from "greater-london-latest-free.shp.zip" the following layer(s):
        'railways'
    to "\tests\greater-london-latest-free-shp" ...
    In progress ... Done.

``london_shp`` is in `dict`_ type, with the default ``layer_name`` being its key.

.. code-block:: python

    >>> london_railways_shp = london_shp[layer_name]

    >>> print(london_railways_shp.head())
       osm_id  code  ... tunnel                                           geometry
    0   30804  6101  ...      F    LINESTRING (0.00486 51.62793, 0.00620 51.62927)
    1  101298  6103  ...      F  LINESTRING (-0.22496 51.49354, -0.22507 51.494...
    2  101486  6103  ...      F  LINESTRING (-0.20555 51.51954, -0.20514 51.519...
    3  101511  6101  ...      F  LINESTRING (-0.21189 51.52419, -0.21079 51.523...
    4  282898  6103  ...      F  LINESTRING (-0.18626 51.61591, -0.18687 51.61384)
    [5 rows x 8 columns]

.. note::

    - The parameter ``feature_names`` is related to ``'fclass'`` in ``london_railways_shp``. We can specify one feature name (or multiple feature names) to get a subset of ``london_railways_shp``.

    - Similar to :py:meth:`.read_osm_pbf()<pydriosm.reader.GeofabrikReader.read_osm_pbf>`, if the method :py:meth:`.read_shp_zip()<pydriosm.reader.GeofabrikReader.read_shp_zip>` could not find the target *.shp* file at the default or specified directory (i.e. ``data_dir``), it will try to extract the *.shp* file from the *.shp.zip* file (or download the *.shp.zip* file first if it does not exist, in which case a confirmation to proceed is by default required as ``download_confirmation_required=True``).

    - If we'd like to delete the *.shp* files and/or the downloaded data file (ending with *.shp.zip*), set the parameters ``rm_extracts=True`` and/or ``rm_shp_zip=True``.

.. _qs-merge-subregion-layer-shp:

In addition, we can use the method :py:meth:`.merge_subregion_layer_shp()<pydriosm.reader.GeofabrikReader.merge_subregion_layer_shp>` to merge multiple shapefiles of different subregions over a specific layer.

For example, to merge the 'railways' layer of London and Kent:

.. code-block:: python

    >>> layer_name = 'railways'
    >>> subregion_names = ['London', 'Kent']

    >>> path_to_merged_shp = geofabrik_reader.merge_subregion_layer_shp(
    ...     layer_name, subregion_names, data_dir, verbose=True, ret_merged_shp_path=True)
    Confirm to download .shp.zip data of the following geographic region(s):
        Greater London
        Kent
    ? [No]|Yes: yes
    "greater-london-latest-free.shp.zip" of Greater London is already available at "tests".
    Downloading "kent-latest-free.shp.zip" to "\tests" ...
    Done.
    Extracting from "greater-london-latest-free.shp.zip" the following layer(s):
        'railways'
    to "\tests\greater-london-latest-free-shp" ...
    In progress ... Done.
    Extracting from "kent-latest-free.shp.zip" the following layer(s):
        'railways'
    to "\tests\kent-latest-free-shp" ...
    In progress ... Done.
    Merging the following shapefiles:
        "greater-london_gis_osm_railways_free_1.shp"
        "kent_gis_osm_railways_free_1.shp"
    In progress ... Done.
    Find the merged .shp file(s) at "\tests\greater-london_kent_railways".

    >>> print(os.path.relpath(path_to_merged_shp))
    tests\greater-london_kent_railways\greater-london_kent_railways.shp

For more details, also check out the functions :py:func:`merge_shps()<pydriosm.reader.merge_shps>` and :py:func:`merge_layer_shps()<pydriosm.reader.merge_layer_shps>` (see also :ref:`pydriosm.reader<reader>`).

|

.. _qs-import-fetch-data:

Import and fetch data with a PostgreSQL server
==============================================

Beyond downloading and reading OSM data, the package further provides a module :ref:`pydriosm.ios<ios>` for communicating with `PostgreSQL`_ server, that is, to import the OSM data into, and fetch it from, PostgreSQL databases.

To establish a connection with the server, we need to specify the username, password, host address of a PostgreSQL server and name of a database. For example:

.. code-block:: python

    >>> from pydriosm import PostgresOSM

    >>> host = 'localhost'
    >>> port = 5432
    >>> username = 'postgres'
    >>> password = None  # We need to type it in manually if `None`
    >>> database_name = 'osmdb_test'

    >>> # Create an instance of a running PostgreSQL server
    >>> osmdb_test = PostgresOSM(host, port, username, password, database_name)
    Password (postgres@localhost:5432): ***
    Connecting postgres:***@localhost:5432/osmdb_test ... Successfully.

.. _qs-note-on-ios-data-source:

.. note::

    - If we don't specify a password (for creating the instance ``osmdb_test``) as the parameter ``password`` is ``None`` by default, we'll be asked to manually type in the password to the PostgreSQL server.

    - The class :py:class:`PostgresOSM<pydriosm.ios.PostgresOSM>` has incorporated all available classes from the modules: :py:mod:`downloader<downloader>` and :py:mod:`pydriosm.reader<reader>` as properties. In the case of the above instance, ``osmdb_test.Downloader`` is equivalent to :py:class:`GeofabrikDownloader<pydriosm.downloader.GeofabrikDownloader>`, as the parameter ``data_source`` is ``'Geofabrik'`` by default.

    - To relate the instance ``osmdb_test`` to 'BBBike' data, we could 1) recreate an instance by setting ``data_source='BBBike'``; or 2) set ``osmdb_test.DataSource='BBBike'``


.. _qs-import-the-data-to-the-database:

Import data into the database
-----------------------------

To import any of the above OSM data to a database in the connected PostgreSQL server, we can use the method :py:meth:`.import_osm_data()<pydriosm.ios.PostgresOSM.import_osm_data>` or :py:meth:`.import_subregion_osm_pbf()<pydriosm.ios.PostgresOSM.import_subregion_osm_pbf>`.

For example, let's now try to import ``rutland_pbf_parsed`` that we have obtained from :ref:`PBF data (.osm.pbf / .pbf)<qs-pbf-data>`:

.. code-block:: python

    >>> subregion_name = 'Rutland'

    >>> osmdb_test.import_osm_data(rutland_pbf_parsed, table_name=subregion_name,
    ...                            verbose=True)
    Importing data into "Rutland" at postgres:***@localhost:5432/osmdb_test ...
        points ... done: 4195 features.
        lines ... done: 7405 features.
        multilinestrings ... done: 53 features.
        multipolygons ... done: 6190 features.
        other_relations ... done: 13 features.

.. note::

    The parameter ``schema_names`` is ``None`` by default, meaning that we are going to import all of the five layers of the PBF data into the database.

In the example above, five schemas, including 'points', 'lines', 'multilinestrings', 'multipolygons' and 'other_relations' are, if they do not exist, created in the database 'osmdb_test'. Each of the schemas corresponds to a key (i.e. name of a layer) of ``rutland_pbf_parsed`` (as illustrated in :numref:`pbf_schemas_example`); and the data of each layer is imported into a table named as 'Rutland' under the corresponding schema (as illustrated in :numref:`pbf_table_example`).

.. figure:: _images/pbf_schemas_example.*
    :name: pbf_schemas_example
    :width: 45%

    An illustration of schemas for importing OSM PBF data into a PostgreSQL database


.. figure:: _images/pbf_table_example.*
    :name: pbf_table_example
    :width: 42%

    An illustration of table name for storing the 'lines' layer of the OSM PBF data of Rutland


.. _qs-fetch-data-from-the-database:

Fetch data from the database
----------------------------

To fetch all of the imported PBF data of Rutland, we can use the method :py:meth:`.fetch_osm_data()<pydriosm.ios.PostgresOSM.fetch_osm_data>`:

.. code-block:: python

    >>> rutland_pbf_parsed_ = osmdb_test.fetch_osm_data(subregion_name, layer_names=None,
    ...                                                 decode_wkt=True)

We could find that ``rutland_pbf_parsed_`` is an equivalent of ``rutland_pbf_parsed``:

.. code-block:: python

    >>> check_equivalence = all(
    ...     rutland_pbf_parsed[lyr_name].equals(rutland_pbf_parsed_[lyr_name])
    ...     for lyr_name in rutland_pbf_parsed_.keys())

    >>> print(f"`rutland_pbf_parsed_` equals `rutland_pbf_parsed`: {check_equivalence}"))
    `rutland_pbf_parsed_` equals `rutland_pbf_parsed`: True

.. note::

    - The parameter ``layer_names`` is ``None`` by default, meaning that we're going to fetch data of all layers available from the database.

    - The data stored in the database was parsed by the :py:meth:`geofabrik_reader.read_osm_pbf()<pydriosm.reader.GeofabrikReader.read_osm_pbf>` given ``parse_raw_feat=True`` (see :ref:`above<parse_raw_feat>`). When it is being imported in the PostgreSQL server, the data type of the column 'coordinates' is converted from `list`_ to `str`_. Therefore, in the above example of using the method :py:meth:`.read_osm_pbf()<pydriosm.ios.PostgresOSM.read_osm_pbf>`, we set the parameter ``decode_wkt``, which defaults to ``False``, to be ``True``, so as to retrieve the same data.


.. _qs-import-fetch-layer-data:

Import/fetch data of specific layers
-------------------------------------

Of course, we can also import/fetch data of only a specific layer or multiple layers (and in a customised order). For example, let's firstly import the transport-related layers of Birmingham shapefile data.

.. note::

    'Birmingham' is not listed on the free download catalogue of Geofabrik, but that of BBBike. We need to change the data source to 'BBBike' for the instance ``osmdb_test`` (see also the :ref:`note<qs-note-on-ios-data-source>` above).

.. code-block:: python

    >>> osmdb_test.DataSource = 'BBBike'

    >>> subregion_name = 'Birmingham'

    >>> birmingham_shp = osmdb_test.Reader.read_shp_zip(subregion_name, data_dir=data_dir,
    ...                                                 verbose=True)
    Confirm to download .shp.zip data of the following geographic region(s):
        Birmingham
    ? [No]|Yes: yes
    Downloading "Birmingham.osm.shp.zip" to "\tests" ...
    Done.
    Extracting all of "Birmingham.osm.shp.zip" to "\tests" ...
    In progress ... Done.
    Parsing "\tests\Birmingham-shp\shape" ... Done.

    # Check names of layers included in the data
    >>> print(list(birmingham_shp.keys()))
    ['buildings',
     'landuse',
     'natural',
     'places',
     'points',
     'railways',
     'roads',
     'waterways']

    >>> # Import the data of 'railways', 'roads' and 'waterways'
    >>> lyr_names = ['railways', 'roads', 'waterways']
    >>> osmdb_test.import_osm_data(birmingham_shp, table_name=subregion_name,
    ...                            schema_names=lyr_names, verbose=True)
    Importing data into "Birmingham" at postgres:***@localhost:5432/osmdb_test ...
        railways ... done: 3176 features.
        roads ... done: 116939 features.
        waterways ... done: 2897 features.

To fetch only the 'railways' data of Birmingham:

.. code-block:: python

    >>> lyr_name = 'railways'

    >>> birmingham_shp_ = osmdb_test.fetch_osm_data(subregion_name, layer_names=lyr_name,
    ...                                             sort_by='osm_id')

    >>> birmingham_shp_railways_ = birmingham_shp_[lyr_name]

    >>> print(birmingham_shp_railways_.head())
        osm_id  ...                                           geometry
    0      740  ...  LINESTRING (-1.8178905 52.5700974, -1.8179287 ...
    1     2148  ...  LINESTRING (-1.8731878 52.5055513, -1.8727074 ...
    2  2950000  ...  LINESTRING (-1.8794134 52.4813762, -1.8795969 ...
    3  3491845  ...  LINESTRING (-1.7406017 52.5185831, -1.7394216 ...
    4  3981454  ...  LINESTRING (-1.7747469 52.5228419, -1.7744914 ...
    [5 rows x 4 columns]

.. note::

    The data retrieved from a PostgreSQL database may not be in the same order as it is in the database (see the test code below). However, they contain exactly the same information. We may sort the data by ``id`` (or ``osm_id``) to make a comparison.

.. code-block:: python

    >>> birmingham_shp_railways = birmingham_shp[lyr_name]

    >>> print(birmingham_shp_railways.head())
        osm_id  ...                                           geometry
    0      740  ...  LINESTRING (-1.81789 52.57010, -1.81793 52.569...
    1     2148  ...  LINESTRING (-1.87319 52.50555, -1.87271 52.505...
    2  2950000  ...  LINESTRING (-1.87941 52.48138, -1.87960 52.481...
    3  3491845  ...  LINESTRING (-1.74060 52.51858, -1.73942 52.518...
    4  3981454  ...  LINESTRING (-1.77475 52.52284, -1.77449 52.522...
    [5 rows x 4 columns]

.. note::

    ``birmingham_shp_railways`` is a `geopandas.GeoDataFrame`_  and ``birmingham_shp_railways_`` is a `pandas.DataFrame`_. We may have to transform the format of either one to the other before making a comparison between them.

.. code-block:: python

    >>> import geopandas as gpd

    >>> check_equivalence =
    ...     gpd.GeoDataFrame(birmingham_shp_railways_).equals(birmingham_shp_railways)

    >>> print(f"`birmingham_shp_railways_` equals `birmingham_shp_railways`: "
    ...       f"{check_equivalence}")
    `birmingham_shp_railways_` equals `birmingham_shp_railways`: True


.. _qs-import-data-of-all-subregions:

Drop data
---------

If we would now like to drop the data of all or selected layers that have been imported for one or multiple geographic regions, we can use the method :py:meth:`.drop_subregion_table()<pydriosm.ios.PostgresOSM.drop_subregion_table>`.

For example, to drop the 'railways' data of Birmingham:

.. code-block:: python

    >>> osmdb_test.drop_subregion_table(subregion_name, lyr_name, verbose=True)
    Confirmed to drop the following table:
        "Birmingham"
      from the following schema:
        "railways"
      at postgres:***@localhost:5432/osmdb_test
    ? [No]|Yes: yes
    Dropping ...
        "railways"."Birmingham" ... Done.

To also drop the 'waterways' of Birmingham and both 'lines' and 'multilinestrings' of Rutland:

.. code-block:: python

    >>> subregion_names = ['Birmingham', 'Rutland']
    >>> lyr_names = ['waterways', 'lines', 'multilinestrings']

    >>> osmdb_test.drop_subregion_table(subregion_names, lyr_names, verbose=True)
    Confirmed to drop the following tables:
        "Birmingham" and
        "Rutland"
      from the following schemas:
        "lines",
        "multilinestrings" and
        "waterways"
      at postgres:***@localhost:5432/osmdb_test
    ? [No]|Yes: yes
    Dropping ...
        "lines"."Rutland" ... Done.
        "multilinestrings"."Rutland" ... Done.
        "waterways"."Birmingham" ... Done.

We could also easily drop the whole database 'osmdb_test' if we don't need it any more:

.. code-block:: python

    >>> osmdb_test.PostgreSQL.drop_database(verbose=True)
    Confirmed to drop the database "osmdb_test"
        from postgres:***@localhost:5432/osmdb_test?
     [No]|Yes: yes
    Dropping the database "osmdb_test" ... Done.


Clear up "the mess" in here before we move on
=============================================

To remove all the data files that have been downloaded and generated:

.. code-block:: python

    >>> from pyhelpers.dir import cd, delete_dir

    >>> list_of_data_dirs = ['Birmingham-shp', 'greater-london_kent_railways']

    >>> for dat_dir in list_of_data_dirs:
    ...     delete_dir(cd(data_dir, dat_dir), confirmation_required=False, verbose=True)
    Deleting "\tests\Birmingham-shp" ... Done.
    Deleting "\tests\greater-london_kent_railways" ... Done.

    >>> list_of_data_files = ['Birmingham.osm.shp.zip',
    ...                       'greater-london-latest.osm.pbf',
    ...                       'greater-london-latest-free.shp.zip',
    ...                       'kent-latest-free.shp.zip',
    ...                       'rutland-latest.osm.pbf',
    ...                       'west-midlands-latest.osm.pbf',
    ...                       'west-yorkshire-latest.osm.pbf']

    >>> for dat_file in list_of_data_files:
    ...     os.remove(cd(data_dir, dat_file))

    >>> # # To remove the "tests" directory
    >>> # delete_dir(cd(data_dir))

.. _`OpenStreetMap`: https://www.openstreetmap.org/
.. _`Geofabrik`: https://download.geofabrik.de/
.. _`BBBike`: https://extract.bbbike.org/
.. _`protocolbuffer binary format`: https://wiki.openstreetmap.org/wiki/PBF_Format
.. _`dict`: https://docs.python.org/3/library/stdtypes.html#dict
.. _`GeoJSON`: https://geojson.org/
.. _`Pickle`: https://docs.python.org/3/library/pickle.html#module-pickle
.. _`pyshp`: https://pypi.org/project/pyshp/
.. _`GeoPandas`: http://geopandas.org/
.. _`PostgreSQL`: https://www.postgresql.org/
.. _`list`: https://docs.python.org/3/library/stdtypes.html#list
.. _`str`: https://docs.python.org/3/library/stdtypes.html#str
.. _`geopandas.GeoDataFrame`: https://geopandas.org/reference/geopandas.GeoDataFrame.html
.. _`pandas.DataFrame`: https://pandas.pydata.org/pandas-docs/stable/reference/api/pandas.DataFrame.html

**(The end of the quick start)**

For more details, check out :ref:`Modules<modules>`.
