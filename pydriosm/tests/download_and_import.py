# Download a bunch of OSM data extracts and import them to local PostgreSQL

import fuzzywuzzy.process

from pydriosm.download_GeoFabrik import download_subregion_osm_file, get_region_subregion_index, \
    get_subregion_info_index
from pydriosm.osm_psql import OSM
from pydriosm.read_GeoFabrik import read_raw_osm_pbf
from pydriosm.utils import get_all_subregions


# Make OSM data available for a given region and (optional) all subregions of
def make_subregion_osm_data_available(region_name, file_format=".osm.pbf", update=False):

    region_names = get_subregion_info_index('GeoFabrik-subregion-name-list', update=False)
    region_name_ = fuzzywuzzy.process.extractOne(region_name, region_names, score_cutoff=10)[0]

    region_subregion_index = get_region_subregion_index("GeoFabrik-region-subregion-index", update=False)
    subregions = list(get_all_subregions(region_name_, region_subregion_index))[0]

    if subregions:
        subregions = list(subregions.keys())
        for subregion in subregions:
            download_subregion_osm_file(subregion, file_format=file_format, update=update)
    else:
        download_subregion_osm_file(region_name, file_format=file_format, update=update)


#
def import_osm_extracts(update=False):

    subregion_names = get_region_subregion_index("GeoFabrik-no-subregion-list")

    osmdb = OSM()
    osmdb.connect_db(database_name='osm_extracts')
    for subregion_name in subregion_names:
        subregion_osm_pbf = read_raw_osm_pbf(subregion_name, update=update)
        osmdb.import_data(subregion_osm_pbf, table_name=subregion_name)
