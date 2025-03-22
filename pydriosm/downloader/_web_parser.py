"""

"""

import collections
import concurrent.futures
import json
import re
import urllib.parse

import bs4
import pandas as pd
import requests
import shapely.geometry
from pyhelpers.ops import fake_requests_headers, parse_size, update_dict

from pydriosm.utils import first_unique


# == Geofabrik =====================================================================================


def get_geofabrik_raw_directory_index(url):
    # noinspection PyShadowingNames
    """

    :param url:
    :return:

    **Examples**::

        >>> from pydriosm.downloader._web_parser import get_geofabrik_raw_directory_index
        >>> url = 'https://download.geofabrik.de/'
        >>> raw_directory_index = get_geofabrik_raw_directory_index(url)
        Traceback (most recent call last):
            ... ...
        ValueError: No 'details' div found on the page.
        >>> url = 'https://download.geofabrik.de/europe/great-britain.html'
        >>> raw_directory_index = get_geofabrik_raw_directory_index(url)
        >>> type(raw_directory_index)
        pandas.core.frame.DataFrame
        >>> raw_directory_index.columns.tolist()
        ['file', 'date', 'size', 'metric_file_size', 'url']
    """

    with requests.get(url=url, headers=fake_requests_headers()) as response:
        response.raise_for_status()  # Raise an exception for HTTP errors
        soup = bs4.BeautifulSoup(response.content, features='html.parser')

    # Extract table data
    cold_soup = soup.find(name='div', attrs={'id': 'details'})
    if not cold_soup:
        raise ValueError("No 'details' div found on the page.")

    # Extract headers and rows
    ths, tds = [], []
    for tr in cold_soup.find_all('tr'):
        if len(tr.find_all('th')) > 0:
            ths = [th.get_text(strip=True) for th in tr.find_all('th')]
        else:
            tds.append([td.get_text(strip=True) for td in tr.find_all('td')])

    if not ths or not tds:
        raise ValueError("No raw directory index is available on the web page.")

    # Create DataFrame
    data = pd.DataFrame(data=tds, columns=ths)

    # Process DataFrame columns
    data['date'] = pd.to_datetime(data['date'])
    data['size'] = data['size'].astype('int64')

    data['metric_file_size'] = data['size'].map(
        lambda x: parse_size(x, binary=False, precision=0 if (x <= 1000) else 1))

    data['url'] = data['file'].map(lambda x: urllib.parse.urljoin(url, x))

    return data


def _parse_geofabrik_download_index_urls(urls):
    """
    Parse the dictionary of download URLs in the (original) dataframe of download index.

    :param urls: (original) series of the URLs provided in the official download index
    :type urls: pandas.Series
    :return: download index with parsed data of the URLs for downloading data
    :rtype: pandas.DataFrame

    .. seealso::

        - Examples for the method
          :meth:`~pydriosm.downloader.GeofabrikDownloader.get_download_index`.
    """

    if isinstance(urls, pd.Series):
        dat = urls.map(lambda x: pd.DataFrame.from_dict(data=x, orient='index').T).values
    else:
        dat = [pd.DataFrame.from_dict(data=x, orient='index').T for x in urls]

    # Concatenate all DataFrames and rename columns
    download_index_urls = pd.concat(dat, ignore_index=True).rename(
        columns={'pbf': '.osm.pbf', 'shp': '.shp.zip', 'bz2': '.osm.bz2'})

    # Replace NaN with None
    download_index_urls = download_index_urls.where(pd.notnull(download_index_urls), None)

    return download_index_urls


