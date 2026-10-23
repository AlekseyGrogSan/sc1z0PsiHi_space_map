import io
import pytest
from PIL import Image

from app.services.image_ops import image_service

def create_sample_equirectangular_image(width: int = 400, height: int = 200) -> bytes:
    """Генерирует тестовое синтетическое изображение панорамы с соотношением 2:1."""
    img = Image.new("RGB", (width, height), color=(73, 109, 137))
    for x in range(width):
        for y in range(height):
            img.putpixel((x, y), (int(255 * x / width), int(255 * y / height), 128))
    stream = io.BytesIO()
    img.save(stream, format="JPEG")
    return stream.getvalue()

def test_inspect_dimensions():
    sample_bytes = create_sample_equirectangular_image(800, 400)
    w, h = image_service.inspect_dimensions(sample_bytes)
    assert w == 800
    assert h == 400

def test_compute_blurhash():
    sample_bytes = create_sample_equirectangular_image(200, 100)
    bhash = image_service.compute_blurhash(sample_bytes)
    assert isinstance(bhash, str)
    assert len(bhash) > 5

def test_generate_preview_webp():
    sample_bytes = create_sample_equirectangular_image(1600, 800)
    preview_bytes = image_service.generate_preview_webp(sample_bytes, max_width=1024, max_height=512)
    assert len(preview_bytes) > 0

    with Image.open(io.BytesIO(preview_bytes)) as preview_img:
        assert preview_img.format == "WEBP"
        assert preview_img.width <= 1024
        assert preview_img.height <= 512

def test_generate_thumbnail_webp():
    sample_bytes = create_sample_equirectangular_image(400, 200)
    thumb_bytes = image_service.generate_thumbnail_webp(sample_bytes, max_width=200, max_height=100)
    assert len(thumb_bytes) > 0

    with Image.open(io.BytesIO(thumb_bytes)) as thumb_img:
        assert thumb_img.format == "WEBP"
        assert thumb_img.width <= 200
        assert thumb_img.height <= 100

def test_slice_equirectangular_to_cubemap():
    sample_bytes = create_sample_equirectangular_image(256, 128)
    cubemap_faces = image_service.slice_equirectangular_to_cubemap(sample_bytes, face_size=64)

    expected_faces = ["f", "b", "u", "d", "l", "r"]
    assert set(cubemap_faces.keys()) == set(expected_faces)

    for face, face_bytes in cubemap_faces.items():
        assert len(face_bytes) > 0
        with Image.open(io.BytesIO(face_bytes)) as f_img:
            assert f_img.format == "WEBP"
            assert f_img.size == (64, 64)

def test_stitch_frames_fallback():
    # Проверка устойчивости: передача недостаточного количества кадров
    success, res, msg = image_service.stitch_frames_opencv([b"fake_frame"])
    assert success is False
    assert res is None
