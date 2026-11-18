import {
  sidecarFetchNewsPerspectives,
  sidecarFetchNewsSources,
  sidecarFetchNewsStories,
  sidecarFetchNewsTopics,
  sidecarHideNewsCluster,
  sidecarManageNewsFeed,
  sidecarManageNewsTopic,
  sidecarRefreshNews,
  sidecarSaveNewsClusterToBrain,
  sidecarSetDomainTrust,
  sidecarTranslateNewsArticle,
} from "./api";
import { escapeHtml, formatRelativeTime, MOD_LABEL, state } from "./state";
import type { NewsLane, NewsStoryCluster } from "./types";

export interface NewsViewActions {
  onOpenSiteUrl: (url: string, title: string) => void;
  onCompareUrls: (urls: Array<{ url: string; title: string }>) => Promise<void>;
  onAskInNewsChat: (prompt: string) => Promise<void>;
  onRefreshShell: () => void;
}

let newsAutoWarmedThisSession = false;

export async function refreshNewsState(lane?: NewsLane): Promise<void> {
  const target = lane ?? state.newsActiveLane ?? "stories";
  if (target === "stories" || target === "foryou" || target === "perspectives") {
    const fetchLane = async () => {
      if (target === "stories") {
        const res = await sidecarFetchNewsStories("top", "", false, 30);
        state.newsStories = res.stories;
        return res.stories;
      }
      if (target === "foryou") {
        const res = await sidecarFetchNewsStories("foryou", "", state.newsExploreMode, 30);
        state.newsForYouStories = res.stories;
        return res.stories;
      }
      const res = await sidecarFetchNewsStories("perspectives", "", state.newsExploreMode, 25);
      state.newsPerspectivesStories = res.stories;
      if (!state.newsSelectedClusterId && res.stories.length > 0) {
        state.newsSelectedClusterId = res.stories[0].cluster_id;
      }
      if (state.newsSelectedClusterId) {
        state.newsPerspectiveMatrix = await sidecarFetchNewsPerspectives(
          state.newsSelectedClusterId,
          false
        );
      }
      return res.stories;
    };

    const initial = await fetchLane();
    if (initial.length === 0 && !newsAutoWarmedThisSession) {
      newsAutoWarmedThisSession = true;
      await sidecarRefreshNews(false, false);
      await fetchLane();
    }
  } else if (target === "topics") {
    const res = await sidecarFetchNewsTopics();
    state.newsTopics = res.topics;
  } else if (target === "sources") {
    const res = await sidecarFetchNewsSources({
      q: state.newsSourcesFilterQuery,
      category: state.newsSourcesFilterCategory,
      band: state.newsSourcesFilterBand,
      conflicted: state.newsSourcesConflictedOnly,
      withRss: state.newsSourcesRssOnly,
    });
    state.newsSources = res.sources;
    state.newsCategories = res.categories;
    state.newsSourcesAsOf = res.as_of;
  }
}

function renderBandPillHtml(band: string, conf10: number): string {
  const lbl = `${(band || "low").toUpperCase()} · ${Number(conf10 || 0).toFixed(1)}/10`;
  const cls = band === "high" || band === "good" ? "news-band-good" : "news-band-low";
  return `<span class="news-band-pill ${cls}">${escapeHtml(lbl)}</span>`;
}

