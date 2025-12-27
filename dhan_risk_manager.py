"""
DhanHQ Automated Risk Management System
Monitors positions PNL and triggers kill switch based on daily limits
"""
from dotenv import load_dotenv
import os
import requests
import schedule
import time
import json
from datetime import datetime
import logging
import sys

# ============================================================================
# CONFIGURATION - UPDATE THESE VALUES
# ============================================================================
load_dotenv()  # Loads variables from .env into environment

def get_dhan_token():
    """Get Access Token from Env, fallback to file if missing"""
    # 1. Try Environment Variable (.env)
    token = os.getenv("DHAN_ACCESS_TOKEN")
    if token and token.strip():
        return token.strip()
    
    # 2. Try Fallback File
    # (Looks for 'dhan_token.txt' in the same folder as this script)
    try:
        script_dir = os.path.dirname(os.path.abspath(__file__))
        token_file = os.path.join(script_dir, "dhan_token.txt")
        
        if os.path.exists(token_file):
            with open(token_file, "r") as f:
                file_token = f.read().strip()
                if file_token:
                    return file_token
    except Exception as e:
        print(f"Warning: Could not read token file: {e}")
        
    return None

CONFIG = {
    "ACCESS_TOKEN": get_dhan_token(),  # Dhan API Access Token
    "DAILY_STOPLOSS": float(os.getenv("DAILY_STOPLOSS")), # Stoploss threshold: negative to trigger on loss, 0 to trigger at breakeven, positive to trigger when in profit
    "DAILY_TARGET": float(os.getenv("DAILY_TARGET")), # Stop if profit reaches this (positive value)
    "CHECK_INTERVAL_SECONDS": int(os.getenv("CHECK_INTERVAL_SECONDS")), # How often to check PNL (in seconds)
    "MARKET_START_TIME": os.getenv("MARKET_START_TIME"), # Market opening time
    "MARKET_END_TIME": os.getenv("MARKET_END_TIME"), # Market closing time
    "ENABLE_LOGGING": True,                     # Save logs to file
    # Read log file path from environment variable `LOG_FILE`, fallback to default name
    "LOG_FILE": os.getenv("LOG_FILE", "/tmp/dhan_risk_manager.log"),       # Log file name
    # Logging level (e.g. DEBUG, INFO, WARN, ERROR). Read from .env via LOG_LEVEL
    "LOG_LEVEL": os.getenv("LOG_LEVEL", "WARN"),
    
    # Telegram Configuration (booleans parsed from env)
    "TELEGRAM_ENABLED": os.getenv("TELEGRAM_ENABLED"),       # Enable Telegram notifications (parsed later)
    "TELEGRAM_BOT_TOKEN": os.getenv("TELEGRAM_BOT_TOKEN"),    # Get from @BotFather
    "TELEGRAM_CHAT_ID": os.getenv("TELEGRAM_CHAT_ID"),        # Your Telegram chat ID
    "SEND_PNL_UPDATES": os.getenv("SEND_PNL_UPDATES"),      # Send PNL on every check (parsed later)
    "SEND_ONLY_ALERTS": os.getenv("SEND_ONLY_ALERTS"),       # Only send stoploss/target alerts (not every check) (parsed later)
    # Per-position percent-based profit taking
    "ENABLE_POSITION_PERCENT_TAKE": os.getenv("ENABLE_POSITION_PERCENT_TAKE"),  # Enable per-position percent take
    "POSITION_PERCENT_TAKE": float(os.getenv("POSITION_PERCENT_TAKE") or 0.0),  # Percent profit threshold per position (e.g., 5.0)
    # Per-position percent-based stoploss
    "ENABLE_POSITION_PERCENT_STOPLOSS": os.getenv("ENABLE_POSITION_PERCENT_STOPLOSS"),  # Enable per-position percent stoploss
    "POSITION_PERCENT_STOPLOSS": float(os.getenv("POSITION_PERCENT_STOPLOSS") or 0.0),  # Percent stoploss threshold per position (positive value, e.g., 2.0 means -2%)
    # Trailing Stoploss Configuration
    "ENABLE_TRAILING_STOPLOSS": os.getenv("ENABLE_TRAILING_STOPLOSS"),  # Enable trailing stoploss feature
    "TRAILING_STOPLOSS_ACTIVATE_PROFIT": float(os.getenv("TRAILING_STOPLOSS_ACTIVATE_PROFIT") or 0.0), # Profit level to activate trailing
    "TRAILING_STOPLOSS_TRAIL_PERCENT": float(os.getenv("TRAILING_STOPLOSS_TRAIL_PERCENT") or 0.0),  # Trail percentage (e.g., 10 for 10%)
    "ENABLE_KILL_SWITCH": os.getenv("ENABLE_KILL_SWITCH"),      # Activate Dhan's kill switch on limit breach
    # Telegram periodic PNL alert interval (seconds). 0 or missing => disabled
    "TELEGRAM_PNL_INTERVAL_SECONDS": int(os.getenv("TELEGRAM_PNL_INTERVAL_SECONDS") or 0),
}


# Helper to parse boolean-ish env values
def _env_to_bool(val, default=False):
    if isinstance(val, bool):
        return val
    if val is None:
        return default
    return str(val).strip().lower() in ("1", "true", "yes", "y", "on")

# Normalize boolean-like config values (overwrite string values with booleans)
CONFIG["TELEGRAM_ENABLED"] = _env_to_bool(CONFIG.get("TELEGRAM_ENABLED"), False)
CONFIG["SEND_PNL_UPDATES"] = _env_to_bool(CONFIG.get("SEND_PNL_UPDATES"), False)
CONFIG["SEND_ONLY_ALERTS"] = _env_to_bool(CONFIG.get("SEND_ONLY_ALERTS"), False)
CONFIG["ENABLE_POSITION_PERCENT_TAKE"] = _env_to_bool(CONFIG.get("ENABLE_POSITION_PERCENT_TAKE"), False)
CONFIG["ENABLE_POSITION_PERCENT_STOPLOSS"] = _env_to_bool(CONFIG.get("ENABLE_POSITION_PERCENT_STOPLOSS"), False)
CONFIG["ENABLE_TRAILING_STOPLOSS"] = _env_to_bool(CONFIG.get("ENABLE_TRAILING_STOPLOSS"), False)
CONFIG["ENABLE_KILL_SWITCH"] = _env_to_bool(CONFIG.get("ENABLE_KILL_SWITCH"), False)

