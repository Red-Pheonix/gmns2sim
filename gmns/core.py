
import gmnspy
import pandas as pd
import os

from utils.units import UnitSystem


def load_gmns_data_and_config(gmns_folder: str):
    """Read a GMNS folder.

    Returns (gmns_data, config_df, units). `units` comes from config.csv; a
    dataset shipping no config.csv is assumed to be SI (metres, m/s).
    """
    gmns_data = gmnspy.in_out.read_gmns_network(gmns_folder)

    # strip leading/trailing whitespace from string columns
    for key, df in gmns_data.items():
        gmns_data[key] = df.apply(
            lambda col: col.str.strip() if col.dtype == "object" else col
        )

    # load config
    config_path = os.path.join(gmns_folder, "config.csv")
    config_df = pd.read_csv(config_path) if os.path.exists(config_path) else None

    units = UnitSystem.from_config(config_df)

    return gmns_data, config_df, units


DEFAULT_CRS = 4326


def _crs_from_config(config_df, default=DEFAULT_CRS):
    """CRS declared in config.csv, else `default`.

    A dataset already in projected metres (say EPSG:32619) that gets read as
    lon/lat produces no error — just nonsense coordinates — so the declared
    value is preferred over any assumption.
    """
    if config_df is None or len(config_df) == 0 or "crs" not in config_df.columns:
        return default
    val = config_df.iloc[0]["crs"]
    if pd.isna(val):
        return default
    text = str(val).strip()
    if not text:
        return default
    return int(text) if text.isdigit() else text