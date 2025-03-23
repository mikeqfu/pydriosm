"""
Download `OpenStreetMap <https://www.openstreetmap.org/>`_ (OSM) data from free download servers:
`Geofabrik <https://download.geofabrik.de/>`_ and `BBBike <https://download.bbbike.org/>`_.
"""

from ._bbbike import BBBikeDownloader
from ._geofabrik import GeofabrikDownloader

__all__ = [
    'GeofabrikDownloader',
    'BBBikeDownloader',
]
