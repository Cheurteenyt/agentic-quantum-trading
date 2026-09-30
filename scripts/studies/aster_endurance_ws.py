#!/usr/bin/env python3
"""ONE-SHOT endurance WS Aster (T3, 30/09) — soak 20 min fstream (2 markPrice@1s),
latence push (corrigée du skew via /fapi/v1/time), pings client, reconnect backoff,
+ sonde RAW (frames de contrôle : pings serveur observés, pongs aux nôtres).
Aucune écriture DB. Sortie : reports/aster_endurance_ws.json"""
import json, time, socket, ssl, base64, os, struct, threading, statistics
from pathlib import Path
from curl_cffi import requests as creq
from websockets.sync.client import connect

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "reports" / "aster_endurance_ws.json"
T0 = time.time()
DURATION = 1200  # 20 min
HOST = "fstream.asterdex.com"
SOAK_PATH = "/stream?streams=btcusdt@markPrice@1s/ethusdt@markPrice@1s"
soak_events, raw_events, msgs, our_ping_rtts = [], [], [], []
lat_samples = {}   # stream -> [(recv_wall, E)]
conn_idx = [0]
skews = []


def rest_time():
    r = creq.get("https://fapi.asterdex.com/fapi/v1/time", impersonate="chrome131", timeout=10)
    return r.json()["serverTime"], time.time()


def pct(vals, q):
    if not vals:
        return None
    vals = sorted(vals)
    return vals[min(len(vals) - 1, max(0, int(round(q * (len(vals) - 1)))))]


# skew : 3 sondes REST avant + 3 après
for _ in range(3):
    st, lt = rest_time()
    skews.append(st - lt)
    time.sleep(0.5)
skew0 = statistics.median(skews)
raw_events.append({"ev": "skew0_s", "v": round(skew0, 3)})

# ---------- SONDE RAW : frames de contrôle ----------
def mask_frame(opcode, payload=b""):
    b0 = 0x80 | opcode
    ln = len(payload)
    if ln < 126:
        head = struct.pack("!BB", b0, 0x80 | ln)
    elif ln < 65536:
        head = struct.pack("!BBH", b0, 0x80 | 126, ln)
    else:
        head = struct.pack("!BBQ", b0, 0x80 | 127, ln)
    mask = os.urandom(4)
    return head + mask + bytes(b ^ mask[i % 4] for i, b in enumerate(payload))


def raw_probe():
    for attempt in range(3):
        try:
            s = ssl.create_default_context().wrap_socket(
                socket.create_connection((HOST, 443), timeout=30), server_hostname=HOST)
            key = base64.b64encode(os.urandom(16)).decode()
            s.sendall((f"GET /stream?streams=btcusdt@markPrice@1s HTTP/1.1\r\nHost: {HOST}\r\n"
                       f"Upgrade: websocket\r\nConnection: Upgrade\r\n"
                       f"Sec-WebSocket-Key: {key}\r\nSec-WebSocket-Version: 13\r\n\r\n").encode())
            buf = b""
            while b"\r\n\r\n" not in buf:
                c = s.recv(4096)
                if not c:
                    raise RuntimeError("handshake EOF")
                buf += c
            head, buf = buf.split(b"\r\n\r\n", 1)
            if b" 101 " not in head.split(b"\r\n")[0]:
                raise RuntimeError("handshake: " + head[:80].decode(errors="replace"))
            raw_events.append({"ev": "raw_connect", "t_rel": round(time.time() - T0, 1), "attempt": attempt})
            s.settimeout(30)
            last_ping = time.time()
            t_end = T0 + DURATION
            while time.time() < t_end:
                try:
                    chunk = s.recv(65536)
                except socket.timeout:
                    raw_events.append({"ev": "raw_idle30s", "t_rel": round(time.time() - T0, 1)})
                    continue
                except Exception as e:
                    raw_events.append({"ev": "raw_recv_exc", "t_rel": round(time.time() - T0, 1), "e": repr(e)[:120]})
                    raise
                if not chunk:
                    raise RuntimeError("raw EOF")
                buf += chunk
                while True:
                    b = buf
                    if len(b) < 2:
                        break
                    op = b[0] & 0x0F
                    ln = b[1] & 0x7F
                    off = 2
                    if ln == 126:
                        if len(b) < 4:
                            break
                        ln = int.from_bytes(b[2:4], "big"); off = 4
                    elif ln == 127:
                        if len(b) < 10:
                            break
                        ln = int.from_bytes(b[2:10], "big"); off = 10
                    if b[1] & 0x80:
                        off += 4
                    if len(b) < off + ln:
                        break
                    buf = b[off + ln:]
                    if op == 0x9:
                        raw_events.append({"ev": "SERVER_PING", "t_rel": round(time.time() - T0, 1),
                                           "len": ln})
                        s.sendall(mask_frame(0xA))  # pong immédiat
                    elif op == 0xA:
                        raw_events.append({"ev": "SERVER_PONG", "t_rel": round(time.time() - T0, 1),
                                           "after_our_ping": True, "len": ln})
                    elif op == 0x8:
                        raw_events.append({"ev": "SERVER_CLOSE", "t_rel": round(time.time() - T0, 1),
                                           "payload": b[off:off + ln][:8].hex()})
                        raise RuntimeError("server close frame")
                if time.time() - last_ping >= 60:
                    try:
                        s.sendall(mask_frame(0x9, b"hb"))
                        raw_events.append({"ev": "OUR_PING", "t_rel": round(time.time() - T0, 1)})
                        last_ping = time.time()
                    except Exception as e:
                        raw_events.append({"ev": "our_ping_exc", "e": repr(e)[:80]})
                        raise
            s.sendall(mask_frame(0x8, struct.pack("!H", 1000)))
            s.close()
            raw_events.append({"ev": "raw_clean_close", "t_rel": round(time.time() - T0, 1)})
            return
        except Exception as e:
            raw_events.append({"ev": "raw_attempt_failed", "attempt": attempt,
                               "t_rel": round(time.time() - T0, 1), "e": repr(e)[:160]})
            time.sleep(10)


