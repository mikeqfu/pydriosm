# PyDriosm

*A Python package for downloading, reading and PostgreSQL-based I/O of OpenStreetMap data.*

[![PyPI Release Version](https://img.shields.io/pypi/v/pydriosm)](https://pypi.org/project/pydriosm/) 
[![Python Version](https://img.shields.io/pypi/pyversions/pydriosm)](https://docs.python.org/3/)
[![License](https://img.shields.io/github/license/mikeqfu/pydriosm)](https://github.com/mikeqfu/pydriosm/blob/master/LICENSE) 
[![ReadTheDocs Documentation](https://img.shields.io/readthedocs/pydriosm?logo=readthedocs)](https://pydriosm.readthedocs.io/en/latest/?badge=latest)
[![GitHub Actions Workflow Status](https://img.shields.io/github/actions/workflow/status/mikeqfu/pydriosm/github-pages.yml?logo=github&branch=master)](https://github.com/mikeqfu/pydriosm/actions)
[![Codacy - Code Quality](https://app.codacy.com/project/badge/Grade/b411ce89cbc445f58377a5799646d4cb)](https://app.codacy.com/gh/mikeqfu/pydriosm/dashboard?utm_source=gh&utm_medium=referral&utm_content=&utm_campaign=Badge_grade) 
[![DOI](https://img.shields.io/badge/10.5281%2Fzenodo.4281194-blue?label=doi)](https://doi.org/10.5281/zenodo.4281194)

**PyDriosm** is an open-source Python package designed to simplify the acquisition and management of [OpenStreetMap](https://www.openstreetmap.org/) (OSM) data. It provides automated utilities for downloading and parsing data extracts from [Geofabrik](https://download.geofabrik.de/) and [BBBike](https://extract.bbbike.org/) in several popular formats, including [Protocolbuffer Binary Format](https://wiki.openstreetmap.org/wiki/PBF_Format) (PBF), [Shapefiles](https://wiki.openstreetmap.org/wiki/Shapefiles) and [GeoPackage](https://www.geopackage.org/) (GPKG).

Beyond data retrieval, the package integrates a robust I/O interface for [PostgreSQL](https://www.postgresql.org/) databases. This allows users to import parsed OSM data directly into a relational database, facilitating complex spatial querying and efficient data manipulation. By handling the complexities of source scraping, file parsing and schema mapping, **pydriosm** provides a streamlined workflow for researchers and developers working with large-scale geographic datasets.

### Core features:

* **Automated downloads**: Direct access to Geofabrik and BBBike subregion extracts.
* **Format support**: Parse regional data of PBF, Shapefiles and GeoPackage files into standard Pandas DataFrames or GeoDataFrames.
* **PostgreSQL integration**: Streamlined geometry I/O for efficient database storage.
* **Multi-region processing**: Tools for merging regional data layers into unified datasets.

## Installation

To install the latest release of **pydriosm** from [PyPI](https://pypi.org/project/pydriosm/) via [pip](https://pip.pypa.io/en/stable/cli/pip/):

```bash
$ pip install --upgrade pydriosm
```

For more information, see the [Installation](https://pydriosm.readthedocs.io/en/latest/installation.html). 

## Quick start

For a concise guide with practical examples, please check out the [Quick Start](https://pydriosm.readthedocs.io/en/latest/quick-start.html) tutorial, which demonstrates how to use **pydriosm** to download, parse and perform storage I/O operations on OSM data using a PostgreSQL database.

## Documentation

The complete PyHelpers Documentation is available in [[HTML](https://pydriosm.readthedocs.io/en/latest/)\] \[[PDF](https://pydriosm.readthedocs.io/_/downloads/en/latest/pdf/)] formats. 

It is hosted on [ReadTheDocs](https://readthedocs.org/projects/pydriosm/) and provides detailed examples, tutorials and comprehensive references to help users get the most out of **pydriosm**. 

## Cite as

Fu, Q. (2020). PyDriosm: An open-source tool for downloading, reading and PostgreSQL-based I/O of OpenStreetMap data. Zenodo. [doi:10.5281/zenodo.4281194](https://doi.org/10.5281/zenodo.4281194)

```bibtex
@software{qian_fu_pydriosm_4281194,
  author    = {Fu, Qian},
  title     = {{PyDriosm: An open-source tool for downloading, reading and PostgreSQL-based I/O of OpenStreetMap data}},
  year      = {2020},
  publisher = {Zenodo},
  doi       = {10.5281/zenodo.4281194},
  license   = {GPLv3},
  url       = {https://github.com/mikeqfu/pydriosm}
}
```

(Please also refer to the export options from [Zenodo](https://zenodo.org/search?q=parent.id%3A4281194&f=allversions%3Atrue&l=list&p=1&s=10&sort=version) to reference the specific version of **pydriosm** as appropriate.)

## License

-   **PyDriosm** is licensed under [GNU General Public License v3.0](https://github.com/mikeqfu/pydriosm/blob/master/LICENSE) or later (GPLv3+). 
-   The free [OpenStreetMap](https://www.openstreetmap.org/) data, which is used for the development of **PyDriosm**, is licensed under the [Open Data Commons Open Database License](https://opendatacommons.org/licenses/odbl/) (ODbL) by the [OpenStreetMap Foundation](https://osmfoundation.org/) (OSMF).

## Acknowledgement

The development of **pydriosm**, including the example code that demonstrates how to use the package, heavily relies on freely available [OpenStreetMap](https://www.openstreetmap.org/) data. The author would like to express sincere gratitude to all the [OpenStreetMap contributors](https://wiki.openstreetmap.org/wiki/Contributors) for their invaluable contributions in making this data accessible to the community.
