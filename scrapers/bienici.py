"""ImmoRadar - Scraper Bien'ici (corrigé)"""
import time, json, re, logging, requests
from config import SEARCH_CONFIG, SCRAPING_CONFIG
from database import insert_listing, generate_listing_id

logger = logging.getLogger("immo_radar.bienici")


class BieniciScraper:
    BASE_URL = "https://www.bienici.com"

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update(SCRAPING_CONFIG["headers"])
        self.delay = SCRAPING_CONFIG["request_delay"]
        self.max_listings = SCRAPING_CONFIG["max_listings_per_source"]

    def _build_search_url(self, city, page=1):
        """URL de recherche Bien'ici — format HTML classique."""
        name = city["name"].lower().replace(" ", "-").replace("'", "-")
        cp = city.get("postal_code", "")

        url = f"{self.BASE_URL}/recherche/achat/{name}-{cp}"

        params = []
        if SEARCH_CONFIG.get("price_min"): params.append(f"prix-min={SEARCH_CONFIG['price_min']}")
        if SEARCH_CONFIG.get("price_max"): params.append(f"prix-max={SEARCH_CONFIG['price_max']}")
        if SEARCH_CONFIG.get("surface_min"): params.append(f"surface-min={SEARCH_CONFIG['surface_min']}")
        if page > 1: params.append(f"page={page}")
        if params: url += "?" + "&".join(params)
        return url

    def _parse_html(self, html):
        """Parse la page HTML de Bien'ici pour extraire les annonces."""
        listings = []

        # Méthode 1 : __NEXT_DATA__ (Next.js)
        m = re.search(r'<script[^>]*id="__NEXT_DATA__"[^>]*>(.*?)</script>', html, re.DOTALL)
        if m:
            try:
                next_data = json.loads(m.group(1))
                # Naviguer dans la structure Next.js
                page_props = next_data.get("props", {}).get("pageProps", {})

                # Chercher les annonces dans différents chemins possibles
                ads = (page_props.get("realEstateAds", {}).get("realEstateAds", [])
                       or page_props.get("ads", [])
                       or page_props.get("results", {}).get("realEstateAds", [])
                       or page_props.get("searchResults", {}).get("realEstateAds", []))

                for ad in ads:
                    l = self._parse_ad(ad)
                    if l: listings.append(l)

                if listings:
                    logger.debug(f"Bienici: {len(listings)} annonces via __NEXT_DATA__")
                    return listings
            except (json.JSONDecodeError, KeyError, TypeError) as e:
                logger.debug(f"Bienici __NEXT_DATA__ parse error: {e}")

        # Méthode 2 : window.__INITIAL_STATE__
        m = re.search(r'window\.__INITIAL_STATE__\s*=\s*(\{.*?\});?\s*</script>', html, re.DOTALL)
        if m:
            try:
                state = json.loads(m.group(1))
                ads = (state.get("searchResults", {}).get("realEstateAds", [])
                       or state.get("results", []))
                for ad in ads:
                    l = self._parse_ad(ad)
                    if l: listings.append(l)
                if listings:
                    logger.debug(f"Bienici: {len(listings)} annonces via __INITIAL_STATE__")
                    return listings
            except: pass

        # Méthode 3 : JSON-LD
        for m in re.finditer(r'<script[^>]*type="application/ld\+json"[^>]*>(.*?)</script>', html, re.DOTALL):
            try:
                data = json.loads(m.group(1).strip())
                items = data if isinstance(data, list) else [data]
                for item in items:
                    if item.get("@type") in ("Product","RealEstateListing","Residence","Offer","ItemList"):
                        if item.get("@type") == "ItemList":
                            for elem in item.get("itemListElement", []):
                                l = self._from_jsonld(elem.get("item", elem))
                                if l: listings.append(l)
                        else:
                            l = self._from_jsonld(item)
                            if l: listings.append(l)
            except: pass

        # Méthode 4 : Extraction brute des données JSON dans le HTML
        for m in re.finditer(r'"id":"(\d+)"[^}]*"price":(\d+)[^}]*"surfaceArea":([\d.]+)', html):
            try:
                listings.append({
                    "source": "bienici",
                    "url": f"{self.BASE_URL}/annonce/vente/{m.group(1)}",
                    "title": "", "price": int(m.group(2)),
                    "surface": float(m.group(3)),
                    "raw_data": {"id": m.group(1)},
                })
            except: pass

        logger.debug(f"Bienici parse: {len(listings)} annonces")
        return listings

    def _parse_ad(self, ad):
        """Parse un objet annonce JSON."""
        try:
            price = ad.get("price")
            if not price: return None
            ad_id = str(ad.get("id", ""))
            slug = ad.get("slug", ad_id)
            url = ad.get("url") or f"{self.BASE_URL}/annonce/vente/{slug}/{ad_id}"
            if not url.startswith("http"): url = f"{self.BASE_URL}{url}"

            dpe = ad.get("energyClassification") or ad.get("energyValue") or ""
            ges = ad.get("greenhouseGasClassification") or ""

            return {
                "source": "bienici", "url": url,
                "title": ad.get("title") or f"{ad.get('propertyType','')} {ad.get('roomsQuantity','')}p.",
                "description": ad.get("description", ""),
                "price": int(price),
                "surface": ad.get("surfaceArea") or ad.get("surface"),
                "rooms": ad.get("roomsQuantity") or ad.get("rooms"),
                "property_type": (ad.get("propertyType") or "").lower(),
                "city": ad.get("city"),
                "postal_code": ad.get("postalCode") or ad.get("zipCode"),
                "address": ad.get("street"),
                "latitude": ad.get("blurredLatitude") or ad.get("latitude"),
                "longitude": ad.get("blurredLongitude") or ad.get("longitude"),
                "images": [p.get("url","") for p in ad.get("photos",[])[:5]] if ad.get("photos") else [],
                "dpe_letter": dpe if dpe in "ABCDEFG" else None,
                "ges_letter": ges if ges in "ABCDEFG" else None,
                "raw_data": {"id":ad_id, "publication_date":ad.get("publicationDate")},
            }
        except: return None

    def _from_jsonld(self, data):
        try:
            offers = data.get("offers", {})
            price = offers.get("price") if isinstance(offers, dict) else None
            if not price: return None
            url = data.get("url", "")
            if url and not url.startswith("http"): url = f"{self.BASE_URL}{url}"
            return {"source":"bienici","url":url,"title":data.get("name",""),
                    "description":data.get("description",""),"price":int(float(price))}
        except: return None

    def scrape(self):
        new_listings = []
        total = 0
        for city in SEARCH_CONFIG["cities"]:
            logger.info(f"Bienici: {city['name']}...")
            page = 1
            while total < self.max_listings and page <= 5:
                url = self._build_search_url(city, page)
                logger.debug(f"Bienici URL: {url}")
                try:
                    time.sleep(self.delay)
                    resp = self.session.get(url, timeout=15, allow_redirects=True)
                    resp.raise_for_status()
                    logger.debug(f"Bienici: page {page} — {len(resp.text)} chars, status {resp.status_code}, final URL: {resp.url}")
                except requests.RequestException as e:
                    logger.error(f"Bienici erreur: {e}")
                    break

                # Sauvegarder le HTML pour debug
                if page == 1 and total == 0:
                    try:
                        with open("data/debug_bienici.html", "w", encoding="utf-8") as f:
                            f.write(resp.text[:50000])
                        logger.debug("Bienici: HTML sauvegardé dans data/debug_bienici.html")
                    except: pass

                listings = self._parse_html(resp.text)
                if not listings:
                    logger.info(f"Bienici: aucune annonce page {page}")
                    break
                for l in listings:
                    if not l: continue
                    l.setdefault("city", city["name"])
                    l.setdefault("latitude", city.get("lat"))
                    l.setdefault("longitude", city.get("lon"))
                    l["id"] = generate_listing_id("bienici", l.get("url",""), l.get("title",""), l.get("price",0))
                    if insert_listing(l):
                        new_listings.append(l)
                        logger.info(f"  NOUVEAU: {l.get('title','?')[:50]} — {l.get('price','?')}€ — {l.get('surface','?')}m²")
                    total += 1
                page += 1
        logger.info(f"Bienici: {len(new_listings)} nouvelles sur {total}")
        return new_listings
