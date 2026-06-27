from typing import Dict, List
from timing_node import TimingNode
from timing_table import get_value_from_table
import parse_cell_db
import parse_sdc

# ASAP7 wire RC parameters for placement-stage estimation.
# DEF unit: 1 unit = 1 nm = 0.001 μm  (UNITS DISTANCE MICRONS 1000)
# Liberty units: time in ps, capacitance in fF.
_DEF_UNIT_TO_UM = 1.0 / 1000       # nm → μm
_WIRE_CAP_FF_PER_UM = 0.2           # fF/μm  (average across M1-M4)
_WIRE_RES_OHM_PER_UM = 20.0         # Ω/μm   (average across M1-M4)


def _wire_delay_ps(wire_length_def_units: float) -> float:
    """Lumped-RC net delay: 0.5 × R × C, result in ps."""
    length_um = wire_length_def_units * _DEF_UNIT_TO_UM
    cap_ff = length_um * _WIRE_CAP_FF_PER_UM
    res_ohm = length_um * _WIRE_RES_OHM_PER_UM
    # 0.5 × R(Ω) × C(fF) × 1e-15(F/fF) → seconds; × 1e12 → ps
    return 0.5 * res_ohm * cap_ff * 1e-3


def _get_delay_and_slew(timing_table, transition_type, in_slew, output_cap):
    delay_t = timing_table[f"cell_{transition_type}"]
    slew_t = timing_table[f"{transition_type}_transition"]
    if delay_t is None or delay_t.values is None or slew_t is None or slew_t.values is None:
        return 0.0, 0.0
    d = get_value_from_table(delay_t.values, delay_t.index_1, delay_t.index_2, in_slew, output_cap)
    s = get_value_from_table(slew_t.values, slew_t.index_1, slew_t.index_2, in_slew, output_cap)
    return d, s


