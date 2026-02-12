import pandas as pd

def build_generalized_phases(valid_phase_combinations):
    """
    Convert valid_phase_combinations dictionary into a generalized phases DataFrame.

    Args:
        valid_phase_combinations (dict):
            {
                timing_plan_id: [
                    {
                        phase_combo_item...
                    },
                    ...
                ]
            }

    Returns:
        pd.DataFrame
    """

    rows = []

    for timing_plan_id, combos in valid_phase_combinations.items():
        for i, combo in enumerate(combos):
            nema_combo = "+".join(map(str, combo["NEMA_phases"]))

            controlled_movement_ids = ";".join(
                f'{m["startRoad"]}->{m["endRoad"]}'
                for m in combo.get("movements", [])
            )

            rows.append({
                "timing_plan_id": timing_plan_id,
                "node_id": combo["node"],
                "phase_id": i + 1,  # resets per timing_plan_id
                "controlled_movement_ids": controlled_movement_ids,
                "nema_phase_combination": nema_combo,
                "min_green": combo["min_green"],
                "max_green": combo["max_green"],
                "yellow": combo["yellow"],
                "all_red": combo["all_red"],
                "walk": combo["walk"],
                "ped_clearance": combo["ped_clearance"],
                "veh_ext": combo["veh_ext"],
                "is_coordinated": 0,
                "start_phase": 0,
                "prefer_next_phase": 0,
            })

    return pd.DataFrame(rows)

def generate_phase_transition_table(generalized_phases: pd.DataFrame, 
                                    flexible: bool = True) -> pd.DataFrame:
    """
    Generate the phase_transition table (feasible arcs).
    
    In flexible mode, any phase can transition to any other phase.
    In cyclic mode, only sequential transitions are allowed.
    """
    records = []
    
    # Get unique intersections
    node_ids = generalized_phases['node_id'].unique()
    
    for node_id in node_ids:
        node_phases = generalized_phases[generalized_phases['node_id'] == node_id]
        phase_ids = sorted(node_phases['phase_id'].tolist())
        
        if len(phase_ids) < 2:
            continue
        
        if flexible:
            # Allow any phase to transition to any other
            for from_phase in phase_ids:
                for to_phase in phase_ids:
                    if from_phase != to_phase:
                        # Get timing for from_phase
                        from_row = node_phases[node_phases['phase_id'] == from_phase].iloc[0]
                        min_time = from_row['min_green'] + from_row['yellow'] + from_row['all_red']
                        max_time = from_row['max_green'] + from_row['yellow'] + from_row['all_red']
                        
                        records.append({
                            'node_id': node_id,
                            'from_phase': from_phase,
                            'to_phase': to_phase,
                            'allowed': 1,
                            'min_time_to_transition': min_time,
                            'max_time_to_transition': max_time
                        })
        else:
            # Cyclic sequence only
            for i, from_phase in enumerate(phase_ids):
                to_phase = phase_ids[(i + 1) % len(phase_ids)]
                
                from_row = node_phases[node_phases['phase_id'] == from_phase].iloc[0]
                min_time = from_row['min_green'] + from_row['yellow'] + from_row['all_red']
                max_time = from_row['max_green'] + from_row['yellow'] + from_row['all_red']
                
                records.append({
                    'node_id': node_id,
                    'from_phase': from_phase,
                    'to_phase': to_phase,
                    'allowed': 1,
                    'min_time_to_transition': min_time,
                    'max_time_to_transition': max_time
                })
    
    return pd.DataFrame(records)

def generate_timing_constraints_table(generalized_phases: pd.DataFrame) -> pd.DataFrame:
    """
    Generate the timing_constraints table.
    """
    records = []
    
    for _, row in generalized_phases.iterrows():
        interphase_loss = row['yellow'] + row['all_red']
        min_duration = row['min_green'] + interphase_loss
        max_duration = row['max_green'] + interphase_loss
        ped_min_green = row['walk'] + row['ped_clearance'] if row['walk'] > 0 else row['min_green']
        
        records.append({
            'node_id': row['node_id'],
            'phase_id': row['phase_id'],
            'g_min': row['min_green'],
            'g_max': row['max_green'],
            'yellow': row['yellow'],
            'all_red': row['all_red'],
            'walk': row['walk'],
            'ped_clearance': row['ped_clearance'],
            'veh_ext': row['veh_ext'],
            'min_duration': min_duration,
            'max_duration': max_duration,
            'ped_min_green': ped_min_green,
            'interphase_loss': interphase_loss
        })
    
    return pd.DataFrame(records)

def convert_to_converted_phases(phase_records):
    """
    phase_records: list of dicts like the one in your screenshot

    Returns:
    converted_phases format:
    [
        {
            "nema_phase_combo": "2+5",
            "movements": ["NBL", "NBT", ...]
        }
    ]
    """
    
    # ---------------------------------------------
    # MAPPINGS
    # ---------------------------------------------
    NODE_TO_DIR = {
        "2": "S",
        "4": "N",
        "5": "E",
        "7": "W"
    }

    TURN_TO_SUFFIX = {
        "turn_left": "L",
        "go_straight": "T",
        "turn_right": "R"
    }

    converted_phases = []

    for phase in phase_records:
        movements_out = []

        for mv in phase["movements"]:
            # startRoad looks like "2_6"
            start_node = mv["startRoad"].split("_")[0]

            direction = NODE_TO_DIR.get(start_node)
            if direction is None:
                continue  # skip unknown approaches

            turn_suffix = TURN_TO_SUFFIX.get(mv["type"])
            if turn_suffix is None:
                continue  # skip unknown movement types

            movements_out.append(f"{direction}B{turn_suffix}")

        nema_combo = "+".join(str(p) for p in phase["NEMA_phases"])

        converted_phases.append({
            "nema_phase_combo": nema_combo,
            "movements": movements_out
        })

    return converted_phases

def build_movement_links(movements):
    """
    Convert movements dictionary into movement_links list.

    Args:
        movements (dict):
            {
                movement_id: {
                    "startRoad": str,
                    "endRoad": str,
                    "type": str
                },
                ...
            }

    Returns:
        list[dict]
    """

    movement_links = []

    for m in movements.values():
        start_road = m["startRoad"]
        end_road = m["endRoad"]

        node_id = int(start_road.split("_")[1])

        movement_links.append({
            "movement_id": f"{start_road}->{end_road}",
            "node_id": node_id,
            "ib_link_id": int(start_road.replace("_", "")),
            "ob_link_id": int(end_road.replace("_", "")),
            "mvmt_txt_id": "",
            "approach": "",
            "turn_type": m["type"].replace("_", " "),
            "nema_phase": None,
        })

    return movement_links