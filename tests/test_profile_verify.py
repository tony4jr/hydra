"""T11 UA/플랫폼 검증 테스트."""
from worker.profile_verify import compare_ua, extract_chrome_version, _extract_platform


def test_extract_chrome_version():
    ua = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/144.0.7559.60 Safari/537.36"
    assert extract_chrome_version(ua) == 144


def test_extract_chrome_version_none_for_invalid():
    assert extract_chrome_version("") is None
    assert extract_chrome_version(None) is None
    assert extract_chrome_version("Mozilla/5.0 Safari") is None


def test_extract_platform_mac():
    ua = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)"
    assert _extract_platform(ua) == "Macintosh; Intel Mac OS X 10_15_7"


def test_compare_ua_match():
    intended = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) Chrome/144.0.0 Safari/537.36"
    runtime = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) Chrome/144.0.0 Safari/537.36"
    res = compare_ua(intended, runtime)
    assert res["match"] is True
    assert res["details"]["intended_chrome"] == 144
    assert res["details"]["runtime_chrome"] == 144


def test_compare_ua_chrome_mismatch():
    intended = "Mozilla/5.0 (Win) Chrome/144.0.0"
    runtime = "Mozilla/5.0 (Win) Chrome/120.0.0"  # 의도와 다름
    res = compare_ua(intended, runtime)
    assert res["match"] is False
    assert res["details"]["chrome_version_match"] is False


def test_compare_ua_platform_mismatch():
    intended = "Mozilla/5.0 (Windows NT 10.0; Win64) Chrome/144.0.0"
    runtime = "Mozilla/5.0 (Macintosh) Chrome/144.0.0"  # 플랫폼 다름
    res = compare_ua(intended, runtime)
    assert res["match"] is False
    assert res["details"]["platform_match"] is False


def test_compare_ua_handles_missing_runtime():
    intended = "Chrome/144.0"
    res = compare_ua(intended, "")
    assert res["match"] is False
