import ast
import operator
import os
import random
import re
from pathlib import Path

import telebot
from dotenv import load_dotenv
from telebot import types

from database import db


BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")

BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()

if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN is not set. Put it in .env before starting the bot.")

bot = telebot.TeleBot(BOT_TOKEN)

BTN_CHARACTER = "Персонаж"
BTN_INVENTORY = "Инвентарь"
BTN_ITEMS = "Предметы"
BTN_SKILLS = "Навыки"
BTN_CREATURES = "Мои существа"
BTN_ABILITIES = "Способности"
BTN_DICE = "Кубы"
BTN_HELP = "Помощь"
BTN_BACK = "Назад в меню"
BTN_CREATE_CREATURE = "Создать существо"
BTN_CREATE_ABILITY = "Создать способность"

CREATURE_PREFIX = "Существо: "
ABILITY_PREFIX = "Способность: "

SAFE_BINARY_OPS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
}

SAFE_UNARY_OPS = {
    ast.UAdd: operator.pos,
    ast.USub: operator.neg,
}

STAT_ALIASES = {
    "сила": "strength",
    "ловкость": "dexterity",
    "телосложение": "constitution",
    "интеллект": "intelligence",
    "мудрость": "wisdom",
    "харизма": "charisma",
    "хп": "hp",
    "hp": "hp",
    "кд": "ac",
    "ac": "ac",
    "инициатива": "initiative",
    "скорость": "speed",
    "уровень": "level",
    "очки чародейства": "sorcery_points",
    "очков чародейства": "sorcery_points",
    "очко чародейства": "sorcery_points",
}

STAT_LABELS = {
    "strength": "Сила",
    "dexterity": "Ловкость",
    "constitution": "Телосложение",
    "intelligence": "Интеллект",
    "wisdom": "Мудрость",
    "charisma": "Харизма",
    "hp": "ХП",
    "ac": "КД",
    "initiative": "Инициатива",
    "speed": "Скорость",
    "level": "Уровень",
    "sorcery_points": "Очки чародейства",
}

PRIMARY_STATS_ORDER = [
    "strength",
    "dexterity",
    "constitution",
    "intelligence",
    "wisdom",
    "charisma",
    "hp",
    "ac",
    "initiative",
    "speed",
]


def normalize_text(text):
    return (text or "").strip()


def stat_label(stat_name):
    return STAT_LABELS.get(stat_name, stat_name.replace("_", " ").capitalize())


def build_main_keyboard():
    keyboard = types.ReplyKeyboardMarkup(resize_keyboard=True)
    keyboard.row(types.KeyboardButton(BTN_CHARACTER), types.KeyboardButton(BTN_INVENTORY))
    keyboard.row(types.KeyboardButton(BTN_ITEMS), types.KeyboardButton(BTN_SKILLS))
    keyboard.row(types.KeyboardButton(BTN_CREATURES), types.KeyboardButton(BTN_ABILITIES))
    keyboard.row(types.KeyboardButton(BTN_DICE), types.KeyboardButton(BTN_HELP))
    return keyboard


def build_creatures_keyboard(user_id):
    keyboard = types.ReplyKeyboardMarkup(resize_keyboard=True)
    for creature in db.get_creatures(user_id):
        keyboard.row(types.KeyboardButton(f"{CREATURE_PREFIX}{creature['creature_name']}"))
    keyboard.row(types.KeyboardButton(BTN_CREATE_CREATURE), types.KeyboardButton(BTN_BACK))
    return keyboard


def build_abilities_keyboard(user_id):
    keyboard = types.ReplyKeyboardMarkup(resize_keyboard=True)
    for ability in db.get_abilities(user_id):
        keyboard.row(types.KeyboardButton(f"{ABILITY_PREFIX}{ability['ability_name']}"))
    keyboard.row(types.KeyboardButton(BTN_CREATE_ABILITY), types.KeyboardButton(BTN_BACK))
    return keyboard


