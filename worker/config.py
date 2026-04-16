"""Worker 설정. 환경 변수 또는 config 파일에서 로드."""
import os
from pathlib import Path


class WorkerConfig:
    def __init__(self):
        self.server_url = os.getenv("HYDRA_SERVER_URL", "http://localhost:8000")
        self.worker_token = os.getenv("HYDRA_WORKER_TOKEN", "")
        self.heartbeat_interval = int(os.getenv("HYDRA_HEARTBEAT_INTERVAL", "30"))
        self.task_fetch_interval = int(os.getenv("HYDRA_TASK_FETCH_INTERVAL", "5"))
        self.max_concurrent_tasks = int(os.getenv("HYDRA_MAX_CONCURRENT", "3"))
        self.worker_version = "0.1.0"
        self.config_path = Path.home() / ".hydra-worker" / "config.json"

    def save(self):
        """설정을 파일에 저장."""
        import json
        self.config_path.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "server_url": self.server_url,
            "worker_token": self.worker_token,
        }
        self.config_path.write_text(json.dumps(data, indent=2))

    def load(self):
        """파일에서 설정 로드."""
        import json
        if self.config_path.exists():
            data = json.loads(self.config_path.read_text())
            self.server_url = data.get("server_url", self.server_url)
            self.worker_token = data.get("worker_token", self.worker_token)


config = WorkerConfig()
