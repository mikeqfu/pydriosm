# pydriosm

**(Version 1.0.3)**

This package provides helpful utilities for researchers to easily download and read/parse the OpenStreetMap data extracts (in **.osm.pbf** and **.shp.zip**) that are available at [Geofabrik's free download server](https://download.geofabrik.de/) and [BBBike.org](https://www.bbbike.org/). In addition, it also provides a convenient way of importing/dumping the parsed data to a PostgreSQL sever. (Note that the package is written in Python 3.x on Windows operating system and might not be compatible with Python 2.x.)



## Quick start

This is a brief introduction of what we may do with this package.



### Installation

On Windows, use the command prompt to run:

```
pip install pydriosm
```

If you are using IDEs, we should be able to find *pydriosm* in the PyPI repository. (For example, if we are using PyCharm, we can find *pydriosm* in "Project Interpreter" in "Settings" and install click "Install Package".)

It is important to note that successful installation of *pydriosm* requires a few supporting packages to ensure its full functionality. However, on Windows OS, some of the supporting packages, such as [Fiona](https://pypi.org/project/Fiona/), [GDAL](https://pypi.org/project/GDAL/) and [Shapely](https://pypi.org/project/Shapely/), may fail to go through `pip install`; instead, they necessitate installing their binaries (e.g. **.whl**) which can be downloaded from [Unofficial Windows Binaries for Python Extension Packages](https://www.lfd.uci.edu/~gohlke/pythonlibs/). Once those packages are ready, go ahead with the 'pip' command. 

Here is a list of supporting packages:

*beautifulsoup4*, *Fiona*, *fuzzywuzzy*, *gdal*, *geopandas*, *html5lib*, *humanfriendly*, *lxml*, *numpy+mkl*, *pandas*, *psycopg2*, *pyshp*, *python-Levenshtein*, *python-rapidjson*, *requests*, *shapely*, *sqlalchemy*, sqlalchemy-utils, *tqdm*. 



### Example - DRI .osm.pbf data of the Greater London area

Here is an example to illustrate what's included in this package and what we may do by using it. Firstly, we import the package: 

```python
import pydriosm
```

To download data for a region (or rather, a subregion) of which the OSM data extract is available, we just need to simply specify the name of the (sub)region. Let's say we would like to have data of the Greater London area:

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

The parameter`download_path` is `None` by default. In that case, a default file path will be generated and the downloaded file will be saved there; however, we may also set this parameter to be any other valid path. For example, try

```python
import os

default_filename = pydriosm.get_default_filename(subregion_name)
download_path = os.path.join(os.getcwd(), "test_data", default_filename)

pydriosm.download_subregion_osm_file(subregion_name, download_path=download_path)
```



#### Reading/parsing data

Pre-parsing the **.osm.pbf** data relies mainly on [GDAL](https://pypi.org/project/GDAL/):

```python
greater_london = pydriosm.read_osm_pbf(subregion_name, rm_raw_file=False)
```

Note that `greater_london` is a `dict` with its keys being the name of five different layers: 'points', 'lines', 'multilinestrings', 'multipolygons', and 'other_relations'.

To skip pre-parsing, we could go straight to fully parse the **.osm.pbf** data:

```python
greater_london_parsed = pydriosm.read_parsed_osm_pbf(subregion_name)
```

`read_parsed_osm_pbf()` also returns a `dict`.

To make things easier, we can simply skip the download step and run the `read_...` functions directly. That is, if the targeted data is not available, either of the above `read_...` functions will download the data first. By default, a confirmation of downloading the data will be asked with the setting of `download_confirmation_required=True`. 



#### Importing data to PostgreSQL

*pydriosm* also provides a class, named '**OSM**', which communicates with PostgreSQL server. 

```python
osmdb = pydriosm.OSM()
```

For the class to establish a connection with the server, we need type in our username, password, host name/address and name of the database we intend to connect. For example, we may type in 'postgres' to connect the common database (i.e. 'postgres'). Note that all quotation marks should be removed when typing in the name.



If we may want to connect to another database, we could try:

```python
osmdb.connect_db(database_name='osm_data_extracts')
```

'osm_data_extracts' will be created automatically if it does not exist before the connection is established.

Now we would want to dump the parsed **.osm.pbf** data to our server. To import `greater_london_parsed` into the database 'osm_data_extracts':

```python
osmdb.dump_osm_pbf_data(greater_london_parsed, table_name=subregion_name)
```

Each element (i.e. layer) of `greater_london_parsed` data will be stored in a different schema. The schema is named as the name of a layer.

To read the data from the server:

```python
greater_london_loaded = osmdb.read_osm_pbf_data(subregion_name)
```

Note that `greater_london_loaded` may not be exactly the same as `greater_london_parsed`. This is because the elements in `greater_london_parsed` is in the following order: 'points', 'lines', 'multilinestrings', 'multipolygons' and 'other_relations'; whereas when dumping `greater_london_parsed` to the server, the five different schemas are sorted alphabetically as follows: 'lines', 'multilinestrings', 'multipolygons', 'other_relations', and 'points', and so reading data from the server will be following this order. 

If we want data of specific layer (or layers), or in a specific order of layers (schemas): 

```python
london_points_lines = osmdb.read_osm_pbf_data(subregion_name, 'points', 'lines')
# Or
# london_lines_mul = osmdb.read_osm_pbf_data(subregion_name, 'lines', 'multilinestrings')
```



---

Data/Map data © [Geofabrik GmbH](http://www.geofabrik.de/) and [OpenStreetMap Contributors](http://www.openstreetmap.org/) 

All data from the [OpenStreetMap](https://www.openstreetmap.org) is licensed under the [OpenStreetMap License](https://www.openstreetmap.org/copyright). 