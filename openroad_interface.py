"""Persistent OpenROAD process wrapper.

Keeps a single OpenROAD subprocess alive across multiple commands,
avoiding the overhead of restarting the tool for every query.
"""
import os
import select
import subprocess
import time
import uuid
from typing import List, Optional, Tuple


class OpenRoadInterface:
    def __init__(self, benchmark_path: str, platform_path: str, design_name: str):
        self.benchmark_path = benchmark_path
        self.platform_path  = platform_path
        self.design_name    = design_name
        self.process: Optional[subprocess.Popen] = None
        self._initialized   = False

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    def start(self, load_design: bool = False):
        if self.process is not None:
            return
        self.process = subprocess.Popen(
            ["openroad"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True, bufsize=1,
        )
        print(f"[INFO] OpenROAD started (PID {self.process.pid})")
        time.sleep(0.5)
        if load_design:
            self._load_design()

    def close(self):
        if not self.process:
            return
        try:
            self.process.stdin.write("exit\n")
            self.process.stdin.flush()
            self.process.wait(timeout=5)
        except Exception:
            self.process.kill()
            self.process.wait()
        finally:
            self.process      = None
            self._initialized = False

    def is_alive(self) -> bool:
        return self.process is not None and self.process.poll() is None

    def __enter__(self):
        self.start()
        return self

    def __exit__(self, *_):
        self.close()

    # ── Commands ──────────────────────────────────────────────────────────────

    def send(self, command: str, timeout: float = 30.0) -> str:
        if not self.process:
            raise RuntimeError("OpenROAD not started. Call start() first.")

        marker = f"__DONE_{uuid.uuid4().hex}__"
        self.process.stdin.write(command + "\n")
        self.process.stdin.write(f'puts "{marker}"\n')
        self.process.stdin.flush()

        lines      = []
        deadline   = time.time() + timeout
        while True:
            if time.time() > deadline:
                raise TimeoutError(f"Command timed out after {timeout}s: {command!r}")
            if hasattr(select, "select"):
                ready, _, _ = select.select([self.process.stdout], [], [], 0.1)
                if not ready:
                    continue
            line = self.process.stdout.readline()
            if not line:
                if self.process.poll() is not None:
                    raise RuntimeError("OpenROAD process terminated unexpectedly")
                continue
            if marker in line:
                break
            lines.append(line)
        return "".join(lines)

    def send_many(self, commands: List[str]) -> List[str]:
        return [self.send(cmd) for cmd in commands]

    def run_tcl(self, script_path: str) -> Tuple[str, str]:
        if not os.path.exists(script_path):
            return "", f"File not found: {script_path}"
        return self.send(f"source {script_path}"), ""

    # ── Design helpers ────────────────────────────────────────────────────────

    def _load_design(self):
        if self._initialized:
            return
        p = self.platform_path
        self.send(f"read_liberty {p}/lib/asap7sc7p5t_AO_RVT_FF_nldm_211120.lib.gz")
        self.send(f"read_lef {p}/lef/asap7_tech_1x_201209.lef")
        self.send(f"read_lef {p}/lef/asap7sc7p5t_28_R_1x_220121a.lef")
        def_file = f"{self.benchmark_path}/{self.design_name}.def"
        if os.path.exists(def_file):
            self.send(f"read_def {def_file}")
        sdc_file = f"{self.benchmark_path}/{self.design_name}.sdc"
        if os.path.exists(sdc_file):
            self.send(f"read_sdc {sdc_file}")
        self._initialized = True

    def worst_slack(self) -> float:
        out = self.send("report_worst_slack")
        for line in out.splitlines():
            if "slack" in line.lower():
                parts = line.split()
                for i, p in enumerate(parts):
                    if "slack" in p.lower() and i + 1 < len(parts):
                        try:
                            return float(parts[i + 1])
                        except ValueError:
                            pass
        return 0.0

    def tns(self) -> float:
        out = self.send("report_tns")
        for line in out.splitlines():
            if "tns" in line.lower():
                parts = line.split()
                for i, p in enumerate(parts):
                    if "tns" in p.lower() and i + 1 < len(parts):
                        try:
                            return float(parts[i + 1])
                        except ValueError:
                            pass
        return 0.0
