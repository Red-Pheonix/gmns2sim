import json
from pathlib import Path

from gmns.core import load_gmns_data_and_config, _crs_from_config
from gmns.movements import build_movement_index, build_turn_movements_by_node
from gmns.network import (
    build_network_links,
    prepare_vehicle_link_mappings,
    prepare_vehicle_links,
    select_vehicle_lanes,
    select_vehicle_nodes,
)
from gmns.traffic_control import (
    build_valid_phase_combinations_for_network,
)


class CityFlowConverter:
    def __init__(self, gmns_folder, crs=None):
        self.gmns_folder = Path(gmns_folder)
        self.crs = crs

    def convert(self):
        gmns_data, config_df, units = load_gmns_data_and_config(str(self.gmns_folder))
        print(f"  units: {units.describe()}")
        crs = self.crs if self.crs is not None else _crs_from_config(config_df)
        print(f"  crs  : {crs}")

        vehicle_links = prepare_vehicle_links(gmns_data["link"], units)
        all_nodes, link_to_road_map, _ = prepare_vehicle_link_mappings(vehicle_links)

        selected_nodes = select_vehicle_nodes(gmns_data["node"], all_nodes, crs)
        selected_lanes = select_vehicle_lanes(gmns_data["lane"], link_to_road_map, units)

        turn_movements_by_node = build_turn_movements_by_node(
            gmns_data,
            link_to_road_map,
        )
        movement_index = build_movement_index(turn_movements_by_node)

        valid_phase_combinations = build_valid_phase_combinations_for_network(
            gmns_data,
            movement_index,
            turn_movements_by_node,
        )
        traffic_phases_by_node = self._generate_lightphases(
            valid_phase_combinations,
            turn_movements_by_node,
        )

        network_links = build_network_links(
            vehicle_links,
            selected_nodes,
            selected_lanes,
        )
        roads = list(network_links.values())

        intersections = self._build_intersections(
            selected_nodes,
            roads,
            turn_movements_by_node,
            traffic_phases_by_node,
        )

        return {
            "intersections": intersections,
            "roads": roads,
        }

    def write(self, output_path, indent=4, write_config=True,
              interval=1.0, seed=0, save_replay=True):
        """Write the CityFlow roadnet JSON, and by default the config and flow
        files that go with it.

        CityFlow will not open a roadnet on its own: the engine is constructed
        from a config.json, which must name both a roadnet and a flow file that
        exist. The converter produces no demand, so the flow is written empty —
        valid, loadable, and the obvious place to add vehicles.

        Returns the roadnet Path when write_config is False, otherwise a dict
        of {"roadnet", "flow", "config"} Paths.
        """
        cityflow_network = self.convert()
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        with output_path.open("w") as output_file:
            json.dump(cityflow_network, output_file, indent=indent)

        if not write_config:
            return output_path

        stem = output_path.stem
        flow_path = output_path.with_name(f"{stem}_flow.json")
        config_path = output_path.with_name(f"{stem}_config.json")

        with flow_path.open("w") as flow_file:
            json.dump([], flow_file, indent=indent)

        # dir is "./" and the file names are bare, so the folder can be moved
        # or zipped and CityFlow still finds everything.
        config = {
            "interval": interval,
            "seed": seed,
            "dir": "./",
            "roadnetFile": output_path.name,
            "flowFile": flow_path.name,
            "rlTrafficLight": False,
            "laneChange": False,
            "saveReplay": save_replay,
            "roadnetLogFile": f"{stem}_replay_roadnet.json",
            "replayLogFile": f"{stem}_replay.txt",
        }
        with config_path.open("w") as config_file:
            json.dump(config, config_file, indent=indent)

        return {"roadnet": output_path, "flow": flow_path, "config": config_path}

    @staticmethod
    def _generate_lightphases(valid_phase_combinations, turn_movements_by_node):
        traffic_phases_by_node = {}
        timing_plans_by_node = [
            (v[0]["node"], v) for v in valid_phase_combinations.values() if v
        ]

        for node_id, combos in timing_plans_by_node:
            node_id = str(node_id)
            if node_id in traffic_phases_by_node:
                continue

            movements = turn_movements_by_node.get(node_id, {})
            if not movements:
                continue

            # availableRoadLinks are indices into the intersection's roadLinks,
            # which _build_intersections builds from this same dict in this
            # same order. Sorting here instead would silently point every phase
            # at the wrong movements. GMNS ids are "any" (utdf2gmns emits e.g.
            # "106_39_74_SBL"), so sorting numerically also raises.
            key_to_index = {str(k): i for i, k in enumerate(movements.keys())}

            # The phase list is shaped for Sim2Signal/LibSignal's CityFlow
            # loader, which hardcodes phase 0 as the yellow/guard phase and
            # treats EVERY other index as an actionable green phase. So: one
            # empty 5 s guard first, then green phases only -- no clearance
            # phases, which would each become an extra RL action. Phase times
            # after index 0 are ignored by that loader (the agent decides).
            lightphases = [{"time": 5.0, "availableRoadLinks": []}]
            road_link_indices = set()

            for combo in combos:
                valid_movements = [
                    key_to_index.get(str(mvmt)) for mvmt in combo["mvmt_ids"]
                ]
                valid_movements = [v for v in valid_movements if v is not None]
                if not valid_movements:
                    continue

                road_link_indices.update(valid_movements)
                lightphases.append(
                    {
                        "time": combo["min_green"],
                        "availableRoadLinks": sorted(valid_movements),
                    }
                )

            traffic_phases_by_node[node_id] = {
                "roadLinkIndices": sorted(road_link_indices),
                "lightphases": lightphases,
            }

        return traffic_phases_by_node

    @staticmethod
    def _build_intersections(
        selected_nodes,
        roads,
        turn_movements_by_node,
        traffic_phases_by_node,
    ):
        intersections = []

        for _, row in selected_nodes.iterrows():
            node_id = str(row["node_id"])
            traffic_light = traffic_phases_by_node.get(
                node_id,
                {
                    "roadLinkIndices": [],
                    "lightphases": [],
                },
            )

            intersections.append(
                {
                    "id": node_id,
                    "point": {
                        "x": row["x_coord"],
                        "y": row["y_coord"],
                    },
                    "width": 15,
                    "roads": [
                        road["id"]
                        for road in roads
                        if road["startIntersection"] == node_id
                        or road["endIntersection"] == node_id
                    ],
                    "roadLinks": list(
                        turn_movements_by_node.get(node_id, {}).values()
                    ),
                    "trafficLight": traffic_light,
                    "virtual": node_id not in traffic_phases_by_node,
                }
            )

        return intersections
