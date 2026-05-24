import argparse
import json
import shutil
import tempfile
from pathlib import Path


def parse_args():
    parser = argparse.ArgumentParser(
        description="Load a CityFlow roadnet JSON and run a short simulation."
    )
    parser.add_argument(
        "roadnet",
        nargs="?",
        default="output/cityflow/Arlington/arlington_net.json",
        help="Path to the CityFlow roadnet JSON.",
    )
    parser.add_argument(
        "--flow",
        help="Optional CityFlow flow JSON. Defaults to an empty flow.",
    )
    parser.add_argument(
        "--steps",
        type=int,
        default=10,
        help="Number of simulation steps to run. Defaults to 10.",
    )
    parser.add_argument(
        "--thread-num",
        type=int,
        default=1,
        help="CityFlow engine thread count. Defaults to 1.",
    )
    parser.add_argument(
        "--interval",
        type=float,
        default=1.0,
        help="Simulation interval in seconds. Defaults to 1.0.",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=0,
        help="Random seed. Defaults to 0.",
    )
    parser.add_argument(
        "--save-replay",
        action="store_true",
        help="Write CityFlow replay files into the temporary run directory.",
    )
    return parser.parse_args()


def write_config(run_dir, roadnet_path, flow_path, args):
    roadnet_copy = run_dir / roadnet_path.name
    flow_copy = run_dir / flow_path.name
    shutil.copyfile(roadnet_path, roadnet_copy)
    shutil.copyfile(flow_path, flow_copy)

    config = {
        "interval": args.interval,
        "seed": args.seed,
        "dir": str(run_dir),
        "roadnetFile": roadnet_copy.name,
        "flowFile": flow_copy.name,
        "rlTrafficLight": True,
        "saveReplay": args.save_replay,
        "roadnetLogFile": "roadnet_log.json",
        "replayLogFile": "replay_log.txt",
    }

    config_path = run_dir / "cityflow_config.json"
    with config_path.open("w") as config_file:
        json.dump(config, config_file, indent=4)

    return config_path


def run_simulation(args):
    try:
        import cityflow
    except ModuleNotFoundError as exc:
        raise SystemExit("Missing required dependency: cityflow") from exc

    roadnet_path = Path(args.roadnet).resolve()
    if not roadnet_path.exists():
        raise SystemExit(f"Roadnet file does not exist: {roadnet_path}")

    with tempfile.TemporaryDirectory(prefix="cityflow_run_") as temp_dir:
        run_dir = Path(temp_dir)

        if args.flow:
            flow_path = Path(args.flow).resolve()
            if not flow_path.exists():
                raise SystemExit(f"Flow file does not exist: {flow_path}")
        else:
            flow_path = run_dir / "empty_flow.json"
            with flow_path.open("w") as flow_file:
                json.dump([], flow_file)

        config_path = write_config(run_dir, roadnet_path, flow_path, args)
        engine = cityflow.Engine(str(config_path), thread_num=args.thread_num)

        for _ in range(args.steps):
            engine.next_step()

        print(f"Ran {args.steps} CityFlow steps")
        print(f"Vehicles still running: {engine.get_vehicle_count()}")
        print(f"Average travel time: {engine.get_average_travel_time()}")


def main():
    args = parse_args()
    run_simulation(args)


if __name__ == "__main__":
    main()
