import json

import pytest

from deepcheck.models import Claim, Finding, Report, Source, Verdict, format_timestamp
from deepcheck.report import to_html, to_json, to_markdown


def make_report():
    findings = [
        Finding(
            claim=Claim(
                id="c001",
                text="Crime fell 88% in the capital.",
                quote="crime is down 88%",
                formatted_time="4:42",
                checkability="high",
            ),
            verdict=Verdict(
                rating="false",
                confidence="high",
                explanation="Homicides fell about 40%, not 88%.",
                correction="Homicides fell roughly 40%.",
                sources=[Source(title="City data", url="https://example.com/a")],
            ),
        ),
        Finding(
            claim=Claim(id="c002", text="The bill passed in March.", quote="passed"),
            verdict=Verdict(
                rating="true", confidence="medium", explanation="It did."
            ),
        ),
    ]
    return Report(
        video_id="abc12345678",
        video_url="https://www.youtube.com/watch?v=abc12345678",
        title="A Speech",
        checked_at="2026-07-25 10:00 UTC",
        word_count=11531,
        findings=findings,
        model="claude-opus-5",
        transcript_source="youtube-deepsummary",
    )


class TestOrdering:
    def test_false_sorts_before_true(self):
        ordered = make_report().sorted_findings()
        assert [f.verdict.rating for f in ordered] == ["false", "true"]

    def test_counts(self):
        counts = make_report().counts()
        assert counts["false"] == 1 and counts["true"] == 1
        assert counts["misleading"] == 0


class TestMarkdown:
    def test_includes_claim_correction_and_source(self):
        out = to_markdown(make_report())
        assert "Crime fell 88%" in out
        assert "**Correction:** Homicides fell roughly 40%." in out
        assert "[City data](https://example.com/a)" in out

    def test_includes_timestamp_when_anchored(self):
        assert "`[4:42]`" in to_markdown(make_report())


class TestJson:
    def test_roundtrips(self):
        data = json.loads(to_json(make_report()))
        assert data["word_count"] == 11531
        assert data["findings"][0]["verdict"]["rating"] == "false"
        assert data["counts"]["false"] == 1


class TestHtml:
    def test_is_self_contained(self):
        out = to_html(make_report())
        assert out.startswith("<!DOCTYPE html>")
        # No external requests of any kind.
        for marker in ["<script", "<link", "@import", "src="]:
            assert marker not in out

    def test_escapes_user_content(self):
        report = make_report()
        report.findings[0].claim.text = '<img onerror="x"> & "quoted"'
        out = to_html(report)
        assert "<img onerror" not in out
        assert "&lt;img" in out

    def test_supports_both_themes(self):
        out = to_html(make_report())
        assert "prefers-color-scheme: dark" in out
        assert '[data-theme="dark"]' in out


@pytest.mark.parametrize(
    "seconds,expected",
    [(0, "0:00"), (65, "1:05"), (3661, "1:01:01"), (None, "0:00"), ("bad", "")],
)
def test_format_timestamp(seconds, expected):
    assert format_timestamp(seconds) == expected