# Normalize log level string to numeric logging level
try:
    _lvl_name = str(CONFIG.get("LOG_LEVEL", "WARN")).strip().upper()
except Exception:
    _lvl_name = "WARN"

_LOG_LEVEL_MAP = {
    'CRITICAL': logging.CRITICAL,
    'FATAL': logging.CRITICAL,
    'ERROR': logging.ERROR,
    'WARN': logging.WARNING,
    'WARNING': logging.WARNING,
    'INFO': logging.INFO,
    'DEBUG': logging.DEBUG,
    'NOTSET': logging.NOTSET
}

CONFIG["LOG_LEVEL_NUM"] = _LOG_LEVEL_MAP.get(_lvl_name, logging.WARNING)

# If periodic Telegram PNL updates are enabled, disable per-check PNL sends to avoid duplicates
if CONFIG.get("TELEGRAM_PNL_INTERVAL_SECONDS", 0) > 0:
    CONFIG["EFFECTIVE_SEND_PNL_UPDATES"] = False
else:
    CONFIG["EFFECTIVE_SEND_PNL_UPDATES"] = CONFIG["SEND_PNL_UPDATES"]

# ============================================================================
# LOGGING SETUP
# ============================================================================

def setup_logging():
    """Setup logging configuration with UTF-8 encoding for Windows compatibility"""
    log_format = '%(asctime)s - %(levelname)s - %(message)s'
    # Create handlers with UTF-8 encoding for Windows compatibility
    root = logging.getLogger()
    # Remove existing handlers to avoid duplicate logs on reload
    for h in list(root.handlers):
        root.removeHandler(h)

    # File handler with UTF-8 encoding (optional)
    if CONFIG.get("ENABLE_LOGGING"):
        try:
            file_handler = logging.FileHandler(CONFIG["LOG_FILE"], encoding='utf-8')
            file_handler.setLevel(CONFIG.get("LOG_LEVEL_NUM", logging.WARNING))
            file_handler.setFormatter(logging.Formatter(log_format))
            root.addHandler(file_handler)
        except Exception:
            # Fallback: skip file handler if it fails to open
            pass

    # Console handler with UTF-8 encoding
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(CONFIG.get("LOG_LEVEL_NUM", logging.WARNING))
    console_handler.setFormatter(logging.Formatter(log_format))
    # Set UTF-8 encoding for console output (Python 3.7+)
    if hasattr(sys.stdout, 'reconfigure'):
        try:
            sys.stdout.reconfigure(encoding='utf-8')
        except Exception:
            pass
    root.addHandler(console_handler)

    # Ensure root logger level is set from config
    root.setLevel(CONFIG.get("LOG_LEVEL_NUM", logging.WARNING))

# ============================================================================
# TELEGRAM NOTIFICATION CLASS
# ============================================================================

class TelegramNotifier:
    def __init__(self, bot_token, chat_id, enabled=True):
        self.bot_token = bot_token
        self.chat_id = chat_id
        self.enabled = enabled
        self.base_url = f"https://api.telegram.org/bot{bot_token}"
        
    def send_message(self, message, parse_mode="HTML"):
        """Send a message via Telegram"""
        if not self.enabled:
            return False
            
        url = f"{self.base_url}/sendMessage"
        payload = {
            "chat_id": self.chat_id,
            "text": message,
            "parse_mode": parse_mode
        }
        
        try:
            response = requests.post(url, json=payload, timeout=10)
            if response.status_code == 200:
                logging.info("✓ Telegram notification sent")
                return True
            else:
                logging.error(f"Failed to send Telegram: {response.status_code} - {response.text}")
                return False
        except Exception as e:
            logging.error(f"Error sending Telegram notification: {e}")
            return False
    
    def send_pnl_update(self, pnl, stoploss, target, positions_data=None):
        """Send PNL update message"""
        # Determine emoji based on PNL
        if pnl > 0:
            emoji = "📈"
            pnl_status = "Profit"
        elif pnl < 0:
            emoji = "📉"
            pnl_status = "Loss"
        else:
            emoji = "➖"
            pnl_status = "Breakeven"
        
        # Calculate distance from limits
        distance_from_sl = ((pnl - stoploss) / abs(stoploss)) * 100 if stoploss != 0 else 0
        distance_from_target = ((target - pnl) / target) * 100 if target != 0 else 0
        
        message = f"""
{emoji} <b>PNL Update</b> {emoji}

💰 <b>Current P&L:</b> ₹{pnl:,.2f} ({pnl_status})

📊 <b>Risk Limits:</b>
   🔴 Stoploss: ₹{stoploss:,.2f} ({distance_from_sl:.1f}% away)
   🟢 Target: ₹{target:,.2f} ({distance_from_target:.1f}% away)

⏰ Time: {datetime.now().strftime('%I:%M:%S %p')}
"""
        
        # Add position details if provided
        if positions_data:
            message += "\n📋 <b>Positions:</b>\n"
            for pos in positions_data[:5]:  # Limit to 5 positions
                pnl_emoji = "🟢" if pos['total'] >= 0 else "🔴"
                message += f"   {pnl_emoji} {pos['symbol']}: ₹{pos['total']:,.2f}\n"
            
            if len(positions_data) > 5:
                message += f"   ... and {len(positions_data) - 5} more\n"
        
        return self.send_message(message)
    
    def send_kill_switch_alert(self, reason, pnl, limit_value, kill_switch_enabled=False):
        """Send kill switch activation alert"""
        if reason == "STOPLOSS":
            emoji = "🚨"
            title = "STOPLOSS BREACHED"
            color = "🔴"
        else:  # TARGET
            emoji = "🎯"
            title = "TARGET ACHIEVED"
            color = "🟢"

        if kill_switch_enabled:
            action_title = "KILL SWITCH ACTIVATING!"
            action_details = """
<b>Actions being taken:</b>
1️⃣ Squaring off all positions
2️⃣ Cancelling all pending orders
3️⃣ Disabling trading for today
"""
        else:
            action_title = "CLOSING POSITIONS"
            action_details = """
<b>Actions being taken:</b>
1️⃣ Squaring off all positions
2️⃣ Cancelling all pending orders

⚠️ <i>Kill Switch activation is disabled.</i>
"""

        message = f"""
{emoji}{emoji}{emoji} <b>{title}</b> {emoji}{emoji}{emoji}

{color} <b>P&L:</b> ₹{pnl:,.2f}
{color} <b>Limit:</b> ₹{limit_value:,.2f}

⚡ <b>{action_title}</b>

{action_details}
⏰ Time: {datetime.now().strftime('%I:%M:%S %p')}
📅 Date: {datetime.now().strftime('%d %B %Y')}

🛑 <b>Shutdown in progress...</b>
"""
        
        return self.send_message(message)
    
    def send_startup_message(self, config):
        """Send script startup notification"""
        message = f"""
🤖 <b>Dhan Risk Manager Started</b>

📊 <b>Configuration:</b>
   🔴 Stoploss: ₹{config['DAILY_STOPLOSS']:,.2f}
   🟢 Target: ₹{config['DAILY_TARGET']:,.2f}
   ⏱ Check Interval: {config['CHECK_INTERVAL_SECONDS']} second(s)
"""
        if config.get("ENABLE_TRAILING_STOPLOSS"):
            message += f"""
   🚀 <b>Trailing SL Enabled</b>
      - Activate at: ₹{config['TRAILING_STOPLOSS_ACTIVATE_PROFIT']:,.2f}
      - Trail by: {config['TRAILING_STOPLOSS_TRAIL_PERCENT']}%
"""
        
        if config.get("ENABLE_KILL_SWITCH"):
            message += """
   ✅ <b>Kill Switch Enabled</b>
"""

        message += f"""
🕐 Market Hours: {config['MARKET_START_TIME']} - {config['MARKET_END_TIME']}

✅ Monitoring active
⏰ Started: {datetime.now().strftime('%I:%M:%S %p')}
"""
        return self.send_message(message)
    
    def send_error_alert(self, error_message):
        """Send error notification"""
        message = f"""
⚠️ <b>Error Alert</b>

❌ {error_message}

⏰ Time: {datetime.now().strftime('%I:%M:%S %p')}

⚠️ Please check the logs or system
"""
        return self.send_message(message)

