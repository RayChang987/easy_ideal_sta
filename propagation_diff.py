import torch
from math import floor, ceil
from timing_table_diff import get_value_from_table_torch

# =========================
# Stable Soft Max Utilities
# =========================


def soft_max_stable(values, device, alpha=50.0):
    if not values:
        return torch.tensor(
            float("-inf"), device=device
        )  # 如果沒有候選值，返回負無限大

    stacked = torch.stack(values)
    return torch.logsumexp(alpha * stacked, dim=0) / alpha


# =========================
# Main Differentiable Engine
# =========================


def calculate_delay_diff_torch(
    topo_order,
    cell_db,
    sdc_info,
    inst_to_clocks,
    p2p_delay,
    cell_lookup,
    type_to_cells,
    device,
    alpha=50.0,
):

    print("Starting Stable Differentiable Delay Calculation...")

    zero = torch.tensor(0.0, device=device)
    neg_one = torch.tensor(-1.0, device=device)

    default_period = min(sdc_info[0][key]["period"] for key in sdc_info[0])
    default_uncertainty = max(sdc_info[0][key]["uncertainty"] for key in sdc_info[0])

    # 獨立宣告 TNS
    tns = zero.clone()
    power = zero.clone()
    cost = zero.clone()
    reversed_topo = topo_order[::-1]

    # =========================
    # Initialize Nodes
    # =========================
    for node in reversed_topo:
        # 全部獨立宣告，不共用任何變數！
        node.load = zero.clone()
        node.rise_at = zero.clone()
        node.fall_at = zero.clone()
        node.rise_slew = zero.clone()
        node.fall_slew = zero.clone()

    # =========================
    # Backward Load Propagation
    # =========================
    for node in reversed_topo:

        if node.inst == "PIN":
            if node.pin in sdc_info[1]:
                init_delay = float(sdc_info[1][node.pin]["delay"])
                node.rise_at = torch.tensor(init_delay, device=device)
                node.fall_at = torch.tensor(init_delay, device=device)

        for arc in node.fanout:
            if arc.arc_type != "net":
                continue

            driver = arc.src
            load_pin = arc.dst

            if load_pin.inst == "PIN":
                continue

            if load_pin.type in cell_lookup:
                load_pin.is_fusion = True
                cell_group_name, _ = cell_lookup[load_pin.type]

                f_idx = load_pin.fusion_index
                l_idx = int(torch.floor(f_idx).item())
                u_idx = int(torch.ceil(f_idx).item())

                u_type = type_to_cells[cell_group_name][u_idx]
                l_type = type_to_cells[cell_group_name][l_idx]

                upper_cap = cell_db[u_type]["pins"][load_pin.pin]["capacitance"]
                lower_cap = cell_db[l_type]["pins"][load_pin.pin]["capacitance"]

                if l_idx == u_idx:
                    driver.load = driver.load + upper_cap
                else:
                    weight_u = f_idx - l_idx
                    weight_l = u_idx - f_idx
                    driver.load = (
                        driver.load + upper_cap * weight_u + lower_cap * weight_l
                    )

            else:
                driver.load = (
                    driver.load
                    + cell_db[load_pin.type]["pins"][load_pin.pin]["capacitance"]
                )

    # =========================
    # Forward Timing Propagation
    # =========================
    for node in topo_order:

        if len(node.fanin) == 0:
            continue

        rise_at_candidates = []
        fall_at_candidates = []
        rise_slew_candidates = []
        fall_slew_candidates = []

        for arc in node.fanin:
            src = arc.src
            dst = arc.dst
            src_key = f"{src.inst}/{src.pin}" if src.inst != "PIN" else f"PIN/{src.pin}"
            dst_key = f"{dst.inst}/{dst.pin}" if dst.inst != "PIN" else f"PIN/{dst.pin}"
            real_rise_delay, real_fall_delay = p2p_delay.get(src_key, {}).get(
                dst_key, (zero, zero)
            )

            if arc.arc_type == "net":
                rise_at_candidates.append(src.rise_at + real_rise_delay)
                fall_at_candidates.append(src.fall_at + real_fall_delay)
                rise_slew_candidates.append(src.rise_slew)
                fall_slew_candidates.append(src.fall_slew)
                continue

            # ----- CELL ARC -----
            key = f"{src.pin}/{dst.pin}/{arc.when}"
            if arc.timing_type != "None":
                key += f"/{arc.timing_type}"

            timing_sense = cell_db[src.type]["timing_arcs"][key]["timing_sense"]
            output_cap = node.load

            def get_d_s_linear(transition_type, in_slew):
                def fetch_linear(c_type):
                    # 直接抓取預先算好的線性係數
                    linear_params = cell_db[c_type]["timing_arcs"][key]["linear_model"]

                    d_params = linear_params[f"cell_{transition_type}"]
                    s_params = linear_params[f"{transition_type}_transition"]

                    # Delay = w_slew * in_slew + w_cap * output_cap + bias
                    d = (
                        d_params["w_slew"] * in_slew
                        + d_params["w_cap"] * output_cap
                        + d_params["bias"]
                    )

                    # Slew = w_slew * in_slew + w_cap * output_cap + bias
                    s = (
                        s_params["w_slew"] * in_slew
                        + s_params["w_cap"] * output_cap
                        + s_params["bias"]
                    )

                    return d, s

                # 處理 Fusion (連續型 Cell) 的內插邏輯不變，只是底層呼叫 fetch_linear
                if getattr(src, "is_fusion", False):
                    cell_group_name, _ = cell_lookup[src.type]
                    f_idx = src.fusion_index
                    f_idx_val = f_idx.item()
                    l_idx = int(floor(f_idx_val))
                    u_idx = int(ceil(f_idx_val))

                    u_type = type_to_cells[cell_group_name][u_idx]

                    if l_idx == u_idx:
                        return fetch_linear(u_type)

                    l_type = type_to_cells[cell_group_name][l_idx]
                    d_u, s_u = fetch_linear(u_type)
                    d_l, s_l = fetch_linear(l_type)

                    weight_u = f_idx - l_idx
                    weight_l = u_idx - f_idx

                    return (
                        d_u * weight_u + d_l * weight_l,
                        s_u * weight_u + s_l * weight_l,
                    )

                return fetch_linear(src.type)

            base_table = cell_db[src.type]["timing_arcs"][key]["timing_tables"]

            if timing_sense in ["positive_unate", "non_unate"]:
                if "cell_rise" in base_table:
                    d, s = get_d_s_linear("rise", src.rise_slew)
                    rise_at_candidates.append(src.rise_at + d)
                    rise_slew_candidates.append(s)

                if "cell_fall" in base_table:
                    d, s = get_d_s_linear("fall", src.fall_slew)
                    fall_at_candidates.append(src.fall_at + d)
                    fall_slew_candidates.append(s)

            if timing_sense in ["negative_unate", "non_unate"]:
                if "cell_rise" in base_table:
                    d, s = get_d_s_linear("rise", src.fall_slew)
                    rise_at_candidates.append(src.fall_at + d)
                    rise_slew_candidates.append(s)

                if "cell_fall" in base_table:
                    d, s = get_d_s_linear("fall", src.rise_slew)
                    fall_at_candidates.append(src.rise_at + d)
                    fall_slew_candidates.append(s)

        # --- Combine ---
        # 1. Arrival Time 獨立取平滑最大值
        node.rise_at = (
            soft_max_stable(rise_at_candidates, device, alpha=alpha)
            if rise_at_candidates
            else zero
        )
        node.fall_at = (
            soft_max_stable(fall_at_candidates, device, alpha=alpha)
            if fall_at_candidates
            else zero
        )

        # 2. Slew 獨立取平滑最大值
        node.rise_slew = (
            soft_max_stable(rise_slew_candidates, device, alpha=alpha)
            if rise_slew_candidates
            else zero
        )
        node.fall_slew = (
            soft_max_stable(fall_slew_candidates, device, alpha=alpha)
            if fall_slew_candidates
            else zero
        )

        # =========================
        # Endpoint Slack Calculation
        # =========================
        # 只有在沒有 fanout 的終點才計算 Slack
        if len(node.fanout) == 0:

            # --- 情況 A: 終點是 Primary Output (Port) ---
            if node.type == "Port":
                final_arrival = soft_max_stable(
                    [node.rise_at, node.fall_at], device, alpha=alpha
                )

                # 加上 SDC 規範的 output delay
                if node.pin in sdc_info[1]:
                    final_arrival = final_arrival + torch.tensor(
                        float(sdc_info[1][node.pin]["delay"]), device=device
                    )

                clock_period = default_period - default_uncertainty
                slack_violation = torch.relu(final_arrival - float(clock_period))
                tns = tns + slack_violation

            # --- 情況 B: 終點是 Flip-Flop (或有 clocked_on 屬性的 Cell) ---
            else:
                clocked_on = cell_db.get(node.type, {}).get("clocked_on", None)
                if clocked_on is not None and node.inst in inst_to_clocks:
                    inst_clk = sdc_info[0][inst_to_clocks[node.inst]]
                    clock_period = inst_clk["period"] - inst_clk["uncertainty"]

                    # 準備抓取 Setup Time，先蒐集再一次做 soft max
                    rise_setup_candidates = [zero]
                    fall_setup_candidates = [zero]

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

                    # 可微分的 Setup Table 查表函數
                    def get_setup_value_torch(
                        c_type, arc_key, constraint_type, n_slew, c_slew
                    ):
                        if arc_key not in cell_db[c_type]["timing_arcs"]:
                            return zero
                        t_table = cell_db[c_type]["timing_arcs"][arc_key][
                            "timing_tables"
                        ]
                        if constraint_type in t_table:
                            dt = t_table[constraint_type]
                            if not isinstance(c_slew, torch.Tensor):
                                c_slew = torch.tensor(
                                    c_slew, dtype=torch.float32, device=device
                                )
                            return get_value_from_table_torch(
                                dt["values"],
                                dt["index_1"],
                                dt["index_2"],
                                n_slew,
                                c_slew,
                            )
                        return zero

                    for key in keys:
                        # 獨立宣告 clock slew
                        clock_slew = zero

                        if getattr(node, "is_fusion", False):
                            cell_group_name, _ = cell_lookup[node.type]

                            f_idx = node.fusion_index
                            l_idx_val = int(torch.floor(f_idx).long())
                            u_idx_val = int(torch.ceil(f_idx).long())

                            u_type = type_to_cells[cell_group_name][u_idx_val]
                            l_type = type_to_cells[cell_group_name][l_idx_val]

                            def interp_setup_torch(constraint_type, n_slew):
                                val_u = get_setup_value_torch(
                                    u_type, key, constraint_type, n_slew, clock_slew
                                )
                                if l_idx_val == u_idx_val:
                                    return val_u
                                val_l = get_setup_value_torch(
                                    l_type, key, constraint_type, n_slew, clock_slew
                                )

                                weight_u = f_idx - l_idx_val
                                weight_l = u_idx_val - f_idx
                                return val_u * weight_u + val_l * weight_l

                            r_setup_val = interp_setup_torch(
                                "rise_constraint", node.rise_slew
                            )
                            f_setup_val = interp_setup_torch(
                                "fall_constraint", node.fall_slew
                            )

                        else:
                            r_setup_val = get_setup_value_torch(
                                node.type,
                                key,
                                "rise_constraint",
                                node.rise_slew,
                                clock_slew,
                            )
                            f_setup_val = get_setup_value_torch(
                                node.type,
                                key,
                                "fall_constraint",
                                node.fall_slew,
                                clock_slew,
                            )

                        rise_setup_candidates.append(r_setup_val)
                        fall_setup_candidates.append(f_setup_val)

                    rise_setup_delay = soft_max_stable(
                        rise_setup_candidates, device, alpha=alpha
                    )
                    fall_setup_delay = soft_max_stable(
                        fall_setup_candidates, device, alpha=alpha
                    )

                    # 加上 Setup Time 後再進行 LSE 組合
                    final_arrival = soft_max_stable(
                        [
                            node.rise_at + rise_setup_delay,
                            node.fall_at + fall_setup_delay,
                        ],
                        device=device,
                        alpha=alpha,
                    )

                    slack_violation = torch.relu(final_arrival - float(clock_period))
                    tns = tns + slack_violation
        # =========================

        if node.is_fusion:
            cell_group_name, _ = cell_lookup[node.type]
            f_idx = node.fusion_index
            l_idx_val = int(torch.floor(f_idx).long())
            u_idx_val = int(torch.ceil(f_idx).long())
            u_type = type_to_cells[cell_group_name][u_idx_val]
            l_type = type_to_cells[cell_group_name][l_idx_val]
            power_u = cell_db[u_type]["average_power"]
            power_l = cell_db[l_type]["average_power"]

            weight_u = f_idx - l_idx_val
            weight_l = u_idx_val - f_idx
            power = power + power_u * weight_u + power_l * weight_l

    # (原本的 return 區塊)
    cost = tns + 10 * power
    print(f"TNS: {-tns.item()/1000:.2f} ns")
    print(f"Cost: {cost.item()/1000:.2f}")
    print("Stable Differentiable Calculation Done.")

    return cost


