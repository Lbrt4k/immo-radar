"""ImmoRadar - Enrichissement DVF (Demandes de Valeurs Foncières)"""
import json, logging, requests, sqlite3
from datetime import datetime, timedelta
from config import DB_PATH

logger = logging.getLogger("immo_radar.dvf")

DVF_API = "https://api.cquest.org/dvf"
CACHE_TTL_DAYS = 7


def _get_cached(cache_key):
    try:
        conn = sqlite3.connect(str(DB_PATH))
        row = conn.execute("SELECT data, created_at FROM dvf_cache WHERE cache_key=?", (cache_key,)).fetchone()
        conn.close()
        if row:
            created = datetime.fromisoformat(row[1])
            if datetime.now() - created < timedelta(days=CACHE_TTL_DAYS):
                return json.loads(row[0])
    except:
        pass
    return None


def _set_cache(cache_key, data):
    try:
        conn = sqlite3.connect(str(DB_PATH))
        conn.execute(
            "INSERT OR REPLACE INTO dvf_cache (cache_key, data, created_at) VALUES (?,?,?)",
            (cache_key, json.dumps(data), datetime.now().isoformat())
        )
        conn.commit()
        conn.close()
    except:
        pass


def get_dvf_prices(lat, lon, radius_m=1000):
    """Récupère les prix DVF autour d'un point GPS."""
    cache_key = f"dvf:{lat:.3f}:{lon:.3f}:{radius_m}"
    cached = _get_cached(cache_key)
    if cached is not None:
        return cached

    try:
        params = {"lat": lat, "lon": lon, "dist": radius_m}
        resp = requests.get(DVF_API, params=params, timeout=10)
        resp.raise_for_status()
        data = resp.json()

        results = []
        for r in data.get("resultats", []):
            price = r.get("valeur_fonciere")
            surface = r.get("surface_reelle_bati")
            if price and surface and surface > 0:
                results.append({
                    "price": float(price),
                    "surface": float(surface),
                    "price_m2": float(price) / float(surface),
                    "date": r.get("date_mutation"),
                    "type": r.get("type_local"),
                })

        _set_cache(cache_key, results)
        logger.debug(f"DVF: {len(results)} ventes trouvées autour de ({lat}, {lon})")
        return results
    except Exception as e:
        logger.error(f"DVF erreur: {e}")
        return []


def compute_median_price_m2(dvf_results):
    """Calcule le prix médian au m² depuis les résultats DVF."""
    prices = [r["price_m2"] for r in dvf_results if r.get("price_m2")]
    if not prices:
        return None
    prices.sort()
    n = len(prices)
    if n % 2 == 0:
        return (prices[n // 2 - 1] + prices[n // 2]) / 2
    return prices[n // 2]


def enrich_with_dvf(listing):
    """Enrichit une annonce avec les données DVF."""
    lat = listing.get("latitude")
    lon = listing.get("longitude")
    if not lat or not lon:
        return {}

    dvf_results = get_dvf_prices(lat, lon)
    if not dvf_results:
        return {}

    median = compute_median_price_m2(dvf_results)
    if not median:
        return {}

    enrichment = {"dvf_median_price": round(median, 2)}

    surface = listing.get("surface")
    price = listing.get("price")
    if surface and price and surface > 0:
        listing_price_m2 = price / surface
        gap = ((median - listing_price_m2) / median) * 100
        enrichment["dvf_price_gap"] = round(gap, 1)

    logger.debug(f"DVF enrichment: median={median:.0f}€/m², gap={enrichment.get('dvf_price_gap', 'N/A')}%")
    return enrichment
