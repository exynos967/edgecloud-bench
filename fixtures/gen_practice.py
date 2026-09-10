#!/usr/bin/env python3
"""公开练习题生成器 (fixtures/practice/) — 供自测与调试用 (p08 已删: L_out=1 族物理饱和无区分度)
与官方计分题无关 (不同种子/参数)。全部满足官方约束: K<=8, R<=2000, ΣL_out<=2e5。"""
import json, random, os

HERE = os.path.dirname(os.path.abspath(__file__))


def tbl_full():
    return [[bs, 2 + 0.002 * bs, 5 + 0.05 * bs, 1 + 0.001 * bs,
             0.5 + 0.05 * bs, 3 + 0.08 * bs, 0.5 + 0.02 * bs]
            for bs in [1, 2, 4, 8, 16, 32, 64, 128, 256, 512, 1024, 2048, 4096]]


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
    os.makedirs(os.path.join(HERE, "practice"), exist_ok=True)
    path = os.path.join(HERE, "practice", f"{name}.json")
    with open(path, "w") as f:
        json.dump(cfg, f)
    print("wrote", os.path.relpath(path, HERE))


FULL = tbl_full()

# p01/p02: 突发
gen("p01_burst_k4", 4, 1.0, 2.0, 10.0, 125000, 16,
    150.0, 20.0, 0.4, 0.05, 0.5, 0.5, 0.5,
    FULL, bursty(60, (256, 1024), (50, 200), 550.0, 7101))
gen("p02_burst_k8", 8, 1.0, 2.0, 10.0, 125000, 16,
    250.0, 25.0, 0.8, 0.1, 0.5, 0.5, 0.5,
    FULL, bursty(120, (128, 512), (40, 160), 450.0, 7102))

# p03: 泊松稳态
gen("p03_poisson_k8", 8, 1.0, 2.0, 10.0, 125000, 32,
    300.0, 25.0, 0.5, 0.08, 0.5, 0.5, 0.5,
    FULL, poisson(120, 0.01, (512, 2048), (30, 150), 7103))

# p04: 纯吞吐
gen("p04_throughput", 4, 1.0, 2.0, 10.0, 125000, 16,
    1000.0, 100.0, 0.6, 0.1, 1.0, 1.0, 0.0,
    FULL, bursty(150, (128, 512), (100, 300), 800.0, 7104))

# p05: 纯等待 (SLO 紧)
gen("p05_latency", 4, 1.0, 2.0, 10.0, 125000, 16,
    1376.0, 258.0, 0.70643875, 0.238449, 0.145778044, 0.0, 1.0,
    FULL, bursty(50, (256, 1024), (30, 120), 650.0, 7105))

# p06: 大 prefill (NL=64)
gen("p06_bigprefill", 4, 1.0, 2.0, 10.0, 125000, 64,
    400.0, 20.0, 0.5, 0.08, 0.5, 0.5, 0.5,
    FULL, bursty(60, (1024, 4096), (50, 200), 650.0, 7106))

# p07: K=1 退化
gen("p07_k1", 1, 1.0, 2.0, 10.0, 125000, 16,
    150.0, 20.0, 0.3, 0.05, 0.5, 0.5, 0.5,
    FULL, bursty(40, (256, 1024), (50, 150), 500.0, 7107))

# p09: 稀疏到达 + 长空闲
gen("p09_sparse", 2, 1.0, 2.0, 10.0, 125000, 4,
    100.0, 20.0, 0.1, 0.01, 0.5, 0.5, 0.5,
    [[1, 3.0, 10.0, 2.0, 1.0, 4.0, 1.0], [4, 3.0, 10.0, 2.0, 1.0, 4.0, 1.0]],
    [[0.0, 4, 2], [800.0, 4, 3], [3000.0, 4, 1]])

# p10: 较大规模混合
gen("p10_large_mix", 8, 1.0, 2.0, 10.0, 125000, 32,
    500.0, 40.0, 1.0, 0.1, 0.8, 0.5, 0.5,
    FULL, poisson(1000, 0.01, (128, 1024), (1, 100), 7110))
