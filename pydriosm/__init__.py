from .downloader import *
from .reader import *
from .ios import *
from .settings import gdal_configurations

gdal_configurations(reset=False)

__package_name__ = 'pydriosm'
__version__ = '2.0.0'
__author__ = 'Qian Fu'
__email__ = 'qian.fu@outlook.com'
__description__ = "A toolkit for manipulating OpenStreetMap data."
