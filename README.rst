########
PyDriosm
########

|PyPI| |Python| |Documentation| |License| |DOI|

.. |PyPI| image:: https://img.shields.io/pypi/v/pydriosm
    :alt: PyPI - Release
    :target: https://pypi.org/project/pydriosm/
.. |Python| image:: https://img.shields.io/pypi/pyversions/pydriosm
    :alt: PyPI - Python version
    :target: https://docs.python.org/3/
.. |Documentation| image:: https://readthedocs.org/projects/pydriosm/badge/?version=latest
    :alt: ReadTheDocs - Documentation status
    :target: https://pydriosm.readthedocs.io/en/latest/?badge=latest
.. |License| image:: https://img.shields.io/pypi/l/pydriosm
    :alt: PyPI - License
    :target: https://github.com/mikeqfu/pydriosm/blob/master/LICENSE
.. |DOI| image:: https://zenodo.org/badge/92493726.svg
    :alt: Zenodo - DOI
    :target: https://zenodo.org/badge/latestdoi/92493726

PyDriosm is an open-source tool for researchers/practitioners to easily download and read `OpenStreetMap <https://www.openstreetmap.org/>`_ (OSM) data in popular file formats such as `protobuf binary format <https://wiki.openstreetmap.org/wiki/PBF_Format>`_ (PBF) and `shapefile <https://wiki.openstreetmap.org/wiki/Shapefiles>`_, which are available for free download from `Geofabrik <https://download.geofabrik.de/>`_ and `BBBike <https://www.bbbike.org/>`_. The package also provides a convenient way for `PostgreSQL <https://www.postgresql.org/>`_-based I/O and storage of parsed OSM data.

Installation
############

To install the latest release of pydriosm from `PyPI <https://pypi.org/project/pydriosm/>`_ via `pip <https://pip.pypa.io/en/stable/cli/pip/>`_:

.. code-block:: bash

    pip install --upgrade pydriosm

For more information, please refer to `Installation <https://pydriosm.readthedocs.io/en/latest/installation.html>`_.

Documentation
#############

The full PyDriosm documentation (including detailed examples and a quick-start tutorial) is hosted on `ReadTheDocs <https://readthedocs.org/projects/pydriosm/>`_: [`HTML <https://pydriosm.readthedocs.io/en/latest/>`_] [`PDF <https://pydriosm.readthedocs.io/_/downloads/en/latest/pdf/>`_].

License
#######

- PyDriosm is licensed under `GNU General Public License v3 <https://github.com/mikeqfu/pydriosm/blob/master/LICENSE>`_ or later (GPLv3+).
- The free `OpenStreetMap <https://www.openstreetmap.org/>`_ data, which is used for the development of PyDriosm, is licensed under the `Open Data Commons Open Database License <https://opendatacommons.org/licenses/odbl/>`_ (ODbL) by the `OpenStreetMap Foundation <https://osmfoundation.org/>`_ (OSMF).

Cite as
#######

Fu, Q. (2020). PyDriosm: an open-source tool for downloading, reading and PostgreSQL-based I/O of OpenStreetMap data. `doi:10.5281/zenodo.4281194 <https://doi.org/10.5281/zenodo.4281194>`_

.. code-block:: bibtex

    @software{qian_fu_pydriosm_4281194,
      author    = {Qian Fu},
      title     = {{PyDriosm: an open-source tool for downloading, reading
                    and PostgreSQL-based I/O of OpenStreetMap data}},
      year      = 2020,
      publisher = {Zenodo},
      doi       = {10.5281/zenodo.4718623},
      url       = {https://doi.org/10.5281/zenodo.4281194}
    }

**Note:** Please also refer to the export options from `Zenodo <https://zenodo.org/search?page=1&size=20&q=conceptrecid:4281194&all_versions&sort=-version>`_ to reference the specific version as appropriate for the use of PyDriosm.
