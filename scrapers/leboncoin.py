"""ImmoRadar - Scraper LeBonCoin (API publique)"""
import time, json, logging, requests
from config import SEARCH_CONFIG, SCRAPING_CONFIG
from database import insert_listing, generate_listing_id

logger = logging.getLogger("immo_radar.leboncoin")


class LeBonCoinScraper:
    """Scraper LeBonCoin via l'API publique."""

    API_URL = "https://api.leboncoin.fr/finder/search"
    BASE_URL = "https://www.leboncoin.fr"

    # Mapping villes -> codes départements LBC
    DEPT_CODES = {
        "01": "alsace", "02": "alsace", "03": "auvergne", "06": "provence_alpes_cote_d_azur",
        "13": "provence_alpes_cote_d_azur", "31": "midi_pyrenees", "33": "aquitaine",
        "34": "languedoc_roussillon", "35": "bretagne", "38": "rhone_alpes",
        "44": "pays_de_la_loire", "59": "nord_pas_de_calais", "67": "alsace",
        "69": "rhone_alpes", "75": "ile_de_france", "76": "haute_normandie",
        "77": "ile_de_france", "78": "ile_de_france", "83": "provence_alpes_cote_d_azur",
        "91": "ile_de_france", "92": "ile_de_france", "93": "ile_de_france",
        "94": "ile_de_france", "95": "ile_de_france",
    }

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "fr-FR,fr;q=0.9",
            "Origin": "https://www.leboncoin.fr",
            "Referer": "https://www.leboncoin.fr/",
            "api_key": "ba0c2dad52b3ec",
        })
        self.delay = SCRAPING_CONFIG["request_delay"]
        self.max_listings = SCRAPING_CONFIG["max_listings_per_source"]

    def _build_payload(self, city, page=1):
        """Construit le payload de recherche LBC."""
        dept = city.get("dept", city.get("postal_code", "69000")[:2])

        filters = {
            "category": {"id": "9"},  # 9 = Ventes immobilières
            "enums": {
                "real_estate_type": ["1", "2"],  # 1=maison, 2=appartement
                "ad_type": ["offer"],
            },
            "ranges": {},
            "location": {
                "locations": [{
                    "locationType": "city",
                    "label": city["name"],
                    "city": city["name"],
                    "zipcode": city.get("postal_code", ""),
                    "department_id": dept,
                    "region_id": "",
                }]
            },
        }

        if SEARCH_CONFIG.get("price_min") or SEARCH_CONFIG.get("price_max"):
            filters["ranges"]["price"] = {}
            if SEARCH_CONFIG.get("price_min"):
                filters["ranges"]["price"]["min"] = SEARCH_CONFIG["price_min"]
            if SEARCH_CONFIG.get("price_max"):
                filters["ranges"]["price"]["max"] = SEARCH_CONFIG["price_max"]

        if SEARCH_CONFIG.get("surface_min"):
            filters["ranges"]["square"] = {"min": SEARCH_CONFIG["surface_min"]}

        if SEARCH_CONFIG.get("rooms_min"):
            filters["ranges"]["rooms"] = {"min": SEARCH_CONFIG["rooms_min"]}

        return {
            "limit": 35,
            "limit_alu": 3,
            "filters": filters,
            "offset": (page - 1) * 35,
            "sort_by": "time",
            "sort_order": "desc",
        }

    def _parse_ad(self, ad):
        """Parse un résultat de l'API LBC."""
        try:
            list_id = str(ad.get("list_id", ""))
            price = None
            surface = None
            rooms = None
            dpe = None
            ges = None
            prop_type = ""

            # Extraire le prix
            price_list = ad.get("price", [])
            if isinstance(price_list, list) and price_list:
                price = int(price_list[0])
            elif isinstance(price_list, (int, float)):
                price = int(price_list)

            if not price:
                return None

            # Extraire les attributs
            for attr in ad.get("attributes", []):
                key = attr.get("key", "")
                val = attr.get("value", "")
                if key == "square": surface = float(val)
                elif key == "rooms": rooms = int(val)
                elif key == "energy_rate": dpe = val.upper() if val in "abcdefgABCDEFG" else None
                elif key == "ges": ges = val.upper() if val in "abcdefgABCDEFG" else None
                elif key == "real_estate_type":
                    prop_type = "maison" if val == "1" else "appartement" if val == "2" else val

            # Extraire la localisation
            location = ad.get("location", {})
            city = location.get("city", "")
            postal = location.get("zipcode", "")
            lat = location.get("lat")
            lon = location.get("lng")

            # Extraire les images
            images = []
            for img in ad.get("images", {}).get("urls_large", ad.get("images", {}).get("urls", []))[:5]:
                images.append(img)

            url = ad.get("url") or f"{self.BASE_URL}/ad/ventes_immobilieres/{list_id}.htm"
            if not url.startswith("http"):
                url = f"{self.BASE_URL}{url}"

            return {
                "source": "leboncoin",
                "url": url,
                "title": ad.get("subject", ad.get("title", "")),
                "description": ad.get("body", ""),
                "price": price,
                "surface": surface,
                "rooms": rooms,
                "property_type": prop_type,
                "city": city,
                "postal_code": postal,
                "address": location.get("address", ""),
                "latitude": lat,
                "longitude": lon,
                "images": images,
                "dpe_letter": dpe,
                "ges_letter": ges,
                "raw_data": {"list_id": list_id, "first_publication_date": ad.get("first_publication_date")},
            }
        except Exception as e:
            logger.debug(f"LBC parse error: {e}")
            return None

    def _try_html_fallback(self, city):
        """Fallback: scraper la page HTML si l'API ne marche pas."""
        listings = []
        name = city["name"].lower().replace(" ", "-").replace("'", "-")
        dept = city.get("dept", "")

        url = f"{self.BASE_URL}/recherche?category=9&locations={name}__{dept}"
        params = []
        if SEARCH_CONFIG.get("price_min"): params.append(f"price_min={SEARCH_CONFIG['price_min']}")
        if SEARCH_CONFIG.get("price_max"): params.append(f"price_max={SEARCH_CONFIG['price_max']}")
        if SEARCH_CONFIG.get("surface_min"): params.append(f"square_min={SEARCH_CONFIG['surface_min']}")
        if params: url += "&" + "&".join(params)

        logger.debug(f"LBC HTML fallback URL: {url}")

        try:
            resp = self.session.get(url, timeout=15, allow_redirects=True)
            resp.raise_for_status()
            html = resp.text
            logger.debug(f"LBC HTML: {len(html)} chars")

            # Sauvegarder pour debug
            try:
                with open("data/debug_leboncoin.html", "w", encoding="utf-8") as f:
                    f.write(html[:80000])
            except: pass

            # Chercher __NEXT_DATA__
            import re
            m = re.search(r'<script[^>]*id="__NEXT_DATA__"[^>]*>(.*?)</script>', html, re.DOTALL)
            if m:
                try:
                    data = json.loads(m.group(1))
                    props = data.get("props", {}).get("pageProps", {})

                    # LBC peut mettre les annonces dans différents endroits
                    ads = (props.get("searchData", {}).get("ads", [])
                           or props.get("ads", [])
                           or props.get("initialData", {}).get("ads", []))

                    for ad in ads:
                        l = self._parse_ad(ad)
                        if l: listings.append(l)

                    if listings:
                        logger.debug(f"LBC HTML fallback: {len(listings)} via __NEXT_DATA__")
                except Exception as e:
                    logger.debug(f"LBC __NEXT_DATA__ error: {e}")

            # Chercher du JSON brut
            if not listings:
                import re
                for m in re.finditer(r'"list_id":(\d+).*?"subject":"([^"]*)".*?"price":\[(\d+)\]', html):
                    try:
                        lid = m.group(1)
                        listings.append({
                            "source": "leboncoin",
                            "url": f"{self.BASE_URL}/ad/ventes_immobilieres/{lid}.htm",
                            "title": m.group(2),
                            "price": int(m.group(3)),
                        })
                    except: pass

        except Exception as e:
            logger.debug(f"LBC HTML fallback error: {e}")

        return listings

    def scrape(self):
        """Lance le scraping LeBonCoin."""
        new_listings = []
        total = 0

        for city in SEARCH_CONFIG["cities"]:
            logger.info(f"LeBonCoin: {city['name']}...")
            page = 1

            while total < self.max_listings and page <= 3:
                payload = self._build_payload(city, page)
                logger.debug(f"LBC API page {page}")

                try:
                    time.sleep(self.delay)
                    resp = self.session.post(self.API_URL, json=payload, timeout=15)

                    if resp.status_code == 200:
                        data = resp.json()
                        ads = data.get("ads", [])
                        logger.debug(f"LBC API: {len(ads)} résultats page {page}")

                        if not ads:
                            break

                        for ad in ads:
                            l = self._parse_ad(ad)
                            if l:
                                l.setdefault("city", city["name"])
                                l.setdefault("latitude", city.get("lat"))
                                l.setdefault("longitude", city.get("lon"))
                                l["id"] = generate_listing_id("leboncoin", l["url"], l.get("title",""), l.get("price",0))
                                if insert_listing(l):
                                    new_listings.append(l)
                                    logger.info(f"  NOUVEAU: {l.get('title','?')[:50]} — {l.get('price','?')}€ — {l.get('surface','?')}m²")
                                total += 1
                        page += 1
                    else:
                        logger.warning(f"LBC API status {resp.status_code} — fallback HTML")
                        # Fallback vers HTML
                        fallback = self._try_html_fallback(city)
                        for l in fallback:
                            l.setdefault("city", city["name"])
                            l.setdefault("latitude", city.get("lat"))
                            l.setdefault("longitude", city.get("lon"))
                            l["id"] = generate_listing_id("leboncoin", l.get("url",""), l.get("title",""), l.get("price",0))
                            if insert_listing(l):
                                new_listings.append(l)
                                logger.info(f"  NOUVEAU: {l.get('title','?')[:50]} — {l.get('price','?')}€")
                            total += 1
                        break

                except Exception as e:
                    logger.error(f"LBC erreur: {e}")
                    # Essayer le fallback HTML
                    fallback = self._try_html_fallback(city)
                    for l in fallback:
                        l.setdefault("city", city["name"])
                        l.setdefault("latitude", city.get("lat"))
                        l.setdefault("longitude", city.get("lon"))
                        l["id"] = generate_listing_id("leboncoin", l.get("url",""), l.get("title",""), l.get("price",0))
                        if insert_listing(l):
                            new_listings.append(l)
                            total += 1
                    break

        logger.info(f"LeBonCoin: {len(new_listings)} nouvelles sur {total}")
        return new_listings
