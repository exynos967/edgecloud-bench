#!/usr/bin/env python3
"""15 道手工隐藏题的生成器 (来源: 开发期原始脚本, 逐字节可复现验证)

场景覆盖:
  e1_nl1 / e2_r1 / e3_k8burst / e4_sparse / e5_sparse_arrival  边缘退化场景
  f1_lout1 / f2_burst300                                        极端负载
  g1_loose_slo                                                SLO 宽松
  perf_max                                                    官方约束上限性能题
  final_mix                                                   综合混合负载
  rand_0 / rand_2 / rand_3                                    随机参数组合 (rand_1 已删, rand_4 在 stress/)
  g2_midmix                                                   中等规模混合 (校准锚定)
  tp19                                                        重吞吐 (wtp=1, K=8)

注意: perf_max 的原始生成脚本中 `if t > 0: t += ...` 因 t 初值 0 永不触发,
全体请求都在 t=0 到达。此处忠实复现该行为 (而非"修复"它)。
"""
import json, random, os

HERE = os.path.dirname(os.path.abspath(__file__))


def tbl_full():
    """标准表: 仿 GPU, prefill_proc 线性于 L_in, decode 次线性于组大小"""
    return [[bs, 2 + 0.002 * bs, 5 + 0.05 * bs, 1 + 0.001 * bs,
             0.5 + 0.05 * bs, 3 + 0.08 * bs, 0.5 + 0.02 * bs]
            for bs in [1, 2, 4, 8, 16, 32, 64, 128, 256, 512, 1024, 2048, 4096]]


def tbl_sparse():
    """稀疏表: 部分 batch_size 的某些列为 -1 (缺失), 考察插值"""
    return [
        [1, 2.0, 5.0, 1.0, -1, 3.0, -1],
        [16, 2.0, 6.0, 1.0, 1.3, 4.3, 0.8],
        [256, -1, 18.0, -1, 13.3, 23.5, 5.6],
        [4096, 10.0, 210.0, 5.0, -1, 330.0, -1],
    ]


def tbl_perf():
    """perf_max/tp19 用的显式 13 行表"""
    return [[1, 2.002, 5.05, 1.001, 0.55, 3.08, 0.52], [2, 2.004, 5.1, 1.002, 0.6, 3.16, 0.54],
            [4, 2.008, 5.2, 1.004, 0.7, 3.32, 0.58], [8, 2.016, 5.4, 1.008, 0.9, 3.64, 0.66],
            [16, 2.032, 5.8, 1.016, 1.3, 4.28, 0.82], [32, 2.064, 6.6, 1.032, 2.1, 5.56, 1.14],
            [64, 2.128, 8.2, 1.064, 3.7, 8.12, 1.78], [128, 2.256, 11.4, 1.128, 6.9, 13.24, 3.06],
            [256, 2.512, 17.8, 1.256, 13.3, 23.48, 5.62], [512, 3.024, 30.6, 1.512, 26.1, 44.08, 10.74],
            [1024, 4.048, 56.2, 2.024, 51.7, 85.04, 21.02], [2048, 6.096, 107.4, 3.048, 102.9, 166.16, 41.54],
            [4096, 10.192, 209.8, 5.096, 205.3, 328.4, 82.6]]


def gen(name, K, S, lat, bw, bpt, layers, slo1, slo2, tpub, tpbase, distbase, wtp, wc,
        table_rows, requests):
    cfg = {
        "K": K, "S": S, "latency": lat, "bw": bw, "bpt": bpt, "layers": layers,
        "SLO1": slo1, "SLO2": slo2, "tpUB": tpub, "tpBase": tpbase,
        "distBase": distbase, "wtp": wtp, "wc": wc,
        "table": table_rows,
        "requests": requests,
    }
    path = os.path.join(HERE, "hidden", f"{name}.json")
    with open(path, "w") as f:
        json.dump(cfg, f)
    print("wrote", os.path.relpath(path, HERE))


FULL = tbl_full()

