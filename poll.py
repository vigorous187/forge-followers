#!/usr/bin/env python3
"""Poll Jayden Aj's TikTok + Instagram + YouTube follower counts and publish them
as a single-commit JSON file to vigorous187/forge-followers (branch: main).

The Forge-co talent page fetches
  https://raw.githubusercontent.com/vigorous187/forge-followers/main/followers.json
every page view (cache-busted per 15-min bucket) and animates the counters.

Auth: GitHub writes go through the custom.github connector surrogate exchange
(see ~/workspace/skills/github/SKILL.md). No raw credentials are stored here.
TikTok is scraped anonymously; Instagram is read via the linked instagram-cli.
"""
import json, re, sys, time, urllib.request, urllib.error, subprocess, datetime

sys.path.insert(0, "/opt/hatch/skills/skill-creator/bin")
from dynamic_credentials import add_surrogate_to_request, read_json_response

REPO = "vigorous187/forge-followers"
BRANCH = "main"
GH_API = "https://api.github.com"
IG_ACCOUNT_ID = "17841418593469845"
IG_USERNAME = "jaydenaj"
TT_URL = "https://www.tiktok.com/@jaydenaj"
YT_URL = "https://www.youtube.com/channel/UCaDMmdYFxc5LPtoFbRx3Xlg"
STATE_FILE = "/home/hatch/workspace/forge-followers/state.json"
LOCAL_DIR = "/home/hatch/workspace/forge-followers"


def log(msg):
    ts = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=-4))).strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{ts} EDT] {msg}", flush=True)


def fetch_tiktok(retries=3):
    for attempt in range(retries):
        try:
            req = urllib.request.Request(
                TT_URL,
                headers={
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                                  "AppleWebKit/537.36 (KHTML, like Gecko) "
                                  "Chrome/126.0.0.0 Safari/537.36",
                    "Accept-Language": "en-US,en;q=0.9",
                },
            )
            with urllib.request.urlopen(req, timeout=25) as resp:
                html = resp.read().decode("utf-8", "replace")
            m = re.search(r'"followerCount":(\d+)', html)
            if m:
                return int(m.group(1))
            log(f"tiktok: followerCount not found in page (attempt {attempt+1})")
        except Exception as exc:  # noqa: BLE001
            log(f"tiktok fetch failed (attempt {attempt+1}): {exc}")
        time.sleep(5 * (attempt + 1))
    return None


def fetch_instagram(retries=2):
    for attempt in range(retries):
        try:
            out = subprocess.run(
                ["instagram-cli", "profile", "--account-id", IG_ACCOUNT_ID,
                 "--username", IG_USERNAME],
                capture_output=True, text=True, timeout=60,
            )
            d = json.loads(out.stdout)
            for p in d.get("profiles", []):
                if p.get("follower_count") is not None:
                    return int(p["follower_count"])
            log(f"instagram: no follower_count in response (attempt {attempt+1}): {out.stdout[:200]}")
        except Exception as exc:  # noqa: BLE001
            log(f"instagram fetch failed (attempt {attempt+1}): {exc}")
        time.sleep(5 * (attempt + 1))
    return None


def fetch_youtube(retries=3):
    """Jayden's YouTube channel (@JaydenAj13) only exposes a rounded
    subscriber string (e.g. "2.07K subscribers") in the page HTML, so the
    count is approximate. Convert K/M suffixes to an int."""
    def to_int(s, suffix):
        n = float(s.replace(",", ""))
        return int(n * 1000) if suffix.upper() == "K" else int(n * 1000000) if suffix.upper() == "M" else int(n)

    for attempt in range(retries):
        try:
            req = urllib.request.Request(
                YT_URL,
                headers={
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                                  "AppleWebKit/537.36 (KHTML, like Gecko) "
                                  "Chrome/126.0.0.0 Safari/537.36",
                    "Accept-Language": "en-US,en;q=0.9",
                },
            )
            with urllib.request.urlopen(req, timeout=25) as resp:
                html = resp.read().decode("utf-8", "replace")
            m = re.search(r'([\d.,]+)([KM]?)\s*subscribers', html, re.IGNORECASE)
            if m:
                return to_int(m.group(1), m.group(2))
            log(f"youtube: subscriber count not found in page (attempt {attempt+1})")
        except Exception as exc:  # noqa: BLE001
            log(f"youtube fetch failed (attempt {attempt+1}): {exc}")
        time.sleep(5 * (attempt + 1))
    return None


