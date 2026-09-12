import sys


class Scheduler:
    def __init__(self, k, layers):
        self.k = k
        self.layers = layers
        self.local_task = None
        self.remote_task = [None] * k
        self.req = {}
        self.phase_sets = {name: set() for name in (
            "arrived", "post_ready", "decode_ready", "dpost_ready",
            "proc_ready", "dproc_ready")}
        self.next_remote = 0

    def add_request(self, rid, lin):
        self.req[rid] = {
            "lin": lin,
            "remote": None,
            "phase": "arrived",
            "iter": 0,
        }
        self.phase_sets["arrived"].add(rid)

    def set_phase(self, rid, phase):
        r = self.req.get(rid)
        if r is None:
            return
        old = r["phase"]
        if old in self.phase_sets:
            self.phase_sets[old].discard(rid)
        r["phase"] = phase
        if phase in self.phase_sets:
            self.phase_sets[phase].add(rid)

    def handle_xdn(self, parts):
        # XDN UP|DOWN remote size PRE|DEC m rid...
        if len(parts) < 7:
            return
        direction, kind = parts[1], parts[4]
        m = int(parts[5])
        ids = [int(x) for x in parts[6:6 + m]]
        if kind == "PRE":
            target = "proc_ready" if direction == "UP" else "post_ready"
            for rid in ids:
                r = self.req.get(rid)
                if r is not None and r["phase"] not in ("finished", "post_ready", "decode_ready"):
                    self.set_phase(rid, target)
        else:
            target = "dproc_ready" if direction == "UP" else "dpost_ready"
            for rid in ids:
                r = self.req.get(rid)
                if r is not None and r["phase"] != "finished":
                    self.set_phase(rid, target)

    def handle_frame(self, events):
        pending_dpost = []
        for parts in events:
            if not parts:
                continue
            typ = parts[0]
            if typ == "ARR":
                self.add_request(int(parts[1]), int(parts[2]))
            elif typ == "XDN":
                self.handle_xdn(parts)
            elif typ == "FIN":
                rid = int(parts[1])
                if rid in self.req:
                    self.set_phase(rid, "finished")
            elif typ == "TDN":
                server = parts[1]
                task = self.local_task if server == "E" else self.remote_task[int(server[1:])]
                if server == "E":
                    self.local_task = None
                else:
                    self.remote_task[int(server[1:])] = None
                if task is None:
                    continue
                kind = task["kind"]
                if kind == "PPOST":
                    for rid in task["ids"]:
                        r = self.req.get(rid)
                        if r is not None and r["phase"] != "finished":
                            self.set_phase(rid, "decode_ready")
                elif kind == "DPOST":
                    pending_dpost.extend(task["ids"])

        for rid in pending_dpost:
            r = self.req.get(rid)
            if r is not None and r["phase"] != "finished":
                r["iter"] += 1
                self.set_phase(rid, "decode_ready")

        assignments = []

        # One local task per response.  Prioritize completing already transferred data,
        # then advance output, and finally start newly arrived requests.
        if self.local_task is None:
            chosen = None
            if self.phase_sets["post_ready"]:
                chosen = [next(iter(self.phase_sets["post_ready"]))]
            if chosen is not None:
                rid = chosen[0]
                r = self.req[rid]
                self.local_task = {"kind": "PPOST", "ids": chosen}
                self.set_phase(rid, "post_assigned")
                assignments.append(("E", f"P POST {r['remote']} {rid}"))
            else:
                dpost = list(self.phase_sets["dpost_ready"])
                if dpost:
                    self.local_task = {"kind": "DPOST", "ids": dpost}
                    for rid in dpost:
                        self.set_phase(rid, "dpost_assigned")
                    text = "D POST -1 {} {}".format(len(dpost), " ".join(map(str, dpost)))
                    assignments.append(("E", text))
                else:
                    dpre = list(self.phase_sets["decode_ready"])
                    if dpre:
                        self.local_task = {"kind": "DPRE", "ids": dpre}
                        for rid in dpre:
                            self.set_phase(rid, "dpre_assigned")
                        text = "D PRE -1 {} {}".format(len(dpre), " ".join(map(str, dpre)))
                        assignments.append(("E", text))
                    else:
                        arrived = list(self.phase_sets["arrived"])
                        if arrived:
                            rid = arrived[0]
                            remote = self.next_remote % self.k
                            self.next_remote += 1
                            self.req[rid]["remote"] = remote
                            self.set_phase(rid, "pre_assigned")
                            self.local_task = {"kind": "PPRE", "ids": [rid]}
                            assignments.append(("E", f"P PRE {remote} {rid}"))

        # Schedule at most one task on each free remote computer.
        for remote in range(self.k):
            if self.remote_task[remote] is not None:
                continue
            inp = [rid for rid in self.phase_sets["proc_ready"]
                   if self.req[rid]["remote"] == remote]
            if inp:
                rid = inp[0]
                self.set_phase(rid, "proc_assigned")
                self.remote_task[remote] = {"kind": "PPROC", "ids": [rid]}
                assignments.append((f"C{remote}", f"P PROC 0 {self.layers} {remote} {rid}"))
                continue
            dec = [rid for rid in self.phase_sets["dproc_ready"]
                   if self.req[rid]["remote"] == remote]
            if dec:
                self.remote_task[remote] = {"kind": "DPROC", "ids": dec}
                for rid in dec:
                    self.set_phase(rid, "dproc_assigned")
                text = "D PROC {} {} {}".format(remote, len(dec), " ".join(map(str, dec)))
                assignments.append((f"C{remote}", text))

        return assignments


def main():
    inp = sys.stdin.buffer
    line = inp.readline()
    if not line:
        return
    first = line.decode().strip().split()
    if len(first) < 6:
        return
    k = int(first[0])
    layers = int(first[5])
    if not inp.readline():
        return
    nline = inp.readline()
    if not nline:
        return
    n = int(nline.decode().strip().split()[0])
    for _ in range(n):
        if not inp.readline():
            return

    sched = Scheduler(k, layers)
    out = sys.stdout
    while True:
        line = inp.readline()
        if not line:
            return
        head = line.decode().strip()
        if head == "END":
            return
        if not head:
            continue
        count_line = inp.readline()
        if not count_line:
            return
        try:
            e = int(count_line.decode().strip().split()[0])
        except Exception:
            return
        events = []
        for _ in range(e):
            ev = inp.readline()
            if not ev:
                return
            events.append(ev.decode().strip().split())
        assignments = sched.handle_frame(events)
        out.write(str(len(assignments)) + "\n")
        for server, text in assignments:
            out.write(server + " " + text + "\n")
        out.flush()


if __name__ == "__main__":
    main()
