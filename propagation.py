# engine/propagation.py
from timing_node import TimingNode
from timing_table import get_value_from_table, get_1d_value_from_table
import parse_cell_db
import parse_sdc


def calculate_node(
    node: TimingNode,
    cell_db: dict[str, parse_cell_db.cell_info_t],
    sdc_data: parse_sdc.sdc_data_t,
    inst_to_clocks,
    p2p_delay,
    type_to_cells,
):
    max_at = 0.0
    max_rise_at = -1.0
    max_fall_at = -1.0
    best_arc = None
    best_step_delay = 0.0
    default_period = min(sdc_data.clocks[key].period for key in sdc_data.clocks)
    default_uncertainty = max(
        sdc_data.clocks[key].uncertainty for key in sdc_data.clocks
    )
    for arc in node.fanin:
        src_node = arc.src
        if src_node.sizable:
            src_type = type_to_cells[src_node.cell_gp][src_node.type_id]
        else:
            src_type = src_node.type
        # 用來裝載 (Arrival_Time, Delay, Slew) 的候選清單
        rise_candidates = []
        fall_candidates = []

        # arc.real_delay = p2p_delay.get(f"{arc.src.inst}/{arc.src.pin}", {}).get(
        #     f"{arc.dst.inst}/{arc.dst.pin}", (0, 0)
        # )
        # --- Delay Calculation Logic ---
        if arc.arc_type == "net":
            # Wire delay (Positive Unate behavior)

            rise_candidates.append(
                # (src_node.rise_at + arc.real_delay[0], arc.real_delay[0], src_node.rise_slew)
                (src_node.rise_at + 0, 0, src_node.rise_slew)
            )
            fall_candidates.append(
                # (src_node.fall_at + arc.real_delay[1], arc.real_delay[1], src_node.fall_slew)
                (src_node.fall_at + 0, 0, src_node.fall_slew)
            )

        elif arc.arc_type == "cell":
            key = f"{arc.src.pin}/{node.pin}/{arc.when}"
            if arc.timing_type != "None":
                key += f"/{arc.timing_type}"

            timing_table = cell_db[src_type].timing_arcs[key].timing_tables
            timing_sense = cell_db[src_type].timing_arcs[key].timing_sense
            output_cap = node.load

            # 提取 Helper 函式，讓取值更乾淨
            def get_d_s(transition_type, in_slew):
                delay_t = timing_table[f"cell_{transition_type}"]
                slew_t = timing_table[f"{transition_type}_transition"]
                if (
                    delay_t is None
                    or delay_t.values is None
                    or slew_t is None
                    or slew_t.values is None
                ):
                    return 0.0, 0.0
                d = get_value_from_table(
                    delay_t.values,
                    delay_t.index_1,
                    delay_t.index_2,
                    in_slew,
                    output_cap,
                )
                s = get_value_from_table(
                    slew_t.values,
                    slew_t.index_1,
                    slew_t.index_2,
                    in_slew,
                    output_cap,
                )
                return d, s

            # == RR (Rise->Rise) & FF (Fall->Fall) ==
            if timing_sense in ["positive_unate", "non_unate"]:
                if "cell_rise" in timing_table:
                    d, s = get_d_s("rise", src_node.rise_slew)
                    rise_candidates.append((src_node.rise_at + d, d, s))
                if "cell_fall" in timing_table:
                    d, s = get_d_s("fall", src_node.fall_slew)
                    fall_candidates.append((src_node.fall_at + d, d, s))

            # == FR (Fall->Rise) & RF (Rise->Fall) ==
            if timing_sense in ["negative_unate", "non_unate"]:
                if "cell_rise" in timing_table:
                    d, s = get_d_s("rise", src_node.fall_slew)
                    rise_candidates.append((src_node.fall_at + d, d, s))
                if "cell_fall" in timing_table:
                    d, s = get_d_s("fall", src_node.rise_slew)
                    fall_candidates.append((src_node.rise_at + d, d, s))

        # --- 取出最糟情況 (Max Arrival Time) ---
        # 從候選名單中，挑選 Arrival Time (索引 0) 最大的那組解
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

        # 將結算完的 Delay 存回 arc
        arc.rise_delay = current_rise_delay
        arc.fall_delay = current_fall_delay

        # Update max arrival time and best arc for this node
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

    # 更新 Node 狀態
    node.rise_at = max_rise_at
    node.fall_at = max_fall_at
    node.rise_domain = node.rise_at >= node.fall_at

    node.worst_pred_arc = best_arc
    node.worst_pred_delay = best_step_delay

    # --- Endpoint Setup/Recovery Check ---
    rise_setup_delay = 0.0
    fall_setup_delay = 0.0
    final_arrival_time = 0.0
    clocked_on = cell_db.get(node.type, {}).clocked_on if node.type in cell_db else None
    slack = 0.0
    node_type = type_to_cells[node.cell_gp][node.type_id] if node.sizable else node.type
    if len(node.fanout) == 0:
        if node.type == "Port":
            final_arrival_time = node.at()
            if node.pin in sdc_data.port_delay:
                final_arrival_time += sdc_data.port_delay[node.pin].delay
        else:
            if clocked_on is not None:
                key_prefix = (
                    f"{clocked_on[1:]}/{node.pin}"
                    if clocked_on.startswith("!")
                    else f"{clocked_on}/{node.pin}"
                )
                keys = [
                    k
                    for k in cell_db[node_type].timing_arcs.keys()
                    if k.startswith(key_prefix)
                ]

                for key in keys:
                    setup_table = cell_db[node_type].timing_arcs[key].timing_tables
                    clock_slew = 0.0

                    if "rise_constraint" in setup_table:
                        dt = setup_table["rise_constraint"]
                        if dt.values is not None:
                            rise_setup_delay = max(
                                get_value_from_table(
                                    dt.values,
                                    dt.index_1,
                                    dt.index_2,
                                    node.rise_slew,
                                    clock_slew,
                                ),
                                rise_setup_delay,
                            )

                    if "fall_constraint" in setup_table:
                        dt = setup_table["fall_constraint"]
                        if dt.values is not None:
                            fall_setup_delay = max(
                                get_value_from_table(
                                    dt.values,
                                    dt.index_1,
                                    dt.index_2,
                                    node.fall_slew,
                                    clock_slew,
                                ),
                                fall_setup_delay,
                            )

            final_arrival_time = max(
                node.rise_at + rise_setup_delay, node.fall_at + fall_setup_delay
            )

        # --- WNS / TNS Calculation ---
        clock_period = default_period - default_uncertainty
        if node.type == "Port":
            pass
        elif clocked_on is not None and node.inst in inst_to_clocks:
            inst_clk = sdc_data.clocks[inst_to_clocks[node.inst]]
            clock_period = inst_clk.period - inst_clk.uncertainty
        else:
            return 0.0
        slack = clock_period - final_arrival_time
    node.end_point_slack = slack
    return slack


