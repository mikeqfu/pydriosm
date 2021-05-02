### Release history



#### [2.0.3](https://github.com/mikeqfu/pydriosm/releases/tag/2.0.3)

*25 April 2021*

##### Main [changes](https://github.com/mikeqfu/pydriosm/compare/2.0.2...2.0.3) since [v2.0.2](https://github.com/mikeqfu/pydriosm/tree/d7cb423ae30dc3443139fc6063ea3ce24ed7afd9):

- modified the module [downloader](https://github.com/mikeqfu/pydriosm/blob/e5f8fe491cb0bf1f7c22e6e02851c78c288327e8/pydriosm/downloader.py) with [bug fixes](https://github.com/mikeqfu/pydriosm/commit/52f76723a84cd822fc002f89bf92a744cbd88141)
- in the module [reader](https://github.com/mikeqfu/pydriosm/blob/e5f8fe491cb0bf1f7c22e6e02851c78c288327e8/pydriosm/reader.py),
  - renamed [get_default_shp_crs()](https://github.com/mikeqfu/pydriosm/commit/5786c620fee89fa2a0db4c8329f7d9cabf7ea81d#diff-fc8bd4c3f1ee495f89956160ebf3736c1b8f8021e61f3eb14662439f8a781aacL694) to [get_epsg4326_wgs84_crs_ref()](https://github.com/mikeqfu/pydriosm/commit/5786c620fee89fa2a0db4c8329f7d9cabf7ea81d#diff-fc8bd4c3f1ee495f89956160ebf3736c1b8f8021e61f3eb14662439f8a781aacR733)
  - added functions [get_epsg4326_wgs84_prj_ref()](https://github.com/mikeqfu/pydriosm/commit/5786c620fee89fa2a0db4c8329f7d9cabf7ea81d#diff-fc8bd4c3f1ee495f89956160ebf3736c1b8f8021e61f3eb14662439f8a781aacR765-R791), [make_pyshp_fields()](https://github.com/mikeqfu/pydriosm/commit/5786c620fee89fa2a0db4c8329f7d9cabf7ea81d#diff-fc8bd4c3f1ee495f89956160ebf3736c1b8f8021e61f3eb14662439f8a781aacR794-R834) and [write_to_shapefile()](https://github.com/mikeqfu/pydriosm/commit/5786c620fee89fa2a0db4c8329f7d9cabf7ea81d#diff-fc8bd4c3f1ee495f89956160ebf3736c1b8f8021e61f3eb14662439f8a781aacR837-R917)
  - used [pyshp](https://pypi.org/project/pyshp/) as the default tool of reading/writing shapefiles; this replaced the previous dependency GeoPandas, which would not be required for installing PyDriosm but still reserved as an alternative option if already available
- in the module [ios](https://github.com/mikeqfu/pydriosm/blob/e5f8fe491cb0bf1f7c22e6e02851c78c288327e8/pydriosm/ios.py), let the class [PostgresOSM](https://github.com/mikeqfu/pydriosm/commit/90587bb0ab7bd26d3597481d463b280cdaf1a728#diff-c77b790ee115d5ffc02dec7d637d7d22d5e61747bc0e3c0cbc917810c8c4fb7bR126) inherit from [pyhelpers.sql.PostgreSQL](https://pyhelpers.readthedocs.io/en/latest/_generated/pyhelpers.sql.PostgreSQL.html) and modified the class with [bug fixes](https://github.com/mikeqfu/pydriosm/commit/90587bb0ab7bd26d3597481d463b280cdaf1a728)
- in the module [utils](https://github.com/mikeqfu/pydriosm/blob/e5f8fe491cb0bf1f7c22e6e02851c78c288327e8/pydriosm/utils.py),
  - removed the function [get_osm_geom_object_dict()](https://github.com/mikeqfu/pydriosm/blob/d7cb423ae30dc3443139fc6063ea3ce24ed7afd9/pydriosm/utils.py#L145-L167)
  - added functions [get_shp_shape_types_dict()](https://github.com/mikeqfu/pydriosm/commit/1a82b3d96383500898af13f6a49023f6c88f4c06#diff-262651b10b835e2d78c1c6d4157b36f97721b7a10a13f197715ee984266c3882R147-R172) and [get_shp_shape_types_geom_dict()](https://github.com/mikeqfu/pydriosm/commit/1a82b3d96383500898af13f6a49023f6c88f4c06#diff-262651b10b835e2d78c1c6d4157b36f97721b7a10a13f197715ee984266c3882R175-R192)
- modified default download directories
- updated the package data

**For more details, check out [PyDriosm 2.0.3 documentation](https://pydriosm.readthedocs.io/en/2.0.3/).**



#### [2.0.2](https://github.com/mikeqfu/pydriosm/releases/tag/2.0.2)

*24 November 2020*

##### Main [changes](https://github.com/mikeqfu/pydriosm/compare/2.0.1...2.0.2) since [v2.0.1](https://github.com/mikeqfu/pydriosm/tree/fde43179f0db724e5ff2fe69afba74f6d53d37c0):

- added a parameter '[max_tmpfile_size](https://github.com/mikeqfu/pydriosm/commit/3b4d8c3c58f40f4a405586594fa57524a8e825e8)' to the classes [GeofabrikDownloader](https://pydriosm.readthedocs.io/en/2.0.2/_generated/pydriosm.downloader.GeofabrikDownloader.html) and [BBBikeDownloader](https://pydriosm.readthedocs.io/en/2.0.2/_generated/pydriosm.downloader.BBBikeDownloader.html), to set the maximum size (which defaults to 100 MB) of in-memory temporary file while instantiating both the classes
- added a new function [validate_shp_layer_names()](https://pydriosm.readthedocs.io/en/2.0.2/_generated/pydriosm.utils.validate_shp_layer_names.html) to the module [utils](https://pydriosm.readthedocs.io/en/2.0.2/utils.html)
- optimised import statements for all modules

**For more details, check out [PyDriosm 2.0.2 documentation](https://pydriosm.readthedocs.io/en/2.0.2/).**



#### [2.0.1](https://github.com/mikeqfu/pydriosm/releases/tag/2.0.1)

*19 November 2020*

##### Main [changes](https://github.com/mikeqfu/pydriosm/compare/2.0.0...2.0.1) since [v2.0.0](https://github.com/mikeqfu/pydriosm/tree/941e9f5b45a0a356eba5a0281307f19807955357):

- optimised import statements for the modules [downloader](https://github.com/mikeqfu/pydriosm/commit/a4d000a9f0e435e283e15c0a0db45049335e286c) and [reader](https://github.com/mikeqfu/pydriosm/commit/09ff2fc65986105566ee923b96284a78f503b3ba)



#### [2.0.0](https://github.com/mikeqfu/pydriosm/releases/tag/2.0.0)

*19 November 2020*

This release introduces a brand new PyDriosm, which is a highly modified version of the predecessors tagged "1.0.x".

*Note that v2 is NOT compatible with the earlier versions labelled v1.*

##### Main [changes](https://github.com/mikeqfu/pydriosm/compare/1.0.20...2.0.0) since [v1.0.20](https://github.com/mikeqfu/pydriosm/tree/371dbce63886cf22f8484337ed5ced826acfcf05):

- featured with the following three new modules:
  - **[downloader](https://github.com/mikeqfu/pydriosm/blob/941e9f5b45a0a356eba5a0281307f19807955357/pydriosm/downloader.py)**, modified from the former [download_GeoFabrik](https://github.com/mikeqfu/pydriosm/blob/371dbce63886cf22f8484337ed5ced826acfcf05/pydriosm/download_GeoFabrik.py) and [download_BBBike](https://github.com/mikeqfu/pydriosm/blob/371dbce63886cf22f8484337ed5ced826acfcf05/pydriosm/download_BBBike.py), for downloading data
  - **[reader](https://github.com/mikeqfu/pydriosm/blob/941e9f5b45a0a356eba5a0281307f19807955357/pydriosm/reader.py)**, modified from the former [read_GeoFabrik](https://github.com/mikeqfu/pydriosm/blob/371dbce63886cf22f8484337ed5ced826acfcf05/pydriosm/read_GeoFabrik.py), for reading the data
  - **[ios](https://github.com/mikeqfu/pydriosm/blob/941e9f5b45a0a356eba5a0281307f19807955357/pydriosm/ios.py)**, modified from the former [osm_psql](https://github.com/mikeqfu/pydriosm/blob/371dbce63886cf22f8484337ed5ced826acfcf05/pydriosm/osm_psql.py) and [dump_GeoFabrik](https://github.com/mikeqfu/pydriosm/blob/371dbce63886cf22f8484337ed5ced826acfcf05/pydriosm/dump_GeoFabrik.py), for PostgreSQL-based I/O and storage of the data
- renamed the rest of the modules, fixed known bugs and added a number of new functions/classes
- created [PyDriosm documentation](https://readthedocs.org/projects/pydriosm/) hosted at [Read the Docs](https://readthedocs.org/).



#### [1.0.20](https://github.com/mikeqfu/pydriosm/releases/tag/1.0.20)

*27 January 2020*

*(Note that [v1.0.19](https://pypi.org/project/pydriosm/1.0.19/) was deprecated and removed from Releases on GitHub.)*

##### Main [changes](https://github.com/mikeqfu/pydriosm/compare/1.0.18...1.0.20) since [v1.0.18](https://github.com/mikeqfu/pydriosm/tree/6396d117a84d2bfe5b3e065e4b4bf29ff24c106b):

- modified the following class and functions with bug fixes: 
  - [OSM](https://github.com/mikeqfu/pydriosm/commit/68f1edfd77ab8a9cc78cccf5197b245edf91dd19) in the module [osm_psql](https://github.com/mikeqfu/pydriosm/blob/68f1edfd77ab8a9cc78cccf5197b245edf91dd19/pydriosm/osm_psql.py)
  - [regulate_input_subregion_name()](https://github.com/mikeqfu/pydriosm/commit/57511fdc6948b9eb86eb07b99f4b15e1f8161dc9) in [download_GeoFabrik](https://github.com/mikeqfu/pydriosm/blob/57511fdc6948b9eb86eb07b99f4b15e1f8161dc9/pydriosm/download_GeoFabrik.py)
  - [psql_osm_pbf_data_extracts()](https://github.com/mikeqfu/pydriosm/commit/f6b0ef15bde37dd9dc65864003cb36c49b671aec) in [dump_GeoFabrik](https://github.com/mikeqfu/pydriosm/blob/f6b0ef15bde37dd9dc65864003cb36c49b671aec/pydriosm/dump_GeoFabrik.py)
  - [parse_osm_pbf()](https://github.com/mikeqfu/pydriosm/commit/a3384eea4a628a7b2e75b19d5e9976e7172ece99#diff-c8b9e0cb8aea477d560c1f28ff9d49c58879751c45aea29eb89176cecb41ac0cL512-R602) and [read_osm_pbf()](https://github.com/mikeqfu/pydriosm/commit/a3384eea4a628a7b2e75b19d5e9976e7172ece99#diff-c8b9e0cb8aea477d560c1f28ff9d49c58879751c45aea29eb89176cecb41ac0cL607-R695) in the module [read_GeoFabrik](https://github.com/mikeqfu/pydriosm/blob/a3384eea4a628a7b2e75b19d5e9976e7172ece99/pydriosm/read_GeoFabrik.py)
- removed the function [split_list()](https://github.com/mikeqfu/pydriosm/commit/e3399e8ac602332aa15ddcfb23cece572906d7f4#diff-262651b10b835e2d78c1c6d4157b36f97721b7a10a13f197715ee984266c3882L111-L120) from the module [utils](https://github.com/mikeqfu/pydriosm/blob/e3399e8ac602332aa15ddcfb23cece572906d7f4/pydriosm/utils.py)
- updated the package data



#### [1.0.18](https://github.com/mikeqfu/pydriosm/releases/tag/1.0.18)

*9 January 2020*

##### Main [changes](https://github.com/mikeqfu/pydriosm/compare/1.0.17...1.0.18) since [v1.0.17](https://github.com/mikeqfu/pydriosm/tree/cc6504c11189a4ac6b42cec24b25cae079e3b715):

- modified the module [download_GeoFabrik](https://github.com/mikeqfu/pydriosm/commit/af47dfb667a721be97ec9ae5eac0000b4571876b#diff-a2d854a6efc7bb0057ad30f933a3cd9ac250a85d4ab74181644827157659939e), allowing it to download data of a deep or a shallow set of subregions
- modified the following functions with bug fixes: 
  - [get_subregion_table()](https://github.com/mikeqfu/pydriosm/commit/d3b559f4b14b768eb657d471357ba621b14356a1#diff-a2d854a6efc7bb0057ad30f933a3cd9ac250a85d4ab74181644827157659939eL59-R119) in the module [download_GeoFabrik](https://github.com/mikeqfu/pydriosm/blob/d3b559f4b14b768eb657d471357ba621b14356a1/pydriosm/download_GeoFabrik.py)
  - [find_osm_shp_file()](https://github.com/mikeqfu/pydriosm/commit/a2627d8ec1e816f5d349dd9ff272f29a1faa7f2e#diff-c8b9e0cb8aea477d560c1f28ff9d49c58879751c45aea29eb89176cecb41ac0cL24-R58), [merge_multi_shp()](https://github.com/mikeqfu/pydriosm/commit/a2627d8ec1e816f5d349dd9ff272f29a1faa7f2e#diff-c8b9e0cb8aea477d560c1f28ff9d49c58879751c45aea29eb89176cecb41ac0cL139-R246) and [parse_osm_pbf()](https://github.com/mikeqfu/pydriosm/commit/b33b6296ede78ebff0af4753007cc3e22b691835#diff-c8b9e0cb8aea477d560c1f28ff9d49c58879751c45aea29eb89176cecb41ac0cL511-R603) in the module [read_GeoFabrik](https://github.com/mikeqfu/pydriosm/blob/b33b6296ede78ebff0af4753007cc3e22b691835/pydriosm/read_GeoFabrik.py)
- integrated the function [collect_bbbike_subregion_download_catalogue()](https://github.com/mikeqfu/pydriosm/commit/92df65fdde05b554b732222942796eb9292e0677#diff-1adc77ee4baedd4f5bf14bb36545835023a25c9f5df660bb5fa33b1082c33688L94) into [collect_bbbike_download_catalogue()](https://github.com/mikeqfu/pydriosm/commit/92df65fdde05b554b732222942796eb9292e0677) in the module [download_BBBike](https://github.com/mikeqfu/pydriosm/blob/92df65fdde05b554b732222942796eb9292e0677/pydriosm/download_BBBike.py)
- added a new module [update](https://github.com/mikeqfu/pydriosm/commit/2f96a487e2fce263772853b5a50fe7037d443697)
- set up default parameters for PostgreSQL connection
- updated the package data
- tested the package in Python 3.8



#### [1.0.17](https://github.com/mikeqfu/pydriosm/releases/tag/1.0.17)

*29 November 2019*

##### Main [changes](https://github.com/mikeqfu/pydriosm/compare/1.0.16...1.0.17) since [v1.0.16](https://github.com/mikeqfu/pydriosm/tree/140d0cc85fc3d3346994d214821762465acc5aab):

- modified the following functions with bug fixes in the module [download_GeoFabrik](https://github.com/mikeqfu/pydriosm/blob/8c39e6be675f163221009b4e6c66c4db904c3ccf/pydriosm/download_GeoFabrik.py):
  - [collect_subregion_info_catalogue()](https://github.com/mikeqfu/pydriosm/commit/8c39e6be675f163221009b4e6c66c4db904c3ccf#diff-a2d854a6efc7bb0057ad30f933a3cd9ac250a85d4ab74181644827157659939eL126-R209)
  - [get_default_path_to_osm_file()](https://github.com/mikeqfu/pydriosm/commit/8c39e6be675f163221009b4e6c66c4db904c3ccf#diff-a2d854a6efc7bb0057ad30f933a3cd9ac250a85d4ab74181644827157659939eL455-R511)
- modified the following functions with bug fixes in the module [read_GeoFabrik](https://github.com/mikeqfu/pydriosm/blob/94d075441dfa6ace22eec6c7c24217a2fcc2343b/pydriosm/read_GeoFabrik.py)
  - [merge_multi_shp()](https://github.com/mikeqfu/pydriosm/commit/94d075441dfa6ace22eec6c7c24217a2fcc2343b#diff-c8b9e0cb8aea477d560c1f28ff9d49c58879751c45aea29eb89176cecb41ac0cL140-R218)
  - [read_shp_zip()](https://github.com/mikeqfu/pydriosm/commit/94d075441dfa6ace22eec6c7c24217a2fcc2343b#diff-c8b9e0cb8aea477d560c1f28ff9d49c58879751c45aea29eb89176cecb41ac0cL252-R359)
  - [read_osm_pbf()](https://github.com/mikeqfu/pydriosm/commit/94d075441dfa6ace22eec6c7c24217a2fcc2343b#diff-c8b9e0cb8aea477d560c1f28ff9d49c58879751c45aea29eb89176cecb41ac0cL559-R661)
- updated the package data



#### [1.0.16](https://github.com/mikeqfu/pydriosm/releases/tag/1.0.16)

*6 October 2019*

##### Main [changes](https://github.com/mikeqfu/pydriosm/compare/1.0.15...1.0.16) since [v1.0.15](https://github.com/mikeqfu/pydriosm/tree/c9faa653488036e43b332dc61a9e6614018f785f):

- fixed known bugs
- updated the package data



#### [1.0.15](https://github.com/mikeqfu/pydriosm/releases/tag/1.0.15)

*29 August 2019*

*(Note that [v1.0.14](https://pypi.org/project/pydriosm/1.0.14/), [v1.0.13](https://pypi.org/project/pydriosm/1.0.13/) and [v1.0.12](https://pypi.org/project/pydriosm/1.0.12/) were deprecated and removed from Releases on GitHub.)*

##### Main [changes](https://github.com/mikeqfu/pydriosm/compare/1.0.11...1.0.15) since [v1.0.11](https://github.com/mikeqfu/pydriosm/tree/42c47d60c1a30c37c80b9757fd4c32e60f053bd3):

- added a new method [.db_exists()](https://github.com/mikeqfu/pydriosm/commit/73ff3b2bee1d85947d86bf32421e90dcabb7d47d#diff-cb2783bddce6ef6c0d7479f7e4ada08bdcec39cb0e9d0af83a4d1398b5737491R72-R76) of the class [OSM](https://github.com/mikeqfu/pydriosm/blob/73ff3b2bee1d85947d86bf32421e90dcabb7d47d/pydriosm/osm_psql.py#L30); modified the method [.create_db()](https://github.com/mikeqfu/pydriosm/commit/73ff3b2bee1d85947d86bf32421e90dcabb7d47d#diff-cb2783bddce6ef6c0d7479f7e4ada08bdcec39cb0e9d0af83a4d1398b5737491L72-R96), allowing it to check if a database exists
- modified the following functions with bug fixes in the module [read_GeoFabrik](https://github.com/mikeqfu/pydriosm/blob/758bcbd4dc48a03b1bb72c161ba8e87f04a80a82/pydriosm/read_GeoFabrik.py): 
  - [extract_shp_zip()](https://github.com/mikeqfu/pydriosm/commit/758bcbd4dc48a03b1bb72c161ba8e87f04a80a82#diff-c8b9e0cb8aea477d560c1f28ff9d49c58879751c45aea29eb89176cecb41ac0cL74-R114)
  - [read_shp()](https://github.com/mikeqfu/pydriosm/commit/758bcbd4dc48a03b1bb72c161ba8e87f04a80a82#diff-c8b9e0cb8aea477d560c1f28ff9d49c58879751c45aea29eb89176cecb41ac0cL168-R214) 
  - [read_shp_zip()](https://github.com/mikeqfu/pydriosm/commit/758bcbd4dc48a03b1bb72c161ba8e87f04a80a82#diff-c8b9e0cb8aea477d560c1f28ff9d49c58879751c45aea29eb89176cecb41ac0cL193-R296)
- updated the [LICENSE](https://github.com/mikeqfu/pydriosm/commit/90d12a5aaa36882115e89e5e9f7672b9058f7cda)



#### [1.0.11](https://github.com/mikeqfu/pydriosm/releases/tag/1.0.11)

*4 April 2019*

*(Note that [v1.0.10](https://pypi.org/project/pydriosm/1.0.10/) and [v1.0.9](https://pypi.org/project/pydriosm/1.0.9/) were deprecated and removed from Releases on GitHub.)*

##### Main [changes](https://github.com/mikeqfu/pydriosm/compare/1.0.8...1.0.11) since [v1.0.8](https://github.com/mikeqfu/pydriosm/tree/305be3f0996be2aa3f5003c3f96b06466d769f50):

- added a parameter '[database_name](https://github.com/mikeqfu/pydriosm/commit/9846653bb2d08580b972a0dbf10c84b1e8bd9050)' that allows customised database name when dumping data to PostgreSQL
- added a function [regulate_table_name()](https://github.com/mikeqfu/pydriosm/commit/4cfdd7ebcb489b7b618f6c6163cad9354c071b77#diff-cb2783bddce6ef6c0d7479f7e4ada08bdcec39cb0e9d0af83a4d1398b5737491R17-R27) that regulates PostgreSQL table names
- removed duplicates from the list of the smallest subregions
- fixed [a minor bug](https://github.com/mikeqfu/pydriosm/commit/f2b22a5af3e7026c7c0810b1857550249c9fc61a) for creating a default data directory
- modified the following functions (with bug fixes):
  - [get_default_path_to_osm_file()](https://github.com/mikeqfu/pydriosm/commit/f2b22a5af3e7026c7c0810b1857550249c9fc61a) in the module [download_GeoFabrik](https://github.com/mikeqfu/pydriosm/blob/42c47d60c1a30c37c80b9757fd4c32e60f053bd3/pydriosm/download_GeoFabrik.py)
  - [parse_layer_data()](https://github.com/mikeqfu/pydriosm/commit/ec968392139282e8c66d7d0c477f9e6c5967e56c#diff-c8b9e0cb8aea477d560c1f28ff9d49c58879751c45aea29eb89176cecb41ac0cL297-R375) in the module [read_GeoFabrik](https://github.com/mikeqfu/pydriosm/blob/42c47d60c1a30c37c80b9757fd4c32e60f053bd3/pydriosm/read_GeoFabrik.py)
  - [dump_osm_pbf_data_by_layer()](https://github.com/mikeqfu/pydriosm/commit/ec968392139282e8c66d7d0c477f9e6c5967e56c#diff-cb2783bddce6ef6c0d7479f7e4ada08bdcec39cb0e9d0af83a4d1398b5737491L170-R179) in the module [osm_psql](https://github.com/mikeqfu/pydriosm/blob/42c47d60c1a30c37c80b9757fd4c32e60f053bd3/pydriosm/osm_psql.py)
  - [psql_osm_pbf_data_extracts()](https://github.com/mikeqfu/pydriosm/commit/ec968392139282e8c66d7d0c477f9e6c5967e56c#diff-06caa7c5b7806a98b9c915f4b9e44a9b7c305ead0c66e31baae94a58370c4615L68-R74) in the module [dump_GeoFabrik](https://github.com/mikeqfu/pydriosm/blob/42c47d60c1a30c37c80b9757fd4c32e60f053bd3/pydriosm/dump_GeoFabrik.py)



#### [1.0.8](https://github.com/mikeqfu/pydriosm/releases/tag/1.0.8)

*18 Mar 2019*

*(Note that [v1.0.6](https://pypi.org/project/pydriosm/1.0.6/) and [v1.0.7](https://pypi.org/project/pydriosm/1.0.7/) have been removed from Releases on GitHub.)*

##### Main [changes](https://github.com/mikeqfu/pydriosm/compare/1.0.5...1.0.8) since [v1.0.5](https://github.com/mikeqfu/pydriosm/tree/9b37bbe76223332b037f12a8fa49d1fdb24c7262):

- Fixed minor bugs in the following functions:
  - [parse_layer_data()](https://github.com/mikeqfu/pydriosm/commit/d266c3e49cf8a0d4e1065e60c5e3a6a657ff9332)
  - [psql_subregion_osm_data_extracts()](https://github.com/mikeqfu/pydriosm/commit/f6fada22e192a56bd2d6fc250bdaedf9f6d00041)
  - [read_shp_zip()](https://github.com/mikeqfu/pydriosm/commit/613f0a9fb3c70db9094590e9f614f254000369ce)
  - [retrieve_subregions()](https://github.com/mikeqfu/pydriosm/commit/bfbbbb4fc71108845df8fc1eae5d590a7b693d92)
- added [regulate_input_data_dir()](https://github.com/mikeqfu/pydriosm/commit/93792ec3493d0b13237cf24c531353f0e77d8f67)
- made major changes to functions and fixed a few potential [bugs](https://github.com/mikeqfu/pydriosm/commit/a415ed5d8b6394342a9ac9fb53bb041a3133fa44)



#### [1.0.5](https://github.com/mikeqfu/pydriosm/releases/tag/1.0.5)

*11 March 2019*

*(Note that [v1.0.4](https://pypi.org/project/pydriosm/1.0.4/), [v1.0.3](https://pypi.org/project/pydriosm/1.0.3/), [v1.0.2](https://pypi.org/project/pydriosm/1.0.2/) and [v1.0.1](https://pypi.org/project/pydriosm/1.0.1/) were deprecated and removed from Releases on GitHub.)*

##### Main [changes](https://github.com/mikeqfu/pydriosm/compare/1.0.0...1.0.5) since [v1.0.0](https://github.com/mikeqfu/pydriosm/tree/5dfa679abc6645570752d5332acd8e9dd467df53):

- added a parameter 'chunk_size' to the function [dump_osm_pbf_data()](https://github.com/mikeqfu/pydriosm/commit/cd209d985a3270b90d22501fdc5e3a8e8b142ac4#diff-cb2783bddce6ef6c0d7479f7e4ada08bdcec39cb0e9d0af83a4d1398b5737491L173-R204) in the module [osm_psql](https://github.com/mikeqfu/pydriosm/blob/cd209d985a3270b90d22501fdc5e3a8e8b142ac4/pydriosm/osm_psql.py), which allows users to parse/read/dump data in a chunk-wise way
- in the module [dump_GeoFabrik](https://github.com/mikeqfu/pydriosm/blob/4558a89938fa6f28ab105a6ee5d54a95745302e2/pydriosm/dump_GeoFabrik.py):
  - added a new function [retrieve_subregions()](https://github.com/mikeqfu/pydriosm/commit/4558a89938fa6f28ab105a6ee5d54a95745302e2#diff-06caa7c5b7806a98b9c915f4b9e44a9b7c305ead0c66e31baae94a58370c4615R19-R40), which retrieves a list of subregions of a given region name from the 'region-subregion index'
  - added a '[sleeping time](https://github.com/mikeqfu/pydriosm/commit/9b37bbe76223332b037f12a8fa49d1fdb24c7262)' to the function [psql_subregion_osm_data_extracts()](https://github.com/mikeqfu/pydriosm/blob/9b37bbe76223332b037f12a8fa49d1fdb24c7262/pydriosm/dump_GeoFabrik.py#L45-L152)
- integrated the function [read_parsed_osm_pbf()](https://github.com/mikeqfu/pydriosm/blob/243788f02c10fa91024b165819b52e6973fa3b26/pydriosm/read_GeoFabrik.py#L474-L515) into [read_osm_pbf()](https://github.com/mikeqfu/pydriosm/blob/243788f02c10fa91024b165819b52e6973fa3b26/pydriosm/read_GeoFabrik.py#L319-L391) in the module [read_GeoFabrik](https://github.com/mikeqfu/pydriosm/blob/a1fb4ddce3f451e29f79fc1e06b999ab9e4eb0b2/pydriosm/read_GeoFabrik.py)
- modified the function [gdal_configurations()](https://github.com/mikeqfu/pydriosm/commit/d85af9a3a37cbb8ffb2280090844dc61bde706f2) in the module [settings](https://github.com/mikeqfu/pydriosm/blob/d85af9a3a37cbb8ffb2280090844dc61bde706f2/pydriosm/settings.py)
- added a new function [split_list()](https://github.com/mikeqfu/pydriosm/commit/243788f02c10fa91024b165819b52e6973fa3b26#diff-262651b10b835e2d78c1c6d4157b36f97721b7a10a13f197715ee984266c3882R242-R249) to the module [utils](https://github.com/mikeqfu/pydriosm/blob/243788f02c10fa91024b165819b52e6973fa3b26/pydriosm/utils.py)



#### [1.0.0](https://github.com/mikeqfu/pydriosm/releases/tag/1.0.0)

*4 March 2019*

**Initial release.**



The earlier versions up to v0.2.9 have been deprecated.