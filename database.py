"""Local SQLite Memory & Profile Intelligence Database for PulseAI Agent."""
import sqlite3
import threading
from datetime import datetime
from typing import Any, Dict, List, Optional

DB_PATH = "agent_memory.db"
_DB_LOCK = threading.RLock()


def get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn


def init_db() -> None:
    with _DB_LOCK, get_conn() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS contacts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                handle TEXT NOT NULL,
                platform TEXT NOT NULL,
                name TEXT DEFAULT '',
                profile_url TEXT DEFAULT '',
                persona TEXT DEFAULT 'personal',
                stage TEXT DEFAULT 'casual',
                warmth_score INTEGER DEFAULT 4,
                whitelisted INTEGER DEFAULT 1,
                chat_style TEXT DEFAULT '',
                chat_target TEXT DEFAULT '',
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(handle, platform)
            );

            CREATE TABLE IF NOT EXISTS profile_intel (
                contact_id INTEGER PRIMARY KEY,
                bio_summary TEXT DEFAULT '',
                fav_songs TEXT DEFAULT '',
                hobbies TEXT DEFAULT '',
                likes TEXT DEFAULT '',
                dislikes TEXT DEFAULT '',
                vibe_notes TEXT DEFAULT '',
                role_company TEXT DEFAULT '',
                skills TEXT DEFAULT '',
                recent_activity TEXT DEFAULT '',
                conversation_goal TEXT DEFAULT '',
                last_scanned TEXT DEFAULT '',
                FOREIGN KEY(contact_id) REFERENCES contacts(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS chat_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                contact_id INTEGER NOT NULL,
                sender TEXT NOT NULL,
                content TEXT NOT NULL,
                mood TEXT DEFAULT '',
                timestamp TEXT DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(contact_id) REFERENCES contacts(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS memory_facts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                contact_id INTEGER NOT NULL,
                category TEXT NOT NULL,
                fact TEXT NOT NULL,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(contact_id, fact),
                FOREIGN KEY(contact_id) REFERENCES contacts(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS activity_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                platform TEXT NOT NULL,
                level TEXT DEFAULT 'info',
                message TEXT NOT NULL,
                timestamp TEXT DEFAULT CURRENT_TIMESTAMP
            );
            """
        )
        # Auto-migrate older databases cleanly
        cols = {row["name"] for row in conn.execute("PRAGMA table_info(contacts)").fetchall()}
        if "chat_style" not in cols:
            conn.execute("ALTER TABLE contacts ADD COLUMN chat_style TEXT DEFAULT ''")
        if "chat_target" not in cols:
            conn.execute("ALTER TABLE contacts ADD COLUMN chat_target TEXT DEFAULT ''")


def log_event(platform: str, message: str, level: str = "info") -> None:
    now = datetime.now().strftime("%H:%M:%S")
    with _DB_LOCK, get_conn() as conn:
        conn.execute(
            "INSERT INTO activity_logs (platform, level, message, timestamp) VALUES (?, ?, ?, ?)",
            (platform, level, message, now),
        )
        conn.execute(
            """
            DELETE FROM activity_logs
            WHERE id NOT IN (SELECT id FROM activity_logs ORDER BY id DESC LIMIT 300)
            """
        )


def get_logs(limit: int = 60) -> List[Dict[str, Any]]:
    with _DB_LOCK, get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM activity_logs ORDER BY id DESC LIMIT ?", (limit,)
        ).fetchall()
    return [dict(r) for r in reversed(rows)]


def upsert_contact(
    handle: str,
    platform: str,
    name: str = "",
    profile_url: str = "",
    persona: Optional[str] = None,
    stage: str = "casual",
    whitelisted: int = 1,
    chat_style: str = "",
    chat_target: str = "",
) -> int:
    handle = handle.strip()
    platform = platform.strip().lower()
    default_persona = "professional" if platform == "linkedin" else "personal"
    chosen_persona = persona or default_persona

    with _DB_LOCK, get_conn() as conn:
        row = conn.execute(
            "SELECT id FROM contacts WHERE handle = ? AND platform = ?",
            (handle, platform),
        ).fetchone()
        if row:
            updates = []
            params: List[Any] = []
            if name:
                updates.append("name = ?")
                params.append(name)
            if profile_url:
                updates.append("profile_url = ?")
                params.append(profile_url)
            if persona:
                updates.append("persona = ?")
                params.append(persona)
            if chat_style:
                updates.append("chat_style = ?")
                params.append(chat_style.strip())
            if chat_target:
                updates.append("chat_target = ?")
                params.append(chat_target.strip())
            if updates:
                params.append(row["id"])
                conn.execute(
                    f"UPDATE contacts SET {', '.join(updates)} WHERE id = ?", params
                )
            return int(row["id"])

        cur = conn.execute(
            """
            INSERT INTO contacts
                (handle, platform, name, profile_url, persona, stage, whitelisted, chat_style, chat_target)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                handle,
                platform,
                name or handle,
                profile_url,
                chosen_persona,
                stage,
                whitelisted,
                chat_style.strip(),
                chat_target.strip(),
            ),
        )
        contact_id = int(cur.lastrowid)
        conn.execute(
            "INSERT OR IGNORE INTO profile_intel (contact_id) VALUES (?)",
            (contact_id,),
        )
        return contact_id


def delete_contact(contact_id: int) -> None:
    with _DB_LOCK, get_conn() as conn:
        conn.execute("DELETE FROM contacts WHERE id = ?", (contact_id,))


def list_contacts(platform: Optional[str] = None) -> List[Dict[str, Any]]:
    with _DB_LOCK, get_conn() as conn:
        if platform:
            rows = conn.execute(
                "SELECT * FROM contacts WHERE platform = ? ORDER BY id DESC",
                (platform.lower(),),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM contacts ORDER BY platform, id DESC"
            ).fetchall()
    return [dict(r) for r in rows]


def get_contact_by_handle(handle: str, platform: str) -> Optional[Dict[str, Any]]:
    with _DB_LOCK, get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM contacts WHERE LOWER(handle) = LOWER(?) AND platform = ?",
            (handle.strip(), platform.strip().lower()),
        ).fetchone()
    return dict(row) if row else None


