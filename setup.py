import setuptools

import pydriosm

with open("README.rst", 'r', encoding='utf-8') as readme:
    long_description = readme.read()

setuptools.setup(

    name=pydriosm.__package_name__,

    version=pydriosm.__version__,

    description=pydriosm.__description__,
    long_description=long_description,
    long_description_content_type="text/x-rst",

    url='https://github.com/mikeqfu/pydriosm',

    author=pydriosm.__author__,
    author_email=pydriosm.__email__,

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
        'Documentation': 'https://pydriosm.readthedocs.io/en/latest/',
        'Source': 'https://github.com/mikeqfu/pydriosm',
        'Tracker': 'https://github.com/mikeqfu/pydriosm/issues',
    },

    packages=setuptools.find_packages(exclude=["*.tests", "tests.*", "tests"]),

    install_requires=[
        'beautifulsoup4',
        'Fiona',
        'fuzzywuzzy',
        'GDAL~=3.1.4',
        'geopandas',
        'html5lib',
        'humanfriendly',
        'lxml',
        'more-itertools',
        'pandas~=1.1.5',
        'psycopg2',
        'pyhelpers>=1.2.9',
        'pyproj',
        'pyshp',
        'requests',
        'Shapely',
        'SQLAlchemy',
        'SQLAlchemy-Utils',
        'tqdm',
    ],

    package_data={"": ["requirements.txt", "LICENSE"]},
    include_package_data=True,

)
