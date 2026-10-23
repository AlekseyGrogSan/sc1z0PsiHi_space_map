import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from app.services.s3 import S3Service

@pytest.mark.asyncio
async def test_generate_presigned_put_url():
    service = S3Service()
    
    mock_s3_client = AsyncMock()
    mock_s3_client.generate_presigned_url = AsyncMock(
        return_value="https://minio.test/spaces-staging/panoramas/1/raw.jpg?sig=123"
    )

    mock_cm = AsyncMock()
    mock_cm.__aenter__.return_value = mock_s3_client
    mock_cm.__aexit__.return_value = None

    with patch.object(service, "_client", return_value=mock_cm):
        url = await service.generate_presigned_put_url(
            bucket="spaces-staging",
            key="panoramas/1/raw.jpg",
            content_type="image/jpeg",
            expires_in=600,
        )

        assert "https://minio.test/spaces-staging" in url
        mock_s3_client.generate_presigned_url.assert_called_once_with(
            ClientMethod="put_object",
            Params={
                "Bucket": "spaces-staging",
                "Key": "panoramas/1/raw.jpg",
                "ContentType": "image/jpeg",
            },
            ExpiresIn=600,
        )

@pytest.mark.asyncio
async def test_generate_presigned_get_url():
    service = S3Service()

    mock_s3_client = AsyncMock()
    mock_s3_client.generate_presigned_url = AsyncMock(
        return_value="https://minio.test/spaces-staging/file.jpg?sig=abc"
    )

    mock_cm = AsyncMock()
    mock_cm.__aenter__.return_value = mock_s3_client
    mock_cm.__aexit__.return_value = None

    with patch.object(service, "_client", return_value=mock_cm):
        url = await service.generate_presigned_get_url(
            bucket="spaces-staging",
            key="file.jpg",
            expires_in=1200,
        )

        assert "file.jpg" in url
        mock_s3_client.generate_presigned_url.assert_called_once_with(
            ClientMethod="get_object",
            Params={
                "Bucket": "spaces-staging",
                "Key": "file.jpg",
            },
            ExpiresIn=1200,
        )
