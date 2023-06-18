"""
Define custom errors/exceptions.
"""


class InvalidSubregionNameError(Exception):
    """
    Exception raised when an input `subregion_name` is not recognizable.
    """

    def __init__(self, subregion_name, msg=None):
        """
        :param subregion_name: name of a (sub)region available on a free download server
        :type subregion_name: str
        :param msg: index of optional messages, defaults to ``None``; options include {1, 2}
        :type msg: int | None

        :ivar: str subregion_name: name of a (sub)region available on a free download server
        :ivar: int | None msg: index of optional messages; options include {1, 2}
        :ivar: str: error message

        **Examples**::

            >>> from pydriosm.errors import InvalidSubregionNameError

            >>> raise InvalidSubregionNameError(subregion_name='abc')
            Traceback (most recent call last):
              ...
            pydriosm.errors.InvalidSubregionNameError:
              `subregion_name='abc'` -> The input of `subregion_name` is not recognizable.
              Check the `.data_source`, or try another one instead.

            >>> from pydriosm.downloader import GeofabrikDownloader, BBBikeDownloader

            >>> gfd = GeofabrikDownloader()
            >>> gfd.validate_subregion_name(subregion_name='birmingham')
            Traceback (most recent call last):
              ...
            pydriosm.errors.InvalidSubregionNameError:
              `subregion_name='birmingham'`
                1) `subregion_name` fails to match any in `<downloader>.valid_subregion_names`; or
                2) The queried (sub)region is not available on the free download server.

            >>> bbd = BBBikeDownloader()
            >>> bbd.validate_subregion_name(subregion_name='bham')
            Traceback (most recent call last):
              ...
            pydriosm.errors.InvalidSubregionNameError:
              `subregion_name='bham'` -> The input of `subregion_name` is not recognizable.
              Check the `.data_source`, or try another one instead.
        """

        self.subregion_name = subregion_name
        self.msg = msg

        if self.msg == 1:
            self.message = \
                "\t1) `subregion_name` fails to match any in " \
                "`<downloader>.valid_subregion_names`; " \
                "or\n" \
                "\t2) The queried (sub)region is not available on the free download server."
        else:
            self.message = "The input of `subregion_name` is not recognizable.\n" \
                           "  Check the `.data_source`, or try another one instead."

        super().__init__(self.message)

    def __str__(self):
        conj = "\n" if self.msg == 1 else " -> "
        return f"\n  `subregion_name='{self.subregion_name}'`{conj}{self.message}"


class InvalidFileFormatError(Exception):
    """
    Exception raised when an input `osm_file_format` is not recognizable.
    """

    def __init__(self, osm_file_format, valid_file_formats=None):
        """
        :param osm_file_format: file format/extension of the OSM data on the free download server
        :type osm_file_format: str
        :param valid_file_formats: filename extensions of the data files available on
            the free download server, defaults to ``None``
        :type valid_file_formats: typing.Iterable | None

        :ivar: str osm_file_format: file format/extension of the OSM data
            available on the free download server
        :ivar: int | None message: error message

        **Examples**::

            >>> from pydriosm.errors import InvalidFileFormatError

            >>> raise InvalidFileFormatError(osm_file_format='abc')
            Traceback (most recent call last):
              ...
            pydriosm.errors.InvalidFileFormatError:
              `osm_file_format='abc'` -> The input `osm_file_format` is unidentifiable.

            >>> from pydriosm.downloader import GeofabrikDownloader, BBBikeDownloader

            >>> gfd = GeofabrikDownloader()
            >>> gfd.validate_file_format(osm_file_format='abc')
            Traceback (most recent call last):
              ...
            pydriosm.errors.InvalidFileFormatError:
              `osm_file_format='abc'` -> The input `osm_file_format` is unidentifiable.
                Valid options include: {'.shp.zip', '.osm.pbf', '.osm.bz2'}.

            >>> bbd = BBBikeDownloader()
            >>> bbd.validate_file_format(osm_file_format='abc')
            Traceback (most recent call last):
              ...
            pydriosm.errors.InvalidFileFormatError:
              `osm_file_format='abc'` -> The input `osm_file_format` is unidentifiable.
                Valid options include: {'.shp.zip', '.geojson.xz', '.mapsforge-osm.zip', '.pbf', ...
        """

        self.osm_file_format = osm_file_format

        self.message = "The input `osm_file_format` is unidentifiable."
        if valid_file_formats:
            self.message += f"\n\tValid options include: {valid_file_formats}."

        super().__init__(self.message)

    def __str__(self):
        return f"\n  `osm_file_format='{self.osm_file_format}'` -> {self.message}"


class OtherTagsReformatError(Exception):
    """
    Exception raised when errors occur in the process of parsing ``other_tags`` in a PBF data file.
    """

    def __init__(self, other_tags):
        """
        :param other_tags: data of ``'other_tags'`` of a single feature in a PBF data file
        :type other_tags: str | None

        :ivar str | None other_tags: data of ``'other_tags'`` of a single feature
            in a PBF data file
        :ivar str message: error message

        **Examples**::

            >>> from pydriosm.errors import OtherTagsReformatError

            >>> raise OtherTagsReformatError(other_tags='abc')
            Traceback (most recent call last):
              ...
            pydriosm.errors.OtherTagsReformatError:
              `other_tags='abc'` -> Failed to reformat the ...
        """

        self.other_tags = other_tags
        self.message = "Failed to reformat the `other_tags`."

        super().__init__(self.message)

    def __str__(self):
        return f"\n  `other_tags='{self.other_tags}'` -> {self.message}"
