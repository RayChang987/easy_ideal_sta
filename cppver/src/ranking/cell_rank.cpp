#include "easysta/ranking/cell_rank.hpp"

#include <algorithm>
#include <fstream>
#include <sstream>
#include <unordered_set>

namespace easysta::ranking {

namespace {

std::vector<std::string> split_csv_line(const std::string& line) {
    std::vector<std::string> fields;
    std::string cur;
    bool in_quotes = false;
    for (char c : line) {
        if (c == '"') {
            in_quotes = !in_quotes;
        } else if (c == ',' && !in_quotes) {
            fields.push_back(cur);
            cur.clear();
        } else {
            cur.push_back(c);
        }
    }
    fields.push_back(cur);
    return fields;
}

std::string trim(const std::string& s) {
    size_t start = s.find_first_not_of(" \t\r\n");
    if (start == std::string::npos) return "";
    size_t end = s.find_last_not_of(" \t\r\n");
    return s.substr(start, end - start + 1);
}

bool is_missing(const std::string& s) {
    return s.empty() || s == "NaN" || s == "nan";
}

} // namespace

GateRankResult load_gate_rank(const std::string& csv_path) {
    GateRankResult result;

    std::ifstream f(csv_path);
    std::string header_line;
    if (!std::getline(f, header_line)) return result;

    auto headers = split_csv_line(header_line);
    int idx_type = -1, idx_name = -1, idx_delay = -1, idx_power = -1;
    for (size_t i = 0; i < headers.size(); ++i) {
        std::string h = trim(headers[i]);
        if (h == "Target_Cell_Type") idx_type = static_cast<int>(i);
        else if (h == "Cell_Name") idx_name = static_cast<int>(i);
        else if (h == "Delay_Raw") idx_delay = static_cast<int>(i);
        else if (h == "Power_Raw") idx_power = static_cast<int>(i);
    }
    if (idx_type < 0 || idx_name < 0 || idx_delay < 0 || idx_power < 0) return result;

    std::unordered_map<std::string, std::vector<GateRankRow>> by_type;

    std::string line;
    while (std::getline(f, line)) {
        if (line.empty()) continue;
        auto fields = split_csv_line(line);
        int max_idx = std::max({idx_type, idx_name, idx_delay, idx_power});
        if (static_cast<int>(fields.size()) <= max_idx) continue;

        std::string type = trim(fields[idx_type]);
        std::string name = trim(fields[idx_name]);
        std::string delay_s = trim(fields[idx_delay]);
        std::string power_s = trim(fields[idx_power]);

        if (is_missing(type) || is_missing(name) || is_missing(delay_s) || is_missing(power_s)) {
            continue; // mirrors pandas .dropna()
        }

        GateRankRow row;
        row.cell_name = name;
        row.delay_raw = std::stod(delay_s);
        row.power_raw = std::stod(power_s);
        by_type[type].push_back(row);
    }

    for (auto& kv : by_type) {
        const std::string& type = kv.first;
        auto& rows = kv.second;
        // Stable sort by Power_Raw ascending (mirrors sort_values("Power_Raw")).
        std::stable_sort(rows.begin(), rows.end(),
                          [](const GateRankRow& a, const GateRankRow& b) {
                              return a.power_raw < b.power_raw;
                          });

        // drop_duplicates("Cell_Name") keeping first occurrence.
        std::unordered_set<std::string> seen;
        std::vector<GateRankRow> deduped;
        for (auto& row : rows) {
            if (seen.insert(row.cell_name).second) {
                deduped.push_back(row);
            }
        }

        result.gate_rank[type] = deduped;
        auto& cells = result.type_to_cells[type];
        for (size_t i = 0; i < deduped.size(); ++i) {
            cells.push_back(deduped[i].cell_name);
            result.cell_lookup[deduped[i].cell_name] = std::make_pair(type, static_cast<int>(i));
        }
    }

    return result;
}

} // namespace easysta::ranking
