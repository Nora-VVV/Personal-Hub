(() => {
  const DEFAULT_VAULT = "Knowledge";
  const DEFAULT_FOLDER = "01_Research/Inbox";
  const READ_STORAGE_KEY = "personal_hub_read_ids_v1";
  const SETTINGS_KEY = "personal_hub_obsidian_settings_v1";
  const FEEDBACK_STORAGE_KEY = "personal_hub_feedback_v1";

  const CATEGORY_NAMES = {
    battery: "电池与储能学术",
    ai: "AI 前沿",
    science: "科学发现与 AI4S",
    education: "教育教学",
    industry: "储能产业",
  };

  let currentData = null;
  let filteredItems = [];
  let activeCategory = "all";
  let minScore = 0;
  let hideRead = false;
  let searchQuery = "";
  let selectedIndex = -1;
  let activeItem = null;
  let readSet = new Set();
  let feedbackMap = {};

  const dateSelect = document.getElementById("dateSelect");
  const generatedAtText = document.getElementById("generatedAtText");
  const categoryTabs = document.getElementById("categoryTabs");
  const cardList = document.getElementById("cardList");
  const emptyState = document.getElementById("emptyState");
  const statsBadge = document.getElementById("statsBadge");
  const searchInput = document.getElementById("searchInput");
  const hideReadToggle = document.getElementById("hideReadToggle");

  const drawerOverlay = document.getElementById("drawerOverlay");
  const detailDrawer = document.getElementById("detailDrawer");
  const closeDrawerBtn = document.getElementById("closeDrawerBtn");
  const drawerVoteUp = document.getElementById("drawerVoteUp");
  const drawerVoteDown = document.getElementById("drawerVoteDown");

  const settingsModal = document.getElementById("settingsModal");
  const openSettingsBtn = document.getElementById("openSettingsBtn");
  const closeSettingsBtn = document.getElementById("closeSettingsBtn");
  const cancelSettingsBtn = document.getElementById("cancelSettingsBtn");
  const saveSettingsBtn = document.getElementById("saveSettingsBtn");
  const vaultNameInput = document.getElementById("vaultNameInput");
  const folderPathInput = document.getElementById("folderPathInput");
  const zoteroUserIdInput = document.getElementById("zoteroUserIdInput");
  const zoteroApiKeyInput = document.getElementById("zoteroApiKeyInput");
  const zoteroCollectionInput = document.getElementById("zoteroCollectionInput");
  const obsidianPathHint = document.getElementById("obsidianPathHint");

  const feedbackModal = document.getElementById("feedbackModal");
  const openFeedbackBtn = document.getElementById("openFeedbackBtn");
  const feedbackCountBadge = document.getElementById("feedbackCountBadge");
  const closeFeedbackBtn = document.getElementById("closeFeedbackBtn");
  const closeFeedbackBtn2 = document.getElementById("closeFeedbackBtn2");
  const feedbackPreview = document.getElementById("feedbackPreview");
  const copyFeedbackBtn = document.getElementById("copyFeedbackBtn");
  const clearFeedbackBtn = document.getElementById("clearFeedbackBtn");

  const personalNoteInput = document.getElementById("personalNoteInput");
  const sendObsidianBtn = document.getElementById("sendObsidianBtn");
  const sendZoteroBtn = document.getElementById("sendZoteroBtn");
  const downloadRisBtn = document.getElementById("downloadRisBtn");
  const copyMarkdownBtn = document.getElementById("copyMarkdownBtn");
  const downloadMdBtn = document.getElementById("downloadMdBtn");
  const toastEl = document.getElementById("toast");

  function showToast(msg) {
    toastEl.textContent = msg;
    toastEl.classList.remove("opacity-0");
    clearTimeout(showToast._timer);
    showToast._timer = setTimeout(() => {
      toastEl.classList.add("opacity-0");
    }, 3000);
  }

  function loadReadSet() {
    try {
      const arr = JSON.parse(localStorage.getItem(READ_STORAGE_KEY) || "[]");
      readSet = new Set(arr);
    } catch {
      readSet = new Set();
    }
  }

  function saveReadSet() {
    const arr = Array.from(readSet).slice(-2000);
    localStorage.setItem(READ_STORAGE_KEY, JSON.stringify(arr));
  }

  function loadFeedback() {
    try {
      feedbackMap = JSON.parse(localStorage.getItem(FEEDBACK_STORAGE_KEY) || "{}");
    } catch {
      feedbackMap = {};
    }
    updateFeedbackBadge();
  }

  function saveFeedback() {
    localStorage.setItem(FEEDBACK_STORAGE_KEY, JSON.stringify(feedbackMap));
    updateFeedbackBadge();
  }

  function updateFeedbackBadge() {
    feedbackCountBadge.textContent = String(Object.keys(feedbackMap).length);
  }

  function toggleVote(item, voteType) {
    if (!item) return;
    const existing = feedbackMap[item.id];
    if (existing && existing.vote === voteType) {
      delete feedbackMap[item.id];
      showToast("已取消反馈标记");
    } else {
      feedbackMap[item.id] = {
        vote: voteType,
        title_zh: item.title_zh || "",
        title_orig: item.title_orig || "",
        source: item.source || "",
        category: item.category || "",
        score: item.score || 0,
        tags: item.tags || [],
        date: currentData?.date || new Date().toISOString().slice(0, 10),
      };
      showToast(voteType === "up" ? "👍 已标记为有用" : "👎 已标记为噪音");
    }
    saveFeedback();
    renderCards();
    if (activeItem && activeItem.id === item.id) {
      updateDrawerVoteButtons(item.id);
    }
  }

  function updateDrawerVoteButtons(itemId) {
    const vote = feedbackMap[itemId]?.vote;
    drawerVoteUp.className =
      vote === "up"
        ? "text-xs px-2.5 py-1.5 rounded-lg border border-emerald-400 bg-emerald-100 text-emerald-800 font-semibold transition"
        : "text-xs px-2.5 py-1.5 rounded-lg border border-slate-200 bg-white hover:bg-emerald-50 text-slate-600 transition";
    drawerVoteDown.className =
      vote === "down"
        ? "text-xs px-2.5 py-1.5 rounded-lg border border-rose-400 bg-rose-100 text-rose-800 font-semibold transition"
        : "text-xs px-2.5 py-1.5 rounded-lg border border-slate-200 bg-white hover:bg-rose-50 text-slate-600 transition";
  }

  function buildFeedbackReport() {
    const entries = Object.values(feedbackMap);
    if (!entries.length) {
      return "暂无反馈记录。\n\n在日常浏览卡片时，点击 👍（有用）或 👎（噪音），周末来这里一键复制并发送给 AI 帮你优化信源和打分提示词。";
    }
    const ups = entries.filter((e) => e.vote === "up");
    const downs = entries.filter((e) => e.vote === "down");

    const formatRow = (e) =>
      `- [${e.score}] (${CATEGORY_NAMES[e.category] || e.category} / ${e.source}) ${e.title_zh}`;

    return [
      `# Personal Hub 阅读反馈报告（共 ${entries.length} 条）`,
      `请根据以下我近期点赞和点踩的条目，帮我分析：1) 哪些信源质量高/低需要调整；2) config/prompt.txt 的打分和降权规则该如何微调。`,
      "",
      `## 👍 觉得有用（${ups.length} 条）`,
      ups.length ? ups.map(formatRow).join("\n") : "- （无）",
      "",
      `## 👎 觉得是噪音或分数虚高（${downs.length} 条）`,
      downs.length ? downs.map(formatRow).join("\n") : "- （无）",
    ].join("\n");
  }

  function getSettings() {
    try {
      const saved = JSON.parse(localStorage.getItem(SETTINGS_KEY) || "{}");
      return {
        vault: saved.vault || DEFAULT_VAULT,
        folder: saved.folder || DEFAULT_FOLDER,
        zoteroUserId: saved.zoteroUserId || "",
        zoteroApiKey: saved.zoteroApiKey || "",
        zoteroCollection: saved.zoteroCollection || "",
      };
    } catch {
      return {
        vault: DEFAULT_VAULT,
        folder: DEFAULT_FOLDER,
        zoteroUserId: "",
        zoteroApiKey: "",
        zoteroCollection: "",
      };
    }
  }

  function saveSettings(newSettings) {
    localStorage.setItem(
      SETTINGS_KEY,
      JSON.stringify({
        vault: (newSettings.vault || "").trim() || DEFAULT_VAULT,
        folder: (newSettings.folder || "").trim().replace(/^\/+|\/+$/g, "") || DEFAULT_FOLDER,
        zoteroUserId: (newSettings.zoteroUserId || "").trim(),
        zoteroApiKey: (newSettings.zoteroApiKey || "").trim(),
        zoteroCollection: (newSettings.zoteroCollection || "").trim(),
      })
    );
    updateObsidianPathHint();
  }

  function updateObsidianPathHint() {
    const s = getSettings();
    const zoteroMode = s.zoteroUserId && s.zoteroApiKey ? "Zotero API 直传" : "Zotero .ris 模式";
    obsidianPathHint.textContent = `${s.vault}/${s.folder} · ${zoteroMode}`;
  }

  function getScoreStyle(score) {
    if (score >= 4.5) return "bg-amber-100 text-amber-800 border border-amber-300";
    if (score >= 3.5) return "bg-emerald-100 text-emerald-800 border border-emerald-200";
    return "bg-slate-100 text-slate-600 border border-slate-200";
  }

  function escapeHtml(str) {
    return String(str || "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  async function init() {
    loadReadSet();
    loadFeedback();
    updateObsidianPathHint();
    bindEvents();

    try {
      const idxResp = await fetch("data/index.json?t=" + Date.now());
      if (idxResp.ok) {
        const idx = await idxResp.json();
        const dates = idx.dates || [];
        dateSelect.innerHTML = dates
          .map((d, i) => `<option value="${d}">${d}${i === 0 ? " (最新)" : ""}</option>`)
          .join("");
      }
    } catch (e) {
      console.warn("Could not load index.json:", e);
    }

    await loadBrief("latest");
  }

  async function loadBrief(dateKey) {
    const url =
      dateKey === "latest"
        ? `data/latest.json?t=${Date.now()}`
        : `data/archive/${dateKey}.json?t=${Date.now()}`;
    try {
      const resp = await fetch(url);
      if (!resp.ok) throw new Error("HTTP " + resp.status);
      currentData = await resp.json();
      const genTime = (currentData.generated_at || "").replace("T", " ").slice(0, 16);
      generatedAtText.textContent = `${currentData.date || ""} · 更新于 ${genTime}`;
      renderCategoryTabs();
      applyFilters();
    } catch (e) {
      generatedAtText.textContent = "数据加载失败";
      cardList.innerHTML = `<div class="p-8 text-center text-red-500 text-sm">无法加载数据文件（${escapeHtml(e.message)}）。</div>`;
    }
  }

  function renderCategoryTabs() {
    const items = currentData?.items || [];
    const counts = { all: items.length };
    items.forEach((it) => {
      counts[it.category] = (counts[it.category] || 0) + 1;
    });

    const cats = [{ id: "all", name: "全部" }, ...(currentData?.categories || [])];
    categoryTabs.innerHTML = cats
      .map((c) => {
        const active = activeCategory === c.id;
        const count = counts[c.id] || 0;
        return `
          <button data-cat="${c.id}" class="cat-tab px-3 py-1.5 rounded-full text-xs font-medium transition ${
            active
              ? "bg-slate-900 text-white"
              : "bg-slate-100 text-slate-700 hover:bg-slate-200"
          }">
            ${escapeHtml(c.name)} <span class="opacity-70 ml-0.5">${count}</span>
          </button>
        `;
      })
      .join("");

    categoryTabs.querySelectorAll(".cat-tab").forEach((btn) => {
      btn.addEventListener("click", () => {
        activeCategory = btn.dataset.cat;
        selectedIndex = -1;
        renderCategoryTabs();
        applyFilters();
      });
    });
  }

  function applyFilters() {
    const items = currentData?.items || [];
    const q = searchQuery.trim().toLowerCase();

    filteredItems = items.filter((item) => {
      if (activeCategory !== "all" && item.category !== activeCategory) return false;
      if ((item.score || 0) < minScore) return false;
      if (hideRead && readSet.has(item.id)) return false;
      if (q) {
        const hay = [
          item.title_zh,
          item.title_orig,
          item.source,
          ...(item.tags || []),
          item.tldr?.problem,
          item.tldr?.method,
          item.tldr?.takeaway,
        ]
          .join(" ")
          .toLowerCase();
        if (!hay.includes(q)) return false;
      }
      return true;
    });

    const unreadCount = filteredItems.filter((i) => !readSet.has(i.id)).length;
    statsBadge.textContent = `显示 ${filteredItems.length} 条 · 未读 ${unreadCount}`;
    renderCards();
  }

  function renderCards() {
    if (!filteredItems.length) {
      cardList.innerHTML = "";
      emptyState.classList.remove("hidden");
      return;
    }
    emptyState.classList.add("hidden");

    cardList.innerHTML = filteredItems
      .map((item, idx) => {
        const isRead = readSet.has(item.id);
        const vote = feedbackMap[item.id]?.vote;
        const catName = CATEGORY_NAMES[item.category] || item.category;
        const scoreCls = getScoreStyle(item.score || 0);
        const activeCls = idx === selectedIndex ? "card-active" : "";
        const tagsHtml = (item.tags || [])
          .map(
            (t) =>
              `<span class="px-2 py-0.5 rounded bg-slate-100 text-slate-600 text-xs">#${escapeHtml(t)}</span>`
          )
          .join("");

        return `
          <article data-idx="${idx}" class="hub-card bg-white rounded-xl border border-slate-200 p-5 hover:border-slate-300 transition cursor-pointer ${activeCls} ${
            isRead ? "opacity-65" : ""
          }">
            <div class="flex items-start justify-between gap-3">
              <div class="space-y-1 min-w-0">
                <div class="flex flex-wrap items-center gap-2 text-xs">
                  <span class="px-2 py-0.5 rounded-full font-semibold ${scoreCls}">★ ${(item.score || 0).toFixed(1)}</span>
                  <span class="px-2 py-0.5 rounded bg-blue-50 text-blue-700 font-medium">${escapeHtml(catName)}</span>
                  <span class="text-slate-600 font-medium">${escapeHtml(item.source)}</span>
                  <span class="text-slate-400">${escapeHtml(item.published_at || "")}</span>
                </div>
                <h2 class="text-base sm:text-lg font-semibold text-slate-900 leading-snug pt-1">
                  ${escapeHtml(item.title_zh)}
                </h2>
                <p class="text-xs text-slate-400 truncate">${escapeHtml(item.title_orig)}</p>
              </div>
              <div class="flex items-center gap-1.5 shrink-0">
                <button data-vote-up="${idx}" class="text-xs px-2 py-1 rounded-lg border transition ${
                  vote === "up"
                    ? "border-emerald-400 bg-emerald-100 text-emerald-800"
                    : "border-slate-200 text-slate-500 hover:bg-emerald-50"
                }" title="有用">👍</button>
                <button data-vote-down="${idx}" class="text-xs px-2 py-1 rounded-lg border transition ${
                  vote === "down"
                    ? "border-rose-400 bg-rose-100 text-rose-800"
                    : "border-slate-200 text-slate-500 hover:bg-rose-50"
                }" title="噪音">👎</button>
                <button data-toggle-read="${item.id}" class="text-xs px-2.5 py-1 rounded-lg border border-slate-200 ${
                  isRead
                    ? "text-slate-400 hover:bg-slate-100"
                    : "text-slate-600 hover:bg-slate-100"
                }" title="标记已读/未读">
                  ${isRead ? "已读 ✓" : "已读"}
                </button>
              </div>
            </div>

            <div class="mt-3 space-y-1 text-sm text-slate-700 bg-slate-50 rounded-lg p-3">
              <p><span class="font-medium text-slate-900">问题：</span>${escapeHtml(item.tldr?.problem || "-")}</p>
              <p><span class="font-medium text-slate-900">方法：</span>${escapeHtml(item.tldr?.method || "-")}</p>
              <p><span class="font-medium text-slate-900">结论：</span>${escapeHtml(item.tldr?.takeaway || "-")}</p>
            </div>

            <div class="mt-3 flex flex-wrap items-center justify-between gap-2">
              <div class="flex flex-wrap gap-1.5">${tagsHtml}</div>
              <span class="text-xs text-blue-600 font-medium">展开核验与沉淀 →</span>
            </div>
          </article>
        `;
      })
      .join("");

    cardList.querySelectorAll(".hub-card").forEach((el) => {
      el.addEventListener("click", (e) => {
        const upBtn = e.target.closest("[data-vote-up]");
        if (upBtn) {
          e.stopPropagation();
          toggleVote(filteredItems[Number(upBtn.dataset.voteUp)], "up");
          return;
        }
        const downBtn = e.target.closest("[data-vote-down]");
        if (downBtn) {
          e.stopPropagation();
          toggleVote(filteredItems[Number(downBtn.dataset.voteDown)], "down");
          return;
        }
        const readBtn = e.target.closest("[data-toggle-read]");
        if (readBtn) {
          e.stopPropagation();
          toggleRead(readBtn.dataset.toggleRead);
          return;
        }
        const idx = Number(el.dataset.idx);
        selectedIndex = idx;
        openDrawer(filteredItems[idx]);
      });
    });
  }

  function toggleRead(id) {
    if (readSet.has(id)) {
      readSet.delete(id);
    } else {
      readSet.add(id);
    }
    saveReadSet();
    applyFilters();
  }

  function openDrawer(item) {
    if (!item) return;
    activeItem = item;

    if (!readSet.has(item.id)) {
      readSet.add(item.id);
      saveReadSet();
    }

    const scoreEl = document.getElementById("drawerScore");
    scoreEl.textContent = `★ ${(item.score || 0).toFixed(1)}`;
    scoreEl.className = `px-2.5 py-0.5 rounded-full text-xs font-semibold ${getScoreStyle(item.score || 0)}`;

    document.getElementById("drawerSource").textContent = item.source || "";
    document.getElementById("drawerDate").textContent = item.published_at || "";
    document.getElementById("drawerOrigLink").href = item.url || "#";
    document.getElementById("drawerTitleZh").textContent = item.title_zh || "";
    document.getElementById("drawerTitleOrig").textContent = item.title_orig || "";

    const metaParts = [];
    if (item.authors && item.authors.length) {
      const shown = item.authors.slice(0, 4).join(", ");
      metaParts.push(`作者：${shown}${item.authors.length > 4 ? " et al." : ""}`);
    }
    if (item.doi) {
      metaParts.push(`DOI: ${item.doi}`);
    }
    document.getElementById("drawerMetaLine").textContent = metaParts.join(" ｜ ");

    document.getElementById("drawerProblem").textContent = item.tldr?.problem || "-";
    document.getElementById("drawerMethod").textContent = item.tldr?.method || "-";
    document.getElementById("drawerTakeaway").textContent = item.tldr?.takeaway || "-";

    const metricsBox = document.getElementById("drawerMetricsBox");
    const metricsEl = document.getElementById("drawerMetrics");
    if (item.conditions_and_metrics) {
      metricsBox.classList.remove("hidden");
      metricsEl.textContent = item.conditions_and_metrics;
    } else {
      metricsBox.classList.add("hidden");
    }

    document.getElementById("drawerDeepDive").textContent = item.deep_dive || "";
    document.getElementById("drawerInspiration").textContent = item.inspiration || "";

    document.getElementById("drawerTags").innerHTML = (item.tags || [])
      .map((t) => `<span class="px-2 py-0.5 rounded bg-slate-100 text-slate-600 text-xs">#${escapeHtml(t)}</span>`)
      .join("");

    updateDrawerVoteButtons(item.id);
    personalNoteInput.value = "";
    document.getElementById("drawerBody").scrollTop = 0;

    drawerOverlay.classList.remove("hidden");
    detailDrawer.classList.remove("translate-x-full");
    renderCards();
  }

  function closeDrawer() {
    drawerOverlay.classList.add("hidden");
    detailDrawer.classList.add("translate-x-full");
    activeItem = null;
  }

  function sanitizeFilename(name) {
    return (name || "note")
      .replace(/[\\/:*?"<>|#^\[\]]/g, "-")
      .replace(/\s+/g, " ")
      .trim()
      .slice(0, 60);
  }

  function buildObsidianMarkdown(item) {
    const today = new Date().toISOString().slice(0, 10);
    const catName = CATEGORY_NAMES[item.category] || item.category;
    const purposeTags = Array.from(document.querySelectorAll(".purpose-cb:checked")).map(
      (cb) => cb.value
    );
    const allTags = Array.from(new Set([...purposeTags, ...(item.tags || [])]));
    const personalNote = personalNoteInput.value.trim();

    const yamlTags = allTags.map((t) => `  - ${t}`).join("\n");
    const safeYamlTitle = (item.title_zh || "").replace(/"/g, '\\"');
    const doiLine = item.doi ? `doi: "${item.doi}"\n` : "";

    return `---
title: "${safeYamlTitle}"
source: "${(item.source || "").replace(/"/g, '\\"')}"
category: ${catName}
published: ${item.published_at || today}
captured: ${today}
score: ${(item.score || 0).toFixed(1)}
${doiLine}url: ${item.url || ""}
status: inbox
tags:
${yamlTags}
---

# ${item.title_zh}

> **原文标题**：${item.title_orig}  
> **来源**：${item.source} ｜ **AI 评分**：⭐ ${(item.score || 0).toFixed(1)} ｜ [点击直达原文](${item.url})

## 💡 我的解读与待验证假设
${personalNote ? personalNote : "> （待补充个人批判、启发或待验证假设）"}

## 📌 三行速览（TL;DR）
- **核心问题**：${item.tldr?.problem || ""}
- **核心方法**：${item.tldr?.method || ""}
- **关键结论**：${item.tldr?.takeaway || ""}

## 📊 核心工况与量化指标
${item.conditions_and_metrics || "（无额外量化指标）"}

## 🔍 核心实现与证据核验
${item.deep_dive || ""}

## 🔗 跨界与工程启发
${item.inspiration || ""}

---
- [ ] 下载原文 PDF / SI 并精读
- [ ] 核验核心图表与实验工况后，升级为正式核心笔记（status: evergreen）
`;
  }

  function buildRisContent(item) {
    const isPaper =
      item.doi ||
      item.category === "battery" ||
      (item.source || "").toLowerCase().includes("arxiv") ||
      (item.source || "").toLowerCase().includes("papers");
    const lines = [];
    lines.push(`TY  - ${isPaper ? "JOUR" : "ELEC"}`);
    lines.push(`TI  - ${item.title_orig || item.title_zh}`);
    if (item.title_zh && item.title_zh !== item.title_orig) {
      lines.push(`ST  - ${item.title_zh}`);
    }
    if (item.authors && item.authors.length) {
      item.authors.forEach((au) => lines.push(`AU  - ${au}`));
    }
    if (item.source) lines.push(`T2  - ${item.source}`);
    const year = (item.published_at || "").slice(0, 4);
    if (year) lines.push(`PY  - ${year}`);
    if (item.published_at) lines.push(`DA  - ${item.published_at.replace(/-/g, "/")}`);
    if (item.doi) lines.push(`DO  - ${item.doi}`);
    if (item.url) lines.push(`UR  - ${item.url}`);

    const abstractParts = [
      item.title_zh ? `【中文标题】${item.title_zh}` : "",
      item.tldr?.problem ? `【问题】${item.tldr.problem}` : "",
      item.tldr?.method ? `【方法】${item.tldr.method}` : "",
      item.tldr?.takeaway ? `【结论】${item.tldr.takeaway}` : "",
      personalNoteInput.value.trim() ? `【我的批注】${personalNoteInput.value.trim()}` : "",
    ].filter(Boolean);
    if (abstractParts.length) {
      lines.push(`AB  - ${abstractParts.join(" ")}`);
    }

    const purposeTags = Array.from(document.querySelectorAll(".purpose-cb:checked")).map((cb) => cb.value);
    const allTags = Array.from(new Set(["PersonalHub", ...purposeTags, ...(item.tags || [])]));
    allTags.forEach((t) => lines.push(`KW  - ${t}`));
    lines.push("ER  - ");
    return lines.join("\r\n");
  }

  function downloadRis(item) {
    if (!item) return;
    const ris = buildRisContent(item);
    const filename = sanitizeFilename(item.title_zh || item.title_orig) + ".ris";
    const blob = new Blob([ris], { type: "application/x-research-info-systems;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = filename;
    a.click();
    URL.revokeObjectURL(url);
  }

  async function sendToZotero() {
    if (!activeItem) return;
    const s = getSettings();

    // 未配置 Zotero API 时，自动降级为下载 .ris（零配置可用）
    if (!s.zoteroUserId || !s.zoteroApiKey) {
      downloadRis(activeItem);
      showToast("已下载 .ris 题录文件，双击即可导入 Zotero（如需直传请在右上角设置 API）");
      return;
    }

    const isPaper =
      activeItem.doi ||
      activeItem.category === "battery" ||
      (activeItem.source || "").toLowerCase().includes("arxiv") ||
      (activeItem.source || "").toLowerCase().includes("papers");

    const purposeTags = Array.from(document.querySelectorAll(".purpose-cb:checked")).map((cb) => cb.value);
    const allTags = Array.from(new Set(["PersonalHub", ...purposeTags, ...(activeItem.tags || [])]));

    const abstractText = [
      `【中文标题】${activeItem.title_zh}`,
      `【问题】${activeItem.tldr?.problem || ""}`,
      `【方法】${activeItem.tldr?.method || ""}`,
      `【结论】${activeItem.tldr?.takeaway || ""}`,
      activeItem.conditions_and_metrics ? `【工况与指标】\n${activeItem.conditions_and_metrics}` : "",
      personalNoteInput.value.trim() ? `【我的批注】${personalNoteInput.value.trim()}` : "",
    ]
      .filter(Boolean)
      .join("\n");

    const creators = (activeItem.authors || []).map((name) => ({
      creatorType: "author",
      name,
    }));

    const zoteroItem = {
      itemType: isPaper ? "journalArticle" : "webpage",
      title: activeItem.title_orig || activeItem.title_zh,
      creators,
      date: activeItem.published_at || "",
      url: activeItem.url || "",
      abstractNote: abstractText,
      tags: allTags.map((tag) => ({ tag })),
      collections: s.zoteroCollection ? [s.zoteroCollection] : [],
      extra: `AI Score: ${(activeItem.score || 0).toFixed(1)}\nChinese Title: ${activeItem.title_zh || ""}`,
    };

    if (isPaper) {
      zoteroItem.publicationTitle = activeItem.source || "";
      if (activeItem.doi) zoteroItem.DOI = activeItem.doi;
    } else {
      zoteroItem.websiteTitle = activeItem.source || "";
    }

    const origBtnText = sendZoteroBtn.textContent;
    sendZoteroBtn.disabled = true;
    sendZoteroBtn.textContent = "正在写入 Zotero...";

    try {
      const resp = await fetch(`https://api.zotero.org/users/${encodeURIComponent(s.zoteroUserId)}/items`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "Zotero-API-Version": "3",
          "Zotero-API-Key": s.zoteroApiKey,
        },
        body: JSON.stringify([zoteroItem]),
      });

      if (!resp.ok) {
        const errText = await resp.text();
        throw new Error(`HTTP ${resp.status}: ${errText.slice(0, 80)}`);
      }
      showToast("📚 已成功写入 Zotero 文献库 ✓");
    } catch (e) {
      console.error("Zotero API error:", e);
      downloadRis(activeItem);
      showToast("Zotero API 写入失败，已自动下载 .ris 文件兜底");
    } finally {
      sendZoteroBtn.disabled = false;
      sendZoteroBtn.textContent = origBtnText;
    }
  }

  function sendToObsidian() {
    if (!activeItem) return;
    const { vault, folder } = getSettings();
    const md = buildObsidianMarkdown(activeItem);
    const filename = sanitizeFilename(activeItem.title_zh);
    const filePath = folder ? `${folder}/${filename}` : filename;
    const uri = `obsidian://new?vault=${encodeURIComponent(vault)}&file=${encodeURIComponent(
      filePath
    )}&content=${encodeURIComponent(md)}`;

    if (uri.length > 24000) {
      navigator.clipboard?.writeText(md);
      showToast("正文较长，已自动复制 Markdown 到剪贴板，请直接粘贴进 Obsidian");
      return;
    }

    window.location.href = uri;
    showToast(`正在唤起 Obsidian 写入 ${vault}/${folder}...`);
  }

  async function copyMarkdown() {
    if (!activeItem) return;
    const md = buildObsidianMarkdown(activeItem);
    try {
      await navigator.clipboard.writeText(md);
      showToast("已复制规范 Markdown ✓");
    } catch {
      showToast("复制失败，请使用下载 .md 按钮");
    }
  }

  function downloadMarkdown() {
    if (!activeItem) return;
    const md = buildObsidianMarkdown(activeItem);
    const filename = sanitizeFilename(activeItem.title_zh) + ".md";
    const blob = new Blob([md], { type: "text/markdown;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = filename;
    a.click();
    URL.revokeObjectURL(url);
    showToast(`已下载 ${filename}`);
  }

  function bindEvents() {
    dateSelect.addEventListener("change", () => {
      selectedIndex = -1;
      loadBrief(dateSelect.value);
    });

    document.querySelectorAll(".score-btn").forEach((btn) => {
      btn.addEventListener("click", () => {
        minScore = Number(btn.dataset.score);
        document.querySelectorAll(".score-btn").forEach((b) => {
          b.className =
            "score-btn px-2.5 py-1 rounded-md text-xs font-medium bg-slate-100 text-slate-700 hover:bg-slate-200";
        });
        btn.className =
          "score-btn px-2.5 py-1 rounded-md text-xs font-medium bg-slate-900 text-white";
        selectedIndex = -1;
        applyFilters();
      });
    });

    hideReadToggle.addEventListener("change", () => {
      hideRead = hideReadToggle.checked;
      selectedIndex = -1;
      applyFilters();
    });

    searchInput.addEventListener("input", () => {
      searchQuery = searchInput.value;
      selectedIndex = -1;
      applyFilters();
    });

    closeDrawerBtn.addEventListener("click", closeDrawer);
    drawerOverlay.addEventListener("click", closeDrawer);
    drawerVoteUp.addEventListener("click", () => toggleVote(activeItem, "up"));
    drawerVoteDown.addEventListener("click", () => toggleVote(activeItem, "down"));

    sendObsidianBtn.addEventListener("click", sendToObsidian);
    sendZoteroBtn.addEventListener("click", sendToZotero);
    downloadRisBtn.addEventListener("click", () => {
      downloadRis(activeItem);
      showToast("已下载 .ris 题录文件，双击即可导入 Zotero");
    });
    copyMarkdownBtn.addEventListener("click", copyMarkdown);
    downloadMdBtn.addEventListener("click", downloadMarkdown);

    // Settings modal
    openSettingsBtn.addEventListener("click", () => {
      const s = getSettings();
      vaultNameInput.value = s.vault;
      folderPathInput.value = s.folder;
      zoteroUserIdInput.value = s.zoteroUserId;
      zoteroApiKeyInput.value = s.zoteroApiKey;
      zoteroCollectionInput.value = s.zoteroCollection;
      settingsModal.classList.remove("hidden");
    });
    const closeSettings = () => settingsModal.classList.add("hidden");
    closeSettingsBtn.addEventListener("click", closeSettings);
    cancelSettingsBtn.addEventListener("click", closeSettings);
    saveSettingsBtn.addEventListener("click", () => {
      saveSettings({
        vault: vaultNameInput.value,
        folder: folderPathInput.value,
        zoteroUserId: zoteroUserIdInput.value,
        zoteroApiKey: zoteroApiKeyInput.value,
        zoteroCollection: zoteroCollectionInput.value,
      });
      closeSettings();
      showToast("设置已保存 ✓");
    });

    // Feedback modal
    const closeFeedback = () => feedbackModal.classList.add("hidden");
    openFeedbackBtn.addEventListener("click", () => {
      feedbackPreview.value = buildFeedbackReport();
      feedbackModal.classList.remove("hidden");
    });
    closeFeedbackBtn.addEventListener("click", closeFeedback);
    closeFeedbackBtn2.addEventListener("click", closeFeedback);
    copyFeedbackBtn.addEventListener("click", async () => {
      try {
        await navigator.clipboard.writeText(feedbackPreview.value);
        showToast("已复制反馈报告，可直接粘贴给 AI 分析 ✓");
      } catch {
        showToast("复制失败，请手动全选文本框内容复制");
      }
    });
    clearFeedbackBtn.addEventListener("click", () => {
      if (!Object.keys(feedbackMap).length) return;
      if (confirm("确认清空已记录的点赞与点踩反馈吗？")) {
        feedbackMap = {};
        saveFeedback();
        feedbackPreview.value = buildFeedbackReport();
        renderCards();
        showToast("已清空历史反馈");
      }
    });

    // Keyboard navigation
    document.addEventListener("keydown", (e) => {
      const tag = (e.target.tagName || "").toLowerCase();
      if (tag === "input" || tag === "textarea" || tag === "select") {
        if (e.key === "Escape") e.target.blur();
        return;
      }

      if (e.key === "Escape") {
        closeDrawer();
        closeSettings();
        closeFeedback();
      } else if (e.key === "j" || e.key === "J") {
        if (!filteredItems.length) return;
        selectedIndex = Math.min(filteredItems.length - 1, selectedIndex + 1);
        renderCards();
        document.querySelector(`[data-idx="${selectedIndex}"]`)?.scrollIntoView({ block: "nearest", behavior: "smooth" });
      } else if (e.key === "k" || e.key === "K") {
        if (!filteredItems.length) return;
        selectedIndex = Math.max(0, selectedIndex - 1);
        renderCards();
        document.querySelector(`[data-idx="${selectedIndex}"]`)?.scrollIntoView({ block: "nearest", behavior: "smooth" });
      } else if (e.key === "Enter" && selectedIndex >= 0 && filteredItems[selectedIndex]) {
        openDrawer(filteredItems[selectedIndex]);
      } else if ((e.key === "r" || e.key === "R") && selectedIndex >= 0 && filteredItems[selectedIndex]) {
        toggleRead(filteredItems[selectedIndex].id);
      }
    });
  }

  init();
})();
