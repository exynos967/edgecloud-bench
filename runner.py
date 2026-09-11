#!/usr/bin/env python3
"""
edgecloud-bench 评测器 — 还原 Codeforces 2251 A 的打分流程

用法:
  python3 runner.py <solution> [--subset public|hidden|all|samples|stress] [--json out.json]
  python3 runner.py <solution> --binary   # 跳过编译, 直接评测可执行文件
  python3 runner.py <solution> --final    # 只跑 20 道冻结决赛题 (聚合分)

规则: 一次提交一次出分。默认跑 22 道预赛题 (逐题明细) + 自动附跑 20 道冻结决赛题 (聚合分)。
结果归档 results/<solution_name>.json 单文件 (含预赛明细与决赛聚合, 重跑覆盖)。
"""
import json, os, subprocess, sys, time, argparse

BENCH = os.path.dirname(os.path.abspath(__file__))
SIM = os.path.join(BENCH, "interactor", "simulator.py")
FIXTURES = os.path.join(BENCH, "fixtures")
# 目录按存在性自适应: 官方评分仓库含 public/hidden/final; 公开自测仓库含 samples/practice/stress
PUBLIC = os.path.join(FIXTURES, "public")
HIDDEN = os.path.join(FIXTURES, "hidden")
FINAL = os.path.join(FIXTURES, "final")       # 20 道冻结决赛题 (仅官方评分仓库)
PRACTICE = os.path.join(FIXTURES, "practice")  # 公开练习题 (仅公开仓库)
STRESS = os.path.join(FIXTURES, "stress")     # 超规格压力测试 (opt-in)
TIME_LIMIT = 15        # CF: 15 秒 CPU
MEM_LIMIT_MB = 256     # CF: 256 MB


def build_command(src, workdir):
    """按扩展名构建启动命令。返回 argv 列表 (模拟器接受多参数 argv)"""
    ext = os.path.splitext(src)[1].lower()
    if ext in (".cpp", ".cc", ".cxx"):
        # 二进制路径含源文件名 + pid, 保证并行评测互不覆盖
        tag = os.path.basename(src).replace(".", "_")
        exe = os.path.join(workdir, f"solution_{tag}_{os.getpid()}")
        r = subprocess.run(["g++", "-O2", "-std=gnu++17", "-o", exe, src],
                           capture_output=True, text=True)
        if r.returncode != 0:
            print("编译失败:\n" + r.stderr)
            sys.exit(2)
        return [exe]
    if ext == ".py":
        return ["python3", src]
    # 其他: 视为可执行文件
    if os.path.isfile(src) and os.access(src, os.X_OK):
        return [src]
    print(f"✗ 不支持的 solution 类型: {src} (支持 .cpp/.cc/.cxx/.py 或可执行文件)")
    sys.exit(2)


def run_fixture(fixture, cmd):
    """跑单个测试: 返回 (status, wall_ms, result_dict)
    TLE/MLE 由模拟器内 RLIMIT_CPU/RLIMIT_AS 对 solution 施加 (CF 语义), 此处墙钟仅兜底"""
    t0 = time.time()
    status = "OK"
    try:
        r = subprocess.run(["python3", SIM, fixture] + cmd,
                           capture_output=True, text=True, timeout=600)
        wall_ms = int((time.time() - t0) * 1000)
        out = r.stdout.strip()
        d = {}
        try:
            d = json.JSONDecoder().raw_decode(out)[0]
        except Exception:
            d = {"error": f"bad interactor output: {out[:100]}", "points": 0.0}
        err = d.get("error") or ""
        if err:
            if "time limit" in err:
                status = "TLE"
            elif "segmentation" in err:
                status = "RE"
            else:
                status = "WA"      # 协议违规 / 提前退出, CF 判 WA
            d["points"] = 0.0
    except subprocess.TimeoutExpired:
        wall_ms = int(time.time() - t0) * 1000
        status = "TLE"
        d = {"points": 0.0, "error": "wall timeout (simulator hang)"}
    return status, wall_ms, d


def eval_fixtures(fixtures, exe):
    results = []
    for fx in fixtures:
        test_name = os.path.basename(fx)[:-5]
        status, wall_ms, d = run_fixture(fx, exe)
        rec = {
            "test": test_name,
            "status": status,
            "runtime_ms": wall_ms,
            "points": d.get("points", 0.0),
            "tp": d.get("tp"),
            "mean_tdr": d.get("mean_tdr"),
            "mean_tpot": d.get("mean_tpot"),
            "dist": d.get("dist"),
            "norm_tp": d.get("norm_tp"),
            "norm_c": d.get("norm_c"),
            "normalized_score": d.get("normalized_score"),
            "error": d.get("error"),
        }
        results.append(rec)
    return results


def summarize(archive):
    """归档首部的中文成绩摘要, 登记排行榜时直接抄这一块"""
    s = {}
    for key in ("final", "prelim"):
        if key not in archive:
            continue
        stage = archive[key]
        ok = sum(1 for r in stage["per_test"] if r["status"] == "OK")
        n = len(stage["per_test"])
        label = "决赛" if key == "final" else ("预赛" if stage.get("subset") == "all" else f"子集({stage.get('subset')})")
        if key == "final":
            s["决赛平均分(排名依据)"] = stage["mean_points"]
        else:
            s[f"{label}平均分"] = stage["mean_points"]
        s[f"{label}总分"] = stage["total_points"]
        s[f"{label}通过"] = f"{ok}/{n}"
    return s


