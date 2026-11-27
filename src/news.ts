import {
  apiEnsureNewsPerspectivesConversation,
  apiGetConversation,
  sidecarFetchFollowedStories,
  sidecarFetchNewsSources,
  sidecarFetchNewsStories,
  sidecarFetchNewsTopics,
  sidecarHideNewsCluster,
  sidecarManageNewsFeed,
  sidecarManageNewsTopic,
  sidecarMarkFollowedStoryRead,
  sidecarPinFollowedStory,
  sidecarRefreshFollowedStories,
  sidecarRefreshNews,
  sidecarSaveNewsClusterToBrain,
  sidecarSetDomainTrust,
  sidecarTranslateNewsArticle,
  sidecarUnpinFollowedStory,
} from "./api";
import { bindChatThreadEvents, formatCitationsInText, renderMessageBlock, type ChatActions } from "./chat";
import { drawWordmark, fontsReady } from "./design-system/brand";
import { icon } from "./design-system/icons";
import { t, tCount } from "./i18n";
import {
  escapeHtml,
  formatRelativeTime,
  getResolvedTheme,
  isContentLanguageAllowed,
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
  onImportProfileFile?: (bundleB64: string, pin: string, localPin?: string) => void | Promise<void>;
  onOpenNewsSettings?: (targetTab?: string) => void;
  onOpenNewsHome?: () => void;
  onSendPerspectivesTopic?: (
    topic: string,
    clusterId?: string,
    followedStoryId?: string
  ) => Promise<void>;
  perspChatActions?: ChatActions;
  onRefreshShell: () => void;
}

let newsAutoWarmedThisSession = false;
const expandedStoryFamilyPills = new Set<string>();

