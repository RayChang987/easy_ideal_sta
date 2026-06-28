from typing import Dict, Optional


_PROPAGATION_TYPES = {
    "combinational", "combinational_rise", "combinational_fall",
    "rising_edge", "falling_edge",
    "setup_rising", "setup_falling",
    "hold_rising", "hold_falling",
    "recovery_rising",
}

_SKIP_TYPES = {"preset", "clear", "non_seq", "removal", "nochange"}


class timing_table_t:
    def __init__(self, index_1, index_2, values):
        self.index_1 = index_1
        self.index_2 = index_2
        self.values  = values


class timing_arc_t:
    def __init__(self, timing_sense: str, timing_tables: Dict[str, timing_table_t]):
        self.timing_sense  = timing_sense
        self.timing_tables = timing_tables


class pin_data_t:
    def __init__(self, direction: str, capacitance: float):
        self.direction   = direction
        self.capacitance = capacitance


class cell_info_t:
    def __init__(self, cell_name: str, pins: Dict[str, pin_data_t],
                 timing_arcs: Dict[str, timing_arc_t],
                 clocked_on: Optional[str] = None):
        self.cell_name   = cell_name
        self.pins        = pins
        self.timing_arcs = timing_arcs
        self.clocked_on  = clocked_on


def load_cell_db(libraries) -> Dict[str, cell_info_t]:
    cell_db = {}

    for library in libraries:
        for cell_group in library.get_groups("cell"):
            cell_name  = cell_group.args[0]
            pins_data  = {}
            timing_arcs = {}
            clock_pin  = None

            for group in cell_group.groups:
                if group.group_name == "pin":
                    pin_name     = group.args[0]
                    timing_sense = "non_unate"

                    for sub in group.groups:
                        if sub.group_name != "timing":
                            continue

                        # Collect lookup tables
                        tables = {}
                        for tbl in sub.groups:
                            if (len(tbl.attributes) == 3
                                    and tbl.attributes[0].name == "index_1"
                                    and tbl.attributes[1].name == "index_2"
                                    and tbl.attributes[2].name == "values"):
                                tables[tbl.group_name] = timing_table_t(
                                    tbl.get_array("index_1"),
                                    tbl.get_array("index_2"),
                                    tbl.get_array("values"),
                                )

                        try:
                            timing_type = sub["timing_type"] or "None"
                        except KeyError:
                            timing_type = "combinational"

                        if any(x in str(timing_type) for x in _SKIP_TYPES):
                            continue

                        related_pin = None
                        for attr in sub.attributes:
                            name = str(attr.name)
                            if name == "related_pin":
                                related_pin = str(attr.value).strip('"\'')
                            elif name == "timing_sense":
                                timing_sense = str(attr.value)

                        if related_pin and related_pin != pin_name:
                            key = f"{related_pin}/{pin_name}/None"
                            if timing_type not in ("combinational", None):
                                key += f"/{timing_type}"
                            if str(timing_type) in _PROPAGATION_TYPES:
                                timing_arcs[key] = timing_arc_t(timing_sense, tables)

                    pins_data[pin_name] = pin_data_t(
                        direction=group["direction"],
                        capacitance=group["capacitance"],
                    )

                elif group.group_name == "ff":
                    try:
                        clock_pin = str(group["clocked_on"]).strip('"\'')
                    except KeyError:
                        pass

                elif group.group_name == "bus":
                    for sub in group.groups:
                        if sub.group_name == "memory_write":
                            print("Found memory_write group in bus, checking for clocked_on...")
                            try:
                                clock_pin = str(sub["clocked_on"]).strip('"\'')
                            except KeyError:
                                pass

            cell_db[cell_name] = cell_info_t(cell_name, pins_data, timing_arcs, clock_pin)

    return cell_db