def run_final(exe, name):
    """冻结决赛: 20 题, 只输出聚合分 (防过拟合), 明细随单文件归档供审计"""
    if not os.path.isdir(FINAL):
        print("✗ 本仓库不含冻结决赛题 (仅官方评分环境提供)")
        sys.exit(2)
    fixtures = sorted(os.path.join(FINAL, f) for f in os.listdir(FINAL) if f.endswith(".json"))
    results = eval_fixtures(fixtures, exe)
    total = round(sum(r["points"] for r in results), 6)
    mean = round(total / len(results), 6) if results else 0.0
    print("=" * 60)
    print(f"  solution={name}  FINAL (20 道冻结决赛题)")
    print(f"  通过: {sum(1 for r in results if r['status'] == 'OK')}/{len(results)}")
    print(f"  FINAL TOTAL: {total:.6f}")
    print(f"  FINAL MEAN : {mean:.6f}   (官方口径: 20 题 points 算术平均)")
    print("=" * 60)
    return {"total_points": total, "mean_points": mean, "per_test": results}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("solution", help="solution 路径 (.cpp/.py/可执行文件)")
    ap.add_argument("--subset", default="all",
                    choices=["public", "hidden", "practice", "all", "samples", "stress"])
    ap.add_argument("--binary", action="store_true", help="直接跑二进制, 跳过编译")
    ap.add_argument("--json", default=None, help="结果 JSON 输出路径")
    ap.add_argument("--final", action="store_true",
                    help="只跑 fixtures/final 20 道冻结决赛题, 输出聚合分")
    args = ap.parse_args()

    name = os.path.splitext(os.path.basename(args.solution))[0]
    workdir = os.path.join(BENCH, "results")
    os.makedirs(workdir, exist_ok=True)
    if args.binary:
        if not (os.path.isfile(args.solution) and os.access(args.solution, os.X_OK)):
            print(f"✗ --binary 要求可执行文件: {args.solution}")
            sys.exit(2)
        exe = [args.solution]
    else:
        exe = build_command(args.solution, workdir)

    if args.final:
        archive = {
            "solution": name,
            "成绩摘要": None,
            "time_limit_s": TIME_LIMIT,
            "mem_limit_mb": MEM_LIMIT_MB,
            "final": run_final(exe, name),
        }
        archive["成绩摘要"] = summarize(archive)
        out_path = args.json or os.path.join(workdir, f"{name}.json")
        if out_path != os.devnull:
            with open(out_path, "w") as f:
                json.dump(archive, f, indent=2, ensure_ascii=False)
            print(f"结果已写入: {out_path}")
        return

    def ls_json(d):
        return sorted(os.path.join(d, f) for f in os.listdir(d) if f.endswith(".json")) if os.path.isdir(d) else []

    fixtures = []
    if args.subset in ("public", "all"):
        fixtures += ls_json(PUBLIC)
    if args.subset in ("hidden", "all"):
        fixtures += ls_json(HIDDEN)
    if args.subset in ("practice",):
        fixtures += ls_json(PRACTICE)
    if args.subset in ("samples", "all") and not ls_json(PUBLIC) and not ls_json(HIDDEN):
        # 公开自测仓库: all 包含 samples (官方样例也可跑通验证)
        fixtures += ls_json(os.path.join(FIXTURES, "samples"))
    elif args.subset in ("samples",):
        fixtures += ls_json(os.path.join(FIXTURES, "samples"))
    if args.subset in ("stress",):
        fixtures += ls_json(STRESS)

    results = eval_fixtures(fixtures, exe)

    total = round(sum(r["points"] for r in results), 6)
    mean = round(total / len(results), 6) if results else 0.0

    print("=" * 108)
    print(f"  solution={name}  subset={args.subset}")
    print(f"{'test':<18}{'status':<5}{'ms':>7}{'points':>12}{'tp':>12}{'tdr':>14}{'tpot':>12}{'dist':>10}{'norm_tp':>10}{'norm_c':>10}")
    print("-" * 108)
    for r in results:
        print(f"{r['test']:<18}{r['status']:<5}{r['runtime_ms']:>7}{r['points']:>12.6f}"
              f"{str(r['tp']):>12}{str(r['mean_tdr']):>14}{str(r['mean_tpot']):>12}"
              f"{str(r['dist']):>10}{str(r['norm_tp']):>10}{str(r['norm_c']):>10}")
        if r["error"]:
            print(f"    └─ {r['error']}")
    print("-" * 108)
    print(f"{'TOTAL':<18}{'':<5}{'':>7}{total:>12.6f}   ({len(results)} 题)")
    print(f"{'MEAN':<18}{'':<5}{'':>7}{mean:>12.6f}   (均值口径同官方决赛: 各题 points 算术平均)")
    print("=" * 108)

    out = {
        "solution": name,
        "成绩摘要": None,
        "time_limit_s": TIME_LIMIT,
        "mem_limit_mb": MEM_LIMIT_MB,
        "prelim": {
            "subset": args.subset,
            "total_points": total,
            "mean_points": mean,
            "per_test": results,
        },
    }

    # 官方评分仓库: 默认全量提交自动附跑冻结决赛, 一份报告给出预赛明细 + 决赛聚合两种分数
    if args.subset == "all" and os.path.isdir(FINAL):
        print()
        out["final"] = run_final(exe, name)

    out["成绩摘要"] = summarize(out)
    out_path = args.json or os.path.join(workdir, f"{name}.json")
    if out_path != os.devnull:
        with open(out_path, "w") as f:
            json.dump(out, f, indent=2, ensure_ascii=False)
        print(f"结果已写入: {out_path}")


if __name__ == "__main__":
    main()