def update_contact_settings(
    contact_id: int,
    persona: Optional[str] = None,
    stage: Optional[str] = None,
    warmth_score: Optional[int] = None,
    whitelisted: Optional[int] = None,
    name: Optional[str] = None,
    profile_url: Optional[str] = None,
    chat_style: Optional[str] = None,
    chat_target: Optional[str] = None,
) -> None:
    valid_personas = {"personal", "friendly", "professional"}
    valid_stages = {"casual", "flirty", "romantic", "propose"}
    updates = []
    params: List[Any] = []

    if persona in valid_personas:
        updates.append("persona = ?")
        params.append(persona)
    if stage in valid_stages:
        updates.append("stage = ?")
        params.append(stage)
    if warmth_score is not None:
        updates.append("warmth_score = ?")
        params.append(max(1, min(10, int(warmth_score))))
    if whitelisted is not None:
        updates.append("whitelisted = ?")
        params.append(1 if whitelisted else 0)
    if name is not None:
        updates.append("name = ?")
        params.append(name.strip())
    if profile_url is not None:
        updates.append("profile_url = ?")
        params.append(profile_url.strip())
    if chat_style is not None:
        updates.append("chat_style = ?")
        params.append(chat_style.strip())
    if chat_target is not None:
        updates.append("chat_target = ?")
        params.append(chat_target.strip())

    if not updates:
        return

    params.append(contact_id)
    with _DB_LOCK, get_conn() as conn:
        conn.execute(f"UPDATE contacts SET {', '.join(updates)} WHERE id = ?", params)


def update_stage_warmth(
    contact_id: int, stage: Optional[str] = None, warmth_delta: int = 0
) -> None:
    with _DB_LOCK, get_conn() as conn:
        row = conn.execute(
            "SELECT stage, warmth_score FROM contacts WHERE id = ?", (contact_id,)
        ).fetchone()
        if not row:
            return
        new_warmth = max(1, min(10, int(row["warmth_score"]) + int(warmth_delta)))
        valid_stages = {"casual", "flirty", "romantic", "propose"}
        new_stage = stage if stage in valid_stages else row["stage"]
        conn.execute(
            "UPDATE contacts SET stage = ?, warmth_score = ? WHERE id = ?",
            (new_stage, new_warmth, contact_id),
        )


