"""ImmoRadar - Alertes Telegram"""
import json, logging, requests
from config import TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, SCORING_CONFIG
from database import mark_alert_sent, get_stats

logger = logging.getLogger("immo_radar.alerts")


def _format_message(listing):
    """Formate un message Telegram pour une annonce."""
    score = listing.get("ai_score", 0)
    if score >= 80: emoji = "🔥"
    elif score >= 70: emoji = "⭐"
    else: emoji = "📌"

    reasons = json.loads(listing.get("ai_reasons", "[]")) if isinstance(listing.get("ai_reasons"), str) else listing.get("ai_reasons", [])

    msg = f"""{emoji} *Score {score:.0f}/100* — {listing.get('ai_recommendation', '').upper()}

*{listing.get('title', 'Annonce')}*
💰 {listing.get('price', '?'):,}€
📐 {listing.get('surface', '?')} m² | 🏠 {listing.get('rooms', '?')} pièces
📍 {listing.get('city', '?')} ({listing.get('postal_code', '')})
🏷️ Source: {listing.get('source', '?')}"""

    if listing.get("dvf_price_gap"):
        gap = listing["dvf_price_gap"]
        msg += f"\n📊 {'↓' if gap > 0 else '↑'} {abs(gap):.1f}% vs marché"

    if listing.get("dpe_letter"):
        msg += f"\n🌡️ DPE: {listing['dpe_letter']}"
        if listing.get("dpe_renovation_potential"):
            msg += f" (potentiel +{listing['dpe_renovation_potential']*100:.0f}%)"

    if listing.get("ai_rental_yield"):
        msg += f"\n💵 Rendement estimé: {listing['ai_rental_yield']:.1f}%"

    if reasons:
        msg += "\n\n🤖 *Analyse IA:*"
        for r in reasons[:3]:
            msg += f"\n  • {r}"

    if listing.get("url"):
        msg += f"\n\n🔗 [Voir l'annonce]({listing['url']})"

    return msg


def send_telegram(text):
    """Envoie un message via Telegram Bot API."""
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        logger.info(f"[CONSOLE ALERT]\n{text}\n{'='*50}")
        return True

    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
        resp = requests.post(url, json={
            "chat_id": TELEGRAM_CHAT_ID,
            "text": text,
            "parse_mode": "Markdown",
            "disable_web_page_preview": False,
        }, timeout=10)
        resp.raise_for_status()
        logger.debug("Telegram: message envoyé")
        return True
    except Exception as e:
        logger.error(f"Telegram erreur: {e}")
        return False


def send_alerts(listings):
    """Envoie les alertes pour les nouvelles annonces scorées."""
    sent = 0
    for listing in listings:
        msg = _format_message(listing)
        if send_telegram(msg):
            mark_alert_sent(listing["id"])
            sent += 1
    logger.info(f"Alertes envoyées: {sent}/{len(listings)}")
    return sent


def send_daily_recap():
    """Envoie un récap quotidien."""
    stats = get_stats()
    msg = f"""📊 *ImmoRadar — Récap du jour*

📦 Total annonces: {stats['total']}
🎯 Scorées: {stats['scored']}
⭐ Top deals (≥70): {stats['top_deals']}
📈 Score moyen: {stats['avg_score']:.1f}

🏙️ *Par ville:*"""
    for city, count in stats.get("by_city", {}).items():
        msg += f"\n  • {city}: {count}"

    msg += "\n\n🔍 *Par source:*"
    for source, count in stats.get("by_source", {}).items():
        msg += f"\n  • {source}: {count}"

    send_telegram(msg)
