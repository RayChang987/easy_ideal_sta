import torch


def get_value_from_table_torch(
    values, input_slew_index, output_load_index, input_slew, output_load, device=None
):
    axis1 = input_slew_index[0]
    axis2 = output_load_index[0]
    table = values

    size1 = len(axis1)
    size2 = len(axis2)

    # 1. 尋找 Index（張量化版本）
    # 支援 scalar / batched tensor；detach 只用在找區間，不影響插值梯度。
    s = (
        input_slew
        if isinstance(input_slew, torch.Tensor)
        else torch.tensor(input_slew, dtype=axis1.dtype, device=axis1.device)
    )
    l = (
        output_load
        if isinstance(output_load, torch.Tensor)
        else torch.tensor(output_load, dtype=axis2.dtype, device=axis2.device)
    )

    if not isinstance(s, torch.Tensor):
        s = torch.as_tensor(s, dtype=axis1.dtype, device=axis1.device)
    else:
        s = s.to(dtype=axis1.dtype, device=axis1.device)

    if not isinstance(l, torch.Tensor):
        l = torch.as_tensor(l, dtype=axis2.dtype, device=axis2.device)
    else:
        l = l.to(dtype=axis2.dtype, device=axis2.device)

    if size1 > 1:
        i = torch.bucketize(s.detach(), axis1, right=False) - 1
        i = i.clamp(min=0, max=size1 - 2)
    else:
        i = torch.zeros_like(s, dtype=torch.long)

    if size2 > 1:
        j = torch.bucketize(l.detach(), axis2, right=False) - 1
        j = j.clamp(min=0, max=size2 - 2)
    else:
        j = torch.zeros_like(l, dtype=torch.long)

    # 2. 取得區間的上下界
    x1l = axis1[i]
    x1u = axis1[i + 1] if size1 > 1 else axis1[0]

    x2l = axis2[j]
    x2u = axis2[j + 1] if size2 > 1 else axis2[0]

    # 3. 計算距離比例 dx
    # 【關鍵修復】：這裡直接使用帶有梯度的 input_slew / output_load 進行相減
    # 不作 clamp，允許 dx > 1.0 或 dx < 0.0，完美重現原版的線性外插！
    dx1 = (
        (s - x1l) / (x1u - x1l)
        if size1 > 1
        else torch.zeros_like(s, dtype=axis1.dtype, device=axis1.device)
    )
    dx2 = (
        (l - x2l) / (x2u - x2l)
        if size2 > 1
        else torch.zeros_like(l, dtype=axis2.dtype, device=axis2.device)
    )

    # 4. 取得四個頂點的數值 (支援 1D / 2D table)
    idx_i0 = i
    idx_i1 = i + 1 if size1 > 1 else i
    idx_j0 = j
    idx_j1 = j + 1 if size2 > 1 else j

    y00 = table[idx_i0, idx_j0]
    y10 = table[idx_i1, idx_j0]
    y01 = table[idx_i0, idx_j1]
    y11 = table[idx_i1, idx_j1]

    # 5. 雙線性內插 / 外插 (保留了 dx1, dx2 的梯度，能順利反向傳播)
    value = (
        (1 - dx1) * (1 - dx2) * y00
        + dx1 * (1 - dx2) * y10
        + (1 - dx1) * dx2 * y01
        + dx1 * dx2 * y11
    )

    return value
