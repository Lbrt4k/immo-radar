"""ImmoRadar - Point d'entrée principal"""
import argparse, logging, sys, time
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("immo_radar")

from config import DATA_DIR, SCORING_CONFIG
from database import get_unscored_listings, get_unsent_alerts, get_stats, export_to_json
from scrapers import PapScraper, BieniciScraper, LeBonCoinScraper
from enrichment import enrich_with_dvf, enrich_with_dpe
from database import update_listing_enrichment
from scorer import score_listings
from alerts import send_alerts, send_daily_recap


def _scrape_source(name, scraper):
    """Scrape une source (utilisé en parallèle)."""
    try:
        logger.info(f"--- {name} ---")
        new = scraper.scrape()
        logger.info(f"{name}: {len(new)} nouvelles annonces")
        return new
    except Exception as e:
        logger.error(f"{name} erreur: {e}")
        return []


def run_scrape():
    """Lance le scraping sur toutes les sources en parallèle."""
    logger.info("=" * 50)
    logger.info("SCRAPING — Recherche de nouvelles annonces...")

    all_new = []
    scrapers = [
        ("LeBonCoin", LeBonCoinScraper()),
        ("PAP.fr", PapScraper()),
    ]

    # Lancer les scrapers en parallèle
    with ThreadPoolExecutor(max_workers=len(scrapers)) as executor:
        futures = {executor.submit(_scrape_source, name, s): name for name, s in scrapers}
        for future in as_completed(futures):
            result = future.result()
            if result:
                all_new.extend(result)

    logger.info(f"Total nouvelles annonces: {len(all_new)}")
    return all_new


def run_enrich():
    """Enrichit les annonces avec DVF + DPE."""
    logger.info("=" * 50)
    logger.info("ENRICHISSEMENT — DVF + DPE...")

    listings = get_unscored_listings()
    enriched = 0
    for listing in listings:
        data = {}
        try:
            dvf = enrich_with_dvf(listing)
            if dvf: data.update(dvf)
        except Exception as e:
            logger.error(f"DVF erreur: {e}")

        try:
            dpe = enrich_with_dpe(listing)
            if dpe: data.update(dpe)
        except Exception as e:
            logger.error(f"DPE erreur: {e}")

        if data:
            update_listing_enrichment(listing["id"], data)
            enriched += 1

        time.sleep(0.2)

    logger.info(f"Enrichissement: {enriched}/{len(listings)}")
    return enriched


def run_score():
    """Score les annonces non-scorées via IA."""
    logger.info("=" * 50)
    logger.info("SCORING IA...")

    listings = get_unscored_listings()
    if not listings:
        logger.info("Aucune annonce à scorer")
        return 0

    scored = score_listings(listings)
    logger.info(f"Scoring: {scored} annonces scorées")
    return scored


def run_alert():
    """Envoie les alertes pour les bons deals."""
    logger.info("=" * 50)
    logger.info("ALERTES...")

    min_score = SCORING_CONFIG.get("min_score_alert", 65)
    listings = get_unsent_alerts(min_score)
    if not listings:
        logger.info("Aucune nouvelle alerte")
        return 0

    sent = send_alerts(listings)
    logger.info(f"Alertes: {sent} envoyées")
    return sent


def run_export():
    """Exporte les données pour le dashboard."""
    export_path = DATA_DIR / "export.json"
    count = export_to_json(str(export_path))
    logger.info(f"Export: {count} annonces -> {export_path}")
    return count


def run_pipeline():
    """Pipeline complet: scrape -> enrich -> score -> alert -> export."""
    logger.info("🚀 ImmoRadar — Pipeline complet")
    logger.info("=" * 50)

    new = run_scrape()
    if new:
        run_enrich()
        run_score()
        run_alert()
    run_export()

    stats = get_stats()
    logger.info("=" * 50)
    logger.info(f"📊 STATS: {stats['total']} annonces | {stats['scored']} scorées | {stats['top_deals']} top deals | Score moyen: {stats['avg_score']:.1f}")
    logger.info("=" * 50)


def run_loop():
    """Boucle automatique avec schedule."""
    try:
        import schedule
    except ImportError:
        logger.error("Module 'schedule' non installé. Lancez: pip install schedule")
        return

    logger.info("🔄 Mode boucle — Ctrl+C pour arrêter")

    schedule.every(4).hours.do(run_pipeline)
    schedule.every().day.at("20:00").do(send_daily_recap)

    # Lancer immédiatement
    run_pipeline()

    while True:
        schedule.run_pending()
        time.sleep(60)


def main():
    parser = argparse.ArgumentParser(description="ImmoRadar — Détecteur de bonnes affaires immobilières")
    parser.add_argument("--scrape", action="store_true", help="Lancer le scraping")
    parser.add_argument("--enrich", action="store_true", help="Enrichir les annonces (DVF/DPE)")
    parser.add_argument("--score", action="store_true", help="Scorer les annonces via IA")
    parser.add_argument("--alert", action="store_true", help="Envoyer les alertes")
    parser.add_argument("--dashboard", action="store_true", help="Exporter pour le dashboard")
    parser.add_argument("--loop", action="store_true", help="Mode boucle automatique")
    parser.add_argument("--recap", action="store_true", help="Envoyer le récap quotidien")
    parser.add_argument("-v", "--verbose", action="store_true", help="Mode verbose")

    args = parser.parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    # Si aucun argument, lancer le pipeline complet
    if not any([args.scrape, args.enrich, args.score, args.alert, args.dashboard, args.loop, args.recap]):
        run_pipeline()
        return

    if args.loop:
        run_loop()
        return

    if args.scrape: run_scrape()
    if args.enrich: run_enrich()
    if args.score: run_score()
    if args.alert: run_alert()
    if args.dashboard: run_export()
    if args.recap: send_daily_recap()


if __name__ == "__main__":
    main()
