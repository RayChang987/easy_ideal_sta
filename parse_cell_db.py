from collections import defaultdict
import os
import sys
from typing import Dict, Optional


class timing_table_t:
    def __init__(self, index_1, index_2, values):
        self.index_1 = index_1
        self.index_2 = index_2
        self.values = values


class timing_arc_t:
    def __init__(self, timing_sense: str, timing_tables: Dict[str, timing_table_t]):
        self.timing_sense = timing_sense
        self.timing_tables = timing_tables


class pin_data_t:
    def __init__(
        self,
        direction: str,
        capacitance: float,
        related_ground_pin: str = None,
        related_power_pin: str = None,
    ):
        self.direction = direction
        self.capacitance = capacitance
        # self.related_ground_pin = related_ground_pin
        # self.related_power_pin = related_power_pin


class cell_info_t:
    def __init__(
        self,
        cell_name: str,
        pins: Dict[str, pin_data_t],
        timing_arcs: Dict[str, timing_arc_t],
        clocked_on: Optional[str] = None,
        power_table=None,
    ):
        self.cell_name = cell_name
        self.pins = pins
        self.timing_arcs = timing_arcs
        self.clocked_on = clocked_on
        # self.power_table = power_table


def load_cell_db(libraries):
    cell_db = {}  # cell_name -> cell_info_t
    for library in libraries:
        for cell_group in library.get_groups("cell"):
            cell_name = cell_group.args[0]
            pins_data = {}
            timing_arcs = {}
            power_tables = {}
            clock_pin = None
            # 遍歷 Cell 內的所有 Group
            for group in cell_group.groups:
                if group.group_name == "pin":
                    pin_name = group.args[0]

                    # 2. 抓取 Timing Arcs (只抓 Propagation Delay，過濾 Setup/Hold)
                    timing_sense = "non_unate"
                    for sub_group in group.groups:
                        if sub_group.group_name == "timing":
                            timing_tables = dict()
                            for timing_table in sub_group.groups:
                                if (
                                    len(timing_table.attributes) == 3
                                    and timing_table.attributes[0].name == "index_1"
                                    and timing_table.attributes[1].name == "index_2"
                                    and timing_table.attributes[2].name == "values"
                                ):
                                    timing_tables[timing_table.group_name] = (
                                        timing_table_t(
                                            index_1=timing_table.get_array("index_1"),
                                            index_2=timing_table.get_array("index_2"),
                                            values=timing_table.get_array("values"),
                                        )
                                    )
                            # 檢查 timing_type
                            timing_type = "combinational"

                            try:
                                timing_type = sub_group["timing_type"]
                            except KeyError:
                                pass  # 預設為 combinational
                            if timing_type is None:
                                timing_type = "None"
                            # 過濾掉 Constraint 類型的 Arc (Setup/Hold/Recovery/Removal)
                            # 這些是用來做 Check 的，不是用來算傳播延遲的
                            if any(
                                x in str(timing_type)
                                for x in [
                                    "preset",
                                    "clear",
                                    "non_seq",
                                    "removal",
                                    "nochange",
                                ]
                            ):
                                continue

                            # 抓取 related_pin
                            related_pin = None
                            when_cond = "None"
                            for attr in sub_group.attributes:
                                if str(attr.name) == "related_pin":
                                    related_pin = (
                                        str(attr.value)
                                        .replace('"', "")
                                        .replace("'", "")
                                    )
                                # if str(attr.name) == "when":
                                #     when_cond = (
                                #         str(attr.value)
                                #         .replace('"', "")
                                #         .replace("'", "")
                                #     )
                                if str(attr.name) == "timing_sense":
                                    timing_sense = str(attr.value)

                            if related_pin and related_pin != pin_name:
                                key = related_pin + "/" + pin_name + "/" + when_cond
                                if timing_type != "combinational":
                                    key += "/" + timing_type
                                if (
                                    timing_type == "rising_edge"
                                    or timing_type == "falling_edge"
                                    or timing_type == "combinational"
                                    or timing_type == "combinational_fall"
                                    or timing_type == "combinational_rise"
                                    or timing_type == "hold_rising"
                                    or timing_type == "setup_rising"
                                    or timing_type == "hold_falling"
                                    or timing_type == "setup_falling"
                                    or timing_type == "recovery_rising"
                                ):
                                    timing_arcs[key] = timing_arc_t(
                                        timing_tables=timing_tables,
                                        timing_sense=timing_sense,
                                    )
                        # elif sub_group.group_name == "internal_power":
                        #     related_pg_pin = None
                        #     for attr in sub_group.attributes:
                        #         if str(attr.name) == "related_pg_pin":
                        #             related_pg_pin = (
                        #                 str(attr.value)
                        #                 .replace('"', "")
                        #                 .replace("'", "")
                        #             )
                        #         if str(attr.name) == "when":
                        #             when = (
                        #                 str(attr.value)
                        #                 .replace('"', "")
                        #                 .replace("'", "")
                        #             )
                        #     if related_pg_pin:
                        #         # Drop the 'when' condition
                        #         key = pin_name + "/" + related_pg_pin
                        #         if key not in power_tables:
                        #             power_tables[key] = defaultdict(list)
                        #         for power_table in sub_group.groups:
                        #             if (
                        #                 len(power_table.attributes) == 3
                        #                 and power_table.attributes[0].name == "index_1"
                        #                 and power_table.attributes[1].name == "index_2"
                        #                 and power_table.attributes[2].name == "values"
                        #             ):
                        #                 power_tables[key][power_table.group_name].append({
                        #                     "index_1": power_table.get_array("index_1"),
                        #                     "index_2": power_table.get_array("index_2"),
                        #                     "values": power_table.get_array("values"),
                        #                 })
                        #             elif (
                        #                 len(power_table.attributes) == 2
                        #                 and power_table.attributes[0].name == "index_1"
                        #             ):
                        #                 power_tables[key][power_table.group_name].append({
                        #                     "index_1": power_table.get_array("index_1"),
                        #                     "values": power_table.get_array("values"),
                        #                 })
                    pin_data = pin_data_t(
                        direction=group["direction"],
                        capacitance=group["capacitance"],
                        related_ground_pin=group.get("related_ground_pin", None),
                        related_power_pin=group.get("related_power_pin", None),
                    )
                    pins_data[pin_name] = pin_data
                elif group.group_name == "ff":
                    # 抓 clocked_on pin
                    try:
                        clock_pin = (
                            str(group["clocked_on"]).replace('"', "").replace("'", "")
                        )
                    except KeyError:
                        pass
                elif group.group_name == "bus":
                    try:
                        for sub_group in group.groups:
                            if sub_group.group_name == "memory_write":
                                print(
                                    "Found memory_write group in bus, checking for clocked_on..."
                                )
                                clock_pin = (
                                    str(sub_group["clocked_on"])
                                    .replace('"', "")
                                    .replace("'", "")
                                )
                    except KeyError:
                        pass
            cell_db[cell_name] = cell_info_t(
                cell_name=cell_name,
                pins=pins_data,
                timing_arcs=timing_arcs,
                clocked_on=clock_pin,
                power_table=None,
            )

    return cell_db


