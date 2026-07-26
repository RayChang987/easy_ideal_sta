#include "easysta/liberty/cell_db.hpp"

#include <cstdlib>

namespace easysta::liberty {

namespace {

const std::vector<std::string> kPropagationTypes = {
    "combinational", "combinational_rise", "combinational_fall",
    "rising_edge", "falling_edge",
    "setup_rising", "setup_falling",
    "hold_rising", "hold_falling",
    "recovery_rising",
};

const std::vector<std::string> kSkipTypes = {
    "preset", "clear", "non_seq", "removal", "nochange",
};

bool is_propagation_type(const std::string& t) {
    for (const auto& p : kPropagationTypes) if (p == t) return true;
    return false;
}

bool contains_skip_type(const std::string& t) {
    for (const auto& s : kSkipTypes) if (t.find(s) != std::string::npos) return true;
    return false;
}

TimingTable build_table(const LibGroup& tbl) {
    TimingTable table;
    auto idx1 = get_array(tbl, "index_1");
    auto idx2 = get_array(tbl, "index_2");
    auto vals = get_array(tbl, "values");
    if (!idx1.empty()) table.index_1 = idx1[0];
    if (!idx2.empty()) table.index_2 = idx2[0];
    table.values = vals;
    table.has_values = !vals.empty();
    return table;
}

} // namespace

std::unordered_map<std::string, CellInfo> load_cell_db(const std::vector<LibGroup>& libraries) {
    std::unordered_map<std::string, CellInfo> cell_db;

    for (const auto& library : libraries) {
        for (const LibGroup* cell_group : get_groups(library, "cell")) {
            if (cell_group->args.empty()) continue;
            std::string cell_name = cell_group->args[0];

            std::unordered_map<std::string, PinData> pins_data;
            std::unordered_map<std::string, TimingArcDef> timing_arcs;
            std::optional<std::string> clock_pin;

            for (const auto& group : cell_group->groups) {
                if (group.group_name == "pin") {
                    if (group.args.empty()) continue;
                    std::string pin_name = group.args[0];
                    std::string timing_sense = "non_unate"; // persists across timing sub-groups, mirrors parse_cell_db.py

                    for (const auto& sub : group.groups) {
                        if (sub.group_name != "timing") continue;

                        std::unordered_map<std::string, TimingTable> tables;
                        for (const auto& tbl : sub.groups) {
                            if (tbl.attributes.size() == 3 &&
                                tbl.attributes[0].name == "index_1" &&
                                tbl.attributes[1].name == "index_2" &&
                                tbl.attributes[2].name == "values") {
                                tables[tbl.group_name] = build_table(tbl);
                            }
                        }

                        auto tt_opt = get_attr(sub, "timing_type");
                        std::string timing_type = (tt_opt.has_value() && !tt_opt->empty()) ? *tt_opt : "None";

                        if (contains_skip_type(timing_type)) continue;

                        std::string related_pin;
                        for (const auto& attr : sub.attributes) {
                            if (attr.name == "related_pin") {
                                related_pin = attr.value;
                            } else if (attr.name == "timing_sense") {
                                timing_sense = attr.value;
                            }
                        }

                        if (!related_pin.empty() && related_pin != pin_name) {
                            std::string key = related_pin + "/" + pin_name + "/None";
                            if (timing_type != "combinational") key += "/" + timing_type;
                            if (is_propagation_type(timing_type)) {
                                TimingArcDef arc;
                                arc.timing_sense = timing_sense;
                                arc.timing_tables = tables;
                                timing_arcs[key] = std::move(arc);
                            }
                        }
                    }

                    PinData pd;
                    pd.direction = get_attr(group, "direction").value_or("");
                    auto cap = get_attr(group, "capacitance");
                    pd.capacitance = cap.has_value() ? std::strtod(cap->c_str(), nullptr) : 0.0;
                    pins_data[pin_name] = pd;

                } else if (group.group_name == "ff") {
                    clock_pin = get_attr(group, "clocked_on").value_or("None");
                } else if (group.group_name == "bus") {
                    for (const auto& sub : group.groups) {
                        if (sub.group_name == "memory_write") {
                            clock_pin = get_attr(sub, "clocked_on").value_or("None");
                        }
                    }
                }
            }

            CellInfo info;
            info.cell_name = cell_name;
            info.pins = std::move(pins_data);
            info.timing_arcs = std::move(timing_arcs);
            info.clocked_on = clock_pin;
            cell_db[cell_name] = std::move(info);
        }
    }

    return cell_db;
}

} // namespace easysta::liberty
