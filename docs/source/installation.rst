============
Installation
============

To install the latest release of PyDriosm at `PyPI`_ via `pip`_:

.. code-block:: bash

    pip install --upgrade pydriosm

To install the more recent version hosted directly from `GitHub repository`_:

.. code-block:: bash

    pip install --upgrade git+https://github.com/mikeqfu/pydriosm.git


.. note::

    Possibilities of ``pip install`` being unsuccessful or causing errors:

    - For *Windows* users:
        The ``pip`` method might fail to install some dependencies, such as `GDAL`_, `Fiona`_ and `Shapely`_. If errors occur when directly installing any of those dependencies, ``pip install`` instead their respective *.whl* files, which can be downloaded from `Unofficial Windows Binaries for Python Extension Packages`_. After the *.whl* files are installed successfully, try ``pip install pydriosm`` again.

    - For *Linux/Unix* users:
        To try out any earlier version (<2.0.0) that is not compatible with 2.0.0+, check `this page <https://github.com/mikeqfu/pydriosm/issues/1#issuecomment-540684439>`_ for instructions if errors occur during installation.


To test if PyDriosm is correctly installed, try to import the package via an interpreter shell:

.. code-block:: python

    >>> import pydriosm

    >>> pydriosm.__version__

.. parsed-literal::
    The current release version is: |version|


.. note::

    - If using a `virtual environment`_, ensure that it is activated.

    - To ensure you get the most recent version, it is always recommended to add ``--upgrade`` (or ``-U``) to ``pip install``.

    - The package has not yet been tested with `Python 2`_. For users who have installed both `Python 2`_ and `Python 3`_, it would be recommended to replace ``pip`` with ``pip3``. But you are more than welcome to volunteer testing the package with `Python 2`_ and any issues should be logged/reported onto the `Issues`_ page.

    - For more general instructions, check the `Installing Packages`_ page.

.. _`PyPI`: https://pypi.org/project/pydriosm/
.. _`pip`: https://packaging.python.org/key_projects/#pip
.. _`GitHub repository`: https://github.com/mikeqfu/pydriosm

.. _`virtual environment`: https://packaging.python.org/glossary/#term-Virtual-Environment
.. _`virtualenv`: https://packaging.python.org/key_projects/#virtualenv
.. _`Python 2`: https://docs.python.org/2/
.. _`Python 3`: https://docs.python.org/3/
.. _`Issues`: https://github.com/mikeqfu/pydriosm/issues

.. _`GDAL`: https://pypi.org/project/GDAL/
.. _`Fiona`: https://pypi.org/project/Fiona/
.. _`Shapely`: https://pypi.org/project/Shapely/
.. _`python-Levenshtein`: https://pypi.org/project/python-Levenshtein/
.. _`Unofficial Windows Binaries for Python Extension Packages`: https://www.lfd.uci.edu/~gohlke/pythonlibs/
.. _`Installing Packages`: https://packaging.python.org/tutorials/installing-packages
