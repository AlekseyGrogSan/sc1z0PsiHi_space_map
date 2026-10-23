# 🗺️ Карта пространства (Indoor Navigation & Virtual 360° Tour)

> Сервис для создания интерактивных карт помещений, 3D-панорам и пешеходной навигации внутри зданий и на мероприятиях (Кейс ТрансТелеКом / ТТК).

---

## 📌 О проекте в двух словах
Платформа решает проблему ориентации посетителей на крупных площадках (отели, конгресс-центры, выставки, ТЦ). 
- **Организатор**: рисует или загружает 2D-план этажа, фотографирует со смартфона серию кадров (или загружает готовую 360° панораму), расставляет стенды/точки интереса (POI) и связывает помещения в виртуальный тур.
- **Посетитель**: открывает карту со смартфона по ссылке или QR-коду (без регистрации), находит нужный стенд или услугу, строит оптимальный маршрут от точки А к точке Б и может заранее осмотреть путь через панорамы.

---

## 🛠 Технологический стек

| Компонент | Технологии | Назначение |
| :--- | :--- | :--- |
| **Backend** | Python 3.12+, **FastAPI** (Uvicorn / Gunicorn) | Асинхронный REST API, валидация данных, аутентификация |
| **База данных** | **PostgreSQL 16** + asyncpg + SQLAlchemy 2.0 + Alembic | Хранение сущностей пространств, этажей, графа навигации, пользователей и POI |
| **Файловое хранилище**| **MinIO (S3-совместимое)** | Хранение 2D-чертежей, исходных фото, 360-панорам и тайлов |
| **Фоновые задачи** | Celery / Arq + Redis + Pillow / OpenCV / pyvips | Сшивка серий фото, нарезка кубических тайлов (cubemap), сжатие в WebP |
| **3D Просмотрщик** | Pannellum / Marzipano / Photo-Sphere-Viewer | Плавный просмотр 360-панорам и хотспотов в мобильном браузере |
| **2D Карта** | Leaflet.js / OpenLayers (`L.CRS.Simple`) | Интерактивная отрисовка 2D-плана этажа, маркеров и полилиний маршрутов |

---

## 🚀 Быстрый старт (Разработка)

### 1. Переменные окружения (`.env`)
```env
# База данных
DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/indoor_nav_db

# MinIO / S3
S3_ENDPOINT=http://localhost:9000
S3_ACCESS_KEY=minioadmin
S3_SECRET_KEY=minioadmin
S3_BUCKET_PUBLIC=spaces-public
S3_BUCKET_STAGING=spaces-staging
S3_PUBLIC_URL_PREFIX=http://localhost:9000/spaces-public

# JWT Security
SECRET_KEY=super-secret-jwt-key-change-in-production
ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=60
```

### 2. Запуск инфраструктуры (Docker Compose)
```bash
docker run -d --name pg-indoor -e POSTGRES_PASSWORD=postgres -p 5432:5432 postgres:16-alpine
docker run -d --name minio-indoor -p 9000:9000 -p 9001:9001 \
  -e MINIO_ROOT_USER=minioadmin -e MINIO_ROOT_PASSWORD=minioadmin \
  minio/minio server /data --console-address ":9001"
```

### 3. Запуск Backend
```bash
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
alembic upgrade head
uvicorn app.main:app --reload --port 8000
```
Документация Swagger UI доступна по адресу: `http://localhost:8000/docs`

---

## 📁 Структура документации
- [Полное описание проекта и архитектуры](PROJECT_OVERVIEW.md)
- [Задачи и строгие запреты для ИИ-разработчика](RULES_AND_CONSTRAINTS.md)
- [Скилл для ИИ-ассистента (Инженерные паттерны)](SKILL.md)
- [Бэклог и дорожная карта (Roadmap)](TASKS.md)
