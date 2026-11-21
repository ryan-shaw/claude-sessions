"""Self-check: python3 test_sessions.py"""
import json, os, tempfile, time
from pathlib import Path
import sessions

SID = "11111111-2222-3333-4444-555555555555"

def stub_bin(d, name, body):
    p = Path(d) / name
    p.write_text("#!/bin/sh\n" + body + "\n")
    p.chmod(0o755)

def wait_for(cond, secs=5):
    end = time.time() + secs
    while not cond():
        assert time.time() < end, "timed out"
        time.sleep(0.02)

def write_fixture(root):
    proj = root / "-Users-x-Development-acme-api"
    proj.mkdir(parents=True)
    recs = [
        {"type": "user", "isMeta": True, "message": {"content": "skill text"}, "timestamp": "2026-01-01T09:59:00Z", "sessionId": SID},
        {"type": "user", "message": {"content": "<task-notification>x</task-notification>"}, "timestamp": "2026-01-01T09:59:30Z"},
        {"type": "user", "cwd": "/Users/x/Development/acme/api", "gitBranch": "DD-1-fix", "timestamp": "2026-01-01T10:00:00Z",
         "message": {"content": "Fix the\nlogin  Bug please"}},
        {"type": "assistant", "gitBranch": "main", "timestamp": "2026-01-01T10:01:00Z",
         "message": {"content": [{"type": "text", "text": "Looking at the Widget for ABC-123, see PR 4242"},
                                 {"type": "tool_use", "name": "Edit", "input": {"file_path": "/a/b.py"}},
                                 {"type": "tool_use", "name": "Read", "input": {"file_path": "/a/c.py"}},
                                 {"type": "tool_use", "id": "t1", "name": "Artifact", "input": {"file_path": "/a/rate-limit-report.html", "description": "Quota findings"}},
                                 {"type": "tool_use", "id": "t2", "name": "Artifact", "input": {"action": "list"}}]}},
        {"type": "user", "timestamp": "2026-01-01T10:02:00Z",
         "message": {"content": [{"type": "tool_result", "content": "secret tool output"}]}},
        {"type": "user", "timestamp": "2026-01-01T10:02:20Z",
         "message": {"content": [{"type": "tool_result", "tool_use_id": "t1", "content": [{"type": "text", "text": "Published https://claude.ai/code/artifact/abc-1"}]},
                                 {"type": "tool_result", "tool_use_id": "t2", "content": "https://claude.ai/code/artifact/other-2"}]}},
        {"type": "pr-link", "prNumber": 7, "prUrl": "https://github.com/acme/api/pull/7", "prRepository": "acme/api", "timestamp": "2026-01-01T10:03:00Z"},
        {"type": "cost-state", "totalCostUSD": 1.5, "totalLinesAdded": 10, "totalLinesRemoved": 2},
    ]
    p = proj / f"{SID}.jsonl"
    p.write_text("\n".join(json.dumps(r) for r in recs) + "\n{not json\n")
    (proj / "empty.jsonl").write_text(json.dumps({"type": "ai-title", "aiTitle": "nothing"}) + "\n")
    sub = proj / SID / "subagents"
    sub.mkdir(parents=True)
    (sub / "agent-abc.jsonl").write_text(json.dumps({"type": "assistant", "message": {"content": [{"type": "text", "text": "sub work"}]}}) + "\n")
    (sub / "agent-abc.meta.json").write_text(json.dumps({"description": "Explore Jira"}))
    return p

def test_all():
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        path = write_fixture(root)
        sessions.DEV = Path("/Users/x/Development")

        s = sessions.parse_session(path)
        assert s["id"] == SID
        assert s["cwd"] == "/Users/x/Development/acme/api"
        assert s["project"] == "acme/api"
        assert s["branches"] == ["DD-1-fix", "main"]
        assert s["title"] == "Fix the login Bug please", s["title"]  # skipped isMeta + <task-notification>, whitespace collapsed
        assert s["start"] == "2026-01-01T09:59:00Z" and s["end"] == "2026-01-01T10:03:00Z"
        assert s["cost"] == 1.5 and s["added"] == 10 and s["removed"] == 2
        assert s["prs"] == [{"repo": "acme/api", "number": 7, "url": "https://github.com/acme/api/pull/7"}]
        assert s["files"] == ["/a/b.py"]
        assert s["artifacts"] == [{"url": "https://claude.ai/code/artifact/abc-1", "title": "rate limit report",
                                   "description": "Quota findings"}]  # published only, not listed
        assert "rate limit report quota findings" in s["text"]  # artifacts are searchable by name
        assert s["file_keys"] == ["/a/b.py"]  # not inside a git checkout -> absolute path
        assert s["subagents"] == 1
        assert "widget" in s["text"] and "secret tool output" not in s["text"]
        assert "skill text" not in s["text"] and "task-notification" not in s["text"]  # injected text not searchable

        # ai-title wins over first prompt
        with path.open("a") as f:
            f.write(json.dumps({"type": "ai-title", "aiTitle": "Login fix"}) + "\n")
        assert sessions.parse_session(path)["title"] == "Login fix"

        # metadata-only file is excluded
        assert sessions.parse_session(path.parent / "empty.jsonl") is None

        # no cwd -> decoded folder name
        nocwd = path.parent / "nocwd.jsonl"
        nocwd.write_text(json.dumps({"type": "user", "message": {"content": "hi"}}) + "\n")
        assert sessions.parse_session(nocwd)["cwd"] == "/Users/x/Development/acme/api"

        idx = sessions.Index(root)
        idx.refresh()
        v = idx.version
        idx.refresh()
        assert idx.version == v  # nothing changed
        os.utime(path, (1, 2_000_000_000))
        idx.refresh()
        assert idx.version == v + 1
        assert idx.by_id[SID][1]["mtime"] == 2_000_000_000
        ids = [x["id"] for x in idx.sessions()]
        assert set(ids) == {SID, "nocwd"} and all("text" not in x for x in idx.sessions())
        assert all(x["related"] == [] for x in idx.sessions())  # too few docs to relate
        # a change inside the 60s throttle window still gets related recomputed later, with no further writes
        idx._related_at = time.time()
        os.utime(path, (1, 2_000_000_001))
        idx.refresh()
        assert idx._related_dirty
        v = idx.version
        idx._related_at = 0
        idx.refresh()  # nothing changed on disk
        assert not idx._related_dirty and idx.version == v + 1

        hits = idx.search("WIDGET")
        assert [h["id"] for h in hits] == [SID] and "widget" in hits[0]["snippet"].lower()
        assert idx.search("") == [] and idx.search("zzz-nope") == []
        assert len(idx.search("acme/api")) == 2  # cwd match

        full = idx.session(SID)
        assert full["summary"]["id"] == SID
        assert "secret tool output" not in json.dumps(full["messages"])  # tool_result-only message dropped
        assert "skill text" not in json.dumps(full["messages"])  # isMeta (injected skill/context) hidden
        last = full["messages"][-1]
        assert last["role"] == "assistant" and [t["name"] for t in last["tools"]] == ["Edit", "Read", "Artifact", "Artifact"]
        assert full["subagents"] == [{"name": "Explore Jira", "messages": [{"role": "assistant", "ts": None, "text": "sub work", "tools": []}]}]
        assert idx.session("../../etc/passwd") is None

        # malformed records (string message, null text, non-dict input) don't break the index
        bad = path.parent / "bad.jsonl"
        bad.write_text("\n".join(json.dumps(r) for r in [
            {"type": "user", "message": "oops"},
            {"type": "assistant", "message": {"content": [{"type": "text", "text": None}, {"type": "tool_use", "name": "Edit", "input": "x"}]}},
            {"type": "user", "message": {"content": "real prompt"}},
        ]) + "\n")
        idx.refresh()
        assert "bad" in [x["id"] for x in idx.sessions()] and idx.session("bad")["messages"]
        bad.unlink()

        # refresh drops deleted files
        nocwd.unlink()
        idx.refresh()
        assert [x["id"] for x in idx.sessions()] == [SID]

