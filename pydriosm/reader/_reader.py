"""
Base reader.
"""

import collections
import glob
import itertools
import os
import re
import shutil

from pyhelpers._cache import _format_err_msg
from pyhelpers.dirs import cd, validate_dir
from pyhelpers.ops import get_number_of_chunks
from pyhelpers.settings import gdal_configurations
from pyhelpers.store import load_pickle, save_pickle
from pyhelpers.text import find_similar_str

from pydriosm.downloader import BBBikeDownloader, GeofabrikDownloader
from pydriosm.reader.parser import PBFReadParse, SHPReadParse, VarReadParse
from pydriosm.utils import check_relpath, remove_osm_file


class _Reader:
    """
    Initialization of a data reader.
    """

    #: str: Name of the free download server.
    NAME = 'OSM Reader'
    #: str: Full name of the data resource.
    LONG_NAME = 'OpenStreetMap data reader and parser'
    #: str: Default data directory.
    DEFAULT_DATA_DIR = 'osm_data'

    #: PBFReadParse: Read/parse `PBF <https://wiki.openstreetmap.org/wiki/PBF_Format>`_ data.
    PBF = PBFReadParse
    #: SHPReadParse: Read/parse `Shapefile <https://wiki.openstreetmap.org/wiki/Shapefiles>`_ data.
    SHP = SHPReadParse
    #: VarReadParse: Read/parse OSM data of various formats (other than PBF and Shapefile).
    VAR = VarReadParse

    def __init__(self, downloader=None, data_dir=None, max_tmpfile_size=None):
        """
        :param downloader: class of a downloader, valid options include
            :class:`~pydriosm.downloader.GeofabrikDownloader` and
            :class:`~pydriosm.downloader.BBBikeDownloader`
        :type downloader: GeofabrikDownloader | BBBikeDownloader | None
        :param data_dir: directory where the data file is located/saved, defaults to ``None``;
            when ``data_dir=None``,
            it refers to the directory specified by the corresponding downloader
        :type data_dir: str | None
        :param max_tmpfile_size: defaults to ``None``,
            see also the function `pyhelpers.settings.gdal_configurations()`_
        :type max_tmpfile_size: int | None

        :ivar GeofabrikDownloader | BBBikeDownloader | None downloader:
            instance of the class :class:`~pydriosm.downloader.GeofabrikDownloader` or
            :class:`~pydriosm.downloader.BBBikeDownloader`

        .. _`pyhelpers.settings.gdal_configurations()`:
            https://pyhelpers.readthedocs.io/en/latest/_generated/
            pyhelpers.settings.gdal_configurations.html

        **Tests**::

            >>> from pydriosm.reader._reader import _Reader

            >>> r = _Reader()

            >>> r.NAME
            'OSM Reader'

            >>> r.SHP
            pydriosm.reader.SHPReadParse
        """

        if downloader is None:
            from pydriosm.downloader._downloader import _Downloader
            self.downloader = _Downloader
        else:
            assert downloader in {GeofabrikDownloader, BBBikeDownloader}
            # noinspection PyCallingNonCallable
            self.downloader = downloader(download_dir=data_dir)
            for x in {'NAME', 'LONG_NAME', 'FILE_FORMATS'}:
                setattr(self, x, getattr(self.downloader, x))

        self.max_tmpfile_size = 5000 if max_tmpfile_size is None else max_tmpfile_size

    @classmethod
    def cdd(cls, *sub_dir, mkdir=False, **kwargs):
        """
        Change directory to default data directory and its subdirectories or a specific file.

        :param sub_dir: name of directory; names of directories (and/or a filename)
        :type sub_dir: str | os.PathLike[str]
        :param mkdir: whether to create a directory, defaults to ``False``
        :type mkdir: bool
        :param kwargs: [optional] parameters of the function `pyhelpers.dir.cd()`_
        :return: an absolute pathname to a directory (or a file)
        :rtype: str | os.PathLike[str]

        .. _`pyhelpers.dir.cd()`:
            https://pyhelpers.readthedocs.io/en/latest/_generated/pyhelpers.dir.cd.html

        **Tests**::

            >>> from pydriosm.reader._reader import _Reader
            >>> import os

            >>> os.path.relpath(_Reader.cdd())
            'osm_data'

            >>> os.path.exists(_Reader.cdd())
            False
        """

        pathname = cd(cls.DEFAULT_DATA_DIR, *sub_dir, mkdir=mkdir, **kwargs)

        return pathname

    # noinspection PyTypeChecker
    @property
    def data_dir(self):
        """
        Name or pathname of a data directory.

        :return: name or pathname of a directory for saving downloaded data files
        :rtype: str | None

        **Tests**::

            >>> from pydriosm.reader._reader import _Reader
            >>> from pydriosm.downloader import GeofabrikDownloader, BBBikeDownloader
            >>> import os

            >>> r = _Reader()
            >>> os.path.relpath(r.data_dir)
            'osm_data'

            >>> r = _Reader(downloader=GeofabrikDownloader)
            >>> os.path.relpath(r.data_dir)
            'osm_data\\geofabrik'

            >>> r = _Reader(downloader=BBBikeDownloader)
            >>> os.path.relpath(r.data_dir)
            'osm_data\\bbbike'
        """

        if hasattr(self.downloader, 'download_dir'):
            _data_dir = getattr(self.downloader, 'download_dir')
        else:
            _data_dir = validate_dir(self.downloader.DEFAULT_DOWNLOAD_DIR)

        return _data_dir

    @property
    def data_paths(self):
        """
        Pathnames of all data files.

        :return: pathnames of all data files
        :rtype: list

        **Tests**::

            >>> from pydriosm.reader._reader import _Reader

            >>> r = _Reader()
            >>> r.data_paths
            []
        """

        if hasattr(self.downloader, 'download_dir'):
            _data_paths = getattr(self.downloader, 'data_paths')
        else:
            _data_paths = []

        return _data_paths

    # noinspection PyTypeChecker
    def get_file_path(self, subregion_name, osm_file_format, data_dir=None):
        """
        Get the path to an OSM data file (if available) of a specific file format
        for a geographic (sub)region.

        :param subregion_name: name of a geographic (sub)region (case-insensitive)
            that is available on a free download server
        :type subregion_name: str
        :param osm_file_format: format (file extension) of OSM data
        :type osm_file_format: str
        :param data_dir: directory where the data file is located/saved, defaults to ``None``;
            when ``data_dir=None``,
            it refers to the directory specified by the corresponding downloader
        :type data_dir: str | None
        :return: path to the data file
        :rtype: str | None

        **Tests**::

            >>> from pydriosm.reader._reader import _Reader
            >>> from pydriosm.downloader import GeofabrikDownloader, BBBikeDownloader
            >>> import os

            >>> r = _Reader(downloader=GeofabrikDownloader)

            >>> subrgn_name = 'rutland'
            >>> file_format = ".pbf"
            >>> dat_dir = "tests\\osm_data"

            >>> path_to_rutland_pbf = r.get_file_path(subrgn_name, file_format, dat_dir)
            >>> os.path.relpath(path_to_rutland_pbf)
            'tests\\osm_data\\rutland\\rutland-latest.osm.pbf'
            >>> os.path.isfile(path_to_rutland_pbf)
            False

            >>> subrgn_name = 'leeds'
            >>> path_to_leeds_pbf = r.get_file_path(subrgn_name, file_format, dat_dir)
            >>> path_to_leeds_pbf is None
            True

            >>> # Change the `downloader` to `BBBikeDownloader`
            >>> r = _Reader(downloader=BBBikeDownloader)
            >>> path_to_leeds_pbf = r.get_file_path(subrgn_name, file_format, dat_dir)
            >>> os.path.relpath(path_to_leeds_pbf)
            'tests\\osm_data\\leeds\\Leeds.osm.pbf'
        """

        _, _, _, path_to_file = self.downloader.get_valid_download_info(
            subregion_name=subregion_name, osm_file_format=osm_file_format, download_dir=data_dir)

        # if path_to_file is None:
        #     raise InvalidSubregionNameError(subregion_name=subregion_name, msg=1)

        return path_to_file

    @classmethod
    def validate_file_path(cls, path_to_osm_file, osm_filename=None, data_dir=None):
        """
        Validate the pathname of an OSM data file.

        :param path_to_osm_file: pathname of an OSM data file
        :type path_to_osm_file: str | os.PathLike[str]
        :param osm_filename: filename of the OSM data file
        :type osm_filename: str
        :param data_dir: name or pathname of the data directory
        :type data_dir: str | os.PathLike[str]
        :return: validated pathname of the specified OSM data file
        :rtype: str

        **Tests**::

            >>> from pydriosm.reader._reader import _Reader
            >>> import os

            >>> file_path = _Reader.validate_file_path("a\\b\\c.osm.pbf")
            >>> file_path
            'a\\b\\c.osm.pbf'
            >>> file_path = _Reader.validate_file_path("a\\b\\c.osm.pbf", "x.y.z", data_dir="a\\b")
            >>> os.path.relpath(file_path)
            'a\\b\\x.y.z'
        """

        if not data_dir:  # Go to default file path
            valid_file_path = path_to_osm_file

        else:
            osm_pbf_dir = validate_dir(path_to_dir=data_dir)
            if osm_filename is None:
                osm_filename_ = os.path.basename(path_to_osm_file)
            else:
                osm_filename_ = osm_filename
            valid_file_path = os.path.join(osm_pbf_dir, osm_filename_)

        return valid_file_path

    @classmethod
    def remove_extracts(cls, path_to_extract_dir, verbose):
        """
        Remove data extracts.

        :param path_to_extract_dir: pathname of the directory where data extracts are stored
        :type path_to_extract_dir: str | os.PathLike[str]
        :param verbose: whether to print relevant information in console as the function runs,
            defaults to ``False``
        :type verbose: bool | int

        See examples for the methods
        :meth:`GeofabrikReader.read_shp_zip()<pydriosm.reader.GeofabrikReader.read_shp_zip>` and
        :meth:`BBBikeReader.read_shp_zip()<pydriosm.reader.BBBikeReader.read_shp_zip>`.
        """

        if verbose:
            extr_dir_rel_path = check_relpath(path_to_extract_dir)
            print(f"Deleting the extracts \"{extr_dir_rel_path}\\\"", end=" ... ")

        try:
            # for f in glob.glob(os.path.join(extract_dir, "gis_osm*")):
            #     # if layer not in f:
            #     os.remove(f)
            shutil.rmtree(path_to_extract_dir)

            if verbose:
                print("Done.")

        except Exception as e:
            print(f"Failed. {_format_err_msg(e)}")

    @classmethod
    def validate_input_dtype(cls, var_input):
        """
        Validate the data type of the input variable.

        :param var_input: a variable
        :type var_input: str | list | None
        :return: validated input
        :rtype: list

        **Tests**::

            >>> from pydriosm.reader._reader import _Reader

            >>> _Reader.validate_input_dtype(var_input=None)
            []

            >>> _Reader.validate_input_dtype(var_input='str')
            ['str']

            >>> _Reader.validate_input_dtype(var_input=['str'])
            ['str']
        """

        if var_input:
            var_input_ = [var_input] if isinstance(var_input, str) else var_input.copy()
        else:
            var_input_ = []

        return var_input_

    def _read_osm_pbf(self, pbf_pathname, chunk_size_limit, readable, expand, pickle_it,
                      path_to_pickle, ret_pickle_path, rm_pbf_file, verbose, **kwargs):

        if verbose:
            action_msg = "Parsing" if readable or expand else "Reading"
            print(f"{action_msg} \"{check_relpath(pbf_pathname)}\"", end=" ... ")

        try:
            number_of_chunks = get_number_of_chunks(
                file_or_obj=pbf_pathname, chunk_size_limit=chunk_size_limit)

            data = self.PBF.read_pbf(
                pbf_pathname=pbf_pathname, readable=readable, expand=expand,
                number_of_chunks=number_of_chunks, **kwargs)

            if verbose:
                print("Done.")

            if pickle_it and (readable or expand):
                save_pickle(data, path_to_pickle, verbose=verbose)

                if ret_pickle_path:
                    data = data, path_to_pickle

            if rm_pbf_file:
                remove_osm_file(pbf_pathname, verbose=verbose)

        except Exception as e:
            print(f"Failed. {_format_err_msg(e)}")

            data = None

        return data

    def read_osm_pbf(self, subregion_name, data_dir=None, readable=False, expand=False,
                     parse_geometry=False, parse_properties=False, parse_other_tags=False,
                     update=False, download=True, pickle_it=False, ret_pickle_path=False,
                     rm_pbf_file=False, chunk_size_limit=50, verbose=False, **kwargs):
        """
        Read a PBF (.osm.pbf) data file of a geographic (sub)region.

        :param subregion_name: name of a geographic (sub)region (case-insensitive)
            that is available on Geofabrik free download server
        :type subregion_name: str
        :param data_dir: directory where the .osm.pbf data file is located/saved;
            if ``None``, the default local directory
        :type data_dir: str | None
        :param readable: whether to parse each feature in the raw data, defaults to ``False``
        :type readable: bool
        :param expand: whether to expand dict-like data into separate columns, defaults to ``False``
        :type expand: bool
        :param parse_geometry: whether to represent the ``'geometry'`` field
            in a `shapely.geometry`_ format, defaults to ``False``
        :type parse_geometry: bool
        :param parse_properties: whether to represent the ``'properties'`` field
            in a tabular format, defaults to ``False``
        :type parse_properties: bool
        :param parse_other_tags: whether to represent a ``'other_tags'`` (of ``'properties'``)
            in a `dict`_ format, defaults to ``False``
        :type parse_other_tags: bool
        :param download: whether to download/update the PBF data file of the given subregion,
            if it is not available at the specified path, defaults to ``True``
        :type download: bool
        :param update: whether to check to update pickle backup (if available), defaults to ``False``
        :type update: bool
        :param pickle_it: whether to save the .pbf data as a pickle file, defaults to ``False``
        :type pickle_it: bool
        :param ret_pickle_path: (when ``pickle_it=True``)
            whether to return a path to the saved pickle file
        :type ret_pickle_path: bool
        :param rm_pbf_file: whether to delete the downloaded .osm.pbf file, defaults to ``False``
        :type rm_pbf_file: bool
        :param chunk_size_limit: threshold (in MB) that triggers the use of chunk parser,
            defaults to ``50``;
            if the size of the .osm.pbf file (in MB) is greater than ``chunk_size_limit``,
            it will be parsed in a chunk-wise way
        :type chunk_size_limit: int | None
        :param verbose: whether to print relevant information in console as the function runs,
            defaults to ``False``
        :type verbose: bool | int
        :param kwargs: [optional] parameters of the method
            :meth:`PBFReadParse.read_pbf()<pydriosm.reader.PBFReadParse.read_pbf>`
        :return: dictionary of the .osm.pbf data;
            when ``pickle_it=True``, return a tuple of the dictionary and a path to the pickle file
        :rtype: dict | tuple | None

        .. _`shapely.geometry`:
            https://shapely.readthedocs.io/en/latest/manual.html#geometric-objects
        .. _`dict`:
            https://docs.python.org/3/library/stdtypes.html#dict

        .. seealso::

            - Examples for the methods
              :meth:`GeofabrikReader.read_osm_pbf()<pydriosm.reader.GeofabrikReader.read_osm_pbf>`
              and :meth:`BBBikeReader.read_osm_pbf()<pydriosm.reader.BBBikeReader.read_osm_pbf>`.
        """

        kwargs.update({'max_tmpfile_size': self.max_tmpfile_size})
        gdal_configurations(**kwargs)

        osm_file_format = ".osm.pbf"

        subregion_name_, _, _, path_to_osm_pbf = self.downloader.get_valid_download_info(
            subregion_name=subregion_name, osm_file_format=osm_file_format, download_dir=data_dir)

        if path_to_osm_pbf is not None:
            suffix = "-pbf.pkl" if readable else "-raw.pkl"
            path_to_pickle = path_to_osm_pbf.replace(osm_file_format, suffix)

            if os.path.isfile(path_to_pickle) and not update:
                osm_pbf_data = load_pickle(path_to_pickle)

                if ret_pickle_path:
                    osm_pbf_data = osm_pbf_data, path_to_pickle

            else:  # If the target file is not available, try downloading it:
                if (not os.path.exists(path_to_osm_pbf) or update) and download:
                    self.downloader.download_osm_data(
                        subregion_names=subregion_name, osm_file_format=osm_file_format,
                        download_dir=data_dir, update=update, confirmation_required=False,
                        verbose=verbose)

                if os.path.isfile(path_to_osm_pbf):
                    osm_pbf_data = self._read_osm_pbf(
                        pbf_pathname=path_to_osm_pbf, chunk_size_limit=chunk_size_limit,
                        readable=readable, expand=expand, parse_geometry=parse_geometry,
                        parse_properties=parse_properties, parse_other_tags=parse_other_tags,
                        pickle_it=pickle_it, path_to_pickle=path_to_pickle,
                        ret_pickle_path=ret_pickle_path, rm_pbf_file=rm_pbf_file, verbose=verbose)

                else:
                    osm_pbf_data = None
                    if verbose:
                        print(f"The {osm_file_format} file for \"{subregion_name_}\" is not found.")

            return osm_pbf_data

    def get_shp_pathname(self, subregion_name, layer_name=None, feature_name=None, data_dir=None):
        """
        Get path(s) to shapefile(s) for a geographic (sub)region
        (by searching a local data directory).

        :param subregion_name: name of a geographic (sub)region (case-insensitive)
            that is available on Geofabrik free download server
        :type subregion_name: str
        :param layer_name: name of a .shp layer (e.g. ``'railways'``), defaults to ``None``
        :type layer_name: str | None
        :param feature_name: name of a feature (e.g. ``'rail'``);
            if ``None`` (default), all available features included
        :type feature_name: str | None
        :param data_dir: directory where the search is conducted; if ``None`` (default),
            the default directory
        :type data_dir: str | None
        :return: path(s) to shapefile(s)
        :rtype: list

        **Examples**::

            >>> from pydriosm.reader import GeofabrikReader
            >>> from pyhelpers.dirs import delete_dir
            >>> import os

            >>> gfr = GeofabrikReader()

            >>> subrgn_name = 'london'
            >>> file_format = ".shp"
            >>> dat_dir = "tests\\osm_data"

            >>> # Try to get the shapefiles' pathnames
            >>> london_shp_path = gfr.get_shp_pathname(subregion_name=subrgn_name, data_dir=dat_dir)
            >>> london_shp_path  # An empty list if no data is available
            []

            >>> # Download the shapefiles of London
            >>> path_to_london_shp_zip = gfr.downloader.download_osm_data(
            ...     subrgn_name, file_format, dat_dir, verbose=True, ret_download_path=True)
            To download .shp.zip data of the following geographic (sub)region(s):
                Greater London
            ? [No]|Yes: yes
            Downloading "greater-london-latest-free.shp.zip"
                to "tests\\osm_data\\greater-london\\" ... Done.

            >>> # Extract the downloaded .zip file
            >>> gfr.SHP.unzip_shp_zip(path_to_london_shp_zip[0], verbose=True)
            Extracting "tests\\osm_data\\greater-london\\greater-london-latest-free.shp.zip"
                to "tests\\osm_data\\greater-london\\greater-london-latest-free-shp\\" ... Done.

            >>> # Try again to get the shapefiles' pathnames
            >>> london_shp_path = gfr.get_shp_pathname(subrgn_name, data_dir=dat_dir)
            >>> len(london_shp_path) > 1
            True

            >>> # Get the file path of 'railways' shapefile
            >>> lyr_name = 'railways'
            >>> railways_shp_path = gfr.get_shp_pathname(subrgn_name, lyr_name, data_dir=dat_dir)
            >>> len(railways_shp_path)
            1
            >>> railways_shp_path = railways_shp_path[0]
            >>> os.path.relpath(railways_shp_path)
            'tests\\osm_data\\greater-london\\greater-london-latest-free-shp\\gis_osm_railways_fr...

            >>> # Get/save shapefile data of features labelled 'rail' only
            >>> feat_name = 'rail'
            >>> railways_shp = gfr.SHP.read_layer_shps(
            ...     railways_shp_path, feature_names=feat_name, save_feat_shp=True)
            >>> railways_shp.head()
                osm_id  code  ...                                        coordinates shape_type
            0    30804  6101  ...  [(0.0048644, 51.6279262), (0.0061979, 51.62926...          3
            3   101511  6101  ...  [(-0.2119027, 51.5241906), (-0.2108059, 51.523...          3
            5   361978  6101  ...  [(-0.0298545, 51.6619398), (-0.0302322, 51.659...          3
            6  2370155  6101  ...  [(-0.3379005, 51.5937776), (-0.3367807, 51.593...          3
            7  2526598  6101  ...  [(-0.1886021, 51.3602632), (-0.1884216, 51.360...          3
            [5 rows x 9 columns]

            >>> # Get the file path to the data of 'rail'
            >>> rail_shp_path = gfr.get_shp_pathname(subrgn_name, lyr_name, feat_name, dat_dir)
            >>> len(rail_shp_path)
            1
            >>> rail_shp_path = rail_shp_path[0]
            >>> os.path.relpath(rail_shp_path)
            'tests\\osm_data\\greater-london\\greater-london-latest-free-shp\\railways\\rail.shp'

            >>> # Retrieve the data of 'rail' feature
            >>> railways_rail_shp = gfr.SHP.read_layer_shps(rail_shp_path)
            >>> railways_rail_shp.head()
                osm_id  code  ...                                        coordinates shape_type
            0    30804  6101  ...  [(0.0048644, 51.6279262), (0.0061979, 51.62926...          3
            1   101511  6101  ...  [(-0.2119027, 51.5241906), (-0.2108059, 51.523...          3
            2   361978  6101  ...  [(-0.0298545, 51.6619398), (-0.0302322, 51.659...          3
            3  2370155  6101  ...  [(-0.3379005, 51.5937776), (-0.3367807, 51.593...          3
            4  2526598  6101  ...  [(-0.1886021, 51.3602632), (-0.1884216, 51.360...          3
            [5 rows x 9 columns]

            >>> # Delete the example data and the test data directory
            >>> delete_dir(dat_dir, verbose=True)
            To delete the directory "tests\\osm_data\\" (Not empty)
            ? [No]|Yes: yes
            Deleting "tests\\osm_data\\" ... Done.
        """

        osm_file_format, shp_file_ext = ".shp.zip", ".shp"

        path_to_shp_zip = self.get_file_path(
            subregion_name=subregion_name, osm_file_format=osm_file_format, data_dir=data_dir)
        shp_dir = os.path.splitext(path_to_shp_zip)[0].replace(".", "-")

        available_pathnames = glob.glob(os.path.join(shp_dir, f"*{shp_file_ext}"))
        if not available_pathnames:
            available_pathnames = glob.glob(os.path.join(shp_dir, "*", f"*{shp_file_ext}"))

        if layer_name is None:
            path_to_osm_shp_file = available_pathnames

        else:
            layer_name_ = find_similar_str(x=layer_name, lookup_list=self.SHP.LAYER_NAMES)

            pat_ = f'gis_osm_{layer_name_}(_a)?(_free)?(_1)?'
            if feature_name is None:
                pat = re.compile(f"{pat_}{shp_file_ext}")
                lookup = available_pathnames
            else:
                if isinstance(feature_name, str):
                    ft_name = feature_name
                else:
                    ft_name = "_".join(list(feature_name))
                pat = re.compile(f"{pat_}_{ft_name}{shp_file_ext}")
                lookup = glob.glob(os.path.join(shp_dir, layer_name_, f"*{shp_file_ext}"))

            path_to_osm_shp_file = [f for f in lookup if re.search(pat, f)]

        # if not path_to_osm_shp_file: print("The required file is not found.")
        # if len(path_to_osm_shp_file) == 1: path_to_osm_shp_file = path_to_osm_shp_file[0]

        return path_to_osm_shp_file

    @classmethod
    def make_shp_pkl_pathname(cls, shp_zip_filename, extract_dir, layer_names_, feature_names_):
        """
        Make a pathname of a pickle file for saving shapefile data.

        :param shp_zip_filename: filename of a .shp.zip file
        :type shp_zip_filename: str
        :param extract_dir: pathname of a directory to which the .shp.zip file is extracted
        :type extract_dir: str
        :param layer_names_: names of shapefile layers
        :type layer_names_: list
        :param feature_names_: names of shapefile features
        :type feature_names_: list
        :return: pathname of a pickle file for saving data of the specified shapefile
        :rtype: str

        See examples for the methods
        :meth:`GeofabrikReader.read_shp_zip()<pydriosm.reader.GeofabrikReader.read_shp_zip>` and
        :meth:`BBBikeReader.read_shp_zip()<pydriosm.reader.BBBikeReader.read_shp_zip>`.
        """

        if layer_names_:  # layer is not None
            temp = layer_names_ + (feature_names_ if feature_names_ else [])
            # Make a local path for saving a pickle file for .shp data
            if cls.NAME == 'Geofabrik':
                filename_ = shp_zip_filename.replace("-latest-free.shp.zip", "")
                sub_fname = "-".join(x[:3] for x in [filename_] + temp if x)
            else:
                filename_ = shp_zip_filename.replace(".osm.shp.zip", "").lower()
                sub_fname = "-".join(x for x in [filename_] + temp if x)
            path_to_shp_pickle = os.path.join(os.path.dirname(extract_dir), sub_fname + "-shp.pkl")

        else:  # len(layer_names_) >= 12
            if cls.NAME == 'Geofabrik':
                path_to_shp_pickle = extract_dir.replace("-latest-free-shp", "-shp.pkl")
            else:
                path_to_shp_pickle = extract_dir + ".pkl"

        return path_to_shp_pickle

    def _get_shp_layer_names(self, extract_dir_):
        if self.NAME == 'Geofabrik':
            lyr_names_ = [
                self.SHP.find_shp_layer_name(x) for x in os.listdir(extract_dir_) if x != 'README']
        else:
            lyr_names_ = [
                x.rsplit(".", 1)[0] for x in os.listdir(os.path.join(extract_dir_, "shape"))]

        return lyr_names_

    def validate_shp_layer_names(self, layer_names_, extract_dir, shp_zip_pathname, subregion_name,
                                 osm_file_format, data_dir, update, download, verbose):
        """
        Validate the input of layer name(s) for reading shapefiles.

        :param layer_names_: names of shapefile layers
        :type layer_names_: list
        :param extract_dir: pathname of a directory to which the .shp.zip file is extracted
        :type extract_dir: str
        :param shp_zip_pathname: pathname of a .shp.zip file
        :type shp_zip_pathname: str
        :param subregion_name: name of a geographic (sub)region (case-insensitive)
            that is available on Geofabrik free download server
        :type subregion_name: str
        :param osm_file_format: format (file extension) of OSM data
        :type osm_file_format: str
        :param data_dir: name or pathname of the data directory
        :type data_dir: str | os.PathLike[str]
        :param update: whether to check to update pickle backup (if available), defaults to ``False``
        :type update: bool
        :param download: whether to download/update the PBF data file of the given subregion,
            if it is not available at the specified path, defaults to ``True``
        :type download: bool
        :param verbose: whether to print relevant information in console as the function runs,
            defaults to ``False``
        :type verbose: bool | int
        :return: validated shapefile layer names
        :rtype: list

        See examples for the methods
        :meth:`GeofabrikReader.read_shp_zip()<pydriosm.reader.GeofabrikReader.read_shp_zip>` and
        :meth:`BBBikeReader.read_shp_zip()<pydriosm.reader.BBBikeReader.read_shp_zip>`.
        """

        if self.NAME == 'Geofabrik':
            extract_dir_ = path_to_extract_dir = extract_dir
        else:
            path_to_extract_dir = os.path.dirname(shp_zip_pathname)
            extract_dir_ = os.path.splitext(shp_zip_pathname)[0].replace(".osm.", "-")

        download_args = {
            'subregion_names': subregion_name,
            'osm_file_format': osm_file_format,
            'download_dir': data_dir,
            'update': update,
            'confirmation_required': False,
            'verbose': verbose,
            # 'ret_download_path': True,
        }

        layer_name_list = [find_similar_str(x, self.SHP.LAYER_NAMES) for x in layer_names_]

        if not os.path.exists(extract_dir_):
            if (not os.path.exists(shp_zip_pathname) or update) and download:
                # Download the requested OSM file
                self.downloader.download_osm_data(**download_args)

            if os.path.isfile(shp_zip_pathname):
                # and shp_zip_pathname in self.downloader.data_paths:
                self.SHP.unzip_shp_zip(
                    shp_zip_pathname=shp_zip_pathname, extract_to=path_to_extract_dir,
                    layer_names=layer_names_, verbose=verbose)

                if not layer_names_:
                    lyr_names_ = self._get_shp_layer_names(extract_dir_=extract_dir_)
                    layer_name_list = sorted(list(set(lyr_names_)))

        else:
            unavailable_layers = []

            layer_names_temp_ = self._get_shp_layer_names(extract_dir_=extract_dir_)
            layer_names_temp = sorted(list(set(layer_name_list + layer_names_temp_)))

            for layer_name in layer_names_temp:
                if self.NAME == 'Geofabrik':
                    shp_filename = self.get_shp_pathname(
                        subregion_name=subregion_name, layer_name=layer_name, data_dir=data_dir)
                    if not shp_filename:
                        unavailable_layers.append(layer_name)
                else:
                    shp_filename = os.path.join(extract_dir_, "shape", f"{layer_name}.shp")
                    if not os.path.isfile(shp_filename):
                        unavailable_layers.append(layer_name)

            if len(unavailable_layers) > 0:
                if not os.path.exists(shp_zip_pathname) and download:
                    self.downloader.download_osm_data(**download_args)

                if os.path.isfile(shp_zip_pathname):
                    self.SHP.unzip_shp_zip(
                        shp_zip_pathname=shp_zip_pathname, extract_to=path_to_extract_dir,
                        layer_names=unavailable_layers, verbose=verbose)

            if not layer_name_list:
                layer_name_list = layer_names_temp

        return layer_name_list

    def _read_shp_zip(self, shp_pathnames, feature_names_, layer_name_list, pickle_it,
                      path_to_pickle, ret_pickle_path, rm_extracts, extract_dir, rm_shp_zip,
                      shp_zip_pathname, verbose, **kwargs):
        if verbose:
            # print(f'Reading the shapefile(s) data', end=" ... ")
            files_dir = check_relpath(
                os.path.commonpath(list(itertools.chain.from_iterable(shp_pathnames))))
            msg_ = "the shapefile(s) at\n\t" if os.path.isdir(files_dir) else ""
            print(f'Reading {msg_}"{files_dir}\\"', end=" ... ")

        try:
            kwargs.update({'feature_names': feature_names_, 'ret_feat_shp_path': False})
            shp_dat_list = [
                self.SHP.read_layer_shps(shp_pathnames=x, **kwargs) for x in shp_pathnames]

            shp_data = collections.OrderedDict(zip(layer_name_list, shp_dat_list))

            if verbose:
                print("Done.")

            if pickle_it:
                save_pickle(shp_data, path_to_pickle, verbose=verbose)

                if ret_pickle_path:
                    shp_data = shp_data, path_to_pickle

            if os.path.exists(extract_dir) and rm_extracts:
                self.remove_extracts(extract_dir, verbose=verbose)

            if os.path.isfile(shp_zip_pathname) and rm_shp_zip:
                remove_osm_file(shp_zip_pathname, verbose=verbose)

        except Exception as e:
            print(f"Failed. {_format_err_msg(e)}")
            shp_data = None

        return shp_data

    def read_shp_zip(self, subregion_name, layer_names=None, feature_names=None, data_dir=None,
                     update=False, download=True, pickle_it=False, ret_pickle_path=False,
                     rm_extracts=False, rm_shp_zip=False, verbose=False, **kwargs):
        """
        Read a .shp.zip data file of a geographic (sub)region.

        :param subregion_name: name of a geographic (sub)region (case-insensitive)
            that is available on Geofabrik free download server
        :type subregion_name: str
        :param layer_names: name of a .shp layer, e.g. 'railways', or names of multiple layers;
            if ``None`` (default), all available layers
        :type layer_names: str | list | None
        :param feature_names: name of a feature, e.g. 'rail', or names of multiple features;
            if ``None`` (default), all available features
        :type feature_names: str | list | None
        :param data_dir: directory where the .shp.zip data file is located/saved;
            if ``None``, the default directory
        :type data_dir: str | None
        :param update: whether to check to update pickle backup (if available), defaults to ``False``
        :type update: bool
        :param download: whether to ask for confirmation
            before starting to download a file, defaults to ``True``
        :type download: bool
        :param pickle_it: whether to save the .shp data as a pickle file, defaults to ``False``
        :type pickle_it: bool
        :param ret_pickle_path: (when ``pickle_it=True``)
            whether to return a path to the saved pickle file
        :type ret_pickle_path: bool
        :param rm_extracts: whether to delete extracted files from the .shp.zip file,
            defaults to ``False``
        :type rm_extracts: bool
        :param rm_shp_zip: whether to delete the downloaded .shp.zip file, defaults to ``False``
        :type rm_shp_zip: bool
        :param verbose: whether to print relevant information in console as the function runs,
            defaults to ``False``
        :type verbose: bool | int
        :param kwargs: [optional] parameters of the method
            :meth:`SHPReadParse.read_shp()<pydriosm.reader.SHPReadParse.read_shp>`
        :return: dictionary of the shapefile data,
            with keys and values being layer names and tabular data
            (in the format of `geopandas.GeoDataFrame`_), respectively
        :rtype: dict | collections.OrderedDict | None

        .. _`geopandas.GeoDataFrame`: https://geopandas.org/reference.html#geodataframe

        See examples for the methods
        :meth:`GeofabrikReader.read_shp_zip()<pydriosm.reader.GeofabrikReader.read_shp_zip>` and
        :meth:`BBBikeReader.read_shp_zip()<pydriosm.reader.BBBikeReader.read_shp_zip>`.
        """

        osm_file_format = ".shp.zip"

        subregion_name_, shp_zip_filename, _, shp_zip_pathname = \
            self.downloader.get_valid_download_info(
                subregion_name=subregion_name, osm_file_format=osm_file_format,
                download_dir=data_dir)

        layer_names_, feature_names_ = map(self.validate_input_dtype, [layer_names, feature_names])

        if all(x is not None for x in {shp_zip_filename, shp_zip_pathname}):
            # The shapefile data of the subregion should be downloadable
            extract_dir_temp = os.path.splitext(shp_zip_pathname)[0]
            if self.NAME == 'Geofabrik':
                extract_dir = extract_dir_temp.replace(".", "-")
                shp_pathname_ = os.path.join(extract_dir, "gis_osm_{}_*.shp")
            else:
                extract_dir = extract_dir_temp.replace(".osm.", "-")
                shp_pathname_ = os.path.join(extract_dir, "shape", "{}.shp")

            path_to_pickle = self.make_shp_pkl_pathname(
                shp_zip_filename=shp_zip_filename, extract_dir=extract_dir,
                layer_names_=layer_names_, feature_names_=feature_names_)

            if os.path.isfile(path_to_pickle) and not update:
                shp_data = load_pickle(path_to_pickle, verbose=verbose)

                if ret_pickle_path:
                    shp_data = shp_data, path_to_pickle

            else:
                layer_name_list = self.validate_shp_layer_names(
                    layer_names_=layer_names_, extract_dir=extract_dir,
                    shp_zip_pathname=shp_zip_pathname, subregion_name=subregion_name_,
                    osm_file_format=osm_file_format, data_dir=data_dir, update=update,
                    download=download, verbose=verbose)

                if len(layer_name_list) > 0:
                    shp_pathnames = [
                        glob.glob(shp_pathname_.format(layer_name))
                        for layer_name in layer_name_list]

                    shp_data = self._read_shp_zip(
                        shp_pathnames=shp_pathnames, feature_names_=feature_names_,
                        layer_name_list=layer_name_list, pickle_it=pickle_it,
                        path_to_pickle=path_to_pickle, ret_pickle_path=ret_pickle_path,
                        rm_extracts=rm_extracts, extract_dir=extract_dir, rm_shp_zip=rm_shp_zip,
                        shp_zip_pathname=shp_zip_pathname, verbose=verbose, **kwargs)

                else:
                    shp_data = None
                    if verbose:
                        print(f"The {osm_file_format} file for \"{subregion_name_}\" is not found.")

            return shp_data

    def read_osm_var(self, meth, subregion_name, osm_file_format, data_dir=None, download=False,
                     verbose=False, **kwargs):
        """
        Read data file of various formats (other than PBF and shapefile)
        for a geographic (sub)region.

        :param meth: name of a class method for getting (auxiliary) prepacked data
        :type meth: typing.Callable
        :param subregion_name: name of a geographic (sub)region (case-insensitive)
            that is available on a free download server
        :type subregion_name: str
        :param osm_file_format: format (file extension) of OSM data
        :type osm_file_format: str
        :param data_dir: directory where the data file is located/saved, defaults to ``None``;
            when ``data_dir=None``,
            it refers to the directory specified by the corresponding downloader
        :type data_dir: str | None
        :param download: whether to download/update the PBF data file of the given subregion,
            if it is not available at the specified path, defaults to ``True``
        :type download: bool
        :param verbose: whether to print relevant information in console as the function runs,
            defaults to ``False``
        :type verbose: bool | int
        :param kwargs: [optional] parameters of the method specified by ``meth``
        :return: data of the specified file format
        :rtype: pandas.DataFrame | None

        See examples for the methods
        :meth:`BBBikeReader.read_csv_xz()<pydriosm.reader.BBBikeReader.read_csv_xz>` and
        :meth:`BBBikeReader.read_geojson_xz()<pydriosm.reader.BBBikeReader.read_geojson_xz>`.
        """

        subregion_name_ = self.downloader.validate_subregion_name(subregion_name)

        path_to_osm_var = self.get_file_path(subregion_name_, osm_file_format, data_dir)

        if not os.path.isfile(path_to_osm_var) and download:
            self.downloader.download_osm_data(
                subregion_names=subregion_name_, osm_file_format=osm_file_format,
                download_dir=data_dir, confirmation_required=False, verbose=verbose)
            downloaded = True
        else:
            downloaded = False

        if os.path.isfile(path_to_osm_var):
            if verbose:
                prt_msg = "the data" if downloaded else f'"{check_relpath(path_to_osm_var)}"'
                print(f"Parsing {prt_msg}", end=" ... ")

            try:
                # getattr(self.VAR, 'read_...')
                osm_var_data = meth(path_to_osm_var, **kwargs)

                if verbose:
                    print("Done.")

            except Exception as e:
                print(f"Failed. {_format_err_msg(e)}")
                osm_var_data = None

            return osm_var_data

        else:
            print(f'The requisite data file "{check_relpath(path_to_osm_var)}" does not exist.')