def normalize_math_expression(text):
    expr = text.replace(" ", "").replace(",", ".")
    expr = re.sub(r"(\d+(?:\.\d+)?)%", r"(\1/100)", expr)
    return expr


def contains_only_math_tokens(text):
    return bool(text) and re.fullmatch(r"[0-9\.\,\+\-\*\/\(\)%\s]+", text) is not None


def eval_math_node(node):
    if isinstance(node, ast.Expression):
        return eval_math_node(node.body)
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
        return node.value
    if isinstance(node, ast.Num):
        return node.n
    if isinstance(node, ast.BinOp) and type(node.op) in SAFE_BINARY_OPS:
        left = eval_math_node(node.left)
        right = eval_math_node(node.right)
        return SAFE_BINARY_OPS[type(node.op)](left, right)
    if isinstance(node, ast.UnaryOp) and type(node.op) in SAFE_UNARY_OPS:
        operand = eval_math_node(node.operand)
        return SAFE_UNARY_OPS[type(node.op)](operand)
    raise ValueError("Unsupported expression")


def parse_math_expression(text):
    if not contains_only_math_tokens(text):
        return None

    raw_expr = text.replace(" ", "").replace(",", ".")
    percent_match = re.fullmatch(r"(.+?)([+\-])(\d+(?:\.\d+)?)%", raw_expr)
    if percent_match:
        base_expr = percent_match.group(1)
        operator_symbol = percent_match.group(2)
        percent_value = float(percent_match.group(3))
        base_value = parse_math_expression(base_expr)
        if base_value is None:
            return None
        delta = base_value * percent_value / 100
        value = base_value + delta if operator_symbol == "+" else base_value - delta
        return int(round(value)) if abs(value - round(value)) < 1e-9 else round(value, 4)

    expr = normalize_math_expression(text)
    try:
        tree = ast.parse(expr, mode="eval")
        value = eval_math_node(tree)
    except Exception:
        return None

    if isinstance(value, float):
        value = int(round(value)) if abs(value - round(value)) < 1e-9 else round(value, 4)
    return value


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
    return {
        "count": count,
        "sides": sides,
        "modifier": modifier,
        "rolls": rolls,
        "total": sum(rolls) + modifier,
    }


def parse_named_roll(text):
    match = re.fullmatch(
        r"\s*(атака|бросок|чек|проверка)\s+(.+?)\s+(\d*d\d+(?:[+-]\d+)?)\s*",
        text.lower(),
    )
    if not match:
        return None

    roll = parse_dice_expression(match.group(3))
    if not roll:
        return None

    roll["kind"] = match.group(1)
    roll["label"] = match.group(2).strip()
    return roll


def format_dice_result(result):
    modifier = f"{result['modifier']:+d}" if result["modifier"] else ""
    rolls = ", ".join(str(value) for value in result["rolls"])
    return (
        f"Бросок: {result['count']}d{result['sides']}{modifier}\n"
        f"Выпало: {rolls}\n"
        f"Итог: {result['total']}"
    )


def format_named_roll_result(result):
    return f"{result['kind'].capitalize()} {result['label']}\n\n{format_dice_result(result)}"


def parse_key_value_segments(text):
    segments = [segment.strip() for segment in text.split(";") if segment.strip()]
    if not segments:
        return "", "", {}

    head = segments[0]
    description_parts = []
    stats = {}
    for segment in segments[1:]:
        if "=" in segment:
            key, value = segment.split("=", 1)
            stats[key.strip().lower()] = value.strip()
        else:
            description_parts.append(segment)
    return head, " | ".join(description_parts), stats


def extract_description_and_notes(stats):
    stats = dict(stats)
    description = ""
    notes = ""
    for key in ("описание", "description"):
        if key in stats:
            description = stats.pop(key)
            break
    for key in ("заметка", "заметки", "notes"):
        if key in stats:
            notes = stats.pop(key)
            break
    return description, notes, stats


