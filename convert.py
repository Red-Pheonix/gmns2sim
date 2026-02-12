import pandas as pd
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

GMNS_FOLDER = "datasets/Arlington_Signals"

gmns_data, config_df = load_gmns_data_and_config(GMNS_FOLDER)

vehicle_links = prepare_vehicle_links(gmns_data["link"])
all_nodes, link_to_road_map, road_to_link_map = prepare_vehicle_link_mappings(
    vehicle_links
)

# get node data
selected_nodes = select_vehicle_nodes(gmns_data["node"], all_nodes)
selected_lanes = select_vehicle_lanes(gmns_data["lane"], link_to_road_map)


network_links = build_network_links(
    vehicle_links,
    selected_nodes,
    selected_lanes,
)

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

print(gmns_data.keys())
