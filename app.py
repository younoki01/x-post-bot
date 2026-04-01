import os
import json
import hmac
import hashlib
import time
import requests
from datetime import datetime, timezone, timedelta
from flask import Flask, request, jsonify

app = Flask(__name__)

SLACK_BOT_TOKEN      = os.environ["SLACK_BOT_TOKEN"]
SLACK_SIGNING_SECRET = os.environ["SLACK_SIGNING_SECRET"]
X_API_KEY            = os.environ["X_API_KEY"]
X_API_SECRET         = os.environ["X_API_SECRET"]
X_ACCESS_TOKEN       = os.environ["X_ACCESS_TOKEN"]
X_ACCESS_SECRET      = os.environ["X_ACCESS_SECRET"]
THREADS_ACCESS_TOKEN = os.environ["THREADS_ACCESS_TOKEN"]
GH_PAT               = os.environ["GH_PAT"]
GH_REPO              = "younoki01/x-benchmark"

JST = timezone(timedelta(hours=9))

def verify_slack_signature(request) -> bool:
    return True

def post_to_x(text: str) -> str:
    from requests_oauthlib import OAuth1
    url = "https://api.twitter.com/2/tweets"
    auth = OAuth1(X_API_KEY, X_API_SECRET, X_ACCESS_TOKEN, X_ACCESS_SECRET)
    r = requests.post(url, json={"text": text}, auth=auth)
    print(f"X API response: {r.status_code} {r.text[:200]}")
    r.raise_for_status()
    return r.json()["data"]["id"]

def post_to_threads(text: str) -> str:
    if len(text) > 500:
        text = text[:497] + "..."
    url1 = "https://graph.threads.net/v1.0/me/threads"
    params1 = {
        "media_type": "TEXT",
        "topic_tag": "JOB_SEARCH",
        "text": text,
        "access_token": THREADS_ACCESS_TOKEN,
    }
    r1 = requests.post(url1, params=params1)
    print(f"Threads container: {r1.status_code} {r1.text[:200]}")
    r1.raise_for_status()
    container_id = r1.json()["id"]
    url2 = "https://graph.threads.net/v1.0/me/threads_publish"
    params2 = {"creation_id": container_id, "access_token": THREADS_ACCESS_TOKEN}
    r2 = requests.post(url2, params=params2)
    print(f"Threads publish: {r2.status_code} {r2.text[:200]}")
    r2.raise_for_status()
    return r2.json()["id"]

def update_slack_message(channel: str, ts: str, text: str):
    headers = {"Authorization": f"Bearer {SLACK_BOT_TOKEN}", "Content-Type": "application/json"}
    r = requests.post("https://slack.com/api/chat.update", headers=headers,
                      json={"channel": channel, "ts": ts, "text": text})
    print(f"Slack update: {r.status_code} {r.text[:200]}")

def open_edit_modal(trigger_id: str, original_text: str, channel: str, message_ts: str):
    headers = {"Authorization": f"Bearer {SLACK_BOT_TOKEN}", "Content-Type": "application/json"}
    modal = {
        "trigger_id": trigger_id,
        "view": {
            "type": "modal",
            "callback_id": "edit_and_post",
            "private_metadata": json.dumps({"channel": channel, "message_ts": message_ts}),
            "title": {"type": "plain_text", "text": "投稿を編集"},
            "submit": {"type": "plain_text", "text": "投稿する"},
            "close": {"type": "plain_text", "text": "キャンセル"},
            "blocks": [
                {
                    "type": "input",
                    "block_id": "post_text_block",
                    "label": {"type": "plain_text", "text": "投稿内容"},
                    "element": {
                        "type": "plain_text_input",
                        "action_id": "post_text_input",
                        "multiline": True,
                        "initial_value": original_text,
                    }
                },
                {
                    "type": "input",
                    "block_id": "platform_block",
                    "label": {"type": "plain_text", "text": "投稿先"},
                    "element": {
                        "type": "static_select",
                        "action_id": "platform_select",
                        "initial_option": {"text": {"type": "plain_text", "text": "X + Threads"}, "value": "both"},
                        "options": [
                            {"text": {"type": "plain_text", "text": "X + Threads"}, "value": "both"},
                            {"text": {"type": "plain_text", "text": "X のみ"}, "value": "x"},
                            {"text": {"type": "plain_text", "text": "Threads のみ"}, "value": "threads"},
                        ]
                    }
                }
            ]
        }
    }
    r = requests.post("https://slack.com/api/views.open", headers=headers, json=modal)
    print(f"Modal open: {r.status_code} {r.text[:200]}")

def load_from_github(filepath: str) -> dict:
    url = f"https://api.github.com/repos/{GH_REPO}/contents/{filepath}"
    headers = {"Authorization": f"Bearer {GH_PAT}"}
    r = requests.get(url, headers=headers)
    if r.status_code != 200:
        return {}
    import base64
    return json.loads(base64.b64decode(r.json()["content"]).decode())

