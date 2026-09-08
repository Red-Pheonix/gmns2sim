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

def _as_id(value):
    """Keep an id as an int when it is one, otherwise as text."""
    text = str(value).strip()
    try:
        number = float(text)
    except (TypeError, ValueError):
        return text
    return int(number) if number.is_integer() else text


def _phase_groups(phases_by_ring):
    """Concurrent phase groups within a barrier, or None if not derivable.

    NEMA runs ring 1 alongside ring 2 at the same position (1+5, 2+6, ...).
    A position present in only one ring is a phase that runs on its own, which
    is ordinary at T-intersections and for protected lefts with no concurrent
    partner. Those are kept as single-phase groups: dropping them silently
    removes their green time from the cycle.
    """
    by_pos = {}
    for ring_records in phases_by_ring.values():
        for rec in ring_records:
            pos = rec.get("position")
            if pos is None or pd.isna(pos):
                return None
            by_pos.setdefault(int(pos), []).append(rec)
    if not by_pos:
        return None
    return [tuple(by_pos[pos]) for pos in sorted(by_pos)]


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

            # The cross product would emit pairs like 1+6 that never run
            # together, inflating the cycle, so group by position instead.
            combos_to_try = _phase_groups(phases_by_ring)
            if combos_to_try is None:
                if len(phases_by_ring) < 2:
                    continue
                combos_to_try = itertools.product(*phases_by_ring.values())

            for combo in combos_to_try:
                combo_df = pd.DataFrame(combo)

                if not combo_df["signal_phase_num"].isin(range(1, 9)).all():
                    continue

                combo_df["mvmt_ids"] = combo_df["timing_phase_id"].map(
                    timing_phase_to_movements
                )

                combo_df = combo_df[combo_df["mvmt_ids"].notna()]
                if combo_df.empty:
                    continue
                
                # grab all movements and delete duplicates
                mvmt_ids = list({m for ms in combo_df["mvmt_ids"] for m in ms})
                all_movements = [movement_index.get(str(mvmt_id)) for mvmt_id in mvmt_ids]
                all_movements = [m for m in all_movements if m is not None]

                # apply bounds
                final_min_green = max(min_green, combo_df["min_green"].max())
                final_max_green = min(max_green, combo_df["max_green"].min())
                # 5 s is a fallback for a missing clearance, not a floor to
                # impose on a declared one — clamping a real 4 s clearance up
                # to 5 lengthens every cycle it appears in.
                declared = combo_df["clearance"].dropna()
                clearance = float(declared.max()) if not declared.empty else 5.0

                # GMNS carries a single clearance, so split it the usual way.
                # The total is what matters for the cycle.
                yellow = min(3.0, clearance)
                all_red = clearance - yellow
                final_walk = max(walk, combo_df["walk_time"].max())
                final_ped_clearance = max(
                    ped_clearance, combo_df["ped_clearance"].max()
                )
                final_veh_ext = max(veh_ext, combo_df["extension"].max())

                phase_combo_item = {
                    # GMNS ids are "any"; utdf2gmns uses strings like "39_1"
                    "timing_plan_id": _as_id(combo_df.iloc[0]["timing_plan_id"]),
                    "node": _as_id(combo_df.iloc[0]["node"]),
                    "phases": list(combo_df["timing_phase_id"]),
                    "NEMA_phases": list(combo_df["signal_phase_num"]),
                    "min_green": float(final_min_green),
                    "max_green": float(final_max_green),
                    "yellow": float(yellow),
                    "all_red": float(round(all_red, 1)),
                    "walk": int(final_walk),
                    "ped_clearance": int(final_ped_clearance),
                    "veh_ext": int(final_veh_ext),
                    "movements": all_movements,
                    "mvmt_ids": mvmt_ids,
                }

                valid_phase_combinations[timing_plan_id].append(
                    phase_combo_item
                )

    return valid_phase_combinations

def _has_signal_control_data(gmns_data):
    """True only if the GMNS signal-control tables needed to build timing
    plans are present and non-empty."""
    for table in ("signal_timing_plan", "signal_timing_phase"):
        df = gmns_data.get(table)
        if df is None or df.empty:
            return False
    return True


def build_valid_phase_combinations_for_network(
    gmns_data, movement_index, turn_movements_by_node
):
    """
    Top-level entry for signal phasing. Builds valid phase combinations from
    the GMNS signal-control tables when they exist, and otherwise falls back
    to a synthesized default plan so networks without signal-control files
    still convert.
    """
    if _has_signal_control_data(gmns_data):
        timing_phase_to_movements = build_timing_phase_to_movements(gmns_data)
        timing_plan_to_node = (
            gmns_data["signal_timing_plan"]
            .set_index("timing_plan_id")["controller_id"]
            .map(_as_id)
            .to_dict()
        )
        signal_timing_phase = gmns_data["signal_timing_phase"].copy()
        signal_timing_phase["node"] = signal_timing_phase["timing_plan_id"].map(
            timing_plan_to_node
        )
        return build_valid_phase_combinations(
            signal_timing_phase,
            timing_phase_to_movements,
            movement_index,
        )

    print(
        "[traffic_control] signal-control files not found; "
        "synthesizing a default one-phase-per-approach signal plan."
    )
    return build_default_valid_phase_combinations(
        turn_movements_by_node, movement_index
    )


