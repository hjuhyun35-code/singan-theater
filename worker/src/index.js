/**
 * 신간극장 — 텔레그램 전화받는 곳
 *
 * 텔레그램에서 버튼을 누르거나 메시지를 보내면 여기로 즉시 옵니다(webhook).
 * 여기서는 아무 일도 오래 하지 않습니다. 확인하고, 짧게 답하고, GitHub 를 깨웁니다.
 * 실제 작업(카드 만들기·인스타 발행)은 GitHub 워크플로가 합니다.
 *
 * 받는 것 두 가지
 *   1) "초안" 이 들어간 메시지  → 오늘치 초안을 새로 만듭니다 (10~20분 걸립니다)
 *   2) 카드 아래 버튼 누름       → 그 초안을 인스타에 올리거나 버립니다 (1분 안)
 *
 * ★ 아무나 이 주소를 알아내 눌러도 안 되도록 두 겹으로 막습니다.
 *   - 텔레그램이 붙여 보내는 비밀 머리글(WEBHOOK_SECRET)이 맞아야 합니다.
 *   - 미리 정해둔 대화방(ALLOWED_CHAT_ID)에서 온 것이어야 합니다.
 */

const TG = "https://api.telegram.org/bot";

/** 텔레그램에 짧게 한 마디 합니다. 실패해도 전체를 멈추지 않습니다. */
async function tell(env, method, body) {
  try {
    await fetch(`${TG}${env.TELEGRAM_TOKEN}/${method}`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify(body),
    });
  } catch (_) {
    /* 답을 못 해도 GitHub 깨우는 건 계속합니다 */
  }
}

/** GitHub 워크플로를 깨웁니다. */
async function wake(env, payload) {
  const res = await fetch(
    `https://api.github.com/repos/${env.GITHUB_REPO}/dispatches`,
    {
      method: "POST",
      headers: {
        authorization: `Bearer ${env.GITHUB_TOKEN}`,
        accept: "application/vnd.github+json",
        "content-type": "application/json",
        // GitHub 은 User-Agent 가 없으면 403 을 돌려줍니다.
        "user-agent": "singan-telegram",
      },
      body: JSON.stringify({ event_type: "telegram", client_payload: payload }),
    }
  );
  if (!res.ok) {
    console.log("GitHub 깨우기 실패", res.status, await res.text());
  }
  return res.ok;
}

export default {
  async fetch(request, env) {
    // 브라우저로 열어봤을 때 살아있는지만 알려줍니다.
    if (request.method !== "POST") {
      return new Response("신간극장 텔레그램 수신함. 살아 있습니다.");
    }

    // 1겹: 텔레그램이 보낸 게 맞는가
    const given = request.headers.get("x-telegram-bot-api-secret-token");
    if (!env.WEBHOOK_SECRET || given !== env.WEBHOOK_SECRET) {
      return new Response("누구세요", { status: 401 });
    }

    let update;
    try {
      update = await request.json();
    } catch (_) {
      return new Response("ok"); // 이상한 요청은 조용히 넘깁니다
    }

    const q = update.callback_query;
    const msg = update.message;

    // 2겹: 내 대화방에서 온 것인가
    const chatId = q ? q.message?.chat?.id : msg?.chat?.id;
    if (!chatId || String(chatId) !== String(env.ALLOWED_CHAT_ID)) {
      return new Response("ok");
    }

    // ── 버튼을 누른 경우 ────────────────────────────────
    if (q) {
      const data = q.data || "";
      // 이미 처리된 글의 잠긴 버튼입니다.
      if (data === "done" || !data.includes(":")) {
        await tell(env, "answerCallbackQuery", {
          callback_query_id: q.id,
          text: "이미 처리된 글입니다",
        });
        return new Response("ok");
      }
      const [action, slug] = [data.slice(0, data.indexOf(":")), data.slice(data.indexOf(":") + 1)];
      // 텔레그램은 몇 초 안에 답을 못 받으면 버튼을 계속 빙글빙글 돌립니다.
      // 그래서 GitHub 를 깨우기 전에 먼저 답합니다.
      await tell(env, "answerCallbackQuery", {
        callback_query_id: q.id,
        text: action === "pub" ? "올리는 중입니다..." : "넘기는 중입니다...",
      });
      await wake(env, {
        action: action === "pub" ? "publish" : "skip",
        slug,
        chat_id: chatId,
        message_id: q.message.message_id,
      });
      return new Response("ok");
    }

    // ── 메시지를 보낸 경우 ──────────────────────────────
    if (msg && typeof msg.text === "string") {
      const text = msg.text.trim();

      // "릴스" 또는 "영상" → 세로 영상을 만듭니다.
      // 뒤에 초안 번호를 붙이면 그 초안으로, 안 붙이면 가장 최근 초안으로 만듭니다.
      //   릴스            → 최근 것
      //   릴스 20260806-1 → 그 초안
      if (text.includes("릴스") || text.includes("영상")) {
        const slug = (text.match(/\d{8}-\d+/) || [""])[0];
        await tell(env, "sendMessage", {
          chat_id: chatId,
          text:
            "영상을 만들기 시작했습니다" +
            (slug ? ` (${slug})` : " (가장 최근 초안)") +
            ".\n10~20분 걸립니다. 다 되면 여기로 보내드립니다.\n\n" +
            "음악은 안 들어갑니다. 받으신 뒤 인스타 앱에서 붙여 올려주세요.",
        });
        await wake(env, { action: "reel", slug, chat_id: chatId });
        return new Response("ok");
      }

      if (text.includes("초안")) {
        await tell(env, "sendMessage", {
          chat_id: chatId,
          text:
            "초안을 만들기 시작했습니다.\n" +
            "카드가 나오기까지 10~20분 걸립니다. 다 되면 여기로 보내드립니다.",
        });
        await wake(env, { action: "draft", chat_id: chatId });
        return new Response("ok");
      }

      // 뭘 할 수 있는지 알려줍니다.
      await tell(env, "sendMessage", {
        chat_id: chatId,
        text:
          "이렇게 쓰시면 됩니다.\n\n" +
          "• 초안 — 오늘치 초안을 새로 만듭니다 (10~20분)\n" +
          "• 릴스 — 최근 초안으로 세로 영상을 만듭니다 (10~20분, 음악 없음)\n" +
          "• 릴스 20260806-1 — 그 초안으로 영상을 만듭니다\n" +
          "• 카드 아래 [승인하고 올리기] 버튼 — 인스타에 올립니다 (1분 안)",
      });
    }

    return new Response("ok");
  },
};
