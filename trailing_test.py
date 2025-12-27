import unittest
from unittest.mock import MagicMock

# Mock CONFIG dictionary to simulate settings from dhan_risk_manager.py
CONFIG = {
    "ENABLE_TRAILING_STOPLOSS": True,
    "TRAILING_STOPLOSS_ACTIVATE_PROFIT": 1000.0,
    "TRAILING_STOPLOSS_TRAIL_PERCENT": 10.0,  # Trail by 10%, so SL is at 90% of PNL
    "DAILY_STOPLOSS": -500.0,
    "DAILY_TARGET": 2000.0,
    "TELEGRAM_ENABLED": False,
    "SEND_PNL_UPDATES": False,
    "SEND_ONLY_ALERTS": False,
    "ENABLE_POSITION_PERCENT_TAKE": False,
    "ENABLE_POSITION_PERCENT_STOPLOSS": False,
    "TELEGRAM_PNL_INTERVAL_SECONDS": 0,
    "EFFECTIVE_SEND_PNL_UPDATES": False,
}

# Simplified DhanRiskManager for testing the trailing stoploss logic
class SimpleDhanRiskManager:
    def __init__(self, config, telegram_notifier=None):
        self.config = config
        self.daily_stoploss = config["DAILY_STOPLOSS"]
        self.daily_target = config["DAILY_TARGET"]
        self.telegram = telegram_notifier

    def check_trailing_stoploss(self, pnl):
        # This method isolates and simulates the trailing stoploss logic
        if self.config.get("ENABLE_TRAILING_STOPLOSS") and pnl > 0:
            activation_profit = float(self.config.get("TRAILING_STOPLOSS_ACTIVATE_PROFIT", 0.0))
            trail_percent = float(self.config.get("TRAILING_STOPLOSS_TRAIL_PERCENT", 0.0))

            if activation_profit > 0 and trail_percent > 0 and pnl >= activation_profit:
                new_trailing_stoploss = pnl * (1 - (trail_percent / 100))
                if new_trailing_stoploss > self.daily_stoploss:
                    self.daily_stoploss = new_trailing_stoploss
                    # In real code, logging and notification would happen here


class TestTrailingStoploss(unittest.TestCase):

    def setUp(self):
        """Set up a new risk manager for each test."""
        # Reset CONFIG for each test to ensure isolation
        self.config = CONFIG.copy()
        self.telegram_mock = MagicMock()
        self.risk_manager = SimpleDhanRiskManager(self.config, self.telegram_mock)

    def test_trailing_not_activated_below_threshold(self):
        """SL should not change if PNL is below the activation profit."""
        initial_sl = self.risk_manager.daily_stoploss
        self.risk_manager.check_trailing_stoploss(pnl=500)
        self.assertEqual(self.risk_manager.daily_stoploss, initial_sl)

    def test_trailing_activates_at_threshold(self):
        """SL should be updated when PNL hits the activation profit."""
        self.risk_manager.check_trailing_stoploss(pnl=1000)
        # 1000 * (1 - 10/100) = 900
        self.assertAlmostEqual(self.risk_manager.daily_stoploss, 900.0)

    def test_trailing_updates_as_pnl_increases(self):
        """SL should continue to update as PNL increases."""
        # First update
        self.risk_manager.check_trailing_stoploss(pnl=1200)
        # 1200 * 0.9 = 1080
        self.assertAlmostEqual(self.risk_manager.daily_stoploss, 1080.0)
        
        # Second update
        self.risk_manager.check_trailing_stoploss(pnl=1500)
        # 1500 * 0.9 = 1350
        self.assertAlmostEqual(self.risk_manager.daily_stoploss, 1350.0)

    def test_trailing_stoploss_does_not_move_down(self):
        """SL should not decrease if PNL falls after an update."""
        # Set an initial trailed SL
        self.risk_manager.check_trailing_stoploss(pnl=1500)
        self.assertAlmostEqual(self.risk_manager.daily_stoploss, 1350.0)
        
        # PNL drops, SL should hold
        self.risk_manager.check_trailing_stoploss(pnl=1400)
        self.assertAlmostEqual(self.risk_manager.daily_stoploss, 1350.0)

    def test_trailing_disabled(self):
        """SL should not change if the feature is disabled in config."""
        self.config["ENABLE_TRAILING_STOPLOSS"] = False
        self.risk_manager = SimpleDhanRiskManager(self.config)
        initial_sl = self.risk_manager.daily_stoploss
        
        self.risk_manager.check_trailing_stoploss(pnl=1500)
        self.assertEqual(self.risk_manager.daily_stoploss, initial_sl)
        
    def test_initial_stoploss_is_respected(self):
        """Trailing SL should only take effect if it's higher than the initial SL."""
        self.config["DAILY_STOPLOSS"] = 1100.0
        self.risk_manager = SimpleDhanRiskManager(self.config)
        
        # PNL is 1200, new potential SL is 1080. Since 1080 is not > 1100, it should not update.
        self.risk_manager.check_trailing_stoploss(pnl=1200)
        self.assertAlmostEqual(self.risk_manager.daily_stoploss, 1100.0)
        
        # PNL is 1300, new potential SL is 1170. Since 1170 > 1100, it should update.
        self.risk_manager.check_trailing_stoploss(pnl=1300)
        self.assertAlmostEqual(self.risk_manager.daily_stoploss, 1170.0)


if __name__ == '__main__':
    unittest.main()