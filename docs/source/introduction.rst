:orphan:

==============
About PyDriosm
==============

**PyDriosm** is an open-source Python package designed to simplify the acquisition and management of `OpenStreetMap <https://www.openstreetmap.org/>`_ (OSM) data. It provides automated utilities for downloading and parsing data extracts from `Geofabrik <https://download.geofabrik.de/>`_ and `BBBike <https://download.bbbike.org/>`_ in several popular formats, including `Protocolbuffer Binary Format <https://wiki.openstreetmap.org/wiki/PBF_Format>`_ (PBF), `Shapefiles <https://wiki.openstreetmap.org/wiki/Shapefiles>`_ and `GeoPackage <https://www.geopackage.org/>`_ (GPKG).

Beyond data retrieval, the package integrates a robust I/O interface for `PostgreSQL <https://www.postgresql.org/>`_ databases. This allows users to import parsed OSM data directly into a relational database, facilitating complex spatial querying and efficient data manipulation. By handling the complexities of source scraping, file parsing and schema mapping, **pydriosm** provides a streamlined workflow for researchers and developers working with large-scale geographic datasets.

**Core features:**

- **Automated downloads**: Direct access to Geofabrik and BBBike subregion extracts.
- **Format support**: Parse regional data of PBF, Shapefiles and GeoPackage files into standard Pandas DataFrames or GeoDataFrames.
- **PostgreSQL integration**: Streamlined geometry I/O for efficient database storage.
- **Multi-region processing**: Tools for merging regional data layers into unified datasets.
