"""
Package initialization.
"""

import datetime
import json

import pkg_resources

from .downloader import BBBikeDownloader, GeofabrikDownloader
from .ios import PostgresOSM
from .reader import BBBikeReader, GeofabrikReader

with open(pkg_resources.resource_filename(__name__, "data/metadata.json"), mode='r') as metadata_file:
    metadata = json.load(metadata_file)

__project__ = metadata['Project']
__pkgname__ = metadata['Package']

__author__ = metadata['Author']
__affiliation__ = metadata['Affiliation']
__author_email__ = metadata['Email']

__description__ = metadata['Description']

__copyright__ = f'2019-{datetime.datetime.now().year}, {__author__}'

__version__ = metadata['Version']
__license__ = metadata['License']

__all__ = [
    __author__,
    __description__,
    __author_email__,
    __pkgname__,
    __version__,
    'downloader', 'GeofabrikDownloader', 'BBBikeDownloader',
    'reader', 'GeofabrikReader', 'BBBikeReader',
    'ios', 'PostgresOSM',
]
