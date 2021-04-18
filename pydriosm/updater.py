"""
Updating package data.
"""

import time

from pyhelpers.ops import confirmed

from .downloader import BBBikeDownloader, GeofabrikDownloader


def update_package_data(confirmation_required=True, interval_sec=2, verbose=True):
    """
    Update package data.

    :param confirmation_required: whether asking for confirmation to proceed, defaults to ``True``
    :type confirmation_required: bool
    :param interval_sec: time gap (in seconds) between the updating of different classes, defaults to ``5``
    :type interval_sec: int
    :param verbose: whether to print relevant information in console, defaults to ``True``
    :type verbose: bool, int

    **Example**::

        >>> from pydriosm.updater import update_package_data

        >>> update_package_data(confirmation_required=True, verbose=True)

    |

    (**THE END OF** :ref:`Modules<modules>`.)
    """

    if confirmed("To update resources (which may take a few minutes)\n?"):

        update = True

        geofabrik_downloader = GeofabrikDownloader()

        _ = geofabrik_downloader.get_download_index(
            update=update, confirmation_required=confirmation_required, verbose=verbose)

        time.sleep(interval_sec)

        _ = geofabrik_downloader.get_continents_subregion_tables(
            update=update, confirmation_required=confirmation_required, verbose=verbose)

        time.sleep(interval_sec)

        _ = geofabrik_downloader.get_region_subregion_tier(
            update=update, confirmation_required=confirmation_required, verbose=verbose)

        time.sleep(interval_sec)

        _ = geofabrik_downloader.get_download_catalogue(
            update=update, confirmation_required=confirmation_required, verbose=verbose)

        time.sleep(interval_sec)

        _ = geofabrik_downloader.get_list_of_subregion_names(
            update=update, confirmation_required=confirmation_required, verbose=verbose)

        time.sleep(interval_sec)

        bbbike_downloader = BBBikeDownloader()

        _ = bbbike_downloader.get_list_of_cities(
            update=update, confirmation_required=confirmation_required, verbose=verbose)

        time.sleep(interval_sec)

        _ = bbbike_downloader.get_coordinates_of_cities(
            update=update, confirmation_required=confirmation_required, verbose=verbose)

        time.sleep(interval_sec)

        _ = bbbike_downloader.get_subregion_catalogue(
            update=update, confirmation_required=confirmation_required, verbose=verbose)

        time.sleep(interval_sec)

        _ = bbbike_downloader.get_list_of_subregion_names(
            update=update, confirmation_required=confirmation_required, verbose=verbose)

        time.sleep(interval_sec)

        _ = bbbike_downloader.get_download_index(
            update=update, confirmation_required=confirmation_required, verbose=verbose)

        if verbose:
            print("\nUpdate finished.")
