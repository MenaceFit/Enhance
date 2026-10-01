"""Private object storage with short-lived signed URLs.

* ``LocalStorage`` — files on disk, served by ``GET /files/...`` only with a
  valid HMAC signature and expiry (development, single-node deployments).
* ``S3Storage`` — any S3-compatible service (AWS S3, Cloudflare R2, MinIO),
  presigned GET URLs, server-side encryption, private bucket.

Keys are always namespaced ``users/{user_id}/...``: users are isolated and an
account is erased with a single prefix deletion.
"""

from __future__ import annotations

import hashlib
import hmac
import mimetypes
import shutil
import time
from abc import ABC, abstractmethod
from functools import lru_cache
from pathlib import Path
from urllib.parse import quote, urlencode

from app.core.config import get_settings


class Storage(ABC):
    @abstractmethod
    def put(self, key: str, data: bytes, content_type: str | None = None) -> None: ...

    @abstractmethod
    def get(self, key: str) -> bytes: ...

    @abstractmethod
    def exists(self, key: str) -> bool: ...

    @abstractmethod
    def delete(self, key: str) -> None: ...

    @abstractmethod
    def delete_prefix(self, prefix: str) -> int: ...

    @abstractmethod
    def signed_url(self, key: str, ttl: int | None = None, download_name: str | None = None) -> str: ...

    def copy(self, src: str, dst: str) -> None:
        self.put(dst, self.get(src), mimetypes.guess_type(dst)[0])


def _sign(secret: str, key: str, exp: int, dl: str) -> str:
    msg = f"{key}\n{exp}\n{dl}".encode()
    return hmac.new(secret.encode(), msg, hashlib.sha256).hexdigest()[:40]


class LocalStorage(Storage):
    def __init__(self, root: Path, secret: str, api_prefix: str, default_ttl: int):
        self.root = root.resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self.secret = secret
        self.api_prefix = api_prefix
        self.default_ttl = default_ttl

    def _path(self, key: str) -> Path:
        p = (self.root / key).resolve()
        if self.root not in p.parents and p != self.root:
            raise ValueError("invalid storage key")
        return p

    def put(self, key, data, content_type=None):
        p = self._path(key)
        p.parent.mkdir(parents=True, exist_ok=True)
        tmp = p.with_suffix(p.suffix + ".tmp")
        tmp.write_bytes(data)
        tmp.replace(p)

    def get(self, key):
        return self._path(key).read_bytes()

    def exists(self, key):
        return self._path(key).is_file()

    def delete(self, key):
        self._path(key).unlink(missing_ok=True)

    def delete_prefix(self, prefix):
        p = self._path(prefix.rstrip("/"))
        if p.is_dir():
            n = sum(1 for _ in p.rglob("*") if _.is_file())
            shutil.rmtree(p, ignore_errors=True)
            return n
        if p.is_file():
            p.unlink()
            return 1
        return 0

    def signed_url(self, key, ttl=None, download_name=None):
        exp = int(time.time()) + (ttl or self.default_ttl)
        dl = download_name or ""
        params = {"exp": exp, "sig": _sign(self.secret, key, exp, dl)}
        if dl:
            params["dl"] = dl
        return f"{self.api_prefix}/files/{quote(key)}?{urlencode(params)}"

    def verify(self, key: str, exp: int, sig: str, dl: str = "") -> bool:
        if exp < time.time():
            return False
        return hmac.compare_digest(_sign(self.secret, key, exp, dl), sig)

    def path_for(self, key: str) -> Path:
        return self._path(key)


class S3Storage(Storage):
    def __init__(self, cfg):
        import boto3
        from botocore.config import Config

        self.bucket = cfg.s3_bucket
        self.sse = cfg.s3_server_side_encryption
        self.default_ttl = cfg.signed_url_ttl_seconds
        def make(endpoint):
            return boto3.client(
                "s3",
                endpoint_url=endpoint,
                region_name=cfg.s3_region,
                aws_access_key_id=cfg.s3_access_key_id,
                aws_secret_access_key=cfg.s3_secret_access_key,
                config=Config(signature_version="s3v4", retries={"max_attempts": 4, "mode": "standard"}),
            )

        self.client = make(cfg.s3_endpoint_url)
        # The signature covers the host: sign with the endpoint the *browser* will use.
        self.signer = make(cfg.s3_public_endpoint_url) if cfg.s3_public_endpoint_url else self.client

    def put(self, key, data, content_type=None):
        extra = {"ContentType": content_type or mimetypes.guess_type(key)[0] or "application/octet-stream"}
        if self.sse:
            extra["ServerSideEncryption"] = self.sse
        self.client.put_object(Bucket=self.bucket, Key=key, Body=data, **extra)

    def get(self, key):
        return self.client.get_object(Bucket=self.bucket, Key=key)["Body"].read()

    def exists(self, key):
        try:
            self.client.head_object(Bucket=self.bucket, Key=key)
            return True
        except Exception:
            return False

    def delete(self, key):
        self.client.delete_object(Bucket=self.bucket, Key=key)

    def delete_prefix(self, prefix):
        count = 0
        paginator = self.client.get_paginator("list_objects_v2")
        for page in paginator.paginate(Bucket=self.bucket, Prefix=prefix):
            objs = [{"Key": o["Key"]} for o in page.get("Contents", [])]
            for i in range(0, len(objs), 1000):
                self.client.delete_objects(Bucket=self.bucket, Delete={"Objects": objs[i : i + 1000], "Quiet": True})
                count += len(objs[i : i + 1000])
        return count

    def signed_url(self, key, ttl=None, download_name=None):
        params = {"Bucket": self.bucket, "Key": key}
        if download_name:
            params["ResponseContentDisposition"] = f'attachment; filename="{download_name}"'
        return self.signer.generate_presigned_url("get_object", Params=params, ExpiresIn=ttl or self.default_ttl)

    def copy(self, src, dst):
        extra = {"ServerSideEncryption": self.sse} if self.sse else {}
        self.client.copy_object(Bucket=self.bucket, Key=dst, CopySource={"Bucket": self.bucket, "Key": src}, **extra)


@lru_cache
def get_storage() -> Storage:
    cfg = get_settings()
    if cfg.storage_backend == "s3":
        return S3Storage(cfg)
    return LocalStorage(cfg.local_storage_path, cfg.secret_key, cfg.api_prefix, cfg.signed_url_ttl_seconds)


def user_prefix(user_id) -> str:
    return f"users/{user_id}/"


def renders_prefix(user_id, photo_id=None) -> str:
    """Temporary editor previews live under ``tmp/`` so that an object-storage lifecycle
    rule (expire after 1 day) cleans them up; erasure also deletes them immediately."""
    base = f"tmp/renders/{user_id}/"
    return f"{base}{photo_id}/" if photo_id else base