function renderStoryCardsHtml(
  stories: NewsStoryCluster[],
  lane: "stories" | "foryou"
): string {
  if (stories.length === 0) {
    return `
      <div class="kb-card">
        <div class="kb-card-header">
          <span>no news clusters loaded yet</span>
        </div>
        <div class="muted">
          Click [refresh feeds] above to poll active RSS/Atom sources cleanly, or ask a breaking-news question in [ chat ].
        </div>
      </div>
    `;
  }

  return stories
    .map((s) => {
      const bulletsHtml = s.summary_md
        .split("\n")
        .filter((ln) => ln.trim())
        .map((ln) => `<div>${escapeHtml(ln)}</div>`)
        .join("");

      const famHtml = (s.families ?? [])
        .map((f) => {
          const confMark = f.conflict ? " [!]" : "";
          const langTag = f.language && f.language !== "en" ? ` [${f.language}]` : "";
          return `<button class="context-pill" data-news-open-url="${escapeHtml(f.url)}" data-news-open-title="${escapeHtml(s.headline)}" title="trust ${f.trust_effective.toFixed(1)}/10 (${f.category})${langTag}">${escapeHtml(f.domain)} · ${f.trust_effective.toFixed(1)}${escapeHtml(confMark)}${escapeHtml(langTag)}</button>`;
        })
        .join(" ");

      const reasonsHtml =
        s.brain_match_reasons && s.brain_match_reasons.length > 0
          ? `<div class="muted">match: ${escapeHtml(s.brain_match_reasons.join(" · "))}${s.outside_usual ? " · [outside usual sources]" : ""}</div>`
          : "";

      const leadArt = s.articles?.[0];
      const hasNonEnglish = Boolean(leadArt && leadArt.language && leadArt.language !== "en");
      const compareUrls = s.families
        .slice(0, 3)
        .map((f) => `${f.url}|||${s.headline}`)
        .join(";;;");

      return `
        <div class="kb-card news-story-card" data-news-cluster="${escapeHtml(s.cluster_id)}">
          <div class="kb-card-header">
            <span>
              ${renderBandPillHtml(s.has_conflict ? "contested" : s.band, s.confidence10)}
              <strong>${escapeHtml(s.headline)}</strong>
            </span>
            <span class="muted">
              ${s.independent_families} fam${s.collapsed_mirrors > 0 ? ` · +${s.collapsed_mirrors} wire collapsed` : ""} · ${escapeHtml(formatRelativeTime(String(Math.floor(s.updated_at))))}
            </span>
          </div>
          ${
            s.lead_image
              ? `<div class="news-card-media-row"><img class="news-card-thumb" src="${escapeHtml(s.lead_image)}" alt="" loading="lazy" /><div>${bulletsHtml}</div></div>`
              : `<div>${bulletsHtml}</div>`
          }
          ${reasonsHtml}
          <div class="composer-controls">${famHtml}</div>
          <div class="composer-controls">
            ${
              leadArt
                ? `<button class="citation-link" data-news-open-reader="${escapeHtml(leadArt.article_id)}">[open reader]</button>`
                : ""
            }
            ${
              hasNonEnglish && leadArt
                ? `<button class="citation-link" data-news-translate="${escapeHtml(leadArt.article_id)}">[translate ${escapeHtml(leadArt.language)}->en]</button>`
                : ""
            }
            <button class="citation-link" data-news-ask-chat="${escapeHtml(s.headline)}">[ask in chat]</button>
            ${
              s.families.length >= 2
                ? `<button class="citation-link" data-news-open-perspectives="${escapeHtml(s.cluster_id)}">[perspectives (${s.families.length})]</button>
                   <button class="citation-link" data-news-compare-urls="${escapeHtml(compareUrls)}">[compare ${Math.min(3, s.families.length)} tabs]</button>`
                : ""
            }
            <button class="citation-link" data-news-save-brain="${escapeHtml(s.cluster_id)}">[save to brain]</button>
            ${
              lane === "foryou" && s.topic_tags.length > 0
                ? `<button class="citation-link" data-news-less-topic="${escapeHtml(s.topic_tags[0])}">[less like this]</button>`
                : ""
            }
            <button class="citation-link" data-news-hide-cluster="${escapeHtml(s.cluster_id)}">[hide]</button>
          </div>
        </div>
      `;
    })
    .join("");
}