def test_lib(cell_info, cell_name):
    print(f"Testing cell_info for cell: {cell_name}")
    if cell_name in cell_info:
        print(f"Found cell: {cell_info[cell_name].cell_name}")
        print("Pins:")
        for pin_name, pin_data in cell_info[cell_name].pins.items():
            print(f"  {pin_name}: {pin_data.direction}")

    else:
        raise ValueError(f"Cell '{cell_name}' not found in cell_info.")


LIB_CACHE_FILE = "raw_libs.pkl"


if __name__ == "__main__":
    import os
    import pickle
    from read_lib import read_lib

    raw_libs = None
    if os.path.exists(LIB_CACHE_FILE):
        print(f"[INFO] Found cache file '{LIB_CACHE_FILE}', loading directly...")
        try:
            with open(LIB_CACHE_FILE, "rb") as f:
                raw_libs = pickle.load(f)
            print("[INFO] Libraries loaded from cache successfully.")
        except Exception as e:
            print(f"[WARN] Failed to load cache: {e}. Fallback to parsing.")
            raw_libs = None
    if raw_libs is None:
        print("[INFO] Parsing libraries from source (this may take a while)...")
        raw_libs = read_lib()

        if raw_libs:
            print(f"[INFO] Saving parsed libraries to cache '{LIB_CACHE_FILE}'...")
            try:
                with open(LIB_CACHE_FILE, "wb") as f:
                    pickle.dump(raw_libs, f)
            except Exception as e:
                print(f"[WARN] Could not save cache: {e}")

    if not raw_libs:
        print("No libraries loaded. Exiting.")
        sys.exit(1)

    print("Extracting Cell Database...")
    cell_db = get_cell_info(raw_libs)
    test_lib(cell_db, "SDFHx1_ASAP7_75t_L")
