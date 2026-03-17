#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Конвертер Telegram стикеров в ZIP для FluffyChat.
Поддерживает статические (.webp), видео (.webm) и анимированные (.tgs) стикеры.
Использует Telegram Bot API.
Для TGS требуется библиотека pyrlottie.
"""

import os
import sys
import json
import zipfile
import argparse
import tempfile
import shutil
import subprocess
import logging
from datetime import datetime
from urllib.parse import urlparse
from pathlib import Path

import requests
from PIL import Image

# Настройка логирования
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Проверка наличия библиотек
try:
    from apng import APNG
    APNG_AVAILABLE = True
except ImportError:
    logger.error("Библиотека apng не установлена. Установите: pip install apng")
    sys.exit(1)

try:
    import pyrlottie
    PYLOTTIE_AVAILABLE = True
except ImportError:
    PYLOTTIE_AVAILABLE = False
    logger.warning("pyrlottie не установлен. TGS-стикеры не будут конвертироваться.")

# OpenCV не обязателен, если есть ffmpeg
try:
    import cv2
    CV2_AVAILABLE = True
except ImportError:
    CV2_AVAILABLE = False

# numpy для удаления чёрного фона (не обязательно)
try:
    import numpy as np
    NUMPY_AVAILABLE = True
except ImportError:
    NUMPY_AVAILABLE = False
    logger.warning("numpy не установлен. Удаление чёрного фона может работать медленнее.")

# ----------------------------------------------------------------------
# Конфигурация
BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
API_URL = "https://api.telegram.org/bot{}/"
DEFAULT_MAX_SIZE = 256

# ----------------------------------------------------------------------
def extract_pack_name_from_url(url):
    """Извлекает имя пака из ссылки вида https://t.me/addstickers/NAME"""
    parsed = urlparse(url)
    path = parsed.path
    parts = path.split('/')
    if len(parts) >= 3 and parts[1] == 'addstickers':
        return parts[2]
    return url.strip('/').split('/')[-1]

def get_sticker_set(pack_name, bot_token):
    """Получает информацию о наборе стикеров через Bot API"""
    url = API_URL.format(bot_token) + "getStickerSet"
    params = {"name": pack_name}
    response = requests.get(url, params=params)
    if response.status_code != 200:
        raise Exception(f"HTTP error {response.status_code}")
    data = response.json()
    if not data.get("ok"):
        raise Exception(f"Telegram API error: {data.get('description')}")
    return data["result"]

def download_file(file_id, target_path, bot_token):
    """Скачивает файл по file_id через Bot API"""
    url = API_URL.format(bot_token) + "getFile"
    params = {"file_id": file_id}
    resp = requests.get(url, params=params).json()
    if not resp.get("ok"):
        raise Exception("Cannot get file path")
    file_path = resp["result"]["file_path"]
    download_url = f"https://api.telegram.org/file/bot{bot_token}/{file_path}"
    r = requests.get(download_url, stream=True)
    if r.status_code == 200:
        with open(target_path, 'wb') as f:
            for chunk in r.iter_content(1024):
                f.write(chunk)
    else:
        raise Exception(f"Failed to download file: {r.status_code}")

def resize_image(img, max_size):
    """Масштабирует изображение с сохранением пропорций"""
    if max_size is None:
        return img
    width, height = img.size
    if width <= max_size and height <= max_size:
        return img
    if width > height:
        new_width = max_size
        new_height = int(height * max_size / width)
    else:
        new_height = max_size
        new_width = int(width * max_size / height)
    return img.resize((new_width, new_height), Image.Resampling.LANCZOS)

def remove_black_bg(image, threshold=30):
    """
    Заменяет чёрный фон (пиксели, где все каналы < threshold) на прозрачный.
    Возвращает RGBA изображение.
    """
    if image.mode != 'RGBA':
        image = image.convert('RGBA')
    if NUMPY_AVAILABLE:
        data = np.array(image)
        # Создаём маску для чёрного: R, G, B все меньше порога
        black_mask = np.all(data[:,:,:3] < threshold, axis=2)
        data[black_mask, 3] = 0  # устанавливаем прозрачность
        return Image.fromarray(data)
    else:
        # Медленный метод без numpy
        datas = image.getdata()
        new_data = []
        for item in datas:
            # item = (R, G, B, A)
            if item[0] < threshold and item[1] < threshold and item[2] < threshold:
                new_data.append((item[0], item[1], item[2], 0))
            else:
                new_data.append(item)
        image.putdata(new_data)
        return image