function renderPerspectivesLaneHtml(): string {
  const list = state.newsPerspectivesStories;
  if (list.length === 0) {
    return `
      <div class="kb-card">
        <div class="muted">
          No multi-family stories yet. Click [refresh feeds (+ web)] or ask a contested news question in [ chat ] first.
        </div>
      </div>
    `;
  }

  const selectorHtml = `
    <div class="kb-card">
      <div class="vault-form-row">
        <label class="muted">story cluster (${list.length}):</label>
        <select id="news-persp-cluster-select" class="vault-input">
          ${list
            .map(
              (s) =>
                `<option value="${escapeHtml(s.cluster_id)}" ${s.cluster_id === state.newsSelectedClusterId ? "selected" : ""}>[${s.families.length} fam · ${s.confidence10.toFixed(1)}] ${escapeHtml(s.headline.slice(0, 72))}</option>`
            )
            .join("")}
        </select>
        <button id="news-persp-recompute-btn" type="button">[re-analyze perspectives]</button>
      </div>
    </div>
  `;

  const m = state.newsPerspectiveMatrix;
  if (!m || !m.ok) {
    return `${selectorHtml}<div class="kb-card"><span class="muted">Select a cluster to build its Perspective Spread matrix.</span></div>`;
  }

  const comparePayload = (m.framings ?? [])
    .flatMap((fr) => fr.sources.slice(0, 1))
    .slice(0, 4)
    .map((s) => `${s.url}|||${m.headline}`)
    .join(";;;");

  const gridCols = Math.max(1, Math.min(3, (m.framings ?? []).length));

  return `
    ${selectorHtml}
    <div class="kb-card">
      <div class="kb-card-header">
        <span><strong>perspective spread · ${escapeHtml(m.headline)}</strong></span>
        <span>
          ${comparePayload ? `<button class="citation-link" data-news-compare-urls="${escapeHtml(comparePayload)}">[tile in compare view (${MOD_LABEL}+m)]</button>` : ""}
        </span>
      </div>
      <div class="muted">analyzer: ${escapeHtml(m.analyzer_model)} · ${escapeHtml(m.privacy_disclosure)}</div>

      <div class="kb-section" style="margin-top:6px;">
        <div class="kb-section-title"><span>agreed facts across independent families</span></div>
        ${(m.agreed ?? []).map((a) => `<div>* ${escapeHtml(a)}</div>`).join("")}
      </div>

      <div class="news-persp-grid" style="grid-template-columns: repeat(${gridCols}, minmax(0, 1fr));">
        ${(m.framings ?? [])
          .map(
            (fr) => `
          <div class="news-persp-col kb-card">
            <div class="kb-card-header"><strong>${escapeHtml(fr.label)}</strong></div>
            <div class="composer-controls">
              ${fr.sources
                .map(
                  (src) => `
                <button class="context-pill" data-news-open-url="${escapeHtml(src.url)}" data-news-open-title="${escapeHtml(src.title)}" title="${escapeHtml(src.why)}">
                  ${escapeHtml(src.domain)} (${src.trust_effective.toFixed(1)} · ${escapeHtml(src.category)})${src.conflict ? " [!]" : ""}
                </button>`
                )
                .join("")}
            </div>
            ${fr.claims.map((cl) => `<div style="margin-top:4px;">* ${escapeHtml(cl)}</div>`).join("")}
          </div>`
          )
          .join("")}
      </div>

      <div class="kb-section" style="margin-top:6px;">
        <div class="kb-section-title"><span>blind spots, missing perspectives &amp; system counterfactual</span></div>
        ${(m.blind_spots ?? []).map((b) => `<div class="muted">- ${escapeHtml(b)}</div>`).join("")}
        <div class="muted">- counterfactual: ${escapeHtml(m.system_counterfactual)}</div>
      </div>
    </div>
  `;
}

function renderTopicsLaneHtml(): string {
  const topics = state.newsTopics;
  return `
    <div class="kb-card">
      <div class="kb-card-header">
        <span><strong>tracked news topics &amp; watches</strong></span>
        <span class="muted">queries automatically stripped by PII Scrubber before searching</span>
      </div>
      <div class="vault-form-row">
        <input id="news-topic-name-input" class="vault-input" placeholder="e.g. EU AI Act, Berlin Transit, Semiconductors_" />
        <input id="news-topic-kw-input" class="vault-input" placeholder="optional keywords comma-separated_" />
        <button id="news-topic-add-btn" type="button">[+ track topic &amp; watch]</button>
      </div>
    </div>
    ${
      topics.length === 0
        ? `<div class="kb-card"><span class="muted">No custom beats added yet. Track any topic above or click [save to brain] on stories.</span></div>`
        : topics
            .map(
              (t) => `
          <div class="source-row">
            <div class="source-row-top">
              <span>
                <strong>${escapeHtml(t.name)}</strong>
                ${t.suppressed ? `<span class="source-cut-badge">[suppressed]</span>` : ""}
                ${t.badge_unread ? `<span class="source-cut-badge">[watch !]</span>` : ""}
              </span>
              <span>
                <button class="rail-menu-btn" data-news-ask-chat="${escapeHtml(`${t.name} latest news`)}">[query now]</button>
                <button class="rail-menu-btn" data-news-topic-del="${escapeHtml(t.topic_id)}">[remove]</button>
              </span>
            </div>
            <div class="muted">
              keywords: ${escapeHtml(t.keywords.join(", ") || t.name)} · last checked: ${
                t.last_checked_at > 0 ? escapeHtml(formatRelativeTime(String(Math.floor(t.last_checked_at)))) : "pending"
              }
            </div>
          </div>`
            )
            .join("")
    }
  `;
}

