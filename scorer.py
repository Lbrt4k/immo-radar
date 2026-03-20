"""ImmoRadar - Scoring IA via Claude API"""
import json, logging, random
from config import ANTHROPIC_API_KEY, SCORING_CONFIG, SCORING_WEIGHTS
from database import update_listing_score

logger = logging.getLogger("immo_radar.scorer")


def _build_prompt(listing):
    """Construit le prompt de scoring pour Claude."""
    context = f"""Tu es un expert en investissement immobilier en France.
Analyse cette annonce et attribue un score de 0 à 100 (100 = meilleure affaire).

ANNONCE:
- Titre: {listing.get('title', 'N/A')}
- Prix: {listing.get('price', 'N/A')}€
- Surface: {listing.get('surface', 'N/A')} m²
- Pièces: {listing.get('rooms', 'N/A')}
- Type: {listing.get('property_type', 'N/A')}
- Ville: {listing.get('city', 'N/A')} ({listing.get('postal_code', '')})
- DPE: {listing.get('dpe_letter', 'N/A')}
- GES: {listing.get('ges_letter', 'N/A')}

DONNÉES MARCHÉ:
- Prix médian DVF: {listing.get('dvf_median_price', 'N/A')} €/m²
- Écart prix/marché: {listing.get('dvf_price_gap', 'N/A')}%
- Potentiel rénovation DPE: {listing.get('dpe_renovation_potential', 'N/A')}

CRITÈRES D'INVESTISSEMENT (profil investisseur):
1. Impôts: Estime l'impact fiscal probable (revenus fonciers, plus-value)
2. Frais syndic: Estime les frais annuels de copropriété
3. Type de chauffage: Identifie le type et évalue l'efficacité énergétique
4. Frais des charges: Estime les charges communes annuelles
5. Taux de crédits: Recommande un taux de financement approprié
6. Frais de Notaire: Estime les frais d'acquisition (~7-8%)
7. Opération Blanche: Évalue si loyer net ≥ paiements crédits (rentabilité)

CRITÈRES DE PONDÉRATION:
- Écart prix vs marché: {SCORING_WEIGHTS['price_gap']*100}%
- Rendement locatif: {SCORING_WEIGHTS['rental_yield']*100}%
- Potentiel DPE: {SCORING_WEIGHTS['dpe_potential']*100}%
- Localisation: {SCORING_WEIGHTS['location']*100}%
- Rapport surface/prix: {SCORING_WEIGHTS['surface_value']*100}%

Réponds UNIQUEMENT en JSON valide avec ce format:
{{
  "score": <0-100>,
  "reasons": ["raison 1", "raison 2", "raison 3"],
  "details": {{
    "price_gap_score": <0-100>,
    "rental_yield_score": <0-100>,
    "dpe_score": <0-100>,
    "location_score": <0-100>,
    "surface_value_score": <0-100>
  }},
  "investor_analysis": {{
    "estimated_taxes_annual": "<estimé>",
    "estimated_syndic_fees_annual": "<estimé>",
    "heating_type": "<type>",
    "estimated_charges_annual": "<estimé>",
    "recommended_credit_rate": "<taux %>",
    "estimated_notary_fees": "<estimé>",
    "blank_operation_feasible": <true|false>
  }},
  "estimated_value": <valeur estimée en euros>,
  "rental_yield": <rendement locatif estimé en %>,
  "recommendation": "<acheter|surveiller|passer>"
}}"""
    return context


def score_with_claude(listing):
    """Score une annonce via l'API Claude."""
    if not ANTHROPIC_API_KEY:
        logger.warning("Pas de clé API Anthropic — scoring simulé")
        return _simulated_score(listing)

    try:
        import anthropic
        client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

        prompt = _build_prompt(listing)
        response = client.messages.create(
            model=SCORING_CONFIG["model"],
            max_tokens=SCORING_CONFIG["max_tokens"],
            messages=[{"role": "user", "content": prompt}],
        )

        text = response.content[0].text.strip()
        # Extraire le JSON de la réponse
        if "```json" in text:
            text = text.split("```json")[1].split("```")[0].strip()
        elif "```" in text:
            text = text.split("```")[1].split("```")[0].strip()

        result = json.loads(text)
        logger.info(f"Score IA: {result['score']}/100 — {result.get('recommendation', 'N/A')}")
        return result

    except Exception as e:
        logger.error(f"Erreur scoring Claude: {e}")
        return _simulated_score(listing)


def _simulated_score(listing):
    """Score simulé quand l'API n'est pas dispo."""
    base = 50
    price = listing.get("price", 0)
    surface = listing.get("surface", 0)

    if price and surface and surface > 0:
        price_m2 = price / surface
        if price_m2 < 2000: base += 15
        elif price_m2 < 3000: base += 8
        elif price_m2 > 5000: base -= 10

    gap = listing.get("dvf_price_gap")
    if gap and gap > 10: base += 12
    elif gap and gap > 5: base += 6

    dpe = listing.get("dpe_letter")
    if dpe in ("F", "G"): base += 8
    elif dpe in ("A", "B"): base += 5

    score = max(0, min(100, base + random.randint(-5, 5)))
    reasons = []
    if gap and gap > 5: reasons.append(f"Prix {gap:.0f}% sous le marché")
    if surface and surface > 50: reasons.append(f"Belle surface de {surface}m²")
    if dpe in ("F", "G"): reasons.append("Fort potentiel rénovation énergétique")
    if not reasons: reasons.append("Annonce à analyser en détail")

    return {
        "score": score,
        "reasons": reasons,
        "recommendation": "acheter" if score >= 70 else "surveiller" if score >= 50 else "passer",
        "estimated_value": price,
        "rental_yield": round(random.uniform(3, 8), 1) if price else None,
    }


def score_listings(listings):
    """Score une liste d'annonces."""
    scored = 0
    for listing in listings:
        result = score_with_claude(listing)
        if result:
            update_listing_score(listing["id"], result)
            scored += 1
    logger.info(f"Scoring terminé: {scored}/{len(listings)}")
    return scored
