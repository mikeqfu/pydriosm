"""
Quick start
"""

# Download data ==================================================================================

from pydriosm import GeofabrikDownloader

# Create an instance for downloading the GeoFabrik data extracts
geofabrik_downloader = GeofabrikDownloader()

# To check what data is available for downloads
geofabrik_download_catalogue = geofabrik_downloader.get_download_catalogue()

print(geofabrik_download_catalogue.columns.tolist())
"""
['Subregion', 'SubregionURL', '.osm.pbf', '.osm.pbf.Size', '.shp.zip', '.osm.bz2']
"""

print(geofabrik_download_catalogue.head())
"""
      Subregion  ...                                           .osm.bz2
0       Algeria  ...  http://download.geofabrik.de/africa/algeria-la...
1        Angola  ...  http://download.geofabrik.de/africa/angola-lat...
2         Benin  ...  http://download.geofabrik.de/africa/benin-late...
3      Botswana  ...  http://download.geofabrik.de/africa/botswana-l...
4  Burkina Faso  ...  http://download.geofabrik.de/africa/burkina-fa...
[5 rows x 6 columns]
"""

# To download OSM PBF data of London, specify the name of the region and file format:
subregion_name = 'London'  # case-insensitive
osm_file_format = ".pbf"
download_dir = "tests"  # Specify a download directory

# Download the OSM PBF data of London
geofabrik_downloader.download_osm_data(subregion_name, osm_file_format, download_dir,
                                       verbose=True)
"""
Confirm to download .osm.pbf data of the following geographic region(s):
    Greater London
? [No]|Yes: yes
Downloading "greater-london-latest.osm.pbf" to "\\tests" ... 
Done. 
"""

path_to_london_pbf = geofabrik_downloader.download_osm_data(
    subregion_name, osm_file_format, download_dir, confirmation_required=False,
    ret_download_path=True)

import os

london_pbf_filename = os.path.basename(path_to_london_pbf)

print(f"Default filename: '{london_pbf_filename}'")
"""
Default filename: 'greater-london-latest.osm.pbf'
"""

print(f"Current (relative) file path: '{os.path.relpath(path_to_london_pbf)}'")
"""
Current (relative) file path: 'tests\\greater-london-latest.osm.pbf'
"""

# Default filename and file path
london_pbf_filename, default_path_to_london_pbf = \
    geofabrik_downloader.get_default_path_to_osm_file(subregion_name, osm_file_format)

print(f"Default filename: '{london_pbf_filename}'")
""" 
Default filename: 'greater-london-latest.osm.pbf'
"""

from pyhelpers.dir import cd

path_to_london_pbf = cd(download_dir, london_pbf_filename)

print(f"Current (relative) file path: '{os.path.relpath(path_to_london_pbf)}'")
"""
Current file path: 'tests\\greater-london-latest.osm.pbf'
"""

# Download PBF data of multiple subregions
subregion_names = ['Rutland', 'West Yorkshire', 'West Midlands']

paths_to_pbf = geofabrik_downloader.download_osm_data(subregion_names, osm_file_format,
                                                      download_dir, ret_download_path=True,
                                                      verbose=True)

type(paths_to_pbf)
"""
<class 'list'>
"""

for path_to_pbf in paths_to_pbf:
    print(f"'{os.path.relpath(path_to_pbf)}'")
"""
tests\\rutland-latest.osm.pbf
tests\\west-yorkshire-latest.osm.pbf
tests\\west-midlands-latest.osm.pbf
"""

# Read/parse data ================================================================================

from pydriosm import GeofabrikReader  # from pydriosm.reader import GeofabrikReader

geofabrik_reader = GeofabrikReader()

# PBF data (.osm.pbf / .pbf) ---------------------------------------------------------------------
subregion_name = 'Rutland'
data_dir = download_dir

rutland_pbf_raw = geofabrik_reader.read_osm_pbf(subregion_name, data_dir)

type(rutland_pbf_raw)
"""
<class 'dict'>
"""

# The 'points' layer
rutland_pbf_points = rutland_pbf_raw['points']

print(rutland_pbf_points.head())
"""
                                              points
0  {"type": "Feature", "geometry": {"type": "Poin...
1  {"type": "Feature", "geometry": {"type": "Poin...
2  {"type": "Feature", "geometry": {"type": "Poin...
3  {"type": "Feature", "geometry": {"type": "Poin...
4  {"type": "Feature", "geometry": {"type": "Poin...
"""

import json

rutland_pbf_points_0 = rutland_pbf_points['points'][0]
type(rutland_pbf_points_0)
"""
<class 'str'>
"""

rutland_pbf_points_0_ = json.loads(rutland_pbf_points_0)
type(rutland_pbf_points_0_)
"""
<class 'dict'>
"""

print(list(rutland_pbf_points_0_.keys()))
"""
['type', 'geometry', 'properties', 'id']
"""

# more granular tabular data
rutland_pbf_parsed = geofabrik_reader.read_osm_pbf(subregion_name, data_dir,
                                                   parse_raw_feat=True)

