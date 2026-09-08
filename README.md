# gmns2sim

Convert a [GMNS](https://github.com/zephyr-data-specs/GMNS) network into a simulator's
native format. SUMO and CityFlow are supported.

The repo is still named `GMNS2UTDF`; the installable package is `gmns2sim`. For UTDF
*input*, see [utdf2gmns](https://github.com/xyluo25/utdf2gmns).

## Install

```bash
pip install git+https://github.com/Red-Pheonix/GMNS2UTDF.git
pip install eclipse-sumo      # or "gmns2sim[sumo]" — provides netconvert
```

`netconvert` is only needed for the `.net.xml` merge step; skip it with `--no-netconvert`.

Development install:

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

```python
from converter import SumoConverter, CityFlowConverter

SumoConverter("datasets/Arlington_Signals").write("out/", basename="arlington")
CityFlowConverter("datasets/Arlington_Signals").write("out/")
```

SUMO output is the `.nod` / `.edg` / `.con` / `.tll` XML set, plus a merged `.net.xml`
unless `--no-netconvert`. CityFlow output is a single roadnet JSON.

## Input

Read through `gmnspy`, which validates against the GMNS spec. Required tables are
`node`, `link`, `lane` and `movement`; signal control comes from `signal_timing_plan`,
`signal_timing_phase` and `signal_phase_mvmt` when present. Without signal tables, a
default one-phase-per-approach plan is synthesized and a warning printed.

Example datasets: `datasets/Arlington_Signals` (full signal tables, US units) and
`datasets/tempe_3` (geometry only, no `config.csv`).

## Units and CRS

GMNS does not fix units — a dataset declares them in `config.csv`:

| field | applies to | example |
|---|---|---|
| `long_length` | link length | `mile`, `meter`, `kilometer` |
| `short_length` | lane and right-of-way widths | `foot`, `meter` |
| `speed` | free-flow speed | `mph`, `mps`, `kph` |
| `crs` | coordinates | `32619`, `4326` |

Everything is converted to SI internally. A missing `config.csv` or field falls back to
metres, m/s and EPSG:4326; `--crs` overrides the CRS. Geographic lon/lat is projected to
UTM metres, already-projected input is used as-is.

Wrong units or CRS raise no error — the network just converts with every link 1609× too
long, or lands in the wrong place. Check the resolved values the converter prints:

```
  units: lengths: mile (links) / foot (widths), speed: mph
  crs  : 32619
```

## Known issues

- `netconvert` fails on `datasets/tempe_3` with
  `Invalid linkIndex 8 for traffic light '34' with 8 links` — an off-by-one in the
  generated `.tll.xml`. Use `--no-netconvert` there. Arlington is fine.
- Top-level module names (`gmns`, `converter`, `utils`) may collide with other installed
  packages.
