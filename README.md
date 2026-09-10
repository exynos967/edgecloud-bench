# edgecloud-bench

**边缘云协同调度能力评测基准（公开自测版）** — 源自 Codeforces Round 2251 题 A（交互题），用于评测大模型的协议理解与在线调度策略设计能力。

> 本仓库是**自测/开发版**：包含题面、官方样例、模拟器、评测器与公开练习题。
> 权威评分的计分题集不在本仓库；正式成绩由评测方在私有题集上跑出。

## 题目

系统由 1 台本地计算机 E 和 K 台远端计算机 C0…C(K-1) 组成，持续接收推理请求。每个请求先经 **prefill**（P PRE→P PROC→P POST，一次），再逐 token 执行 **decode**（D PRE→D PROC→D POST，每 token 一轮）。传输自动排队（上行/下行两条 FIFO 共享链路），参赛者每收到一个事件帧就要决定各空闲计算机执行什么任务。题目全文见 [`docs/PROBLEM.md`](docs/PROBLEM.md)

## 打分方式

每题得分（与官方公式逐字段对齐）：

```
tp   = ΣL_out / 总耗时                      # 吞吐
tdr  = 各请求 " arrival→可开始decode " 均值
tpot = 相邻 token 间隔均值
dist = sqrt( max(0,(tdr-SLO1)/SLO1)² + max(0,(tpot-SLO2)/SLO2)² )
Score = 1000 × ( w_tp·clamp(tp; tp_base, tp_UB) + w_c·clamp(dist; dist_base, 0) )
```

正式赛制为两阶段：22 道预赛题给逐题反馈，20 道冻结决赛题的均值即最终成绩。**本仓库只含 2 道官方样例与 10 道公开练习题**，正式计分题不公开。

## 测什么能力

| 维度 | 考察点 |
|---|---|
| 协议理解 | 9 种事件、6 种指令、状态机约束（分片连续、远端绑定、E 单任务、每帧 ≤K+1 任务） |
| 调度策略 | prefill/decode 权衡、攒批、分片、负载均衡 |
| 前瞻建模 | 传输 FIFO 完成时间估计、积压感知 |
| 工程性能 | 15s CPU / 256MB 下处理约 10⁶ 事件帧 |
| 鲁棒性 | FIN 与 TDN 同帧、空帧、END、表插值边界 |

## 用法（自测）

```bash
python3 runner.py solution.cpp          # 默认: 2 官方样例 + 10 公开练习题
python3 runner.py solution.py           # 也支持 Python（官方原题不限语言）
python3 runner.py solution.cpp --subset samples|practice|stress
python3 make_handout.py <model_workspace>   # 生成模型侧目录 (只有题面+样例)
```

练习题生成器：`python3 fixtures/gen_practice.py`（种子固定，可复现）。

## 给模型的测试提示词

```text
你在参加一个交互式调度编程评测。

题目：阅读当前目录下的 PROBLEM.md（官方英文题干，交互协议、约束、评分公式以它为准）。
参考：samples/ 下两个 JSON 由官方题面样例整理为评测器输入格式（test_ex1 = 官方 Example 1
      完整参数；test_ex2 = 官方 Example 2 交互片段的重建，部分参数为补全值），
      可用于理解协议，但评测题与它们不同。

任务：独立编写程序 solution（语言不限，如 GNU C++17 / Python 3），通过标准输入输出与交互器通信：
      循环读取事件帧 → 输出任务分配（首行任务数 n，随后 n 行指令）→ flush。
      程序限制 15 秒 CPU、256MB 内存；协议违规该题得 0 分。
      注意交互量可达约 10⁶ 帧，解释型语言需自行评估性能风险。

规则：
- 只允许依据 PROBLEM.md 与 samples/ 解题，不得读取评测环境中的其他任何文件
  （测试数据、评分器、他人解答等），不得探测环境信息
- 提交前请自行充分调试；samples/ 的样例参数可供你自建模拟环境验证协议与策略
- 正式评测只提交一次：评测方将你的 solution 提交给评测器，
  返回预赛 22 题逐题成绩与冻结决赛 20 题的总成绩

完成后将 solution 源码文件放在当前目录即可。
```
