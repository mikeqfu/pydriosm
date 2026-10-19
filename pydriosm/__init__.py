# Copyright (c) 2019-2026 Qian Fu
#
# This program is free software: you can redistribute it and/or modify it under the terms of the
# GNU General Public License as published by the Free Software Foundation, either version 3 of
# the License, or (at your option) any later version.
#
# This program is distributed in the hope that it will be useful, but WITHOUT ANY WARRANTY;
# without even the implied warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.
# See the GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License along with this program.
# If not, see <https://www.gnu.org/licenses/>.

"""
Package initialization.
"""

import datetime
import importlib.metadata
import logging
import pathlib
import tomllib

from . import downloader, errors, ios, reader, utils
from .downloader import BBBikeDownloader, Downloader, GeofabrikDownloader
from .ios import BBBikeIOS, GeofabrikIOS, PostgresOSM
from .reader import BBBikeReader, GeofabrikReader, Reader

logging.getLogger(__name__).addHandler(logging.NullHandler())


def _load_metadata():
    """
    Extract package metadata from local configuration or installed distribution.

    This function attempts to parse metadata from ``pyproject.toml`` during
    local development and falls back gracefully to ``importlib.metadata`` when
    running within an installed site-packages environment.

    :return: A dictionary containing metadata key-value pairs.
    :rtype: dict[str, str | None]
    """

    package_name = __package__ or 'pydriosm'

    # Fetch standard distribution metadata
    dist_meta = importlib.metadata.metadata(package_name)
    version = dist_meta.get('Version')
    description = dist_meta.get('Summary')
    license_str = dist_meta.get('License')

    # Safely locate pyproject.toml for custom tool metadata
    current_dir = pathlib.Path(__file__).resolve().parent
    pyproject_toml = "pyproject.toml"

    possible_paths = [
        current_dir / pyproject_toml,  # Installed wheel location
        current_dir.parent / pyproject_toml,  # Local repository root
        pathlib.Path.cwd() / pyproject_toml,  # Working directory fallback
    ]

    pyproject_path = next((p for p in possible_paths if p.is_file()), None)

    if not pyproject_path:
        raise FileNotFoundError(
            f'Fatal error: "{pyproject_toml}" not found. '
            f'Configuration source is missing.'
        )

    with open(pyproject_path, mode='rb') as f:
        cfg = tomllib.load(f)

    project_info = cfg.get('project', {})
    custom_info = cfg.get('tool', {}).get('pydriosm', {}).get('metadata', {})

    name = project_info.get('name', package_name)
    version = version or project_info.get('version')
    description = description or project_info.get('description')

    authors_str = ', '.join(a.get('name', '') for a in project_info.get('authors', []))

    # Format copyright string
    start_year = 2019
    current_year = datetime.date.today().year
    years = f'{start_year}-{current_year}' if current_year > start_year else f'{start_year}'
    copyright_str = (
        f'Copyright (c) {years} {authors_str}'.strip() if authors_str
        else f'Copyright (c) {years}'
    )

    # Parse corresponding author details
    corr_auth_list = custom_info.get('corresponding-author', [])
    corr_author_str = ''
    affiliation_str = ''

    if isinstance(corr_auth_list, list) and corr_auth_list:
        first_corr = corr_auth_list[0]
        if isinstance(first_corr, dict):
            c_name = first_corr.get('name', '')
            c_email = first_corr.get('email', '')
            corr_author_str = f'{c_name} <{c_email}>' if c_email else c_name
            affiliation_str = first_corr.get('affiliation', '')

    return {
        'name': name,
        'version': version,
        'description': description,
        'license': license_str,
        'authors': authors_str,
        'copyright': copyright_str,

        # Custom medata
        'project-name': custom_info.get('project-name', ''),
        'project-start': custom_info.get('project-start', ''),
        'corresponding-author': corr_author_str,
        'affiliation': affiliation_str,
        'funder': custom_info.get('funder', ''),
    }


METADATA = _load_metadata()

__project__ = METADATA.get('project-name')
__pkgname__ = METADATA.get('name')
__description__ = METADATA.get('description')

__title__ = f"{__project__}: {__description__.strip('.')}" if __description__ else __project__

__version__ = METADATA.get('version')
__license__ = METADATA.get('license')
__copyright__ = METADATA.get('copyright')

__first_release__ = METADATA.get('project-start')

__funder__ = METADATA.get("funder")

__author__ = METADATA.get('authors')
__corresponding_author__ = METADATA.get('corresponding-author')
__affiliation__ = METADATA.get('affiliation')

__all__ = [
    '__project__',
    '__title__',
    '__version__',
    '__license__',
    '__copyright__',
    '__first_release__',
    '__funder__',
    '__author__',
    '__corresponding_author__',

    # Downloaders
    'downloader',
    'Downloader',
    'BBBikeDownloader',
    'GeofabrikDownloader',

    # Readers
    'reader',
    'Reader',
    'GeofabrikReader',
    'BBBikeReader',

    # Database I/O
    'ios',
    'BBBikeIOS',
    'GeofabrikIOS',
    'PostgresOSM',

    # Helper modules
    'errors',
    'utils',
]
