import os
import pandas as pd

GMNS_FOLDER = "datasets/Arlington_Signals"

# open all csv files and load them into a dict with pandas dataframes
def load_gmns_data(gmns_folder):
    gmns_data = {}
    for filename in os.listdir(gmns_folder):
        if filename.lower().endswith(".csv"):
            file_path = os.path.join(gmns_folder, filename)

            # remove the .csv extension
            name = os.path.splitext(filename)[0]

            gmns_data[name] = pd.read_csv(file_path)

    return gmns_data

gmns_data = load_gmns_data(GMNS_FOLDER)

print(gmns_data.keys())
