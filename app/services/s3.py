import json
import logging
from typing import Optional
import aioboto3
from botocore.exceptions import ClientError

from app.core.config import settings

logger = logging.getLogger(__name__)

class S3Service:
    def __init__(self):
        self.endpoint_url = settings.S3_ENDPOINT
        self.access_key = settings.S3_ACCESS_KEY
        self.secret_key = settings.S3_SECRET_KEY
        self.region = settings.S3_REGION
        self.public_bucket = settings.S3_BUCKET_PUBLIC
        self.staging_bucket = settings.S3_BUCKET_STAGING
        self.session = aioboto3.Session()

    def _client(self):
        return self.session.client(
            "s3",
            endpoint_url=self.endpoint_url,
            aws_access_key_id=self.access_key,
            aws_secret_access_key=self.secret_key,
            region_name=self.region,
        )

    async def ensure_buckets_exist(self) -> None:
        """Создает необходимые бакеты при старте сервиса и настраивает публичную политику чтения."""
        async with self._client() as s3:
            for bucket_name in [self.public_bucket, self.staging_bucket]:
                try:
                    await s3.head_bucket(Bucket=bucket_name)
                    logger.info(f"S3 Бакет '{bucket_name}' существует.")
                except ClientError as e:
                    error_code = e.response.get("Error", {}).get("Code")
                    if error_code in ["404", "NoSuchBucket"]:
                        logger.info(f"Создание S3 бакета '{bucket_name}'...")
                        await s3.create_bucket(Bucket=bucket_name)
                    else:
                        logger.warning(f"Ошибка проверки бакета '{bucket_name}': {e}")

            # Публичная политика для spaces-public (анонимное чтение)
            public_policy = {
                "Version": "2012-10-17",
                "Statement": [
                    {
                        "Sid": "PublicReadGetObject",
                        "Effect": "Allow",
                        "Principal": "*",
                        "Action": "s3:GetObject",
                        "Resource": f"arn:aws:s3:::{self.public_bucket}/*",
                    }
                ],
            }
            try:
                await s3.put_bucket_policy(Bucket=self.public_bucket, Policy=json.dumps(public_policy))
                logger.info(f"Публичная политика чтения для '{self.public_bucket}' успешно настроена.")
            except Exception as e:
                logger.warning(f"Не удалось применить публичную политику к бакету '{self.public_bucket}': {e}")

    async def generate_presigned_put_url(
        self, bucket: str, key: str, content_type: str = "image/jpeg", expires_in: int = 900
    ) -> str:
        """Генерирует временную ссылку для ПРЯМОЙ загрузки клиентом в MinIO (минуя FastAPI)."""
        async with self._client() as s3:
            return await s3.generate_presigned_url(
                ClientMethod="put_object",
                Params={
                    "Bucket": bucket,
                    "Key": key,
                    "ContentType": content_type,
                },
                ExpiresIn=expires_in,
            )

    async def generate_presigned_get_url(self, bucket: str, key: str, expires_in: int = 3600) -> str:
        """Генерирует временную ссылку для чтения приватного объекта."""
        async with self._client() as s3:
            return await s3.generate_presigned_url(
                ClientMethod="get_object",
                Params={
                    "Bucket": bucket,
                    "Key": key,
                },
                ExpiresIn=expires_in,
            )

    async def put_bytes(self, bucket: str, key: str, data: bytes, content_type: str = "image/webp") -> None:
        """Загрузка байтов объекта в MinIO."""
        async with self._client() as s3:
            await s3.put_object(
                Bucket=bucket,
                Key=key,
                Body=data,
                ContentType=content_type,
                CacheControl="public, max-age=31536000, immutable" if bucket == self.public_bucket else None,
            )

    async def get_bytes(self, bucket: str, key: str) -> bytes:
        """Чтение байтов объекта из MinIO."""
        async with self._client() as s3:
            response = await s3.get_object(Bucket=bucket, Key=key)
            async with response["Body"] as stream:
                return await stream.read()

    async def delete_object(self, bucket: str, key: str) -> None:
        """Удаление объекта."""
        async with self._client() as s3:
            await s3.delete_object(Bucket=bucket, Key=key)

    async def copy_object(self, source_bucket: str, source_key: str, dest_bucket: str, dest_key: str) -> None:
        """Копирование объекта между бакетами."""
        async with self._client() as s3:
            copy_source = {"Bucket": source_bucket, "Key": source_key}
            await s3.copy_object(CopySource=copy_source, Bucket=dest_bucket, Key=dest_key)

s3_service = S3Service()
