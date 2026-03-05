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
import json
import pkgutil

metadata = json.loads(pkgutil.get_data(__name__, "data/.metadata").decode())

__project__ = metadata['Project']
__pkgname__ = metadata['Package']

__author__ = metadata['Author']
__affil__ = metadata['Affiliation']
__email__ = metadata['Email']

__desc__ = metadata['Description']

__copyright__ = f'2019-{datetime.datetime.now().year} {__author__}'

__version__ = metadata['Version']
__license__ = metadata['License']

__first_release__ = metadata['First release']