def save_png(image, output_path, max_size=None, keep_alpha=True, remove_black=False, black_threshold=30):
    """Универсальное сохранение PNG с опциями"""
    if max_size:
        image = resize_image(image, max_size)
    if remove_black:
        image = remove_black_bg(image, black_threshold)
        keep_alpha = True
    if keep_alpha and image.mode == 'RGBA':
        image.save(output_path, format='PNG', optimize=True, compress_level=9)
    else:
        # Конвертируем в палитру для экономии места
        if image.mode in ('RGBA', 'LA'):
            image = image.convert('P', palette=Image.Palette.ADAPTIVE, colors=256)
        else:
            image = image.convert('P', palette=Image.Palette.ADAPTIVE, colors=256)
        image.save(output_path, format='PNG', optimize=True, compress_level=9)

def convert_webp_to_png(webp_path, png_path, max_size=None, remove_black=False, black_threshold=30):
    """Конвертирует статический WebP в PNG"""
    with Image.open(webp_path) as img:
        save_png(img, png_path, max_size, keep_alpha=True, remove_black=remove_black, black_threshold=black_threshold)

def create_apng_from_frames(frame_files, delays, output_path):
    """Создаёт APNG из списка файлов кадров и задержек (в мс)"""
    apng = APNG()
    for f, d in zip(frame_files, delays):
        apng.append_file(f, delay=d)
    apng.save(output_path)

def check_ffmpeg():
    """Проверяет наличие ffmpeg в системе"""
    return shutil.which("ffmpeg") is not None

