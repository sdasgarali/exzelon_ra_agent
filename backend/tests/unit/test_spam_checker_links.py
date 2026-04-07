"""Tests for spam checker link/image ratio detection."""
import pytest
from app.services.spam_checker import check_spam_score


pytestmark = pytest.mark.unit


class TestLinkDetection:
    """Test link counting and penalty."""

    def test_no_links_no_penalty(self):
        result = check_spam_score("Hello", "<p>Just plain text email content here.</p>")
        link_flags = [f for f in result["flagged_words"] if "link" in f["word"].lower()]
        assert len(link_flags) == 0

    def test_two_links_ok(self):
        body = '<p>Check out <a href="https://example.com">our site</a> and <a href="https://docs.example.com">docs</a>.</p>'
        result = check_spam_score("Hello", body)
        link_flags = [f for f in result["flagged_words"] if "links" in f["word"].lower()]
        assert len(link_flags) == 0

    def test_three_links_flagged(self):
        body = '<p><a href="a">1</a> <a href="b">2</a> <a href="c">3</a></p>'
        result = check_spam_score("Hello", body)
        link_flags = [f for f in result["flagged_words"] if "links" in f["word"].lower()]
        assert len(link_flags) > 0

    def test_many_links_high_penalty(self):
        body = '<p>' + ' '.join(f'<a href="url{i}">link{i}</a>' for i in range(6)) + '</p>'
        result = check_spam_score("Hello", body)
        link_flags = [f for f in result["flagged_words"] if "links" in f["word"].lower()]
        assert link_flags[0]["severity"] == "high"


class TestImageDetection:
    """Test image counting and penalty."""

    def test_no_images_ok(self):
        result = check_spam_score("Hello", "<p>Text only email.</p>")
        img_flags = [f for f in result["flagged_words"] if "image" in f["word"].lower()]
        assert len(img_flags) == 0

    def test_one_image_flagged(self):
        body = '<p>Check this <img src="logo.png" alt="logo">.</p>'
        result = check_spam_score("Hello", body)
        img_flags = [f for f in result["flagged_words"] if "image" in f["word"].lower()]
        assert len(img_flags) > 0

    def test_multiple_images_higher_penalty(self):
        body = '<p><img src="a.png"><img src="b.png"><img src="c.png"></p>'
        result = check_spam_score("Hello", body)
        img_flags = [f for f in result["flagged_words"] if "image" in f["word"].lower()]
        assert img_flags[0]["count"] == 3


class TestLinkToTextRatio:
    """Test high link-to-text ratio detection."""

    def test_short_text_with_links_flagged(self):
        body = '<p>Hi! <a href="a">Click here</a> <a href="b">and here</a></p>'
        result = check_spam_score("Hello", body)
        ratio_flags = [f for f in result["flagged_words"] if "link-to-text" in f["word"].lower()]
        assert len(ratio_flags) > 0

    def test_long_text_with_links_ok(self):
        # 100 words + 2 links should be fine
        words = " ".join([f"word{i}" for i in range(100)])
        body = f'<p>{words} <a href="a">link1</a> <a href="b">link2</a></p>'
        result = check_spam_score("Hello", body)
        ratio_flags = [f for f in result["flagged_words"] if "link-to-text" in f["word"].lower()]
        assert len(ratio_flags) == 0
