# 🏠 ImmoRadar

**Détecteur intelligent de bonnes affaires immobilières en France.**

ImmoRadar scrape les principaux sites d'annonces (LeBonCoin, PAP, Bien'ici), croise les données avec les prix du marché (DVF) et le diagnostic énergétique (DPE), puis utilise l'IA (Claude API) pour scorer chaque annonce de 0 à 100.

## ✨ Fonctionnalités

- **Scraping multi-sources** : LeBonCoin, PAP.fr, Bien'ici
- **Enrichissement automatique** : prix marché DVF + diagnostic DPE
- **Scoring IA** : analyse par Claude (Anthropic) avec score 0-100
- **Alertes Telegram** : notification instantanée des meilleures affaires
- **Dashboard pro** : interface web dark mode avec filtres et graphiques
- **100% local** : tourne sur votre machine, aucun serveur requis

## 🚀 Installation

```bash
git clone https://github.com/VOTRE-USERNAME/immo-radar.git
cd immo-radar
chmod +x setup.sh
bash setup.sh
```

Le script va :
1. Créer un environnement Python virtuel
2. Installer les dépendances
3. Vous demander vos clés API (optionnel)

## 📋 Utilisation

```bash
# Pipeline complet (scrape + enrichir + scorer + alerter)
./run.sh

# Scraping seul (mode verbose)
./run.sh --scrape -v

# Mode automatique (toutes les 4h)
./run_loop.sh
```

## 🌐 Dashboard

```bash
cd immo-radar
python3 -m http.server 8000
```
Puis ouvrir http://localhost:8000/dashboard.html

## ⚙️ Configuration

Modifier `config.py` pour :
- Ajouter/supprimer des villes
- Changer les critères de prix, surface, etc.
- Ajuster les pondérations du scoring

## 🔑 Clés API

| Service | Obligatoire | Utilité |
|---------|-------------|---------|
| Anthropic (Claude) | Non | Scoring IA avancé |
| Telegram Bot | Non | Alertes en temps réel |

Sans clé API, le scoring fonctionne en mode simulé.

## 📁 Structure

```
immo-radar/
├── main.py              # Point d'entrée CLI
├── config.py            # Configuration
├── database.py          # Base SQLite
├── scorer.py            # Scoring IA (Claude API)
├── alerts.py            # Alertes Telegram
├── dashboard.html       # Interface web
├── scrapers/
│   ├── pap.py           # Scraper PAP.fr
│   ├── bienici.py       # Scraper Bien'ici
│   └── leboncoin.py     # Scraper LeBonCoin
└── enrichment/
    ├── dvf.py           # Données DVF (prix marché)
    └── dpe.py           # Données DPE (énergie)
```

## 📄 Licence

MIT
