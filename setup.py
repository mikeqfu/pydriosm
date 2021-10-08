import setuptools

# noinspection PyProtectedMember
from pydriosm import __author__, __description__, __email__, __package__, __version__

with open("README.rst", 'r', encoding='utf-8') as readme:
    long_description = readme.read()

setuptools.setup(

    name=__package__,

    version=__version__,

    description=__description__,
    long_description=long_description,
    long_description_content_type="text/x-rst",

    url='https://github.com/mikeqfu/pydriosm',

    author=__author__,
    author_email=__email__,

    license='GPLv3',

    classifiers=[
        'Intended Audience :: Education',
        'Intended Audience :: End Users/Desktop',
        'Intended Audience :: Information Technology',
        'Intended Audience :: Science/Research',

        'Topic :: Education',
        'Topic :: Scientific/Engineering',
        'Topic :: Utilities',

        'License :: OSI Approved :: GNU General Public License v3 (GPLv3)',

        'Programming Language :: Python :: 3',
        'Operating System :: Microsoft :: Windows',
        'Operating System :: POSIX :: Linux'
    ],

    keywords=['Python',
              'OpenStreetMap', 'OSM', 'PostgreSQL',
              'Geofabrik', 'BBBike',
              'Protocolbuffer Binary Format', 'PBF Format',
              'Shapefile', 'Shapefiles'],

    project_urls={
        'Documentation': 'https://pydriosm.readthedocs.io/en/{}/'.format(__version__),
        'Source': 'https://github.com/mikeqfu/pydriosm',
        'Tracker': 'https://github.com/mikeqfu/pydriosm/issues',
    },

    packages=setuptools.find_packages(exclude=["*.tests", "tests.*", "tests"]),

    install_requires=[
        'beautifulsoup4',
        'lxml',
        'GDAL>=3.0',
        'html5lib',
        'humanfriendly',
        'lxml',
        'more-itertools',
        'pyshp',
        'tqdm',
        # 'Fiona',
        # 'geopandas',
        'pyhelpers>=1.2.17',  # which requires the following dependencies:
        # 'Shapely',
        # 'pyproj',
        # 'requests',
        # 'pandas',
        # 'fuzzywuzzy',
        # 'psycopg2',
        # 'SQLAlchemy',
    ],

    package_data={"": ["requirements.txt", "LICENSE"]},
    include_package_data=True,

)
