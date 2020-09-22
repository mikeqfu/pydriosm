"""
Update package data.
"""

import time

from pyhelpers.ops import confirmed

from .downloader import BBBikeDownloader, GeoFabrikDownloader


def update_package_data(confirmation_required=True, interval_sec=5, verbose=True):
    """
    Update package data.

    :param confirmation_required: whether to prompt a message for confirmation to proceed, defaults to ``True``
    :type confirmation_required: bool
    :param interval_sec: time gap (in seconds) between the updating of different classes, defaults to ``5``
    :type interval_sec: int
    :param verbose: whether to print relevant information in console as the function runs, defaults to ``True``
    :type verbose: bool, int

    **Example**::

        from pydriosm.updater import update_package_data

        confirmation_required = True
        time_gap = 5
        verbose = True

        update_package_data(confirmation_required=True, verbose=True)
    """

    if confirmed("To update resources (which may take a few minutes)?"):

        geofabrik_downloader = GeoFabrikDownloader()

        _ = geofabrik_downloader.get_index_of_all_downloads(update=True, confirmation_required=confirmation_required,
                                                            verbose=verbose)

        time.sleep(interval_sec)

        _ = geofabrik_downloader.get_continents_subregion_tables(update=True,
                                                                 confirmation_required=confirmation_required,
                                                                 verbose=verbose)

        time.sleep(interval_sec)

        _ = geofabrik_downloader.get_region_subregion_tier(update=True, confirmation_required=confirmation_required,
                                                           verbose=verbose)

        time.sleep(interval_sec)

        _ = geofabrik_downloader.get_subregion_downloads_catalogue(update=True,
                                                                   confirmation_required=confirmation_required,
                                                                   verbose=verbose)

        time.sleep(interval_sec)

        _ = geofabrik_downloader.get_subregion_name_list(update=True, confirmation_required=confirmation_required,
                                                         verbose=verbose)

        time.sleep(interval_sec)

        bbbike_downloader = BBBikeDownloader()

        _ = bbbike_downloader.get_subregion_catalogue(update=True, confirmation_required=confirmation_required,
                                                      verbose=verbose)

        time.sleep(interval_sec)

        _ = bbbike_downloader.get_subregion_name_list(update=True, confirmation_required=confirmation_required,
                                                      verbose=verbose)

        time.sleep(interval_sec)

        _ = bbbike_downloader.get_download_dictionary(update=True, confirmation_required=confirmation_required,
                                                      verbose=verbose)

        if verbose:
            print("\nUpdate finished.")
