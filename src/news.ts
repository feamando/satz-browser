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
import { drawWordmark, fontsReady } from "./design-system/brand";
import { icon } from "./design-system/icons";
import { t, tCount } from "./i18n";
import {
  escapeHtml,
  formatRelativeTime,
  getResolvedTheme,
  isContentLanguageAllowed,
  MOD_LABEL,
  state,
} from "./state";
import type { NewsLane, NewsStoryCluster } from "./types";
import {
  bindInlineProfileGateEvents,
  renderInlineProfileGateHtml,
} from "./profile_prompt";

export interface NewsViewActions {
  onOpenSiteUrl: (url: string, title: string, activate?: boolean) => void;
  onCompareUrls: (urls: Array<{ url: string; title: string }>) => Promise<void>;
  onAskInNewsChat: (prompt: string) => Promise<void>;
  onUnlockProfile?: (profileId: string, pin: string) => void | Promise<void>;
  onUnlockProfileKeychain?: (profileId: string) => void | Promise<void>;
  onCreateProfile?: (name: string, pin: string) => void | Promise<void>;
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
  const variant =
    low.startsWith("error") || msg.startsWith(t("common.error_prefix"))
      ? "banner danger"
      : "banner";
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
          <b>${escapeHtml(t("news.empty_title"))}</b>
        </div>
        <div class="muted">
          ${escapeHtml(t("news.empty_hint"))}
        </div>
      </div>
    `;
  }

  const primaryLang = state.contentTranslationConfig?.primary_language || "en";

  return `<div class="news-story-list">${stories
    .map((s) => {
      const showOrig = Boolean(state.newsStoryShowOriginal[s.cluster_id]);
      const hasClusterTr = Boolean(s.translated_headline || s.translated_summary_md);
      const dispHeadline = !showOrig && s.translated_headline ? s.translated_headline : s.headline;
      const dispSummaryMd =
        !showOrig && s.translated_summary_md ? s.translated_summary_md : s.summary_md;
      const bulletLines = dispSummaryMd
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
          const langTag =
            f.language && !isContentLanguageAllowed(f.language) ? ` (${f.language})` : "";
          return `<button type="button" class="pill" data-news-open-url="${escapeHtml(f.url)}" data-news-open-title="${escapeHtml(dispHeadline)}" title="${escapeHtml(t("news.trust_title", { trust: f.trust_effective.toFixed(1), category: f.category, langTag }))}">${escapeHtml(f.domain)} · ${f.trust_effective.toFixed(1)}${escapeHtml(confMark)}${escapeHtml(langTag)}</button>`;
        })
        .join("");
      const moreFamsTooltip = hiddenFams
        .map((f) => `${f.domain} (${f.trust_effective.toFixed(1)})`)
        .join(", ");
      const moreFamsPill =
        hiddenFams.length > 0
          ? `<button type="button" class="pill" data-news-expand-fams="${escapeHtml(s.cluster_id)}" title="${escapeHtml(moreFamsTooltip)}">+${hiddenFams.length}</button>`
          : isExpanded && fams.length > 2
            ? `<button type="button" class="pill" data-news-expand-fams="${escapeHtml(s.cluster_id)}" title="${escapeHtml(t("news.collapse_sources"))}">${escapeHtml(t("news.less"))}</button>`
            : "";

      const reasonsParts = s.brain_match_reasons ?? [];
      const reasonsHtml =
        reasonsParts.length > 0 || s.outside_usual
          ? `<div class="story-match">
              ${reasonsParts.length > 0 ? `<span>${escapeHtml(t("news.match_prefix", { reasons: reasonsParts.join(" · ") }))}</span>` : ""}
              ${s.outside_usual ? `<span class="flag">${escapeHtml(t("news.outside_usual"))}</span>` : ""}
            </div>`
          : "";

      const leadArt = s.articles?.[0];
      const artLang = leadArt?.language || s.language || "";
      const hasUnsupportedLang = Boolean(artLang && !isContentLanguageAllowed(artLang));
      const trSrc = s.translation_source_lang || artLang || "?";
      const trTgt = s.translation_target_lang || primaryLang;
      const compareUrls = fams
        .slice(0, 3)
        .map((f) => `${f.url}|||${dispHeadline}`)
        .join(";;;");

      const relAge = formatRelativeTime(String(Math.floor(s.updated_at)));
      const statusHtml = s.has_conflict
        ? `<span class="live">${escapeHtml(t("news.contested_age", { age: relAge }))}</span>`
        : `<span>${escapeHtml(t("news.fam_age", { count: s.independent_families, age: relAge }))}</span>`;
      const primaryTopic = s.topic_tags?.[0] ?? "";
      const secondActionKind: "perspectives" | "translate" | "ask" =
        fams.length >= 2
          ? "perspectives"
          : hasUnsupportedLang && leadArt && !hasClusterTr
            ? "translate"
            : "ask";

      const secondActionHtml =
        secondActionKind === "perspectives"
          ? `<button type="button" class="btn-text" data-news-open-perspectives="${escapeHtml(s.cluster_id)}">${escapeHtml(t("news.perspectives_n", { count: fams.length }))}</button>`
          : secondActionKind === "translate" && leadArt
            ? `<button type="button" class="btn-text" data-news-translate="${escapeHtml(leadArt.article_id)}">${escapeHtml(t("news.translate_arrow", { lang: artLang, target: primaryLang }))}</button>`
            : `<button type="button" class="btn-text" data-news-ask-chat="${escapeHtml(dispHeadline)}">${escapeHtml(t("news.ask_in_chat"))}</button>`;

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
              ${s.collapsed_mirrors > 0 ? `<span>${escapeHtml(t("news.plus_wire", { count: s.collapsed_mirrors }))}</span>` : ""}
              ${
                hasClusterTr && !showOrig
                  ? `<span class="badge soft">${escapeHtml(t("news.tr_pill", { src: trSrc, tgt: trTgt }))}</span>`
                  : ""
              }
              ${renderBandPillHtml(s.has_conflict ? "contested" : s.band, s.confidence10)}
            </div>
            <h3 class="story-title">${escapeHtml(dispHeadline)}</h3>
            ${bulletsHtml}
            ${reasonsHtml}
            <div class="story-foot">
              <div class="pills ${isExpanded ? "expanded" : ""}">
                ${famHtml}${moreFamsPill}
              </div>
              <div class="acts">
                ${
                  leadArt
                    ? `<button type="button" class="btn-text pri" data-news-open-reader="${escapeHtml(leadArt.article_id)}">${escapeHtml(t("news.open_reader"))}</button>`
                    : ""
                }
                ${
                  hasClusterTr
                    ? `<button type="button" class="btn-text" data-news-toggle-orig="${escapeHtml(s.cluster_id)}">${escapeHtml(
                        showOrig
                          ? t("news.tr_show_tr", { src: trSrc, tgt: trTgt })
                          : t("news.tr_show_orig", { src: trSrc })
                      )}</button>`
                    : ""
                }
                ${secondActionHtml}
                <button type="button" class="btn-text" data-news-save-brain="${escapeHtml(s.cluster_id)}">${escapeHtml(t("common.save"))}</button>
                <div class="story-more-anchor">
                  <button
                    type="button"
                    class="icon-btn"
                    data-news-story-menu="${escapeHtml(s.cluster_id)}"
                    title="${escapeHtml(t("news.more_actions"))}"
                    aria-expanded="${menuOpen ? "true" : "false"}"
                  >${icon("more", "ico-sm")}</button>
                  ${
                    menuOpen
                      ? `<div class="menu story-more-menu" role="menu">
                          ${
                            fams.length >= 2
                              ? `<button type="button" class="menu-item" data-news-compare-urls="${escapeHtml(compareUrls)}">${icon("compare", "ico-sm")}<span>${escapeHtml(t("news.compare_n", { count: Math.min(3, fams.length) }))}</span></button>`
                              : ""
                          }
                          ${
                            hasUnsupportedLang && leadArt && secondActionKind !== "translate"
                              ? `<button type="button" class="menu-item" data-news-translate="${escapeHtml(leadArt.article_id)}">${icon("translate", "ico-sm")}<span>${escapeHtml(t("news.translate_arrow", { lang: artLang, target: primaryLang }))}</span></button>`
                              : ""
                          }
                          ${
                            secondActionKind !== "ask"
                              ? `<button type="button" class="menu-item" data-news-ask-chat="${escapeHtml(s.headline)}">${icon("chat", "ico-sm")}<span>${escapeHtml(t("news.ask_in_chat"))}</span></button>`
                              : ""
                          }
                          ${
                            lane === "foryou" && s.topic_tags.length > 0
                              ? `<button type="button" class="menu-item" data-news-less-topic="${escapeHtml(s.topic_tags[0])}">${icon("x", "ico-sm")}<span>${escapeHtml(t("news.less_like_this"))}</span></button>`
                              : ""
                          }
                          <button type="button" class="menu-item danger" data-news-hide-cluster="${escapeHtml(s.cluster_id)}">${icon("trash", "ico-sm")}<span>${escapeHtml(t("news.hide"))}</span></button>
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
          ${escapeHtml(t("news.no_persp_stories"))}
        </div>
      </div>
    `;
  }

  const selectorHtml = `
    <div class="card">
      <div class="form-row">
        <label class="muted">${escapeHtml(t("news.story_cluster_n", { count: list.length }))}</label>
        <select id="news-persp-cluster-select" class="select">
          ${list
            .map(
              (s) =>
                `<option value="${escapeHtml(s.cluster_id)}" ${s.cluster_id === state.newsSelectedClusterId ? "selected" : ""}>${s.families.length} fam · ${s.confidence10.toFixed(1)} · ${escapeHtml(s.headline.slice(0, 72))}</option>`
            )
            .join("")}
        </select>
        <button id="news-persp-recompute-btn" type="button" class="btn">${escapeHtml(t("news.reanalyze_perspectives"))}</button>
      </div>
    </div>
  `;

  const m = state.newsPerspectiveMatrix;
  if (!m || !m.ok) {
    return `${selectorHtml}<div class="card"><span class="muted">${escapeHtml(t("news.select_cluster_persp"))}</span></div>`;
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
        <b>${escapeHtml(t("news.perspective_spread"))}</b>
        <span class="truncate muted">${escapeHtml(m.headline)}</span>
        <span class="end">
          ${comparePayload ? `<button type="button" class="btn" data-news-compare-urls="${escapeHtml(comparePayload)}">${icon("compare", "ico-sm")}<span>${escapeHtml(t("news.tile_compare", { mod: MOD_LABEL }))}</span></button>` : ""}
        </span>
      </div>
      <div class="muted">${escapeHtml(t("news.analyzer_line", { model: m.analyzer_model, privacy: m.privacy_disclosure }))}</div>

      <div class="section">
        <div class="label">${escapeHtml(t("news.agreed_facts"))}</div>
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
        <div class="label">${escapeHtml(t("news.blind_spots_heading"))}</div>
        <ul class="persp-bullets muted">
          ${(m.blind_spots ?? []).map((b) => `<li>${escapeHtml(b)}</li>`).join("")}
          <li>${escapeHtml(t("news.counterfactual", { text: m.system_counterfactual }))}</li>
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
        <b>${escapeHtml(t("news.tracked_topics_title"))}</b>
        <span class="end muted">${escapeHtml(t("news.topics_scrubber_note"))}</span>
      </div>
      <div class="form-row">
        <input id="news-topic-name-input" class="input" placeholder="${escapeHtml(t("news.topic_name_placeholder"))}" />
        <input id="news-topic-kw-input" class="input" placeholder="${escapeHtml(t("news.topic_kw_placeholder"))}" />
        <button id="news-topic-add-btn" type="button" class="btn primary">${icon("plus", "ico-sm")}<span>${escapeHtml(t("news.track_topic"))}</span></button>
      </div>
    </div>
    ${
      topics.length === 0
        ? `<div class="card"><span class="muted">${escapeHtml(t("news.no_topics"))}</span></div>`
        : `<div class="card news-card-list">
            ${topics
              .map(
                (tp) => `
              <div class="source-row">
                <div class="source-row-top">
                  <span class="t">
                    <b>${escapeHtml(tp.name)}</b>
                    ${tp.suppressed ? ` <span class="flag">${escapeHtml(t("news.suppressed"))}</span>` : ""}
                    ${tp.badge_unread ? ` <span class="badge">${escapeHtml(t("news.watch_badge"))}</span>` : ""}
                  </span>
                  <button type="button" class="btn-text" data-news-ask-chat="${escapeHtml(t("news.latest_news_query", { name: tp.name }))}">${escapeHtml(t("news.query_now"))}</button>
                  <button type="button" class="btn-text" data-news-topic-del="${escapeHtml(tp.topic_id)}">${escapeHtml(t("news.remove"))}</button>
                </div>
                <div class="source-row-meta">
                  ${escapeHtml(t("news.topic_meta", {
                    keywords: tp.keywords.join(", ") || tp.name,
                    checked: tp.last_checked_at > 0
                      ? formatRelativeTime(String(Math.floor(tp.last_checked_at)))
                      : t("common.pending"),
                  }))}
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
        <b>${escapeHtml(t("news.trust_registry_title"))}</b>
        <span class="badge soft">${srcs.length}</span>
        <span class="muted">${escapeHtml(t("news.as_of", { date: state.newsSourcesAsOf || "2026-10-09" }))}</span>
        <span class="end muted">${escapeHtml(t("news.trust_cap_note"))}</span>
      </div>
      <div class="form-row">
        <div class="input-wrap">
          ${icon("search", "ico-sm")}
          <input id="news-src-search-input" class="input" value="${escapeHtml(state.newsSourcesFilterQuery)}" placeholder="${escapeHtml(t("news.filter_sources_placeholder"))}" />
        </div>
        <select id="news-src-cat-select" class="select">
          <option value="">${escapeHtml(t("news.all_categories", { count: cats.length }))}</option>
          ${cats
            .map(
              (c) =>
                `<option value="${escapeHtml(c.id)}" ${state.newsSourcesFilterCategory === c.id ? "selected" : ""}>${escapeHtml(c.id)} (${c.score ?? "-"})</option>`
            )
            .join("")}
        </select>
        <select id="news-src-band-select" class="select">
          <option value="">${escapeHtml(t("news.all_bands"))}</option>
          <option value="high" ${state.newsSourcesFilterBand === "high" ? "selected" : ""}>${escapeHtml(t("news.band_high"))}</option>
          <option value="good" ${state.newsSourcesFilterBand === "good" ? "selected" : ""}>${escapeHtml(t("news.band_good"))}</option>
          <option value="low" ${state.newsSourcesFilterBand === "low" ? "selected" : ""}>${escapeHtml(t("news.band_low"))}</option>
          <option value="sceptical" ${state.newsSourcesFilterBand === "sceptical" ? "selected" : ""}>${escapeHtml(t("news.band_sceptical"))}</option>
          <option value="unscored" ${state.newsSourcesFilterBand === "unscored" ? "selected" : ""}>${escapeHtml(t("news.band_unscored"))}</option>
        </select>
        <div class="news-src-checks">
          <label><input type="checkbox" id="news-src-rss-chk" ${state.newsSourcesRssOnly ? "checked" : ""} /> ${escapeHtml(t("news.with_rss"))}</label>
          <label><input type="checkbox" id="news-src-conf-chk" ${state.newsSourcesConflictedOnly ? "checked" : ""} /> ${escapeHtml(t("news.conflicts"))}</label>
        </div>
      </div>
      <div class="form-row">
        <input id="news-add-feed-url" class="input" placeholder="${escapeHtml(t("news.add_feed_placeholder"))}" />
        <input id="news-add-feed-title" class="input" placeholder="${escapeHtml(t("news.optional_label"))}" />
        <button id="news-add-feed-btn" type="button" class="btn">${icon("plus", "ico-sm")}<span>${escapeHtml(t("news.add_feed_btn"))}</span></button>
      </div>
    </div>

    <div class="table-wrap">
      <table class="table">
        <thead>
          <tr>
            <th>${escapeHtml(t("news.col_domain_feeds"))}</th>
            <th>${escapeHtml(t("news.col_category"))}</th>
            <th class="num">${escapeHtml(t("news.col_system"))}</th>
            <th>${escapeHtml(t("news.col_personal_trust"))}</th>
            <th class="num">${escapeHtml(t("news.col_effective"))}</th>
          </tr>
        </thead>
        <tbody>
          ${
            srcs.length === 0
              ? `<tr><td colspan="5" class="muted">${escapeHtml(t("news.no_sources_matched"))}</td></tr>`
              : srcs
                  .map((d) => {
                    const personalVal = d.personal ?? d.system;
                    const confBadge = d.conflict
                      ? ` <span class="badge soft" title="${escapeHtml(t("news.conflict_title"))}">${escapeHtml(t("news.conflict_badge"))}</span>`
                      : "";
                    const rubricTag = d.rubric ? ` · rubric: ${d.rubric}` : "";
                    const feedsHtml = d.feeds
                      .map(
                        (f) => `
                      <div class="news-src-rss-row">
                        <span class="truncate">RSS (${escapeHtml(f.language)}): ${escapeHtml(f.feed_url)}</span>
                        <span class="badge ${f.enabled && f.last_fetched_at > 0 ? "good" : "soft"}">${escapeHtml(
                          !f.enabled
                            ? t("common.paused")
                            : f.last_fetched_at > 0
                              ? t("news.synced_age", { age: formatRelativeTime(String(Math.floor(f.last_fetched_at))) })
                              : t("common.pending")
                        )}</span>
                        <button type="button" class="btn-text" data-news-toggle-feed="${escapeHtml(f.feed_id)}" data-enabled="${f.enabled ? "0" : "1"}">${escapeHtml(f.enabled ? t("news.pause") : t("news.sync"))}</button>
                      </div>`
                      )
                      .join("");
                    return `
                      <tr>
                        <td>
                          <div><b>${escapeHtml(d.domain)}</b></div>
                          <div class="muted">${escapeHtml(t("news.family_line", { family: d.family, rubric: rubricTag }))}</div>
                          ${feedsHtml}
                        </td>
                        <td>${escapeHtml(d.category || "unscored")}</td>
                        <td class="num" title="${escapeHtml(d.why || t("news.system_rubric"))}">${d.system.toFixed(1)}</td>
                        <td>
                          <div class="slider-row">
                            <input class="slider" type="range" min="0" max="10" step="0.5" value="${personalVal}" data-news-src-slider="${escapeHtml(d.domain)}" />
                            <span class="slider-val" data-news-src-slider-val="${escapeHtml(d.domain)}">${personalVal.toFixed(1)}</span>
                            ${
                              d.personal !== null
                                ? `<button type="button" class="btn-text" data-news-src-reset="${escapeHtml(d.domain)}">${escapeHtml(t("common.reset"))}</button>`
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
  const artHasTr = Boolean(art.translated_text || art.title_tr || art.snippet_tr);
  const showingTranslated = artHasTr && !state.newsReaderShowOriginal;
  const displayTitle = showingTranslated && art.title_tr ? art.title_tr : art.title;
  const displayText = showingTranslated
    ? art.translated_text || art.snippet_tr || art.body_text || art.snippet || ""
    : art.body_text || art.snippet || t("news.reader_summary_only");

  return `
    <div class="card reader-card">
      <div class="card-h">
        <span class="muted">${escapeHtml(t("news.reader_meta", { domain: art.domain, trust: art.trust_effective.toFixed(1), category: art.category }))}</span>
        <span class="end">
          ${
            artHasTr
              ? `<button id="news-reader-toggle-orig-btn" type="button" class="btn">${escapeHtml(showingTranslated ? t("news.show_original", { lang: art.language || "?" }) : t("news.show_translation"))}</button>`
              : `<button type="button" class="btn" data-news-translate="${escapeHtml(art.article_id)}">${icon("translate", "ico-sm")}<span>${escapeHtml(t("news.translate"))}</span></button>`
          }
          <button type="button" class="btn primary" data-news-open-url="${escapeHtml(art.url)}" data-news-open-title="${escapeHtml(displayTitle)}">${icon("external", "ico-sm")}<span>${escapeHtml(t("news.open_live_tab"))}</span></button>
          <button id="news-reader-close-btn" type="button" class="icon-btn" title="${escapeHtml(t("news.close_reader"))}">${icon("x", "ico-sm")}</button>
        </span>
      </div>
      <div class="reader">
        <h1>${escapeHtml(displayTitle)}</h1>
        ${art.author ? `<div class="muted">${escapeHtml(t("news.by_author", { author: art.author, age: formatRelativeTime(String(Math.floor(art.published_at))) }))}</div>` : ""}
        ${art.image_url ? `<img class="attach-img" src="${escapeHtml(art.image_url)}" alt="" />` : ""}
        <div class="reader-body">${escapeHtml(displayText)}</div>
      </div>
    </div>
  `;
}

function getNewsLaneSubtitle(lane: NewsLane): string {
  switch (lane) {
    case "stories":
      return t("news.sub_stories");
    case "foryou":
      return t("news.sub_foryou");
    case "perspectives":
      return t("news.sub_perspectives");
    case "topics":
      return t("news.sub_topics");
    case "sources":
      return t("news.sub_sources");
  }
}

export function paintNewsWordmark(): void {
  const cv = document.getElementById("news-wordmark-canvas") as HTMLCanvasElement | null;
  if (!cv) return;
  const draw = () => {
    const live = document.getElementById("news-wordmark-canvas") as HTMLCanvasElement | null;
    if (live) {
      drawWordmark(live, { height: 24, theme: getResolvedTheme(), variant: "backdrop" });
    }
  };
  if (typeof document !== "undefined" && document.fonts?.check("700 16px Besley")) {
    draw();
  } else {
    void fontsReady().then(draw);
  }
}

export function renderNewsLaneView(
  container: HTMLElement,
  actions: NewsViewActions
): void {
  const prof = state.knowledge.profile;
  const isUnlocked = Boolean(prof?.unlocked && prof?.active_profile);
  const hasProfiles = (prof?.profiles.length ?? 0) > 0;
  if (!isUnlocked || !hasProfiles) {
    container.innerHTML = `
      <div class="news-view">
        ${renderInlineProfileGateHtml({
          iconName: "news",
          subtitle: t("news.locked_subtitle"),
        })}
      </div>
    `;
    bindInlineProfileGateEvents(container, {
      onUnlockProfile: actions.onUnlockProfile,
      onUnlockProfileKeychain: actions.onUnlockProfileKeychain,
      onCreateProfile: actions.onCreateProfile,
    });
    return;
  }

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

  const nStat = state.sidecar.news;
  const syncAge =
    nStat?.last_sync_at && nStat.last_sync_at > 0
      ? formatRelativeTime(String(Math.floor(nStat.last_sync_at)))
      : "";
  const syncMetaText = nStat
    ? `${tCount("news.hourly_sync", nStat.feeds_enabled)}${
        syncAge ? ` · ${t("news.synced_short", { age: syncAge })}` : ""
      }${nStat.brain_stories ? ` · ${t("news.in_brain_n", { count: nStat.brain_stories })}` : ""}`
    : "";

  container.innerHTML = `
    <div class="news-view">
      <div class="view-h">
        <div>
          <h1 class="news-brand-lockup" aria-label="Satz News">
            <canvas id="news-wordmark-canvas" aria-hidden="true"></canvas>
            <span class="display news-brand-sub">${escapeHtml(t("common.news"))}</span>
            ${state.newsLoading || nStat?.syncing ? `<span class="badge soft">${escapeHtml(t("common.syncing"))}</span>` : ""}
          </h1>
          <p>${escapeHtml(getNewsLaneSubtitle(lane))}${
            syncMetaText ? ` · ${escapeHtml(syncMetaText)}` : ""
          }</p>
        </div>
        <div class="end news-head-actions">
          <button
            id="news-explore-toggle-btn"
            class="btn"
            type="button"
            aria-pressed="${state.newsExploreMode ? "true" : "false"}"
          >${escapeHtml(t("news.explore_toggle", { state: state.newsExploreMode ? t("common.on") : t("common.off") }))}</button>
          <button id="news-refresh-feeds-btn" class="btn" type="button">
            ${icon("reload", "ico-sm")}
            <span>${escapeHtml(t("news.sync_feeds_btn"))}</span>
          </button>
          <button id="news-refresh-search-btn" class="btn primary" type="button">
            ${icon("search", "ico-sm")}
            <span>${escapeHtml(t("news.refresh_web_btn"))}</span>
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

  paintNewsWordmark();
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
      state.newsStatusMessage = t("news.syncing_feeds_status");
      renderNewsLaneView(container, actions);
      const res = await sidecarRefreshNews(true, false, true);
      state.newsLoading = false;
      state.newsStatusMessage = res.ok
        ? t("news.feeds_synced_status", {
            fetched: res.fetched_feeds ?? 0,
            unchanged: res.not_modified ?? 0,
            articles: res.articles_ingested ?? 0,
            clusters: res.clusters ?? 0,
            brain: res.brain_synced ?? 0,
          })
        : `${t("common.error_prefix")} ${res.error ?? t("news.feed_refresh_failed")}`;
      await refreshNewsState(state.newsActiveLane);
      renderNewsLaneView(container, actions);
      actions.onRefreshShell();
    })();
  });

  container.querySelector("#news-refresh-search-btn")?.addEventListener("click", () => {
    void (async () => {
      state.newsLoading = true;
      state.newsStatusMessage = t("news.polling_web_status");
      renderNewsLaneView(container, actions);
      const res = await sidecarRefreshNews(true, true, true);
      state.newsLoading = false;
      state.newsStatusMessage = res.ok
        ? t("news.feeds_web_synced_status", {
            articles: res.articles_ingested ?? 0,
            clusters: res.clusters ?? 0,
            brain: res.brain_synced ?? 0,
          })
        : `${t("common.error_prefix")} ${res.error ?? t("news.refresh_failed")}`;
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
    const readNewsTarget = () => {
      const el = btn as HTMLElement;
      return {
        url: el.getAttribute("data-news-open-url") ?? "",
        title: el.getAttribute("data-news-open-title") ?? "",
      };
    };
    btn.addEventListener("click", () => {
      const { url, title } = readNewsTarget();
      if (url) actions.onOpenSiteUrl(url, title, true);
    });
    btn.addEventListener("mousedown", (e) => {
      if ((e as MouseEvent).button === 1) e.preventDefault();
    });
    btn.addEventListener("auxclick", (e) => {
      const me = e as MouseEvent;
      if (me.button !== 1) return;
      me.preventDefault();
      me.stopPropagation();
      const { url, title } = readNewsTarget();
      if (url) actions.onOpenSiteUrl(url, title, false);
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
          ? t("news.saved_brain_status")
          : `${t("common.error_prefix")} ${r.error ?? t("news.unlock_to_save_brain")}`;
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
        state.newsStatusMessage = t("news.reduced_topic_status", { name });
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

  container.querySelectorAll("[data-news-toggle-orig]").forEach((btn) => {
    btn.addEventListener("click", () => {
      const cid = (btn as HTMLElement).getAttribute("data-news-toggle-orig") ?? "";
      if (!cid) return;
      state.newsStoryShowOriginal[cid] = !state.newsStoryShowOriginal[cid];
      renderNewsLaneView(container, actions);
    });
  });

  container.querySelectorAll("[data-news-translate]").forEach((btn) => {
    btn.addEventListener("click", () => {
      state.newsStoryMenuId = null;
      const aid = (btn as HTMLElement).getAttribute("data-news-translate") ?? "";
      if (!aid) return;
      state.newsStatusMessage = t("news.translating_article");
      renderNewsLaneView(container, actions);
      const targetLang = state.contentTranslationConfig?.primary_language || "";
      void sidecarTranslateNewsArticle(aid, targetLang).then(async (r) => {
        if (r.ok && (r.translated_text || r.title_tr || r.snippet_tr)) {
          for (const s of [...state.newsStories, ...state.newsForYouStories, ...state.newsPerspectivesStories]) {
            for (const a of s.articles) {
              if (a.article_id === aid) {
                if (r.translated_text) a.translated_text = r.translated_text;
                if (r.title_tr) a.title_tr = r.title_tr;
                if (r.snippet_tr) a.snippet_tr = r.snippet_tr;
                if (!s.translated_headline && r.title_tr) s.translated_headline = r.title_tr;
                if (!s.translated_summary_md && r.snippet_tr) s.translated_summary_md = r.snippet_tr;
              }
            }
          }
          state.newsReaderArticleId = aid;
          state.newsReaderShowOriginal = false;
          state.newsStatusMessage = t("news.translated_article");
        } else {
          state.newsStatusMessage = `${t("common.error_prefix")} ${r.error ?? t("news.translation_failed")}`;
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
    state.newsStatusMessage = t("news.reanalyzing_persp");
    renderNewsLaneView(container, actions);
    void sidecarFetchNewsPerspectives(state.newsSelectedClusterId, true).then((mat) => {
      state.newsPerspectiveMatrix = mat;
      state.newsStatusMessage = mat?.ok ? t("news.persp_updated") : t("news.persp_failed");
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
      state.newsStatusMessage = r.ok ? t("news.tracked_topic_added", { name }) : `${t("common.error_prefix")} ${r.error}`;
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
      state.newsStatusMessage = r.ok ? t("news.added_item", { item: val }) : `${t("common.error_prefix")} ${r.error}`;
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
