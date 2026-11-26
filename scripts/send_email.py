import html
import json
import os
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

LATEST_JSON_PATH = os.path.join("docs", "data", "latest.json")

CATEGORY_NAMES = {
    "battery": "电池与储能学术",
    "ai": "AI 前沿",
    "science": "科学发现与 AI4S",
    "education": "教育教学",
    "industry": "储能产业",
}

SMTP_PRESETS = {
    "qq.com": ("smtp.qq.com", 465),
    "foxmail.com": ("smtp.qq.com", 465),
    "163.com": ("smtp.163.com", 465),
    "126.com": ("smtp.126.com", 465),
    "gmail.com": ("smtp.gmail.com", 465),
    "outlook.com": ("smtp-mail.outlook.com", 587),
    "hotmail.com": ("smtp-mail.outlook.com", 587),
    "icloud.com": ("smtp.mail.me.com", 587),
}


def esc(text: str) -> str:
    return html.escape(str(text or "").strip())


def resolve_smtp_config(user_email: str) -> tuple[str, int]:
    custom_host = os.environ.get("SMTP_HOST", "").strip()
    custom_port = os.environ.get("SMTP_PORT", "").strip()

    if custom_host:
        return custom_host, int(custom_port or "465")

    domain = user_email.split("@")[-1].lower() if "@" in user_email else ""
    if domain in SMTP_PRESETS:
        host, default_port = SMTP_PRESETS[domain]
        return host, int(custom_port or str(default_port))

    raise RuntimeError(
        f"无法自动识别邮箱域名 '{domain}' 的 SMTP 服务器，请在 GitHub Secrets 中补充添加 SMTP_HOST。"
    )


def get_hub_url() -> str:
    repo = os.environ.get("GITHUB_REPOSITORY", "").strip()
    if "/" in repo:
        owner, name = repo.split("/", 1)
        return f"https://{owner}.github.io/{name}/"
    return ""


def score_badge_style(score: float) -> str:
    if score >= 4.5:
        return "background:#fef3c7;color:#92400e;border:1px solid #fcd34d;"
    if score >= 3.8:
        return "background:#d1fae5;color:#065f46;border:1px solid #6ee7b7;"
    return "background:#f1f5f9;color:#475569;border:1px solid #cbd5e1;"


def build_html_email(data: dict, hub_url: str) -> tuple[str, str]:
    date_str = data.get("date", "")
    items = data.get("items", [])
    stats = data.get("stats", {})

    # 优先展示 >= 3.8 分的精选（若不足 5 条，则取前 8 条保底），单封邮件精读卡片最多 15 条
    featured = [it for it in items if float(it.get("score", 0)) >= 3.8][:15]
    if len(featured) < 5:
        featured = items[:8]
    featured_ids = {it.get("id") for it in featured}
    others = [it for it in items if it.get("id") not in featured_ids]

    high_count = sum(1 for it in items if float(it.get("score", 0)) >= 4.0)
    subject = f"Personal Hub 情报早报 ({date_str}) · {high_count} 篇高分精选"

    cards_html = []
    for it in featured:
        score = float(it.get("score", 0))
        cat_name = CATEGORY_NAMES.get(it.get("category", ""), it.get("category", ""))
        tldr = it.get("tldr") or {}
        metrics = (it.get("conditions_and_metrics") or "").strip()
        inspiration = (it.get("inspiration") or "").strip()
        tags = " ".join(
            f'<span style="display:inline-block;background:#f1f5f9;color:#475569;font-size:11px;padding:2px 6px;border-radius:4px;margin-right:4px;">#{esc(t)}</span>'
            for t in (it.get("tags") or [])[:4]
        )

        metrics_block = ""
        if metrics:
            metrics_html = esc(metrics).replace("\n", "<br/>")
            metrics_block = f"""
            <div style="margin-top:8px;padding:8px 10px;background:#f8fafc;border-left:3px solid #94a3b8;font-size:12px;color:#334155;line-height:1.6;">
              <strong style="color:#0f172a;">工况与指标：</strong><br/>{metrics_html}
            </div>"""

        insp_block = ""
        if inspiration:
            insp_block = f"""
            <div style="margin-top:8px;padding:8px 10px;background:#fffbeb;border-radius:6px;font-size:12px;color:#78350f;line-height:1.6;">
              <strong>🔗 跨界启发：</strong>{esc(inspiration)}
            </div>"""

        cards_html.append(f"""
        <div style="background:#ffffff;border:1px solid #e2e8f0;border-radius:10px;padding:16px;margin-bottom:14px;">
          <div style="font-size:12px;margin-bottom:6px;line-height:1.8;">
            <span style="display:inline-block;padding:1px 8px;border-radius:999px;font-weight:700;{score_badge_style(score)}">★ {score:.1f}</span>
            <span style="display:inline-block;padding:1px 7px;border-radius:4px;background:#eff6ff;color:#1d4ed8;font-weight:600;margin-left:4px;">{esc(cat_name)}</span>
            <span style="color:#64748b;margin-left:6px;">{esc(it.get('source', ''))} · {esc(it.get('published_at', ''))}</span>
          </div>
          <div style="margin:6px 0 4px 0;">
            <a href="{esc(it.get('url', '#'))}" style="font-size:16px;font-weight:700;color:#0f172a;text-decoration:none;line-height:1.45;">
              {esc(it.get('title_zh', ''))}
            </a>
          </div>
          <div style="font-size:12px;color:#94a3b8;margin-bottom:10px;line-height:1.4;">
            {esc(it.get('title_orig', ''))}
          </div>
          <div style="background:#f8fafc;border-radius:8px;padding:10px 12px;font-size:13px;color:#334155;line-height:1.65;">
            <div style="margin-bottom:4px;"><strong style="color:#0f172a;">问题：</strong>{esc(tldr.get('problem', '-'))}</div>
            <div style="margin-bottom:4px;"><strong style="color:#0f172a;">方法：</strong>{esc(tldr.get('method', '-'))}</div>
            <div><strong style="color:#0f172a;">结论：</strong>{esc(tldr.get('takeaway', '-'))}</div>
          </div>
          {metrics_block}
          {insp_block}
          <div style="margin-top:10px;display:flex;justify-content:space-between;align-items:center;">
            <div>{tags}</div>
          </div>
        </div>
        """)

    others_html = ""
    if others:
        rows = "".join(
            f"""<li style="margin-bottom:8px;font-size:13px;line-height:1.5;color:#334155;">
              <span style="color:#64748b;font-weight:600;">[{float(it.get('score', 0)):.1f}]</span>
              <a href="{esc(it.get('url', '#'))}" style="color:#1e40af;text-decoration:none;">{esc(it.get('title_zh', ''))}</a>
              <span style="color:#94a3b8;font-size:12px;"> — {esc(it.get('source', ''))}</span>
            </li>"""
            for it in others
        )
        others_html = f"""
        <div style="background:#ffffff;border:1px solid #e2e8f0;border-radius:10px;padding:16px;margin-top:16px;">
          <h3 style="margin:0 0 10px 0;font-size:14px;color:#0f172a;">📋 其余常规动态（{len(others)} 篇）</h3>
          <ul style="margin:0;padding-left:18px;">{rows}</ul>
        </div>"""

    hub_link_html = ""
    if hub_url:
        hub_link_html = f"""
        <a href="{esc(hub_url)}" style="display:inline-block;margin-top:10px;padding:7px 14px;background:#0f172a;color:#ffffff;text-decoration:none;border-radius:6px;font-size:12px;font-weight:600;">
          打开 Web 看板完整版（支持一键写入 Obsidian）↗
        </a>"""

    body = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head><meta charset="UTF-8" /></head>
