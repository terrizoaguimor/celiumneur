#!/usr/bin/env python3
"""Verify the pinned external RTL evidence without redistributing its source."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any


SCHEMA = "celiumneur.external-rtl-audit.v1"
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
GIT_OID_RE = re.compile(r"^[0-9a-f]{40}$")
DEFAULT_MANIFEST = Path(__file__).with_name("source_snapshot.lock.json")
FINDINGS_PATH = Path(__file__).with_name("FINDINGS.md")


class AuditError(RuntimeError):
    """Raised when an audit precondition or evidence check fails."""


def normalized_bytes(path: Path) -> bytes:
    """Return content with platform line endings normalized to LF."""
    return path.read_bytes().replace(b"\r\n", b"\n").replace(b"\r", b"\n")


def digest(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def run_git(repo: Path, *args: str) -> str:
    command = ["git", "-C", str(repo), *args]
    result = subprocess.run(command, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        detail = result.stderr.strip() or result.stdout.strip()
        raise AuditError(f"git failed in {repo}: {' '.join(args)}: {detail}")
    return result.stdout.strip()


def normalize_remote(value: str) -> str:
    remote = value.strip().replace("git@github.com:", "https://github.com/")
    remote = remote.removesuffix("/").removesuffix(".git")
    return remote.casefold()


def require_hex(value: Any, pattern: re.Pattern[str], label: str) -> None:
    if not isinstance(value, str) or pattern.fullmatch(value) is None:
        raise AuditError(f"{label} is not a valid hexadecimal identifier")


def validate_manifest(manifest: dict[str, Any]) -> None:
    if manifest.get("schema") != SCHEMA:
        raise AuditError(f"unsupported manifest schema: {manifest.get('schema')!r}")

    sources = manifest.get("sources")
    findings = manifest.get("findings")
    if not isinstance(sources, list) or not sources:
        raise AuditError("manifest has no sources")
    if not isinstance(findings, list) or not findings:
        raise AuditError("manifest has no findings")

    source_ids: set[str] = set()
    file_paths: dict[str, set[str]] = {}
    for source in sources:
        source_id = source.get("id")
        if not isinstance(source_id, str) or not source_id:
            raise AuditError("source id must be a non-empty string")
        if source_id in source_ids:
            raise AuditError(f"duplicate source id: {source_id}")
        source_ids.add(source_id)
        require_hex(source.get("commit"), GIT_OID_RE, f"{source_id}.commit")
        require_hex(source.get("tree"), GIT_OID_RE, f"{source_id}.tree")

        license_info = source.get("license")
        if not isinstance(license_info, dict):
            raise AuditError(f"{source_id}.license is missing")
        require_hex(
            license_info.get("normalized_sha256"),
            SHA256_RE,
            f"{source_id}.license.normalized_sha256",
        )

        paths: set[str] = set()
        for evidence_file in source.get("files", []):
            path = evidence_file.get("path")
            if not isinstance(path, str) or not path:
                raise AuditError(f"{source_id} has an invalid evidence path")
            if path in paths:
                raise AuditError(f"{source_id} repeats evidence path {path}")
            paths.add(path)
            require_hex(
                evidence_file.get("normalized_sha256"),
                SHA256_RE,
                f"{source_id}:{path}",
            )
        file_paths[source_id] = paths

    finding_ids: set[str] = set()
    findings_text = FINDINGS_PATH.read_text(encoding="utf-8")
    for finding in findings:
        finding_id = finding.get("id")
        source_id = finding.get("source")
        if not isinstance(finding_id, str) or not finding_id:
            raise AuditError("finding id must be a non-empty string")
        if finding_id in finding_ids:
            raise AuditError(f"duplicate finding id: {finding_id}")
        finding_ids.add(finding_id)
        if source_id not in source_ids:
            raise AuditError(f"{finding_id} references unknown source {source_id}")
        if f"## {finding_id} " not in findings_text:
            raise AuditError(f"{finding_id} is not documented in FINDINGS.md")

        anchors = finding.get("anchors")
        if not isinstance(anchors, list) or not anchors:
            raise AuditError(f"{finding_id} has no evidence anchors")
        for anchor in anchors:
            path = anchor.get("path")
            if path not in file_paths[source_id]:
                raise AuditError(f"{finding_id} anchor is not in the source file lock: {path}")
            start = anchor.get("start")
            end = anchor.get("end")
            if not isinstance(start, int) or not isinstance(end, int) or start < 1 or end < start:
                raise AuditError(f"{finding_id} has an invalid line range {start}:{end}")
            require_hex(
                anchor.get("normalized_sha256"),
                SHA256_RE,
                f"{finding_id}:{path}:{start}-{end}",
            )


def clone_source(source: dict[str, Any], clone_root: Path) -> Path:
    target = clone_root / source["directory"]
    if target.exists():
        return target

    clone_root.mkdir(parents=True, exist_ok=True)
    command = [
        "git",
        "clone",
        "--filter=blob:none",
        "--no-checkout",
        source["repository"],
        str(target),
    ]
    result = subprocess.run(command, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        detail = result.stderr.strip() or result.stdout.strip()
        raise AuditError(f"clone failed for {source['id']}: {detail}")

    sparse_paths = [source["license"]["path"]]
    sparse_paths.extend(item["path"] for item in source["files"])
    run_git(target, "sparse-checkout", "init", "--no-cone")
    run_git(target, "sparse-checkout", "set", "--no-cone", *sparse_paths)
    run_git(target, "checkout", "--detach", source["commit"])
    return target


def verify_hash(path: Path, expected: str, label: str) -> None:
    if not path.is_file():
        raise AuditError(f"missing {label}: {path}")
    actual = digest(normalized_bytes(path))
    if actual != expected:
        raise AuditError(f"hash drift for {label}: expected {expected}, got {actual}")


def verify_anchor(repo: Path, finding_id: str, anchor: dict[str, Any]) -> None:
    path = repo / anchor["path"]
    try:
        lines = normalized_bytes(path).decode("utf-8").splitlines()
    except UnicodeDecodeError as exc:
        raise AuditError(f"{finding_id} evidence is not UTF-8: {path}") from exc

    start = anchor["start"]
    end = anchor["end"]
    if end > len(lines):
        raise AuditError(f"{finding_id} range {start}:{end} exceeds {path} ({len(lines)} lines)")
    payload = ("\n".join(lines[start - 1 : end]) + "\n").encode("utf-8")
    actual = digest(payload)
    expected = anchor["normalized_sha256"]
    if actual != expected:
        raise AuditError(
            f"anchor drift for {finding_id} at {anchor['path']}:{start}-{end}: "
            f"expected {expected}, got {actual}"
        )


def verify_source(
    source: dict[str, Any], findings: list[dict[str, Any]], repo: Path
) -> None:
    if not repo.is_dir():
        raise AuditError(f"missing source directory for {source['id']}: {repo}")

    origin = run_git(repo, "remote", "get-url", "origin")
    if normalize_remote(origin) != normalize_remote(source["repository"]):
        raise AuditError(f"origin drift for {source['id']}: {origin}")
    head = run_git(repo, "rev-parse", "HEAD")
    if head != source["commit"]:
        raise AuditError(f"commit drift for {source['id']}: expected {source['commit']}, got {head}")
    tree = run_git(repo, "rev-parse", "HEAD^{tree}")
    if tree != source["tree"]:
        raise AuditError(f"tree drift for {source['id']}: expected {source['tree']}, got {tree}")
    dirty = run_git(repo, "status", "--porcelain")
    if dirty:
        raise AuditError(f"source checkout is dirty for {source['id']}")

    license_info = source["license"]
    verify_hash(
        repo / license_info["path"],
        license_info["normalized_sha256"],
        f"{source['id']} license",
    )
    for evidence_file in source["files"]:
        verify_hash(
            repo / evidence_file["path"],
            evidence_file["normalized_sha256"],
            f"{source['id']}:{evidence_file['path']}",
        )

    source_findings = [finding for finding in findings if finding["source"] == source["id"]]
    for finding in source_findings:
        for anchor in finding["anchors"]:
            verify_anchor(repo, finding["id"], anchor)
    print(
        f"PASS source={source['id']} commit={head} "
        f"files={len(source['files'])} findings={len(source_findings)}"
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument(
        "--validate-manifest",
        action="store_true",
        help="validate only the local lock and findings index",
    )
    mode.add_argument(
        "--source-root",
        type=Path,
        help="verify existing exact source checkouts under this directory",
    )
    mode.add_argument(
        "--clone-dir",
        type=Path,
        help="sparse-clone missing pinned sources here, then verify them",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
        validate_manifest(manifest)
        manifest_hash = digest(normalized_bytes(args.manifest))
        print(
            f"PASS manifest schema={SCHEMA} sources={len(manifest['sources'])} "
            f"findings={len(manifest['findings'])} sha256={manifest_hash}"
        )
        if args.validate_manifest:
            return 0

        root = args.source_root or args.clone_dir
        assert root is not None
        for source in manifest["sources"]:
            repo = (
                clone_source(source, root)
                if args.clone_dir is not None
                else root / source["directory"]
            )
            verify_source(source, manifest["findings"], repo)
        print(f"PASS external-audit sources={len(manifest['sources'])} findings={len(manifest['findings'])}")
        return 0
    except (AuditError, FileNotFoundError, json.JSONDecodeError) as exc:
        print(f"FAIL external-audit: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
