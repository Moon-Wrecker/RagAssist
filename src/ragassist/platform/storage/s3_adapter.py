"""S3 and in-memory object store adapters.

Sources consulted (AGENTS.md rule 3.5):
- aioboto3 docs / README: clients are created with ``async with session.client(...)``; ``endpoint_url``
  redirects to LocalStack; ``response["Body"]`` is an aiohttp stream read with ``async with`` + ``await read()``.
  Credentials and region are accepted by ``aioboto3.Session``. This adapter follows that pattern.
"""

import io
from typing import Any

try:
    import aioboto3
except (ImportError, ModuleNotFoundError, Exception):
    aioboto3 = None

from ragassist.platform.storage.ports import ObjectStore
from ragassist.shared.config.settings import Settings, get_settings


class S3ObjectStore(ObjectStore):
    """Adapter for AWS S3 and LocalStack S3 storage."""

    def __init__(self, settings: Settings | None = None) -> None:
        if aioboto3 is None:
            raise RuntimeError("aioboto3 is required for S3ObjectStore")
        self.settings = settings or get_settings()
        self.bucket = self.settings.S3_BUCKET_DOCS
        self.session = aioboto3.Session(
            aws_access_key_id=self.settings.AWS_ACCESS_KEY_ID,
            aws_secret_access_key=self.settings.AWS_SECRET_ACCESS_KEY,
            region_name=self.settings.AWS_REGION,
        )

    def _get_client_kwargs(self) -> dict[str, Any]:
        kwargs: dict[str, Any] = {}
        if self.settings.USE_LOCALSTACK and self.settings.LOCALSTACK_ENDPOINT:
            kwargs["endpoint_url"] = self.settings.LOCALSTACK_ENDPOINT
        return kwargs

    async def put_object(
        self,
        key: str,
        data: bytes,
        content_type: str = "application/octet-stream",
        metadata: dict[str, str] | None = None,
    ) -> str:
        async with self.session.client("s3", **self._get_client_kwargs()) as s3:
            extra_args: dict[str, Any] = {"ContentType": content_type}
            if metadata:
                extra_args["Metadata"] = metadata
            await s3.put_object(
                Bucket=self.bucket,
                Key=key,
                Body=data,
                **extra_args,
            )
            return f"s3://{self.bucket}/{key}"

    async def get_object(self, key: str) -> bytes:
        async with self.session.client("s3", **self._get_client_kwargs()) as s3:
            response = await s3.get_object(Bucket=self.bucket, Key=key)
            async with response["Body"] as stream:
                return await stream.read()

    async def delete_object(self, key: str) -> bool:
        async with self.session.client("s3", **self._get_client_kwargs()) as s3:
            await s3.delete_object(Bucket=self.bucket, Key=key)
            return True


class InMemoryObjectStore(ObjectStore):
    """In-memory object store for tests and fast offline execution."""

    def __init__(self) -> None:
        self._storage: dict[str, tuple[bytes, str, dict[str, str]]] = {}

    async def put_object(
        self,
        key: str,
        data: bytes,
        content_type: str = "application/octet-stream",
        metadata: dict[str, str] | None = None,
    ) -> str:
        self._storage[key] = (data, content_type, metadata or {})
        return f"mem://{key}"

    async def get_object(self, key: str) -> bytes:
        if key not in self._storage:
            raise KeyError(f"Object not found: {key}")
        return self._storage[key][0]

    async def delete_object(self, key: str) -> bool:
        if key in self._storage:
            del self._storage[key]
            return True
        return False

