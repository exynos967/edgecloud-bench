// Edge-Cloud collaborative scheduling -- interactive scheduler.
//
// Protocol: two startup config lines, then the task-time table (N rows), then
// repeated event frames.  Every frame is read completely before responding;
// the response (assignment count followed by that many assignments) is flushed
// immediately.
//
// Policy
//   - The local computer always prefers input-stage work: P POST, then P PRE,
//     then D PRE (which feeds the remotes), then D POST (which drains them).
//     The input stage is a hard prerequisite for every token and carries the
//     TDR target, so serving it first costs little and pays off broadly.
//   - A remote always prefers P PROC over D PROC, for the same reason.
//   - Output groups are unbounded by the protocol, so a group takes every
//     request that is ready -- capped only by the task-time table, which can
//     say that a smaller batch is more efficient per token.
//   - No resource is ever left idle while a legal task exists, so the run can
//     never reach the stuck state.
package main

import (
	"bufio"
	"os"
	"sort"
	"strconv"
)

const (
	stNotArr  = -1
	stArr     = 0
	stPpreRun = 1
	stPreUp   = 2
	stPprocOk = 3
	stPprocRn = 4
	stPreDown = 5
	stPpostOk = 6
	stPpostRn = 7
	stDpreOk  = 8
	stDpreRun = 9
	stDecUp   = 10
	stDprocOk = 11
	stDprocRn = 12
	stDecDown = 13
	stDpostOk = 14
	stDpostRn = 15
	stFin     = 16
)

// ---------------- fast input ----------------
type FastIn struct {
	r   *bufio.Reader
	buf []byte
	tok []byte
	pos int
	n   int
}

func NewFastIn() *FastIn {
	return &FastIn{r: bufio.NewReaderSize(os.Stdin, 1<<16), buf: make([]byte, 1<<16)}
}

func (f *FastIn) fill() bool {
	if f.pos < f.n {
		return true
	}
	n, err := f.r.Read(f.buf)
	f.n, f.pos = n, 0
	return n > 0 && err == nil
}

func (f *FastIn) skipSpace() bool {
	for {
		if f.pos >= f.n {
			if !f.fill() {
				return false
			}
			continue
		}
		if f.buf[f.pos] <= ' ' {
			f.pos++
			continue
		}
		return true
	}
}

// Next returns the next whitespace-delimited token, or nil at EOF.  The slice
// aliases the read buffer, so callers must consume it before reading again --
// a refill would overwrite it.
func (f *FastIn) Next() []byte {
	if !f.skipSpace() {
		return nil
	}
	start := f.pos
	for f.pos < f.n && f.buf[f.pos] > ' ' {
		f.pos++
	}
	if f.pos < f.n {
		return f.buf[start:f.pos]
	}
	f.tok = append(f.tok[:0], f.buf[start:f.pos]...)
	for {
		if !f.fill() {
			break
		}
		p := f.pos
		for f.pos < f.n && f.buf[f.pos] > ' ' {
			f.pos++
		}
		f.tok = append(f.tok, f.buf[p:f.pos]...)
		if f.pos < f.n {
			break
		}
	}
	return f.tok
}

// Int parses the next integer, skipping any leading whitespace.
func (f *FastIn) Int() int {
	if !f.skipSpace() {
		return 0
	}
	neg := false
	if f.buf[f.pos] == '-' || f.buf[f.pos] == '+' {
		neg = f.buf[f.pos] == '-'
		f.pos++
	}
	v := 0
	for {
		for f.pos < f.n && f.buf[f.pos] >= '0' && f.buf[f.pos] <= '9' {
			v = v*10 + int(f.buf[f.pos]-'0')
			f.pos++
		}
		if f.pos < f.n {
			break
		}
		if !f.fill() {
			break
		}
	}
	if neg {
		return -v
	}
	return v
}

// Float parses the next real.  Only the startup table uses it, not the hot loop.
func (f *FastIn) Float() float64 {
	t := f.Next()
	if t == nil {
		return 0
	}
	v, _ := strconv.ParseFloat(string(t), 64)
	return v
}

func atoi(b []byte) int {
	v := 0
	for i := 0; i < len(b); i++ {
		if b[i] < '0' || b[i] > '9' {
			break
		}
		v = v*10 + int(b[i]-'0')
	}
	return v
}

