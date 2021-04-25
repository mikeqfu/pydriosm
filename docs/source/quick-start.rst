.. _pydriosm-quick-start:

===========
Quick start
===========

For a demonstration of how pydriosm works with `OpenStreetMap`_ (OSM) data, this part of the documentation provides a quick guide with some practical examples of using the package to download, parse and store the OSM data.

.. note::

    - All the data for this quick-start tutorial will be downloaded and saved to a directory named "tests" (which will be created if it does not exist) at the current working directory as you move from one code block to another.

    - The downloaded data and those being generated during the tutorial will all be deleted from the "tests" directory; a manual confirmation will be prompted at the end of the tutorial to determine whether the "tests" folder should remain.


.. _qs-download-data:

Download data
=============

The current release version of the package works mainly for the OSM data extracts that is available for free download from `Geofabrik`_ and `BBBike`_ download servers.

To start with, you could use the class :py:class:`GeofabrikDownloader<pydriosm.downloader.GeofabrikDownloader>` (see also :ref:`pydriosm.downloader<downloader>`) to get a sample from the free `Geofabrik`_ download server.

.. code-block:: python

    >>> from pydriosm.downloader import GeofabrikDownloader

    >>> # Create an instance for downloading the Geofabrik data extracts
    >>> geofabrik_downloader = GeofabrikDownloader()

To explore what data is available for download, you may check out a download catalogue by using the method :py:meth:`.get_download_catalogue()<pydriosm.downloader.GeofabrikDownloader.get_download_catalogue>` :

.. code-block:: python

    >>> # A download catalogue for all subregions
    >>> geofabrik_download_catalogue = geofabrik_downloader.get_download_catalogue()

    >>> # Check the column names
    >>> geofabrik_download_catalogue.columns.tolist()
    ['Subregion',
     'SubregionURL',
     '.osm.pbf',
     '.osm.pbf.Size',
     '.shp.zip',
     '.osm.bz2']

    >>> geofabrik_download_catalogue.head()
          Subregion  ...                                           .osm.bz2
    0       Algeria  ...  https://download.geofabrik.de/africa/algeria-l...
    1        Angola  ...  https://download.geofabrik.de/africa/angola-la...
    2         Benin  ...  https://download.geofabrik.de/africa/benin-lat...
    3      Botswana  ...  https://download.geofabrik.de/africa/botswana-...
    4  Burkina Faso  ...  https://download.geofabrik.de/africa/burkina-f...
    [5 rows x 6 columns]

If you'd like to download say the `protocolbuffer binary format`_ (PBF) data of a specific geographic region, you need to specify the name of the region and file format (e.g. ``".pbf"``). For example, to download the PBF data of ``'London'`` and save it to a local directory named ``"tests"``:

.. code-block:: python

    >>> subregion_name = 'London'  # case-insensitive
    >>> osm_file_format = ".pbf"  # or ".osm.pbf"
    >>> download_dir = "tests"  # a download directory

    >>> # Download the OSM PBF data of London from Geofabrik
    >>> geofabrik_downloader.download_osm_data(subregion_name, osm_file_format,
    ...                                        download_dir, verbose=True)
    To download .osm.pbf data of the following geographic region(s):
        Greater London
    ? [No]|Yes: yes
    Downloading "greater-london-latest.osm.pbf" to "tests\" ... Done.

.. note::

    - If the data file does not exist at the specific directory, you'll be asked to confirm whether to proceed to download it, as a function parameter ``confirmation_required`` is ``True`` by default. To skip the confirmation, you just need to set it to be ``False``.

    - If the ``download_dir`` is ``None`` by default, the downloaded data file would be saved to a default data directory, which in this case should be ``"osm_geofabrik\Europe\Great Britain\England\"``.

Now you should be able to find the downloaded data file at "*<current working directory>\tests\*", and the filename is "*greater-london-latest.osm.pbf*" by default.

To retrieve the default filename and the full path to the downloaded file, you could set the parameter ``ret_download_path`` to be ``True`` when executing the method:

