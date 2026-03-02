import re
import os


def load_sdf(file_path):
    """
    Parses both INTERCONNECT and CELL (IOPATH) delays from an SDF file.

    Args:
        file_path (str): The path to the SDF file.

    Returns:
        dict: A nested dictionary where:
              data[source_pin][dest_pin] = (rise_max_delay, fall_max_delay)
    """

    if not os.path.exists(file_path):
        raise FileNotFoundError(f"The file '{file_path}' was not found.")

    sdf_data = {}

    # Regex 解析邏輯:
    # 1. 抓取 INTERCONNECT
    pattern_interconnect = re.compile(
        r"\(INTERCONNECT\s+(?P<src>\S+)\s+(?P<dst>\S+)\s+"
        r"\([^:]+::(?P<r_max>[\d\.-]+)\)"
        r"(?:\s+\([^:]+::(?P<f_max>[\d\.-]+)\))?"
    )

    # 2. 抓取 INSTANCE 以追蹤當前的 Cell Context
    # 使用 [^)]* 來匹配括號內的所有字元，避免 Instance 名稱有怪異符號
    pattern_instance = re.compile(r"\(INSTANCE\s*(?P<inst>[^)]*)\)")

    # 3. 抓取 IOPATH (格式與 INTERCONNECT 後半段幾乎完全一致)
    pattern_iopath = re.compile(
        r"\(IOPATH\s+(?P<src>\S+)\s+(?P<dst>\S+)\s+"
        r"\([^:]+::(?P<r_max>[\d\.-]+)\)"
        r"(?:\s+\([^:]+::(?P<f_max>[\d\.-]+)\))?"
    )

    # 用來記錄目前讀取到的 Cell Instance
    current_instance = ""

    try:
        with open(file_path, "r", encoding="utf-8") as f:
            for line in f:

                # --- 處理 INSTANCE 狀態 ---
                if "INSTANCE" in line:
                    match = pattern_instance.search(line)
                    if match:
                        inst_name = match.group("inst").strip()
                        # 去除跳脫字元 (例如 i50\/i484 -> i50/i484)
                        current_instance = inst_name.replace("\\", "")
                    continue

                # --- 處理 IOPATH (Cell Delay) ---
                if "IOPATH" in line:
                    match = pattern_iopath.search(line)
                    if match:
                        src_pin = match.group("src")
                        dst_pin = match.group("dst")

                        # 將 Instance 與 Pin 組合在一起 (例如 i50/i484/A)
                        # 如果是 Top-level (current_instance 為空或 *)，則直接使用 pin name
                        if current_instance and current_instance != "*":
                            full_src = f"{current_instance}/{src_pin}"
                            full_dst = f"{current_instance}/{dst_pin}"
                        else:
                            full_src = src_pin
                            full_dst = dst_pin

                        r_max = float(match.group("r_max"))
                        f_max = (
                            float(match.group("f_max"))
                            if match.group("f_max")
                            else r_max
                        )

                        if full_src not in sdf_data:
                            sdf_data[full_src] = {}
                        sdf_data[full_src][full_dst] = (r_max, f_max)
                    continue

                # --- 處理 INTERCONNECT (Wire Delay) ---
                if "INTERCONNECT" in line:
                    match = pattern_interconnect.search(line)
                    if match:
                        src_pin = match.group("src").replace("\\", "")
                        dst_pin = match.group("dst").replace("\\", "")

                        r_max = float(match.group("r_max"))
                        f_max = (
                            float(match.group("f_max"))
                            if match.group("f_max")
                            else r_max
                        )

                        if src_pin not in sdf_data:
                            sdf_data[src_pin] = {}
                        sdf_data[src_pin][dst_pin] = (r_max, f_max)
                    continue

    except Exception as e:
        print(f"Error parsing file: {e}")
        return {}

    return sdf_data


# --- 使用範例 ---
if __name__ == "__main__":
    # 這裡可以用你的測試檔名
    filename = "aes_cipher_top.sdf"

    # 若需本地測試，可先建立一個 dummy 檔案：
    # with open(filename, 'w') as f:
    #     f.write('(CELL (CELLTYPE "OR2x6") (INSTANCE i50\/i484) (DELAY (ABSOLUTE (IOPATH A Y (18.230::20.717) (21.038::23.288)))))\n')
    #     f.write('(INTERCONNECT i0\/Y i43\/i76\/SE (0.123::0.456))\n')

    delays = load_sdf(filename)

    print(f"Parsing file: {filename}\n")

    # 1. 測試查找 Interconnect delay
    src_int = "i0/Y"
    dst_int = "i43/i76/SE"
    if src_int in delays and dst_int in delays[src_int]:
        r, f = delays[src_int][dst_int]
        print(f"[Wire Delay] {src_int} -> {dst_int}: Rise={r}, Fall={f}")

    # 2. 測試查找 Cell delay (IOPATH)
    src_cell = "input129/A"
    dst_cell = "input129/Y"
    if src_cell in delays and dst_cell in delays[src_cell]:
        r, f = delays[src_cell][dst_cell]
        print(f"[Cell Delay] {src_cell} -> {dst_cell}: Rise={r}, Fall={f}")

    print("-" * 30)
