# ⚡ Ночной блиц-план бэкенда: 1 ночь, 3 разработчика
## Проект: «Карта пространства» (FastAPI + PostgreSQL + MinIO)

> **Цель**: За 8–10 часов ночного спринта написать 100% рабочего фундаментального бэкенда без конфликтов в Git и подготовить готовый API для фронтенда к утру.

---

## 🛡️ Золотые правила параллельной ночной работы (Чтобы не было Git-конфликтов)

1. **Раздельные файлы по модулям**: Никаких правок в чужих файлах роутов или схем.
   - 👤 Дев 1 владеет: `app/api/v1/auth.py`, `spaces.py`, `floors.py`, `public.py`, `app/models/user.py`, `space.py`
   - 👤 Дев 2 владеет: `app/api/v1/panoramas.py`, `media.py`, `app/services/s3.py`, `image_ops.py`, `app/models/panorama.py`
   - 👤 Дев 3 владеет: `app/api/v1/pois.py`, `navigation.py`, `app/services/pathfinder.py`, `app/models/poi.py`, `navigation.py`
2. **Все ID — это `UUID`**: Все таблицы используют `uuid.uuid4`. Никаких автоинкрементных `int id`, чтобы не зависеть от порядка вставок в БД.
3. **Общий Base и единый `main.py`**:
   - В первые 30 минут Дев 1 пушит скелет проекта с заготовками пустых роутеров в ветку `main`.
   - Дев 2 и Дев 3 работают в ветках `feat/media-panoramas` и `feat/poi-navigation`.
   - В `app/main.py` Дев 1 заранее прописывает `app.include_router(...)` для всех трёх модулей.

---

## ⏰ Почасовой график ночи (Timeline)

| Время | 👤 Разработчик 1 (Core & Auth & Spaces) | 👤 Разработчик 2 (MinIO & Panoramas) | 👤 Разработчик 3 (POI & Навигация A*) |
| :--- | :--- | :--- | :--- |
| **00:00 – 00:45** | **Старт**: Docker-compose, каркас FastAPI, `Base`, заглушки роутеров. Пулл в `main`. | Поднимает локальный MinIO, пишет класс `S3Service` (`aioboto3` / presigned URLs). | Пишет независимый чистый алгоритм **A\*** на Python с тестами на dummy-графе. |
| **00:45 – 03:00** | Модели `User`, `Space`, `Floor`. JWT Auth, хеширование паролей, RBAC dependencies. | Модели `Panorama`, `PanoramaHotspot`. Загрузка 2D-плана и готовой панорамы в MinIO. | Модели `POI`, `NavNode`, `NavEdge`. CRUD для POI и сохранение графа с фронтенда. |
| **03:00 – 05:30** | CRUD для Spaces и Floors. Логика публикации `is_published`. | Фоновый ресайз (WebP), генерация BlurHash, эндпоинт связей панорам (`/connections`). | Эндпоинт расчета маршрута `POST /navigation/route` (связка A* с графом в БД). |
| **05:30 – 07:00** | Сборка единого агрегатора `GET /public/spaces/{slug}`. Настройка CORS. | Сессия загрузки серии фото со смартфона (`/stitch-session`) + заглушка сшивки. | Привязка цепочки панорам к полилинии маршрута и текстовые шаги («Идите 15м»). |
| **07:00 – 08:30** | **СЛИЯНИЕ ВЕТОК**: Прогон сквозных тестов в Swagger UI, фиксы, передача фронтенду. |

---

## 👤 РАЗРАБОТЧИК 1: Инфраструктура, Auth, Spaces & Public Gateway

### Файлы, которые ты создаешь и держишь:
- `docker-compose.yml` (Postgres 16, MinIO, Redis)
- `app/core/config.py` (pydantic-settings: переменные БД, S3, JWT)
- `app/core/database.py` (`async_sessionmaker`, `DeclarativeBase`)
- `app/core/security.py` (хеширование bcrypt, JWT create/decode)
- `app/models/user.py`, `app/models/space.py`
- `app/schemas/auth.py`, `app/schemas/space.py`
- `app/api/v1/auth.py`, `app/api/v1/spaces.py`, `app/api/v1/floors.py`, `app/api/v1/public.py`
- `app/main.py`

