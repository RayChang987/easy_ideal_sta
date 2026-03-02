import sys
import os

from parse_cell_db import load_cell_db
from parse_sdc import load_sdc
from parse_sdf import load_sdf
from parse_cell_rank import load_gate_rank
from parse_lib import load_libs
from build_graph import build_timing_graph
from resizer import optimize

LIB_CACHE_FILE = "raw_libs.pkl"
CSV_FILE = "gate_ranking_all_cells_analysis.csv"
if __name__ == "__main__":

    if len(sys.argv) != 6:
        print(
            "Usage: python main.py <json_file> <top_module> <sdc_file> <def_file> <output_tcl_file>"
        )
        sys.exit(1)

    json_file = sys.argv[1]
    top_module = sys.argv[2]
    sdc_file = sys.argv[3]
    def_file = sys.argv[4]
    output_tcl_file = sys.argv[5]
    # sdf_file = sys.argv[5]
    # version = ""
    # if len(sys.argv) == 7:
    #     version = sys.argv[6].lower()

    sdc_info = load_sdc(sdc_file)
    raw_libs = load_libs(LIB_CACHE_FILE)
    if not raw_libs:
        print("No libraries loaded. Exiting.")
        sys.exit(1)

    print("Extracting Cell Database...")
    cell_db = load_cell_db(raw_libs)
    tg = build_timing_graph(json_file, top_module, cell_db, sdc_info)
    order = tg.topo_sort()
    if order:
        print(f"[SUCCESS] Topological sort finished. Length: {len(order)}")
    else:
        print("[FAIL] Graph contains cycles or is empty.")

    print("Running Delay Calculation...")
    # sdf_file = 'aes_cipher_top.sdf'
    # sdf_data = load_sdf(sdf_file)



    gate_rank, cell_lookup, type_to_cells = load_gate_rank(CSV_FILE)

    optimize(
        topo_order=order,
        cell_db=cell_db,
        sdc_info=sdc_info,
        inst_to_clocks=tg.instance_to_clocks,
        p2p_delay=None,
        cell_lookup=cell_lookup,
        type_to_cells=type_to_cells,
        output_file=output_tcl_file,
    )
