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
        DEMO_LAYOUT = {
            "rooms": [
                {"id": "room-hall", "title": "Входная группа и Регистрация", "x": 50, "y": 50, "width": 650, "height": 450, "color": "#e9ecef"},
                {"id": "room-conf", "title": "Конференц-зал «ТрансТелеКом»", "x": 1200, "y": 50, "width": 750, "height": 500, "color": "#dee2e6"},
                {"id": "room-expo", "title": "Экспозиционный зал", "x": 50, "y": 550, "width": 1350, "height": 600, "color": "#ffffff"},
                {"id": "room-lounge", "title": "Кофе-брейк & Лаундж Зона", "x": 1450, "y": 800, "width": 500, "height": 350, "color": "#feeedf"},
                {"id": "room-wc", "title": "Санузлы (WC)", "x": 1450, "y": 600, "width": 250, "height": 150, "color": "#eef2f6"},
                {"id": "room-lobby", "title": "Центральный холл и Эскалаторы", "x": 700, "y": 50, "width": 500, "height": 500, "color": "#f8f9fa"},
                {"id": "stand-1", "title": "Стенд #1: ТТК Цифровые Сервисы", "x": 150, "y": 880, "width": 300, "height": 170, "color": "#d1e7dd"},
                {"id": "stand-2", "title": "Стенд #2: IoT и Умный Город", "x": 550, "y": 880, "width": 300, "height": 170, "color": "#e2e3e5"},
                {"id": "stand-3", "title": "Стенд #3: Индор-Навигация", "x": 950, "y": 880, "width": 350, "height": 170, "color": "#cff4fc"},
                {"id": "stand-4", "title": "Стенд #4: Облачные Решения", "x": 150, "y": 630, "width": 300, "height": 170, "color": "#fff3cd"},
                {"id": "stand-5", "title": "Стенд #5: Кибербезопасность", "x": 550, "y": 630, "width": 300, "height": 170, "color": "#f8d7da"},
                {"id": "stand-6", "title": "Стенд #6: Партнерская Зона", "x": 950, "y": 630, "width": 350, "height": 170, "color": "#e2e3e5"},
            ],
            "obstacles": [
                {"id": "obs-stage", "type": "rect", "title": "Сцена Конференц-зала", "x": 1400, "y": 420, "width": 450, "height": 80},
                {"id": "obs-stairs", "type": "rect", "title": "Лестница и Лифты на 2 этаж", "x": 780, "y": 250, "width": 340, "height": 180},
            ],
            "walls": [
                {"x1": 50, "y1": 1150, "x2": 1950, "y2": 1150},
                {"x1": 1950, "y1": 50, "x2": 1950, "y2": 1150},
                {"x1": 50, "y1": 50, "x2": 300, "y2": 50},
                {"x1": 450, "y1": 50, "x2": 1950, "y2": 50},
                {"x1": 50, "y1": 50, "x2": 50, "y2": 1150},
                {"x1": 50, "y1": 500, "x2": 300, "y2": 500},
                {"x1": 440, "y1": 500, "x2": 700, "y2": 500},
                {"x1": 700, "y1": 50, "x2": 700, "y2": 260},
                {"x1": 700, "y1": 380, "x2": 700, "y2": 500},
                {"x1": 1200, "y1": 50, "x2": 1200, "y2": 260},
                {"x1": 1200, "y1": 380, "x2": 1200, "y2": 550},
                {"x1": 1400, "y1": 550, "x2": 1400, "y2": 800},
                {"x1": 1400, "y1": 900, "x2": 1400, "y2": 1150},
                {"x1": 1450, "y1": 780, "x2": 1950, "y2": 780},
                {"x1": 1450, "y1": 580, "x2": 1950, "y2": 580},
            ],
            "corridors": [
                {"x1": 375, "y1": 50, "x2": 375, "y2": 550, "width": 60},
                {"x1": 650, "y1": 320, "x2": 750, "y2": 320, "width": 60},
                {"x1": 1150, "y1": 320, "x2": 1250, "y2": 320, "width": 60},
                {"x1": 1350, "y1": 850, "x2": 1450, "y2": 850, "width": 60},
            ],
        }

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
                layout_data=DEMO_LAYOUT,
            )
            db.add(floor)
            await db.flush()
            print("🗺️ 2D-план этажа успешно сохранен в PostgreSQL и MinIO!")
        else:
            # Актуализируем геометрию и размеры
            floor.layout_data = DEMO_LAYOUT
            floor.width_px = 2000
            floor.height_px = 1200
            floor.ppm = 20.0
            db.add(floor)
            await db.flush()
            print("📐 Векторная планировка демо-этажа (комнаты, стены, стенды) обновлена в PostgreSQL!")

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
                x_coord=375.0,
                y_coord=180.0,
                initial_heading=180.0,
                status="ready",
                blurhash=bhash,
                preview_key=preview_key,
                original_key=orig_key,
                cubemap_prefix=cubemap_prefix,
            )
            db.add(pano)
            print("📸 360° Панорама успешно обработана, нарезана на Cubemap и залита в MinIO!")

        # 5. Создаем демонстрационные POI (вход, стенды, конференц-зал, кофе, WC)
        from app.models.poi import POI, POICategory
        stmt = select(POI).where(POI.floor_id == floor.id)
        existing_pois = (await db.execute(stmt)).scalars().all()
        if not existing_pois:
            demo_pois = [
                POI(
                    id=uuid.uuid4(),
                    floor_id=floor.id,
                    title="Главный вход и Регистрация",
                    category=POICategory.ENTRANCE,
                    description="Входная зона для гостей и участников выставки",
                    x_coord=375.0,
                    y_coord=80.0,
                    panorama_id=pano.id if pano else None,
                ),
                POI(
                    id=uuid.uuid4(),
                    floor_id=floor.id,
                    title="Стенд #1: ТТК Цифровые Сервисы",
                    category=POICategory.STAND,
                    description="Магистральный интернет, приватные каналы связи и CDN",
                    x_coord=300.0,
                    y_coord=965.0,
                ),
                POI(
                    id=uuid.uuid4(),
                    floor_id=floor.id,
                    title="Стенд #2: IoT и Умный Город",
                    category=POICategory.STAND,
                    description="Решения для датчиков, транспорта и умных остановок",
                    x_coord=700.0,
                    y_coord=965.0,
                ),
                POI(
                    id=uuid.uuid4(),
                    floor_id=floor.id,
                    title="Стенд #3: Индор-Навигация",
                    category=POICategory.STAND,
                    description="Интерактивные 3D-карты, BLE-маяки и цифровые двойники помещений",
                    x_coord=1125.0,
                    y_coord=965.0,
                ),
                POI(
                    id=uuid.uuid4(),
                    floor_id=floor.id,
                    title="Стенд #4: Облачные Решения",
                    category=POICategory.STAND,
                    description="Облачные серверы, хранилища и SaaS-платформы",
                    x_coord=300.0,
                    y_coord=715.0,
                ),
                POI(
                    id=uuid.uuid4(),
                    floor_id=floor.id,
                    title="Стенд #5: Кибербезопасность",
                    category=POICategory.STAND,
                    description="Защита от DDoS, сетевые экраны и SOC",
                    x_coord=700.0,
                    y_coord=715.0,
                ),
                POI(
                    id=uuid.uuid4(),
                    floor_id=floor.id,
                    title="Стенд #6: Партнерская Зона",
                    category=POICategory.STAND,
                    description="Партнерские решения и интеграционные проекты",
                    x_coord=1125.0,
                    y_coord=715.0,
                ),
                POI(
                    id=uuid.uuid4(),
                    floor_id=floor.id,
                    title="Конференц-зал «ТрансТелеКом»",
                    category=POICategory.STAGE,
                    description="Главный зал на 250 мест, доклады и круглые столы",
                    x_coord=1600.0,
                    y_coord=350.0,
                ),
                POI(
                    id=uuid.uuid4(),
                    floor_id=floor.id,
                    title="Кофе-брейк & Лаундж Зона",
                    category=POICategory.FOOD,
                    description="Горячий кофе, чай, выпечка и зона для нетворкинга",
                    x_coord=1650.0,
                    y_coord=980.0,
                ),
                POI(
                    id=uuid.uuid4(),
                    floor_id=floor.id,
                    title="Санузлы (WC)",
                    category=POICategory.WC,
                    description="Мужские, женские и санузлы для МГН",
                    x_coord=1575.0,
                    y_coord=675.0,
                ),
            ]
            for p in demo_pois:
                db.add(p)
            await db.flush()
            print("📍 Добавлено 10 демонстрационных точек интереса (POI)!")
        else:
            demo_pois = existing_pois
            # Актуализируем координаты POI в залах и стендах
            for p in demo_pois:
                if "Стенд #1" in p.title:
                    p.x_coord, p.y_coord = 300.0, 965.0
                elif "Стенд #2" in p.title:
                    p.x_coord, p.y_coord = 700.0, 965.0
                elif "Стенд #3" in p.title:
                    p.x_coord, p.y_coord = 1125.0, 965.0
                elif "Стенд #4" in p.title:
                    p.x_coord, p.y_coord = 300.0, 715.0
                elif "Стенд #5" in p.title:
                    p.x_coord, p.y_coord = 700.0, 715.0
                elif "Стенд #6" in p.title:
                    p.x_coord, p.y_coord = 1125.0, 715.0
                elif "Конференц-зал" in p.title:
                    p.x_coord, p.y_coord = 1600.0, 350.0
                elif "Кофе" in p.title:
                    p.x_coord, p.y_coord = 1650.0, 980.0
                elif "Санузлы" in p.title:
                    p.x_coord, p.y_coord = 1575.0, 675.0
                elif "Главный вход" in p.title:
                    p.x_coord, p.y_coord = 375.0, 80.0
                db.add(p)
            await db.flush()

        # 6. Авто-генерация графа путей по демо-данным
        from app.services.auto_graph import generate_auto_graph
        from app.repositories.navigation_repository import navigation_repo
        nodes_payload, edges_payload = generate_auto_graph(
            width=floor.width_px or 2000,
            height=floor.height_px or 1200,
            layout=floor.layout_data or DEMO_LAYOUT,
            pois=demo_pois,
        )
        await navigation_repo.replace_floor_graph(db, floor, nodes_payload, edges_payload)
        print(f"⚡ Навигационный граф построен: {len(nodes_payload)} узлов, {len(edges_payload)} связей!")

        await db.commit()
        print("✅ Все демо-данные успешно загружены! Можно тестировать API и фронтенд.")

if __name__ == "__main__":
    asyncio.run(seed())
