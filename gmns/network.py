import pandas as pd
from pyproj import CRS, Transformer
from pyproj import Transformer

from utils.units import UnitSystem

# Defaults are held in SI and applied after the source values are converted, so
# they stay correct whatever units the dataset declares.
DEFAULT_ROW_WIDTH_M = 3.6576   # 12 ft
DEFAULT_LANE_WIDTH_M = 3.6576  # 12 ft


def prepare_vehicle_links(link_df: pd.DataFrame, units: UnitSystem = None) -> pd.DataFrame:
    """
    Filter vehicle-capable links and convert to SI using the dataset's units.
    Returns a DataFrame indexed by link_id.
    """
    units = units or UnitSystem()
    vehicle_links = link_df[link_df["lanes"] > 0].copy()

    vehicle_links["road_id"] = (
        vehicle_links["from_node_id"].astype(str)
        + "_"
        + vehicle_links["to_node_id"].astype(str)
    )

    vehicle_links["free_speed"] = units.to_mps(vehicle_links["free_speed"])
    if "row_width" not in vehicle_links.columns:
        vehicle_links["row_width"] = pd.NA
    vehicle_links["row_width"] = units.to_m_short(
        pd.to_numeric(vehicle_links["row_width"], errors="coerce")
    ).fillna(DEFAULT_ROW_WIDTH_M)
    vehicle_links["length"] = units.to_m_long(vehicle_links["length"])

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

def project_node_coords(node_df: pd.DataFrame, crs) -> pd.DataFrame:
    """
    Ensure node x_coord/y_coord are in meters so they are consistent with the
    meter-based lane widths and lengths.

    `crs` is the coordinate reference system of the input (e.g. an EPSG code).
    If it is geographic (lon/lat degrees), coordinates are projected to the
    UTM zone covering the network centroid. If it is already projected, the
    coordinates are returned unchanged.
    """
    src_crs = CRS.from_user_input(crs)
    if not src_crs.is_geographic:
        return node_df.copy()

    projected = node_df.copy()
    x, y = projected["x_coord"], projected["y_coord"]

    # Pick the UTM zone covering the network centroid.
    lon0, lat0 = x.mean(), y.mean()
    utm_zone = int((lon0 + 180) // 6) + 1
    epsg = (32600 if lat0 >= 0 else 32700) + utm_zone
    transformer = Transformer.from_crs(src_crs, CRS.from_epsg(epsg), always_xy=True)

    projected["x_coord"], projected["y_coord"] = transformer.transform(
        x.values, y.values
    )
    return projected


def select_vehicle_nodes(node_df: pd.DataFrame, all_nodes: set, crs) -> pd.DataFrame:
    """
    Select nodes that appear in vehicle links, projecting their coordinates to
    meters when the input CRS is geographic.
    """
    selected = node_df[node_df["node_id"].isin(all_nodes)]
    return project_node_coords(selected, crs)

# allowed_uses tokens that mark a motor-vehicle lane. Covers the GMNS "ALL"
# convention and osm2gmns' "auto". Matched case-insensitively against the
# comma-separated tokens in the field.
VEHICLE_USE_TOKENS = {"all", "auto"}

def _allows_vehicles(allowed_uses) -> bool:
    if pd.isna(allowed_uses):
        return False
    tokens = {t.strip().lower() for t in str(allowed_uses).split(",")}
    return bool(tokens & VEHICLE_USE_TOKENS)


def select_vehicle_lanes(lane_df: pd.DataFrame, link_to_road_map: dict,
                         units: UnitSystem = None) -> pd.DataFrame:
    """
    Select lanes belonging to vehicle links and usable by vehicles.
    """
    units = units or UnitSystem()
    selected_lanes = lane_df[
        lane_df["link_id"].isin(link_to_road_map.keys())
    ].copy()

    # keep only vehicle-usable lanes (GMNS "ALL" or osm2gmns "auto")
    selected_lanes = selected_lanes[
        selected_lanes["allowed_uses"].apply(_allows_vehicles)
    ]

    # convert the widths present, then fill gaps with the SI default
    selected_lanes["width"] = units.to_m_short(
        pd.to_numeric(selected_lanes["width"], errors="coerce")
    ).fillna(DEFAULT_LANE_WIDTH_M)

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