"""페르소나 device_hint 기반 AdsPower fingerprint_config 번들 생성.

찐 사람다움을 위해 OS↔GPU↔폰트↔해상도↔코어 가 현실적 조합으로 묶이도록
가중 랜덤 선택. 매 호출이 독립적이며 외부 상태 없음 (순수 함수).
"""

import random

# ─── GPU pools (vendor, renderer, weight) ────────────────────────────

WINDOWS_GPU_POOL = [
    ("Google Inc. (Intel)",
     "ANGLE (Intel, Intel(R) UHD Graphics 620 Direct3D11 vs_5_0 ps_5_0, D3D11)", 25),
    ("Google Inc. (Intel)",
     "ANGLE (Intel, Intel(R) UHD Graphics 630 Direct3D11 vs_5_0 ps_5_0, D3D11)", 20),
    ("Google Inc. (Intel)",
     "ANGLE (Intel, Intel(R) Iris(R) Xe Graphics Direct3D11 vs_5_0 ps_5_0, D3D11)", 15),
    ("Google Inc. (NVIDIA)",
     "ANGLE (NVIDIA, NVIDIA GeForce RTX 3060 Direct3D11 vs_5_0 ps_5_0, D3D11)", 15),
    ("Google Inc. (NVIDIA)",
     "ANGLE (NVIDIA, NVIDIA GeForce GTX 1660 Direct3D11 vs_5_0 ps_5_0, D3D11)", 10),
    ("Google Inc. (AMD)",
     "ANGLE (AMD, AMD Radeon RX 6600 Direct3D11 vs_5_0 ps_5_0, D3D11)", 10),
    ("Google Inc. (NVIDIA)",
     "ANGLE (NVIDIA, NVIDIA GeForce RTX 4060 Direct3D11 vs_5_0 ps_5_0, D3D11)", 5),
]

APPLE_GPU_POOL = [
    ("Google Inc. (Apple)",
     "ANGLE (Apple, ANGLE Metal Renderer: Apple M1, Unspecified Version)", 30),
    ("Google Inc. (Apple)",
     "ANGLE (Apple, ANGLE Metal Renderer: Apple M2, Unspecified Version)", 35),
    ("Google Inc. (Apple)",
     "ANGLE (Apple, ANGLE Metal Renderer: Apple M3, Unspecified Version)", 25),
    ("Google Inc. (Apple)",
     "ANGLE (Apple, ANGLE Metal Renderer: Apple M1 Pro, Unspecified Version)", 10),
]

# ─── Font lists ──────────────────────────────────────────────────────

WINDOWS_KO_FONTS = [
    "Malgun Gothic", "Malgun Gothic Semilight",
    "Gulim", "GulimChe", "Dotum", "DotumChe",
    "Batang", "BatangChe", "Gungsuh", "GungsuhChe",
    "Arial", "Arial Black", "Calibri", "Cambria", "Consolas",
    "Courier New", "Georgia", "Impact", "Segoe UI",
    "Tahoma", "Times New Roman", "Trebuchet MS", "Verdana",
]

MAC_KO_FONTS = [
    "Apple SD Gothic Neo", "AppleGothic", "AppleMyungjo", "PilGi",
    "Apple Color Emoji", "Apple Symbols",
    "Helvetica", "Helvetica Neue", "Lucida Grande",
    "Menlo", "Monaco", "SF Pro", "Times New Roman", "Arial",
]

# ─── Common (all bundles) ────────────────────────────────────────────

COMMON_FP = {
    "browser_kernel_config": {"version": "ua_auto", "type": "chrome"},
    "automatic_timezone": "0",
    "timezone": "Asia/Seoul",
    "language_switch": "0",
    "language": ["ko-KR", "ko", "en-US", "en"],
    "location_switch": "1",
    "webrtc": "disabled",
    "canvas": "1",
    "webgl_image": "1",
    "audio": "1",
    "client_rects": "1",
    "webgl": "2",
    "device_name_switch": "1",
    "mac_address_config": {"model": "1"},
    "media_devices": "2",
    "speech_switch": "1",
    "scan_port_type": "1",
}