function renderSourcesLaneHtml(): string {
  const cats = state.newsCategories ?? [];
  const srcs = state.newsSources ?? [];

  return `
    <div class="kb-card">
      <div class="kb-card-header">
        <span><strong>source trust registry &amp; RSS feeds</strong> (as of ${escapeHtml(state.newsSourcesAsOf || "2026-10-09")})</span>
        <span class="muted">effective = 0.7 * system + 0.3 * yours (30% hard cap)</span>
      </div>
      <div class="vault-form-row">
        <input id="news-src-search-input" class="vault-input" value="${escapeHtml(state.newsSourcesFilterQuery)}" placeholder="filter domain, category, rubric_" />
        <select id="news-src-cat-select" class="vault-input">
          <option value="">all categories (${cats.length})</option>
          ${cats
            .map(
              (c) =>
                `<option value="${escapeHtml(c.id)}" ${state.newsSourcesFilterCategory === c.id ? "selected" : ""}>${escapeHtml(c.id)} (${c.score ?? "-"})</option>`
            )
            .join("")}
        </select>
        <select id="news-src-band-select" class="vault-input">
          <option value="">all bands</option>
          <option value="high" ${state.newsSourcesFilterBand === "high" ? "selected" : ""}>9-10 high trust</option>
          <option value="good" ${state.newsSourcesFilterBand === "good" ? "selected" : ""}>7-8 good trust</option>
          <option value="low" ${state.newsSourcesFilterBand === "low" ? "selected" : ""}>5-6 low trust</option>
          <option value="sceptical" ${state.newsSourcesFilterBand === "sceptical" ? "selected" : ""}>0-4 sceptical</option>
          <option value="unscored" ${state.newsSourcesFilterBand === "unscored" ? "selected" : ""}>unscored (5.0)</option>
        </select>
        <label class="muted"><input type="checkbox" id="news-src-rss-chk" ${state.newsSourcesRssOnly ? "checked" : ""} /> with RSS</label>
        <label class="muted"><input type="checkbox" id="news-src-conf-chk" ${state.newsSourcesConflictedOnly ? "checked" : ""} /> conflicts</label>
      </div>
      <div class="vault-form-row" style="margin-top:6px;">
        <input id="news-add-feed-url" class="vault-input" placeholder="add RSS/Atom URL (e.g. https://rss.dw.com/xml/rss-en-all) or domain_" />
        <input id="news-add-feed-title" class="vault-input" placeholder="optional label_" />
        <button id="news-add-feed-btn" type="button">[+ add feed / domain]</button>
      </div>
    </div>
    ${srcs
      .slice(0, 120)
      .map((d) => {
        const personalVal = d.personal ?? d.system;
        const confBadge = d.conflict
          ? ` <span class="msg-error-badge" title="|yours - system| >= 3.0">[conflict · you disagree]</span>`
          : "";
        const rubricTag = d.rubric ? ` · rubric: ${d.rubric}` : "";
        const feedsHtml = d.feeds
          .map(
            (f) => `
          <div class="rail-row">
            <span class="truncate muted">RSS (${escapeHtml(f.language)}): ${escapeHtml(f.feed_url)}</span>
            <button class="rail-menu-btn" data-news-toggle-feed="${escapeHtml(f.feed_id)}" data-enabled="${f.enabled ? "0" : "1"}">[${f.enabled ? "enabled" : "paused"}]</button>
          </div>`
          )
          .join("");
        return `
          <div class="source-row">
            <div class="source-row-top">
              <span>
                <strong>${escapeHtml(d.domain)}</strong>
                <span class="muted">· ${escapeHtml(d.category || "unscored")} · fam:${escapeHtml(d.family)}${escapeHtml(rubricTag)}</span>
              </span>
              <span>
                eff <strong>${d.effective.toFixed(2)}</strong>/10 [${escapeHtml(d.band)}]${confBadge}
              </span>
            </div>
            <div class="muted">
              system: ${d.system.toFixed(1)} (${escapeHtml(d.why || "rubric")}) · yours: ${
          d.personal !== null ? d.personal.toFixed(1) : `default (${d.system.toFixed(1)})`
        }
            </div>
            <div class="vault-form-row">
              <span class="muted">personal (0-10, 30% max blend):</span>
              <input type="range" min="0" max="10" step="0.5" value="${personalVal}" data-news-src-slider="${escapeHtml(d.domain)}" />
              <span class="muted" data-news-src-slider-val="${escapeHtml(d.domain)}">${personalVal.toFixed(1)}</span>
              ${
                d.personal !== null
                  ? `<button class="rail-menu-btn" data-news-src-reset="${escapeHtml(d.domain)}">[reset]</button>`
                  : ""
              }
            </div>
            ${feedsHtml}
          </div>`;
      })
      .join("")}
  `;
}

