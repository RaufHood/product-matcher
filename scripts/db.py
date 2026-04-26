import sqlite3
from pathlib import Path


def execute_schema(conn: sqlite3.Connection, schema_path: Path) -> None:
    conn.executescript(schema_path.read_text(encoding="utf-8"))
    conn.commit()


def upsert_market(conn: sqlite3.Connection, market_code: str, market_name: str) -> int:
    conn.execute(
        """
        INSERT INTO markets (market_code, market_name)
        VALUES (?, ?)
        ON CONFLICT(market_code) DO UPDATE SET market_name = excluded.market_name
        """,
        (market_code, market_name),
    )
    row = conn.execute("SELECT id FROM markets WHERE market_code = ?", (market_code,)).fetchone()
    return int(row[0])


def upsert_name_entity(
    conn: sqlite3.Connection, table_name: str, column_name: str, value: str
) -> int:
    conn.execute(
        f"INSERT INTO {table_name} ({column_name}) VALUES (?) ON CONFLICT({column_name}) DO NOTHING",
        (value,),
    )
    row = conn.execute(
        f"SELECT id FROM {table_name} WHERE {column_name} = ?", (value,)
    ).fetchone()
    return int(row[0])
