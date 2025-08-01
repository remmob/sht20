"""Constants for the SHT20 Modbus integration"""

# Integration domain
DOMAIN = "sht20"

# Config entry keys
CONF_NAME = "name"
CONF_MODE = "mode"
CONF_DEVICE = "device"          # RTU only
CONF_DEVICE_ID = "device_id"    # Modbus unit ID
CONF_BAUDRATE = "baudrate"      # RTU only
CONF_SCAN_INTERVAL = "scan_interval"
CONF_PORT = "port"              # TCP only
CONF_TEMP_OFFSET = "temp_offset"
CONF_HUM_OFFSET = "hum_offset"
CONF_MULTIPLIER = "multiplier"

# Default values
DEFAULT_NAME = "sht20"
DEFAULT_PORT = 502
DEFAULT_DEVICE_ID = 1
DEFAULT_BAUDRATE = 9600
DEFAULT_SCAN_INTERVAL = 10
DEFAULT_MULTIPLIER = 0.1

# Platforms to set up
PLATFORMS = ["sensor"]

# Minimum required Home Assistant version
REQUIRED_VERSION = "2025.6.0"
