import time

from pyhelpers.ops import confirmed

from pydriosm.download_BBBike import collect_bbbike_download_catalogue
from pydriosm.download_BBBike import collect_bbbike_subregion_catalogue
from pydriosm.download_GeoFabrik import collect_continents_subregion_tables
from pydriosm.download_GeoFabrik import collect_region_subregion_tier
from pydriosm.download_GeoFabrik import collect_subregion_info_catalogue


def update_pkg_metadata(confirmation_required=True, verbose=True):

    if confirmed("To update package metadata? (Note that it may take a few minutes.)"):

        collect_subregion_info_catalogue(confirmation_required=confirmation_required, verbose=verbose)

        time.sleep(10)

        collect_continents_subregion_tables(confirmation_required=confirmation_required, verbose=verbose)

        time.sleep(10)

        collect_region_subregion_tier(confirmation_required=confirmation_required, update=False, verbose=verbose)

        time.sleep(10)

        collect_bbbike_subregion_catalogue(confirmation_required=confirmation_required, verbose=verbose)

        time.sleep(10)

        collect_bbbike_download_catalogue(confirmation_required=confirmation_required, verbose=verbose)

        if verbose:
            print("\nUpdate finished.")

# update_pkg_metadata(verbose=True)
