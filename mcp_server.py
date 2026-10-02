#!/usr/bin/env python3
"""MCP server (stdio) over your Claude Code session history. Read-only.

Register for all projects:
  claude mcp add --scope user claude-sessions -- python3 /path/to/mcp_server.py
"""
import json
import os
import shlex
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import sessions as S  # noqa: E402

ROOT = Path(os.environ.get("CLAUDE_SESSIONS_ROOT", S.ROOT))
CACHE = Path(os.environ.get("CLAUDE_SESSIONS_CACHE", S.CACHE_DIR / "summaries.json"))
PROTOCOL = "2026-07-28"
INFO = {"name": "claude-sessions", "version": "1.0.0"}
CAPS = {"tools": {"listChanged": False}}
INDEX = S.Index(ROOT)


def _summaries():
    try:
        d = json.loads(CACHE.read_text())
        return d if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}


def _rows():
    INDEX.refresh()
    return [s for _, s in INDEX.by_id.values()]


def _brief(s, sm):
    return {"id": s["id"], "title": s["title"], "project": s["project"], "cwd": s["cwd"], "start": s["start"],
            "end": s["end"], "summary": (sm.get(s["id"]) or {}).get("summary"), "prs": [p["url"] for p in s["prs"]],
            "artifacts": s["artifacts"],
            "cost_usd": round(s["cost"], 2)}


def _newest(rows):
    return sorted(rows, key=lambda s: s["end"] or "", reverse=True)


def _utc(dt):
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")


def search_sessions(query, limit=10):
    sm, rows = _summaries(), _rows()
    k, q = max(1, min(int(limit), 50)), str(query).lower().strip()
    # verbatim hits first: TF-IDF drops ids like "4242" (no token) and "ABC-123" (only "abc" survives)
    ranked = S.retrieve(q, rows, k=len(rows))
    exact = {s["id"]: s for s in _newest(rows) if q and (q in s["text"] or q in s["title"].lower())}
    if len(exact) > k:  # a common word: keep only verbatim hits, but in TF-IDF order (unscored ones newest first)
        exact = {**{s["id"]: s for s in ranked if s["id"] in exact}, **exact}
    hits = list({**exact, **{s["id"]: s for s in ranked}}.values())[:k]
    return [{**_brief(s, sm), "snippet": S.snippet(s, q, 150) if s["id"] in exact else S.excerpts(s, q, 300)}
            for s in hits]


def get_session(id, max_chars=20000):
    INDEX.refresh()
    hit = INDEX.by_id.get(id)
    if not hit:
        raise ValueError(f"unknown session id: {id}")
    path, s = hit
    related = [{"id": r["id"], "title": INDEX.by_id[r["id"]][1]["title"], "score": r["score"]}
               for r in INDEX.related.get(id, []) if r["id"] in INDEX.by_id]
    return {**_brief(s, _summaries()), "branches": s["branches"], "files": s["file_keys"], "related": related,
            "resume": f"cd {shlex.quote(s['cwd'])} && claude --resume {shlex.quote(s['id'])}",
            "transcript": S.transcript_text(path, limit=max(1000, min(int(max_chars), 200_000)))}


def sessions_for_file(path):
    path = str(path)
    key = path if (":" in path and not path.startswith("/")) else S.file_key(path)
    sm = _summaries()
    return [_brief(s, sm) for s in _newest(_rows()) if key in s["file_keys"] or path in s["files"]]


def recent_sessions(days=7, project=None):
    cutoff = _utc(datetime.now(timezone.utc) - timedelta(days=float(days)))
    sm = _summaries()
    return [_brief(s, sm) for s in _newest(_rows()) if (s["end"] or "") >= cutoff
            and (not project or s["project"] == project or s["project"].startswith(f"{project}/"))]


def session_digest(week_offset=0):
    now = datetime.now().astimezone()
    monday = (now - timedelta(days=now.weekday())).replace(hour=0, minute=0, second=0, microsecond=0)
    monday += timedelta(weeks=int(week_offset))
    end = monday + timedelta(days=7)
    lo, hi = _utc(monday), _utc(end)
    sm = _summaries()
    groups = {}
    week = sorted((s for s in _rows() if lo <= (s["start"] or "") < hi), key=lambda s: s["start"])
    for s in week:
        groups.setdefault(s["project"].split("/")[0], []).append(_brief(s, sm))
    return {"from": monday.isoformat(), "to": end.isoformat(), "sessions": len(week), "groups": groups}


