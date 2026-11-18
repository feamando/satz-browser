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
import { icon } from "./design-system/icons";
import { escapeHtml, formatRelativeTime, MOD_LABEL, state } from "./state";
import type { NewsLane, NewsStoryCluster } from "./types";

export interface NewsViewActions {
  onOpenSiteUrl: (url: string, title: string) => void;
  onCompareUrls: (urls: Array<{ url: string; title: string }>) => Promise<void>;
  onAskInNewsChat: (prompt: string) => Promise<void>;
  onRefreshShell: () => void;
}

let newsAutoWarmedThisSession = false;
const expandedStoryFamilyPills = new Set<string>();

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

function renderStatusBannerHtml(msg: string): string {
  const low = msg.toLowerCase();
  const variant = low.startsWith("error") ? "banner danger" : "banner";
  return `<div class="${variant}">${escapeHtml(msg)}</div>`;
}

function renderBandPillHtml(band: string, conf10: number): string {
  const num = Number(conf10 || 0);
  const pct = Math.max(0, Math.min(100, Math.round(num * 10)));
  const isLow = band === "low" || band === "sceptical" || band === "contested";
  const tip = `${(band || "low").toUpperCase()} · ${num.toFixed(1)}/10`;
  return `<span class="conf ${isLow ? "low" : ""}" style="--c:${pct}%" title="${escapeHtml(tip)}"><i></i>${num.toFixed(1)}</span>`;
}

