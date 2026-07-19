князь недоволен, света и связи нету. В условиях джуглей с ракетами я создал этот реп.

# YummyAnimeDownloader
<img width="2205" height="1279" alt="изображение" src="https://github.com/user-attachments/assets/2ae26c12-ed14-4329-83b1-cfde79ea45b5" />

Скачивание аниме с [YummyAnime](https://ru.yummyani.me) через Kodik и Sibnet плееры.

## Возможности

- Поиск аниме по ссылке с YummyAnime
- Выбор озвучки, плеера и качества
- Выбор диапазона серий
- Параллельное скачивание серий
- Прогресс-бар в реальном времени (WebSocket)

## Требования

- Python 3.10+
- [ffmpeg](https://ffmpeg.org/) (для склейки сегментов)

## Установка и запуск

### Windows

```bat
git clone https://github.com/timcho968/YummyAnimeDownloader.git
cd YummyAnimeDownloader
start.bat
```

Скрипт сам установит зависимости, Playwright и запустит сервер.

### Linux / macOS

```bash
git clone https://github.com/timcho968/YummyAnimeDownloader.git
cd YummyAnimeDownloader
chmod +x start.sh kill.sh
./start.sh
```

Скрипт сам создаст `.venv`, установит зависимости и Playwright при первом запуске.

### Остановка сервера

| Windows | Linux/macOS |
|---------|-------------|
| `kill_server.bat` | `./kill.sh` |

Открой http://localhost:8000 в браузере.

## Лицензия

MIT