rutland_pbf_parsed_points = rutland_pbf_parsed['points']

print(rutland_pbf_parsed_points.head())
"""
         id               coordinates  ... man_made                    other_tags
0    488432  [-0.5134241, 52.6555853]  ...     None               "odbl"=>"clean"
1    488658  [-0.5313354, 52.6737716]  ...     None                          None
2  13883868  [-0.7229332, 52.5889864]  ...     None                          None
3  14049101  [-0.7249922, 52.6748223]  ...     None  "traffic_calming"=>"cushion"
4  14558402  [-0.7266686, 52.6695051]  ...     None      "direction"=>"clockwise"
[5 rows x 12 columns]
"""

# Shapefiles (.shp.zip / .shp) -------------------------------------------------------------------
subregion_name = 'London'
layer_name = 'railways'

# Read the .shp.zip file
london_shp = geofabrik_reader.read_shp_zip(subregion_name, layer_names=layer_name,
                                           data_dir=data_dir, verbose=True)
"""
Confirm to download .shp.zip data of the following geographic region(s):
    Greater London
? [No]|Yes: >? yes
Downloading "greater-london-latest-free.shp.zip" to "\\tests" ... 
104MB [00:14,  7.41MB/s]                         
Done. 
Extracting from "greater-london-latest-free.shp.zip" the following layer(s):
    'railways'
to "\\tests\\greater-london-latest-free-shp" ... 
In progress ... Done. 
"""

london_railways_shp = london_shp[layer_name]

print(london_railways_shp.head())
"""
   osm_id  code  ... tunnel                                           geometry
0   30804  6101  ...      F    LINESTRING (0.00486 51.62793, 0.00620 51.62927)
1  101298  6103  ...      F  LINESTRING (-0.22496 51.49354, -0.22507 51.494...
2  101486  6103  ...      F  LINESTRING (-0.20555 51.51954, -0.20514 51.519...
3  101511  6101  ...      F  LINESTRING (-0.21189 51.52419, -0.21079 51.523...
4  282898  6103  ...      F  LINESTRING (-0.18626 51.61591, -0.18687 51.61384)
[5 rows x 8 columns]
"""

# To merge .shp files of multiple subregions on a specific layer
layer_name = 'railways'
subregion_names = ['London', 'Kent']

path_to_merged_shp = geofabrik_reader.merge_subregion_layer_shp(layer_name, subregion_names,
                                                                data_dir, verbose=True,
                                                                ret_merged_shp_path=True)
"""
Confirm to download .shp.zip data of the following geographic region(s):
    Greater London
    Kent
? [No]|Yes: >? yes
"greater-london-latest-free.shp.zip" of Greater London is already available at "tests".
Downloading "kent-latest-free.shp.zip" to "\\tests" ... 
52MB [00:06,  8.05MB/s]                        
Done. 
Extracting from "greater-london-latest-free.shp.zip" the following layer(s):
    'railways'
to "\\tests\\greater-london-latest-free-shp" ... 
In progress ... Done. 
Extracting from "kent-latest-free.shp.zip" the following layer(s):
    'railways'
to "\\tests\\kent-latest-free-shp" ... 
In progress ... Done. 
Merging the following shapefiles:
    "greater-london_gis_osm_railways_free_1.shp"
    "kent_gis_osm_railways_free_1.shp"
In progress ... Done.
Find the merged .shp file(s) at "\\tests\\greater-london_kent_railways".
"""

print(os.path.relpath(path_to_merged_shp))
"""
tests\\greater-london_kent_railways\\greater-london_kent_railways.shp
"""

# Import and retrieve data with a PostgreSQL server ==============================================

from pydriosm import PostgresOSM

host = 'localhost'
port = 5432
username = 'postgres'
password = None  # We need to type it in manually if `None`
database_name = 'osmdb_test'

osmdb_test = PostgresOSM(host, port, username, password, database_name)
"""
Password (postgres@localhost:5432): ***
Connecting postgres:***@localhost:5432/osmdb_test ... Successfully.
"""

# Import data to the database --------------------------------------------------------------------
subregion_name = 'Rutland'

osmdb_test.import_osm_data(rutland_pbf_parsed, table_name=subregion_name, verbose=True)
"""
Importing data into "Rutland" at postgres:***@localhost:5432/osmdb_test ... 
    points ... done: 4195 features.
    lines ... done: 7405 features.
    multilinestrings ... done: 53 features.
    multipolygons ... done: 6190 features.
    other_relations ... done: 13 features.
"""

# Retrieve data from the database ----------------------------------------------------------------
rutland_pbf_parsed_ = osmdb_test.fetch_osm_data(subregion_name, layer_names=None,
                                                decode_wkt=True)

check_equivalence = all(rutland_pbf_parsed[lyr_name].equals(rutland_pbf_parsed_[lyr_name])
                        for lyr_name in rutland_pbf_parsed_.keys())

print("`rutland_pbf_parsed_` equals `rutland_pbf_parsed`: {}".format(check_equivalence))
"""
`rutland_pbf_parsed_` equals `rutland_pbf_parsed`: True
"""