def _schema(props, required=()):
    return {"type": "object", "properties": props, "required": list(required)}


TOOLS = {
    "search_sessions": (search_sessions, "Search the user's past Claude Code sessions across all projects by topic. "
                        "Returns the best matches with summaries and snippets; use get_session for a full transcript.",
                        _schema({"query": {"type": "string", "description": "Topic, error, ticket id, etc."},
                                 "limit": {"type": "integer", "default": 10, "maximum": 50}}, ["query"])),
    "get_session": (get_session, "Read one past session: metadata, summary, files edited, related sessions, the "
                    "resume command, and the transcript text (head and tail kept when long).",
                    _schema({"id": {"type": "string"},
                             "max_chars": {"type": "integer", "default": 20000, "maximum": 200000}}, ["id"])),
    "sessions_for_file": (sessions_for_file, "Every past session that edited a file, newest first. Accepts an "
                          "absolute path (worktrees resolve to the main repo) or a 'repo:path/in/repo' key.",
                          _schema({"path": {"type": "string"}}, ["path"])),
    "recent_sessions": (recent_sessions, "Sessions active in the last N days, newest first, optionally limited to "
                        "a project (e.g. 'acme' includes its subfolders).",
                        _schema({"days": {"type": "number", "default": 7}, "project": {"type": "string"}})),
    "session_digest": (session_digest, "One week's sessions (Monday to Sunday, local time) grouped by top-level "
                       "folder with summaries, for writing standups or weekly updates. week_offset -1 = last week.",
                       _schema({"week_offset": {"type": "integer", "default": 0}})),
}


def _call(name, args):
    if name not in TOOLS:
        return {"resultType": "complete", "isError": True, "content": [{"type": "text", "text": f"unknown tool: {name}"}]}
    try:
        out = TOOLS[name][0](**(args if isinstance(args, dict) else {}))
    except Exception as e:  # bad arguments or unknown id: report to the model, keep serving
        return {"resultType": "complete", "isError": True, "content": [{"type": "text", "text": f"{type(e).__name__}: {e}"}]}
    return {"resultType": "complete", "content": [{"type": "text", "text": json.dumps(out, indent=1)}]}


def handle(msg):
    method, mid, params = msg.get("method"), msg.get("id"), msg.get("params") or {}
    if "id" not in msg:
        return None  # notification
    if method == "initialize":  # pre-2026-07-28 clients
        result = {"protocolVersion": params.get("protocolVersion", PROTOCOL), "capabilities": CAPS, "serverInfo": INFO}
    elif method == "server/discover":
        result = {"supportedVersions": [PROTOCOL, "2025-06-18", "2025-03-26"], "capabilities": CAPS, "serverInfo": INFO}
    elif method == "ping":
        result = {}
    elif method == "tools/list":
        result = {"resultType": "complete", "ttlMs": 60_000, "cacheScope": "private",  # personal data: never shared caches
                  "tools": [{"name": n, "description": d, "inputSchema": sch} for n, (_, d, sch) in TOOLS.items()]}
    elif method == "tools/call":
        result = _call(params.get("name"), params.get("arguments") or {})
    else:
        return {"jsonrpc": "2.0", "id": mid, "error": {"code": -32601, "message": f"method not found: {method}"}}
    return {"jsonrpc": "2.0", "id": mid, "result": result}


def main():
    for line in sys.stdin:
        if not line.strip():
            continue
        try:
            msg = json.loads(line)
            reply = handle(msg) if isinstance(msg, dict) else {"jsonrpc": "2.0", "id": None, "error": {"code": -32600, "message": "invalid request"}}
        except ValueError:
            reply = {"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": "parse error"}}
        if reply is not None:
            sys.stdout.write(json.dumps(reply) + "\n")
            sys.stdout.flush()


if __name__ == "__main__":
    main()
