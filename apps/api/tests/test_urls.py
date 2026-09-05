"""URL 归一化测试(searcher 去重与 merger 证据合并共用)。"""
import pytest

from orca.urls import norm_url


def test_strips_utm_and_fragment():
    assert norm_url("https://docs.python.org/a/?utm_source=x#sec") == \
        "https://docs.python.org/a"


def test_strips_trailing_slash():
    assert norm_url("https://docs.python.org/3/") == "https://docs.python.org/3"


def test_host_lowercased_path_case_preserved():
    assert norm_url("https://DOCS.python.org/3/WhatsNew") == \
        "https://docs.python.org/3/WhatsNew"


def test_http_upgraded_to_https_for_comparison():
    assert norm_url("http://docs.python.org/3/") == \
        norm_url("https://docs.python.org/3")


def test_normalization_is_idempotent():
    u = norm_url("https://developer.mozilla.org/zh-CN/docs/Web/X?a=1&utm_term=y")
    assert norm_url(u) == u


def test_keeps_other_query_params():
    a = norm_url("https://x.org/p?id=1")
    b = norm_url("https://x.org/p?id=2")
    assert a != b


def test_unparseable_raises():
    with pytest.raises(ValueError):
        norm_url("not a url")
