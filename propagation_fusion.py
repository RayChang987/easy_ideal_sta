# engine/propagation.py
from math import ceil, floor

import torch

from timing_node import TimingNode
from timing_table import get_value_from_table, get_1d_value_from_table
from math import floor, ceil


def calculate_delay_fusion(
    topo_order: list,
    cell_db,
    sdc_info,
    inst_to_clocks,
    p2p_delay,
    cell_lookup,
    type_to_cells,
):
    print("Starting Delay Calculation...")
    default_period = min(sdc_info[0][key]["period"] for key in sdc_info[0])
    default_uncertainty = max(sdc_info[0][key]["uncertainty"] for key in sdc_info[0])

    tns = 0.0
    wns = 0.0
    calculated_node_count = 0
    output_port_cap = 0.0

    reversed_topo = topo_order[::-1]

    # 1. 處理 Output/Input 初始負載與 Delay 傳遞
    for node in reversed_topo:
        if node.inst == "PIN":
            if node.pin in sdc_info[1]:
                node.fall_at = sdc_info[1][node.pin]["delay"]
                node.rise_at = sdc_info[1][node.pin]["delay"]
        arcs = node.fanout
        for arc in arcs:
            if arc.arc_type == "net":
                driver = arc.src
                load_pin = arc.dst
                if load_pin.inst != "PIN":
                    if load_pin.type in cell_lookup:
                        load_pin.is_fusion = True
                        cell_group_name, index = cell_lookup[load_pin.type]
                        lower_index = floor(load_pin.fusion_index)
                        upper_index = ceil(load_pin.fusion_index)
                        upper_type_name = type_to_cells[cell_group_name][upper_index]
                        lower_type_name = type_to_cells[cell_group_name][lower_index]
                        upper_cap = cell_db[upper_type_name]["pins"][load_pin.pin][
                            "capacitance"
                        ]
                        lower_cap = cell_db[lower_type_name]["pins"][load_pin.pin][
                            "capacitance"
                        ]
                        if lower_index == upper_index:
                            driver.load += cell_db[upper_type_name]["pins"][
                                load_pin.pin
                            ]["capacitance"]
                        else:

                            driver.load += upper_cap * (
                                load_pin.fusion_index - lower_index
                            ) + lower_cap * (upper_index - load_pin.fusion_index)
                    else:
                        load_pin.is_fusion = False
                        driver.load += cell_db[load_pin.type]["pins"][load_pin.pin][
                            "capacitance"
                        ]

    # 2. 開始 Topo 迴圈
    worst_node = None
    for node in topo_order:
        calculated_node_count += 1
        if len(node.fanin) == 0:
            continue

        max_at = 0.0
        max_rise_at = -1.0
        max_fall_at = -1.0

        best_arc = None
        best_step_delay = 0.0

        for arc in node.fanin:
            src_node = arc.src

            rise_candidates = []
            fall_candidates = []

            # --- Delay Calculation Logic ---
            if arc.arc_type == "net":
                rise_candidates.append(
                    (src_node.rise_at + 0.0, 0.0, src_node.rise_slew)
                )
                fall_candidates.append(
                    (src_node.fall_at + 0.0, 0.0, src_node.fall_slew)
                )

            elif arc.arc_type == "cell":

                key = f"{arc.src.pin}/{node.pin}/{arc.when}"
                if arc.timing_type != "None":
                    key += f"/{arc.timing_type}"

                timing_sense = cell_db[arc.src.type]["timing_arcs"][key]["timing_sense"]
                output_cap = node.load

                # 提取 Helper 函式，處理 Fusion Sizing 的 Delay 與 Slew 內插
                def get_d_s(transition_type, in_slew):
                    def fetch_val(c_type):
                        timing_table = cell_db[c_type]["timing_arcs"][key][
                            "timing_tables"
                        ]
                        delay_t = timing_table[f"cell_{transition_type}"]
                        slew_t = timing_table[f"{transition_type}_transition"]
                        d = get_value_from_table(
                            delay_t["values"],
                            delay_t["index_1"],
                            delay_t["index_2"],
                            in_slew,
                            output_cap,
                        )
                        s = get_value_from_table(
                            slew_t["values"],
                            slew_t["index_1"],
                            slew_t["index_2"],
                            in_slew,
                            output_cap,
                        )
                        return d, s

                    # 檢查 src 是否啟用了 is_fusion
                    if getattr(arc.src, "is_fusion", False):
                        load_pin.is_fusion = True
                        cell_group_name, index = cell_lookup[arc.src.type]
                        l_idx = floor(arc.src.fusion_index)
                        u_idx = ceil(arc.src.fusion_index)
                        u_type = type_to_cells[cell_group_name][u_idx]
                        l_type = type_to_cells[cell_group_name][l_idx]
                        cell_group_name, _ = cell_lookup[arc.src.type]
                        if l_idx == u_idx:
                            return fetch_val(u_type)
                        else:
                            d_u, s_u = fetch_val(u_type)
                            d_l, s_l = fetch_val(l_type)
                            weight_u = arc.src.fusion_index - l_idx
                            weight_l = u_idx - arc.src.fusion_index
                            d_interp = d_u * weight_u + d_l * weight_l
                            s_interp = s_u * weight_u + s_l * weight_l
                            return d_interp, s_interp
                    else:
                        return fetch_val(arc.src.type)

                # 基於原版 table check，這裡安全起見先確認原 type 是否存在該 transition
                base_timing_table = cell_db[arc.src.type]["timing_arcs"][key][
                    "timing_tables"
                ]

                # == RR (Rise->Rise) & FF (Fall->Fall) ==
                if timing_sense in ["positive_unate", "non_unate"]:
                    if "cell_rise" in base_timing_table:
                        d, s = get_d_s("rise", src_node.rise_slew)
                        rise_candidates.append((src_node.rise_at + d, d, s))
                    if "cell_fall" in base_timing_table:
                        d, s = get_d_s("fall", src_node.fall_slew)
                        fall_candidates.append((src_node.fall_at + d, d, s))

                # == FR (Fall->Rise) & RF (Rise->Fall) ==
                if timing_sense in ["negative_unate", "non_unate"]:
                    if "cell_rise" in base_timing_table:
                        d, s = get_d_s("rise", src_node.fall_slew)
                        rise_candidates.append((src_node.fall_at + d, d, s))
                    if "cell_fall" in base_timing_table:
                        d, s = get_d_s("fall", src_node.rise_slew)
                        fall_candidates.append((src_node.rise_at + d, d, s))

            # --- 取出最糟情況 (Max Arrival Time) ---
            if rise_candidates:
                rise_at, current_rise_delay, rise_slew = max(
                    rise_candidates, key=lambda x: x[0]
                )
            else:
                rise_at, current_rise_delay, rise_slew = -1.0, 0.0, 0.0

            if fall_candidates:
                fall_at, current_fall_delay, fall_slew = max(
                    fall_candidates, key=lambda x: x[0]
                )
            else:
                fall_at, current_fall_delay, fall_slew = -1.0, 0.0, 0.0

            arc.rise_delay = current_rise_delay
            arc.fall_delay = current_fall_delay

            if rise_at > max_rise_at:
                max_rise_at = rise_at
                max_rise_slew = rise_slew
                if rise_at > max_at:
                    max_at = rise_at
                    best_arc = arc
                    best_step_delay = current_rise_delay

            if fall_at > max_fall_at:
                max_fall_at = fall_at
                max_fall_slew = fall_slew
                if fall_at > max_at:
                    max_at = fall_at
                    best_arc = arc
                    best_step_delay = current_fall_delay

            node.rise_slew = max(node.rise_slew, rise_slew)
            node.fall_slew = max(node.fall_slew, fall_slew)

        node.rise_at = max_rise_at
        node.fall_at = max_fall_at
        node.worst_pred_arc = best_arc
        node.worst_pred_delay = best_step_delay

        # --- Endpoint Setup/Recovery Check ---
        rise_setup_delay = 0.0
        fall_setup_delay = 0.0
        final_arrival_time = 0.0
        clocked_on = cell_db.get(node.type, {}).get("clocked_on", None)

        if len(node.fanout) == 0:
            if node.type == "Port":
                final_arrival_time = node.at()
                if node.pin in sdc_info[1]:
                    final_arrival_time += sdc_info[1][node.pin]["delay"]
            else:
                if clocked_on is not None:
                    key_prefix = (
                        f"{clocked_on[1:]}/{node.pin}"
                        if clocked_on.startswith("!")
                        else f"{clocked_on}/{node.pin}"
                    )
                    keys = [
                        k
                        for k in cell_db[node.type]["timing_arcs"].keys()
                        if k.startswith(key_prefix)
                    ]

                    def get_setup_value(
                        c_type, arc_key, constraint_type, n_slew, c_slew
                    ):
                        if arc_key not in cell_db[c_type]["timing_arcs"]:
                            return 0.0
                        t_table = cell_db[c_type]["timing_arcs"][arc_key][
                            "timing_tables"
                        ]
                        if constraint_type in t_table:
                            dt = t_table[constraint_type]
                            return get_value_from_table(
                                dt["values"],
                                dt["index_1"],
                                dt["index_2"],
                                n_slew,
                                c_slew,
                            )
                        return 0.0

                    for key in keys:
                        clock_slew = 0.0  # 依照你原本的設定

                        if getattr(node, "is_fusion", False):
                            cell_group_name, _ = cell_lookup[node.type]
                            l_idx = floor(node.fusion_index)
                            u_idx = ceil(node.fusion_index)
                            u_type = type_to_cells[cell_group_name][u_idx]
                            l_type = type_to_cells[cell_group_name][l_idx]

                            def interp_setup(constraint_type, n_slew):
                                val_u = get_setup_value(
                                    u_type, key, constraint_type, n_slew, clock_slew
                                )
                                if l_idx == u_idx:
                                    return val_u
                                val_l = get_setup_value(
                                    l_type, key, constraint_type, n_slew, clock_slew
                                )
                                return val_u * (node.fusion_index - l_idx) + val_l * (
                                    u_idx - node.fusion_index
                                )

                            rise_setup_val = interp_setup(
                                "rise_constraint", node.rise_slew
                            )
                            fall_setup_val = interp_setup(
                                "fall_constraint", node.fall_slew
                            )
                        else:
                            rise_setup_val = get_setup_value(
                                node.type,
                                key,
                                "rise_constraint",
                                node.rise_slew,
                                clock_slew,
                            )
                            fall_setup_val = get_setup_value(
                                node.type,
                                key,
                                "fall_constraint",
                                node.fall_slew,
                                clock_slew,
                            )

                        rise_setup_delay = max(rise_setup_val, rise_setup_delay)
                        fall_setup_delay = max(fall_setup_val, fall_setup_delay)

                final_arrival_time = max(
                    node.rise_at + rise_setup_delay, node.fall_at + fall_setup_delay
                )

            # --- WNS / TNS Calculation ---
            clock_period = default_period - default_uncertainty
            if node.type == "Port":
                pass
            elif clocked_on is not None and node.inst in inst_to_clocks:
                inst_clk = sdc_info[0][inst_to_clocks[node.inst]]
                clock_period = inst_clk["period"] - inst_clk["uncertainty"]
            else:
                continue

            if final_arrival_time > clock_period:
                slack = clock_period - final_arrival_time
                tns += abs(slack)
                if abs(slack) > wns:
                    worst_node = node
                    wns = abs(slack)

        if best_arc:
            best_arc.real_rise_delay, best_arc.real_fall_delay = p2p_delay.get(
                f"{best_arc.src.inst}/{best_arc.src.pin}", {}
            ).get(f"{best_arc.dst.inst}/{best_arc.dst.pin}", (0.0, 0.0))

    print("Delay Calculation Done.")
    print(f"TNS: -{tns/1000:.2f} ns, WNS: -{wns/1000:.2f} ns")
    if worst_node:
        print(f"Worst Node: {worst_node}, AT={worst_node.at()/1000:.2f} ns")
        report_instance_path(worst_node)


