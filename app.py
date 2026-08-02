"""승인 화면.

브라우저에서 초안을 보고, 문구를 고치고, 마음에 드는 것만 골라 발행합니다.
발행 버튼을 누르기 전까지는 인터넷에 아무것도 올라가지 않습니다.
"""

from pathlib import Path

from flask import Flask, abort, jsonify, redirect, render_template, request, send_file, url_for

from src import publisher, store, uploader
from src.aladin import affiliate_link
from src.settings import load_config
from src.writer import compose_threads_text

app = Flask(__name__)


@app.route("/")
def index():
    config = load_config()
    return render_template(
        "review.html",
        drafts=store.list_drafts("draft"),
        history=[d for d in store.list_drafts(None) if d["status"] != "draft"][:20],
        threads_on=config["발행"]["쓰레드_사용"],
        instagram_on=config["발행"]["인스타_사용"],
    )


@app.route("/card/<int:draft_id>/<int:index>")
def card_image(draft_id: int, index: int):
    draft = store.get_draft(draft_id)
    if not draft or index >= len(draft["cards"]):
        abort(404)
    path = Path(draft["cards"][index])
    if not path.exists():
        abort(404)
    return send_file(path, mimetype="image/jpeg")


@app.route("/save/<int:draft_id>", methods=["POST"])
def save(draft_id: int):
    store.update_text(draft_id, request.json.get("text", ""))
    return jsonify({"ok": True})


@app.route("/skip/<int:draft_id>", methods=["POST"])
def skip(draft_id: int):
    store.mark_skipped(draft_id)
    return redirect(url_for("index"))


@app.route("/publish", methods=["POST"])
def publish():
    config = load_config()
    partner = config["제휴"]["알라딘_파트너ID"]
    credit = (
        config["제휴"].get("출처표기_문구", "")
        if config["제휴"].get("출처표기_사용")
        else ""
    )
    use_threads = config["발행"]["쓰레드_사용"]
    use_instagram = config["발행"]["인스타_사용"]
    attach_images = config["발행"]["쓰레드_이미지_첨부"]

    ids = [int(i) for i in request.form.getlist("draft_ids")]
    results = []

    for draft_id in ids:
        draft = store.get_draft(draft_id)
        if not draft or draft["status"] != "draft":
            continue

        edited = request.form.get(f"text_{draft_id}")
        if edited is not None and edited.strip() != (draft["threads_text"] or "").strip():
            store.update_text(draft_id, edited.strip())
            draft["threads_text"] = edited.strip()

        search_line = (request.form.get(f"search_{draft_id}") or draft["search_line"] or "").strip()
        if search_line != (draft["search_line"] or ""):
            store.update_search_line(draft_id, search_line)

        link = affiliate_link(draft["link"] or "", partner)
        text = compose_threads_text(
            draft["threads_text"], draft["hashtags"] or "", link, credit
        )
        # 캡션 첫 줄은 검색에 잡히는 줄이라 맨 앞에 둡니다.
        # 출처 표기와 알라딘 링크는 상위 등급 승인 조건이라 캡션에도 넣습니다.
        caption = "\n\n".join(
            p
            for p in [search_line, draft["threads_text"], draft["hashtags"] or "", link, credit]
            if p
        )

        threads_id = instagram_id = None
        try:
            image_urls = uploader.upload_all(draft["cards"]) if draft["cards"] else []

            if use_instagram:
                instagram_id = publisher.post_to_instagram(
                    caption, image_urls, draft["alts"]
                )
            if use_threads:
                threads_id = publisher.post_to_threads(
                    text, image_urls if attach_images else []
                )

            store.mark_published(draft_id, threads_id, instagram_id)
            results.append({"id": draft_id, "title": draft["title"], "ok": True})
        except Exception as exc:
            # 한쪽만 올라간 경우도 기록해 둡니다.
            note = f"{type(exc).__name__}: {exc}"
            if threads_id or instagram_id:
                note = f"일부만 발행됨 (쓰레드={threads_id}, 인스타={instagram_id}) / {note}"
            store.mark_failed(draft_id, note)
            results.append(
                {"id": draft_id, "title": draft["title"], "ok": False, "error": note}
            )

    return render_template("result.html", results=results)


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=False)
