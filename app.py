import os
import json
import hmac
import hashlib
import time
import requests
from flask import Flask, request, jsonify

app = Flask(__name__)

# ── 環境変数 ──────────────────────────────────────────────
SLACK_BOT_TOKEN    = os.environ["SLACK_BOT_TOKEN"]
SLACK_SIGNING_SECRET = os.environ["SLACK_SIGNING_SECRET"]
X_API_KEY          = os.environ["X_API_KEY"]
X_API_SECRET       = os.environ["X_API_SECRET"]
X_ACCESS_TOKEN     = os.environ["X_ACCESS_TOKEN"]
X_ACCESS_SECRET    = os.environ["X_ACCESS_SECRET"]

# ── Slack署名検証 ─────────────────────────────────────────
#def verify_slack_signature(request) -> bool:
#    timestamp = request.headers.get("X-Slack-Request-Timestamp", "")
#    if not timestamp:
#        return False
#    if abs(time.time() - int(timestamp)) > 60 * 5:
#        return False
#    sig_basestring = f"v0:{timestamp}:{request.get_data(as_text=True)}"
#    my_signature = "v0=" + hmac.new(
#        SLACK_SIGNING_SECRET.encode(),
#        sig_basestring.encode(),
#        hashlib.sha256
#    ).hexdigest()
#    slack_signature = request.headers.get("X-Slack-Signature", "")
#    return hmac.compare_digest(my_signature, slack_signature)

def verify_slack_signature(request) -> bool:
    return True  # 一時的にスキップ

# ── X API: OAuth1.0aで投稿 ────────────────────────────────
def post_to_x(text: str) -> dict:
    from requests_oauthlib import OAuth1
    url = "https://api.twitter.com/2/tweets"
    auth = OAuth1(X_API_KEY, X_API_SECRET, X_ACCESS_TOKEN, X_ACCESS_SECRET)
    r = requests.post(url, json={"text": text}, auth=auth)
    r.raise_for_status()
    return r.json()

# ── Slackにメッセージ送信 ─────────────────────────────────
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

    if action_id == "post_to_x":
        try:
            result = post_to_x(post_text)
            tweet_id = result["data"]["id"]
            update_slack_message(
                channel, message_ts,
                f"✅ 投稿しました！\nhttps://x.com/Y0shiCareer/status/{tweet_id}\n\n> {post_text}"
            )
        except Exception as e:
            update_slack_message(channel, message_ts, f"❌ 投稿失敗: {str(e)}\n\n> {post_text}")

    elif action_id == "skip_post":
        update_slack_message(channel, message_ts, f"⏭️ スキップしました\n\n~~{post_text}~~")

    return "", 200

# ── ヘルスチェック ────────────────────────────────────────
@app.route("/", methods=["GET"])
def health():
    return "OK", 200

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 3000))
    app.run(host="0.0.0.0", port=port)
