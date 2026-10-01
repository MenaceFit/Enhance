"""Object storage backends (S3 tested against moto's in-memory S3)."""

from __future__ import annotations

import time
from types import SimpleNamespace
from urllib.parse import parse_qs, urlparse

import pytest

from app.core.storage import LocalStorage, S3Storage


def test_local_storage_signing_and_isolation(tmp_path):
    st = LocalStorage(tmp_path, "secret-0123456789-0123456789-0123", "/api/v1", 60)
    st.put("users/a/photos/p/x.webp", b"data")
    url = st.signed_url("users/a/photos/p/x.webp", download_name="vinted_ai_01.jpg")
    q = parse_qs(urlparse(url).query)
    assert st.verify("users/a/photos/p/x.webp", int(q["exp"][0]), q["sig"][0], q["dl"][0])
    assert not st.verify("users/b/photos/p/x.webp", int(q["exp"][0]), q["sig"][0], q["dl"][0])  # key bound
    assert not st.verify("users/a/photos/p/x.webp", int(q["exp"][0]), q["sig"][0], "other.jpg")  # name bound
    assert not st.verify("users/a/photos/p/x.webp", int(time.time()) - 1, q["sig"][0], q["dl"][0])  # expiry
    with pytest.raises(ValueError):
        st.put("../escape.txt", b"x")
    assert st.delete_prefix("users/a/") == 1 and not st.exists("users/a/photos/p/x.webp")


def test_s3_storage_roundtrip_and_public_signing():
    moto = pytest.importorskip("moto")
    import boto3

    with moto.mock_aws():
        boto3.client("s3", region_name="us-east-1").create_bucket(Bucket="vai")
        cfg = SimpleNamespace(
            s3_bucket="vai", s3_server_side_encryption="AES256", signed_url_ttl_seconds=300,
            s3_endpoint_url=None, s3_public_endpoint_url="https://files.example.com", s3_region="us-east-1",
            s3_access_key_id="test", s3_secret_access_key="test",
        )
        st = S3Storage(cfg)
        st.put("users/u1/photos/p1/a.webp", b"a", "image/webp")
        st.put("users/u1/photos/p1/b.webp", b"b")
        st.put("users/u2/photos/p9/c.webp", b"c")
        assert st.get("users/u1/photos/p1/a.webp") == b"a" and st.exists("users/u1/photos/p1/b.webp")
        head = st.client.head_object(Bucket="vai", Key="users/u1/photos/p1/a.webp")
        assert head["ServerSideEncryption"] == "AES256" and head["ContentType"] == "image/webp"
        st.copy("users/u1/photos/p1/a.webp", "users/u1/photos/p1/copy.webp")
        assert st.get("users/u1/photos/p1/copy.webp") == b"a"
        url = st.signed_url("users/u1/photos/p1/a.webp", download_name="vinted_ai_01.jpg")
        assert url.startswith("https://files.example.com/") and "response-content-disposition" in url
        assert st.delete_prefix("users/u1/") == 3
        assert not st.exists("users/u1/photos/p1/a.webp") and st.exists("users/u2/photos/p9/c.webp")
