#pragma once

#include <string>
#include <unordered_map>

#include "easysta/constraints/sdc_parser.hpp"
#include "easysta/graph/timing_graph.hpp"
#include "easysta/liberty/cell_db.hpp"

namespace easysta::netlist {

// Mirrors build_graph.py: build_timing_graph
graph::TimingGraph build_timing_graph(const std::string& json_file, const std::string& top_module,
                                       const std::unordered_map<std::string, liberty::CellInfo>& cell_db,
                                       const constraints::SdcData& sdc_data);

} // namespace easysta::netlist
