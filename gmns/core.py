
import gmnspy
import pandas as pd
import os

def load_gmns_data_and_config(gmns_folder: str):
    gmns_data = gmnspy.in_out.read_gmns_network(gmns_folder)

    # strip leading/trailing whitespace from string columns
    for key, df in gmns_data.items():
        gmns_data[key] = df.apply(
            lambda col: col.str.strip() if col.dtype == "object" else col
        )

    # load config
    config_path = os.path.join(gmns_folder, "config.csv")
    config_df = pd.read_csv(config_path) if os.path.exists(config_path) else None

    return gmns_data, config_df