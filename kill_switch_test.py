import unittest
from unittest.mock import MagicMock, patch

# Since we can't easily import from the script, we recreate the necessary parts.
# This test focuses on the logic within check_and_manage_risk.

# Mock base CONFIG
BASE_CONFIG = {
    "DAILY_STOPLOSS": -1000.0,
    "DAILY_TARGET": 2000.0,
    "ENABLE_KILL_SWITCH": False, # Default off
    "TELEGRAM_ENABLED": True,
    # Add other keys that might be accessed to avoid KeyErrors
    "ENABLE_TRAILING_STOPLOSS": False,
    "EFFECTIVE_SEND_PNL_UPDATES": False,
    "SEND_ONLY_ALERTS": False,
    "ENABLE_POSITION_PERCENT_TAKE": False,
    "ENABLE_POSITION_PERCENT_STOPLOSS": False,
}

class SimplifiedDhanRiskManager:
    """A simplified version of DhanRiskManager to test the kill switch logic."""
    def __init__(self, config, telegram_notifier=None):
        self.config = config
        self.daily_stoploss = config["DAILY_STOPLOSS"]
        self.daily_target = config["DAILY_TARGET"]
        self.telegram = telegram_notifier
        self.kill_switch_triggered = False

        # Mock methods that would be part of the full class
        self.get_positions_pnl = MagicMock()
        self.trigger_kill_switch = MagicMock()
        self.cancel_all_pending_orders = MagicMock()
        self.square_off_all_positions = MagicMock()

    def check_and_manage_risk(self):
        # This is a simplified recreation of the core logic from the main script.
        pnl, position_details = self.get_positions_pnl()

        # Stoploss breached
        if pnl <= self.daily_stoploss:
            if self.telegram:
                kill_switch_enabled = self.config.get("ENABLE_KILL_SWITCH", False)
                self.telegram.send_kill_switch_alert("STOPLOSS", pnl, self.daily_stoploss, kill_switch_enabled)
            
            self.cancel_all_pending_orders()
            self.square_off_all_positions(position_details)
            
            if self.config.get("ENABLE_KILL_SWITCH"):
                kill_switch_result = self.trigger_kill_switch(position_details)
                if kill_switch_result[0]:
                    return ["STOPLOSS_BREACHED", kill_switch_result[1]]
                else:
                    return ["KILL_SWITCH_FAILED", kill_switch_result[1]]
            else:
                self.kill_switch_triggered = True
                return ["STOPLOSS_BREACHED", "Kill switch not enabled"]
        
        # Target achieved
        elif pnl >= self.daily_target:
            if self.telegram:
                kill_switch_enabled = self.config.get("ENABLE_KILL_SWITCH", False)
                self.telegram.send_kill_switch_alert("TARGET", pnl, self.daily_target, kill_switch_enabled)

            self.cancel_all_pending_orders()
            self.square_off_all_positions(position_details)

            if self.config.get("ENABLE_KILL_SWITCH"):
                kill_switch_result = self.trigger_kill_switch(position_details)
                if kill_switch_result[0]:
                    return ["TARGET_ACHIEVED", kill_switch_result[1]]
                else:
                    return ["KILL_SWITCH_FAILED", kill_switch_result[1]]
            else:
                self.kill_switch_triggered = True
                return ["TARGET_ACHIEVED", "Kill switch not enabled"]

        return ["WITHIN_LIMITS", "Success"]


