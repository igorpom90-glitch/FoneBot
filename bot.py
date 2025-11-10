import os
import time
import json
import re
import logging
import requests
from bs4 import BeautifulSoup
from flask import Flask
import threading
from datetime import datetime
import pytz

# ---------------------- LOG -----------------------
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

# ---------------------- CONFIG -----------------------
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
CHAT_ID = os.environ.get("CHAT_ID")

PRICE_MIN = 50.0
PRICE_MAX = 70.0
CHECK_INTERVAL = 600  # 10 minutos
TIMEZONE = "America/Sao_Paulo"

STATE_FILE = "state_fone.json"

URLS = [
    {"name": "Amazon", "url": "https://www.amazon.com.br/s?k=Xiaomi+Redmi+Buds+6+Play"},
    {"name": "Mercado Livre", "url": "https://www.mercadolivre.com.br/fone-de-ouvido-Xiaomi-Redmi-Buds-6-Play"},
    {"name": "Casas Bahia", "url": "https://www.casasbahia.com.br/fone-de-ouvido-Xiaomi-Redmi-Buds-6-Play"},
    {"name": "Magazine Luiza", "url": "https://www.magazineluiza.com.br/fone-de-ouvido-Xiaomi-Redmi-Buds-6-Play"},
    {"name": "Pichau", "url": "https://www.pichau.com.br/fone-de-ouvido-Xiaomi-Redmi-Buds-6-Play"},
    {"name": "Kabum", "url": "https://www.kabum.com.br/produto/fone-de-ouvido-Xiaomi-Redmi-Buds-6-Play"},
    {"name": "Fast Shop", "url": "https://www.fastshop.com.br/fone-de-ouvido-Xiaomi-Redmi-Buds-6-Play"},
    {"name": "ShopFacil", "url": "https://www.shopfacil.com.br/fone-de-ouvido-Xiaomi-Redmi-Buds-6-Play"},
    {"name": "Carrefour", "url": "https://www.carrefour.com.br/fone-de-ouvido-Xiaomi-Redmi-Buds-6-Play"},
    {"name": "Submarino", "url": "https://www.submarino.com.br/fone-de-ouvido-Xiaomi-Redmi-Buds-6-Play"}
]

HEADERS = {
    "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 14_0 like Mac OS X) "
                  "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/14.0 Mobile/15A372 Safari/604.1"
}

# ---------------------- FUNÇÕES -----------------------
def send_telegram(message: str):
    if not TELEGRAM_TOKEN or not CHAT_ID:
        logging.error("TELEGRAM_TOKEN ou CHAT_ID não configurados.")
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {"chat_id": CHAT_ID, "text": message, "parse_mode": "HTML"}
    try:
        requests.post(url, json=payload, timeout=15)
    except Exception as e:
        logging.error(f"Erro ao enviar Telegram: {e}")

def fetch_price(url: str):
    try:
        r = requests.get(url, headers=HEADERS, timeout=20)
        r.raise_for_status()
        text = BeautifulSoup(r.text, "html.parser").get_text(" ", strip=True)
        prices = re.findall(r"R\$\s*([0-9\.\,]+)", text)
        if prices:
            return float(prices[0].replace(".", "").replace(",", "."))
    except Exception as e:
        logging.error(f"Erro ao buscar preço de {url}: {e}")
    return None

def load_state():
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except:
            pass
    return {}

def save_state(state):
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)

# ---------------------- MONITOR -----------------------
def monitor():
    state = load_state()
    logging.info("Loop de monitoramento iniciado.")
    tz = pytz.timezone(TIMEZONE)
    last_day = None

    while True:
        now = datetime.now(tz)
        today_str = now.strftime("%d/%m/%Y")

        # ---------- Mensagem de início do dia ----------
        if last_day != today_str:
            send_telegram(f"🤖 Dia {today_str}, irei começar a mandar os updates que ainda estou vivo de 10 em 10 minutos.")
            last_day = today_str

        message_parts = []
        found_prices = False

        for loja in URLS:
            nome = loja["name"]
            url = loja["url"]
            price = fetch_price(url)

            if price is not None and PRICE_MIN <= price <= PRICE_MAX:
                found_prices = True
                send_telegram(f"🤖 Ainda estou ativo - {now.strftime('%H:%M:%S')}, produto Xiaomi Redmi Buds 6 Play a R$ {price:.2f} na loja {nome}\n{url}")

        if not found_prices:
            send_telegram(f"🤖 Ainda estou ativo - {now.strftime('%H:%M:%S')}, promoção do fone não encontrada em nenhuma loja.")

        time.sleep(CHECK_INTERVAL)

# ---------------------- SERVIDOR WEB -----------------------
app = Flask(__name__)

@app.route("/")
def home():
    return "Bot do fone rodando ✅"

def start_web():
    port = int(os.environ.get("PORT", 8080))
    logging.info(f"Flask rodando na porta {port}")
    app.run(host="0.0.0.0", port=port)

# ---------------------- MAIN -----------------------
if __name__ == "__main__":
    send_telegram("🤖 Bot do fone iniciado. Monitorando preços e enviando sinal de atividade a cada 10 minutos a partir das 00:00.")
    threading.Thread(target=monitor, daemon=True).start()
    start_web()
