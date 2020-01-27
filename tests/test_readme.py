"""
# Pack 'pydriosm'
python setup.py sdist bdist_wheel

# Upload distributions to TestPyPI
python -m twine upload --repository-url https://test.pypi.org/legacy/ dist/*

# Install 'pydriosm':

# Download .whl files from https://www.lfd.uci.edu/~gohlke/pythonlibs/ to install some packages, if necessary.
pip install GDAL-3.0.2-cp38-cp38-win_amd64.whl
pip install Fiona-1.8.13-cp38-cp38-win_amd64.whl
pip install Shapely-1.6.4.post2-cp38-cp38-win_amd64.whl

pip install --upgrade --extra-index-url https://test.pypi.org/simple/ pydriosm

# Upload the tested distributions to PyPI
twine upload dist/*

"""

# Setting preference for pandas
from pyhelpers.settings import pd_preferences

pd_preferences()


""" Import pydriosm """
import pydriosm as dri

subregion_list = dri.fetch_subregion_info_catalogue("GeoFabrik-subregion-name-list")
print(subregion_list)


""" 1. Download data ============================================================================================= """

subregion_name = 'london'  # or subregion_name = 'London'  # case-insensitive and fuzzy (but not too... fuzzy)
dri.download_subregion_osm_file(subregion_name, osm_file_format=".osm.pbf",
                                download_dir=None, update=False,
                                download_confirmation_required=True, deep_retry=False,
                                verbose=True)

# Default filename and file path
default_fn, default_fp = dri.get_default_path_to_osm_file(subregion_name,
                                                          osm_file_format=".osm.pbf",
                                                          mkdir=False, update=False)
print("Default filename: {}".format(default_fn))
print("Default file path: {}".format(default_fp))

# Specify the our own data directory
customised_data_dir = "test_data"
# So "test_data" folder will be created in our current working directory

# Alternatively, we could specify a full path
# import os
# customised_data_dir = os.path.join(os.getcwd(), "test_data")

# Download .pbf data of both 'London' and 'Kent' to the `customised_data_dir`
dri.download_subregion_osm_file('London', 'Kent', osm_file_format=".osm.pbf",
                                download_dir=customised_data_dir, update=False,
                                download_confirmation_required=True, deep_retry=False,
                                verbose=True)

""" 2. Read/parse data =========================================================================================== """

# 2.1  .osm.pbf data
greater_london = dri.read_osm_pbf(subregion_name, data_dir=None, parsed=True,
                                  file_size_limit=50, fmt_other_tags=True,
                                  fmt_single_geom=True, fmt_multi_geom=True,
                                  update=False, download_confirmation_required=True,
                                  pickle_it=False, rm_osm_pbf=False, verbose=True)

greater_london_test = dri.read_osm_pbf(subregion_name, data_dir=customised_data_dir,
                                       verbose=True)

# 2.2  .shp.zip / **.shp** data
layer_name = 'railways'  # We must specify a layer

# Read the .shp.zip file
greater_london_shp = dri.read_shp_zip(subregion_name, layer=layer_name,
                                      feature=None, data_dir=None, update=False,
                                      download_confirmation_required=True,
                                      pickle_it=True, rm_extracts=False,
                                      rm_shp_zip=False, verbose=True)

greater_london_shp_rail = dri.read_shp_zip(subregion_name, layer=layer_name,
                                           feature='rail')
rail = greater_london_shp[greater_london_shp.fclass == 'rail']
greater_london_shp_rail.equals(rail)  # True

# To merge .shp files of multiple subregions on a specific layer
subregion_names = ['London', 'Kent']
dri.merge_multi_shp(subregion_names, layer=layer_name, update_shp_zip=False,
                    download_confirmation_required=True, data_dir=None,
                    prefix="gis_osm", rm_zip_extracts=False, rm_shp_parts=False,
                    merged_shp_dir=None, verbose=True)

default_fn_, default_fp_ = dri.get_default_path_to_osm_file(subregion_names[0],
                                                            osm_file_format=".shp.zip")
print(default_fp_)


""" 3. Import and retrieve data with a PostgreSQL server ========================================================= """

osmdb = dri.OSM(username='postgres', password=None, host='localhost', port=5432,
                database_name='test_osmdb')
# Or simply,
# osmdb = dri.OSM(database_name='test_osmdb')


# 3.1  Import the data to the database
osmdb.dump_osm_pbf_data(greater_london, table_name=subregion_name, parsed=True,
                        if_exists='replace', chunk_size=None,
                        subregion_name_as_table_name=True, verbose=True)


# 3.2  Retrieve data from the database
greater_london_retrieval = osmdb.read_osm_pbf_data(table_name=subregion_name,
                                                   parsed=True,
                                                   subregion_name_as_table_name=True,
                                                   chunk_size=None, sorted_by_id=True)

greater_london['points'].equals(greater_london_retrieval['points'])  # True

# To query data of a specific layer (or several layers), or in a specific order of layers (schemas)
london_points_lines = osmdb.read_osm_pbf_data(subregion_name, 'points', 'lines')
london_lines_mul = osmdb.read_osm_pbf_data('london', 'lines', 'multilinestrings')


# 3.3  Import data of all subregions of a given (sub)region to the database
subregions = dri.retrieve_names_of_subregions_of('Central America', deep=False)

# To import data of all contained in `subregions`:
dri.psql_osm_pbf_data_extracts(*subregions,
                               username='postgres', password=None,
                               host='localhost', port=5432,
                               database_name='test_osmdb',
                               data_dir=customised_data_dir,
                               update_osm_pbf=False, if_table_exists='replace',
                               file_size_limit=50, parsed=True,
                               fmt_other_tags=True, fmt_single_geom=True,
                               fmt_multi_geom=True,
                               pickle_raw_file=False, rm_raw_file=False,
                               confirmation_required=True, verbose=True)

# To import all subregion data of "Great Britain", find its all subregions
gb_subregions_shallow = dri.retrieve_names_of_subregions_of('Great Britain', deep=False)
print(gb_subregions_shallow)
gb_subregions_deep = dri.retrieve_names_of_subregions_of('Great Britain', deep=True)
print(gb_subregions_deep)

# To drop the database 'osm_pbf_data_extracts'
osmdb.drop()

# To remove the files generated from the above
from pyhelpers.dir import rm_dir

rm_dir(dri.cd_dat_geofabrik("Europe"))
rm_dir(dri.regulate_input_data_dir(customised_data_dir))
