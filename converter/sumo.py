"""SUMO converter — produces netconvert input files (.nod.xml, .edg.xml,
.con.xml, .tll.xml) and optionally invokes netconvert to build the merged
.net.xml.

Architecture mirrors CityFlowConverter:
    1. Shared GMNS pipeline (gmns/* modules) loads + reshapes raw input.
    2. SUMO-specific adapter helpers (_build_*) translate the CityFlow-leaning
       intermediate structures into SUMO-shaped dicts.
    3. Serialization helpers (_write_*) emit XML via lxml.etree.

This is a SCAFFOLD. The adapter helpers currently return empty lists so the
end-to-end flow (including netconvert invocation) can be exercised before we
fill in the real conversion logic piece by piece.
"""
from pathlib import Path
import os
import shutil
import subprocess

from lxml import etree

from gmns.core import load_gmns_data_and_config
from gmns.movements import build_movement_index, build_turn_movements_by_node
from gmns.network import (
    build_network_links,
    prepare_vehicle_link_mappings,
    prepare_vehicle_links,
    select_vehicle_lanes,
    select_vehicle_nodes,
)
from gmns.traffic_control import (
    build_timing_phase_to_movements,
    build_valid_phase_combinations,
)


class SumoConverter:
    def __init__(self, gmns_folder):
        self.gmns_folder = Path(gmns_folder)

    # ------------------------------------------------------------------
    # Top-level pipeline
    # ------------------------------------------------------------------
    def convert(self):
        """Run the shared GMNS pipeline and reshape into SUMO-ready dicts.

        Returns a dict with one entry per netconvert input file:
            {
                "nodes":       [...],   # → .nod.xml
                "edges":       [...],   # → .edg.xml
                "connections": [...],   # → .con.xml
                "tl_logics":   [...],   # → .tll.xml
            }
        """
        gmns_data, _ = load_gmns_data_and_config(str(self.gmns_folder))

        # --- Layer 1: shared GMNS pipeline (identical to CityFlow converter) -
        # NOTE: these helpers were written with CityFlow's shapes in mind. We
        # still reuse them, but the Layer-2 adapters below may need to massage
        # their output into SUMO's expected form.
        vehicle_links = prepare_vehicle_links(gmns_data["link"])
        all_nodes, link_to_road_map, _ = prepare_vehicle_link_mappings(vehicle_links)

        selected_nodes = select_vehicle_nodes(gmns_data["node"], all_nodes)
        selected_lanes = select_vehicle_lanes(gmns_data["lane"], link_to_road_map)

        turn_movements_by_node = build_turn_movements_by_node(
            gmns_data,
            link_to_road_map,
        )
        movement_index = build_movement_index(turn_movements_by_node)

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

        valid_phase_combinations = build_valid_phase_combinations(
            signal_timing_phase,
            timing_phase_to_movements,
            movement_index,
        )

        network_links = build_network_links(
            vehicle_links,
            selected_nodes,
            selected_lanes,
        )
        roads = list(network_links.values())

        # --- Layer 2: SUMO-shaped adapters -----------------------------------
        signalized_node_ids = {
            str(v[0]["node"]) for v in valid_phase_combinations.values() if v
        }

        nodes = self._build_nodes(selected_nodes, signalized_node_ids)
        edges = self._build_edges(roads)
        connections = self._build_connections(
            turn_movements_by_node, signalized_node_ids
        )
        tl_logics = self._build_tl_logics(
            valid_phase_combinations,
            turn_movements_by_node,
        )

        return {
            "nodes": nodes,
            "edges": edges,
            "connections": connections,
            "tl_logics": tl_logics,
        }

    def write(self, output_dir, basename=None, run_netconvert=True):
        """Write the four netconvert input files and (optionally) invoke
        netconvert to produce <basename>.net.xml.

        Returns a dict mapping section name -> produced Path.
        """
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        if basename is None:
            basename = self.gmns_folder.name.lower()

        data = self.convert()

        paths = {
            "nodes":       output_dir / f"{basename}.nod.xml",
            "edges":       output_dir / f"{basename}.edg.xml",
            "connections": output_dir / f"{basename}.con.xml",
            "tl_logics":   output_dir / f"{basename}.tll.xml",
        }

        self._write_nodes_xml(data["nodes"], paths["nodes"])
        self._write_edges_xml(data["edges"], paths["edges"])
        self._write_connections_xml(data["connections"], paths["connections"])
        self._write_tl_logics_xml(data["tl_logics"], paths["tl_logics"])

        if run_netconvert:
            paths["net"] = output_dir / f"{basename}.net.xml"
            self._run_netconvert(paths)

        return paths

    # ------------------------------------------------------------------
    # Layer 2: SUMO-shaped adapters (STUBS)
    # ------------------------------------------------------------------
    @staticmethod
    def _build_nodes(selected_nodes, signalized_node_ids):
        """Map selected GMNS nodes into SUMO node dicts.

        Node type is "traffic_light" when the node has any valid phase
        combinations, "priority" otherwise. Boundary / virtual nodes
        (those with only inbound+outbound dummy roads) fall through to
        "priority"; netconvert handles them fine as edge endpoints.
        """
        nodes = []
        for _, row in selected_nodes.iterrows():
            node_id = str(row["node_id"])
            nodes.append({
                "id": node_id,
                "x": float(row["x_coord"]),
                "y": float(row["y_coord"]),
                "type": "traffic_light" if node_id in signalized_node_ids
                        else "priority",
            })
        return nodes

    @staticmethod
    def _build_edges(roads):
        """Map CityFlow-shaped road dicts into SUMO edge dicts.

        Shape is only included when the road has intermediate vertices;
        for the common 2-point (start→end) case we omit it and let SUMO
        infer the straight line between the from/to nodes.
        """
        edges = []
        for road in roads:
            lanes = road.get("lanes") or []
            speed = next(
                (l["maxSpeed"] for l in lanes if l.get("maxSpeed") is not None),
                13.89,  # ~50 km/h fallback
            )
            edge = {
                "id": road["id"],
                "from": road["startIntersection"],
                "to": road["endIntersection"],
                "numLanes": len(lanes) or int(road.get("lane_count", 1)),
                "speed": float(speed),
            }
            pts = road.get("points") or []
            if len(pts) > 2:
                edge["shape"] = [(p["x"], p["y"]) for p in pts]
            edges.append(edge)
        return edges

    @staticmethod
    def _build_connections(turn_movements_by_node, signalized_node_ids):
        """Flatten CityFlow-shaped roadLinks into per-lane SUMO connections.

        For signalized nodes, each connection gets a tl= reference and a
        linkIndex= position. The ordering here MUST match the ordering
        used by _build_tl_logics to construct phase state strings —
        movements sorted by integer id, then lane-links in declaration
        order — so the linkIndex of each connection lines up with its
        column in the state string.
        """
        type_to_dir = {
            "turn_left": "l",
            "go_straight": "s",
            "turn_right": "r",
        }

        connections = []
        for node_id, movements in turn_movements_by_node.items():
            is_signal = node_id in signalized_node_ids
            sorted_keys = sorted(movements.keys(), key=int)
            link_idx = 0

            for mvmt_id in sorted_keys:
                mvmt = movements[mvmt_id]
                for ll in mvmt["laneLinks"]:
                    conn = {
                        "from": mvmt["startRoad"],
                        "to": mvmt["endRoad"],
                        "fromLane": int(ll["startLaneIndex"]),
                        "toLane": int(ll["endLaneIndex"]),
                        "dir": type_to_dir.get(mvmt["type"], "s"),
                    }
                    if is_signal:
                        conn["tl"] = node_id
                        conn["linkIndex"] = link_idx
                        link_idx += 1
                    connections.append(conn)
        return connections

    @staticmethod
    def _build_tl_logics(valid_phase_combinations, turn_movements_by_node):
        """Build per-node SUMO tlLogic dicts with phase state strings.

        SUMO phase encoding differs from CityFlow's: instead of an index
        list into roadLinks, each phase is a length-N string where N is
        the number of controlled lane-links at the node and each
        character is one of {G,g,r,y,s}. We use 'G'/'r' only for now
        (no yellow/clearance interval).

        Movement ordering mirrors CityFlow's _generate_lightphases so
        availableRoadLinks indices remain meaningful, then each movement
        is expanded into one column per laneLink.
        """
        tl_logics = []
        seen = set()

        for combos in valid_phase_combinations.values():
            if not combos:
                continue
            node_id = str(combos[0]["node"])
            if node_id in seen:
                continue
            seen.add(node_id)

            movements = turn_movements_by_node.get(node_id, {})
            if not movements:
                continue

            sorted_keys = sorted(movements.keys(), key=int)
            key_to_movement_idx = {k: i for i, k in enumerate(sorted_keys)}

            # link_to_movement_idx[k] = which movement (by sorted index) owns
            # the kth lane-link column in the state string. Order must match
            # _build_connections' iteration exactly.
            link_to_movement_idx = []
            for i, mvmt_id in enumerate(sorted_keys):
                for _ in movements[mvmt_id]["laneLinks"]:
                    link_to_movement_idx.append(i)
            n_links = len(link_to_movement_idx)

            # All-red guard phase, same convention as CityFlow converter.
            phases = [{"duration": 5.0, "state": "r" * n_links}]

            for combo in combos:
                active_movements = {
                    key_to_movement_idx.get(str(mid))
                    for mid in combo["mvmt_ids"]
                }
                active_movements.discard(None)
                if not active_movements:
                    continue
                state = "".join(
                    "G" if link_to_movement_idx[k] in active_movements else "r"
                    for k in range(n_links)
                )
                phases.append({
                    "duration": float(combo["min_green"]),
                    "state": state,
                })

            tl_logics.append({
                "id": node_id,
                "programID": "0",
                "type": "static",
                "offset": 0,
                "phases": phases,
            })

        return tl_logics

    # ------------------------------------------------------------------
    # Layer 3: XML serialization (lxml)
    # ------------------------------------------------------------------
    @staticmethod
    def _write_xml(root, path):
        tree = etree.ElementTree(root)
        tree.write(
            str(path),
            pretty_print=True,
            xml_declaration=True,
            encoding="UTF-8",
        )

    @classmethod
    def _write_nodes_xml(cls, nodes, path):
        root = etree.Element("nodes")
        for n in nodes:
            etree.SubElement(root, "node", {
                "id": str(n["id"]),
                "x": f'{n["x"]}',
                "y": f'{n["y"]}',
                "type": n.get("type", "priority"),
            })
        cls._write_xml(root, path)

    @classmethod
    def _write_edges_xml(cls, edges, path):
        root = etree.Element("edges")
        for e in edges:
            attrs = {
                "id": str(e["id"]),
                "from": str(e["from"]),
                "to": str(e["to"]),
                "numLanes": str(e["numLanes"]),
                "speed": f'{e["speed"]}',
            }
            shape = e.get("shape")
            if shape:
                attrs["shape"] = " ".join(f"{x},{y}" for x, y in shape)
            etree.SubElement(root, "edge", attrs)
        cls._write_xml(root, path)

    @classmethod
    def _write_connections_xml(cls, connections, path):
        root = etree.Element("connections")
        for c in connections:
            attrs = {
                "from": str(c["from"]),
                "to": str(c["to"]),
                "fromLane": str(c["fromLane"]),
                "toLane": str(c["toLane"]),
            }
            for opt in ("dir", "tl", "linkIndex"):
                if opt in c:
                    attrs[opt] = str(c[opt])
            etree.SubElement(root, "connection", attrs)
        cls._write_xml(root, path)

    @classmethod
    def _write_tl_logics_xml(cls, tl_logics, path):
        root = etree.Element("additional")
        for tl in tl_logics:
            tlel = etree.SubElement(root, "tlLogic", {
                "id": str(tl["id"]),
                "programID": str(tl.get("programID", "0")),
                "type": tl.get("type", "static"),
                "offset": str(tl.get("offset", 0)),
            })
            for ph in tl["phases"]:
                etree.SubElement(tlel, "phase", {
                    "duration": str(ph["duration"]),
                    "state": ph["state"],
                })
        cls._write_xml(root, path)

    # ------------------------------------------------------------------
    # netconvert invocation
    # ------------------------------------------------------------------
    @staticmethod
    def _run_netconvert(paths):
        exe = shutil.which("netconvert")
        if not exe:
            raise RuntimeError(
                "netconvert not found on PATH. Install SUMO or pass "
                "run_netconvert=False to write inputs only."
            )
        env = os.environ.copy()
        # Infer SUMO_HOME from the netconvert binary location if not set.
        # Linux/Windows typical:   <SUMO_HOME>/bin/netconvert
        # macOS Eclipse framework: <root>/bin/netconvert with data under
        #                          <root>/share/sumo/{data,tools}
        if not env.get("SUMO_HOME"):
            bin_parent = Path(exe).resolve().parent.parent
            for candidate in (bin_parent, bin_parent / "share" / "sumo"):
                if (candidate / "data").exists() or (candidate / "tools").exists():
                    env["SUMO_HOME"] = str(candidate)
                    break
        cmd = [
            exe,
            "--node-files", str(paths["nodes"]),
            "--edge-files", str(paths["edges"]),
            "--connection-files", str(paths["connections"]),
            "--tllogic-files", str(paths["tl_logics"]),
            "--output-file", str(paths["net"]),
        ]
        subprocess.run(cmd, check=True, env=env)
