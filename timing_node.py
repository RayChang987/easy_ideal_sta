class TimingNode:
    def __init__(self, inst: str, pin: str, type: str):
        self.inst = inst
        self.pin  = pin
        self.type = type
        self.name = f"{inst}/{pin}"

        self.fanin  = []   # list[TimingArc]
        self.fanout = []   # list[TimingArc]

        # STA state
        self.rise_at   = 0.0
        self.fall_at   = 0.0
        self.rise_slew = 0.0
        self.fall_slew = 0.0
        self.load      = 0.0

        # Critical-path traceback
        self.worst_pred_arc   = None
        self.worst_pred_delay = 0.0

        # Resizer info
        self.type_id  = -1
        self.sizable  = False
        self.cell_gp  = None

        self.end_point_slack = 1e18

    def __repr__(self):
        return self.name

    def at(self):
        return max(self.rise_at, self.fall_at)


class TimingArc:
    def __init__(self, src, dst, arc_type: str,
                 delay: float = 0.0, when: str = "None", timing_type: str = "None"):
        self.src         = src
        self.dst         = dst
        self.arc_type    = arc_type    # "cell" or "net"
        self.rise_delay  = delay
        self.fall_delay  = delay
        self.when        = when
        self.timing_type = timing_type

    def __repr__(self):
        return (f"{self.src} -> {self.dst} "
                f"({self.arc_type}, rise={self.rise_delay}, fall={self.fall_delay})")