# ==========================================
# Phase 2: Differentiable Engine (每次迭代呼叫)
# ==========================================
# ==========================================
# Phase 2: Differentiable Engine (每次迭代呼叫) - 修復 In-place 錯誤版
# ==========================================
def calculate_delay_diff_torch_levelized(compiler, topo_order, device):
    N = compiler.num_nodes
    zero = torch.tensor(0.0, device=device)

    # 宣告全局狀態 Tensor
    rise_at = torch.zeros(N, device=device)
    fall_at = torch.zeros(N, device=device)
    rise_slew = torch.zeros(N, device=device)
    fall_slew = torch.zeros(N, device=device)
    load = torch.zeros(N, device=device)

    # =========================================
    # 1. Backward Load Propagation
    # =========================================
    load_indices = []
    load_values = []

    for op in compiler.backward_loads:
        load_indices.append(op["driver_idx"])
        if not op["is_fusion"]:
            load_values.append(torch.tensor(op["cap_val"], device=device))
        else:
            # 處理 Fusion Node 電容內插 (保留梯度)
            f_idx = op["node_ref"].fusion_index
            l_idx = int(torch.floor(f_idx).item())
            u_idx = int(torch.ceil(f_idx).item())

            u_type = compiler.type_to_cells[op["group_name"]][u_idx]
            l_type = compiler.type_to_cells[op["group_name"]][l_idx]

            u_cap = compiler.cell_db[u_type]["pins"][op["pin"]]["capacitance"]
            l_cap = compiler.cell_db[l_type]["pins"][op["pin"]]["capacitance"]

            weight_u = f_idx - l_idx
            weight_l = u_idx - f_idx

            interp_cap = (
                u_cap * weight_u + l_cap * weight_l if l_idx != u_idx else u_cap
            )
            load_values.append(interp_cap)

    if load_indices:
        idx_tensor = torch.tensor(load_indices, dtype=torch.long, device=device)
        val_tensor = torch.stack(load_values)

        # 💡 解法 1：先 clone 一份全新的 load，再做 inplace add，保證安全
        load = load.clone()
        load.scatter_add_(dim=0, index=idx_tensor, src=val_tensor)

    # =========================================
    # 2. Forward Timing Propagation (Level by Level)
    # =========================================
    for lvl in range(1, compiler.num_levels):
        arcs = compiler.forward_arcs_by_level[lvl]
        if not arcs:
            continue

        dst_indices = []
        new_rise_at_vals = []
        new_fall_at_vals = []
        new_rise_slew_vals = []
        new_fall_slew_vals = []

        for arc in arcs:
            src_idx = arc["src_idx"]
            dst_idx = arc["dst_idx"]
            dst_indices.append(dst_idx)

            if arc["type"] == "net":
                new_rise_at_vals.append(rise_at[src_idx] + arc["r_delay"])
                new_fall_at_vals.append(fall_at[src_idx] + arc["f_delay"])
                new_rise_slew_vals.append(rise_slew[src_idx])
                new_fall_slew_vals.append(fall_slew[src_idx])
            else:
                src_node = arc["src_node"]
                key = arc["arc_key"]
                out_cap = load[dst_idx]

                def get_linear_weights(c_type):
                    return compiler.cell_db[c_type]["timing_arcs"][key]["linear_model"]

                if getattr(src_node, "is_fusion", False):
                    f_idx = src_node.fusion_index
                    l_idx = int(torch.floor(f_idx).item())
                    u_idx = int(torch.ceil(f_idx).item())
                    group_name, _ = compiler.cell_lookup[src_node.type]

                    u_type = compiler.type_to_cells[group_name][u_idx]
                    l_type = compiler.type_to_cells[group_name][l_idx]

                    model_u = get_linear_weights(u_type)
                    if l_idx == u_idx:
                        model = model_u
                    else:
                        model_l = get_linear_weights(l_type)
                        weight_u = f_idx - l_idx
                        weight_l = u_idx - f_idx
                        model = {}
                        for trans_key in model_u.keys():
                            model[trans_key] = {
                                "w_slew": model_u[trans_key]["w_slew"] * weight_u
                                + model_l[trans_key]["w_slew"] * weight_l,
                                "w_cap": model_u[trans_key]["w_cap"] * weight_u
                                + model_l[trans_key]["w_cap"] * weight_l,
                                "bias": model_u[trans_key]["bias"] * weight_u
                                + model_l[trans_key]["bias"] * weight_l,
                            }
                else:
                    model = get_linear_weights(src_node.type)

                def calc_linear(trans_type, in_slew):
                    m_d = model.get(
                        f"cell_{trans_type}", {"w_slew": 0, "w_cap": 0, "bias": 0}
                    )
                    m_s = model.get(
                        f"{trans_type}_transition", {"w_slew": 0, "w_cap": 0, "bias": 0}
                    )
                    d = m_d["w_slew"] * in_slew + m_d["w_cap"] * out_cap + m_d["bias"]
                    s = m_s["w_slew"] * in_slew + m_s["w_cap"] * out_cap + m_s["bias"]
                    return d, s

                sense = arc["timing_sense"]
                in_s_r = rise_slew[src_idx]
                in_s_f = fall_slew[src_idx]

                r_at, f_at, r_slew, f_slew = zero, zero, zero, zero

                if sense in ["positive_unate", "non_unate"]:
                    d_r, s_r = calc_linear("rise", in_s_r)
                    d_f, s_f = calc_linear("fall", in_s_f)
                    r_at = torch.maximum(r_at, rise_at[src_idx] + d_r)
                    f_at = torch.maximum(f_at, fall_at[src_idx] + d_f)
                    r_slew = torch.maximum(r_slew, s_r)
                    f_slew = torch.maximum(f_slew, s_f)

                if sense in ["negative_unate", "non_unate"]:
                    d_r, s_r = calc_linear("rise", in_s_f)
                    d_f, s_f = calc_linear("fall", in_s_r)
                    r_at = torch.maximum(r_at, fall_at[src_idx] + d_r)
                    f_at = torch.maximum(f_at, rise_at[src_idx] + d_f)
                    r_slew = torch.maximum(r_slew, s_r)
                    f_slew = torch.maximum(f_slew, s_f)

                new_rise_at_vals.append(r_at)
                new_fall_at_vals.append(f_at)
                new_rise_slew_vals.append(r_slew)
                new_fall_slew_vals.append(f_slew)

        # --- 本層聚合 ---
        if dst_indices:
            idx_t = torch.tensor(dst_indices, dtype=torch.long, device=device)

            # 💡 解法 2：創造全新的 Version，讓 Autograd 能夠回溯舊的版本
            rise_at = rise_at.clone()
            fall_at = fall_at.clone()
            rise_slew = rise_slew.clone()
            fall_slew = fall_slew.clone()

            rise_at.scatter_reduce_(
                dim=0,
                index=idx_t,
                src=torch.stack(new_rise_at_vals),
                reduce="amax",
                include_self=False,
            )
            fall_at.scatter_reduce_(
                dim=0,
                index=idx_t,
                src=torch.stack(new_fall_at_vals),
                reduce="amax",
                include_self=False,
            )
            rise_slew.scatter_reduce_(
                dim=0,
                index=idx_t,
                src=torch.stack(new_rise_slew_vals),
                reduce="amax",
                include_self=False,
            )
            fall_slew.scatter_reduce_(
                dim=0,
                index=idx_t,
                src=torch.stack(new_fall_slew_vals),
                reduce="amax",
                include_self=False,
            )

    # =========================================
    # 3. Endpoint TNS Calculation
    # =========================================
    ends = compiler.endpoints
    if len(ends["indices"]) > 0:
        idx = ends["indices"]
        final_arrival = torch.maximum(rise_at[idx], fall_at[idx])
        final_arrival = final_arrival + ends["setup"]
        slack_violation = torch.relu(final_arrival - ends["period"])
        tns = slack_violation.sum()
    else:
        tns = zero

    return tns
