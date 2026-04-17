"""Worker 초기 설정 — 환경 검증 + 서버 연결."""
import sys
import os
import platform
import subprocess
import shutil
from worker.config import WorkerConfig


def setup():
    print("=" * 50)
    print("  HYDRA Worker 설정")
    print(f"  OS: {platform.system()} {platform.machine()}")
    print("=" * 50)

    config = WorkerConfig()
    errors = []

    # 1. Python 버전 체크
    py_ver = sys.version_info
    print(f"\n[1/5] Python 버전: {py_ver.major}.{py_ver.minor}.{py_ver.micro}", end=" ")
    if py_ver >= (3, 11):
        print("✅")
    else:
        print("❌ (3.11 이상 필요)")
        errors.append("Python 3.11 이상이 필요합니다")

    # 2. AdsPower 연결 테스트
    print("[2/5] AdsPower 연결:", end=" ")
    adspower_url = input(f"\n  AdsPower API URL [{config.adspower_api_url}]: ").strip()
    if not adspower_url:
        adspower_url = config.adspower_api_url
    try:
        import httpx
        resp = httpx.get(f"{adspower_url}/status", timeout=5)
        if resp.status_code == 200:
            print("  ✅ AdsPower 연결됨")
            config.adspower_api_url = adspower_url
        else:
            print("  ❌ AdsPower 응답 없음")
            errors.append("AdsPower가 실행 중인지 확인하세요")
    except Exception:
        print("  ❌ AdsPower 연결 실패")
        errors.append(f"AdsPower에 연결할 수 없습니다 ({adspower_url})")

    # 3. ADB 확인
    print("[3/5] ADB:", end=" ")
    adb_path = shutil.which("adb")
    if adb_path:
        print(f"✅ ({adb_path})")
        try:
            result = subprocess.run(["adb", "devices"], capture_output=True, text=True, timeout=5)
            devices = [l for l in result.stdout.strip().split("\n")[1:] if l.strip() and "device" in l]
            if devices:
                device_id = devices[0].split("\t")[0]
                print(f"  디바이스: {device_id}")
                config.adb_device_id = device_id
            else:
                print("  ⚠️ 연결된 디바이스 없음 (USB 테더링 연결 후 다시 시도)")
        except Exception:
            print("  ⚠️ ADB 디바이스 확인 실패")
    else:
        print("❌ ADB를 찾을 수 없습니다")
        errors.append("ADB를 설치하세요 (Android Platform Tools)")

    # 4. 서버 연결
    print("[4/5] 서버 연결:", end=" ")
    server_url = input(f"\n  서버 주소 [{config.server_url}]: ").strip()
    if not server_url:
        server_url = config.server_url

    token = input("  연결 토큰: ").strip()
    if not token:
        print("  ❌ 토큰을 입력해주세요")
        errors.append("연결 토큰이 필요합니다")
    else:
        try:
            import httpx
            resp = httpx.post(
                f"{server_url}/api/workers/heartbeat",
                headers={"X-Worker-Token": token},
                json={"version": "0.1.0", "os_type": platform.system().lower()},
                timeout=10,
            )
            if resp.status_code == 200:
                print(f"  ✅ 서버 연결 성공 ({server_url})")
                config.server_url = server_url
                config.worker_token = token
            elif resp.status_code == 401:
                print("  ❌ 토큰이 유효하지 않습니다")
                errors.append("토큰이 올바른지 확인하세요")
            else:
                print(f"  ❌ 서버 응답 오류 ({resp.status_code})")
                errors.append("서버에 연결할 수 없습니다")
        except Exception as e:
            print(f"  ❌ 서버 연결 실패: {e}")
            errors.append(f"서버에 연결할 수 없습니다 ({server_url})")

    # 5. 결과
    print(f"\n[5/5] 결과:")
    if errors:
        print("  ❌ 문제가 있습니다:")
        for e in errors:
            print(f"     - {e}")
        print("\n  문제를 해결한 후 다시 실행해주세요.")
    else:
        config.save()
        print("  ✅ 모든 준비 완료!")
        print(f"  설정 저장됨: {config.config_path}")
        print(f"\n  Worker 시작: python -m worker")


if __name__ == "__main__":
    setup()