# 'Birmingham' is not in the list of cities on the free Geofabrik download server
osmdb_test.DataSource = 'BBBike'

# Another example: import transport-related layers of the shapefile of Birmingham
subregion_name = 'Birmingham'

birmingham_shp = osmdb_test.Reader.read_shp_zip(subregion_name, data_dir=data_dir,
                                                verbose=True)
"""
Confirm to download .shp.zip data of the following geographic region(s):
    Birmingham
? [No]|Yes: >? yes
Downloading "Birmingham.osm.shp.zip" to "\\tests" ... 
65MB [00:08,  7.45MB/s]                        
Done. 
Extracting all of "Birmingham.osm.shp.zip" to "\\tests" ... 
In progress ... Done. 
Parsing "\\tests\\Birmingham-shp\\shape" ... Done. 
"""

print(list(birmingham_shp.keys()))
"""
['buildings', 'landuse', 'natural', 'places', 'points', 'railways', 'roads', 'waterways']
"""

# Import the data of 'railways', 'roads' and 'waterways'
lyr_names = ['railways', 'roads', 'waterways']

osmdb_test.import_osm_data(birmingham_shp, table_name=subregion_name,
                           schema_names=lyr_names, verbose=True)
"""
Importing data into "Birmingham" at postgres:***@localhost:5432/osmdb_test ... 
    railways ... done: 3176 features.
    roads ... done: 116939 features.
    waterways ... done: 2897 features.
"""

# To fetch only the 'railways' data of Birmingham:
lyr_name = 'railways'

birmingham_shp_ = osmdb_test.fetch_osm_data(subregion_name, layer_names=lyr_name,
                                            decode_wkt=True, sort_by='osm_id')

birmingham_shp_railways_ = birmingham_shp_[lyr_name]
print(birmingham_shp_railways_.head())
"""
    osm_id  ...                                           geometry
0      740  ...  LINESTRING (-1.8178905 52.5700974, -1.8179287 ...
1     2148  ...  LINESTRING (-1.8731878 52.5055513, -1.8727074 ...
2  2950000  ...  LINESTRING (-1.8794134 52.4813762, -1.8795969 ...
3  3491845  ...  LINESTRING (-1.7406017 52.5185831, -1.7394216 ...
4  3981454  ...  LINESTRING (-1.7747469 52.5228419, -1.7744914 ...
[5 rows x 4 columns]
"""

birmingham_shp_railways = birmingham_shp[lyr_name]

print(birmingham_shp_railways.head())
"""
    osm_id  ...                                           geometry
0      740  ...  LINESTRING (-1.81789 52.57010, -1.81793 52.569...
1     2148  ...  LINESTRING (-1.87319 52.50555, -1.87271 52.505...
2  2950000  ...  LINESTRING (-1.87941 52.48138, -1.87960 52.481...
3  3491845  ...  LINESTRING (-1.74060 52.51858, -1.73942 52.518...
4  3981454  ...  LINESTRING (-1.77475 52.52284, -1.77449 52.522...
[5 rows x 4 columns]
"""

import pandas as pd

check_equivalence = birmingham_shp_railways_.equals(pd.DataFrame(birmingham_shp_railways))

print(f"`birmingham_shp_railways_` equals `birmingham_shp_railways`: {check_equivalence}")
"""
`birmingham_shp_railways_` equals `birmingham_shp_railways`: True
"""

# To drop the database ---------------------------------------------------------------------------

osmdb_test.drop_subregion_table(subregion_name, lyr_name, verbose=True)
"""
Confirmed to drop the following table: 
    "Birmingham"
  from the following schema: 
    "railways"
  at postgres:***@localhost:5432/osmdb_test
? [No]|Yes: >? yes
Dropping ... 
    "railways"."Birmingham" ... Done. 
"""

subregion_names = ['Birmingham', 'Rutland']
lyr_names = ['waterways', 'lines', 'multilinestrings']

osmdb_test.drop_subregion_table(subregion_names, lyr_names, verbose=True)
"""
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
"""

# Drop the database
osmdb_test.PostgreSQL.drop_database(verbose=True)

# Clear up (the mess in here) before we move on
from pyhelpers.dir import delete_dir

list_of_data_dirs = ['Birmingham-shp', 'greater-london_kent_railways']

for dat_dir in list_of_data_dirs:
    delete_dir(cd(data_dir, dat_dir), confirmation_required=False, verbose=True)
"""
Deleting "\\tests\\Birmingham-shp" ... Done.
Deleting "\\tests\\greater-london_kent_railways" ... Done.
"""

list_of_data_files = ['Birmingham.osm.shp.zip',
                      'greater-london-latest.osm.pbf',
                      'greater-london-latest-free.shp.zip',
                      'kent-latest-free.shp.zip',
                      'rutland-latest.osm.pbf',
                      'west-midlands-latest.osm.pbf',
                      'west-yorkshire-latest.osm.pbf']

for dat_file in list_of_data_files:
    os.remove(cd(data_dir, dat_file))
