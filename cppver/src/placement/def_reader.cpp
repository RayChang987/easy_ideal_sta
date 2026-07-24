#include "easysta/placement/def_reader.hpp"

#include <algorithm>
#include <cmath>
#include <fstream>
#include <limits>
#include <regex>
#include <set>

namespace easysta::placement {

namespace {

bool starts_with_dash_space(const std::string& s) {
    return s.size() >= 2 && s[0] == '-' && s[1] == ' ';
}

std::string trim(const std::string& s) {
    size_t start = s.find_first_not_of(" \t\r\n");
    if (start == std::string::npos) return "";
    size_t end = s.find_last_not_of(" \t\r\n");
    return s.substr(start, end - start + 1);
}

long long manhattan_dist(const DefPoint& a, const DefPoint& b) {
    return std::llabs(a.first - b.first) + std::llabs(a.second - b.second);
}

double basic_prim(const std::vector<DefPoint>& pts) {
    size_t n = pts.size();
    if (n <= 1) return 0.0;
    std::vector<bool> visited(n, false);
    std::vector<double> min_dist(n, std::numeric_limits<double>::infinity());
    min_dist[0] = 0.0;
    double total = 0.0;
    for (size_t iter = 0; iter < n; ++iter) {
        int u = -1;
        double curr_m = std::numeric_limits<double>::infinity();
        for (size_t i = 0; i < n; ++i) {
            if (!visited[i] && min_dist[i] < curr_m) {
                curr_m = min_dist[i];
                u = static_cast<int>(i);
            }
        }
        if (u == -1) break;
        visited[u] = true;
        total += curr_m;
        for (size_t v = 0; v < n; ++v) {
            if (!visited[v]) {
                double d = static_cast<double>(manhattan_dist(pts[u], pts[v]));
                if (d < min_dist[v]) min_dist[v] = d;
            }
        }
    }
    return total;
}

double fast_partition_mst(const std::vector<DefPoint>& points) {
    std::vector<DefPoint> pts_sorted = points;
    std::stable_sort(pts_sorted.begin(), pts_sorted.end(),
                      [](const DefPoint& a, const DefPoint& b) { return a.first < b.first; });

    const size_t chunk_size = 100;
    double total_approx_len = 0.0;
    bool have_last = false;
    DefPoint last_point_of_prev_chunk{};

    for (size_t start = 0; start < pts_sorted.size(); start += chunk_size) {
        size_t end = std::min(start + chunk_size, pts_sorted.size());
        std::vector<DefPoint> chunk(pts_sorted.begin() + start, pts_sorted.begin() + end);

        total_approx_len += basic_prim(chunk);

        if (have_last) {
            total_approx_len += static_cast<double>(manhattan_dist(last_point_of_prev_chunk, chunk.front()));
        }
        last_point_of_prev_chunk = chunk.back();
        have_last = true;
    }

    return total_approx_len;
}

} // namespace

double calc_rmst_length_fast(std::vector<DefPoint> points) {
    std::set<DefPoint> uniq(points.begin(), points.end());
    std::vector<DefPoint> pts(uniq.begin(), uniq.end());
    size_t n = pts.size();

    if (n <= 1) return 0.0;

    long long min_x = pts[0].first, max_x = pts[0].first;
    long long min_y = pts[0].second, max_y = pts[0].second;
    for (const auto& p : pts) {
        min_x = std::min(min_x, p.first);
        max_x = std::max(max_x, p.first);
        min_y = std::min(min_y, p.second);
        max_y = std::max(max_y, p.second);
    }
    double hpwl = static_cast<double>((max_x - min_x) + (max_y - min_y));

    if (n <= 3) return hpwl;
    if (n > 2000) return fast_partition_mst(pts) * 0.5;

    return basic_prim(pts);
}

namespace {

void process_net(const std::string& net_str,
                  const std::unordered_map<std::string, DefPoint>& inst_pos,
                  const std::unordered_map<std::string, DefPoint>& port_pos,
                  std::unordered_map<std::string, DefPoint>& component_pos,
                  std::unordered_map<std::string, double>& pin_wl,
                  const std::regex& pair_re) {
    std::vector<std::pair<std::string, std::string>> pairs;
    auto begin = std::sregex_iterator(net_str.begin(), net_str.end(), pair_re);
    auto end = std::sregex_iterator();
    for (auto it = begin; it != end; ++it) {
        pairs.emplace_back((*it)[1].str(), (*it)[2].str());
    }

    std::vector<DefPoint> net_points;
    for (const auto& pr : pairs) {
        const std::string& inst = pr.first;
        const std::string& pin = pr.second;
        std::string pin_key = inst + "/" + pin;

        const DefPoint* pos = nullptr;
        if (inst == "PIN") {
            auto it = port_pos.find(pin);
            if (it != port_pos.end()) pos = &it->second;
        } else {
            auto it = inst_pos.find(inst);
            if (it != inst_pos.end()) pos = &it->second;
        }
        if (pos == nullptr) continue;

        component_pos.emplace(pin_key, *pos); // setdefault semantics
        net_points.push_back(*pos);
    }

    double wl = net_points.empty() ? 0.0 : calc_rmst_length_fast(net_points);
    for (const auto& pr : pairs) {
        std::string pin_key = pr.first + "/" + pr.second;
        if (component_pos.find(pin_key) != component_pos.end()) {
            pin_wl[pin_key] = wl;
        }
    }
}

} // namespace

DefResult read_def(const std::string& file_path) {
    std::unordered_map<std::string, DefPoint> inst_pos;
    std::unordered_map<std::string, DefPoint> port_pos;

    static const std::regex placed_re(R"((?:PLACED|FIXED)\s+\(\s*(-?\d+)\s+(-?\d+)\s*\))");
    static const std::regex pair_re(R"(\(\s*(\S+)\s+(\S+)\s*\))");
    static const std::regex comp_start_re(R"(^COMPONENTS\s+\d+)");
    static const std::regex pins_start_re(R"(^PINS\s+\d+)");
    static const std::regex nets_start_re(R"(^NETS\s+\d+)");
    static const std::regex end_re(R"(^END\s+)");
    static const std::regex dash_name_re(R"(^-\s+(\S+))");

    DefResult result;

    enum class Section { None, Components, Pins, Nets };
    Section section = Section::None;
    std::string current_port;
    bool have_current_port = false;
    std::string net_buf;
    bool have_net_buf = false;

    std::ifstream f(file_path);
    std::string raw;
    while (std::getline(f, raw)) {
        std::string line = trim(raw);

        if (std::regex_search(line, comp_start_re)) {
            section = Section::Components;
            continue;
        }
        if (std::regex_search(line, pins_start_re)) {
            section = Section::Pins;
            have_current_port = false;
            continue;
        }
        if (std::regex_search(line, nets_start_re)) {
            section = Section::Nets;
            have_net_buf = false;
            continue;
        }
        if (std::regex_search(line, end_re)) {
            if (have_net_buf) {
                process_net(net_buf, inst_pos, port_pos, result.component_pos, result.pin_wl, pair_re);
                have_net_buf = false;
            }
            section = Section::None;
            have_current_port = false;
            continue;
        }

        if (section == Section::Components && starts_with_dash_space(line)) {
            std::smatch m_name, m_pos;
            if (std::regex_search(line, m_name, dash_name_re) &&
                std::regex_search(line, m_pos, placed_re)) {
                inst_pos[m_name[1].str()] = {std::stoll(m_pos[1].str()), std::stoll(m_pos[2].str())};
            }
        } else if (section == Section::Pins) {
            if (starts_with_dash_space(line)) {
                std::smatch m;
                if (std::regex_search(line, m, dash_name_re)) {
                    current_port = m[1].str();
                    have_current_port = true;
                } else {
                    have_current_port = false;
                }
            }
            if (have_current_port) {
                std::smatch m_pos;
                if (std::regex_search(line, m_pos, placed_re)) {
                    port_pos[current_port] = {std::stoll(m_pos[1].str()), std::stoll(m_pos[2].str())};
                    have_current_port = false;
                }
            }
        } else if (section == Section::Nets) {
            if (starts_with_dash_space(line)) {
                if (have_net_buf) {
                    process_net(net_buf, inst_pos, port_pos, result.component_pos, result.pin_wl, pair_re);
                }
                net_buf = line;
                have_net_buf = true;
            } else if (have_net_buf) {
                net_buf += ' ' + line;
            }

            if (have_net_buf) {
                std::string rstripped = net_buf;
                size_t end_pos = rstripped.find_last_not_of(" \t\r\n");
                if (end_pos != std::string::npos) rstripped = rstripped.substr(0, end_pos + 1);
                if (!rstripped.empty() && rstripped.back() == ';') {
                    process_net(net_buf, inst_pos, port_pos, result.component_pos, result.pin_wl, pair_re);
                    have_net_buf = false;
                }
            }
        }
    }

    return result;
}

} // namespace easysta::placement
