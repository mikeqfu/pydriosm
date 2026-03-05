import gc

import pandas as pd
from pyhelpers._cache import _check_dependencies, _check_relative_pathname, _print_failure_message
from pyhelpers.ops import get_number_of_chunks, split_list
from pyhelpers.store import save_data

from pydriosm.ios._base import BaseIOS
from pydriosm.reader._pbf import PBF


class ImportPBF(BaseIOS):
    """
    A class for importing parsed PBF data.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def _import_pbf(self, subregion_name_, osm_file_format, path_to_osm_pbf, chunk_size_limit=50,
                    expand=False, parse_geometry=False, parse_properties=False,
                    parse_other_tags=False, if_exists='fail', pickle_pbf_file=False, verbose=False,
                    **kwargs):
        number_of_chunks = get_number_of_chunks(path_to_osm_pbf, chunk_size_limit)

        if verbose:
            print(f'Reading "{_check_relative_pathname(path_to_osm_pbf)}"', end=" ... ")

        osm_pbf_data = PBF.read_pbf(
            path_to_file=path_to_osm_pbf,
            number_of_chunks=number_of_chunks,
            expand=expand,
            parse_geometry=parse_geometry,
            parse_properties=parse_properties,
            parse_other_tags=parse_other_tags
        )

        if verbose:
            print("Done.")

        if osm_pbf_data is not None:
            import_args = {
                'osm_data': osm_pbf_data,
                'table_name': subregion_name_,
                'if_exists': if_exists,
                'confirmation_required': False,
                'verbose': 2 if verbose else False,
            }
            kwargs.update(import_args)
            self.import_osm_data(**kwargs)

            if pickle_pbf_file:
                path_to_pickle = path_to_osm_pbf.replace(osm_file_format, "-pbf.pickle")
                save_data(osm_pbf_data, path_to_pickle, verbose=verbose)

        del osm_pbf_data
        gc.collect()

    def _import_pbf_layer(self, layer, layer_name, subregion_name_, number_of_chunks=1,
                          expand=False, parse_geometry=False, parse_properties=False,
                          parse_other_tags=False, pickle_pbf_file=False, verbose=False,
                          raise_error=True, **kwargs):
        if verbose:
            print(f'\t"{layer_name}"', end=" ... ")

        features = [feat for feat in layer]
        count_of_features = len(features)

        list_of_chunks = split_list(lst=features, num_of_sub=number_of_chunks)

        del features
        gc.collect()

        layer_dat_list = []
        try:
            for chunk in list_of_chunks:  # Loop through all chunks
                if expand:
                    lyr_dat = pd.DataFrame(f.ExportToJson(as_object=True) for f in chunk)
                else:
                    lyr_dat = pd.DataFrame([f.ExportToJson() for f in chunk], columns=[layer_name])

                layer_dat = PBF.transform_pbf_layer_field(
                    layer_data=lyr_dat, layer_name=layer_name, parse_geometry=parse_geometry,
                    parse_properties=parse_properties, parse_other_tags=parse_other_tags)

                import_args = {
                    'layer_data': layer_dat,
                    'table_name': subregion_name_,
                    'schema_name': layer_name,
                    'if_exists': 'append',  # if_exists if if_exists == 'fail' else 'append'
                    'confirmation_required': False,
                }
                kwargs.update(import_args)
                self.import_osm_layer(**kwargs)

                if pickle_pbf_file:
                    layer_dat_list.append(layer_dat)

                del layer_dat
                gc.collect()

            if verbose:
                print(f"Done. ({count_of_features} features)")

        except Exception as e:
            _print_failure_message(
                e=e, prefix="Failed. Error:", verbose=verbose, raise_error=raise_error)

        return layer_dat_list

    def _import_pbf_chunk_wisely(self, subregion_name_, osm_file_format, path_to_osm_pbf,
                                 chunk_size_limit=50, expand=False, parse_geometry=False,
                                 parse_properties=False, parse_other_tags=False, if_exists='fail',
                                 pickle_pbf_file=False, verbose=False, raise_error=False,
                                 **kwargs):
        # Reference: https://gdal.org/python/osgeo.ogr.Feature-class.html

        if verbose:
            print(f'Importing the data of "{subregion_name_}" chunk-wisely\n'
                  f'  into {self.address} ... ')

        osgeo_ogr = _check_dependencies('osgeo.ogr')
        raw_osm_pbf = osgeo_ogr.Open(path_to_osm_pbf)
        layer_count = raw_osm_pbf.GetLayerCount()

        number_of_chunks = get_number_of_chunks(
            file_or_obj=path_to_osm_pbf, chunk_size_limit=chunk_size_limit)

        layer_names, layer_data_list = [], []
        for i in range(layer_count):
            layer = raw_osm_pbf.GetLayerByIndex(i)  # Hold the i-th layer
            layer_name = layer.GetName()

            tbl_exists = self.subregion_table_exists(
                subregion_name=subregion_name_, layer_name=layer_name)

            if tbl_exists:
                if if_exists == 'fail':
                    if verbose:
                        print(f'\tTable "{subregion_name_}" already exists.')

                    lyr_dat = PBF._read_layer_chunkwise(
                        layer, number_of_chunks=number_of_chunks, readable=True, expand=expand,
                        parse_geometry=parse_geometry, parse_properties=parse_properties,
                        parse_other_tags=parse_other_tags)

                    if pickle_pbf_file:
                        layer_names.append(layer_name)
                        layer_data_list.append(lyr_dat)

                    continue

                elif if_exists == 'replace':
                    self.drop_subregion_tables(
                        subregion_names=subregion_name_, schema_names=layer_name,
                        confirmation_required=False)

            layer_dat_list = self._import_pbf_layer(
                layer=layer, layer_name=layer_name, subregion_name_=subregion_name_,
                number_of_chunks=number_of_chunks, expand=expand, parse_geometry=parse_geometry,
                parse_properties=parse_properties, parse_other_tags=parse_other_tags,
                pickle_pbf_file=pickle_pbf_file, verbose=verbose, raise_error=raise_error,
                **kwargs)

            if pickle_pbf_file:
                layer_names.append(layer_name)
                layer_data_list.append(pd.concat(layer_dat_list, axis=0, ignore_index=True))

        raw_osm_pbf.Release()

        del raw_osm_pbf
        gc.collect()

        if pickle_pbf_file:
            osm_pbf_data = dict(zip(layer_names, layer_data_list))
            path_to_pickle = path_to_osm_pbf.replace(osm_file_format, "-pbf.pickle")
            save_data(osm_pbf_data, path_to_pickle, verbose=verbose)

        del osm_pbf_data
        gc.collect()
