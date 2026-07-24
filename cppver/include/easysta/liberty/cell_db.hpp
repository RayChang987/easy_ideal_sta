#pragma once

#include <optional>
#include <string>
#include <unordered_map>
#include <vector>

#include "easysta/liberty/liberty_parser.hpp"

namespace easysta::liberty {

// Mirrors parse_cell_db.py

struct TimingTable {
    std::vector<double> index_1;
    std::vector<double> index_2;
    std::vector<std::vector<double>> values;
    bool has_values = false;
};

struct TimingArcDef {
    std::string timing_sense;
    std::unordered_map<std::string, TimingTable> timing_tables; // e.g. "cell_rise" -> table
};

struct PinData {
    std::string direction;
    double capacitance = 0.0;
};

struct CellInfo {
    std::string cell_name;
    std::unordered_map<std::string, PinData> pins;
    std::unordered_map<std::string, TimingArcDef> timing_arcs; // key: "related_pin/pin/None[/timing_type]"
    std::optional<std::string> clocked_on;
};

std::unordered_map<std::string, CellInfo> load_cell_db(const std::vector<LibGroup>& libraries);

} // namespace easysta::liberty
