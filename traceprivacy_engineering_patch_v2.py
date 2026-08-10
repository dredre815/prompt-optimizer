from pathlib import Path

# Apply the already-audited capture/social-fixture engineering patch first.
import traceprivacy_engineering_patch  # noqa: F401

ROOT = Path(__file__).resolve().parent / "trace_privacy"
p = ROOT / "common.py"
s = p.read_text(encoding="utf-8")
start = s.index("    def call_json(\n", s.index("class DirectTraceClient:"))
end = s.index("\n\n\ndef deepseek_probe", start)
new_method = r'''    def call_json(
        self,
        messages: list[dict[str, str]],
        *,
        model: str = PRIMARY_MODEL,
        max_tokens: int = 450,
        temperature: float = 0.0,
    ) -> tuple[dict[str, Any], Any]:
        """Issue one real model call and preserve it even if JSON is truncated.

        DeepSeek can occasionally terminate a syntactically valid JSON-mode
        response at the configured completion-token boundary. Retrying would
        alter the encrypted trace and break the matched-call-count control.
        Instead, record the one HTTP call exactly once, recover an explicitly
        emitted action when possible, and otherwise treat a malformed
        intermediate response as an opaque note. A final response without an
        recoverable action still fails closed.
        """
        start_wall = time.time()
        start = time.perf_counter()
        response = self.client.chat.completions.create(
            model=model,
            messages=messages,
            stream=False,
            max_tokens=max_tokens,
            temperature=temperature,
            response_format={"type": "json_object"},
            extra_body={"thinking": {"type": self.thinking}},
        )
        end = time.perf_counter()
        content = response.choices[0].message.content or "{}"
        usage = response.usage.model_dump() if response.usage is not None else {}
        event = {
            "call_index": len(self.events),
            "start_wall": start_wall,
            "start_rel_s": start - self.t0,
            "end_wall": time.time(),
            "latency_s": end - start,
            "gap_from_prev_s": 0.0 if not self.events else max(0.0, start_wall - float(self.events[-1]["end_wall"])),
            "prompt_bytes": len(json.dumps(messages, ensure_ascii=False).encode("utf-8")),
            "response_bytes": len(content.encode("utf-8")),
            "prompt_tokens": usage.get("prompt_tokens"),
            "completion_tokens": usage.get("completion_tokens"),
            "total_tokens": usage.get("total_tokens"),
            "returned_model": response.model,
            "ok": True,
            "json_parse_ok": True,
            "json_recovery": None,
        }
        parse_error: Exception | None = None
        try:
            parsed = json.loads(content)
        except json.JSONDecodeError as exc:
            parse_error = exc
            match = re.search(r"\{[\s\S]*\}", content)
            if match:
                try:
                    parsed = json.loads(match.group(0))
                    parse_error = None
                except json.JSONDecodeError as nested:
                    parse_error = nested
        if parse_error is not None:
            event["json_parse_ok"] = False
            prompt_text = "\n".join(str(m.get("content", "")) for m in messages).lower()
            is_final = (
                "sole final trading decision maker" in prompt_text
                or 'return json only with schema {"action"' in prompt_text
            )
            action_match = re.search(r'"action"\s*:\s*"([^"\\]+)', content, flags=re.I)
            confidence_match = re.search(r'"confidence"\s*:\s*([0-9]*\.?[0-9]+)', content, flags=re.I)
            if is_final:
                if action_match is None:
                    event["json_recovery"] = "failed_final_no_action"
                    self.events.append(event)
                    raise parse_error
                confidence = 0.5
                if confidence_match is not None:
                    try:
                        confidence = float(confidence_match.group(1))
                    except ValueError:
                        confidence = 0.5
                parsed = {
                    "action": action_match.group(1),
                    "confidence": confidence,
                    "rationale": "Recovered from a token-truncated JSON response; raw response hash="
                    + hashlib.sha256(content.encode("utf-8")).hexdigest(),
                    "_json_recovered": True,
                }
                event["json_recovery"] = "final_action_regex"
            else:
                note_match = re.search(r'"note"\s*:\s*"([\s\S]*)', content, flags=re.I)
                note = note_match.group(1) if note_match else content
                note = note.replace("\\n", " ").replace("\\\"", '"')
                # Keep the continuation deterministic and bounded; no retry and
                # no extra network call is introduced.
                parsed = {
                    "note": note[: max(256, min(2400, len(note)))],
                    "_json_recovered": True,
                }
                event["json_recovery"] = "intermediate_opaque_note"
        self.events.append(event)
        return parsed, response'''
s = s[:start] + new_method + s[end:]
p.write_text(s, encoding="utf-8")
print("TracePrivacy engineering patch v2 applied")
