"""Worker 앱 빌드 스크립트.

사용법:
  Windows: python worker/build.py --os windows
  Mac:     python worker/build.py --os mac

필요: pip install pyinstaller
"""
import subprocess
import sys
import platform


def build():
    os_type = platform.system().lower()

    name = "hydra-worker"
    if os_type == "windows":
        name += ".exe"

    sep = ";" if os_type == "windows" else ":"

    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--onefile",
        "--name", "hydra-worker",
        "--add-data", f"worker/config.py{sep}worker/",
        "worker/__main__.py",
    ]

    print(f"Building for {os_type}...")
    subprocess.run(cmd, check=True)
    print(f"\nBuild complete: dist/{name}")
    print("배포: dist/ 폴더의 파일을 Worker PC에 복사하세요.")


if __name__ == "__main__":
    build()
