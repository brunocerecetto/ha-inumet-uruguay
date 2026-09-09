"""Constants for the Inumet Uruguay integration."""

DOMAIN = "inumet_uruguay"
NAME = "Inumet Uruguay"
MANUFACTURER = "matbott & 🤖"
VERSION = "3.5.1"

# Official public data sources. The resource index is used to discover movable paths.
BASE_URL = "https://www.inumet.gub.uy"
INFO_RESOURCES_PATH = "android/info_recursosV5.json"
ESTADO_ACTUAL_PATH = "reportes/estadoActual/datos_inumet_ui_publica.mch"
ESTADO_ACTUAL_V2_PATH = "reportes/estadoActual/estadoActualV2.mch"
ESTACIONES_PATH = "reportes/estaciones/estaciones.mch"
FORECAST_PATH = "reportes/pronosticos/pronosticoV4.json"
GENERAL_ALERTS_PATH = "reportes/riesgo/advGral.mch"
SPECIAL_ALERTS_PATH = "reportes/riesgo/avisoGral.mch"

# Intervalo de actualización
DEFAULT_UPDATE_INTERVAL = 30

# Constantes para la configuración
CONF_STATION_ID = "station_id"
CONF_STATION_NAME = "station_name"
CONF_UPDATE_INTERVAL = "update_interval"
