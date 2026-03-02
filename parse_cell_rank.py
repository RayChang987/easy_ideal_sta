import pandas as pd


def load_and_clean_csv(csv_path: str) -> pd.DataFrame:

    df = pd.read_csv(csv_path)


    df = df[["Target_Cell_Type", "Cell_Name", "Delay_Raw", "Power_Raw"]]


    df = df.dropna()

    return df


def sort_power_group(group: pd.DataFrame) -> pd.DataFrame:


    group = group.sort_values(by="Power_Raw", ascending=True)


    group = group.drop_duplicates(subset=["Cell_Name"], keep="first")

    return group


def load_gate_rank(csv_path: str):
    """
    回傳:
        gate_rank: dict[cell_type] = sorted dataframe
        cell_index_map: dict[cell_name] = (cell_type, index)
        type_to_cells: dict[cell_type] = [cell_name0, cell_name1, ...]
    """

    df = load_and_clean_csv(csv_path)

    gate_rank = {}
    grouped = df.groupby("Target_Cell_Type")

    full_cell_type_map = {}

    for target_cell, group in grouped:
        for cell_name in group["Cell_Name"]:
            full_cell_type_map[cell_name] = target_cell

        # 排序並濾除重複的 Cell
        sorted_df = sort_power_group(group)
        gate_rank[target_cell] = sorted_df

    cell_index_map, type_to_cells = build_cell_index_map(gate_rank, full_cell_type_map)

    return gate_rank, cell_index_map, type_to_cells


def build_cell_index_map(gate_rank: dict, full_cell_type_map: dict):
    """
    回傳:
        cell_lookup: cell_name -> (cell_type, index)
        type_to_cells: cell_type -> [cell_name0, cell_name1, ...]
    """

    cell_lookup = {}
    type_to_cells = {}

    # 1️⃣ 先全部設成 -1
    for cell_name, cell_type in full_cell_type_map.items():
        cell_lookup[cell_name] = (cell_type, -1)

    # 2️⃣ 建立 sorted index + array
    for cell_type, sorted_df in gate_rank.items():

        # 重設 index 以對應陣列索引 (前面已經排過序了，這裡不用再排一次)
        sorted_df = sorted_df.reset_index(drop=True)

        cell_array = []
        for idx, row in sorted_df.iterrows():
            cell_name = row["Cell_Name"]

            cell_lookup[cell_name] = (cell_type, idx)
            cell_array.append(cell_name)

        type_to_cells[cell_type] = cell_array

    return cell_lookup, type_to_cells


# ==========================
# 測試區
# ==========================
if __name__ == "__main__":
    csv_file = "gate_ranking_all_cells_analysis.csv"

    try:
        gate_rank, cell_lookup, type_to_cells = load_gate_rank(csv_file)

        test_cell = "SDFHx4_ASAP7_75t_SL"

        if test_cell in cell_lookup:
            cell_type, index = cell_lookup[test_cell]
            print(f"{test_cell}")
            print(f"  Cell Type : {cell_type}")
            print(f"  Sorted Index : {index}")
        else:
            print("Cell not found.")

        print("=" * 40)
        example_type = list(type_to_cells.keys())[0]
        print(example_type, "->", type_to_cells[example_type])

        if "SDFH" in type_to_cells:
            print(type_to_cells["SDFH"])

    except FileNotFoundError:
        print(f"找不到檔案: {csv_file}，請確認路徑是否正確。")
