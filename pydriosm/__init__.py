import datetime

from .downloader import BBBikeDownloader, GeofabrikDownloader
from .ios import PostgresOSM
from .reader import BBBikeReader, GeofabrikReader

__all__ = [
    'downloader', 'GeofabrikDownloader', 'BBBikeDownloader',
    'reader', 'GeofabrikReader', 'BBBikeReader',
    'ios', 'PostgresOSM',
]

__project_name__ = 'PyDriosm'
__package_name__ = 'pydriosm'
__description__ = \
    f'{__package_name__}: ' \
    f'an open-source tool for downloading, reading and PostgreSQL-based I/O of OpenStreetMap data.'

__author__ = 'Qian Fu'
__affiliation__ = 'School of Engineering, University of Birmingham'
__email__ = 'q.fu@bham.ac.uk'

__copyright__ = f'2019-{datetime.datetime.now().year}, {__author__}'

__version__ = '2.0.4'
