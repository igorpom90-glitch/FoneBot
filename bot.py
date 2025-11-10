import os
import time
import json
import re
import logging
import requests
from bs4 import BeautifulSoup
from flask import Flask
import threading
from datetime import datetime, timedelta, timezone

# ---------------------- LOG -----------------------
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

# ---------------------- CONFIG -----------------------
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
CHAT_ID = os.environ.get("CHAT_ID")

PRICE_MIN = 50.0
PRICE_MAX = 70.0
ACTIVE_INTERVAL = 600  # 10 minutos
URLS = json.loads(os.environ.get("PRODUCT_URLS_JSON", "[]"))
STATE_FILE = "state.json"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 14_0 like Mac OS X) "
                  "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/14.0 Mobile/15A372 Safari/604.1"
}

# Fuso horário de Campos dos Goytacazes
BR_TZ = timezone(timedelta(hours=-3))

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

    while True:
        now = datetime.now(BR_TZ)
        current_time_str = now.strftime("%H:%M:%S")
        message_base = f"🤖 Ainda estou ativo - {current_time_str}"

        encontrados = []
        for loja in URLS:
            nome = loja.get("name", "Loja desconhecida")
            url = loja.get("url", "")
            price = fetch_price(url)
            if price is None:
                continue
            if PRICE_MIN <= price <= PRICE_MAX:
                encontrados.append(f"🏪 {nome} - R$ {price:.2f}\n{url}")
                state[nome] = price

        save_state(state)

        # ---------- Mensagem final ----------
        if encontrados:
            for item in encontrados:
                send_telegram(f"{message_base}\n✅ Achei promoção do fone!\n{item}")
        else:
            send_telegram(f"{message_base}, promoção do fone não encontrada em nenhuma loja ❌")

        time.sleep(ACTIVE_INTERVAL)

# ---------------------- SERVIDOR WEB -----------------------
app = Flask(__name__)

@app.route("/")
def home():
    return "Bot rodando ✅"

def start_web():
    port = int(os.environ.get("PORT", 8080))
    logging.info(f"Flask rodando na porta {port}")
    app.run(host="0.0.0.0", port=port)

# ---------------------- MAIN -----------------------
if __name__ == "__main__":
    send_telegram("🤖 Bot do fone iniciado. Mensagens de status a cada 10 minutos.")
    threading.Thread(target=monitor, daemon=True).start()
    start_web()
