reader
======

.. py:module:: pydriosm.reader

.. automodule:: pydriosm.reader
    :noindex:
    :no-members:
    :no-inherited-members:

.. rubric:: Classes
.. autosummary::
    :toctree: _generated/
    :template: class.rst

    GeofabrikReader
    BBBikeReader

.. rubric:: Parsers for .osm.pbf / .osm.bz2 file
.. autosummary::
    :toctree: _generated/
    :template: function.rst

    get_osm_pbf_layer_names
    parse_osm_pbf_layer
    parse_osm_pbf

.. rubric:: Parsers for .shp / .shp.zip file
.. autosummary::
    :toctree: _generated/
    :template: function.rst

    unzip_shp_zip
    read_shp_file
    get_epsg4326_wgs84_crs_ref
    get_epsg4326_wgs84_prj_ref
    make_pyshp_fields
    write_to_shapefile
    parse_layer_shp
    merge_shps
    merge_layer_shps

.. rubric:: Parsers for .xz file
.. autosummary::
    :toctree: _generated/
    :template: function.rst

    parse_csv_xz
    parse_geojson_xz
