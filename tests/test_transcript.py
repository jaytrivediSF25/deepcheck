import pytest

from deepcheck.models import Segment
from deepcheck.transcript import TranscriptError, parse_vtt, parse_video_id, to_text


class TestParseVideoId:
    @pytest.mark.parametrize(
        "value",
        [
            "iGDTiTfovwI",
            "https://www.youtube.com/watch?v=iGDTiTfovwI",
            "https://www.youtube.com/watch?v=iGDTiTfovwI&t=42s",
            "https://youtu.be/iGDTiTfovwI",
            "https://www.youtube.com/shorts/iGDTiTfovwI",
            "https://www.youtube.com/embed/iGDTiTfovwI",
            "https://www.youtube.com/live/iGDTiTfovwI",
        ],
    )
    def test_accepts_known_shapes(self, value):
        assert parse_video_id(value) == "iGDTiTfovwI"

    def test_rejects_garbage(self):
        with pytest.raises(TranscriptError):
            parse_video_id("https://example.com/not-a-video")


class TestParseVtt:
    def test_parses_cues_and_timestamps(self):
        vtt = """WEBVTT
Kind: captions
Language: en

00:00:01.000 --> 00:00:04.000
Hello there

00:01:05.500 --> 00:01:08.000
General Kenobi
"""
        segments = parse_vtt(vtt)
        assert [s.text for s in segments] == ["Hello there", "General Kenobi"]
        assert segments[0].start == 1.0
        assert segments[1].formatted_time == "1:05"

    def test_collapses_rolling_window_repeats(self):
        vtt = """WEBVTT

00:00:01.000 --> 00:00:02.000
the quick brown

00:00:02.000 --> 00:00:03.000
the quick brown fox

00:00:03.000 --> 00:00:04.000
the quick brown fox
"""
        assert [s.text for s in parse_vtt(vtt)] == ["the quick brown fox"]

    def test_strips_inline_tags(self):
        vtt = """WEBVTT

00:00:01.000 --> 00:00:02.000
<c.colorE5E5E5>hello</c> <00:00:01.500>world
"""
        assert parse_vtt(vtt)[0].text == "hello world"

    def test_empty_input_raises(self):
        with pytest.raises(TranscriptError):
            parse_vtt("WEBVTT\n")


class TestSegment:
    def test_from_upstream_shape(self):
        seg = Segment.from_upstream(
            {"time": 65.0, "text": "  spaced  ", "formatted_time": "1:05"}
        )
        assert seg.start == 65.0
        assert seg.text == "spaced"
        assert seg.formatted_time == "1:05"

    def test_from_youtube_transcript_api_shape(self):
        # Older rows use `start` and carry no formatted_time.
        seg = Segment.from_upstream({"start": 3661.0, "text": "x"})
        assert seg.start == 3661.0
        assert seg.formatted_time == "1:01:01"


def test_to_text_joins_and_collapses_whitespace():
    segments = [Segment(0, "one"), Segment(1, "two  three")]
    assert to_text(segments) == "one two three"
