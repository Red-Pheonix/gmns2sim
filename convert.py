import argparse


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
            "For cityflow: path to the output JSON file. "
            "For sumo: path to the output directory (will be created)."
        ),
    )
    parser.add_argument(
        "--indent",
        type=int,
        default=4,
        help="(cityflow only) JSON indentation level. Defaults to 4.",
    )
    parser.add_argument(
        "--basename",
        default=None,
        help="(sumo only) Basename for the generated .nod/.edg/.con/.tll/.net files. "
             "Defaults to the input folder name (lowercased).",
    )
    parser.add_argument(
        "--no-netconvert",
        action="store_true",
        help="(sumo only) Skip the netconvert merge step; emit input XMLs only.",
    )
    return parser.parse_args()


def main():
    args = parse_args()

    if args.format == "cityflow":
        try:
            from converter import CityFlowConverter
        except ModuleNotFoundError as exc:
            if exc.name == "gmnspy":
                raise SystemExit("Missing required dependency: gmnspy") from exc
            raise
        output_path = CityFlowConverter(args.input).write(args.output, indent=args.indent)
        print(f"Wrote CityFlow network to {output_path}")
    else:
        try:
            from converter import SumoConverter
        except ModuleNotFoundError as exc:
            if exc.name == "gmnspy":
                raise SystemExit("Missing required dependency: gmnspy") from exc
            raise
        paths = SumoConverter(args.input).write(
            args.output,
            basename=args.basename,
            run_netconvert=not args.no_netconvert,
        )
        for kind, p in paths.items():
            print(f"  {kind:<12} {p}")


if __name__ == "__main__":
    main()