def format_character(user_id):
    character = db.get_character(user_id)
    stats = db.get_stats(user_id)
    lines = [
        "Персонаж",
        "",
        f"Имя: {character.get('name') or 'не задано'}",
        f"Класс: {character.get('class_name') or 'не задан'}",
        f"Раса: {character.get('race') or 'не задана'}",
        f"Уровень: {character.get('level') or 1}",
        f"Очки чародейства: {character.get('sorcery_points') or 0}",
    ]

    if stats:
        lines.extend(["", "Характеристики:"])
        for key in PRIMARY_STATS_ORDER:
            if key in stats:
                lines.append(f"- {stat_label(key)}: {stats[key]}")
        for key, value in stats.items():
            if key not in PRIMARY_STATS_ORDER:
                lines.append(f"- {stat_label(key)}: {value}")
    else:
        lines.extend(["", "Характеристики пока не записаны."])

    if character.get("notes"):
        lines.extend(["", f"Заметки: {character['notes']}"])

    lines.extend(
        [
            "",
            "Примеры:",
            "- сила 16",
            "- хп 24",
            "- очки чародейства 5",
            "- имя персонажа Арден",
            "- класс чародей",
        ]
    )
    return "\n".join(lines)


def format_inventory(user_id):
    items = db.get_inventory(user_id)
    if not items:
        return (
            "Инвентарь пуст.\n\n"
            "Примеры:\n"
            "- добавь в инвентарь 3 зелья лечения\n"
            "- в инвентарь 1 веревка; длина=15м; вес=5"
        )

    lines = ["Инвентарь", ""]
    for item in items:
        props = ", ".join(f"{key}: {value}" for key, value in item["properties"].items())
        details = f" | {props}" if props else ""
        notes = f" | {item['notes']}" if item["notes"] else ""
        lines.append(f"- {item['item_name']} x{item['quantity']}{details}{notes}")
    return "\n".join(lines)


def format_items(user_id):
    items = db.get_item_definitions(user_id)
    if not items:
        return (
            "Предметы пока не записаны.\n\n"
            "Примеры:\n"
            "- предмет длинный меч; урон=1d8; вес=3; цена=15\n"
            "- предмет кольцо защиты; бонус_кд=1"
        )

    lines = ["Предметы", ""]
    for item in items:
        stats_text = ", ".join(f"{key}: {value}" for key, value in item["stats"].items())
        description = f" | {item['description']}" if item["description"] else ""
        lines.append(f"- {item['item_name']}{' | ' + stats_text if stats_text else ''}{description}")
    return "\n".join(lines)


def format_skills(user_id):
    skills = db.get_skills(user_id)
    if not skills:
        return (
            "Навыки пока не записаны.\n\n"
            "Примеры:\n"
            "- навык скрытность +5\n"
            "- добавь навык взлом +7"
        )

    lines = ["Навыки", ""]
    for skill in skills:
        notes = f" | {skill['notes']}" if skill["notes"] else ""
        lines.append(f"- {skill['skill_name']}: {skill['bonus']:+d}{notes}")
    return "\n".join(lines)


def format_creatures(user_id):
    creatures = db.get_creatures(user_id)
    if not creatures:
        return (
            "У вас пока нет существ.\n\n"
            "Пример:\n"
            "- существо волк; кд=13; хп=11; скорость=40; описание=Серый волк"
        )

    lines = ["Мои существа", ""]
    for creature in creatures:
        short_stats = ", ".join(f"{key}: {value}" for key, value in list(creature["stats"].items())[:3])
        suffix = f" | {short_stats}" if short_stats else ""
        lines.append(f"- {creature['creature_name']}{suffix}")
    lines.extend(["", "Нажмите кнопку с именем существа, чтобы открыть карточку."])
    return "\n".join(lines)


