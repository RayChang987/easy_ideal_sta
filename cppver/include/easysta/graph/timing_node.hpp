#pragma once

#include <algorithm>
#include <string>
#include <vector>

namespace easysta::graph {

struct TimingArc;

// Mirrors timing_node.py: TimingNode
struct TimingNode {
    std::string inst;
    std::string pin;
    std::string type;
    std::string name;

    std::vector<TimingArc*> fanin;
    std::vector<TimingArc*> fanout;

    // STA state
    double rise_at = 0.0;
    double fall_at = 0.0;
    double rise_slew = 0.0;
    double fall_slew = 0.0;
    double load = 0.0;
    bool rise_domain = false;

    // Critical-path traceback
    TimingArc* worst_pred_arc = nullptr;
    double worst_pred_delay = 0.0;

    // Resizer info (unused on the base CLI path, kept for parity)
    int type_id = -1;
    bool sizable = false;
    std::string cell_gp;

    double end_point_slack = 1e18;

    TimingNode(std::string inst_, std::string pin_, std::string type_)
        : inst(std::move(inst_)), pin(std::move(pin_)), type(std::move(type_)) {
        name = inst + "/" + pin;
    }

    double at() const { return std::max(rise_at, fall_at); }
};

// Mirrors timing_node.py: TimingArc
struct TimingArc {
    TimingNode* src;
    TimingNode* dst;
    std::string arc_type;   // "cell" or "net"
    double rise_delay;
    double fall_delay;
    std::string when;
    std::string timing_type;

    TimingArc(TimingNode* src_, TimingNode* dst_, std::string arc_type_,
              double delay = 0.0, std::string when_ = "None",
              std::string timing_type_ = "None")
        : src(src_), dst(dst_), arc_type(std::move(arc_type_)),
          rise_delay(delay), fall_delay(delay), when(std::move(when_)),
          timing_type(std::move(timing_type_)) {}
};

} // namespace easysta::graph
