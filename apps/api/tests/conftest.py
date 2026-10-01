from __future__ import annotations

import os
import shutil
import tempfile
from pathlib import Path

import pytest

_TMP = Path(tempfile.mkdtemp(prefix="vai-tests-"))
os.environ.update(
    {
        "ENVIRONMENT": "test",
        "DATABASE_URL": os.environ.get("TEST_DATABASE_URL", f"sqlite:///{_TMP / 'test.db'}"),
        "LOCAL_STORAGE_PATH": str(_TMP / "storage"),
        "JOB_BACKEND": "sync",
        "ADMIN_EMAILS": "admin@example.com",
        "SECRET_KEY": "test-secret-key-0123456789-0123456789-abcdef",
        "AI_ROUTING": "{}",
        "ANTHROPIC_API_KEY": "",
        "RATE_LIMIT_AUTH_PER_MINUTE": "1000",
        "RATE_LIMIT_UPLOADS_PER_MINUTE": "1000",
    }
)


@pytest.fixture(scope="session")
def app():
    from app.main import create_app

    return create_app()


@pytest.fixture()
def client(app):
    from fastapi.testclient import TestClient

    from app.core.security import rate_limiter

    rate_limiter.reset()
    with TestClient(app, base_url="http://testserver") as c:
        yield c


@pytest.fixture(scope="session")
def jpeg_bytes():
    import io

    from PIL import Image

    from app.imaging.synthetic import make_scene

    img, _ = make_scene("hoodie", 600, 800, seed=7)
    buf = io.BytesIO()
    Image.fromarray(img).save(buf, "JPEG", quality=90)
    return buf.getvalue()


def pytest_sessionfinish(session, exitstatus):
    shutil.rmtree(_TMP, ignore_errors=True)
