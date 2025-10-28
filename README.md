# NB Power for Home Assistant

A custom integration that logs in to [NB Power’s](https://nbpower.com) customer portal and retrieves your energy usage and billing data for display in Home Assistant.

This integration was built for NB Power customers in New Brunswick, Canada and provides live access to the same data you see in the NB Power web dashboard — including month-to-date usage, cost, and projected bill.

---

## ✨ Features

- 🔐 Secure login to your NB Power online account
- ⚡ Fetches energy data directly from NB Power’s Widget API
- 📅 Exposes sensors for:
  - **Month-to-date kWh**
  - **Month-to-date cost**
  - **Projected monthly bill**
  - **Projected kWh**
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


---

## 🧠 How it Works

The component logs into `nbpower.com`, collects session cookies, and calls the NB Power **WidgetAPI** endpoints (`VerifyToken`, `GetMultiMeter`, `GetUsageGeneration`).

Month-to-date values come from the `getTentativeData` block. The integration retrieves the current month's summary (kWh, cost, and projection details) each refresh and exposes those values directly as sensor states and attributes.

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
