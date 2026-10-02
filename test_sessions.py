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
         "message": {"content": [{"type": "text", "text": "Looking at the Widget"},
                                 {"type": "tool_use", "name": "Edit", "input": {"file_path": "/a/b.py"}},
                                 {"type": "tool_use", "name": "Read", "input": {"file_path": "/a/c.py"}}]}},
        {"type": "user", "timestamp": "2026-01-01T10:02:00Z",
         "message": {"content": [{"type": "tool_result", "content": "secret tool output"}]}},
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
        assert last["role"] == "assistant" and [t["name"] for t in last["tools"]] == ["Edit", "Read"]
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
        ]
        inp = "\n".join(json.dumps(m) for m in msgs) + "\nnot json\n"
        r = subprocess.run([sys.executable, str(Path(__file__).resolve().parent / "mcp_server.py")],
                           input=inp, capture_output=True, text=True, timeout=30, env=env)
        lines = r.stdout.splitlines()
        assert len(lines) == 13, r.stdout + r.stderr  # 14 messages minus 1 notification
        out = {m.get("id"): m for m in map(json.loads, lines)}
        text = lambda i: json.loads(out[i]["result"]["content"][0]["text"])
        assert out[1]["result"]["protocolVersion"] == "2025-06-18"
        assert "tools" in out[2]["result"]["capabilities"]
        assert out[3]["result"]["cacheScope"] == "private" and isinstance(out[3]["result"]["ttlMs"], int)  # 2026-07-28 schema
        assert {t["name"] for t in out[3]["result"]["tools"]} == {"search_sessions", "get_session", "sessions_for_file", "recent_sessions", "session_digest"}
        assert text(4)[0]["id"] == SID and text(4)[0]["summary"] == "Fixed login."
        g = text(5)
        assert "User: Fix the" in g["transcript"] and g["files"] == ["/a/b.py"] and "claude --resume" in g["resume"]
        assert [x["id"] for x in text(6)] == [SID]
        assert SID in [x["id"] for x in text(7)]
        assert {"from", "to", "sessions", "groups"} <= set(text(8))
        assert out[9]["result"]["isError"] and out[10]["result"]["isError"] and out[12]["result"]["isError"]
        assert out[11]["error"]["code"] == -32601
        assert out[None]["error"]["code"] == -32700

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
    print("ok")
