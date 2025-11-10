# bot.py (versão com headers, retries e delays)
import os
import time
import json
import re
import logging
import random
import requests
from requests.adapters import HTTPAdapter, Retry
from bs4 import BeautifulSoup
from flask import Flask
import threading
from datetime import datetime, timedelta, timezone

# ---------------------- LOG -----------------------
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

# ---------------------- CONFIG -----------------------
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
CHAT_ID = os.environ.get("CHAT_ID")

PRICE_MIN = float(os.environ.get("PRICE_MIN", "50"))
PRICE_MAX = float(os.environ.get("PRICE_MAX", "70"))
ACTIVE_INTERVAL = int(os.environ.get("ACTIVE_INTERVAL", "600"))  # 10 minutos
URLS = json.loads(os.environ.get("PRODUCT_URLS_JSON", "[]"))
STATE_FILE = os.environ.get("STATE_FILE", "state_earbuds.json")

# Optional proxy (ex: "http://user:pass@1.2.3.4:8080" or "http://1.2.3.4:8080")
PROXY = os.environ.get("PROXY", "") or None
PROXIES = {"http": PROXY, "https": PROXY} if PROXY else None

# Fuso horário Campos dos Goytacazes (UTC-3)
BR_TZ = timezone(timedelta(hours=-3))

# ---------------------- SESSÃO REQUESTS (retries/backoff) -----------------------
session = requests.Session()
retries = Retry(total=3, backoff_factor=1, status_forcelist=(429, 500, 502, 503, 504))
adapter = HTTPAdapter(max_retries=retries)
session.mount("https://", adapter)
session.mount("http://", adapter)

# Headers mais realistas (desktop + mobile fallback)
HEADERS_DESKTOP = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/118.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
    "Accept-Language": "pt-BR,pt;q=0.9,en-US;q=0.8,en;q=0.7",
    "Referer": "https://www.google.com/",
    "Connection": "keep-alive",
}

HEADERS_MOBILE = {
    "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) "
                  "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.0 Mobile/15E148 Safari/604.1",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
    "Accept-Language": "pt-BR,pt;q=0.9",
    "Referer": "https://www.google.com/",
    "Connection": "keep-alive",
}

# ---------------------- HELPERS -----------------------
def send_telegram(message: str):
    if not TELEGRAM_TOKEN or not CHAT_ID:
        logging.error("TELEGRAM_TOKEN ou CHAT_ID não configurados.")
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {"chat_id": CHAT_ID, "text": message, "parse_mode": "HTML"}
    try:
        session.post(url, json=payload, timeout=15, proxies=PROXIES)
    except Exception as e:
        logging.error("Erro ao enviar Telegram: %s", e)

def extract_price_from_text(text: str):
    # procura padrões como R$ 1.234,56 ou 1234,56
    m = re.search(r"R\$\s*([0-9\.\,]{1,})", text)
    if m:
        raw = m.group(1)
        try:
            return float(raw.replace(".", "").replace(",", "."))
        except:
            pass
    # fallback: busca número com vírgula
    m2 = re.search(r"([0-9]{2,}\,[0-9]{2})", text)
    if m2:
        try:
            return float(m2.group(1).replace(".", "").replace(",", "."))
        except:
            pass
    return None

def fetch_price(url: str):
    """
    Tenta buscar preço com headers desktop; se 403, tenta mobile; adiciona delays.
    Retorna float preço ou None.
    """
    try:
        # delay pequeno antes da requisição para reduzir padrão de scraping
        time.sleep(random.uniform(1.0, 3.0))

        # tenta header desktop
        r = session.get(url, headers=HEADERS_DESKTOP, timeout=20, proxies=PROXIES)
        if r.status_code == 403:
            logging.info("403 com desktop header em %s — tentando mobile header", url)
            # tentativa com mobile headers e novo delay
            time.sleep(random.uniform(1.0, 2.0))
            r = session.get(url, headers=HEADERS_MOBILE, timeout=20, proxies=PROXIES)

        r.raise_for_status()
        html = r.text

        # 1) extrair preço do HTML bruto (mais genérico)
        price = extract_price_from_text(html)
        if price:
            return price

        # 2) tentar seletores comuns
        soup = BeautifulSoup(html, "html.parser")
        selectors = [
            "#priceblock_ourprice", "#priceblock_dealprice",
            ".price", ".product-price", ".price-tag", ".preco", ".valor", ".price-sales",
            ".product-price__value", ".price__selling", ".pricebox-price"
        ]
        for sel in selectors:
            el = soup.select_one(sel)
            if el and el.get_text(strip=True):
                p = extract_price_from_text(el.get_text(" ", strip=True))
                if p:
                    return p

    except requests.exceptions.RequestException as e:
        logging.warning("Request error ao buscar %s: %s", url, e)
    except Exception as e:
        logging.exception("Erro inesperado ao buscar preço: %s", e)

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
    logging.info("Loop de monitoramento iniciado (fones).")
    # para garantir que a primeira execução envie mensagem imediatamente:
    last_sent = None

    while True:
        now = datetime.now(BR_TZ)
        current_time_str = now.strftime("%d/%m/%Y %H:%M:%S")
        send_now = False

        if last_sent is None:
            send_now = True
        else:
            elapsed = (now - last_sent).total_seconds()
            if elapsed >= ACTIVE_INTERVAL:
                send_now = True

        # checar preços em todas as lojas (sempre checamos; só enviamos a cada ACTIVE_INTERVAL)
        encontrados = []
        for loja in URLS:
            nome = loja.get("name", "Loja desconhecida")
            url = loja.get("url", "")
            if not url:
                continue
            price = fetch_price(url)
            logging.info("Busca %s -> %s", nome, price)
            if price is not None and PRICE_MIN <= price <= PRICE_MAX:
                encontrados.append((nome, price, url))
                # atualiza estado para evitar repetição de notificação de preço se quiser
                state[nome] = price

        # salva estado sempre
        save_state(state)

        # envia mensagens SOMENTE quando for hora de enviar (cada ACTIVE_INTERVAL)
        if send_now:
            base = f"🤖 Ainda estou ativo - {current_time_str}"
            if encontrados:
                for nome, price, url in encontrados:
                    send_telegram(f"{base}\n✅ Achei promoção do fone!\n🏪 {nome}\n💰 R$ {price:.2f}\n{url}")
            else:
                send_telegram(f"{base}, promoção do fone não encontrada em nenhuma loja ❌")
            last_sent = now

        # espera pouco e volta ao topo para checar novamente (não enviar) — evita drift
        time.sleep(5)

# ---------------------- SERVIDOR WEB -----------------------
app = Flask(__name__)

@app.route("/")
def home():
    return "Bot fone rodando ✅"

def start_web():
    port = int(os.environ.get("PORT", 8080))
    logging.info("Flask rodando na porta %s", port)
    app.run(host="0.0.0.0", port=port)

# ---------------------- MAIN -----------------------
if __name__ == "__main__":
    send_telegram("🤖 Bot do fone iniciado. Mensagens a cada 10 minutos (com headers mais realistas).")
    threading.Thread(target=monitor, daemon=True).start()
    start_web()
