import heapq
import re


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
    """Parse a DEF file without external dependencies.

    Returns:
        component_pos: dict  "inst/pin" → (x, y)  (uses cell origin as pin position)
        pin_wl:        dict  "inst/pin" → RMST wire length in DEF units
    """
    inst_pos = {}   # inst_name  → (x, y)  from COMPONENTS
    port_pos = {}   # port_name  → (x, y)  from PINS

    # ------------------------------------------------------------------ #
    # Pass 1 — single scan: collect positions and process nets on the fly  #
    # ------------------------------------------------------------------ #
    _PLACED_RE = re.compile(r'(?:PLACED|FIXED)\s+\(\s*(-?\d+)\s+(-?\d+)\s*\)')
    _PAIR_RE   = re.compile(r'\(\s*(\S+)\s+(\S+)\s*\)')

    component_pos = {}
    pin_wl = {}

    section = None
    current_port = None
    net_buf = None   # accumulates tokens for the current net statement

    with open(file_path) as f:
        for raw in f:
            line = raw.strip()

            # ── Section markers ──────────────────────────────────────── #
            if re.match(r'^COMPONENTS\s+\d+', line):
                section = 'COMPONENTS'
                continue
            if re.match(r'^PINS\s+\d+', line):
                section = 'PINS'
                current_port = None
                continue
            if re.match(r'^NETS\s+\d+', line):
                section = 'NETS'
                net_buf = None
                continue
            if re.match(r'^END\s+', line):
                # flush any open net buffer
                if net_buf is not None:
                    _process_net(net_buf, inst_pos, port_pos,
                                 component_pos, pin_wl, _PAIR_RE)
                    net_buf = None
                section = None
                current_port = None
                continue

            # ── COMPONENTS ───────────────────────────────────────────── #
            if section == 'COMPONENTS' and line.startswith('- '):
                m_name = re.match(r'-\s+(\S+)', line)
                m_pos  = _PLACED_RE.search(line)
                if m_name and m_pos:
                    inst_pos[m_name.group(1)] = (int(m_pos.group(1)),
                                                  int(m_pos.group(2)))

            # ── PINS ─────────────────────────────────────────────────── #
            elif section == 'PINS':
                if line.startswith('- '):
                    m = re.match(r'-\s+(\S+)', line)
                    current_port = m.group(1) if m else None
                if current_port:
                    m_pos = _PLACED_RE.search(line)
                    if m_pos:
                        port_pos[current_port] = (int(m_pos.group(1)),
                                                   int(m_pos.group(2)))
                        current_port = None

            # ── NETS ─────────────────────────────────────────────────── #
            elif section == 'NETS':
                if line.startswith('- '):
                    # flush previous net
                    if net_buf is not None:
                        _process_net(net_buf, inst_pos, port_pos,
                                     component_pos, pin_wl, _PAIR_RE)
                    net_buf = line
                elif net_buf is not None:
                    net_buf += ' ' + line

                # A net statement ending on this line
                if net_buf is not None and net_buf.rstrip().endswith(';'):
                    _process_net(net_buf, inst_pos, port_pos,
                                 component_pos, pin_wl, _PAIR_RE)
                    net_buf = None

    return component_pos, pin_wl


def _process_net(net_str, inst_pos, port_pos, component_pos, pin_wl, pair_re):
    """Compute RMST for one net statement and update component_pos / pin_wl."""
    pairs = pair_re.findall(net_str)
    net_points = []

    for inst, pin in pairs:
        pin_key = f"{inst}/{pin}"
        if inst == 'PIN':
            pos = port_pos.get(pin)
        else:
            pos = inst_pos.get(inst)
        if pos is None:
            continue
        component_pos.setdefault(pin_key, pos)
        net_points.append(pos)

    wl = calc_rmst_length_fast(net_points) if net_points else 0
    for inst, pin in pairs:
        pin_key = f"{inst}/{pin}"
        if pin_key in component_pos:
            pin_wl[pin_key] = wl


if __name__ == "__main__":
    import sys
    path = sys.argv[1] if len(sys.argv) > 1 else "contest.def"
    component_pos, pin_wl = read_def(path)
    print(f"component_pos entries: {len(component_pos)}")
    print(f"pin_wl entries:        {len(pin_wl)}")
