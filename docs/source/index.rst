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

PyDriosm is an open-source tool that provides an effortless way to download and access `OpenStreetMap <https://www.openstreetmap.org/>`_ (OSM) data in popular file formats, such as `shapefile <https://wiki.openstreetmap.org/wiki/Shapefiles>`_ and `protobuf binary format <https://wiki.openstreetmap.org/wiki/PBF_Format>`_ (PBF), which are freely available from `Geofabrik <https://download.geofabrik.de/>`_ and `BBBike <https://download.bbbike.org/>`_. Additionally, the package offers a comprehensive solution for convenient I/O operations and efficient storage capabilities for parsed OSM data within `PostgreSQL <https://www.postgresql.org/>`_ databases. This means that users can easily read from and write to PostgreSQL databases, enabling efficient data manipulation, querying, and other essential tasks. Whether you are a researcher, practitioner, or simply interested in working with OSM data, PyDriosm can be useful and helpful to streamline your workflow and enhance your experience.


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
