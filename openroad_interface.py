"""
OpenRoad Interface Example
演示如何在 Python 程序执行过程中与 OpenRoad 交互获取数据
"""

import subprocess
import os
import uuid
import select
import time
from typing import Optional, List, Tuple


class OpenRoadInterface:
    """与 OpenRoad 进程交互的接口类 - 持久化进程版本"""

    def __init__(self, benchmark_path: str, platform_path: str, design_name: str):
        """
        初始化 OpenRoad 接口

        Args:
            benchmark_path: 基准测试路径
            platform_path: 平台路径
            design_name: 设计名称
        """
        self.benchmark_path = benchmark_path
        self.platform_path = platform_path
        self.design_name = design_name
        self.process: Optional[subprocess.Popen] = None
        self._initialized = False

    def start_openroad(self, load_design: bool = False):
        """
        启动 OpenRoad 进程（只启动一次，保持运行）

        Args:
            load_design: 是否自动加载设计文件
        """
        if self.process is not None:
            print("[INFO] OpenRoad process already running")
            return

        print("[INFO] Starting persistent OpenRoad process...")

        try:
            self.process = subprocess.Popen(
                ["openroad"],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,  # 合并 stderr 到 stdout
                text=True,
                bufsize=1,
                universal_newlines=True,
            )
            print(
                "[INFO] OpenRoad process started successfully (PID: {})".format(
                    self.process.pid
                )
            )

            # 等待 OpenRoad 启动
            time.sleep(0.5)

            # 如果需要，自动加载设计
            if load_design:
                self._load_design()

        except Exception as e:
            print(f"[ERROR] Failed to start OpenRoad: {e}")
            self.process = None

    def _load_design(self):
        """内部方法：加载设计文件"""
        if self._initialized:
            return

        print("[INFO] Loading design files...")

        # 加载库文件
        self.send_command(
            f"read_liberty {self.platform_path}/lib/asap7sc7p5t_AO_RVT_FF_nldm_211120.lib.gz"
        )

        # 加载 LEF
        self.send_command(f"read_lef {self.platform_path}/lef/asap7_tech_1x_201209.lef")
        self.send_command(
            f"read_lef {self.platform_path}/lef/asap7sc7p5t_28_R_1x_220121a.lef"
        )

        # 加载 DEF（如果存在）
        def_file = f"{self.output_path}/{self.design_name}.def"
        if os.path.exists(def_file):
            self.send_command(f"read_def {def_file}")

        # 加载 SDC（如果存在）
        sdc_file = f"{self.benchmark_path}/{self.design_name}.sdc"
        if os.path.exists(sdc_file):
            self.send_command(f"read_sdc {sdc_file}")

        self._initialized = True
        print("[INFO] Design loaded successfully")

    def send_command(self, command: str, timeout: float = 30.0) -> str:
        """
        向 OpenRoad 发送命令并获取输出（同步方式）

        Args:
            command: TCL 命令
            timeout: 超时时间（秒）

        Returns:
            命令输出结果
        """
        if not self.process:
            raise RuntimeError(
                "OpenRoad process not started. Call start_openroad() first."
            )

        try:
            # 生成唯一的结束标记
            marker = f"__CMD_DONE_{uuid.uuid4().hex}__"

            # 发送命令和标记
            self.process.stdin.write(command + "\n")
            self.process.stdin.write(f'puts "{marker}"\n')
            self.process.stdin.flush()

            # 读取输出直到看到标记
            output_lines = []
            start_time = time.time()

            while True:
                if time.time() - start_time > timeout:
                    raise TimeoutError(f"Command timed out after {timeout}s")

                # 使用 select 检查是否有数据可读（仅限 Unix）
                if hasattr(select, "select"):
                    ready, _, _ = select.select([self.process.stdout], [], [], 0.1)
                    if not ready:
                        continue

                line = self.process.stdout.readline()

                if not line:
                    # 进程可能已终止
                    if self.process.poll() is not None:
                        raise RuntimeError("OpenRoad process terminated unexpectedly")
                    continue

                # 检查是否到达结束标记
                if marker in line:
                    break

                output_lines.append(line)

            return "".join(output_lines)

        except Exception as e:
            print(f"[ERROR] Failed to send command: {e}")
            return ""

    def send_commands(self, commands: List[str]) -> List[str]:
        """
        批量发送多个命令

        Args:
            commands: TCL 命令列表

        Returns:
            每个命令的输出列表
        """
        results = []
        for cmd in commands:
            output = self.send_command(cmd)
            results.append(output)
        return results

    def run_tcl_script(self, tcl_script_path: str) -> Tuple[str, str]:
        """
        使用当前进程运行 TCL 脚本（通过 source 命令）

        Args:
            tcl_script_path: TCL 脚本路径

        Returns:
            (stdout, stderr) 输出元组 - stderr 始终为空字符串
        """
        print(f"[INFO] Running TCL script in persistent process: {tcl_script_path}")

        if not os.path.exists(tcl_script_path):
            return "", f"File not found: {tcl_script_path}"

        try:
            # 使用 source 命令在当前进程中执行脚本
            output = self.send_command(f"source {tcl_script_path}")
            return output, ""

        except Exception as e:
            print(f"[ERROR] Failed to run TCL script: {e}")
            return "", str(e)

    def get_timing_report(self, output_file: str = "timing_report.txt") -> str:
        """
        获取时序报告（使用持久进程）

        Args:
            output_file: 输出文件名

        Returns:
            时序报告内容
        """
        if not self._initialized:
            self._load_design()

        print("[INFO] Generating timing report...")

        # 直接使用当前进程执行命令
        self.send_command(
            f"report_checks -path_delay max -fields {{input_pin slew capacitance}} -format full_clock_expanded > {output_file}"
        )
        wns_output = self.send_command("report_worst_slack")
        tns_output = self.send_command("report_tns")

        # 读取输出文件
        result = wns_output + "\n" + tns_output
        if os.path.exists(output_file):
            with open(output_file, "r") as f:
                result += "\n" + f.read()

        return result

    def get_wire_rc(self, net_name: str) -> dict:
        """
        获取特定线网的 RC 信息（使用持久进程）

        Args:
            net_name: 线网名称

        Returns:
            包含 R 和 C 值的字典
        """
        if not self._initialized:
            self._load_design()

        print(f"[INFO] Getting RC info for net: {net_name}")

        # 直接查询线网信息
        output = self.send_command(f"""
set net [get_nets {net_name}]
if {{$net != ""}} {{
    puts "Net found: {net_name}"
}} else {{
    puts "Net not found: {net_name}"
}}
""")

        return {"output": output, "net_name": net_name}

    def get_worst_slack(self) -> float:
        """获取最差松弛值"""
        if not self._initialized:
            self._load_design()

        output = self.send_command("report_worst_slack")
        # 解析输出获取数值
        # 格式通常是 "worst slack XXX"
        try:
            for line in output.split("\n"):
                if "slack" in line.lower():
                    parts = line.split()
                    for i, part in enumerate(parts):
                        if "slack" in part.lower() and i + 1 < len(parts):
                            return float(parts[i + 1])
        except:
            pass
        return 0.0

    def get_tns(self) -> float:
        """获取总负松弛"""
        if not self._initialized:
            self._load_design()

        output = self.send_command("report_tns")
        # 解析输出获取数值
        try:
            for line in output.split("\n"):
                if "tns" in line.lower():
                    parts = line.split()
                    for i, part in enumerate(parts):
                        if "tns" in part.lower() and i + 1 < len(parts):
                            return float(parts[i + 1])
        except:
            pass
        return 0.0

    def close(self):
        """关闭 OpenRoad 进程"""
        if self.process:
            try:
                print("[INFO] Closing OpenRoad process...")
                self.process.stdin.write("exit\n")
                self.process.stdin.flush()
                self.process.wait(timeout=5)
                print("[INFO] OpenRoad process closed gracefully")
            except:
                print("[WARN] Force killing OpenRoad process...")
                self.process.kill()
                self.process.wait()
            finally:
                self.process = None
                self._initialized = False

    def is_alive(self) -> bool:
        """检查进程是否还在运行"""
        return self.process is not None and self.process.poll() is None

    def __enter__(self):
        """支持 with 语句"""
        self.start_openroad()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """支持 with 语句"""
        self.close()


