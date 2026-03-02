import heapq
from lefdef import C_DefReader
import sys


# === 1. 增加 RMST (最小生成樹) 演算法 ===
def get_manhattan_dist(p1, p2):
    return abs(p1[0] - p2[0]) + abs(p1[1] - p2[1])


def calc_rmst_length_fast(points):
    points = list(set(points))
    n = len(points)

    if n <= 1:
        return 0

    # 計算 HPWL 作為基準
    xs = [p[0] for p in points]
    ys = [p[1] for p in points]
    hpwl = (max(xs) - min(xs)) + (max(ys) - min(ys))

    if n <= 3:
        return hpwl
    if n > 2000:
        return fast_partition_mst(points) * 0.5

    # --- Prim's Algorithm (O(N^2)) ---
    visited = [False] * n
    min_dist = [float("inf")] * n
    min_dist[0] = 0
    total_len = 0

    for _ in range(n):
        u = -1
        curr_min = float("inf")
        for i in range(n):
            if not visited[i] and min_dist[i] < curr_min:
                curr_min = min_dist[i]
                u = i
        if u == -1:
            break
        visited[u] = True
        total_len += curr_min
        for v in range(n):
            if not visited[v]:
                dist = get_manhattan_dist(points[u], points[v])
                if dist < min_dist[v]:
                    min_dist[v] = dist
    # if n > 1000:
    #     print(f'{total_len} {est_wl} {n}, Ratio: {total_len/est_wl:.2f}')
    return total_len


def fast_partition_mst(points):

    pts_sorted = sorted(points, key=lambda p: p[0])

    chunk_size = 100
    chunks = [
        pts_sorted[i : i + chunk_size] for i in range(0, len(pts_sorted), chunk_size)
    ]

    total_approx_len = 0
    last_point_of_prev_chunk = None

    for chunk in chunks:

        total_approx_len += basic_prim(chunk)


        if last_point_of_prev_chunk:

            total_approx_len += get_manhattan_dist(last_point_of_prev_chunk, chunk[0])
        last_point_of_prev_chunk = chunk[-1]

    return total_approx_len


def basic_prim(pts):

    n = len(pts)
    if n <= 1:
        return 0
    visited = [False] * n
    min_dist = [float("inf")] * n
    min_dist[0] = 0
    total = 0
    for _ in range(n):
        u = -1
        curr_m = float("inf")
        for i in range(n):
            if not visited[i] and min_dist[i] < curr_m:
                curr_m = min_dist[i]
                u = i
        if u == -1:
            break
        visited[u] = True
        total += curr_m
        for v in range(n):
            if not visited[v]:
                d = abs(pts[u][0] - pts[v][0]) + abs(pts[u][1] - pts[v][1])
                if d < min_dist[v]:
                    min_dist[v] = d
    return total


# === Main Function ===
def read_def(file_path):
    def_reader = C_DefReader()
    _def = def_reader.read(file_path)
    nets = _def.c_nets
    pins = _def.c_pins
    components = _def.c_components

    component_id = {}
    pin_id = {}

    for i in range(_def.c_num_components):
        id = components[i].c_id

        component_id[id] = components[i]


    for i in range(_def.c_num_pins):
        name = pins[i].c_name
        pin_id[name] = pins[i]

    component_pos = {}
    pin_wl = {}
    for i in range(_def.c_num_nets):
        net_points = []
        for j in range(nets[i].c_num_pins):
            instance_name = nets[i].c_instances[j]
            pin_name = nets[i].c_pins[j]

            s_inst = (
                str(instance_name, "utf-8")
                if isinstance(instance_name, bytes)
                else str(instance_name)
            )
            s_pin = (
                str(pin_name, "utf-8") if isinstance(pin_name, bytes) else str(pin_name)
            )
            pin_key = f"{s_inst}/{s_pin}"

            comp = component_id.get(instance_name)
            if comp:

                if pin_key not in component_pos:
                    component_pos[pin_key] = (comp.c_x, comp.c_y)
                    net_points.append((comp.c_x, comp.c_y))

            else:
                io_pin = pin_id.get(instance_name)
                if io_pin:
                    if pin_key not in component_pos:
                        component_pos[pin_key] = (io_pin.c_x, io_pin.c_y)
                        net_points.append((io_pin.c_x, io_pin.c_y))
        if not net_points:
            wl = 0
        else:
            wl = calc_rmst_length_fast(net_points)

        for j in range(nets[i].c_num_pins):
            instance_name = nets[i].c_instances[j]
            pin_name = nets[i].c_pins[j]

            s_inst = (
                str(instance_name, "utf-8")
                if isinstance(instance_name, bytes)
                else str(instance_name)
            )
            s_pin = (
                str(pin_name, "utf-8") if isinstance(pin_name, bytes) else str(pin_name)
            )

            pin_key = f"{s_inst}/{s_pin}"
            pin_wl[pin_key] = wl
    return component_pos, pin_wl


if __name__ == "__main__":

    path = "/ISPD26-Contest/aes_cipher_top/TCP_250_UTIL_0.40/contest.def"
    components_pos, pin_wl = read_def(path)
    print(components_pos)
    print(pin_wl)