def calculate_delay(
    topo_order: list[TimingNode],
    cell_db: dict[str, parse_cell_db.cell_info_t],
    sdc_data: parse_sdc.sdc_data_t,
    inst_to_clocks,
    p2p_delay,
    cell_lookup,
    type_to_cells,
):
    print("Starting Delay Calculation...")
    tns = 0.0
    wns = 0.0
    calculated_node_count = 0
    output_port_cap = 0.0
    violation_end_points = []
    ps_end_points = []
    reversed_topo = topo_order[::-1]

    # 1. 處理 Output/Input 初始負載與 Delay 傳遞
    for node in reversed_topo:
        if node.inst == "PIN":
            if node.pin in sdc_data.port_delay:
                node.fall_at = sdc_data.port_delay[node.pin].delay
                node.rise_at = sdc_data.port_delay[node.pin].delay
        arcs = node.fanout
        for arc in arcs:
            if arc.arc_type == "net":
                driver = arc.src
                load_pin = arc.dst
                c_near = 0.0
                if load_pin.inst == "PIN":
                    c_near = output_port_cap
                else:
                    if load_pin.sizable:
                        cell_type = type_to_cells[load_pin.cell_gp][load_pin.type_id]
                        c_near += cell_db[cell_type].pins[load_pin.pin].capacitance
                    else:
                        c_near += cell_db[load_pin.type].pins[load_pin.pin].capacitance
                driver.load += c_near

    # 2. 開始 Topo 迴圈
    worst_node = None
    for node in topo_order:
        calculated_node_count += 1
        if len(node.fanin) == 0:
            continue
        slack = calculate_node(
            node, cell_db, sdc_data, inst_to_clocks, p2p_delay, type_to_cells
        )
        if slack < 0:
            tns += abs(slack)
            if worst_node is None or abs(slack) > wns:
                worst_node = node
                wns = abs(slack)
            if len(node.fanout) == 0:
                violation_end_points.append((node, slack))
        else:
            if len(node.fanout) == 0:
                ps_end_points.append((node, slack))

    print("Delay Calculation Done.")
    print(f"TNS: -{tns/1000:.2f} ns, WNS: -{wns/1000:.2f} ns")
    if worst_node:
        print(f"Worst Node: {worst_node}, AT={worst_node.at()/1000:.2f} ns")
        report_instance_path(worst_node)
    return ps_end_points, violation_end_points


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
        path_stack.append(curr)
        if curr.worst_pred_arc:
            curr = curr.worst_pred_arc.src
        else:
            curr = None

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
            f"Rise: {start_node.inst}/{start_node.pin} {arrow} {next_node.inst}/{next_node.pin} : delay {rise_delay/1000:.2f} ps (AT: {next_node.rise_at/1000:.4f})"
        )
        print(
            f"Fall: {start_node.inst}/{start_node.pin} {arrow} {next_node.inst}/{next_node.pin} : delay {fall_delay/1000:.2f} ps (AT: {next_node.fall_at/1000:.4f})"
        )

        start_node = next_node

    print("=" * 60)
