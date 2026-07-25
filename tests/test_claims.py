from deepcheck.claims import anchor_claim, chunk_segments, prioritize
from deepcheck.models import Claim, Segment


def make_segments(n, words=10):
    return [
        Segment(start=float(i), text=" ".join(f"w{i}-{j}" for j in range(words)))
        for i in range(n)
    ]


class TestChunking:
    def test_splits_on_word_budget(self):
        chunks = chunk_segments(make_segments(10, words=10), chunk_words=25)
        assert len(chunks) > 1
        assert sum(len(c) for c in chunks) == 10

    def test_single_chunk_when_under_budget(self):
        assert len(chunk_segments(make_segments(3), chunk_words=1000)) == 1

    def test_empty_input(self):
        assert chunk_segments([], chunk_words=100) == []

    def test_oversized_segment_is_not_dropped(self):
        segments = [Segment(0, " ".join("x" for _ in range(500)))]
        chunks = chunk_segments(segments, chunk_words=10)
        assert sum(len(c) for c in chunks) == 1


class TestAnchoring:
    def setup_method(self):
        self.chunk = [
            Segment(0.0, "Crime is down eighty eight percent in the capital", "0:00"),
            Segment(30.0, "We removed over five thousand career criminals", "0:30"),
        ]

    def test_exact_substring(self):
        found = anchor_claim("down eighty eight percent", self.chunk)
        assert found is not None and found.start == 0.0

    def test_case_and_punctuation_insensitive(self):
        found = anchor_claim("Down Eighty-Eight Percent!", self.chunk)
        assert found is not None and found.start == 0.0

    def test_fuzzy_fallback_for_asr_drift(self):
        found = anchor_claim("we removed over 5000 career criminals", self.chunk)
        assert found is not None and found.start == 30.0

    def test_unrelated_quote_returns_none(self):
        assert anchor_claim("zebra quantum harpsichord tuesday", self.chunk) is None

    def test_empty_quote_returns_none(self):
        assert anchor_claim("", self.chunk) is None


class TestPrioritize:
    def _claims(self, checkabilities):
        return [
            Claim(id=f"c{i}", text=f"t{i}", quote="", checkability=c)
            for i, c in enumerate(checkabilities)
        ]

    def test_keeps_most_checkable(self):
        claims = self._claims(["low", "high", "low", "high"])
        kept = prioritize(claims, 2)
        assert [c.checkability for c in kept] == ["high", "high"]

    def test_preserves_transcript_order(self):
        claims = self._claims(["high", "low", "high"])
        kept = prioritize(claims, 2)
        assert [c.id for c in kept] == ["c0", "c2"]

    def test_no_op_when_under_limit(self):
        claims = self._claims(["high", "low"])
        assert prioritize(claims, 10) == claims

    def test_zero_limit_disables_trimming(self):
        claims = self._claims(["high", "low"])
        assert prioritize(claims, 0) == claims
