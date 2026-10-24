import math
import os
from PIL import Image, ImageDraw, ImageFont

def generate_demo_floor_plan(output_path: str):
    """
    Генерирует архитектурный 2D-план этажа выставки ТТК:
    - Разрешение: 2000x1200 px
    - Главный холл, Экспозона, Конференц-зал, Кофе-поинт, Санузлы, Стенды
    """
    width, height = 2000, 1200
    # Светло-серый фон чертежа
    img = Image.new("RGB", (width, height), color=(248, 249, 250))
    draw = ImageDraw.Draw(img)

    # Внешние стены здания
    margin = 50
    draw.rectangle(
        [margin, margin, width - margin, height - margin],
        outline=(33, 37, 41),
        width=8,
    )

    # 1. Главный холл и зона регистрации (слева внизу)
    draw.rectangle([margin, 700, 700, height - margin], outline=(73, 80, 87), width=4, fill=(233, 236, 239))
    draw.text((150, 900), "ВХОДНАЯ ГРУППА И РЕГИСТРАЦИЯ", fill=(33, 37, 41))

    # Главный вход (дверной проем)
    draw.rectangle([300, height - margin - 8, 450, height - margin + 8], fill=(40, 167, 69))
    draw.text((320, height - margin - 35), "ГЛАВНЫЙ ВХОД", fill=(40, 167, 69))

    # 2. Главный конференц-зал (справа внизу)
    draw.rectangle([1200, 650, width - margin, height - margin], outline=(73, 80, 87), width=4, fill=(222, 226, 230))
    draw.text((1400, 900), "КОНФЕРЕНЦ-ЗАЛ «ТРАНСТЕЛЕКОМ» (250 мест)", fill=(33, 37, 41))

    # Сцена в конференц-зале
    draw.rectangle([1400, 700, 1850, 780], outline=(220, 53, 69), width=3, fill=(248, 215, 218))
    draw.text((1580, 730), "СЦЕНА", fill=(220, 53, 69))

    # 3. Экспозона / Выставка стендов (центр и верх)
    draw.rectangle([ margin, margin, 1400, 650], outline=(73, 80, 87), width=4, fill=(255, 255, 255))
    draw.text((100, 80), "ЭКСПОЗИЦИОННЫЙ ЗАЛ (СТЕНДЫ КОМПАНИЙ)", fill=(108, 117, 125))

    # Ряды выставочных стендов (A1, A2, B1, B2, Стенд ТТК)
    stands = [
        ([150, 150, 450, 320], "Стенд #1: ТТК Цифровые Сервисы", (209, 231, 221), (15, 81, 50)),
        ([550, 150, 850, 320], "Стенд #2: IoT и Умный Город", (226, 227, 229), (65, 70, 75)),
        ([950, 150, 1300, 320], "Стенд #3: Индор-Навигация", (207, 244, 252), (5, 81, 96)),
        ([150, 400, 450, 570], "Стенд #4: Облачные Решения", (255, 243, 205), (102, 77, 3)),
        ([550, 400, 850, 570], "Стенд #5: Кибербезопасность", (248, 215, 218), (132, 32, 41)),
        ([950, 400, 1300, 570], "Стенд #6: Партнерская Зона", (226, 227, 229), (65, 70, 75)),
    ]
    for box, title, fill_c, text_c in stands:
        draw.rectangle(box, outline=(108, 117, 125), width=2, fill=fill_c)
        draw.text((box[0] + 20, box[1] + 60), title, fill=text_c)

    # 4. Кофе-поинт и Лаундж (справа вверху)
    draw.rectangle([1450, margin, width - margin, 400], outline=(73, 80, 87), width=3, fill=(254, 237, 222))
    draw.text((1550, 200), "КОФЕ-БРЕЙК & ЛАУНДЖ ЗОНА", fill=(147, 83, 31))

    # 5. Санузлы (WC)
    draw.rectangle([1450, 450, 1700, 600], outline=(73, 80, 87), width=2, fill=(238, 242, 246))
    draw.text((1520, 515), "САНУЗЛЫ (WC)", fill=(51, 65, 85))

    # 6. Лестница и Лифты на 2 этаж
    draw.rectangle([750, 750, 1150, 950], outline=(13, 110, 253), width=3, fill=(207, 226, 255))
    draw.text((820, 830), "ЛЕСТНИЦА И ЛИФТ НА 2 ЭТАЖ", fill=(8, 66, 152))

    # Сетка и метки масштаба
    draw.line([(width - 300, height - 30), (width - 100, height - 30)], fill=(0, 0, 0), width=4)
    draw.text((width - 260, height - 55), "10 МЕТРОВ (PPM=20)", fill=(0, 0, 0))

    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    img.save(output_path, "PNG")
    print(f"План этажа сохранен: {output_path} ({width}x{height})")

def generate_demo_panorama(output_path: str):
    """Генерирует тестовую 360-эквидистантную панораму 2:1 (2048x1024)."""
    w, h = 2048, 1024
    img = Image.new("RGB", (w, h), color=(180, 200, 220))
    draw = ImageDraw.Draw(img)

    # Пол
    draw.rectangle([0, h // 2, w, h], fill=(210, 215, 220))
    # Стены и разметка по сторонам света
    directions = [
        (0, "СЕВЕР (ЭКСПОЗОНА И СТЕНД ТТК)"),
        (w // 4, "ВОСТОК (КОФЕ-БРЕЙК И ВЫХОД)"),
        (w // 2, "ЮГ (ГЛАВНЫЙ ВХОД И РЕГИСТРАЦИЯ)"),
        (3 * w // 4, "ЗАПАД (КОНФЕРЕНЦ-ЗАЛ)"),
    ]
    for x_offset, label in directions:
        draw.line([(x_offset, h // 3), (x_offset, 2 * h // 3)], fill=(100, 120, 140), width=4)
        draw.text((x_offset + 20, h // 2 - 40), label, fill=(30, 40, 50))

    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    img.save(output_path, "JPEG", quality=90)
    print(f"Панорама сохранена: {output_path} ({w}x{h})")

if __name__ == "__main__":
    base_dir = "/home/northbarvinok/Source/sc1z0PsiHi_space_map/demo_assets"
    generate_demo_floor_plan(f"{base_dir}/floor_1_plan.png")
    generate_demo_panorama(f"{base_dir}/hall_360_panorama.jpg")
