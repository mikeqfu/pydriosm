from .downloader import BBBikeDownloader, GeofabrikDownloader
from .ios import PostgresOSM
from .reader import BBBikeReader, GeofabrikReader
from .settings import gdal_configurations

gdal_configurations(reset=False)

__all__ = ['downloader', 'GeofabrikDownloader', 'BBBikeDownloader',
           'reader', 'GeofabrikReader', 'BBBikeReader',
           'ios', 'PostgresOSM']

__package_name__ = 'pydriosm'
__package_name_alt__ = 'PyDriosm'
__version__ = '2.0.1'
__author__ = 'Qian Fu'
__email__ = 'qian.fu@outlook.com'
__description__ = "An open-source tool for downloading, reading and PostgreSQL-based I/O of OpenStreetMap data."