# ============================================================================
# DHAN API CLASS
# ============================================================================

class DhanRiskManager:
    def __init__(self, config, telegram_notifier=None):
        self.access_token = config["ACCESS_TOKEN"]
        self.daily_stoploss = config["DAILY_STOPLOSS"]
        self.daily_target = config["DAILY_TARGET"]
        self.base_url = "https://api.dhan.co/"
        self.headers = {
            "access-token": self.access_token,
            "Content-Type": "application/json"
        }
        self.kill_switch_triggered = False
        self.telegram = telegram_notifier
        self.dhan_client_id = None  # Will be fetched from positions API
        
    def get_positions_pnl(self):
        """Fetch current positions and calculate total PNL"""
        url = f"{self.base_url}/positions"
        
        try:
            response = requests.get(url, headers=self.headers, timeout=10)
            
            if response.status_code == 200:
                data = response.json()
                
                if not data:
                    logging.info("No open positions found")
                    # Return a consistent tuple: (pnl, position_details)
                    return 0, []
                
                # Extract client ID from first position
                if data and not self.dhan_client_id:
                    self.dhan_client_id = data[0].get('dhanClientId')
                
                total_pnl = 0
                position_details = []
                
                for position in data:
                    realized_pnl = float(position.get('realizedProfit', 0))
                    unrealized_pnl = float(position.get('unrealizedProfit', 0))
                    position_pnl = realized_pnl + unrealized_pnl
                    total_pnl += position_pnl
                    
                    position_details.append({
                        'symbol': position.get('tradingSymbol', 'N/A'),
                        'realized': realized_pnl,
                        'unrealized': unrealized_pnl,
                        'total': position_pnl,
                        'position_data': position  # Store full position data for squaring off
                    })
                
                # Log position details
                logging.info("=" * 70)
                logging.info("CURRENT POSITIONS:")
                for pos in position_details:
                    logging.info(f"  {pos['symbol']}: Realized=₹{pos['realized']:.2f}, "
                               f"Unrealized=₹{pos['unrealized']:.2f}, Total=₹{pos['total']:.2f}")
                logging.info("=" * 70)
                logging.info(f"TOTAL DAY P&L: ₹{total_pnl:.2f}")
                logging.info("=" * 70)
                
                return total_pnl, position_details
                
            elif response.status_code == 401:
                logging.error("Authentication failed. Please check your ACCESS_TOKEN")
                return None, None
            else:
                logging.error(f"Error fetching positions: {response.status_code} - {response.text}")
                return None, None
                
        except requests.exceptions.Timeout:
            logging.error("Request timed out while fetching positions")
            return None, None
        except requests.exceptions.RequestException as e:
            logging.error(f"Network error in get_positions_pnl: {e}")
            return None, None
        except Exception as e:
            logging.error(f"Unexpected error in get_positions_pnl: {e}")
            return None, None
    
    def square_off_all_positions(self, position_details):
        """Square off all open positions by placing opposite orders"""
        if not position_details:
            logging.info("No positions to square off")
            return True
        
        logging.warning("=" * 70)
        logging.warning("SQUARING OFF ALL POSITIONS")
        logging.warning("=" * 70)
        
        squared_off_count = 0
        failed_count = 0
        
        for pos in position_details:
            try:
                position_data = pos['position_data']
                net_qty = int(position_data.get('netQty', 0))
                
                if net_qty == 0:
                    logging.info(f"  ✓ {pos['symbol']}: No net position to square off")
                    continue
                
                # Determine transaction type (opposite of current position)
                transaction_type = "SELL" if net_qty > 0 else "BUY"
                quantity = abs(net_qty)
                
                # Prepare order payload
                order_payload = {
                    "dhanClientId": self.dhan_client_id or position_data.get('dhanClientId'),
                    "transactionType": transaction_type,
                    "exchangeSegment": position_data.get('exchangeSegment'),
                    "productType": position_data.get('productType'),
                    "orderType": "MARKET",
                    "validity": "DAY",
                    "securityId": position_data.get('securityId'),
                    "quantity": str(quantity),
                    "disclosedQuantity": "",
                    "price": "",
                    "triggerPrice": "",
                    "afterMarketOrder": False
                }
                
                # Place square off order
                url = f"{self.base_url}/orders"
                response = requests.post(url, headers=self.headers, json=order_payload, timeout=10)
                
                if response.status_code == 200:
                    result = response.json()
                    logging.warning(f"  ✓ {pos['symbol']}: Squared off {quantity} qty "
                                  f"({transaction_type}) - Order ID: {result.get('orderId')}")
                    squared_off_count += 1
                else:
                    logging.error(f"  ✗ {pos['symbol']}: Failed to square off - {response.text}")
                    failed_count += 1
                    
            except Exception as e:
                logging.error(f"  ✗ {pos['symbol']}: Exception - {e}")
                failed_count += 1
        
        logging.warning("=" * 70)
        logging.warning(f"Square Off Summary: {squared_off_count} successful, {failed_count} failed")
        logging.warning("=" * 70)
        
        return failed_count == 0

    def square_off_position(self, pos):
        """Square off a single position by placing an opposite market order."""
        try:
            position_data = pos['position_data']
            net_qty = int(position_data.get('netQty', 0))

            if net_qty == 0:
                logging.info(f"  ✓ {pos['symbol']}: No net position to square off")
                return True

            transaction_type = "SELL" if net_qty > 0 else "BUY"
            quantity = abs(net_qty)

            order_payload = {
                "dhanClientId": self.dhan_client_id or position_data.get('dhanClientId'),
                "transactionType": transaction_type,
                "exchangeSegment": position_data.get('exchangeSegment'),
                "productType": position_data.get('productType'),
                "orderType": "MARKET",
                "validity": "DAY",
                "securityId": position_data.get('securityId'),
                "quantity": str(quantity),
                "disclosedQuantity": "",
                "price": "",
                "triggerPrice": "",
                "afterMarketOrder": False
            }

            url = f"{self.base_url}/orders"
            response = requests.post(url, headers=self.headers, json=order_payload, timeout=10)

            if response.status_code == 200:
                result = response.json()
                logging.warning(f"  ✓ {pos['symbol']}: Squared off {quantity} qty ({transaction_type}) - Order ID: {result.get('orderId')}")
                return True
            else:
                logging.error(f"  ✗ {pos['symbol']}: Failed to square off - {response.text}")
                return False

        except Exception as e:
            logging.error(f"  ✗ {pos['symbol']}: Exception during square off - {e}")
            return False
    
    def cancel_all_pending_orders(self):
        """Cancel all pending orders"""
        logging.warning("=" * 70)
        logging.warning("CANCELLING ALL PENDING ORDERS")
        logging.warning("=" * 70)
        
        try:
            # Get all orders
            url = f"{self.base_url}/orders"
            response = requests.get(url, headers=self.headers, timeout=10)
            
            if response.status_code != 200:
                logging.error(f"Failed to fetch orders: {response.text}")
                return False
            
            orders = response.json()
            
            if not orders:
                logging.info("  No pending orders found")
                return True
            
            # Filter pending orders
            pending_orders = [
                order for order in orders 
                if order.get('orderStatus') in ['PENDING', 'TRANSIT']
            ]
            
            if not pending_orders:
                logging.info("  No pending orders to cancel")
                return True
            
            cancelled_count = 0
            failed_count = 0
            
            for order in pending_orders:
                try:
                    order_id = order.get('orderId')
                    symbol = order.get('tradingSymbol', 'N/A')
                    
                    # Cancel order
                    cancel_url = f"{self.base_url}/orders/{order_id}"
                    cancel_response = requests.delete(cancel_url, headers=self.headers, timeout=10)
                    
                    if cancel_response.status_code == 200:
                        logging.warning(f"  ✓ Cancelled: {symbol} - Order ID: {order_id}")
                        cancelled_count += 1
                    else:
                        logging.error(f"  ✗ Failed to cancel: {symbol} - {cancel_response.text}")
                        failed_count += 1
                        
                except Exception as e:
                    logging.error(f"  ✗ Exception cancelling order {order_id}: {e}")
                    failed_count += 1
            
            logging.warning("=" * 70)
            logging.warning(f"Cancellation Summary: {cancelled_count} successful, {failed_count} failed")
            logging.warning("=" * 70)
            
            return failed_count == 0
            
        except Exception as e:
            logging.error(f"Exception in cancel_all_pending_orders: {e}")
            return False
    
    def trigger_kill_switch(self, position_details):
        """Trigger the kill switch to disable trading for the day"""
        # Note: Kill Switch requires all positions to be closed and no pending orders
        # It only disables trading, doesn't automatically square off positions
        url = f"{self.base_url}/killSwitch"
        
        # Add query parameter for activation
        params = {"killSwitchStatus": "ACTIVATE"}
        
        try:
            logging.warning("🔴 INITIATING KILL SWITCH... 🔴")
            logging.warning("Note: Ensure all positions are closed and no pending orders exist")
            
            response = requests.post(url, headers=self.headers, params=params, timeout=10)
            
            if response.status_code == 200:
                result = response.json()
                client_id = result.get('dhanClientId', 'N/A')
                kill_switch_status = result.get('killSwitchStatus', 'N/A')
                logging.warning("=" * 70)
                logging.warning("=" * 70)
                if "activated" in str.lower(kill_switch_status):
                    logging.warning("🔴 KILL SWITCH ACTIVATED SUCCESSFULLY! 🔴")
                    logging.warning("Trading disabled for the current trading day")
                    logging.warning(f"Client ID: {client_id}")
                    logging.warning(f"Status: {kill_switch_status}")
                    self.kill_switch_triggered = True
                    return [True, kill_switch_status]
                else:
                    logging.error(f"Kill switch activation failed: {kill_switch_status}")
                    logging.error(f"Client ID: {client_id}")
                    logging.error(f"Status: {kill_switch_status}")
                    return [False, kill_switch_status]
            else:
                logging.error(f"Failed to trigger kill switch: {response.status_code}")
                logging.error(f"Response: {response.text}")
                return [False, response.text]

        except requests.exceptions.Timeout:
            logging.error("Request timed out while triggering kill switch")
            return [False, "Request timed out"]
        except Exception as e:
            logging.error(f"Exception in trigger_kill_switch: {e}")
            return [False, str(e)]
    
    def check_and_manage_risk(self):
        """Check PNL against limits and trigger kill switch if breached"""
        
        if self.kill_switch_triggered:
            logging.info("Kill switch already triggered. Skipping check.")
            return ["KILL_SWITCH_ACTIVE", "Success"]
        
        result = self.get_positions_pnl()
        
        if result[0] is None:
            logging.warning("Could not fetch PNL. Skipping risk check.")
            if self.telegram:
                self.telegram.send_error_alert("Failed to fetch PNL data from Dhan API")
            return ["ERROR", "Failed to fetch PNL"]
        
        pnl, position_details = result
        
        logging.info(f"Risk Check: P&L=₹{pnl:.2f} | "
                    f"Stoploss=₹{self.daily_stoploss:.2f} | "
                    f"Target=₹{self.daily_target:.2f}")

        # Trailing Stoploss Logic
        if CONFIG.get("ENABLE_TRAILING_STOPLOSS") and pnl > 0:
            activation_profit = float(CONFIG.get("TRAILING_STOPLOSS_ACTIVATE_PROFIT", 0.0))
            trail_percent = float(CONFIG.get("TRAILING_STOPLOSS_TRAIL_PERCENT", 0.0))

            if activation_profit > 0 and trail_percent > 0 and pnl >= activation_profit:
                # Calculate new potential stoploss
                new_trailing_stoploss = pnl * (1 - (trail_percent / 100))

                # Stoploss should only move up
                if new_trailing_stoploss > self.daily_stoploss:
                    old_sl = self.daily_stoploss
                    self.daily_stoploss = new_trailing_stoploss
                    logging.warning(f"🚀 TRAILING STOPLOSS UPDATED: New SL=₹{self.daily_stoploss:.2f} (was ₹{old_sl:.2f}) | Current PNL=₹{pnl:.2f}")
                    
                    # Notify via Telegram
                    if self.telegram:
                        try:
                            msg = f"🚀 <b>Trailing Stoploss Updated</b>\n\nNew SL: ₹{self.daily_stoploss:,.2f}\nPNL: ₹{pnl:,.2f}"
                            self.telegram.send_message(msg)
                        except Exception as e:
                            logging.error(f"Failed to send Telegram trailing SL update: {e}")
        
        # Send PNL update to Telegram if enabled and effective send flag is true.
        if (
            self.telegram
            and CONFIG.get("EFFECTIVE_SEND_PNL_UPDATES", False)
            and not CONFIG["SEND_ONLY_ALERTS"]
        ):
            # Get position details for telegram message
            positions_data = self._get_positions_for_telegram()
            self.telegram.send_pnl_update(pnl, self.daily_stoploss, self.daily_target, positions_data)

        # Per-position percent-based profit-taking
        try:
            if CONFIG.get("ENABLE_POSITION_PERCENT_TAKE") and CONFIG.get("POSITION_PERCENT_TAKE", 0) > 0:
                threshold_pct = float(CONFIG.get("POSITION_PERCENT_TAKE", 0.0))
                logging.info(f"Checking per-position percent-take threshold: {threshold_pct}%")
                positions_to_square = []

                for pos in position_details:
                    pos_data = pos.get('position_data', {})
                    try:
                        net_qty = int(pos_data.get('netQty', 0))
                    except Exception:
                        net_qty = 0

                    if net_qty == 0:
                        continue

                    # Try common average price keys (include Dhan's fields like buyAvg and costPrice)
                    avg_price = None
                    for key in (
                        'averagePrice', 'avgPrice', 'avg_price', 'average_price',
                        'entryPrice', 'entry_price', 'buyAvg', 'costPrice'
                    ):
                        val = pos_data.get(key)
                        if val is not None and val != "":
                            try:
                                avg_price = float(val)
                                break
                            except Exception:
                                continue

                    if not avg_price or avg_price == 0:
                        # Log as INFO so it's visible in normal runs and include position keys for debugging
                        try:
                            keys = list(pos_data.keys())
                        except Exception:
                            keys = None
                        logging.info(f"Skipping percent check for {pos.get('symbol')} due to missing/zero avg price; keys={keys}")
                        continue

                    invested_value = abs(net_qty) * avg_price
                    if invested_value == 0:
                        continue

                    position_pnl = pos.get('total', 0)
                    try:
                        percent = (position_pnl / invested_value) * 100
                    except Exception:
                        percent = 0

                    logging.info(f"{pos.get('symbol')}: P&L=₹{position_pnl:.2f} | Invested=₹{invested_value:.2f} | Percent={percent:.2f}%")
                    # Additional debug info to help troubleshoot live discrepancies
                    try:
                        logging.info(f"  -> position_data keys: {list(pos_data.keys())}")
                    except Exception:
                        logging.info("  -> position_data keys: <unable to list keys>")
                    logging.info(f"  -> avg_price detected: {avg_price}")
                    logging.info(f"  -> net_qty: {net_qty}")
                    logging.info(f"  -> invested_value: {invested_value}")
                    logging.info(f"  -> computed percent: {percent:.4f} | threshold_pct: {threshold_pct}")

                    # Check for profit-taking
                    if percent >= threshold_pct:
                        positions_to_square.append((pos, percent, 'TAKE_PROFIT'))

                    # Check for per-position stoploss (negative percent)
                    stoploss_pct = float(CONFIG.get('POSITION_PERCENT_STOPLOSS', 0.0))
                    if CONFIG.get('ENABLE_POSITION_PERCENT_STOPLOSS') and stoploss_pct > 0:
                        # percent is positive for profit, negative for loss
                        if percent <= -abs(stoploss_pct):
                            positions_to_square.append((pos, percent, 'POSITION_STOPLOSS'))

                # Square off identified positions
                if positions_to_square:
                    for p, pct, reason in positions_to_square:
                        sym = p.get('symbol')
                        if reason == 'TAKE_PROFIT':
                            logging.warning(f"Position percent threshold met for {sym}: {pct:.2f}% >= {threshold_pct}% — squaring off (TAKE PROFIT)")
                        else:
                            logging.warning(f"Position percent stoploss met for {sym}: {pct:.2f}% <= -{stoploss_pct:.2f}% — squaring off (POSITION STOPLOSS)")

                        success = self.square_off_position(p)
                        logging.info(f"  -> square_off_position returned: {success}")

                        # Notify via Telegram (simple message)
                        if self.telegram:
                            try:
                                if reason == 'TAKE_PROFIT':
                                    msg = f"⚡ Per-position profit target reached for <b>{sym}</b> — {pct:.2f}% ≥ {threshold_pct}%\nSquaring off {abs(int(p['position_data'].get('netQty',0)))} qty."
                                else:
                                    msg = f"⚠️ Per-position stoploss triggered for <b>{sym}</b> — {pct:.2f}% ≤ -{stoploss_pct:.2f}%\nSquaring off {abs(int(p['position_data'].get('netQty',0)))} qty."
                                self.telegram.send_message(msg)
                            except Exception as e:
                                logging.error(f"Failed to send Telegram per-position message: {e}")

        except Exception as e:
            logging.error(f"Error during per-position percent checks: {e}")
        
        # Check if stoploss is breached
        if pnl <= self.daily_stoploss:
            logging.warning(f"⚠️  STOPLOSS BREACHED! P&L (₹{pnl:.2f}) <= Stoploss (₹{self.daily_stoploss:.2f})")
            
            # Send Telegram alert before taking action
            if self.telegram:
                try:
                    kill_switch_enabled = CONFIG.get("ENABLE_KILL_SWITCH", False)
                    logging.info("Attempting to send Telegram alert (STOPLOSS)")
                    sent = self.telegram.send_kill_switch_alert("STOPLOSS", pnl, self.daily_stoploss, kill_switch_enabled)
                    logging.info(f"Telegram alert (STOPLOSS) sent: {sent}")
                except Exception as e:
                    logging.error(f"Exception while sending Telegram alert: {e}")
            
            self.cancel_all_pending_orders()
            self.square_off_all_positions(position_details)
            
            # Conditionally trigger kill switch
            if CONFIG.get("ENABLE_KILL_SWITCH"):
                kill_switch_result = self.trigger_kill_switch(position_details)
                if kill_switch_result[0]:
                    # Send confirmation that kill switch was activated
                    if self.telegram:
                        try:
                            logging.info("Sending Telegram confirmation: kill-switch ACTIVATED (STOPLOSS)")
                            conf_msg = f"🔴 <b>Kill Switch Activated</b> (STOPLOSS)\nP&L: ₹{pnl:,.2f}\nStatus: {kill_switch_result[1]}"
                            self.telegram.send_message(conf_msg)
                        except Exception as e:
                            logging.error(f"Failed to send kill-switch confirmation message: {e}")
                    return ["STOPLOSS_BREACHED", kill_switch_result[1]]
                else:
                    return ["KILL_SWITCH_FAILED", kill_switch_result[1]]
            else:
                logging.warning("Skipping kill switch activation because it is disabled by default.")
                self.kill_switch_triggered = True # Still consider it triggered to stop monitoring
                return ["STOPLOSS_BREACHED", "Kill switch not enabled"]

        # Check if target is achieved
        elif pnl >= self.daily_target:
            logging.warning(f"✅ TARGET ACHIEVED! P&L (₹{pnl:.2f}) >= Target (₹{self.daily_target:.2f})")
            
            # Send Telegram alert before taking action
            if self.telegram:
                try:
                    kill_switch_enabled = CONFIG.get("ENABLE_KILL_SWITCH", False)
                    logging.info("Attempting to send Telegram alert (TARGET)")
                    sent = self.telegram.send_kill_switch_alert("TARGET", pnl, self.daily_target, kill_switch_enabled)
                    logging.info(f"Telegram alert (TARGET) sent: {sent}")
                except Exception as e:
                    logging.error(f"Exception while sending Telegram alert: {e}")

            # Conditionally trigger kill switch
            if CONFIG.get("ENABLE_KILL_SWITCH"):
                kill_switch_result = self.trigger_kill_switch(position_details)
                if kill_switch_result[0]:
                    # Send confirmation that kill switch was activated
                    if self.telegram:
                        try:
                            logging.info("Sending Telegram confirmation: kill-switch ACTIVATED (TARGET)")
                            conf_msg = f"🟢 <b>Kill Switch Activated</b> (TARGET)\nP&L: ₹{pnl:,.2f}\nStatus: {kill_switch_result[1]}"
                            self.telegram.send_message(conf_msg)
                        except Exception as e:
                            logging.error(f"Failed to send kill-switch confirmation message: {e}")
                    return ["TARGET_ACHIEVED", kill_switch_result[1]]
                else:
                    return ["KILL_SWITCH_FAILED", kill_switch_result[1]]
            else:
                logging.warning("Skipping kill switch activation because it is disabled by default.")
                self.kill_switch_triggered = True # Still consider it triggered to stop monitoring
                return ["TARGET_ACHIEVED", "Kill switch not enabled"]

        else:
            logging.info(f"✓ Within limits. Continue trading.")
            return ["WITHIN_LIMITS", "Success"]

    def _get_positions_for_telegram(self):
        """Helper method to get position data for Telegram messages"""
        url = f"{self.base_url}/positions"
        
        try:
            response = requests.get(url, headers=self.headers, timeout=10)
            
            if response.status_code == 200:
                data = response.json()
                positions = []
                
                for position in data:
                    realized_pnl = float(position.get('realizedProfit', 0))
                    unrealized_pnl = float(position.get('unrealizedProfit', 0))
                    positions.append({
                        'symbol': position.get('tradingSymbol', 'N/A'),
                        'realized': realized_pnl,
                        'unrealized': unrealized_pnl,
                        'total': realized_pnl + unrealized_pnl
                    })
                
                return positions
            else:
                return None
        except Exception as e:
            logging.error(f"Error fetching positions for Telegram: {e}")
            return None