export async function refreshNewsState(
  lane?: NewsLane | "topics" | "sources" | "settings",
  onProgress?: (detail: string, statusLine?: string) => void
): Promise<void> {
  const target = lane ?? state.newsActiveLane ?? "stories";
  onProgress?.(t("profile.detail_news_fetch"), t("profile.status_loading_news"));
  if (target === "stories") {
    const fetchLane = async () => {
      const [storiesRes, topicsRes, followedRes] = await Promise.all([
        sidecarFetchNewsStories("top", "", false, 30),
        sidecarFetchNewsTopics(),
        sidecarFetchFollowedStories(true),
      ]);
      state.newsStories = storiesRes.stories;
      state.newsTopics = topicsRes.topics;
      if (followedRes.ok) {
        state.newsFollowedStories = followedRes.stories;
      }
      return storiesRes.stories;
    };

    const initial = await fetchLane();
    if (initial.length === 0 && !newsAutoWarmedThisSession) {
      newsAutoWarmedThisSession = true;
      onProgress?.(t("profile.detail_news_update"), t("profile.status_updating_news"));
      await sidecarRefreshNews(false, false);
      await fetchLane();
    }
  } else if (target === "tracked") {
    const res = await sidecarFetchFollowedStories(true);
    if (res.ok) {
      state.newsFollowedStories = res.stories;
    }
  } else if (target === "perspectives") {
    const [storiesRes, topicsRes, followedRes] = await Promise.all([
      sidecarFetchNewsStories("top", "", false, 15),
      sidecarFetchNewsTopics(),
      sidecarFetchFollowedStories(false),
    ]);
    state.newsPerspectivesStories = storiesRes.stories;
    if (state.newsStories.length === 0) {
      state.newsStories = storiesRes.stories;
    }
    state.newsTopics = topicsRes.topics;
    if (followedRes.ok) {
      state.newsFollowedStories = followedRes.stories;
    }
    try {
      const pConv = await apiEnsureNewsPerspectivesConversation();
      state.newsPerspectivesDetail = await apiGetConversation(pConv.id);
    } catch {
      // Sidecar/Tauri DB might still be warming up
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
  } else if (target === "settings") {
    const [topicsRes, sourcesRes] = await Promise.all([
      sidecarFetchNewsTopics(),
      sidecarFetchNewsSources({
        q: state.newsSourcesFilterQuery,
        category: state.newsSourcesFilterCategory,
        band: state.newsSourcesFilterBand,
        conflicted: state.newsSourcesConflictedOnly,
        withRss: state.newsSourcesRssOnly,
      }),
    ]);
    state.newsTopics = topicsRes.topics;
    state.newsSources = sourcesRes.sources;
    state.newsCategories = sourcesRes.categories;
    state.newsSourcesAsOf = sourcesRes.as_of;
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
  lane: "stories"
): string {
  const pinnedByCluster = new Map<string, string>();
  for (const fs of state.newsFollowedStories) {
    if (fs.seed_cluster_id) {
      pinnedByCluster.set(fs.seed_cluster_id, fs.story_id);
    }
  }
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
      const pinnedStoryId = pinnedByCluster.get(s.cluster_id) ?? "";

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
                <button
                  type="button"
                  class="btn-text ${pinnedStoryId ? "pri" : ""}"
                  data-news-pin-story="${escapeHtml(s.cluster_id)}"
                  data-news-pinned-id="${escapeHtml(pinnedStoryId)}"
                >${icon("pin", "ico-sm")}<span>${escapeHtml(
                    pinnedStoryId ? t("news.pinned_story") : t("news.pin_story")
                  )}</span></button>
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
                            false
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

function renderTrackedStoriesLaneHtml(): string {
  const stories = state.newsFollowedStories;
  if (stories.length === 0) {
    return `
      <div class="card inset">
        <div class="card-h">
          <b>${escapeHtml(t("news.story_empty_title"))}</b>
          <button type="button" class="btn primary sm" data-news-goto-top="1">${escapeHtml(t("news.story_goto_top"))}</button>
        </div>
        <div class="settings-card-note">${escapeHtml(t("news.story_empty_sub"))}</div>
      </div>
    `;
  }

  return `
    <div class="stories">
      ${stories
        .map((st) => {
          const relAge = formatRelativeTime(String(Math.floor(st.updated_at || st.created_at)));
          const overviewHtml = formatCitationsInText(
            st.summary_overview || st.title,
            st.updates.map((u) => u.url)
          );
          const updatesHtml = st.updates
            .slice(0, 12)
            .map((u, idx) => {
              const uAge = formatRelativeTime(String(Math.floor(u.published_at)));
              const uTitle = u.title_tr || u.title;
              const uSnip = u.snippet_tr || u.snippet;
              return `
                <div class="tracked-update-row ${u.is_new ? "is-new" : ""}">
                  <div class="tracked-update-meta">
                    <span class="badge soft">${idx + 1}</span>
                    ${u.is_new ? `<span class="badge accent">${escapeHtml(t("news.story_new_badge"))}</span>` : ""}
                    <b>${escapeHtml(u.domain)}</b>
                    <span>${u.trust_effective.toFixed(1)}/10</span>
                    <span>${escapeHtml(uAge)}</span>
                  </div>
                  <div class="tracked-update-title">${escapeHtml(uTitle)}</div>
                  ${uSnip ? `<div class="tracked-update-snip">${escapeHtml(uSnip.slice(0, 220))}</div>` : ""}
                  <div class="tracked-update-acts">
                    <button type="button" class="btn-text pri" data-news-open-reader="${escapeHtml(u.article_id)}">${escapeHtml(t("news.open_reader"))}</button>
                    <button type="button" class="btn-text" data-news-open-url="${escapeHtml(u.url)}" data-news-open-title="${escapeHtml(uTitle)}">${escapeHtml(t("news.open_live_tab"))}</button>
                  </div>
                </div>
              `;
            })
            .join("");

          return `
            <article class="story tracked-story-card" data-tracked-story-id="${escapeHtml(st.story_id)}">
              <div class="tracked-story-head">
                ${
                  st.lead_image
                    ? `<img class="story-thumb" src="${escapeHtml(st.lead_image)}" alt="" loading="lazy" referrerpolicy="no-referrer" />`
                    : ""
                }
                <div class="story-c">
                  <div class="story-meta">
                    ${st.unread_updates > 0 ? `<span class="badge accent">${escapeHtml(tCount("news.story_unread_n", st.unread_updates))}</span>` : ""}
                    <span>${escapeHtml(tCount("news.story_updates_n", st.update_count))}</span>
                    <span>${escapeHtml(t("news.fam_age", { count: st.independent_families, age: relAge }))}</span>
                    ${renderBandPillHtml(st.band, st.confidence10)}
                  </div>
                  <h3 class="story-title">${escapeHtml(st.title)}</h3>
                </div>
              </div>

              <div class="tracked-overview">
                <div class="label">${escapeHtml(t("news.story_overview_head"))}</div>
                <div class="tracked-overview-body">${overviewHtml}</div>
              </div>

              <div class="story-foot">
                <div class="acts">
                  <button type="button" class="btn primary sm" data-tracked-open-persp="${escapeHtml(st.story_id)}" data-tracked-title="${escapeHtml(st.title)}">${escapeHtml(t("news.story_perspectives_btn"))}</button>
                  <button type="button" class="btn sm" data-tracked-refresh="${escapeHtml(st.story_id)}">${icon("reload", "ico-sm")}<span>${escapeHtml(t("news.story_refresh_overview"))}</span></button>
                  ${
                    st.unread_updates > 0
                      ? `<button type="button" class="btn sm" data-tracked-read="${escapeHtml(st.story_id)}">${escapeHtml(t("news.story_mark_read"))}</button>`
                      : ""
                  }
                  <button type="button" class="btn-text" data-tracked-unpin="${escapeHtml(st.story_id)}">${icon("pin", "ico-sm")}<span>${escapeHtml(t("news.unpin_story"))}</span></button>
                </div>
              </div>

              <div class="tracked-timeline">
                <div class="label">${escapeHtml(t("news.story_timeline_head"))}</div>
                ${updatesHtml}
              </div>
            </article>
          `;
        })
        .join("")}
    </div>
  `;
}

function renderPerspectivesLaneHtml(): string {
  const topics = state.newsTopics;
  const followed = state.newsFollowedStories;
  const recentStories =
    state.newsPerspectivesStories.length > 0
      ? state.newsPerspectivesStories
      : state.newsStories;
  const detail = state.newsPerspectivesDetail;
  const stream = state.newsPerspectivesStream;
  const isStreaming = Boolean(stream);
  const messages = detail?.messages ?? [];

  const topicChipsHtml = topics
    .slice(0, 10)
    .map(
      (tp) =>
        `<button type="button" class="pill" ${isStreaming ? "disabled" : ""} data-persp-pick-topic="${escapeHtml(tp.name)}">${escapeHtml(tp.name)}</button>`
    )
    .join("");

  const followedChipsHtml = followed
    .slice(0, 8)
    .map(
      (fs) =>
        `<button type="button" class="pill ${fs.unread_updates > 0 ? "accent" : ""}" ${isStreaming ? "disabled" : ""} data-persp-pick-followed="${escapeHtml(fs.story_id)}" data-persp-pick-title="${escapeHtml(fs.title)}">${escapeHtml(fs.title.length > 50 ? `${fs.title.slice(0, 49)}...` : fs.title)}${fs.update_count > 1 ? ` · ${fs.update_count}` : ""}</button>`
    )
    .join("");

  const storyChipsHtml = recentStories
    .slice(0, 5)
    .map((s) => {
      const headline = s.translated_headline || s.headline;
      return `<button type="button" class="pill" ${isStreaming ? "disabled" : ""} data-persp-pick-cluster="${escapeHtml(s.cluster_id)}" data-persp-pick-title="${escapeHtml(headline)}">${escapeHtml(headline.length > 52 ? `${headline.slice(0, 51)}...` : headline)}</button>`;
    })
    .join("");

  const messagesHtml = messages
    .map((m) =>
      renderMessageBlock(
        m.id,
        m.role,
        m.content,
        m.model,
        m.source_ids_json,
        m.cited_sources ?? state.messageCitedSources[m.id],
        undefined,
        m.citation_check,
        m.citations_ok,
        m.citations_flagged,
        m.findings ?? state.messageFindings[m.id],
        m.brain_sources ?? state.messageBrainSources[m.id],
        undefined,
        m.answer_meta ?? state.messageAnswerMeta[m.id],
        undefined,
        undefined,
        undefined,
        m.ui_cards ?? state.messageUiCards[m.id]
      )
    )
    .join("");

  const streamingHtml = stream
    ? `
      <div id="perspectives-stream-row" class="persp-stream-wrap">
        ${stream.status ? `<div class="msg-status muted">${escapeHtml(stream.status)}</div>` : ""}
        ${
          stream.text
            ? renderMessageBlock(
                "__persp_stream__",
                "assistant",
                stream.text,
                state.selectedModel,
                null
              )
            : `<div class="msg-bot"><div class="msg-head"><b>${escapeHtml(t("chat.assistant"))}</b> · <span class="badge soft">${escapeHtml(stream.status || t("common.syncing"))}</span></div></div>`
        }
      </div>
    `
    : "";

  const emptyStateHtml =
    messages.length === 0 && !stream
      ? `
      <div class="card inset persp-empty">
        <div class="card-h">
          <b>${escapeHtml(t("news.persp_empty_title"))}</b>
        </div>
        <div class="settings-card-note">${escapeHtml(t("news.persp_empty_sub"))}</div>
        <div class="ns-chip-list">
          ${
            topics.length === 0
              ? `
            <button type="button" class="pill" data-persp-pick-topic="European energy policy and grid tariffs">European energy policy</button>
            <button type="button" class="pill" data-persp-pick-topic="Global AI regulation and chip export rules">AI regulation &amp; chips</button>
            <button type="button" class="pill" data-persp-pick-topic="ECB and Federal Reserve interest rates">Central bank rates</button>
          `
              : ""
          }
        </div>
      </div>
    `
      : "";

  return `
    <div class="persp-shell">
      <div class="persp-topics-bar">
        <div class="persp-chips-row">
          <span class="persp-chips-label">${escapeHtml(t("news.persp_tracked_topics"))}:</span>
          ${topicChipsHtml || `<span class="muted">${escapeHtml(t("news.no_topics_yet"))}</span>`}
          <button type="button" class="btn-text end" data-news-open-settings="chat">${icon("settings", "ico-sm")}<span>${escapeHtml(t("news.persp_manage_topics"))}</span></button>
        </div>
        ${
          followedChipsHtml
            ? `<div class="persp-chips-row">
                <span class="persp-chips-label">${escapeHtml(t("news.persp_followed_stories"))}:</span>
                ${followedChipsHtml}
              </div>`
            : ""
        }
        ${
          storyChipsHtml
            ? `<div class="persp-chips-row">
                <span class="persp-chips-label">${escapeHtml(t("news.persp_recent_stories"))}:</span>
                ${storyChipsHtml}
              </div>`
            : ""
        }
      </div>

      <div class="persp-thread-scroll" id="persp-messages-list">
        <div class="thread">
          ${emptyStateHtml}
          ${messagesHtml}
          ${streamingHtml}
        </div>
      </div>

      <div class="persp-composer">
        <div class="persp-input-row">
          <input
            id="persp-topic-input"
            type="text"
            placeholder="${escapeHtml(t("news.persp_topic_ph"))}"
            ${isStreaming ? "disabled" : ""}
          />
          <button id="persp-send-btn" type="button" class="btn primary" ${isStreaming ? "disabled" : ""}>
            <span>${escapeHtml(t("news.persp_compare_btn"))}</span>
          </button>
        </div>
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
    ...state.newsPerspectivesStories.flatMap((s) => s.articles ?? []),
    ...state.newsFollowedStories.flatMap((fs) => fs.updates ?? []),
  ];
  const art = allArts.find((a) => a.article_id === aid);
  if (!art) return "";
  const artHasTr = Boolean(art.translated_text || art.title_tr || art.snippet_tr);
  const showingTranslated = artHasTr && !state.newsReaderShowOriginal;
  const displayTitle = showingTranslated && art.title_tr ? art.title_tr : art.title;
  const rawBody = "body_text" in art && art.body_text ? art.body_text : art.snippet;
  const displayText = showingTranslated
    ? art.translated_text || art.snippet_tr || rawBody || ""
    : rawBody || t("news.reader_summary_only");
  const artCategory = "category" in art && art.category ? art.category : art.domain;
  const artAuthor = "author" in art && art.author ? art.author : "";

  return `
    <div class="card reader-card">
      <div class="card-h">
        <span class="muted">${escapeHtml(t("news.reader_meta", { domain: art.domain, trust: art.trust_effective.toFixed(1), category: artCategory }))}</span>
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
        ${artAuthor ? `<div class="muted">${escapeHtml(t("news.by_author", { author: artAuthor, age: formatRelativeTime(String(Math.floor(art.published_at))) }))}</div>` : ""}
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
    case "tracked":
      return t("news.sub_tracked");
    case "perspectives":
      return t("news.sub_perspectives");
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
      onImportProfileFile: actions.onImportProfileFile,
    });
    return;
  }

  const lane: NewsLane =
    state.newsActiveLane === "perspectives"
      ? "perspectives"
      : state.newsActiveLane === "tracked"
        ? "tracked"
        : "stories";
  let bodyHtml = "";
  if (lane === "stories") {
    bodyHtml = renderStoryCardsHtml(state.newsStories, "stories");
  } else if (lane === "tracked") {
    bodyHtml = renderTrackedStoriesLaneHtml();
  } else {
    bodyHtml = renderPerspectivesLaneHtml();
  }

  const onboardBannerHtml =
    lane === "stories" && state.newsTopics.length === 0
      ? `
      <div class="card inset news-onboard-banner">
        <div class="card-h">
          <b>${escapeHtml(t("news.empty_onboard_banner_title"))}</b>
          <button type="button" class="btn primary sm" data-news-open-settings="chat">${escapeHtml(t("news.open_settings_btn"))}</button>
        </div>
        <div class="settings-card-note">${escapeHtml(t("news.empty_onboard_banner_sub"))}</div>
      </div>
    `
      : "";

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
          <button class="btn" type="button" data-news-open-settings="chat">
            ${icon("settings", "ico-sm")}
            <span>${escapeHtml(t("top.news_settings"))}</span>
          </button>
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
      ${onboardBannerHtml}
      ${renderReaderOverlayHtml()}
      ${bodyHtml}
    </div>
  `;

  paintNewsWordmark();
  bindNewsViewEvents(container, actions, () => renderNewsLaneView(container, actions));
}

export function renderNewsSettingsManualView(
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
      onImportProfileFile: actions.onImportProfileFile,
    });
    return;
  }

  const acc = state.newsSettingsManualAcc;
  const enabledFeeds = state.newsSources.filter((s) => s.feeds?.some((f) => f.enabled)).length;
  const totalScored = state.newsSources.length;
  const nStat = state.sidecar.news;

  container.innerHTML = `
    <div class="news-view">
      <div class="view-h">
        <div>
          <h1>${escapeHtml(t("news.manual_title"))}</h1>
          <p>${escapeHtml(t("news.manual_sub"))}</p>
        </div>
        <div class="end news-head-actions">
          <button id="ns-manual-open-chat-btn" class="btn" type="button">
            ${icon("chat", "ico-sm")}
            <span>${escapeHtml(t("news.manual_chat_btn"))}</span>
          </button>
          <button id="news-refresh-feeds-btn" class="btn" type="button">
            ${icon("reload", "ico-sm")}
            <span>${escapeHtml(t("news.sync_feeds_btn"))}</span>
          </button>
          <button id="news-refresh-search-btn" class="btn primary" type="button">
            ${icon("search", "ico-sm")}
            <span>${escapeHtml(t("news.refresh_web_btn"))}</span>
          </button>
          ${state.newsLoading || nStat?.syncing ? `<span class="badge soft">${escapeHtml(t("common.syncing"))}</span>` : ""}
          <button id="ns-manual-back-news-btn" class="btn" type="button">
            ${icon("news", "ico-sm")}
            <span>${escapeHtml(t("top.back_to_news"))}</span>
          </button>
        </div>
      </div>

      ${
        state.newsStatusMessage
          ? renderStatusBannerHtml(state.newsStatusMessage)
          : ""
      }

      <section class="acc news-manual-acc ${acc.topics ? "" : "closed"}" data-ns-acc="topics">
        <button class="acc-h" type="button" data-ns-acc-toggle="topics" aria-expanded="${acc.topics ? "true" : "false"}">
          <span class="rail-acc-chevron">${icon("chev", "ico-sm")}</span>
          <span class="label">${escapeHtml(t("news.manual_topics_head"))}</span>
          <span class="acc-count">${escapeHtml(tCount("news.manual_topics_count", state.newsTopics.length))}</span>
        </button>
        <div class="acc-body">
          ${renderTopicsLaneHtml()}
        </div>
      </section>

      <section class="acc news-manual-acc ${acc.sources ? "" : "closed"}" data-ns-acc="sources">
        <button class="acc-h" type="button" data-ns-acc-toggle="sources" aria-expanded="${acc.sources ? "true" : "false"}">
          <span class="rail-acc-chevron">${icon("chev", "ico-sm")}</span>
          <span class="label">${escapeHtml(t("news.manual_sources_head"))}</span>
          <span class="acc-count">${escapeHtml(t("news.manual_sources_count", { enabled: enabledFeeds, total: totalScored }))}</span>
        </button>
        <div class="acc-body">
          ${renderSourcesLaneHtml()}
        </div>
      </section>
    </div>
  `;

  container.querySelectorAll("[data-ns-acc-toggle]").forEach((btn) => {
    btn.addEventListener("click", () => {
      const k = (btn as HTMLElement).getAttribute("data-ns-acc-toggle") as "topics" | "sources" | null;
      if (!k) return;
      state.newsSettingsManualAcc[k] = !state.newsSettingsManualAcc[k];
      renderNewsSettingsManualView(container, actions);
    });
  });

  container.querySelector("#ns-manual-open-chat-btn")?.addEventListener("click", () => {
    actions.onOpenNewsSettings?.("chat");
  });

  container.querySelector("#ns-manual-back-news-btn")?.addEventListener("click", () => {
    actions.onOpenNewsHome?.();
  });

  bindNewsViewEvents(container, actions, () => renderNewsSettingsManualView(container, actions));
}

function bindNewsViewEvents(
  container: HTMLElement,
  actions: NewsViewActions,
  onReRender?: () => void
): void {
  const reRender = onReRender ?? (() => renderNewsLaneView(container, actions));
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
      reRender();
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
      await refreshNewsState(onReRender ? "settings" : state.newsActiveLane);
      reRender();
      actions.onRefreshShell();
    })();
  });

  container.querySelector("#news-refresh-search-btn")?.addEventListener("click", () => {
    void (async () => {
      state.newsLoading = true;
      state.newsStatusMessage = t("news.polling_web_status");
      reRender();
      const res = await sidecarRefreshNews(true, true, true);
      state.newsLoading = false;
      state.newsStatusMessage = res.ok
        ? t("news.feeds_web_synced_status", {
            articles: res.articles_ingested ?? 0,
            clusters: res.clusters ?? 0,
            brain: res.brain_synced ?? 0,
          })
        : `${t("common.error_prefix")} ${res.error ?? t("news.refresh_failed")}`;
      await refreshNewsState(onReRender ? "settings" : state.newsActiveLane);
      reRender();
      actions.onRefreshShell();
    })();
  });

  container.querySelectorAll("[data-news-open-settings]").forEach((btn) => {
    btn.addEventListener("click", () => {
      const tab = (btn as HTMLElement).getAttribute("data-news-open-settings") ?? "chat";
      actions.onOpenNewsSettings?.(tab);
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
      reRender();
    });
  });

  container.querySelectorAll("[data-news-story-menu]").forEach((btn) => {
    btn.addEventListener("click", (e) => {
      e.stopPropagation();
      const cid = (btn as HTMLElement).getAttribute("data-news-story-menu") ?? "";
      if (!cid) return;
      state.newsStoryMenuId = state.newsStoryMenuId === cid ? null : cid;
      reRender();
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
      const cl = [...state.newsStories, ...state.newsPerspectivesStories].find(
        (s) => s.cluster_id === cid
      );
      const topicPrompt = cl?.translated_headline || cl?.headline || "";
      actions.onRefreshShell();
      if (topicPrompt && actions.onSendPerspectivesTopic) {
        void actions.onSendPerspectivesTopic(topicPrompt, cid);
      } else {
        void refreshNewsState("perspectives").then(() => {
          actions.onRefreshShell();
        });
      }
    });
  });

  container.querySelectorAll("[data-news-pin-story]").forEach((btn) => {
    btn.addEventListener("click", () => {
      const el = btn as HTMLElement;
      const cid = el.getAttribute("data-news-pin-story") ?? "";
      const pinnedId = el.getAttribute("data-news-pinned-id") ?? "";
      if (!cid) return;
      void (async () => {
        if (pinnedId) {
          const r = await sidecarUnpinFollowedStory(pinnedId);
          state.newsStatusMessage = r.ok
            ? t("news.unpinned_story_toast")
            : `${t("common.error_prefix")} ${r.error ?? ""}`;
        } else {
          const r = await sidecarPinFollowedStory({ cluster_id: cid });
          state.newsStatusMessage = r.ok
            ? t("news.pinned_story_toast")
            : `${t("common.error_prefix")} ${r.error ?? ""}`;
        }
        await refreshNewsState("stories");
        reRender();
        actions.onRefreshShell();
      })();
    });
  });

  container.querySelectorAll("[data-news-goto-top]").forEach((btn) => {
    btn.addEventListener("click", () => {
      state.newsActiveLane = "stories";
      state.activeTabId = "news-lane:stories";
      void refreshNewsState("stories").then(() => {
        actions.onRefreshShell();
      });
    });
  });

  container.querySelectorAll("[data-tracked-unpin]").forEach((btn) => {
    btn.addEventListener("click", () => {
      const sid = (btn as HTMLElement).getAttribute("data-tracked-unpin") ?? "";
      if (!sid) return;
      void sidecarUnpinFollowedStory(sid).then(async () => {
        state.newsStatusMessage = t("news.unpinned_story_toast");
        await refreshNewsState("tracked");
        reRender();
        actions.onRefreshShell();
      });
    });
  });

  container.querySelectorAll("[data-tracked-read]").forEach((btn) => {
    btn.addEventListener("click", () => {
      const sid = (btn as HTMLElement).getAttribute("data-tracked-read") ?? "";
      if (!sid) return;
      void sidecarMarkFollowedStoryRead(sid).then(async () => {
        await refreshNewsState("tracked");
        reRender();
        actions.onRefreshShell();
      });
    });
  });

  container.querySelectorAll("[data-tracked-refresh]").forEach((btn) => {
    btn.addEventListener("click", () => {
      const sid = (btn as HTMLElement).getAttribute("data-tracked-refresh") ?? "";
      if (!sid) return;
      state.newsLoading = true;
      reRender();
      void sidecarRefreshFollowedStories(sid).then((r) => {
        state.newsLoading = false;
        if (r.ok) {
          state.newsFollowedStories = r.stories;
        }
        reRender();
        actions.onRefreshShell();
      });
    });
  });

  container.querySelectorAll("[data-tracked-open-persp]").forEach((btn) => {
    btn.addEventListener("click", () => {
      const el = btn as HTMLElement;
      const sid = el.getAttribute("data-tracked-open-persp") ?? "";
      const title = el.getAttribute("data-tracked-title") ?? "";
      if (!sid) return;
      state.newsActiveLane = "perspectives";
      state.activeTabId = "news-lane:perspectives";
      actions.onRefreshShell();
      void actions.onSendPerspectivesTopic?.(title, undefined, sid);
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
        reRender();
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
        reRender();
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
        await refreshNewsState("stories");
        reRender();
      });
    });
  });

  container.querySelectorAll("[data-news-open-reader]").forEach((btn) => {
    btn.addEventListener("click", () => {
      state.newsReaderArticleId = (btn as HTMLElement).getAttribute("data-news-open-reader") ?? null;
      state.newsReaderShowOriginal = false;
      reRender();
    });
  });

  container.querySelector("#news-reader-close-btn")?.addEventListener("click", () => {
    state.newsReaderArticleId = null;
    reRender();
  });

  container.querySelector("#news-reader-toggle-orig-btn")?.addEventListener("click", () => {
    state.newsReaderShowOriginal = !state.newsReaderShowOriginal;
    reRender();
  });

  container.querySelectorAll("[data-news-toggle-orig]").forEach((btn) => {
    btn.addEventListener("click", () => {
      const cid = (btn as HTMLElement).getAttribute("data-news-toggle-orig") ?? "";
      if (!cid) return;
      state.newsStoryShowOriginal[cid] = !state.newsStoryShowOriginal[cid];
      reRender();
    });
  });

  container.querySelectorAll("[data-news-translate]").forEach((btn) => {
    btn.addEventListener("click", () => {
      state.newsStoryMenuId = null;
      const aid = (btn as HTMLElement).getAttribute("data-news-translate") ?? "";
      if (!aid) return;
      state.newsStatusMessage = t("news.translating_article");
      reRender();
      const targetLang = state.contentTranslationConfig?.primary_language || "";
      void sidecarTranslateNewsArticle(aid, targetLang).then(async (r) => {
        if (r.ok && (r.translated_text || r.title_tr || r.snippet_tr)) {
          for (const s of [...state.newsStories, ...state.newsPerspectivesStories]) {
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
          for (const fs of state.newsFollowedStories) {
            for (const u of fs.updates) {
              if (u.article_id === aid) {
                if (r.translated_text) u.translated_text = r.translated_text;
                if (r.title_tr) u.title_tr = r.title_tr;
                if (r.snippet_tr) u.snippet_tr = r.snippet_tr;
              }
            }
          }
          state.newsReaderArticleId = aid;
          state.newsReaderShowOriginal = false;
          state.newsStatusMessage = t("news.translated_article");
        } else {
          state.newsStatusMessage = `${t("common.error_prefix")} ${r.error ?? t("news.translation_failed")}`;
        }
        reRender();
      });
    });
  });

  // Chat-based Perspectives events
  const perspInput = container.querySelector("#persp-topic-input") as HTMLInputElement | null;
  const submitPerspectivesTopic = () => {
    const val = (perspInput?.value ?? "").trim();
    if (!val || state.newsPerspectivesStream) return;
    if (perspInput) perspInput.value = "";
    void actions.onSendPerspectivesTopic?.(val);
  };
  container.querySelector("#persp-send-btn")?.addEventListener("click", submitPerspectivesTopic);
  perspInput?.addEventListener("keydown", (e) => {
    if ((e as KeyboardEvent).key === "Enter" && !(e as KeyboardEvent).shiftKey) {
      e.preventDefault();
      submitPerspectivesTopic();
    }
  });
  container.querySelectorAll("[data-persp-pick-topic]").forEach((btn) => {
    btn.addEventListener("click", () => {
      const topic = (btn as HTMLElement).getAttribute("data-persp-pick-topic") ?? "";
      if (topic && !state.newsPerspectivesStream) {
        void actions.onSendPerspectivesTopic?.(topic);
      }
    });
  });
  container.querySelectorAll("[data-persp-pick-cluster]").forEach((btn) => {
    btn.addEventListener("click", () => {
      const el = btn as HTMLElement;
      const cid = el.getAttribute("data-persp-pick-cluster") ?? "";
      const title = el.getAttribute("data-persp-pick-title") ?? "";
      if (title && !state.newsPerspectivesStream) {
        void actions.onSendPerspectivesTopic?.(title, cid || undefined);
      }
    });
  });
  container.querySelectorAll("[data-persp-pick-followed]").forEach((btn) => {
    btn.addEventListener("click", () => {
      const el = btn as HTMLElement;
      const sid = el.getAttribute("data-persp-pick-followed") ?? "";
      const title = el.getAttribute("data-persp-pick-title") ?? "";
      if (title && sid && !state.newsPerspectivesStream) {
        void actions.onSendPerspectivesTopic?.(title, undefined, sid);
      }
    });
  });

  container.querySelectorAll(".tracked-story-card [data-citation-idx]").forEach((btn) => {
    btn.addEventListener("click", () => {
      const el = btn as HTMLElement;
      const idx = Number(el.getAttribute("data-citation-idx") || "0");
      const cardEl = el.closest("[data-tracked-story-id]") as HTMLElement | null;
      const sid = cardEl?.getAttribute("data-tracked-story-id") ?? "";
      const story = state.newsFollowedStories.find((s) => s.story_id === sid);
      const upd = idx > 0 ? story?.updates[idx - 1] : undefined;
      if (upd) {
        state.newsReaderArticleId = upd.article_id;
        state.newsReaderShowOriginal = false;
        reRender();
      }
    });
  });

  const perspScroll = container.querySelector("#persp-messages-list") as HTMLElement | null;
  if (perspScroll) {
    perspScroll.scrollTop = perspScroll.scrollHeight;
  }
  if (actions.perspChatActions) {
    bindChatThreadEvents(container, actions.perspChatActions, {
      onStateChange: reRender,
      activeConvId: state.newsPerspectivesDetail?.conversation.id ?? "",
      getSources: () => state.newsPerspectivesDetail?.sources ?? [],
      getMessages: () => state.newsPerspectivesDetail?.messages ?? [],
    });
  }

  // Topics events
  const addTopicBtn = container.querySelector("#news-topic-add-btn") as HTMLButtonElement | null;
  addTopicBtn?.addEventListener("click", () => {
    const nameEl = container.querySelector("#news-topic-name-input") as HTMLInputElement | null;
    const kwEl = container.querySelector("#news-topic-kw-input") as HTMLInputElement | null;
    const name = nameEl?.value.trim() ?? "";
    if (!name || addTopicBtn.disabled) {
      if (!name) nameEl?.focus();
      return;
    }
    addTopicBtn.disabled = true;
    void sidecarManageNewsTopic({
      action: "add",
      name,
      keywords: kwEl?.value.trim() ?? "",
      watch: true,
    })
      .then(async (r) => {
        state.newsStatusMessage = r.ok ? t("news.tracked_topic_added", { name }) : `${t("common.error_prefix")} ${r.error}`;
        await refreshNewsState(onReRender ? "settings" : "topics");
      })
      .catch((err) => {
        state.newsStatusMessage = `${t("common.error_prefix")} ${String(err)}`;
      })
      .finally(() => {
        reRender();
        actions.onRefreshShell();
      });
  });

  container.querySelectorAll("[data-news-topic-del]").forEach((btn) => {
    btn.addEventListener("click", () => {
      const el = btn as HTMLButtonElement;
      const tid = el.getAttribute("data-news-topic-del") ?? "";
      if (!tid || el.disabled) return;
      el.disabled = true;
      void sidecarManageNewsTopic({ action: "delete", topic_id: tid })
        .then(async () => {
          await refreshNewsState(onReRender ? "settings" : "topics");
        })
        .catch((err) => {
          state.newsStatusMessage = `${t("common.error_prefix")} ${String(err)}`;
        })
        .finally(() => {
          reRender();
          actions.onRefreshShell();
        });
    });
  });

  // Sources events
  const reloadSources = () => {
    void refreshNewsState(onReRender ? "settings" : "sources").then(() => {
      reRender();
      actions.onRefreshShell();
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

  const addFeedBtn = container.querySelector("#news-add-feed-btn") as HTMLButtonElement | null;
  addFeedBtn?.addEventListener("click", () => {
    const urlEl = container.querySelector("#news-add-feed-url") as HTMLInputElement | null;
    const titleEl = container.querySelector("#news-add-feed-title") as HTMLInputElement | null;
    const val = urlEl?.value.trim() ?? "";
    if (!val || addFeedBtn.disabled) {
      if (!val) urlEl?.focus();
      return;
    }
    addFeedBtn.disabled = true;
    const isUrl = val.startsWith("http://") || val.startsWith("https://");
    void sidecarManageNewsFeed(
      isUrl
        ? { feed_url: val, title: titleEl?.value.trim() ?? "" }
        : { domain: val, title: titleEl?.value.trim() ?? "" }
    )
      .then((r) => {
        state.newsStatusMessage = r.ok ? t("news.added_item", { item: val }) : `${t("common.error_prefix")} ${r.error}`;
      })
      .catch((err) => {
        state.newsStatusMessage = `${t("common.error_prefix")} ${String(err)}`;
      })
      .finally(() => {
        reloadSources();
      });
  });

  container.querySelectorAll("[data-news-toggle-feed]").forEach((btn) => {
    btn.addEventListener("click", () => {
      const el = btn as HTMLButtonElement;
      if (el.disabled) return;
      const fid = el.getAttribute("data-news-toggle-feed") ?? "";
      const en = el.getAttribute("data-enabled") === "1";
      el.disabled = true;
      void sidecarManageNewsFeed({ action: "toggle", feed_id: fid, enabled: en })
        .catch((err) => {
          state.newsStatusMessage = `${t("common.error_prefix")} ${String(err)}`;
        })
        .finally(() => {
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
