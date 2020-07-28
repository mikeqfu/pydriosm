import time

from pyhelpers.ops import confirmed

from download.download_BBBike import BBBike
from .download_GeoFabrik import collect_continents_subregion_tables, collect_region_subregion_tier, \
    collect_subregion_info_catalogue


def update_backup_data(confirmation_required=True, time_gap=5, verbose=True):
    """


    :param confirmation_required:
    :param time_gap:
    :param verbose:

    **Example**::

        from pydriosm.updater import update_backup_data

        confirmation_required = True
        time_gap              = 5
        verbose               = True

        update_backup_data(confirmation_required=True, verbose=True)
    """

    if confirmed("Updating package data may take a few minutes. Continue?"):

        collect_subregion_info_catalogue(confirmation_required=confirmation_required, verbose=verbose)

        time.sleep(time_gap)

        collect_continents_subregion_tables(confirmation_required=confirmation_required, verbose=verbose)

        time.sleep(time_gap)

        collect_region_subregion_tier(confirmation_required=confirmation_required, update=False, verbose=verbose)

        time.sleep(time_gap)

        bbbike = BBBike()

        bbbike.get_subregion_catalogue(update=True, confirmation_required=confirmation_required, verbose=verbose)

        time.sleep(time_gap)

        bbbike.get_download_dictionary(update=True, confirmation_required=confirmation_required, verbose=verbose)

        if verbose:
            print("\nUpdate finished.")
