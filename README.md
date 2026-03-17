# Telegram Stickers to FluffyChat Converter

Скрипт на Python для скачивания стикерпаков из Telegram и конвертации их в формат ZIP, совместимый с мессенджером [FluffyChat](https://fluffychat.im).  
Поддерживаются все типы стикеров:
- Статические (`.webp`) → `.png`
- Видеостикеры (`.webm`) → анимированные `.png` (APNG) с сохранением прозрачности (если есть)
- Анимированные стикеры (`.tgs`) → APNG (через библиотеку `pyrlottie`)

## 📦 Возможности
- Работа через **Telegram Bot API** (не требует авторизации пользователя).
- Оптимизация размера: масштабирование до заданного размера, сжатие PNG.
- Принудительное удаление чёрного фона для видео и TGS (экспериментально).
- Пакетная обработка списка ссылок из файла.
- Автоматическое создание `meta.json` по образцу FluffyChat.

## 🔧 Установка

### 1. Системные зависимости (Ubuntu/Debian)
```bash
sudo apt update
sudo apt install ffmpeg build-essential cmake libcairo2-dev
```

**Для других ОС**:
- **macOS**: `brew install ffmpeg cairo`
- **Windows**: скачайте ffmpeg с [официального сайта](https://ffmpeg.org/download.html) и добавьте в PATH; для cairo может потребоваться [GTK](https://www.gtk.org/docs/installations/windows).

### 2. Python-пакеты
Рекомендуется использовать виртуальное окружение:
```bash
python3 -m venv venv
source venv/bin/activate   # для Linux/macOS
# или venv\Scripts\activate для Windows
```

Установите зависимости:
```bash
pip install requests Pillow opencv-python apng numpy pyrlottie
```

> **Примечание**: `pyrlottie` может потребовать компиляции. Если возникнут ошибки, установите дополнительно `librlottie-dev` (Ubuntu: `sudo apt install librlottie-dev`) или обратитесь к [документации pyrlottie](https://github.com/GramAddict/pyrlottie).

### 3. Получение токена бота Telegram
1. Напишите [@BotFather](https://t.me/BotFather) в Telegram.
2. Отправьте команду `/newbot` и следуйте инструкциям.
3. Скопируйте полученный токен (например, `123456:ABCdef...`).

Токен можно передавать каждый раз через аргумент `--token` или сохранить в переменную окружения:
```bash
export TELEGRAM_BOT_TOKEN="ваш_токен"
```

## 🚀 Использование

### Базовый запуск для одной ссылки
```bash
python tg2fc.py --link "https://t.me/addstickers/НАЗВАНИЕ_ПАКА" --max-size 256
```
На выходе получится файл `НАЗВАНИЕ_ПАКА.zip`.

### Обработка списка ссылок из файла
Создайте текстовый файл `links.txt` с одной ссылкой на строку:
```
https://t.me/addstickers/Pack1
https://t.me/addstickers/Pack2
```
Затем выполните:
```bash
python tg2fc.py --file links.txt --output ./my_packs
```

### Параметры
| Аргумент | Описание |
|----------|----------|
| `--link` | Ссылка на стикерпак (пример: https://t.me/addstickers/Cheerful_Choco) |
| `--file` | Файл со списком ссылок (по одной на строку) |
| `--token` | Токен бота Telegram (если не задан в переменной окружения) |
| `--output` | Папка для сохранения ZIP-архивов (по умолчанию текущая) |
| `--max-size` | Максимальный размер изображения в пикселях (по умолчанию 256) |
| `--remove-black-bg` | Принудительно заменять чёрный фон на прозрачный (для видео и TGS) |
| `--black-threshold` | Порог яркости для определения чёрного (0-255, по умолчанию 30) |

### Пример с удалением чёрного фона
```bash
python tg2fc.py --link "https://t.me/addstickers/Cheerful_Choco" --max-size 256 --remove-black-bg --black-threshold 40
```

## 📂 Структура выходного ZIP
- `0.png`, `1.png`, … – стикеры в формате PNG (или APNG для анимированных).
- `meta.json` – метаданные для FluffyChat.

## ⚠️ Известные ограничения
- Если видео или TGS изначально не содержат альфа-канал, флаг `--remove-black-bg` может дать артефакты (например, удалить чёрные части рисунка). Настраивайте порог.
- Для работы с TGS необходима библиотека `pyrlottie`, которая требует компиляции.

## 🤝 Как помочь проекту
- Сообщайте об ошибках в [Issues](https://github.com/axel36rus/tg2fc/issues).
- Предлагайте улучшения через Pull Requests.

## 📄 Лицензия
MIT License. Подробнее в файле `LICENSE`.