function renderReaderOverlayHtml(): string {
  const aid = state.newsReaderArticleId;
  if (!aid) return "";
  const allArts = [
    ...state.newsStories.flatMap((s) => s.articles ?? []),
    ...state.newsForYouStories.flatMap((s) => s.articles ?? []),
    ...state.newsPerspectivesStories.flatMap((s) => s.articles ?? []),
  ];
  const art = allArts.find((a) => a.article_id === aid);
  if (!art) return "";
  const showingTranslated = Boolean(art.translated_text) && !state.newsReaderShowOriginal;
  const displayText = showingTranslated
    ? art.translated_text || ""
    : art.body_text || art.snippet || "(summary only; click open live tab to read full article)";

  return `
    <div class="kb-card news-reader-overlay">
      <div class="kb-card-header">
        <span><strong>reader · ${escapeHtml(art.domain)}</strong> (${art.trust_effective.toFixed(1)}/10 · ${escapeHtml(art.category)})</span>
        <span>
          ${art.translated_text ? `<button id="news-reader-toggle-orig-btn" class="citation-link">[${showingTranslated ? `show original (${art.language})` : "show translation"}]</button>` : `<button class="citation-link" data-news-translate="${escapeHtml(art.article_id)}">[translate]</button>`}
          <button class="citation-link" data-news-open-url="${escapeHtml(art.url)}" data-news-open-title="${escapeHtml(art.title)}">[open live tab (focus mode)]</button>
          <button id="news-reader-close-btn" class="citation-link">[close reader]</button>
        </span>
      </div>
      <div><strong>${escapeHtml(art.title)}</strong></div>
      ${art.author ? `<div class="muted">by ${escapeHtml(art.author)} · ${escapeHtml(formatRelativeTime(String(Math.floor(art.published_at))))}</div>` : ""}
      ${art.image_url ? `<img class="chat-attachment-img" src="${escapeHtml(art.image_url)}" alt="" />` : ""}
      <div class="msg-body">${escapeHtml(displayText)}</div>
    </div>
  `;
}

export function renderNewsLaneView(
  container: HTMLElement,
  actions: NewsViewActions
): void {
  const lane = state.newsActiveLane;
  let bodyHtml = "";
  if (lane === "stories") {
    bodyHtml = renderStoryCardsHtml(state.newsStories, "stories");
  } else if (lane === "foryou") {
    bodyHtml = renderStoryCardsHtml(state.newsForYouStories, "foryou");
  } else if (lane === "perspectives") {
    bodyHtml = renderPerspectivesLaneHtml();
  } else if (lane === "topics") {
    bodyHtml = renderTopicsLaneHtml();
  } else if (lane === "sources") {
    bodyHtml = renderSourcesLaneHtml();
  }

  container.innerHTML = `
    <div class="knowledge-view">
      <div class="kb-card-header" style="border-bottom: 1px solid #1a1a1a; padding-bottom: 8px;">
        <span>
          <strong>satz news · ${escapeHtml(lane)}</strong>
          ${state.newsLoading ? `<span class="muted"> [refreshing...]</span>` : ""}
        </span>
        <span class="composer-controls">
          <button id="news-explore-toggle-btn" class="${state.newsExploreMode ? "active" : ""}" type="button">[explore outside preferences: ${state.newsExploreMode ? "on" : "off"}]</button>
          <button id="news-refresh-feeds-btn" type="button">[refresh feeds]</button>
          <button id="news-refresh-search-btn" type="button">[refresh feeds + brave/web]</button>
        </span>
      </div>
      ${
        state.newsStatusMessage
          ? `<div class="profile-status-banner">${escapeHtml(state.newsStatusMessage)}</div>`
          : ""
      }
      ${renderReaderOverlayHtml()}
      ${bodyHtml}
    </div>
  `;

  bindNewsViewEvents(container, actions);
}