.. code-block:: python

    >>> path_to_london_pbf = geofabrik_downloader.download_osm_data(
    ...     subregion_name, osm_file_format, download_dir, confirmation_required=False,
    ...     ret_download_path=True)

    >>> import os

    >>> # Default filename:
    >>> london_pbf_filename = os.path.basename(path_to_london_pbf)
    >>> print(f"Default filename: \"{london_pbf_filename}\"")
    Default filename: "greater-london-latest.osm.pbf"

    >>> # Relative file path:
    >>> print(f"Current (relative) file path: \"{os.path.relpath(path_to_london_pbf)}\"")
    Current (relative) file path: "tests\greater-london-latest.osm.pbf"

Alternatively, you could also make use of the method :py:meth:`.get_default_path_to_osm_file()<pydriosm.downloader.GeofabrikDownloader.get_default_path_to_osm_file>` to get the default path to the data file (even when it does not exist):

.. code-block:: python

    >>> london_pbf_filename, default_path_to_london_pbf = \
    ...     geofabrik_downloader.get_default_path_to_osm_file(subregion_name, osm_file_format)

    >>> print(f"Default filename: \"{london_pbf_filename}\"")
    Default filename: "greater-london-latest.osm.pbf"

    >>> path_to_london_pbf = os.path.join(download_dir, london_pbf_filename)
    >>> print(f"Current (relative) file path: \"{os.path.relpath(path_to_london_pbf)}\"")
    Current (relative) file path: "tests\greater-london-latest.osm.pbf"

In addition, you can also download data of multiple (sub)regions at one go. For example, to download PBF data of three different regions, including ``'Rutland'``, ``'West Yorkshire'`` and ``'West Midlands'`` (where you can set ``confirmation_required=False`` to waive the requirement of confirmation to proceed to download the data):

.. code-block:: python

    >>> subregion_names = ['Rutland', 'West Yorkshire', 'West Midlands']

    >>> paths_to_pbf = geofabrik_downloader.download_osm_data(
    ...     subregion_names, osm_file_format, download_dir, ret_download_path=True,
    ...     verbose=True)
    To download .osm.pbf data of the following geographic region(s):
        Rutland
        West Yorkshire
        West Midlands
    ? [No]|Yes: yes
    Downloading "rutland-latest.osm.pbf" to "tests\" ... Done.
    Downloading "west-yorkshire-latest.osm.pbf" to "tests\" ... Done.
    Downloading "west-midlands-latest.osm.pbf" to "tests\" ... Done.

    >>> type(paths_to_pbf)
    list

    >>> for path_to_pbf in paths_to_pbf:
    ...     print(f"\"{os.path.relpath(path_to_pbf)}\"")
    "tests\rutland-latest.osm.pbf"
    "tests\west-yorkshire-latest.osm.pbf"
    "tests\west-midlands-latest.osm.pbf"


.. _qs-read-parse-data:

Read/parse data
===============

To read/parse any of the downloaded data files above, you could use the class :py:class:`GeofabrikReader<pydriosm.reader.GeofabrikReader>` (see also :ref:`pydriosm.reader<reader>`).

.. code-block:: python

    >>> # Create an instance for reading the downloaded Geofabrik data extracts
    >>> from pydriosm.reader import GeofabrikReader

    >>> geofabrik_reader = GeofabrikReader()

.. _qs-pbf-data:

PBF data (.pbf / .osm.pbf)
--------------------------

To read the PBF data, you can use the method :py:meth:`.read_osm_pbf()<pydriosm.reader.GeofabrikReader.read_osm_pbf>`, whose parser depends largely on `GDAL/OGR <https://pypi.org/project/GDAL/>`_. Also check out the function :py:func:`parse_osm_pbf()<pydriosm.reader.GeofabrikReader.parse_osm_pbf>` for more details.

Now, let's try to read the PBF data of Rutland:

.. code-block:: python

    >>> subregion_name = 'Rutland'
    >>> data_dir = download_dir  # "tests"

    >>> rutland_pbf_raw = geofabrik_reader.read_osm_pbf(subregion_name, data_dir)

    >>> type(rutland_pbf_raw)
    dict

