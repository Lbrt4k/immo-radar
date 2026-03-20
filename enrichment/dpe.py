"""ImmoRadar - Enrichissement DPE (Diagnostic de Performance Énergétique)"""
import logging, requests

logger = logging.getLogger("immo_radar.dpe")

ADEME_API = "https://data.ademe.fr/data-fair/api/v1/datasets/dpe-v2-logements-existants/lines"

# Potentiel de plus-value après rénovation énergétique
DPE_RENOVATION_POTENTIAL = {
    "A": 0.0,
    "B": 0.0,
    "C": 0.02,
    "D": 0.05,
    "E": 0.10,
    "F": 0.18,
    "G": 0.25,
}


def get_dpe_data(address, postal_code):
    """Cherche le DPE d'un bien via l'API ADEME."""
    if not address or not postal_code:
        return None
    try:
        params = {
            "q": address,
            "q_fields": "adresse_bien",
            "qs": f"code_postal_bien:{postal_code}",
            "size": 5,
            "sort": "-date_etablissement_dpe",
            "select": "classe_consommation_energie,classe_estimation_ges,consommation_energie,estimation_ges,date_etablissement_dpe"
        }
        resp = requests.get(ADEME_API, params=params, timeout=10)
        resp.raise_for_status()
        results = resp.json().get("results", [])
        if results:
            r = results[0]
            return {
                "dpe_letter": r.get("classe_consommation_energie"),
                "ges_letter": r.get("classe_estimation_ges"),
                "energy_consumption": r.get("consommation_energie"),
                "ges_value": r.get("estimation_ges"),
                "date": r.get("date_etablissement_dpe"),
            }
    except Exception as e:
        logger.error(f"ADEME DPE erreur: {e}")
    return None


def compute_renovation_potential(dpe_letter):
    """Estime le potentiel de plus-value après rénovation énergétique."""
    if not dpe_letter:
        return 0.0
    return DPE_RENOVATION_POTENTIAL.get(dpe_letter.upper(), 0.0)


def enrich_with_dpe(listing):
    """Enrichit une annonce avec les données DPE."""
    enrichment = {}

    # Si pas de DPE dans l'annonce, chercher via ADEME
    if not listing.get("dpe_letter"):
        dpe_data = get_dpe_data(listing.get("address"), listing.get("postal_code"))
        if dpe_data:
            enrichment["dpe_letter"] = dpe_data.get("dpe_letter")
            enrichment["ges_letter"] = dpe_data.get("ges_letter")

    dpe = enrichment.get("dpe_letter") or listing.get("dpe_letter")
    if dpe:
        potential = compute_renovation_potential(dpe)
        if potential > 0:
            enrichment["dpe_renovation_potential"] = potential
            logger.debug(f"DPE {dpe}: potentiel rénovation = +{potential*100:.0f}%")

    return enrichment
