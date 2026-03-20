"""ImmoRadar - Configuration centrale"""
import os
from pathlib import Path

# === Répertoires ===
BASE_DIR = Path(__file__).parent
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)
DB_PATH = DATA_DIR / "immo_radar.db"

# === Clés API (variables d'environnement) ===
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")

# === Critères de recherche ===
SEARCH_CONFIG = {
    "cities": [
        {"name": "Lyon", "code": "69123", "dept": "69", "postal_code": "69000", "lat": 45.764, "lon": 4.8357},
        {"name": "Marseille", "code": "13055", "dept": "13", "postal_code": "13000", "lat": 43.2965, "lon": 5.3698},
    ],
    "property_types": ["appartement", "maison"],
    "price_min": 50000,
    "price_max": 300000,
    "surface_min": 20,
    "rooms_min": 1,
    "radius_km": 15,
}

# === Pondération du scoring ===
SCORING_WEIGHTS = {
    "price_gap": 0.30,
    "rental_yield": 0.25,
    "dpe_potential": 0.15,
    "location": 0.15,
    "surface_value": 0.15,
}

# === Config scraping ===
SCRAPING_CONFIG = {
    "headers": {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
        "Accept-Language": "fr-FR,fr;q=0.9,en;q=0.5",
        "Accept-Encoding": "gzip, deflate, br",
        "Connection": "keep-alive",
        "Upgrade-Insecure-Requests": "1",
    },
    "request_delay": 1.5,
    "max_listings_per_source": 50,
}

# === Config scoring IA ===
SCORING_CONFIG = {
    "model": "claude-haiku-4-5-20251001",
    "max_tokens": 512,
    "min_score_alert": 65,
}
