import argparse
from pathlib import Path


def parse_args():
    parser = argparse.ArgumentParser(
        description="Convert a GMNS signal network folder to CityFlow JSON or SUMO XML."
    )
    parser.add_argument(
        "-f", "--format",
        choices=["cityflow", "sumo"],
        default="cityflow",
        help="Target format. Defaults to cityflow.",
    )
    parser.add_argument("input", help="Path to the input GMNS folder.")
    parser.add_argument(
        "output",
        help=(
            "Path to the output directory (will be created if it doesn't "
            "exist). For cityflow this is where <basename>.json is written; "
            "for sumo it holds the .nod/.edg/.con/.tll/.net.xml set."
        ),
    )
    parser.add_argument(
        "--basename",
        default=None,
        help="Basename for the generated file(s). Defaults to the input "
             "folder name (lowercased).",
    )
    parser.add_argument(
        "--indent",
        type=int,
        default=4,
        help="(cityflow only) JSON indentation level. Defaults to 4.",
    )
    parser.add_argument(
        "--crs",
        default=None,
        help="CRS of the input node coordinates (EPSG code). Defaults to the "
             "crs field in config.csv, then 4326. Geographic lon/lat inputs "
             "are projected to UTM meters; already-projected inputs "
             "(e.g. 32619) are left as-is.",
    )
    parser.add_argument(
        "--no-netconvert",
        action="store_true",
        help="(sumo only) Skip the netconvert merge step; emit input XMLs only.",
    )
    return parser.parse_args()


def main():
    args = parse_args()

    basename = args.basename or Path(args.input).name.lower()
    output_dir = Path(args.output)

    if args.format == "cityflow":
        try:
            from converter import CityFlowConverter
        except ModuleNotFoundError as exc:
            if exc.name == "gmnspy":
                raise SystemExit("Missing required dependency: gmnspy") from exc
            raise
        output_dir.mkdir(parents=True, exist_ok=True)
        produced = CityFlowConverter(args.input, crs=args.crs).write(
            output_dir / f"{basename}.json",
            indent=args.indent,
        )
        if isinstance(produced, dict):
            for kind, p in produced.items():
                print(f"  {kind:<12} {p}")
        else:
            print(f"  roadnet      {produced}")
    else:
        try:
            from converter import SumoConverter
        except ModuleNotFoundError as exc:
            if exc.name == "gmnspy":
                raise SystemExit("Missing required dependency: gmnspy") from exc
            raise
        paths = SumoConverter(args.input, crs=args.crs).write(
            output_dir,
            basename=basename,
            run_netconvert=not args.no_netconvert,
        )
        for kind, p in paths.items():
            print(f"  {kind:<12} {p}")


if __name__ == "__main__":
    main()
