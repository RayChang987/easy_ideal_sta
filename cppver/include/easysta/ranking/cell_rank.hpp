#pragma once

#include <string>
#include <unordered_map>
#include <utility>
#include <vector>

namespace easysta::ranking {

// Mirrors parse_cell_rank.py — power-ranks cells within each cell type.
struct GateRankRow {
    std::string cell_name;
    double delay_raw = 0.0;
    double power_raw = 0.0;
};

struct GateRankResult {
    std::unordered_map<std::string, std::vector<GateRankRow>> gate_rank;     // type -> power-sorted rows
    std::unordered_map<std::string, std::pair<std::string, int>> cell_lookup; // cell_name -> (type, index)
    std::unordered_map<std::string, std::vector<std::string>> type_to_cells;  // type -> [cell_name...]
};

GateRankResult load_gate_rank(const std::string& csv_path);

} // namespace easysta::ranking
