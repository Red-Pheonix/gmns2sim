
def build_lane_links(row):
    lane_links = []

    start_ib = int(row["start_ib_lane"])
    end_ib = int(row["end_ib_lane"])
    start_ob = int(row["start_ob_lane"])
    end_ob = int(row["end_ob_lane"])

    for ib_lane in range(start_ib, end_ib + 1):
        for ob_lane in range(start_ob, end_ob + 1):
            lane_links.append({
                "startLaneIndex": ib_lane - 1,  # 0-based
                "endLaneIndex": ob_lane - 1,    # 0-based
                "points": []
            })

    return lane_links

def build_turn_movements_by_node(
    gmns_data,
    link_to_road_map
):
    
    type_map = {
        "left": "turn_left",
        "uturn": "turn_left",
        "thru": "go_straight",
        "right": "turn_right",
    }
    
    # process movement data
    movement_df = gmns_data["movement"].copy()

    # map inbound and outbound link IDs to road IDs
    movement_df["ib_road_id"] = movement_df["ib_link_id"].map(link_to_road_map)
    movement_df["ob_road_id"] = movement_df["ob_link_id"].map(link_to_road_map)

    # get rid of car-less movements
    movement_df = movement_df[
        movement_df["ib_road_id"].notna()
        & movement_df["ob_road_id"].notna()
    ]

    # preprocessing for lane ranges
    movement_df["start_ib_lane"] = movement_df["start_ib_lane"].clip(lower=1)
    movement_df["end_ib_lane"] = movement_df["end_ib_lane"].fillna(
        movement_df["start_ib_lane"]
    )
    movement_df["end_ob_lane"] = movement_df["end_ob_lane"].fillna(
        movement_df["start_ob_lane"]
    )

    turn_movements_by_node = {}

    for _, row in movement_df.iterrows():
        node_id = str(row["node_id"])
        mvmt_id = str(row["mvmt_id"])

        movement = {
            "type": type_map[row["type"]],
            "startRoad": row["ib_road_id"],
            "endRoad": row["ob_road_id"],
            "direction": 0,
            "laneLinks": build_lane_links(row),
        }

        if node_id not in turn_movements_by_node:
            turn_movements_by_node[node_id] = {}

        turn_movements_by_node[node_id][mvmt_id] = movement

    return turn_movements_by_node

def build_movement_index(turn_movements_by_node):
    movement_index = {}

    for node_id, movements in turn_movements_by_node.items():
        for mvmt_id, mvmt in movements.items():
            movement_index[mvmt_id] = {
                "node": node_id,
                "startRoad": mvmt["startRoad"],
                "endRoad": mvmt["endRoad"],
                "type": mvmt["type"],
            }

    return movement_index