# ============================================================================
# MARKET HOURS CHECK
# ============================================================================

def is_market_hours():
    """Check if current time is within market hours"""
    now = datetime.now().time()
    start_time = datetime.strptime(CONFIG["MARKET_START_TIME"], "%H:%M").time()
    end_time = datetime.strptime(CONFIG["MARKET_END_TIME"], "%H:%M").time()
    
    # Check if today is a weekday (Monday=0, Sunday=6)
    # is_weekday = datetime.now().weekday() < 5

    # OR allow on all days
    is_weekday = True
    
    return is_weekday and start_time <= now <= end_time

# ============================================================================
# MONITORING FUNCTION
# ============================================================================

risk_manager = None
telegram_notifier = None

def monitor_risk():
    """Main monitoring function called by scheduler"""
    global risk_manager, telegram_notifier
    
    if not is_market_hours():
        logging.info("Outside market hours. Skipping check.")
        return
    
    if risk_manager is None:
        # Initialize Telegram notifier if enabled
        if CONFIG["TELEGRAM_ENABLED"]:
            telegram_notifier = TelegramNotifier(
                bot_token=CONFIG["TELEGRAM_BOT_TOKEN"],
                chat_id=CONFIG["TELEGRAM_CHAT_ID"],
                enabled=True
            )
        
        risk_manager = DhanRiskManager(CONFIG, telegram_notifier)
    
    logging.info("\n" + "=" * 70)
    logging.info(f"PNL CHECK at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    logging.info("=" * 70)
    
    status = risk_manager.check_and_manage_risk()
    
    # Stop monitoring if kill switch was triggered
    if status[0] in ["STOPLOSS_BREACHED", "TARGET_ACHIEVED"]:
        logging.warning("\n🛑 STOPPING MONITORING - KILL SWITCH ACTIVATED 🛑")
        logging.warning("Script will continue running but no more checks will be performed")
        logging.warning("You can safely stop the script now (Ctrl+C)")
        # Clear all scheduled jobs (periodic PNL updates and checks)
        try:
            schedule.clear()
            logging.info("Cleared all scheduled jobs due to kill switch activation")
        except Exception as e:
            logging.error(f"Error clearing scheduled jobs: {e}")
        return schedule.CancelJob
    elif status[0] == "KILL_SWITCH_FAILED":
        logging.error(f"Kill switch activation failed! {status[1]}")
        if telegram_notifier:
            telegram_notifier.send_error_alert(f"Kill switch activation FAILED! {status[1]}")


def send_periodic_pnl():
    """Send periodic PNL update via Telegram according to configured interval."""
    global risk_manager, telegram_notifier

    if not CONFIG.get("TELEGRAM_ENABLED"):
        return

    if CONFIG.get("TELEGRAM_PNL_INTERVAL_SECONDS", 0) <= 0:
        return

    if not is_market_hours():
        logging.info("Outside market hours. Skipping Telegram periodic PNL update.")
        return

    # Ensure instances exist
    if risk_manager is None:
        if CONFIG["TELEGRAM_ENABLED"]:
            telegram_notifier = TelegramNotifier(
                bot_token=CONFIG["TELEGRAM_BOT_TOKEN"],
                chat_id=CONFIG["TELEGRAM_CHAT_ID"],
                enabled=True
            )
        risk_manager = DhanRiskManager(CONFIG, telegram_notifier)

    # If kill switch already triggered, cancel further periodic updates
    if risk_manager.kill_switch_triggered:
        logging.info("Kill switch already active — cancelling periodic PNL job")
        return schedule.CancelJob

    result = risk_manager.get_positions_pnl()
    if result is None or result[0] is None:
        logging.warning("Could not fetch PNL for periodic Telegram update.")
        if telegram_notifier:
            telegram_notifier.send_error_alert("Failed to fetch PNL for periodic update")
        return

    pnl, _ = result
    positions_data = risk_manager._get_positions_for_telegram()

    if telegram_notifier:
        telegram_notifier.send_pnl_update(pnl, risk_manager.daily_stoploss, risk_manager.daily_target, positions_data)

# ============================================================================
# MAIN EXECUTION
# ============================================================================

def validate_config():
    """Validate configuration before starting"""
    errors = []
    
    if CONFIG["ACCESS_TOKEN"] == "YOUR_ACCESS_TOKEN_HERE":
        errors.append("ACCESS_TOKEN not configured")
    
    # Allow non-negative DAILY_STOPLOSS to enable kill-switch at breakeven or profit
    if CONFIG.get("DAILY_STOPLOSS") is None:
        errors.append("DAILY_STOPLOSS not configured")

    # Warn if stoploss is >= target — kill-switch may trigger before reaching target
    try:
        if (
            CONFIG.get("DAILY_STOPLOSS") is not None
            and CONFIG.get("DAILY_TARGET") is not None
            and float(CONFIG["DAILY_STOPLOSS"]) >= float(CONFIG["DAILY_TARGET"])
        ):
            logging.warning(
                "Configuration warning: DAILY_STOPLOSS (₹{:.2f}) >= DAILY_TARGET (₹{:.2f}) — kill-switch may trigger before reaching target"
                .format(CONFIG["DAILY_STOPLOSS"], CONFIG["DAILY_TARGET"]) 
            )
    except Exception:
        # If logging not yet configured or values invalid, skip the warning
        pass
    
    if CONFIG["DAILY_TARGET"] <= 0:
        errors.append("DAILY_TARGET must be positive")
    
    if CONFIG["CHECK_INTERVAL_SECONDS"] < 1:
        errors.append("CHECK_INTERVAL_SECONDS must be at least 1")

    # Validate Telegram config if enabled
    if CONFIG["TELEGRAM_ENABLED"]:
        if CONFIG["TELEGRAM_BOT_TOKEN"] == "YOUR_BOT_TOKEN":
            errors.append("TELEGRAM_BOT_TOKEN not configured (Telegram is enabled)")
        
        if CONFIG["TELEGRAM_CHAT_ID"] == "YOUR_CHAT_ID":
            errors.append("TELEGRAM_CHAT_ID not configured (Telegram is enabled)")

    # Validate Trailing Stoploss config if enabled
    if CONFIG["ENABLE_TRAILING_STOPLOSS"]:
        if CONFIG["TRAILING_STOPLOSS_ACTIVATE_PROFIT"] <= 0:
            errors.append("TRAILING_STOPLOSS_ACTIVATE_PROFIT must be positive")
        if not (0 < CONFIG["TRAILING_STOPLOSS_TRAIL_PERCENT"] < 100):
            errors.append("TRAILING_STOPLOSS_TRAIL_PERCENT must be between 0 and 100")
    
    return errors

def main():
    """Main function to start the risk manager"""
    
    # Setup logging
    setup_logging()
    
    logging.info("=" * 70)
    logging.info("DHAN RISK MANAGER - STARTING")
    logging.info("=" * 70)
    
    # Validate configuration
    errors = validate_config()
    if errors:
        logging.error("Configuration errors found:")
        for error in errors:
            logging.error(f"  - {error}")
        logging.error("\nPlease fix the configuration and restart.")
        sys.exit(1)
    
    # Display configuration
    logging.info("\nConfiguration:")
    logging.info(f"  Daily Stoploss: ₹{CONFIG['DAILY_STOPLOSS']:.2f}")
    logging.info(f"  Daily Target: ₹{CONFIG['DAILY_TARGET']:.2f}")
    logging.info(f"  Check Interval: {CONFIG['CHECK_INTERVAL_SECONDS']} second(s)")
    logging.info(f"  Market Hours: {CONFIG['MARKET_START_TIME']} - {CONFIG['MARKET_END_TIME']}")
    logging.info(f"  Log Level: {CONFIG.get('LOG_LEVEL', 'WARN')} ({CONFIG.get('LOG_LEVEL_NUM')})")
    logging.info(f"  Trailing Stoploss: {'Enabled' if CONFIG['ENABLE_TRAILING_STOPLOSS'] else 'Disabled'}")
    if CONFIG['ENABLE_TRAILING_STOPLOSS']:
        logging.info(f"    - Activate at Profit > ₹{CONFIG['TRAILING_STOPLOSS_ACTIVATE_PROFIT']:.2f}")
        logging.info(f"    - Trail Percentage: {CONFIG['TRAILING_STOPLOSS_TRAIL_PERCENT']}%")
    logging.info(f"  Kill Switch Activation: {'Enabled' if CONFIG['ENABLE_KILL_SWITCH'] else 'Disabled (Default)'}")
    logging.info(f"  Telegram Alerts: {'Enabled' if CONFIG['TELEGRAM_ENABLED'] else 'Disabled'}")
    if CONFIG['TELEGRAM_ENABLED']:
        logging.info(f"    - Send PNL Updates (env): {CONFIG['SEND_PNL_UPDATES']}")
        logging.info(f"    - Send PNL Updates (effective): {CONFIG.get('EFFECTIVE_SEND_PNL_UPDATES', False)}")
        logging.info(f"    - Only Alerts Mode: {CONFIG['SEND_ONLY_ALERTS']}")
        if CONFIG.get('TELEGRAM_PNL_INTERVAL_SECONDS', 0) > 0:
            logging.info(f"    - Periodic PNL interval: {CONFIG['TELEGRAM_PNL_INTERVAL_SECONDS']} second(s) (per-check PNL disabled)")
    logging.info("=" * 70)
    
    # Initialize Telegram and send startup message
    if CONFIG["TELEGRAM_ENABLED"]:
        telegram = TelegramNotifier(
            bot_token=CONFIG["TELEGRAM_BOT_TOKEN"],
            chat_id=CONFIG["TELEGRAM_CHAT_ID"],
            enabled=True
        )
        logging.info("\nSending Telegram startup notification...")
        telegram.send_startup_message(CONFIG)
    
    # Initial check
    logging.info("\nPerforming initial PNL check...")
    monitor_risk()
    
    # Schedule periodic checks
    logging.info(f"\nScheduling checks every {CONFIG['CHECK_INTERVAL_SECONDS']} second(s)")
    logging.info("Press Ctrl+C to stop\n")

    schedule.every(CONFIG["CHECK_INTERVAL_SECONDS"]).seconds.do(monitor_risk)

    # Schedule periodic Telegram PNL updates if enabled and interval > 0
    if CONFIG.get("TELEGRAM_ENABLED") and CONFIG.get("TELEGRAM_PNL_INTERVAL_SECONDS", 0) > 0:
        logging.info(f"Scheduling Telegram PNL updates every {CONFIG['TELEGRAM_PNL_INTERVAL_SECONDS']} second(s)")
        schedule.every(CONFIG["TELEGRAM_PNL_INTERVAL_SECONDS"]).seconds.do(send_periodic_pnl)

    try:
        while True:
            schedule.run_pending()
            time.sleep(1)
    except KeyboardInterrupt:
        logging.info("\n\n🛑 Script stopped by user")
        logging.info("=" * 70)
        sys.exit(0)

if __name__ == "__main__":
    main()