def get_geofabrik_download_index():
    """
    Get the official index of downloads for all available geographic (sub)regions.

    :return: the official index of all downloads
    :rtype: pandas.DataFrame

    **Examples**::

        >>> from pydriosm.downloader._web_parser import get_geofabrik_download_index
        >>> geofabrik_download_index = get_geofabrik_download_index()
        >>> type(geofabrik_download_index)
        pandas.core.frame.DataFrame
        >>> geofabrik_download_index.head()
                    id  ...                                            updates
        0  afghanistan  ...  https://download.geofabrik.de/asia/afghanistan...
        1       africa  ...       https://download.geofabrik.de/africa-updates
        2      albania  ...  https://download.geofabrik.de/europe/albania-u...
        3      alberta  ...  https://download.geofabrik.de/north-america/ca...
        4      algeria  ...  https://download.geofabrik.de/africa/algeria-u...
        [5 rows x 13 columns]

    .. seealso::

        - Examples for the method
          :meth:`~pydriosm.downloader.GeofabrikDownloader.get_download_index`.
    """

    url = 'https://download.geofabrik.de/index-v1.json'

    with requests.get(url=url, headers=fake_requests_headers()) as response:
        response.raise_for_status()
        raw_data = pd.DataFrame(json.loads(response.content)['features'])

    # Process 'properties'
    properties = pd.DataFrame(raw_data['properties'].to_list()).where(pd.notnull, None)

    # Process 'geometry'
    geometry_ = pd.DataFrame(raw_data['geometry'].to_list())
    geometry = geometry_.apply(
        lambda x: getattr(shapely.geometry, x['type'])(
            [shapely.geometry.Polygon(x['coordinates'][0][0])]), axis=1)
    geometry = pd.DataFrame(geometry, columns=['geometry'])

    data = pd.concat([properties, geometry], axis=1)

    # Process 'name'
    temp_names = data['name'].str.strip().str.replace('<br />', ' ')
    data['name'] = temp_names.map(
        lambda x: x.replace('us/', '').title() if x.startswith('us/') else x)

    temp = (k for k, v in collections.Counter(data['name']).items() if v > 1)
    duplicates = {i: x for k in temp for i, x in enumerate(data['name']) if x == k}
    for i in duplicates:
        if data.at[i, 'id'].startswith('us/'):
            data.at[i, 'name'] += ' (US)'

    # Process 'urls'
    urls_column_name = 'urls'
    urls = _parse_geofabrik_download_index_urls(data[urls_column_name])
    data = data.drop(columns=[urls_column_name])

    # Put all together
    download_index = pd.concat([data, urls], axis=1)

    return download_index


def _parse_geofabrik_subregion_table_tr(tr, url):
    """
    Parse a <tr> tag under a <table> tag of the HTML data of a (sub)region.

    :param tr: <tr> tag under a <table> tag of a subregion's HTML data
    :type tr: bs4.element.Tag
    :param url: URL of a subregion's web page
    :type url: str
    :return: data contained in the <tr> tag
    :rtype: list

    .. seealso::

        - Examples for the method
          :meth:`~pydriosm.downloader.GeofabrikDownloader.get_subregion_table`.
    """

    td_data = []

    tds = tr.find_all('td')

    for td in tds:
        if td.has_attr('class'):
            # noinspection PyArgumentList
            td_text = td.get_text(separator=' ', strip=True)
            td_data.extend([td_text, urllib.parse.urljoin(base=url, url=td.a['href'])])

        else:
            td_link = urllib.parse.urljoin(url, url=td.a['href']) if td.a else None

            if td.has_attr('style'):
                if td.get('style').startswith('border-right'):
                    td_data.append(td_link)
                elif td.get('style').startswith('border-left'):
                    td_data.append(re.sub(r'[()]', '', td.text.strip().replace('\xa0', ' ')))

            else:
                td_data.append(td_link)

    return td_data


