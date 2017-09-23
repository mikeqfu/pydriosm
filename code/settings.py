""" Settings """

import gdal
from matplotlib import pyplot, rcParamsDefault
from numpy.core import arrayprint
from pandas import reset_option, set_option


# Set preferences for displaying results
def pd_preferences(reset=False):
    if not reset:
        set_option('expand_frame_repr', False)  # Set the representation of DataFrame NOT to wrap
        set_option('display.width', 560)  # Set the display width
        # set_option('precision', 4)
        set_option('display.max_columns', 100)
        set_option('display.max_rows', 10)
        set_option('io.excel.xlsx.writer', 'xlsxwriter')
        set_option('mode.chained_assignment', None)
    else:
        reset_option('all')


# Set preferences for displaying results
def np_preferences(reset=False):
    if not reset:
        arrayprint._line_width = 120
    else:
        arrayprint._line_width = 80  # 75


# Set preferences for plotting
def mpl_preferences(use_cambria=False, reset=False):
    """

    # import matplotlib as mpl
    # mpl.rc('font', family='Times New Roman')

    # Get a list of supported file formats for matplotlib savefig() function
    # plt.gcf().canvas.get_supported_filetypes()
    # plt.gcf().canvas.get_supported_filetypes_grouped()
    # (Aside: "gcf" is short for "get current fig" manager)

    """
    if not reset:
        pyplot.style.use('ggplot')
        if use_cambria:  # Use the font, 'Cambria'
            # Add 'Cambria' to the front of the 'font.serif' list
            pyplot.rcParams['font.serif'] = ['Cambria'] + pyplot.rcParams['font.serif']
            # Set 'font.family' to 'serif', so that matplotlib will use that list
            pyplot.rcParams['font.family'] = 'serif'
        pyplot.rcParams['font.size'] = 13
        pyplot.rcParams['font.weight'] = 'normal'
        pyplot.rcParams['legend.labelspacing'] = 0.9
        pyplot.rcParams['hatch.linewidth'] = 1.0
        pyplot.rcParams['hatch.color'] = 'k'
    else:
        pyplot.style.use('classic')
        pyplot.rcParams = rcParamsDefault


#
def gdal_configurations(reset=False):
    if not reset:
        # Whether to enable interleaved reading. Defaults to NO.
        gdal.SetConfigOption('OGR_INTERLEAVED_READING', 'YES')
        # Whether to enable custom indexing. Defaults to YES.
        gdal.SetConfigOption('USE_CUSTOM_INDEXING', 'YES')
        # Whether to compress nodes in temporary DB. Defaults to NO.
        gdal.SetConfigOption('COMPRESS_NODES', 'NO')
        # Maximum size in MB of in-memory temporary file. If it exceeds that value, it will go to disk. Defaults to 100.
        gdal.SetConfigOption('MAX_TMPFILE_SIZE', '2000')
    else:
        gdal.SetConfigOption('OGR_INTERLEAVED_READING', 'NO')
        gdal.SetConfigOption('USE_CUSTOM_INDEXING', 'YES')
        gdal.SetConfigOption('COMPRESS_NODES', 'NO')
        gdal.SetConfigOption('MAX_TMPFILE_SIZE', '100')


pd_preferences(reset=False)
np_preferences(reset=False)
mpl_preferences(use_cambria=False, reset=False)
gdal_configurations(reset=False)
