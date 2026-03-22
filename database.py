import json
import sqlite3
import threading
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "dnd_bot.db"


class Database:
    def __init__(self, db_path=None):
        self.db_path = Path(db_path) if db_path else DB_PATH
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.lock = threading.RLock()
        self.init_db()

    def _connect(self):
        conn = sqlite3.connect(self.db_path, check_same_thread=False, timeout=30)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("PRAGMA journal_mode = WAL")
        return conn

    def init_db(self):
        with self.lock:
            conn = self._connect()
            cur = conn.cursor()

            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS characters (
                    user_id INTEGER PRIMARY KEY,
                    name TEXT DEFAULT '',
                    class_name TEXT DEFAULT '',
                    race TEXT DEFAULT '',
                    level INTEGER DEFAULT 1,
                    notes TEXT DEFAULT '',
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
                """
            )

            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS character_stats (
                    user_id INTEGER NOT NULL,
                    stat_name TEXT NOT NULL,
                    stat_value TEXT NOT NULL,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (user_id, stat_name)
                )
                """
            )

            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS inventory_items (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    item_name TEXT NOT NULL,
                    quantity INTEGER DEFAULT 1,
                    notes TEXT DEFAULT '',
                    properties_json TEXT DEFAULT '{}',
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE (user_id, item_name)
                )
                """
            )

            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS item_definitions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    item_name TEXT NOT NULL,
                    description TEXT DEFAULT '',
                    stats_json TEXT DEFAULT '{}',
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE (user_id, item_name)
                )
                """
            )

            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS skills (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    skill_name TEXT NOT NULL,
                    bonus INTEGER DEFAULT 0,
                    notes TEXT DEFAULT '',
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE (user_id, skill_name)
                )
                """
            )

            conn.commit()
            conn.close()

    def ensure_character(self, user_id):
        with self.lock:
            conn = self._connect()
            cur = conn.cursor()
            cur.execute("INSERT OR IGNORE INTO characters (user_id) VALUES (?)", (user_id,))
            conn.commit()
            conn.close()

    def set_character_field(self, user_id, field_name, value):
        if field_name not in {"name", "class_name", "race", "level", "notes"}:
            raise ValueError(f"Unsupported field: {field_name}")
        self.ensure_character(user_id)
        with self.lock:
            conn = self._connect()
            cur = conn.cursor()
            cur.execute(
                f"UPDATE characters SET {field_name} = ?, updated_at = CURRENT_TIMESTAMP WHERE user_id = ?",
                (value, user_id),
            )
            conn.commit()
            conn.close()

    def get_character(self, user_id):
        self.ensure_character(user_id)
        conn = self._connect()
        cur = conn.cursor()
        cur.execute("SELECT * FROM characters WHERE user_id = ?", (user_id,))
        row = cur.fetchone()
        conn.close()
        return dict(row) if row else None

    def set_stat(self, user_id, stat_name, stat_value):
        self.ensure_character(user_id)
        with self.lock:
            conn = self._connect()
            cur = conn.cursor()
            cur.execute(
                """
                INSERT INTO character_stats (user_id, stat_name, stat_value)
                VALUES (?, ?, ?)
                ON CONFLICT(user_id, stat_name)
                DO UPDATE SET stat_value = excluded.stat_value, updated_at = CURRENT_TIMESTAMP
                """,
                (user_id, stat_name.lower(), str(stat_value)),
            )
            conn.commit()
            conn.close()

    def get_stats(self, user_id):
        conn = self._connect()
        cur = conn.cursor()
        cur.execute(
            "SELECT stat_name, stat_value FROM character_stats WHERE user_id = ? ORDER BY stat_name",
            (user_id,),
        )
        rows = cur.fetchall()
        conn.close()
        return {row["stat_name"]: row["stat_value"] for row in rows}

    def upsert_skill(self, user_id, skill_name, bonus=0, notes=""):
        self.ensure_character(user_id)
        with self.lock:
            conn = self._connect()
            cur = conn.cursor()
            cur.execute(
                """
                INSERT INTO skills (user_id, skill_name, bonus, notes)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(user_id, skill_name)
                DO UPDATE SET bonus = excluded.bonus, notes = excluded.notes, updated_at = CURRENT_TIMESTAMP
                """,
                (user_id, skill_name.strip(), int(bonus), notes.strip()),
            )
            conn.commit()
            conn.close()

    def get_skills(self, user_id):
        conn = self._connect()
        cur = conn.cursor()
        cur.execute(
            "SELECT skill_name, bonus, notes FROM skills WHERE user_id = ? ORDER BY skill_name",
            (user_id,),
        )
        rows = cur.fetchall()
        conn.close()
        return [dict(row) for row in rows]

    def upsert_item_definition(self, user_id, item_name, description="", stats=None):
        self.ensure_character(user_id)
        stats_payload = json.dumps(stats or {}, ensure_ascii=False)
        with self.lock:
            conn = self._connect()
            cur = conn.cursor()
            cur.execute(
                """
                INSERT INTO item_definitions (user_id, item_name, description, stats_json)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(user_id, item_name)
                DO UPDATE SET description = excluded.description, stats_json = excluded.stats_json,
                              updated_at = CURRENT_TIMESTAMP
                """,
                (user_id, item_name.strip(), description.strip(), stats_payload),
            )
            conn.commit()
            conn.close()

    def get_item_definitions(self, user_id):
        conn = self._connect()
        cur = conn.cursor()
        cur.execute(
            "SELECT item_name, description, stats_json FROM item_definitions WHERE user_id = ? ORDER BY item_name",
            (user_id,),
        )
        rows = cur.fetchall()
        conn.close()
        items = []
        for row in rows:
            item = dict(row)
            item["stats"] = json.loads(item.pop("stats_json") or "{}")
            items.append(item)
        return items

    def upsert_inventory_item(self, user_id, item_name, quantity=1, notes="", properties=None):
        self.ensure_character(user_id)
        properties_payload = json.dumps(properties or {}, ensure_ascii=False)
        with self.lock:
            conn = self._connect()
            cur = conn.cursor()
            cur.execute(
                """
                INSERT INTO inventory_items (user_id, item_name, quantity, notes, properties_json)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(user_id, item_name)
                DO UPDATE SET quantity = excluded.quantity, notes = excluded.notes,
                              properties_json = excluded.properties_json, updated_at = CURRENT_TIMESTAMP
                """,
                (user_id, item_name.strip(), int(quantity), notes.strip(), properties_payload),
            )
            conn.commit()
            conn.close()

    def get_inventory(self, user_id):
        conn = self._connect()
        cur = conn.cursor()
        cur.execute(
            "SELECT item_name, quantity, notes, properties_json FROM inventory_items WHERE user_id = ? ORDER BY item_name",
            (user_id,),
        )
        rows = cur.fetchall()
        conn.close()
        items = []
        for row in rows:
            item = dict(row)
            item["properties"] = json.loads(item.pop("properties_json") or "{}")
            items.append(item)
        return items


db = Database()
