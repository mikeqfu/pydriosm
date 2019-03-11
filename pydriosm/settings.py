""" Settings

Reference: https://www.gdal.org/drv_osm.html

"""

import gdal


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