<body style="margin:0;padding:0;background:#f1f5f9;font-family:-apple-system,BlinkMacSystemFont,'PingFang SC','Microsoft YaHei',sans-serif;">
  <div style="max-width:680px;margin:0 auto;padding:20px 12px;">
    <div style="background:#ffffff;border:1px solid #e2e8f0;border-radius:12px;padding:18px 20px;margin-bottom:16px;">
      <div style="font-size:18px;font-weight:800;color:#0f172a;">Personal Hub · 每日科研与前沿情报</div>
      <div style="font-size:12px;color:#64748b;margin-top:4px;">
        日期：{esc(date_str)} ｜ 共处理 {stats.get('processed', len(items))} 篇 ｜ 高分精选（≥4.0）：{high_count} 篇
      </div>
      {hub_link_html}
    </div>

    {''.join(cards_html)}
    {others_html}

    <div style="text-align:center;font-size:11px;color:#94a3b8;margin-top:20px;line-height:1.6;">
      由 Personal Hub GitHub Actions 自动生成并推送<br/>
      如需调整信源或打分标准，可在 GitHub 网页版修改 config/sources.yaml 或 config/prompt.txt
    </div>
  </div>
</body>
</html>"""

    return subject, body


def main():
    smtp_user = os.environ.get("SMTP_USER", "").strip()
    smtp_pass = os.environ.get("SMTP_PASS", "").strip()

    if not smtp_user or not smtp_pass:
        print("[Email] SMTP_USER 或 SMTP_PASS 未配置，跳过发送邮件。")
        return

    if not os.path.exists(LATEST_JSON_PATH):
        print(f"[Email] 未找到 {LATEST_JSON_PATH}，跳过发送邮件。")
        return

    with open(LATEST_JSON_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)

    if not data.get("items"):
        print("[Email] 当日无有效条目，跳过发送邮件。")
        return

    email_to_raw = os.environ.get("EMAIL_TO", "").strip() or smtp_user
    recipients = [addr.strip() for addr in email_to_raw.split(",") if addr.strip()]

    smtp_host, smtp_port = resolve_smtp_config(smtp_user)
    subject, html_body = build_html_email(data, get_hub_url())

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = f"Personal Hub <{smtp_user}>"
    msg["To"] = ", ".join(recipients)
    msg.attach(MIMEText(html_body, "html", "utf-8"))

    print(f"[Email] Connecting to {smtp_host}:{smtp_port} to send to {len(recipients)} recipient(s)...")
    if smtp_port == 465:
        with smtplib.SMTP_SSL(smtp_host, smtp_port, timeout=30) as server:
            server.login(smtp_user, smtp_pass)
            server.sendmail(smtp_user, recipients, msg.as_string())
    else:
        with smtplib.SMTP(smtp_host, smtp_port, timeout=30) as server:
            server.starttls()
            server.login(smtp_user, smtp_pass)
            server.sendmail(smtp_user, recipients, msg.as_string())

    print(f"[Email] 邮件发送成功 -> {', '.join(recipients)}")


if __name__ == "__main__":
    main()
