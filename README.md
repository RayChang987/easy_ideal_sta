# Easy STA

Easy STA is a Python-based static timing analysis and gate-sizing prototype for JSON netlists (Yosys-style), SDC constraints, and ASAP7 liberty data.

It builds a timing graph, propagates delay/slack, and generates an OpenROAD-compatible TCL script with `replace_cell` commands for resizing.

## Features

- Parse clock and I/O timing constraints from SDC
- Parse multi-library ASAP7 liberty files into an internal cell database
- Build a timing graph from a JSON netlist
- Perform delay/slack propagation on topological order
- Apply a simple sizing strategy on violating endpoints
- Export sizing actions as a TCL script for OpenROAD

## Repository Overview

- `main.py`: Main entry point
- `build_graph.py`: Timing graph construction from netlist JSON
- `parse_sdc.py`: SDC parser (`create_clock`, max I/O delay, clock uncertainty)
- `read_lib.py` / `parse_lib.py` / `parse_cell_db.py`: Liberty loading and cell DB build
- `propagation.py`: Delay/slack propagation core
- `resizer.py`: Sizing loop and TCL generation
- `parse_cell_rank.py`: Loads gate ranking CSV and maps equivalent cell options
- `openroad_interface.py`: Optional persistent OpenROAD process wrapper

## Requirements

- Python 3.10+ (tested in Python 3.12 virtual environment)
- Linux environment (OpenROAD workflow assumptions)
- Python packages from `requirements.txt`

Install dependencies:

```bash
pip install -r requirements.txt
```

## Required Input Data

Before running `main.py`, ensure these are available:

1. Netlist JSON file (contains `modules` and target top module)
2. Top module name (must match a module in JSON)
3. SDC file
4. DEF file path (accepted by CLI; currently not consumed in `main.py` logic)
5. Output TCL path
6. `gate_ranking_all_cells_analysis.csv` in project root
7. ASAP7 liberty files under:
   - `/ISPD26-Contest/Platform/ASAP7/lib`

> Note: `read_lib.py` currently uses a hardcoded liberty directory. If your libraries are elsewhere, edit `read_lib.py`.

## Usage

```bash
yosys -p "read_verilog <.v>; hierarchy -auto-top; write_json output.json"
python main.py <json_file> <top_module> <sdc_file> <def_file> <output_tcl_file>
```

Example:

```bash
python main.py \
  aes_cipher_top.json \
  aes_cipher_top \
  /path/to/contest.sdc \
  /path/to/contest.def \
  resize_result.tcl
```

## What the Flow Does

1. Load SDC constraints
2. Load liberty cache (`raw_libs.pkl`) or parse liberty sources
3. Build cell database from parsed liberty data
4. Build timing graph from netlist JSON
5. Topologically sort graph nodes
6. Load gate ranking CSV
7. Run optimization pass and emit `replace_cell` commands

## Output

Primary output:

- A TCL script (your `output_tcl_file`) containing commands like:

```tcl
replace_cell <instance_name> <new_cell_name>
```

Auxiliary cache:

- `raw_libs.pkl` (generated automatically after first successful liberty parse)


## Known Limitations

- Liberty path is hardcoded in `read_lib.py`
- Current optimizer in `resizer.py` runs a minimal iteration strategy (`MAX_IT = 1`)
- `def_file` argument is currently passed through CLI but not used by `main.py`
- `run_all.bash` appears to target an older invocation form and may require updates

## Troubleshooting

- **"No libraries loaded. Exiting."**
  - Check liberty file path and file availability
- **Module not found in JSON**
  - Verify `<top_module>` matches JSON module name exactly
- **CSV loading errors**
  - Confirm `gate_ranking_all_cells_analysis.csv` exists and has expected columns:
    `Target_Cell_Type`, `Cell_Name`, `Delay_Raw`, `Power_Raw`

## License

No license file is currently included in this repository.
