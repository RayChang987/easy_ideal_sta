#include "easysta/netlist/build_graph.hpp"

#include <cstdint>
#include <fstream>
#include <iostream>
#include <sstream>
#include <unordered_map>
#include <vector>

#include <nlohmann/json.hpp>

namespace easysta::netlist {

using easysta::graph::TimingArc;
using easysta::graph::TimingGraph;
using easysta::graph::TimingNode;
using easysta::liberty::CellInfo;

namespace {

struct PinRef {
    std::string inst;
    std::string pin;
    std::string cell_type;
};

std::vector<std::string> split(const std::string& s, char delim) {
    std::vector<std::string> parts;
    std::stringstream ss(s);
    std::string item;
    while (std::getline(ss, item, delim)) parts.push_back(item);
    return parts;
}

} // namespace

TimingGraph build_timing_graph(const std::string& json_file, const std::string& top_module,
                                const std::unordered_map<std::string, CellInfo>& cell_db,
                                const constraints::SdcData& sdc_data) {
    std::ifstream f(json_file);
    nlohmann::json netlist;
    f >> netlist;

    if (!netlist.contains("modules") || !netlist["modules"].contains(top_module)) {
        std::cerr << "Error: Module " << top_module << " not found in JSON." << std::endl;
        std::exit(1);
    }

    const auto& mod = netlist["modules"][top_module];
    const auto cells = mod.contains("cells") ? mod["cells"] : nlohmann::json::object();
    const auto ports = mod.contains("ports") ? mod["ports"] : nlohmann::json::object();

    TimingGraph tg;
    std::unordered_map<int64_t, std::vector<PinRef>> net_drivers;
    std::unordered_map<int64_t, std::vector<PinRef>> net_loads;
    std::unordered_map<std::string, std::string> inst_to_clocks;
    std::unordered_map<int64_t, std::string> id_to_clock_name;
    std::unordered_map<int64_t, bool> is_clock_net;
    const auto& port_to_clock = sdc_data.port_to_clock;

    std::cout << "Building Ports..." << std::endl;
    for (auto it = ports.begin(); it != ports.end(); ++it) {
        const std::string& port_name = it.key();
        const auto& port_data = it.value();
        tg.get_node("PIN", port_name, "Port");

        bool is_clock_port = port_to_clock.find(port_name) != port_to_clock.end();
        std::string direction = port_data.value("direction", "");

        for (const auto& bit : port_data["bits"]) {
            int64_t net_id = bit.get<int64_t>();
            if (is_clock_port) {
                is_clock_net[net_id] = true;
                id_to_clock_name[net_id] = port_to_clock.at(port_name);
            }
            if (direction == "input") {
                net_drivers[net_id].push_back({"PIN", port_name, "Port"});
            } else if (direction == "output") {
                net_loads[net_id].push_back({"PIN", port_name, "Port"});
            }
        }
    }

    std::cout << "Building Cells..." << std::endl;
    for (auto it = cells.begin(); it != cells.end(); ++it) {
        const std::string& inst_name = it.key();
        const auto& cell_data = it.value();
        std::string cell_type = cell_data.value("type", "");
        const auto connections = cell_data.contains("connections") ? cell_data["connections"]
                                                                     : nlohmann::json::object();

        auto cell_it = cell_db.find(cell_type);
        if (cell_it == cell_db.end()) {
            std::cout << "[Warning] Unknown cell type: " << cell_type << " @ " << inst_name << std::endl;
            continue;
        }
        const CellInfo& info = cell_it->second;

        for (const auto& kv : info.timing_arcs) {
            const std::string& arc_key = kv.first;
            auto parts = split(arc_key, '/');
            if (parts.size() < 2) continue;
            const std::string& src_pin = parts[0];
            const std::string& dst_pin = parts[1];
            std::string when = parts.size() > 2 ? parts[2] : "None";
            std::string timing_type = parts.size() > 3 ? parts[3] : "None";

            if (connections.contains(src_pin) && connections.contains(dst_pin)) {
                TimingArc* arc = tg.add_arc(
                    tg.get_node(inst_name, src_pin, cell_type),
                    tg.get_node(inst_name, dst_pin, cell_type),
                    "cell", 0.0, when, timing_type);
                // cell_db (and thus &kv.second) outlives the graph: it's
                // owned in main() for the whole run.
                arc->cell_arc_def = &kv.second;
            }
        }

        for (auto conn_it = connections.begin(); conn_it != connections.end(); ++conn_it) {
            const std::string& pin_name = conn_it.key();
            auto lib_pin_it = info.pins.find(pin_name);
            std::string pin_dir = (lib_pin_it != info.pins.end()) ? lib_pin_it->second.direction : "";

            for (const auto& bit : conn_it.value()) {
                int64_t net_id = bit.get<int64_t>();
                auto clk_it = is_clock_net.find(net_id);
                if (clk_it != is_clock_net.end() && clk_it->second) {
                    inst_to_clocks[inst_name] = id_to_clock_name[net_id];
                }
                if (pin_dir == "output") {
                    net_drivers[net_id].push_back({inst_name, pin_name, cell_type});
                } else if (pin_dir == "input") {
                    net_loads[net_id].push_back({inst_name, pin_name, cell_type});
                }
            }
        }
    }

    std::cout << "Building Net Arcs..." << std::endl;
    for (const auto& kv : net_drivers) {
        int64_t net_id = kv.first;
        for (const auto& d : kv.second) {
            TimingNode* src = tg.get_node(d.inst, d.pin, d.cell_type);
            auto loads_it = net_loads.find(net_id);
            if (loads_it == net_loads.end()) continue;
            for (const auto& l : loads_it->second) {
                tg.add_arc(src, tg.get_node(l.inst, l.pin, l.cell_type), "net");
            }
        }
    }

    tg.instance_to_clocks = std::move(inst_to_clocks);
    return tg;
}

} // namespace easysta::netlist
