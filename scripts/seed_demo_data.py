import asyncio
import io
import uuid
from PIL import Image
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

import sys
from pathlib import Path

# Добавляем корень проекта в sys.path, чтобы скрипт можно было запускать любым способом:
# python scripts/seed_demo_data.py или docker compose exec api python scripts/seed_demo_data.py
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.core.config import settings
from app.core.database import async_session_factory
from app.core.security import hash_password
from app.models.floor import Floor
from app.models.panorama import Panorama, PanoramaHotspot
from app.models.space import Space, SpaceMember, SpaceRole
from app.models.user import SystemRole, User
from app.services.image_ops import image_service
from app.services.s3 import s3_service

async def seed():
    print("🌱 Запуск сидера демонстрационных данных...")
    assets_dir = Path(__file__).resolve().parent.parent / "demo_assets"
    plan_path = assets_dir / "floor_1_plan.png"
    pano_path = assets_dir / "hall_360_panorama.jpg"

    with open(plan_path, "rb") as f:
        plan_bytes = f.read()

    with open(pano_path, "rb") as f:
        pano_bytes = f.read()

    # Инициализация бакетов S3
    await s3_service.ensure_buckets_exist()

    async with async_session_factory() as db:
        # 1. Проверяем или создаем пользователя-организатора
        stmt = select(User).where(User.email == "demo@ttk.ru")
        user = (await db.execute(stmt)).scalar_one_or_none()
        if not user:
            user = User(
                email="demo@ttk.ru",
                hashed_password=hash_password("DemoPassword123!"),
                full_name="Организатор ТТК",
                system_role=SystemRole.ORGANIZER,
                is_active=True,
            )
            db.add(user)
            await db.flush()
            print("👤 Создан демо-пользователь: demo@ttk.ru / DemoPassword123!")

        # 2. Проверяем или создаем Пространство
        stmt = select(Space).where(Space.slug == "ttk-conf-2026")
        space = (await db.execute(stmt)).scalar_one_or_none()
        if not space:
            space = Space(
                title="IT-Конференция ТТК 2026",
                slug="ttk-conf-2026",
                description="Главный выставочный павильон и конференц-залы ТТК",
                is_published=True,
                settings={"theme": "dark", "accent_color": "#e30613"},
            )
            db.add(space)
            await db.flush()

            member = SpaceMember(
                space_id=space.id,
                user_id=user.id,
                role=SpaceRole.OWNER,
            )
            db.add(member)
            print(f"🏢 Создано пространство: {space.title} (slug: {space.slug})")

        # 3. Создаем 1 Этаж и загружаем план в MinIO
        stmt = select(Floor).where(Floor.space_id == space.id, Floor.floor_number == 1)
        floor = (await db.execute(stmt)).scalar_one_or_none()
        if not floor:
            floor_id = uuid.uuid4()
            plan_opt_key = f"floors/{floor_id}/plan/optimized.webp"
            plan_thumb_key = f"floors/{floor_id}/plan/thumb.webp"

            # Оптимизируем и заливаем в MinIO
            opt_plan_webp = image_service.generate_optimized_floor_plan(plan_bytes)
            thumb_plan_webp = image_service.generate_thumbnail_webp(plan_bytes)

            await s3_service.put_bytes(settings.S3_BUCKET_PUBLIC, plan_opt_key, opt_plan_webp, "image/webp")
            await s3_service.put_bytes(settings.S3_BUCKET_PUBLIC, plan_thumb_key, thumb_plan_webp, "image/webp")

            floor = Floor(
                id=floor_id,
                space_id=space.id,
                floor_number=1,
                title="1 этаж (Экспозона и Конференц-зал)",
                plan_original_key=plan_opt_key,
                plan_optimized_key=plan_opt_key,
                width_px=2000,
                height_px=1200,
                ppm=20.0,
            )
            db.add(floor)
            await db.flush()
            print("🗺️ 2D-план этажа успешно сохранен в PostgreSQL и MinIO!")

        # 4. Создаем 360-панораму в холле и загружаем в MinIO
        stmt = select(Panorama).where(Panorama.floor_id == floor.id)
        pano = (await db.execute(stmt)).scalar_one_or_none()
        if not pano:
            pano_id = uuid.uuid4()
            bhash = image_service.compute_blurhash(pano_bytes)
            preview_webp = image_service.generate_preview_webp(pano_bytes)
            cubemap_faces = image_service.slice_equirectangular_to_cubemap(pano_bytes, face_size=512)

            preview_key = f"panoramas/{pano_id}/preview.webp"
            orig_key = f"panoramas/{pano_id}/original.jpg"
            cubemap_prefix = f"panoramas/{pano_id}/cubemap"

            await s3_service.put_bytes(settings.S3_BUCKET_PUBLIC, orig_key, pano_bytes, "image/jpeg")
            await s3_service.put_bytes(settings.S3_BUCKET_PUBLIC, preview_key, preview_webp, "image/webp")
            for face, f_bytes in cubemap_faces.items():
                await s3_service.put_bytes(
                    settings.S3_BUCKET_PUBLIC, f"{cubemap_prefix}/l1/{face}_0_0.webp", f_bytes, "image/webp"
                )

            pano = Panorama(
                id=pano_id,
                floor_id=floor.id,
                title="Главный вход и Ресепшн",
                x_coord=380.0,
                y_coord=900.0,
                initial_heading=180.0,
                status="ready",
                blurhash=bhash,
                preview_key=preview_key,
                original_key=orig_key,
                cubemap_prefix=cubemap_prefix,
            )
            db.add(pano)
            print("📸 360° Панорама успешно обработана, нарезана на Cubemap и залита в MinIO!")

        await db.commit()
        print("✅ Все демо-данные успешно загружены! Можно тестировать API и фронтенд.")

if __name__ == "__main__":
    asyncio.run(seed())
