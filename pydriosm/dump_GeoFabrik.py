# Download a bunch of OSM data extracts and import them to local PostgreSQL

import gc
import rapidjson

import ogr
import pandas as pd

from pydriosm.download_GeoFabrik import get_region_subregion_index, remove_subregion_osm_file
from pydriosm.osm_psql import OSM
from pydriosm.read_GeoFabrik import justify_subregion_input, read_osm_pbf
from pydriosm.utils import confirmed


# Dump data extracts to PostgreSQL
def psql_osm_extracts(update=False, file_size_limit=100, rm_raw_file=True):
    """
    :param update: [bool] False (default)
    :param file_size_limit: [int] 100 (default)
    :param rm_raw_file: [bool] True (default)
    :return:
    """
    if confirmed("To dump GeoFabrik OSM data extracts to PostgreSQL?"):
        subregion_names = get_region_subregion_index("GeoFabrik-no-subregion-list")

        osmdb = OSM()
        osmdb.connect_db(database_name='osm_extracts')
        for subregion_name in subregion_names:

            subregion_filename, path_to_osm_pbf = justify_subregion_input(subregion_name)

            subregion_osm_pbf = read_osm_pbf(
                subregion_name, update=update, download_confirmation_required=False, file_size_limit=file_size_limit,
                pickle_it=False, rm_raw_file=False)

            if subregion_osm_pbf is not None:
                osmdb.dump_data(subregion_osm_pbf, table_name=subregion_name)
                del subregion_osm_pbf
                gc.collect()

            else:
                raw_osm_pbf = ogr.Open(path_to_osm_pbf)
                layer_count = raw_osm_pbf.GetLayerCount()
                print("\nParsing and importing \"{}\" feature-wisely ... ".format(subregion_name))
                for i in range(layer_count):
                    lyr = raw_osm_pbf.GetLayerByIndex(i)  # Hold the i-th layer
                    layer_name = lyr.GetName()
                    print("          \"{}\" ... ".format(layer_name), end="")
                    try:
                        # Reference: https://gdal.org/python/osgeo.ogr.Feature-class.html
                        f, counter = lyr.GetNextFeature(), 1
                        # Loop through all other available features
                        while f is not None:
                            feat = rapidjson.loads(f.ExportToJson())  # Get features from the i-th layer
                            feat_data = pd.DataFrame.from_dict(feat, orient='index')
                            if counter == 1:
                                osmdb.dump_layer_data(feat_data.T, subregion_name, layer_name, if_exists='replace')
                            else:
                                osmdb.dump_layer_data(feat_data.T, subregion_name, layer_name, if_exists='append')
                            del feat_data  # f.Destroy()
                            f = lyr.GetNextFeature()
                            counter += 1
                        print("Done. Total amount of features: {}".format(counter - 1))
                    except Exception as e:
                        print("Failed. {}".format(e))

            if rm_raw_file:
                remove_subregion_osm_file(path_to_osm_pbf)
