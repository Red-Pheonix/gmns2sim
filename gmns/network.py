from utils.unit_converters import mph_to_mps, foot_to_meter, miles_to_meters
import pandas as pd


def prepare_vehicle_links(link_df: pd.DataFrame) -> pd.DataFrame:
    """
    Filter vehicle-capable links and apply unit conversions.
    Returns a DataFrame indexed by link_id.
    """
    vehicle_links = link_df[link_df["lanes"] > 0].copy()

    vehicle_links["road_id"] = (
        vehicle_links["from_node_id"].astype(str)
        + "_"
        + vehicle_links["to_node_id"].astype(str)
    )

    vehicle_links["free_speed"] = vehicle_links["free_speed"].apply(mph_to_mps)
    vehicle_links["row_width"] = vehicle_links["row_width"].apply(foot_to_meter)
    vehicle_links["length"] = vehicle_links["length"].apply(miles_to_meters)

    return vehicle_links.set_index("link_id")

def prepare_vehicle_link_mappings(vehicle_links: pd.DataFrame):
    """
    Build graph mappings from vehicle links.

    Expects vehicle_links to be indexed by link_id and contain:
    from_node_id, to_node_id, road_id
    """
    link_to_road_map = vehicle_links["road_id"].to_dict()

    road_to_link_map = (
        vehicle_links
        .reset_index()
        .set_index("road_id")["link_id"]
        .to_dict()
    )

    all_nodes = set(vehicle_links["from_node_id"]) | set(vehicle_links["to_node_id"])

    return all_nodes, link_to_road_map, road_to_link_map

def select_vehicle_nodes(node_df: pd.DataFrame, all_nodes: set) -> pd.DataFrame:
    """
    Select nodes that appear in vehicle links.
    """
    return node_df[node_df["node_id"].isin(all_nodes)]

def select_vehicle_lanes(lane_df: pd.DataFrame, link_to_road_map: dict) -> pd.DataFrame:
    """
    Select lanes belonging to vehicle links and usable by vehicles.
    """
    selected_lanes = lane_df[
        lane_df["link_id"].isin(link_to_road_map.keys())
    ].copy()

    selected_lanes["width"] = selected_lanes["width"].apply(foot_to_meter)

    # keep only vehicle-usable lanes
    selected_lanes = selected_lanes[selected_lanes["allowed_uses"] == "ALL"]

    return selected_lanes

def build_network_links(
    vehicle_links: pd.DataFrame,
    nodes,
    lanes,
    default_speed: float = 20.1168,
) -> dict:
    """
    Build network links dictionary keyed by from_to node IDs.
    """
    network_links = {}
    
    # now try putting the data together
    # node_id -> (x, y)
    node_xy = (
        nodes
        .set_index('node_id')[['x_coord', 'y_coord']]
        .to_dict('index')
    )

    # link_id -> lanes
    lanes_by_link = (
        lanes
        .groupby('link_id')
        .apply(lambda df: df.to_dict('records'))
        .to_dict()
    )

    for link_id, link in vehicle_links.iterrows():
        from_id = link["from_node_id"]
        to_id = link["to_node_id"]
        link_key = f"{from_id}_{to_id}"

        # ---- points (straight line using nodes) ----
        points = [
            {
                "x": node_xy[from_id]["x_coord"],
                "y": node_xy[from_id]["y_coord"],
            },
            {
                "x": node_xy[to_id]["x_coord"],
                "y": node_xy[to_id]["y_coord"],
            },
        ]

        # ---- lanes ----
        lanes = []
        for lane in lanes_by_link.get(link_id, []):
            lanes.append(
                {
                    "width": lane["width"],
                    "maxSpeed": link.get("free_speed", default_speed),
                }
            )

        network_links[link_key] = {
            "id": link_key,
            "points": points,
            "lanes": lanes,
            "startIntersection": str(from_id),
            "endIntersection": str(to_id),
            "lane_count": link["lanes"],
        }

    return network_links