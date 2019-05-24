""" Settings

Reference: https://www.gdal.org/drv_osm.html

"""

import gdal
import pandas


# Set GDAL configurations
def gdal_configurations(reset=False, max_tmpfile_size=2500):
    if not reset:
        # Whether to enable interleaved reading. Defaults to NO.
        gdal.SetConfigOption('OGR_INTERLEAVED_READING', 'YES')
        # Whether to enable custom indexing. Defaults to YES.
        gdal.SetConfigOption('USE_CUSTOM_INDEXING', 'YES')
        # Whether to compress nodes in temporary DB. Defaults to NO.
        gdal.SetConfigOption('COMPRESS_NODES', 'YES')
        # Maximum size in MB of in-memory temporary file. If it exceeds that value, it will go to disk. Defaults to 100.
        gdal.SetConfigOption('MAX_TMPFILE_SIZE', str(max_tmpfile_size))
    else:
        gdal.SetConfigOption('OGR_INTERLEAVED_READING', 'NO')
        gdal.SetConfigOption('USE_CUSTOM_INDEXING', 'YES')
        gdal.SetConfigOption('COMPRESS_NODES', 'NO')
        gdal.SetConfigOption('MAX_TMPFILE_SIZE', '100')


# Set preferences for displaying results
def pd_preferences(reset=False):
    if not reset:
        pandas.set_option('display.precision', 2)
        pandas.set_option('expand_frame_repr', False)  # Set the representation of DataFrame NOT to wrap
        pandas.set_option('display.width', 600)  # Set the display width
        pandas.set_option('precision', 4)
        pandas.set_option('display.max_columns', 100)
        pandas.set_option('display.max_rows', 20)
        pandas.set_option('io.excel.xlsx.writer', 'xlsxwriter')
        pandas.set_option('mode.chained_assignment', None)
        pandas.set_option('display.float_format', lambda x: '%.4f' % x)
    else:
        pandas.reset_option('all')