def format_creature_card(user_id, creature_name):
    creature = db.get_creature(user_id, creature_name)
    if not creature:
        return f"Существо «{creature_name}» не найдено."

    lines = [f"Существо: {creature['creature_name']}"]
    if creature["description"]:
        lines.extend(["", f"Описание: {creature['description']}"])
    if creature["stats"]:
        lines.extend(["", "Характеристики:"])
        for key, value in creature["stats"].items():
            lines.append(f"- {key}: {value}")
    if creature["notes"]:
        lines.extend(["", f"Заметки: {creature['notes']}"])
    return "\n".join(lines)


def format_abilities(user_id):
    abilities = db.get_abilities(user_id)
    if not abilities:
        return (
            "У вас пока нет способностей.\n\n"
            "Пример:\n"
            "- способность Огненный шар; уровень=3; урон=8d6; описание=Взрыв огня"
        )

    lines = ["Способности", ""]
    for ability in abilities:
        short_stats = ", ".join(f"{key}: {value}" for key, value in list(ability["stats"].items())[:3])
        suffix = f" | {short_stats}" if short_stats else ""
        lines.append(f"- {ability['ability_name']}{suffix}")
    lines.extend(["", "Нажмите кнопку с именем способности, чтобы открыть карточку."])
    return "\n".join(lines)


def format_ability_card(user_id, ability_name):
    ability = db.get_ability(user_id, ability_name)
    if not ability:
        return f"Способность «{ability_name}» не найдена."

    lines = [f"Способность: {ability['ability_name']}"]
    if ability["description"]:
        lines.extend(["", f"Описание: {ability['description']}"])
    if ability["stats"]:
        lines.extend(["", "Параметры:"])
        for key, value in ability["stats"].items():
            lines.append(f"- {key}: {value}")
    if ability["notes"]:
        lines.extend(["", f"Заметки: {ability['notes']}"])
    return "\n".join(lines)


def help_text():
    return (
        "DnD-бот\n\n"
        "Основные разделы:\n"
        f"- {BTN_CHARACTER}\n"
        f"- {BTN_INVENTORY}\n"
        f"- {BTN_ITEMS}\n"
        f"- {BTN_SKILLS}\n"
        f"- {BTN_CREATURES}\n"
        f"- {BTN_ABILITIES}\n"
        f"- {BTN_DICE}\n\n"
        "Можно писать без команд:\n"
        "- 2d20+5\n"
        "- 54-30%\n"
        "- сила 18\n"
        "- очки чародейства 5\n"
        "- добавь в инвентарь 2 факела\n"
        "- предмет длинный меч; урон=1d8\n"
        "- навык скрытность +6\n"
        "- существо волк; кд=13; хп=11\n"
        "- способность Огненный шар; уровень=3; урон=8d6\n"
    )


def handle_character_update(user_id, text):
    low = text.lower()

    for prefix, field in (
        ("имя персонажа ", "name"),
        ("класс ", "class_name"),
        ("раса ", "race"),
        ("заметка ", "notes"),
        ("заметки ", "notes"),
    ):
        if low.startswith(prefix):
            value = text[len(prefix):].strip()
            if not value:
                return "Нужно указать значение."
            db.set_character_field(user_id, field, value)
            names = {
                "name": "Имя персонажа",
                "class_name": "Класс",
                "race": "Раса",
                "notes": "Заметки",
            }
            return f"{names[field]} обновлено: {value}"

    stat_match = re.fullmatch(r"\s*([A-Za-zА-Яа-яЁё_ ]+)\s*[:= ]\s*(-?\d+)\s*", text)
    if stat_match:
        raw_name = stat_match.group(1).strip().lower()
        value = int(stat_match.group(2))
        stat_name = STAT_ALIASES.get(raw_name, raw_name)
        if stat_name == "level":
            db.set_character_field(user_id, "level", value)
            return f"Уровень обновлен: {value}"
        if stat_name == "sorcery_points":
            db.set_character_field(user_id, "sorcery_points", value)
            return f"Очки чародейства обновлены: {value}"
        db.set_stat(user_id, stat_name, value)
        return f"{stat_label(stat_name)} обновлено: {value}"

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
        return "Не удалось понять название предмета для инвентаря."

    db.upsert_inventory_item(user_id, item_name, quantity=quantity, notes=description, properties=props)
    return f"В инвентарь добавлено: {item_name} x{quantity}"