``rutland_pbf_raw`` is in `dict`_ type and has five keys: ``'points'``, ``'lines'``, ``'multilinestrings'``, ``'multipolygons'`` and ``'other_relations'``, corresponding to the names of the five different layers of the PBF data.

Check out the **'points'** layer:

.. code-block:: python

    >>> rutland_pbf_points = rutland_pbf_raw['points']

    >>> rutland_pbf_points.head()
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
    str

    >>> # Decode the str-type data
    >>> rutland_pbf_points_0_ = json.loads(rutland_pbf_points_0)
    >>> type(rutland_pbf_points_0_)
    dict

    >>> list(rutland_pbf_points_0_.keys())
    ['type', 'geometry', 'properties', 'id']

    >>> rutland_pbf_points_0_
    {'type': 'Feature',
     'geometry': {'type': 'Point', 'coordinates': [-0.5134241, 52.6555853]},
     'properties': {'osm_id': '488432',
      'name': None,
      'barrier': None,
      'highway': None,
      'ref': None,
      'address': None,
      'is_in': None,
      'place': None,
      'man_made': None,
      'other_tags': '"odbl"=>"clean"'},
     'id': 488432}

The charts (:numref:`points` - :numref:`other_relations`) below illustrate the different geometry types and structures (i.e. all keys within the corresponding GeoJSON data) for each layer:

.. figure:: _images/Point.*
    :name: points
    :align: center
    :width: 85%

    Type of the geometry object and keys within the nested dictionary of ``'points'``.


.. figure:: _images/LineString.*
    :name: lines
    :align: center
    :width: 85%

    Type of the geometry object and keys within the nested dictionary of ``'lines'``.


.. figure:: _images/MultiLineString.*
    :name: multilinestrings
    :align: center
    :width: 85%

    Type of the geometry object and keys within the nested dictionary of ``'multilinestrings'``.


.. figure:: _images/MultiPolygon.*
    :name: multipolygons
    :align: center
    :width: 85%

    Type of the geometry object and keys within the nested dictionary of ``'multipolygons'``.


.. figure:: _images/GeometryCollection.*
    :name: other_relations
    :align: center
    :width: 85%

    Type of the geometry object and keys within the nested dictionary of ``'other_relations'``.


.. _parse_raw_feat:

If you set ``parse_raw_feat`` (which defaults to ``False``) to be ``True`` when reading the PBF data, you can also parse the GeoJSON record to obtain data of 'visually' (though not virtually) higher level of granularity:

.. code-block:: python

    >>> rutland_pbf_parsed = geofabrik_reader.read_osm_pbf(subregion_name, data_dir,
    ...                                                    parse_raw_feat=True,
    ...                                                    verbose=True)
    Parsing "\tests\rutland-latest.osm.pbf" ... Done.

    >>> # Data of the parsed 'points' layer
    >>> rutland_pbf_parsed_points = rutland_pbf_parsed['points']

    >>> rutland_pbf_parsed_points.head()
             id               coordinates  ... man_made                    other_tags
    0    488432  [-0.5134241, 52.6555853]  ...     None               "odbl"=>"clean"
    1    488658  [-0.5313354, 52.6737716]  ...     None                          None
    2  13883868  [-0.7229332, 52.5889864]  ...     None                          None
    3  14049101  [-0.7249816, 52.6748426]  ...     None  "traffic_calming"=>"cushion"
    4  14558402  [-0.7266581, 52.6695058]  ...     None      "direction"=>"clockwise"
    [5 rows x 12 columns]

