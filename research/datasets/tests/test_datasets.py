from urllib.request import urlopen
import multiprocessing.dummy as mp
from multiprocessing import cpu_count

from .._base import FETCH_URLS


def test_urls():
    """Test whether URLS are working."""
    urls = [
        url
        for sublist in [[url] for url in list(FETCH_URLS.values()) if type(url) == str]
        for url in sublist
    ]

    p = mp.Pool(cpu_count())
    url_status = p.map(lambda url: (urlopen(url).status == 200), urls)

    assert all(url_status)