// ---------------- ready queues ----------------
// Requests enter a class in nondecreasing readiness order, so the queue front
// is always the request that has been waiting longest.
type Queue struct {
	items []int
	ticks []int
	head  int
}

func (q *Queue) Push(rid, tick int) {
	q.items = append(q.items, rid)
	q.ticks = append(q.ticks, tick)
}

func (q *Queue) Empty() bool { return q.head >= len(q.items) }

// TakeFirst removes and returns up to n of the longest-waiting entries.
func (q *Queue) TakeFirst(n int, dst []int) []int {
	avail := len(q.items) - q.head
	if n > avail {
		n = avail
	}
	if n <= 0 {
		return dst[:0]
	}
	end := q.head + n
	dst = append(dst[:0], q.items[q.head:end]...)
	q.head = end
	if q.head > 1024 && q.head*2 >= len(q.items) {
		q.items = append(q.items[:0], q.items[q.head:]...)
		q.ticks = append(q.ticks[:0], q.ticks[q.head:]...)
		q.head = 0
	}
	return dst
}

// Remove drops rid from the queue.  Needed only when a request's final D POST
// and its FIN arrive in the same frame, which can strand a D-PRE queue entry.
func (q *Queue) Remove(rid int) {
	for i := q.head; i < len(q.items); i++ {
		if q.items[i] == rid {
			copy(q.items[i:], q.items[i+1:])
			copy(q.ticks[i:], q.ticks[i+1:])
			q.items = q.items[:len(q.items)-1]
			q.ticks = q.ticks[:len(q.ticks)-1]
			return
		}
	}
}

// ---------------- scheduler state ----------------
var (
	kRemote   int
	numLayers int

	// task-time table columns, sorted by batch size:
	// 0 prefill_pre 1 prefill_proc 2 prefill_post
	// 3 decode_pre  4 decode_proc   5 decode_post
	tkey [6][]float64
	tval [6][]float64

	st     []int
	remv   []int
	nextLs []int

	q0  Queue // arrived, waiting for P PRE
	q6  Queue // waiting for P POST
	q8  Queue // ready for the next D PRE
	q14 Queue // waiting for D POST
	q3  []Queue
	q11 []Queue

	load  []int
	efree = true
	busyC []bool

	out      []byte
	w        *bufio.Writer
	tick     int
	maxBatch int
)

func tcost(c int, x float64) float64 {
	kk := tkey[c]
	vv := tval[c]
	if len(kk) == 0 {
		return 0
	}
	if x <= kk[0] {
		return vv[0]
	}
	if x >= kk[len(kk)-1] {
		return vv[len(vv)-1]
	}
	i := sort.SearchFloat64s(kk, x)
	if i < len(kk) && kk[i] == x {
		return vv[i]
	}
	return vv[i-1] + (vv[i]-vv[i-1])*(x-kk[i-1])/(kk[i]-kk[i-1])
}

// pickMaxBatch sizes output groups from the task-time table.
//
// A group of m costs decode_pre(m)+decode_post(m) on the local computer and
// decode_proc(m) on one remote, so its token rate is bounded by
//
//	m / max(decode_pre(m)+decode_post(m), decode_proc(m)/K)
//
// and the group size maximising that bound is used.  For the flat or sublinear
// decode costs of the public examples this is simply "take everything ready";
// a table whose costs grow faster than linearly would otherwise be badly served
// by always batching everything.
func pickMaxBatch() int {
	best := 1
	bestRate := 0.0
	den := float64(kRemote)
	if den < 1 {
		den = 1
	}
	for m := 1; m <= 4096; m++ {
		fm := float64(m)
		d := tcost(3, fm) + tcost(5, fm)
		if c := tcost(4, fm) / den; c > d {
			d = c
		}
		if d <= 0 {
			continue
		}
		if rate := fm / d; rate >= bestRate {
			bestRate = rate
			best = m
		}
	}
	return best
}

func touch(rid int) {
	for len(st) <= rid {
		st = append(st, stNotArr)
		remv = append(remv, -1)
		nextLs = append(nextLs, 0)
	}
}

