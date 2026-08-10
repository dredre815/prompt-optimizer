from pathlib import Path

ROOT = Path(__file__).resolve().parent / "trace_privacy"


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{label}: expected one match, found {count}")
    return text.replace(old, new, 1)


# 1) GitHub Actions captures use Linux cooked-v2 (or Ethernet on a concrete
# interface). Parse pcap bytes directly instead of depending on tcpdump's
# human-readable output format. Select the default interface to avoid the
# duplicate frames produced by '-i any' on this runner image.
p = ROOT / "common.py"
s = p.read_text(encoding="utf-8")
s = replace_once(s, "import socket\n", "import socket\nimport struct\n", "common struct import")
start = s.index("class PacketCapture:")
end = s.index("\n\nclass DirectTraceClient:", start)
new_class = r'''class PacketCapture:
    """Capture actual encrypted TCP payload packets to/from api.deepseek.com."""

    def __init__(self, pcap_path: Path):
        self.pcap_path = pcap_path
        self.proc: subprocess.Popen[str] | None = None
        self.remote_ips = sorted(
            {
                info[4][0]
                for info in socket.getaddrinfo("api.deepseek.com", 443, family=socket.AF_INET, type=socket.SOCK_STREAM)
            }
        )
        if not self.remote_ips:
            raise RuntimeError("Could not resolve api.deepseek.com to an IPv4 address")

    def start(self) -> None:
        self.pcap_path.parent.mkdir(parents=True, exist_ok=True)
        host_filter = " or ".join(f"host {ip}" for ip in self.remote_ips)
        expr = f"tcp port 443 and ({host_filter})"
        try:
            iface = subprocess.check_output(
                ["sh", "-c", "ip route show default | awk 'NR==1 {print $5}'"],
                text=True,
            ).strip()
        except Exception:
            iface = ""
        cmd = [
            "sudo", "tcpdump", "-i", iface or "any", "-U", "-s", "0", "-nn",
            "-w", str(self.pcap_path), expr,
        ]
        self.proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True)
        time.sleep(0.45)
        if self.proc.poll() is not None:
            stderr = self.proc.stderr.read() if self.proc.stderr else ""
            raise RuntimeError(f"tcpdump exited before capture: {stderr}")

    def stop(self) -> None:
        if self.proc is None:
            return
        self.proc.send_signal(signal.SIGINT)
        try:
            self.proc.wait(timeout=8)
        except subprocess.TimeoutExpired:
            self.proc.terminate()
            self.proc.wait(timeout=5)
        if not self.pcap_path.exists() or self.pcap_path.stat().st_size < 24:
            stderr = self.proc.stderr.read() if self.proc.stderr else ""
            raise RuntimeError(f"pcap was not created or is empty: {stderr}")

    @staticmethod
    def _ip_offset(frame: bytes, linktype: int) -> int | None:
        if linktype == 1:  # Ethernet
            if len(frame) < 14:
                return None
            ethertype = int.from_bytes(frame[12:14], "big")
            offset = 14
            while ethertype in {0x8100, 0x88A8} and len(frame) >= offset + 4:
                ethertype = int.from_bytes(frame[offset + 2:offset + 4], "big")
                offset += 4
            return offset if ethertype == 0x0800 else None
        if linktype == 113:  # Linux cooked v1
            return 16 if len(frame) >= 16 and int.from_bytes(frame[14:16], "big") == 0x0800 else None
        if linktype == 276:  # Linux cooked v2
            return 20 if len(frame) >= 20 and int.from_bytes(frame[0:2], "big") == 0x0800 else None
        return None

    def parse(self) -> list[dict[str, Any]]:
        raw = self.pcap_path.read_bytes()
        if len(raw) < 24:
            raise RuntimeError("pcap is shorter than its global header")
        magic = raw[:4]
        formats = {
            b"\xd4\xc3\xb2\xa1": ("<", 1_000_000.0),
            b"\xa1\xb2\xc3\xd4": (">", 1_000_000.0),
            b"\x4d\x3c\xb2\xa1": ("<", 1_000_000_000.0),
            b"\xa1\xb2\x3c\x4d": (">", 1_000_000_000.0),
        }
        if magic not in formats:
            raise RuntimeError(f"unsupported pcap magic: {magic.hex()}")
        endian, frac_scale = formats[magic]
        linktype = struct.unpack_from(endian + "I", raw, 20)[0]
        offset = 24
        packets: list[dict[str, Any]] = []
        first_ts: float | None = None
        last_seen: dict[tuple[Any, ...], float] = {}
        while offset + 16 <= len(raw):
            ts_sec, ts_frac, captured_len, _wire_len = struct.unpack_from(endian + "IIII", raw, offset)
            offset += 16
            if captured_len < 0 or offset + captured_len > len(raw):
                raise RuntimeError("truncated pcap packet record")
            frame = raw[offset:offset + captured_len]
            offset += captured_len
            ip_offset = self._ip_offset(frame, linktype)
            if ip_offset is None or len(frame) < ip_offset + 20:
                continue
            ip = frame[ip_offset:]
            if ip[0] >> 4 != 4 or ip[9] != 6:
                continue
            ihl = (ip[0] & 0x0F) * 4
            if ihl < 20 or len(ip) < ihl + 20:
                continue
            total_len = int.from_bytes(ip[2:4], "big")
            src_ip = socket.inet_ntoa(ip[12:16])
            dst_ip = socket.inet_ntoa(ip[16:20])
            tcp = ip[ihl:]
            src_port = int.from_bytes(tcp[0:2], "big")
            dst_port = int.from_bytes(tcp[2:4], "big")
            seq = int.from_bytes(tcp[4:8], "big")
            ack = int.from_bytes(tcp[8:12], "big")
            tcp_hlen = (tcp[12] >> 4) * 4
            if tcp_hlen < 20:
                continue
            payload_len = max(0, total_len - ihl - tcp_hlen)
            if payload_len <= 0:
                continue
            if dst_ip in self.remote_ips and dst_port == 443:
                direction = "up"
                signed_len = payload_len
            elif src_ip in self.remote_ips and src_port == 443:
                direction = "down"
                signed_len = -payload_len
            else:
                continue
            ts = float(ts_sec) + float(ts_frac) / frac_scale
            # Linux '-i any' can expose the same skb twice. Retain genuine TCP
            # retransmissions but remove identical copies emitted within 1 ms.
            dedup_key = (src_ip, src_port, dst_ip, dst_port, seq, ack, payload_len)
            prior = last_seen.get(dedup_key)
            if prior is not None and ts - prior <= 0.001:
                continue
            last_seen[dedup_key] = ts
            if first_ts is None:
                first_ts = ts
            packets.append(
                {
                    "timestamp_wall": ts,
                    "time_rel_s": ts - first_ts,
                    "direction": direction,
                    "payload_len": payload_len,
                    "signed_len": signed_len,
                }
            )
        return packets'''
