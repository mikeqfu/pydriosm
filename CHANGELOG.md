### Changelog / Release notes

<br/>

#### **[2.1.1](https://github.com/mikeqfu/pydriosm/releases/tag/2.1.1)**

(*9 January 2022*)

##### **Notable [changes](https://github.com/mikeqfu/pydriosm/compare/2.1.0...2.1.1) since [2.1.0](https://pypi.org/project/pydriosm/2.1.0/):**

- Improved the following methods/modules (with bug fixes): 
  - the methods [.write_to_shapefile()](https://github.com/mikeqfu/pydriosm/commit/57baec84a3d8366f6d8f6f324fbcbdf6e7f67fa6), [.read_layer_shps()](https://github.com/mikeqfu/pydriosm/commit/bec76cb0fc21b152849cbc8cccb2634b04dd59f8#diff-fc8bd4c3f1ee495f89956160ebf3736c1b8f8021e61f3eb14662439f8a781aacL1795-R2028), and [.merge_layer_shps()](https://github.com/mikeqfu/pydriosm/commit/bec76cb0fc21b152849cbc8cccb2634b04dd59f8#diff-fc8bd4c3f1ee495f89956160ebf3736c1b8f8021e61f3eb14662439f8a781aacR2105-R2343) of the class [SHPReadParse](https://github.com/mikeqfu/pydriosm/blob/7d2aa13c30c9df324a431567da69c7813e706c94/pydriosm/reader.py#L1030);  
  - the modules [downloader](https://github.com/mikeqfu/pydriosm/commit/3404a8ad46b03e921110e695005bd47510c8a4f2#diff-5b569a7b9029a0d3c195aacccacf61b1f151777568a288bbd8703a88f67fc2f3) and [_updater](https://github.com/mikeqfu/pydriosm/commit/3404a8ad46b03e921110e695005bd47510c8a4f2#diff-3464d30b2db28f204143ad7f953d55614ece799bc0ae918cc0ad42c6497b39cf). 

**For more information and detailed specifications, check out [PyDriosm 2.1.1 documentation](https://pydriosm.readthedocs.io/en/2.1.1/).**

<br/>

#### **[2.1.0](https://github.com/mikeqfu/pydriosm/releases/tag/2.1.0)**

(*20 November 2022*)

***Note that this release is a highly modified version and not compatible with any previous versions.***

##### **Notable [changes](https://github.com/mikeqfu/pydriosm/compare/2.0.3...2.1.0) since [2.0.3](https://pypi.org/project/pydriosm/2.0.3/):**

- Made major modifications and sweeping changes to the modules: [downloader](https://github.com/mikeqfu/pydriosm/commit/2761bc7f3cf265ca9621dc10f46ef6dcbcedf263), [reader](https://github.com/mikeqfu/pydriosm/commit/2e4befe4ea7847cba889aa4f983355db717e59e4), [ios](https://github.com/mikeqfu/pydriosm/commit/e508b11cf121d25356a02975481c4aaabf4ada56) and [utils](https://github.com/mikeqfu/pydriosm/commit/c69fe4f5a863eda4f925904afdf2daa2b6390c60).
- Removed the module [settings](https://github.com/mikeqfu/pydriosm/commit/2916dc938a5890b0a19cd4431fd00f9292c7ec65).
- Replaced the module [updater](https://github.com/mikeqfu/pydriosm/commit/ab6ec0ec4689bc719716ba36f9259834bb269a94) with [_updater](https://github.com/mikeqfu/pydriosm/commit/159ba27ff3410ff53ca4210409da02d03cdc2b7e).
- Added a new module [errors](https://github.com/mikeqfu/pydriosm/commit/d9f60388bd085c375873bfc2f8cc395a6f111de3).

**For more information and detailed specifications, check out [PyDriosm 2.1.0 documentation](https://pydriosm.readthedocs.io/en/2.1.0/).**

<br/>

#### **[2.0.3](https://github.com/mikeqfu/pydriosm/releases/tag/2.0.3)**

(*25 April 2021*)

##### **Notable [changes](https://github.com/mikeqfu/pydriosm/compare/2.0.2...2.0.3) since [2.0.2](https://pypi.org/project/pydriosm/2.0.2/):**

- Renamed the function [~~get_default_shp_crs()~~](https://github.com/mikeqfu/pydriosm/commit/5786c620fee89fa2a0db4c8329f7d9cabf7ea81d#diff-fc8bd4c3f1ee495f89956160ebf3736c1b8f8021e61f3eb14662439f8a781aacL694) to [get_epsg4326_wgs84_crs_ref()](https://github.com/mikeqfu/pydriosm/commit/5786c620fee89fa2a0db4c8329f7d9cabf7ea81d#diff-fc8bd4c3f1ee495f89956160ebf3736c1b8f8021e61f3eb14662439f8a781aacR733) in the module [reader](https://github.com/mikeqfu/pydriosm/blob/924f943de08a03595b3604f71591a0c34952a54e/pydriosm/reader.py).
- Removed the function [get_osm_geom_object_dict()](https://github.com/mikeqfu/pydriosm/blob/d7cb423ae30dc3443139fc6063ea3ce24ed7afd9/pydriosm/utils.py#L145-L167) from the module [utils](https://github.com/mikeqfu/pydriosm/blob/924f943de08a03595b3604f71591a0c34952a54e/pydriosm/utils.py)
- Changed the default package for reading/writing shapefiles from [GeoPandas](https://pypi.org/project/geopandas/) to [PyShp](https://pypi.org/project/pyshp/) (Note that [GeoPandas](https://pypi.org/project/geopandas/) would not be required for installing [PyDriosm 2.0.3](https://pypi.org/project/pydriosm/2.0.3/)+ but would still be reserved as an alternative option if available.
- Modified the default download directories.
- Improved the class [PostgresOSM](https://github.com/mikeqfu/pydriosm/commit/90587bb0ab7bd26d3597481d463b280cdaf1a728) in the module [ios](https://github.com/mikeqfu/pydriosm/blob/924f943de08a03595b3604f71591a0c34952a54e/pydriosm/ios.py) and the module [downloader](https://github.com/mikeqfu/pydriosm/commit/52f76723a84cd822fc002f89bf92a744cbd88141) with bug fixes. 
- Added the following new functions:
  - [get_epsg4326_wgs84_prj_ref()](https://github.com/mikeqfu/pydriosm/commit/5786c620fee89fa2a0db4c8329f7d9cabf7ea81d#diff-fc8bd4c3f1ee495f89956160ebf3736c1b8f8021e61f3eb14662439f8a781aacR765-R791), [specify_pyshp_fields()](https://github.com/mikeqfu/pydriosm/commit/5786c620fee89fa2a0db4c8329f7d9cabf7ea81d#diff-fc8bd4c3f1ee495f89956160ebf3736c1b8f8021e61f3eb14662439f8a781aacR794-R834) and [write_to_shapefile()](https://github.com/mikeqfu/pydriosm/commit/5786c620fee89fa2a0db4c8329f7d9cabf7ea81d#diff-fc8bd4c3f1ee495f89956160ebf3736c1b8f8021e61f3eb14662439f8a781aacR837-R917) to the module [reader](https://github.com/mikeqfu/pydriosm/blob/924f943de08a03595b3604f71591a0c34952a54e/pydriosm/reader.py);
  - [shp_shape_types_dict()](https://github.com/mikeqfu/pydriosm/commit/1a82b3d96383500898af13f6a49023f6c88f4c06#diff-262651b10b835e2d78c1c6d4157b36f97721b7a10a13f197715ee984266c3882R147-R172) and [shp_shape_types_geom_dict()](https://github.com/mikeqfu/pydriosm/commit/1a82b3d96383500898af13f6a49023f6c88f4c06#diff-262651b10b835e2d78c1c6d4157b36f97721b7a10a13f197715ee984266c3882R175-R192) to the module [utils](https://github.com/mikeqfu/pydriosm/blob/924f943de08a03595b3604f71591a0c34952a54e/pydriosm/utils.py).

**For more information and detailed specifications, check out [PyDriosm 2.0.3 documentation](https://pydriosm.readthedocs.io/en/2.0.3/).**

<br/>

#### **[2.0.2](https://github.com/mikeqfu/pydriosm/releases/tag/2.0.2)**

(*24 November 2020*)

##### **Notable [changes](https://github.com/mikeqfu/pydriosm/compare/2.0.1...2.0.2) since [2.0.1](https://pypi.org/project/pydriosm/2.0.1/):**

- Added [a new parameter](https://github.com/mikeqfu/pydriosm/commit/3b4d8c3c58f40f4a405586594fa57524a8e825e8) `max_tmpfile_size` for setting the maximum size of in-memory temporary file while instantiating the classes [GeofabrikReader](https://github.com/mikeqfu/pydriosm/commit/3b4d8c3c58f40f4a405586594fa57524a8e825e8#diff-fc8bd4c3f1ee495f89956160ebf3736c1b8f8021e61f3eb14662439f8a781aacR1259) and [BBBikeReader](https://github.com/mikeqfu/pydriosm/commit/3b4d8c3c58f40f4a405586594fa57524a8e825e8#diff-fc8bd4c3f1ee495f89956160ebf3736c1b8f8021e61f3eb14662439f8a781aacR2123) for reading OSM data.
- Added a new function [validate_shp_layer_names()](https://pydriosm.readthedocs.io/en/2.0.2/_generated/pydriosm.utils.validate_shp_layer_names.html) to the module [utils](https://pydriosm.readthedocs.io/en/2.0.2/utils.html).
- Optimized import statements for all modules.

**For more information and detailed specifications, check out [PyDriosm 2.0.2 documentation](https://pydriosm.readthedocs.io/en/2.0.2/).**

<br/>

#### **[2.0.1](https://github.com/mikeqfu/pydriosm/releases/tag/2.0.1)**

(*19 November 2020*)

##### **Notable [changes](https://github.com/mikeqfu/pydriosm/compare/2.0.0...2.0.1) since [2.0.0](https://pypi.org/project/pydriosm/2.0.0/):**

- Optimized import statements for the modules [downloader](https://github.com/mikeqfu/pydriosm/commit/a4d000a9f0e435e283e15c0a0db45049335e286c) and [reader](https://github.com/mikeqfu/pydriosm/commit/09ff2fc65986105566ee923b96284a78f503b3ba).

<br/>

#### **[2.0.0](https://github.com/mikeqfu/pydriosm/releases/tag/2.0.0)**

(*19 November 2020*)

This release introduces a highly modified version of the predecessors tagged "1.0.x". Note that this new version is not compatible with any previous versions.

##### **Notable [changes](https://github.com/mikeqfu/pydriosm/compare/1.0.20...2.0.0) since [1.0.20](https://pypi.org/project/pydriosm/1.0.20/):**

- Featured with the following three new modules:
  - [**downloader**](https://github.com/mikeqfu/pydriosm/blob/941e9f5b45a0a356eba5a0281307f19807955357/pydriosm/downloader.py), modified from the former [download_GeoFabrik](https://github.com/mikeqfu/pydriosm/blob/371dbce63886cf22f8484337ed5ced826acfcf05/pydriosm/download_GeoFabrik.py) and [download_BBBike](https://github.com/mikeqfu/pydriosm/blob/371dbce63886cf22f8484337ed5ced826acfcf05/pydriosm/download_BBBike.py), for downloading data;
  - [**reader**](https://github.com/mikeqfu/pydriosm/blob/941e9f5b45a0a356eba5a0281307f19807955357/pydriosm/reader.py), modified from the former [read_GeoFabrik](https://github.com/mikeqfu/pydriosm/blob/371dbce63886cf22f8484337ed5ced826acfcf05/pydriosm/read_GeoFabrik.py), for reading the data;
  - [**ios**](https://github.com/mikeqfu/pydriosm/blob/941e9f5b45a0a356eba5a0281307f19807955357/pydriosm/ios.py), modified from the former [osm_psql](https://github.com/mikeqfu/pydriosm/blob/371dbce63886cf22f8484337ed5ced826acfcf05/pydriosm/osm_psql.py) and [dump_GeoFabrik](https://github.com/mikeqfu/pydriosm/blob/371dbce63886cf22f8484337ed5ced826acfcf05/pydriosm/dump_GeoFabrik.py), for PostgreSQL-based I/O and storage of the data.
- Renamed the rest of the modules, fixed known bugs and added a number of new functions/classes.

<br/>

#### **[1.0.20](https://github.com/mikeqfu/pydriosm/releases/tag/1.0.20)**

(*27 January 2020*)

*Note that [1.0.19](https://pypi.org/project/pydriosm/1.0.19/) had been removed from [GitHub Releases](https://github.com/mikeqfu/pydriosm/releases).*

##### **Notable [changes](https://github.com/mikeqfu/pydriosm/compare/1.0.18...1.0.20) since [1.0.18](https://pypi.org/project/pydriosm/1.0.18/):**

- Removed the function [split_list()](https://github.com/mikeqfu/pydriosm/commit/e3399e8ac602332aa15ddcfb23cece572906d7f4#diff-262651b10b835e2d78c1c6d4157b36f97721b7a10a13f197715ee984266c3882L111-L120) from the module [utils](https://github.com/mikeqfu/pydriosm/blob/e3399e8ac602332aa15ddcfb23cece572906d7f4/pydriosm/utils.py).
- Improved the following class and functions with bug fixes: 
  - [OSM](https://github.com/mikeqfu/pydriosm/commit/68f1edfd77ab8a9cc78cccf5197b245edf91dd19) in the module [osm_psql](https://github.com/mikeqfu/pydriosm/blob/68f1edfd77ab8a9cc78cccf5197b245edf91dd19/pydriosm/osm_psql.py);
  - [regulate_input_subregion_name()](https://github.com/mikeqfu/pydriosm/commit/57511fdc6948b9eb86eb07b99f4b15e1f8161dc9) in [download_GeoFabrik](https://github.com/mikeqfu/pydriosm/blob/57511fdc6948b9eb86eb07b99f4b15e1f8161dc9/pydriosm/download_GeoFabrik.py);
  - [read_pbf()](https://github.com/mikeqfu/pydriosm/commit/a3384eea4a628a7b2e75b19d5e9976e7172ece99#diff-c8b9e0cb8aea477d560c1f28ff9d49c58879751c45aea29eb89176cecb41ac0cL512-R602) and [read_pbf()](https://github.com/mikeqfu/pydriosm/commit/a3384eea4a628a7b2e75b19d5e9976e7172ece99#diff-c8b9e0cb8aea477d560c1f28ff9d49c58879751c45aea29eb89176cecb41ac0cL607-R695) in the module [read_GeoFabrik](https://github.com/mikeqfu/pydriosm/blob/a3384eea4a628a7b2e75b19d5e9976e7172ece99/pydriosm/read_GeoFabrik.py);
  - [psql_osm_pbf_data_extracts()](https://github.com/mikeqfu/pydriosm/commit/f6b0ef15bde37dd9dc65864003cb36c49b671aec) in [dump_GeoFabrik](https://github.com/mikeqfu/pydriosm/blob/f6b0ef15bde37dd9dc65864003cb36c49b671aec/pydriosm/dump_GeoFabrik.py).

<br/>

#### **[1.0.18](https://github.com/mikeqfu/pydriosm/releases/tag/1.0.18)**

(*9 January 2020*)

##### **Notable [changes](https://github.com/mikeqfu/pydriosm/compare/1.0.17...1.0.18) since [1.0.17](https://pypi.org/project/pydriosm/1.0.17/):**

- Integrated the function [collect_bbbike_subregion_download_catalogue()](https://github.com/mikeqfu/pydriosm/commit/92df65fdde05b554b732222942796eb9292e0677#diff-1adc77ee4baedd4f5bf14bb36545835023a25c9f5df660bb5fa33b1082c33688L94) into [collect_bbbike_download_catalogue()](https://github.com/mikeqfu/pydriosm/commit/92df65fdde05b554b732222942796eb9292e0677) in the module [download_BBBike](https://github.com/mikeqfu/pydriosm/blob/92df65fdde05b554b732222942796eb9292e0677/pydriosm/download_BBBike.py).
- Modified the module [download_GeoFabrik](https://github.com/mikeqfu/pydriosm/commit/af47dfb667a721be97ec9ae5eac0000b4571876b#diff-a2d854a6efc7bb0057ad30f933a3cd9ac250a85d4ab74181644827157659939e), allowing it to download data of a deep or shallow set of subregions.
- Improved the following functions with bug fixes: 
  - [get_subregion_table()](https://github.com/mikeqfu/pydriosm/commit/d3b559f4b14b768eb657d471357ba621b14356a1#diff-a2d854a6efc7bb0057ad30f933a3cd9ac250a85d4ab74181644827157659939eL59-R119) in the module [download_GeoFabrik](https://github.com/mikeqfu/pydriosm/blob/d3b559f4b14b768eb657d471357ba621b14356a1/pydriosm/download_GeoFabrik.py)
  - [find_osm_shp_file()](https://github.com/mikeqfu/pydriosm/commit/a2627d8ec1e816f5d349dd9ff272f29a1faa7f2e#diff-c8b9e0cb8aea477d560c1f28ff9d49c58879751c45aea29eb89176cecb41ac0cL24-R58), [merge_multi_shp()](https://github.com/mikeqfu/pydriosm/commit/a2627d8ec1e816f5d349dd9ff272f29a1faa7f2e#diff-c8b9e0cb8aea477d560c1f28ff9d49c58879751c45aea29eb89176cecb41ac0cL139-R246) and [read_pbf()](https://github.com/mikeqfu/pydriosm/commit/b33b6296ede78ebff0af4753007cc3e22b691835#diff-c8b9e0cb8aea477d560c1f28ff9d49c58879751c45aea29eb89176cecb41ac0cL511-R603) in the module [read_GeoFabrik](https://github.com/mikeqfu/pydriosm/blob/b33b6296ede78ebff0af4753007cc3e22b691835/pydriosm/read_GeoFabrik.py)
- Added a new module [update](https://github.com/mikeqfu/pydriosm/commit/2f96a487e2fce263772853b5a50fe7037d443697).
- Added default parameters for PostgreSQL database connection.

<br/>

#### **[1.0.17](https://github.com/mikeqfu/pydriosm/releases/tag/1.0.17)**

(*29 November 2019*)

##### **Notable [changes](https://github.com/mikeqfu/pydriosm/compare/1.0.16...1.0.17) since [1.0.16](https://pypi.org/project/pydriosm/1.0.16/):**

- Improved the following functions with bug fixes:
  - [collect_subregion_info_catalogue()](https://github.com/mikeqfu/pydriosm/commit/8c39e6be675f163221009b4e6c66c4db904c3ccf#diff-a2d854a6efc7bb0057ad30f933a3cd9ac250a85d4ab74181644827157659939eL126-R209) and [get_default_pathname()](https://github.com/mikeqfu/pydriosm/commit/8c39e6be675f163221009b4e6c66c4db904c3ccf#diff-a2d854a6efc7bb0057ad30f933a3cd9ac250a85d4ab74181644827157659939eL455-R511) in the module [download_GeoFabrik](https://github.com/mikeqfu/pydriosm/blob/8c39e6be675f163221009b4e6c66c4db904c3ccf/pydriosm/download_GeoFabrik.py);
  - [merge_multi_shp()](https://github.com/mikeqfu/pydriosm/commit/94d075441dfa6ace22eec6c7c24217a2fcc2343b#diff-c8b9e0cb8aea477d560c1f28ff9d49c58879751c45aea29eb89176cecb41ac0cL140-R218), [read_shp_zip()](https://github.com/mikeqfu/pydriosm/commit/94d075441dfa6ace22eec6c7c24217a2fcc2343b#diff-c8b9e0cb8aea477d560c1f28ff9d49c58879751c45aea29eb89176cecb41ac0cL252-R359) and [read_pbf()](https://github.com/mikeqfu/pydriosm/commit/94d075441dfa6ace22eec6c7c24217a2fcc2343b#diff-c8b9e0cb8aea477d560c1f28ff9d49c58879751c45aea29eb89176cecb41ac0cL559-R661) in the module [read_GeoFabrik](https://github.com/mikeqfu/pydriosm/blob/94d075441dfa6ace22eec6c7c24217a2fcc2343b/pydriosm/read_GeoFabrik.py).

<br/>

#### **[1.0.16](https://github.com/mikeqfu/pydriosm/releases/tag/1.0.16)**

(*6 October 2019*)

##### **Notable [changes](https://github.com/mikeqfu/pydriosm/compare/1.0.15...1.0.16) since [1.0.15](https://pypi.org/project/pydriosm/1.0.15/):**

- Fixed some known bugs.

<br/>

#### **[1.0.15](https://github.com/mikeqfu/pydriosm/releases/tag/1.0.15)**

(*29 August 2019*)

*Note that [1.0.14](https://pypi.org/project/pydriosm/1.0.14/), [1.0.13](https://pypi.org/project/pydriosm/1.0.13/) and [1.0.12](https://pypi.org/project/pydriosm/1.0.12/) had been removed from [GitHub Releases](https://github.com/mikeqfu/pydriosm/releases).*

##### **Notable [changes](https://github.com/mikeqfu/pydriosm/compare/1.0.11...1.0.15) since [1.0.11](https://pypi.org/project/pydriosm/1.0.11/):**

- Improved the functions: [extract_shp_zip()](https://github.com/mikeqfu/pydriosm/commit/758bcbd4dc48a03b1bb72c161ba8e87f04a80a82#diff-c8b9e0cb8aea477d560c1f28ff9d49c58879751c45aea29eb89176cecb41ac0cL74-R114), [read_shp()](https://github.com/mikeqfu/pydriosm/commit/758bcbd4dc48a03b1bb72c161ba8e87f04a80a82#diff-c8b9e0cb8aea477d560c1f28ff9d49c58879751c45aea29eb89176cecb41ac0cL168-R214) and [read_shp_zip()](https://github.com/mikeqfu/pydriosm/commit/758bcbd4dc48a03b1bb72c161ba8e87f04a80a82#diff-c8b9e0cb8aea477d560c1f28ff9d49c58879751c45aea29eb89176cecb41ac0cL193-R296) with bug fixes in the module [read_GeoFabrik](https://github.com/mikeqfu/pydriosm/blob/758bcbd4dc48a03b1bb72c161ba8e87f04a80a82/pydriosm/read_GeoFabrik.py).
- Added a new method [OSM.db_exists()](https://github.com/mikeqfu/pydriosm/commit/73ff3b2bee1d85947d86bf32421e90dcabb7d47d#diff-cb2783bddce6ef6c0d7479f7e4ada08bdcec39cb0e9d0af83a4d1398b5737491R72-R76), allowing [OSM.create_db()](https://github.com/mikeqfu/pydriosm/commit/73ff3b2bee1d85947d86bf32421e90dcabb7d47d#diff-cb2783bddce6ef6c0d7479f7e4ada08bdcec39cb0e9d0af83a4d1398b5737491L72-R96) to check whether a database exists.
- Updated the [LICENSE](https://github.com/mikeqfu/pydriosm/commit/90d12a5aaa36882115e89e5e9f7672b9058f7cda).

<br/>

#### **[1.0.11](https://github.com/mikeqfu/pydriosm/releases/tag/1.0.11)**

(*4 April 2019*)

*Note that [1.0.10](https://pypi.org/project/pydriosm/1.0.10/) and [1.0.9](https://pypi.org/project/pydriosm/1.0.9/) had been removed from [GitHub Releases](https://github.com/mikeqfu/pydriosm/releases).*

##### **Notable [changes](https://github.com/mikeqfu/pydriosm/compare/1.0.8...1.0.11) since [1.0.8](https://pypi.org/project/pydriosm/1.0.8/):**

- Fixed [a minor bug](https://github.com/mikeqfu/pydriosm/commit/f2b22a5af3e7026c7c0810b1857550249c9fc61a) for creating a default data directory.
- Improved the following functions (with bug fixes):
  - [get_default_pathname()](https://github.com/mikeqfu/pydriosm/commit/f2b22a5af3e7026c7c0810b1857550249c9fc61a) in the module [download_GeoFabrik](https://github.com/mikeqfu/pydriosm/blob/42c47d60c1a30c37c80b9757fd4c32e60f053bd3/pydriosm/download_GeoFabrik.py);
  - [parse_layer_data()](https://github.com/mikeqfu/pydriosm/commit/ec968392139282e8c66d7d0c477f9e6c5967e56c#diff-c8b9e0cb8aea477d560c1f28ff9d49c58879751c45aea29eb89176cecb41ac0cL297-R375) in the module [read_GeoFabrik](https://github.com/mikeqfu/pydriosm/blob/42c47d60c1a30c37c80b9757fd4c32e60f053bd3/pydriosm/read_GeoFabrik.py);
  - [dump_osm_pbf_data_by_layer()](https://github.com/mikeqfu/pydriosm/commit/ec968392139282e8c66d7d0c477f9e6c5967e56c#diff-cb2783bddce6ef6c0d7479f7e4ada08bdcec39cb0e9d0af83a4d1398b5737491L170-R179) in the module [osm_psql](https://github.com/mikeqfu/pydriosm/blob/42c47d60c1a30c37c80b9757fd4c32e60f053bd3/pydriosm/osm_psql.py);
  - [psql_osm_pbf_data_extracts()](https://github.com/mikeqfu/pydriosm/commit/ec968392139282e8c66d7d0c477f9e6c5967e56c#diff-06caa7c5b7806a98b9c915f4b9e44a9b7c305ead0c66e31baae94a58370c4615L68-R74) in the module [dump_GeoFabrik](https://github.com/mikeqfu/pydriosm/blob/42c47d60c1a30c37c80b9757fd4c32e60f053bd3/pydriosm/dump_GeoFabrik.py), [with a new parameter](https://github.com/mikeqfu/pydriosm/commit/9846653bb2d08580b972a0dbf10c84b1e8bd9050) `database_name` for specifying a database name when dumping data to a PostgreSQL server.
- Added a function [regulate_table_name()](https://github.com/mikeqfu/pydriosm/commit/4cfdd7ebcb489b7b618f6c6163cad9354c071b77#diff-cb2783bddce6ef6c0d7479f7e4ada08bdcec39cb0e9d0af83a4d1398b5737491R17-R27), which regulates PostgreSQL table names, to the module [osm_psql](https://github.com/mikeqfu/pydriosm/blob/305be3f0996be2aa3f5003c3f96b06466d769f50/pydriosm/osm_psql.py).

<br/>

#### **[1.0.8](https://github.com/mikeqfu/pydriosm/releases/tag/1.0.8)**

(*18 Mar 2019*)

*Note that [1.0.6](https://pypi.org/project/pydriosm/1.0.6/) and [1.0.7](https://pypi.org/project/pydriosm/1.0.7/) had been removed from [GitHub Releases](https://github.com/mikeqfu/pydriosm/releases).*

##### **Notable [changes](https://github.com/mikeqfu/pydriosm/compare/1.0.5...1.0.8) since [1.0.5](https://pypi.org/project/pydriosm/1.0.5/):**

- Made [some major changes](https://github.com/mikeqfu/pydriosm/commit/a415ed5d8b6394342a9ac9fb53bb041a3133fa44) (with potential bug fixes).
- Fixed minor bugs in the following functions:
  - [parse_layer_data()](https://github.com/mikeqfu/pydriosm/commit/d266c3e49cf8a0d4e1065e60c5e3a6a657ff9332) and [read_shp_zip()](https://github.com/mikeqfu/pydriosm/commit/613f0a9fb3c70db9094590e9f614f254000369ce) in the module [read_GeoFabrik](https://github.com/mikeqfu/pydriosm/blob/305be3f0996be2aa3f5003c3f96b06466d769f50/pydriosm/read_GeoFabrik.py);
  - [retrieve_subregions()](https://github.com/mikeqfu/pydriosm/commit/bfbbbb4fc71108845df8fc1eae5d590a7b693d92) and [psql_subregion_osm_data_extracts()](https://github.com/mikeqfu/pydriosm/commit/f6fada22e192a56bd2d6fc250bdaedf9f6d00041) in the module [dump_GeoFabrik](https://github.com/mikeqfu/pydriosm/blob/305be3f0996be2aa3f5003c3f96b06466d769f50/pydriosm/dump_GeoFabrik.py).
- Added a function [regulate_input_data_dir()](https://github.com/mikeqfu/pydriosm/commit/93792ec3493d0b13237cf24c531353f0e77d8f67) to the module [utils](https://github.com/mikeqfu/pydriosm/blob/305be3f0996be2aa3f5003c3f96b06466d769f50/pydriosm/utils.py).

<br/>

#### **[1.0.5](https://github.com/mikeqfu/pydriosm/releases/tag/1.0.5)**

(*11 March 2019*)

*Note that [1.0.4](https://pypi.org/project/pydriosm/1.0.4/), [1.0.3](https://pypi.org/project/pydriosm/1.0.3/), [1.0.2](https://pypi.org/project/pydriosm/1.0.2/) and [1.0.1](https://pypi.org/project/pydriosm/1.0.1/) had been removed from [GitHub Releases](https://github.com/mikeqfu/pydriosm/releases).*

##### **Notable [changes](https://github.com/mikeqfu/pydriosm/compare/1.0.0...1.0.5) since [1.0.0](https://pypi.org/project/pydriosm/1.0.0/):**

- Integrated the function [read_parsed_osm_pbf()](https://github.com/mikeqfu/pydriosm/blob/243788f02c10fa91024b165819b52e6973fa3b26/pydriosm/read_GeoFabrik.py#L474-L515) into [read_pbf()](https://github.com/mikeqfu/pydriosm/blob/243788f02c10fa91024b165819b52e6973fa3b26/pydriosm/read_GeoFabrik.py#L319-L391) in the module [read_GeoFabrik](https://github.com/mikeqfu/pydriosm/blob/a1fb4ddce3f451e29f79fc1e06b999ab9e4eb0b2/pydriosm/read_GeoFabrik.py).
- Improved the following functions
  - [dump_osm_pbf_data()](https://github.com/mikeqfu/pydriosm/commit/cd209d985a3270b90d22501fdc5e3a8e8b142ac4#diff-cb2783bddce6ef6c0d7479f7e4ada08bdcec39cb0e9d0af83a4d1398b5737491L173-R204) in the module [osm_psql](https://github.com/mikeqfu/pydriosm/blob/cd209d985a3270b90d22501fdc5e3a8e8b142ac4/pydriosm/osm_psql.py), with a new parameter `chunk_size` allowing users to parse/read/dump data in a chunk-wise way;
  - [psql_subregion_osm_data_extracts()](https://github.com/mikeqfu/pydriosm/blob/9b37bbe76223332b037f12a8fa49d1fdb24c7262/pydriosm/dump_GeoFabrik.py#L45-L152) in the module [dump_GeoFabrik](https://github.com/mikeqfu/pydriosm/blob/4558a89938fa6f28ab105a6ee5d54a95745302e2/pydriosm/dump_GeoFabrik.py);
  - [gdal_configurations()](https://github.com/mikeqfu/pydriosm/commit/d85af9a3a37cbb8ffb2280090844dc61bde706f2) in the module [settings](https://github.com/mikeqfu/pydriosm/blob/d85af9a3a37cbb8ffb2280090844dc61bde706f2/pydriosm/settings.py).
- Added new function:
  - [retrieve_subregions()](https://github.com/mikeqfu/pydriosm/commit/4558a89938fa6f28ab105a6ee5d54a95745302e2#diff-06caa7c5b7806a98b9c915f4b9e44a9b7c305ead0c66e31baae94a58370c4615R19-R40), which retrieves a list of subregions of a given (sub)region name, to the module [dump_GeoFabrik](https://github.com/mikeqfu/pydriosm/blob/4558a89938fa6f28ab105a6ee5d54a95745302e2/pydriosm/dump_GeoFabrik.py);
  - [split_list()](https://github.com/mikeqfu/pydriosm/commit/243788f02c10fa91024b165819b52e6973fa3b26#diff-262651b10b835e2d78c1c6d4157b36f97721b7a10a13f197715ee984266c3882R242-R249) to the module [utils](https://github.com/mikeqfu/pydriosm/blob/243788f02c10fa91024b165819b52e6973fa3b26/pydriosm/utils.py).

<br/>

#### **[1.0.0](https://github.com/mikeqfu/pydriosm/releases/tag/1.0.0)**

(*4 March 2019*)

This is a release of a **brand-new** version.

*Note that the initial releases (of early versions up to **~~0.2.9~~**) had been permanently deleted.*