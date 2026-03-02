# timing_graph.py
from collections import deque
from timing_node import TimingNode, TimingArc


class TimingGraph:
    def __init__(self):
        self.nodes = {}  # (inst, pin) -> TimingNode
        self.arcs = []
        self.instance_to_clocks = (
            dict()
        )  # instance_name -> clock_name (for clocked cells)

    def get_node(self, inst: str, pin: str, type="Unknown"):
        key = (inst, pin)
        if key not in self.nodes:
            if type == "Unknown":
                raise RuntimeError(
                    f"Trying to get a node ({inst}, {pin}) but type is not specified"
                )
            self.nodes[key] = TimingNode(inst, pin, type)
        return self.nodes[key]

    def add_arc(
        self,
        src_node: TimingNode,
        dst_node: TimingNode,
        arc_type: str,
        delay: float = 0.0,
        when=None,
        timing_type: str = "None",
    ):
        arc = TimingArc(src_node, dst_node, arc_type, delay, when, timing_type)
        src_node.fanout.append(arc)
        dst_node.fanin.append(arc)
        self.arcs.append(arc)

    from collections import deque

    def topo_sort(self):
        indeg = {node: 0 for node in self.nodes.values()}
        for arc in self.arcs:
            indeg[arc.dst] += 1

        q = deque([n for n, d in indeg.items() if d == 0])
        order = []

        while q:
            node = q.popleft()
            order.append(node)
            for arc in node.fanout:
                neighbor = arc.dst
                indeg[neighbor] -= 1
                if indeg[neighbor] == 0:
                    q.append(neighbor)

        if len(order) != len(self.nodes):
            self.find_cycle()

        return order

    def find_cycle(self):
        visited = set()
        stack = set()
        parent = {}

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
                    # 👉 找到 cycle，回溯路徑
                    cycle = [v]
                    cur = u
                    while cur != v:
                        cycle.append(cur)
                        cur = parent[cur]
                    cycle.append(v)
                    cycle.reverse()

                    print("Cycle found:")
                    print(" -> ".join(n.name for n in cycle))
                    return True

            stack.remove(u)
            return False

        for node in self.nodes.values():
            if node not in visited:
                if dfs(node):
                    return True

        return False
