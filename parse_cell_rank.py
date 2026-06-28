import pandas as pd


def load_gate_rank(csv_path: str):
    """Load and rank cells by power within each cell-type group.

    Returns
    -------
    gate_rank     : dict[cell_type -> sorted DataFrame]
    cell_lookup   : dict[cell_name -> (cell_type, sorted_index)]
    type_to_cells : dict[cell_type -> [cell_name, ...]]  (ordered by power)
    """
    df = (pd.read_csv(csv_path)
            [["Target_Cell_Type", "Cell_Name", "Delay_Raw", "Power_Raw"]]
            .dropna())

    gate_rank     = {}
    cell_lookup   = {}
    type_to_cells = {}

    for cell_type, group in df.groupby("Target_Cell_Type"):
        sorted_df = (group.sort_values("Power_Raw")
                         .drop_duplicates("Cell_Name")
                         .reset_index(drop=True))
        gate_rank[cell_type] = sorted_df

        cells = sorted_df["Cell_Name"].tolist()
        type_to_cells[cell_type] = cells
        for idx, name in enumerate(cells):
            cell_lookup[name] = (cell_type, idx)

    return gate_rank, cell_lookup, type_to_cells
