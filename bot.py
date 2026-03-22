import random
import re
from pathlib import Path

import telebot
from dotenv import load_dotenv
from telebot import types

from database import db


BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")

import os

BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()

if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN is not set. Put it in .env before starting the bot.")

bot = telebot.TeleBot(BOT_TOKEN, parse_mode="Markdown")

MAIN_BUTTONS = [
    "🧙 Персонаж",
    "🎒 Инвентарь",
    "🗡️ Предметы",
    "✨ Навыки",
    "🎲 Кубы",
    "📋 Помощь",
]

STAT_ALIASES = {
    "сила": "strength",
    "ловкость": "dexterity",
    "телосложение": "constitution",
    "интеллект": "intelligence",
    "мудрость": "wisdom",
    "харизма": "charisma",
    "str": "strength",
    "dex": "dexterity",
    "con": "constitution",
    "int": "intelligence",
    "wis": "wisdom",
    "cha": "charisma",
    "хп": "hp",
    "hp": "hp",
    "кд": "ac",
    "ac": "ac",
    "инициатива": "initiative",
    "скорость": "speed",
    "уровень": "level",
}


def build_main_keyboard():
    keyboard = types.ReplyKeyboardMarkup(resize_keyboard=True)
    keyboard.row(types.KeyboardButton("🧙 Персонаж"), types.KeyboardButton("🎒 Инвентарь"))
    keyboard.row(types.KeyboardButton("🗡️ Предметы"), types.KeyboardButton("✨ Навыки"))
    keyboard.row(types.KeyboardButton("🎲 Кубы"), types.KeyboardButton("📋 Помощь"))
    return keyboard


def normalize_text(text):
    return (text or "").strip()


def parse_dice_expression(text):
    match = re.fullmatch(r"\s*(\d*)d(\d+)([+-]\d+)?\s*", text.lower())
    if not match:
        return None

    count = int(match.group(1) or 1)
    sides = int(match.group(2))
    modifier = int(match.group(3) or 0)

    if count < 1 or count > 100 or sides < 2 or sides > 1000:
        return None

    rolls = [random.randint(1, sides) for _ in range(count)]
    total = sum(rolls) + modifier
    return {
        "count": count,
        "sides": sides,
        "modifier": modifier,
        "rolls": rolls,
        "total": total,
    }


def format_dice_result(result):
    modifier = result["modifier"]
    modifier_text = f"{modifier:+d}" if modifier else ""
    rolls_text = ", ".join(str(x) for x in result["rolls"])
    return (
        f"🎲 *Бросок:* `{result['count']}d{result['sides']}{modifier_text}`\n\n"
        f"• Выпало: {rolls_text}\n"
        f"• Итог: *{result['total']}*"
    )


def parse_key_value_segments(text):
    segments = [segment.strip() for segment in text.split(";") if segment.strip()]
    if not segments:
        return "", "", {}

    head = segments[0]
    description = ""
    stats = {}

    for segment in segments[1:]:
        if "=" in segment:
            key, value = segment.split("=", 1)
            stats[key.strip().lower()] = value.strip()
        else:
            description = segment if not description else f"{description}; {segment}"

    return head, description, stats


def format_character(user_id):
    character = db.get_character(user_id)
    stats = db.get_stats(user_id)

    lines = [
        "🧙 *Персонаж*",
        "",
        f"• Имя: {character.get('name') or 'не задано'}",
        f"• Класс: {character.get('class_name') or 'не задан'}",
        f"• Раса: {character.get('race') or 'не задана'}",
        f"• Уровень: {character.get('level') or 1}",
    ]

    if stats:
        lines.extend(["", "*Статы:*"])
        for key, value in stats.items():
            lines.append(f"• {key}: {value}")
    else:
        lines.extend(["", "Статы пока не записаны."])

    lines.extend(
        [
            "",
            "*Примеры:*",
            "• `сила 16`",
            "• `хп 24`",
            "• `имя персонажа Арден`",
            "• `класс паладин`",
        ]
    )
    return "\n".join(lines)