.. note::

    - The data can be further transformed/parsed through two more parameters, ``transform_geom`` and ``transform_other_tags``, both of which default to ``False``.

    - The method :py:meth:`.read_osm_pbf()<pydriosm.reader.GeofabrikReader.read_osm_pbf>` may take dozens of minutes or longer to parse large-size PBF data file. If the size of a data file is greater than a specified ``chunk_size_limit`` (which defaults to ``50`` MB), the data will be parsed in a chunk-wise manner.

    - If only the name of a geographic region is provided, e.g. ``rutland_pbf = geofabrik_reader.read_osm_pbf(subregion_name='London')``, the function will go to look for the data file at the default file path. Otherwise, you must specify ``data_dir`` where the data file is located.

    - If the data file does not exist at the default or a specified directory, the function will try to download it first. By default, a manual confirmation of downloading the data is required. To waive the requirement, set ``download_confirmation_required=False``.

    - If ``pickle_it=True``, the parsed data will be saved as a `Pickle`_ file. The function will try to load the `Pickle`_ file next time when you run it, provided that ``update=False`` (default); if ``update=True``, the function will try to download and parse the latest version of the data file.


.. _qs-shp-zip-data:

Shapefiles (.shp.zip / .shp)
-----------------------------

To read shapefile data, you can use the method :py:meth:`.read_shp_zip()<pydriosm.reader.GeofabrikReader.read_shp_zip>`, which depends on `pyshp`_ (or optionally, `GeoPandas`_, which is not required for the installation of PyDriosm).

For example, let's try to read the 'railways' layer of the shapefile data of London:

.. code-block:: python

    >>> subregion_name = 'London'
    >>> layer_name = 'railways'  # if layer_name=None (default), all layers will be included

    >>> london_shp = geofabrik_reader.read_shp_zip(subregion_name, layer_names=layer_name,
    ...                                            feature_names=None, data_dir=data_dir,
    ...                                            verbose=True)
    To download .shp.zip data of the following geographic region(s):
        Greater London
    ? [No]|Yes: yes
    Downloading "greater-london-latest-free.shp.zip" to "tests\" ... Done.
    Extracting the following layer(s):
        'railways'
    from "tests\greater-london-latest-free.shp.zip" ...
    to "tests\greater-london-latest-free-shp\"
    Done.

``london_shp`` is in `dict`_ type, with the default ``layer_name`` being its key.

