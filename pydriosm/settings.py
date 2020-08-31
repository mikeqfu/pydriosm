""" Settings """

import gdal


def gdal_configurations(reset=False, max_tmpfile_size=5000):
    """
    Set GDAL configurations. See also [`GC-1 <https://www.gdal.org/drv_osm.html>`_]

    :param reset: reset to default settings, defaults to ``False``
    :type reset: bool
    :param max_tmpfile_size: maximum size of the temporary file, defaults to ``5000``
    :type max_tmpfile_size: int
    :return:
    """

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
