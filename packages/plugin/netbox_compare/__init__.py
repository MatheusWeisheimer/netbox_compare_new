from netbox.plugins import PluginConfig


class NetBoxCompareConfig(PluginConfig):
    name = "netbox_compare"
    verbose_name = "NetBox Compare"
    description = "Compare documented and running device state"
    version = "0.1.0"
    base_url = "compare"
    min_version = "4.5.0"
    max_version = "4.5.99"
    default_settings = {
        # Development credential store: path to a TOML file (never shown in the UI).
        "credentials_file": None,
    }


config = NetBoxCompareConfig
