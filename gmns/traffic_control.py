import itertools
import pandas as pd

# defaults
MIN_GREEN = 5.0
MAX_GREEN = 60.0
YELLOW = 3.0
ALL_RED = 2.0
WALK = 0.0
PED_CLEARANCE = 0.0
VEH_EXT = 3.0

def build_valid_phase_combinations(
    phase_df,
    timing_phase_to_movements,
    movement_index,
    min_green=MIN_GREEN,
    max_green=MAX_GREEN,
    walk=WALK,
    ped_clearance=PED_CLEARANCE,
    veh_ext=VEH_EXT,
):
    """
    Build valid phase combinations grouped by timing_plan_id.
    """

    valid_phase_combinations = {}

    for timing_plan_id, tp_df in phase_df.groupby("timing_plan_id"):
        valid_phase_combinations[timing_plan_id] = []

        for barrier_id, barrier_df in tp_df.groupby("barrier"):

            phases_by_ring = {
                ring: ring_df.to_dict("records")
                for ring, ring_df in barrier_df.groupby("ring")
            }

            if len(phases_by_ring) < 2:
                continue

            for combo in itertools.product(*phases_by_ring.values()):
                combo_df = pd.DataFrame(combo)

                if not combo_df["signal_phase_num"].isin(range(1, 9)).all():
                    continue

                combo_df["mvmt_ids"] = combo_df["timing_phase_id"].map(
                    timing_phase_to_movements
                )

                combo_df = combo_df[combo_df["mvmt_ids"].notna()]
                if len(combo_df) < 2:
                    continue

                combo_df["movements"] = combo_df["mvmt_ids"].apply(
                    lambda ids: list(
                        {
                            (m["startRoad"], m["endRoad"]): m
                            for mvmt_id in (ids or [])
                            if (m := movement_index.get(str(mvmt_id)))
                        }.values()
                    )
                )

                if combo_df.empty:
                    continue

                # flatten + deduplicate movements
                all_movements = [
                    m for ms in combo_df["movements"] for m in ms
                ]
                all_movements = list(
                    {
                        (m["startRoad"], m["endRoad"]): m
                        for m in all_movements
                    }.values()
                )

                # apply bounds
                final_min_green = max(min_green, combo_df["min_green"].max())
                final_max_green = min(max_green, combo_df["max_green"].min())
                clearance = max(5, combo_df["clearance"].max())

                yellow = 3.0
                all_red = clearance - yellow
                final_walk = max(walk, combo_df["walk_time"].max())
                final_ped_clearance = max(
                    ped_clearance, combo_df["ped_clearance"].max()
                )
                final_veh_ext = max(veh_ext, combo_df["extension"].max())

                phase_combo_item = {
                    "timing_plan_id": int(combo_df.iloc[0]["timing_plan_id"]),
                    "node": int(combo_df.iloc[0]["node"]),
                    "phases": list(combo_df["timing_phase_id"]),
                    "NEMA_phases": list(combo_df["signal_phase_num"]),
                    "min_green": int(final_min_green),
                    "max_green": int(final_max_green),
                    "yellow": int(yellow),
                    "all_red": int(all_red),
                    "walk": int(final_walk),
                    "ped_clearance": int(final_ped_clearance),
                    "veh_ext": int(final_veh_ext),
                    "movements": all_movements,
                }

                valid_phase_combinations[timing_plan_id].append(
                    phase_combo_item
                )

    return valid_phase_combinations

def build_timing_phase_to_movements(gmns_data):
    signal_phase_mvmt_df = gmns_data["signal_phase_mvmt"].copy()

    # drop NaN movement IDs
    signal_phase_mvmt_df = signal_phase_mvmt_df[
        signal_phase_mvmt_df["mvmt_id"].notna()
    ]

    # ensure integers
    signal_phase_mvmt_df["mvmt_id"] = signal_phase_mvmt_df["mvmt_id"].astype(int)

    # build mapping: timing_phase_id -> list of mvmt_id
    timing_phase_to_movements = (
        signal_phase_mvmt_df
        .groupby("timing_phase_id")["mvmt_id"]
        .apply(list)
        .to_dict()
    )

    return timing_phase_to_movements