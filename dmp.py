import math
from scipy.optimize import brentq


class DmpSlewCalculator:
    def __init__(self, r_pi, c1, c2, table_slew, rd=None):
        """
        參數單位建議:
        Resistance: kOhm
        Capacitance: pF
        Time: ns
        """
        self.r_pi = r_pi
        self.c1 = c1
        self.c2 = c2
        self.c_total = c1 + c2
        self.table_slew = table_slew

        # 閾值設定 (對應 OpenSTA 的 vl_, vh_)
        self.vl = 0.2  # 20%
        self.vh = 0.8  # 80%
        self.vth = 0.5  # 50%

        # 如果沒有提供 Rd，我們嘗試從 Table Slew 反推
        # 假設 Table Slew 是推動 C_total 造成的
        if rd is None:
            # 簡單 RC 充電公式反推 R: Slew = R * C * ln(0.8/0.2)
            # ln(0.8/0.2) approx 1.386
            self.rd = self.table_slew / (self.c_total)
            # print(f"[Info] Rd not provided. Estimated Rd = {self.rd:.4f} kOhm")
        else:
            self.rd = rd

        # 初始化係數 (對應 C++ DmpPi::init)
        self._init_coefficients()

    def _init_coefficients(self):
        """
        移植自 DmpPi::init
        計算 Pi 模型的極點 (Poles) 和留數 (Residues)
        """
        # 防止除以零
        if self.c1 <= 1e-15:
            self.c1 = 1e-15
        if self.c2 <= 1e-15:
            self.c2 = 1e-15
        if self.r_pi <= 1e-6:
            self.r_pi = 1e-6

        # 計算二次方程式的係數來找極點
        # s^2 * (Rpi*Rd*C1*C2) + s * (Rd(C1+C2) + Rpi*C1) + 1 = 0
        a = self.r_pi * self.rd * self.c1 * self.c2 + 1e-9
        b = self.rd * (self.c1 + self.c2) + self.r_pi * self.c1

        delta = b * b - 4 * a
        if delta < 0:
            delta = 0  # 避免複數，雖然物理上RC電路應為實根
        sqrt_val = math.sqrt(delta)

        # OpenSTA 使用的是倒數極點 (1/tau)
        self.p1 = (b + sqrt_val) / (2 * a)
        self.p2 = (b - sqrt_val) / (2 * a)

        self.z1 = 1.0 / (self.r_pi * self.c1)

        # 計算 V0 (Ramp Response) 的係數 k0 ~ k4
        p1p2 = self.p1 * self.p2
        self.k0 = 1.0 / (
            self.rd * self.c2
        )  # 這裡 OpenSTA 原始碼可能有不同定義，依照 DMP 論文通常是這樣
        # 修正：參考 C++ k0_ = 1.0 / (rd_ * c2_);

        self.k2 = self.z1 / p1p2
        self.k1 = (1.0 - self.k2 * (self.p1 + self.p2)) / p1p2

        if abs(self.p2 - self.p1) < 1e-9:
            # 避免極點重合導致除以零 (簡單處理)
            self.p2 += 1e-9

        self.k4 = (self.k1 * self.p1 + self.k2) / (self.p2 - self.p1)
        self.k3 = -self.k1 - self.k4

    def _V0_ramp_response(self, t):
        """
        移植自 DmpPi::V0
        這是對 "單位斜坡 (Unit Ramp)" 的響應
        """
        if t <= 0:
            return 0.0

        exp_p1 = math.exp(-self.p1 * t)
        exp_p2 = math.exp(-self.p2 * t)

        # vo = k0 * (k1 + k2*t + k3*exp(-p1*t) + k4*exp(-p2*t))
        vo = self.k0 * (self.k1 + self.k2 * t + self.k3 * exp_p1 + self.k4 * exp_p2)
        return vo

    def _Vo_saturated_ramp(self, t, dt):
        """
        移植自 DmpAlg::Vo
        這是對 "飽和斜坡 (Saturated Ramp)" 的響應
        Driver 輸出並不是無限上升，而是在 dt 時間後停在 VDD
        Vo(t) = (V0(t) - V0(t-dt)) / dt
        """
        term1 = self._V0_ramp_response(t)
        term2 = self._V0_ramp_response(t - dt)
        return (term1 - term2) / dt

    def calculate_real_slew(self):
        """
        計算真實的 Driver Waveform Slew
        """
        # dt 是 Driver 內部的切換時間 (Input Slew 傳遞過來的效應)
        # 在 DMP 中，這通常會透過迭代找出。
        # 這裡我們做一個合理的假設：Driver 內部的 dt 近似於 Table Slew (如果是純電容負載的話)
        # 或者更精確地說，它是 Table Slew / Derate (假設 Table Slew 是 0-100% full swing 時間)
        dt = self.table_slew

        # 定義求解函數： V_out(t) - Target_Voltage = 0
        def target_func(t, v_target):
            return self._Vo_saturated_ramp(t, dt) - v_target

        # 估計搜尋範圍 (Upper bound)
        t_max = dt + self.c_total * (self.rd + self.r_pi) * 10.0

        try:
            # 1. 找 20% 點 (vl)
            t_low = brentq(target_func, 0, t_max, args=(self.vl,))

            # 2. 找 80% 點 (vh)
            t_high = brentq(target_func, t_low, t_max, args=(self.vh,))

            # 3. 計算 Slew
            real_slew = t_high - t_low

            return real_slew, t_low, t_high

        except ValueError:
            print(
                "Error: Solver failed to find crossing points. Parameters might be physically unrealistic."
            )
            return None, None, None


if __name__ == "__main__":
    # ==========================================
    # 使用範例 (填入你的 Report 數值)
    # ==========================================

    # 範例數據 (來自你之前的 report_dcalc)
    # Pi model C2=40.66 Rpi=0.75 C1=123.81
    # Table Slew = 516.11 ps = 0.516 ns

    my_c1 = 0.075  # pF (注意單位換算: 123.81 fF = 0.12381 pF)
    my_c2 = 0.075  # pF (40.66 fF)
    my_rpi = 0.75  # kOhm (假設 lib 單位是 kOhm)
    my_table_slew = 0.51611  # ns

    # 建立計算器
    # 注意：我們沒有 Rd，所以程式會自動估算

    calculator = DmpSlewCalculator(
        r_pi=my_rpi, c1=my_c1, c2=my_c2, table_slew=my_table_slew
    )

    # 計算
    real_slew, t20, t80 = calculator.calculate_real_slew()

    if real_slew:
        print("-" * 30)
        print(f"Table Slew (Input): {my_table_slew*1000:.2f} ps")
        print(f"Calculated Real Slew: {real_slew*1000:.2f} ps")
        print(f"Slew Degradation: +{(real_slew - my_table_slew)*1000:.2f} ps")
        print("-" * 30)
