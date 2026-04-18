########
PyDriosm
########

*A Python package for downloading, reading and PostgreSQL-based I/O of OpenStreetMap data.*

|PyPI| |Python| |License| |Docs| |Build| |Codacy| |DOI|

.. |PyPI| image:: https://img.shields.io/pypi/v/pydriosm
    :alt: PyPI Release Version
    :target: https://pypi.org/project/pydriosm/
.. |Python| image:: https://img.shields.io/pypi/pyversions/pydriosm
    :alt: Python Version
    :target: https://docs.python.org/3/
.. |License| image:: https://img.shields.io/github/license/mikeqfu/pydriosm
    :alt: PyPI - License
    :target: https://github.com/mikeqfu/pydriosm/blob/master/LICENSE
.. |Docs| image:: https://img.shields.io/readthedocs/pydriosm?logo=readthedocs
    :alt: ReadTheDocs - Documentation status
    :target: https://pydriosm.readthedocs.io/en/latest/?badge=latest
.. |Build| image:: https://img.shields.io/github/actions/workflow/status/mikeqfu/pydriosm/github-pages.yml?logo=github&branch=master
    :alt: GitHub Actions Workflow Status
    :target: https://github.com/mikeqfu/pydriosm/actions
.. |Codacy| image:: https://app.codacy.com/project/badge/Grade/b411ce89cbc445f58377a5799646d4cb
    :alt: Codacy - Code Quality
    :target: https://www.codacy.com/gh/mikeqfu/pydriosm/dashboard?utm_source=github.com&amp;utm_medium=referral&amp;utm_content=mikeqfu/pydriosm&amp;utm_campaign=Badge_Grade
.. |DOI| image:: https://img.shields.io/badge/10.5281%2Fzenodo.4281194-blue?label=doi
    :alt: DOI
    :target: https://doi.org/10.5281/zenodo.4281194

| **Author**: Qian Fu
| **Email**: q.fu@bham.ac.uk

**PyDriosm** is an open-source Python package designed to simplify the acquisition and management of `OpenStreetMap <https://www.openstreetmap.org/>`_ (OSM) data. It provides automated utilities for downloading and parsing data extracts from `Geofabrik <https://download.geofabrik.de/>`_ and `BBBike <https://download.bbbike.org/>`_ in several popular formats, including `Protocolbuffer Binary Format <https://wiki.openstreetmap.org/wiki/PBF_Format>`_ (PBF), `Shapefiles <https://wiki.openstreetmap.org/wiki/Shapefiles>`_ and `GeoPackage <https://www.geopackage.org/>`_ (GPKG).

Beyond data retrieval, the package integrates a robust I/O interface for `PostgreSQL <https://www.postgresql.org/>`_ databases. This allows users to import parsed OSM data directly into a relational database, facilitating complex spatial querying and efficient data manipulation. By handling the complexities of source scraping, file parsing and schema mapping, **pydriosm** provides a streamlined workflow for researchers and developers working with large-scale geographic datasets.

    **Core features:**

    - **Automated downloads**: Direct access to Geofabrik and BBBike subregion extracts.
    - **Format support**: Parse regional data of PBF, Shapefiles and GeoPackage files into standard Pandas DataFrames or GeoDataFrames.
    - **PostgreSQL integration**: Streamlined geometry I/O for efficient database storage.
    - **Multi-region processing**: Tools for merging regional data layers into unified datasets.


.. toctree::
    :maxdepth: 1
    :includehidden:
    :caption: Getting Started

    installation
    quick-start

.. toctree::
    :maxdepth: 1
    :includehidden:
    :caption: Usage & Reference

    subpackages
    modules

.. toctree::
    :maxdepth: 2
    :includehidden:
    :caption: Additional Info

    license
    acknowledgement
    contributors


Indices
#######

* :ref:`genindex`
* :ref:`modindex`
* :ref:`search`
