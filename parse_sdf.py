"""SDF parser — extracts INTERCONNECT and CELL (IOPATH) delays.

Returns:
    dict[src_pin][dst_pin] = (rise_max_delay, fall_max_delay)
"""
import re
import os

_RE_INSTANCE    = re.compile(r'\(INSTANCE\s*([^)]*)\)')
_RE_INTERCONNECT = re.compile(
    r'\(INTERCONNECT\s+(\S+)\s+(\S+)\s+'
    r'\([^:]+::([\d.\-]+)\)'
    r'(?:\s+\([^:]+::([\d.\-]+)\))?'
)
_RE_IOPATH = re.compile(
    r'\(IOPATH\s+(\S+)\s+(\S+)\s+'
    r'\([^:]+::([\d.\-]+)\)'
    r'(?:\s+\([^:]+::([\d.\-]+)\))?'
)


def load_sdf(file_path):
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"SDF file not found: '{file_path}'")

    data = {}
    current_inst = ""

    def _store(src, dst, r_str, f_str):
        r = float(r_str)
        f = float(f_str) if f_str else r
        data.setdefault(src, {})[dst] = (r, f)

    with open(file_path, encoding="utf-8") as f:
        for line in f:
            if "INSTANCE" in line:
                m = _RE_INSTANCE.search(line)
                if m:
                    current_inst = m.group(1).strip().replace("\\", "")
                continue

            if "IOPATH" in line:
                m = _RE_IOPATH.search(line)
                if m:
                    prefix = f"{current_inst}/" if current_inst and current_inst != "*" else ""
                    _store(prefix + m.group(1), prefix + m.group(2), m.group(3), m.group(4))
                continue

            if "INTERCONNECT" in line:
                m = _RE_INTERCONNECT.search(line)
                if m:
                    _store(
                        m.group(1).replace("\\", ""),
                        m.group(2).replace("\\", ""),
                        m.group(3), m.group(4),
                    )

    return data
