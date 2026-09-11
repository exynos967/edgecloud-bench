#!/usr/bin/env python3
"""Codeforces 2251 A 交互模拟器 + 评分器 (传输 FIFO 正确建模: 完成时间依赖后续入队)"""
import json, subprocess, sys, math, bisect, os
from collections import deque
from heapq import heappush, heappop

def build_pwl(table, col):
    pts = sorted((r[0], r[col]) for r in table if r[col] > 0)
    xs = [p[0] for p in pts]; ys = [p[1] for p in pts]
    def f(x):
        if not xs: return 1.0
        if x <= xs[0]: return ys[0]
        if x >= xs[-1]: return ys[-1]
        i = min(bisect.bisect_right(xs, x) - 1, len(xs) - 2)
        t = (x - xs[i]) / (xs[i+1] - xs[i])
        return ys[i] + t * (ys[i+1] - ys[i])
    return f

class Sim:
    def __init__(self, cfg, trace=False):
        self.c = cfg; self.trace = trace
        self.K = cfg["K"]; self.S = cfg["S"]; self.lat = cfg["latency"]
        self.bw = cfg["bw"]; self.bpt = cfg["bpt"]; self.NL = cfg["layers"]
        self.tbl = cfg["table"]
        self.f_ppre = build_pwl(self.tbl, 1); self.f_pproc = build_pwl(self.tbl, 2)
        self.f_ppost = build_pwl(self.tbl, 3); self.f_dpre = build_pwl(self.tbl, 4)
        self.f_dproc = build_pwl(self.tbl, 5); self.f_dpost = build_pwl(self.tbl, 6)
        self.reqs = cfg["requests"]
        self.R = len(self.reqs)
        self.st = [0]*self.R
        self.rem = [-1]*self.R
        self.arr = [a for a, _, _ in self.reqs]
        self.Lin = [l for _, l, _ in self.reqs]
        self.Lout = [o for _, _, o in self.reqs]
        self.post_t = [-1.0]*self.R
        self.done = [0]*self.R
        self.tdr = [-1.0]*self.R
        self.token_times = [[] for _ in range(self.R)]
        self.pidx = [0]*self.R
        self.e_busy = False
        self.r_busy = [False]*self.K
        self.pq = []; self.seq = 0
        # 传输队列: FIFO of items; 首项有完成事件在堆中
        self.upq = deque()   # (kind, rid, members, enqueued_t)
        self.dnq = deque()   # (kind, rid, members, remote, enqueued_t)
        self.up_active_until = None  # 首项传输完成时间 (已入堆)
        self.dn_active_until = None
        self.now = 0.0
        self.err = None
        # 资源利用率统计
        self.busy_E = 0.0
        self.busy_R = [0.0]*self.K
        self.busy_up = 0.0
        self.busy_dn = 0.0

    def xfer(self, n): return self.lat + 8.0 * self.bpt * n / (self.bw * 1e6)

    def enq_up(self, t, kind, rid, members):
        self.upq.append((kind, rid, members, t))
        if len(self.upq) == 1:
            n = self.Lin[rid] if kind == 'PRE' else len(members)
            done = t + self.xfer(n)
            heappush(self.pq, (done, self.seq, ('XUP', kind, rid, members))); self.seq += 1

    def deq_up(self):
        kind, rid, members, t0 = self.upq.popleft()
        done = self.now
        self.busy_up += self.xfer(self.Lin[rid] if kind == 'PRE' else len(members))
        if self.upq:
            k2, r2, m2, t2 = self.upq[0]
            n2 = self.Lin[r2] if k2 == 'PRE' else len(m2)
            d2 = done + self.xfer(n2)
            heappush(self.pq, (d2, self.seq, ('XUP', k2, r2, m2))); self.seq += 1

    def enq_dn(self, t, kind, rid, members, remote):
        self.dnq.append((kind, rid, members, remote, t))
        if len(self.dnq) == 1:
            n = self.Lin[rid] if kind == 'PRE' else len(members)
            done = t + self.xfer(n)
            heappush(self.pq, (done, self.seq, ('XDN', kind, rid, members, remote))); self.seq += 1

    def deq_dn(self):
        k0, r0, m0, rem0, t0 = self.dnq.popleft()
        done = self.now
        self.busy_dn += self.xfer(self.Lin[r0] if k0 == 'PRE' else len(m0))
        if self.dnq:
            k2, r2, m2, rem2, t2 = self.dnq[0]
            n2 = self.Lin[r2] if k2 == 'PRE' else len(m2)
            d2 = done + self.xfer(n2)
            heappush(self.pq, (d2, self.seq, ('XDN', k2, r2, m2, rem2))); self.seq += 1

    def start_task(self, t, server, spec, dur):
        if server == 'E':
            self.busy_E += self.S + dur
        else:
            self.busy_R[int(server[1:])] += self.S + dur
        heappush(self.pq, (t + self.S + dur, self.seq, ('TDN', server, spec, dur)))
        self.seq += 1

    def fmt_ev(self, p):
        k = p[0]
        if k == 'ARR': return f"ARR {p[1]} {self.Lin[p[1]]}"
        if k == 'TDN':
            _, server, spec, dur = p
            return f"TDN {server} {spec} {dur:.9f}"
        if k == 'XUP':
            _, kind, rid, members = p
            if kind == 'PRE':
                return f"XDN UP {self.rem[rid]} {self.Lin[rid]*self.bpt} PRE 1 {rid}"
            r = self.rem[members[0]]
            return f"XDN UP {r} {len(members)*self.bpt} DEC {len(members)} " + " ".join(map(str, members))
        if k == 'XDN':
            _, kind, rid, members, remote = p
            if kind == 'PRE':
                return f"XDN DOWN {remote} {self.Lin[rid]*self.bpt} PRE 1 {rid}"
            return f"XDN DOWN {remote} {len(members)*self.bpt} DEC {len(members)} " + " ".join(map(str, members))
        raise ValueError(k)

    def apply_side(self, p, fins):
        k = p[0]; t = self.now
        if k == 'ARR':
            self.st[p[1]] = 1
        elif k == 'XUP':
            _, kind, rid, members = p
            self.deq_up()
            if kind == 'PRE':
                self.st[rid] = 11
            else:
                for r in members: self.st[r] = 41
        elif k == 'XDN':
            _, kind, rid, members, remote = p
            self.deq_dn()
            if kind == 'PRE':
                self.st[rid] = 21
            else:
                for r in members:
                    self.st[r] = 31
                    self.post_t[r] = t
        elif k == 'TDN':
            _, server, spec, dur = p
            toks = spec.split()
            if server == 'E':
                self.e_busy = False
                if toks[0] == 'P' and toks[1] == 'PRE':
                    rid = int(toks[3])
                    self.enq_up(t, 'PRE', rid, None)
                elif toks[0] == 'P' and toks[1] == 'POST':
                    rid = int(toks[3])
                    self.st[rid] = 30
                    self.post_t[rid] = t
                    self.tdr[rid] = t - self.arr[rid]
                elif toks[0] == 'D' and toks[1] == 'PRE':
                    m = int(toks[3]); g = [int(x) for x in toks[4:4+m]]
                    byr = {}
                    for r in g: byr.setdefault(self.rem[r], []).append(r)
                    for remote in sorted(byr):
                        self.enq_up(t, 'DEC', None, byr[remote])
                    for r in g: self.st[r] = 40
                else:
                    m = int(toks[3]); g = [int(x) for x in toks[4:4+m]]
                    for r in g:
                        self.done[r] += 1
                        self.token_times[r].append(t)
                        if self.done[r] >= self.Lout[r]:
                            self.st[r] = 99
                            fins.append(r)
                        else:
                            self.st[r] = 30; self.post_t[r] = t
            else:
                kk = int(server[1:])
                self.r_busy[kk] = False
                if toks[0] == 'P':
                    ls, le = int(toks[2]), int(toks[3]); rid = int(toks[5])
                    if le == self.NL:
                        self.enq_dn(t, 'PRE', rid, None, kk)
                        self.st[rid] = 20
                    else:
                        self.st[rid] = 11
                else:
                    # D PROC <remote> <m> <rid...>
                    m = int(toks[3]); g = [int(x) for x in toks[4:4+m]]
                    self.enq_dn(t, 'DEC', None, g, kk)
                    for r in g: self.st[r] = 50

    def run(self, proc):
        c = self.c
        def send(s):
            proc.stdin.write(s + "\n"); proc.stdin.flush()
            if self.trace: print(">>>", s)
        def recv():
            line = proc.stdout.readline()
            if not line: raise EOFError
            if self.trace: print("<<<", line.rstrip())
            return line.rstrip("\n")
        try:
            send(f'{self.K} {self.S:.9f} {self.lat:.9f} {self.bw:.9f} {self.bpt} {self.NL}')
            send(f'{c["SLO1"]:.9f} {c["SLO2"]:.9f} {c["tpUB"]:.9f} {c["tpBase"]:.9f} {c["distBase"]:.9f} {c["wtp"]:.9f} {c["wc"]:.9f}')
            send(str(len(self.tbl)))
            for r in self.tbl:
                send(" ".join([str(int(r[0]))] + [f"{v:.9f}" for v in r[1:]]))
        except (BrokenPipeError, OSError):
            self.err = "solution closed input pipe"
            return self.compute_score()
        for i, (a, l, o) in enumerate(self.reqs):
            heappush(self.pq, (a, self.seq, ('ARR', i))); self.seq += 1
        frames = 0
        while True:
            if not self.pq:
                self.err = "stuck: no future events"; break
            t = self.pq[0][0]
            self.now = t
            evs = []
            while self.pq and self.pq[0][0] == t:   # 官方: 仅内部时间戳严格相同的事件并帧
                _, _, p = heappop(self.pq); evs.append(p)
            fins = []
            for p in evs: self.apply_side(p, fins)
            lines = [f"{t:.9f}", str(len(evs) + len(fins))]
            for p in evs: lines.append(self.fmt_ev(p))
            for r in fins: lines.append(f"FIN {r}")
            try:
                for l in lines: send(l)
            except (BrokenPipeError, OSError):
                self.err = "solution closed input pipe"; break
            try:
                resp = recv()
            except EOFError:
                self.err = "solution closed output"; break
            try:
                n = int(resp.split()[0])
            except Exception:
                self.err = f"bad count: {resp!r}"; break
            if not (0 <= n <= self.K + 1):   # 官方: 每帧 0 <= n <= K+1
                self.err = f"assignment count {n} out of range [0, {self.K + 1}]"; break
            assigns = []
            try:
                for _ in range(n): assigns.append(recv())
            except EOFError:
                self.err = "solution closed output mid-response"; break
            if not self.apply_tasks(t, assigns): break
            frames += 1
            if frames > 2_000_000: self.err = "frame limit"; break
            if all(self.st[i] == 99 for i in range(self.R)):
                try: send("END")
                except (BrokenPipeError, OSError): pass
                try: proc.wait(timeout=5)
                except Exception: pass
                break
        return self.compute_score()

    def apply_tasks(self, t, assigns):
        used = set()
        for line in assigns:
            toks = line.split()
            if len(toks) < 2: self.err = f"bad assign {line!r}"; return False
            server = toks[0]
            if server in used: self.err = "double assign"; return False
            if server == 'E':
                if self.e_busy: self.err = "E busy"; return False
                step = toks[1] + " " + toks[2]
                if step == "P PRE":
                    remote, rid = int(toks[3]), int(toks[4])
                    if not (0 <= remote < self.K): self.err = "P PRE remote range"; return False
                    if self.st[rid] != 1: self.err = f"P PRE st={self.st[rid]}"; return False
                    self.rem[rid] = remote; self.st[rid] = 10
                    self.start_task(t, 'E', f"P PRE {remote} {rid}", self.f_ppre(self.Lin[rid]))
                elif step == "P POST":
                    remote, rid = int(toks[3]), int(toks[4])
                    if self.st[rid] != 21:
                        self.err = f"P POST st={self.st[rid]}"; return False
                    self.start_task(t, 'E', f"P POST {remote} {rid}", self.f_ppost(self.Lin[rid]))
                elif step == "D PRE":
                    m1 = int(toks[3]); m = int(toks[4]); g = [int(x) for x in toks[5:5+m]]
                    if len(set(g)) != m or m < 1: self.err = "D PRE dup"; return False
                    for r in g:
                        if self.st[r] != 30: self.err = f"D PRE st={self.st[r]}"; return False
                    self.start_task(t, 'E', f"D PRE -1 {m} " + " ".join(map(str, g)), self.f_dpre(m))
                elif step == "D POST":
                    m1 = int(toks[3]); m = int(toks[4]); g = [int(x) for x in toks[5:5+m]]
                    if len(set(g)) != m or m < 1: self.err = "D POST dup"; return False
                    for r in g:
                        if self.st[r] != 31: self.err = f"D POST st={self.st[r]}"; return False
                    self.start_task(t, 'E', f"D POST -1 {m} " + " ".join(map(str, g)), self.f_dpost(m))
                else:
                    self.err = f"E step {step}"; return False
                self.e_busy = True; used.add('E')
            elif server.startswith('C'):
                kk = int(server[1:])
                if not (0 <= kk < self.K): self.err = "server range"; return False
                if self.r_busy[kk]: self.err = "R busy"; return False
                if toks[1] == 'P':
                    ls, le, remote, rid = int(toks[3]), int(toks[4]), int(toks[5]), int(toks[6])
                    if remote != kk: self.err = "P PROC remote field"; return False
                    if self.st[rid] != 11 and self.st[rid] != 12: self.err = f"P PROC st={self.st[rid]}"; return False
                    if self.rem[rid] != kk: self.err = "P PROC remote"; return False
                    if not (0 <= ls < le <= self.NL): self.err = "piece range"; return False
                    if ls != self.pidx[rid]: self.err = f"piece gap ls={ls} expect {self.pidx[rid]}"; return False
                    self.pidx[rid] = le
                    dur = self.f_pproc(self.Lin[rid]) * (le - ls) / self.NL
                    self.start_task(t, server, f"P PROC {ls} {le} {remote} {rid}", dur)
                    self.st[rid] = 12
                else:
                    remote, m = int(toks[3]), int(toks[4])
                    g = [int(x) for x in toks[5:5+m]]
                    if remote != kk: self.err = "D PROC remote"; return False
                    if len(set(g)) != m or m < 1: self.err = "D PROC dup"; return False
                    for r in g:
                        if self.st[r] != 41: self.err = f"D PROC st={self.st[r]}"; return False
                        if self.rem[r] != kk: self.err = "D PROC member remote"; return False
                    self.start_task(t, server, f"D PROC {remote} {m} " + " ".join(map(str, g)), self.f_dproc(m))
                self.r_busy[kk] = True; used.add(server)
            else:
                self.err = f"bad server {server}"; return False
        return True

    def compute_score(self):
        if self.err: return {"error": self.err, "score": 0}
        c = self.c
        tot = sum(self.Lout)
        t0 = min(self.arr); t1 = max(max(self.token_times[i]) for i in range(self.R))
        tp = tot / (t1 - t0) if t1 > t0 else 0
        tdr = sum(self.tdr) / self.R
        gaps = []
        for i in range(self.R):
            tt = self.token_times[i]
            for j in range(1, len(tt)): gaps.append(tt[j] - tt[j-1])
        tpot = sum(gaps)/len(gaps) if gaps else 0.0
        et = max(0.0, (tdr - c["SLO1"])/c["SLO1"])
        ep = max(0.0, (tpot - c["SLO2"])/c["SLO2"])
        dist = math.sqrt(et*et + ep*ep)
        tp_c = max(0.0, min(1.0, (tp - c["tpBase"])/(c["tpUB"] - c["tpBase"]))) if c["tpUB"] > c["tpBase"] else 0
        wc_c = max(0.0, 1.0 - dist/c["distBase"]) if c["distBase"] > 0 else (1.0 if dist == 0 else 0.0)
        normalized = c["wtp"]*tp_c + c["wc"]*wc_c   # CF: normalized_score
        score = 1000 * normalized                     # CF: points
        elapsed = t1 - t0
        tdr_sorted = sorted(self.tdr)
        return {"points": round(score, 6),           # CF 官方 per-test points
                "score": round(score, 3),
                "normalized_score": round(normalized, 6),
                "norm_tp": round(tp_c, 6),            # CF: norm_tp
                "norm_c": round(wc_c, 6),             # CF: norm_c
                "tp": round(tp, 6), "mean_tdr": round(tdr, 6), "mean_tpot": round(tpot, 6),
                "dist": round(dist, 6),
                "tdr_max": round(tdr_sorted[-1], 1),
                "tdr_p90": round(tdr_sorted[int(len(tdr_sorted)*0.9)], 1),
                "tp_comp": round(tp_c, 4), "wc_comp": round(wc_c, 4), "elapsed": round(elapsed, 1),
                "util_E": round(self.busy_E / elapsed, 3) if elapsed > 0 else 0,
                "util_up": round(self.busy_up / elapsed, 3) if elapsed > 0 else 0,
                "util_dn": round(self.busy_dn / elapsed, 3) if elapsed > 0 else 0,
                "util_R": [round(b / elapsed, 3) for b in self.busy_R] if elapsed > 0 else []}

