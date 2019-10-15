# 1. Pack 'pydriosm'
#       python setup.py sdist bdist_wheel

# 2. Upload distributions to TestPyPI:
#       python -m twine upload --repository-url https://test.pypi.org/legacy/ dist/*

# 3. Install/upgrade 'pydriosm':
#       pip install --upgrade --extra-index-url https://test.pypi.org/simple/ pydriosm

from pyhelpers.settings import pd_preferences

import pydriosm as dri

pd_preferences()

# To get a full list of subregion names that are available
subregion_list = dri.fetch_subregion_info_catalogue("GeoFabrik-subregion-name-list")
print(subregion_list)

# Download .pbf data of "London" ("Greater London")
subregion_name = 'London'

dri.download_subregion_osm_file(subregion_name, osm_file_format=".osm.pbf",
                                download_dir=None, update=False,
                                download_confirmation_required=True)

# Check the default file path and name
default_fn, default_fp = dri.get_default_path_to_osm_file(subregion_name,
                                                          osm_file_format=".osm.pbf",
                                                          mkdir=False, update=False)
print("Default filename: {}".format(default_fn))
print("Default file path: {}".format(default_fp))

# Specify the our own data directory
customised_data_dir = "tests\\test_data"

# Download .pbf data of both 'London' and 'Kent' to the `customised_data_dir`
dri.download_subregion_osm_file('London', 'Kent', osm_file_format=".osm.pbf",
                                download_dir=customised_data_dir, update=False,
                                download_confirmation_required=True)

# Read the .osm.pbf data (downloaded to the default directory `default_fp`)
greater_london = dri.read_osm_pbf(subregion_name, data_dir=None, parsed=True,
                                  file_size_limit=50, fmt_other_tags=True,
                                  fmt_single_geom=True, fmt_multi_geom=True,
                                  update=False, download_confirmation_required=True,
                                  pickle_it=True, rm_osm_pbf=False)


greater_london_alt = dri.read_osm_pbf(subregion_name, data_dir=customised_data_dir)


# Read .shp.zip file
layer_name = 'railways'

greater_london_shp = dri.read_shp_zip(subregion_name, layer=layer_name,
                                      feature=None, data_dir=None, update=False,
                                      download_confirmation_required=True,
                                      pickle_it=True, rm_extracts=False,
                                      rm_shp_zip=True)

# Merge *.shp files of specific layers of multiple subregions
subregion_names = ['Greater London', 'Kent']
dri.merge_multi_shp(subregion_names, layer=layer_name, update_shp_zip=False,
                    download_confirmation_required=True, output_dir=None)

# Importing .osm.pbf data
osmdb = dri.OSM(username='postgres', host='localhost', port=5432, database_name='postgres')

# Connect to a database
osmdb.connect_db(database_name='osm_pbf_data_extracts')

# (1) Import the .osm.pbf data to the database
osmdb.dump_osm_pbf_data(greater_london, table_name=subregion_name, parsed=True,
                        if_exists='replace', chunk_size=None,
                        subregion_name_as_table_name=True)

# (2) Retrieve the .osm.pbf data
greater_london_retrieval = osmdb.read_osm_pbf_data(table_name=subregion_name,
                                                   parsed=True,
                                                   subregion_name_as_table_name=True,
                                                   chunk_size=None, id_sorted=True)

# query data of a specific layer (or several layers, say 'points' and 'lines'), or in a specific order of layers
london_points_lines = osmdb.read_osm_pbf_data(subregion_name, 'points', 'lines')
# Another example:
london_lines_mul = osmdb.read_osm_pbf_data('london', 'lines', 'multilinestrings')

# (3) Import data of all subregions of a given (sub)region to the database
subregions = dri.retrieve_names_of_subregions_of('England')

# Import data of all contained in `subregions`
dri.psql_osm_pbf_data_extracts(subregions, database_name='osm_pbf_data_extracts',
                               data_dir=customised_data_dir, update_osm_pbf=False,
                               if_table_exists='replace', file_size_limit=50,
                               parsed=True, fmt_other_tags=True,
                               fmt_single_geom=True, fmt_multi_geom=True,
                               rm_raw_file=True)

gb_subregions = dri.retrieve_names_of_subregions_of('Great Britain')
