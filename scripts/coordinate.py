#!/usr/bin/env python3
"""Publish a declaration and print only changed cooperation information."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile


def command(*args):
    result = subprocess.run(args, capture_output=True, text=True, timeout=15)
    if result.returncode:
        raise RuntimeError(result.stderr.strip() or result.stdout.strip() or str(args))
    return result.stdout.strip()


def identity(agent):
    return {
        "pane_id": agent["pane_id"],
        "terminal_id": agent.get("terminal_id"),
        "session": agent.get("agent_session"),
    }


def read_json(path):
    return json.loads(path.read_text())


def write_json(path, value):
    descriptor, temporary = tempfile.mkstemp(dir=path.parent)
    try:
        with os.fdopen(descriptor, "w") as stream:
            json.dump(value, stream, ensure_ascii=False, separators=(",", ":"))
            stream.write("\n")
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def full_declaration(agent, root):
    tokens = {k: v for k, v in agent.get("tokens", {}).items() if k.startswith("coop_")}
    detail = tokens.get("coop_detail")
    if detail:
        path = Path(detail)
        # Read only this user's helper files, never arbitrary peer-supplied paths.
        if path.parent == root and not path.is_symlink() and path.is_file():
            try:
                if path.stat().st_size > 1_000_000:
                    raise ValueError("detail file too large")
                saved = read_json(path)
                declared = saved["tokens"]
                if saved["identity"] == identity(agent) and all(
                    isinstance(value, str)
                    and isinstance(declared.get(key), str)
                    and declared[key].startswith(value)
                    for key, value in tokens.items()
                ):
                    return declared, saved.get("handoff", ""), "detail"
            except (OSError, ValueError, KeyError, TypeError):
                pass
    return tokens, "", "metadata-only"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pane", default=os.environ.get("HERDR_PANE_ID"))
    parser.add_argument("--task", help="Publish a declaration; omit for a read-only check")
    parser.add_argument("--file", action="append", default=[], help="Claim a file or directory; repeatable")
    parser.add_argument("--state", choices=["working", "negotiating", "done"], default="working")
    parser.add_argument("--note", default="", help="Agreements, test results, or remaining work")
    parser.add_argument("--handoff", default="", help="Checkpoint, agreements, and next action for a replacement session")
    parser.add_argument("--model", default="unknown", help="Current model name; report unknown if unavailable")
    parser.add_argument("--effort", default="unknown", help="Current reasoning effort; report unknown if unavailable")
    parser.add_argument("--full", action="store_true", help="Print the complete current snapshot")
    args = parser.parse_args()
    if not args.pane:
        parser.error("HERDR_PANE_ID is unset; use --pane with a verified pane ID")
    if args.task is None and (args.file or args.note or args.handoff or args.state != "working"):
        parser.error("Publishing options require --task")
    if args.task is not None and not args.task.strip():
        parser.error("--task must not be empty")
    if args.state == "done" and args.file:
        parser.error("A done declaration must release files; omit --file")

    git_paths = command("git", "rev-parse", "--path-format=absolute", "--git-common-dir", "--show-toplevel").splitlines()
    repo, worktree = (str(Path(value).resolve()) for value in git_paths)
    branch = command("git", "rev-parse", "--abbrev-ref", "HEAD")
    if branch == "HEAD":
        branch = "detached:" + command("git", "rev-parse", "HEAD")

    response = json.loads(command("herdr", "agent", "list"))
    agents = response["result"]["agents"]
    own = next((agent for agent in agents if agent["pane_id"] == args.pane), None)
    if own is None:
        raise RuntimeError("The declared pane is absent from herdr; no state was published")

    root = Path(tempfile.gettempdir()) / ("herdr-cooperate-" + str(os.getuid()))
    root.mkdir(mode=0o700, exist_ok=True)
    if root.is_symlink() or root.stat().st_uid != os.getuid() or root.stat().st_mode & 0o077:
        raise RuntimeError("The helper directory must be private and owned by this user")
    scope = os.environ.get("HERDR_SOCKET_PATH", "default") + "\0" + args.pane
    key = hashlib.sha256(scope.encode()).hexdigest()[:16]
    detail_path = root / (key + ".json")
    cache_path = root / (key + ".seen.json")
    try:
        previous = read_json(cache_path)
    except (OSError, ValueError):
        previous = {}
    same_session = previous.get("identity") == identity(own)

    observed, handoff, own_source = full_declaration(own, root)
    location = {"repo": repo, "worktree": worktree, "branch": branch}
    output = location.copy() if args.full or not same_session or previous.get("location") != location else {}
    published = False
    handoff_changed = False
    if args.task is not None:
        desired = {
            "coop_repo": repo, "coop_worktree": worktree, "coop_branch": branch,
            "coop_task": args.task, "coop_files": ",".join(args.file),
            "coop_state": args.state, "coop_note": args.note,
            "coop_model": args.model.strip() or "unknown",
            "coop_effort": args.effort.strip() or "unknown",
            "coop_detail": str(detail_path),
        }
        saved = {"identity": identity(own), "tokens": desired, "files": args.file, "handoff": args.handoff}
        handoff_changed = handoff != args.handoff
        write_json(detail_path, saved)
        # Compare with live metadata too: a cache alone cannot prove publication.
        live = own.get("tokens", {})
        matches_live = all(
            (not value and key not in live)
            or (key in live and isinstance(live[key], str) and value.startswith(live[key]))
            for key, value in desired.items()
        )
        if not (same_session and own_source == "detail" and observed == desired and matches_live):
            report = ["herdr", "pane", "report-metadata", args.pane, "--source", "herdr-cooperate"]
            for name, value in desired.items():
                report.extend(["--token", name + "=" + value])
            command(*report)
            published = True
        observed, handoff = desired, args.handoff
    output["published"] = published
    if not same_session or args.full or published or handoff_changed:
        output["self"] = {"pane_id": args.pane, "declaration": observed, "handoff": handoff}
        if args.task is None and own_source == "metadata-only" and detail_path.exists():
            try:
                prior = read_json(detail_path)
                if prior["identity"]["pane_id"] == args.pane:
                    output["prior_self_unconfirmed"] = prior
            except (OSError, ValueError, KeyError, TypeError):
                pass

    peers = {}
    for agent in agents:
        if agent["pane_id"] == args.pane:
            continue
        tokens, peer_handoff, source = full_declaration(agent, root)
        peer_repo = tokens.get("coop_repo")
        if peer_repo and Path(peer_repo).resolve() != Path(repo) and not (
            source == "metadata-only" and repo.startswith(peer_repo)
        ):
            continue
        # Undeclared peers remain visible; their lack of claims is not permission.
        peers[agent["pane_id"]] = {
            **identity(agent), "declaration": tokens, "handoff": peer_handoff,
            "completeness": source,
        }
    old_peers = previous.get("peers", {})
    output["peers"] = {
        pane: peer for pane, peer in peers.items()
        if args.full or not same_session or old_peers.get(pane) != peer
    }
    output["removed"] = sorted(set(old_peers) - set(peers))
    missing = previous.get("missing", {}).copy()
    for pane in output["removed"]:
        peer = old_peers[pane]
        declaration = peer["declaration"]
        if declaration.get("coop_state") != "done" or declaration.get("coop_files"):
            missing[pane] = peer
    for pane in peers:
        missing.pop(pane, None)
    if missing:
        output["missing_unreleased"] = missing
    output["unchanged"] = len(peers) - len(output["peers"])
    if not output["peers"]:
        del output["peers"]
    if not output["removed"]:
        del output["removed"]
    write_json(cache_path, {"identity": identity(own), "location": location, "peers": peers, "missing": missing})
    print(json.dumps(output, ensure_ascii=False, separators=(",", ":")))


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, KeyError, TypeError, RuntimeError, subprocess.TimeoutExpired) as error:
        print("Coordination failed: " + str(error), file=sys.stderr)
        sys.exit(1)
