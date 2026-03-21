import os
import json
import hmac
import hashlib
import time
import requests
from flask import Flask, request, jsonify

app = Flask(__name__)

# ── 環境変数 ──────────────────────────────────────────────
SLACK_BOT_TOKEN      = os.environ["SLACK_BOT_TOKEN"]
SLACK_SIGNING_SECRET = os.environ["SLACK_SIGNING_SECRET"]
X_API_KEY            = os.environ["X_API_KEY"]
X_API_SECRET         = os.environ["X_API_SECRET"]
X_ACCESS_TOKEN       = os.environ["X_ACCESS_TOKEN"]
X_ACCESS_SECRET      = os.environ["X_ACCESS_SECRET"]
THREADS_ACCESS_TOKEN = os.environ["THREADS_ACCESS_TOKEN"]

# ── Threads トピック設定 ──────────────────────────────────
THREADS_TOPIC = "JOB_SEARCH"  # 転職活動

# ── Slack署名検証 ─────────────────────────────────────────
def verify_slack_signature(request) -> bool:
    return True  # 開発中はスキップ

# ── X API: 投稿 ───────────────────────────────────────────
def post_to_x(text: str) -> str:
    from requests_oauthlib import OAuth1
    url = "https://api.twitter.com/2/tweets"
    auth = OAuth1(X_API_KEY, X_API_SECRET, X_ACCESS_TOKEN, X_ACCESS_SECRET)
    r = requests.post(url, json={"text": text}, auth=auth)
    r.raise_for_status()
    tweet_id = r.json()["data"]["id"]
    return f"https://x.com/Y0shiCareer/status/{tweet_id}"

# ── Threads API: 投稿 ─────────────────────────────────────
def post_to_threads(text: str) -> str:
    # Step1: メディアコンテナ作成
    url1 = "https://graph.threads.net/v1.0/me/threads"
    params1 = {
        "media_type": "TEXT",
        "text": text,
        "topic_tag": THREADS_TOPIC,
        "access_token": THREADS_ACCESS_TOKEN,
    }
    r1 = requests.post(url1, params=params1)
    r1.raise_for_status()
    container_id = r1.json()["id"]

    # Step2: 投稿公開
    url2 = "https://graph.threads.net/v1.0/me/threads_publish"
    params2 = {
        "creation_id": container_id,
        "access_token": THREADS_ACCESS_TOKEN,
    }
    r2 = requests.post(url2, params=params2)
    r2.raise_for_status()
    post_id = r2.json()["id"]
    return f"https://www.threads.net/@shushoku.concierge/post/{post_id}"

# ── Slackメッセージ更新 ───────────────────────────────────
def update_slack_message(channel: str, ts: str, text: str):
    headers = {
        "Authorization": f"Bearer {SLACK_BOT_TOKEN}",
        "Content-Type": "application/json",
    }
    payload = {"channel": channel, "ts": ts, "text": text}
    requests.post("https://slack.com/api/chat.update", headers=headers, json=payload)

# ── Slackインタラクション受け取り ─────────────────────────
@app.route("/slack/actions", methods=["POST"])
def slack_actions():
    if not verify_slack_signature(request):
        return jsonify({"error": "Invalid signature"}), 403

    payload = json.loads(request.form.get("payload", "{}"))
    actions = payload.get("actions", [])
    if not actions:
        return "", 200

    action = actions[0]
    action_id = action.get("action_id", "")
    post_text = action.get("value", "")
    channel = payload["channel"]["id"]
    message_ts = payload["message"]["ts"]

    results = []

    if action_id in ("post_to_x", "post_to_both"):
        try:
            url = post_to_x(post_text)
            results.append(f"✅ X投稿完了: {url}")
        except Exception as e:
            results.append(f"❌ X投稿失敗: {str(e)}")

    if action_id in ("post_to_threads", "post_to_both"):
        try:
            url = post_to_threads(post_text)
            results.append(f"✅ Threads投稿完了: {url}")
        except Exception as e:
            results.append(f"❌ Threads投稿失敗: {str(e)}")

    if action_id == "skip_post":
        update_slack_message(channel, message_ts, f"⏭️ スキップしました\n\n~~{post_text[:50]}...~~")
        return "", 200

    result_text = "\n".join(results)
    update_slack_message(channel, message_ts, f"{result_text}\n\n> {post_text[:100]}...")

    return "", 200

# ── ヘルスチェック ────────────────────────────────────────
@app.route("/", methods=["GET"])
def health():
    return "OK", 200

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 3000))
    app.run(host="0.0.0.0", port=port)
