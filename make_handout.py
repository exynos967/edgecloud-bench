#!/usr/bin/env python3
"""生成模型侧 handout 目录: 只有题面与官方样例, 不含计分题/评分器/答案

用法:
  python3 make_handout.py /path/to/model_workspace

评测流程 (环境隔离):
  1. 运营方: python3 make_handout.py <model_workspace>
  2. 模型在 <model_workspace> 中工作, 产出 solution
  3. 运营方取回 solution, 在本仓库根目录跑: python3 runner.py <path/to/solution>
"""
import os, shutil, sys

BENCH = os.path.dirname(os.path.abspath(__file__))


def main():
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    dst = sys.argv[1]
    os.makedirs(os.path.join(dst, "samples"), exist_ok=True)
    shutil.copy(os.path.join(BENCH, "docs", "PROBLEM.md"), os.path.join(dst, "PROBLEM.md"))
    for f in os.listdir(os.path.join(BENCH, "fixtures", "samples")):
        if f.endswith(".json"):
            shutil.copy(os.path.join(BENCH, "fixtures", "samples", f),
                        os.path.join(dst, "samples", f))
    print(f"handout 已生成: {dst}")
    print(f"  PROBLEM.md + samples/ ({len(os.listdir(os.path.join(dst, 'samples')))} 个样例 JSON)")


if __name__ == "__main__":
    main()