.. code-block:: python

    >>> london_railways_shp = london_shp[layer_name]

    >>> london_railways_shp.head()
       osm_id  code  ...                                        coordinates shape_type
    0   30804  6101  ...  [(0.0048644, 51.6279262), (0.0061979, 51.62926...          3
    1  101298  6103  ...  [(-0.2249632, 51.4935445), (-0.2250662, 51.494...          3
    2  101486  6103  ...  [(-0.2055497, 51.5195429), (-0.2051377, 51.519...          3
    3  101511  6101  ...  [(-0.2119027, 51.5241906), (-0.2108059, 51.523...          3
    4  282898  6103  ...  [(-0.1862586, 51.6159083), (-0.1868721, 51.613...          3
    [5 rows x 9 columns]

.. note::

    - The parameter ``feature_names`` is related to ``'fclass'`` in ``london_railways_shp``. You can specify one feature name (or multiple feature names) to get a subset of ``london_railways_shp``.

    - Similar to the method :py:meth:`.read_osm_pbf()<pydriosm.reader.GeofabrikReader.read_osm_pbf>`, if :py:meth:`.read_shp_zip()<pydriosm.reader.GeofabrikReader.read_shp_zip>` could not find the target *.shp* file at the default or specified directory (i.e. ``data_dir``), it will try to extract the *.shp* file from the *.shp.zip* file (or download the *.shp.zip* file first if it does not exist, in which case a confirmation to proceed is by default required as ``download_confirmation_required=True``).

    - If you'd like to delete the *.shp* files and/or the downloaded data file (ending with *.shp.zip*), set the parameters ``rm_extracts=True`` and/or ``rm_shp_zip=True``.

.. _qs-merge-subregion-layer-shp:

In addition, you can use the method :py:meth:`.merge_subregion_layer_shp()<pydriosm.reader.GeofabrikReader.merge_subregion_layer_shp>` to merge multiple shapefiles of different subregions over a specific layer.

For example, to merge the 'railways' layer of London and Kent:

.. code-block:: python

    >>> layer_name = 'railways'
    >>> subregion_names = ['London', 'Kent']

    >>> path_to_merged_shp = geofabrik_reader.merge_subregion_layer_shp(
    ...     subregion_names, layer_name, data_dir, verbose=True, ret_merged_shp_path=True)
    "greater-london-latest-free.shp.zip" is already available at "tests\".
    To download .shp.zip data of the following geographic region(s):
        Kent
    ? [No]|Yes: >? yes
    Downloading "kent-latest-free.shp.zip" to "tests\" ... Done.
    Extracting the following layer(s):
        'railways'
    from "tests\greater-london-latest-free.shp.zip" ...
    to "tests\greater-london-latest-free-shp\"
    Done.
    Extracting the following layer(s):
        'railways'
    from "tests\kent-latest-free.shp.zip" ...
    to "tests\kent-latest-free-shp\"
    Done.
    Merging the following shapefiles:
        "greater-london_gis_osm_railways_free_1.shp"
        "kent_gis_osm_railways_free_1.shp"
    In progress ... Done.
    Find the merged shapefile at "tests\greater-london_kent_railways\".

    >>> # Relative path of the merged shapefile
    >>> print(os.path.relpath(path_to_merged_shp))
    tests\greater-london_kent_railways\greater-london_kent_railways.shp

For more details, also check out the functions: :py:func:`merge_shps()<pydriosm.reader.merge_shps>` and :py:func:`merge_layer_shps()<pydriosm.reader.merge_layer_shps>`.


.. _qs-import-fetch-data:

Import and fetch data with a PostgreSQL server
==============================================

In addition to downloading and reading OSM data, the package further provides a module :ref:`pydriosm.ios<ios>` for communicating with `PostgreSQL`_ server, that is, to import the OSM data into, and fetch it from, PostgreSQL databases.

To establish a connection with the server, you need to specify the username, password, host address of a PostgreSQL server and name of a database. For example:

.. code-block:: python

    >>> from pydriosm.ios import PostgresOSM

    >>> host = 'localhost'
    >>> port = 5432
    >>> username = 'postgres'
    >>> password = None  # You need to type it in manually if `None`
    >>> database_name = 'osmdb_test'

    >>> # Create an instance of a running PostgreSQL server
    >>> osmdb_test = PostgresOSM(host, port, username, password, database_name)
    Password (postgres@localhost:5432): ***
    Connecting postgres:***@localhost:5432/osmdb_test ... Successfully.

The example is illustrated in :numref:`pbf_db_example`:

.. figure:: _images/pbf_db_example.*
    :name: pbf_db_example
    :align: center
    :width: 60%

    An illustration of the database named *'osmdb_test'*.

.. _qs-note-on-ios-data-source:

.. note::

    - If you don't specify a password (for creating the instance ``osmdb_test``) as the parameter ``password`` is ``None`` by default, you'll be asked to manually type in the password to the PostgreSQL server.

    - The class :py:class:`PostgresOSM<pydriosm.ios.PostgresOSM>` has incorporated all available classes from the modules: :py:mod:`downloader<pydriosm.downloader>` and :py:mod:`reader<pydriosm.reader>` as properties. In the case of the above instance, ``osmdb_test.Downloader`` is equivalent to the class :py:class:`GeofabrikDownloader<pydriosm.downloader.GeofabrikDownloader>`, as the parameter ``data_source`` is ``'Geofabrik'`` by default.

    - To relate the instance ``osmdb_test`` to 'BBBike' data, you could: 1) recreate an instance by setting ``data_source='BBBike'``; or 2) set ``osmdb_test.DataSource`` to be ``'BBBike'``


.. _qs-import-the-data-to-the-database:

Import data into the database
-----------------------------

To import any of the above OSM data to a database in the connected PostgreSQL server, you can use the method :py:meth:`.import_osm_data()<pydriosm.ios.PostgresOSM.import_osm_data>` or :py:meth:`.import_subregion_osm_pbf()<pydriosm.ios.PostgresOSM.import_subregion_osm_pbf>`.

For example, let's now try to import ``rutland_pbf_parsed`` that you have obtained from :ref:`PBF data (.osm.pbf / .pbf)<qs-pbf-data>`:

.. code-block:: python

    >>> subregion_name = 'Rutland'

    >>> osmdb_test.import_osm_data(rutland_pbf_parsed, table_name=subregion_name, verbose=True)
    To import data into table "Rutland" at postgres:***@localhost:5432/osmdb_test
    ? [No]|Yes: yes
    Importing the data ...
        "points" ... Done: <total of rows> features.
        "lines" ... Done: <total of rows> features.
        "multilinestrings" ... Done: <total of rows> features.
        "multipolygons" ... Done: <total of rows> features.
        "other_relations" ... Done: <total of rows> features.

.. note::

    The parameter ``schema_names`` is ``None`` by default, meaning that you are going to import all the five layers of the PBF data into the database.

In the example above, five schemas, including 'points', 'lines', 'multilinestrings', 'multipolygons' and 'other_relations' are, if they do not exist, created in the database 'osmdb_test'. Each of the schemas corresponds to a key (i.e. name of a layer) of ``rutland_pbf_parsed`` (as illustrated in :numref:`pbf_schemas_example`); and the data of each layer is imported into a table named as 'Rutland' under the corresponding schema (as illustrated in :numref:`pbf_table_example`).

.. figure:: _images/pbf_schemas_example.*
    :name: pbf_schemas_example
    :align: center
    :width: 60%

    An illustration of schemas for importing OSM PBF data into a PostgreSQL database.


.. figure:: _images/pbf_table_example.*
    :name: pbf_table_example
    :align: center
    :width: 100%

    An illustration of table name for storing the *'points'* layer of the OSM PBF data of Rutland.


.. _qs-fetch-data-from-the-database:

Fetch data from the database
----------------------------

To fetch all the imported PBF data of Rutland, you can use the method :py:meth:`.fetch_osm_data()<pydriosm.ios.PostgresOSM.fetch_osm_data>`:

.. code-block:: python

    >>> rutland_pbf_parsed_ = osmdb_test.fetch_osm_data(subregion_name, layer_names=None,
    ...                                                 decode_wkt=True)

You could find that ``rutland_pbf_parsed_`` is an equivalent of ``rutland_pbf_parsed``:

.. code-block:: python

    >>> check_equivalence = all(
    ...     rutland_pbf_parsed[lyr_name].equals(rutland_pbf_parsed_[lyr_name])
    ...     for lyr_name in rutland_pbf_parsed_.keys())

    >>> print(f"`rutland_pbf_parsed_` equals `rutland_pbf_parsed`: {check_equivalence}")
    `rutland_pbf_parsed_` equals `rutland_pbf_parsed`: True

.. note::

    - The parameter ``layer_names`` is ``None`` by default, meaning that you're going to fetch data of all layers available from the database.

    - The data stored in the database was parsed by the method :py:meth:`.read_osm_pbf()<pydriosm.reader.GeofabrikReader.read_osm_pbf>` given ``parse_raw_feat=True`` (see :ref:`above<parse_raw_feat>`). When it is being imported in the PostgreSQL server, the data type of the column 'coordinates' is converted from `list`_ to `str`_. Therefore, in the above example of using the method :py:meth:`.fetch_osm_data()<pydriosm.ios.PostgresOSM.fetch_osm_data>`, the parameter ``decode_wkt`` was set to ``True`` to retrieve the same data.


.. _qs-import-fetch-layer-data:

Import/fetch specific layers of shapefile
-----------------------------------------

Of course, you can also import/fetch data of only a specific layer or multiple layers (and in a customised order). For example, let's firstly import the transport-related layers of Birmingham shapefile data.

.. note::

    'Birmingham' is not listed on the free download catalogue of Geofabrik, but that of BBBike. You need to change the data source to 'BBBike' for the instance ``osmdb_test`` (see also the :ref:`note<qs-note-on-ios-data-source>` above).

.. code-block:: python

    >>> osmdb_test.DataSource = 'BBBike'

    >>> subregion_name = 'Birmingham'

    >>> birmingham_shp = osmdb_test.Reader.read_shp_zip(subregion_name, data_dir=data_dir,
    ...                                                 verbose=True)
    To download .shp.zip data of the following geographic region(s):
        Birmingham
    ? [No]|Yes: yes
    Downloading "Birmingham.osm.shp.zip" to "tests\" ... Done.
    Extracting "tests\Birmingham.osm.shp.zip" ...
    to "tests\"
    Done.
    Parsing files at "tests\Birmingham-shp\shape\" ... Done.

    >>> type(birmingham_shp)
    dict

    >>> # Check names of layers included in the data
    >>> list(birmingham_shp.keys())
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

    >>> osmdb_test.import_osm_data(birmingham_shp, subregion_name, lyr_names, verbose=True)
    To import data into table "Birmingham" at postgres:***@localhost:5432/osmdb_test
    ? [No]|Yes: yes
    Importing the data ...
        "railways" ... Done: <total of rows> features.
        "roads" ... Done: <total of rows> features.
        "waterways" ... Done: <total of rows> features.

As illustrated in :numref:`pbf_schemas_example_2`, three schemas: 'railways', 'roads' and 'waterways' are created in the *'osmdb_test'* database for storing the data of the three shapefile layers of Birmingham.

.. figure:: _images/pbf_schemas_example_2.*
    :name: pbf_schemas_example_2
    :align: center
    :width: 60%

    An illustration of the newly created schemas for the selected layers of Birmingham shapefile data.


To fetch only the 'railways' data of Birmingham:

.. code-block:: python

    >>> lyr_name = 'railways'

    >>> birmingham_shp_ = osmdb_test.fetch_osm_data(subregion_name, layer_names=lyr_name,
    ...                                             decode_wkt=True, sort_by='osm_id')

    >>> # This is dict-type
    >>> type(birmingham_shp_)
    dict

    >>> # Data frame of the 'railways' layer
    >>> birmingham_shp_railways_ = birmingham_shp_[lyr_name]

    >>> birmingham_shp_railways_.head()
        osm_id  ... shape_type
    0      740  ...          3
    1     2148  ...          3
    2  2950000  ...          3
    3  3491845  ...          3
    4  3981454  ...          3
    [5 rows x 5 columns]

    >>> birmingham_shp_railways_.columns.tolist()
    ['osm_id', 'name', 'type', 'coordinates', 'shape_type']

.. note::

    The data retrieved from a PostgreSQL database may not be in the same order as it is in the database (see the test code below). However, they contain exactly the same information. You may sort the data by ``id`` (or ``osm_id``) to make a comparison.

.. code-block:: python

    >>> birmingham_shp_railways = birmingham_shp[lyr_name]

    >>> birmingham_shp_railways.head()
        osm_id  ... shape_type
    0      740  ...          3
    1     2148  ...          3
    2  2950000  ...          3
    3  3491845  ...          3
    4  3981454  ...          3
    [5 rows x 5 columns]

    >>> birmingham_shp_railways.columns.tolist()
    ['osm_id', 'name', 'type', 'coordinates', 'shape_type']

.. note::

    - ``birmingham_shp_railways`` and ``birmingham_shp_railways_`` both `pandas.DataFrame`_.

    - It must be noted that empty strings, ``''``, are automatically saved as ``None`` when importing ``birmingham_shp`` into the PostgreSQL database. Therefore, the retrieved ``birmingham_shp_railways_`` may not be exactly equal to ``birmingham_shp_railways``.

.. code-block:: python

    >>> check_eq = birmingham_shp_railways_.equals(birmingham_shp_railways)

    >>> print(f"`birmingham_shp_railways_` equals `birmingham_shp_railways`: {check_eq}")
    `birmingham_shp_railways_` equals `birmingham_shp_railways`: False

    >>> # Try filling ``None`` values with ``''``
    >>> birmingham_shp_railways_.fillna('', inplace=True)

    >>> # Check again the equivalence
    >>> check_eq = birmingham_shp_railways_.equals(birmingham_shp_railways)
    >>> print(f"`birmingham_shp_railways_` equals `birmingham_shp_railways`: {check_eq}")
    `birmingham_shp_railways_` equals `birmingham_shp_railways`: True


.. _qs-import-data-of-all-subregions:

Drop data
---------

If you would now like to drop the data of all or selected layers that have been imported for one or multiple geographic regions, you can use the method :py:meth:`.drop_subregion_table()<pydriosm.ios.PostgresOSM.drop_subregion_table>`.

For example, to drop the 'railways' data of Birmingham:

.. code-block:: python

    >>> # Recall that: subregion_name == 'Birmingham'; lyr_name == 'railways'

    >>> osmdb_test.drop_subregion_table(subregion_name, lyr_name, verbose=True)
    To drop table "railways"."Birmingham" from postgres:***@localhost:5432/osmdb_test
    ? [No]|Yes: yes
    Dropping the table ...
        "railways"."Birmingham" ... Done.

To also drop the 'waterways' of Birmingham and both 'lines' and 'multilinestrings' of Rutland:

.. code-block:: python

    >>> subregion_names = ['Birmingham', 'Rutland']
    >>> lyr_names = ['waterways', 'lines', 'multilinestrings']

    >>> osmdb_test.drop_subregion_table(subregion_names, lyr_names, verbose=True)
    To drop tables from postgres:***@localhost:5432/osmdb_test:
        "Birmingham"
        "Rutland"
     under the schemas:
        "lines"
        "multilinestrings"
        "waterways"
    ? [No]|Yes: yes
    Dropping the tables ...
        "lines"."Rutland" ... Done.
        "multilinestrings"."Rutland" ... Done.
        "waterways"."Birmingham" ... Done.

You could also easily drop the whole database 'osmdb_test' if you don't need it anymore:

.. code-block:: python

    >>> osmdb_test.drop_database(verbose=True)
    To drop the database "osmdb_test" from postgres:***@localhost:5432
    ? [No]|Yes: yes
    Dropping "osmdb_test" ... Done.


Clear up 'the mess' in here
===========================

To remove all the data files that have been downloaded and generated:

.. code-block:: python

    >>> from pyhelpers.dir import cd, delete_dir

    >>> list_of_data_dirs = ['Birmingham-shp', 'greater-london_kent_railways']

    >>> for dat_dir in list_of_data_dirs:
    ...     delete_dir(cd(data_dir, dat_dir), confirmation_required=False, verbose=True)
    Deleting "tests\Birmingham-shp\" ... Done.
    Deleting "tests\greater-london_kent_railways\" ... Done.

    >>> list_of_data_files = ['Birmingham.osm.shp.zip',
    ...                       'greater-london-latest.osm.pbf',
    ...                       'greater-london-latest-free.shp.zip',
    ...                       'kent-latest-free.shp.zip',
    ...                       'rutland-latest.osm.pbf',
    ...                       'west-midlands-latest.osm.pbf',
    ...                       'west-yorkshire-latest.osm.pbf']

    >>> for dat_file in list_of_data_files:
    ...     rel_file_path = os.path.relpath(cd(data_dir, dat_file))
    ...     print("Deleting \"{}\"".format(rel_file_path), end=" ... ")
    ...     try:
    ...         os.remove(rel_file_path)
    ...         print("Done.")
    ...     except Exception as e:
    ...         print("Failed. {}".format(e))
    Deleting "tests\Birmingham.osm.shp.zip" ... Done.
    Deleting "tests\greater-london-latest.osm.pbf" ... Done.
    Deleting "tests\greater-london-latest-free.shp.zip" ... Done.
    Deleting "tests\kent-latest-free.shp.zip" ... Done.
    Deleting "tests\rutland-latest.osm.pbf" ... Done.
    Deleting "tests\west-midlands-latest.osm.pbf" ... Done.
    Deleting "tests\west-yorkshire-latest.osm.pbf" ... Done.

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
.. _`pandas.DataFrame`: https://pandas.pydata.org/pandas-docs/stable/reference/api/pandas.DataFrame.html

|

(**THE END of** :ref:`Quick start<pydriosm-quick-start>`.)

For more details, check out :ref:`Modules<modules>`.
