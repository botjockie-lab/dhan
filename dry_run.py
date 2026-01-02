"""Dry-run test harness for DhanRiskManager per-position percent-taking

This script simulates a handful of positions and demonstrates the
percent-based profit-taking logic without calling the real Dhan API.
It monkeypatches `get_positions_pnl` and `requests.post` to simulate
API responses and order placement.
"""
import logging
import requests
from datetime import datetime

from dhan_risk_manager import DhanRiskManager


logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')


class FakeResponse:
    def __init__(self, status_code=200, payload=None, text=""):
        self.status_code = status_code
        self._payload = payload or {}
        self.text = text

    def json(self):
        return self._payload


def main():
    # Create a fake config enabling per-position percent take at 5%
    cfg = {
        "ACCESS_TOKEN": "TEST_TOKEN",
        "DAILY_STOPLOSS": -1000.0,
        "DAILY_TARGET": 1000.0,
        "CHECK_INTERVAL_SECONDS": 60,
        "MARKET_START_TIME": "09:15",
        "MARKET_END_TIME": "15:30",
        "ENABLE_LOGGING": False,
        "LOG_FILE": "dryrun.log",
        "TELEGRAM_ENABLED": False,
        "TELEGRAM_BOT_TOKEN": "",
        "TELEGRAM_CHAT_ID": "",
        "SEND_PNL_UPDATES": False,
        "SEND_ONLY_ALERTS": False,
        "ENABLE_POSITION_PERCENT_TAKE": True,
        "POSITION_PERCENT_TAKE": 5.0,
    }

    # Build example positions
    # Format mirrors what Dhan API position objects might contain (keys used by the manager)
    raw_positions = [
        # Below threshold (0.5% profit)
        {
            'tradingSymbol': 'ABC',
            'netQty': 10,
            'realizedProfit': 0,
            'unrealizedProfit': 5,  # ₹5 on ₹1000 invested -> 0.5%
            'averagePrice': 100,
            'exchangeSegment': 'NSE',
            'productType': 'MIS',
            'securityId': 'SEC-ABC',
            'dhanClientId': 'CL-1'
        },
        # Above threshold (6% profit)
        {
            'tradingSymbol': 'XYZ',
            'netQty': 5,
            'realizedProfit': 0,
            'unrealizedProfit': 60,  # ₹60 on ₹1000 invested -> 6%
            'averagePrice': 200,
            'exchangeSegment': 'NSE',
            'productType': 'MIS',
            'securityId': 'SEC-XYZ',
            'dhanClientId': 'CL-1'
        },
        # Lossing position
        {
            'tradingSymbol': 'LMN',
            'netQty': -20,
            'realizedProfit': 0,
            'unrealizedProfit': -10,  # Loss
            'averagePrice': 50,
            'exchangeSegment': 'NSE',
            'productType': 'MIS',
            'securityId': 'SEC-LMN',
            'dhanClientId': 'CL-1'
        }
    ]

    # Convert to manager's expected position_details structure
    position_details = []
    total_pnl = 0
    for p in raw_positions:
        realized = float(p.get('realizedProfit', 0))
        unrealized = float(p.get('unrealizedProfit', 0))
        total = realized + unrealized
        total_pnl += total
        position_details.append({
            'symbol': p.get('tradingSymbol', 'N/A'),
            'realized': realized,
            'unrealized': unrealized,
            'total': total,
            'position_data': p
        })

    # Instantiate manager
    manager = DhanRiskManager(cfg)

    # Monkeypatch get_positions_pnl to return our simulated positions
    def fake_get_positions_pnl():
        return total_pnl, position_details

    manager.get_positions_pnl = fake_get_positions_pnl

    # Monkeypatch requests.post used by square_off_position to simulate order placement
    original_post = requests.post

    def fake_post(url, headers=None, json=None, timeout=None, params=None):
        logging.info(f"[fake_post] POST to {url} with payload: {json or params}")
        if url.rstrip('/').endswith('/orders'):
            return FakeResponse(200, {'orderId': 'DRYRUN-ORDER-001'})
        if url.rstrip('/').endswith('/killSwitch'):
            return FakeResponse(200, {'dhanClientId': 'CL-1', 'killSwitchStatus': 'activated'})
        return FakeResponse(200, {})

    requests.post = fake_post

    try:
        print('\n--- Dry-run: Demonstrating per-position percent-taking ---')
        print(f"Simulated total P&L: ₹{total_pnl:.2f}")
        status = manager.check_and_manage_risk()
        print('\nManager returned status:', status)
        print('\nRemaining positions list after dry-run (unchanged in simulation):')
        for pos in position_details:
            print(f" - {pos['symbol']}: P&L=₹{pos['total']:.2f} | netQty={pos['position_data'].get('netQty')}")
        print('\nNote: This was a simulated run; real API calls were not performed for positions retrieval.')
    finally:
        # restore monkeypatched call
        requests.post = original_post


if __name__ == '__main__':
    main()