def format_inventory(user_id):
    items = db.get_inventory(user_id)
    if not items:
        return (
            "🎒 *Инвентарь пуст*\n\n"
            "*Примеры:*\n"
            "• `добавь в инвентарь 3 зелья лечения`\n"
            "• `в инвентарь 1 веревка; длина=15м; вес=5`"
        )

    lines = ["🎒 *Инвентарь*", ""]
    for item in items:
        props = ", ".join(f"{k}: {v}" for k, v in item["properties"].items())
        details = f" | {props}" if props else ""
        notes = f" | {item['notes']}" if item["notes"] else ""
        lines.append(f"• {item['item_name']} x{item['quantity']}{details}{notes}")
    return "\n".join(lines)


def format_items(user_id):
    items = db.get_item_definitions(user_id)
    if not items:
        return (
            "🗡️ *Предметы не записаны*\n\n"
            "*Примеры:*\n"
            "• `предмет длинный меч; урон=1d8; вес=3; цена=15`\n"
            "• `предмет кольцо защиты; бонус_кд=1`"
        )

    lines = ["🗡️ *Предметы*", ""]
    for item in items:
        stats_text = ", ".join(f"{k}: {v}" for k, v in item["stats"].items())
        description = f" | {item['description']}" if item["description"] else ""
        if stats_text:
            lines.append(f"• {item['item_name']} | {stats_text}{description}")
        else:
            lines.append(f"• {item['item_name']}{description}")
    return "\n".join(lines)


def format_skills(user_id):
    skills = db.get_skills(user_id)
    if not skills:
        return (
            "✨ *Навыки не записаны*\n\n"
            "*Примеры:*\n"
            "• `навык скрытность +5`\n"
            "• `добавь навык взлом +7`"
        )

    lines = ["✨ *Навыки*", ""]
    for skill in skills:
        note = f" | {skill['notes']}" if skill["notes"] else ""
        lines.append(f"• {skill['skill_name']}: {skill['bonus']:+d}{note}")
    return "\n".join(lines)


def help_text():
    return (
        "📋 *DnD бот*\n\n"
        "Кнопки:\n"
        "• `🧙 Персонаж`\n"
        "• `🎒 Инвентарь`\n"
        "• `🗡️ Предметы`\n"
        "• `✨ Навыки`\n"
        "• `🎲 Кубы`\n\n"
        "Можно писать *без команд*:\n"
        "• `2d20+5`\n"
        "• `сила 18`\n"
        "• `хп 31`\n"
        "• `имя персонажа Боромир`\n"
        "• `класс воин`\n"
        "• `добавь в инвентарь 2 факела`\n"
        "• `предмет боевой молот; урон=1d8; вес=2`\n"
        "• `навык запугивание +4`\n"
        "• `покажи инвентарь`\n"
        "• `мои навыки`\n"
    )


def handle_character_update(user_id, text):
    low = text.lower()

    for prefix, field in (
        ("имя персонажа ", "name"),
        ("класс ", "class_name"),
        ("раса ", "race"),
        ("заметка ", "notes"),
    ):
        if low.startswith(prefix):
            value = text[len(prefix):].strip()
            if not value:
                return "❌ Нужное значение не указано."
            db.set_character_field(user_id, field, value)
            return f"✅ Поле `{field}` обновлено: *{value}*"

    stat_match = re.fullmatch(r"\s*([A-Za-zА-Яа-яёЁ_]+)\s*[:= ]\s*(-?\d+)\s*", text)
    if stat_match:
        raw_name = stat_match.group(1).lower()
        value = stat_match.group(2)
        stat_name = STAT_ALIASES.get(raw_name, raw_name)
        if stat_name == "level":
            db.set_character_field(user_id, "level", int(value))
            return f"✅ Уровень обновлен: *{value}*"
        db.set_stat(user_id, stat_name, value)
        return f"✅ Стат `{stat_name}` обновлен: *{value}*"

    return None


def handle_inventory_update(user_id, text):
    match = re.fullmatch(r"\s*(?:добавь\s+)?(?:в\s+инвентарь)\s+(\d+)?\s*(.+)", text, flags=re.IGNORECASE)
    if not match:
        return None

    quantity = int(match.group(1) or 1)
    body = match.group(2).strip()
    head, description, props = parse_key_value_segments(body)
    item_name = head.strip()
    if not item_name:
        return "❌ Не удалось понять название предмета для инвентаря."

    db.upsert_inventory_item(user_id, item_name, quantity=quantity, notes=description, properties=props)
    return f"✅ В инвентарь сохранено: *{item_name}* x{quantity}"


