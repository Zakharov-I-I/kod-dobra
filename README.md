# ДоброДень — Telegram-бот

Каждый день присылает одно доброе дело на 5–30 минут. Серии, достижения, статистика, админ-панель для пилота.

## Быстрый запуск (Windows / macOS / Linux)
1. Установи Python 3.10+ (python.org; на Windows поставь галочку «Add to PATH»).
2. Создай бота: в Telegram открой @BotFather → `/newbot` → задай имя и username (оканчивается на `bot`) → скопируй токен.
3. Узнай свой ID: напиши @userinfobot — он ответит числом. Это твой ID администратора.
4. В папке проекта:
   ```
   python -m venv venv
   venv\Scripts\activate          (Linux/macOS: source venv/bin/activate)
   pip install -r requirements.txt
   copy .env.example .env         (Linux/macOS: cp .env.example .env)
   ```
5. Открой `.env`, вставь `BOT_TOKEN` и `ADMIN_IDS`.
6. `python main.py` — в консоли появится «Бот запущен: @твой_бот». Напиши боту `/start`.

Бот работает, пока запущена программа. Компьютер уснул или выключился — рассылка остановится; после запуска бот сам досылает пропущенное задание дня.
Запускай **только один экземпляр** (иначе ошибка «Conflict: terminated by other getUpdates»).

## Круглосуточная работа
**VPS (Linux, systemd):** скопируй проект в `/opt/dobroden_bot`, создай venv и `.env`, затем
```
sudo cp dobroden.service /etc/systemd/system/
sudo useradd -r dobroden && sudo chown -R dobroden /opt/dobroden_bot
sudo systemctl enable --now dobroden
journalctl -u dobroden -f        # логи
```
**Docker:** `docker build -t dobroden .` и
`docker run -d --restart=always --env-file .env -v $(pwd)/data:/app/data dobroden`.

## Команды
Пользователь: `/start /today /done /stats /settings /time /help /privacy /deleteme`.
Админ (ID из `ADMIN_IDS`): `/admin` — метрики пилота (≥5 дел за первую неделю, ≥10 всего, средняя серия, сегменты, категории);
`/export` — CSV без Telegram-ID; `/broadcast текст` — рассылка; `/addtask 2 | 15 | Текст` — добавить задание в банк.

## Правила
Серия не обнуляется после одного пропущенного дня, после двух подряд — обнуляется. Заменить задание можно 1 раз в день. Отметить можно задание сегодняшнего или вчерашнего дня. Напоминание — один раз, не позже 22:00.

## Данные и резервная копия
Всё хранится в одном файле `data/dobroden.db` — копируй его для бэкапа. Хранятся: Telegram-ID, ник, выбранные настройки и история заданий. `/deleteme` стирает всё о пользователе. Для пилота с несовершеннолетними нужно согласие родителей/школы — проверьте это отдельно.

## Тесты
`python -m unittest discover -s tests` (проверяют логику без Telegram).