def handle_inventory_delete(user_id, text):
    match = re.fullmatch(r"\s*(?:удали|убери)\s+(?:из\s+инвентаря\s+)?(.+)", text, flags=re.IGNORECASE)
    if not match:
        return None
    item_name = match.group(1).strip()
    if db.delete_inventory_item(user_id, item_name):
        return f"Из инвентаря удалено: {item_name}"
    return f"Предмет «{item_name}» не найден в инвентаре."


def handle_item_definition_update(user_id, text):
    match = re.fullmatch(r"\s*(?:добавь\s+)?предмет\s+(.+)", text, flags=re.IGNORECASE)
    if not match:
        return None

    head, description, stats = parse_key_value_segments(match.group(1).strip())
    item_name = head.strip()
    if not item_name:
        return "Не удалось понять название предмета."

    db.upsert_item_definition(user_id, item_name, description=description, stats=stats)
    return f"Предмет сохранен: {item_name}"


def handle_item_definition_delete(user_id, text):
    match = re.fullmatch(r"\s*(?:удали|убери)\s+предмет\s+(.+)", text, flags=re.IGNORECASE)
    if not match:
        return None
    item_name = match.group(1).strip()
    if db.delete_item_definition(user_id, item_name):
        return f"Предмет удален: {item_name}"
    return f"Предмет «{item_name}» не найден."


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
    return f"Навык сохранен: {skill_name} {bonus:+d}"


def handle_skill_delete(user_id, text):
    match = re.fullmatch(r"\s*(?:удали|убери)\s+навык\s+(.+)", text, flags=re.IGNORECASE)
    if not match:
        return None
    skill_name = match.group(1).strip()
    if db.delete_skill(user_id, skill_name):
        return f"Навык удален: {skill_name}"
    return f"Навык «{skill_name}» не найден."


def handle_creature_update(user_id, text):
    match = re.fullmatch(r"\s*(?:добавь\s+)?существо\s+(.+)", text, flags=re.IGNORECASE)
    if not match:
        return None

    head, description, stats = parse_key_value_segments(match.group(1).strip())
    creature_name = head.strip()
    if not creature_name:
        return "Не удалось понять имя существа."

    extra_description, notes, stats = extract_description_and_notes(stats)
    final_description = extra_description or description
    db.upsert_creature(user_id, creature_name, description=final_description, stats=stats, notes=notes)
    return f"Существо сохранено: {creature_name}"


def handle_creature_delete(user_id, text):
    match = re.fullmatch(r"\s*(?:удали|убери)\s+существо\s+(.+)", text, flags=re.IGNORECASE)
    if not match:
        return None
    creature_name = match.group(1).strip()
    if db.delete_creature(user_id, creature_name):
        return f"Существо удалено: {creature_name}"
    return f"Существо «{creature_name}» не найдено."


def handle_ability_update(user_id, text):
    match = re.fullmatch(r"\s*(?:добавь\s+)?способность\s+(.+)", text, flags=re.IGNORECASE)
    if not match:
        return None

    head, description, stats = parse_key_value_segments(match.group(1).strip())
    ability_name = head.strip()
    if not ability_name:
        return "Не удалось понять название способности."

    extra_description, notes, stats = extract_description_and_notes(stats)
    final_description = extra_description or description
    db.upsert_ability(user_id, ability_name, description=final_description, stats=stats, notes=notes)
    return f"Способность сохранена: {ability_name}"


