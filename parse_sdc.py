import re
from collections import defaultdict
from typing import Dict, Optional


class clock_t:
    def __init__(
        self, name=None, period: float = None, uncertainty: float = 0, ports=[]
    ):
        self.name = name
        self.period = period
        self.uncertainty = uncertainty
        self.ports = ports


class port_data_t:
    def __init__(self, delay: float, type: str, minmax: str):
        self.delay = delay
        self.type = type
        self.minmax = minmax


class sdc_data_t:
    def __init__(self, clocks: Dict[str, clock_t], port_delay: Dict[str, port_data_t]):
        self.clocks = clocks
        self.port_delay = port_delay
        self.port_to_clock = dict()  # port_name -> clock_name


def normalize_port_name(port):
    # 如果是 array_name[bit_index] 的形式，只保留 array_name
    m = re.match(r"(\w+)\[\d+\]", port)
    if m:
        return m.group(1)
    return port


def load_sdc(sdc_path):
    clocks = {}
    port_delay = {}

    with open(sdc_path, "r") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue

            # --------------------------------------------------
            # create_clock
            # --------------------------------------------------
            if line.startswith("create_clock"):
                m_name = re.search(r"-name\s+(\S+)", line)
                m_period = re.search(r"-period\s+([\d\.]+)", line)
                m_port = re.search(r"\[get_ports\s+\{(.+?)\}\]", line)

                if not (m_name and m_period and m_port):
                    continue

                clk_name = m_name.group(1)
                period = float(m_period.group(1))
                port = m_port.group(1)

                clocks[clk_name] = clock_t(period=period, uncertainty=0, ports=[port])
            # --------------------------------------------------
            # set_input_delay / set_output_delay (MAX ONLY)
            # --------------------------------------------------
            elif line.startswith("set_input_delay") or line.startswith(
                "set_output_delay"
            ):

                # skip min constraint
                if "-min" in line:
                    continue

                # delay value
                m_delay = re.search(r"-add_delay\s+([\d\.]+)", line)
                if not m_delay:
                    continue
                delay = float(m_delay.group(1))

                # port
                m_port = re.search(r"\[get_ports\s+\{(.+?)\}\]", line)
                if not m_port:
                    continue
                port = normalize_port_name(m_port.group(1))
                if "-clock_fall" not in line:
                    if line.startswith("set_input_delay"):
                        port_delay[port] = port_data_t(
                            delay=delay, type="internal", minmax="max"
                        )
                    else:
                        port_delay[port] = port_data_t(
                            delay=delay, type="external", minmax="max"
                        )
            elif line.startswith("set_clock_uncertainty"):
                # uncertainty value
                m_val = re.search(r"set_clock_uncertainty\s+([\d\.]+)", line)
                if not m_val:
                    continue
                uncertainty_val = float(m_val.group(1))

                # setup or hold
                is_hold = "-hold" in line
                utype = "hold" if is_hold else "setup"

                # clock name
                m_clk = re.search(r"\[get_clocks\s+\{(.+?)\}\]", line)
                if not m_clk:
                    continue
                clk = m_clk.group(1)

                # There might be some clock uncertainty constraints that refer to clocks not defined in create_clock
                # (e.g., generated clocks). We will still store the uncertainty for these clocks, and if they are later defined in create_clock,
                # we can update their information.
                # If they are never defined,we can still keep the uncertainty info in case it's useful for analysis.
                if clk not in clocks:
                    clocks[clk] = {"ports": [], "period": None, "uncertainty": 0}
                    clocks[clk] = clock_t(period=None, uncertainty=0, ports=[])
                clocks[clk].uncertainty = uncertainty_val

    sdc_data = sdc_data_t(clocks, port_delay)
    for clk_name, clk_info in sdc_data.clocks.items():
        for port in clk_info.ports:
            sdc_data.port_to_clock[port] = clk_name
    return sdc_data


if __name__ == "__main__":
    sdc_file = "/ISPD26-Contest/Benchmarks/bsg_chip/TCP_1200_UTIL_0.30/contest.sdc"
    sdc_data = load_sdc(sdc_file)
    clocks = sdc_data.clocks
    print("Clocks:")
    for clk_name, clk_info in clocks.items():
        print(
            f"  Clock: {clk_name}, Period: {clk_info.period} ns, Uncertainty: {clk_info.uncertainty} ns, Ports: {clk_info.ports}"
        )
    print("Port Delays:")
    for port, info in sdc_data.port_delay.items():
        print(
            f"  Port: {port}, Delay: {info.delay} ns, Type: {info.type}, MinMax: {info.minmax}"
        )
