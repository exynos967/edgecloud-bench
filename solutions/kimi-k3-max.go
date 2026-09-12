package main

import (
	"os"
	"sort"
	"strconv"
)

// ---------- fast input ----------
type FastReader struct {
	buf []byte
	pos int
	n   int
}

func NewFastReader() *FastReader { return &FastReader{buf: make([]byte, 1<<16)} }

func (r *FastReader) readByte() int {
	if r.pos >= r.n {
		n, _ := os.Stdin.Read(r.buf)
		if n <= 0 {
			return -1
		}
		r.n = n
		r.pos = 0
	}
	b := r.buf[r.pos]
	r.pos++
	return int(b)
}

var tokBuf [128]byte

func (r *FastReader) token() []byte {
	c := r.readByte()
	for c == ' ' || c == '\n' || c == '\r' || c == '\t' {
		c = r.readByte()
	}
	if c < 0 {
		return nil
	}
	i := 0
	for c >= 0 && c != ' ' && c != '\n' && c != '\r' && c != '\t' {
		tokBuf[i] = byte(c)
		i++
		c = r.readByte()
	}
	return tokBuf[:i]
}

func atoi(b []byte) int64 {
	var x int64
	i := 0
	neg := false
	if b[0] == '-' {
		neg = true
		i = 1
	} else if b[0] == '+' {
		i = 1
	}
	for ; i < len(b); i++ {
		x = x*10 + int64(b[i]-'0')
	}
	if neg {
		return -x
	}
	return x
}

func atof(b []byte) float64 {
	i := 0
	neg := false
	if b[0] == '-' {
		neg = true
		i = 1
	} else if b[0] == '+' {
		i = 1
	}
	var x float64
	for ; i < len(b) && b[i] != '.'; i++ {
		if b[i] < '0' || b[i] > '9' { // exponent or other notation: fall back
			v, _ := strconv.ParseFloat(string(b), 64)
			return v
		}
		x = x*10 + float64(b[i]-'0')
	}
	if i < len(b) && b[i] == '.' {
		i++
		base := 1.0
		for ; i < len(b); i++ {
			if b[i] < '0' || b[i] > '9' {
				v, _ := strconv.ParseFloat(string(b), 64)
				return v
			}
			x = x*10 + float64(b[i]-'0')
			base *= 10
		}
		x /= base
	}
	if neg {
		return -x
	}
	return x
}

// ---------- table ----------
type trow struct {
	size int
	val  float64
}

var tab [6][]trow

func lookup(col int, size int64) float64 {
	v := tab[col]
	if size <= int64(v[0].size) {
		return v[0].val
	}
	if size >= int64(v[len(v)-1].size) {
		return v[len(v)-1].val
	}
	i := sort.Search(len(v), func(i int) bool { return int64(v[i].size) >= size })
	if int64(v[i].size) == size {
		return v[i].val
	}
	x0 := float64(v[i-1].size)
	y0 := v[i-1].val
	x1 := float64(v[i].size)
	y1 := v[i].val
	return y0 + (y1-y0)*(float64(size)-x0)/(x1-x0)
}

// ---------- state ----------
const (
	stArrived  = 0
	stPprocRdy = 1
	stPpostRdy = 2
	stDecRdy   = 3
	stDprocRdy = 4
	stDpostRdy = 5
	stInflight = 6
	stDone     = 7
)

type ritem struct {
	rid int
	ts  float64
}

var (
	K, LAY     int
	BPT        int64
	S, LAT, BW float64

	rstate  []int8
	rremote []int
	rlin    []int64

	arrQ    []int
	arrHead int

	ppostH []int // min-heap of rid

	decR   map[int]struct{}
	dpostR map[int]struct{}

	pprocQ []Queue // per remote, FIFO by ready time
	dprocQ []Queue

	eBusy       bool
	rBusy       []bool
	rBusyUntil  []float64
	pendPrefill []float64
	inflightUP  []int64
	inflightDec int64 // requests with D PRE issued but D POST not yet done
)

type Queue struct {
	items []ritem
	head  int
}

func (q *Queue) push(it ritem) { q.items = append(q.items, it) }
func (q *Queue) empty() bool   { return q.head >= len(q.items) }
func (q *Queue) front() ritem  { return q.items[q.head] }
func (q *Queue) pop()          { q.head++ }
func (q *Queue) takeAll() []ritem {
	r := q.items[q.head:]
	q.items = q.items[:0]
	q.head = 0
	return r
}

// min-heap for ppostH
func heapPush(h *[]int, x int) {
	*h = append(*h, x)
	i := len(*h) - 1
	for i > 0 {
		p := (i - 1) / 2
		if (*h)[p] <= (*h)[i] {
			break
		}
		(*h)[p], (*h)[i] = (*h)[i], (*h)[p]
		i = p
	}
}
func heapPop(h *[]int) int {
	top := (*h)[0]
	last := (*h)[len(*h)-1]
	*h = (*h)[:len(*h)-1]
	if len(*h) > 0 {
		(*h)[0] = last
		i := 0
		for {
			l, r := 2*i+1, 2*i+2
			m := i
			if l < len(*h) && (*h)[l] < (*h)[m] {
				m = l
			}
			if r < len(*h) && (*h)[r] < (*h)[m] {
				m = r
			}
			if m == i {
				break
			}
			(*h)[m], (*h)[i] = (*h)[i], (*h)[m]
			i = m
		}
	}
	return top
}

