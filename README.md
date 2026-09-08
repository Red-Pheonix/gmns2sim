# gmns2sim

Convert a [GMNS](https://github.com/zephyr-data-specs/GMNS) network into a simulator's
native format. SUMO and CityFlow are supported.

> **Note on the repo name.** The directory is still called `GMNS2UTDF`, which is
> backwards — this converts GMNS *to* simulators, it does not produce UTDF. The
> installable package is `gmns2sim`. Worth renaming the repo at some point.

## Where this sits

GMNS is the hub format, so a full pipeline is two independent halves:

```
        your source                    your target
    ┌─────────────────┐            ┌─────────────────┐
    │  UTDF / OSM /   │            │  SUMO           │
    │  Synchro / ...  │──► GMNS ──►│  CityFlow       │
    └─────────────────┘            └─────────────────┘
         x2gmns                         gmns2y   ← this repo
```

That split is the point: whoever writes an `x2gmns` for their own source data gets every
`gmns2y` target for free, and vice versa. This repo only ever reads GMNS.

For UTDF input, see [utdf2gmns](https://github.com/xyluo25/utdf2gmns).

## Install

```bash
pip install git+https://github.com/Red-Pheonix/GMNS2UTDF.git
```

For the `.net.xml` merge step you also need SUMO's `netconvert`. The simplest route,
which needs no system install and works on macOS, Linux and Colab:

```bash
pip install eclipse-sumo      # or: pip install "gmns2sim[sumo]"
```

Skip it with `--no-netconvert` if you only want the input XMLs.

For development, clone and install editable:

```bash
git clone https://github.com/Red-Pheonix/GMNS2UTDF.git && cd GMNS2UTDF
pip install -e .
```

## Use

```bash
gmns2sim -f sumo     path/to/gmns_folder  out/
gmns2sim -f cityflow path/to/gmns_folder  out/
gmns2sim -f sumo --no-netconvert datasets/tempe_3 out/
```

Or from Python:

```python
from converter import SumoConverter, CityFlowConverter

SumoConverter("datasets/Arlington_Signals").write("out/", basename="arlington")
CityFlowConverter("datasets/Arlington_Signals").write("out/")
```

SUMO output is the `.nod` / `.edg` / `.con` / `.tll` XML set, plus a merged `.net.xml`
unless `--no-netconvert`. CityFlow output is a single roadnet JSON.

## Units

GMNS does not fix units. A dataset declares them in `config.csv`:

| field | applies to | example |
|---|---|---|
| `long_length` | link length | `mile`, `meter`, `kilometer` |
| `short_length` | lane and right-of-way widths | `foot`, `meter` |
| `speed` | free-flow speed | `mph`, `mps`, `kph` |

Units are read from that file and everything is converted to SI internally. **A dataset
with no `config.csv`, or with a field missing, is assumed to be metres and m/s.**

This matters more than it sounds. Two datasets can both be perfectly valid GMNS and
disagree by a factor of 1609, and reading one as the other raises no error — the network
loads, converts and runs, with every link 1609× too long. If your output looks strange,
check `config.csv` before anything else. The converter prints the units it resolved:

```
  units: lengths: mile (links) / foot (widths), speed: mph
  crs  : 32619
```

## Coordinate reference system

Also taken from `config.csv` (the `crs` field), overridable with `--crs`. Geographic
lon/lat input (EPSG:4326) is projected to UTM metres; already-projected input is used
as-is. Falls back to EPSG:4326 when nothing declares one.

Reading projected metres as if they were lon/lat produces no error either, just a
network in the wrong place — so the declared value is preferred over any assumption.

## Input

Read through `gmnspy`, which validates against the GMNS spec. Required tables are
`node`, `link`, `lane` and `movement`; signal control comes from `signal_timing_plan`,
`signal_timing_phase` and `signal_phase_mvmt` when present. When no signal tables are
found, a default one-phase-per-approach plan is synthesized and a warning is printed.

Two example datasets are included: `datasets/Arlington_Signals` (full signal tables,
US units) and `datasets/tempe_3` (geometry only, no `config.csv`).

## Known issues

- `netconvert` fails on `datasets/tempe_3` with
  `Invalid linkIndex 8 for traffic light '34' with 8 links` — an off-by-one in the
  generated `.tll.xml`. Use `--no-netconvert` for that dataset. Arlington is fine.
- The top-level module names (`gmns`, `converter`, `utils`) are generic enough to
  collide with other installed packages. Worth moving under a single namespace.