# E1: NL=1 退化 (无分片)
gen("e1_nl1", 2, 1.0, 2.0, 10.0, 125000, 1,
    100.0, 20.0, 0.5, 0.05, 0.5, 0.5, 0.5,
    FULL, [[i * 10.0, 100 + i * 10, 20 + i] for i in range(20)])

# E2: R=1 退化
gen("e2_r1", 4, 1.0, 2.0, 10.0, 125000, 16,
    100.0, 20.0, 0.5, 0.05, 0.5, 0.5, 0.5,
    FULL, [[0.0, 500, 50]])

# E3: K=8 突发 (前 20 个同时到达, 之后每 5ms 一个)
random.seed(3)
gen("e3_k8burst", 8, 1.0, 2.0, 10.0, 125000, 16,
    200.0, 25.0, 0.8, 0.1, 0.5, 0.5, 0.5,
    FULL, [[0.0 if i < 20 else (i - 20) * 5.0, random.randint(128, 512), random.randint(40, 160)]
           for i in range(80)])

# E4: 稀疏表 (含 -1 缺失值, 考察插值)
gen("e4_sparse", 4, 1.0, 2.0, 10.0, 125000, 16,
    200.0, 25.0, 0.8, 0.1, 0.5, 0.5, 0.5,
    tbl_sparse(), [[i * 8.0, 200 + i * 20, 30 + i * 2] for i in range(30)])

# E5: 稀疏到达 + 长空闲 (END 正确性)
gen("e5_sparse_arrival", 2, 1.0, 2.0, 10.0, 125000, 4,
    100.0, 20.0, 0.1, 0.01, 0.5, 0.5, 0.5,
    [[1, 3.0, 10.0, 2.0, 1.0, 4.0, 1.0], [4, 3.0, 10.0, 2.0, 1.0, 4.0, 1.0]],
    [[0.0, 4, 2], [1000.0, 4, 3], [5000.0, 4, 1]])