function renderStoryCardsHtml(
  stories: NewsStoryCluster[],
  lane: "stories" | "foryou"
): string {
  if (stories.length === 0) {
    return `
      <div class="card">
        <div class="card-h">
          <b>No news clusters loaded yet</b>
        </div>
        <div class="muted">
          Click Refresh feeds above to poll active RSS/Atom sources, or ask a breaking-news question in Chat.
        </div>
      </div>
    `;
  }

  return `<div class="news-story-list">${stories
    .map((s) => {
      const bulletLines = s.summary_md
        .split("\n")
        .map((ln) => ln.replace(/^[-*•]\s+/, "").trim())
        .filter(Boolean)
        .slice(0, 3);
      const bulletsHtml =
        bulletLines.length > 0
          ? `<ul>${bulletLines.map((ln) => `<li>${escapeHtml(ln)}</li>`).join("")}</ul>`
          : "";

      const fams = s.families ?? [];
      const isExpanded = expandedStoryFamilyPills.has(s.cluster_id);
      const shownFams = isExpanded ? fams : fams.slice(0, 2);
      const hiddenFams = isExpanded ? [] : fams.slice(2);
      const famHtml = shownFams
        .map((f) => {
          const confMark = f.conflict ? " · !" : "";
          const langTag = f.language && f.language !== "en" ? ` (${f.language})` : "";
          return `<button type="button" class="pill" data-news-open-url="${escapeHtml(f.url)}" data-news-open-title="${escapeHtml(s.headline)}" title="Trust ${f.trust_effective.toFixed(1)}/10 (${escapeHtml(f.category)})${escapeHtml(langTag)}">${escapeHtml(f.domain)} · ${f.trust_effective.toFixed(1)}${escapeHtml(confMark)}${escapeHtml(langTag)}</button>`;
        })
        .join("");
      const moreFamsTooltip = hiddenFams
        .map((f) => `${f.domain} (${f.trust_effective.toFixed(1)})`)
        .join(", ");
      const moreFamsPill =
        hiddenFams.length > 0
          ? `<button type="button" class="pill" data-news-expand-fams="${escapeHtml(s.cluster_id)}" title="${escapeHtml(moreFamsTooltip)}">+${hiddenFams.length}</button>`
          : isExpanded && fams.length > 2
            ? `<button type="button" class="pill" data-news-expand-fams="${escapeHtml(s.cluster_id)}" title="Collapse sources">Less</button>`
            : "";

      const reasonsParts = s.brain_match_reasons ?? [];
      const reasonsHtml =
        reasonsParts.length > 0 || s.outside_usual
          ? `<div class="story-match">
              ${reasonsParts.length > 0 ? `<span>Match: ${escapeHtml(reasonsParts.join(" · "))}</span>` : ""}
              ${s.outside_usual ? `<span class="flag">outside usual sources</span>` : ""}
            </div>`
          : "";

      const leadArt = s.articles?.[0];
      const hasNonEnglish = Boolean(leadArt && leadArt.language && leadArt.language !== "en");
      const compareUrls = fams
        .slice(0, 3)
        .map((f) => `${f.url}|||${s.headline}`)
        .join(";;;");

      const relAge = formatRelativeTime(String(Math.floor(s.updated_at)));
      const statusHtml = s.has_conflict
        ? `<span class="live">contested · ${escapeHtml(relAge)}</span>`
        : `<span>${s.independent_families} fam · ${escapeHtml(relAge)}</span>`;
      const primaryTopic = s.topic_tags?.[0] ?? "";
      const secondActionKind: "perspectives" | "translate" | "ask" =
        fams.length >= 2
          ? "perspectives"
          : hasNonEnglish && leadArt
            ? "translate"
            : "ask";

      const secondActionHtml =
        secondActionKind === "perspectives"
          ? `<button type="button" class="btn-text" data-news-open-perspectives="${escapeHtml(s.cluster_id)}">Perspectives (${fams.length})</button>`
          : secondActionKind === "translate" && leadArt
            ? `<button type="button" class="btn-text" data-news-translate="${escapeHtml(leadArt.article_id)}">Translate ${escapeHtml(leadArt.language)}→en</button>`
            : `<button type="button" class="btn-text" data-news-ask-chat="${escapeHtml(s.headline)}">Ask in chat</button>`;

      const menuOpen = state.newsStoryMenuId === s.cluster_id;

      return `
        <article class="story ${s.lead_image ? "" : "no-thumb"}" data-news-cluster="${escapeHtml(s.cluster_id)}">
          ${
            s.lead_image
              ? `<img class="story-thumb" src="${escapeHtml(s.lead_image)}" alt="" loading="lazy" referrerpolicy="no-referrer" />`
              : ""
          }
          <div class="story-c">
            <div class="story-meta">
              ${statusHtml}
              ${primaryTopic ? `<span>${escapeHtml(primaryTopic)}</span>` : ""}
              ${s.collapsed_mirrors > 0 ? `<span>+${s.collapsed_mirrors} wire</span>` : ""}
              ${renderBandPillHtml(s.has_conflict ? "contested" : s.band, s.confidence10)}
            </div>
            <h3 class="story-title">${escapeHtml(s.headline)}</h3>
            ${bulletsHtml}
            ${reasonsHtml}
            <div class="story-foot">
              <div class="pills ${isExpanded ? "expanded" : ""}">
                ${famHtml}${moreFamsPill}
              </div>
              <div class="acts">
                ${
                  leadArt
                    ? `<button type="button" class="btn-text pri" data-news-open-reader="${escapeHtml(leadArt.article_id)}">Open reader</button>`
                    : ""
                }
                ${secondActionHtml}
                <button type="button" class="btn-text" data-news-save-brain="${escapeHtml(s.cluster_id)}">Save</button>
                <div class="story-more-anchor">
                  <button
                    type="button"
                    class="icon-btn"
                    data-news-story-menu="${escapeHtml(s.cluster_id)}"
                    title="More actions"
                    aria-expanded="${menuOpen ? "true" : "false"}"
                  >${icon("more", "ico-sm")}</button>
                  ${
                    menuOpen
                      ? `<div class="menu story-more-menu" role="menu">
                          ${
                            fams.length >= 2
                              ? `<button type="button" class="menu-item" data-news-compare-urls="${escapeHtml(compareUrls)}">${icon("compare", "ico-sm")}<span>Compare (${Math.min(3, fams.length)})</span></button>`
                              : ""
                          }
                          ${
                            hasNonEnglish && leadArt && secondActionKind !== "translate"
                              ? `<button type="button" class="menu-item" data-news-translate="${escapeHtml(leadArt.article_id)}">${icon("translate", "ico-sm")}<span>Translate ${escapeHtml(leadArt.language)}→en</span></button>`
                              : ""
                          }
                          ${
                            secondActionKind !== "ask"
                              ? `<button type="button" class="menu-item" data-news-ask-chat="${escapeHtml(s.headline)}">${icon("chat", "ico-sm")}<span>Ask in chat</span></button>`
                              : ""
                          }
                          ${
                            lane === "foryou" && s.topic_tags.length > 0
                              ? `<button type="button" class="menu-item" data-news-less-topic="${escapeHtml(s.topic_tags[0])}">${icon("x", "ico-sm")}<span>Less like this</span></button>`
                              : ""
                          }
                          <button type="button" class="menu-item danger" data-news-hide-cluster="${escapeHtml(s.cluster_id)}">${icon("trash", "ico-sm")}<span>Hide</span></button>
                        </div>`
                      : ""
                  }
                </div>
              </div>
            </div>
          </div>
        </article>
      `;
    })
    .join("")}</div>`;
}

