============
Installation
============

To install the latest release of PyDriosm from `PyPI`_ via `pip`_:

.. _`PyPI`: https://pypi.org/project/pydriosm/
.. _`pip`: https://pip.pypa.io/en/stable/cli/pip/

.. code-block:: console

    pip install --upgrade pydriosm


To install the most recent version of PyDriosm hosted on `GitHub`_:

.. _`GitHub`: https://github.com/mikeqfu/pydriosm

.. code-block:: console

    pip install --upgrade git+https://github.com/mikeqfu/pydriosm.git


.. warning::

    - `Pip`_ may fail to install the dependency package `GDAL`_. In such a circumstance, try instead to `install their .whl files`_, which can be downloaded from the web page of the `archived "unofficial Windows binaries for Python extension packages"`_ (by Christoph Gohlke) or a `mirror site`_ (by Erin Turnbull). For how to install a .whl file, see the answers to this `StackOverflow question`_.

    .. _`GDAL`: https://pypi.org/project/GDAL/
    .. _`archived "unofficial Windows binaries for Python extension packages"`: https://www.lfd.uci.edu/~gohlke/pythonlibs/
    .. _`mirror site`: http://eturnbull.ca/pythonlibs/
    .. _`StackOverflow question`: https://stackoverflow.com/questions/27885397


.. note::

    - If using a `virtual environment`_, make sure it is activated.
    - It is recommended to add `pip install`_ the option ``--upgrade`` (or ``-U``) to ensure that you are getting the latest stable release of the package.
    - Non-essential dependencies (e.g. `GeoPandas`_) of PyDriosm are not enforced to be installed along with the installation of the package. This is intended to optimise the installation requirements. If a `ModuleNotFoundError`_ or an `ImportError`_ pops out when importing/running a function or a method, first try to install the module(s)/package(s) mentioned in the error message, and then try to import/run the function or method again.
    - For more general instructions on the installation of Python packages, please refer to the official guide of `Installing Packages`_.

    .. _`virtual environment`: https://packaging.python.org/glossary/#term-Virtual-Environment
    .. _`pip install`: https://pip.pypa.io/en/stable/cli/pip_install/
    .. _`ModuleNotFoundError`: https://docs.python.org/3/library/exceptions.html#ModuleNotFoundError
    .. _`ImportError`: https://docs.python.org/3/library/exceptions.html#ImportError
    .. _`GeoPandas`: https://geopandas.org/en/stable/getting_started/install.html#installing-with-pip
    .. _`install their .whl files`: https://stackoverflow.com/a/27909082/4981844
    .. _`Installing Packages`: https://packaging.python.org/tutorials/installing-packages/


To check whether PyDriosm has been correctly installed, try to import the package via an interpreter shell:

.. code-block:: python
    :name: cmd current version

    >>> import pydriosm

    >>> pydriosm.__version__  # Check the latest version

.. parsed-literal::
    The latest version is: |version|