def main():
    import resource
    cfg = json.load(open(sys.argv[1]))
    trace = "--trace" in sys.argv
    sim = Sim(cfg, trace)
    tle = int(os.environ.get("BENCH_TIME_LIMIT", "15"))     # CF: 15s CPU
    mem_mb = int(os.environ.get("BENCH_MEM_LIMIT", "256"))  # CF: 256MB (峰值实际内存口径)
    # CF 测的是峰值 working set, 不是虚拟地址空间: Go/Java 等运行时启动即保留大量
    # 虚拟内存 (Go: failed to reserve page summary memory), RLIMIT_AS=256MB 会直接
    # 杀死它们。虚拟上限只留兜底防失控, 256MB 判定改为事后读子进程峰值 RSS。
    vas = int(os.environ.get("BENCH_VAS_BACKSTOP", "4096")) * 1024 * 1024
    def limits():
        resource.setrlimit(resource.RLIMIT_CPU, (tle, tle + 1))
        resource.setrlimit(resource.RLIMIT_AS, (vas, vas))
    proc = subprocess.Popen(sys.argv[2:], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                            text=True, bufsize=1, preexec_fn=limits)
    res = sim.run(proc)
    rc = proc.poll()
    try:
        if rc is None:
            proc.kill()
        proc.wait()          # 先回收, ru_maxrss 才包含该子进程
    except Exception:
        pass
    if rc is not None and rc in (-24, -9):      # SIGXCPU / SIGKILL (CPU 超限)
        res = {"error": "time limit exceeded (CPU)", "points": 0.0}
    elif rc == -11:
        res = {"error": "segmentation fault", "points": 0.0}
    elif "error" not in res:
        peak_mb = resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss / 1024
        if peak_mb > mem_mb:
            res = {"error": f"memory limit exceeded (peak RSS {peak_mb:.0f}MB > {mem_mb}MB)",
                   "points": 0.0}
    print(json.dumps(res, indent=2))

if __name__ == "__main__":
    main()
