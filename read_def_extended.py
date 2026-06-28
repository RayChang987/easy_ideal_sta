"""Extended DEF parser: die area, component types/positions, and net connections."""
import re
from read_def import calc_rmst_length_fast


def read_def_full(file_path):
    """Parse a DEF file and return full layout + connectivity data.

    Returns
    -------
    die_area    : list[(x, y)]   polygon from DIEAREA
    components  : dict[inst_name -> {'type', 'x', 'y', 'orient'}]
    nets        : dict[net_name  -> [(inst, pin), ...]]
    port_pos    : dict[port_name -> (x, y)]
    component_pos : dict['inst/pin' -> (x, y)]  (driver position per pin)
    pin_wl      : dict['inst/pin' -> RMST wirelength in DEF units]
    """
    die_area = []
    components = {}   # inst_name -> {type, x, y, orient}
    nets = {}         # net_name  -> [(inst, pin)]
    inst_pos = {}     # inst_name -> (x, y)
    port_pos = {}     # port_name -> (x, y)
    component_pos = {}
    pin_wl = {}

    _PLACED_RE = re.compile(r'(?:PLACED|FIXED)\s+\(\s*(-?\d+)\s+(-?\d+)\s*\)\s+(\S+)')
    _PAIR_RE   = re.compile(r'\(\s*(\S+)\s+(\S+)\s*\)')
    _XY_RE     = re.compile(r'\(\s*(-?\d+)\s+(-?\d+)\s*\)')

    section = None
    current_port = None
    net_buf = None
    current_net = None

    with open(file_path) as f:
        for raw in f:
            line = raw.strip()

            # --- DIEAREA -------------------------------------------------------
            if re.match(r'^DIEAREA\b', line):
                die_area = [(int(m.group(1)), int(m.group(2)))
                            for m in _XY_RE.finditer(line)]
                continue

            # --- Section headers -----------------------------------------------
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
                current_net = None
                continue
            if re.match(r'^END\s+', line):
                if net_buf is not None:
                    _process_net(current_net, net_buf, inst_pos, port_pos,
                                 component_pos, pin_wl, nets, _PAIR_RE)
                    net_buf = None
                section = None
                current_port = None
                continue

            # --- COMPONENTS ----------------------------------------------------
            if section == 'COMPONENTS' and line.startswith('- '):
                m_name = re.match(r'-\s+(\S+)\s+(\S+)', line)
                m_pos  = _PLACED_RE.search(line)
                if m_name and m_pos:
                    iname, itype = m_name.group(1), m_name.group(2)
                    x, y, orient = int(m_pos.group(1)), int(m_pos.group(2)), m_pos.group(3)
                    components[iname] = {'type': itype, 'x': x, 'y': y, 'orient': orient}
                    inst_pos[iname] = (x, y)

            # --- PINS ----------------------------------------------------------
            elif section == 'PINS':
                if line.startswith('- '):
                    m = re.match(r'-\s+(\S+)', line)
                    current_port = m.group(1) if m else None
                if current_port:
                    m_pos = _PLACED_RE.search(line)
                    if m_pos:
                        port_pos[current_port] = (int(m_pos.group(1)), int(m_pos.group(2)))
                        current_port = None

            # --- NETS ----------------------------------------------------------
            elif section == 'NETS':
                if line.startswith('- '):
                    if net_buf is not None:
                        _process_net(current_net, net_buf, inst_pos, port_pos,
                                     component_pos, pin_wl, nets, _PAIR_RE)
                    m = re.match(r'-\s+(\S+)', line)
                    current_net = m.group(1) if m else None
                    net_buf = line
                elif net_buf is not None:
                    net_buf += ' ' + line

                if net_buf is not None and net_buf.rstrip().endswith(';'):
                    _process_net(current_net, net_buf, inst_pos, port_pos,
                                 component_pos, pin_wl, nets, _PAIR_RE)
                    net_buf = None
                    current_net = None

    return die_area, components, nets, port_pos, component_pos, pin_wl


def _process_net(net_name, net_str, inst_pos, port_pos,
                 component_pos, pin_wl, nets, pair_re):
    pairs = pair_re.findall(net_str)
    net_points = []
    conn_list = []

    for inst, pin in pairs:
        pin_key = f"{inst}/{pin}"
        pos = port_pos.get(pin) if inst == 'PIN' else inst_pos.get(inst)
        if pos is None:
            continue
        component_pos.setdefault(pin_key, pos)
        net_points.append(pos)
        conn_list.append((inst, pin))

    wl = calc_rmst_length_fast(net_points) if net_points else 0
    for inst, pin in pairs:
        pin_key = f"{inst}/{pin}"
        if pin_key in component_pos:
            pin_wl[pin_key] = wl

    if net_name and conn_list:
        nets[net_name] = conn_list


if __name__ == "__main__":
    import sys
    path = sys.argv[1] if len(sys.argv) > 1 else "contest.def"
    die, comps, nets_, ports, cpos, wl = read_def_full(path)
    print(f"Die area    : {die}")
    print(f"Components  : {len(comps)}")
    print(f"Nets        : {len(nets_)}")
    print(f"Ports       : {len(ports)}")
    print(f"pin_wl keys : {len(wl)}")
