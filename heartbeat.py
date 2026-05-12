"""
Heartbeat: faz GET em /health a cada N minutos para manter o túnel ativo.
Uso: python3 heartbeat.py
"""
import time
import urllib.request
import urllib.error
from datetime import datetime
import config

INTERVAL = 4 * 60  # 4 minutos (abaixo do timeout típico de túneis)
URL = f"http://localhost:{config.WEBHOOK_PORT}/health"


def ping() -> bool:
    try:
        with urllib.request.urlopen(URL, timeout=5) as r:
            return r.status == 200
    except (urllib.error.URLError, OSError):
        return False


def main():
    print(f"Heartbeat iniciado — ping em {URL} a cada {INTERVAL // 60} min")
    print("Ctrl+C para encerrar.\n")
    while True:
        ok = ping()
        status = "OK" if ok else "FALHOU — servidor local está rodando?"
        print(f"[{datetime.now().strftime('%H:%M:%S')}] heartbeat → {status}")
        time.sleep(INTERVAL)


if __name__ == "__main__":
    main()
