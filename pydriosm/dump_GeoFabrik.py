# Download a bunch of OSM data extracts and import them to local PostgreSQL

import gc
import math
import os
import rapidjson
import time

import ogr
import pandas as pd

from pydriosm.download_GeoFabrik import download_subregion_osm_file, remove_subregion_osm_file
from pydriosm.download_GeoFabrik import get_region_subregion_index
from pydriosm.osm_psql import OSM
from pydriosm.read_GeoFabrik import justify_subregion_input, parse_layer_data, read_osm_pbf
from pydriosm.utils import confirmed, split_list


# Retrieve all subregions (if available) from index
def retrieve_subregions(region_name):
    """
    Reference:
    https://stackoverflow.com/questions/9807634/find-all-occurrences-of-a-key-in-nested-python-dictionaries-and-lists
    :param region_name: [str] name of a (sub)region
    :return: [str or None] (list of) subregions if available; None otherwise
    """

    def find_subregions(reg_name, reg_sub_idx):
        for k, v in reg_sub_idx.items():
            if k == reg_name:
                yield list(v.keys()) if isinstance(v, dict) else [reg_name] if isinstance(reg_name, str) else reg_name
            elif isinstance(v, dict):
                for sub in find_subregions(reg_name, v):
                    yield list(sub.keys()) if isinstance(sub, dict) else [sub] if isinstance(sub, str) else sub

    region_subregion_index = get_region_subregion_index("GeoFabrik-region-subregion-index", file_format=".pickle")
    result = list(find_subregions(region_name, region_subregion_index))[0]
    return result


# Dump data extracts to PostgreSQL
def psql_subregion_osm_data_extracts(selected_subregions, update_osm_pbf=False, if_exists='replace', file_size_limit=50,
                                     granulated=True, fmt_other_tags=True, fmt_single_geom=True, fmt_multi_geom=True,
                                     rm_raw_file=False):
    """
    Import data of selected or all (sub)regions, which do not have (sub-)subregions, into PostgreSQL server

    :param selected_subregions: [list or None]
    :param update_osm_pbf: [bool] False (default)
    :param if_exists: [str] 'replace' (default); 'append'; or 'fail'
    :param file_size_limit: [int] 100 (default)
    :param granulated: [bool]
    :param fmt_other_tags: [bool]
    :param fmt_single_geom: [bool]
    :param fmt_multi_geom: [bool]
    :param rm_raw_file: [bool] True (default)
    :return:
    """
    if selected_subregions:
        subregion_names = selected_subregions
        confirm_msg = "To dump GeoFabrik OSM data extracts of the following subregions to PostgreSQL? \n{}\n".format(
            "\n".join(subregion_names))
    else:
        subregion_names = get_region_subregion_index("GeoFabrik-no-subregion-list")
        confirm_msg = "To dump GeoFabrik OSM data extracts of all subregions to PostgreSQL? "

    if confirmed(confirm_msg):

        # Connect to PostgreSQL server
        osmdb = OSM()
        osmdb.connect_db(database_name='osm_data_extracts')

        err_subregion_names = []
        for subregion_name in subregion_names:
            subregion_filename, path_to_osm_pbf = justify_subregion_input(subregion_name)

            if not os.path.isfile(path_to_osm_pbf) or update_osm_pbf:
                download_subregion_osm_file(subregion_name, download_path=path_to_osm_pbf, update=update_osm_pbf)

            file_size_in_mb = round(os.path.getsize(path_to_osm_pbf) / (1024 ** 2), 1)

            try:
                if file_size_in_mb <= file_size_limit:

                    subregion_osm_pbf = read_osm_pbf(
                        subregion_name, download_confirmation_required=False,
                        file_size_limit=file_size_limit, granulated=granulated,
                        fmt_other_tags=fmt_other_tags, fmt_single_geom=fmt_single_geom, fmt_multi_geom=fmt_multi_geom,
                        pickle_it=False, rm_raw_file=rm_raw_file)

                    if subregion_osm_pbf is not None:
                        osmdb.dump_osm_pbf_data(subregion_osm_pbf, table_name=subregion_name, if_exists=if_exists)
                        del subregion_osm_pbf
                        gc.collect()

                else:
                    print("\nParsing and importing \"{}\" feature-wisely to PostgreSQL ... ".format(subregion_name))
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

                            if osmdb.subregion_table_exists(lyr_name, subregion_name) and if_exists == 'replace':
                                osmdb.drop_subregion_data_by_layer(subregion_name, lyr_name)

                            # Loop through all available features
                            for lyr_chunk in chunked_lyr_feats:
                                lyr_chunk_dat = pd.DataFrame(rapidjson.loads(f.ExportToJson()) for f in lyr_chunk)
                                lyr_chunk_dat = parse_layer_data(lyr_chunk_dat, lyr_name,
                                                                 fmt_other_tags, fmt_single_geom, fmt_multi_geom)
                                if_exists_ = if_exists if if_exists == 'fail' else 'append'
                                osmdb.dump_osm_pbf_data_by_layer(lyr_chunk_dat, if_exists=if_exists_,
                                                                 schema_name=lyr_name, table_name=subregion_name)
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
                err_subregion_names.append(subregion_name)

            if subregion_name != subregion_names[-1]:
                time.sleep(60)

        if len(err_subregion_names) == 0:
            print("\nMission accomplished.\n")
        else:
            print("\nErrors occurred when parsing data of the following subregion(s):")
            print(*err_subregion_names, sep=", ")


# england_subregions = retrieve_subregions('England')
