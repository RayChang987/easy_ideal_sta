# timing_table.py
import numpy as np
from scipy.interpolate import RegularGridInterpolator


def clamp(x, lo, hi):
    return max(lo, min(x, hi))


def find_axis_index(axis, x):
    """
    模擬 OpenSTA Axis::findAxisIndex
    回傳 i，使得 axis[i] <= x <= axis[i+1]
    並且 i 永遠在 [0, len(axis)-2]
    """
    if x <= axis[0]:
        return 0
    if x >= axis[-1]:
        return len(axis) - 2
    return np.searchsorted(axis, x) - 1


def get_value_from_table(
    values, input_slew_index, output_load_index, input_slew, output_load
):

    axis1 = np.array(input_slew_index[0])  # index_1
    axis2 = np.array(output_load_index[0])  # index_2
    table = np.array(values)

    size1 = len(axis1)
    size2 = len(axis2)

    # === size1 == 1 ===
    if size1 == 1:
        if size2 == 1:
            return float(table[0, 0])
        j = find_axis_index(axis2, output_load)
        x2l, x2u = axis2[j], axis2[j + 1]
        dx2 = (output_load - x2l) / (x2u - x2l)
        y00 = table[0, j]
        y01 = table[0, j + 1]
        return float((1 - dx2) * y00 + dx2 * y01)

    # === size2 == 1 ===
    if size2 == 1:
        i = find_axis_index(axis1, input_slew)
        x1l, x1u = axis1[i], axis1[i + 1]
        dx1 = (input_slew - x1l) / (x1u - x1l)
        y00 = table[i, 0]
        y10 = table[i + 1, 0]
        return float((1 - dx1) * y00 + dx1 * y10)

    # === bilinear ===
    i = find_axis_index(axis1, input_slew)
    j = find_axis_index(axis2, output_load)

    x1l, x1u = axis1[i], axis1[i + 1]
    x2l, x2u = axis2[j], axis2[j + 1]

    dx1 = (input_slew - x1l) / (x1u - x1l)
    dx2 = (output_load - x2l) / (x2u - x2l)

    y00 = table[i, j]
    y10 = table[i + 1, j]
    y01 = table[i, j + 1]
    y11 = table[i + 1, j + 1]

    value = (
        (1 - dx1) * (1 - dx2) * y00
        + dx1 * (1 - dx2) * y10
        + dx1 * dx2 * y11
        + (1 - dx1) * dx2 * y01
    )

    return float(value)


import numpy as np

import numpy as np


def get_1d_value_from_table(values, axis_index, target_value):

    # 假設 axis_index 的格式被包裝在一層 list/tuple 中
    axis = np.array(axis_index[0])

    # 加上 .flatten() 確保無論輸入是 [1,2,3] 還是 [[1,2,3]]，都會變成單純的 1D array
    table = np.array(values).flatten()

    size = len(axis)

    # === 當表格只有一個值時 (size == 1) ===
    if size == 1:
        return float(table[0])

    # === 線性插值 (Linear Interpolation) ===
    i = find_axis_index(axis, target_value)

    # 取得區間的上下界
    xl, xu = axis[i], axis[i + 1]

    # 計算目標值在該區間的比例 (0.0 ~ 1.0)
    dx = (target_value - xl) / (xu - xl)

    # 取得對應的 Y 值 (此時 table 已經是 1D，可以直接用 [i] 讀取)
    y0 = table[i]
    y1 = table[i + 1]

    # 透過距離比例進行加權計算
    value = (1 - dx) * y0 + dx * y1

    return float(value)
