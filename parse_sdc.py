"""SDC parser — supports create_clock, set_input/output_delay, set_clock_uncertainty."""
import re
from typing import Dict


class clock_t:
    def __init__(self, name: str = "", period: float = None,
                 uncertainty: float = 0.0, ports: list = None):
        self.name = name
        self.period = period
        self.uncertainty = uncertainty
        self.ports = ports or []


class port_data_t:
    def __init__(self, delay: float, type: str, minmax: str):
        self.delay = delay
        self.type = type
        self.minmax = minmax


class sdc_data_t:
    def __init__(self, clocks: Dict[str, clock_t],
                 port_delay: Dict[str, port_data_t]):
        self.clocks = clocks
        self.port_delay = port_delay
        self.port_to_clock: Dict[str, str] = {
            port: name
            for name, clk in clocks.items()
            for port in clk.ports
        }


def _port(line: str) -> str:
    """Extract port name from [get_ports {name}], stripping bus indices."""
    m = re.search(r'\[get_ports\s+\{(.+?)\}\]', line)
    if not m:
        return ""
    name = m.group(1)
    bus = re.match(r'(\w+)\[\d+\]', name)
    return bus.group(1) if bus else name


def load_sdc(sdc_path: str) -> sdc_data_t:
    clocks: Dict[str, clock_t] = {}
    port_delay: Dict[str, port_data_t] = {}

    with open(sdc_path) as f:
        for raw in f:
            line = raw.strip()
            if not line or line.startswith("#"):
                continue

            if line.startswith("create_clock"):
                m_name   = re.search(r'-name\s+(\S+)', line)
                m_period = re.search(r'-period\s+([\d.]+)', line)
                port     = _port(line)
                if m_name and m_period and port:
                    clocks[m_name.group(1)] = clock_t(
                        name=m_name.group(1),
                        period=float(m_period.group(1)),
                        ports=[port],
                    )

            elif line.startswith(("set_input_delay", "set_output_delay")):
                if "-min" in line or "-clock_fall" in line:
                    continue
                m_delay = re.search(r'-add_delay\s+([\d.]+)', line)
                port    = _port(line)
                if m_delay and port:
                    is_input = line.startswith("set_input_delay")
                    port_delay[port] = port_data_t(
                        delay=float(m_delay.group(1)),
                        type="internal" if is_input else "external",
                        minmax="max",
                    )

            elif line.startswith("set_clock_uncertainty"):
                if "-hold" in line:
                    continue
                m_val = re.search(r'set_clock_uncertainty\s+([\d.]+)', line)
                m_clk = re.search(r'\[get_clocks\s+\{(.+?)\}\]', line)
                if m_val and m_clk:
                    clk = m_clk.group(1)
                    if clk not in clocks:
                        clocks[clk] = clock_t(name=clk)
                    clocks[clk].uncertainty = float(m_val.group(1))

    return sdc_data_t(clocks, port_delay)
