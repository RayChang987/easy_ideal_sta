# timing_node.py
class TimingNode:
    def __init__(self, inst, pin, type):
        self.inst = inst
        self.pin = pin
        self.type = type
        self.fanin = []  # list of TimingArc
        self.fanout = []  # list of TimingArc
        self.load = 0.0
        self.name = f"{inst}/{pin}"

        # --- STA Status ---
        self.rise_at = 0.0  # Rise Arrival Time
        self.fall_at = 0.0  # Fall Arrival Time
        self.rise_slew = 0.0  # Rise Slew
        self.fall_slew = 0.0  # Fall Slew
        self.load = 0.0  # Cap Load
        self.pin_load = 0.0
        # --- Traceback Info (新增) ---
        self.worst_pred_arc = None  # 造成最大 AT 的那條 Arc
        self.worst_pred_delay = 0.0  # 該 Arc 的 delay 值

        # Power
        self.internal_power = 0.0
        self.switching_power = 0.0
        # Resizer Info
        self.type_id = -1
        self.sizable = False
        self.cell_gp = None
        self.criticality = 0.0
        self.end_point_slack = 1e18

    def __repr__(self):
        return self.name

    def at(self):
        return max(self.rise_at, self.fall_at)


class TimingArc:
    def __init__(self, src, dst, arc_type, delay=0.0, when="None", timing_type="None"):
        self.src = src  # TimingNode
        self.dst = dst  # TimingNode
        self.arc_type = arc_type  # "cell" or "net"
        self.rise_delay = delay  # Placeholder for delay from lib
        self.fall_delay = delay  # Placeholder for delay from lib
        self.when = when  # Placeholder for when condition
        self.timing_type = timing_type

        self.real_delay = 0.0  # Delay from OpenSTA

    def __repr__(self):
        return f"{self.src} -> {self.dst} ({self.arc_type}, rise_delay={self.rise_delay}, fall_delay={self.fall_delay})"
