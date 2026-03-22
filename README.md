# DnD Bot

Telegram bot for:

- character stats
- inventory
- item definitions and item stats
- skills
- dice rolls
- freeform text input without commands

## Local Run

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

## Railway Deploy

This repository is ready for Railway:

- `Dockerfile` is included
- `railway.json` is included
- required variable: `BOT_TOKEN`

### Steps

1. Push this repository to GitHub
2. In Railway choose `New Project`
3. Select `Deploy from GitHub Repo`
4. Choose this DnD bot repository
5. Add variable:

```text
BOT_TOKEN=your_telegram_bot_token
```

6. Deploy

No volume is required for the basic version.

## GitHub

This project is separate from the music bot and lives in:

`C:\WER\dnd_bot`

Example push after you create an empty GitHub repository:

```powershell
cd C:\WER\dnd_bot
& "C:\Program Files\Git\cmd\git.exe" remote add origin https://github.com/YOUR_NAME/YOUR_REPO.git
& "C:\Program Files\Git\cmd\git.exe" push -u origin master
```

## Freeform Examples

- `2d20+5`
- `атака мечом 1d20+5`
- `сила 16`
- `хп 24`
- `имя персонажа Арден`
- `класс паладин`
- `добавь в инвентарь 3 зелья лечения`
- `предмет длинный меч; урон=1d8; вес=3`
- `навык скрытность +6`
- `удали навык скрытность`
- `покажи инвентарь`
