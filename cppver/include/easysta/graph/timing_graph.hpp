#pragma once

#include <memory>
#include <string>
#include <unordered_map>
#include <vector>

#include "easysta/graph/timing_node.hpp"

namespace easysta::graph {

struct PinKeyHash {
    size_t operator()(const std::pair<std::string, std::string>& k) const {
        return std::hash<std::string>()(k.first) ^ (std::hash<std::string>()(k.second) << 1);
    }
};

// Mirrors timing_graph.py: TimingGraph
class TimingGraph {
public:
    std::unordered_map<std::pair<std::string, std::string>, std::unique_ptr<TimingNode>, PinKeyHash> nodes;
    std::vector<std::unique_ptr<TimingArc>> arcs;
    std::unordered_map<std::string, std::string> instance_to_clocks;

    TimingNode* get_node(const std::string& inst, const std::string& pin,
                          const std::string& type = "Unknown");

    TimingArc* add_arc(TimingNode* src, TimingNode* dst, const std::string& arc_type,
                        double delay = 0.0, const std::string& when = "None",
                        const std::string& timing_type = "None");

    // Kahn topo sort; on cycle, prints the cycle via find_cycle() and returns
    // a partial/empty order (mirrors the Python behavior).
    std::vector<TimingNode*> topo_sort();

    bool find_cycle();
};

} // namespace easysta::graph
