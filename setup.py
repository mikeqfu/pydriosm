import setuptools

import pydriosm.settings

with open("README.md", 'r') as readme:
    long_description = readme.read()

setuptools.setup(

    name='pydriosm',
    version='0.1.1',

    author='Qian Fu',
    author_email='qian.fu@outlook.com',

    description="Download, parse and store OSM data extracts",
    long_description=long_description,
    long_description_content_type="text/markdown",

    url='https://github.com/mikeqfu/pydriosm',

    install_requires=[
        'beautifulsoup4',
        'Fiona',
        'fuzzywuzzy',
        'gdal',
        'geopandas',
        'html5lib',
        'humanfriendly',
        'lxml',
        'numpy',
        'pandas',
        'pyshp',
        'python-Levenshtein',
        'requests',
        'shapely',
        'sqlalchemy',
        'sqlalchemy-utils',
        'tqdm'
    ],

    packages=setuptools.find_packages(exclude=["*.tests", "tests.*", "tests"]),

    package_data={"pydriosm": ["dat/*"]},
    include_package_data=True,

    classifiers=[
        'License :: OSI Approved :: GNU General Public License v3 (GPLv3)',
        'Programming Language :: Python :: 3',
        'Programming Language :: Python :: 3.4',
        'Programming Language :: Python :: 3.5',
        'Programming Language :: Python :: 3.6',
        'Programming Language :: Python :: 3.7',
        'Operating System :: Microsoft :: Windows :: Windows 7',
        'Operating System :: Microsoft :: Windows :: Windows 8',
        'Operating System :: Microsoft :: Windows :: Windows 8.1',
        'Operating System :: Microsoft :: Windows :: Windows 10',
    ],
)

pydriosm.settings.gdal_configurations()
