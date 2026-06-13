"""Cloudflare R2 object storage (S3-compatible) via boto3.

A single client is created lazily from SampaiSettings. R2 is addressed with the
account endpoint + bucket; uploads are private and downloads use presigned URLs.
"""

from __future__ import annotations

import asyncio
import functools
from dataclasses import dataclass

import boto3
from botocore.config import Config

from lightrag.api.sampai.config import SampaiSettings

_client = None
_bucket: str | None = None
_presign_ttl: int = 3600


def init_r2(settings: SampaiSettings) -> None:
    """Create the global R2 client (idempotent)."""
    global _client, _bucket, _presign_ttl
    if _client is not None:
        return
    _bucket = settings.r2_bucket
    _presign_ttl = settings.r2_presign_ttl
    _client = boto3.client(
        "s3",
        endpoint_url=settings.r2_endpoint.rstrip("/"),
        aws_access_key_id=settings.r2_access_key_id,
        aws_secret_access_key=settings.r2_secret_access_key,
        region_name="auto",
        config=Config(signature_version="s3v4", retries={"max_attempts": 3}),
    )


def _require():
    if _client is None:
        raise RuntimeError("R2 not initialized — call init_r2() in lifespan startup")
    return _client, _bucket


@dataclass
class R2Object:
    key: str
    url: str  # canonical object URL (citation key); access is via presigned GET


def object_url(key: str) -> str:
    _, bucket = _require()
    settings = SampaiSettings.load()
    return f"{settings.r2_endpoint.rstrip('/')}/{bucket}/{key}"


async def _to_thread(fn, *args, **kwargs):
    return await asyncio.to_thread(functools.partial(fn, *args, **kwargs))


async def put_object(key: str, body: bytes, content_type: str | None = None) -> R2Object:
    client, bucket = _require()
    kwargs = {"Bucket": bucket, "Key": key, "Body": body}
    if content_type:
        kwargs["ContentType"] = content_type
    await _to_thread(client.put_object, **kwargs)
    return R2Object(key=key, url=object_url(key))


async def get_bytes(key: str) -> bytes:
    client, bucket = _require()
    resp = await _to_thread(client.get_object, Bucket=bucket, Key=key)
    return await _to_thread(resp["Body"].read)


async def delete_object(key: str) -> None:
    client, bucket = _require()
    await _to_thread(client.delete_object, Bucket=bucket, Key=key)


async def presigned_get_url(key: str, expires: int | None = None) -> str:
    client, bucket = _require()
    return await _to_thread(
        client.generate_presigned_url,
        "get_object",
        Params={"Bucket": bucket, "Key": key},
        ExpiresIn=expires or _presign_ttl,
    )


async def healthcheck() -> bool:
    """Best-effort: list the bucket (HeadBucket) to confirm creds/endpoint."""
    client, bucket = _require()
    try:
        await _to_thread(client.head_bucket, Bucket=bucket)
        return True
    except Exception:
        return False
