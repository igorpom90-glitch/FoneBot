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

# ---------------------- LOG -----------------------
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

# ---------------------- CONFIG -----------------------
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
CHAT_ID = os.environ.get("CHAT_ID")

PRICE_MIN = 50.0
PRICE_MAX = 70.0
SYNC_INTERVAL = 600  # 10 minutos em segundos

URLS = json.loads(os.environ.get("PRODUCT_URLS_JSON", "[]"))
STATE_FILE = "state.json"

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
    today = None
    deu_certo_enviado = False

    while True:
        agora = datetime.now()

        # ---------- Reset diário ----------
        if today != agora.date():
            today = agora.date()
            send_telegram(f"📅 Dia {today.strftime('%d/%m/%Y')}, irei começar a mandar os updates que ainda estou vivo de 10 em 10 minutos")

        # ---------- Mensagem única teste ----------
        if not deu_certo_enviado and agora.hour == 21 and agora.minute == 34:
            send_telegram("✅ deu certo")
            deu_certo_enviado = True

        # ---------- Sincronização de mensagem "ainda estou vivo" ----------
        minutos_passados = agora.hour * 60 + agora.minute
        if minutos_passados % (SYNC_INTERVAL // 60) == 0:  # múltiplo de 10 minutos
            send_telegram("🤖 Ainda estou ativo e monitorando preços...")

        # ---------- Checa preços ----------
        achados = []
        for loja in URLS:
            nome = loja.get("name", "Loja desconhecida")
            url = loja.get("url", "")
            price = fetch_price(url)

            if price and PRICE_MIN <= price <= PRICE_MAX:
                achados.append((nome, price, url))
                # Atualiza estado
                last_price = state.get(nome)
                if last_price != price:
                    state[nome] = price
                    save_state(state)

        # ---------- Envia mensagens ----------
        if achados:
            for nome, price, url in achados:
                send_telegram(f"✅ Produto encontrado!\n🏪 {nome}\n💰 R$ {price:.2f}\n{url}")
        else:
            send_telegram("🤖 Ainda estou vivo, promoção não encontrada em nenhuma loja")

        time.sleep(60)  # loop rápido para não perder o intervalo sincronizado

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
    send_telegram("🤖 Bot iniciado. Monitorando preços e enviando sinal de atividade sincronizado a cada 10 minutos.")
    
    threading.Thread(target=monitor, daemon=True).start()
    start_web()
