import json

import setuptools

with open(file="pydriosm/data/.metadata", mode='r') as metadata_file:
    metadata = json.load(metadata_file)

__pkgname__ = metadata['Package']
__version__ = metadata['Version']
__homepage__ = f'https://github.com/mikeqfu/{__pkgname__}'

setuptools.setup(
    name=__pkgname__,
    version=__version__,
    description=metadata['Description'],
    url=__homepage__,
    author=metadata['Author'],
    author_email=metadata['Email'],
    license=metadata['License'],
    project_urls={
        'Documentation': f'https://{__pkgname__}.readthedocs.io/en/{__version__}/',
        'Source': __homepage__,
        'Issue Tracker': f'{__homepage__}/issues',
    },
)
