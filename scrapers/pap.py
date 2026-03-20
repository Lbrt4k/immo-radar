"""ImmoRadar - Scraper PAP.fr (corrigé)"""
import time, re, json, logging, requests
from config import SEARCH_CONFIG, SCRAPING_CONFIG
from database import insert_listing, generate_listing_id

logger = logging.getLogger("immo_radar.pap")


class PapScraper:
    BASE_URL = "https://www.pap.fr"

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update(SCRAPING_CONFIG["headers"])
        self.delay = SCRAPING_CONFIG["request_delay"]
        self.max_listings = SCRAPING_CONFIG["max_listings_per_source"]

    def _build_search_url(self, city, page=1):
        """URL de recherche PAP - format correct."""
        name = city["name"].lower().replace(" ", "-").replace("'", "-")
        # PAP utilise le département, pas le code INSEE
        dept = city.get("dept", city.get("postal_code", "")[:2])

        url = f"{self.BASE_URL}/annonce/vente-immobiliere-{name}-{dept}"

        params = []
        if SEARCH_CONFIG.get("price_min"): params.append(f"prix-min={SEARCH_CONFIG['price_min']}")
        if SEARCH_CONFIG.get("price_max"): params.append(f"prix-max={SEARCH_CONFIG['price_max']}")
        if SEARCH_CONFIG.get("surface_min"): params.append(f"surface-min={SEARCH_CONFIG['surface_min']}")
        if SEARCH_CONFIG.get("rooms_min"): params.append(f"nb-pieces-min={SEARCH_CONFIG['rooms_min']}")
        if page > 1: params.append(f"page={page}")
        if params: url += "?" + "&".join(params)
        return url

    def _parse_html(self, html):
        """Parse le HTML de PAP pour extraire les annonces."""
        listings = []

        # Méthode 1 : JSON-LD (le plus fiable)
        for m in re.finditer(r'<script[^>]*type="application/ld\+json"[^>]*>(.*?)</script>', html, re.DOTALL):
            try:
                data = json.loads(m.group(1).strip())
                items = data if isinstance(data, list) else [data]
                for item in items:
                    if item.get("@type") in ("Product","Residence","RealEstateListing","Offer","ApartmentComplex"):
                        l = self._from_jsonld(item)
                        if l: listings.append(l)
            except: pass

        # Méthode 2 : Chercher les données dans les attributs data-* ou scripts JS
        for m in re.finditer(r'window\.__DATA__\s*=\s*(\{.*?\});', html, re.DOTALL):
            try:
                data = json.loads(m.group(1))
                for ad in data.get("ads", data.get("listings", data.get("results", []))):
                    l = self._from_dict(ad)
                    if l: listings.append(l)
            except: pass

        # Méthode 3 : Parse HTML brut - chercher les blocs d'annonces
        if not listings:
            # Chercher les liens d'annonces avec prix
            blocks = re.findall(
                r'<a[^>]*href="(/annonces/[^"]+)"[^>]*>.*?(\d[\d\s]+)\s*€.*?(\d+)\s*m²',
                html, re.DOTALL
            )
            for link, price, surface in blocks:
                try:
                    listings.append({
                        "source": "pap", "url": f"{self.BASE_URL}{link}",
                        "title": "", "price": int(price.replace(" ","")),
                        "surface": float(surface),
                    })
                except: pass

            # Alternative : chercher les containers d'annonces
            if not listings:
                # Pattern pour les résultats de recherche PAP
                ad_blocks = re.findall(
                    r'<div[^>]*class="[^"]*search-list-item[^"]*"[^>]*>(.*?)</div>\s*</div>\s*</div>',
                    html, re.DOTALL
                )
                for block in ad_blocks:
                    l = self._parse_block(block)
                    if l: listings.append(l)

        logger.debug(f"PAP parse: {len(listings)} annonces trouvées")
        return listings

    def _from_jsonld(self, data):
        try:
            url = data.get("url", "")
            if url and not url.startswith("http"): url = f"{self.BASE_URL}{url}"
            offers = data.get("offers", {})
            price = offers.get("price") if isinstance(offers, dict) else None
            if not price: return None
            return {"source":"pap","url":url,"title":data.get("name",""),
                    "description":data.get("description",""),"price":int(float(price)),
                    "raw_data":data}
        except: return None

    def _from_dict(self, ad):
        try:
            price = ad.get("price") or ad.get("prix")
            if not price: return None
            url = ad.get("url") or ad.get("link") or ""
            if url and not url.startswith("http"): url = f"{self.BASE_URL}{url}"
            return {
                "source":"pap","url":url,"title":ad.get("title",ad.get("titre","")),
                "description":ad.get("description",""),"price":int(price),
                "surface":ad.get("surface") or ad.get("living_area"),
                "rooms":ad.get("rooms") or ad.get("nb_rooms") or ad.get("nb_pieces"),
                "city":ad.get("city") or ad.get("ville"),
                "postal_code":ad.get("zipcode") or ad.get("cp"),
                "dpe_letter":ad.get("dpe"),
                "raw_data":ad,
            }
        except: return None

    def _parse_block(self, block):
        try:
            url_m = re.search(r'href="(/annonces/[^"]+)"', block)
            price_m = re.search(r'(\d[\d\s\.]+)\s*€', block)
            surface_m = re.search(r'(\d+)\s*m²', block)
            title_m = re.search(r'<h2[^>]*>(.*?)</h2>', block, re.DOTALL)
            if not price_m: return None
            return {
                "source":"pap",
                "url": f"{self.BASE_URL}{url_m.group(1)}" if url_m else "",
                "title": re.sub(r'<[^>]+>','',title_m.group(1)).strip() if title_m else "",
                "price": int(price_m.group(1).replace(" ","").replace(".","")),
                "surface": float(surface_m.group(1)) if surface_m else None,
            }
        except: return None

    def scrape(self):
        new_listings = []
        total = 0
        for city in SEARCH_CONFIG["cities"]:
            logger.info(f"PAP: {city['name']}...")
            page = 1
            while total < self.max_listings and page <= 5:
                url = self._build_search_url(city, page)
                logger.debug(f"PAP URL: {url}")
                try:
                    time.sleep(self.delay)
                    resp = self.session.get(url, timeout=15, allow_redirects=True)
                    resp.raise_for_status()
                    logger.debug(f"PAP: page {page} — {len(resp.text)} chars, status {resp.status_code}, final URL: {resp.url}")
                except requests.RequestException as e:
                    logger.error(f"PAP erreur: {e}")
                    break

                # Sauvegarder le HTML pour debug (première page seulement)
                if page == 1 and total == 0:
                    try:
                        with open("data/debug_pap.html", "w", encoding="utf-8") as f:
                            f.write(resp.text[:50000])
                        logger.debug("PAP: HTML sauvegardé dans data/debug_pap.html")
                    except: pass

                listings = self._parse_html(resp.text)
                if not listings:
                    logger.info(f"PAP: aucune annonce trouvée page {page}")
                    break
                for l in listings:
                    l.setdefault("city", city["name"])
                    l.setdefault("latitude", city.get("lat"))
                    l.setdefault("longitude", city.get("lon"))
                    l["id"] = generate_listing_id("pap", l.get("url",""), l.get("title",""), l.get("price",0))
                    if insert_listing(l):
                        new_listings.append(l)
                        logger.info(f"  NOUVEAU: {l.get('title','?')[:50]} — {l.get('price','?')}€ — {l.get('surface','?')}m²")
                    total += 1
                page += 1
        logger.info(f"PAP: {len(new_listings)} nouvelles sur {total}")
        return new_listings