def get_geofabrik_subregion_table(url):
    # noinspection PyShadowingNames
    """
    Get download information of all geographic (sub)regions on a web page.

    :param url: URL of a subregion's web page
    :type url: str
    :return: download information of all available subregions on the given ``url``
    :rtype: pandas.DataFrame | None

    **Examples**::

        >>> from pydriosm.downloader._web_parser import get_geofabrik_subregion_table
        >>> # Download information on the homepage
        >>> url = 'https://download.geofabrik.de/'
        >>> subregion_table = get_geofabrik_subregion_table(url)
        >>> subregion_table
                       subregion  ... .osm.bz2
        0                 Africa  ...     None
        1             Antarctica  ...     None
        2                   Asia  ...     None
        3  Australia and Oceania  ...     None
        4        Central America  ...     None
        5                 Europe  ...     None
        6          North America  ...     None
        7          South America  ...     None
        [8 rows x 6 columns]
        >>> subregion_table.columns.to_list()
        ['subregion',
         'subregion-url',
         '.osm.pbf',
         '.osm.pbf-size',
         '.shp.zip',
         '.osm.bz2']
        >>> # Download information about 'Great Britain'
        >>> url = 'https://download.geofabrik.de/europe/united-kingdom.html'
        >>> subregion_table = get_geofabrik_subregion_table(url)
        >>> subregion_table
          subregion  ... .osm.bz2
        0   England  ...     None
        1  Scotland  ...     None
        2     Wales  ...     None
        [3 rows x 6 columns]
        >>> # Download information about 'Antarctica'
        >>> url = 'https://download.geofabrik.de/antarctica.html'
        >>> subregion_table = get_geofabrik_subregion_table(url)
        Compiling information about subregions of "Antarctica" ... Failed.
        >>> subregion_table.empty
        True
        >>> # To get more information about the above failure, set `verbose=2`
        >>> subregion_table = get_geofabrik_subregion_table(url)
        Compiling information about subregions of "Antarctica" ... Failed.
        No subregion data is available for "Antarctica" on Geofabrik's free download server.
        >>> subregion_table is None
        True
    """

    with requests.get(url, headers=fake_requests_headers()) as response:
        response.raise_for_status()
        soup = bs4.BeautifulSoup(response.content, features='html.parser')

    tr_data = []

    h3_tags = soup.find_all(name='h3', string=re.compile(r'(Special )?Sub[ \-]Regions?'))

    attrs = {'id': re.compile(r'(special)?subregions')}
    tables = [h3_tag.find_next('table', attrs=attrs) for h3_tag in h3_tags] if len(h3_tags) > 0 \
        else soup.find_all('table', attrs=attrs)

    for table in tables:
        if table:  # Ensure the table exists (for `find_next` case)
            trs = table.find_all('tr', onmouseover=True)
            tr_data.extend([_parse_geofabrik_subregion_table_tr(tr=tr, url=url) for tr in trs])

    column_names = [  # Specify column names
        'subregion', 'subregion-url', '.osm.pbf', '.osm.pbf-size', '.shp.zip', '.osm.bz2']

    tr_data_ = [dat + [None] if len(dat) == 5 else dat for dat in tr_data]

    if tr_data_:
        subregion_table = pd.DataFrame(data=tr_data_, columns=column_names)
        return subregion_table.where(pd.notnull(subregion_table), None)


def get_geofabrik_continent_tables(url='https://download.geofabrik.de/'):
    # noinspection PyShadowingNames
    """

    :param url:
    :return:

    **Examples**::

        >>> from pydriosm.downloader._web_parser import get_geofabrik_continent_tables
        >>> url = 'https://download.geofabrik.de/'
        >>> continent_tables = get_geofabrik_continent_tables(url)
        >>> type(continent_tables)
        dict
        >>> list(continent_tables)
        ['Africa',
         'Antarctica',
         'Asia',
         'Australia and Oceania',
         'Central America',
         'Europe',
         'North America',
         'South America']
    """

    with requests.get(url=url, headers=fake_requests_headers()) as response:
        response.raise_for_status()
        soup = bs4.BeautifulSoup(markup=response.content, features='html.parser')

    # Scan the homepage to collect info of regions for each continent
    tds = soup.find_all('td', attrs={'class': 'subregion'})
    continent_names = [td.a.text for td in tds]

    continent_links = [urllib.parse.urljoin(url, url=td.a['href']) for td in tds]
    continent_links_dat = [get_geofabrik_subregion_table(url=url) for url in continent_links]
    continent_tables = dict(zip(continent_names, continent_links_dat))

    return continent_tables


