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

CONFIG = {
    "ACCESS_TOKEN": os.getenv("DHAN_ACCESS_TOKEN"),
    "DAILY_STOPLOSS": float(os.getenv("DAILY_STOPLOSS")), # Stop if loss reaches this (negative value)
    "DAILY_TARGET": float(os.getenv("DAILY_TARGET")), # Stop if profit reaches this (positive value)
    "CHECK_INTERVAL_SECONDS": int(os.getenv("CHECK_INTERVAL_SECONDS")), # How often to check PNL (in seconds)
    "MARKET_START_TIME": os.getenv("MARKET_START_TIME"), # Market opening time
    "MARKET_END_TIME": os.getenv("MARKET_END_TIME"), # Market closing time
    "ENABLE_LOGGING": True,                     # Save logs to file
    "LOG_FILE": "dhan_risk_manager.log",       # Log file name
    
    # Telegram Configuration
    "TELEGRAM_ENABLED": os.getenv("TELEGRAM_ENABLED"),       # Enable Telegram notifications
    "TELEGRAM_BOT_TOKEN": os.getenv("TELEGRAM_BOT_TOKEN"),    # Get from @BotFather
    "TELEGRAM_CHAT_ID": os.getenv("TELEGRAM_CHAT_ID"),        # Your Telegram chat ID
    "SEND_PNL_UPDATES": os.getenv("SEND_PNL_UPDATES"),      # Send PNL on every check
    "SEND_ONLY_ALERTS": os.getenv("SEND_ONLY_ALERTS"),       # Only send stoploss/target alerts (not every check)
}

# ============================================================================
# LOGGING SETUP
# ============================================================================

def setup_logging():
    """Setup logging configuration with UTF-8 encoding for Windows compatibility"""
    log_format = '%(asctime)s - %(levelname)s - %(message)s'
    
    # Create handlers with UTF-8 encoding for Windows compatibility
    handlers = []
    
    if CONFIG["ENABLE_LOGGING"]:
        # File handler with UTF-8 encoding
        file_handler = logging.FileHandler(CONFIG["LOG_FILE"], encoding='utf-8')
        file_handler.setFormatter(logging.Formatter(log_format))
        handlers.append(file_handler)
    
    # Console handler with UTF-8 encoding
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(logging.Formatter(log_format))
    # Set UTF-8 encoding for console output (Python 3.7+)
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
    handlers.append(console_handler)
    
    logging.basicConfig(
        level=logging.INFO,
        format=log_format,
        handlers=handlers
    )

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
    
    def send_kill_switch_alert(self, reason, pnl, limit_value):
        """Send kill switch activation alert"""
        if reason == "STOPLOSS":
            emoji = "🚨"
            title = "STOPLOSS BREACHED"
            color = "🔴"
        else:  # TARGET
            emoji = "🎯"
            title = "TARGET ACHIEVED"
            color = "🟢"
        
        message = f"""
{emoji}{emoji}{emoji} <b>{title}</b> {emoji}{emoji}{emoji}

{color} <b>P&L:</b> ₹{pnl:,.2f}
{color} <b>Limit:</b> ₹{limit_value:,.2f}

⚡ <b>KILL SWITCH ACTIVATING!</b>

<b>Actions being taken:</b>
1️⃣ Squaring off all positions
2️⃣ Cancelling all pending orders
3️⃣ Disabling trading for today

⏰ Time: {datetime.now().strftime('%I:%M:%S %p')}
📅 Date: {datetime.now().strftime('%d %B %Y')}

🛑 <b>Complete shutdown in progress...</b>
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
                    return 0
                
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
                if kill_switch_status == "ACTIVATED":
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
        
        # Send PNL update to Telegram if enabled
        if self.telegram and CONFIG["SEND_PNL_UPDATES"] and not CONFIG["SEND_ONLY_ALERTS"]:
            # Get position details for telegram message
            positions_data = self._get_positions_for_telegram()
            self.telegram.send_pnl_update(pnl, self.daily_stoploss, self.daily_target, positions_data)
        
        # Check if stoploss is breached
        if pnl <= self.daily_stoploss:
            logging.warning(f"⚠️  STOPLOSS BREACHED! P&L (₹{pnl:.2f}) <= Stoploss (₹{self.daily_stoploss:.2f})")
            
            # Send Telegram alert before kill switch
            if self.telegram:
                self.telegram.send_kill_switch_alert("STOPLOSS", pnl, self.daily_stoploss)
            self.cancel_all_pending_orders()
            self.square_off_all_positions(position_details)
            kill_switch_result = self.trigger_kill_switch(position_details)
            if kill_switch_result[0]:
                return ["STOPLOSS_BREACHED", kill_switch_result[1]]
            else:
                return ["KILL_SWITCH_FAILED", kill_switch_result[1]]

        # Check if target is achieved
        elif pnl >= self.daily_target:
            logging.warning(f"✅ TARGET ACHIEVED! P&L (₹{pnl:.2f}) >= Target (₹{self.daily_target:.2f})")
            
            # Send Telegram alert before kill switch
            if self.telegram:
                self.telegram.send_kill_switch_alert("TARGET", pnl, self.daily_target)
            kill_switch_result = self.trigger_kill_switch(position_details)
            if kill_switch_result[0]:
                return ["TARGET_ACHIEVED", kill_switch_result[1]]
            else:
                return ["KILL_SWITCH_FAILED", kill_switch_result[1]]

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
    is_weekday = datetime.now().weekday() < 5
    
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
        return schedule.CancelJob
    elif status[0] == "KILL_SWITCH_FAILED":
        logging.error(f"Kill switch activation failed! {status[1]}")
        if telegram_notifier:
            telegram_notifier.send_error_alert(f"Kill switch activation FAILED! {status[1]}")

# ============================================================================
# MAIN EXECUTION
# ============================================================================

def validate_config():
    """Validate configuration before starting"""
    errors = []
    
    if CONFIG["ACCESS_TOKEN"] == "YOUR_ACCESS_TOKEN_HERE":
        errors.append("ACCESS_TOKEN not configured")
    
    if CONFIG["DAILY_STOPLOSS"] >= 0:
        errors.append("DAILY_STOPLOSS must be negative")
    
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
    logging.info(f"  Telegram Alerts: {'Enabled' if CONFIG['TELEGRAM_ENABLED'] else 'Disabled'}")
    if CONFIG['TELEGRAM_ENABLED']:
        logging.info(f"    - Send PNL Updates: {CONFIG['SEND_PNL_UPDATES']}")
        logging.info(f"    - Only Alerts Mode: {CONFIG['SEND_ONLY_ALERTS']}")
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