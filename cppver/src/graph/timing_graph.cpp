#include "easysta/graph/timing_graph.hpp"

#include <deque>
#include <functional>
#include <iostream>
#include <unordered_map>
#include <unordered_set>

namespace easysta::graph {

TimingNode* TimingGraph::get_node(const std::string& inst, const std::string& pin,
                                   const std::string& type) {
    auto key = std::make_pair(inst, pin);
    auto it = nodes.find(key);
    if (it == nodes.end()) {
        if (type == "Unknown") {
            throw std::runtime_error("Node (" + inst + ", " + pin + ") not found and type unspecified");
        }
        auto node = std::make_unique<TimingNode>(inst, pin, type);
        TimingNode* raw = node.get();
        nodes.emplace(key, std::move(node));
        return raw;
    }
    return it->second.get();
}

TimingArc* TimingGraph::add_arc(TimingNode* src, TimingNode* dst, const std::string& arc_type,
                                 double delay, const std::string& when,
                                 const std::string& timing_type) {
    auto arc = std::make_unique<TimingArc>(src, dst, arc_type, delay, when, timing_type);
    TimingArc* raw = arc.get();
    src->fanout.push_back(raw);
    dst->fanin.push_back(raw);
    arcs.push_back(std::move(arc));
    return raw;
}

std::vector<TimingNode*> TimingGraph::topo_sort() {
    std::unordered_map<TimingNode*, int> indeg;
    indeg.reserve(nodes.size());
    for (auto& kv : nodes) indeg[kv.second.get()] = 0;
    for (auto& arc : arcs) indeg[arc->dst] += 1;

    std::deque<TimingNode*> q;
    for (auto& kv : indeg) {
        if (kv.second == 0) q.push_back(kv.first);
    }

    std::vector<TimingNode*> order;
    order.reserve(nodes.size());
    while (!q.empty()) {
        TimingNode* node = q.front();
        q.pop_front();
        order.push_back(node);
        for (TimingArc* arc : node->fanout) {
            if (--indeg[arc->dst] == 0) {
                q.push_back(arc->dst);
            }
        }
    }

    if (order.size() != nodes.size()) {
        find_cycle();
    }
    return order;
}

bool TimingGraph::find_cycle() {
    std::unordered_set<TimingNode*> visited, stack;
    std::unordered_map<TimingNode*, TimingNode*> parent;

    // Iterative DFS to avoid stack overflow on large graphs; mirrors the
    // recursive Python logic (first cycle found via DFS from any unvisited node).
    std::function<bool(TimingNode*)> dfs = [&](TimingNode* u) -> bool {
        visited.insert(u);
        stack.insert(u);
        for (TimingArc* arc : u->fanout) {
            TimingNode* v = arc->dst;
            if (visited.find(v) == visited.end()) {
                parent[v] = u;
                if (dfs(v)) return true;
            } else if (stack.find(v) != stack.end()) {
                std::vector<TimingNode*> cycle{v};
                TimingNode* cur = u;
                while (cur != v) {
                    cycle.push_back(cur);
                    cur = parent[cur];
                }
                cycle.push_back(v);
                std::string msg = "Cycle: ";
                for (auto it = cycle.rbegin(); it != cycle.rend(); ++it) {
                    if (it != cycle.rbegin()) msg += " -> ";
                    msg += (*it)->name;
                }
                std::cout << msg << std::endl;
                return true;
            }
        }
        stack.erase(u);
        return false;
    };

    for (auto& kv : nodes) {
        TimingNode* node = kv.second.get();
        if (visited.find(node) == visited.end() && dfs(node)) {
            return true;
        }
    }
    return false;
}

std::vector<std::vector<TimingNode*>> levelize(const std::vector<TimingNode*>& topo_order) {
    std::unordered_map<TimingNode*, int> level;
    level.reserve(topo_order.size());

    int max_level = -1;
    for (TimingNode* node : topo_order) {
        int lvl = 0;
        for (TimingArc* arc : node->fanin) {
            lvl = std::max(lvl, level.at(arc->src) + 1);
        }
        level[node] = lvl;
        max_level = std::max(max_level, lvl);
    }

    std::vector<std::vector<TimingNode*>> levels(max_level + 1);
    for (TimingNode* node : topo_order) {
        levels[level.at(node)].push_back(node);
    }
    return levels;
}

} // namespace easysta::graph
