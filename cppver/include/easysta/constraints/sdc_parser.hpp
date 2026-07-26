#pragma once

#include <optional>
#include <string>
#include <unordered_map>
#include <vector>

namespace easysta::constraints {

// Mirrors parse_sdc.py

struct ClockInfo {
    std::string name;
    std::optional<double> period;
    double uncertainty = 0.0;
    std::vector<std::string> ports;
};

struct PortDelayInfo {
    double delay = 0.0;
    std::string type;    // "internal" (input) or "external" (output)
    std::string minmax;  // "max"
};

struct SdcData {
    std::unordered_map<std::string, ClockInfo> clocks;
    std::unordered_map<std::string, PortDelayInfo> port_delay;
    std::unordered_map<std::string, std::string> port_to_clock;
};

SdcData load_sdc(const std::string& sdc_path);

} // namespace easysta::constraints
