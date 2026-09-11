package main

import (
	"bufio"
	"os"
	"strconv"
)

type FastInput struct {
	r       *os.File
	buf     []byte
	pos     int
	n       int
	scratch []byte
}

func NewFastInput(r *os.File) *FastInput {
	return &FastInput{r: r, buf: make([]byte, 1<<20)}
}

func (in *FastInput) nextToken() ([]byte, bool) {
	for {
		for in.pos < in.n && in.buf[in.pos] <= ' ' {
			in.pos++
		}
		if in.pos < in.n {
			break
		}
		read, err := in.r.Read(in.buf)
		in.pos = 0
		in.n = read
		if read == 0 {
			if err != nil {
				return nil, false
			}
			continue
		}
	}

	start := in.pos
	for {
		for in.pos < in.n && in.buf[in.pos] > ' ' {
			in.pos++
		}
		if in.pos < in.n {
			return in.buf[start:in.pos], true
		}

		in.scratch = append(in.scratch[:0], in.buf[start:in.n]...)
		read, err := in.r.Read(in.buf)
		in.pos = 0
		in.n = read
		if read == 0 {
			if err != nil {
				return in.scratch, len(in.scratch) != 0
			}
			continue
		}
		for in.pos < in.n && in.buf[in.pos] > ' ' {
			in.pos++
		}
		if in.pos < in.n {
			in.scratch = append(in.scratch, in.buf[:in.pos]...)
			return in.scratch, true
		}
		in.scratch = append(in.scratch, in.buf[:in.n]...)
		start = 0
	}
}

func mustToken(in *FastInput) []byte {
	token, ok := in.nextToken()
	if !ok {
		return nil
	}
	return token
}

func parseInt(token []byte) int {
	if len(token) == 0 {
		return 0
	}
	sign := 1
	start := 0
	if token[0] == '-' {
		sign = -1
		start = 1
	} else if token[0] == '+' {
		start = 1
	}
	value := 0
	for _, c := range token[start:] {
		value = value*10 + int(c-'0')
	}
	return sign * value
}

const (
	tokUnknown uint8 = iota
	tokARR
	tokFIN
	tokXDN
	tokTDN
	tokEND
	tokP
	tokD
	tokE
	tokUP
	tokDOWN
	tokPRE
	tokPROC
	tokPOST
)

func tokenCode(token []byte) uint8 {
	switch len(token) {
	case 1:
		switch token[0] {
		case 'P':
			return tokP
		case 'D':
			return tokD
		case 'E':
			return tokE
		}
	case 2:
		if token[0] == 'U' && token[1] == 'P' {
			return tokUP
		}
	case 3:
		switch token[0] {
		case 'A':
			if token[1] == 'R' && token[2] == 'R' {
				return tokARR
			}
		case 'F':
			if token[1] == 'I' && token[2] == 'N' {
				return tokFIN
			}
		case 'X':
			if token[1] == 'D' && token[2] == 'N' {
				return tokXDN
			}
		case 'T':
			if token[1] == 'D' && token[2] == 'N' {
				return tokTDN
			}
		case 'E':
			if token[1] == 'N' && token[2] == 'D' {
				return tokEND
			}
		case 'P':
			if token[1] == 'R' && token[2] == 'E' {
				return tokPRE
			}
		}
	case 4:
		switch token[0] {
		case 'D':
			if token[1] == 'O' && token[2] == 'W' && token[3] == 'N' {
				return tokDOWN
			}
		case 'P':
			if token[1] == 'R' && token[2] == 'O' && token[3] == 'C' {
				return tokPROC
			}
			if token[1] == 'O' && token[2] == 'S' && token[3] == 'T' {
				return tokPOST
			}
		}
	}
	return tokUnknown
}

type Queue struct {
	items []int
	head  int
}

func (q *Queue) push(value int) {
	q.items = append(q.items, value)
}

func (q *Queue) resetIfEmpty() {
	if q.head == len(q.items) {
		q.items = q.items[:0]
		q.head = 0
	}
}

