from collections import deque
from timing_node import TimingNode, TimingArc


class TimingGraph:
    def __init__(self):
        self.nodes: dict = {}   # (inst, pin) -> TimingNode
        self.arcs:  list = []
        self.instance_to_clocks: dict = {}   # inst_name -> clock_name

    def get_node(self, inst: str, pin: str, type: str = "Unknown") -> TimingNode:
        key = (inst, pin)
        if key not in self.nodes:
            if type == "Unknown":
                raise RuntimeError(f"Node ({inst}, {pin}) not found and type unspecified")
            self.nodes[key] = TimingNode(inst, pin, type)
        return self.nodes[key]

    def add_arc(self, src: TimingNode, dst: TimingNode, arc_type: str,
                delay: float = 0.0, when: str = "None", timing_type: str = "None"):
        arc = TimingArc(src, dst, arc_type, delay, when, timing_type)
        src.fanout.append(arc)
        dst.fanin.append(arc)
        self.arcs.append(arc)

    def topo_sort(self) -> list:
        indeg = {n: 0 for n in self.nodes.values()}
        for arc in self.arcs:
            indeg[arc.dst] += 1

        q     = deque(n for n, d in indeg.items() if d == 0)
        order = []
        while q:
            node = q.popleft()
            order.append(node)
            for arc in node.fanout:
                indeg[arc.dst] -= 1
                if indeg[arc.dst] == 0:
                    q.append(arc.dst)

        if len(order) != len(self.nodes):
            self.find_cycle()
        return order

    def find_cycle(self) -> bool:
        visited, stack, parent = set(), set(), {}

        def dfs(u):
            visited.add(u)
            stack.add(u)
            for arc in u.fanout:
                v = arc.dst
                if v not in visited:
                    parent[v] = u
                    if dfs(v):
                        return True
                elif v in stack:
                    cycle, cur = [v], u
                    while cur != v:
                        cycle.append(cur)
                        cur = parent[cur]
                    cycle.append(v)
                    print("Cycle: " + " -> ".join(n.name for n in reversed(cycle)))
                    return True
            stack.remove(u)
            return False

        for node in self.nodes.values():
            if node not in visited and dfs(node):
                return True
        return False