def video_has_alpha(video_path):
    """Проверяет, содержит ли видео альфа-канал через ffprobe"""
    if not shutil.which("ffprobe"):
        return False
    cmd = [
        "ffprobe", "-v", "error", "-select_streams", "v:0",
        "-show_entries", "stream=pix_fmt", "-of", "default=noprint_wrappers=1:nokey=1",
        video_path
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        pix_fmt = result.stdout.strip()
        return any(x in pix_fmt for x in ['yuva', 'rgba', 'gbra', 'pal8', 'alpha'])
    except:
        return False

def convert_webm_to_apng(webm_path, apng_path, max_size=None, fps=10, temp_dir=None,
                         remove_black=False, black_threshold=30):
    """Конвертирует WebM в APNG через ffmpeg (с опцией удаления чёрного фона)"""
    if not check_ffmpeg():
        raise ImportError("ffmpeg не найден. Установите ffmpeg.")

    if temp_dir is None:
        temp_dir = tempfile.mkdtemp()
    else:
        os.makedirs(temp_dir, exist_ok=True)

    has_alpha = video_has_alpha(webm_path)
    if not has_alpha and not remove_black:
        logger.warning("      Видео не содержит альфа-канал. Прозрачность невозможна (используйте --remove-black-bg для принудительного удаления чёрного фона).")

    # Извлекаем кадры через ffmpeg
    frame_pattern = os.path.join(temp_dir, "frame_%04d.png")
    cmd = [
        "ffmpeg", "-i", webm_path,
        "-vf", f"fps={fps}",
        "-pix_fmt", "rgba" if has_alpha else "rgb24",
        "-compression_level", "0",
        frame_pattern
    ]
    try:
        subprocess.run(cmd, check=True, capture_output=True, text=True)
    except subprocess.CalledProcessError as e:
        raise Exception(f"ffmpeg error: {e.stderr}")

    import glob
    frame_files = sorted(glob.glob(os.path.join(temp_dir, "frame_*.png")))
    if not frame_files:
        raise Exception("ffmpeg не создал кадры")

    delays = [int(1000 / fps)] * len(frame_files)

    # Применяем удаление чёрного фона, если нужно
    if remove_black or not has_alpha:
        logger.info(f"      Применяется удаление чёрного фона (порог {black_threshold})")
        processed_dir = os.path.join(temp_dir, "processed")
        os.makedirs(processed_dir, exist_ok=True)
        processed_files = []
        for f in frame_files:
            img = Image.open(f).convert('RGBA')
            img = remove_black_bg(img, black_threshold)
            out_f = os.path.join(processed_dir, os.path.basename(f))
            save_png(img, out_f, max_size=max_size, keep_alpha=True, remove_black=False)
            processed_files.append(out_f)
            os.remove(f)
        frame_files = processed_files
    elif max_size:
        # Только масштабирование
        scaled_dir = os.path.join(temp_dir, "scaled")
        os.makedirs(scaled_dir, exist_ok=True)
        scaled_files = []
        for f in frame_files:
            img = Image.open(f)
            out_f = os.path.join(scaled_dir, os.path.basename(f))
            save_png(img, out_f, max_size=max_size, keep_alpha=has_alpha, remove_black=False)
            scaled_files.append(out_f)
            os.remove(f)
        frame_files = scaled_files

    create_apng_from_frames(frame_files, delays, apng_path)

    # Очистка
    for f in frame_files:
        if os.path.exists(f):
            os.remove(f)
    if temp_dir is None:
        os.rmdir(temp_dir)

def convert_tgs_to_apng(tgs_path, apng_path, max_size=None, fps=30, temp_dir=None,
                        remove_black=False, black_threshold=30):
    """Конвертирует TGS в APNG через pyrlottie"""
    if not PYLOTTIE_AVAILABLE:
        raise ImportError("pyrlottie не установлен")

    with open(tgs_path, 'rb') as f:
        tgs_data = f.read()

    # Получаем свойства анимации
    width, height, duration = pyrlottie.get_properties(tgs_data)
    num_frames = int(duration * fps)
    if num_frames == 0:
        num_frames = 30  # запасной вариант

    delays = [int(1000 / fps)] * num_frames

    if temp_dir is None:
        temp_dir = tempfile.mkdtemp()
    else:
        os.makedirs(temp_dir, exist_ok=True)

    frame_files = []
    for i in range(num_frames):
        t = i / fps
        # Рендерим кадр как массив байт RGBA
        frame_data = pyrlottie.render_frame(tgs_data, t)
        # Преобразуем в PIL Image
        img = Image.frombytes('RGBA', (width, height), frame_data)

        # Применяем удаление чёрного фона, если нужно
        if remove_black:
            img = remove_black_bg(img, black_threshold)

        # Масштабирование
        if max_size:
            img = resize_image(img, max_size)

        frame_file = os.path.join(temp_dir, f"frame_{i:04d}.png")
        save_png(img, frame_file, max_size=None, keep_alpha=True, remove_black=False)
        frame_files.append(frame_file)

    create_apng_from_frames(frame_files, delays, apng_path)

    # Очистка
    for f in frame_files:
        os.remove(f)
    if temp_dir is None:
        os.rmdir(temp_dir)

def create_meta(emojis, pack_name, output_dir):
    """Создаёт файл meta.json в output_dir"""
    meta = {
        "metaVersion": 2,
        "host": "telegram_stickers",
        "exportedAt": datetime.utcnow().isoformat() + "Z",
        "emojis": []
    }
    for i, (filename, original_name) in enumerate(emojis):
        name = original_name or f"sticker{i}"
        meta["emojis"].append({
            "downloaded": True,
            "fileName": filename,
            "emoji": {
                "name": name,
                "category": pack_name,
                "aliases": []
            }
        })
    meta_path = os.path.join(output_dir, "meta.json")
    with open(meta_path, "w", encoding="utf-8") as f:
        json.dump(meta, f, indent=4, ensure_ascii=False)

def process_pack(pack_name, bot_token, output_zip_dir=".", max_size=DEFAULT_MAX_SIZE,
                 remove_black=False, black_threshold=30):
    """Основная функция обработки одного пака"""
    logger.info(f"Обработка пака: {pack_name}")
    try:
        pack_info = get_sticker_set(pack_name, bot_token)
    except Exception as e:
        logger.error(f"Не удалось получить информацию о паке {pack_name}: {e}")
        return

    stickers = pack_info["stickers"]
    pack_title = pack_info.get("title", pack_name)
    logger.info(f"Название: {pack_title}, стикеров: {len(stickers)}")

    with tempfile.TemporaryDirectory() as tmpdir:
        frames_dir = os.path.join(tmpdir, "frames")
        os.makedirs(frames_dir, exist_ok=True)

        emoji_entries = []

        for idx, sticker in enumerate(stickers):
            file_id = sticker["file_id"]
            is_animated = sticker.get("is_animated", False)
            is_video = sticker.get("is_video", False)
            emoji = sticker.get("emoji", "")

            ext = ".tgs" if is_animated else ".webm" if is_video else ".webp"
            temp_file = os.path.join(tmpdir, f"temp_{idx}{ext}")
            logger.info(f"  Скачивание стикера {idx+1} ({ext})...")
            try:
                download_file(file_id, temp_file, bot_token)
            except Exception as e:
                logger.error(f"    Ошибка скачивания: {e}. Пропускаем.")
                continue

            out_filename = f"{idx}.png"
            out_path = os.path.join(tmpdir, out_filename)

            try:
                if not is_animated and not is_video:
                    convert_webp_to_png(temp_file, out_path, max_size,
                                        remove_black=remove_black, black_threshold=black_threshold)
                    logger.info(f"    Конвертирован в PNG (оптимизирован)")
                elif is_animated:
                    if PYLOTTIE_AVAILABLE:
                        convert_tgs_to_apng(temp_file, out_path, max_size, temp_dir=frames_dir,
                                            remove_black=remove_black, black_threshold=black_threshold)
                        logger.info(f"    Конвертирован в APNG (TGS, оптимизирован)")
                    else:
                        logger.warning(f"    TGS-стикеры не поддерживаются (pyrlottie не установлен). Пропускаем.")
                        os.remove(temp_file)
                        continue
                elif is_video:
                    if check_ffmpeg():
                        convert_webm_to_apng(temp_file, out_path, max_size, temp_dir=frames_dir,
                                             remove_black=remove_black, black_threshold=black_threshold)
                        logger.info(f"    Конвертирован в APNG (WebM, оптимизирован)")
                    else:
                        logger.warning(f"    WebM-стикеры не поддерживаются (ffmpeg не найден). Пропускаем.")
                        os.remove(temp_file)
                        continue
            except Exception as e:
                logger.error(f"    Ошибка конвертации: {e}. Пропускаем.")
                if os.path.exists(temp_file):
                    os.remove(temp_file)
                continue

            os.remove(temp_file)
            name = emoji if emoji else f"sticker{idx}"
            emoji_entries.append((out_filename, name))

        if not emoji_entries:
            logger.warning("Не удалось обработать ни одного стикера, пропускаем пак.")
            return

        create_meta(emoji_entries, pack_name, tmpdir)

        if os.path.exists(frames_dir):
            shutil.rmtree(frames_dir)

        zip_filename = f"{pack_name}.zip"
        zip_path = os.path.join(output_zip_dir, zip_filename)
        with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zf:
            for file in os.listdir(tmpdir):
                file_path = os.path.join(tmpdir, file)
                if os.path.isfile(file_path) and (file.endswith('.png') or file == 'meta.json'):
                    zf.write(file_path, file)

        logger.info(f"Готово: {zip_path} (размер: {os.path.getsize(zip_path) / 1024:.1f} KB)")

def main():
    parser = argparse.ArgumentParser(description="Конвертер Telegram стикеров в ZIP для FluffyChat")
    parser.add_argument("--link", help="Ссылка на стикерпак (https://t.me/addstickers/NAME)")
    parser.add_argument("--file", help="Файл со списком ссылок (по одной на строку)")
    parser.add_argument("--token", help="Токен бота Telegram (если не задан в TELEGRAM_BOT_TOKEN)")
    parser.add_argument("--output", default=".", help="Папка для сохранения ZIP-архивов (по умолчанию текущая)")
    parser.add_argument("--max-size", type=int, default=DEFAULT_MAX_SIZE,
                        help=f"Максимальный размер изображения (по умолчанию {DEFAULT_MAX_SIZE})")
    parser.add_argument("--remove-black-bg", action="store_true",
                        help="Принудительно удалять чёрный фон (заменять на прозрачный)")
    parser.add_argument("--black-threshold", type=int, default=30,
                        help="Порог яркости для определения чёрного фона (0-255, по умолчанию 30)")
    args = parser.parse_args()

    bot_token = args.token or BOT_TOKEN
    if not bot_token:
        logger.error("Не задан токен бота. Укажите --token или переменную окружения TELEGRAM_BOT_TOKEN")
        sys.exit(1)

    links = []
    if args.link:
        links.append(args.link)
    if args.file:
        try:
            with open(args.file, 'r') as f:
                for line in f:
                    line = line.strip()
                    if line:
                        links.append(line)
        except Exception as e:
            logger.error(f"Ошибка чтения файла {args.file}: {e}")
            sys.exit(1)

    if not links:
        logger.error("Ничего не указано. Используйте --link или --file")
        sys.exit(1)

    os.makedirs(args.output, exist_ok=True)

    for link in links:
        pack_name = extract_pack_name_from_url(link)
        try:
            process_pack(pack_name, bot_token, args.output, args.max_size,
                         args.remove_black_bg, args.black_threshold)
        except KeyboardInterrupt:
            logger.info("Прервано пользователем")
            sys.exit(0)
        except Exception as e:
            logger.error(f"Необработанная ошибка при обработке {link}: {e}")
            continue

if __name__ == "__main__":
    main()