func setst(rid, ns int) {
	st[rid] = ns
	switch ns {
	case stArr:
		q0.Push(rid, tick)
	case stPpostOk:
		q6.Push(rid, tick)
	case stDpreOk:
		q8.Push(rid, tick)
	case stDpostOk:
		q14.Push(rid, tick)
	case stPprocOk:
		q3[remv[rid]].Push(rid, tick)
	case stDprocOk:
		q11[remv[rid]].Push(rid, tick)
	}
}

func appendInts(dst []byte, g []int) []byte {
	for _, rid := range g {
		dst = append(dst, ' ')
		dst = strconv.AppendInt(dst, int64(rid), 10)
	}
	return dst
}

func main() {
	in := NewFastIn()
	kRemote = in.Int()
	in.Float() // S, schedule cost -- transfers and ordering are what matter here
	in.Float() // latency
	in.Float() // bandwidth
	in.Int()   // bytes_per_token
	numLayers = in.Int()
	for i := 0; i < 7; i++ {
		in.Float() // SLO1 SLO2 tp_UB tp_base dist_base w_tp w_c
	}

	n := in.Int()
	type pt struct{ x, y float64 }
	cols := [6][]pt{}
	for i := 0; i < n; i++ {
		bs := in.Float()
		for j := 0; j < 6; j++ {
			v := in.Float()
			if v >= -0.5 { // -1 marks a missing entry
				cols[j] = append(cols[j], pt{bs, v})
			}
		}
	}
	for j := 0; j < 6; j++ {
		sort.Slice(cols[j], func(a, b int) bool { return cols[j][a].x < cols[j][b].x })
		for _, p := range cols[j] {
			tkey[j] = append(tkey[j], p.x)
			tval[j] = append(tval[j], p.y)
		}
	}
	maxBatch = pickMaxBatch()

	q3 = make([]Queue, kRemote)
	q11 = make([]Queue, kRemote)
	load = make([]int, kRemote)
	busyC = make([]bool, kRemote)
	out = make([]byte, 0, 1<<16)
	w = bufio.NewWriterSize(os.Stdout, 1<<16)

	fins := make([]int, 0, 64)
	var g []int

	for {
		tok := in.Next()
		if tok == nil || string(tok) == "END" {
			break
		}
		tick++
		e := in.Int()
		fins = fins[:0]
		for i := 0; i < e; i++ {
			ev := in.Next()
			switch ev[0] {
			case 'A': // ARR <rid> <L_in>
				rid := in.Int()
				in.Int() // L_in is not needed by this policy
				touch(rid)
				remv[rid] = -1
				setst(rid, stArr)
			case 'T': // TDN <server> <task_spec> <dur>
				srv := in.Next()
				if srv[0] == 'E' {
					efree = true
				} else {
					busyC[atoi(srv[1:])] = false
				}
				grp := in.Next()
				isP := grp[0] == 'P'
				sub := in.Next()
				isPre := string(sub) == "PRE"
				isProc := string(sub) == "PROC"
				isPost := !isPre && !isProc
				if isP {
					if isPre { // P PRE <remote> <rid>
						in.Int()
						rid := in.Int()
						in.Next() // dur
						setst(rid, stPreUp)
					} else if isProc { // P PROC <ls> <le> <remote> <rid>
						in.Int() // ls
						le := in.Int()
						in.Int() // remote
						rid := in.Int()
						in.Next() // dur
						if le == numLayers {
							setst(rid, stPreDown)
						} else {
							nextLs[rid] = le
							setst(rid, stPprocOk)
						}
					} else { // P POST <remote> <rid>
						in.Int()
						rid := in.Int()
						in.Next() // dur
						setst(rid, stDpreOk)
					}
				} else if isProc { // D PROC <remote> <m> <rid...>
					in.Int()
					m := in.Int()
					for j := 0; j < m; j++ {
						setst(in.Int(), stDecDown)
					}
					in.Next() // dur
				} else { // D PRE -1 <m> <rid...>  or  D POST -1 <m> <rid...>
					in.Int() // -1
					m := in.Int()
					ns := stDecUp
					if isPost {
						ns = stDpreOk
					}
					for j := 0; j < m; j++ {
						setst(in.Int(), ns)
					}
					in.Next() // dur
				}
			case 'X': // XDN <UP|DOWN> <remote> <size> <PRE|DEC> <m> <rid...>
				dir := in.Next()
				isUp := dir[0] == 'U'
				in.Int() // remote
				in.Int() // size
				kind := in.Next()
				isPre := kind[0] == 'P'
				m := in.Int()
				var ns int
				if isPre {
					if isUp {
						ns = stPprocOk
					} else {
						ns = stPpostOk
					}
				} else {
					if isUp {
						ns = stDprocOk
					} else {
						ns = stDpostOk
					}
				}
				for j := 0; j < m; j++ {
					setst(in.Int(), ns)
				}
			default: // FIN <rid>
				fins = append(fins, in.Int())
			}
		}
		for _, rid := range fins {
			if st[rid] == stDpreOk {
				q8.Remove(rid)
			}
			setst(rid, stFin)
			load[remv[rid]]--
		}

		out = out[:0]
		cnt := 0

		if efree {
			if !q6.Empty() { // P POST: completes TDR for a waiting request
				rid := q6.items[q6.head]
				out = append(out, "E P POST "...)
				out = strconv.AppendInt(out, int64(remv[rid]), 10)
				out = append(out, ' ')
				out = strconv.AppendInt(out, int64(rid), 10)
				out = append(out, '\n')
				q6.head++
				setst(rid, stPpostRn)
				cnt++
				efree = false
			} else if !q0.Empty() { // P PRE: starts a new request's input stage
				rid := q0.items[q0.head]
				best := 0
				for k := 1; k < kRemote; k++ {
					if load[k] < load[best] {
						best = k
					}
				}
				remv[rid] = best
				load[best]++
				out = append(out, "E P PRE "...)
				out = strconv.AppendInt(out, int64(best), 10)
				out = append(out, ' ')
				out = strconv.AppendInt(out, int64(rid), 10)
				out = append(out, '\n')
				q0.head++
				setst(rid, stPpreRun)
				cnt++
				efree = false
			} else if !q8.Empty() { // D PRE: feeds the remotes
				g = q8.TakeFirst(maxBatch, g)
				out = append(out, "E D PRE -1 "...)
				out = strconv.AppendInt(out, int64(len(g)), 10)
				out = appendInts(out, g)
				out = append(out, '\n')
				for _, rid := range g {
					setst(rid, stDpreRun)
				}
				cnt++
				efree = false
			} else if !q14.Empty() { // D POST: emits tokens
				g = q14.TakeFirst(maxBatch, g)
				out = append(out, "E D POST -1 "...)
				out = strconv.AppendInt(out, int64(len(g)), 10)
				out = appendInts(out, g)
				out = append(out, '\n')
				for _, rid := range g {
					setst(rid, stDpostRn)
				}
				cnt++
				efree = false
			}
		}

		for k := 0; k < kRemote; k++ {
			if busyC[k] {
				continue
			}
			if !q3[k].Empty() { // P PROC before D PROC: input stage first
				rid := q3[k].items[q3[k].head]
				out = append(out, 'C')
				out = strconv.AppendInt(out, int64(k), 10)
				out = append(out, " P PROC 0 "...)
				out = strconv.AppendInt(out, int64(numLayers), 10)
				out = append(out, ' ')
				out = strconv.AppendInt(out, int64(k), 10)
				out = append(out, ' ')
				out = strconv.AppendInt(out, int64(rid), 10)
				out = append(out, '\n')
				q3[k].head++
				setst(rid, stPprocRn)
				cnt++
				busyC[k] = true
			} else if !q11[k].Empty() {
				g = q11[k].TakeFirst(maxBatch, g)
				out = append(out, 'C')
				out = strconv.AppendInt(out, int64(k), 10)
				out = append(out, " D PROC "...)
				out = strconv.AppendInt(out, int64(k), 10)
				out = append(out, ' ')
				out = strconv.AppendInt(out, int64(len(g)), 10)
				out = appendInts(out, g)
				out = append(out, '\n')
				for _, rid := range g {
					setst(rid, stDprocRn)
				}
				cnt++
				busyC[k] = true
			}
		}

		w.WriteString(strconv.Itoa(cnt))
		w.WriteByte('\n')
		w.Write(out)
		w.Flush()
	}
}
