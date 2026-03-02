from timing_node import TimingNode


from propagation import calculate_delay, calculate_node



def load_cell_group_type(
    topo_order: list[TimingNode], cell_db, cell_lookup, type_to_cells
):

    for node in topo_order:
        if node.type in cell_lookup:  # Except for PI/PO
            cell_type, index = cell_lookup[node.type]
            if index == -1:
                node.sizable = False
                raise ValueError(
                    f"Cell {node.type} has index -1, which is unexpected. Please check the cell lookup."
                )
            else:
                node.sizable = True
                node.cell_gp = cell_type
                node.type_id = index


def write_cell_type(
    topo_order: list[TimingNode], cell_lookup, type_to_cells, output_path
):
    """
    write_cell_type
    This function generates a TCL file for openroad to resize cells.
    """
    with open(output_path, "w") as f:
        for node in topo_order:
            if node.type in cell_lookup and node.sizable:  # Except for PI/PO
                cells = type_to_cells[node.cell_gp]
                f.write(f"replace_cell {node.inst} {cells[node.type_id]}\n")

    print(f"[INFO] Optimization results written to '{output_path}'")


def size_up(node: TimingNode, type_to_cells):
    if not node.sizable:
        return 0
    if node.type_id < len(type_to_cells[node.cell_gp]) - 1:
        node.type_id += 1
        return 1
    return 0


def size_down(node: TimingNode, type_to_cells):
    if not node.sizable:
        return 0
    if node.type_id > 0:
        node.type_id -= 1
        return 1
    return 0


def trace(ps_end_points, violation_end_points):
    end_points = ps_end_points + violation_end_points
    for end_point in violation_end_points:
        curr = end_point[0]
        while curr is not None:
            curr.criticality += 1
            curr.end_point_slack = min(curr.end_point_slack, end_point[1])
            if curr.worst_pred_arc is not None:
                curr = curr.worst_pred_arc.src
            else:
                break


def optimize(
    topo_order: list[TimingNode],
    cell_db,
    sdc_info,
    inst_to_clocks,
    p2p_delay,
    cell_lookup,
    type_to_cells,
    output_file,
):
    load_cell_group_type(topo_order, cell_db, cell_lookup, type_to_cells)
    MAX_IT = 1
    for T in range(MAX_IT):
        ps_end_points, violation_end_points = calculate_delay(
            topo_order,
            cell_db,
            sdc_info,
            inst_to_clocks,
            p2p_delay,
            cell_lookup,
            type_to_cells,
        )
        for node in topo_order:
            if node.end_point_slack<0:
                size_up(node, type_to_cells)
                size_up(node, type_to_cells)
                size_up(node, type_to_cells)

    write_cell_type(topo_order, cell_lookup, type_to_cells, output_file)
