"""Tests for content fingerprint module — similarity detection & entropy scoring."""
import pytest
from app.services.content_fingerprint import (
    compute_content_hash,
    compute_shingles,
    jaccard_similarity,
    compute_entropy_score,
)


pytestmark = pytest.mark.unit


class TestComputeContentHash:
    """Test content hashing with normalization."""

    def test_same_text_same_hash(self):
        h1 = compute_content_hash("Hello world!")
        h2 = compute_content_hash("Hello world!")
        assert h1 == h2

    def test_case_insensitive(self):
        h1 = compute_content_hash("Hello World")
        h2 = compute_content_hash("hello world")
        assert h1 == h2

    def test_strips_punctuation(self):
        h1 = compute_content_hash("Hello, world!")
        h2 = compute_content_hash("Hello world")
        assert h1 == h2

    def test_collapses_whitespace(self):
        h1 = compute_content_hash("Hello   world")
        h2 = compute_content_hash("Hello world")
        assert h1 == h2

    def test_different_text_different_hash(self):
        h1 = compute_content_hash("Hello world")
        h2 = compute_content_hash("Goodbye world")
        assert h1 != h2

    def test_returns_hex_string(self):
        result = compute_content_hash("test")
        assert isinstance(result, str)
        assert len(result) == 64  # SHA-256 hex


class TestComputeShingles:
    """Test word-level n-gram shingle generation."""

    def test_basic_shingles(self):
        shingles = compute_shingles("the quick brown fox jumps")
        assert "the quick brown" in shingles
        assert "quick brown fox" in shingles
        assert "brown fox jumps" in shingles

    def test_short_text(self):
        shingles = compute_shingles("hello world")
        assert len(shingles) == 1
        assert "hello world" in shingles

    def test_empty_text(self):
        shingles = compute_shingles("")
        assert len(shingles) == 0

    def test_strips_html(self):
        shingles = compute_shingles("<p>the quick brown fox</p>")
        assert "the quick brown" in shingles

    def test_custom_n(self):
        shingles = compute_shingles("a b c d e", n=2)
        assert "a b" in shingles
        assert "b c" in shingles

    def test_lowercases(self):
        shingles = compute_shingles("The Quick Brown Fox")
        assert "the quick brown" in shingles


class TestJaccardSimilarity:
    """Test Jaccard similarity computation."""

    def test_identical_sets(self):
        s = {"a", "b", "c"}
        assert jaccard_similarity(s, s) == 1.0

    def test_disjoint_sets(self):
        assert jaccard_similarity({"a", "b"}, {"c", "d"}) == 0.0

    def test_partial_overlap(self):
        sim = jaccard_similarity({"a", "b", "c"}, {"b", "c", "d"})
        assert abs(sim - 0.5) < 0.01  # 2/4 = 0.5

    def test_empty_sets(self):
        assert jaccard_similarity(set(), set()) == 0.0

    def test_one_empty(self):
        assert jaccard_similarity({"a"}, set()) == 0.0

    def test_subset(self):
        sim = jaccard_similarity({"a", "b"}, {"a", "b", "c"})
        assert abs(sim - 2 / 3) < 0.01


class TestComputeEntropyScore:
    """Test entropy-based content variability scoring."""

    def test_personalized_content_scores_higher(self):
        without = compute_entropy_score(
            "Meeting tomorrow",
            "Hi, I wanted to reach out about our product.",
        )
        with_personalization = compute_entropy_score(
            "Meeting tomorrow {{contact_first_name}}",
            "Hi {{contact_first_name}}, I wanted to reach out about our {{product}}.",
        )
        assert with_personalization["has_personalization"] is True
        assert with_personalization["score"] > without["score"]

    def test_returns_expected_keys(self):
        result = compute_entropy_score("Subject", "Body text here.")
        assert "subject_entropy" in result
        assert "body_entropy" in result
        assert "has_personalization" in result
        assert "score" in result

    def test_score_range(self):
        result = compute_entropy_score("Test subject", "Some body content.")
        assert 0 <= result["score"] <= 100

    def test_empty_content(self):
        result = compute_entropy_score("", "")
        assert result["score"] == 0
        assert result["subject_entropy"] == 0.0
        assert result["body_entropy"] == 0.0

    def test_repetitive_content_low_entropy(self):
        result = compute_entropy_score("aaaa", "aaaa aaaa aaaa")
        assert result["subject_entropy"] < 1.0

    def test_diverse_content_higher_entropy(self):
        result = compute_entropy_score(
            "Meeting with John at Acme Corp",
            "The quick brown fox jumps over the lazy dog near the river bank.",
        )
        assert result["body_entropy"] > 2.0

    def test_detects_jinja_placeholders(self):
        result = compute_entropy_score(
            "Hello {{name}}",
            "Dear {{name}}, your account at {{company}} is ready.",
        )
        assert result["has_personalization"] is True

    def test_detects_spintax(self):
        result = compute_entropy_score(
            "Subject",
            "This is a {great|wonderful|fantastic} opportunity.",
        )
        assert result["has_personalization"] is True