function renderPerspectivesLaneHtml(): string {
  const list = state.newsPerspectivesStories;
  if (list.length === 0) {
    return `
      <div class="card">
        <div class="muted">
          No multi-family stories yet. Refresh feeds (+ web) or ask a contested news question in Chat first.
        </div>
      </div>
    `;
  }

  const selectorHtml = `
    <div class="card">
      <div class="form-row">
        <label class="muted">Story cluster (${list.length})</label>
        <select id="news-persp-cluster-select" class="select">
          ${list
            .map(
              (s) =>
                `<option value="${escapeHtml(s.cluster_id)}" ${s.cluster_id === state.newsSelectedClusterId ? "selected" : ""}>${s.families.length} fam · ${s.confidence10.toFixed(1)} · ${escapeHtml(s.headline.slice(0, 72))}</option>`
            )
            .join("")}
        </select>
        <button id="news-persp-recompute-btn" type="button" class="btn">Re-analyze perspectives</button>
      </div>
    </div>
  `;

  const m = state.newsPerspectiveMatrix;
  if (!m || !m.ok) {
    return `${selectorHtml}<div class="card"><span class="muted">Select a cluster to build its Perspective Spread matrix.</span></div>`;
  }

  const comparePayload = (m.framings ?? [])
    .flatMap((fr) => fr.sources.slice(0, 1))
    .slice(0, 4)
    .map((s) => `${s.url}|||${m.headline}`)
    .join(";;;");

  const gridCols = Math.max(1, Math.min(3, (m.framings ?? []).length));

  return `
    ${selectorHtml}
    <div class="card">
      <div class="card-h">
        <b>Perspective spread</b>
        <span class="truncate muted">${escapeHtml(m.headline)}</span>
        <span class="end">
          ${comparePayload ? `<button type="button" class="btn" data-news-compare-urls="${escapeHtml(comparePayload)}">${icon("compare", "ico-sm")}<span>Tile in Compare (${escapeHtml(MOD_LABEL)}+M)</span></button>` : ""}
        </span>
      </div>
      <div class="muted">Analyzer: ${escapeHtml(m.analyzer_model)} · ${escapeHtml(m.privacy_disclosure)}</div>

      <div class="section">
        <div class="label">Agreed facts across independent families</div>
        <ul class="persp-bullets">
          ${(m.agreed ?? []).map((a) => `<li>${escapeHtml(a)}</li>`).join("")}
        </ul>
      </div>

      <div class="persp-grid" style="--cols:${gridCols};">
        ${(m.framings ?? [])
          .map(
            (fr) => `
          <div class="card inset persp-card">
            <div class="card-h"><b>${escapeHtml(fr.label)}</b></div>
            <div class="persp-pills">
              ${fr.sources
                .map(
                  (src) => `
                <button type="button" class="pill" data-news-open-url="${escapeHtml(src.url)}" data-news-open-title="${escapeHtml(src.title)}" title="${escapeHtml(src.why)}">
                  ${escapeHtml(src.domain)} · ${src.trust_effective.toFixed(1)} (${escapeHtml(src.category)})${src.conflict ? " · !" : ""}
                </button>`
                )
                .join("")}
            </div>
            <ul>
              ${fr.claims.map((cl) => `<li>${escapeHtml(cl)}</li>`).join("")}
            </ul>
          </div>`
          )
          .join("")}
      </div>

      <div class="section">
        <div class="label">Blind spots, missing perspectives &amp; system counterfactual</div>
        <ul class="persp-bullets muted">
          ${(m.blind_spots ?? []).map((b) => `<li>${escapeHtml(b)}</li>`).join("")}
          <li>Counterfactual: ${escapeHtml(m.system_counterfactual)}</li>
        </ul>
      </div>
    </div>
  `;
}