func popValid(q *Queue, requests []Request, expected State) int {
	for q.head < len(q.items) {
		rid := q.items[q.head]
		q.head++
		if rid >= 0 && rid < len(requests) && requests[rid].state == expected {
			q.resetIfEmpty()
			return rid
		}
	}
	q.resetIfEmpty()
	return -1
}

func drainValid(q *Queue, requests []Request, expected State) []int {
	ids := make([]int, 0, len(q.items)-q.head)
	for q.head < len(q.items) {
		rid := q.items[q.head]
		q.head++
		if rid >= 0 && rid < len(requests) && requests[rid].state == expected {
			ids = append(ids, rid)
		}
	}
	q.resetIfEmpty()
	return ids
}

type State uint8

const (
	stateNone State = iota
	statePreReady
	statePreInFlight
	stateProcWaitUp
	stateProcReady
	stateProcInFlight
	statePostWaitDown
	statePostReady
	statePostInFlight
	stateDecodePreReady
	stateDecodePreInFlight
	stateDecodeProcWaitUp
	stateDecodeProcReady
	stateDecodeProcInFlight
	stateDecodePostWaitDown
	stateDecodePostReady
	stateDecodePostInFlight
	stateFinished
)

type Request struct {
	remote int
	state  State
}

type Command struct {
	server []byte
	spec   []byte
}

func appendIDs(dst []byte, ids []int) []byte {
	for _, rid := range ids {
		dst = append(dst, ' ')
		dst = strconv.AppendInt(dst, int64(rid), 10)
	}
	return dst
}

