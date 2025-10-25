from __future__ import annotations

from homeassistant.const import CONF_SCAN_INTERVAL

DOMAIN = "nbpower"
DEFAULT_SCAN_INTERVAL = 86400  # seconds
MIN_SCAN_INTERVAL = 3600  # seconds

CONF_ACCOUNT_NUMBER = "account_number"
CONF_UTILITY_ACCOUNT_NUMBER = "utility_account_number"
CONF_METER_NUMBER = "meter_number"

USAGE_SENSOR_KEYS: dict[tuple[str, str], str] = {
    ("Mi", "K"): "usage_15min_kwh",
    ("Mi", "D"): "usage_15min_dollars",
    ("H", "K"): "usage_hourly_kwh",
    ("H", "D"): "usage_hourly_dollars",
    ("D", "K"): "usage_daily_kwh",
    ("D", "D"): "usage_daily_dollars",
    ("M", "K"): "usage_monthly_kwh",
    ("M", "D"): "usage_monthly_dollars",
}

__all__ = [
    "CONF_ACCOUNT_NUMBER",
    "CONF_METER_NUMBER",
    "CONF_SCAN_INTERVAL",
    "CONF_UTILITY_ACCOUNT_NUMBER",
    "DEFAULT_SCAN_INTERVAL",
    "DOMAIN",
    "MIN_SCAN_INTERVAL",
    "USAGE_SENSOR_KEYS",
]
BASE = "https://nbpower.com"
WIDGET_API = "https://nbp-svc.smartcmobile.com/WidgetAPI"