# 示例使用
def example_usage():
    """示例：如何在程序中使用持久化 OpenRoad 接口"""

    # 配置参数
    benchmark_path = "/ISPD26-Contest/Benchmarks/aes_cipher_top/TCP_250_UTIL_0.40"
    platform_path = "/ISPD26-Contest/Platform/ASAP7"
    output_path = "/ISPD26-Contest-TCLAB/output"
    design_name = "aes_cipher_top"

    # 使用 with 语句自动管理资源
    print("=== 示例：持久化 OpenRoad 进程 ===\n")

    with OpenRoadInterface(
        benchmark_path, platform_path, output_path, design_name
    ) as or_if:

        print("\n--- OpenRoad 进程已启动并加载设计 ---\n")

        # 示例1: 多次查询而不重启进程
        print("=== 查询 1: 获取 WNS ===")
        wns = or_if.get_worst_slack()
        print(f"WNS: {wns}\n")

        print("=== 查询 2: 获取 TNS ===")
        tns = or_if.get_tns()
        print(f"TNS: {tns}\n")

        print("=== 查询 3: 发送自定义命令 ===")
        output = or_if.send_command("report_checks -path_delay max")
        print(f"Output (first 300 chars):\n{output[:300]}\n")

        print("=== 查询 4: 批量发送命令 ===")
        commands = ['puts "Command 1"', 'puts "Command 2"', 'puts "Command 3"']
        results = or_if.send_commands(commands)
        for i, result in enumerate(results):
            print(f"Result {i+1}: {result.strip()}")

        print("\n--- 所有查询完成，进程即将关闭 ---")

    print("\n=== 进程已关闭 ===")


if __name__ == "__main__":
    example_usage()