function renderTopicsLaneHtml(): string {
  const topics = state.newsTopics;
  return `
    <div class="card">
      <div class="card-h">
        <b>Tracked news topics &amp; watches</b>
        <span class="end muted">Queries stripped by PII Scrubber before searching</span>
      </div>
      <div class="form-row">
        <input id="news-topic-name-input" class="input" placeholder="e.g. EU AI Act, Berlin Transit, Semiconductors" />
        <input id="news-topic-kw-input" class="input" placeholder="Optional keywords comma-separated" />
        <button id="news-topic-add-btn" type="button" class="btn primary">${icon("plus", "ico-sm")}<span>Track topic</span></button>
      </div>
    </div>
    ${
      topics.length === 0
        ? `<div class="card"><span class="muted">No custom topics added yet. Track a topic above or click Save on a story.</span></div>`
        : `<div class="card news-card-list">
            ${topics
              .map(
                (t) => `
              <div class="source-row">
                <div class="source-row-top">
                  <span class="t">
                    <b>${escapeHtml(t.name)}</b>
                    ${t.suppressed ? ` <span class="flag">suppressed</span>` : ""}
                    ${t.badge_unread ? ` <span class="badge">watch</span>` : ""}
                  </span>
                  <button type="button" class="btn-text" data-news-ask-chat="${escapeHtml(`${t.name} latest news`)}">Query now</button>
                  <button type="button" class="btn-text" data-news-topic-del="${escapeHtml(t.topic_id)}">Remove</button>
                </div>
                <div class="source-row-meta">
                  Keywords: ${escapeHtml(t.keywords.join(", ") || t.name)} · Last checked: ${
                    t.last_checked_at > 0
                      ? escapeHtml(formatRelativeTime(String(Math.floor(t.last_checked_at))))
                      : "pending"
                  }
                </div>
              </div>`
              )
              .join("")}
          </div>`
    }
  `;
}

