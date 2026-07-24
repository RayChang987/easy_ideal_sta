#include "easysta/constraints/sdf_parser.hpp"

#include <fstream>
#include <regex>
#include <stdexcept>

namespace easysta::constraints {

namespace {

std::string strip_backslash(std::string s) {
    std::string out;
    out.reserve(s.size());
    for (char c : s) {
        if (c != '\\') out.push_back(c);
    }
    return out;
}

std::string trim(const std::string& s) {
    size_t start = s.find_first_not_of(" \t\r\n");
    if (start == std::string::npos) return "";
    size_t end = s.find_last_not_of(" \t\r\n");
    return s.substr(start, end - start + 1);
}

void store(SdfData& data, const std::string& src, const std::string& dst,
           const std::string& r_str, const std::string& f_str) {
    double r = std::stod(r_str);
    double f = f_str.empty() ? r : std::stod(f_str);
    data[src][dst] = std::make_pair(r, f);
}

bool contains(const std::string& s, const char* sub) {
    return s.find(sub) != std::string::npos;
}

} // namespace

SdfData load_sdf(const std::string& file_path) {
    std::ifstream f(file_path);
    if (!f.good()) {
        throw std::runtime_error("SDF file not found: '" + file_path + "'");
    }

    static const std::regex re_instance(R"(\(INSTANCE\s*([^)]*)\))");
    static const std::regex re_interconnect(
        R"(\(INTERCONNECT\s+(\S+)\s+(\S+)\s+\([^:]+::([\d.\-]+)\)(?:\s+\([^:]+::([\d.\-]+)\))?)");
    static const std::regex re_iopath(
        R"(\(IOPATH\s+(\S+)\s+(\S+)\s+\([^:]+::([\d.\-]+)\)(?:\s+\([^:]+::([\d.\-]+)\))?)");

    SdfData data;
    std::string current_inst;

    std::string line;
    while (std::getline(f, line)) {
        if (contains(line, "INSTANCE")) {
            std::smatch m;
            if (std::regex_search(line, m, re_instance)) {
                current_inst = strip_backslash(trim(m[1].str()));
            }
            continue;
        }

        if (contains(line, "IOPATH")) {
            std::smatch m;
            if (std::regex_search(line, m, re_iopath)) {
                std::string prefix = (!current_inst.empty() && current_inst != "*")
                                          ? current_inst + "/" : "";
                store(data, prefix + m[1].str(), prefix + m[2].str(), m[3].str(),
                      m[4].matched ? m[4].str() : "");
            }
            continue;
        }

        if (contains(line, "INTERCONNECT")) {
            std::smatch m;
            if (std::regex_search(line, m, re_interconnect)) {
                store(data, strip_backslash(m[1].str()), strip_backslash(m[2].str()),
                      m[3].str(), m[4].matched ? m[4].str() : "");
            }
        }
    }

    return data;
}

} // namespace easysta::constraints
