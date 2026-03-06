import json
import os

# Имя файла настроек
SETTINGS_FILE = "settings.json"

# Настройки по умолчанию
DEFAULT_SETTINGS = {
    "LPU_MOPR_kod": "250250",
    "OID_FRMO": "1.2.643.5.1.13.13.12.2.25.2242",  #  F033.OID_SPMO(particial)
    "UIDMO": "25202609300",  # F032, F038, F034.UIDSPMO(particial)
    "SPR_path": ""
}


def load_settings():
    """Загружает настройки из файла или создает новый с дефолтными."""
    if not os.path.exists(SETTINGS_FILE):
        save_settings(DEFAULT_SETTINGS)
        return DEFAULT_SETTINGS

    with open(SETTINGS_FILE, "r") as f:
        return json.load(f)


def save_settings(settings):
    """Сохраняет словарь настроек в файл JSON."""
    with open(SETTINGS_FILE, "w") as f:
        json.dump(settings, f, indent=4)

