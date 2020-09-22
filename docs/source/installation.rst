============
Installation
============

If you are using a `virtualenv <https://packaging.python.org/key_projects/#virtualenv>`_, ensure that the virtualenv is activated.

To install the latest release of `pydriosm <https://github.com/mikeqfu/pydriosm>`_ at `PyPI <https://pypi.org/project/pydriosm/>`_ via `pip <https://packaging.python.org/key_projects/#pip>`_ on Windows Command Prompt (CMD) or Linux/Unix terminal, try:

.. code-block:: bash

   pip install --upgrade pydriosm

To install the more recent version under development, try:

.. code-block:: bash

   pip install --upgrade git+https://github.com/mikeqfu/pydriosm.git

To test if *pydriosm* is correctly installed, try importing the package from an interpreter shell:

.. parsed-literal::

    >>> import pydriosm
    >>> pydriosm.__version__  # Check the current release
    |version|

.. note::

    - To ensure you get the most recent version, it is always recommended to add ``--upgrade`` (or ``-U``) to ``pip install``.

    - The package has not yet been tested with Python 2. For users who have installed both Python 2 and 3, it would be recommended to replace ``pip`` with ``pip3``. But you are more than welcome to volunteer testing the package with Python 2 and any issues should be logged/reported onto the `Issues <https://github.com/mikeqfu/pydriosm/issues>`_ page.

    - Failure to ``pip install pydriosm``

        - For *Windows* users:
            The ``pip`` method might fail to install some dependencies, such as `Fiona <https://pypi.org/project/Fiona/>`_, `GDAL <https://pypi.org/project/GDAL/>`_, `Shapely <https://pypi.org/project/Shapely/>`_ and `python-Levenshtein <https://pypi.org/project/python-Levenshtein/>`_. If errors occur when ``pip`` installing these packages, try instead to ``pip install`` their respective *.whl* files, which can be downloaded from the `Unofficial Windows Binaries for Python Extension Packages <https://www.lfd.uci.edu/~gohlke/pythonlibs/>`_. After they are installed successfully, try again to install pydriosm.

        - For *Linux/Unix* users:
            To try out any earlier version (<2.0.0) on *Linux*, check `this page <https://github.com/mikeqfu/pydriosm/issues/1#issuecomment-540684439>`_ for installation instructions. However, it's always recommended to use the latest version.

    - For more general instructions, check the `Installing Packages <https://packaging.python.org/tutorials/installing-packages>`_ page.
