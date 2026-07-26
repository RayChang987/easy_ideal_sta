#pragma once

#include <string>
#include <unordered_map>
#include <utility>

namespace easysta::constraints {

// Mirrors parse_sdf.py — extracts INTERCONNECT and CELL (IOPATH) delays.
// data[src_pin][dst_pin] = (rise_max_delay, fall_max_delay)
// Not wired into main.cpp (matches the Python code, which imports but never
// calls load_sdf), kept for parity.
using SdfData = std::unordered_map<std::string, std::unordered_map<std::string, std::pair<double, double>>>;

SdfData load_sdf(const std::string& file_path);

} // namespace easysta::constraints
