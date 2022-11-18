============
Installation
============

To install the latest release of pydriosm from `PyPI`_ via `pip`_:

.. _`PyPI`: https://pypi.org/project/pydriosm/
.. _`pip`: https://pip.pypa.io/en/stable/cli/pip/

.. code-block:: bash

    pip install --upgrade pydriosm

To install the most recent version of pydriosm hosted on `GitHub`_:

.. _`GitHub`: https://github.com/mikeqfu/pydriosm

.. code-block:: bash

    pip install --upgrade git+https://github.com/mikeqfu/pydriosm.git


.. note::

    If errors occur during the installation process:

    **For Windows users**:

    - If ``pip`` fails to install some non-essential dependencies, such as `GDAL <https://pypi.org/project/GDAL/>`_, try instead to ``pip install`` their corresponding wheel files (*.whl*), which can be downloaded from `Unofficial Windows Binaries for Python Extension Packages <https://www.lfd.uci.edu/~gohlke/pythonlibs/>`_. For information about how to do this, check out the best answer to this `StackOverflow question <https://stackoverflow.com/questions/27885397>`_.
    - After the *.whl* files of those dependencies are successfully installed, try running ``pip install pydriosm`` again.

    **For Linux/Unix users**:

    - To try out any earlier version (<2.0.0) that is not compatible with 2.0.0+, please refer to `this issue <https://github.com/mikeqfu/pydriosm/issues/1#>`_ for more information.


To check whether pydriosm has been correctly installed, try to import the package via an interpreter shell:

.. code-block:: python
    :name: cmd current version

    >>> import pydriosm

    >>> pydriosm.__version__  # Check the latest version

.. parsed-literal::
    The latest version is: |version|


.. note::

    - If using a `virtual environment`_, make sure it is activated.
    - It is recommended to add ``pip install`` the option ``--upgrade`` (or ``-U``) to ensure that you are getting the latest stable release of the package.
    - For more general instructions on the installation of Python packages, please refer to the official guide on `Installing Packages`_.

    .. _`virtual environment`: https://packaging.python.org/glossary/#term-Virtual-Environment
    .. _`pip install`: https://pip.pypa.io/en/stable/cli/pip_install/
    .. _`Installing Packages`: https://packaging.python.org/tutorials/installing-packages/