threading.Thread(target=raw_probe, daemon=True).start()

# ---------- SOAK websockets.sync ----------
t_end = T0 + DURATION
last_ping_check = 0
last_recv = time.time()
while time.time() < t_end:
    conn_idx[0] += 1
    ci = conn_idx[0]
    try:
        with connect("wss://" + HOST + SOAK_PATH, open_timeout=15, close_timeout=5,
                     ping_interval=None, ping_timeout=20) as ws:
            soak_events.append({"ev": "connect", "n": ci, "t_rel": round(time.time() - T0, 1)})
            while time.time() < t_end:
                try:
                    m = ws.recv(timeout=20)
                except TimeoutError:
                    soak_events.append({"ev": "idle20s", "t_rel": round(time.time() - T0, 1)})
                    continue
                now = time.time()
                gap = now - last_recv
                if gap > 3.0:
                    soak_events.append({"ev": "gap", "s": round(gap, 2), "t_rel": round(now - T0, 1)})
                last_recv = now
                try:
                    d = json.loads(m)
                    data = d.get("data", {})
                    st = d.get("stream", "?")
                    msgs.append((now, data.get("E", 0), st))
                    lat_samples.setdefault(st, []).append((now, data.get("E", 0)))
                except Exception:
                    soak_events.append({"ev": "bad_json", "t_rel": round(now - T0, 1)})
                if now - last_ping_check >= 120:
                    last_ping_check = now
                    tp = time.monotonic()
                    p = ws.ping()
                    try:
                        ws.pong(p)  # bloque jusqu'au pong (ping_timeout=20)
                        our_ping_rtts.append({"t_rel": round(now - T0, 1),
                                              "rtt_ms": round((time.monotonic() - tp) * 1000, 1)})
                    except Exception as e:
                        soak_events.append({"ev": "our_ping_timeout", "e": repr(e)[:80],
                                            "t_rel": round(time.time() - T0, 1)})
    except Exception as e:
        soak_events.append({"ev": "disconnect", "n": ci, "t_rel": round(time.time() - T0, 1),
                            "e": repr(e)[:200]})
        time.sleep(min(20, 5 * ci))  # backoff 5/10/20

for _ in range(3):
    st, lt = rest_time()
    skews.append(st - lt)
    time.sleep(0.5)
skew1 = statistics.median(skews)

per_stream, lat_all = {}, []
for st, samples in lat_samples.items():
    lats = [(rw + skew1 - e) * 1000 for rw, e in samples if e]
    per_stream[st] = {"n": len(samples), "msg_per_s": round(len(samples) / DURATION, 3),
                      "lat_ms_p50": pct(lats, .5), "lat_ms_p95": pct(lats, .95),
                      "lat_ms_max": max(lats) if lats else None}
    lat_all += lats
n_disc = sum(1 for e in soak_events if e["ev"] == "disconnect")

OUT.write_text(json.dumps({
    "t0": T0, "duration_s": DURATION, "skew0": round(skew0, 3), "skew1": round(skew1, 3),
    "soak_events": soak_events, "raw_events": raw_events,
    "our_ping_rtts": our_ping_rtts,
    "total_msgs": len(msgs), "n_connects": conn_idx[0], "n_disconnects": n_disc,
    "per_stream": per_stream,
    "lat_all_ms": {"p50": pct(lat_all, .5), "p95": pct(lat_all, .95),
                   "max": max(lat_all) if lat_all else None, "n": len(lat_all)},
}, indent=1))
print("WROTE", OUT, "msgs:", len(msgs), "connects:", conn_idx[0], "disc:", n_disc, flush=True)
