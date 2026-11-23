#!/usr/bin/env python3
"""Offline-fetch OpenMotion native components for slow / blocked networks.

Reads url + sha256 from the installed app's runtime-lock.json, downloads from
fast mirrors (with parallel HTTP ranges where supported), verifies sha256 and
places the archive where the installer expects it:

    <OM_HOME>/cache/native/downloads/<sha256>.zip

The OpenMotion installer (scripts/runtime-assets.mjs) compares sha256 first:
a matching archive in that directory makes it skip the slow download entirely
and just extract. Run `npm-installer.mjs prepare --home <OM_HOME>` afterwards.

Usage:
    python fetch_om_components.py --app-root <APP_ROOT> [--home <OM_HOME>]
                                  [--components browser,media] [--segments 12]

Only the Agent should run this, and only when nativeRuntimeStatus() reports a
component that is not ready. It never touches project data or personal files.
"""
import argparse
import concurrent.futures
import hashlib
import json
import os
import platform
import re
import shutil
import subprocess
import sys
import tempfile
import time

GITHUB_PROXIES = ["https://gh-proxy.com/", "https://ghfast.top/"]
CHROME_MIRROR = "https://cdn.npmmirror.com/binaries/chrome-for-testing/"


def log(msg):
    print(msg, flush=True)


def curl(args, timeout=300):
    return subprocess.run(
        ["curl", "-sS", "-L", "--connect-timeout", "20", "--max-time", str(timeout)] + args,
        capture_output=True, text=True,
    )


