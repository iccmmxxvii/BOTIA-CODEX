# BOTIA – Polymarket BTC 5m Paper Trading

BOTIA es un bot headless de paper trading para mercados BTC Up/Down 5m de Polymarket.

## Features

- Consume datos reales de Polymarket:
  - Gamma (metadata de mercados)
  - RTDS (precio spot BTC en tiempo real)
- Simula entradas en mercados BTC Up/Down 5m:
  - Usa último precio BTC vs `price_to_beat` del market
  - Crea múltiples paper trades (micro-bets)
  - Resuelve PnL según resultado del mercado

## Estructura

- `botia_agent.py`: entrypoint headless
- `core/config.py`: configuración vía `.env`
- `core/storage.py`: schema SQLite y conexión
- `core/log.py`: logging y STATUS.md
- `core/engine.py`: lógica de heartbeat, ticks, paper trades y resolución
- `core/polymarket/gamma.py`: cliente Gamma API
- `core/polymarket/rtds.py`: cliente WebSocket RTDS (cryptoPrices:BTC)
- `core/utils/timeutils.py`: helpers de tiempo

## Uso rápido

```bash
cd botia
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env
# edita MARKET_SLUG si es necesario

python3 -m compileall .
python3 botia_agent.py
```
