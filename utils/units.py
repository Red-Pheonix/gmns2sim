"""Unit handling driven by the GMNS `config.csv`.

GMNS does not fix units — a dataset declares them in `config.csv` via the
`short_length`, `long_length` and `speed` fields. Two datasets can both be
perfectly valid GMNS and disagree by a factor of 1609.

That matters because nothing errors when you get it wrong. A network read as
miles when it is really metres still loads, still converts, still runs; every
link is just 1609x too long. So units are resolved once, here, from the config
the dataset ships with, rather than assumed at each call site.

Default when a dataset ships no `config.csv`, or omits a field: SI. Metres and
metres per second.
"""
from dataclasses import dataclass

# multiply by these to reach the SI base unit
LENGTH_TO_M = {
    "m": 1.0, "meter": 1.0, "meters": 1.0, "metre": 1.0, "metres": 1.0,
    "km": 1000.0, "kilometer": 1000.0, "kilometers": 1000.0,
    "kilometre": 1000.0, "kilometres": 1000.0,
    "ft": 0.3048, "foot": 0.3048, "feet": 0.3048,
    "yd": 0.9144, "yard": 0.9144, "yards": 0.9144,
    "mi": 1609.344, "mile": 1609.344, "miles": 1609.344,
    "in": 0.0254, "inch": 0.0254, "inches": 0.0254,
}

SPEED_TO_MPS = {
    "mps": 1.0, "m/s": 1.0, "meters_per_second": 1.0, "meters per second": 1.0,
    "kph": 1 / 3.6, "kmh": 1 / 3.6, "km/h": 1 / 3.6, "kmph": 1 / 3.6,
    "kilometers_per_hour": 1 / 3.6, "kilometers per hour": 1 / 3.6,
    "mph": 0.44704, "mi/h": 0.44704,
    "miles_per_hour": 0.44704, "miles per hour": 0.44704,
    "fps": 0.3048, "ft/s": 0.3048,
}

DEFAULT_SHORT_LENGTH = "meter"   # lane width, row width
DEFAULT_LONG_LENGTH = "meter"    # link length
DEFAULT_SPEED = "mps"            # free speed


def _factor(name, table, default, field):
    key = str(name).strip().lower() if name is not None else ""
    if not key or key in ("nan", "none"):
        key = default
    if key not in table:
        raise ValueError(
            f"config.csv: unrecognised {field} unit {name!r}. "
            f"Known values: {', '.join(sorted(table))}"
        )
    return table[key]


@dataclass(frozen=True)
class UnitSystem:
    """The units a GMNS dataset is written in, and the factors to reach SI."""

    short_length: str = DEFAULT_SHORT_LENGTH
    long_length: str = DEFAULT_LONG_LENGTH
    speed: str = DEFAULT_SPEED

    @property
    def short_length_to_m(self) -> float:
        return _factor(self.short_length, LENGTH_TO_M, DEFAULT_SHORT_LENGTH, "short_length")

    @property
    def long_length_to_m(self) -> float:
        return _factor(self.long_length, LENGTH_TO_M, DEFAULT_LONG_LENGTH, "long_length")

    @property
    def speed_to_mps(self) -> float:
        return _factor(self.speed, SPEED_TO_MPS, DEFAULT_SPEED, "speed")

    def to_m_short(self, value):
        """Lane widths, right-of-way widths."""
        return value * self.short_length_to_m

    def to_m_long(self, value):
        """Link lengths."""
        return value * self.long_length_to_m

    def to_mps(self, value):
        """Free-flow speeds."""
        return value * self.speed_to_mps

    @classmethod
    def from_config(cls, config_df) -> "UnitSystem":
        """Build from a GMNS config.csv DataFrame. Missing fields fall back to SI."""
        if config_df is None or len(config_df) == 0:
            return cls()
        row = config_df.iloc[0]

        def pick(field, default):
            if field not in config_df.columns:
                return default
            val = row[field]
            try:
                import pandas as pd
                if pd.isna(val):
                    return default
            except Exception:
                pass
            text = str(val).strip()
            return text or default

        return cls(
            short_length=pick("short_length", DEFAULT_SHORT_LENGTH),
            long_length=pick("long_length", DEFAULT_LONG_LENGTH),
            speed=pick("speed", DEFAULT_SPEED),
        )

    def describe(self) -> str:
        return (f"lengths: {self.long_length} (links) / {self.short_length} (widths), "
                f"speed: {self.speed}")