s = s[:start] + new_class + s[end:]
p.write_text(s, encoding="utf-8")

# 2) The current TradingAgents sentiment analyst pre-fetches Yahoo/StockTwits/
# Reddit through module-level references, bypassing the graph-level tool hooks.
# Route those three references to the already frozen scenario fixture.
p = ROOT / "tradingagents_runner.py"
s = p.read_text(encoding="utf-8")
s = replace_once(
    s,
    "    news_text,\n    pcap_summary,\n",
    "    news_text,\n    pad_text,\n    pcap_summary,\n",
    "TradingAgents pad_text import",
)
needle = '''@tool("get_global_news")
def fixture_get_global_news(curr_date: str, look_back_days: int | None = None, limit: int | None = None) -> str:
    """Return frozen global macro headlines."""
    return macro_text(current())
'''
addition = needle + r'''


def fixture_stocktwits_messages(ticker: str, limit: int = 30) -> str:
    s = current()
    counts = {
        "bull": "18 Bullish, 6 Bearish, 6 unlabeled",
        "neutral": "10 Bullish, 10 Bearish, 10 unlabeled",
        "bear": "6 Bullish, 18 Bearish, 6 unlabeled",
    }[s.regime]
    text = (
        f"Frozen StockTwits cashtag sample for {s.ticker}: {counts}. "
        f"All messages fall within the requested window and discuss {s.company_name}."
    )
    return pad_text(text, 3200, f"stocktwits:{s.scenario_id}")


def fixture_reddit_posts(ticker: str) -> str:
    s = current()
    tone = {
        "bull": "engagement-weighted discussion emphasizes improving demand and cash generation",
        "neutral": "engagement-weighted discussion is balanced between execution and valuation",
        "bear": "engagement-weighted discussion emphasizes weakening demand and balance-sheet risk",
    }[s.regime]
    text = f"Frozen Reddit sample for {s.ticker}: {tone}."
    return pad_text(text, 3200, f"reddit:{s.scenario_id}")
'''
s = replace_once(s, needle, addition, "TradingAgents deterministic social fixtures")
needle = '''    for name, obj in replacements.items():
        setattr(tg, name, obj)

    # Eliminate all non-DeepSeek network traffic. This is a conservative setup:
'''
replacement = '''    for name, obj in replacements.items():
        setattr(tg, name, obj)

    import tradingagents.agents.analysts.sentiment_analyst as sentiment_module

    sentiment_module.get_news = fixture_get_news
    sentiment_module.fetch_stocktwits_messages = fixture_stocktwits_messages
    sentiment_module.fetch_reddit_posts = fixture_reddit_posts

    # Eliminate all non-DeepSeek network traffic. This is a conservative setup:
'''
s = replace_once(s, needle, replacement, "TradingAgents sentiment module hooks")
p.write_text(s, encoding="utf-8")

print("TracePrivacy engineering patch v1 applied")