def gh(method, path, data=None):
    body = json.dumps(data).encode() if data is not None else None
    req = urllib.request.Request(
        GH_API + path, data=body, method=method,
        headers={"User-Agent": "Kaelen-Muse/1.0", "Content-Type": "application/json",
                 "Accept": "application/vnd.github+json"},
    )
    add_surrogate_to_request(req, "custom.github", entry_name="access_token",
                             allowed_hosts=("api.github.com",))
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return resp.status, read_json_response(resp)
    except urllib.error.HTTPError as exc:
        try:
            payload = json.loads(exc.read().decode("utf-8", "replace"))
        except Exception:
            payload = {}
        return exc.code, payload


def publish(counts):
    """Force-push a single root commit containing followers.json (+ poller + README)."""
    blobs = {}
    files = {
        "followers.json": json.dumps(counts, indent=2) + "\n",
        "poll.py": open(f"{LOCAL_DIR}/poll.py").read(),
        "README.md": open(f"{LOCAL_DIR}/README.md").read(),
    }
    tree = []
    for name, content in files.items():
        st, blob = gh("POST", f"/repos/{REPO}/git/blobs",
                      {"content": content, "encoding": "utf-8"})
        if st != 201:
            log(f"blob create failed for {name}: {st} {blob}")
            return False
        tree.append({"path": name, "mode": "100644", "type": "blob", "sha": blob["sha"]})
    st, tree_resp = gh("POST", f"/repos/{REPO}/git/trees", {"tree": tree})
    if st != 201:
        log(f"tree create failed: {st} {tree_resp}")
        return False
    msg = "Follower counts %s" % counts["updated_at"]
    st, commit = gh("POST", f"/repos/{REPO}/git/commits",
                    {"message": msg, "tree": tree_resp["sha"], "parents": []})
    if st != 201:
        log(f"commit create failed: {st} {commit}")
        return False
    st, ref = gh("PATCH", f"/repos/{REPO}/git/refs/heads/{BRANCH}",
                 {"sha": commit["sha"], "force": True})
    if st != 200:
        log(f"ref update failed: {st} {ref}")
        return False
    log(f"published: tiktok={counts['tiktok']} instagram={counts['instagram']} youtube={counts['youtube']}")
    return True


def main():
    try:
        state = json.load(open(STATE_FILE))
    except Exception:
        state = {"tiktok": None, "instagram": None, "youtube": None}

    tt = fetch_tiktok()
    ig = fetch_instagram()
    yt = fetch_youtube()

    # Sanity guard: TikTok sometimes serves an anti-bot page that still contains
    # "followerCount":0. Treat an implausible drop (< 50% of last-known) as a
    # transient failure so the last-known value is kept via the stale path below.
    if tt is not None and state.get("tiktok") and tt < state["tiktok"] * 0.5:
        log(f"tiktok value {tt} implausibly low vs last-known {state['tiktok']}; treating as failed")
        tt = None

    if tt is None and state.get("tiktok") is None:
        log("tiktok failed and no prior value; aborting publish")
        return 1
    if ig is None and state.get("instagram") is None:
        log("instagram failed and no prior value; aborting publish")
        return 1

    counts = {
        "tiktok": tt if tt is not None else state["tiktok"],
        "instagram": ig if ig is not None else state["instagram"],
        "youtube": yt if yt is not None else state.get("youtube"),
        "tiktok_stale": tt is None,
        "instagram_stale": ig is None,
        "youtube_stale": yt is None,
        "youtube_approx": True,
        "updated_at": datetime.datetime.now(
            datetime.timezone(datetime.timedelta(hours=-4))).isoformat(),
    }
    if not publish(counts):
        return 1
    json.dump({"tiktok": counts["tiktok"], "instagram": counts["instagram"],
               "youtube": counts["youtube"]},
              open(STATE_FILE, "w"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
