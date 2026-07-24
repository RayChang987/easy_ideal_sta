#pragma once

#include <string>
#include <unordered_map>
#include <utility>
#include <vector>

namespace easysta::placement {

using DefPoint = std::pair<long long, long long>;

// Mirrors read_def.py.
struct DefResult {
    std::unordered_map<std::string, DefPoint> component_pos; // "inst/pin" -> (x, y)
    std::unordered_map<std::string, double> pin_wl;            // "inst/pin" -> RMST wire length (DEF units)
};

double calc_rmst_length_fast(std::vector<DefPoint> points);

DefResult read_def(const std::string& file_path);

} // namespace easysta::placement
