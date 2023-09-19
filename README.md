# PyDriosm

[![PyPI](https://img.shields.io/pypi/v/pydriosm)](https://pypi.org/project/pydriosm/) 
[![Python Version](https://img.shields.io/pypi/pyversions/pydriosm)](https://docs.python.org/3/) 
[![Documentation Status](https://readthedocs.org/projects/pydriosm/badge/?version=latest)](https://pydriosm.readthedocs.io/en/latest/?badge=latest) 
[![License](https://img.shields.io/pypi/l/pydriosm)](https://github.com/mikeqfu/pydriosm/blob/master/LICENSE) 
[![Codacy Badge](https://app.codacy.com/project/badge/Grade/b411ce89cbc445f58377a5799646d4cb)](https://app.codacy.com/gh/mikeqfu/pydriosm/dashboard?utm_source=gh&utm_medium=referral&utm_content=&utm_campaign=Badge_grade) 
[![DOI](https://zenodo.org/badge/92493726.svg)](https://zenodo.org/badge/latestdoi/92493726)

PyDriosm is an open-source tool that provides an effortless way to download and access [OpenStreetMap](https://www.openstreetmap.org/) (OSM) data in popular file formats, such as [shapefile](https://wiki.openstreetmap.org/wiki/Shapefiles) and [protobuf binary format](https://wiki.openstreetmap.org/wiki/PBF_Format) (PBF), which are freely available from [Geofabrik](https://download.geofabrik.de/) and [BBBike](https://download.bbbike.org/). Additionally, the package offers a comprehensive solution for convenient I/O operations and efficient storage capabilities for parsed OSM data within [PostgreSQL](https://www.postgresql.org/) databases. This means that users can easily read from and write to PostgreSQL databases, enabling efficient data manipulation, querying, and other essential tasks. Whether you are a researcher, practitioner, or simply interested in working with OSM data, PyDriosm can be useful and helpful to streamline your workflow and enhance your experience. 

## Installation

To install the latest release of PyDriosm from [PyPI](https://pypi.org/project/pydriosm/) via [pip](https://pip.pypa.io/en/stable/cli/pip/):

```bash
pip install --upgrade pydriosm
```

Please also refer to [Installation](https://pydriosm.readthedocs.io/en/latest/installation.html) for more information. 

## Quick start

For a concise guide with practical examples, please check out the [quick-start tutorial](https://pydriosm.readthedocs.io/en/latest/quick-start.html). This tutorial showcases how to utilise PyDriosm for various tasks, such as downloading, parsing, and performing storage I/O operations on OSM data using a PostgreSQL database.

## Documentation

The complete PyDriosm documentation: [[HTML](https://pydriosm.readthedocs.io/en/latest/)\] \[[PDF](https://pydriosm.readthedocs.io/_/downloads/en/latest/pdf/)] 

It is hosted on [ReadTheDocs](https://readthedocs.org/projects/pydriosm/) and provides a wealth of detailed examples. 

## License

-   PyDriosm is licensed under [GNU General Public License v3.0](https://github.com/mikeqfu/pydriosm/blob/master/LICENSE) or later (GPLv3+). 
-   The free [OpenStreetMap](https://www.openstreetmap.org/) data, which is used for the development of PyDriosm, is licensed under the [Open Data Commons Open Database License](https://opendatacommons.org/licenses/odbl/) (ODbL) by the [OpenStreetMap Foundation](https://osmfoundation.org/) (OSMF).

## Acknowledgement

The development of PyDriosm, including the example code that demonstrates how to use the package, heavily relies on freely available [OpenStreetMap](https://www.openstreetmap.org/) data. The author would like to express sincere gratitude to all the [OpenStreetMap contributors](https://wiki.openstreetmap.org/wiki/Contributors) for their invaluable contributions in making this data accessible to the community.

## Cite as

Fu, Q. (2020). PyDriosm: an open-source tool for downloading, reading and PostgreSQL-based I/O of OpenStreetMap data. Zenodo. [doi:10.5281/zenodo.4281194](https://doi.org/10.5281/zenodo.4281194)

```bibtex
@software{qian_fu_pydriosm_4281194,
  author    = {Qian Fu},
  title     = {{PyDriosm: an open-source tool for downloading, reading
                and PostgreSQL-based I/O of OpenStreetMap data}},
  year      = 2020,
  publisher = {Zenodo},
  doi       = {10.5281/zenodo.4718623},
  url       = {https://doi.org/10.5281/zenodo.4281194}
}
```

(Please also refer to the export options from [Zenodo](https://zenodo.org/search?page=1&size=20&q=conceptrecid:4281194&all_versions&sort=-version) to reference the specific version of PyDriosm as appropriate.)

## Contributors

<!--suppress HtmlDeprecatedAttribute -->
<table>
  <tbody>
    <tr>
      <td align="center">
        <a href="https://github.com/mikeqfu" target="_blank"><img src="https://avatars.githubusercontent.com/u/1729711?v=4?s=100" width="100px;" alt="Qian Fu"/><br><sub><b>Qian Fu</b></sub></a><br>
        <a href="https://github.com/mikeqfu/pydriosm" target="_blank" title="Seeding">&#127793;</a>
        <a href="https://github.com/mikeqfu/pydriosm/commits?author=mikeqfu" target="_blank" title="Code">&#128187;</a>
        <a href="https://github.com/mikeqfu/pydriosm/tree/master/tests" target="_blank" title="Tests">&#129514;</a>
        <a href="https://pydriosm.readthedocs.io/en/latest/" target="_blank" title="Documentation">&#128214;</a>
      </td>
  </tbody>
</table>