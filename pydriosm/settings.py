"""
Default settings for working environment.
"""

import osgeo.gdal


def gdal_configurations(reset=False, max_tmpfile_size=5000):
    """
    Set `GDAL <https://gdal.org/index.html>`_ configurations.
    See also [`GC-1 <https://www.gdal.org/drv_osm.html>`_].

    :param reset: reset to default settings, defaults to ``False``
    :type reset: bool
    :param max_tmpfile_size: maximum size of the temporary file, defaults to ``5000``
    :type max_tmpfile_size: int

    **Example**::

        >>> from pydriosm.settings import gdal_configurations

        >>> gdal_configurations(max_tmpfile_size=500)
    """

    if not reset:
        # Whether to enable interleaved reading. Defaults to NO.
        osgeo.gdal.SetConfigOption('OGR_INTERLEAVED_READING', 'YES')
        # Whether to enable custom indexing. Defaults to YES.
        osgeo.gdal.SetConfigOption('USE_CUSTOM_INDEXING', 'YES')
        # Whether to compress nodes in temporary DB. Defaults to NO.
        osgeo.gdal.SetConfigOption('COMPRESS_NODES', 'YES')
        # Maximum size in MB of in-memory temporary file. If it exceeds that value,
        # it will go to disk. Defaults to 100.
        osgeo.gdal.SetConfigOption('MAX_TMPFILE_SIZE', str(max_tmpfile_size))
    else:
        osgeo.gdal.SetConfigOption('OGR_INTERLEAVED_READING', 'NO')
        osgeo.gdal.SetConfigOption('USE_CUSTOM_INDEXING', 'YES')
        osgeo.gdal.SetConfigOption('COMPRESS_NODES', 'NO')
        osgeo.gdal.SetConfigOption('MAX_TMPFILE_SIZE', '100')