func main() {
	in := NewFastInput(os.Stdin)

	first, ok := in.nextToken()
	if !ok {
		return
	}
	remoteCount := parseInt(first)
	mustToken(in) // S
	mustToken(in) // latency_in_ms
	mustToken(in) // bandwidth_gbps
	mustToken(in) // bytes_per_token
	layers := parseInt(mustToken(in))

	for i := 0; i < 7; i++ {
		mustToken(in)
	}

	rowCount := parseInt(mustToken(in))
	for i := 0; i < rowCount*7; i++ {
		mustToken(in)
	}

	requests := make([]Request, 0, 2048)
	preReady := Queue{}
	postReady := Queue{}
	decodePreReady := Queue{}
	decodePostReady := Queue{}
	procReady := make([]Queue, remoteCount)
	decodeProcReady := make([]Queue, remoteCount)

	localBusy := false
	remoteBusy := make([]bool, remoteCount)
	activeOnRemote := make([]int, remoteCount)
	nextRemoteTieBreak := 0
	output := bufio.NewWriterSize(os.Stdout, 1<<20)

	for {
		frameHeader, ok := in.nextToken()
		if !ok || tokenCode(frameHeader) == tokEND {
			return
		}
		_ = frameHeader // The timestamp is not needed by a reactive scheduler.
		eventCount := parseInt(mustToken(in))

		for eventIndex := 0; eventIndex < eventCount; eventIndex++ {
			eventType := tokenCode(mustToken(in))
			if eventType == tokARR {
				rid := parseInt(mustToken(in))
				_ = parseInt(mustToken(in)) // L_in is not needed for a full piece.
				for len(requests) <= rid {
					requests = append(requests, Request{remote: -1})
				}
				requests[rid].state = statePreReady
				preReady.push(rid)
				continue
			}

			if eventType == tokFIN {
				rid := parseInt(mustToken(in))
				if rid >= 0 && rid < len(requests) && requests[rid].state != stateFinished {
					requests[rid].state = stateFinished
					remote := requests[rid].remote
					if remote >= 0 {
						activeOnRemote[remote]--
					}
				}
				continue
			}

			if eventType == tokXDN {
				direction := tokenCode(mustToken(in))
				remote := parseInt(mustToken(in))
				mustToken(in) // size
				phase := tokenCode(mustToken(in))
				memberCount := parseInt(mustToken(in))
				for i := 0; i < memberCount; i++ {
					rid := parseInt(mustToken(in))
					if rid < 0 || rid >= len(requests) {
						continue
					}
					request := &requests[rid]
					if phase == tokPRE {
						if direction == tokUP && request.state == stateProcWaitUp {
							request.state = stateProcReady
							procReady[request.remote].push(rid)
						} else if direction == tokDOWN && request.state == statePostWaitDown {
							request.state = statePostReady
							postReady.push(rid)
						}
					} else if direction == tokUP && request.state == stateDecodeProcWaitUp {
						request.state = stateDecodeProcReady
						decodeProcReady[remote].push(rid)
					} else if direction == tokDOWN && request.state == stateDecodePostWaitDown {
						request.state = stateDecodePostReady
						decodePostReady.push(rid)
					}
				}
				continue
			}

			// TDN
			server := mustToken(in)
			serverCode := tokenCode(server)
			serverRemote := -1
			if len(server) >= 2 && server[0] == 'C' {
				serverRemote = parseInt(server[1:])
			}
			kind := tokenCode(mustToken(in))
			step := tokenCode(mustToken(in))
			if serverCode == tokE {
				localBusy = false
			} else if serverRemote >= 0 && serverRemote < remoteCount {
				remoteBusy[serverRemote] = false
			}

			if kind == tokP && step == tokPRE {
				mustToken(in) // remote
				rid := parseInt(mustToken(in))
				mustToken(in) // duration
				if rid >= 0 && rid < len(requests) && requests[rid].state == statePreInFlight {
					requests[rid].state = stateProcWaitUp
				}
			} else if kind == tokP && step == tokPROC {
				mustToken(in) // ls
				mustToken(in) // le
				mustToken(in) // remote
				rid := parseInt(mustToken(in))
				mustToken(in) // duration
				if rid >= 0 && rid < len(requests) && requests[rid].state == stateProcInFlight {
					requests[rid].state = statePostWaitDown
				}
			} else if kind == tokP && step == tokPOST {
				mustToken(in) // remote
				rid := parseInt(mustToken(in))
				mustToken(in) // duration
				if rid >= 0 && rid < len(requests) && requests[rid].state == statePostInFlight {
					requests[rid].state = stateDecodePreReady
					decodePreReady.push(rid)
				}
			} else if kind == tokD && step == tokPRE {
				mustToken(in) // marker
				memberCount := parseInt(mustToken(in))
				for i := 0; i < memberCount; i++ {
					rid := parseInt(mustToken(in))
					if rid >= 0 && rid < len(requests) && requests[rid].state == stateDecodePreInFlight {
						requests[rid].state = stateDecodeProcWaitUp
					}
				}
				mustToken(in) // duration
			} else if kind == tokD && step == tokPROC {
				mustToken(in) // remote
				memberCount := parseInt(mustToken(in))
				for i := 0; i < memberCount; i++ {
					rid := parseInt(mustToken(in))
					if rid >= 0 && rid < len(requests) && requests[rid].state == stateDecodeProcInFlight {
						requests[rid].state = stateDecodePostWaitDown
					}
				}
				mustToken(in) // duration
			} else if kind == tokD && step == tokPOST {
				mustToken(in) // marker
				memberCount := parseInt(mustToken(in))
				for i := 0; i < memberCount; i++ {
					rid := parseInt(mustToken(in))
					if rid >= 0 && rid < len(requests) && requests[rid].state == stateDecodePostInFlight {
						requests[rid].state = stateDecodePreReady
						decodePreReady.push(rid)
					}
				}
				mustToken(in) // duration
			}
		}

		commands := make([]Command, 0, remoteCount+1)
		if !localBusy {
			ids := drainValid(&decodePostReady, requests, stateDecodePostReady)
			if len(ids) != 0 {
				spec := make([]byte, 0, 24+len(ids)*8)
				spec = append(spec, "D POST -1 "...)
				spec = strconv.AppendInt(spec, int64(len(ids)), 10)
				for _, rid := range ids {
					requests[rid].state = stateDecodePostInFlight
				}
				spec = appendIDs(spec, ids)
				commands = append(commands, Command{server: []byte("E"), spec: spec})
				localBusy = true
			} else {
				rid := popValid(&postReady, requests, statePostReady)
				if rid >= 0 {
					requests[rid].state = statePostInFlight
					spec := []byte("P POST ")
					spec = strconv.AppendInt(spec, int64(requests[rid].remote), 10)
					spec = append(spec, ' ')
					spec = strconv.AppendInt(spec, int64(rid), 10)
					commands = append(commands, Command{server: []byte("E"), spec: spec})
					localBusy = true
				} else {
					ids = drainValid(&decodePreReady, requests, stateDecodePreReady)
					if len(ids) != 0 {
						spec := make([]byte, 0, 24+len(ids)*8)
						spec = append(spec, "D PRE -1 "...)
						spec = strconv.AppendInt(spec, int64(len(ids)), 10)
						for _, decodeRid := range ids {
							requests[decodeRid].state = stateDecodePreInFlight
						}
						spec = appendIDs(spec, ids)
						commands = append(commands, Command{server: []byte("E"), spec: spec})
						localBusy = true
					} else {
						rid = popValid(&preReady, requests, statePreReady)
						if rid >= 0 {
							chosenRemote := 0
							bestLoad := int(^uint(0) >> 1)
							for offset := 0; offset < remoteCount; offset++ {
								candidate := (nextRemoteTieBreak + offset) % remoteCount
								if activeOnRemote[candidate] < bestLoad {
									bestLoad = activeOnRemote[candidate]
									chosenRemote = candidate
								}
							}
							nextRemoteTieBreak = (chosenRemote + 1) % remoteCount
							requests[rid].remote = chosenRemote
							requests[rid].state = statePreInFlight
							activeOnRemote[chosenRemote]++
							spec := []byte("P PRE ")
							spec = strconv.AppendInt(spec, int64(chosenRemote), 10)
							spec = append(spec, ' ')
							spec = strconv.AppendInt(spec, int64(rid), 10)
							commands = append(commands, Command{server: []byte("E"), spec: spec})
							localBusy = true
						}
					}
				}
			}
		}

		for remote := 0; remote < remoteCount; remote++ {
			if remoteBusy[remote] {
				continue
			}
			ids := drainValid(&decodeProcReady[remote], requests, stateDecodeProcReady)
			if len(ids) != 0 {
				spec := make([]byte, 0, 24+len(ids)*8)
				spec = append(spec, "D PROC "...)
				spec = strconv.AppendInt(spec, int64(remote), 10)
				spec = append(spec, ' ')
				spec = strconv.AppendInt(spec, int64(len(ids)), 10)
				for _, rid := range ids {
					requests[rid].state = stateDecodeProcInFlight
				}
				spec = appendIDs(spec, ids)
				server := []byte("C")
				server = strconv.AppendInt(server, int64(remote), 10)
				commands = append(commands, Command{server: server, spec: spec})
				remoteBusy[remote] = true
				continue
			}

			rid := popValid(&procReady[remote], requests, stateProcReady)
			if rid >= 0 {
				requests[rid].state = stateProcInFlight
				spec := []byte("P PROC 0 ")
				spec = strconv.AppendInt(spec, int64(layers), 10)
				spec = append(spec, ' ')
				spec = strconv.AppendInt(spec, int64(remote), 10)
				spec = append(spec, ' ')
				spec = strconv.AppendInt(spec, int64(rid), 10)
				server := []byte("C")
				server = strconv.AppendInt(server, int64(remote), 10)
				commands = append(commands, Command{server: server, spec: spec})
				remoteBusy[remote] = true
			}
		}

		output.WriteString(strconv.Itoa(len(commands)))
		output.WriteByte('\n')
		for _, command := range commands {
			output.Write(command.server)
			output.WriteByte(' ')
			output.Write(command.spec)
			output.WriteByte('\n')
		}
		output.Flush()
	}

}