def test_file_keys():
    with tempfile.TemporaryDirectory() as d:
        root = Path(d).resolve()
        (root / "main" / ".git" / "worktrees" / "wt").mkdir(parents=True)
        (root / "main" / "src").mkdir()
        (root / "wt" / "src").mkdir(parents=True)
        (root / "wt" / ".git").write_text(f"gitdir: {root}/main/.git/worktrees/wt\n")
        assert sessions.file_key(str(root / "main/src/a.py")) == "main:src/a.py"
        assert sessions.file_key(str(root / "wt/src/a.py")) == "main:src/a.py"  # worktree -> main repo name
        assert sessions.file_key(str(root / "gone/x.py")) == str(root / "gone/x.py")
        assert sessions.file_key("relative.py") == "relative.py"
        # a deleted in-repo worktree (.claude/worktrees/<n>) still maps to the main-checkout key
        assert sessions.file_key(str(root / "main/.claude/worktrees/old/src/a.py")) == "main:src/a.py"

def test_related():
    docs = [{"id": i, "text": t} for i, t in [
        ("a", "redis migration cluster keys eviction plan"), ("b", "redis migration cluster failover drill"),
        ("c", "turnstile captcha widget siteverify worker"), ("d", "turnstile captcha widget form submit")]]
    rel = sessions.related_sessions(docs)
    assert [r["id"] for r in rel["a"]] == ["b"], rel["a"]
    assert [r["id"] for r in rel["c"]] == ["d"]
    assert 0.15 <= rel["a"][0]["score"] <= 1
    assert sessions.related_sessions([]) == {}

def test_prs():
    with tempfile.TemporaryDirectory() as d:
        stub_bin(d, "gh", r'''case "$3" in *pull/1) echo '{"state":"MERGED","title":"One"}';; *) exit 1;; esac''')
        old = os.environ["PATH"]
        os.environ["PATH"] = f"{d}:{old}"
        try:
            prs = sessions.PRStatus()
            one, two = "https://github.com/a/b/pull/1", "https://github.com/a/b/pull/2"
            prs.want([one, two, "--help", "https://evil.example/a/b/pull/3"])
            wait_for(lambda: prs.version >= 2)
            assert prs.snapshot() == {one: {"state": "merged", "title": "One"}, two: {"state": "unknown", "title": None}}
            v = prs.version
            prs.want([one, two])
            time.sleep(0.2)
            assert prs.version == v  # cached within TTL, not refetched
        finally:
            os.environ["PATH"] = old

def test_iterm_script():
    s = sessions.iterm_script("/x/it's \"q\"", "abc")
    assert s.startswith('tell application "iTerm"')
    assert r'''write text "cd '/x/it'\"'\"'s \"q\"' && claude --resume abc"''' in s, s

CLAUDE_OK = r'''printf '%s\n' "$@" > "$CLAUDE_ARGS"; cat > "$CLAUDE_IN"; echo '{"is_error":false,"result":"Fixed the login bug."}' '''
CLAUDE_OK_EVENTS = r'''echo '[{"type":"system","subtype":"init"},{"type":"assistant"},{"type":"result","is_error":false,"result":"Fixed the login bug."}]' '''  # CLI 2.1.x prints the event stream
CLAUDE_FAIL_EVENTS = r'''echo '[{"type":"system","subtype":"init"},{"type":"result","is_error":true,"result":"Not logged in"}]' '''
CLAUDE_FAIL = r'''echo 'Not logged in' >&2; echo '{"is_error":true,"result":"Not logged in"}'; exit 1'''

