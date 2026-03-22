# DnD Bot

Telegram bot for:

- character stats
- inventory
- item definitions and item stats
- skills
- dice rolls
- freeform text input without commands

## Run

1. Create `.env` from `.env.example`
2. Put your Telegram bot token into `BOT_TOKEN`
3. Install dependencies:

```powershell
python -m venv .venv
.\.venv\Scripts\pip install -r requirements.txt
```

4. Start the bot:

```powershell
.\.venv\Scripts\python bot.py
```

## Freeform examples

- `2d20+5`
- `сила 16`
- `хп 24`
- `имя персонажа Арден`
- `класс паладин`
- `добавь в инвентарь 3 зелья лечения`
- `предмет длинный меч; урон=1d8; вес=3`
- `навык скрытность +6`
- `мои навыки`
