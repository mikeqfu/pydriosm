"""
Download `OpenStreetMap <https://www.openstreetmap.org/>`_ (OSM) data from free download servers:
`Geofabrik <https://download.geofabrik.de/>`_ and `BBBike <https://download.bbbike.org/>`_.
"""

from .bbbike import BBBikeDownloader
from .geofabrik import GeofabrikDownloader

__all__ = [
    'GeofabrikDownloader',
    'BBBikeDownloader',
]