# F1+F2: 共享一条 seed=11 的随机链 (f1 的 100 次 randint 之后继续生成 f2)
random.seed(11)
f1_reqs = [[i * 5.0, random.randint(128, 1024), 1] for i in range(100)]
f2_reqs = [[float(i // 20), random.randint(256, 512), random.randint(10, 80)] for i in range(300)]

# F1: 全 L_out=1 (无 TPOT gap)
gen("f1_lout1", 4, 1.0, 2.0, 10.0, 125000, 16,
    2600.0, 260.0, 0.031982, 0.015991, 0.176078358, 0.5, 0.5,
    FULL, f1_reqs)

# F2: 高频突发 (15 波 x 20 个)
gen("f2_burst300", 8, 1.0, 2.0, 10.0, 125000, 16,
    300.0, 25.0, 1.5, 0.2, 0.5, 0.5, 0.5,
    FULL, f2_reqs)

# G1: SLO 宽松 (验证 norm_c 可达 1)
random.seed(5)
reqs = []
t = 0.0
for i in range(40):
    t += random.expovariate(0.02)
    reqs.append([round(t, 6), random.randint(128, 512), random.randint(30, 100)])
gen("g1_loose_slo", 4, 1.0, 2.0, 10.0, 125000, 16,
    300.0, 50.0, 0.5, 0.05, 0.5, 0.5, 0.5,
    FULL, reqs)

# final_mix: 泊松 + 突发混合, 自定义表
random.seed(2026)
reqs = []
t = 0.0
for i in range(200):
    if i < 50:
        t += random.expovariate(0.2)
    else:
        t += random.expovariate(0.02)
    reqs.append([round(t, 6), random.randint(128, 2048), random.randint(20, 256)])
gen("final_mix", 4, 1.0, 3.0, 20.0, 100000, 32,
    300.0, 25.0, 1.2, 0.15, 0.6, 0.5, 0.5,
    [[bs, 1.5 + 0.001 * bs, 3 + 0.04 * bs, 0.8 + 0.0008 * bs,
      0.4 + 0.04 * bs, 2.5 + 0.06 * bs, 0.4 + 0.015 * bs]
     for bs in [1, 2, 4, 8, 16, 32, 64, 128, 256, 512, 1024, 2048, 4096]],
    reqs)

# perf_max: 官方约束上限性能题 (R=2000->400, ΣL_out≈2e5, 全体 t=0 到达, 纯吞吐权重)
random.seed(19)
reqs = []
t = 0.0
for lout, cnt in [(512, 390), (1, 10)]:
    for i in range(cnt):
        if t > 0:  # 原始脚本此处恒为 False (t 初值 0), 忠实复现
            t += random.expovariate(1.0 / 2.0)
        reqs.append([round(t, 6), random.choice(list(range(1, 4097))), lout])
gen("perf_max", 8, 1.0, 2.0, 10.0, 125000, 64,
    5000.0, 5000.0, 3.0, 0.1, 1.0, 1.0, 0.0,
    tbl_perf(), reqs)

def bursty(R, Lin_rng, Lout_rng, span, seed):
    random.seed(seed)
    reqs = []
    t = 0.0
    for i in range(R):
        if i > 0 and random.random() < 0.7:
            t += random.expovariate(1.0 / (span / max(1, R)))
        reqs.append([round(t, 6), random.randint(*Lin_rng), random.randint(*Lout_rng)])
    return reqs

# rand_0/2/3: 随机参数组合鲁棒性 (rand_1 物理饱和已删除, rand_4 在 stress/)
# 注意: 随机调用顺序必须与原始脚本严格一致 (dict 字面量求值顺序)
# 评分参数为校准后的覆盖值 (锚定 FCFS 基线实测), 不用链上随机值
RAND_CALIBRATED = {
    0: dict(slo1=200.0, slo2=10.0, tpub=0.3887475, tpbase=0.047639, distbase=315.954815491),
    2: dict(slo1=10.0, slo2=1.0, tpub=0.31372125, tpbase=0.046333, distbase=978.388186737),
    3: dict(slo1=1200.0, slo2=18.0, tpub=3.30742, tpbase=0.314763, distbase=1.432775111),
}
for seed in [0, 2, 3]:
    random.seed(1000 + seed)
    K = random.choice([1, 2, 4, 8])
    NL = random.choice([1, 4, 16, 64])
    R = random.randint(20, 300)
    reqs = []
    t = 0.0
    for i in range(R):
        t += random.expovariate(1.0 / random.choice([5, 20, 100]))
        reqs.append([round(t, 6), random.randint(1, 4096), random.randint(1, 512)])
    tot = sum(o for _, _, o in reqs)
    if tot > 200000:
        scale = 200000 / tot
        reqs = [[a, l, max(1, int(o * scale))] for a, l, o in reqs]
    S = random.choice([1, 3, 10])
    lat = random.choice([0.5, 2, 20])
    bw = random.choice([1, 10, 100])
    bpt = random.choice([1000, 125000, 1000000])
    slo1 = random.choice([100, 500, 2000])
    slo2 = random.choice([10, 30, 100])
    tpub = random.choice([0.5, 1, 2])
    tpbase = random.choice([0.01, 0.1])
    distbase = random.choice([0.3, 0.5, 1.0])
    wtp = random.choice([0, 0.5, 1])
    wc = 1.0 - wtp
    cb = RAND_CALIBRATED[seed]
    gen(f"rand_{seed}", K, S, lat, bw, bpt, NL, cb["slo1"], cb["slo2"], cb["tpub"],
        cb["tpbase"], cb["distbase"], wtp, wc, FULL, reqs)

# g2_midmix: 中等规模混合权重 (替换 f3_bigsingle/rand_1, 已校准)
gen("g2_midmix", 4, 1.0, 2.0, 10.0, 125000, 16,
    2880.0, 288.0, 1.47900375, 0.278934, 0.306890796, 0.5, 0.5,
    FULL, bursty(120, (256, 1024), (50, 200), 700.0, 7777))

# tp19: 重吞吐 (wtp=1), bursty 到达; K 已由 16 修为 8 (官方 K<=8)
gen("tp19", 8, 1.0, 2.0, 10.0, 125000, 32,
    800.0, 400.0, 0.8, 0.1, 1.0, 1.0, 0.0,
    FULL, bursty(1500, (128, 512), (4, 32), 500.0, 7))