### Твои задачи на ночь:
1. **Первые 30 мин**: Развернуть `docker-compose.yml`, создать базовую структуру папок и запушить в Git. Дать отмашку ребятам делать `git pull`.
2. **Auth & RBAC**:
   - `POST /api/v1/auth/register` (email, password, full_name)
   - `POST /api/v1/auth/login` (OAuth2 form -> access + refresh tokens)
   - `GET /api/v1/auth/me`
   - Dependency: `get_current_user` и `require_space_role(role)` (проверка, что юзер — владелец или редактор пространства).
3. **Spaces & Floors CRUD**:
   - `POST /api/v1/spaces` (создание пространства)
   - `GET /api/v1/spaces` (список пространств текущего организатора)
   - `GET /api/v1/spaces/{id}`
   - `PATCH /api/v1/spaces/{id}/publish` (переключение `is_published: true/false`)
   - `POST /api/v1/spaces/{id}/floors` (создание этажа: номер, название, ppm)
   - `GET /api/v1/spaces/{id}/floors`
4. **Главный публичный эндпоинт для мобилки**:
   - `GET /api/v1/public/spaces/{slug}`:
     - Проверяет `is_published == True`.
     - Отдает объект: данные пространства, список этажей, все POI этажей и список панорам (без авторизации, кэшируемый за 0.05 сек).

---

## 👤 РАЗРАБОТЧИК 2: MinIO S3, Панорамы и Обработка изображений

### Файлы, которые ты создаешь и держишь:
- `app/services/s3.py` (Генератор presigned URLs через `aioboto3`)
- `app/services/image_ops.py` (BlurHash, превью WebP, нарезка кубических тайлов)
- `app/models/panorama.py`
- `app/schemas/panorama.py`
- `app/api/v1/panoramas.py`
- `app/api/v1/media.py`

### Твои задачи на ночь:
1. **MinIO S3 Клиент (`app/services/s3.py`)**:
   - Автосоздание бакетов `spaces-public` (read-only полиси) и `spaces-staging` при запуске.
   - Метод `generate_presigned_put_url(bucket, key, content_type)` — клиент грузит файл сразу в MinIO!
2. **Загрузка 2D-планов этажей**:
   - `POST /api/v1/floors/{floor_id}/plan/upload-url` -> возвращает `{upload_url, storage_key}`.
   - `POST /api/v1/floors/{floor_id}/plan/confirm-upload` -> обновляет у этажа `plan_optimized_key`.
3. **Панорамы (360° Tour)**:
   - `POST /api/v1/floors/{floor_id}/panoramas` (создает точку: x, y на плане этажа, title, heading).
   - `POST /api/v1/panoramas/{id}/upload-ready-url` (presigned URL для готовой 360-фото).
   - `POST /api/v1/panoramas/{id}/confirm-upload`:
     - В фоне (`asyncio.to_thread` или `BackgroundTasks`) скачивает фото из S3, считает **BlurHash**, сохраняет превью WebP (1024×512) и переводит статус панорамы в `ready`.
   - `POST /api/v1/panoramas/connections` (связка перехода между панорамой A и панорамой B с углами `yaw`, `pitch`).
4. **Серия фото со смартфона (Сшивка)**:
   - `POST /api/v1/panoramas/{id}/stitch-session` (принимает `frame_count`, отдает массив presigned url для каждого кадра).
   - `POST /api/v1/panoramas/{id}/process-stitch` (запускает сшивку кадров через OpenCV `cv2.Stitcher_create()` или fallback-заглушку, если не сшилось).

---

## 👤 РАЗРАБОТЧИК 3: POI, Граф навигации & Алгоритм маршрутизации A*

