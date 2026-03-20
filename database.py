"""ImmoRadar - Base de données SQLite"""
import sqlite3, hashlib, json, logging
from datetime import datetime
from config import DB_PATH

logger = logging.getLogger("immo_radar.db")


def _connect():
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def init_db():
    conn = _connect()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS listings (
            id TEXT PRIMARY KEY,
            source TEXT,
            url TEXT,
            title TEXT,
            description TEXT,
            price INTEGER,
            surface REAL,
            rooms INTEGER,
            property_type TEXT,
            city TEXT,
            postal_code TEXT,
            address TEXT,
            latitude REAL,
            longitude REAL,
            images TEXT,
            dpe_letter TEXT,
            ges_letter TEXT,
            dvf_median_price REAL,
            dvf_price_gap REAL,
            estimated_rent REAL,
            rental_yield REAL,
            dpe_renovation_potential REAL,
            ai_score REAL,
            ai_reasons TEXT,
            ai_recommendation TEXT,
            ai_estimated_value REAL,
            ai_rental_yield REAL,
            ai_investor_analysis TEXT,
            alert_sent INTEGER DEFAULT 0,
            raw_data TEXT,
            created_at TEXT DEFAULT (datetime('now')),
            updated_at TEXT DEFAULT (datetime('now'))
        );
        CREATE TABLE IF NOT EXISTS dvf_cache (
            cache_key TEXT PRIMARY KEY,
            data TEXT,
            created_at TEXT DEFAULT (datetime('now'))
        );
        CREATE INDEX IF NOT EXISTS idx_listings_score ON listings(ai_score);
        CREATE INDEX IF NOT EXISTS idx_listings_city ON listings(city);
        CREATE INDEX IF NOT EXISTS idx_listings_source ON listings(source);
    """)
    # Ajouter colonne si elle n'existe pas (migration)
    try:
        conn.execute("ALTER TABLE listings ADD COLUMN ai_investor_analysis TEXT")
        conn.commit()
    except sqlite3.OperationalError:
        pass  # Colonne existe déjà
    conn.close()
    logger.info(f"Base de données initialisée: {DB_PATH}")


def generate_listing_id(source, url, title, price):
    raw = f"{source}:{url}:{title}:{price}"
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


def insert_listing(listing):
    conn = _connect()
    try:
        conn.execute("""
            INSERT OR IGNORE INTO listings
            (id, source, url, title, description, price, surface, rooms,
             property_type, city, postal_code, address, latitude, longitude,
             images, dpe_letter, ges_letter, raw_data)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """, (
            listing.get("id"),
            listing.get("source"),
            listing.get("url"),
            listing.get("title"),
            listing.get("description"),
            listing.get("price"),
            listing.get("surface"),
            listing.get("rooms"),
            listing.get("property_type"),
            listing.get("city"),
            listing.get("postal_code"),
            listing.get("address"),
            listing.get("latitude"),
            listing.get("longitude"),
            json.dumps(listing.get("images", [])),
            listing.get("dpe_letter"),
            listing.get("ges_letter"),
            json.dumps(listing.get("raw_data", {})),
        ))
        inserted = conn.total_changes > 0
        conn.commit()
        return inserted
    except sqlite3.Error as e:
        logger.error(f"Erreur insert: {e}")
        return False
    finally:
        conn.close()


def update_listing_enrichment(listing_id, data):
    conn = _connect()
    try:
        fields = ", ".join(f"{k}=?" for k in data.keys())
        values = list(data.values()) + [listing_id]
        conn.execute(f"UPDATE listings SET {fields}, updated_at=datetime('now') WHERE id=?", values)
        conn.commit()
    except sqlite3.Error as e:
        logger.error(f"Erreur update enrichment: {e}")
    finally:
        conn.close()


def update_listing_score(listing_id, score_data):
    conn = _connect()
    try:
        conn.execute("""
            UPDATE listings SET
                ai_score=?, ai_reasons=?, ai_recommendation=?,
                ai_estimated_value=?, ai_rental_yield=?,
                ai_investor_analysis=?,
                updated_at=datetime('now')
            WHERE id=?
        """, (
            score_data.get("score"),
            json.dumps(score_data.get("reasons", []), ensure_ascii=False),
            score_data.get("recommendation"),
            score_data.get("estimated_value"),
            score_data.get("rental_yield"),
            json.dumps(score_data.get("investor_analysis", {}), ensure_ascii=False),
            listing_id,
        ))
        conn.commit()
    except sqlite3.Error as e:
        logger.error(f"Erreur update score: {e}")
    finally:
        conn.close()


def get_unscored_listings():
    conn = _connect()
    rows = conn.execute("SELECT * FROM listings WHERE ai_score IS NULL").fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_unsent_alerts(min_score=65):
    conn = _connect()
    rows = conn.execute(
        "SELECT * FROM listings WHERE ai_score >= ? AND alert_sent = 0 ORDER BY ai_score DESC",
        (min_score,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def mark_alert_sent(listing_id):
    conn = _connect()
    conn.execute("UPDATE listings SET alert_sent=1 WHERE id=?", (listing_id,))
    conn.commit()
    conn.close()


def get_all_listings():
    conn = _connect()
    rows = conn.execute("SELECT * FROM listings ORDER BY ai_score DESC NULLS LAST").fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_stats():
    conn = _connect()
    stats = {}
    stats["total"] = conn.execute("SELECT COUNT(*) FROM listings").fetchone()[0]
    stats["scored"] = conn.execute("SELECT COUNT(*) FROM listings WHERE ai_score IS NOT NULL").fetchone()[0]
    stats["avg_score"] = conn.execute("SELECT AVG(ai_score) FROM listings WHERE ai_score IS NOT NULL").fetchone()[0] or 0
    stats["top_deals"] = conn.execute("SELECT COUNT(*) FROM listings WHERE ai_score >= 70").fetchone()[0]
    stats["by_source"] = {}
    for row in conn.execute("SELECT source, COUNT(*) as cnt FROM listings GROUP BY source"):
        stats["by_source"][row[0]] = row[1]
    stats["by_city"] = {}
    for row in conn.execute("SELECT city, COUNT(*) as cnt FROM listings GROUP BY city ORDER BY cnt DESC"):
        stats["by_city"][row[0]] = row[1]
    conn.close()
    return stats


def export_to_json(filepath):
    listings = get_all_listings()
    stats = get_stats()
    data = {"stats": stats, "listings": listings, "exported_at": datetime.now().isoformat()}
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2, default=str)
    logger.info(f"Export: {len(listings)} annonces -> {filepath}")
    return len(listings)


# Auto-init
init_db()
