"""Worker 초기 설정 — 서버 주소와 토큰 입력."""
import sys
from worker.config import config


def setup():
    print("=" * 40)
    print("  HYDRA Worker 설정")
    print("=" * 40)

    server_url = input("\n서버 주소 (예: http://your-server:8000): ").strip()
    if not server_url:
        print("서버 주소를 입력해주세요.")
        sys.exit(1)

    token = input("연결 토큰: ").strip()
    if not token:
        print("토큰을 입력해주세요.")
        sys.exit(1)

    config.server_url = server_url
    config.worker_token = token
    config.save()

    print(f"\n설정 저장됨: {config.config_path}")
    print("Worker를 시작하려면: python -m worker")


if __name__ == "__main__":
    setup()