def save_profile_intel(contact_id: int, **kwargs: str) -> None:
    allowed = {
        "bio_summary",
        "fav_songs",
        "hobbies",
        "likes",
        "dislikes",
        "vibe_notes",
        "role_company",
        "skills",
        "recent_activity",
        "conversation_goal",
    }
    now = datetime.now().isoformat(timespec="seconds")
    with _DB_LOCK, get_conn() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO profile_intel (contact_id) VALUES (?)", (contact_id,)
        )
        updates = ["last_scanned = ?"]
        params: List[Any] = [now]
        for k, v in kwargs.items():
            if k in allowed and v is not None:
                val = str(v).strip()
                if val != "":
                    updates.append(f"{k} = ?")
                    params.append(val)
        params.append(contact_id)
        conn.execute(
            f"UPDATE profile_intel SET {', '.join(updates)} WHERE contact_id = ?",
            params,
        )


def overwrite_profile_intel(contact_id: int, data: Dict[str, Any]) -> None:
    allowed = {
        "bio_summary",
        "fav_songs",
        "hobbies",
        "likes",
        "dislikes",
        "vibe_notes",
        "role_company",
        "skills",
        "recent_activity",
        "conversation_goal",
    }
    with _DB_LOCK, get_conn() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO profile_intel (contact_id) VALUES (?)", (contact_id,)
        )
        updates = []
        params: List[Any] = []
        for k in allowed:
            if k in data:
                updates.append(f"{k} = ?")
                params.append(str(data[k]).strip())
        if updates:
            params.append(contact_id)
            conn.execute(
                f"UPDATE profile_intel SET {', '.join(updates)} WHERE contact_id = ?",
                params,
            )


def add_message(contact_id: int, sender: str, content: str, mood: str = "") -> int:
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with _DB_LOCK, get_conn() as conn:
        cur = conn.execute(
            """
            INSERT INTO chat_history (contact_id, sender, content, mood, timestamp)
            VALUES (?, ?, ?, ?, ?)
            """,
            (contact_id, sender, content.strip(), mood, now),
        )
        return int(cur.lastrowid)


def get_recent_messages(contact_id: int, limit: int = 30) -> List[Dict[str, Any]]:
    with _DB_LOCK, get_conn() as conn:
        rows = conn.execute(
            """
            SELECT id, sender, content, mood, timestamp
            FROM chat_history
            WHERE contact_id = ?
            ORDER BY id DESC LIMIT ?
            """,
            (contact_id, limit),
        ).fetchall()
    return [dict(r) for r in reversed(rows)]


def get_last_message(contact_id: int) -> Optional[Dict[str, Any]]:
    msgs = get_recent_messages(contact_id, limit=1)
    return msgs[0] if msgs else None


def add_memory_fact(contact_id: int, category: str, fact: str) -> None:
    fact = fact.strip()
    if not fact:
        return
    with _DB_LOCK, get_conn() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO memory_facts (contact_id, category, fact) VALUES (?, ?, ?)",
            (contact_id, category.strip().lower(), fact),
        )


def delete_memory_fact(fact_id: int) -> None:
    with _DB_LOCK, get_conn() as conn:
        conn.execute("DELETE FROM memory_facts WHERE id = ?", (fact_id,))


def get_full_context(contact_id: int) -> Optional[Dict[str, Any]]:
    with _DB_LOCK, get_conn() as conn:
        c_row = conn.execute(
            "SELECT * FROM contacts WHERE id = ?", (contact_id,)
        ).fetchone()
        if not c_row:
            return None
        intel_row = conn.execute(
            "SELECT * FROM profile_intel WHERE contact_id = ?", (contact_id,)
        ).fetchone()
        facts = [
            dict(r)
            for r in conn.execute(
                """
                SELECT id, category, fact, created_at
                FROM memory_facts
                WHERE contact_id = ?
                ORDER BY id DESC LIMIT 40
                """,
                (contact_id,),
            ).fetchall()
        ]
    return {
        "contact": dict(c_row),
        "profile_intel": dict(intel_row) if intel_row else {},
        "memory_facts": facts,
        "recent_messages": get_recent_messages(contact_id, limit=25),
    }


def export_all_data() -> Dict[str, Any]:
    contacts = list_contacts()
    full = []
    for c in contacts:
        ctx = get_full_context(c["id"])
        if ctx:
            full.append(ctx)
    return {"exported_at": datetime.now().isoformat(), "contacts": full}