class TestKillSwitchFeature(unittest.TestCase):

    def setUp(self):
        self.mock_telegram = MagicMock()
        self.mock_telegram.send_kill_switch_alert = MagicMock()

    def test_kill_switch_disabled_by_default_on_stoploss(self):
        """Test that kill switch is NOT triggered if ENABLE_KILL_SWITCH is False (default)."""
        config = BASE_CONFIG.copy()
        rm = SimplifiedDhanRiskManager(config, self.mock_telegram)
        rm.get_positions_pnl.return_value = (-1100, [{'data': 'pos1'}]) # Breached SL

        status, reason = rm.check_and_manage_risk()

        # Assert actions
        rm.cancel_all_pending_orders.assert_called_once()
        rm.square_off_all_positions.assert_called_once()
        rm.trigger_kill_switch.assert_not_called()

        # Assert notification
        self.mock_telegram.send_kill_switch_alert.assert_called_with("STOPLOSS", -1100, -1000.0, False)

        # Assert return status
        self.assertEqual(status, "STOPLOSS_BREACHED")
        self.assertEqual(reason, "Kill switch not enabled")

    def test_kill_switch_enabled_and_triggered_on_stoploss(self):
        """Test that kill switch IS triggered if ENABLE_KILL_SWITCH is True."""
        config = BASE_CONFIG.copy()
        config["ENABLE_KILL_SWITCH"] = True
        rm = SimplifiedDhanRiskManager(config, self.mock_telegram)
        
        rm.get_positions_pnl.return_value = (-1100, [{'data': 'pos1'}]) # Breached SL
        rm.trigger_kill_switch.return_value = [True, "activated"]

        status, reason = rm.check_and_manage_risk()

        # Assert actions
        rm.cancel_all_pending_orders.assert_called_once()
        rm.square_off_all_positions.assert_called_once()
        rm.trigger_kill_switch.assert_called_once()

        # Assert notification
        self.mock_telegram.send_kill_switch_alert.assert_called_with("STOPLOSS", -1100, -1000.0, True)

        # Assert return status
        self.assertEqual(status, "STOPLOSS_BREACHED")
        self.assertEqual(reason, "activated")

    def test_kill_switch_enabled_but_fails_on_stoploss(self):
        """Test the behavior when kill switch is enabled but the API call fails."""
        config = BASE_CONFIG.copy()
        config["ENABLE_KILL_SWITCH"] = True
        rm = SimplifiedDhanRiskManager(config, self.mock_telegram)

        rm.get_positions_pnl.return_value = (-1100, [{'data': 'pos1'}]) # Breached SL
        rm.trigger_kill_switch.return_value = [False, "API Error 500"]

        status, reason = rm.check_and_manage_risk()

        # Assert actions
        rm.trigger_kill_switch.assert_called_once()

        # Assert return status
        self.assertEqual(status, "KILL_SWITCH_FAILED")
        self.assertEqual(reason, "API Error 500")

    def test_kill_switch_disabled_by_default_on_target(self):
        """Test that kill switch is NOT triggered for target if ENABLE_KILL_SWITCH is False."""
        config = BASE_CONFIG.copy()
        rm = SimplifiedDhanRiskManager(config, self.mock_telegram)
        rm.get_positions_pnl.return_value = (2100, [{'data': 'pos1'}]) # Breached target

        status, reason = rm.check_and_manage_risk()

        # Assert actions
        rm.trigger_kill_switch.assert_not_called()
        self.mock_telegram.send_kill_switch_alert.assert_called_with("TARGET", 2100, 2000.0, False)
        self.assertEqual(status, "TARGET_ACHIEVED")
        self.assertEqual(reason, "Kill switch not enabled")

    def test_kill_switch_enabled_and_triggered_on_target(self):
        """Test that kill switch IS triggered for target if ENABLE_KILL_SWITCH is True."""
        config = BASE_CONFIG.copy()
        config["ENABLE_KILL_SWITCH"] = True
        rm = SimplifiedDhanRiskManager(config, self.mock_telegram)
        
        rm.get_positions_pnl.return_value = (2100, [{'data': 'pos1'}]) # Breached target
        rm.trigger_kill_switch.return_value = [True, "activated"]

        status, reason = rm.check_and_manage_risk()

        # Assert actions
        rm.trigger_kill_switch.assert_called_once()
        self.mock_telegram.send_kill_switch_alert.assert_called_with("TARGET", 2100, 2000.0, True)
        self.assertEqual(status, "TARGET_ACHIEVED")
        self.assertEqual(reason, "activated")

if __name__ == '__main__':
    unittest.main()