def _rectify_compiled_geofabrik_tiers(region_subregion_tier, having_no_subregions):
    try:
        # Rectify tiers
        region_subregion_tier['Asia']['China']['Taiwan'] = region_subregion_tier['Asia']['Taiwan']
        region_subregion_tier['Asia'].pop('Taiwan')

        # Replace duplicated names
        region_subregion_tier['North America']['United States of America']['Georgia (US)'] = \
            region_subregion_tier['North America']['United States of America'].pop('Georgia')
        having_no_subregions.append('Georgia (US)')

        idx = len(having_no_subregions) - 1 - having_no_subregions[::-1].index('Georgia')
        having_no_subregions[idx] = 'Georgia (US)'

        having_no_subregions = list(first_unique(having_no_subregions))

    except KeyError:
        pass

    return region_subregion_tier, having_no_subregions


def compile_geofabrik_region_subregion_tiers(subregion_tables, verbose=2, indent_level=0,
                                             is_root=True, starting_message=None, end_message="\n"):
    # noinspection PyShadowingNames
    """
    Find all (sub)regions and their subregions.

    :param subregion_tables: download URLs of subregions;
        see examples of the methods
        :meth:`~pydriosm.downloader.GeofabrikDownloader.get_subregion_table` and
        :meth:`~pydriosm.downloader.GeofabrikDownloader.get_continent_tables`
    :type subregion_tables: dict
    :param verbose:
    :type verbose:
    :param indent_level:
    :type indent_level: str
    :param is_root:
    :type is_root: bool
    :param starting_message:
    :param end_message:
    :return: a dictionary of region-subregion, and a list of (sub)regions without subregions
    :rtype: tuple[dict, list]

    **Examples**::

        >>> from pydriosm.downloader._web_parser import compile_geofabrik_region_subregion_tiers
        >>> from pydriosm.downloader._web_parser import get_geofabrik_continent_tables
        >>> continent_tables = get_geofabrik_continent_tables()
        >>> region_subregion_tier, having_no_subregions = \
        ...     compile_geofabrik_region_subregion_tiers(continent_tables, verbose=2)

    .. seealso::

        - Examples for the method
          :meth:`~pydriosm.downloader.GeofabrikDownloader.get_region_subregion_tier`.
    """

    if verbose == 2 and is_root:
        if starting_message is None:
            print("Starting to compile Geofabrik region-subregion tier ... ")
        else:
            print(starting_message)

    region_subregion_tiers = {}

    # Identify regions that have subregions
    having_subregions = {
        region: table for region, table in subregion_tables.items() if table is not None
    }
    having_no_subregions = [
        region for region in subregion_tables if region not in having_subregions
    ]

    # Ensure all regions are included, even those without subregions
    for region in subregion_tables:
        if region not in region_subregion_tiers:  # Store regions with no subregions as None
            region_subregion_tiers.update({region: None})

    for region, table in having_subregions.items():
        subregions = set(table['subregion']) if not table.empty else None
        update_dict(region_subregion_tiers, {region: subregions}, inplace=True)

    # Track continent (top-level regions)
    is_top_tier = indent_level == 0

    # Process each continent separately
    for region_name, subregion_table in having_subregions.items():
        if verbose == 2:
            print("\t" * (indent_level + 1) + region_name + " ... ")  # Print with indentation

        sub_subregion_tables = {
            subregion:
                get_geofabrik_subregion_table(url) for subregion, url in
            zip(subregion_table['subregion'], subregion_table['subregion-url'])
        }

        sub_tiers, no_subregions = compile_geofabrik_region_subregion_tiers(
            sub_subregion_tables, verbose=verbose, indent_level=indent_level + 1, is_root=False
        )

        having_no_subregions.extend(no_subregions)

        region_subregion_tiers.update({region_name: sub_tiers})

        # Print message when a continent has finished processing
        if verbose == 2 and is_top_tier:
            print(
                "\t" * (indent_level + 1) + f"(✔️ Finished processing subregions of {region_name})")

    region_subregion_tiers, having_no_subregions = _rectify_compiled_geofabrik_tiers(
        region_subregion_tiers, having_no_subregions)

    if verbose == 2 and is_root:
        print("✅ Successfully compiled Geofabrik region-subregion tier.", end=end_message)

    return region_subregion_tiers, having_no_subregions