function bindNewsViewEvents(container: HTMLElement, actions: NewsViewActions): void {
  container.querySelector("#news-refresh-feeds-btn")?.addEventListener("click", () => {
    void (async () => {
      state.newsLoading = true;
      state.newsStatusMessage = "polling conditional RSS/Atom feeds...";
      renderNewsLaneView(container, actions);
      const res = await sidecarRefreshNews(true, false);
      state.newsLoading = false;
      state.newsStatusMessage = res.ok
        ? `feeds synced: ${res.fetched_feeds ?? 0} fetched, ${res.not_modified ?? 0} unchanged (304), ${res.articles_ingested ?? 0} articles, ${res.clusters ?? 0} clusters`
        : `error: ${res.error ?? "feed refresh failed"}`;
      await refreshNewsState(state.newsActiveLane);
      renderNewsLaneView(container, actions);
      actions.onRefreshShell();
    })();
  });

  container.querySelector("#news-refresh-search-btn")?.addEventListener("click", () => {
    void (async () => {
      state.newsLoading = true;
      state.newsStatusMessage = "polling feeds + PII-scrubbed web search for tracked topics...";
      renderNewsLaneView(container, actions);
      const res = await sidecarRefreshNews(true, true);
      state.newsLoading = false;
      state.newsStatusMessage = res.ok
        ? `feeds + search synced: ${res.articles_ingested ?? 0} articles into ${res.clusters ?? 0} clusters`
        : `error: ${res.error ?? "refresh failed"}`;
      await refreshNewsState(state.newsActiveLane);
      renderNewsLaneView(container, actions);
      actions.onRefreshShell();
    })();
  });

  container.querySelector("#news-explore-toggle-btn")?.addEventListener("click", () => {
    state.newsExploreMode = !state.newsExploreMode;
    void refreshNewsState(state.newsActiveLane).then(() => {
      renderNewsLaneView(container, actions);
    });
  });

  container.querySelectorAll("[data-news-open-url]").forEach((btn) => {
    btn.addEventListener("click", () => {
      const url = (btn as HTMLElement).getAttribute("data-news-open-url") ?? "";
      const title = (btn as HTMLElement).getAttribute("data-news-open-title") ?? "";
      if (url) actions.onOpenSiteUrl(url, title);
    });
  });

  container.querySelectorAll("[data-news-compare-urls]").forEach((btn) => {
    btn.addEventListener("click", () => {
      const raw = (btn as HTMLElement).getAttribute("data-news-compare-urls") ?? "";
      const pairs = raw
        .split(";;;")
        .filter(Boolean)
        .map((p) => {
          const [url, title] = p.split("|||");
          return { url, title: title || url };
        });
      if (pairs.length >= 2) {
        void actions.onCompareUrls(pairs);
      }
    });
  });

  container.querySelectorAll("[data-news-ask-chat]").forEach((btn) => {
    btn.addEventListener("click", () => {
      const prompt = (btn as HTMLElement).getAttribute("data-news-ask-chat") ?? "";
      if (prompt) void actions.onAskInNewsChat(prompt);
    });
  });

  container.querySelectorAll("[data-news-open-perspectives]").forEach((btn) => {
    btn.addEventListener("click", () => {
      const cid = (btn as HTMLElement).getAttribute("data-news-open-perspectives") ?? "";
      if (!cid) return;
      state.newsActiveLane = "perspectives";
      state.activeTabId = "news-lane:perspectives";
      state.newsSelectedClusterId = cid;
      void refreshNewsState("perspectives").then(() => {
        actions.onRefreshShell();
      });
    });
  });

  container.querySelectorAll("[data-news-save-brain]").forEach((btn) => {
    btn.addEventListener("click", () => {
      const cid = (btn as HTMLElement).getAttribute("data-news-save-brain") ?? "";
      if (!cid) return;
      void sidecarSaveNewsClusterToBrain(cid).then((r) => {
        state.newsStatusMessage = r.ok
          ? "saved story cluster to Satz Brain (News/Stories)."
          : `error: ${r.error ?? "unlock profile to save to Brain"}`;
        renderNewsLaneView(container, actions);
      });
    });
  });

  container.querySelectorAll("[data-news-hide-cluster]").forEach((btn) => {
    btn.addEventListener("click", () => {
      const cid = (btn as HTMLElement).getAttribute("data-news-hide-cluster") ?? "";
      if (!cid) return;
      void sidecarHideNewsCluster(cid).then(async () => {
        await refreshNewsState(state.newsActiveLane);
        renderNewsLaneView(container, actions);
      });
    });
  });

  container.querySelectorAll("[data-news-less-topic]").forEach((btn) => {
    btn.addEventListener("click", () => {
      const name = (btn as HTMLElement).getAttribute("data-news-less-topic") ?? "";
      if (!name) return;
      void sidecarManageNewsTopic({ action: "suppress", name }).then(async () => {
        state.newsStatusMessage = `reduced future stories on "${name}".`;
        await refreshNewsState("foryou");
        renderNewsLaneView(container, actions);
      });
    });
  });

  container.querySelectorAll("[data-news-open-reader]").forEach((btn) => {
    btn.addEventListener("click", () => {
      state.newsReaderArticleId = (btn as HTMLElement).getAttribute("data-news-open-reader") ?? null;
      state.newsReaderShowOriginal = false;
      renderNewsLaneView(container, actions);
    });
  });

  container.querySelector("#news-reader-close-btn")?.addEventListener("click", () => {
    state.newsReaderArticleId = null;
    renderNewsLaneView(container, actions);
  });

  container.querySelector("#news-reader-toggle-orig-btn")?.addEventListener("click", () => {
    state.newsReaderShowOriginal = !state.newsReaderShowOriginal;
    renderNewsLaneView(container, actions);
  });

  container.querySelectorAll("[data-news-translate]").forEach((btn) => {
    btn.addEventListener("click", () => {
      const aid = (btn as HTMLElement).getAttribute("data-news-translate") ?? "";
      if (!aid) return;
      state.newsStatusMessage = "translating article via news_capture role...";
      renderNewsLaneView(container, actions);
      void sidecarTranslateNewsArticle(aid, "en").then(async (r) => {
        if (r.ok && r.translated_text) {
          for (const s of [...state.newsStories, ...state.newsForYouStories, ...state.newsPerspectivesStories]) {
            for (const a of s.articles) {
              if (a.article_id === aid) a.translated_text = r.translated_text;
            }
          }
          state.newsReaderArticleId = aid;
          state.newsReaderShowOriginal = false;
          state.newsStatusMessage = "translated article.";
        } else {
          state.newsStatusMessage = `error: ${r.error ?? "translation failed"}`;
        }
        renderNewsLaneView(container, actions);
      });
    });
  });

  // Perspectives events
  const perspSel = container.querySelector("#news-persp-cluster-select") as HTMLSelectElement | null;
  perspSel?.addEventListener("change", () => {
    state.newsSelectedClusterId = perspSel.value || null;
    void refreshNewsState("perspectives").then(() => {
      renderNewsLaneView(container, actions);
    });
  });

  container.querySelector("#news-persp-recompute-btn")?.addEventListener("click", () => {
    if (!state.newsSelectedClusterId) return;
    state.newsStatusMessage = "re-analyzing source perspectives...";
    renderNewsLaneView(container, actions);
    void sidecarFetchNewsPerspectives(state.newsSelectedClusterId, true).then((mat) => {
      state.newsPerspectiveMatrix = mat;
      state.newsStatusMessage = mat?.ok ? "perspective matrix updated." : "perspective analysis failed.";
      renderNewsLaneView(container, actions);
    });
  });

  // Topics events
  container.querySelector("#news-topic-add-btn")?.addEventListener("click", () => {
    const nameEl = container.querySelector("#news-topic-name-input") as HTMLInputElement | null;
    const kwEl = container.querySelector("#news-topic-kw-input") as HTMLInputElement | null;
    const name = nameEl?.value.trim() ?? "";
    if (!name) return;
    void sidecarManageNewsTopic({
      action: "add",
      name,
      keywords: kwEl?.value.trim() ?? "",
      watch: true,
    }).then(async (r) => {
      state.newsStatusMessage = r.ok ? `tracked topic "${name}" with active watch.` : `error: ${r.error}`;
      await refreshNewsState("topics");
      renderNewsLaneView(container, actions);
      actions.onRefreshShell();
    });
  });

  container.querySelectorAll("[data-news-topic-del]").forEach((btn) => {
    btn.addEventListener("click", () => {
      const tid = (btn as HTMLElement).getAttribute("data-news-topic-del") ?? "";
      if (!tid) return;
      void sidecarManageNewsTopic({ action: "delete", topic_id: tid }).then(async () => {
        await refreshNewsState("topics");
        renderNewsLaneView(container, actions);
        actions.onRefreshShell();
      });
    });
  });

  // Sources events
  const reloadSources = () => {
    void refreshNewsState("sources").then(() => {
      renderNewsLaneView(container, actions);
    });
  };
  const srcQ = container.querySelector("#news-src-search-input") as HTMLInputElement | null;
  srcQ?.addEventListener("change", () => {
    state.newsSourcesFilterQuery = srcQ.value.trim();
    reloadSources();
  });
  const srcCat = container.querySelector("#news-src-cat-select") as HTMLSelectElement | null;
  srcCat?.addEventListener("change", () => {
    state.newsSourcesFilterCategory = srcCat.value;
    reloadSources();
  });
  const srcBand = container.querySelector("#news-src-band-select") as HTMLSelectElement | null;
  srcBand?.addEventListener("change", () => {
    state.newsSourcesFilterBand = srcBand.value;
    reloadSources();
  });
  const rssChk = container.querySelector("#news-src-rss-chk") as HTMLInputElement | null;
  rssChk?.addEventListener("change", () => {
    state.newsSourcesRssOnly = rssChk.checked;
    reloadSources();
  });
  const confChk = container.querySelector("#news-src-conf-chk") as HTMLInputElement | null;
  confChk?.addEventListener("change", () => {
    state.newsSourcesConflictedOnly = confChk.checked;
    reloadSources();
  });

  container.querySelector("#news-add-feed-btn")?.addEventListener("click", () => {
    const urlEl = container.querySelector("#news-add-feed-url") as HTMLInputElement | null;
    const titleEl = container.querySelector("#news-add-feed-title") as HTMLInputElement | null;
    const val = urlEl?.value.trim() ?? "";
    if (!val) return;
    const isUrl = val.startsWith("http://") || val.startsWith("https://");
    void sidecarManageNewsFeed(
      isUrl
        ? { feed_url: val, title: titleEl?.value.trim() ?? "" }
        : { domain: val, title: titleEl?.value.trim() ?? "" }
    ).then((r) => {
      state.newsStatusMessage = r.ok ? `added ${val}` : `error: ${r.error}`;
      reloadSources();
    });
  });

  container.querySelectorAll("[data-news-toggle-feed]").forEach((btn) => {
    btn.addEventListener("click", () => {
      const fid = (btn as HTMLElement).getAttribute("data-news-toggle-feed") ?? "";
      const en = (btn as HTMLElement).getAttribute("data-enabled") === "1";
      void sidecarManageNewsFeed({ action: "toggle", feed_id: fid, enabled: en }).then(() => {
        reloadSources();
      });
    });
  });

  container.querySelectorAll("[data-news-src-slider]").forEach((el) => {
    const inp = el as HTMLInputElement;
    const dom = inp.getAttribute("data-news-src-slider") ?? "";
    inp.addEventListener("input", () => {
      const valEl = container.querySelector(`[data-news-src-slider-val="${dom}"]`);
      if (valEl) valEl.textContent = Number(inp.value).toFixed(1);
    });
    inp.addEventListener("change", () => {
      if (!dom) return;
      void sidecarSetDomainTrust(dom, Number(inp.value)).then(() => {
        reloadSources();
      });
    });
  });

  container.querySelectorAll("[data-news-src-reset]").forEach((btn) => {
    btn.addEventListener("click", () => {
      const dom = (btn as HTMLElement).getAttribute("data-news-src-reset") ?? "";
      if (!dom) return;
      void sidecarSetDomainTrust(dom, null).then(() => {
        reloadSources();
      });
    });
  });
}