def report_instance_path(end_node):
    """
    report_instance_path
    """
    if end_node is None:
        return

    print("=" * 60)
    print(f"Critical Path Report for: {end_node.inst}")

    print(f"Worst Arrival Time: {end_node.at()/1000:.2f} ps")
    print("=" * 60)

    # 1. Backtrace (回溯)
    path_stack = []
    curr = end_node

    while curr is not None:
        # 把當前節點加入路徑
        path_stack.append(curr)

        # 透過 worst_pred_arc 找上一個節點
        if curr.worst_pred_arc:
            curr = curr.worst_pred_arc.src
        else:
            curr = None  # 到達 PI 或起點

    # 2. Print Forward (正向列印)
    # path_stack 裡面是 [Target, ..., ..., PI]
    # 我們要反過來印: PI -> ... -> Target

    # 彈出第一個 (PI)
    start_node = path_stack.pop()
    print(f"Startpoint: {start_node.name} (AT: {start_node.at()/1000:.2f})")
    while path_stack:
        next_node = path_stack.pop()

        # 找出它們中間的 delay (存在 next_node.worst_pred_delay)
        rise_delay = next_node.worst_pred_arc.rise_delay
        fall_delay = next_node.worst_pred_arc.fall_delay
        arc_type = next_node.worst_pred_arc.arc_type

        arrow = "->"
        if arc_type == "net":
            arrow = "--(net)-->"
        if arc_type == "cell":
            arrow = "--(cell)-->"
        if arc_type == "cell":
            print(f"Load: {next_node.load}")
            print(f"Fall Slew: {start_node.fall_slew}")
            print(f"Rise Slew: {start_node.rise_slew}")
            print(f"Output Fall Slew: {next_node.fall_slew}")
            print(f"Output Rise Slew: {next_node.rise_slew}")
        print(
            f"Rise: {start_node.inst}/{start_node.pin} ({start_node.type}) {arrow} {next_node.inst}/{next_node.pin} ({next_node.type}) : delay {rise_delay/1000:.2f} ps (AT: {next_node.rise_at/1000:.4f})"
        )
        print(
            f"Fall: {start_node.inst}/{start_node.pin} ({start_node.type}) {arrow} {next_node.inst}/{next_node.pin} ({next_node.type}): delay {fall_delay/1000:.2f} ps (AT: {next_node.fall_at/1000:.4f})"
        )

        # 前進一步
        start_node = next_node

    print("=" * 60)