def get_geofabrik_catalogue():
    # noinspection PyShadowingNames
    """
    Retrieves and compiles a catalogue of available OSM dataset downloads from Geofabrik.

    :return: A catalogue of available downloads.
    :rtype: pandas.DataFrame

    **Examples**::

        >>> from pydriosm.downloader._web_parser import get_geofabrik_catalogue
        >>> downloads_catalogue = get_geofabrik_catalogue()
        >>> type(downloads_catalogue)
        pandas.core.frame.DataFrame
        >>> catalogue.head()
                       subregion  ... .osm.bz2
        0                 Africa  ...     None
        1             Antarctica  ...     None
        2                   Asia  ...     None
        3  Australia and Oceania  ...     None
        4        Central America  ...     None
        [5 rows x 6 columns]
        >>> catalogue.columns.to_list()
        ['subregion',
         'subregion-url',
         '.osm.pbf',
         '.osm.pbf-size',
         '.shp.zip',
         '.osm.bz2']

    .. seealso::

        - Examples for the method
          :meth:`~pydriosm.downloader.GeofabrikDownloader.get_catalogue`.
    """

    url = 'https://download.geofabrik.de/'

    with requests.get(url, headers=fake_requests_headers()) as response:
        response.raise_for_status()
        soup = bs4.BeautifulSoup(markup=response.content, features='html.parser')

    # Home table
    home_tr_data = []
    table_tags = soup.find_all(name='table', attrs={'id': re.compile(r'(special)?subregions')})
    for table_tag in table_tags:
        trs = table_tag.find_all(name='tr', onmouseover=True)
        home_tr_data += [_parse_geofabrik_subregion_table_tr(tr=tr, url=url) for tr in trs]

    column_names = [  # Specify column names
        'subregion', 'subregion-url', '.osm.pbf', '.osm.pbf-size', '.shp.zip', '.osm.bz2']
    home_tr_data_ = [entry + [None] if len(entry) == 5 else entry for entry in home_tr_data]
    home_table = pd.DataFrame(data=home_tr_data_, columns=column_names)

    # Fetch subregion tables concurrently
    subregion_urls = [
        urllib.parse.urljoin(url, td.a.get('href'))
        for td in soup.find_all(name='td', attrs={'class': 'subregion'})]

    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
        subregion_tables = list(filter(
            lambda x: x is not None, executor.map(get_geofabrik_subregion_table, subregion_urls)))

    # Recursive processing of subregions
    all_tables = [home_table] + subregion_tables
    processed_urls = set(subregion_urls)

    while subregion_tables:
        new_subregion_tables = []

        with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
            results = list(executor.map(
                get_geofabrik_subregion_table,
                [url for tbl in subregion_tables for url in tbl['subregion-url']]))

        for result in results:
            if result is not None:
                new_urls = set(result['subregion-url']) - processed_urls
                processed_urls.update(new_urls)
                new_subregion_tables.append(result)

        subregion_tables = new_subregion_tables
        all_tables.extend(new_subregion_tables)

    # Compile final catalogue
    catalogue = pd.concat(objs=all_tables, axis=0, ignore_index=True).drop_duplicates(
        ignore_index=True)

    # Handle duplicate subregion names
    duplicates = {
        i: x for i, x in enumerate(catalogue['subregion'])
        if catalogue['subregion'].tolist().count(x) > 1}

    for i in duplicates:
        url_ = catalogue.loc[i, 'subregion-url']
        if 'us/' in url_ or 'north-america' in url_:
            catalogue.loc[i, 'subregion'] += ' (US)'

    return catalogue


def get_valid_geofabrik_subregion_names():
    """
    Get names of all available geographic (sub)regions.

    :return: names of all geographic (sub)regions available on Geofabrik free download server
    :rtype: set

    .. seealso::

        - Examples for the method
          :meth:`~pydriosm.downloader.GeofabrikDownloader.get_valid_subregion_names`.
    """

    download_index = get_geofabrik_download_index()

    valid_subregion_names = set(download_index['name'])

    return valid_subregion_names


# == BBBike ========================================================================================
