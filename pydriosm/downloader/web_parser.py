"""

"""

import collections
import concurrent.futures
import json
import os
import re
import urllib.parse

import bs4
import numpy as np
import pandas as pd
import requests
import shapely.geometry
from pyhelpers.ops import fake_requests_headers, parse_size, update_dict
from pyrcs.parser import parse_tr

from pydriosm.utils import first_unique


# == Geofabrik =====================================================================================


def get_geofabrik_raw_directory_index(url):
    # noinspection PyShadowingNames,PyUnresolvedReferences
    """
    Gets a raw directory index (including download information of older file logs).

    :param url: URL of a web page of a data resource (e.g. a subregion).
    :type url: str
    :return: Information of raw directory index.
    :rtype: pandas.DataFrame | None

    **Examples**::

        >>> from pydriosm.downloader.web_parser import get_geofabrik_raw_directory_index
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
    Parses the dictionary of download URLs in the (original) dataframe of download index.

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
    download_index_urls = pd.DataFrame(pd.concat(dat, ignore_index=True)).rename(
        columns={'pbf': '.osm.pbf', 'shp': '.shp.zip', 'bz2': '.osm.bz2'})

    # Replace NaN with None
    download_index_urls = download_index_urls.replace({np.nan: None})

    return download_index_urls


def fetch_geofabrik_download_index():
    """
    Fetches the official index of downloads for all available geographic (sub)regions.

    :return: the official index of all downloads
    :rtype: pandas.DataFrame

    **Examples**::

        >>> from pydriosm.downloader.web_parser import fetch_geofabrik_download_index
        >>> geofabrik_download_index = fetch_geofabrik_download_index()
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
    properties = pd.DataFrame(raw_data['properties'].to_list()).replace({np.nan: None})

    # Process 'geometry'
    geometry_ = pd.DataFrame(raw_data['geometry'].to_list())
    geometry = geometry_.apply(
        lambda x: getattr(shapely.geometry, x['type'])(
            [shapely.geometry.Polygon(x['coordinates'][0][0])]), axis=1)
    geometry = pd.DataFrame(geometry, columns=['geometry'])

    data = pd.DataFrame(pd.concat([properties, geometry], axis=1))

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
    Parses a <tr> tag under a <table> tag of the HTML data of a (sub)region.

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