def save_to_github(filepath: str, content: dict, message: str):
    url = f"https://api.github.com/repos/{GH_REPO}/contents/{filepath}"
    headers = {"Authorization": f"Bearer {GH_PAT}", "Content-Type": "application/json"}
    r = requests.get(url, headers=headers)
    sha = r.json().get("sha") if r.status_code == 200 else None
    import base64
    encoded = base64.b64encode(json.dumps(content, ensure_ascii=False, indent=2).encode()).decode()
    payload = {"message": message, "content": encoded}
    if sha:
        payload["sha"] = sha
    r = requests.put(url, headers=headers, json=payload)
    print(f"GitHub save: {r.status_code} {filepath}")

def do_post(action_id: str, post_text: str) -> list:
    results = []
    posted_log = load_from_github("data/posted_log.json")
    if "posts" not in posted_log:
        posted_log["posts"] = []

    if action_id in ("post_to_x", "post_to_both", "x"):
        try:
            tweet_id = post_to_x(post_text)
            results.append(f"✅ X投稿完了: https://x.com/Y0shiCareer/status/{tweet_id}")
            posted_log["posts"].append({
                "text": post_text, "platform": "x", "post_id": tweet_id,
                "posted_at": datetime.now(JST).isoformat(),
            })
        except Exception as e:
            results.append(f"❌ X投稿失敗: {str(e)}")

    if action_id in ("post_to_threads", "post_to_both", "threads"):
        try:
            post_id = post_to_threads(post_text)
            results.append(f"✅ Threads投稿完了: https://www.threads.net/@shushoku.concierge/post/{post_id}")
            posted_log["posts"].append({
                "text": post_text, "platform": "threads", "post_id": post_id,
                "posted_at": datetime.now(JST).isoformat(),
            })
        except Exception as e:
            results.append(f"❌ Threads投稿失敗: {str(e)}")

    if posted_log["posts"]:
        save_to_github("data/posted_log.json", posted_log, "log: add posted entry")

    return results

@app.route("/slack/actions", methods=["POST"])
def slack_actions():
    if not verify_slack_signature(request):
        return jsonify({"error": "Invalid signature"}), 403

    payload = json.loads(request.form.get("payload", "{}"))
    payload_type = payload.get("type")

    # ── モーダル送信 ──────────────────────────────────────
    if payload_type == "view_submission":
        callback_id = payload["view"]["callback_id"]
        if callback_id == "edit_and_post":
            values = payload["view"]["state"]["values"]
            post_text = values["post_text_block"]["post_text_input"]["value"]
            platform  = values["platform_block"]["platform_select"]["selected_option"]["value"]
            meta = json.loads(payload["view"]["private_metadata"])
            channel    = meta["channel"]
            message_ts = meta["message_ts"]

            results = do_post(platform, post_text)
            result_text = "\n".join(results)
            update_slack_message(channel, message_ts, f"{result_text}\n\n> {post_text[:100]}...")
            return jsonify({"response_action": "clear"})

    # ── ボタン操作 ────────────────────────────────────────
    actions = payload.get("actions", [])
    if not actions:
        return "", 200

    action    = actions[0]
    action_id = action.get("action_id", "")
    post_text = action.get("value", "")
    channel   = payload["channel"]["id"]
    message_ts = payload["message"]["ts"]

    print(f"Action: {action_id}")

    # スキップ理由
    skip_reasons = {
        "skip_theme":   ("テーマが違う", "low"),
        "skip_style":   ("文体が合わない", "low"),
        "skip_thin":    ("内容が薄い", "low"),
        "skip_fact":    ("事実が違う", "low"),
        "skip_timing":  ("タイミングが違う", "neutral"),
    }

    if action_id in skip_reasons:
        reason, score = skip_reasons[action_id]
        feedback = load_from_github("data/feedback.json")
        if "skipped" not in feedback:
            feedback["skipped"] = []
        feedback["skipped"].append({
            "text": post_text, "reason": reason,
            "skipped_at": datetime.now(JST).isoformat(), "score": score,
        })
        save_to_github("data/feedback.json", feedback, f"feedback: skip - {reason}")
        update_slack_message(channel, message_ts, f"⏭️ スキップ（{reason}）\n\n~~{post_text[:50]}...~~")
        return "", 200

    # 編集して投稿
    if action_id == "edit_and_post":
        trigger_id = payload.get("trigger_id")
        open_edit_modal(trigger_id, post_text, channel, message_ts)
        return "", 200

    # 通常投稿
    if action_id in ("post_to_x", "post_to_both", "post_to_threads"):
        results = do_post(action_id, post_text)
        result_text = "\n".join(results)
        update_slack_message(channel, message_ts, f"{result_text}\n\n> {post_text[:100]}...")

    return "", 200

@app.route("/", methods=["GET"])
def health():
    return "OK", 200

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 3000))
    app.run(host="0.0.0.0", port=port)