def handle_item_definition_update(user_id, text):
    match = re.fullmatch(r"\s*(?:добавь\s+)?предмет\s+(.+)", text, flags=re.IGNORECASE)
    if not match:
        return None

    head, description, stats = parse_key_value_segments(match.group(1).strip())
    item_name = head.strip()
    if not item_name:
        return "❌ Не удалось понять название предмета."

    db.upsert_item_definition(user_id, item_name, description=description, stats=stats)
    return f"✅ Предмет сохранен: *{item_name}*"


def handle_skill_update(user_id, text):
    match = re.fullmatch(
        r"\s*(?:добавь\s+)?навык\s+(.+?)\s+([+-]?\d+)(?:\s*[-:]\s*(.+))?\s*",
        text,
        flags=re.IGNORECASE,
    )
    if not match:
        return None

    skill_name = match.group(1).strip()
    bonus = int(match.group(2))
    notes = (match.group(3) or "").strip()
    db.upsert_skill(user_id, skill_name, bonus=bonus, notes=notes)
    return f"✅ Навык сохранен: *{skill_name}* {bonus:+d}"


def handle_show_requests(user_id, text):
    low = text.lower()
    if low in {"персонаж", "мои статы", "характеристики", "покажи персонажа"}:
        return format_character(user_id)
    if low in {"инвентарь", "мой инвентарь", "покажи инвентарь"}:
        return format_inventory(user_id)
    if low in {"предметы", "мои предметы", "покажи предметы"}:
        return format_items(user_id)
    if low in {"навыки", "мои навыки", "покажи навыки", "скилы"}:
        return format_skills(user_id)
    return None


def interpret_freeform(user_id, text):
    text = normalize_text(text)
    if not text:
        return "Напишите действие или используйте кнопки меню."

    dice_result = parse_dice_expression(text)
    if dice_result:
        return format_dice_result(dice_result)

    show_result = handle_show_requests(user_id, text)
    if show_result:
        return show_result

    for handler in (
        handle_character_update,
        handle_inventory_update,
        handle_item_definition_update,
        handle_skill_update,
    ):
        result = handler(user_id, text)
        if result:
            return result

    return (
        "Не понял запрос.\n\n"
        "Попробуйте один из примеров:\n"
        "• `2d20+5`\n"
        "• `сила 16`\n"
        "• `добавь в инвентарь 2 зелья лечения`\n"
        "• `предмет длинный меч; урон=1d8`\n"
        "• `навык скрытность +6`\n"
        "• `мои навыки`"
    )


@bot.message_handler(commands=["start", "menu"])
def handle_start(message):
    db.ensure_character(message.from_user.id)
    bot.send_message(
        message.chat.id,
        "Добро пожаловать в DnD-бота.\n\nВыбирайте раздел кнопками или пишите сразу в чат.",
        reply_markup=build_main_keyboard(),
    )


@bot.message_handler(func=lambda message: message.text == "🧙 Персонаж")
def handle_character_button(message):
    bot.reply_to(message, format_character(message.from_user.id))


@bot.message_handler(func=lambda message: message.text == "🎒 Инвентарь")
def handle_inventory_button(message):
    bot.reply_to(message, format_inventory(message.from_user.id))


@bot.message_handler(func=lambda message: message.text == "🗡️ Предметы")
def handle_items_button(message):
    bot.reply_to(message, format_items(message.from_user.id))


@bot.message_handler(func=lambda message: message.text == "✨ Навыки")
def handle_skills_button(message):
    bot.reply_to(message, format_skills(message.from_user.id))


@bot.message_handler(func=lambda message: message.text == "🎲 Кубы")
def handle_dice_button(message):
    bot.reply_to(
        message,
        "🎲 Отправьте бросок в виде `d20`, `2d6+3`, `4d8-1`.",
    )


@bot.message_handler(func=lambda message: message.text == "📋 Помощь")
def handle_help_button(message):
    bot.reply_to(message, help_text())


@bot.message_handler(content_types=["text"])
def handle_text(message):
    db.ensure_character(message.from_user.id)
    bot.reply_to(message, interpret_freeform(message.from_user.id, message.text))


if __name__ == "__main__":
    print("DND bot is starting...")
    bot.infinity_polling(timeout=60, long_polling_timeout=30)
