# NB Power for Home Assistant

A custom integration that logs in to [NB Power’s](https://nbpower.com) customer portal and retrieves your energy usage and billing data for display in Home Assistant.

This integration was built for NB Power customers in New Brunswick, Canada and provides live access to the same data you see in the NB Power web dashboard — including month-to-date usage, cost, and projected bill.

---

## ✨ Features

- 🔐 Secure login to your NB Power online account
- ⚡ Fetches energy data directly from NB Power’s Widget API
- 📊 Captures 15-minute, hourly, daily, and monthly history for both kWh and $ in a local cache — the API is only asked for days you don’t already have
- 📅 Exposes sensors for:
  - **Month-to-date kWh**
  - **Month-to-date cost**
  - **Projected monthly bill**
  - **Projected kWh**
  - **15-minute, hourly, daily, and monthly usage series (kWh & $) for Lovelace graphs**
- 🃏 Ships with a Lovelace dashboard card (`lovelace/nbpower-card.yaml`) that recreates NB Power’s charts
- 🕒 Data automatically refreshed on a configurable interval (default 5 min)

---

## 🧩 Installation

### Option 1 — HACS (recommended)
1. In Home Assistant → **HACS → Integrations → ⋮ → Custom repositories**
2. Add this repository URL: `https://github.com/noslent/nbpower-ha`
   Category: **Integration**
3. Install **NB Power**
4. Restart Home Assistant

### Option 2 — Manual
Copy this folder to your configuration directory:
```
custom_components/nbpower/
```
Then restart Home Assistant.

---

## ⚙️ Configuration

1. In Home Assistant go to **Settings → Devices & Services**.
2. Click **Add Integration** and search for **NB Power**.
3. Enter your NB Power username and password when prompted.
4. Home Assistant will create the integration entry and add the sensors automatically.

If you previously configured NB Power via `configuration.yaml`, you can safely remove that YAML. When the integration loads it will prompt you to migrate the entry into the UI-based flow.

After setup the following entities will appear:

| Entity ID | Description | Units |
|------------|-------------|-------|
| `sensor.nb_power_mtd_energy` | Energy used this month | kWh |
| `sensor.nb_power_mtd_cost` | Cost so far this month | $ |
| `sensor.nb_power_projected_bill` | Projected end-of-month bill | $ |
| `sensor.nb_power_projected_kwh` | Projected monthly usage | kWh |
| `sensor.nb_power_15_minute_energy_series` | 15-minute kWh dataset (attributes contain the series) | — |
| `sensor.nb_power_15_minute_cost_series` | 15-minute $ dataset | — |
| `sensor.nb_power_hourly_energy_series` | Hourly kWh dataset | — |
| `sensor.nb_power_hourly_cost_series` | Hourly $ dataset | — |
| `sensor.nb_power_daily_energy_series` | Daily kWh dataset | — |
| `sensor.nb_power_daily_cost_series` | Daily $ dataset | — |
| `sensor.nb_power_monthly_energy_series` | Monthly kWh dataset | — |
| `sensor.nb_power_monthly_cost_series` | Monthly $ dataset | — |

> ℹ️ The most recent day’s totals are derived from the daily dataset and exposed in the `previous_day` attribute on every sensor.

> ℹ️ Each dataset sensor also has a companion entity with a `Statistics` suffix. These entities backfill Home Assistant's long-term statistics database without altering the primary sensor history.

> ℹ️ NB Power typically releases 15-minute interval data 24–48 hours after it is collected. The integration automatically looks
> back up to three days to find the latest available dataset.

---

## 📈 Lovelace Card

A ready-to-use Lovelace stack is included at [`lovelace/nbpower-card.yaml`](lovelace/nbpower-card.yaml). Import it as a manual dashboard or copy the cards into your existing view. The card expects the dataset sensors listed above and uses `custom:apexcharts-card` to plot the kWh and $ history side-by-side.

## 🧠 How it Works

The component logs into `nbpower.com`, collects session cookies, and calls the NB Power **WidgetAPI** endpoints (`VerifyToken`, `GetMultiMeter`, `GetUsageGeneration`).

Month-to-date values come from the `getTentativeData` block. Usage history is stored locally in Home Assistant’s storage directory, organised by WidgetAPI mode:

- **Mi** → 15-minute intervals
- **H** → Hourly totals
- **D** → Daily totals
- **M** → Monthly totals

Before requesting new data the integration checks the cache and only calls the API for days or months that are missing. This avoids repeatedly downloading the same history while still picking up newly released intervals as they appear (usually 24–48 hours later). The daily dataset also feeds the `previous_day` attribute so “yesterday” never shows `unavailable`.

---

## 🧑‍💻 Development

- Requires Home Assistant 2024.6 or newer  
- Written in Python 3.11+  
- Uses `aiohttp`, `async_timeout`, and `beautifulsoup4`

To contribute:
```bash
git clone https://github.com/noslent/nbpower-ha
cd nbpower-ha
```
