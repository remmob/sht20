[![en](https://img.shields.io/badge/lang-en-red.svg)](README.md)
[![nl](https://img.shields.io/badge/lang-nl-orange.svg)](README.nl.md)

![Version](https://img.shields.io/github/v/release/remmob/sht20modbus 'Release') ![Downloads](https://img.shields.io/github/downloads/remmob/sht20modbus/total 'Downloads') ![hacs_badge](https://img.shields.io/badge/HACS-Default-orange.svg 'Default Home') [![total issues](https://img.shields.io/github/issues/remmob/sht20modbus 'Total issues')](https://github.com/remmob/sht20modbus/issues) ![Stars](https://img.shields.io/github/stars/remmob/sht20modbus)

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

Setup and tuning are fully UI-driven through Home Assistant's `config_flow`, including temperature and humidity correction applied by Home Assistant itself.

---

## ⚙️ Key Features

- **Three connection modes** — Serial (RTU), TCP and UDP, each configurable from the UI.
- **Temperature & humidity** read directly from the sensor's Modbus registers.
- **Four calculated comfort sensors** — dew point, absolute humidity, enthalpy and apparent ("feels like") temperature, derived from the live readings.
- **Connection monitoring** — get notified when the sensor stops responding, with an automatic recovery message once it is back.
- **Quiet hours** — hold mobile notifications during a set period (e.g. at night) and deliver them afterwards.
- **Temperature and humidity correction** — applied by Home Assistant itself, so it works reliably even on sensor batches that do not store a negative correction correctly.
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

## 📦 Installation

<p float="right">
  <img src="./images/pcb.png" width="200"/>
</p>

### HACS (default store)

SHT20 Modbus is available in the [HACS](https://hacs.xyz) default store.

[![Open your Home Assistant instance and open a repository inside the Home Assistant Community Store.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=remmob&repository=sht20&category=integration)

1. Open **HACS** in Home Assistant.
2. Search for **SHT20** and open it (or use the button above).
3. Click **Download**.
4. **Restart Home Assistant**.

### HACS (custom repository)

1. Open **HACS** in Home Assistant.
2. Click the three-dot menu (⋮) in the top right corner.
3. Select **Custom repositories**.
4. Add this repository URL: `https://github.com/remmob/sht20modbus`.
5. Set the category to **Integration** and click **Add**.
6. Search for **SHT20** and download it.
7. **Restart Home Assistant**.

See the [official HACS documentation](https://hacs.xyz/docs/faq/custom_repositories/) for more details.

### Manual

1. Download or copy the `sht20` folder from this repository: [`custom_components/sht20`](custom_components/sht20)
2. Place this folder in your Home Assistant installation under: `config/custom_components/sht20`
3. **Restart Home Assistant**.

After installing, go to **Settings → Devices & Services → Add Integration** and search for **SHT20**. That's it! 🎉 The UI guides you through connecting and configuring your sensor(s).

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

After submitting, you can fine-tune corrections and notifications via the ⚙️ gear icon.

---

## ⚙️ Options

![options](./images/optionstart.png)<br>
Click the gear icon on the SHT20 integration to open the options.

> ℹ️ *The options screenshot below shows the pre-1.1.0 layout. The current screen also includes ambient pressure and the notification settings described here.*

![options](./images/options.png)<br>

**Available options**

- **Device ID** and **baud rate** — connection parameters only, used to reach the sensor; never written to it. If you change the sensor's own address or baud rate (outside Home Assistant), update these to match so the integration can still connect. Baud rate only appears here for a serial (RTU) connection.
- **Scan interval** — now changeable after setup too. Increase this if the sensor shares a gateway with other Modbus devices.
- **Temperature offset** and **humidity offset** — added to the measured value in Home Assistant, not written to the sensor.
- **Ambient pressure** (hPa) — used by the calculated sensors.
- **Multiplier** — scaling for the raw values. Default **0.01** (the sensor reports hundredths, e.g. `2572` → `25.72`). Set to **1** if no scaling is needed.
- **Connection error notifications** — see below.

The integration reloads automatically so new settings take effect right away.

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