function renderSourcesLaneHtml(): string {
  const cats = state.newsCategories ?? [];
  const srcs = state.newsSources ?? [];

  return `
    <div class="card">
      <div class="card-h">
        <b>Source trust registry &amp; RSS feeds</b>
        <span class="muted">As of ${escapeHtml(state.newsSourcesAsOf || "2026-10-09")}</span>
        <span class="end muted">Personal trust counts for at most 30% (0.7 system + 0.3 yours)</span>
      </div>
      <div class="form-row">
        <div class="input-wrap">
          ${icon("search", "ico-sm")}
          <input id="news-src-search-input" class="input" value="${escapeHtml(state.newsSourcesFilterQuery)}" placeholder="Filter domain, category, rubric" />
        </div>
        <select id="news-src-cat-select" class="select">
          <option value="">All categories (${cats.length})</option>
          ${cats
            .map(
              (c) =>
                `<option value="${escapeHtml(c.id)}" ${state.newsSourcesFilterCategory === c.id ? "selected" : ""}>${escapeHtml(c.id)} (${c.score ?? "-"})</option>`
            )
            .join("")}
        </select>
        <select id="news-src-band-select" class="select">
          <option value="">All bands</option>
          <option value="high" ${state.newsSourcesFilterBand === "high" ? "selected" : ""}>9-10 high trust</option>
          <option value="good" ${state.newsSourcesFilterBand === "good" ? "selected" : ""}>7-8 good trust</option>
          <option value="low" ${state.newsSourcesFilterBand === "low" ? "selected" : ""}>5-6 low trust</option>
          <option value="sceptical" ${state.newsSourcesFilterBand === "sceptical" ? "selected" : ""}>0-4 sceptical</option>
          <option value="unscored" ${state.newsSourcesFilterBand === "unscored" ? "selected" : ""}>Unscored (5.0)</option>
        </select>
        <div class="news-src-checks">
          <label><input type="checkbox" id="news-src-rss-chk" ${state.newsSourcesRssOnly ? "checked" : ""} /> With RSS</label>
          <label><input type="checkbox" id="news-src-conf-chk" ${state.newsSourcesConflictedOnly ? "checked" : ""} /> Conflicts</label>
        </div>
      </div>
      <div class="form-row">
        <input id="news-add-feed-url" class="input" placeholder="Add RSS/Atom URL (e.g. https://rss.dw.com/xml/rss-en-all) or domain" />
        <input id="news-add-feed-title" class="input" placeholder="Optional label" />
        <button id="news-add-feed-btn" type="button" class="btn">${icon("plus", "ico-sm")}<span>Add feed / domain</span></button>
      </div>
    </div>

    <div class="table-wrap">
      <table class="table">
        <thead>
          <tr>
            <th>Domain &amp; feeds</th>
            <th>Category</th>
            <th class="num">System</th>
            <th>Personal trust (max 30%)</th>
            <th class="num">Effective</th>
          </tr>
        </thead>
        <tbody>
          ${
            srcs.length === 0
              ? `<tr><td colspan="5" class="muted">No sources matched the current filters.</td></tr>`
              : srcs
                  .slice(0, 120)
                  .map((d) => {
                    const personalVal = d.personal ?? d.system;
                    const confBadge = d.conflict
                      ? ` <span class="badge soft" title="Personal and system trust differ by at least 3.0">Conflict</span>`
                      : "";
                    const rubricTag = d.rubric ? ` · rubric: ${d.rubric}` : "";
                    const feedsHtml = d.feeds
                      .map(
                        (f) => `
                      <div class="news-src-rss-row">
                        <span class="truncate">RSS (${escapeHtml(f.language)}): ${escapeHtml(f.feed_url)}</span>
                        <button type="button" class="btn-text" data-news-toggle-feed="${escapeHtml(f.feed_id)}" data-enabled="${f.enabled ? "0" : "1"}">${f.enabled ? "Enabled" : "Paused"}</button>
                      </div>`
                      )
                      .join("");
                    return `
                      <tr>
                        <td>
                          <div><b>${escapeHtml(d.domain)}</b></div>
                          <div class="muted">Family: ${escapeHtml(d.family)}${escapeHtml(rubricTag)}</div>
                          ${feedsHtml}
                        </td>
                        <td>${escapeHtml(d.category || "unscored")}</td>
                        <td class="num" title="${escapeHtml(d.why || "System trust rubric")}">${d.system.toFixed(1)}</td>
                        <td>
                          <div class="slider-row">
                            <input class="slider" type="range" min="0" max="10" step="0.5" value="${personalVal}" data-news-src-slider="${escapeHtml(d.domain)}" />
                            <span class="slider-val" data-news-src-slider-val="${escapeHtml(d.domain)}">${personalVal.toFixed(1)}</span>
                            ${
                              d.personal !== null
                                ? `<button type="button" class="btn-text" data-news-src-reset="${escapeHtml(d.domain)}">Reset</button>`
                                : ""
                            }
                          </div>
                        </td>
                        <td class="num">
                          <span>${d.effective.toFixed(2)}/10 · ${escapeHtml(d.band)}</span>${confBadge}
                        </td>
                      </tr>`;
                  })
                  .join("")
          }
        </tbody>
      </table>
    </div>
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
    : art.body_text || art.snippet || "(Summary only; click Open live tab to read full article.)";

  return `
    <div class="card reader-card">
      <div class="card-h">
        <span class="muted">Reader · ${escapeHtml(art.domain)} · ${art.trust_effective.toFixed(1)}/10 · ${escapeHtml(art.category)}</span>
        <span class="end">
          ${
            art.translated_text
              ? `<button id="news-reader-toggle-orig-btn" type="button" class="btn">${showingTranslated ? `Show original (${escapeHtml(art.language)})` : "Show translation"}</button>`
              : `<button type="button" class="btn" data-news-translate="${escapeHtml(art.article_id)}">${icon("translate", "ico-sm")}<span>Translate</span></button>`
          }
          <button type="button" class="btn primary" data-news-open-url="${escapeHtml(art.url)}" data-news-open-title="${escapeHtml(art.title)}">${icon("external", "ico-sm")}<span>Open live tab</span></button>
          <button id="news-reader-close-btn" type="button" class="icon-btn" title="Close reader">${icon("x", "ico-sm")}</button>
        </span>
      </div>
      <div class="reader">
        <h1>${escapeHtml(art.title)}</h1>
        ${art.author ? `<div class="muted">By ${escapeHtml(art.author)} · ${escapeHtml(formatRelativeTime(String(Math.floor(art.published_at))))}</div>` : ""}
        ${art.image_url ? `<img class="attach-img" src="${escapeHtml(art.image_url)}" alt="" />` : ""}
        <div class="reader-body">${escapeHtml(displayText)}</div>
      </div>
    </div>
  `;
}

function getNewsLaneSubtitle(lane: NewsLane): string {
  switch (lane) {
    case "stories":
      return "Clustered by independent source families and corroborated confidence";
    case "foryou":
      return "Matched locally from Brain & Mail with 25% trusted explore";
    case "perspectives":
      return "Framings, shared facts, blind spots, and system counterfactual";
    case "topics":
      return "Custom topics & watches stripped by the PII Scrubber";
    case "sources":
      return "Hand-scored source trust registry (personal trust capped at 30%)";
  }
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
    <div class="news-view">
      <div class="view-h">
        <div>
          <h1>Satz News${state.newsLoading ? ` <span class="badge soft">Refreshing</span>` : ""}</h1>
          <p>${escapeHtml(getNewsLaneSubtitle(lane))}</p>
        </div>
        <div class="end news-head-actions">
          <button
            id="news-explore-toggle-btn"
            class="btn"
            type="button"
            aria-pressed="${state.newsExploreMode ? "true" : "false"}"
          >Explore: ${state.newsExploreMode ? "On" : "Off"}</button>
          <button id="news-refresh-feeds-btn" class="btn" type="button">
            ${icon("reload", "ico-sm")}
            <span>Refresh feeds</span>
          </button>
          <button id="news-refresh-search-btn" class="btn primary" type="button">
            ${icon("search", "ico-sm")}
            <span>Refresh + web</span>
          </button>
        </div>
      </div>
      ${
        state.newsStatusMessage
          ? renderStatusBannerHtml(state.newsStatusMessage)
          : ""
      }
      ${renderReaderOverlayHtml()}
      ${bodyHtml}
    </div>
  `;

  bindNewsViewEvents(container, actions);
}