def build_default_valid_phase_combinations(turn_movements_by_node, movement_index):
    """
    Synthesize a simple default signal plan for when no GMNS signal-control
    tables are available.

    Each intersection (a node with 2+ inbound approaches) gets one phase per
    inbound approach: every movement arriving from that approach is served
    together while the other approaches are held red. This is a safe,
    conflict-free fixed-time fallback rather than an optimized NEMA plan.
    """
    valid_phase_combinations = {}

    for node_id, movements in turn_movements_by_node.items():
        # group movement ids by inbound approach (startRoad)
        approaches = {}
        for mvmt_id, mvmt in movements.items():
            approaches.setdefault(mvmt["startRoad"], []).append(mvmt_id)

        # a single-approach node is not a real intersection; skip it
        if len(approaches) < 2:
            continue

        node = int(node_id)
        combos = []
        for approach in sorted(approaches, key=str):
            mvmt_ids = approaches[approach]
            combo_movements = [
                movement_index.get(mvmt_id) for mvmt_id in mvmt_ids
            ]
            combo_movements = [m for m in combo_movements if m is not None]
            combos.append(
                {
                    "timing_plan_id": node,
                    "node": node,
                    "phases": [],
                    "NEMA_phases": [],
                    "min_green": int(MIN_GREEN),
                    "max_green": int(MAX_GREEN),
                    "yellow": int(YELLOW),
                    "all_red": int(ALL_RED),
                    "walk": int(WALK),
                    "ped_clearance": int(PED_CLEARANCE),
                    "veh_ext": int(VEH_EXT),
                    "movements": combo_movements,
                    "mvmt_ids": mvmt_ids,
                }
            )

        valid_phase_combinations[node] = combos

    return valid_phase_combinations


def _normalize_id(value):
    """Render a GMNS id the same way `str(row["mvmt_id"])` does.

    Numeric ids read back as 5 or 5.0 both become "5"; string ids pass through
    untouched.
    """
    text = str(value).strip()
    try:
        number = float(text)
    except (TypeError, ValueError):
        return text
    return str(int(number)) if number.is_integer() else text


def build_timing_phase_to_movements(gmns_data):
    signal_phase_mvmt = gmns_data.get("signal_phase_mvmt")
    if signal_phase_mvmt is None or signal_phase_mvmt.empty:
        return _default_timing_phase_to_movements(gmns_data)

    signal_phase_mvmt_df = signal_phase_mvmt.copy()

    # drop NaN movement IDs
    signal_phase_mvmt_df = signal_phase_mvmt_df[
        signal_phase_mvmt_df["mvmt_id"].notna()
    ]

    # GMNS types mvmt_id as "any", so ids may be strings (utdf2gmns emits e.g.
    # "106_39_74_SBL"). Normalise to the same string form movement_index is
    # keyed by rather than forcing int, which rejects valid networks.
    signal_phase_mvmt_df["mvmt_id"] = signal_phase_mvmt_df["mvmt_id"].map(_normalize_id)

    # build mapping: timing_phase_id -> list of mvmt_id
    timing_phase_to_movements = (
        signal_phase_mvmt_df
        .groupby("timing_phase_id")["mvmt_id"]
        .apply(list)
        .to_dict()
    )

    return timing_phase_to_movements


# NEMA convention: odd phases serve protected left turns, even phases serve
# the through (and concurrent right) movements at the intersection.
NEMA_ODD_MOVEMENT_TYPES = {"left"}
NEMA_EVEN_MOVEMENT_TYPES = {"thru", "right"}


def _default_timing_phase_to_movements(gmns_data):
    """
    Fallback mapping for when signal_phase_mvmt is absent.

    Assigns each timing phase the movements at its node that match the NEMA
    convention for the phase number: odd phases -> left turns, even phases ->
    through/right movements. This is an approximation (it does not distinguish
    approach directions) but yields valid mvmt_ids so downstream phase building
    still works.
    """
    print(
        "[traffic_control] signal_phase_mvmt not found; "
        "falling back to default NEMA phase-to-movement mapping."
    )

    movement_df = gmns_data["movement"]
    timing_phase_df = gmns_data["signal_timing_phase"]
    timing_plan_df = gmns_data["signal_timing_plan"]

    # timing_plan_id -> node (controller_id)
    plan_to_node = (
        timing_plan_df.set_index("timing_plan_id")["controller_id"].to_dict()
    )

    # node -> {movement type -> [mvmt_id]}
    movements_by_node = {}
    for _, mvmt in movement_df.iterrows():
        if pd.isna(mvmt["mvmt_id"]) or pd.isna(mvmt["node_id"]):
            continue
        node = int(mvmt["node_id"])
        mvmt_type = str(mvmt["type"]).strip().lower()
        movements_by_node.setdefault(node, {}).setdefault(mvmt_type, []).append(
            int(mvmt["mvmt_id"])
        )

    timing_phase_to_movements = {}
    for _, phase in timing_phase_df.iterrows():
        if pd.isna(phase["signal_phase_num"]):
            continue
        node = plan_to_node.get(phase["timing_plan_id"])
        if node is None:
            continue
        node = int(node)

        phase_num = int(phase["signal_phase_num"])
        wanted_types = (
            NEMA_ODD_MOVEMENT_TYPES if phase_num % 2 == 1 else NEMA_EVEN_MOVEMENT_TYPES
        )

        node_movements = movements_by_node.get(node, {})
        mvmt_ids = [
            mvmt_id
            for mvmt_type, ids in node_movements.items()
            if mvmt_type in wanted_types
            for mvmt_id in ids
        ]
        if mvmt_ids:
            timing_phase_to_movements[int(phase["timing_phase_id"])] = mvmt_ids

    return timing_phase_to_movements