def calculate_node(
    node: TimingNode,
    cell_db: Dict[str, parse_cell_db.cell_info_t],
    sdc_data: parse_sdc.sdc_data_t,
    inst_to_clocks,
    p2p_delay,
    type_to_cells,
    net_wl: Dict[str, float] = None,
):
    max_at = -1.0  # sentinel consistent with max_rise_at / max_fall_at
    max_rise_at = -1.0
    max_fall_at = -1.0
    best_arc = None
    best_step_delay = 0.0
    default_period = min(sdc_data.clocks[key].period for key in sdc_data.clocks)
    default_uncertainty = max(sdc_data.clocks[key].uncertainty for key in sdc_data.clocks)

    for arc in node.fanin:
        src_node = arc.src
        src_type = type_to_cells[src_node.cell_gp][src_node.type_id] if src_node.sizable else src_node.type
        rise_candidates = []
        fall_candidates = []

        if arc.arc_type == "net":
            net_delay = 0.0
            if net_wl is not None:
                src_key = f"{src_node.inst}/{src_node.pin}"
                net_delay = _wire_delay_ps(net_wl.get(src_key, 0.0))
            rise_candidates.append((src_node.rise_at + net_delay, net_delay, src_node.rise_slew))
            fall_candidates.append((src_node.fall_at + net_delay, net_delay, src_node.fall_slew))

        elif arc.arc_type == "cell":
            key = f"{arc.src.pin}/{node.pin}/{arc.when}"
            if arc.timing_type != "None":
                key += f"/{arc.timing_type}"

            timing_table = cell_db[src_type].timing_arcs[key].timing_tables
            timing_sense = cell_db[src_type].timing_arcs[key].timing_sense
            output_cap = node.load

            if timing_sense in ("positive_unate", "non_unate"):
                if "cell_rise" in timing_table:
                    d, s = _get_delay_and_slew(timing_table, "rise", src_node.rise_slew, output_cap)
                    rise_candidates.append((src_node.rise_at + d, d, s))
                if "cell_fall" in timing_table:
                    d, s = _get_delay_and_slew(timing_table, "fall", src_node.fall_slew, output_cap)
                    fall_candidates.append((src_node.fall_at + d, d, s))

            if timing_sense in ("negative_unate", "non_unate"):
                if "cell_rise" in timing_table:
                    d, s = _get_delay_and_slew(timing_table, "rise", src_node.fall_slew, output_cap)
                    rise_candidates.append((src_node.fall_at + d, d, s))
                if "cell_fall" in timing_table:
                    d, s = _get_delay_and_slew(timing_table, "fall", src_node.rise_slew, output_cap)
                    fall_candidates.append((src_node.rise_at + d, d, s))

        if rise_candidates:
            rise_at, current_rise_delay, rise_slew = max(rise_candidates, key=lambda x: x[0])
        else:
            rise_at, current_rise_delay, rise_slew = -1.0, 0.0, 0.0

        if fall_candidates:
            fall_at, current_fall_delay, fall_slew = max(fall_candidates, key=lambda x: x[0])
        else:
            fall_at, current_fall_delay, fall_slew = -1.0, 0.0, 0.0

        arc.rise_delay = current_rise_delay
        arc.fall_delay = current_fall_delay

        if rise_at > max_rise_at:
            max_rise_at = rise_at
            if rise_at > max_at:
                max_at = rise_at
                best_arc = arc
                best_step_delay = current_rise_delay

        if fall_at > max_fall_at:
            max_fall_at = fall_at
            if fall_at > max_at:
                max_at = fall_at
                best_arc = arc
                best_step_delay = current_fall_delay

        node.rise_slew = max(node.rise_slew, rise_slew)
        node.fall_slew = max(node.fall_slew, fall_slew)

    node.rise_at = max_rise_at
    node.fall_at = max_fall_at
    node.rise_domain = node.rise_at >= node.fall_at
    node.worst_pred_arc = best_arc
    node.worst_pred_delay = best_step_delay

    clocked_on = cell_db.get(node.type, {}).clocked_on if node.type in cell_db else None
    node_type = type_to_cells[node.cell_gp][node.type_id] if node.sizable else node.type
    slack = 0.0

    if len(node.fanout) == 0:
        # Determine clock period for this endpoint.
        clock_period = default_period - default_uncertainty
        if node.type != "Port":
            if clocked_on is not None and node.inst in inst_to_clocks:
                inst_clk = sdc_data.clocks[inst_to_clocks[node.inst]]
                clock_period = inst_clk.period - inst_clk.uncertainty
            else:
                return 0.0

        if node.type == "Port":
            # set_output_delay reduces the available window: required = period - output_delay.
            output_delay = sdc_data.port_delay[node.pin].delay if node.pin in sdc_data.port_delay else 0.0
            required_time = clock_period - output_delay
            slack = required_time - node.at()
        else:
            # Setup check: required_time = clock_period - setup_time.
            # slack = min(rise_required - rise_AT, fall_required - fall_AT)
            rise_setup_time = 0.0
            fall_setup_time = 0.0

            if clocked_on is not None:
                clk_pin = clocked_on[1:] if clocked_on.startswith("!") else clocked_on
                key_prefix = f"{clk_pin}/{node.pin}"
                keys = [k for k in cell_db[node_type].timing_arcs if k.startswith(key_prefix)]

                for key in keys:
                    setup_table = cell_db[node_type].timing_arcs[key].timing_tables
                    clock_slew = 0.0

                    if "rise_constraint" in setup_table:
                        dt = setup_table["rise_constraint"]
                        if dt.values is not None:
                            rise_setup_time = max(
                                get_value_from_table(dt.values, dt.index_1, dt.index_2, node.rise_slew, clock_slew),
                                rise_setup_time,
                            )

                    if "fall_constraint" in setup_table:
                        dt = setup_table["fall_constraint"]
                        if dt.values is not None:
                            fall_setup_time = max(
                                get_value_from_table(dt.values, dt.index_1, dt.index_2, node.fall_slew, clock_slew),
                                fall_setup_time,
                            )

            rise_required = clock_period - rise_setup_time
            fall_required = clock_period - fall_setup_time
            slack = min(rise_required - node.rise_at, fall_required - node.fall_at)

    node.end_point_slack = slack
    return slack


