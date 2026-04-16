"""Worker 연결 토큰 생성. 사용법: python scripts/generate_worker_token.py --name "PC-1" """
import argparse
from hydra.db.session import SessionLocal
from hydra.services.worker_service import register_worker

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--name", required=True)
    args = parser.parse_args()
    db = SessionLocal()
    worker, token = register_worker(db, args.name)
    db.close()
    print(f"Worker '{worker.name}' registered (ID: {worker.id})")
    print(f"Token: {token}")
    print("이 토큰은 다시 표시되지 않습니다.")

if __name__ == "__main__":
    main()
