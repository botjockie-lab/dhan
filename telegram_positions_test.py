import unittest
from unittest.mock import MagicMock, patch
from dhan_risk_manager import DhanRiskManager, CONFIG

class TelegramPositionsTest(unittest.TestCase):
    def setUp(self):
        # A minimal config for the test
        self.config = {
            "ACCESS_TOKEN": "test_token",
            "DAILY_STOPLOSS": -1000,
            "DAILY_TARGET": 2000,
        }
        self.dhan = DhanRiskManager(self.config)

    @patch('requests.get')
    def test_get_positions_for_telegram(self, mock_get):
        # Sample API response from Dhan
        mock_response_data = [
            {
                "tradingSymbol": "BANKNIFTY",
                "realizedProfit": 0,
                "unrealizedProfit": 1500.50,
            },
            {
                "tradingSymbol": "NIFTY",
                "realizedProfit": 500.25,
                "unrealizedProfit": 0,
            },
            {
                "tradingSymbol": "FINNIFTY",
                "realizedProfit": -200,
                "unrealizedProfit": 0,
            },
            {
                "tradingSymbol": "SENSEX",
                "realizedProfit": 0,
                "unrealizedProfit": -300,
            }
        ]
        
        # Configure the mock
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = mock_response_data
        mock_get.return_value = mock_response

        # Call the method
        positions = self.dhan._get_positions_for_telegram()

        # Assertions
        self.assertEqual(len(positions), 4)

        # 1. Open position (unrealized profit is non-zero)
        self.assertEqual(positions[0]['symbol'], 'BANKNIFTY')
        self.assertEqual(positions[0]['status'], 'OPEN')

        # 2. Closed position (positive realized profit and zero unrealized profit)
        self.assertEqual(positions[1]['symbol'], 'NIFTY')
        self.assertEqual(positions[1]['status'], 'CLOSED')

        # 3. Neither open nor closed (negative realized profit and zero unrealized profit)
        self.assertEqual(positions[2]['symbol'], 'FINNIFTY')
        self.assertEqual(positions[2]['status'], '')
        
        # 4. Open position (unrealized profit is non-zero and negative)
        self.assertEqual(positions[3]['symbol'], 'SENSEX')
        self.assertEqual(positions[3]['status'], 'OPEN')

if __name__ == '__main__':
    unittest.main()
