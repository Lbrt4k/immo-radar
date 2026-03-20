#!/bin/bash
# ============================================================
#  ImmoRadar — Script d'installation automatique
#  Exécuter : bash setup.sh
# ============================================================

set -e

BOLD='\033[1m'
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

echo ""
echo -e "${BLUE}${BOLD}╔══════════════════════════════════════════════╗${NC}"
echo -e "${BLUE}${BOLD}║       🏠  ImmoRadar — Installation          ║${NC}"
echo -e "${BLUE}${BOLD}╚══════════════════════════════════════════════╝${NC}"
echo ""

# ---- 1. Vérifier Python 3 ----
echo -e "${BOLD}[1/5] Vérification de Python 3...${NC}"
if command -v python3 &>/dev/null; then
    PY=$(python3 --version 2>&1)
    echo -e "  ${GREEN}✓${NC} $PY détecté"
else
    echo -e "  ${RED}✗ Python 3 non trouvé${NC}"
    echo -e "  ${YELLOW}Installation via Homebrew...${NC}"
    if command -v brew &>/dev/null; then
        brew install python3
    else
        echo -e "  ${RED}Homebrew non installé. Lance d'abord :${NC}"
        echo '  /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"'
        echo "  Puis relance ce script."
        exit 1
    fi
fi

# ---- 2. Créer l'environnement virtuel ----
echo ""
echo -e "${BOLD}[2/5] Création de l'environnement virtuel...${NC}"
if [ ! -d "venv" ]; then
    python3 -m venv venv
    echo -e "  ${GREEN}✓${NC} Environnement virtuel créé"
else
    echo -e "  ${GREEN}✓${NC} Environnement virtuel déjà existant"
fi

# Activer le venv
source venv/bin/activate
echo -e "  ${GREEN}✓${NC} Environnement activé ($(python --version))"

# ---- 3. Installer les dépendances ----
echo ""
echo -e "${BOLD}[3/5] Installation des dépendances Python...${NC}"
pip install --upgrade pip -q
pip install -r requirements.txt -q
echo -e "  ${GREEN}✓${NC} requests installé"
echo -e "  ${GREEN}✓${NC} schedule installé"

# ---- 4. Créer le dossier data ----
echo ""
echo -e "${BOLD}[4/5] Création du dossier data...${NC}"
mkdir -p data
echo -e "  ${GREEN}✓${NC} Dossier data/ prêt"

# ---- 5. Configuration de la clé API ----
echo ""
echo -e "${BOLD}[5/5] Configuration...${NC}"
echo ""

# Vérifier si la clé est déjà dans l'environnement
if [ -z "$ANTHROPIC_API_KEY" ]; then
    echo -e "  ${YELLOW}Clé API Anthropic non détectée dans l'environnement.${NC}"
    echo ""
    read -p "  Colle ta clé API Anthropic (sk-ant-...): " API_KEY
    echo ""

    if [ -n "$API_KEY" ]; then
        # Créer un fichier .env
        echo "ANTHROPIC_API_KEY=$API_KEY" > .env
        export ANTHROPIC_API_KEY="$API_KEY"
        echo -e "  ${GREEN}✓${NC} Clé API sauvegardée dans .env"
    else
        echo -e "  ${YELLOW}⚠ Pas de clé API — le scoring fonctionnera en mode simulé${NC}"
    fi
else
    echo -e "  ${GREEN}✓${NC} Clé API Anthropic détectée dans l'environnement"
fi

# Telegram (optionnel)
echo ""
echo -e "  ${BOLD}Configuration Telegram (optionnel, appuie Entrée pour passer) :${NC}"
read -p "  Token du bot Telegram: " TG_TOKEN
read -p "  Chat ID Telegram: " TG_CHAT

if [ -n "$TG_TOKEN" ] && [ -n "$TG_CHAT" ]; then
    echo "TELEGRAM_BOT_TOKEN=$TG_TOKEN" >> .env
    echo "TELEGRAM_CHAT_ID=$TG_CHAT" >> .env
    echo -e "  ${GREEN}✓${NC} Telegram configuré"
else
    echo -e "  ${YELLOW}⚠ Telegram non configuré — les alertes s'afficheront dans le terminal${NC}"
fi

# ---- Créer le script de lancement ----
cat > run.sh << 'RUNEOF'
#!/bin/bash
cd "$(dirname "$0")"
source venv/bin/activate

# Charger le .env si présent
if [ -f .env ]; then
    export $(cat .env | xargs)
fi

python3 main.py "$@"
RUNEOF
chmod +x run.sh

cat > run_loop.sh << 'LOOPEOF'
#!/bin/bash
cd "$(dirname "$0")"
source venv/bin/activate

if [ -f .env ]; then
    export $(cat .env | xargs)
fi

echo "🏠 ImmoRadar — Mode surveillance (Ctrl+C pour arrêter)"
python3 main.py --loop ${1:-30}
LOOPEOF
chmod +x run_loop.sh

# ---- Résumé ----
echo ""
echo -e "${GREEN}${BOLD}╔══════════════════════════════════════════════╗${NC}"
echo -e "${GREEN}${BOLD}║       ✅  Installation terminée !            ║${NC}"
echo -e "${GREEN}${BOLD}╚══════════════════════════════════════════════╝${NC}"
echo ""
echo -e "  ${BOLD}Pour lancer ImmoRadar :${NC}"
echo ""
echo -e "    ${BLUE}./run.sh${NC}                  Pipeline complet (1 fois)"
echo -e "    ${BLUE}./run_loop.sh${NC}             Surveillance auto toutes les 30 min"
echo -e "    ${BLUE}./run_loop.sh 15${NC}          Surveillance toutes les 15 min"
echo -e "    ${BLUE}./run.sh --scrape${NC}         Scraping seul"
echo -e "    ${BLUE}./run.sh --score${NC}          Scoring seul"
echo -e "    ${BLUE}./run.sh --dashboard${NC}      Exporter pour le dashboard"
echo ""
echo -e "  ${BOLD}Dashboard :${NC}"
echo -e "    Ouvre ${BLUE}dashboard.html${NC} dans ton navigateur"
echo ""
echo -e "  ${BOLD}Configuration :${NC}"
echo -e "    Modifie les villes et critères dans ${BLUE}config.py${NC}"
echo ""
echo -e "  ${YELLOW}Lancer le premier scan maintenant ? (o/n)${NC}"
read -p "  > " LAUNCH

if [[ "$LAUNCH" == "o" || "$LAUNCH" == "O" || "$LAUNCH" == "oui" ]]; then
    echo ""
    echo -e "${BLUE}${BOLD}Lancement du premier scan...${NC}"
    echo ""
    source venv/bin/activate
    if [ -f .env ]; then
        export $(cat .env | xargs)
    fi
    python3 main.py
fi
