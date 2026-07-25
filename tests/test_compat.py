"""The shim that lets upstream's extractor run on youtube-transcript-api 1.2+."""

import sys
import types

import pytest

from deepcheck import compat


@pytest.fixture
def fake_library(monkeypatch):
    """A stand-in for the 1.2+ instance API, with no classmethods."""
    calls = {}

    class FetchedTranscript:
        def to_raw_data(self):
            return [{"text": "hello", "start": 0.0, "duration": 1.0}]

    class YouTubeTranscriptApi:
        def __init__(self, proxy_config=None, http_client=None):
            calls["proxy_config"] = proxy_config

        def fetch(self, video_id, languages=("en",), preserve_formatting=False):
            calls["fetch"] = (video_id, list(languages), preserve_formatting)
            return FetchedTranscript()

        def list(self, video_id):
            calls["list"] = video_id
            return ["en"]

    class GenericProxyConfig:
        def __init__(self, http_url=None, https_url=None):
            self.http_url, self.https_url = http_url, https_url

    root = types.ModuleType("youtube_transcript_api")
    root.YouTubeTranscriptApi = YouTubeTranscriptApi
    proxies_mod = types.ModuleType("youtube_transcript_api.proxies")
    proxies_mod.GenericProxyConfig = GenericProxyConfig

    monkeypatch.setitem(sys.modules, "youtube_transcript_api", root)
    monkeypatch.setitem(sys.modules, "youtube_transcript_api.proxies", proxies_mod)
    return YouTubeTranscriptApi, calls


def test_installs_missing_classmethods(fake_library):
    api, calls = fake_library
    assert compat.install() is True

    rows = api.get_transcript("vid123", languages=["en", "es"])
    assert rows == [{"text": "hello", "start": 0.0, "duration": 1.0}]
    assert calls["fetch"] == ("vid123", ["en", "es"], False)

    assert api.list_transcripts("vid123") == ["en"]
    assert calls["list"] == "vid123"


def test_translates_proxies_dict(fake_library):
    api, calls = fake_library
    compat.install()

    api.get_transcript("vid123", proxies={"http": "http://p:1", "https": "https://p:2"})
    config = calls["proxy_config"]
    assert config.http_url == "http://p:1"
    assert config.https_url == "https://p:2"


def test_no_proxies_means_no_config(fake_library):
    api, calls = fake_library
    compat.install()
    api.get_transcript("vid123")
    assert calls["proxy_config"] is None


def test_is_a_noop_when_classmethods_exist(fake_library, monkeypatch):
    api, _ = fake_library
    # raising=False: the point of the fake is that the attribute is absent.
    monkeypatch.setattr(
        api, "get_transcript", staticmethod(lambda *a, **k: "original"), raising=False
    )
    assert compat.install() is False
    assert api.get_transcript("x") == "original"


def test_returns_false_without_the_library(monkeypatch):
    monkeypatch.setitem(sys.modules, "youtube_transcript_api", None)
    assert compat.install() is False
