# pydriosm

**(Version 1.0.6)**

This package provides helpful utilities for researchers to easily download and read/parse the OpenStreetMap data extracts (in **.osm.pbf** and **.shp.zip**) which are available at [Geofabrik's free download server](https://download.geofabrik.de/) and [BBBike.org](https://www.bbbike.org/). In addition, it also provides a convenient way to import/dump the parsed data to, and load it from, a PostgreSQL sever. 

(Note that the package is written in Python 3.x and tested only on Windows operating system and might not be compatible with Python 2.x. or other operating systems)



## Installation

On Windows, use the command prompt to run:

```
pip install pydriosm
```

If you are using IDE's, we should be able to find *pydriosm* in the PyPI repository. (For example, if we are using PyCharm, we can find *pydriosm* in "Project Interpreter" in "Settings" and install click "Install Package".)

It is important to note that successful installation of *pydriosm* requires a few supporting packages to ensure its full functionality. However, on Windows OS, some of the supporting packages, such as [Fiona](https://pypi.org/project/Fiona/), [GDAL](https://pypi.org/project/GDAL/) and [Shapely](https://pypi.org/project/Shapely/), may fail to go through `pip install`; instead, they necessitate installing their binaries (e.g. **.whl**) which can be downloaded from [Unofficial Windows Binaries for Python Extension Packages](https://www.lfd.uci.edu/~gohlke/pythonlibs/). Once those packages are ready, go ahead with the 'pip' command. 

Here is a list of supporting packages:

*beautifulsoup4*, *Fiona*, *fuzzywuzzy*, *gdal*, *geopandas*, *html5lib*, *humanfriendly*, *lxml*, *numpy+mkl*, *pandas*, *psycopg2*, *pyshp*, *python-Levenshtein*, *python-rapidjson*, *requests*, *shapely*, *sqlalchemy*, sqlalchemy-utils, *tqdm*. 



## Quick start

This is a brief introduction of some main functions this package can perform.

### Example - DRI .osm.pbf data of the Greater London area

Here is an example to illustrate what we may do by using the package. 

Firstly, we import the package: 

```python
import pydriosm
```

To play with the OSM data for a region (or rather, a subregion) of which the data extract is available, we just need to simply specify the name of the (sub)region. Let's say we would like to have data of the Greater London area:

```python
subregion_name = 'greater london'  
# or subregion_name = 'London'; case-insensitive and fuzzy (but not toooo... fuzzy)
```

Note that we can only get the subregion data that is available. To get a full list of subregion names, we can use

```python
subregion_list = pydriosm.get_subregion_info_index("GeoFabrik-subregion-name-list")
print(subregion_list)
```



#### Downloading data

Download **.osm.pbf** data of 'Greater London'

```python
pydriosm.download_subregion_osm_file(subregion_name, download_path=None)
```

The parameter`download_path` is `None` by default. In that case, a default file path will be generated and the downloaded file will be saved there; however, we may also set this parameter to be any other valid path. For example, 

```python
import os

default_filename = pydriosm.get_default_filename(subregion_name)
download_path = os.path.join(os.getcwd(), "test_data", default_filename)

pydriosm.download_subregion_osm_file(subregion_name, download_path=download_path)
```

The **.osm.pbf** file will then be saved to the `download_path` as specified.



#### Reading/parsing data

Parsing the **.osm.pbf** data relies mainly on [GDAL](https://pypi.org/project/GDAL/):

```python
greater_london = pydriosm.read_osm_pbf(subregion_name, update=False, 
                                       download_confirmation_required=True, 
                                       file_size_limit=60, granulated=True,
                                       fmt_other_tags=True, fmt_single_geom=True, fmt_multi_geom=True, 
                                       pickle_it=True, rm_raw_file=False)
```

Note that `greater_london` is a `dict` with its keys being the name of five different layers: 'points', 'lines', 'multilinestrings', 'multipolygons', and 'other_relations'.

To make things easier, we can simply skip the download step and run `read_osm_pbf()` directly. That is, if the targeted data is not available, `read_osm_pbf()` will download the data first. By default, a confirmation of downloading the data will be asked with the setting of `download_confirmation_required=True`. 

Setting `pickle_it=True` is to save a local copy of the parsed data as a `pickle` file. As long as `update=False`, when we run `read_osm_pbf(subregion_name)` again, the function will load the `pickle` file directly. If `update=True`, the function will try to download the latest version of the data file and parse it again.



#### Importing data into, and retrieving data from, the PostgreSQL server

*pydriosm* also provides a class, named 'OSM', which communicates with PostgreSQL server. 

```python
osmdb = pydriosm.OSM()
```

To establish a connection with the server, we will be asked to type in our username, password, host name/address and name of the database we intend to connect. For example, we may type in 'postgres' to connect the common database (i.e. 'postgres'). Note that all quotation marks should be removed when typing in the name.

If we may want to connect to another database (instead of the default 'postgres'), we use

```python
osmdb.connect_db(database_name='osm_data_extracts')
```

'osm_data_extracts' will be created automatically if it does not exist before the connection is established.



##### (1) Importing data

Now we would want to dump the parsed **.osm.pbf** data to our server. To import `greater_london` into the database **'osm_data_extracts'**:

```python
osmdb.dump_osm_pbf_data(greater_london, table_name=subregion_name, parsed=True, 
                        if_exists='replace', chunk_size=None,
                        subregion_name_as_table_name=True)
```

Each element (i.e. layer) of `greater_london` data will be stored in a different schema. The schema is named as the name of each layer.

##### (2) Retrieving data

To read the data from the server:

```python
greater_london_retrieval = osmdb.read_osm_pbf_data(table_name=subregion_name, parsed=True, 
                                                   subregion_name_as_table_name=True,
                                                   chunk_size=None)
```

Note that `greater_london_retrieval` may not be exactly 'the same' as `greater_london`. This is because the keys of the elements in `greater_london` are in the following order: 'points', 'lines', 'multilinestrings', 'multipolygons' and 'other_relations'; whereas when dumping `greater_london` to the server, the five different schemas are sorted alphabetically as follows: 'lines', 'multilinestrings', 'multipolygons', 'other_relations', and 'points', and so retrieving data from the server will be following this order. However, the data contained in both `greater_london` and `greater_london_retrieval` is the consistent. 

If we want data of specific layer (or layers), or in a specific order of layers (schemas): 

```python
london_points_lines = osmdb.read_osm_pbf_data(subregion_name, 'points', 'lines')
# Another example:
# london_lines_mul = osmdb.read_osm_pbf_data(subregion_name, 'lines', 'multilinestrings')
```



---

Data/Map data © [Geofabrik GmbH](http://www.geofabrik.de/) and [OpenStreetMap Contributors](http://www.openstreetmap.org/) 

All data from the [OpenStreetMap](https://www.openstreetmap.org) is licensed under the [OpenStreetMap License](https://www.openstreetmap.org/copyright). 