def sha256_of(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def target_key(lock):
    system, machine = platform.system(), platform.machine().lower()
    wanted = "win-x64" if system == "Windows" else "mac-arm64"
    if wanted in lock.get("targets", {}):
        return wanted
    for key, value in lock.get("targets", {}).items():
        if value.get("platform") == system.lower() or key.startswith(system[:3].lower()):
            return key
    raise SystemExit("No matching target for %s / %s; pass --target-key" % (system, machine))


def candidate_urls(component, original):
    """Mirror first, official source last as fallback."""
    if component == "browser" and "/chrome-for-testing-public/" in original:
        tail = original.split("/chrome-for-testing-public/", 1)[1]
        return [CHROME_MIRROR + tail, original]
    if original.startswith("https://github.com/"):
        return [p + original for p in GITHUB_PROXIES] + [original]
    return [original]


def probe(url):
    """Return total size if the endpoint supports byte ranges, else None."""
    r = curl(["-D", "-", "-r", "0-0", "-o", os.devnull, url], timeout=40)
    match = re.search(r"content-range:\s*bytes\s+0-0/(\d+)", r.stdout + r.stderr, re.I)
    if match:
        return int(match.group(1))
    head = curl(["-I", url], timeout=40)
    lengths = re.findall(r"content-length:\s*(\d+)", head.stdout + head.stderr, re.I)
    if lengths and "206" in r.stdout:
        return int(lengths[-1])
    return None


def merge_and_verify(parts, target, expected_sha, total, tmp_dir):
    h = hashlib.sha256()
    with open(target, "wb") as out:
        for index in range(len(parts)):
            with open(parts[index], "rb") as src:
                for chunk in iter(lambda: src.read(1024 * 1024), b""):
                    out.write(chunk)
                    h.update(chunk)
    size = os.path.getsize(target)
    digest = h.hexdigest()
    if size != total or digest != expected_sha:
        os.remove(target)
        raise SystemExit("CHECKSUM MISMATCH: size=%d/%d sha=%s expected=%s\n"
                         "Bad archive removed; do not let the installer extract it."
                         % (size, total, digest, expected_sha))
    for p in parts:
        try:
            os.remove(p)
        except OSError:
            pass
    shutil.rmtree(tmp_dir, ignore_errors=True)
    return size


def fetch_whole(url, target, expected_sha, tmp_dir):
    r = curl(["-o", target, "-w", "%{http_code}", url], timeout=900)
    if r.returncode != 0 or not os.path.exists(target):
        raise SystemExit("Whole-file download failed: rc=%s err=%s"
                         % (r.returncode, (r.stderr or "").strip()[:200]))
    if sha256_of(target) != expected_sha:
        os.remove(target)
        raise SystemExit("CHECKSUM MISMATCH for %s; bad archive removed" % url)
    shutil.rmtree(tmp_dir, ignore_errors=True)
    return os.path.getsize(target)


def fetch_ranged(urls, total, target, expected_sha, segments, tmp_dir):
    step = (total + segments - 1) // segments
    ranges = [(i, i * step, min((i + 1) * step - 1, total - 1)) for i in range(segments)]

    def fetch(seg):
        index, start, end = seg
        out = os.path.join(tmp_dir, "part_%02d.bin" % index)
        expected = end - start + 1
        last = ""
        for attempt in range(6):
            url = urls[(index + attempt) % len(urls)]
            r = curl(["-r", "%d-%d" % (start, end), "-o", out, "-w", "%{http_code}", url])
            size = os.path.getsize(out) if os.path.exists(out) else 0
            if r.returncode == 0 and size == expected:
                return index, out
            last = "rc=%s http=%s size=%s/%s" % (r.returncode, r.stdout.strip(), size, expected)
            log("  retry seg %02d attempt %d: %s" % (index, attempt + 1, last))
        raise RuntimeError("segment %d failed: %s" % (index, last))

    log("Downloading %d bytes in %d parallel segments..." % (total, segments))
    with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:
        results = sorted(pool.map(fetch, ranges))
    parts = [p for _, p in results]
    return merge_and_verify(parts, target, expected_sha, total, tmp_dir)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--app-root", required=True, help="appRoot from install.json")
    ap.add_argument("--home", help="OM_HOME (defaults to grandparent of app-root)")
    ap.add_argument("--components", default="browser,media")
    ap.add_argument("--segments", type=int, default=12)
    ap.add_argument("--target-key", help="override runtime-lock target key")
    args = ap.parse_args()

    app_root = args.app_root.replace("\\", "/")
    home = (args.home or os.path.dirname(os.path.dirname(app_root))).replace("\\", "/")
    lock_path = os.path.join(app_root, "scripts", "runtime-lock.json")
    if not os.path.isfile(lock_path):
        raise SystemExit("runtime-lock.json not found: %s" % lock_path)

    with open(lock_path, encoding="utf-8") as f:
        lock = json.load(f)
    key = args.target_key or target_key(lock)
    spec = lock["targets"][key]
    downloads = os.path.join(home, "cache", "native", "downloads")
    os.makedirs(downloads, exist_ok=True)
    log("OM_HOME : %s" % home)
    log("TARGET  : %s" % key)

    for component in [c.strip() for c in args.components.split(",") if c.strip()]:
        info = spec.get(component)
        if not info or not info.get("url"):
            log("[%s] not pinned for this platform, skipping" % component)
            continue
        expected = info["sha256"]
        target = os.path.join(downloads, expected + ".zip")
        if os.path.isfile(target) and sha256_of(target) == expected:
            log("[%s] already cached and verified, skipping" % component)
            continue

        urls = candidate_urls(component, info["url"])
        log("[%s] sources: %s" % (component, ", ".join(urls)))
        total = None
        for url in urls:
            total = probe(url)
            if total:
                log("[%s] size via %s : %d bytes" % (component, url.split("/")[2], total))
                break
        if not total:
            raise SystemExit("[%s] cannot determine archive size from any source" % component)

        tmp_dir = tempfile.mkdtemp(prefix="om_component_")
        t0 = time.time()
        if args.segments > 1:
            size = fetch_ranged(urls, total, target, expected, args.segments, tmp_dir)
        else:
            size = fetch_whole(urls[0], target, expected, tmp_dir)
        log("[%s] OK %d bytes sha256=%s in %.1fs -> %s"
            % (component, size, expected, time.time() - t0, target))

    log("\nDONE. Next: node <APP_ROOT>/scripts/npm-installer.mjs prepare --home \"%s\"" % home)
    log("Then verify with nativeRuntimeStatus(): browser/media = ready, capabilities.export = true")


if __name__ == "__main__":
    main()