def test_summaries():
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        path = write_fixture(root)
        stub_bin(root, "claude", CLAUDE_OK)
        old = os.environ["PATH"]
        os.environ.update(PATH=f"{root}:{old}", CLAUDE_ARGS=str(root / "args"), CLAUDE_IN=str(root / "in"))
        try:
            text = sessions.transcript_text(path)
            assert "User: Fix the" in text and "Claude: Looking at the Widget" in text
            assert "skill text" not in text and "task-notification" not in text
            assert sessions.claude("hi", "sys") == "Fixed the login bug."
            args = (root / "args").read_text().split("\n")
            for flag in ("-p", "--no-session-persistence", "--setting-sources", "--tools", "--strict-mcp-config"):  # strict: no MCP tools either
                assert flag in args, flag
            assert args[args.index("--tools") + 1] == ""  # no tools: injected instructions have nothing to run
            stub_bin(root, "claude", CLAUDE_OK_EVENTS)  # event-array output: reply is the "result" event
            assert sessions.claude("hi", "sys") == "Fixed the login bug."
            stub_bin(root, "claude", CLAUDE_FAIL_EVENTS)
            try:
                sessions.claude("hi", "sys")
                raise AssertionError("expected RuntimeError")
            except RuntimeError as e:
                assert "Not logged in" in str(e)
            stub_bin(root, "claude", CLAUDE_OK)

            idx = sessions.Index(root)
            idx.refresh()
            cache = root / "cache" / "summaries.json"
            sm = sessions.Summaries(idx, cache)
            sm.IDLE = 10 ** 10
            sm.schedule()
            assert sm.version == 0 and sm.get(SID) is None  # still "active": not summarised yet
            sm.IDLE = 0
            sm.schedule()
            wait_for(lambda: sm.get(SID) == "Fixed the login bug.")
            assert "<transcript>" in (root / "in").read_text()
            assert "- rate limit report: Quota findings" in (root / "in").read_text()  # summary can name the artifact
            assert json.loads(cache.read_text())[SID]["summary"] == "Fixed the login bug."
            v = sm.version
            sm.schedule()
            time.sleep(0.2)
            assert sm.version == v  # cached for this mtime

            # failures are recorded, not retried for the same mtime, and never raise
            stub_bin(root, "claude", CLAUDE_FAIL)
            try:
                sessions.claude("hi", "sys")
                raise AssertionError("expected RuntimeError")
            except RuntimeError as e:
                assert "Not logged in" in str(e)
            os.utime(path, (1, 1_700_000_000))  # past: a future mtime would look "active"
            idx.refresh()
            sm.schedule()
            wait_for(lambda: SID in sm.failed)
            v = sm.version
            sm.schedule()
            time.sleep(0.2)
            assert sm.version == v

            # at most 2 queued at once, so Ctrl-C doesn't drain a long paid queue
            for i in range(5):
                (path.parent / f"extra{i}.jsonl").write_text(path.read_text())
            stub_bin(root, "claude", "sleep 0.5; " + CLAUDE_OK)
            idx.refresh()
            sm2 = sessions.Summaries(idx, root / "cache2.json")
            sm2.IDLE = 0
            sm2.schedule()
            assert len(sm2.pending) <= 2, sm2.pending
            wait_for(lambda: not sm2.pending)

            # corrupt cache -> starts empty
            cache.write_text("{not json")
            assert sessions.Summaries(idx, cache).data == {}
        finally:
            os.environ["PATH"] = old

def test_retrieve():
    docs = [{"id": i, "text": t, "title": i, "cwd": "/x"} for i, t in [
        ("a", "redis migration cluster keys eviction"), ("b", "redis migration cluster failover"),
        ("c", "turnstile captcha widget siteverify"), ("d", "turnstile captcha widget form")]]
    assert [s["id"] for s in sessions.retrieve("how did the redis migration go?", docs)][:2] in (["a", "b"], ["b", "a"])
    assert [s["id"] for s in sessions.retrieve("siteverify", docs)] == ["c"]  # df=1 term still found via substring
    assert sessions.retrieve("zzz", docs) == []

