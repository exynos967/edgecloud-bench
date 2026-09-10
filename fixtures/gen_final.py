#!/usr/bin/env python3
"""20 道冻结决赛题生成器 (fixtures/final/)

还原官方赛制: 预赛 22 题给反馈, 决赛 20 题冻结 (模型不可见明细), 最终分 = 20 题均值。
决赛题与隐藏题 (hidden/) 场景族对应但种子/参数不同, 防止针对预赛题集过拟合。
全部满足官方约束: K<=8, R<=2000, L_in<=4096, L_out<=512, ΣL_out<=2e5, NL<=64。
"""
import json, random, os

HERE = os.path.dirname(os.path.abspath(__file__))


def tbl_full():
    return [[bs, 2 + 0.002 * bs, 5 + 0.05 * bs, 1 + 0.001 * bs,
             0.5 + 0.05 * bs, 3 + 0.08 * bs, 0.5 + 0.02 * bs]
            for bs in [1, 2, 4, 8, 16, 32, 64, 128, 256, 512, 1024, 2048, 4096]]


def tbl_sparse():
    return [
        [1, 2.0, 5.0, 1.0, -1, 3.0, -1],
        [16, 2.0, 6.0, 1.0, 1.3, 4.3, 0.8],
        [256, -1, 18.0, -1, 13.3, 23.5, 5.6],
        [4096, 10.0, 210.0, 5.0, -1, 330.0, -1],
    ]


def bursty(R, Lin_rng, Lout_rng, span, seed):
    random.seed(seed)
    reqs = []
    t = 0.0
    for i in range(R):
        if i > 0 and random.random() < 0.7:
            t += random.expovariate(1.0 / (span / max(1, R)))
        reqs.append([round(t, 6), random.randint(*Lin_rng), random.randint(*Lout_rng)])
    return reqs


def poisson(R, rate, Lin_rng, Lout_rng, seed):
    random.seed(seed)
    reqs = []
    t = 0.0
    for i in range(R):
        if i > 0:
            t += random.expovariate(rate)
        reqs.append([round(t, 6), random.randint(*Lin_rng), random.randint(*Lout_rng)])
    return reqs


def gen(name, K, S, lat, bw, bpt, layers, slo1, slo2, tpub, tpbase, distbase, wtp, wc,
        table_rows, requests):
    sum_lout = sum(r[2] for r in requests)
    assert 1 <= K <= 8 and 1 <= len(requests) <= 2000 and sum_lout <= 2e5, name
    assert all(1 <= r[1] <= 4096 and 1 <= r[2] <= 512 for r in requests), name
    arr = [r[0] for r in requests]
    assert arr == sorted(arr), name
    cfg = {
        "K": K, "S": S, "latency": lat, "bw": bw, "bpt": bpt, "layers": layers,
        "SLO1": slo1, "SLO2": slo2, "tpUB": tpub, "tpBase": tpbase,
        "distBase": distbase, "wtp": wtp, "wc": wc,
        "table": table_rows,
        "requests": requests,
    }
    os.makedirs(os.path.join(HERE, "final"), exist_ok=True)
    path = os.path.join(HERE, "final", f"{name}.json")
    with open(path, "w") as f:
        json.dump(cfg, f)
    print("wrote", os.path.relpath(path, HERE))


FULL = tbl_full()

# f01/f02: 突发 (对应 t1/e3/f2)
gen("f01_burst_k4", 4, 1.0, 2.0, 10.0, 125000, 16,
    150.0, 20.0, 0.4, 0.05, 0.5, 0.5, 0.5,
    FULL, bursty(80, (256, 1024), (50, 200), 600.0, 9101))
gen("f02_burst_k8", 8, 1.0, 2.0, 10.0, 125000, 16,
    250.0, 25.0, 0.8, 0.1, 0.5, 0.5, 0.5,
    FULL, bursty(150, (128, 512), (40, 160), 500.0, 9102))

# f03/f04: 泊松稳态 (对应 t2/e5)
gen("f03_poisson_k8", 8, 1.0, 2.0, 10.0, 125000, 32,
    300.0, 25.0, 0.5, 0.08, 0.5, 0.5, 0.5,
    FULL, poisson(150, 0.01, (512, 2048), (30, 150), 9103))
gen("f04_poisson_k2", 2, 1.0, 2.0, 10.0, 125000, 16,
    200.0, 20.0, 0.3, 0.05, 0.5, 0.5, 0.5,
    FULL, poisson(60, 0.005, (256, 1024), (20, 100), 9104))

# f05/f06: 纯吞吐 (对应 t3/tp19)
gen("f05_throughput_k8", 8, 1.0, 2.0, 10.0, 125000, 16,
    800.0, 400.0, 0.9, 0.1, 1.0, 1.0, 0.0,
    FULL, bursty(400, (128, 512), (20, 100), 900.0, 9105))
gen("f06_throughput_k4", 4, 1.0, 2.0, 10.0, 125000, 16,
    1000.0, 100.0, 0.6, 0.1, 1.0, 1.0, 0.0,
    FULL, poisson(300, 0.02, (256, 512), (30, 120), 9106))