def calculate_delay(
    topo_order: List[TimingNode],
    cell_db: Dict[str, parse_cell_db.cell_info_t],
    sdc_data: parse_sdc.sdc_data_t,
    inst_to_clocks,
    p2p_delay,
    type_to_cells,
    net_wl: Dict[str, float] = None,
):
    print("Starting Delay Calculation...")
    tns = 0.0   # sum of negative slacks (negative value)
    wns = 0.0   # most negative slack seen (negative value)
    violation_end_points = []
    worst_node = None

    # Track which driver nodes have had wire cap added (one wire cap per net, not per load).
    wire_cap_added = set()
    for node in reversed(topo_order):
        if node.inst == "PIN" and node.pin in sdc_data.port_delay:
            node.fall_at = sdc_data.port_delay[node.pin].delay
            node.rise_at = sdc_data.port_delay[node.pin].delay
        for arc in node.fanout:
            if arc.arc_type == "net":
                load_pin = arc.dst
                if load_pin.inst != "PIN":
                    cell_type = type_to_cells[load_pin.cell_gp][load_pin.type_id] if load_pin.sizable else load_pin.type
                    arc.src.load += cell_db[cell_type].pins[load_pin.pin].capacitance
                if net_wl is not None:
                    driver = arc.src
                    if id(driver) not in wire_cap_added:
                        src_key = f"{driver.inst}/{driver.pin}"
                        wire_length = net_wl.get(src_key, 0.0)
                        driver.load += wire_length * _DEF_UNIT_TO_UM * _WIRE_CAP_FF_PER_UM
                        wire_cap_added.add(id(driver))

    for node in topo_order:
        if len(node.fanin) == 0:
            continue
        slack = calculate_node(node, cell_db, sdc_data, inst_to_clocks, p2p_delay, type_to_cells, net_wl)
        if slack < 0:
            tns += slack
            if worst_node is None or slack < wns:
                worst_node = node
                wns = slack
            if len(node.fanout) == 0:
                violation_end_points.append((node, slack))

    print("Delay Calculation Done.")
    print(f"TNS: {tns/1000:.2f} ns, WNS: {wns/1000:.2f} ns")
    if worst_node:
        print(f"Worst Node: {worst_node}, AT={worst_node.at()/1000:.2f} ns")
        report_instance_path(worst_node)
    return violation_end_points


def report_instance_path(end_node):
    if end_node is None:
        return

    print("=" * 60)
    print(f"Critical Path Report for: {end_node.inst}")
    print(f"Worst Arrival Time: {end_node.at()/1000:.2f} ns")
    print("=" * 60)

    path_stack = []
    curr = end_node
    while curr is not None:
        path_stack.append(curr)
        curr = curr.worst_pred_arc.src if curr.worst_pred_arc else None

    start_node = path_stack.pop()
    print(f"Startpoint: {start_node.name} (AT: {start_node.at()/1000:.2f} ns)")

    while path_stack:
        next_node = path_stack.pop()
        arc = next_node.worst_pred_arc
        arrow = "--(net)-->" if arc.arc_type == "net" else "--(cell)-->"

        if arc.arc_type == "cell":
            print(f"Load: {next_node.load}")
            print(f"Fall Slew: {start_node.fall_slew}")
            print(f"Rise Slew: {start_node.rise_slew}")
            print(f"Output Fall Slew: {next_node.fall_slew}")
            print(f"Output Rise Slew: {next_node.rise_slew}")

        print(f"Rise: {start_node.inst}/{start_node.pin} {arrow} {next_node.inst}/{next_node.pin} : delay {arc.rise_delay/1000:.2f} ns (AT: {next_node.rise_at/1000:.4f} ns)")
        print(f"Fall: {start_node.inst}/{start_node.pin} {arrow} {next_node.inst}/{next_node.pin} : delay {arc.fall_delay/1000:.2f} ns (AT: {next_node.fall_at/1000:.4f} ns)")

        start_node = next_node

    print("=" * 60)
