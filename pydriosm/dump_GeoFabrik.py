# Download a bunch of OSM data extracts and import them to local PostgreSQL

import gc
import math
import os
import rapidjson
import time

import ogr
import pandas as pd

from pydriosm.download_GeoFabrik import download_subregion_osm_file, remove_subregion_osm_file
from pydriosm.download_GeoFabrik import fetch_region_subregion_tier, retrieve_subregion_names_from
from pydriosm.download_GeoFabrik import get_default_path_to_osm_file
from pydriosm.osm_psql import OSM
from pydriosm.read_GeoFabrik import parse_layer_data, read_osm_pbf
from pydriosm.utils import confirmed, regulate_input_data_dir, split_list


# Dump data extracts to PostgreSQL
def psql_osm_pbf_data_extracts(*subregion_name, data_dir=None, update_osm_pbf=False, if_exists='replace',
                               file_size_limit=50, parsed=True, fmt_other_tags=True, fmt_single_geom=True,
                               fmt_multi_geom=True, rm_raw_file=False):
    """
    Import data of selected or all (sub)regions, which do not have (sub-)subregions, into PostgreSQL server

    :param subregion_name: [str or None]
    :param data_dir: [str or None]
    :param update_osm_pbf: [bool] False (default)
    :param if_exists: [str] 'replace' (default); 'append'; or 'fail'
    :param file_size_limit: [int] 100 (default)
    :param parsed: [bool]
    :param fmt_other_tags: [bool]
    :param fmt_single_geom: [bool]
    :param fmt_multi_geom: [bool]
    :param rm_raw_file: [bool] True (default)
    """
    if not subregion_name:
        subregion_names = fetch_region_subregion_tier("GeoFabrik-non-subregion-list")
        confirm_msg = "To dump GeoFabrik OSM data extracts of all subregions to PostgreSQL? "
    else:
        subregion_names = retrieve_subregion_names_from(*subregion_name)
        confirm_msg = "To dump GeoFabrik OSM data extracts of the following subregions to PostgreSQL? \n{}?\n".format(
            ", ".join(subregion_names))

    if confirmed(confirm_msg):

        # Connect to PostgreSQL server
        osmdb = OSM()
        osmdb.connect_db(database_name='osm_pbf_data_extracts')

        err_subregion_names = []
        for subregion_name_ in subregion_names:
            default_pbf_filename, default_path_to_pbf = get_default_path_to_osm_file(subregion_name_, ".osm.pbf")
            if not data_dir:  # Go to default file path
                path_to_osm_pbf = default_path_to_pbf
            else:
                osm_pbf_dir = regulate_input_data_dir(data_dir)
                path_to_osm_pbf = os.path.join(osm_pbf_dir, default_pbf_filename)

            download_subregion_osm_file(subregion_name_, osm_file_format=".osm.pbf", download_dir=data_dir,
                                        update=update_osm_pbf, download_confirmation_required=False)

            file_size_in_mb = round(os.path.getsize(path_to_osm_pbf) / (1024 ** 2), 1)

            try:
                if file_size_in_mb <= file_size_limit:

                    subregion_osm_pbf = read_osm_pbf(subregion_name_, data_dir, parsed, file_size_limit,
                                                     fmt_other_tags, fmt_single_geom, fmt_multi_geom,
                                                     update_osm_pbf, download_confirmation_required=False,
                                                     pickle_it=False, rm_raw_file=rm_raw_file)

                    if subregion_osm_pbf is not None:
                        osmdb.dump_osm_pbf_data(subregion_osm_pbf, table_name=subregion_name_, if_exists=if_exists)
                        del subregion_osm_pbf
                        gc.collect()

                else:
                    print("\nParsing and importing \"{}\" feature-wisely to PostgreSQL ... ".format(subregion_name_))
                    # Reference: https://gdal.org/python/osgeo.ogr.Feature-class.html
                    raw_osm_pbf = ogr.Open(path_to_osm_pbf)
                    layer_count = raw_osm_pbf.GetLayerCount()
                    for i in range(layer_count):
                        lyr = raw_osm_pbf.GetLayerByIndex(i)  # Hold the i-th layer
                        lyr_name = lyr.GetName()
                        print("                       {} ... ".format(lyr_name), end="")
                        try:
                            lyr_feats = [feat for _, feat in enumerate(lyr)]
                            feats_no, chunks_no = len(lyr_feats), math.ceil(file_size_in_mb / file_size_limit)
                            chunked_lyr_feats = split_list(lyr_feats, chunks_no)

                            del lyr_feats
                            gc.collect()

                            if osmdb.subregion_table_exists(lyr_name, subregion_name_) and if_exists == 'replace':
                                osmdb.drop_subregion_data_by_layer(subregion_name_, lyr_name)

                            # Loop through all available features
                            for lyr_chunk in chunked_lyr_feats:
                                lyr_chunk_dat = pd.DataFrame(rapidjson.loads(f.ExportToJson()) for f in lyr_chunk)
                                lyr_chunk_dat = parse_layer_data(lyr_chunk_dat, lyr_name,
                                                                 fmt_other_tags, fmt_single_geom, fmt_multi_geom)
                                if_exists_ = if_exists if if_exists == 'fail' else 'append'
                                osmdb.dump_osm_pbf_data_by_layer(lyr_chunk_dat, if_exists=if_exists_,
                                                                 schema_name=lyr_name, table_name=subregion_name_)
                                del lyr_chunk_dat
                                gc.collect()

                            print("Done. Total amount of features: {}".format(feats_no))

                        except Exception as e:
                            print("Failed. {}".format(e))

                    raw_osm_pbf.Release()
                    del raw_osm_pbf
                    gc.collect()

                if rm_raw_file:
                    remove_subregion_osm_file(path_to_osm_pbf)

            except Exception as e:
                print(e)
                err_subregion_names.append(subregion_name_)

            if subregion_name_ != subregion_names[-1]:
                time.sleep(60)

        if len(err_subregion_names) == 0:
            print("\nMission accomplished.\n")
        else:
            print("\nErrors occurred when parsing data of the following subregion(s):")
            print(*err_subregion_names, sep=", ")

        osmdb.disconnect()
        del osmdb
