import pytest
from collections import Counter
from hydra.browser.fingerprint_bundle import (
    build_fingerprint_payload,
    WINDOWS_GPU_POOL,
    APPLE_GPU_POOL,
    WINDOWS_KO_FONTS,
    MAC_KO_FONTS,
)


REQUIRED_TOP_KEYS = {
    "random_ua", "browser_kernel_config", "screen_resolution",
    "hardware_concurrency", "device_memory",
    "automatic_timezone", "timezone", "language_switch", "language",
    "location_switch", "webrtc",
    "canvas", "webgl_image", "audio", "client_rects",
    "webgl", "webgl_config", "fonts",
    "device_name_switch", "mac_address_config",
    "media_devices", "media_devices_num", "speech_switch", "scan_port_type",
}


@pytest.mark.parametrize("hint", ["windows_heavy", "windows_10_heavy", "mac_heavy", "mixed"])
def test_payload_has_required_top_keys(hint):
    p = build_fingerprint_payload(hint)
    missing = REQUIRED_TOP_KEYS - set(p.keys())
    assert not missing, f"Missing keys: {missing}"


def test_common_constants_are_fixed():
    p = build_fingerprint_payload("windows_heavy")
    assert p["timezone"] == "Asia/Seoul"
    assert p["language"] == ["ko-KR", "ko", "en-US", "en"]
    assert p["webrtc"] == "disabled"
    assert p["device_name_switch"] == "1"
    assert p["mac_address_config"] == {"model": "1"}
    assert p["browser_kernel_config"] == {"version": "ua_auto", "type": "chrome"}


def test_windows_heavy_uses_windows_ua_and_gpu():
    for _ in range(100):
        p = build_fingerprint_payload("windows_heavy")
        os_versions = p["random_ua"]["ua_system_version"]
        for v in os_versions:
            assert v.startswith("Windows"), f"Got non-Windows UA: {v}"
        vendor = p["webgl_config"]["unmasked_vendor"]
        assert "Apple" not in vendor, f"Windows bundle got Apple GPU: {vendor}"


def test_windows_10_heavy_locks_to_windows_10():
    for _ in range(50):
        p = build_fingerprint_payload("windows_10_heavy")
        assert p["random_ua"]["ua_system_version"] == ["Windows 10"]


def test_mac_heavy_uses_mac_ua_and_apple_gpu():
    for _ in range(100):
        p = build_fingerprint_payload("mac_heavy")
        os_versions = p["random_ua"]["ua_system_version"]
        for v in os_versions:
            assert v.startswith("Mac"), f"Got non-Mac UA: {v}"
        vendor = p["webgl_config"]["unmasked_vendor"]
        assert vendor == "Google Inc. (Apple)"
        renderer = p["webgl_config"]["unmasked_renderer"]
        assert "Apple M" in renderer, f"Got non-Apple renderer: {renderer}"


def test_mac_heavy_uses_mac_fonts():
    p = build_fingerprint_payload("mac_heavy")
    assert "Apple SD Gothic Neo" in p["fonts"]
    assert "AppleGothic" in p["fonts"]
    assert "Malgun Gothic" not in p["fonts"]


def test_windows_heavy_uses_windows_fonts():
    p = build_fingerprint_payload("windows_heavy")
    assert "Malgun Gothic" in p["fonts"]
    assert "Gulim" in p["fonts"]
    assert "Apple SD Gothic Neo" not in p["fonts"]


def test_mixed_rolls_between_windows_and_mac():
    os_kinds = Counter()
    for _ in range(400):
        p = build_fingerprint_payload("mixed")
        os_versions = p["random_ua"]["ua_system_version"]
        if os_versions[0].startswith("Windows"):
            os_kinds["win"] += 1
        elif os_versions[0].startswith("Mac"):
            os_kinds["mac"] += 1
    win_ratio = os_kinds["win"] / 400
    assert 0.42 <= win_ratio <= 0.58, f"win ratio {win_ratio} outside 42-58%"


def test_unknown_device_hint_raises():
    with pytest.raises(ValueError):
        build_fingerprint_payload("android_heavy")


def test_screen_resolution_format():
    p = build_fingerprint_payload("windows_heavy")
    parts = p["screen_resolution"].split("_")
    assert len(parts) == 2
    assert all(x.isdigit() for x in parts)


def test_media_devices_num_within_range():
    for _ in range(50):
        p = build_fingerprint_payload("windows_heavy")
        m = p["media_devices_num"]
        assert 1 <= int(m["audioinput_num"]) <= 2
        assert int(m["videoinput_num"]) == 1
        assert 1 <= int(m["audiooutput_num"]) <= 2


def test_gpu_pools_are_nonempty_and_weighted():
    assert len(WINDOWS_GPU_POOL) >= 5
    assert len(APPLE_GPU_POOL) >= 3
    for entry in WINDOWS_GPU_POOL + APPLE_GPU_POOL:
        assert len(entry) == 3
        vendor, renderer, weight = entry
        assert isinstance(vendor, str) and vendor
        assert isinstance(renderer, str) and renderer
        assert isinstance(weight, int) and weight > 0


def test_hardware_concurrency_is_string_digit():
    p = build_fingerprint_payload("windows_heavy")
    assert p["hardware_concurrency"] in {"2", "4", "6", "8", "16"}


def test_device_memory_max_is_8():
    for _ in range(30):
        p = build_fingerprint_payload("mac_heavy")
        assert p["device_memory"] in {"2", "4", "6", "8"}


def test_webgl_config_has_webgpu():
    p = build_fingerprint_payload("windows_heavy")
    assert p["webgl"] == "2"
    assert "webgpu" in p["webgl_config"]
    assert p["webgl_config"]["webgpu"] == {"webgpu_switch": "1"}
