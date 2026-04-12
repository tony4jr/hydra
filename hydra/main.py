"""
HYDRA — YouTube Comment Marketing Bot
Entry point
"""

from hydra.db.database import init_db


def main():
    print("🐍 HYDRA starting...")

    # 1. Initialize database
    engine = init_db()

    # 2. System health check
    health_check()

    print("✅ HYDRA ready.")


def health_check():
    """Check all external dependencies on startup."""
    checks = {
        "Database": check_db,
        "AdsPower": check_adspower,
        "Internet": check_internet,
    }

    for name, check_fn in checks.items():
        try:
            check_fn()
            print(f"  ✅ {name}")
        except Exception as e:
            print(f"  ❌ {name}: {e}")


def check_db():
    from hydra.db.database import get_session
    session = get_session()
    session.execute("SELECT 1")
    session.close()


def check_adspower():
    import httpx
    try:
        r = httpx.get("http://local.adspower.net:50325/api/v1/browser/active", timeout=3)
        if r.status_code != 200:
            raise Exception(f"Status {r.status_code}")
    except httpx.ConnectError:
        raise Exception("AdsPower not running")


def check_internet():
    import httpx
    httpx.get("https://www.youtube.com", timeout=5)


if __name__ == "__main__":
    main()