function bindNewsViewEvents(container: HTMLElement, actions: NewsViewActions): void {
  container.querySelectorAll("img.story-thumb").forEach((imgEl) => {
    imgEl.addEventListener("error", () => {
      const card = imgEl.closest(".story");
      imgEl.remove();
      card?.classList.add("no-thumb");
    });
  });

  container.querySelector("#news-refresh-feeds-btn")?.addEventListener("click", () => {
    void (async () => {
      state.newsLoading = true;
      state.newsStatusMessage = "Polling conditional RSS/Atom feeds...";
      renderNewsLaneView(container, actions);
      const res = await sidecarRefreshNews(true, false);
      state.newsLoading = false;
      state.newsStatusMessage = res.ok
        ? `Feeds synced: ${res.fetched_feeds ?? 0} fetched, ${res.not_modified ?? 0} unchanged (304), ${res.articles_ingested ?? 0} articles, ${res.clusters ?? 0} clusters.`
        : `error: ${res.error ?? "feed refresh failed"}`;
      await refreshNewsState(state.newsActiveLane);
      renderNewsLaneView(container, actions);
      actions.onRefreshShell();
    })();
  });

  container.querySelector("#news-refresh-search-btn")?.addEventListener("click", () => {
    void (async () => {
      state.newsLoading = true;
      state.newsStatusMessage = "Polling feeds and PII-scrubbed web search for tracked topics...";
      renderNewsLaneView(container, actions);
      const res = await sidecarRefreshNews(true, true);
      state.newsLoading = false;
      state.newsStatusMessage = res.ok
        ? `Feeds + search synced: ${res.articles_ingested ?? 0} articles into ${res.clusters ?? 0} clusters.`
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

  container.querySelectorAll("[data-news-expand-fams]").forEach((btn) => {
    btn.addEventListener("click", () => {
      const cid = (btn as HTMLElement).getAttribute("data-news-expand-fams") ?? "";
      if (!cid) return;
      if (expandedStoryFamilyPills.has(cid)) {
        expandedStoryFamilyPills.delete(cid);
      } else {
        expandedStoryFamilyPills.add(cid);
      }
      renderNewsLaneView(container, actions);
    });
  });

  container.querySelectorAll("[data-news-story-menu]").forEach((btn) => {
    btn.addEventListener("click", (e) => {
      e.stopPropagation();
      const cid = (btn as HTMLElement).getAttribute("data-news-story-menu") ?? "";
      if (!cid) return;
      state.newsStoryMenuId = state.newsStoryMenuId === cid ? null : cid;
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
      state.newsStoryMenuId = null;
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
      state.newsStoryMenuId = null;
      const prompt = (btn as HTMLElement).getAttribute("data-news-ask-chat") ?? "";
      if (prompt) void actions.onAskInNewsChat(prompt);
    });
  });

  container.querySelectorAll("[data-news-open-perspectives]").forEach((btn) => {
    btn.addEventListener("click", () => {
      const cid = (btn as HTMLElement).getAttribute("data-news-open-perspectives") ?? "";
      if (!cid) return;
      state.newsStoryMenuId = null;
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
          ? "Saved story cluster to Satz Brain (News/Stories)."
          : `error: ${r.error ?? "unlock profile to save to Brain"}`;
        renderNewsLaneView(container, actions);
      });
    });
  });

  container.querySelectorAll("[data-news-hide-cluster]").forEach((btn) => {
    btn.addEventListener("click", () => {
      state.newsStoryMenuId = null;
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
      state.newsStoryMenuId = null;
      const name = (btn as HTMLElement).getAttribute("data-news-less-topic") ?? "";
      if (!name) return;
      void sidecarManageNewsTopic({ action: "suppress", name }).then(async () => {
        state.newsStatusMessage = `Reduced future stories on "${name}".`;
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
      state.newsStoryMenuId = null;
      const aid = (btn as HTMLElement).getAttribute("data-news-translate") ?? "";
      if (!aid) return;
      state.newsStatusMessage = "Translating article via news_capture role...";
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
          state.newsStatusMessage = "Translated article.";
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
    state.newsStatusMessage = "Re-analyzing source perspectives...";
    renderNewsLaneView(container, actions);
    void sidecarFetchNewsPerspectives(state.newsSelectedClusterId, true).then((mat) => {
      state.newsPerspectiveMatrix = mat;
      state.newsStatusMessage = mat?.ok ? "Perspective matrix updated." : "Perspective analysis failed.";
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
      state.newsStatusMessage = r.ok ? `Tracked topic "${name}" with active watch.` : `error: ${r.error}`;
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
      state.newsStatusMessage = r.ok ? `Added ${val}` : `error: ${r.error}`;
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
