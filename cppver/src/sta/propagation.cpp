#include "easysta/sta/propagation.hpp"

#include <algorithm>
#include <cmath>
#include <iomanip>
#include <iostream>
#include <limits>
#include <unordered_set>

#include "easysta/graph/timing_table.hpp"

namespace easysta::sta {

using easysta::constraints::ClockInfo;
using easysta::constraints::SdcData;
using easysta::graph::TimingArc;
using easysta::graph::TimingNode;
using easysta::liberty::CellInfo;
using easysta::liberty::TimingTable;

namespace {

// ASAP7 wire RC parameters for placement-stage estimation.
// DEF unit: 1 unit = 1 nm = 0.001 um (UNITS DISTANCE MICRONS 1000)
// Liberty units: time in ps, capacitance in fF.
constexpr double kDefUnitToUm = 1.0 / 1000;      // nm -> um
constexpr double kWireCapFfPerUm = 0.2;           // fF/um (average across M1-M4)
constexpr double kWireResOhmPerUm = 20.0;         // ohm/um (average across M1-M4)

double wire_delay_ps(double wire_length_def_units) {
    double length_um = wire_length_def_units * kDefUnitToUm;
    double cap_ff = length_um * kWireCapFfPerUm;
    double res_ohm = length_um * kWireResOhmPerUm;
    return 0.5 * res_ohm * cap_ff * 1e-3;
}

std::pair<double, double> get_delay_and_slew(const std::unordered_map<std::string, TimingTable>& tt,
                                              const std::string& transition_type,
                                              double in_slew, double output_cap) {
    auto delay_it = tt.find("cell_" + transition_type);
    auto slew_it = tt.find(transition_type + "_transition");
    if (delay_it == tt.end() || !delay_it->second.has_values ||
        slew_it == tt.end() || !slew_it->second.has_values) {
        return {0.0, 0.0};
    }
    double d = graph::get_value_from_table(delay_it->second.values, delay_it->second.index_1,
                                            delay_it->second.index_2, in_slew, output_cap);
    double s = graph::get_value_from_table(slew_it->second.values, slew_it->second.index_1,
                                            slew_it->second.index_2, in_slew, output_cap);
    return {d, s};
}

const std::string& resolve_type(const TimingNode* node, const TypeToCells& type_to_cells) {
    if (node->sizable) {
        return type_to_cells.at(node->cell_gp)[node->type_id];
    }
    return node->type;
}

} // namespace

double calculate_node(TimingNode* node,
                       const std::unordered_map<std::string, CellInfo>& cell_db,
                       const SdcData& sdc_data,
                       const std::unordered_map<std::string, std::string>& inst_to_clocks,
                       const TypeToCells& type_to_cells,
                       const NetWl* net_wl) {
    double max_at = -1.0;
    double max_rise_at = -1.0;
    double max_fall_at = -1.0;
    TimingArc* best_arc = nullptr;
    double best_step_delay = 0.0;

    double default_period = std::numeric_limits<double>::infinity();
    bool have_period = false;
    double default_uncertainty = 0.0;
    for (const auto& kv : sdc_data.clocks) {
        if (kv.second.period.has_value()) {
            default_period = have_period ? std::min(default_period, *kv.second.period) : *kv.second.period;
            have_period = true;
        }
        default_uncertainty = std::max(default_uncertainty, kv.second.uncertainty);
    }

    for (TimingArc* arc : node->fanin) {
        TimingNode* src_node = arc->src;
        std::string src_type = resolve_type(src_node, type_to_cells);

        std::vector<std::tuple<double, double, double>> rise_candidates;
        std::vector<std::tuple<double, double, double>> fall_candidates;

        if (arc->arc_type == "net") {
            double net_delay = 0.0;
            if (net_wl != nullptr) {
                std::string src_key = src_node->inst + "/" + src_node->pin;
                auto it = net_wl->find(src_key);
                double wl = (it != net_wl->end()) ? it->second : 0.0;
                net_delay = wire_delay_ps(wl);
            }
            rise_candidates.emplace_back(src_node->rise_at + net_delay, net_delay, src_node->rise_slew);
            fall_candidates.emplace_back(src_node->fall_at + net_delay, net_delay, src_node->fall_slew);

        } else if (arc->arc_type == "cell") {
            std::string key = arc->src->pin + "/" + node->pin + "/" + arc->when;
            if (arc->timing_type != "None") key += "/" + arc->timing_type;

            const auto& arc_def = cell_db.at(src_type).timing_arcs.at(key);
            const auto& timing_table = arc_def.timing_tables;
            const std::string& timing_sense = arc_def.timing_sense;
            double output_cap = node->load;

            if (timing_sense == "positive_unate" || timing_sense == "non_unate") {
                if (timing_table.count("cell_rise")) {
                    auto [d, s] = get_delay_and_slew(timing_table, "rise", src_node->rise_slew, output_cap);
                    rise_candidates.emplace_back(src_node->rise_at + d, d, s);
                }
                if (timing_table.count("cell_fall")) {
                    auto [d, s] = get_delay_and_slew(timing_table, "fall", src_node->fall_slew, output_cap);
                    fall_candidates.emplace_back(src_node->fall_at + d, d, s);
                }
            }
            if (timing_sense == "negative_unate" || timing_sense == "non_unate") {
                if (timing_table.count("cell_rise")) {
                    auto [d, s] = get_delay_and_slew(timing_table, "rise", src_node->fall_slew, output_cap);
                    rise_candidates.emplace_back(src_node->fall_at + d, d, s);
                }
                if (timing_table.count("cell_fall")) {
                    auto [d, s] = get_delay_and_slew(timing_table, "fall", src_node->rise_slew, output_cap);
                    fall_candidates.emplace_back(src_node->rise_at + d, d, s);
                }
            }
        }

        double rise_at, current_rise_delay, rise_slew;
        if (!rise_candidates.empty()) {
            auto best = *std::max_element(rise_candidates.begin(), rise_candidates.end(),
                                           [](const auto& a, const auto& b) { return std::get<0>(a) < std::get<0>(b); });
            rise_at = std::get<0>(best);
            current_rise_delay = std::get<1>(best);
            rise_slew = std::get<2>(best);
        } else {
            rise_at = -1.0;
            current_rise_delay = 0.0;
            rise_slew = 0.0;
        }

        double fall_at, current_fall_delay, fall_slew;
        if (!fall_candidates.empty()) {
            auto best = *std::max_element(fall_candidates.begin(), fall_candidates.end(),
                                           [](const auto& a, const auto& b) { return std::get<0>(a) < std::get<0>(b); });
            fall_at = std::get<0>(best);
            current_fall_delay = std::get<1>(best);
            fall_slew = std::get<2>(best);
        } else {
            fall_at = -1.0;
            current_fall_delay = 0.0;
            fall_slew = 0.0;
        }

        arc->rise_delay = current_rise_delay;
        arc->fall_delay = current_fall_delay;

        if (rise_at > max_rise_at) {
            max_rise_at = rise_at;
            if (rise_at > max_at) {
                max_at = rise_at;
                best_arc = arc;
                best_step_delay = current_rise_delay;
            }
        }
        if (fall_at > max_fall_at) {
            max_fall_at = fall_at;
            if (fall_at > max_at) {
                max_at = fall_at;
                best_arc = arc;
                best_step_delay = current_fall_delay;
            }
        }

        node->rise_slew = std::max(node->rise_slew, rise_slew);
        node->fall_slew = std::max(node->fall_slew, fall_slew);
    }

    node->rise_at = max_rise_at;
    node->fall_at = max_fall_at;
    node->rise_domain = node->rise_at >= node->fall_at;
    node->worst_pred_arc = best_arc;
    node->worst_pred_delay = best_step_delay;

    auto cdb_it = cell_db.find(node->type);
    std::optional<std::string> clocked_on = (cdb_it != cell_db.end()) ? cdb_it->second.clocked_on : std::nullopt;
    std::string node_type = resolve_type(node, type_to_cells);
    double slack = 0.0;

    if (node->fanout.empty()) {
        double clock_period = default_period - default_uncertainty;
        if (node->type != "Port") {
            auto inst_it = inst_to_clocks.find(node->inst);
            if (clocked_on.has_value() && inst_it != inst_to_clocks.end()) {
                const ClockInfo& inst_clk = sdc_data.clocks.at(inst_it->second);
                clock_period = inst_clk.period.value_or(0.0) - inst_clk.uncertainty;
            } else {
                return 0.0;
            }
        }

        if (node->type == "Port") {
            auto pd_it = sdc_data.port_delay.find(node->pin);
            double output_delay = (pd_it != sdc_data.port_delay.end()) ? pd_it->second.delay : 0.0;
            double required_time = clock_period - output_delay;
            slack = required_time - node->at();
        } else {
            double rise_setup_time = 0.0;
            double fall_setup_time = 0.0;

            if (clocked_on.has_value()) {
                std::string clk_pin = (!clocked_on->empty() && (*clocked_on)[0] == '!')
                                           ? clocked_on->substr(1) : *clocked_on;
                std::string key_prefix = clk_pin + "/" + node->pin;

                const auto& node_type_arcs = cell_db.at(node_type).timing_arcs;
                for (const auto& kv : node_type_arcs) {
                    if (kv.first.rfind(key_prefix, 0) != 0) continue;
                    const auto& setup_table = kv.second.timing_tables;
                    double clock_slew = 0.0;

                    auto rc_it = setup_table.find("rise_constraint");
                    if (rc_it != setup_table.end() && rc_it->second.has_values) {
                        const auto& dt = rc_it->second;
                        rise_setup_time = std::max(
                            graph::get_value_from_table(dt.values, dt.index_1, dt.index_2, node->rise_slew, clock_slew),
                            rise_setup_time);
                    }
                    auto fc_it = setup_table.find("fall_constraint");
                    if (fc_it != setup_table.end() && fc_it->second.has_values) {
                        const auto& dt = fc_it->second;
                        fall_setup_time = std::max(
                            graph::get_value_from_table(dt.values, dt.index_1, dt.index_2, node->fall_slew, clock_slew),
                            fall_setup_time);
                    }
                }
            }

            double rise_required = clock_period - rise_setup_time;
            double fall_required = clock_period - fall_setup_time;
            slack = std::min(rise_required - node->rise_at, fall_required - node->fall_at);
        }
    }

    node->end_point_slack = slack;
    return slack;
}

std::vector<std::pair<TimingNode*, double>> calculate_delay(
    const std::vector<TimingNode*>& topo_order,
    const std::unordered_map<std::string, CellInfo>& cell_db,
    const SdcData& sdc_data,
    const std::unordered_map<std::string, std::string>& inst_to_clocks,
    const TypeToCells& type_to_cells,
    const NetWl* net_wl) {
    std::cout << "Starting Delay Calculation..." << std::endl;
    double tns = 0.0;
    double wns = 0.0;
    std::vector<std::pair<TimingNode*, double>> violation_end_points;
    TimingNode* worst_node = nullptr;

    std::unordered_set<TimingNode*> wire_cap_added;
    for (auto it = topo_order.rbegin(); it != topo_order.rend(); ++it) {
        TimingNode* node = *it;
        if (node->inst == "PIN") {
            auto pd_it = sdc_data.port_delay.find(node->pin);
            if (pd_it != sdc_data.port_delay.end()) {
                node->fall_at = pd_it->second.delay;
                node->rise_at = pd_it->second.delay;
            }
        }
        for (TimingArc* arc : node->fanout) {
            if (arc->arc_type == "net") {
                TimingNode* load_pin = arc->dst;
                if (load_pin->inst != "PIN") {
                    std::string cell_type = resolve_type(load_pin, type_to_cells);
                    arc->src->load += cell_db.at(cell_type).pins.at(load_pin->pin).capacitance;
                }
                if (net_wl != nullptr) {
                    TimingNode* driver = arc->src;
                    if (!wire_cap_added.count(driver)) {
                        std::string src_key = driver->inst + "/" + driver->pin;
                        auto it2 = net_wl->find(src_key);
                        double wire_length = (it2 != net_wl->end()) ? it2->second : 0.0;
                        driver->load += wire_length * kDefUnitToUm * kWireCapFfPerUm;
                        wire_cap_added.insert(driver);
                    }
                }
            }
        }
    }

    for (TimingNode* node : topo_order) {
        if (node->fanin.empty()) continue;
        double slack = calculate_node(node, cell_db, sdc_data, inst_to_clocks, type_to_cells, net_wl);
        if (slack < 0) {
            tns += slack;
            if (worst_node == nullptr || slack < wns) {
                worst_node = node;
                wns = slack;
            }
            if (node->fanout.empty()) {
                violation_end_points.emplace_back(node, slack);
            }
        }
    }

    std::cout << "Delay Calculation Done." << std::endl;
    std::cout << std::fixed << std::setprecision(2);
    std::cout << "TNS: " << (tns / 1000.0) << " ns, WNS: " << (wns / 1000.0) << " ns" << std::endl;
    if (worst_node) {
        std::cout << "Worst Node: " << worst_node->name << ", AT=" << (worst_node->at() / 1000.0) << " ns" << std::endl;
        report_instance_path(worst_node);
    }
    return violation_end_points;
}

void report_instance_path(TimingNode* end_node) {
    if (end_node == nullptr) return;

    std::cout << std::fixed;
    std::cout << std::string(60, '=') << std::endl;
    std::cout << "Critical Path Report for: " << end_node->inst << std::endl;
    std::cout << "Worst Arrival Time: " << std::setprecision(2) << (end_node->at() / 1000.0) << " ns" << std::endl;
    std::cout << std::string(60, '=') << std::endl;

    std::vector<TimingNode*> path_stack;
    TimingNode* curr = end_node;
    while (curr != nullptr) {
        path_stack.push_back(curr);
        curr = curr->worst_pred_arc ? curr->worst_pred_arc->src : nullptr;
    }

    TimingNode* start_node = path_stack.back();
    path_stack.pop_back();
    std::cout << "Startpoint: " << start_node->name << " (AT: " << std::setprecision(2)
              << (start_node->at() / 1000.0) << " ns)" << std::endl;

    while (!path_stack.empty()) {
        TimingNode* next_node = path_stack.back();
        path_stack.pop_back();
        TimingArc* arc = next_node->worst_pred_arc;
        const char* arrow = (arc->arc_type == "net") ? "--(net)-->" : "--(cell)-->";

        if (arc->arc_type == "cell") {
            std::cout << "Load: " << next_node->load << std::endl;
            std::cout << "Fall Slew: " << start_node->fall_slew << std::endl;
            std::cout << "Rise Slew: " << start_node->rise_slew << std::endl;
            std::cout << "Output Fall Slew: " << next_node->fall_slew << std::endl;
            std::cout << "Output Rise Slew: " << next_node->rise_slew << std::endl;
        }

        std::cout << "Rise: " << start_node->inst << "/" << start_node->pin << " " << arrow << " "
                  << next_node->inst << "/" << next_node->pin << " : delay " << std::setprecision(2)
                  << (arc->rise_delay / 1000.0) << " ns (AT: " << std::setprecision(4)
                  << (next_node->rise_at / 1000.0) << " ns)" << std::endl;
        std::cout << "Fall: " << start_node->inst << "/" << start_node->pin << " " << arrow << " "
                  << next_node->inst << "/" << next_node->pin << " : delay " << std::setprecision(2)
                  << (arc->fall_delay / 1000.0) << " ns (AT: " << std::setprecision(4)
                  << (next_node->fall_at / 1000.0) << " ns)" << std::endl;

        start_node = next_node;
    }

    std::cout << std::string(60, '=') << std::endl;
}

} // namespace easysta::sta
