#include "easysta/constraints/sdc_parser.hpp"

#include <fstream>
#include <regex>

namespace easysta::constraints {

namespace {

std::string trim(const std::string& s) {
    size_t start = s.find_first_not_of(" \t\r\n");
    if (start == std::string::npos) return "";
    size_t end = s.find_last_not_of(" \t\r\n");
    return s.substr(start, end - start + 1);
}

// Extract port name from [get_ports {name}], stripping bus indices.
std::string extract_port(const std::string& line) {
    static const std::regex re(R"(\[get_ports\s+\{(.+?)\}\])");
    std::smatch m;
    if (!std::regex_search(line, m, re)) return "";
    std::string name = m[1].str();
    static const std::regex bus_re(R"(^(\w+)\[\d+\])");
    std::smatch bm;
    if (std::regex_search(name, bm, bus_re)) return bm[1].str();
    return name;
}

bool starts_with(const std::string& s, const std::string& prefix) {
    return s.size() >= prefix.size() && s.compare(0, prefix.size(), prefix) == 0;
}

bool contains(const std::string& s, const std::string& sub) {
    return s.find(sub) != std::string::npos;
}

} // namespace

SdcData load_sdc(const std::string& sdc_path) {
    SdcData data;

    static const std::regex re_name(R"(-name\s+(\S+))");
    static const std::regex re_period(R"(-period\s+([\d.]+))");
    static const std::regex re_add_delay(R"(-add_delay\s+([\d.]+))");
    static const std::regex re_unc_val(R"(set_clock_uncertainty\s+([\d.]+))");
    static const std::regex re_clk(R"(\[get_clocks\s+\{(.+?)\}\])");

    std::ifstream f(sdc_path);
    std::string raw;
    while (std::getline(f, raw)) {
        std::string line = trim(raw);
        if (line.empty() || line[0] == '#') continue;

        if (starts_with(line, "create_clock")) {
            std::smatch m_name, m_period;
            std::string port = extract_port(line);
            if (std::regex_search(line, m_name, re_name) &&
                std::regex_search(line, m_period, re_period) && !port.empty()) {
                ClockInfo clk;
                clk.name = m_name[1].str();
                clk.period = std::stod(m_period[1].str());
                clk.ports = {port};
                data.clocks[clk.name] = clk;
            }
        } else if (starts_with(line, "set_input_delay") || starts_with(line, "set_output_delay")) {
            if (contains(line, "-min") || contains(line, "-clock_fall")) continue;
            std::smatch m_delay;
            std::string port = extract_port(line);
            if (std::regex_search(line, m_delay, re_add_delay) && !port.empty()) {
                bool is_input = starts_with(line, "set_input_delay");
                PortDelayInfo pd;
                pd.delay = std::stod(m_delay[1].str());
                pd.type = is_input ? "internal" : "external";
                pd.minmax = "max";
                data.port_delay[port] = pd;
            }
        } else if (starts_with(line, "set_clock_uncertainty")) {
            if (contains(line, "-hold")) continue;
            std::smatch m_val, m_clk;
            if (std::regex_search(line, m_val, re_unc_val) &&
                std::regex_search(line, m_clk, re_clk)) {
                std::string clk_name = m_clk[1].str();
                auto it = data.clocks.find(clk_name);
                if (it == data.clocks.end()) {
                    ClockInfo clk;
                    clk.name = clk_name;
                    it = data.clocks.emplace(clk_name, clk).first;
                }
                it->second.uncertainty = std::stod(m_val[1].str());
            }
        }
    }

    for (const auto& kv : data.clocks) {
        for (const auto& port : kv.second.ports) {
            data.port_to_clock[port] = kv.second.name;
        }
    }

    return data;
}

} // namespace easysta::constraints
