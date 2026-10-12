# 当前真实 interval 与时钟审计

| Provider | Hz | boundaries | substep targets exact | first v0 rejection |
|---|---:|---:|---:|---|
| geophys | 500 | 3501 | 3501 | None |
| geophys | 100 | 700 | 3500 | {'boundary': 3, 'previous_time': 0.020000000000000004, 'native_time': 0.030000000000000013, 'delta_error': 8.673617379884035e-18, 'v0_bound': 3.469446951953614e-18} |
| geophys | 50 | 350 | 3500 | {'boundary': 2, 'previous_time': 0.020000000000000004, 'native_time': 0.04000000000000002, 'delta_error': 1.734723475976807e-17, 'v0_bound': 6.938893903907228e-18} |
| mujoco | 500 | 3487 | 3487 | None |
| mujoco | 100 | 698 | 3490 | None |
| mujoco | 50 | 349 | 3490 | None |

所有真实 canonical 请求/AppliedCanonicalControl 逐子步重构，保留 GeoPhys float32 acknowledgment 与请求的差别，不要求二者 bitwise 相等。每 outer 更新一次 gripper，之后 ZOH；arm hold及native数量校验。完整前缀与 owner snapshot synthetic 重构通过。

二进制64累计 n 个 dt 的界：u=2^-53，gamma_n=n*u/(1-n*u)，误差 <=gamma_n*abs(n*dt)+ulp(n*dt)，且必须独立证明native计数。数学界检查通过不等于现有v0 one-ULP接受。记录层需要整数physics step、projected canonical time、raw native time及误差证明；本轮未修改 v0 或 dt。Live recorder仍未连接此prototype，故 Infrastructure NO-GO。
