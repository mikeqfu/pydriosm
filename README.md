# pydriosm

**Author**: Qian Fu [![Twitter URL](https://img.shields.io/twitter/url/https/twitter.com/Qian_Fu?label=Follow&style=social)](https://twitter.com/Qian_Fu)

[![PyPI](https://img.shields.io/pypi/v/pydriosm?label=PyPI&color=important)](https://pypi.org/project/pydriosm/)
[![PyPI - Python Version](https://img.shields.io/pypi/pyversions/pydriosm?label=Python)](https://www.python.org/downloads/windows/)
[![PyPI - License](https://img.shields.io/pypi/l/pydriosm?color=green&label=License)](https://github.com/mikeqfu/pydriosm/blob/master/LICENSE)
![GitHub code size in bytes](https://img.shields.io/github/languages/code-size/mikeqfu/pydriosm?color=yellowgreen&label=Code%20size)
![PyPI - Downloads](https://img.shields.io/pypi/dm/pydriosm?color=yellow&label=Downloads)

This package provides helpful utilities for researchers to easily download and read/parse the OpenStreetMap data extracts (in **.pbf** and **.shp.zip**) which are available at the free download servers: [Geofabrik](https://download.geofabrik.de/) and [BBBike](https://www.bbbike.org/). In addition, it also provides a convenient way to import/dump the parsed data to, and retrieve it from, a [PostgreSQL](https://www.postgresql.org/) sever. 

(Note that the package is written in Python 3.x and tested only on Windows OS and might not be compatible with Python 2.x. or other operating systems)



---

**<span style="font-size:larger;">Contents</span>**

* [Installation](#installation)
* [Quick start - Example: to handle ".pbf" data of the Greater London area](#quick-start)
  * [Download data](#download-data)
  * [Read/parse data](#read-parse-data)
  * [Import and retrieve data with a PostgreSQL server](#import-retrieve-data)
    * [Import the data to the database](#import-the-data-to-the-database)
    * [Retrieve data from the database](#retrieve-data-from-the-database)
    * [Import data of all subregions of a given (sub)region to the database](#import-data-of-all-subregions)
* [Footnote](#footnote)

---



## Installation

Windows OS users may the "pip install" command in Command Prompt:

```
pip install --upgrade pydriosm
```

If you are using some IDE, such as PyCharm, you should be able to find **pydriosm** in the PyPI repository. (In PyCharm, go to "Settings" and find **pydriosm** in "Project Interpreter"; to install it, select **pydriosm** and then click "Install Package".)

##### Note:

- Successful installation of `pydriosm` (and ensuring its full functionality) requires a few dependencies. On Windows OS, however, `pip install` may fail to go through the installation of some supporting packages, such as [python-Levenshtein](https://pypi.org/project/python-Levenshtein/), [Fiona](https://pypi.org/project/Fiona/), [GDAL](https://pypi.org/project/GDAL/) and [Shapely](https://pypi.org/project/Shapely/). In that case, you might have to resort to installing their **.whl** files, which can be downloaded from the [Unofficial Windows Binaries for Python Extension Packages](https://www.lfd.uci.edu/~gohlke/pythonlibs/). Once those packages are all ready, we could go ahead with the `pip` command. 



## Quick start

Firstly, we import the package: 

```python
import pydriosm as dri
```

The current version of the package deals only with subregion data files provided on the free server. To get a full list of subregion names that are available, you can use

```python
subregion_list = dri.fetch_subregion_info_catalogue("GeoFabrik-subregion-name-list")
print(subregion_list)
```

Below is an example of using **.pbf** data of the "Greater London" area to demonstrate briefly some main functions this package can do. 



### Download data <a name="download-data"></a>

To download the OSM data for a region (or rather, a subregion) of which the data extract is available, you  need to specify the name of the region (e.g. "Greater London"):

```python
subregion_name = 'Greater London'
# or, subregion_name = 'london'; case-insensitive and fuzzy (but not toooo... fuzzy)
```

Download **.pbf** data of "Greater London":

```python
dri.download_subregion_osm_file(subregion_name, osm_file_format=".osm.pbf", 
                                download_dir=None, update=False,
                                download_confirmation_required=True)
```

Note that `download_dir` is `None` by default. In that case, a default file path will be created and the downloaded file will be saved there. 

Check the default file path and name:

```python
default_fn, default_fp = dri.get_default_path_to_osm_file(subregion_name, 
                                                          osm_file_format=".osm.pbf", 
                                                          mkdir=False, update=False)
print("Default filename: {}".format(default_fn))
print("Default file path: {}".format(default_fp))
```

However, you may also set `download_dir` to be any other valid directory, especially when downloading data of multiple subregions. For example, 

```python
# Specify the our own data directory
customised_data_dir = "test_data"
# So "test_data" folder will be created in our current working directory

# Alternatively, we could specify a full path 
# import os
# customised_data_dir = os.path.join(os.getcwd(), "test_data")

# Download .pbf data of both 'London' and 'Kent' to the `customised_data_dir`
dri.download_subregion_osm_file('London', 'Kent', 
                                osm_file_format=".osm.pbf", update=False,
                                download_dir=customised_data_dir, 
                                download_confirmation_required=True)
```

The **.pbf** data file will then be saved to the `download_dir` as specified.



### Read/parse data <a name="read-parse-data"></a>

Parsing the **.pbf** data relies mainly on [GDAL/OGR](https://pypi.org/project/GDAL/), using `read_osm_pbf()` function.

```python
greater_london = dri.read_osm_pbf(subregion_name, data_dir=None, parsed=True, 
                                  file_size_limit=50, fmt_other_tags=True, 
                                  fmt_single_geom=True, fmt_multi_geom=True, 
                                  update=False, download_confirmation_required=True, 
                                  pickle_it=True, rm_raw_file=False)
```

The parsing process may take a few minutes or even longer if the data file is too large. If the file size is greater than the given `file_size_limit` (default: 50 MB), the data will be parsed in a chunk-wise manner. 

Note that `greater_london` is a `dict` with its keys being the name of five different layers: "points", "lines", "multilinestrings", "multipolygons" and "other_relations". 

If only the name of a subregion is given, i.e. `read_osm_pbf(subregion_name, ...)`, the function will go to look for the data file from the default file path. Otherwise, the function requires a specific data directory. For example, to read/parse the data in `customised_data_dir`, i.e. "test_data" folder, you need to set `data_dir=customised_data_dir` as follows:

```python
greater_london_test = dri.read_osm_pbf(subregion_name, data_dir=customised_data_dir)
```

`greater_london` and `greater_london_test` should be the same. 

To make life easier, you can simply skip the download step and use `read_osm_pbf()` directly. That is, if the targeted data is not available, `read_osm_pbf()` will download the data file first. By default, a confirmation of downloading the data will be prompted, given that `download_confirmation_required=True`. 

Setting `pickle_it=True` is to save a local copy of the parsed data as a `pickle` file. If `update=False`, when you run `read_osm_pbf(subregion_name)` again, the function will load the `pickle` file directly. If `update=True`, the function will try to download the latest version of the data file and parse it again.



In comparison, you can use `read_shp_zip()`, which relies mainly on [GeoPandas](http://geopandas.org/), to read **.shp.zip** data files:

```python
# We need to specify a layer, e.g. 'railways'
layer_name = 'railways'

greater_london_shp = dri.read_shp_zip(subregion_name, layer=layer_name, 
                                      feature=None, data_dir=None, update=False,
                                      download_confirmation_required=True, 
                                      pickle_it=True, rm_extracts=False)
```

Note that `greater_london_shp` and `greater_london` are different. 



To get information about more than one subregion, you can also merge **.shp** files of specific layers from those subregions. For example, to merge the "railways" layer of two subregions: "Greater London" and "Essex", we could do as follows.

```python
subregion_names=['Greater London', 'Kent']
# layer_name = 'railways'
dri.merge_multi_shp(subregion_names, layer=layer_name, update_shp_zip=False, 
                   download_confirmation_required=True, output_dir=None)
```

You could also set `data_dir=customised_data_dir` to save the downloaded **.shp.zip** files; or `output_dir=customised_data_dir` to make the merged **.shp** file available into `customised_data_dir`.



### Import and retrieve data with a PostgreSQL server <a name="import-retrieve-data"></a>

**Pydriosm** also provides a class, named "OSM", which communicates with [PostgreSQL](https://www.postgresql.org/) server. 

```python
osmdb = dri.OSM()
```

To establish a connection with the server, you will be asked to type in your username, password, host name/address and name of the database you intend to connect. 

For example, you may type in "postgres" to connect the default database. (Note that the quotation marks should be removed when typing in the name.)

If you would like to connect to another database (instead of the default "postgres"), run 

```python
osmdb.connect_db(database_name='osm_pbf_data_extracts')
```

Then, a database named "**osm_pbf_data_extracts**" will be created automatically if it does not exist before the connection is established.



#### (1) Import the data to the database <a name="import-the-data-to-the-database"></a>

To import `greater_london` (i.e. the parsed **.pbf** data of "Greater London") to the database, "**osm_pbf_data_extracts**":

```python
osmdb.dump_osm_pbf_data(greater_london, table_name=subregion_name, parsed=True, 
                        if_exists='replace', chunk_size=None,
                        subregion_name_as_table_name=True)
```

Each element (i.e. layer) of `greater_london` data will be stored in a different schema. The schema is named as the name of each layer.



#### (2) Retrieve data from the database <a name="retrieve-data-from-the-database"></a>

To retrieve the dumped data:

```python
greater_london_retrieval = osmdb.read_osm_pbf_data(table_name=subregion_name, 
                                                   parsed=True, 
                                                   subregion_name_as_table_name=True,
                                                   chunk_size=None, id_sorted=True)
```

Note that `greater_london_retrieval` may not be exactly the same as `greater_london`. This is because the keys of the elements in `greater_london` are in the following order: 'points', 'lines', 'multilinestrings', 'multipolygons' and 'other_relations'; whereas when dumping `greater_london` to the database, the five different schemas are sorted alphabetically as follows: 'lines', 'multilinestrings', 'multipolygons', 'other_relations', and 'points', and so retrieving data from the server will be in the latter order. Despite that, the data contained in both `greater_london` and `greater_london_retrieval` is consistent. 

If you need to query data of a specific layer (or several layers), or in a specific order of layers (schemas): 

```python
london_points_lines = osmdb.read_osm_pbf_data(subregion_name, 'points', 'lines')
# Another example:
# london_lines_mul = osmdb.read_osm_pbf_data('london', 'lines', 'multilinestrings')
```



#### (3) Import data of all subregions of a given (sub)region to the database <a name="import-data-of-all-subregions"></a>

```python
# Find all subregions (without smaller subregions) of a subregion.
# Take for example, to find all subregions of 'England':
subregions = dri.retrieve_subregion_names_from('England')

# Import data of all contained in `subregions`
dri.psql_osm_pbf_data_extracts(subregions, database_name='osm_pbf_data_extracts', 
                               data_dir=None, update_osm_pbf=False, 
                               if_table_exists='replace', file_size_limit=50,
                               parsed=True, fmt_other_tags=True, 
                               fmt_single_geom=True, fmt_multi_geom=True, 
                               rm_raw_file=False)
```

Setting `rm_raw_file=False` and `data_dir=None` will keep all raw **.pbf** data files in the default data folder.

If you would like to import all subregion data of "Great Britain":

```python
gb_subregions = dri.retrieve_subregion_names_from('Great Britain')
```

Instead of returning `['England', 'Scotland', 'Wales']`, the list `gb_subregions` will include all subregions of "England" (rather than "England" as a single element), "Scotland" and "Wales". 



---

[![Website](https://img.shields.io/website/https/download.geofabrik.de?label=Data%20source&up_color=9cf&up_message=http%3A%2F%2Fdownload.geofabrik.de)](https://download.geofabrik.de/)
[![Website](https://img.shields.io/website/https/download.bbbike.org/osm?label=Data%20source&up_color=9cf&up_message=http%3A%2F%2Fdownload.bbbike.org%2Fosm)](https://download.bbbike.org/osm/)

Data/Map data &copy; [Geofabrik GmbH](http://www.geofabrik.de/) and [OpenStreetMap Contributors](http://www.openstreetmap.org/) <a name="footnote"></a>

All data from the [OpenStreetMap](https://www.openstreetmap.org) is licensed under the [OpenStreetMap License](https://www.openstreetmap.org/copyright). 
