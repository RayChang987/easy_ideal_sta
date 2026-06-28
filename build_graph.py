import json
import sys
from collections import defaultdict
from typing import Dict

from timing_graph import TimingGraph
import parse_cell_db


def build_timing_graph(
    json_file: str,
    top_module: str,
    cell_db: Dict[str, parse_cell_db.cell_info_t],
    sdc_data,
) -> TimingGraph:
    with open(json_file) as f:
        netlist = json.load(f)

    if "modules" not in netlist or top_module not in netlist["modules"]:
        print(f"Error: Module {top_module} not found in JSON.")
        sys.exit(1)

    mod   = netlist["modules"][top_module]
    cells = mod.get("cells", {})
    ports = mod.get("ports", {})

    tg           = TimingGraph()
    net_drivers  = defaultdict(list)  # net_id -> [(inst, pin, cell_type)]
    net_loads    = defaultdict(list)
    inst_to_clocks  = {}
    id_to_clock_name = {}   # net_id -> clock_name
    is_clock_net = set()
    port_to_clock = sdc_data.port_to_clock

    # ── Ports ──────────────────────────────────────────────────────────────────
    print("Building Ports...")
    for port_name, port_data in ports.items():
        tg.get_node("PIN", port_name, "Port")
        for net_id in port_data["bits"]:
            if port_name in port_to_clock:
                is_clock_net.add(net_id)
                id_to_clock_name[net_id] = port_to_clock[port_name]
            if port_data["direction"] == "input":
                net_drivers[net_id].append(("PIN", port_name, "Port"))
            elif port_data["direction"] == "output":
                net_loads[net_id].append(("PIN", port_name, "Port"))

    # ── Cells ──────────────────────────────────────────────────────────────────
    print("Building Cells...")
    for inst_name, cell_data in cells.items():
        cell_type   = cell_data["type"]
        connections = cell_data["connections"]

        if cell_type not in cell_db:
            print(f"[Warning] Unknown cell type: {cell_type} @ {inst_name}")
            continue

        lib_pins = cell_db[cell_type].pins
        lib_arcs = cell_db[cell_type].timing_arcs

        for arc_key, _ in lib_arcs.items():
            parts      = arc_key.split("/")
            src_pin    = parts[0]
            dst_pin    = parts[1]
            when       = parts[2] if len(parts) > 2 else "None"
            timing_type = parts[3] if len(parts) > 3 else "None"
            if src_pin in connections and dst_pin in connections:
                tg.add_arc(
                    tg.get_node(inst_name, src_pin, cell_type),
                    tg.get_node(inst_name, dst_pin, cell_type),
                    arc_type="cell", when=when, timing_type=timing_type,
                )

        for pin_name, nets in connections.items():
            pin_dir = lib_pins[pin_name].direction if pin_name in lib_pins else None
            for net_id in nets:
                if net_id in is_clock_net:
                    inst_to_clocks[inst_name] = id_to_clock_name[net_id]
                if pin_dir == "output":
                    net_drivers[net_id].append((inst_name, pin_name, cell_type))
                elif pin_dir == "input":
                    net_loads[net_id].append((inst_name, pin_name, cell_type))

    # ── Net arcs ───────────────────────────────────────────────────────────────
    print("Building Net Arcs...")
    for net_id, drivers in net_drivers.items():
        for d_inst, d_pin, d_type in drivers:
            src = tg.get_node(d_inst, d_pin, d_type)
            for l_inst, l_pin, l_type in net_loads.get(net_id, []):
                tg.add_arc(src, tg.get_node(l_inst, l_pin, l_type), arc_type="net")

    tg.instance_to_clocks = inst_to_clocks
    return tg