def test_mcp():
    import subprocess, sys
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        write_fixture(root)
        for sid, day, text in [("r1", 5, "redis vacuum"), ("r2", 4, "redis redis redis"),  # newer than SID's session
                               ("p1", 3, "postgres vacuum"), ("p2", 2, "postgres index")]:
            (root / "-Users-x-Development-acme-api" / f"{sid}.jsonl").write_text(json.dumps(
                {"type": "user", "cwd": "/Users/x/Development/acme/db", "timestamp": f"2026-02-0{day}T10:00:00Z", "message": {"content": text}}) + "\n")
        cache = root / "summaries.json"
        cache.write_text(json.dumps({SID: {"mtime": 0, "summary": "Fixed login."}}))
        env = {**os.environ, "CLAUDE_SESSIONS_ROOT": str(root), "CLAUDE_SESSIONS_CACHE": str(cache)}
        call = lambda i, name, args: {"jsonrpc": "2.0", "id": i, "method": "tools/call", "params": {"name": name, "arguments": args}}
        msgs = [
            {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2025-06-18", "capabilities": {}, "clientInfo": {"name": "t", "version": "0"}}},
            {"jsonrpc": "2.0", "method": "notifications/initialized"},
            {"jsonrpc": "2.0", "id": 2, "method": "server/discover"},
            {"jsonrpc": "2.0", "id": 3, "method": "tools/list"},
            call(4, "search_sessions", {"query": "widget"}),
            call(5, "get_session", {"id": SID}),
            call(6, "sessions_for_file", {"path": "/a/b.py"}),
            call(7, "recent_sessions", {"days": 100000}),
            call(8, "session_digest", {"week_offset": 0}),
            call(9, "get_session", {"id": "nope"}),
            call(10, "get_session", {"bogus": 1}),
            {"jsonrpc": "2.0", "id": 11, "method": "nope/nope"},
            call(12, "no_such_tool", {}),
            call(13, "search_sessions", {"query": "ABC-123"}),  # tokenises to "abc" only
            call(14, "search_sessions", {"query": "4242"}),  # no tokens at all
            call(15, "search_sessions", {"query": "4242", "limit": 1}),  # verbatim hit beats newer sessions
            call(16, "search_sessions", {"query": "redis", "limit": 1}),  # more hits than limit: TF-IDF order, not newest
            call(17, "search_sessions", {"query": "  "}),
        ]
        inp = "\n".join(json.dumps(m) for m in msgs) + "\nnot json\n"
        r = subprocess.run([sys.executable, str(Path(__file__).resolve().parent / "mcp_server.py")],
                           input=inp, capture_output=True, text=True, timeout=30, env=env)
        lines = r.stdout.splitlines()
        assert len(lines) == 18, r.stdout + r.stderr  # 19 messages minus 1 notification
        out = {m.get("id"): m for m in map(json.loads, lines)}
        text = lambda i: json.loads(out[i]["result"]["content"][0]["text"])
        assert out[1]["result"]["protocolVersion"] == "2025-06-18"
        assert "tools" in out[2]["result"]["capabilities"]
        assert out[3]["result"]["cacheScope"] == "private" and isinstance(out[3]["result"]["ttlMs"], int)  # 2026-07-28 schema
        assert {t["name"] for t in out[3]["result"]["tools"]} == {"search_sessions", "get_session", "sessions_for_file", "recent_sessions", "session_digest", "live_sessions"}
        assert text(4)[0]["id"] == SID and text(4)[0]["summary"] == "Fixed login."
        g = text(5)
        assert "User: Fix the" in g["transcript"] and g["files"] == ["/a/b.py"] and "claude --resume" in g["resume"]
        assert [x["id"] for x in text(6)] == [SID]
        assert SID in [x["id"] for x in text(7)]
        assert {"from", "to", "sessions", "groups"} <= set(text(8))
        assert out[9]["result"]["isError"] and out[10]["result"]["isError"] and out[12]["result"]["isError"]
        assert out[11]["error"]["code"] == -32601
        assert out[None]["error"]["code"] == -32700
        for i, ident in ((13, "abc-123"), (14, "4242")):  # exact identifiers: found, snippet shows them
            assert text(i) and text(i)[0]["id"] == SID and ident in text(i)[0]["snippet"], text(i)
        assert [x["id"] for x in text(15)] == [SID]
        assert [x["id"] for x in text(16)] == ["r2"], text(16)
        assert text(17) == []

def test_http():
    import threading, urllib.request, urllib.error, http.client
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        write_fixture(root)
        stub = root / "bin"
        stub.mkdir()
        stub_bin(stub, "gh", """echo '{"state":"OPEN","title":"T"}'""")
        stub_bin(stub, "osascript", 'printf "%s" "$2" > "$OSA_OUT"')
        stub_bin(stub, "claude", CLAUDE_OK)
        old_path = os.environ["PATH"]
        os.environ["PATH"] = f"{stub}:{old_path}"
        os.environ["OSA_OUT"] = str(root / "osa.txt")
        os.environ["CLAUDE_ARGS"] = str(root / "args")
        os.environ["CLAUDE_IN"] = str(root / "in")
        idx = sessions.Index(root)
        idx.refresh()
        dist = root / "dist"
        (dist / "assets").mkdir(parents=True)
        (dist / "index.html").write_text("<h1>app</h1>")
        (dist / "assets" / "a.js").write_text("console.log(1)")
        sessions.DIST = dist
        summaries = sessions.Summaries(idx, root / "cache" / "summaries.json")
        summaries.IDLE = 0
        srv = sessions.make_server(idx, 0, summaries=summaries)
        port = srv.server_address[1]
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        base = f"http://127.0.0.1:{port}"
        get = lambda p: json.loads(urllib.request.urlopen(base + p).read())
        try:
            assert [s["id"] for s in get("/api/sessions")] == [SID]
            assert get("/api/search?q=widget")[0]["id"] == SID
            assert get(f"/api/session/{SID}")["summary"]["id"] == SID
            assert set(get("/api/version")) == {"sessions", "prs", "summaries"}
            wait_for(lambda: [s["summary"] for s in get("/api/sessions")] == ["Fixed the login bug."])
            pr7 = "https://github.com/acme/api/pull/7"
            wait_for(lambda: get("/api/prs").get(pr7, {}).get("state") == "open")
            def post(p, origin):
                return urllib.request.urlopen(urllib.request.Request(
                    base + p, data=b"", method="POST", headers={"Origin": origin} if origin else {}))
            ok = f"http://127.0.0.1:{port}"
            assert json.loads(post(f"/api/resume/{SID}", ok).read()) == {"ok": True}
            assert (root / "osa.txt").read_text() == sessions.iterm_script("/Users/x/Development/acme/api", SID)
            for p, o, code in ((f"/api/resume/{SID}", None, 403), (f"/api/resume/{SID}", "http://evil.example", 403),
                               ("/api/resume/nope", ok, 404), ("/api/nope", ok, 404)):
                try:
                    post(p, o)
                    raise AssertionError((p, o))
                except urllib.error.HTTPError as e:
                    assert e.code == code, (p, o, e.code)
            def post_json(p, obj, origin=ok):
                return json.loads(urllib.request.urlopen(urllib.request.Request(
                    base + p, data=json.dumps(obj).encode(), method="POST",
                    headers={"Origin": origin, "Content-Type": "application/json"})).read())
            ans = post_json("/api/ask", {"q": "what about the widget?"})
            assert ans == {"answer": "Fixed the login bug.", "sources": [SID]}
            assert "<sessions>" in (root / "in").read_text() and "widget" in (root / "in").read_text().lower()
            dig = post_json("/api/digest", {"from": "2026-01-01T00:00:00.000Z", "to": "2026-01-08T00:00:00.000Z"})
            assert dig == {"markdown": "Fixed the login bug."}
            for p, obj, code in (("/api/ask", {"q": ""}, 400), ("/api/ask", {"q": "x" * 501}, 400),
                                 ("/api/digest", {"from": "yesterday", "to": "now"}, 400)):
                try:
                    post_json(p, obj)
                    raise AssertionError(p)
                except urllib.error.HTTPError as e:
                    assert e.code == code, (p, obj, e.code)
            for p in ("/api/ask", "/api/digest"):
                try:
                    post_json(p, {"q": "x"}, origin="http://evil.example")
                    raise AssertionError(p)
                except urllib.error.HTTPError as e:
                    assert e.code == 403
            stub_bin(stub, "claude", CLAUDE_FAIL)
            try:
                post_json("/api/ask", {"q": "widget"})
                raise AssertionError("expected 502")
            except urllib.error.HTTPError as e:
                assert e.code == 502 and "Not logged in" in json.loads(e.read())["error"]
            stub_bin(stub, "claude", CLAUDE_OK)
            for bad in ("/api/session/nope", "/api/session/..%2F..%2Fetc%2Fpasswd", "/api/nope"):
                try:
                    urllib.request.urlopen(base + bad)
                    raise AssertionError(bad)
                except urllib.error.HTTPError as e:
                    assert e.code == 404, (bad, e.code)
            assert urllib.request.urlopen(base + "/").read() == b"<h1>app</h1>"
            r = urllib.request.urlopen(base + "/assets/a.js")
            assert r.read() == b"console.log(1)" and "javascript" in r.headers["Content-Type"]
            assert urllib.request.urlopen(base + "/some/route").read() == b"<h1>app</h1>"  # SPA fallback
            for evil in ("/../sessions.py", "/%2e%2e/%2e%2e/etc/passwd", "/assets/../../" + root.name + "/x"):
                c = http.client.HTTPConnection("127.0.0.1", port)
                c.request("GET", evil)
                assert c.getresponse().read() == b"<h1>app</h1>", evil
            c = http.client.HTTPConnection("127.0.0.1", port)
            c.request("GET", "/api/sessions", headers={"Host": "evil.example"})
            assert c.getresponse().status == 403
        finally:
            srv.shutdown()
            os.environ["PATH"] = old_path

def test_backup_restore():
    import io, tarfile
    with tempfile.TemporaryDirectory() as d:
        root, out = Path(d) / "projects", Path(d) / "out"
        path = write_fixture(root)
        sessions.backup(Path(d) / "b.tgz", root)
        path.unlink()
        sub = path.parent / SID / "subagents" / "agent-abc.jsonl"
        sub.write_text("newer")
        assert sessions.restore(Path(d) / "b.tgz", root) == 1  # only the missing file
        assert path.exists() and sub.read_text() == "newer"  # existing file not overwritten
        assert sessions.restore(Path(d) / "b.tgz", out) == 4 and (out / path.parent.name / path.name).exists()  # fresh machine
        evil = Path(d) / "evil.tgz"
        with tarfile.open(evil, "w:gz") as t:
            info = tarfile.TarInfo("../escaped"); info.size = 1
            t.addfile(info, io.BytesIO(b"x"))
        try:
            sessions.restore(evil, root)
            assert False, "path escape not rejected"
        except tarfile.FilterError:
            pass
        assert not (Path(d) / "escaped").exists()

AGENTS = [{"pid": 4242, "cwd": "/Users/x/Development/acme/api", "kind": "interactive", "startedAt": 1, "sessionId": SID,
           "name": "api-fix", "status": "waiting", "waitingFor": "input needed", "state": "running"},
          {"pid": 4343, "cwd": "/tmp", "kind": "interactive", "startedAt": 2, "sessionId": "no-transcript", "name": "other", "status": "idle"}]
# fake claude: answers `agents --json` from $CLAUDE_AGENTS; fake ps prints a pid/ppid/tty table: its caller's parent is
# $PS_PPID, or $PS_MID whose parent is $PS_PPID, so the session is two processes up; session 4242 is on $PS_TTY
CLAUDE_AGENTS = r"""if [ "$1" = agents ]; then cat > /dev/null; cat "$CLAUDE_AGENTS"; exit $?; fi; echo '{"is_error":false,"result":"x"}' """
PS_STUB = r"""cat > /dev/null; [ "$*" = "-A -o pid= -o ppid= -o tty=" ] || exit 1
echo "  $PPID ${PS_MID:-${PS_PPID:-1}} ttys009"; [ -n "$PS_MID" ] && echo "$PS_MID $PS_PPID ??"
echo "4242 1 $PS_TTY"; echo "4343 1 ??"; echo "garbage line"; echo "x 1 ttys001" """

def test_live():
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        stub_bin(root, "claude", CLAUDE_AGENTS)
        stub_bin(root, "ps", PS_STUB)
        old = os.environ["PATH"]
        os.environ.update(PATH=f"{root}:{old}", CLAUDE_AGENTS=str(root / "agents.json"), PS_TTY="ttys002  ")
        try:
            (root / "agents.json").write_text(json.dumps(AGENTS))
            assert sessions.live_agents() == AGENTS
            for bad in ('{"not": "a list"}', "not json", json.dumps([1, "x", AGENTS[0]])):
                (root / "agents.json").write_text(bad)
                assert sessions.live_agents() == ([AGENTS[0]] if bad.startswith("[") else [])  # non-dict entries dropped
            (root / "agents.json").unlink()  # cat fails -> non-zero exit
            assert sessions.live_agents() == []
            procs = sessions.processes()
            assert procs[4242] == (1, "ttys002") and procs[4343] == (1, "") and procs[os.getpid()][1] == "ttys009"
            assert len(procs) == 3  # lines that aren't pid ppid tty are skipped
            for none in ("??", "", "ttys002; rm -rf /", "/dev/ttys002", "pts/0"):
                os.environ["PS_TTY"] = none
                assert sessions.processes().get(4242, (1, ""))[1] == "", none
        finally:
            os.environ["PATH"] = old
        os.environ["PATH"] = str(root / "empty")  # no claude, no ps on PATH
        try:
            assert sessions.live_agents() == [] and sessions.processes() == {}
        finally:
            os.environ["PATH"] = old

def _tail(d, recs, name="t.jsonl"):
    p = Path(d) / name
    p.write_text("\n".join(json.dumps(r) for r in recs) + "\n")
    return sessions.tail_state(p, chunk=4096)

def test_tail_state():
    u = lambda ts, content: {"type": "user", "timestamp": ts, "message": {"content": content}}
    a = lambda ts, *blocks: {"type": "assistant", "timestamp": ts, "message": {"content": list(blocks)}}
    use = lambda i, name, inp=None: {"type": "tool_use", "id": i, "name": name, "input": inp or {}}
    res = lambda i: {"type": "tool_result", "tool_use_id": i, "content": "ok"}
    text = {"type": "text", "text": "done"}
    noise = [{"type": "last-prompt"}, {"type": "custom-title"}, {"type": "bridge-session"}]
    with tempfile.TemporaryDirectory() as d:
        q = {"questions": [{"question": "Which wording for the PR body?"}]}
        cases = {
            "question": ([u("T1", "go"), a("T2", text), a("T3", use("q1", "AskUserQuestion", q))] + noise,
                         ("T3", {"tool": "AskUserQuestion", "question": "Which wording for the PR body?"})),
            "plan approval": ([u("T1", "go"), a("T2", use("p1", "ExitPlanMode"))], ("T2", {"tool": "ExitPlanMode", "question": None})),
            "permission prompt": ([u("T1", "go"), a("T2", use("b1", "Bash", {"command": "rm x"}))], ("T2", {"tool": "Bash", "question": None})),
            "parallel, one outstanding": ([u("T1", "go"), a("T2", use("r1", "Read"), use("b2", "Bash")), u("T3", [res("r1")])],
                                          ("T3", {"tool": "Bash", "question": None})),
            "finished turn": ([u("T1", "go"), a("T2", use("r1", "Read")), u("T3", [res("r1")]), a("T4", text)] + noise, ("T4", None)),
            "old unanswered call before a new prompt": ([a("T1", use("x1", "Bash")), u("T2", "never mind"), a("T3", text)], ("T3", None)),
            "interrupted": ([a("T1", use("x1", "Bash")), u("T2", "[Request interrupted by user]")], ("T2", None)),
            "sidechain ignored": ([u("T1", "go"), a("T2", text), {**a("T9", use("s1", "Bash")), "isSidechain": True}], ("T2", None)),
            "no messages": (noise, (None, None)),
            "parallel, two outstanding": ([u("T1", "go"), a("T2", use("r1", "Read"), use("b2", "Bash"))], ("T2", {"tool": "Bash", "question": None})),
            "list as an id": ([u("T1", "go"), a("T2", {"type": "tool_use", "id": ["x"], "name": "Bash", "input": {}}), u("T3", [{"type": "tool_result", "tool_use_id": {"y": 1}}])],
                              ("T3", None)),
            "big trailing record": ([u("T1", "go"), a("T2", use("q1", "AskUserQuestion", q)), {"type": "api-request-blob", "blob": "x" * 50_000}],
                                    ("T2", {"tool": "AskUserQuestion", "question": "Which wording for the PR body?"})),
            "blocks with no id": ([u("T1", "go"), a("T2", {"type": "tool_use", "name": "Edit", "input": {}}), u("T3", [{"type": "tool_result", "content": "x"}])], ("T3", None)),
            "injected context after a tool call": ([u("T1", "go"), a("T2", use("b1", "Bash")), {**u("T3", "<system-reminder>x</system-reminder>"), "isMeta": True}],
                                                   ("T3", {"tool": "Bash", "question": None})),
            "malformed question input": ([u("T1", "go"), a("T2", use("q1", "AskUserQuestion", {"questions": "nope"}))],
                                         ("T2", {"tool": "AskUserQuestion", "question": None})),
        }
        for name, (recs, (ts, pending)) in cases.items():
            got = _tail(d, recs)
            assert (got["lastMessageAt"], got["pending"]) == (ts, pending), name
            assert got["contextTokens"] is None and got["lastTurnTokens"] is None, name  # these fixtures carry no usage
            assert got["idleSince"] == ts and got["permissionMode"] is None, name  # no peer turns, no mode records
        none = {"lastMessageAt": None, "pending": None, "contextTokens": None, "lastTurnTokens": None,
                "idleSince": None, "permissionMode": None}
        assert sessions.EMPTY_TAIL == none
        (Path(d) / "empty.jsonl").write_text("")
        assert sessions.tail_state(Path(d) / "empty.jsonl") == none
        assert sessions.tail_state(Path(d) / "missing.jsonl") == none
        # token usage: context size is the newest assistant call's input; the last turn sums each call once
        def call(ts, mid, inp, read, write, out, *blocks):
            return {"type": "assistant", "timestamp": ts, "message": {"id": mid, "content": list(blocks or [text]),
                    "usage": {"input_tokens": inp, "cache_read_input_tokens": read, "cache_creation_input_tokens": write, "output_tokens": out}}}
        woken = [u("T0", "old prompt"), call("T1", "m0", 9, 9000, 9, 9),
                 u("T2", "status check"), call("T3", "m1", 4, 29488, 681662, 515, use("s1", "SendMessage")),
                 call("T3", "m1", 4, 29488, 681662, 515),  # one API call split over two records
                 u("T4", [res("s1")]), call("T5", "m2", 2, 711150, 747, 138)]
        got = _tail(d, woken)
        assert got["contextTokens"] == 2 + 711150 + 747
        assert got["lastTurnTokens"] == {"input": 6, "cacheRead": 740638, "cacheWrite": 682409, "output": 653}
        got = _tail(d, woken + [u("T6", "next prompt, no answer yet")])
        assert got["contextTokens"] == 2 + 711150 + 747 and got["lastTurnTokens"] is None  # nothing since the last prompt
        got = _tail(d, [u("T1", "go"), {"type": "assistant", "timestamp": "T2", "message": {"content": [text], "usage": {"input_tokens": "x"}}}])
        assert got["contextTokens"] is None and got["lastTurnTokens"] is None  # malformed usage is ignored
        # turns: newer CLIs mark each turn's first record with turnPosition and say who started it. A message
        # from another session is isMeta, but it starts a turn; idleSince ignores the turns peers started.
        human = lambda ts, n: {**u(ts, "do the work"), "turnPosition": {"promptIndex": n, "turnIndex": n}, "turnOrigin": "human"}
        peer = lambda ts, n: {**u(ts, "Another Claude session sent a message: status?"), "isMeta": True,
                              "turnPosition": {"promptIndex": n, "turnIndex": n}, "turnOrigin": "peer"}
        work = [human("T1", 1), call("T2", "w1", 5, 100, 5, 50, use("b1", "Bash")), u("T3", [res("b1")]), call("T4", "w2", 5, 200, 5, 60)]
        asked = work + [peer("T5", 2), call("T6", "p1", 4, 300, 700000, 500), peer("T7", 3), call("T8", "p2", 2, 700300, 10, 400)]
        got = _tail(d, asked)
        assert got["lastMessageAt"] == "T8" and got["idleSince"] == "T4"   # two status exchanges later, still idle since T4
        assert got["lastTurnTokens"] == {"input": 2, "cacheRead": 700300, "cacheWrite": 10, "output": 400}  # the last wake only
        assert got["pending"] is None and got["contextTokens"] == 2 + 700300 + 10
        got = _tail(d, work)
        assert got["idleSince"] == "T4" and got["lastTurnTokens"] == {"input": 10, "cacheRead": 300, "cacheWrite": 10, "output": 110}
        far = work + [{"type": "api-request-blob", "blob": "x" * 20_000}, peer("T5", 2), call("T6", "p1", 4, 300, 7, 500)]
        got = _tail(d, far)  # the first 4096-byte window holds only the peer turn: keep widening for the real one
        assert got["lastMessageAt"] == "T6" and got["idleSince"] == "T4"
        got = _tail(d, [human("T1", 1), {"type": "assistant", "timestamp": "T2", "message": {"content": [text], "usage": {}}}])
        assert got["contextTokens"] is None  # an empty or all-zero usage block is not a context size
        got = _tail(d, [human("T1", 1), call("T2", "z", 0, 0, 0, 0)])
        assert got["contextTokens"] is None
        got = _tail(d, [peer("T1", 1), call("T2", "p1", 1, 1, 1, 1)])
        assert got["idleSince"] == "T2"  # nothing but peer turns: fall back to the last message
        got = _tail(d, asked + [{"type": "permission-mode", "permissionMode": "default"}, {"type": "permission-mode", "permissionMode": "auto"}])
        assert got["permissionMode"] == "auto"  # the newest record wins
        got = _tail(d, [{**human("T1", 1), "permissionMode": "acceptEdits"}, call("T2", "w1", 1, 1, 1, 1)])
        assert got["permissionMode"] == "acceptEdits"  # user records carry it too
        # with markers, an unmarked user record (a prompt typed while a tool runs, an interruption, a task
        # notification) is part of the turn, not the start of one
        typed = [human("T1", 1), a("T2", use("b1", "Bash")), u("T3", "also do X")]
        got = _tail(d, typed)
        assert got["pending"] == {"tool": "Bash", "question": None} and got["idleSince"] == "T3"
        long = [human("T1", 1), {"type": "api-request-blob", "blob": "x" * 20_000}, call("T2", "w", 1, 1, 1, 1, use("b1", "Bash")),
                {**u("T3", "<task-notification>"), "permissionMode": "auto"}]
        got = _tail(d, long)  # the marker is outside the first window: widen to find it before trusting the heuristic
        assert got["pending"] == {"tool": "Bash", "question": None} and got["idleSince"] == "T3"
        got = _tail(d, typed[1:])  # no markers at all: the old heuristic, so 'also do X' starts a turn
        assert got["pending"] is None
        # context size and mode further back than the turn's start: keep widening for them too
        blob = {"type": "api-request-blob", "blob": "x" * 20_000}
        got = _tail(d, [{"type": "permission-mode", "permissionMode": "plan"}, call("T0", "o", 1, 2, 3, 4), blob,
                        human("T1", 1), a("T2", text)])
        assert got["permissionMode"] == "plan" and got["contextTokens"] == 6 and got["idleSince"] == "T2"
        # ...but only up to the cap: a transcript of nothing but peer turns stops there and falls back
        p = Path(d) / "peers.jsonl"
        p.write_text("\n".join(json.dumps(r) for r in [human("T0", 0), call("T0", "h", 1, 1, 1, 1)]
                               + [x for i in range(1, 400) for x in (peer(f"T{i}", i), call(f"T{i}", f"p{i}", 1, 1, 1, 1))]) + "\n")
        got = sessions.tail_state(p, chunk=4096, cap=16384)
        assert got["idleSince"] == got["lastMessageAt"] == "T399"
        assert sessions.tail_state(p, chunk=4096)["idleSince"] == "T0"  # under the default cap it is found

def test_mcp_live():
    import subprocess, sys
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        write_fixture(root)
        stub_bin(root, "claude", CLAUDE_AGENTS)
        stub_bin(root, "ps", PS_STUB)
        (root / "agents.json").write_text(json.dumps(AGENTS + [{"pid": 4444, "sessionId": "*", "name": "evil", "status": "idle"}]))
        cache = root / "summaries.json"
        cache.write_text(json.dumps({SID: {"mtime": 0, "summary": "Fixed login."}}))
        reg = root / "registry"  # Claude Code's per-process session files; only the Remote Control id is read
        reg.mkdir()
        (reg / "4242.json").write_text(json.dumps({"pid": 4242, "bridgeSessionId": "session_01AbC"}))
        (reg / "4343.json").write_text(json.dumps({"pid": 4343, "bridgeSessionId": "../evil?x=1"}))
        base = {**os.environ, "PATH": f"{root}:{os.environ['PATH']}", "CLAUDE_SESSIONS_ROOT": str(root),
                "CLAUDE_SESSIONS_REGISTRY": str(reg),
                "CLAUDE_SESSIONS_CACHE": str(cache), "CLAUDE_AGENTS": str(root / "agents.json"), "PS_TTY": "ttys002"}
        def run(**env):
            msg = {"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": "live_sessions", "arguments": {}}}
            pings = "".join(json.dumps({"jsonrpc": "2.0", "id": i, "method": "ping"}) + "\n" for i in range(2, 5002))
            r = subprocess.run([sys.executable, "mcp_server.py"], input=json.dumps(msg) + "\n" + pings,
                               capture_output=True, text=True, env={**base, **env}, timeout=60, cwd=Path(__file__).parent)
            replies = [json.loads(line) for line in r.stdout.splitlines()]
            # ~200 KB of requests, more than the server reads ahead: the CLI and ps must not eat the rest
            assert [x["id"] for x in replies] == list(range(1, 5002)), len(replies)
            res = replies[0]["result"]
            assert not res.get("isError"), res
            return json.loads(res["content"][0]["text"])
        rows = run(PS_PPID="4242", PS_MID="7001")  # the session is the server's grandparent
        assert [r["name"] for r in rows] == ["api-fix", "other", "evil"]
        assert set(rows[0]) == {"name", "sessionId", "cwd", "kind", "status", "waitingFor", "tty", "self", "lastMessageAt", "pending", "contextTokens", "lastTurnTokens", "idleSince", "permissionMode", "summary", "url", "state"}
        fix = rows[0]
        assert fix["self"] is True and fix["tty"] == "ttys002" and fix["summary"] == "Fixed login."
        assert fix["status"] == "waiting" and fix["waitingFor"] == "input needed"
        assert fix["lastMessageAt"] == "2026-01-01T10:02:20Z" and fix["pending"] is None  # t1/t2 answered; blocks with no id are ignored
        other = rows[1]
        assert other["self"] is False and other["waitingFor"] is None and other["summary"] is None
        assert other["lastMessageAt"] is None and other["pending"] is None  # running, no transcript
        assert other["contextTokens"] is None and other["lastTurnTokens"] is None
        assert fix["idleSince"] == "2026-01-01T10:02:20Z" and other["idleSince"] is None and other["permissionMode"] is None
        assert fix["state"] == "running" and other["state"] is None
        assert fix["url"] == "https://claude.ai/code/session_01AbC"
        assert other["url"] is None and rows[2]["url"] is None  # an id that is not session_<word> / no registry file
        assert rows[2]["lastMessageAt"] is None  # a sessionId that is not [\w-]+ is never used in a glob
        assert rows[2]["sessionId"] is None  # and is not handed on to a caller that might put it in a command
        assert all(r["self"] is False for r in run(PS_PPID="1"))  # no listed pid among the ancestors
        (root / "-Users-x-Development-acme-api" / f"{SID}.jsonl").write_text('{"type": "assistant", "timestamp": 5, "message": {"content": 7}}\n')
        odd = run(PS_PPID="1")  # a transcript with the wrong shapes: every row still comes back
        assert [r["name"] for r in odd] == ["api-fix", "other", "evil"] and odd[0]["lastMessageAt"] is None
        assert run(PS_PPID="1", CLAUDE_AGENTS=str(root / "missing")) == []
        # resumed from another folder: a stale copy elsewhere loses to the one being written
        stale = root / "-Users-x-old" / f"{SID}.jsonl"
        stale.parent.mkdir()
        stale.write_text('{"type": "assistant", "timestamp": "2020-01-01T00:00:00Z", "message": {"content": []}}\n')
        live = root / "-Users-x-Development-acme-api" / f"{SID}.jsonl"
        live.write_text(json.dumps({"type": "assistant", "timestamp": "2026-02-02T00:00:00Z", "permissionMode": "x; rm -rf ~",
                                    "message": {"content": [{"type": "tool_use", "id": "e", "name": "Bash $(x)", "input": {}}]}}) + "\n")
        os.utime(stale, (1, 1))
        fix = run(PS_PPID="1")[0]
        assert fix["lastMessageAt"] == "2026-02-02T00:00:00Z"
        assert fix["permissionMode"] is None and fix["pending"] == {"tool": None, "question": None}  # not plain words
    import mcp_server  # a reader that raises costs one session its details, never the whole listing
    real = sessions.tail_state
    sessions.tail_state = lambda path: None + 1
    try:
        assert mcp_server._tail("x") == sessions.EMPTY_TAIL
    finally:
        sessions.tail_state = real

if __name__ == "__main__":
    test_backup_restore()
    test_all()
    test_file_keys()
    test_related()
    test_prs()
    test_iterm_script()
    test_summaries()
    test_retrieve()
    test_mcp()
    test_http()
    test_live()
    test_tail_state()
    test_mcp_live()
    print("ok")
