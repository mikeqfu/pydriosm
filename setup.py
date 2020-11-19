import setuptools

import pydriosm

with open("README.rst", 'r', encoding='utf-8') as readme:
    long_description = readme.read()

setuptools.setup(

    name=pydriosm.__package_name__,
    version=pydriosm.__version__,
    author=pydriosm.__author__,
    author_email=pydriosm.__email__,

    description=pydriosm.__description__,
    long_description=long_description,
    long_description_content_type="text/x-rst",

    url='https://github.com/mikeqfu/pydriosm',

    install_requires=[
        'beautifulsoup4~=4.9.3',
        'Fiona~=1.8.17',
        'fuzzywuzzy',
        'GDAL~=3.1.4',
        'geopandas~=0.8.1',
        'html5lib',
        'humanfriendly~=8.2',
        'lxml',
        'more-itertools',
        'pandas~=1.1.4',
        'psycopg2',
        'pyhelpers>=1.2.7',
        'pyproj',
        'pyshp',
        'requests',
        'Shapely~=1.7.1',
        'SQLAlchemy',
        'SQLAlchemy-Utils',
        'tqdm',
    ],

    packages=setuptools.find_packages(exclude=["*.tests", "tests.*", "tests"]),

    include_package_data=True,

    classifiers=[
        'License :: OSI Approved :: GNU General Public License v3 (GPLv3)',
        'Programming Language :: Python :: 3',
        'Operating System :: Microsoft :: Windows',
        'Operating System :: POSIX :: Linux'
    ],
)