def fetch_geofabrik_subregion_table(url, return_soup=False):
    # noinspection PyShadowingNames
    """
    Fetches download information of all geographic (sub)regions on a web page.

    :param url: URL of a subregion's web page
    :type url: str
    :param return_soup: Whether to return the scraped HTML object. Defaults to ``False``.
    :type return_soup: bool
    :return: download information of all available subregions on the given ``url``
    :rtype: tuple[pandas.DataFrame | None, bs4.BeautifulSoup] | pandas.DataFrame | None

    **Examples**::

        >>> from pydriosm.downloader.web_parser import fetch_geofabrik_subregion_table

        >>> # Download information on the homepage
        >>> url = 'https://download.geofabrik.de/'
        >>> subregion_table = fetch_geofabrik_subregion_table(url)
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
        [8 rows x 7 columns]
        >>> subregion_table.columns.to_list()
        ['subregion',
         'subregion-url',
         '.osm.pbf',
         '.osm.pbf-size',
         '.gpkg.zip',
         '.shp.zip',
         '.osm.bz2']

        >>> # Download information about 'Great Britain'
        >>> url = 'https://download.geofabrik.de/europe/united-kingdom.html'
        >>> subregion_table = fetch_geofabrik_subregion_table(url)
        >>> subregion_table
                  subregion  ... .osm.bz2
        0           Bermuda  ...     None
        1           England  ...     None
        2  Falkland Islands  ...     None
        3          Scotland  ...     None
        4             Wales  ...     None
        [5 rows x 7 columns]

        >>> # Download information about 'Antarctica'
        >>> url = 'https://download.geofabrik.de/antarctica.html'
        >>> subregion_table = fetch_geofabrik_subregion_table(url)
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

    if tr_data:
        ths = tables[-1].find_all('th')
        column_names = [
            th.get_text(strip=True) if th.get_text(strip=True) else '.osm.pbf-size' for th in ths]

        i1, i2 = column_names.index('.osm.pbf-size'), column_names.index('.osm.pbf')
        column_names[i1], column_names[i2] = column_names[i2], column_names[i1]

        column_names += [x for x in ['.shp.zip', '.osm.bz2'] if x not in column_names]

        # column_names = [  # Specify column names
        #     'subregion',
        #     'subregion-url',
        #     '.osm.pbf',
        #     '.osm.pbf-size',
        #     '.gpkg.zip',
        #     '.shp.zip',
        #     '.osm.bz2'
        # ]

        tr_data_ = [dat + [None] * (len(column_names) - len(dat)) for dat in tr_data]
        if tr_data_:
            subregion_table = pd.DataFrame(data=tr_data_, columns=column_names)
            subregion_table = subregion_table.rename(
                columns={'Sub Region': 'subregion', 'Quick Links': 'subregion-url'})
            subregion_table = subregion_table.replace({np.nan: None}).convert_dtypes()
            if return_soup:
                return subregion_table, soup
            return subregion_table

    if return_soup:
        return None, soup
    return None


def fetch_geofabrik_continent_tables():
    # noinspection PyShadowingNames
    """
    Fetches download catalogues for each continent.

    :return: Download catalogues for each continent.
    :rtype: dict | None

    **Examples**::

        >>> from pydriosm.downloader.web_parser import fetch_geofabrik_continent_tables
        >>> continent_tables = fetch_geofabrik_continent_tables()
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

    url = 'https://download.geofabrik.de/'

    with requests.get(url=url, headers=fake_requests_headers()) as response:
        response.raise_for_status()
        soup = bs4.BeautifulSoup(markup=response.content, features='html.parser')

    # Scan the homepage to collect info of regions for each continent
    tds = soup.find_all('td', attrs={'class': 'subregion'})
    continent_names = [td.a.get_text() for td in tds]

    continent_links = [urllib.parse.urljoin(url, url=td.a.get('href')) for td in tds]
    continent_links_dat = [fetch_geofabrik_subregion_table(url=url) for url in continent_links]
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
                                             is_root=True, starting_message=None,
                                             end_message="\n"):
    # noinspection PyShadowingNames
    """
    Finds all (sub)regions and their subregions.

    :param subregion_tables: download URLs of subregions;
        see examples of the methods
        :meth:`~pydriosm.downloader.GeofabrikDownloader.get_subregion_table` and
        :meth:`~pydriosm.downloader.GeofabrikDownloader.get_continent_tables`
    :type subregion_tables: dict
    :param verbose:
    :type verbose: bool | int
    :param indent_level:
    :type indent_level: str | int
    :param is_root:
    :type is_root: bool
    :param starting_message:
    :type starting_message: str | None
    :param end_message:
    :type end_message: str
    :return: a dictionary of region-subregion, and a list of (sub)regions without subregions
    :rtype: tuple[dict, list]

    **Examples**::

        >>> from pydriosm.downloader.web_parser import compile_geofabrik_region_subregion_tiers
        >>> from pydriosm.downloader.web_parser import fetch_geofabrik_continent_tables
        >>> continent_tables = fetch_geofabrik_continent_tables()
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
            print("  " * (indent_level + 1) + region_name + " ... ")  # Print with indentation

        sub_subregion_tables = {
            subregion:
                fetch_geofabrik_subregion_table(url) for subregion, url in
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
                "  " * (indent_level + 1) + f"(✔️ Finished processing subregions of {region_name})")

    region_subregion_tiers, having_no_subregions = _rectify_compiled_geofabrik_tiers(
        region_subregion_tiers, having_no_subregions)

    if verbose == 2 and is_root:
        print("✅ Successfully compiled Geofabrik region-subregion tier.", end=end_message)

    return region_subregion_tiers, having_no_subregions


def fetch_geofabrik_catalogue():
    # noinspection PyShadowingNames
    """
    Retrieves and compiles a catalogue of available OSM dataset downloads from Geofabrik.

    :return: A catalogue of available downloads.
    :rtype: pandas.DataFrame

    **Examples**::

        >>> from pydriosm.downloader.web_parser import fetch_geofabrik_catalogue
        >>> geofabrik_catalogue = fetch_geofabrik_catalogue()
        >>> type(geofabrik_catalogue)
        pandas.core.frame.DataFrame
        >>> geofabrik_catalogue.head()
                       subregion  ... .osm.bz2
        0                 Africa  ...     None
        1             Antarctica  ...     None
        2                   Asia  ...     None
        3  Australia and Oceania  ...     None
        4        Central America  ...     None
        [5 rows x 7 columns]
        >>> geofabrik_catalogue.columns.to_list()
        ['subregion',
         'subregion-url',
         '.osm.pbf',
         '.osm.pbf-size',
         '.gpkg.zip',
         '.shp.zip',
         '.osm.bz2']

    .. seealso::

        - Examples for the method
          :meth:`~pydriosm.downloader.GeofabrikDownloader.get_catalogue`.
    """

    url = 'https://download.geofabrik.de/'

    home_table, soup = fetch_geofabrik_subregion_table(url=url, return_soup=True)

    # Fetch subregion tables concurrently
    subregion_urls = [
        urllib.parse.urljoin(url, td.a.get('href'))
        for td in soup.find_all(name='td', attrs={'class': 'subregion'})]

    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
        subregion_tables = list(filter(
            lambda x: x is not None, executor.map(fetch_geofabrik_subregion_table, subregion_urls)))

    # Recursive processing of subregions
    all_tables = [home_table] + subregion_tables
    processed_urls = set(subregion_urls)

    while subregion_tables:
        new_subregion_tables = []

        with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
            results = list(executor.map(
                fetch_geofabrik_subregion_table,
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

    return catalogue.replace({np.nan: None})


def fetch_valid_geofabrik_subregion_names():
    """
    Fetches names of all available geographic (sub)regions.

    :return: names of all geographic (sub)regions available on Geofabrik free download server
    :rtype: set

    .. seealso::

        - Examples for the method
          :meth:`~pydriosm.downloader.GeofabrikDownloader.get_valid_subregion_names`.
    """

    download_index = fetch_geofabrik_download_index()

    valid_subregion_names = set(download_index['name'])

    return valid_subregion_names


# == BBBike ========================================================================================


def fetch_bbbike_cities(url, raise_error=True):
    # noinspection PyShadowingNames
    """
    Fetches the names of all the available cities.

    :return: list of names of cities available on BBBike free download server
    :rtype: list

    .. note::

        - This function is used internally by
          :meth:`BBBikeDownloader.get_bbbike_cities
          <pydriosm.downloader.BBBikeDownloader.get_bbbike_cities>`, which uses
          :attr:`BBBikeDownloader.URL<pydriosm.downloader.BBBikeDownloader.URL>`
          as the default ``url``.
        - The ``url`` used to default to
          ``'https://raw.githubusercontent.com/wosch/bbbike-world/world/etc/cities.txt'``, which
          has been unavailable.

    **Examples**::

        >>> from pydriosm.downloader.web_parser import fetch_bbbike_cities
        >>> url = 'https://download.bbbike.org/osm/bbbike/'
        >>> cities = fetch_bbbike_cities(url)

    .. seealso::

        - Examples for :meth:`~pydriosm.downloader.BBBikeDownloader.get_bbbike_cities`.
    """

    try:  # url = 'https://download.bbbike.org/osm/bbbike/'
        response = requests.get(url, headers=fake_requests_headers(), timeout=10)
        if raise_error:
            response.raise_for_status()
        elif not response.ok:
            return []  # Return empty list if we shouldn't raise error

        soup = bs4.BeautifulSoup(response.content, features='html.parser')
    except Exception as e:
        if raise_error:
            raise e
        return []

    # Find the table or the specific links directly
    links = soup.find_all('a')  # Directory listings are consistently <a> tags inside <tr> or <td>

    if not links and raise_error:
        raise ValueError(
            f"Could not find any links at '{url}'. The page structure might have changed.")

    cities = []
    for a in links:
        text = a.get_text(strip=True)
        # Filter: Must have text; Not parent dir
        if text and not text.startswith((".", "Parent")):
            cities.append(text.rstrip("/"))

    return cities


def fetch_bbbike_subregion_index(url, raise_error=True):
    # noinspection PyShadowingNames
    """
    Fetches a catalogue for geographic (sub)regions.

    :return: catalogue for subregions of BBBike data
    :rtype: pandas.DataFrame

    **Examples**::

        >>> from pydriosm.downloader.web_parser import fetch_bbbike_subregion_index
        >>> url = 'https://download.bbbike.org/osm/bbbike/'
        >>> fetch_bbbike_subregion_index(url)

    .. seealso::

        - Examples for the method
          :meth:`~pydriosm.downloader.BBBikeDownloader.get_subregion_index`.
    """

    # url='https://download.bbbike.org/osm/bbbike/'
    with requests.get(url, headers=fake_requests_headers()) as response:
        if raise_error:
            response.raise_for_status()
        soup = bs4.BeautifulSoup(response.content, features='html.parser')

    thead, tbody = soup.find('thead'), soup.find('tbody')

    ths = [th.text.strip().lower().replace(' ', '_') for th in thead.find_all(name='th')]
    trs = tbody.find_all(name='tr')
    data = parse_tr(trs=trs, ths=ths, as_dataframe=True).drop(index=0)
    data.index = range(len(data))

    for col in ['size', 'type']:
        if data[col].nunique() == 1:
            del data[col]

    data['name'] = data['name'].map(lambda x: x.rstrip('/').strip())
    data['last_modified'] = pd.to_datetime(data['last_modified'])
    data['url'] = [urllib.parse.urljoin(url, x.get('href')) for x in soup.find_all('a')[1:]]

    return data


def fetch_bbbike_city_poly(poly_url, raise_error=True):
    # noinspection PyShadowingNames
    """
    Fetches and parses a .poly file from BBBike to a shapely Polygon.

    :param poly_url: URL to the .poly file (e.g. from download.bbbike.org)
    :type poly_url: str
    :param raise_error: whether to raise an exception if the request fails, defaults to True
    :type raise_error: bool
    :return: a polygon representing the city's boundaries
    :rtype: shapely.Polygon

    **Examples**::

        >>> from pydriosm.downloader.web_parser import get_bbbike_city_poly
        >>> poly_url = 'https://download.bbbike.org/osm/bbbike/Aachen/Aachen.poly'
        >>> aachen_poly = get_bbbike_city_poly(poly_url)
        >>> type(aachen_poly)
        shapely.geometry.polygon.Polygon
        >>> print(aachen_poly)
        POLYGON ((5.88 50.6, 6.58 50.6, 6.58 50.99, 5.88 50.99, 5.88 50.6))
    """

    # poly_url = 'https://download.bbbike.org/osm/bbbike/Aachen/Aachen.poly'
    try:
        response = requests.get(poly_url, headers=fake_requests_headers(), timeout=10)
        if raise_error:
            response.raise_for_status()
        elif not response.ok:
            return None

        # Decode content and split into lines correctly
        lines = response.content.decode('utf-8').splitlines()

    except Exception as e:
        if raise_error:
            raise e
        return None

    # Osmosis polygon format:
    # Line 0: Name, Line 1: Polygon ID, Line 2 to -2: Coords, Line -1: END
    coords = []
    for line in lines:
        parts = line.strip().split()
        # Only process lines that have exactly two numbers (Longitude and Latitude)
        if len(parts) == 2:
            try:
                coords.append([float(x) for x in parts])
            except ValueError:
                continue  # Skip lines that aren't numeric (like the header or "END")

    return shapely.geometry.Polygon(coords)  # (ll, lr, ur, ul)


def fetch_bbbike_cities_poly(url, max_workers=10, raise_error=True):
    # noinspection PyShadowingNames
    """
    Fetches poly information of all cities available on the BBBike download server.

    :param url: The base URL of the BBBike download server.
    :type url: str
    :param max_workers: Number of parallel threads to use. Defaults to ``10``.
    :type max_workers: int
    :param raise_error: Whether to raise an exception if a request fails. Defaults to ``True``.
    :type raise_error: bool
    :return: A DataFrame containing poly information of BBBike cities, i.e. geographic (sub)regions.
    :rtype: pandas.DataFrame

    **Examples**::

        >>> from pydriosm.downloader.web_parser import fetch_bbbike_cities_poly
        >>> url = 'https://download.bbbike.org/osm/bbbike/'
        >>> bbbike_cities_poly = fetch_bbbike_cities_poly(url)
        >>> bbbike_cities_poly.head()
                  name                                           geometry
        0       Aachen  POLYGON ((5.88 50.6, 6.58 50.6, 6.58 50.99, 5....
        1       Aarhus  POLYGON ((9.82 55.99, 10.37 55.99, 10.37 56.29...
        2     Adelaide  POLYGON ((138.46 -35.03, 138.74 -35.03, 138.74...
        3  Albuquerque  POLYGON ((-106.8 35, -106.47 35, -106.47 35.22...
        4   Alexandria  POLYGON ((29.7 31.02, 30.21 31.02, 30.21 31.34...

    .. seealso::

        - Examples for the method
          :meth:`~pydriosm.downloader.BBBikeDownloader.get_coordinates_of_cities`.
    """

    # Fetch the data of BBBike cities
    subregion_index = fetch_bbbike_subregion_index(url=url, raise_error=raise_error)

    if subregion_index is None:
        return None

    def _get_poly(row):
        """Helper to construct URL and fetch the polygon."""
        city_url = row['url']
        city_name = city_url.rstrip('/').split('/')[-1]
        poly_url = urllib.parse.urljoin(city_url, f"{city_name}.poly")

        # Returns (index, polygon) to maintain order during threading
        return row.name, fetch_bbbike_city_poly(poly_url, raise_error=False)

    # Convert the DataFrame rows to a list of dicts/tuples for the executor
    rows = [row for _, row in subregion_index.iterrows()]

    results = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
        # map ensures we can process them as they complete
        results = list(executor.map(_get_poly, rows))

    # Reconstruct DataFrame, sorting it by index to ensure name and geometry match correctly
    results.sort(key=lambda x: x[0])
    geometries = [res[1] for res in results]

    cities_poly = pd.DataFrame({'name': subregion_index['name'], 'geometry': geometries})

    return cities_poly


def fetch_bbbike_valid_subregion_names(cls_instance):
    """
    Fetches a list of names of all geographic (sub)regions.

    :return: a list of geographic (sub)region names available on BBBike free download server
    :rtype: list
    """

    # subregion_names = list(cls_instance.get_names_of_cities())
    subregion_catalogue = cls_instance.get_subregion_index(confirmation_required=False)
    subregion_names = subregion_catalogue['name'].to_list()

    return subregion_names


def _parse_bbbike_tag_a(a, url):
    """
    Parse an <a> tag of a download link.

    :param a: <a> tag of a download link
    :type a: bs4.element.Tag
    :param url: URL of the web page of a subregion
    :type url: str
    :return: data contained in the <a> tag
    :rtype: list
    """

    href = a.attrs.get('href')
    filename, download_url = os.path.basename(href), urllib.parse.urljoin(url, href)

    if not a.has_attr('title'):
        file_format, file_size, last_update = 'Poly', None, None

    else:
        # File type and size
        if a.attrs.get('class') == ['download_link']:
            file_format, file_size = [
                y.strip() if isinstance(y, str) else y.get_text(strip=True) for y in a.contents]
        else:
            file_format, file_size = 'Txt', None
        # Date and time
        last_update = pd.to_datetime(re.sub(r'last update: ?', '', a.attrs.get('title')))

    parsed_dat = [filename, download_url, file_format, file_size, last_update]

    return parsed_dat


def fetch_bbbike_sub_catalogue(subregion_name, url, raise_error=True):
    """
    Fetches the BBBike data catalogue of a specific subregion.

    :param subregion_name: The subregion name.
    :type subregion_name: str
    :param url: The URL of the subregion webpage.
    :type url: str
    :param raise_error: If ``True``, raise the error if there is any.
    :type raise_error: bool
    :return: BBBike data catalogue of the specified subregion.
    :rtype: pandas.DataFrame

    subregion_name = 'Birmingham'
    url = 'https://download.bbbike.org/osm/bbbike/'
    sub_catalogue = fetch_sub_catalogue(subregion_name, url)
    """

    url = urllib.parse.urljoin(url, subregion_name + '/')

    with requests.get(url=url, headers=fake_requests_headers()) as response:
        if raise_error:
            response.raise_for_status()
        soup = bs4.BeautifulSoup(markup=response.content, features='html.parser')

    download_link_a_tags = soup.find_all('a', attrs={'class': ['download_link', 'small']})

    sub_catalogue = pd.DataFrame(_parse_bbbike_tag_a(x, url) for x in download_link_a_tags)
    sub_catalogue.columns = ['filename', 'url', 'data_type', 'size', 'last_update']

    return sub_catalogue


def fetch_bbbike_catalogue(cls_instance, verbose=False):
    """
    Fetches a dict-type index of available formats, data types and a download catalogue.

    :return: a list of available formats, a list of available data types and
        a dictionary of download catalogue
    :rtype: dict
    """

    subregion_names = cls_instance.get_valid_subregion_names()

    catalogue = []
    for subregion_name in subregion_names:
        if verbose == 2:
            print(f'  "{subregion_name}"', end=" ... ")

        sub_catalogue = fetch_bbbike_sub_catalogue(
            subregion_name=subregion_name, url=cls_instance.URL)

        if sub_catalogue is None:
            raise Exception
        else:
            if verbose == 2:
                print("Done.")
            catalogue.append(sub_catalogue)

    subregion_name = subregion_names[0]
    subregion_catalogue = catalogue[0]

    # Available file formats
    file_format = [
        re.sub('{}|CHECKSUM'.format(subregion_name), '', f)
        for f in subregion_catalogue['filename']]

    # Available data types
    data_type = subregion_catalogue['data_type'].to_list()

    download_index = {
        'FileFormat': [x.replace(".osm", "", 1) for x in file_format[:-2]],
        'DataType': data_type[:-2],
        'Catalogue': dict(zip(subregion_names, catalogue)),
    }

    return download_index