### Файлы, которые ты создаешь и держишь:
- `app/services/pathfinder.py` (Чистая математика: алгоритм A\*, расчет расстояний)
- `app/models/poi.py`, `app/models/navigation.py`
- `app/schemas/poi.py`, `app/schemas/navigation.py`
- `app/api/v1/pois.py`
- `app/api/v1/navigation.py`

### Твои задачи на ночь:
1. **Математика A\* (`app/services/pathfinder.py`)**:
   - В первые 45 минут напиши независимый алгоритм A\* на Python на словарях узлов и ребер.
   - Покрой тестом: граф из 5 вершин, поиск пути из А в Б, проверка исключения лестниц при `wheelchair_accessible_only=True`.
2. **Точки интереса (POI)**:
   - `POST /api/v1/floors/{floor_id}/pois`:
     - Координаты `(x, y)` на 2D-плане.
     - Опциональные `(yaw, pitch)` и `panorama_id` для отображения маркера внутри 3D-панорамы.
     - Категория: `stand`, `wifi`, `wc`, `info`, `food`.
   - `GET /api/v1/floors/{floor_id}/pois`
   - `PATCH /api/v1/pois/{id}`
   - `DELETE /api/v1/pois/{id}`
3. **Граф навигации (Для 2D-редактора)**:
   - `GET /api/v1/floors/{floor_id}/navigation/graph` (возвращает список всех вершин и ребер этажа).
   - `PUT /api/v1/floors/{floor_id}/navigation/graph`:
     - Пакетно сохраняет/перезаписывает вершины (`nav_nodes`) и связи (`nav_edges`).
     - Поддерживает типы вершин: `walkway`, `stairs`, `elevator`, `door`.
4. **Эндпоинт маршрутизации (`POST /api/v1/spaces/{space_id}/navigation/route`)**:
   - Принимает: `{from_poi_id, to_poi_id, wheelchair_accessible_only}` (или координаты `x, y`).
   - Загружает граф из БД, запускает твой алгоритм A\*.
   - Возвращает:
     - `total_distance_meters` и `estimated_time_seconds`.
     - Массив полилиний точек для отрисовки цветного маршрута на 2D-карте.
     - Пошаговые текстовые подсказки («Пройдите прямо 15 метров», «Поднимитесь на 2 этаж»).
     - **Важно для презентации**: список ID панорам вдоль пути, чтобы посетитель мог виртуально «пройти» по маршруту!

---

## 🔗 Точки стыковки модулей (Контракты DTO)

Чтобы в 07:00 утра все собралось с первой попытки:

1. **Стыковка Дев 1 и Дев 2**:
   - Дев 1 в `Floor` хранит поля `plan_optimized_key: str | None`. Дев 2 заполняет это поле при конфирме загрузки чертежа.
2. **Стыковка Дев 2 и Дев 3**:
   - В модели `POI` (Дев 3) есть поле `panorama_id: UUID | None`. Дев 3 может связать маркер стенда с панорамой.
   - В модели `NavNode` (Дев 3) есть поле `panorama_id: UUID | None`. Дев 3 находит ближайшие панорамы вдоль рассчитанного маршрута A\*.
3. **Стыковка Дев 1 и Дев 3**:
   - Дев 1 в публичном эндпоинте `GET /public/spaces/{slug}` просто вызывает методы `get_floors_by_space` (свой), `get_pois_by_floor` (от Дев 3) и `get_panoramas_by_floor` (от Дев 2).

---

## 🚀 Финишный чек-лист к 08:30 утра

- [ ] В Swagger (`http://localhost:8000/docs`) открываются все эндпоинты без 500 ошибок.
- [ ] Зарегистрирован организатор, создано пространство, создан 1 этаж.
- [ ] Получен presigned URL, загружен 2D-план этажа.
- [ ] Создана точка панорамы, загружена 360-фото, посчитан BlurHash.
- [ ] Создано 2 POI (стенд и вход), расставлен граф из 4 узлов и 3 ребер.
- [ ] Вызван `POST /navigation/route` — вернулся успешный маршрут с полилинией и дистанцией!
- [ ] Вызван `GET /public/spaces/{slug}` — вернулся полный JSON для мобильного интерфейса.