def handle_ability_delete(user_id, text):
    match = re.fullmatch(r"\s*(?:удали|убери)\s+способность\s+(.+)", text, flags=re.IGNORECASE)
    if not match:
        return None
    ability_name = match.group(1).strip()
    if db.delete_ability(user_id, ability_name):
        return f"Способность удалена: {ability_name}"
    return f"Способность «{ability_name}» не найдена."


def handle_show_requests(user_id, text):
    low = text.lower()
    if text == BTN_CHARACTER or low in {"персонаж", "мои статы", "характеристики", "покажи персонажа"}:
        return format_character(user_id)
    if text == BTN_INVENTORY or low in {"инвентарь", "мой инвентарь", "покажи инвентарь"}:
        return format_inventory(user_id)
    if text == BTN_ITEMS or low in {"предметы", "мои предметы", "покажи предметы"}:
        return format_items(user_id)
    if text == BTN_SKILLS or low in {"навыки", "мои навыки", "покажи навыки", "скилы"}:
        return format_skills(user_id)
    if text == BTN_CREATURES or low in {"мои существа", "существа", "покажи существ"}:
        return format_creatures(user_id)
    if text == BTN_ABILITIES or low in {"способности", "мои способности", "покажи способности"}:
        return format_abilities(user_id)
    if text.startswith(CREATURE_PREFIX):
        return format_creature_card(user_id, text[len(CREATURE_PREFIX):].strip())
    if text.startswith(ABILITY_PREFIX):
        return format_ability_card(user_id, text[len(ABILITY_PREFIX):].strip())
    return None


def fallback_text():
    return (
        "Попробуйте одну из форм:\n"
        "- 5+2\n"
        "- 54-30%\n"
        "- 2d20+5\n"
        "- атака мечом 1d20+5\n"
        "- сила 16\n"
        "- очки чародейства 5\n"
        "- добавь в инвентарь 2 зелья лечения\n"
        "- предмет длинный меч; урон=1d8\n"
        "- навык скрытность +6\n"
        "- существо волк; кд=13; хп=11\n"
        "- способность Огненный шар; уровень=3; урон=8d6"
    )


def interpret_freeform(user_id, text):
    text = normalize_text(text)
    if not text:
        return "Напишите запрос или используйте кнопки меню."

    math_result = parse_math_expression(text)
    if math_result is not None:
        return f"Результат: {text} = {math_result}"

    named_roll = parse_named_roll(text)
    if named_roll:
        return format_named_roll_result(named_roll)

    dice_result = parse_dice_expression(text)
    if dice_result:
        return format_dice_result(dice_result)

    show_result = handle_show_requests(user_id, text)
    if show_result:
        return show_result

    for handler in (
        handle_character_update,
        handle_inventory_delete,
        handle_inventory_update,
        handle_item_definition_delete,
        handle_item_definition_update,
        handle_skill_delete,
        handle_skill_update,
        handle_creature_delete,
        handle_creature_update,
        handle_ability_delete,
        handle_ability_update,
    ):
        result = handler(user_id, text)
        if result:
            return result

    return fallback_text()


@bot.message_handler(commands=["start", "menu"])
def handle_start(message):
    db.ensure_character(message.from_user.id)
    bot.send_message(
        message.chat.id,
        "Добро пожаловать в DnD-бота.\n\nВыберите раздел кнопками или пишите сразу в чат.",
        reply_markup=build_main_keyboard(),
    )


@bot.message_handler(func=lambda message: message.text == BTN_CHARACTER)
def handle_character_button(message):
    bot.reply_to(message, format_character(message.from_user.id), reply_markup=build_main_keyboard())


@bot.message_handler(func=lambda message: message.text == BTN_INVENTORY)
def handle_inventory_button(message):
    bot.reply_to(message, format_inventory(message.from_user.id), reply_markup=build_main_keyboard())


@bot.message_handler(func=lambda message: message.text == BTN_ITEMS)
def handle_items_button(message):
    bot.reply_to(message, format_items(message.from_user.id), reply_markup=build_main_keyboard())


