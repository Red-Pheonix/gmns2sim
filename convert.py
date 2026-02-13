import json
from gmns.traffic_control import (
    build_valid_phase_combinations,
    build_timing_phase_to_movements,
)
from gmns.phasetime_network import (
    build_generalized_phases,
    generate_phase_transition_table,
    generate_timing_constraints_table,
    convert_to_converted_phases,
    build_movement_links,
)
from gmns.core import load_gmns_data_and_config
from gmns.network import (
    prepare_vehicle_links,
    build_network_links,
    select_vehicle_nodes,
    select_vehicle_lanes,
    prepare_vehicle_link_mappings,
)
from gmns.movements import build_turn_movements_by_node, build_movement_index

def generate_lightphases(valid_phase_combinations, turn_movements_by_node):
    traffic_phases_by_node = {}
    timing_plans_by_node = [
        (v[0]["node"], v) for k, v in valid_phase_combinations.items()
    ]
    for node_id, combos in timing_plans_by_node:
        # if node already exists, skip
        if str(node_id) in traffic_phases_by_node:
            continue

        movements = turn_movements_by_node.get(str(node_id), {})
        if not movements:
            continue

        key_to_index = {k: i for i, k in enumerate(sorted(movements.keys(), key=int))}

        # first phase is the yellow light one
        lightphases = []
        yellow_phase = {"time": 5.0, "availableRoadLinks": []}
        lightphases.append(yellow_phase)

        # keep track of road link indices
        road_link_indices = set()
        
        for combo in combos:
            valid_movements = [
                key_to_index.get(str(mvmt)) for mvmt in combo["mvmt_ids"]
            ]
            valid_movements = [v for v in valid_movements if v is not None]
            if not valid_movements:
                continue
            
            road_link_indices = road_link_indices.union(set(valid_movements))
            
            phase = {"time": combo["min_green"], "availableRoadLinks": valid_movements}
            lightphases.append(phase)

        road_link_indices = list(road_link_indices)
        road_link_indices.sort()
        traffic_phases_by_node[str(node_id)] = {
            "roadLinkIndices": road_link_indices,
            "lightphases": lightphases,
        }

    return traffic_phases_by_node

GMNS_FOLDER = "datasets/Arlington_Signals"

gmns_data, config_df = load_gmns_data_and_config(GMNS_FOLDER)

vehicle_links = prepare_vehicle_links(gmns_data["link"])
all_nodes, link_to_road_map, road_to_link_map = prepare_vehicle_link_mappings(
    vehicle_links
)

# get node data
selected_nodes = select_vehicle_nodes(gmns_data["node"], all_nodes)
selected_lanes = select_vehicle_lanes(gmns_data["lane"], link_to_road_map)

# movements
turn_movements_by_node = build_turn_movements_by_node(gmns_data, link_to_road_map)

movement_index = build_movement_index(turn_movements_by_node)

# phases
timing_phase_to_movements = build_timing_phase_to_movements(gmns_data)
timing_plan_to_node = (
    gmns_data["signal_timing_plan"]
    .set_index("timing_plan_id")["controller_id"]
    .astype(int)
    .to_dict()
)

signal_timing_phase = gmns_data["signal_timing_phase"].copy()
signal_timing_phase["node"] = signal_timing_phase["timing_plan_id"].map(
    timing_plan_to_node
)

# pick a single plan for intersection 6 for now
# signal_timing_phase = signal_timing_phase[signal_timing_phase["timing_plan_id"] == 1
phase_df = signal_timing_phase.copy()


valid_phase_combinations = build_valid_phase_combinations(
    phase_df, timing_phase_to_movements, movement_index
)

movements = turn_movements_by_node["6"]
movement_links = build_movement_links(movements)
generalized_phases = build_generalized_phases(valid_phase_combinations)
phase_transition_table = generate_phase_transition_table(
    generalized_phases, flexible=False
)
timing_constraints = generate_timing_constraints_table(generalized_phases)

converted_phases = convert_to_converted_phases(valid_phase_combinations[0])

traffic_phases_by_node = generate_lightphases(
    valid_phase_combinations, turn_movements_by_node
)
# build roads
network_links = build_network_links(
    vehicle_links,
    selected_nodes,
    selected_lanes,
)
roads = list(network_links.values())

# try forming intersections
intersections = []
for idx, row in selected_nodes.iterrows():
    node_id = row["node_id"]

    intersection = {}
    node_id = str(row["node_id"])
    intersection["id"] = node_id
    intersection["point"] = {
        "x": row["x_coord"],
        "y": row["y_coord"],
    }
    intersection["width"] = 15
    intersection["roads"] = [
        road["id"]
        for road in roads
        if road["startIntersection"] == node_id or road["endIntersection"] == node_id
    ]

    intersection["roadLinks"] = list(turn_movements_by_node.get(node_id, {}).values())

    if node_id in traffic_phases_by_node:
        intersection["trafficLight"] = traffic_phases_by_node["6"]
        intersection["virtual"] = False
    else:
        intersection["trafficLight"] = {
            "roadLinkIndices": [],
            "lightphases": [],
        }
        intersection["virtual"] = True
    
    intersections.append(intersection)

cityflow_net = {}
cityflow_net["intersections"] = intersections
cityflow_net["roads"] = roads

# save the network
with open("arlington_net.json", "w") as f:
    json.dump(cityflow_net, f, indent=4)

print("DONE")
