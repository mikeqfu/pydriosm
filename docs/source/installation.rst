============
Installation
============

The easiest way to install the latest stable release of ``pydriosm`` is via `pip`_:

.. _`pip`: https://pip.pypa.io/en/stable/cli/pip/

.. code-block:: console

    pip install --upgrade pydriosm

To install the development version directly from `GitHub`_:

.. _`GitHub`: https://github.com/mikeqfu/pydriosm

.. code-block:: console

    pip install --upgrade git+https://github.com/mikeqfu/pydriosm.git@develop


Dependencies
============

``pydriosm`` requires Python 3.12+ and several core geospatial libraries.

.. note::

    **GDAL Installation**

    Parsing PBF data relies on `GDAL`_. While ``pip`` will attempt to install it, GDAL often requires specific system binaries.

    - **Windows users:** If ``pip install gdal`` fails, it is highly recommended to use pre-built binary wheels. You can find them at the `Geospatial library wheels for Python on Windows`_ repository.
    - **Conda users:** Alternatively, installing via ``conda install -c conda-forge gdal`` often resolves binary dependency issues automatically.

    .. _`GDAL`: https://pypi.org/project/GDAL/
    .. _`Geospatial library wheels for Python on Windows`: https://github.com/cgohlke/geospatial-wheels

.. note::

    - **Environment:** It is strongly recommended to install ``pydriosm`` within a `virtual environment`_.
    - **GeoPandas:** This package requires ``geopandas >= 1.1.0``. If you have an older version of GeoPandas installed, ``pip`` will attempt to upgrade it to ensure compatibility with modern GeoPackage (GPKG) parsing.
    - **Optimization:** To keep the installation lightweight, non-essential tools (e.g. `PyShp`_) are excluded from the base dependencies. If a feature requires an uninstalled library, a ``ModuleNotFoundError`` will guide you on what to install.

    .. _`virtual environment`: https://packaging.python.org/glossary/#term-Virtual-Environment
    .. _`PyShp`: https://pypi.org/project/pyshp/


Verification
============

To verify that ``pydriosm`` has been correctly installed, check the version in a Python interpreter:

.. code-block:: python
    :name: cmd current version

    >>> import pydriosm
    >>> pydriosm.__version__  # Check the latest version

.. parsed-literal::
    The latest version is: |version|


.. tip::

    For more general instructions on installing Python packages, refer to the official `Installing Packages <https://packaging.python.org/tutorials/installing-packages/>`_ guide.