# f07/f08: 纯等待 (对应 t4)
gen("f07_latency_k4", 4, 1.0, 2.0, 10.0, 125000, 16,
    1648.0, 309.0, 0.89142375, 0.251485, 0.093939853, 0.0, 1.0,
    FULL, bursty(60, (256, 1024), (30, 120), 700.0, 9107))
gen("f08_tight_slo_k2", 2, 1.0, 2.0, 10.0, 125000, 16,
    114.0, 22.8, 0.51031, 0.255155, 1.533044656, 0.0, 1.0,
    FULL, poisson(40, 0.008, (128, 512), (20, 80), 9108))

# f09: 大 prefill 促分片 (对应 t6)
gen("f09_bigprefill", 4, 1.0, 2.0, 10.0, 125000, 64,
    400.0, 20.0, 0.5, 0.08, 0.5, 0.5, 0.5,
    FULL, bursty(80, (1024, 4096), (50, 200), 700.0, 9109))

# f10: 全 L_out=1 (对应 f1)
random.seed(9110)
gen("f10_lout1", 4, 1.0, 2.0, 10.0, 125000, 16,
    2680.0, 268.0, 0.033584, 0.016792, 0.178198004, 0.5, 0.5,
    FULL, [[i * 4.0, random.randint(128, 1024), 1] for i in range(120)])

# f11: K=1 退化 (对应 t5)
gen("f11_k1", 1, 1.0, 2.0, 10.0, 125000, 16,
    150.0, 20.0, 0.3, 0.05, 0.5, 0.5, 0.5,
    FULL, bursty(50, (256, 1024), (50, 150), 600.0, 9111))

# f12: NL=1 退化 (对应 e1)
gen("f12_nl1", 2, 1.0, 2.0, 10.0, 125000, 1,
    100.0, 20.0, 0.5, 0.05, 0.5, 0.5, 0.5,
    FULL, [[i * 12.0, 120 + i * 12, 24 + i] for i in range(25)])

# f13: R=1 退化 (对应 e2)
gen("f13_r1", 4, 1.0, 2.0, 10.0, 125000, 32,
    120.0, 25.0, 0.5, 0.05, 0.5, 0.5, 0.5,
    FULL, [[0.0, 800, 64]])

# f14: 稀疏表插值 (对应 e4)
gen("f14_sparse_table", 4, 1.0, 2.0, 10.0, 125000, 16,
    200.0, 25.0, 0.8, 0.1, 0.5, 0.5, 0.5,
    tbl_sparse(), [[i * 9.0, 240 + i * 18, 32 + i * 2] for i in range(35)])

# f15: 混合负载 (对应 final_mix)
random.seed(9115)
reqs = []
t = 0.0
for i in range(180):
    t += random.expovariate(0.2 if i < 40 else 0.02)
    reqs.append([round(t, 6), random.randint(128, 2048), random.randint(20, 250)])
gen("f15_mix", 4, 1.0, 3.0, 20.0, 100000, 32,
    300.0, 25.0, 1.2, 0.15, 0.6, 0.5, 0.5,
    [[bs, 1.5 + 0.001 * bs, 3 + 0.04 * bs, 0.8 + 0.0008 * bs,
      0.4 + 0.04 * bs, 2.5 + 0.06 * bs, 0.4 + 0.015 * bs]
     for bs in [1, 2, 4, 8, 16, 32, 64, 128, 256, 512, 1024, 2048, 4096]],
    reqs)

# f16: SLO 宽松 (对应 g1)
gen("f16_loose_slo", 4, 1.0, 2.0, 10.0, 125000, 16,
    300.0, 50.0, 0.5, 0.05, 0.5, 0.5, 0.5,
    FULL, poisson(50, 0.02, (128, 512), (30, 100), 9116))

# f17/f18: 随机参数组合 (对应 rand_0/2/3); 评分参数为校准后的覆盖值 (锚定 FCFS 基线实测)
FINAL_RAND_CALIBRATED = {
    9217: dict(slo1=810.0, slo2=243.0, tpub=0.27346375, tpbase=0.045501, distbase=0.62124272),
    9218: dict(slo1=39990.0, slo2=39990.0, tpub=0.12718625, tpbase=0.034834, distbase=1.827924634),
}
for seed, name in [(9217, "f17_rand_a"), (9218, "f18_rand_b")]:
    random.seed(seed)
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
    cb = FINAL_RAND_CALIBRATED[seed]
    gen(name, K, S, lat, bw, bpt, NL, cb["slo1"], cb["slo2"], cb["tpub"], cb["tpbase"],
        cb["distbase"], wtp, 1.0 - wtp, FULL, reqs)

# f19: 大规模重吞吐 (对应 tp19 的族)
gen("f19_big_throughput", 8, 1.0, 2.0, 10.0, 125000, 32,
    800.0, 400.0, 0.8, 0.1, 1.0, 1.0, 0.0,
    FULL, bursty(1500, (128, 512), (4, 32), 600.0, 9119))

# f20: 近上限 R=2000 混合权重
gen("f20_large_mix", 8, 1.0, 2.0, 10.0, 125000, 32,
    500.0, 40.0, 1.0, 0.1, 0.8, 0.5, 0.5,
    FULL, poisson(2000, 0.005, (128, 1024), (1, 100), 9120))
