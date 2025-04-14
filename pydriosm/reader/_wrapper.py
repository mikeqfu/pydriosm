from pydriosm.errors import MethodNotAvailableError
from pydriosm.reader._base import BaseReader
from pydriosm.reader._bbbike import BBBikeReader
from pydriosm.reader._geofabrik import GeofabrikReader


class Reader(BaseReader):
    SOURCES: dict = {
        "geofabrik": GeofabrikReader,
        "bbbike": BBBikeReader,
    }

    def __init__(self, data_source='geofabrik', data_dir=None, max_tmpfile_size=None, **kwargs):
        # noinspection PyShadowingNames
        """

        :param data_source:
        :type data_source: str

        :ivar reader:
        :vartype reader: BaseReader | GeofabrikReader | BBBikeReader | None
        :ivar data_source:
        :vartype data_source: str

        **Examples**::

            >>> from pydriosm.reader import Reader
            >>> import os
            >>> reader = Reader()
            >>> subregion_name = 'rutland'
            >>> osm_file_format = ".shp"
            >>> data_dir = "tests/osm_data"
            >>> path_to_file = reader.get_file_path(subregion_name, osm_file_format, data_dir)
            >>> os.path.relpath(path_to_file)  # (on Windows)
            'tests\\osm_data\\rutland\\rutland-latest-free.shp.zip'

            >>> reader.set_source('bbbike')
            >>> path_to_file = reader.get_file_path(subregion_name, osm_file_format, data_dir)
            Traceback (most recent call last):
                ...
            pydriosm.errors.InvalidSubregionNameError:
              `subregion_name='rutland'` -> The input of `subregion_name` is not recognizable.
              Check the `.data_source`, or try another one instead.
            >>> subregion_name = 'Birmingham'
            >>> path_to_file = reader.get_file_path(subregion_name, osm_file_format, data_dir)
            >>> os.path.relpath(path_to_file)  # (on Windows)
            'tests\\osm_data\\birmingham\\Birmingham.osm.shp.zip'
        """

        # Ensure base class initialization
        super().__init__(
            data_source=data_source, data_dir=data_dir, max_tmpfile_size=max_tmpfile_size, **kwargs)

        # Predefine attributes to avoid linter warnings
        self.reader = None
        self.data_source = data_source

        self.set_source(
            data_source=data_source, data_dir=data_dir, max_tmpfile_size=max_tmpfile_size, **kwargs)

    def set_source(self, data_source, data_dir=None, max_tmpfile_size=None, **kwargs):
        """

        :param data_source:
        :param data_dir:
        :param max_tmpfile_size:
        :param kwargs:
        :return:

        **Examples**::

            >>> from pydriosm.reader import Reader
            >>> reader = Reader()
        """

        try:
            if self.reader is not None:
                var_dict = self.reader.__class__.__annotations__ | self.reader.__dict__
                for var_name in var_dict:
                    delattr(self, var_name)

            self.data_source = data_source.lower()

            self.reader = self.SOURCES[self.data_source](
                data_dir=data_dir, max_tmpfile_size=max_tmpfile_size, **kwargs)

            for var_name in self.reader.__class__.__annotations__ | self.reader.__dict__:
                setattr(self, var_name, self.reader.__getattribute__(var_name))

        except KeyError:
            raise ValueError(f'Unsupported source: "{data_source}".')

    def _raise_unavailable_method_error(self, method_name, raise_error=True):
        if raise_error:
            raise MethodNotAvailableError(method_name, self.reader)

    def get_file_path(self, subregion_name, osm_file_format, data_dir=None, raise_error=True):
        # noinspection PyShadowingNames
        """
        Get the local path to an OSM data file of a geographic (sub)region.

        :param subregion_name: name of a geographic (sub)region (case-insensitive)
            that is available on Geofabrik free download server
        :type subregion_name: str
        :param osm_file_format: file format of the OSM data available on the free download server
        :type osm_file_format: str
        :param data_dir: directory where the data file of the ``subregion_name`` is located/saved;
            if ``None`` (default), the default local directory
        :type data_dir: str | None
        :param raise_error: Whether to raise the provided exception;
            if ``raise_error=True`` (default), the error will be suppressed.
        :type raise_error: bool
        :return: path to PBF (.osm.pbf) file
        :rtype: str | None

        **Examples**::

            >>> from pydriosm.reader import Reader
            >>> from pyhelpers.dirs import delete_dir
            >>> import os
            >>> osm_reader = Reader()
            >>> subregion_name = 'rutland'
            >>> osm_file_format = ".pbf"
            >>> data_dir = "tests/osm_data"
            >>> path_to_file = osm_reader.get_file_path(subregion_name, osm_file_format, data_dir)
            >>> # When "rutland-latest.osm.pbf" is unavailable at the package data directory
            >>> os.path.isfile(path_to_file)
            False
            >>> # Download the PBF data file of Rutland to "./tests/osm_data/"
            >>> osm_reader.downloader.download_data(
            ...     subregion_name, osm_file_format, data_dir, verbose=True)
            To download data in the format '.osm.pbf' for the following geographic (sub)region(s):
                "Rutland"
              to "./tests/osm_data/rutland/"
            ? [No]|Yes: yes
            Downloading "rutland-latest.osm.pbf" 100%|██████████| 1.83M/1.83M | 5.63MB/s ...
                Saving "rutland-latest.osm.pbf" to "./tests/osm_data/rutland/" ... Done.
            >>> # Check again
            >>> path_to_file = osm_reader.get_file_path(subregion_name, osm_file_format, data_dir)
            >>> os.path.isfile(path_to_file)
            True
            >>> os.path.relpath(path_to_file)  # (on Windows)
            'tests\\osm_data\\rutland\\rutland-latest.osm.pbf'
            >>> # Delete the test data directory
            >>> delete_dir(data_dir, verbose=True)
            To delete the directory "./tests/osm_data/" (Not empty)
            ? [No]|Yes: yes
            Deleting "./tests/osm_data/" ... Done.
        """

        method_name = self.get_file_path.__name__

        if hasattr(self.reader, method_name):
            return self.reader.get_file_path(
                subregion_name=subregion_name,
                osm_file_format=osm_file_format,
                data_dir=data_dir
            )

        else:
            self._raise_unavailable_method_error(method_name=method_name, raise_error=raise_error)

    def get_pbf_layer_names(self, subregion_name, data_dir=None, raise_error=True):
        """
        Get indices and names of all layers in the PBF data file of a given (sub)region.

        :param subregion_name: name of a geographic (sub)region (case-insensitive)
            that is available on Geofabrik free download server
        :type subregion_name: str
        :param data_dir:
        :type data_dir:
        :param raise_error: Whether to raise the provided exception;
            if ``raise_error=True`` (default), the error will be suppressed.
        :type raise_error: bool
        :return: indices and names of each layer of the PBF data file
        :rtype: dict

        **Examples**::

            >>> from pydriosm.reader import GeofabrikReader
            >>> from pyhelpers.dirs import delete_dir
            >>> import os

            >>> gfr = GeofabrikReader()

            >>> # Download the .shp.zip file of Rutland as an example
            >>> subrgn_name = 'london'
            >>> file_format = ".pbf"
            >>> dat_dir = "tests\\osm_data"

            >>> gfr.downloader.download_osm_data(subrgn_name, file_format, dat_dir, verbose=True)
            To download .osm.pbf data of the following geographic (sub)region(s):
                Greater London
            ? [No]|Yes: yes
            Downloading "greater-london-latest.osm.pbf"
                to "tests\\osm_data\\greater-london\\" ... Done.

            >>> london_pbf_path = gfr.data_paths[0]
            >>> os.path.relpath(london_pbf_path)
            'tests\\osm_data\\greater-london\\greater-london-latest.osm.pbf'

            >>> lyr_idx_names = gfr.get_pbf_layer_names(london_pbf_path)
            >>> lyr_idx_names
            {0: 'points',
             1: 'lines',
             2: 'multilinestrings',
             3: 'multipolygons',
             4: 'other_relations'}

            >>> # Delete the example data and the test data directory
            >>> delete_dir(dat_dir, verbose=True)
            To delete the directory "tests\\osm_data\\" (Not empty)
            ? [No]|Yes: yes
            Deleting "tests\\osm_data\\" ... Done.
        """

        method_name = self.get_pbf_layer_names.__name__

        if hasattr(self.reader, method_name):
            return self.reader.get_pbf_layer_names(subregion_name=subregion_name, data_dir=data_dir)

        else:
            self._raise_unavailable_method_error(method_name=method_name, raise_error=raise_error)

    def get_shp_pathname(self, subregion_name, layer_name=None, feature_name=None, data_dir=None,
                         raise_error=True):
        method_name = self.get_shp_pathname.__name__

        if hasattr(self.reader, method_name):
            return self.reader.get_shp_pathname(
                subregion_name=subregion_name,
                layer_name=layer_name,
                feature_name=feature_name,
                data_dir=data_dir,
            )

        else:
            self._raise_unavailable_method_error(method_name=method_name, raise_error=raise_error)

    def read_pbf(self, subregion_name, data_dir=None, readable=False, expand=False,
                 parse_geometry=False, parse_properties=False, parse_other_tags=False,
                 update=False, download=True, pickle_it=False, ret_pickle_path=False,
                 rm_pbf_file=False, chunk_size_limit=50, verbose=False, raise_error=True,
                 **kwargs):

        method_name = self.read_pbf.__name__

        if hasattr(self.reader, method_name):
            return self.reader.read_pbf(
                subregion_name=subregion_name,
                data_dir=data_dir,
                readable=readable,
                expand=expand,
                parse_geometry=parse_geometry,
                parse_properties=parse_properties,
                parse_other_tags=parse_other_tags,
                update=update,
                download=download,
                pickle_it=pickle_it,
                ret_pickle_path=ret_pickle_path,
                rm_pbf_file=rm_pbf_file,
                chunk_size_limit=chunk_size_limit,
                verbose=verbose,
                **kwargs
            )

        else:
            self._raise_unavailable_method_error(method_name=method_name, raise_error=raise_error)

    def read_shp(self, subregion_name, layer_names=None, feature_names=None, data_dir=None,
                 update=False, download=True, pickle_it=False, ret_pickle_path=False,
                 rm_extracts=False, rm_shp_zip=False, verbose=False, raise_error=True, **kwargs):

        method_name = self.read_shp.__name__

        if hasattr(self.reader, method_name):
            return self.reader.read_shp(
                subregion_name=subregion_name,
                layer_names=layer_names,
                feature_names=feature_names,
                data_dir=data_dir,
                update=update,
                download=download,
                pickle_it=pickle_it,
                ret_pickle_path=ret_pickle_path,
                rm_extracts=rm_extracts,
                rm_shp_zip=rm_shp_zip,
                verbose=verbose,
                **kwargs
            )

        else:
            self._raise_unavailable_method_error(method_name=method_name, raise_error=raise_error)

    def merge_shp_layers(self, subregion_names, layer_name, data_dir=None, engine='pyshp',
                         update=False, download=True, rm_zip_extracts=True,
                         merged_shp_dir=None, rm_shp_temp=True, verbose=False,
                         ret_merged_shp_path=False, raise_error=True):

        method_name = self.merge_shp_layers.__name__

        if hasattr(self.reader, method_name):
            return self.reader.read_csv_xz(
                subregion_names=subregion_names,
                layer_name=layer_name,
                data_dir=data_dir,
                engine=engine,
                update=update,
                download=download,
                rm_zip_extracts=rm_zip_extracts,
                merged_shp_dir=merged_shp_dir,
                rm_shp_temp=rm_shp_temp,
                verbose=verbose,
                ret_merged_shp_path=ret_merged_shp_path
            )

        else:
            self._raise_unavailable_method_error(method_name=method_name, raise_error=raise_error)

    def read_csv_xz(self, subregion_name, data_dir=None, download=False, verbose=False,
                    raise_error=True, **kwargs):

        method_name = self.read_csv_xz.__name__

        if hasattr(self.reader, method_name):
            return self.reader.read_csv_xz(
                subregion_name=subregion_name,
                data_dir=data_dir,
                download=download,
                verbose=verbose,
                **kwargs
            )

        else:
            self._raise_unavailable_method_error(method_name=method_name, raise_error=raise_error)

    def read_geojson_xz(self, subregion_name, data_dir=None, parse_geometry=False, download=False,
                        verbose=False, raise_error=True, **kwargs):

        method_name = self.read_geojson_xz.__name__

        if hasattr(self.reader, method_name):
            return self.reader.read_geojson_xz(
                subregion_name=subregion_name,
                data_dir=data_dir,
                parse_geometry=parse_geometry,
                download=download,
                verbose=verbose,
                **kwargs
            )

        else:
            self._raise_unavailable_method_error(method_name=method_name, raise_error=raise_error)
