import setuptools

import pydriosm.settings

with open("README.md", 'r') as readme:
    long_description = readme.read()

setuptools.setup(

    name='pydriosm',
    version='1.0.15',

    author='Qian Fu',
    author_email='qian.fu@outlook.com',

    description="Download, read/parse and import/export OpenStreetMap data extracts",
    long_description=long_description,
    long_description_content_type="text/markdown",

    url='https://github.com/mikeqfu/pydriosm',

    install_requires=[
        'Fiona',
        'fuzzywuzzy',
        'gdal==2.4.1',
        'geopandas',
        'humanfriendly',
        'more-itertools',
        'numpy',
        'pandas',
        'psycopg2',
        'pyhelpers',
        'pyshp',
        'python-Levenshtein',
        'python-rapidjson',
        'requests',
        'shapely',
        'sqlalchemy',
        'sqlalchemy-utils'
    ],

    packages=setuptools.find_packages(exclude=["*.tests", "tests.*", "tests"]),

    package_data={"pydriosm": ["dat/*"]},
    include_package_data=True,

    classifiers=[
        'License :: OSI Approved :: GNU General Public License v3 (GPLv3)',
        'Programming Language :: Python :: 3 :: Only',
        'Programming Language :: Python :: 3.6',
        'Programming Language :: Python :: 3.7',
        'Operating System :: Microsoft :: Windows',
    ],
)

pydriosm.settings.gdal_configurations(reset=False)
