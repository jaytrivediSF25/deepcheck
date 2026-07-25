"""Compatibility shim for youtube-transcript-api 1.2+.

youtube-deepsummary calls the classmethod API:

    YouTubeTranscriptApi.get_transcript(video_id, languages=[...], proxies=...)
    YouTubeTranscriptApi.list_transcripts(video_id, proxies=...)

Version 1.2 removed both in favour of an instance API (``.fetch()`` / ``.list()``
with a ``proxy_config`` constructor argument). Upstream pins ``==1.1.0``, which
is not installable on every Python version, and the last release that still had
the classmethods (0.6.2) no longer works against YouTube's current endpoints.

Rather than fork upstream or freeze the interpreter, we re-attach the two
classmethods on top of the modern library. Upstream's extractor then runs
unmodified. This is a no-op when the methods already exist.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional


def _proxy_config(proxies: Optional[Dict[str, str]]):
    """Translate a requests-style proxies dict into a ProxyConfig."""
    if not proxies:
        return None
    try:
        from youtube_transcript_api.proxies import GenericProxyConfig
    except ImportError:  # pragma: no cover - very old versions
        return None
    return GenericProxyConfig(
        http_url=proxies.get("http"),
        https_url=proxies.get("https"),
    )


def install() -> bool:
    """Patch the legacy classmethods onto YouTubeTranscriptApi.

    Returns True if a patch was applied, False if none was needed or the
    library is unavailable.
    """
    try:
        from youtube_transcript_api import YouTubeTranscriptApi
    except ImportError:
        return False

    if hasattr(YouTubeTranscriptApi, "get_transcript"):
        return False  # 1.1.x or earlier — upstream works as written

    def get_transcript(
        video_id: str,
        languages: Any = ("en",),
        proxies: Optional[Dict[str, str]] = None,
        preserve_formatting: bool = False,
        **_: Any,
    ) -> List[Dict[str, Any]]:
        api = YouTubeTranscriptApi(proxy_config=_proxy_config(proxies))
        fetched = api.fetch(
            video_id,
            languages=list(languages) if languages else ["en"],
            preserve_formatting=preserve_formatting,
        )
        # Upstream indexes entries as dicts with text/start/duration.
        return fetched.to_raw_data()

    def list_transcripts(
        video_id: str, proxies: Optional[Dict[str, str]] = None, **_: Any
    ):
        api = YouTubeTranscriptApi(proxy_config=_proxy_config(proxies))
        return api.list(video_id)

    YouTubeTranscriptApi.get_transcript = staticmethod(get_transcript)
    YouTubeTranscriptApi.list_transcripts = staticmethod(list_transcripts)
    return True
