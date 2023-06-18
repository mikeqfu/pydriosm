"""
Update (prepacked) package data.
"""

import time

from pyhelpers.ops import confirmed

from .downloader import BBBikeDownloader, GeofabrikDownloader


def _update_prepacked_data(verbose=True, interval=5):
    """
    Update prepacked data used by the downloader classes.

    :param verbose: whether to print relevant information in console, defaults to ``True``
    :type verbose: bool | int
    :param interval: time gap (in seconds) between the updating of different classes,
        defaults to ``5`` (seconds)
    :type interval: int | float

    **Examples**::

        >>> from pydriosm._updater import _update_prepacked_data

        >>> _update_prepacked_data(verbose=True)
        To update resources (which may take a few minutes)
        ? [No]|Yes: no
    """

    if confirmed("To update resources (which may take a few minutes)\n?"):

        meth_args = {
            'update': True,
            'confirmation_required': False,
            'verbose': verbose,
        }

        # -- Geofabrik -----------------------------------------------------------------------------
        gfd = GeofabrikDownloader()

        _ = gfd.get_download_index(**meth_args)

        time.sleep(interval)

        _ = gfd.get_continent_tables(**meth_args)

        time.sleep(interval)

        _ = gfd.get_region_subregion_tier(**meth_args)

        time.sleep(interval)

        _ = gfd.get_catalogue(**meth_args)

        time.sleep(interval)

        _ = gfd.get_valid_subregion_names(**meth_args)

        time.sleep(interval)

        # -- BBBike --------------------------------------------------------------------------------
        bbd = BBBikeDownloader()

        _ = bbd.get_names_of_cities(**meth_args)

        time.sleep(interval)

        _ = bbd.get_coordinates_of_cities(**meth_args)

        time.sleep(interval)

        _ = bbd.get_subregion_index(**meth_args)

        time.sleep(interval)

        _ = bbd.get_valid_subregion_names(**meth_args)

        time.sleep(interval)

        _ = bbd.get_catalogue(**meth_args)

        if verbose:
            print("\nUpdate finished.")
