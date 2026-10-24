import io
import logging
import math
from typing import Dict, List, Optional, Tuple
from PIL import Image

try:
    import blurhash
    HAS_BLURHASH = True
except ImportError:
    HAS_BLURHASH = False

try:
    import cv2
    import numpy as np
    HAS_OPENCV = True
except ImportError:
    HAS_OPENCV = False

try:
    import pypdfium2 as pdfium
    HAS_PDFIUM = True
except ImportError:
    HAS_PDFIUM = False

logger = logging.getLogger(__name__)

class ImageProcessingService:
    @staticmethod
    def inspect_dimensions(image_bytes: bytes) -> Tuple[int, int]:
        """Возвращает (width, height) изображения."""
        with Image.open(io.BytesIO(image_bytes)) as img:
            return img.width, img.height

    @staticmethod
    def render_plan_to_bytes(file_bytes: bytes, filename: str = "", page_index: int = 0) -> Tuple[bytes, int, int]:
        """
        Преобразует входной файл (PNG, JPG, WebP или PDF) в растровые байты RGB и возвращает (bytes, width, height).
        Для PDF рендерит указанную страницу (по умолчанию 0) в высоком разрешении.
        """
        if filename.lower().endswith(".pdf") or file_bytes.startswith(b"%PDF"):
            if not HAS_PDFIUM:
                raise ValueError("Поддержка PDF не активна: библиотека pypdfium2 не установлена")
            pdf = pdfium.PdfDocument(file_bytes)
            if page_index >= len(pdf):
                raise ValueError(f"Страница {page_index + 1} не найдена в PDF документе (всего страниц: {len(pdf)})")
            page = pdf[page_index]
            # scale=2.5 обеспечивает отличную детализацию чертежа (~2400x1500 px для стандартного A4/A3)
            pil_image = page.render(scale=2.5).to_pil().convert("RGB")
            out = io.BytesIO()
            pil_image.save(out, format="PNG")
            png_bytes = out.getvalue()
            return png_bytes, pil_image.width, pil_image.height

        with Image.open(io.BytesIO(file_bytes)) as img:
            rgb_img = img.convert("RGB")
            out = io.BytesIO()
            rgb_img.save(out, format="PNG")
            return out.getvalue(), rgb_img.width, rgb_img.height

    @staticmethod
    def compute_blurhash(image_bytes: bytes, x_components: int = 4, y_components: int = 3) -> str:
        """
        Вычисляет BlurHash строку изображения для мгновенного превью на фронтенде без белого экрана.
        """
        if not HAS_BLURHASH:
            # Fallback BlurHash если библиотека не установлена
            return "LEHLh[WB2yk8pyoJadR*.7kCMdnj"

        try:
            with Image.open(io.BytesIO(image_bytes)) as img:
                # Ресайз до миниатюры для быстрого вычисления хэша
                img_small = img.convert("RGB").resize((64, 32), Image.Resampling.BILINEAR)
                hash_str = blurhash.encode(img_small, x_components=x_components, y_components=y_components)
                return hash_str
        except Exception as e:
            logger.warning(f"Ошибка вычисления BlurHash: {e}")
            return "LEHLh[WB2yk8pyoJadR*.7kCMdnj"

    @staticmethod
    def generate_preview_webp(
        image_bytes: bytes, max_width: int = 1024, max_height: int = 512, quality: int = 80
    ) -> bytes:
        """
        Создает оптимизированное превью панорамы в формате WebP (~50-80 КБ).
        """
        with Image.open(io.BytesIO(image_bytes)) as img:
            img = img.convert("RGB")
            img.thumbnail((max_width, max_height), Image.Resampling.LANCZOS)
            output = io.BytesIO()
            img.save(output, format="WEBP", quality=quality, method=4)
            return output.getvalue()

    @staticmethod
    def generate_thumbnail_webp(
        image_bytes: bytes, max_width: int = 300, max_height: int = 200, quality: int = 75
    ) -> bytes:
        """Миниатюра для иконки/карточки."""
        with Image.open(io.BytesIO(image_bytes)) as img:
            img = img.convert("RGB")
            img.thumbnail((max_width, max_height), Image.Resampling.BILINEAR)
            output = io.BytesIO()
            img.save(output, format="WEBP", quality=quality)
            return output.getvalue()

    @staticmethod
    def generate_optimized_floor_plan(image_bytes: bytes, max_size: int = 2048, quality: int = 85) -> bytes:
        """Конвертирует 2D-план этажа в оптимизированный WebP."""
        with Image.open(io.BytesIO(image_bytes)) as img:
            img = img.convert("RGB")
            if img.width > max_size or img.height > max_size:
                img.thumbnail((max_size, max_size), Image.Resampling.LANCZOS)
            output = io.BytesIO()
            img.save(output, format="WEBP", quality=quality)
            return output.getvalue()

    @staticmethod
    def slice_equirectangular_to_cubemap(image_bytes: bytes, face_size: int = 512) -> Dict[str, bytes]:
        """
        Нарезает 360-эквидистантную панораму на 6 граней куба:
        f (front), b (back), u (up), d (down), l (left), r (right).
        Используется библиотеками Marzipano / Pannellum для плавного вращения на смартфонах.
        """
        faces = ["f", "b", "u", "d", "l", "r"]
        result = {}

        with Image.open(io.BytesIO(image_bytes)) as img:
            img = img.convert("RGB")
            w, h = img.size

            # Математическая проекция пикселей куба в сферу
            for face in faces:
                face_img = Image.new("RGB", (face_size, face_size))
                pixels = face_img.load()

                for y in range(face_size):
                    for x in range(face_size):
                        # Нормализация в диапазон [-1, 1]
                        nx = (x + 0.5) / (face_size / 2.0) - 1.0
                        ny = (y + 0.5) / (face_size / 2.0) - 1.0

                        if face == "f":   # front (+Z)
                            vx, vy, vz = nx, -ny, 1.0
                        elif face == "b": # back (-Z)
                            vx, vy, vz = -nx, -ny, -1.0
                        elif face == "l": # left (-X)
                            vx, vy, vz = -1.0, -ny, nx
                        elif face == "r": # right (+X)
                            vx, vy, vz = 1.0, -ny, -nx
                        elif face == "u": # up (+Y)
                            vx, vy, vz = nx, 1.0, ny
                        elif face == "d": # down (-Y)
                            vx, vy, vz = nx, -1.0, -ny

                        # В сферические координаты
                        r = math.sqrt(vx * vx + vy * vy + vz * vz)
                        theta = math.atan2(vx, vz)      # [-pi, pi]
                        phi = math.asin(vy / r)         # [-pi/2, pi/2]

                        # В координаты исходного эквидистантного изображения
                        uf = (theta / (2.0 * math.pi) + 0.5) * w
                        vf = (0.5 - phi / math.pi) * h

                        ui = int(uf) % w
                        vi = max(0, min(h - 1, int(vf)))

                        pixels[x, y] = img.getpixel((ui, vi))

                out_stream = io.BytesIO()
                face_img.save(out_stream, format="WEBP", quality=80)
                result[face] = out_stream.getvalue()

        return result

    @staticmethod
    def stitch_frames_opencv(frames_bytes: List[bytes]) -> Tuple[bool, Optional[bytes], str]:
        """
        Сшивает серию снимков со смартфона в круговую панораму через OpenCV Stitcher.
        """
        if not HAS_OPENCV:
            logger.warning("OpenCV не установлен, сшивка невозможна.")
            return False, None, "OpenCV is not installed"

        if len(frames_bytes) < 2:
            return False, None, "Need at least 2 frames to stitch"

        images = []
        for b in frames_bytes:
            arr = np.frombuffer(b, dtype=np.uint8)
            img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
            if img is not None:
                images.append(img)

        if len(images) < 2:
            return False, None, "Failed to decode input frames"

        try:
            stitcher = cv2.Stitcher_create(cv2.Stitcher_PANORAMA)
            status, stitched = stitcher.stitch(images)

            if status == cv2.Stitcher_OK:
                success, encoded = cv2.imencode(".webp", stitched, [int(cv2.IMWRITE_WEBP_QUALITY), 85])
                if success:
                    return True, encoded.tobytes(), "OK"
                return False, None, "Failed to encode stitched result to WebP"
            else:
                status_messages = {
                    cv2.Stitcher_ERR_NEED_MORE_IMGS: "Need more overlapping frames",
                    cv2.Stitcher_ERR_HOMOGRAPHY_EST_FAIL: "Homography estimation failed (not enough matching features)",
                    cv2.Stitcher_ERR_CAMERA_PARAMS_ADJUST_FAIL: "Camera parameters adjustment failed",
                }
                msg = status_messages.get(status, f"Stitcher error code {status}")
                return False, None, msg
        except Exception as e:
            logger.error(f"Исключение при сшивке панорамы: {e}")
            return False, None, str(e)

image_service = ImageProcessingService()
