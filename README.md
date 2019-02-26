# pydirosm

(Beta version 0.2.3)



### Quick start

This package contains functions for the convenience of researchers to download and parse the OSM data extracts (in **.osm.pbf** and **.shp.zip**, which are available at [Geofabrik's free download server](https://download.geofabrik.de/) and [BBBike.org](https://www.bbbike.org/)), and if appropriate, import the parsed data into PostgreSQL. 

Note that this package is written in Python 3 on Windows operating system and may not be compatible with Python 2. 



#### Installation (Testing phase)

Currently this package has been uploaded to [TestPyPI](https://test.pypi.org/project/pydriosm/) only. The installation of the package requires a few supporting packages to ensure its complete functionality. However, some of the required packages, such as Fiona, GDAL and Shapely, may necessitate installing their Windows binaries available at [Unofficial Windows Binaries for Python Extension Packages](https://www.lfd.uci.edu/~gohlke/pythonlibs/). 

Otherwise, use the command prompt to run:

```
pip install --extra-index-url https://test.pypi.org/simple/ pydriosm
```



#### Example

```python
import pydirosm
```

To download data for a region (or rather, a subregion) of which the OSM data extract is available, just simply provide the name of the (sub)region. Say if we need the data about 'West Midlands' of England:

```python
subregion_name = 'west midlands'  # Case-insensitive
```



##### Downloading data

Download .osm.pbf data of 'West Midlands'

```python
pydriosm.download_subregion_osm_file(subregion_name, download_path=None)
```

The parameter`download_path` is `None` by default. In that case, a default file path will be generated and the downloaded data file will be saved there; however, we may also set this parameter to be any other valid path. 

```python
import os

default_filename = pydriosm.get_default_filename(subregion_name)
download_path = os.path.join(os.getcwd(), "test_data", default_filename)

pydriosm.download_subregion_osm_file(subregion_name, download_path=download_path)
```



##### Parsing data

Pre-parse the .osm.pbf data:

```python
west_midlands = pydriosm.read_raw_osm_pbf(subregion_name, rm_raw_file=False)
```

Or, fully parse the .osm.pbf data:

```python
west_midlands_parsed = pydriosm.read_parsed_osm_pbf(subregion_name)
```

Note that we may simply skip the download step and run the parse functions directly. If data is not available, the parse function will download the data first. A confirmation of downloading the data will be asked if setting `download_confirmation_required=True`.



##### Importing data to PostgreSQL

The package provides a class, named 'OSM', which communicates with PostgreSQL. 

```python
osm_db = pydriosm.OSM()
```

A username and password to the server will be required. 

Create a database:

```python
osm_db.create_db(database_name='osm_extracts')  

# If the database is already available
# osmdb.connect_db(database_name='osm_extracts')
```

Import the pre-parsed .osm.pbf data into the database named '**osm_extracts**':

```python
osm_db.import_data(west_midlands, table_name=subregion_name)
```



---

Data/Map data © [Geofabrik GmbH](http://www.geofabrik.de/) and [OpenStreetMap Contributors](http://www.openstreetmap.org/) 

All data from the [OpenStreetMap](https://www.openstreetmap.org) is licensed under the [OpenStreetMap License](https://www.openstreetmap.org/copyright). 