def calculate_power(topo_order: list[TimingNode], cell_db, sdc_info):
    """
    Calculate_power

    """
    print("Starting Power Calculation...")
    internal_power = 0
    switching_power = 0
    default_period = min(sdc_info[0][key]["period"] for key in sdc_info[0])
    freq = default_period > 0 and 1e9 / default_period or 1e9 / 1000
    for node in topo_order:
        if node.type not in cell_db:
            continue
        power_pin = cell_db[node.type]["pins"][node.pin]["related_power_pin"]
        ground_pin = cell_db[node.type]["pins"][node.pin]["related_ground_pin"]
        if node.type in cell_db:
            power_tables_list = cell_db[node.type]["power_table"]
            keys = []
            if power_pin is not None:
                keys.append(node.pin + "/" + power_pin)
            if ground_pin is not None:
                keys.append(node.pin + "/" + ground_pin)

            # print(keys)
            rise_internal_power = 0.0
            fall_internal_power = 0.0
            rise_internal_power_count = 0.0
            fall_internal_power_count = 0.0
            for key in keys:
                if key in power_tables_list:

                    power_groups = power_tables_list[key]

                    # rise
                    if "rise_power" in power_groups:
                        for power_table in power_groups["rise_power"]:
                            if "index_2" in power_table:
                                rise_internal_power += get_value_from_table(
                                    power_table["values"],
                                    power_table["index_1"],
                                    power_table["index_2"],
                                    node.rise_slew,
                                    node.load,
                                )
                                rise_internal_power_count += 1
                            elif "index_1" in power_table:
                                rise_internal_power += get_1d_value_from_table(
                                    power_table["values"],
                                    power_table["index_1"],
                                    node.rise_slew,
                                )
                                rise_internal_power_count += 1

                    # fall
                    if "fall_power" in power_groups:
                        for power_table in power_groups["fall_power"]:
                            if "index_2" in power_table:
                                fall_internal_power += get_value_from_table(
                                    power_table["values"],
                                    power_table["index_1"],
                                    power_table["index_2"],
                                    node.fall_slew,
                                    node.load,
                                )
                                fall_internal_power_count += 1
                            elif "index_1" in power_table:
                                fall_internal_power += get_1d_value_from_table(
                                    power_table["values"],
                                    power_table["index_1"],
                                    node.fall_slew,
                                )
                                fall_internal_power_count += 1
            if rise_internal_power_count > 0:
                internal_power += (
                    (rise_internal_power / rise_internal_power_count)
                    * 0.2
                    * freq
                    * 1e-6
                )  # uW
            if fall_internal_power_count > 0:
                internal_power += (
                    (fall_internal_power / fall_internal_power_count)
                    * 0.2
                    * freq
                    * 1e-6
                )  # uW

    for node in topo_order:
        vdd = 0.7
        energy_per_transition = 0.5 * node.load * (vdd**2)
        density = freq * 0.2
        power_watts = (energy_per_transition * 1e-12) * density
        switching_power += power_watts * 1e6
    print(f"Internal Power: {internal_power}")
    print(f"Switching Power: {switching_power}")