def _weighted_pick(pool):
    total = sum(w for _, _, w in pool)
    r = random.uniform(0, total)
    acc = 0
    for vendor, renderer, weight in pool:
        acc += weight
        if r <= acc:
            return vendor, renderer
    vendor, renderer, _ = pool[-1]
    return vendor, renderer


def _random_media_counts():
    return {
        "audioinput_num": str(random.randint(1, 2)),
        "videoinput_num": "1",
        "audiooutput_num": str(random.randint(1, 2)),
    }


def _weighted_choice(items, weights):
    return random.choices(items, weights=weights, k=1)[0]


def _build_windows_heavy() -> dict:
    ua_versions = _weighted_choice(
        [["Windows 10"], ["Windows 11"]], [50, 50]
    )
    vendor, renderer = _weighted_pick(WINDOWS_GPU_POOL)
    return {
        **COMMON_FP,
        "random_ua": {"ua_system_version": ua_versions},
        "screen_resolution": _weighted_choice(
            ["1920_1080", "2560_1440", "1366_768"], [55, 25, 20]
        ),
        "hardware_concurrency": _weighted_choice(["4", "6", "8"], [20, 30, 50]),
        "device_memory": _weighted_choice(["4", "8"], [30, 70]),
        "webgl_config": {
            "unmasked_vendor": vendor,
            "unmasked_renderer": renderer,
            "webgpu": {"webgpu_switch": "1"},
        },
        "fonts": list(WINDOWS_KO_FONTS),
        "media_devices_num": _random_media_counts(),
    }


def _build_windows_10_heavy() -> dict:
    vendor, renderer = _weighted_pick(WINDOWS_GPU_POOL)
    return {
        **COMMON_FP,
        "random_ua": {"ua_system_version": ["Windows 10"]},
        "screen_resolution": _weighted_choice(
            ["1920_1080", "1366_768"], [70, 30]
        ),
        "hardware_concurrency": _weighted_choice(["2", "4"], [30, 70]),
        "device_memory": _weighted_choice(["4", "8"], [50, 50]),
        "webgl_config": {
            "unmasked_vendor": vendor,
            "unmasked_renderer": renderer,
            "webgpu": {"webgpu_switch": "1"},
        },
        "fonts": list(WINDOWS_KO_FONTS),
        "media_devices_num": _random_media_counts(),
    }


def _build_mac_heavy() -> dict:
    ua_versions = _weighted_choice(
        [["Mac OS X 14"], ["Mac OS X 15"]], [40, 60]
    )
    vendor, renderer = _weighted_pick(APPLE_GPU_POOL)
    return {
        **COMMON_FP,
        "random_ua": {"ua_system_version": ua_versions},
        "screen_resolution": _weighted_choice(
            ["1440_900", "1680_1050", "2560_1440", "2880_1800"],
            [25, 20, 25, 30],
        ),
        "hardware_concurrency": _weighted_choice(["8", "16"], [60, 40]),
        "device_memory": "8",
        "webgl_config": {
            "unmasked_vendor": vendor,
            "unmasked_renderer": renderer,
            "webgpu": {"webgpu_switch": "1"},
        },
        "fonts": list(MAC_KO_FONTS),
        "media_devices_num": _random_media_counts(),
    }


def build_fingerprint_payload(device_hint: str) -> dict:
    """Build AdsPower fingerprint_config dict from a persona device_hint.

    Valid hints: "windows_heavy", "windows_10_heavy", "mac_heavy", "mixed".
    """
    if device_hint == "windows_heavy":
        return _build_windows_heavy()
    if device_hint == "windows_10_heavy":
        return _build_windows_10_heavy()
    if device_hint == "mac_heavy":
        return _build_mac_heavy()
    if device_hint == "mixed":
        return random.choice([_build_windows_heavy, _build_mac_heavy])()
    raise ValueError(f"Unknown device_hint: {device_hint}")
