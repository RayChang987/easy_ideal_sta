#pragma once

#include <string>
#include <unordered_map>
#include <vector>

#include "easysta/constraints/sdc_parser.hpp"
#include "easysta/graph/timing_node.hpp"
#include "easysta/liberty/cell_db.hpp"

namespace easysta::sta {

using TypeToCells = std::unordered_map<std::string, std::vector<std::string>>;
using NetWl = std::unordered_map<std::string, double>;

// Mirrors propagation.py

double calculate_node(graph::TimingNode* node,
                       const std::unordered_map<std::string, liberty::CellInfo>& cell_db,
                       const constraints::SdcData& sdc_data,
                       const std::unordered_map<std::string, std::string>& inst_to_clocks,
                       const TypeToCells& type_to_cells,
                       const NetWl* net_wl);

std::vector<std::pair<graph::TimingNode*, double>> calculate_delay(
    const std::vector<graph::TimingNode*>& topo_order,
    const std::unordered_map<std::string, liberty::CellInfo>& cell_db,
    const constraints::SdcData& sdc_data,
    const std::unordered_map<std::string, std::string>& inst_to_clocks,
    const TypeToCells& type_to_cells,
    const NetWl* net_wl);

void report_instance_path(graph::TimingNode* end_node);

} // namespace easysta::sta
