# dhan

Dhan broker related scripts for risk management.

## Features

*   **Daily Stoploss/Target:** Automatically stops trading for the day if your total Profit & Loss (PNL) hits a predefined stoploss or target.
*   **Kill Switch:** Automatically trigger Dhan's Kill Switch feature if your loss limit is breached.
*   **Telegram Notifications:** Get real-time updates on your PNL and alerts on your Telegram.
*   **Per position Target:** (Experimental) Close position when % target is hit.
*   **Per position Stoploss:** (Experimental) Close position when % stoploss is hit.
*   **Trailing Stoploss:** (Experimental) Trail your profits to lock in gains.

## Getting Started

Follow these instructions to get the risk manager up and running.

### Prerequisites

*   Python 3.6+
*   A Dhan account with API access enabled
*   Dhan HQ API Access Token with 24 hrs validity

### Installation & Deployment

1.  **Clone the repository:**
    ```bash
    git clone https://github.com/botjockie-lab/dhan.git
    cd dhan
    ```

2.  **Create a virtual environment (recommended):**
    ```bash
    python3 -m venv venv
    source venv/bin/activate  # On Windows use `venv\Scripts\activate`
    ```

3.  **Install the required dependencies:**
    ```bash
    pip install -r requirements.txt
    ```

4.  **Configure your environment:**
    *   Rename the `.env.example` file to `.env`.
    ```bash
    cp .env.example .env
    ```
    *   Edit the `.env` file and fill in your Dhan Access Token and other settings.
    ```bash
    vi .env
    ```
    *   Hint: In vi editor, press i to activate edit mode, Esc + :wq to save and quit or :q! to quit without saving.


5.  **Run the risk manager:**
    ```bash
    python dhan_risk_manager.py
    ```

6.  **Check the script logs to see if its running without errors:**
    ```bash
        tail -f dhan_risk_manager.log
    ```

7.  **Check Telegram messages from your bot** 
    `only if TELEGRAM_ENABLED=True and TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID are set in .env file.`

## Configuration

All configuration is done via the `.env` file.

| Variable                        | Description                                                                                             | Default     |
| ------------------------------- | ------------------------------------------------------------------------------------------------------- | ----------- |
| `DHAN_ACCESS_TOKEN`             | Your Dhan HQ API access token.                                                                          | `""`        |
| `DAILY_STOPLOSS`                | PNL threshold to stop trading for the day (negative value).                                             | `-5000`     |
| `DAILY_TARGET`                  | PNL target to stop trading for the day.                                                                 | `10000`     |
| `CHECK_INTERVAL_SECONDS`        | How often (in seconds) to check the PNL.                                                                | `1`         |
| `MARKET_START_TIME`             | Market start time (24h format HH:MM). The script will be active after this time.                         | `09:15`     |
| `MARKET_END_TIME`               | Market end time (24h format HH:MM). The script will stop after this time.                                 | `15:30`     |
| `ENABLE_POSITION_PERCENT_TAKE`  | Enable/disable taking profit for individual positions at a certain percentage.                          | `False`     |
| `POSITION_PERCENT_TAKE`         | The percentage gain at which to take profit for a position.                                             | `5.0`       |
| `ENABLE_POSITION_PERCENT_STOPLOSS`| Enable/disable stoploss for individual positions at a certain percentage.                               | `False`     |
| `POSITION_PERCENT_STOPLOSS`     | The percentage loss at which to exit a position.                                                        | `2.0`       |
| `ENABLE_TRAILING_STOPLOSS`      | Enable/disable trailing stoploss for overall PNL.                                                       | `False`     |
| `TRAILING_STOPLOSS_ACTIVATE_PROFIT` | The profit level at which to activate the trailing stoploss.                                            | `1000`      |
| `TRAILING_STOPLOSS_TRAIL_PERCENT` | The percentage of profit to trail.                                                                      | `10`        |
| `ENABLE_KILL_SWITCH`            | If `True`, will trigger Dhan's Kill Switch API when `DAILY_STOPLOSS` is breached.                       | `False`     |
| `LOG_LEVEL`                     | The level of logging detail (`INFO`, `DEBUG`, `WARNING`, `ERROR`).                                      | `INFO`      |
| `TELEGRAM_ENABLED`              | Set to `True` to enable Telegram notifications.                                                         | `False`     |
| `TELEGRAM_BOT_TOKEN`            | Your Telegram Bot Token.                                                                                | `""`        |
| `TELEGRAM_CHAT_ID`              | Your Telegram Chat ID.                                                                                  | `""`        |
| `SEND_PNL_UPDATES`              | Set to `True` to receive PNL updates at every `CHECK_INTERVAL_SECONDS`. Can be noisy.                     | `False`     |
| `TELEGRAM_PNL_INTERVAL_SECONDS` | If `SEND_PNL_UPDATES` is `True`, sends a summary PNL update at this interval (in seconds).             | `600`       |
| `SEND_ONLY_ALERTS`              | If `True`, only sends notifications for breached limits or trades, not regular PNL updates.               | `True`      |


## Disclaimer

This script is for educational purposes only. Use it at your own risk. The author is not responsible for any financial losses.