func chooseRemote(t float64) int {
	best := 0
	bestLoad := 1e300
	for k := 0; k < K; k++ {
		load := rBusyUntil[k]
		if load < t {
			load = t
		}
		load += pendPrefill[k]
		dq := int64(len(dprocQ[k].items)-dprocQ[k].head) + inflightUP[k]
		if dq > 0 {
			load += S + lookup(4, dq)
		}
		if load < bestLoad-1e-9 {
			bestLoad = load
			best = k
		}
	}
	return best
}

func main() {
	// on any unexpected input EOF/corruption, exit cleanly with code 0
	// (the interactor determines the verdict, not our exit path)
	defer func() { _ = recover() }()
	rd := NewFastReader()
	K = int(atoi(rd.token()))
	S = atof(rd.token())
	LAT = atof(rd.token())
	BW = atof(rd.token())
	BPT = atoi(rd.token())
	LAY = int(atoi(rd.token()))
	for i := 0; i < 7; i++ {
		rd.token() // scoring params: read but not needed by the scheduler
	}
	N := atoi(rd.token())
	for i := int64(0); i < N; i++ {
		bs := atoi(rd.token())
		for c := 0; c < 6; c++ {
			v := atof(rd.token())
			if v > -0.5 {
				tab[c] = append(tab[c], trow{int(bs), v})
			}
		}
	}
	for c := 0; c < 6; c++ {
		sort.Slice(tab[c], func(i, j int) bool { return tab[c][i].size < tab[c][j].size })
		if len(tab[c]) == 0 {
			tab[c] = append(tab[c], trow{1, 0.001})
		}
	}

	rBusy = make([]bool, K)
	rBusyUntil = make([]float64, K)
	pendPrefill = make([]float64, K)
	inflightUP = make([]int64, K)
	pprocQ = make([]Queue, K)
	dprocQ = make([]Queue, K)
	decR = make(map[int]struct{})
	dpostR = make(map[int]struct{})

	out := make([]byte, 0, 1<<16)

	for {
		tk := rd.token()
		if tk == nil || tk[0] == 'E' { // EOF or END
			return
		}
		t := atof(tk)
		e := atoi(rd.token())
		var fins []int
		for i := int64(0); i < e; i++ {
			ev := rd.token()
			switch ev[0] {
			case 'A': // ARR rid lin
				rid := int(atoi(rd.token()))
				lin := atoi(rd.token())
				for len(rstate) <= rid {
					rstate = append(rstate, stArrived)
					rremote = append(rremote, 0)
					rlin = append(rlin, 0)
				}
				rstate[rid] = stArrived
				rlin[rid] = lin
				arrQ = append(arrQ, rid)
			case 'T': // TDN server spec... dur
				srv := rd.token()
				if srv[0] == 'E' {
					eBusy = false
				} else {
					rBusy[int(atoi(srv[1:]))] = false
				}
				pd := rd.token()[0]
				st := rd.token()[2] // prE->'E', prOc->'O', poSt->'S'
				if pd == 'P' {
					if st == 'E' { // P PRE remote rid dur
						rd.token()
						rd.token()
						rd.token()
					} else if st == 'O' { // P PROC ls le remote rid dur
						rd.token()
						rd.token()
						rd.token()
						rd.token()
						rd.token()
					} else { // P POST remote rid dur
						rd.token()
						rid := int(atoi(rd.token()))
						rd.token()
						rstate[rid] = stDecRdy
						decR[rid] = struct{}{}
					}
				} else {
					if st == 'E' { // D PRE -1 m rids dur
						rd.token()
						m := atoi(rd.token())
						for j := int64(0); j < m; j++ {
							rd.token()
						}
						rd.token()
					} else if st == 'O' { // D PROC remote m rids dur
						rd.token()
						m := atoi(rd.token())
						for j := int64(0); j < m; j++ {
							rd.token()
						}
						rd.token()
					} else { // D POST -1 m rids dur
						rd.token()
						m := atoi(rd.token())
						for j := int64(0); j < m; j++ {
							rid := int(atoi(rd.token()))
							rstate[rid] = stDecRdy
							decR[rid] = struct{}{}
						}
						inflightDec -= m
						rd.token()
					}
				}
			case 'X': // XDN dir remote size kind m rids
				up := rd.token()[0] == 'U'
				rm := int(atoi(rd.token()))
				rd.token() // size
				pre := rd.token()[0] == 'P'
				m := atoi(rd.token())
				if up && pre {
					rid := int(atoi(rd.token()))
					rstate[rid] = stPprocRdy
					pprocQ[rm].push(ritem{rid, t})
				} else if up {
					for j := int64(0); j < m; j++ {
						rid := int(atoi(rd.token()))
						rstate[rid] = stDprocRdy
						dprocQ[rm].push(ritem{rid, t})
						inflightUP[rm]--
					}
				} else if pre {
					rid := int(atoi(rd.token()))
					rstate[rid] = stPpostRdy
					heapPush(&ppostH, rid)
				} else {
					for j := int64(0); j < m; j++ {
						rid := int(atoi(rd.token()))
						rstate[rid] = stDpostRdy
						dpostR[rid] = struct{}{}
					}
				}
			default: // FIN rid
				fins = append(fins, int(atoi(rd.token())))
			}
		}
		for _, rid := range fins {
			rstate[rid] = stDone
			delete(decR, rid)
		}

		// ---------- decide ----------
		out = out[:0]
		n := 0
		var body []byte
		if !eBusy {
			if len(ppostH) > 0 {
				rid := heapPop(&ppostH)
				body = append(body, "E P POST "...)
				body = strconv.AppendInt(body, int64(rremote[rid]), 10)
				body = append(body, ' ')
				body = strconv.AppendInt(body, int64(rid), 10)
				body = append(body, '\n')
				n++
				rstate[rid] = stInflight
				eBusy = true
			} else if arrHead < len(arrQ) {
				rid := arrQ[arrHead]
				arrHead++
				k := chooseRemote(t)
				rremote[rid] = k
				rstate[rid] = stInflight
				eBusy = true
				body = append(body, "E P PRE "...)
				body = strconv.AppendInt(body, int64(k), 10)
				body = append(body, ' ')
				body = strconv.AppendInt(body, int64(rid), 10)
				body = append(body, '\n')
				n++
				pendPrefill[k] += S + lookup(1, rlin[rid])
			} else if len(dpostR) > 0 {
				body = append(body, "E D POST -1 "...)
				body = strconv.AppendInt(body, int64(len(dpostR)), 10)
				for rid := range dpostR {
					body = append(body, ' ')
					body = strconv.AppendInt(body, int64(rid), 10)
					rstate[rid] = stInflight
				}
				body = append(body, '\n')
				n++
				dpostR = make(map[int]struct{})
				eBusy = true
			} else if len(decR) > 0 {
				// congestion-adaptive batching: when many decode requests are
				// in flight the system is busy; hold small D PRE groups until
				// the batch is worth the per-transfer latency and S overheads.
				m := len(decR)
				batch := int(inflightDec / int64(K))
				if batch < 1 {
					batch = 1
				}
				if batch > 512 {
					batch = 512
				}
				if inflightDec == 0 || m >= batch {
					body = append(body, "E D PRE -1 "...)
					body = strconv.AppendInt(body, int64(m), 10)
					for rid := range decR {
						body = append(body, ' ')
						body = strconv.AppendInt(body, int64(rid), 10)
						rstate[rid] = stInflight
						inflightUP[rremote[rid]]++
						inflightDec++
					}
					body = append(body, '\n')
					n++
					decR = make(map[int]struct{})
					eBusy = true
				}
			}
		}
		for k := 0; k < K; k++ {
			if rBusy[k] {
				continue
			}
			hasP := !pprocQ[k].empty()
			hasD := !dprocQ[k].empty()
			if hasP && (!hasD || pprocQ[k].front().ts <= dprocQ[k].front().ts) {
				it := pprocQ[k].front()
				pprocQ[k].pop()
				rid := it.rid
				body = append(body, 'C')
				body = strconv.AppendInt(body, int64(k), 10)
				body = append(body, " P PROC 0 "...)
				body = strconv.AppendInt(body, int64(LAY), 10)
				body = append(body, ' ')
				body = strconv.AppendInt(body, int64(k), 10)
				body = append(body, ' ')
				body = strconv.AppendInt(body, int64(rid), 10)
				body = append(body, '\n')
				n++
				rstate[rid] = stInflight
				rBusy[k] = true
				rBusyUntil[k] = t + S + lookup(1, rlin[rid])
				pendPrefill[k] -= S + lookup(1, rlin[rid])
			} else if hasD {
				items := dprocQ[k].takeAll()
				body = append(body, 'C')
				body = strconv.AppendInt(body, int64(k), 10)
				body = append(body, " D PROC "...)
				body = strconv.AppendInt(body, int64(k), 10)
				body = append(body, ' ')
				body = strconv.AppendInt(body, int64(len(items)), 10)
				for _, it := range items {
					body = append(body, ' ')
					body = strconv.AppendInt(body, int64(it.rid), 10)
					rstate[it.rid] = stInflight
				}
				body = append(body, '\n')
				n++
				rBusy[k] = true
				rBusyUntil[k] = t + S + lookup(4, int64(len(items)))
			}
		}
		out = strconv.AppendInt(out, int64(n), 10)
		out = append(out, '\n')
		out = append(out, body...)
		os.Stdout.Write(out)
	}
}
