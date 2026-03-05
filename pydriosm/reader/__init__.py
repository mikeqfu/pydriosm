"""
Read the OSM data extracts in various file formats.
"""

from . import _base
from ._bbbike import BBBikeReader
from ._geofabrik import GeofabrikReader
from ._pbf import PBF
from ._shp import SHP
from ._var import VAR
from ._wrapper import Reader
from .formatter import convert_geometry_collection, convert_simplex_geometry, \
    process_geometry_layer, reformat_multipolygon_point, reformat_other_tags, refresh_other_tags

__all__ = [
    'GeofabrikReader', 'BBBikeReader', 'Reader',
    'formatter',
    'reformat_multipolygon_point',
    'process_geometry_layer',
    'convert_geometry_collection',
    'reformat_other_tags',
    'convert_simplex_geometry',
    'refresh_other_tags',
    'PBF', 'SHP', 'VAR',
    '_base'
]
