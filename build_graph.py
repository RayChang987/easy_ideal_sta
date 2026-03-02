# graph/build_graph.py
import json
from collections import defaultdict
import sys
from timing_graph import TimingGraph
import parse_cell_db


def build_timing_graph(
    json_file: str,
    top_module: str,
    cell_db: parse_cell_db.Dict[str, parse_cell_db.cell_info_t],
    sdc_data,
):
    with open(json_file) as f:
        netlist = json.load(f)

    if "modules" not in netlist or top_module not in netlist["modules"]:
        print(f"Error: Module {top_module} not found in JSON.")
        sys.exit(1)

    mod = netlist["modules"][top_module]
    cells = mod.get("cells", {})
    ports = mod.get("ports", {})  # Top Level Ports (PI/PO)
    # print(ports)
    # print(cells)
    tg = TimingGraph()

    # --------------------------------------------------------
    # Step 1: 建立 Ports (Primary Inputs/Outputs) 並準備 Net 資訊
    # --------------------------------------------------------
    net_drivers = defaultdict(
        list
    )  # net_id -> list of (inst_name, pin_name, cell_type)
    net_loads = defaultdict(list)  # net_id -> list of (inst_name, pin_name, cell_type)
    inst_to_clocks = dict()  # instance_name -> clock_name (for clocked cells)
    id_to_port_name = dict()  # net_id -> port_name (for clock nets)
    is_clock_net = set()  # whether this net is a clock net
    port_to_clock = sdc_data.port_to_clock

    print("Building Ports...")
    for port_name, port_data in ports.items():
        direction = port_data["direction"]
        bits = port_data["bits"]  # List of Net IDs
        # 建立 Port 節點
        # 我們用 inst="PIN" 來代表這是 Top Level Port
        port_node = tg.get_node("PIN", port_name, "Port")
        for net_id in bits:
            if port_name in port_to_clock:
                is_clock_net.add(net_id)
                id_to_port_name[net_id] = port_to_clock[port_name]

            if direction == "input":
                # PI 是 Net 的 Driver (訊號從外面進來)
                net_drivers[net_id].append(("PIN", port_name, "Port"))
            elif direction == "output":
                # PO 是 Net 的 Load (訊號要送出去)
                net_loads[net_id].append(("PIN", port_name, "Port"))

    # --------------------------------------------------------
    # Step 2: 建立 Cell Internal Arcs 並記錄 Net 連接
    # --------------------------------------------------------
    print("Building Cells...")
    for inst_name, cell_data in cells.items():
        cell_type = cell_data["type"]
        connections = cell_data["connections"]

        if cell_type not in cell_db:
            print(f"[Warning] Unknown cell type: {cell_type} @ {inst_name}")
            continue
        lib_pins = cell_db[cell_type].pins
        lib_arcs = cell_db[cell_type].timing_arcs
        for lib_arc_key, lib_arc in lib_arcs.items():
            key_parts = lib_arc_key.split("/")
            src_pin = key_parts[0]
            dst_pin = key_parts[1]
            when = key_parts[2] if len(key_parts) > 2 else "None"
            timing_type = key_parts[3] if len(key_parts) > 3 else "None"
            if src_pin in connections and dst_pin in connections:
                src_node = tg.get_node(inst_name, src_pin, cell_type)
                dst_node = tg.get_node(inst_name, dst_pin, cell_type)
                tg.add_arc(
                    src_node,
                    dst_node,
                    arc_type="cell",
                    when=when,
                    timing_type=timing_type,
                )

        for pin_name, nets in connections.items():
            pin_dir = "Unknown"
            if pin_name in lib_pins:
                pin_dir = lib_pins[pin_name].direction
            for net_id in nets:
                if net_id in is_clock_net:
                    inst_to_clocks[inst_name] = id_to_port_name[net_id]
                if pin_dir == "output":
                    net_drivers[net_id].append((inst_name, pin_name, cell_type))
                elif pin_dir == "input":
                    net_loads[net_id].append((inst_name, pin_name, cell_type))
                else:
                    pass

    # --------------------------------------------------------
    # Step 3: 建立 Net Arcs (Driver -> Load)
    # --------------------------------------------------------
    print("Building Net Arcs...")
    for net_id, drivers in net_drivers.items():
        loads = net_loads.get(net_id, [])
        if not drivers:
            pass

        if not loads:
            pass

        for driver_inst, driver_pin, driver_cell_type in drivers:
            src_node = tg.get_node(driver_inst, driver_pin, driver_cell_type)
            for load_inst, load_pin, load_cell_type in loads:
                dst_node = tg.get_node(load_inst, load_pin, load_cell_type)
                tg.add_arc(src_node, dst_node, arc_type="net")
    tg.instance_to_clocks = inst_to_clocks
    return tg
