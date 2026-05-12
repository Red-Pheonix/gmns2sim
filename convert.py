import argparse


def parse_args():
    parser = argparse.ArgumentParser(
        description="Convert a GMNS signal network folder to a CityFlow network JSON."
    )
    parser.add_argument("input", help="Path to the input GMNS folder.")
    parser.add_argument("output", help="Path where the CityFlow JSON should be written.")
    parser.add_argument(
        "--indent",
        type=int,
        default=4,
        help="JSON indentation level. Defaults to 4.",
    )
    return parser.parse_args()


def main():
    args = parse_args()

    try:
        from converter import CityFlowConverter
    except ModuleNotFoundError as exc:
        if exc.name == "gmnspy":
            raise SystemExit("Missing required dependency: gmnspy") from exc
        raise

    output_path = CityFlowConverter(args.input).write(args.output, indent=args.indent)
    print(f"Wrote CityFlow network to {output_path}")


if __name__ == "__main__":
    main()
