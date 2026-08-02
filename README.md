[![en](https://img.shields.io/badge/lang-en-red.svg)](README.md)
[![nl](https://img.shields.io/badge/lang-nl-orange.svg)](README.nl.md)

![Version](https://img.shields.io/github/v/release/remmob/sht20modbus 'Release') ![hacs_badge](https://img.shields.io/badge/HACS-Default-orange.svg 'Default Home') [![total issues](https://img.shields.io/github/issues/remmob/sht20modbus 'Total issues')](https://github.com/remmob/sht20modbus/issues) ![Stars](https://img.shields.io/github/stars/remmob/sht20modbus)

# 🧩 SHT20 Modbus Sensor Integration for Home Assistant

A custom Home Assistant integration to connect and configure **SHT20 Modbus RS485 sensors** (models **XY-MD01** / **XY-MD02**) entirely from the UI — no YAML.

<p float="right">
  <img src="./images/sht20.png" width="200"/>
</p>

Connect your sensor in one of three ways:

- **Serial (RTU)** – e.g. a USB → RS485 adapter
- **TCP** – through an Ethernet/WiFi → RS485 gateway
- **UDP** – for gateways that communicate over UDP *(new in v1.1.0)*

These sensors are available via **AliExpress** and, in the Netherlands, via the **Domoticx** webshop:
[domoticx.net – XY-MD01 / SHT20](https://domoticx.net/webshop/modbus-rs485-rtu-temphum-sensor-9-36vdc-xy-md01-sht20/)
(*Know another shop? Drop a line in the discussions.*)

Setup and tuning are fully UI-driven through Home Assistant's `config_flow`, including calibration written straight to the sensor.

---

## ⚙️ Key Features

- **Three connection modes** — Serial (RTU), TCP and UDP, each configurable from the UI.
- **Temperature & humidity** read directly from the sensor's Modbus registers.
- **Four calculated comfort sensors** — dew point, absolute humidity, enthalpy and apparent ("feels like") temperature, derived from the live readings.
- **Connection monitoring** — get notified when the sensor stops responding, with an automatic recovery message once it is back.
- **Quiet hours** — hold mobile notifications during a set period (e.g. at night) and deliver them afterwards.
- **On-device calibration** — temperature and humidity offsets and the device ID/baud rate are written straight to the sensor.
- **Reconfigurable any time** — change everything later from the options screen; no need to remove and re-add the integration.
- **Multiple sensors**, each with its own settings.
- **Dutch and English** translations of the UI.

---

## 🌡️ Calculated Sensors

Alongside the raw **temperature** and **humidity**, the integration adds four sensors that are calculated on the fly:

| Sensor | What it tells you |
| --- | --- |
| **Dew point** | The temperature at which the air would start to condensate. |
| **Absolute humidity** | The actual amount of water in the air (kg water / kg dry air). |
| **Enthalpy** | The total heat content of the air (kJ/kg). |
| **Apparent temperature** | How warm the air *feels*, based on temperature and humidity. |

The calculations use an ambient **pressure** value that you can set in the options (default 1013.25 hPa) for extra accuracy.

---

## 📦 Installation via HACS

<p float="right">
  <img src="./images/pcb.png" width="200"/>
</p>

1. Open **HACS** in Home Assistant.
2. Open the **three-dot menu (⋮)** in the top right and choose **Custom repositories**.
3. Add the repository URL: `https://github.com/remmob/sht20modbus`
4. Set the category to **Integration** and click **Add**.
5. Search for **SHT20** and install it.
6. **Restart Home Assistant**.
7. Go to **Settings → Devices & Services → Add Integration** and search for **SHT20**.

That's it! 🎉 The UI guides you through connecting and configuring your sensor(s).

---

## 🛠️ Setup

![flow](./images/flowstart.png)

- Give the sensor a **name**.
- Set the **device ID** (Modbus address, default = 1).
- Choose the **connection type**: **TCP**, **UDP** or **RTU** (serial).
- Click **Submit**.

**TCP / UDP**

![tcp](./images/flowtcp.png)

- Enter the **IP address** of your gateway.
- Set the **port** (default = 502).
- Set the **scan interval** (default = 10 seconds).
- Click **Submit**.

**RTU (serial)**

![rtu](./images/flowrtu.png)

- Select the **serial port** (all available ports are listed automatically).
- Choose the **baud rate** (default = 9600).
- Set the **scan interval** (default = 10 seconds).
- Click **Submit**.

After submitting, the integration contacts the sensor and reads back its current settings, which you can then fine-tune via the ⚙️ gear icon.

---

## ⚙️ Options

![options](./images/optionstart.png)<br>
Click the gear icon on the SHT20 integration to open the options.

> ℹ️ *The options screenshot below shows the pre-1.1.0 layout. The current screen also includes ambient pressure and the notification settings described here.*

![options](./images/options.png)<br>

**Available options**

- **Device ID** and **baud rate** — written to the sensor; the form is pre-filled with the values the sensor currently reports.
- **Temperature offset** (−10.0 … +10.0 °C) and **humidity offset** (−10.0 … +10.0 %).
- **Ambient pressure** (hPa) — used by the calculated sensors.
- **Multiplier** — scaling for the raw values. Default **0.01** (the sensor reports hundredths, e.g. `2572` → `25.72`). Set to **1** if no scaling is needed.
- **Connection error notifications** — see below.

The integration only writes to the sensor when a value that lives on the device actually changed, and it reloads automatically so new settings take effect right away.

---

## 🔔 Connection Notifications & Quiet Hours

The SHT20 has no alarm registers, but it can lose communication. The integration watches for that and can let you know:

- **Mobile app notification**, **persistent notification** and/or a **notify service** of your choice.
- A configurable **delay** — only notify after the sensor has been unreachable for *x* seconds, to ignore short hiccups.
- An automatic **recovery message** once communication is restored.
- **Quiet hours** — during the configured period, mobile notifications are held and delivered as soon as the quiet period ends. Persistent notifications are never held.

All of this is optional and switched off by default; enable what you need from the options screen.

---

## 💡 Notes

- Some sensors (e.g. bare-PCB versions) report raw values with a different multiplier. The default multiplier is **0.01**; change it if your readings are off by a factor of ten.

---

©2026 Bommer Software | Author: Mischa Bommer
