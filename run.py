"""이 파일 하나만 실행하면 됩니다.

  1) 신간을 골라 초안을 만들고
  2) 브라우저에 승인 화면을 띄웁니다.

발행은 화면에서 버튼을 눌렀을 때만 일어납니다.

  .venv\\Scripts\\python.exe run.py           # 초안 만들고 화면 열기
  .venv\\Scripts\\python.exe run.py --review  # 초안 만들지 않고 화면만 열기
  .venv\\Scripts\\python.exe run.py --only 5  # 5건만 만들기
"""

import sys
import threading
import webbrowser

from app import app
from src import pipeline, store

PORT = 5000


def main() -> int:
    args = sys.argv[1:]
    skip_generate = "--review" in args

    limit = None
    if "--only" in args:
        limit = int(args[args.index("--only") + 1])

    if not skip_generate:
        try:
            created = pipeline.generate(limit)
        except RuntimeError as exc:
            print(f"\n[막힘] {exc}\n")
            return 1
        if created:
            print(f"초안 {len(created)}건을 만들었습니다.")
        else:
            print("새로 만들 초안이 없습니다. (이미 다룬 책이거나 조건에 맞는 신간이 없음)")

    waiting = len(store.list_drafts("draft"))
    print(f"\n승인 화면을 엽니다 — 대기 중인 초안 {waiting}건")
    print(f"  http://127.0.0.1:{PORT}")
    print("  (창을 닫으려면 이 검은 창에서 Ctrl+C)\n")

    threading.Timer(1.2, lambda: webbrowser.open(f"http://127.0.0.1:{PORT}")).start()
    app.run(host="127.0.0.1", port=PORT, debug=False)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