@bot.message_handler(func=lambda message: message.text == BTN_SKILLS)
def handle_skills_button(message):
    bot.reply_to(message, format_skills(message.from_user.id), reply_markup=build_main_keyboard())


@bot.message_handler(func=lambda message: message.text == BTN_CREATURES)
def handle_creatures_button(message):
    bot.reply_to(message, format_creatures(message.from_user.id), reply_markup=build_creatures_keyboard(message.from_user.id))


@bot.message_handler(func=lambda message: message.text == BTN_ABILITIES)
def handle_abilities_button(message):
    bot.reply_to(message, format_abilities(message.from_user.id), reply_markup=build_abilities_keyboard(message.from_user.id))


@bot.message_handler(func=lambda message: message.text == BTN_CREATE_CREATURE)
def handle_create_creature_button(message):
    bot.reply_to(
        message,
        "Напишите существо в формате:\nсущество волк; кд=13; хп=11; скорость=40; описание=Серый волк",
        reply_markup=build_creatures_keyboard(message.from_user.id),
    )


@bot.message_handler(func=lambda message: message.text == BTN_CREATE_ABILITY)
def handle_create_ability_button(message):
    bot.reply_to(
        message,
        "Напишите способность в формате:\nспособность Огненный шар; уровень=3; урон=8d6; описание=Взрыв огня",
        reply_markup=build_abilities_keyboard(message.from_user.id),
    )


@bot.message_handler(func=lambda message: message.text == BTN_BACK)
def handle_back_button(message):
    bot.reply_to(message, "Главное меню.", reply_markup=build_main_keyboard())


@bot.message_handler(func=lambda message: message.text == BTN_DICE)
def handle_dice_button(message):
    bot.reply_to(
        message,
        "Отправьте бросок в формате d20, 2d6+3, 4d8-1 или текст вроде «атака мечом 1d20+5».",
        reply_markup=build_main_keyboard(),
    )


@bot.message_handler(func=lambda message: message.text == BTN_HELP)
def handle_help_button(message):
    bot.reply_to(message, help_text(), reply_markup=build_main_keyboard())


@bot.message_handler(func=lambda message: message.text.startswith(CREATURE_PREFIX))
def handle_creature_card_button(message):
    creature_name = message.text[len(CREATURE_PREFIX):].strip()
    bot.reply_to(
        message,
        format_creature_card(message.from_user.id, creature_name),
        reply_markup=build_creatures_keyboard(message.from_user.id),
    )


@bot.message_handler(func=lambda message: message.text.startswith(ABILITY_PREFIX))
def handle_ability_card_button(message):
    ability_name = message.text[len(ABILITY_PREFIX):].strip()
    bot.reply_to(
        message,
        format_ability_card(message.from_user.id, ability_name),
        reply_markup=build_abilities_keyboard(message.from_user.id),
    )


@bot.message_handler(content_types=["text"])
def handle_text(message):
    db.ensure_character(message.from_user.id)
    response = interpret_freeform(message.from_user.id, message.text)

    reply_markup = build_main_keyboard()
    low = normalize_text(message.text).lower()
    if low.startswith("существо ") or message.text == BTN_CREATE_CREATURE or message.text.startswith(CREATURE_PREFIX):
        reply_markup = build_creatures_keyboard(message.from_user.id)
    elif low.startswith("способность ") or message.text == BTN_CREATE_ABILITY or message.text.startswith(ABILITY_PREFIX):
        reply_markup = build_abilities_keyboard(message.from_user.id)
    elif message.text == BTN_CREATURES:
        reply_markup = build_creatures_keyboard(message.from_user.id)
    elif message.text == BTN_ABILITIES:
        reply_markup = build_abilities_keyboard(message.from_user.id)

    bot.reply_to(message, response, reply_markup=reply_markup)


if __name__ == "__main__":
    print("DND bot is starting...")
    bot.infinity_polling(timeout=60, long_polling_timeout=30)
