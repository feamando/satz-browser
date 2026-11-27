use crate::db::DbState;
use crate::SidecarState;
use serde::{Deserialize, Serialize};
use std::collections::{HashMap, HashSet};
use std::io::{Read, Write};
use std::net::TcpStream;
use std::sync::Mutex;
use std::time::{Duration, Instant};
use tauri::{
    webview::{PageLoadEvent, WebviewBuilder},
    AppHandle, Emitter, LogicalPosition, LogicalSize, Manager, Rect, WebviewUrl,
};
use url::Url;

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct TabBoundsSpec {
    pub tab_id: String,
    pub url: String,
    pub x: f64,
    pub y: f64,
    pub w: f64,
    pub h: f64,
    #[serde(default)]
    pub toolbar_bottom: Option<f64>,
    #[serde(default)]
    pub viewport_h: Option<f64>,
}

pub fn default_browser_user_agent() -> &'static str {
    #[cfg(windows)]
    {
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36 Edg/131.0.0.0"
    }
    #[cfg(not(windows))]
    {
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.2 Safari/605.1.15"
    }
}

/// Computes the child webview `(x, y, w, h)` in `wry` parent-frame logical coordinates.
/// Guarantees `safe_y >= toolbar_bottom` in content coordinates and adds `titlebar_inset`
/// on macOS (where `wry`'s `parent_view` is `NSThemeFrame` including the window titlebar).
pub fn compute_child_webview_bounds(
    spec: &TabBoundsSpec,
    titlebar_inset: f64,
) -> (f64, f64, f64, f64) {
    let min_toolbar_bottom = spec.toolbar_bottom.unwrap_or(70.0).max(34.0);
    let safe_content_y = spec.y.max(min_toolbar_bottom);
    let dy = (safe_content_y - spec.y).max(0.0);
    let safe_h = (spec.h - dy).max(0.0);
    let safe_w = spec.w.max(0.0);
    let safe_x = spec.x.max(0.0);
    let adjusted_y = safe_content_y + titlebar_inset.max(0.0);
    (safe_x, adjusted_y, safe_w, safe_h)
}

fn window_titlebar_inset(window: &tauri::Window) -> f64 {
    #[cfg(target_os = "macos")]
    {
        let scale = window.scale_factor().unwrap_or(1.0).max(0.1);
        if let (Ok(outer), Ok(inner)) = (window.outer_size(), window.inner_size()) {
            if outer.height > inner.height {
                let diff = (outer.height - inner.height) as f64 / scale;
                if diff >= 1.0 && diff <= 80.0 {
                    return diff;
                }
            }
        }
        28.0
    }
    #[cfg(not(target_os = "macos"))]
    {
        let _ = window;
        0.0
    }
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct TabPageEventPayload {
    pub tab_id: String,
    pub event_type: String,
    pub url: Option<String>,
    pub title: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub has_password_field: Option<bool>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub favicon_url: Option<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct TabNewWindowPayload {
    pub source_tab_id: String,
    pub url: String,
    pub background: bool,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct TabCaptureCacheEntry {
    pub tab_id: String,
    pub url: String,
    pub captured_at: u64,
    pub text_hash: u64,
}

pub struct WebviewManagerState {
    pub max_live_tabs: usize,
    pub tab_urls: Mutex<HashMap<String, String>>,
    pub last_shown: Mutex<HashMap<String, Instant>>,
    pub visible_tabs: Mutex<HashSet<String>>,
    pub capture_cache: Mutex<HashMap<String, TabCaptureCacheEntry>>,
    pub navigator_tabs: Mutex<HashMap<String, String>>,
    pub last_captures: Mutex<HashMap<String, serde_json::Value>>,
    pub recent_bg_open_ms: Mutex<HashMap<String, Instant>>,
    pub recent_new_window: Mutex<HashMap<String, (String, Instant)>>,
}

impl Default for WebviewManagerState {
    fn default() -> Self {
        Self {
            max_live_tabs: 8,
            tab_urls: Mutex::new(HashMap::new()),
            last_shown: Mutex::new(HashMap::new()),
            visible_tabs: Mutex::new(HashSet::new()),
            capture_cache: Mutex::new(HashMap::new()),
            navigator_tabs: Mutex::new(HashMap::new()),
            last_captures: Mutex::new(HashMap::new()),
            recent_bg_open_ms: Mutex::new(HashMap::new()),
            recent_new_window: Mutex::new(HashMap::new()),
        }
    }
}

impl WebviewManagerState {
    pub fn record_bg_open_gesture(&self, tab_id: &str) {
        self.recent_bg_open_ms
            .lock()
            .unwrap()
            .insert(tab_id.to_string(), Instant::now());
    }

    pub fn consume_bg_open_if_recent(&self, tab_id: &str, url: &str) -> bool {
        let now = Instant::now();
        self.recent_new_window
            .lock()
            .unwrap()
            .insert(tab_id.to_string(), (url.to_string(), now));
        let mut bg_map = self.recent_bg_open_ms.lock().unwrap();
        if let Some(ts) = bg_map.remove(tab_id) {
            return now.duration_since(ts) <= Duration::from_millis(800);
        }
        false
    }

    pub fn should_emit_aux_fallback(&self, tab_id: &str, url: &str) -> bool {
        let now = Instant::now();
        let mut nw_map = self.recent_new_window.lock().unwrap();
        if let Some((_, ts)) = nw_map.get(tab_id) {
            if now.duration_since(*ts) <= Duration::from_millis(600) {
                return false;
            }
        }
        nw_map.insert(tab_id.to_string(), (url.to_string(), now));
        true
    }
}

pub fn should_recapture_tab(
    tab_id: &str,
    tab_url: &str,
    visible_tabs: &HashSet<String>,
    cache: &HashMap<String, TabCaptureCacheEntry>,
) -> bool {
    if visible_tabs.contains(tab_id) {
        return true;
    }
    match cache.get(tab_id) {
        Some(entry) => entry.url != tab_url,
        None => true,
    }
}

pub fn wait_for_receivers_with_shared_deadline(
    receivers: Vec<std::sync::mpsc::Receiver<()>>,
    total_budget: Duration,
) -> usize {
    let deadline = Instant::now() + total_budget;
    let mut completed = 0;
    for rx in receivers {
        let rem = deadline.saturating_duration_since(Instant::now());
        if rem.is_zero() {
            break;
        }
        if rx.recv_timeout(rem).is_ok() {
            completed += 1;
        }
    }
    completed
}

pub fn is_likely_url_token(raw: &str) -> bool {
    let t = raw.trim();
    if t.is_empty() || t.contains(' ') || t.starts_with('?') {
        return false;
    }
    if t.starts_with("http://")
        || t.starts_with("https://")
        || t.starts_with("about:")
        || t.starts_with("satzmail://")
    {
        return true;
    }
    let lower = t.to_ascii_lowercase();
    if lower == "localhost"
        || lower.starts_with("localhost:")
        || lower.starts_with("localhost/")
        || lower == "127.0.0.1"
        || lower.starts_with("127.0.0.1:")
        || lower.starts_with("127.0.0.1/")
    {
        return true;
    }
    t.contains('.') && !t.starts_with('.') && !t.ends_with('.')
}

pub fn normalize_url(raw: &str) -> Result<Url, String> {
    let trimmed = raw.trim();
    if trimmed.is_empty() {
        return Url::parse("about:blank").map_err(|e| e.to_string());
    }
    if trimmed.starts_with("http://")
        || trimmed.starts_with("https://")
        || trimmed.starts_with("about:")
        || trimmed.starts_with("satzmail://")
    {
        Url::parse(trimmed).map_err(|e| e.to_string())
    } else if {
        let lower = trimmed.to_ascii_lowercase();
        lower == "localhost"
            || lower.starts_with("localhost:")
            || lower.starts_with("localhost/")
            || lower == "127.0.0.1"
            || lower.starts_with("127.0.0.1:")
            || lower.starts_with("127.0.0.1/")
    } {
        Url::parse(&format!("http://{}", trimmed)).map_err(|e| e.to_string())
    } else if is_likely_url_token(trimmed) {
        Url::parse(&format!("https://{}", trimmed)).map_err(|e| e.to_string())
    } else {
        let encoded = trimmed.replace(' ', "+");
        Url::parse(&format!("https://duckduckgo.com/?q={}", encoded)).map_err(|e| e.to_string())
    }
}

pub fn tab_webview_label(tab_id: &str) -> String {
    format!("tab-{}", tab_id)
}

pub fn close_tab_webview(app: &AppHandle, state: &WebviewManagerState, tab_id: &str) {
    let label = tab_webview_label(tab_id);
    if let Some(wv) = app.get_webview(&label) {
        let _ = wv.close();
    }
    state.tab_urls.lock().unwrap().remove(tab_id);
    state.last_shown.lock().unwrap().remove(tab_id);
    state.visible_tabs.lock().unwrap().remove(tab_id);
    state.capture_cache.lock().unwrap().remove(tab_id);
    state.last_captures.lock().unwrap().remove(tab_id);
    state.recent_bg_open_ms.lock().unwrap().remove(tab_id);
    state.recent_new_window.lock().unwrap().remove(tab_id);
    state
        .navigator_tabs
        .lock()
        .unwrap()
        .retain(|_, v| v != tab_id);
}

pub fn select_lru_eviction_candidates(
    mut live_tab_ids: Vec<String>,
    last_shown_map: &HashMap<String, Instant>,
    protected_tab_ids: &HashSet<String>,
    max_live_tabs: usize,
) -> Vec<String> {
    if live_tab_ids.len() < max_live_tabs {
        return Vec::new();
    }
    let needed_evictions = (live_tab_ids.len() + 1).saturating_sub(max_live_tabs);
    let fallback = Instant::now();
    live_tab_ids.sort_by_key(|tid| last_shown_map.get(tid).copied().unwrap_or(fallback));

    live_tab_ids
        .into_iter()
        .filter(|tid| !protected_tab_ids.contains(tid))
        .take(needed_evictions)
        .collect()
}

fn enforce_lru_cap(
    app: &AppHandle,
    state: &WebviewManagerState,
    protected_tab_ids: &HashSet<String>,
) {
    let window = match app.get_window("main") {
        Some(w) => w,
        None => return,
    };

    let live_tab_ids: Vec<String> = window
        .webviews()
        .into_iter()
        .filter_map(|wv| {
            wv.label()
                .strip_prefix("tab-")
                .map(|rest| rest.to_string())
        })
        .collect();

    let last_shown_map = state.last_shown.lock().unwrap().clone();
    let to_evict = select_lru_eviction_candidates(
        live_tab_ids,
        &last_shown_map,
        protected_tab_ids,
        state.max_live_tabs,
    );

    for candidate_tid in to_evict {
        let label = tab_webview_label(&candidate_tid);
        if let Some(wv) = app.get_webview(&label) {
            let _ = wv.close();
        }
        state.tab_urls.lock().unwrap().remove(&candidate_tid);
        state.last_shown.lock().unwrap().remove(&candidate_tid);
    }
}

pub fn sync_tab_webviews_impl(
    app: &AppHandle,
    state: &WebviewManagerState,
    visible: Vec<TabBoundsSpec>,
) -> Result<(), String> {
    let window = app
        .get_window("main")
        .ok_or_else(|| "main window not found".to_string())?;

    let target_ids: HashSet<String> = visible.iter().map(|v| v.tab_id.clone()).collect();

    // Hide any live tab-* webviews not in `visible`
    for wv in window.webviews() {
        if let Some(tid) = wv.label().strip_prefix("tab-") {
            if !target_ids.contains(tid) {
                let _ = wv.hide();
            }
        }
    }

    {
        let mut vis_lock = state.visible_tabs.lock().unwrap();
        *vis_lock = target_ids.clone();
    }

    let titlebar_inset = window_titlebar_inset(&window);

    for spec in visible {
        let (bx, by, bw, bh) = compute_child_webview_bounds(&spec, titlebar_inset);
        if bw < 10.0 || bh < 10.0 {
            continue;
        }

        let parsed_url = normalize_url(&spec.url)?;
        let normalized_str = parsed_url.to_string();
        let label = tab_webview_label(&spec.tab_id);

        {
            state
                .last_shown
                .lock()
                .unwrap()
                .insert(spec.tab_id.clone(), Instant::now());
        }

        if let Some(existing_wv) = app.get_webview(&label) {
            let _ = existing_wv.set_bounds(Rect {
                position: LogicalPosition::new(bx, by).into(),
                size: LogicalSize::new(bw, bh).into(),
            });

            let should_navigate = {
                let mut map = state.tab_urls.lock().unwrap();
                let prev = map.get(&spec.tab_id).cloned();
                if prev.as_deref() != Some(normalized_str.as_str()) {
                    map.insert(spec.tab_id.clone(), normalized_str.clone());
                    true
                } else {
                    false
                }
            };

            if should_navigate {
                let _ = existing_wv.navigate(parsed_url);
            }
            let _ = existing_wv.show();
        } else {
            enforce_lru_cap(app, state, &target_ids);

            {
                state
                    .tab_urls
                    .lock()
                    .unwrap()
                    .insert(spec.tab_id.clone(), normalized_str.clone());
            }

            let builder = build_child_tab_webview_builder(
                app,
                &spec.tab_id,
                &label,
                parsed_url,
                true,
            );

            let child_wv = window
                .add_child(
                    builder,
                    LogicalPosition::new(bx, by),
                    LogicalSize::new(bw, bh),
                )
                .map_err(|e| format!("failed to add child webview {}: {}", label, e))?;

            #[cfg(windows)]
            attach_child_webview_accelerators(app.clone(), &child_wv, spec.tab_id.clone());

            let _ = child_wv.show();
        }
    }

    Ok(())
}

fn child_tab_bg_open_script() -> &'static str {
    #[cfg(target_os = "macos")]
    {
        r#"(() => {
  if (window.__satzMidInit) return;
  window.__satzMidInit = true;
  const findAnchor = (e) => {
    try {
      const path = typeof e.composedPath === 'function' ? e.composedPath() : [];
      for (const n of path) {
        if (n && n.tagName && (n.tagName === 'A' || n.tagName === 'AREA') && n.href) return n;
      }
      if (e.target && e.target.closest) return e.target.closest('a[href], area[href]');
    } catch (_) {}
    return null;
  };
  window.addEventListener('auxclick', (e) => {
    try {
      if (!e || e.button !== 1) return;
      const anchor = findAnchor(e);
      if (!anchor) return;
      const href = String(anchor.href || '').trim();
      if (href.startsWith('http://') || href.startsWith('https://')) {
        e.preventDefault();
        e.stopPropagation();
        window.open(href, '_blank', 'noopener');
      }
    } catch (_) {}
  }, true);
})();"#
    }
    #[cfg(not(target_os = "macos"))]
    {
        r#"(() => {
  if (window.__satzMidInit) return;
  window.__satzMidInit = true;
  const findAnchor = (e) => {
    try {
      const path = typeof e.composedPath === 'function' ? e.composedPath() : [];
      for (const n of path) {
        if (n && n.tagName && (n.tagName === 'A' || n.tagName === 'AREA') && n.href) return n;
      }
      if (e.target && e.target.closest) return e.target.closest('a[href], area[href]');
    } catch (_) {}
    return null;
  };
  const notifyBgGesture = (e) => {
    try {
      if (!e) return;
      const isMid = e.button === 1;
      const isModClick = (e.ctrlKey || e.metaKey) && e.button === 0;
      if (!isMid && !isModClick) return;
      if (!findAnchor(e)) return;
      if (window.chrome && window.chrome.webview) {
        window.chrome.webview.postMessage('__satz_bg_open__');
      }
    } catch (_) {}
  };
  window.addEventListener('mousedown', notifyBgGesture, true);
  window.addEventListener('auxclick', (e) => {
    notifyBgGesture(e);
    try {
      if (!e || e.button !== 1 || e.defaultPrevented) return;
      const anchor = findAnchor(e);
      if (!anchor) return;
      const href = String(anchor.href || '').trim();
      if (!href.startsWith('http://') && !href.startsWith('https://')) return;
      window.setTimeout(() => {
        try {
          if (window.chrome && window.chrome.webview) {
            window.chrome.webview.postMessage('__satz_bg_fallback__:' + href);
          }
        } catch (_) {}
      }, 90);
    } catch (_) {}
  }, true);
})();"#
    }
}

fn build_child_tab_webview_builder(
    app: &AppHandle,
    tab_id: &str,
    label: &str,
    parsed_url: Url,
    emit_page_events: bool,
) -> WebviewBuilder<tauri::Wry> {
    let tid_load = tab_id.to_string();
    let tid_title = tab_id.to_string();
    let tid_nw = tab_id.to_string();
    let app_load = app.clone();
    let app_title = app.clone();
    let app_nw = app.clone();

    WebviewBuilder::new(label, WebviewUrl::External(parsed_url))
        .user_agent(default_browser_user_agent())
        .initialization_script_for_all_frames(child_tab_bg_open_script())
        .on_new_window(move |url, _features| {
            if url.scheme() == "http" || url.scheme() == "https" {
                let url_str = url.to_string();
                let is_bg = app_nw
                    .try_state::<WebviewManagerState>()
                    .map(|st| st.consume_bg_open_if_recent(&tid_nw, &url_str))
                    .unwrap_or(false);
                let _ = app_nw.emit(
                    "tab-new-window-requested",
                    TabNewWindowPayload {
                        source_tab_id: tid_nw.clone(),
                        url: url_str,
                        background: is_bg,
                    },
                );
            }
            tauri::webview::NewWindowResponse::Deny
        })
        .on_page_load(move |wv, payload| {
            let url_str = payload.url().to_string();
            let ev_type = match payload.event() {
                PageLoadEvent::Started => "load_started",
                PageLoadEvent::Finished => "load_finished",
            };

            if let Some(wv_state) = app_load.try_state::<WebviewManagerState>() {
                wv_state
                    .tab_urls
                    .lock()
                    .unwrap()
                    .insert(tid_load.clone(), url_str.clone());
            }

            if payload.event() == PageLoadEvent::Finished {
                if let Some(db) = app_load.try_state::<DbState>() {
                    let _ = db.record_tab_navigation_or_title(
                        &tid_load,
                        Some(&url_str),
                        None,
                    );
                }
                if !url_str.starts_with("satzmail://") {
                    trigger_dom_capture_and_ingest(
                        app_load.clone(),
                        wv.clone(),
                        tid_load.clone(),
                        url_str.clone(),
                    );
                    if emit_page_events {
                        let app_delayed = app_load.clone();
                        let wv_delayed = wv.clone();
                        let tid_delayed = tid_load.clone();
                        let url_delayed = url_str.clone();
                        std::thread::spawn(move || {
                            std::thread::sleep(Duration::from_millis(1800));
                            trigger_dom_capture_and_ingest(
                                app_delayed,
                                wv_delayed,
                                tid_delayed,
                                url_delayed,
                            );
                        });
                    }
                }
            }

            if emit_page_events {
                let _ = app_load.emit(
                    "tab-page-event",
                    TabPageEventPayload {
                        tab_id: tid_load.clone(),
                        event_type: ev_type.to_string(),
                        url: Some(url_str),
                        title: None,
                        has_password_field: None,
                        favicon_url: None,
                    },
                );
            }
        })
        .on_document_title_changed(move |wv, title| {
            let current_url = wv.url().ok().map(|u| u.to_string());
            if let Some(db) = app_title.try_state::<DbState>() {
                let _ = db.record_tab_navigation_or_title(
                    &tid_title,
                    current_url.as_deref(),
                    Some(&title),
                );
            }
            let cur_u = current_url.clone().unwrap_or_default();
            if !cur_u.starts_with("satzmail://") {
                trigger_dom_capture_and_ingest(
                    app_title.clone(),
                    wv.clone(),
                    tid_title.clone(),
                    cur_u,
                );
            }
            if emit_page_events {
                let _ = app_title.emit(
                    "tab-page-event",
                    TabPageEventPayload {
                        tab_id: tid_title.clone(),
                        event_type: "title_changed".to_string(),
                        url: current_url,
                        title: Some(title),
                        has_password_field: None,
                        favicon_url: None,
                    },
                );
            }
        })
}

#[cfg(windows)]
pub(crate) fn attach_webview_accelerators(app: AppHandle, wv: &tauri::Webview) {
    let _ = wv.with_webview(move |platform_wv| {
        unsafe {
            use webview2_com::AcceleratorKeyPressedEventHandler;
            use webview2_com::Microsoft::Web::WebView2::Win32::{
                COREWEBVIEW2_KEY_EVENT_KIND_KEY_DOWN,
                COREWEBVIEW2_KEY_EVENT_KIND_SYSTEM_KEY_DOWN,
            };

            #[link(name = "user32")]
            extern "system" {
                fn GetKeyState(nVirtKey: i32) -> i16;
            }
            const VK_SHIFT: i32 = 0x10;
            const VK_CONTROL: i32 = 0x11;

            let app_key = app.clone();
            let controller = platform_wv.controller();
            let handler = AcceleratorKeyPressedEventHandler::create(Box::new(
                move |_controller, args| {
                    if let Some(args) = args {
                        let mut kind = COREWEBVIEW2_KEY_EVENT_KIND_KEY_DOWN;
                        let _ = args.KeyEventKind(&mut kind);
                        if kind == COREWEBVIEW2_KEY_EVENT_KIND_KEY_DOWN
                            || kind == COREWEBVIEW2_KEY_EVENT_KIND_SYSTEM_KEY_DOWN
                        {
                            let ctrl_down = (GetKeyState(VK_CONTROL) as u16 & 0x8000) != 0;
                            let shift_down = (GetKeyState(VK_SHIFT) as u16 & 0x8000) != 0;
                            if ctrl_down {
                                let mut key: u32 = 0;
                                let _ = args.VirtualKey(&mut key);
                                let cmd = match (key, shift_down) {
                                    (0x4C, true) => Some("fill_login"),           // Ctrl+Shift+L
                                    (0x57, true) => Some("archive_conversation"), // Ctrl+Shift+W
                                    (0x4E, false) => Some("new_conversation"),     // Ctrl+N
                                    (0x4B, false) => Some("filter_conversations"), // Ctrl+K
                                    (0x42, false) => Some("toggle_brain"),         // Ctrl+B
                                    (0x54, false) => Some("new_tab"),              // Ctrl+T
                                    (0x57, false) => Some("close_tab"),            // Ctrl+W
                                    (0x4C, false) => Some("focus_address"),        // Ctrl+L
                                    (0x4A, false) => Some("toggle_agent_rail"),    // Ctrl+J
                                    (0x4D, false) => Some("toggle_compare"),       // Ctrl+M
                                    (0x44, false) => Some("bookmark_current"),     // Ctrl+D
                                    (0x31, false) => Some("tab_chat"),             // Ctrl+1
                                    (0x32, false) => Some("tab_2"),                // Ctrl+2
                                    (0x33, false) => Some("tab_3"),                // Ctrl+3
                                    (0x34, false) => Some("tab_4"),                // Ctrl+4
                                    (0x35, false) => Some("tab_5"),                // Ctrl+5
                                    (0x36, false) => Some("tab_6"),                // Ctrl+6
                                    (0x37, false) => Some("tab_7"),                // Ctrl+7
                                    (0x38, false) => Some("tab_8"),                // Ctrl+8
                                    (0x39, false) => Some("tab_9"),                // Ctrl+9
                                    _ => None, // Ctrl+F (0x46) left to WebView2 find-in-page
                                };
                                if let Some(action) = cmd {
                                    let _ = args.SetHandled(true);
                                    let _ = app_key.emit("menu-shortcut", action);
                                }
                            }
                        }
                    }
                    Ok(())
                },
            ));
            let mut token: i64 = 0;
            let _ = controller.add_AcceleratorKeyPressed(&handler, &mut token);
        }
    });
}

#[cfg(windows)]
fn attach_child_webview_accelerators(app: AppHandle, child_wv: &tauri::Webview, tab_id: String) {
    attach_webview_accelerators(app.clone(), child_wv);
    let _ = child_wv.with_webview(move |platform_wv| {
        unsafe {
            use webview2_com::{take_pwstr, WebMessageReceivedEventHandler};
            use windows::core::PWSTR;

            let controller = platform_wv.controller();
            if let Ok(core_wv) = controller.CoreWebView2() {
                let app_msg = app.clone();
                let tid_msg = tab_id.clone();
                let msg_handler = WebMessageReceivedEventHandler::create(Box::new(
                    move |_, args| {
                        let Some(args) = args else {
                            return Ok(());
                        };
                        let mut raw_ptr = PWSTR::null();
                        if args.TryGetWebMessageAsString(&mut raw_ptr).is_ok() {
                            let msg = take_pwstr(raw_ptr);
                            if msg == "__satz_bg_open__" {
                                if let Some(wv_state) = app_msg.try_state::<WebviewManagerState>() {
                                    wv_state.record_bg_open_gesture(&tid_msg);
                                }
                            } else if let Some(raw_url) = msg.strip_prefix("__satz_bg_fallback__:") {
                                let trimmed = raw_url.trim();
                                if (trimmed.starts_with("http://") || trimmed.starts_with("https://"))
                                    && trimmed.len() <= 8192
                                {
                                    let should_emit = app_msg
                                        .try_state::<WebviewManagerState>()
                                        .map(|st| st.should_emit_aux_fallback(&tid_msg, trimmed))
                                        .unwrap_or(false);
                                    if should_emit {
                                        let _ = app_msg.emit(
                                            "tab-new-window-requested",
                                            TabNewWindowPayload {
                                                source_tab_id: tid_msg.clone(),
                                                url: trimmed.to_string(),
                                                background: true,
                                            },
                                        );
                                    }
                                }
                            }
                        }
                        Ok(())
                    },
                ));
                let mut msg_token: i64 = 0;
                let _ = core_wv.add_WebMessageReceived(&msg_handler, &mut msg_token);
            }
        }
    });
}

pub fn navigate_tab_webview_impl(
    app: &AppHandle,
    state: &WebviewManagerState,
    tab_id: &str,
    raw_url: &str,
) -> Result<String, String> {
    let parsed_url = normalize_url(raw_url)?;
    let normalized_str = parsed_url.to_string();
    {
        state
            .tab_urls
            .lock()
            .unwrap()
            .insert(tab_id.to_string(), normalized_str.clone());
    }
    let label = tab_webview_label(tab_id);
    if let Some(wv) = app.get_webview(&label) {
        wv.navigate(parsed_url).map_err(|e| e.to_string())?;
    }
    Ok(normalized_str)
}

pub fn control_tab_webview_impl(
    app: &AppHandle,
    tab_id: &str,
    action: &str,
) -> Result<(), String> {
    let label = tab_webview_label(tab_id);
    if let Some(wv) = app.get_webview(&label) {
        match action {
            "back" => wv
                .eval("window.history.back();")
                .map_err(|e| e.to_string())?,
            "forward" => wv
                .eval("window.history.forward();")
                .map_err(|e| e.to_string())?,
            "reload" => wv.reload().map_err(|e| e.to_string())?,
            _ => return Err(format!("unknown tab action: {}", action)),
        }
    }
    Ok(())
}

const COLLECT_AFFORDANCES_BODY: &str = r##"() => {
  try {
    const clean = (s, n) => String(s || '').replace(/\s+/g, ' ').trim().slice(0, n);
    const SENSITIVE_RE = /(password|passwd|passcode|current-password|new-password|cc-number|cc-csc|cvv|cvc)/i;
    const isVisible = (el) => {
      if (!el || el.disabled) return false;
      if (el.getAttribute && (el.getAttribute('aria-disabled') === 'true' || el.getAttribute('aria-hidden') === 'true')) return false;
      const st = window.getComputedStyle ? window.getComputedStyle(el) : null;
      if (st && (st.display === 'none' || st.visibility === 'hidden' || st.opacity === '0')) return false;
      const rect = el.getBoundingClientRect ? el.getBoundingClientRect() : { width: 1, height: 1 };
      if ((rect.width <= 0 || rect.height <= 0) && el.offsetParent === null) return false;
      return true;
    };
    const isSensitive = (el) => {
      const tag = (el.tagName || '').toLowerCase();
      if (tag !== 'input' && tag !== 'textarea') return false;
      const t = (el.type || '').toLowerCase();
      if (t === 'password' || t === 'hidden') return true;
      const ac = el.getAttribute('autocomplete') || '';
      const nm = el.getAttribute('name') || '';
      const idv = el.id || '';
      return SENSITIVE_RE.test(ac) || SENSITIVE_RE.test(nm) || SENSITIVE_RE.test(idv);
    };
    const getLabel = (el) => {
      const ariaLbl = el.getAttribute('aria-label') || '';
      if (ariaLbl) return clean(ariaLbl, 56);
      const labelledBy = el.getAttribute('aria-labelledby') || '';
      if (labelledBy) {
        const ref = document.getElementById(labelledBy.split(/\s+/)[0]);
        if (ref && ref.innerText) return clean(ref.innerText, 56);
      }
      if (el.id) {
        try {
          const forLbl = document.querySelector('label[for="' + CSS.escape(el.id) + '"]');
          if (forLbl && forLbl.innerText) return clean(forLbl.innerText, 56);
        } catch (_) {}
      }
      const wrapLbl = el.closest ? el.closest('label') : null;
      if (wrapLbl && wrapLbl.innerText) return clean(wrapLbl.innerText, 56);
      const tag = (el.tagName || '').toLowerCase();
      if (tag === 'input' || tag === 'textarea' || tag === 'select') {
        return clean(el.getAttribute('placeholder') || el.getAttribute('title') || el.getAttribute('name') || el.id || '', 56);
      }
      const txt = clean(el.innerText || el.value || el.getAttribute('title') || '', 56);
      if (txt) return txt;
      const img = el.querySelector ? el.querySelector('img[alt]') : null;
      return img ? clean(img.getAttribute('alt') || '', 56) : '';
    };
    const getRole = (el) => {
      const tag = (el.tagName || '').toLowerCase();
      const ar = (el.getAttribute('role') || '').toLowerCase();
      if (tag === 'select') return 'select';
      if (tag === 'textarea') return 'textarea';
      if (tag === 'input') {
        const t = (el.type || 'text').toLowerCase();
        if (t === 'checkbox') return 'checkbox';
        if (t === 'radio') return 'radio';
        if (t === 'submit' || t === 'button' || t === 'reset') return 'button';
        if (t === 'search') return 'searchbox';
        return 'input';
      }
      if (ar && ['button', 'tab', 'checkbox', 'radio', 'combobox', 'switch', 'menuitem', 'searchbox', 'option'].includes(ar)) return ar;
      if (tag === 'button') return 'button';
      if (tag === 'a') return 'link';
      return ar || tag;
    };
    const raw = Array.from(document.querySelectorAll(
      'button, input, select, textarea, [role="button"], [role="tab"], [role="checkbox"], [role="radio"], [role="combobox"], [role="switch"], [role="menuitem"], a[href]'
    ));
    const scored = [];
    const seenKeys = new Set();
    for (let i = 0; i < raw.length; i++) {
      const el = raw[i];
      if (!isVisible(el) || isSensitive(el)) continue;
      const role = getRole(el);
      const label = getLabel(el);
      if (!label && role === 'link') continue;
      if (!label && !el.name && !el.id && role !== 'input' && role !== 'searchbox') continue;
      const tag = (el.tagName || '').toLowerCase();
      const tp = tag === 'input' ? (el.type || 'text').toLowerCase() : (tag === 'select' ? 'select' : role);
      const sig = role + '|' + label + '|' + (el.id || el.name || '');
      if (label && seenKeys.has(sig)) continue;
      if (label) seenKeys.add(sig);

      let sc = 0;
      if (role === 'select' || role === 'checkbox' || role === 'radio' || role === 'searchbox' || role === 'input' || role === 'textarea' || role === 'switch' || role === 'tab') sc += 25;
      else if (role === 'button' || role === 'combobox') sc += 20;
      else if (role === 'link') sc += 5;
      if (el.closest && el.closest('main, [role="main"], form, [role="dialog"], [role="tablist"], aside')) sc += 15;
      if (el.closest && el.closest('footer')) sc -= 12;
      if (el.closest && el.closest('header, nav') && role === 'link') sc -= 6;
      const rect = el.getBoundingClientRect ? el.getBoundingClientRect() : { top: 9999 };
      if (rect.top >= 0 && rect.top <= (window.innerHeight || 900) * 1.5) sc += 5;
      scored.push({ el, role, label, type: tp, sc, idx: i });
    }
    scored.sort((a, b) => (b.sc - a.sc) || (a.idx - b.idx));
    const chosen = scored.slice(0, 50);
    chosen.sort((a, b) => a.idx - b.idx);

    const out = [];
    for (let i = 0; i < chosen.length; i++) {
      const item = chosen[i];
      const el = item.el;
      const eid = 'e' + (i + 1);
      try { el.setAttribute('data-satz-eid', eid); } catch (_) {}
      const rec = {
        eid,
        role: item.role,
        label: item.label || item.type,
        type: item.type
      };
      const tag = (el.tagName || '').toLowerCase();
      if (item.role === 'checkbox' || item.role === 'radio' || item.role === 'switch') {
        rec.checked = Boolean(el.checked || el.getAttribute('aria-checked') === 'true');
        rec.value = rec.checked ? 'checked' : 'unchecked';
      } else if (tag === 'select') {
        const selOpt = el.options && el.selectedIndex >= 0 ? el.options[el.selectedIndex] : null;
        rec.value = clean((selOpt && (selOpt.text || selOpt.value)) || el.value || '', 40);
        const opts = [];
        for (let k = 0; k < Math.min(el.options ? el.options.length : 0, 8); k++) {
          const ot = clean(el.options[k].text || el.options[k].value, 28);
          if (ot) opts.push(ot);
        }
        if (opts.length > 0) rec.options = opts;
      } else if (tag === 'input' || tag === 'textarea') {
        rec.value = clean(el.value || '', 40);
      } else if (item.role === 'tab') {
        rec.selected = el.getAttribute('aria-selected') === 'true';
        rec.value = rec.selected ? 'selected' : '';
      } else if (tag === 'a' && el.href) {
        rec.href = String(el.href).slice(0, 120);
      }
      rec.selector_hint = {
        tag,
        id: clean(el.id || '', 60),
        name: clean(el.getAttribute('name') || '', 60),
        aria_label: clean(el.getAttribute('aria-label') || '', 60),
        role: item.role,
        label: item.label
      };
      out.push(rec);
    }
    return out;
  } catch (e) {
    return [];
  }
}"##;

fn dom_affordance_js() -> &'static str {
    static JS: std::sync::OnceLock<String> = std::sync::OnceLock::new();
    JS.get_or_init(|| {
        format!(
            r##"(() => {{
  try {{
    if (window.top !== window.self) {{
      return JSON.stringify({{ url: String(location.href || ''), title: String(document.title || ''), elements: [] }});
    }}
    const collectAffordances = {COLLECT_AFFORDANCES_BODY};
    return JSON.stringify({{
      url: String(location.href || ''),
      title: String(document.title || ''),
      elements: collectAffordances()
    }});
  }} catch (e) {{
    return JSON.stringify({{ url: String(location.href || ''), title: String(document.title || ''), elements: [], error: String(e) }});
  }}
}})()"##
        )
    })
}

fn dom_capture_js() -> &'static str {
    static JS: std::sync::OnceLock<String> = std::sync::OnceLock::new();
    JS.get_or_init(|| {
        let tpl = r##"(() => {
  try {
    const parts = [];
    const sel = window.getSelection ? String(window.getSelection()).trim() : '';
    if (sel) {
      parts.push('[SELECTED TEXT]\n' + sel);
    }
    const acctEl = document.querySelector('[aria-label*="@"][aria-label*="Google"], [aria-label*="Account"], [data-email]');
    if (acctEl) {
      const label = acctEl.getAttribute('aria-label') || acctEl.getAttribute('data-email') || '';
      if (label) parts.push('[AUTHENTICATED ACCOUNT] ' + label);
    }
    const emailRows = document.querySelectorAll('tr.zA, [role="row"]');
    if (emailRows && emailRows.length > 0) {
      const rowLines = [];
      for (let i = 0; i < Math.min(emailRows.length, 25); i++) {
        const r = emailRows[i];
        const txt = (r.innerText || '').replace(/\s+/g, ' ').trim();
        if (txt.length > 8) {
          rowLines.push('[' + (i + 1) + '] ' + txt);
        }
      }
      if (rowLines.length > 0) {
        parts.push('[VISIBLE LIST / INBOX ROWS (TOP = LATEST)]\n' + rowLines.join('\n'));
      }
    }

    const findings = [];
    const seenImgs = new Set();
    const seenVideoIds = new Set();
    const ytLinks = Array.from(document.querySelectorAll('a#video-title[href], a[href*="/watch?v="], a[href*="youtu.be/"]'));
    for (let i = 0; i < ytLinks.length && findings.length < 8; i++) {
      const a = ytLinks[i];
      const href = a.href || '';
      const vm = href.match(/(?:[?&]v=|youtu\.be\/)([A-Za-z0-9_-]{11})/);
      if (!vm) continue;
      const vid = vm[1];
      if (seenVideoIds.has(vid)) continue;
      const rawTitle = (a.innerText || a.getAttribute('title') || a.getAttribute('aria-label') || '').replace(/\s+/g, ' ').trim();
      if (!rawTitle || rawTitle.length < 4) continue;
      seenVideoIds.add(vid);
      const thumbUrl = 'https://i.ytimg.com/vi/' + vid + '/hqdefault.jpg';
      seenImgs.add(thumbUrl);
      findings.push({
        image_url: thumbUrl,
        title: rawTitle.slice(0, 140),
        price: 'video',
        page_url: 'https://www.youtube.com/watch?v=' + vid
      });
    }
    const imgEls = Array.from(document.querySelectorAll('article img, [data-testid*="product" i] img, [class*="product" i] img, [class*="card" i] img, main img, img'));
    for (let i = 0; i < imgEls.length && findings.length < 8; i++) {
      const img = imgEls[i];
      const src = img.currentSrc || img.src || img.getAttribute('data-src') || img.getAttribute('srcset')?.split(' ')[0] || '';
      if (!src || !src.startsWith('http') || seenImgs.has(src)) continue;
      const lowerSrc = src.toLowerCase();
      if (lowerSrc.includes('sprite') || lowerSrc.includes('logo') || lowerSrc.includes('icon') || lowerSrc.includes('pixel') || lowerSrc.endsWith('.svg')) continue;
      const rect = img.getBoundingClientRect ? img.getBoundingClientRect() : { width: img.naturalWidth || 0, height: img.naturalHeight || 0 };
      const w = Math.max(rect.width || 0, img.naturalWidth || 0, img.width || 0);
      const h = Math.max(rect.height || 0, img.naturalHeight || 0, img.height || 0);
      if (w > 0 && h > 0 && (w < 85 || h < 85)) continue;
      const card = img.closest('article, [data-testid*="product" i], [class*="product" i], [class*="card" i], li, a') || img.parentElement;
      const linkEl = img.closest('a[href]') || (card ? card.querySelector('a[href]') : null);
      const href = linkEl && linkEl.href ? linkEl.href : location.href;
      let cardTxt = card && card.innerText ? card.innerText.replace(/\s+/g, ' ').trim() : '';
      const altTxt = (img.alt || img.title || '').replace(/\s+/g, ' ').trim();
      const titleTxt = (altTxt && altTxt.length > 4 ? altTxt : cardTxt).slice(0, 140);
      if (!titleTxt && w < 120) continue;
      const priceMatch = cardTxt.match(/(?:€|\$|£|EUR|USD|CHF)\s?\d+(?:[.,]\d{2})?|\d+(?:[.,]\d{2})?\s?(?:€|\$|£|EUR|USD|CHF)/i);
      const priceTxt = priceMatch ? priceMatch[0].trim() : '';
      seenImgs.add(src);
      findings.push({
        image_url: src,
        title: titleTxt || document.title || location.hostname,
        price: priceTxt,
        page_url: href
      });
    }
    if (findings.length > 0) {
      const fLines = findings.map((f, idx) =>
        `[ITEM ${idx + 1}] ${f.title}${f.price ? ' (' + f.price + ')' : ''} | link: ${f.page_url} | image: ${f.image_url}`
      );
      parts.push('[EXTRACTED PAGE ITEMS & IMAGES]\n' + fLines.join('\n'));
    }

    const pageLinks = [];
    const seenHrefs = new Set();
    const anchorEls = Array.from(document.querySelectorAll('main a[href], article a[href], [role="main"] a[href], h1 a[href], h2 a[href], h3 a[href], a#video-title[href]'));
    for (let i = 0; i < anchorEls.length && pageLinks.length < 15; i++) {
      const a = anchorEls[i];
      const href = a.href || '';
      if (!href.startsWith('http') || seenHrefs.has(href)) continue;
      const txt = (a.innerText || a.getAttribute('title') || '').replace(/\s+/g, ' ').trim();
      if (txt.length < 10 || txt.length > 160) continue;
      seenHrefs.add(href);
      pageLinks.push(`- [${txt}](${href})`);
    }
    if (pageLinks.length > 0) {
      parts.push('[KEY LINKS ON PAGE]\n' + pageLinks.join('\n'));
    }

    const mainEl = document.querySelector('[role="main"], main, article');
    if (mainEl && mainEl.innerText) {
      const mainTxt = mainEl.innerText.trim();
      if (mainTxt.length > 20) {
        parts.push('[MAIN VIEWPORT CONTENT]\n' + mainTxt.slice(0, 60000));
      }
    }
    let bodyTxt = document.body && document.body.innerText ? document.body.innerText.trim() : '';
    if (bodyTxt) {
      parts.push('[FULL PAGE VISIBLE TEXT]\n' + bodyTxt.slice(0, 80000));
    }
    const passEls = document.querySelectorAll('input[type="password"]');
    let hasVisiblePass = false;
    for (let i = 0; i < passEls.length; i++) {
      if (passEls[i].offsetParent !== null) {
        hasVisiblePass = true;
        break;
      }
    }
    let faviconUrl = '';
    try {
      const iconLinks = Array.from(document.querySelectorAll('link[rel]'));
      let bestScore = -1;
      for (let i = 0; i < iconLinks.length; i++) {
        const el = iconLinks[i];
        const rel = String(el.getAttribute('rel') || '').toLowerCase().trim();
        const relTokens = rel.split(/\s+/);
        const isIcon = relTokens.includes('icon') || rel === 'shortcut icon';
        const isTouch = relTokens.includes('apple-touch-icon') || relTokens.includes('apple-touch-icon-precomposed');
        if (!isIcon && !isTouch) continue;
        const href = String(el.href || el.getAttribute('href') || '').trim();
        if (!href || (!href.startsWith('http://') && !href.startsWith('https://') && !href.startsWith('data:image/'))) continue;
        let sc = isIcon ? 50 : 20;
        if (rel === 'icon') sc += 8;
        const t = String(el.getAttribute('type') || '').toLowerCase();
        if (t.includes('svg') || href.toLowerCase().includes('.svg')) sc += 14;
        else if (t.includes('png') || href.toLowerCase().includes('.png')) sc += 12;
        const sizes = String(el.getAttribute('sizes') || '').toLowerCase();
        const sm = sizes.match(/(\d+)x(\d+)/);
        if (sm) {
          const px = parseInt(sm[1], 10);
          if (px >= 24 && px <= 64) sc += 20;
          else if (px > 0 && px < 24) sc += 6;
          else if (px > 64 && px <= 192) sc += 10;
        }
        if (sc > bestScore) {
          bestScore = sc;
          faviconUrl = href;
        }
      }
      if (!faviconUrl && location.origin && (location.origin.startsWith('http://') || location.origin.startsWith('https://'))) {
        faviconUrl = location.origin + '/favicon.ico';
      }
    } catch (_) {}
    const collectAffordances = __COLLECT_AFFORDANCES_BODY__;
    const elements = window.top === window.self ? collectAffordances() : [];
    return JSON.stringify({
      url: location.href,
      title: document.title,
      favicon_url: faviconUrl || null,
      has_password_field: hasVisiblePass,
      visible_text: parts.join('\n\n').slice(0, 120000),
      html: document.documentElement ? document.documentElement.outerHTML.slice(0, 1500000) : '',
      findings: findings,
      elements: elements
    });
  } catch (e) {
    return JSON.stringify({
      url: location.href,
      title: document.title,
      has_password_field: false,
      visible_text: document.body ? (document.body.innerText || '').slice(0, 100000) : '',
      html: '',
      findings: [],
      elements: []
    });
  }
})()"##;
        tpl.replace("__COLLECT_AFFORDANCES_BODY__", COLLECT_AFFORDANCES_BODY)
    })
}

fn truncate_utf8(s: &str, max_bytes: usize) -> &str {
    if s.len() <= max_bytes {
        return s;
    }
    let mut end = max_bytes;
    while end > 0 && !s.is_char_boundary(end) {
        end -= 1;
    }
    &s[..end]
}

fn sidecar_port_and_token<R: tauri::Runtime>(app: &AppHandle<R>) -> (u16, String) {
    if let Some(sc) = app.try_state::<SidecarState>() {
        return (sc.settings.port, sc.token.clone());
    }
    (8020, String::new())
}

/// Captures the rendered DOM + visible text on Windows via WebView2 `ExecuteScript`
/// and posts `{conversation_id, source_id, url, title, visible_text, html}` to `POST /ingest`.
/// Section 2.3: Never triggers autofill during capture.
fn trigger_dom_capture_and_ingest<R: tauri::Runtime>(
    app: AppHandle<R>,
    webview: tauri::Webview<R>,
    tab_id: String,
    fallback_url: String,
) {
    trigger_dom_capture_with_completion(app, webview, tab_id, fallback_url, None);
}

pub fn autofill_tab_credentials_impl(
    app: &AppHandle,
    tab_id: &str,
    _auto_submit: bool,
) -> Result<bool, String> {
    let label = tab_webview_label(tab_id);
    let Some(wv) = app.get_webview(&label) else {
        return Ok(false);
    };
    let url_str = wv.url().ok().map(|u| u.to_string()).unwrap_or_default();
    let (port, token) = sidecar_port_and_token(app);
    Ok(try_autofill_profile_credentials_on_webview(
        &wv,
        &url_str,
        port,
        &token,
    ))
}

fn try_autofill_profile_credentials_on_webview<R: tauri::Runtime>(
    webview: &tauri::Webview<R>,
    url: &str,
    port: u16,
    token: &str,
) -> bool {
    if url.is_empty() {
        return false;
    }
    let Ok(parsed_page_url) = Url::parse(url) else {
        return false;
    };
    if parsed_page_url.scheme() != "http" && parsed_page_url.scheme() != "https" {
        return false;
    }
    let expected_origin = parsed_page_url.origin().ascii_serialization();
    if expected_origin.is_empty() || expected_origin == "null" {
        return false;
    }

    let req_body = serde_json::json!({ "target": url }).to_string();
    let addr_str = format!("127.0.0.1:{}", port);
    let Ok(sock_addr) = addr_str.parse() else {
        return false;
    };
    let Ok(mut stream) = TcpStream::connect_timeout(&sock_addr, Duration::from_millis(400)) else {
        return false;
    };
    let _ = stream.set_write_timeout(Some(Duration::from_millis(800)));
    let _ = stream.set_read_timeout(Some(Duration::from_millis(800)));
    let req = format!(
        "POST /passwords/match HTTP/1.1\r\nHost: 127.0.0.1:{}\r\nX-Satz-Token: {}\r\nContent-Type: application/json\r\nContent-Length: {}\r\nConnection: close\r\n\r\n{}",
        port,
        token,
        req_body.len(),
        req_body
    );
    if stream.write_all(req.as_bytes()).is_err() {
        return false;
    }
    let mut resp = Vec::new();
    let _ = stream.read_to_end(&mut resp);
    let resp_str = String::from_utf8_lossy(&resp);
    let Some(body_idx) = resp_str.find("\r\n\r\n") else {
        return false;
    };
    let json_part = &resp_str[body_idx + 4..];
    let Ok(parsed) = serde_json::from_str::<serde_json::Value>(json_part) else {
        return false;
    };
    let Some(creds) = parsed.get("credentials").and_then(|c| c.as_object()) else {
        return false;
    };
    let username = creds
        .get("username")
        .and_then(|v| v.as_str())
        .unwrap_or("");
    let password = creds
        .get("password")
        .and_then(|v| v.as_str())
        .unwrap_or("");
    if username.is_empty() && password.is_empty() {
        return false;
    }

    let u_json = serde_json::to_string(username).unwrap_or_else(|_| "\"\"".to_string());
    let p_json = serde_json::to_string(password).unwrap_or_else(|_| "\"\"".to_string());
    let orig_json = serde_json::to_string(&expected_origin).unwrap_or_else(|_| "\"\"".to_string());

    // Section 2.3:
    // - Only runs on explicit user action
    // - Verifies `window.location.origin === expectedOrigin`
    // - Only fills top frame (`window.top === window.self`)
    // - Never auto-submits the form
    let js = format!(
        r#"(() => {{
            try {{
                if (window.top !== window.self) return false;
                const expectedOrigin = {orig_json};
                if (!expectedOrigin || window.location.origin !== expectedOrigin) return false;
                const uVal = {u_json};
                const pVal = {p_json};
                const setNativeValue = (el, val) => {{
                    const desc = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value');
                    if (desc && desc.set) {{ desc.set.call(el, val); }} else {{ el.value = val; }}
                    el.dispatchEvent(new Event('input', {{ bubbles: true }}));
                    el.dispatchEvent(new Event('change', {{ bubbles: true }}));
                }};
                const passInputs = Array.from(document.querySelectorAll('input[type="password"]')).filter(el => el.offsetParent !== null);
                if (passInputs.length === 0) return false;
                const userInputs = Array.from(document.querySelectorAll('input[type="email"], input[name*="user" i], input[name*="email" i], input[name*="login" i], input[autocomplete="username"], input[type="text"]')).filter(el => el.offsetParent !== null);
                let filled = false;
                if (uVal && userInputs.length > 0) {{
                    setNativeValue(userInputs[0], uVal);
                    filled = true;
                }}
                if (pVal && passInputs.length > 0) {{
                    setNativeValue(passInputs[0], pVal);
                    filled = true;
                }}
                return filled;
            }} catch (e) {{ return false; }}
        }})()"#
    );

    let _ = webview.eval(&js);
    true
}

fn trigger_dom_capture_with_completion<R: tauri::Runtime>(
    app: AppHandle<R>,
    webview: tauri::Webview<R>,
    tab_id: String,
    fallback_url: String,
    done_tx: Option<std::sync::mpsc::Sender<()>>,
) {
    #[cfg(windows)]
    {
        let app_clone = app.clone();
        let tid_clone = tab_id.clone();
        let url_clone = fallback_url.clone();
        let res = webview.with_webview(move |platform_wv| unsafe {
            use webview2_com::ExecuteScriptCompletedHandler;
            use webview2_com::Microsoft::Web::WebView2::Win32::ICoreWebView2;
            use windows::core::PCWSTR;

            let controller = platform_wv.controller();
            if let Ok(core_wv) = controller.CoreWebView2() {
                let core_wv: ICoreWebView2 = core_wv;
                let mut js: Vec<u16> = dom_capture_js().encode_utf16().collect();
                js.push(0);

                let tx_for_handler = done_tx.clone();
                let handler = ExecuteScriptCompletedHandler::create(Box::new(
                    move |_err_code, result_str: String| {
                        let app_bg = app_clone.clone();
                        let tid_bg = tid_clone.clone();
                        let url_bg = url_clone.clone();
                        let tx_bg = tx_for_handler.clone();
                        std::thread::spawn(move || {
                            handle_captured_dom_json(&app_bg, &tid_bg, &url_bg, &result_str);
                            if let Some(tx) = tx_bg {
                                let _ = tx.send(());
                            }
                        });
                        Ok(())
                    },
                ));
                if core_wv.ExecuteScript(PCWSTR(js.as_ptr()), &handler).is_err() {
                    if let Some(tx) = done_tx {
                        let _ = tx.send(());
                    }
                }
            } else if let Some(tx) = done_tx {
                let _ = tx.send(());
            }
        });
        if res.is_err() {
            // Do nothing if webview closed
        }
    }

    #[cfg(target_os = "macos")]
    {
        let app_clone = app.clone();
        let tid_clone = tab_id.clone();
        let url_clone = fallback_url.clone();
        let tx_outer = done_tx.clone();
        let res = webview.with_webview(move |platform_wv| unsafe {
            use block2::RcBlock;
            use objc2::runtime::AnyObject;
            use objc2::AnyThread;
            use objc2_foundation::{
                NSError, NSJSONSerialization, NSJSONWritingOptions, NSString, NSUTF8StringEncoding,
            };
            use objc2_web_kit::WKWebView;

            let wk_ptr = platform_wv.inner() as *const WKWebView;
            if wk_ptr.is_null() {
                if let Some(tx) = done_tx {
                    let _ = tx.send(());
                }
                return;
            }
            let wk_webview: &WKWebView = &*wk_ptr;
            let app_for_block = app_clone.clone();
            let tid_for_block = tid_clone.clone();
            let url_for_block = url_clone.clone();
            let tx_for_block = done_tx.clone();

            let handler = RcBlock::new(move |val: *mut AnyObject, _err: *mut NSError| {
                let mut result_str = String::new();
                if !val.is_null() {
                    if let Ok(json_data) = NSJSONSerialization::dataWithJSONObject_options_error(
                        &*val,
                        NSJSONWritingOptions::FragmentsAllowed,
                    ) {
                        if let Some(json_ns_str) =
                            NSString::initWithData_encoding(NSString::alloc(), &json_data, NSUTF8StringEncoding)
                        {
                            result_str = json_ns_str.to_string();
                        }
                    }
                }
                let app_bg = app_for_block.clone();
                let tid_bg = tid_for_block.clone();
                let url_bg = url_for_block.clone();
                let tx_bg = tx_for_block.clone();
                std::thread::spawn(move || {
                    handle_captured_dom_json(&app_bg, &tid_bg, &url_bg, &result_str);
                    if let Some(tx) = tx_bg {
                        let _ = tx.send(());
                    }
                });
            });

            wk_webview.evaluateJavaScript_completionHandler(
                &NSString::from_str(dom_capture_js()),
                Some(&handler),
            );
        });
        if res.is_err() {
            if let Some(tx) = tx_outer {
                let _ = tx.send(());
            }
        }
    }

    #[cfg(not(any(windows, target_os = "macos")))]
    {
        let _ = webview;
        std::thread::spawn(move || {
            post_ingest_to_sidecar(&app, &tab_id, &fallback_url, "", None, None, None, None, Some("timeout"));
            if let Some(tx) = done_tx {
                let _ = tx.send(());
            }
        });
    }
}

/// Navigates a tab's live WebView2 (or spawns an off-screen WebView2 if the user is on the `[1 chat]` tab),
/// waits up to `timeout_ms` for the page + SPA content to render, and captures its DOM + findings into `/ingest`.
pub fn navigate_and_capture_tab_impl(
    app: &AppHandle,
    db: &DbState,
    wv_state: &WebviewManagerState,
    tab_id: &str,
    raw_url: &str,
    wait_ms: u64,
) -> Result<String, String> {
    let parsed_url = normalize_url(raw_url)?;
    let normalized_str = parsed_url.to_string();
    {
        wv_state
            .tab_urls
            .lock()
            .unwrap()
            .insert(tab_id.to_string(), normalized_str.clone());
    }
    let _ = db.record_tab_navigation_or_title(tab_id, Some(&normalized_str), None);

    let label = tab_webview_label(tab_id);
    if let Some(existing_wv) = app.get_webview(&label) {
        let _ = existing_wv.navigate(parsed_url);
    } else if let Some(window) = app.get_window("main") {
        let builder = build_child_tab_webview_builder(
            app,
            tab_id,
            &label,
            parsed_url,
            false,
        );

        let inset = window_titlebar_inset(&window);
        if let Ok(child_wv) = window.add_child(
            builder,
            LogicalPosition::new(220.0, 70.0 + inset),
            LogicalSize::new(940.0, 760.0),
        ) {
            #[cfg(windows)]
            attach_child_webview_accelerators(app.clone(), &child_wv, tab_id.to_string());
            let is_vis = wv_state.visible_tabs.lock().unwrap().contains(tab_id);
            if !is_vis {
                let _ = child_wv.hide();
            }
        }
    }

    let wait_dur = Duration::from_millis(wait_ms.clamp(600, 6000));
    std::thread::sleep(wait_dur);

    if let Some(wv) = app.get_webview(&label) {
        let cur_url = wv
            .url()
            .ok()
            .map(|u| u.to_string())
            .unwrap_or_else(|| normalized_str.clone());
        let (tx, rx) = std::sync::mpsc::channel();
        trigger_dom_capture_with_completion(app.clone(), wv, tab_id.to_string(), cur_url, Some(tx));
        let _ = rx.recv_timeout(Duration::from_millis(1200));
    }

    Ok(normalized_str)
}
/// All other open tabs (including tabs suspended by the LRU cap) use their cached capture.
/// Waits on all receivers against one shared deadline of 800 ms total.
pub fn capture_open_tabs_for_conversation(
    app: &AppHandle,
    db: &DbState,
    wv_state: &WebviewManagerState,
    conversation_id: &str,
) -> Result<usize, String> {
    let detail = db
        .get_conversation(conversation_id)
        .map_err(|e| e.to_string())?;
    let open_tabs: Vec<_> = detail.tabs.into_iter().filter(|t| t.is_open).collect();
    if open_tabs.is_empty() {
        return Ok(0);
    }

    let visible_snapshot = wv_state.visible_tabs.lock().unwrap().clone();
    let cache_snapshot = wv_state.capture_cache.lock().unwrap().clone();

    let mut receivers = Vec::new();
    let mut pending_tabs = Vec::new();
    for tab in open_tabs {
        if tab.kind != "site" || tab.url.starts_with("satzmail://") {
            continue;
        }
        if !should_recapture_tab(&tab.id, &tab.url, &visible_snapshot, &cache_snapshot) {
            continue;
        }
        let label = tab_webview_label(&tab.id);
        if let Some(wv) = app.get_webview(&label) {
            let (tx, rx) = std::sync::mpsc::channel();
            trigger_dom_capture_with_completion(
                app.clone(),
                wv,
                tab.id.clone(),
                tab.url.clone(),
                Some(tx),
            );
            receivers.push(rx);
            pending_tabs.push((tab.id.clone(), tab.url.clone(), tab.title.clone()));
        }
    }

    let count = receivers.len();
    let deadline = Instant::now() + Duration::from_millis(800);
    for (idx, rx) in receivers.into_iter().enumerate() {
        let rem = deadline.saturating_duration_since(Instant::now());
        let completed_in_time = if rem.is_zero() {
            rx.try_recv().is_ok()
        } else {
            rx.recv_timeout(rem).is_ok()
        };
        if !completed_in_time {
            if let Some((tid, turl, ttitle)) = pending_tabs.get(idx) {
                post_ingest_to_sidecar(
                    app,
                    tid,
                    turl,
                    ttitle,
                    None,
                    None,
                    None,
                    None,
                    Some("timeout"),
                );
            }
        }
    }
    Ok(count)
}

fn decode_webview_json_value(raw_result: &str) -> Option<serde_json::Value> {
    serde_json::from_str::<String>(raw_result)
        .ok()
        .and_then(|inner| serde_json::from_str::<serde_json::Value>(&inner).ok())
        .or_else(|| serde_json::from_str::<serde_json::Value>(raw_result).ok())
}

fn eval_webview_script_string<R: tauri::Runtime>(
    webview: &tauri::Webview<R>,
    script: &str,
    timeout: Duration,
) -> Option<String> {
    let (tx, rx) = std::sync::mpsc::channel::<String>();

    #[cfg(windows)]
    {
        let script_owned = script.to_string();
        let tx_done = tx.clone();
        let res = webview.with_webview(move |platform_wv| unsafe {
            use webview2_com::ExecuteScriptCompletedHandler;
            use webview2_com::Microsoft::Web::WebView2::Win32::ICoreWebView2;
            use windows::core::PCWSTR;

            let controller = platform_wv.controller();
            if let Ok(core_wv) = controller.CoreWebView2() {
                let core_wv: ICoreWebView2 = core_wv;
                let mut js: Vec<u16> = script_owned.encode_utf16().collect();
                js.push(0);
                let tx_cb = tx_done.clone();
                let handler = ExecuteScriptCompletedHandler::create(Box::new(
                    move |_err_code, result_str: String| {
                        let _ = tx_cb.send(result_str);
                        Ok(())
                    },
                ));
                if core_wv.ExecuteScript(PCWSTR(js.as_ptr()), &handler).is_err() {
                    let _ = tx_done.send(String::new());
                }
            } else {
                let _ = tx_done.send(String::new());
            }
        });
        if res.is_err() {
            return None;
        }
    }

    #[cfg(target_os = "macos")]
    {
        let script_owned = script.to_string();
        let tx_done = tx.clone();
        let res = webview.with_webview(move |platform_wv| unsafe {
            use block2::RcBlock;
            use objc2::runtime::AnyObject;
            use objc2::AnyThread;
            use objc2_foundation::{
                NSError, NSJSONSerialization, NSJSONWritingOptions, NSString, NSUTF8StringEncoding,
            };
            use objc2_web_kit::WKWebView;

            let wk_ptr = platform_wv.inner() as *const WKWebView;
            if wk_ptr.is_null() {
                let _ = tx_done.send(String::new());
                return;
            }
            let wk_webview: &WKWebView = &*wk_ptr;
            let handler = RcBlock::new(move |val: *mut AnyObject, _err: *mut NSError| {
                let mut result_str = String::new();
                if !val.is_null() {
                    if let Ok(json_data) = NSJSONSerialization::dataWithJSONObject_options_error(
                        &*val,
                        NSJSONWritingOptions::FragmentsAllowed,
                    ) {
                        if let Some(json_ns_str) =
                            NSString::initWithData_encoding(NSString::alloc(), &json_data, NSUTF8StringEncoding)
                        {
                            result_str = json_ns_str.to_string();
                        }
                    }
                }
                let _ = tx_done.send(result_str);
            });
            wk_webview.evaluateJavaScript_completionHandler(
                &NSString::from_str(&script_owned),
                Some(&handler),
            );
        });
        if res.is_err() {
            return None;
        }
    }

    #[cfg(not(any(windows, target_os = "macos")))]
    {
        let _ = (webview, script, tx);
        return None;
    }

    rx.recv_timeout(timeout).ok().filter(|s| !s.is_empty())
}

fn build_unsubscribe_actor_js(click_allowed: bool, hint_selector: Option<&str>) -> String {
    let click_flag = if click_allowed { "true" } else { "false" };
    let hint_json = serde_json::to_string(hint_selector.unwrap_or("")).unwrap_or_else(|_| "\"\"".to_string());
    format!(
        r#"(() => {{
  try {{
    if (window.top !== window.self) {{
      return JSON.stringify({{ status: 'ignored_subframe' }});
    }}
    const url = String(location.href || '');
    const title = String(document.title || '');
    const rawBody = document.body ? (document.body.innerText || '') : '';
    const excerpt = rawBody.replace(/\s+/g, ' ').trim().slice(0, 1200);
    const lowBody = excerpt.toLowerCase();
    const hintSelector = String({hint_json} || '').trim();

    const _computeSelector = (node) => {{
      if (!node || node.nodeType !== 1) return '';
      if (node.id) return '#' + CSS.escape(String(node.id));
      const dtid = node.getAttribute && node.getAttribute('data-testid');
      if (dtid) return '[data-testid="' + String(dtid).replace(/"/g, '\\"') + '"]';
      const nm = node.getAttribute && node.getAttribute('name');
      if (nm) return (node.tagName || 'button').toLowerCase() + '[name="' + String(nm).replace(/"/g, '\\"') + '"]';
      const al = node.getAttribute && node.getAttribute('aria-label');
      if (al && al.length <= 64) return (node.tagName || 'button').toLowerCase() + '[aria-label="' + String(al).replace(/"/g, '\\"') + '"]';
      const clsList = Array.from(node.classList || []).filter(c => c && !/^(is-|active|focus|hover)/.test(c)).slice(0, 2);
      const tag = (node.tagName || 'button').toLowerCase();
      return clsList.length ? tag + '.' + clsList.map(c => CSS.escape(c)).join('.') : tag;
    }};

    const passEls = Array.from(document.querySelectorAll('input[type="password"]')).filter(el => el.offsetParent !== null);
    const hasCaptchaEl = Boolean(document.querySelector('iframe[src*="recaptcha" i], iframe[src*="hcaptcha" i], iframe[src*="challenges.cloudflare.com" i], .cf-turnstile, [data-sitekey]'));
    const hasCaptchaTxt = /(verify you are human|complete the captcha|i am not a robot)/i.test(lowBody);
    if (passEls.length > 0 || hasCaptchaEl || hasCaptchaTxt) {{
      return JSON.stringify({{
        status: 'needs_user',
        reason: passEls.length > 0 ? 'login_required' : 'captcha_required',
        url, title, excerpt
      }});
    }}

    const strongPosRe = /\b(unsubscribe|opt[\s-]?out|abmelden|abbestellen|austragen|ja,\s*abmelden|jetzt\s+abmelden|unsubscribe\s+from\s+all|alle\s+abbestellen)\b/i;
    const confirmPosRe = /\b(confirm|bestätigen|speichern|save(?:\s+preferences)?|submit|einstellungen\s+speichern|apply)\b/i;
    const negRe = /\b(resubscribe|subscribe\s+again|wieder\s+anmelden|keep\s+receiving|weiter\s+erhalten|stay\s+subscribed|cancel|abbrechen|zurück|back|anmelden|login|sign\s+in|buy|kaufen|checkout|pay|bestellen|delete\s+account|konto\s+löschen|privacy|datenschutz|impressum|cookie|akzeptieren)\b/i;
    const doneRe = /(you have been unsubscribed|successfully unsubscribed|you are (?:now )?unsubscribed|your e-?mail(?: address)? has been removed|opt[\s-]?out confirmed|erfolgreich abgemeldet|sie wurden(?: erfolgreich)? abgemeldet|abmeldung(?: war)? erfolgreich|abmeldung bestätigt|vom newsletter abgemeldet|erfolgreich ausgetragen|keine (?:weiteren )?(?:e-?mails|newsletter) mehr)/i;
    const pageHasUnsubCtx = strongPosRe.test(lowBody) || /(preferences|einstellungen|newsletter)/i.test(lowBody);

    let bestEl = null;
    let bestScore = -1;
    let bestLabel = '';

    if (hintSelector) {{
      try {{
        const hinted = document.querySelector(hintSelector);
        if (hinted && !hinted.disabled) {{
          const st = window.getComputedStyle(hinted);
          const lbl = String(hinted.innerText || hinted.value || hinted.getAttribute('aria-label') || hinted.getAttribute('title') || 'Confirm').replace(/\s+/g, ' ').trim();
          if ((!st || (st.display !== 'none' && st.visibility !== 'hidden')) && !negRe.test(lbl)) {{
            bestEl = hinted;
            bestScore = 25;
            bestLabel = lbl.slice(0, 90);
          }}
        }}
      }} catch (_) {{}}
    }}

    const candidates = Array.from(document.querySelectorAll('button, input[type="submit"], input[type="button"], a[href], [role="button"]'));

    if (!bestEl) for (const el of candidates) {{
      const style = window.getComputedStyle(el);
      if (style && (style.display === 'none' || style.visibility === 'hidden')) continue;
      if (el.disabled) continue;
      const rect = el.getBoundingClientRect ? el.getBoundingClientRect() : {{ width: 1, height: 1 }};
      if (rect.width === 0 && rect.height === 0 && el.offsetParent === null) continue;

      const labelTxt = String(el.innerText || el.value || el.getAttribute('aria-label') || el.getAttribute('title') || '').replace(/\s+/g, ' ').trim();
      if (!labelTxt || labelTxt.length > 90) continue;
      if (negRe.test(labelTxt)) continue;

      let sc = 0;
      if (strongPosRe.test(labelTxt)) {{
        sc += 15;
      }} else if (confirmPosRe.test(labelTxt) && pageHasUnsubCtx) {{
        sc += 8;
      }} else {{
        continue;
      }}

      const tag = (el.tagName || '').toLowerCase();
      if (tag === 'button' || (tag === 'input' && (el.type === 'submit' || el.type === 'button'))) sc += 5;
      if (el.getAttribute('role') === 'button') sc += 3;

      if (sc > bestScore) {{
        bestScore = sc;
        bestEl = el;
        bestLabel = labelTxt;
      }}
    }}

    if (doneRe.test(lowBody) && bestScore < 15) {{
      return JSON.stringify({{ status: 'already_unsubscribed', url, title, excerpt }});
    }}

    const matchedSelector = bestEl ? _computeSelector(bestEl) : '';

    if (!{click_flag}) {{
      return JSON.stringify({{
        status: bestEl ? 'needs_confirmation' : 'manual_review',
        candidate_label: bestLabel,
        matched_selector: matchedSelector,
        url, title, excerpt
      }});
    }}

    if (bestEl && bestScore >= 8) {{
      // If preference radios/checkboxes offer "unsubscribe from all" / "alle abbestellen", select first
      const toggleInputs = Array.from(document.querySelectorAll('input[type="radio"], input[type="checkbox"]'));
      for (const ti of toggleInputs) {{
        if (ti.checked) continue;
        const wrap = ti.closest('label') || ti.parentElement;
        const lblFor = ti.id ? document.querySelector('label[for="' + CSS.escape(ti.id) + '"]') : null;
        const tTxt = String((lblFor && lblFor.innerText) || (wrap && wrap.innerText) || ti.getAttribute('aria-label') || '').replace(/\s+/g, ' ').trim();
        if (/(unsubscribe from all|all emails|alle abbestellen|von allen abmelden|alle e-?mails|keine e-?mails)/i.test(tTxt)) {{
          ti.click();
          break;
        }}
      }}
      if (typeof bestEl.scrollIntoView === 'function') {{
        bestEl.scrollIntoView({{ block: 'center', behavior: 'instant' }});
      }}
      bestEl.click();
      return JSON.stringify({{
        status: 'clicked',
        clicked_label: bestLabel,
        matched_selector: matchedSelector,
        url, title, excerpt
      }});
    }}

    return JSON.stringify({{
      status: 'manual_review',
      candidate_label: bestLabel,
      matched_selector: matchedSelector,
      url, title, excerpt
    }});
  }} catch (e) {{
    return JSON.stringify({{ status: 'error', reason: String(e), url: String(location.href || '') }});
  }}
}})()"#
    )
}

pub fn run_tab_unsubscribe_actor_impl(
    app: &AppHandle,
    db: &DbState,
    wv_state: &WebviewManagerState,
    tab_id: &str,
    raw_url: &str,
    wait_ms: u64,
    hint_selector: Option<&str>,
) -> Result<serde_json::Value, String> {
    let url_before = navigate_and_capture_tab_impl(app, db, wv_state, tab_id, raw_url, wait_ms)?;
    let label = tab_webview_label(tab_id);
    let Some(wv) = app.get_webview(&label) else {
        return Ok(serde_json::json!({
            "ok": false,
            "status": "error",
            "reason": "Tab webview unavailable after navigation",
            "url": url_before
        }));
    };

    let act_script = build_unsubscribe_actor_js(true, hint_selector);
    let raw_step1 = eval_webview_script_string(&wv, &act_script, Duration::from_millis(3500))
        .unwrap_or_default();
    let parsed_step1 = decode_webview_json_value(&raw_step1).unwrap_or_else(|| {
        serde_json::json!({
            "status": "manual_review",
            "url": url_before,
            "excerpt": ""
        })
    });

    let step1_status = parsed_step1
        .get("status")
        .and_then(|v| v.as_str())
        .unwrap_or("manual_review")
        .to_string();
    let step1_selector = parsed_step1
        .get("matched_selector")
        .and_then(|v| v.as_str())
        .unwrap_or("")
        .to_string();

    if step1_status == "clicked" {
        std::thread::sleep(Duration::from_millis(1800));
        let verify_script = build_unsubscribe_actor_js(false, None);
        let raw_step2 = eval_webview_script_string(&wv, &verify_script, Duration::from_millis(3000))
            .unwrap_or_default();
        let parsed_step2 = decode_webview_json_value(&raw_step2);

        let cur_url = wv
            .url()
            .ok()
            .map(|u| u.to_string())
            .unwrap_or_else(|| url_before.clone());
        let (tx, rx) = std::sync::mpsc::channel();
        trigger_dom_capture_with_completion(app.clone(), wv, tab_id.to_string(), cur_url.clone(), Some(tx));
        let _ = rx.recv_timeout(Duration::from_millis(1200));

        let final_status = parsed_step2
            .as_ref()
            .and_then(|v| v.get("status"))
            .and_then(|v| v.as_str())
            .unwrap_or("clicked")
            .to_string();
        let final_url = parsed_step2
            .as_ref()
            .and_then(|v| v.get("url"))
            .and_then(|v| v.as_str())
            .unwrap_or(&cur_url)
            .to_string();
        let final_title = parsed_step2
            .as_ref()
            .and_then(|v| v.get("title"))
            .and_then(|v| v.as_str())
            .unwrap_or("")
            .to_string();
        let final_excerpt = parsed_step2
            .as_ref()
            .and_then(|v| v.get("excerpt"))
            .and_then(|v| v.as_str())
            .unwrap_or("")
            .to_string();

        return Ok(serde_json::json!({
            "ok": true,
            "status": "clicked",
            "clicked_label": parsed_step1.get("clicked_label").and_then(|v| v.as_str()).unwrap_or(""),
            "matched_selector": step1_selector,
            "url_before": url_before,
            "final_status": final_status,
            "url": final_url,
            "title": final_title,
            "excerpt": final_excerpt
        }));
    }

    Ok(serde_json::json!({
        "ok": true,
        "status": step1_status,
        "reason": parsed_step1.get("reason").and_then(|v| v.as_str()).unwrap_or(""),
        "candidate_label": parsed_step1.get("candidate_label").and_then(|v| v.as_str()).unwrap_or(""),
        "matched_selector": step1_selector,
        "url": parsed_step1.get("url").and_then(|v| v.as_str()).unwrap_or(&url_before),
        "title": parsed_step1.get("title").and_then(|v| v.as_str()).unwrap_or(""),
        "excerpt": parsed_step1.get("excerpt").and_then(|v| v.as_str()).unwrap_or("")
    }))
}

fn handle_captured_dom_json<R: tauri::Runtime>(
    app: &AppHandle<R>,
    tab_id: &str,
    fallback_url: &str,
    raw_result: &str,
) {
    // WebView2 ExecuteScript and macOS NSJSONSerialization with FragmentsAllowed return a JSON-encoded string literal;
    // also support a direct JSON object if a runtime returns an unquoted JSON string.
    let parsed_val: Option<serde_json::Value> = decode_webview_json_value(raw_result);

    if let Some(parsed) = parsed_val {
        if parsed.is_object() {
            let url = parsed
                .get("url")
                .and_then(|v| v.as_str())
                .unwrap_or(fallback_url);
            let title = parsed.get("title").and_then(|v| v.as_str()).unwrap_or("");
            let has_password_field = parsed
                .get("has_password_field")
                .and_then(|v| v.as_bool())
                .unwrap_or(false);
            let favicon_url = parsed
                .get("favicon_url")
                .and_then(|v| v.as_str())
                .map(|s| s.trim().to_string())
                .filter(|s| {
                    !s.is_empty()
                        && s.len() <= 262_144
                        && (s.starts_with("http://")
                            || s.starts_with("https://")
                            || s.starts_with("data:image/"))
                });
            let visible_text = parsed.get("visible_text").and_then(|v| v.as_str());
            let html = parsed.get("html").and_then(|v| v.as_str());
            let findings = parsed.get("findings").cloned();
            let elements = parsed.get("elements").cloned();

            if let Some(wv_state) = app.try_state::<WebviewManagerState>() {
                use std::collections::hash_map::DefaultHasher;
                use std::hash::{Hash, Hasher};
                let mut hasher = DefaultHasher::new();
                visible_text.unwrap_or("").hash(&mut hasher);
                html.unwrap_or("").hash(&mut hasher);
                let text_hash = hasher.finish();
                let captured_at = std::time::SystemTime::now()
                    .duration_since(std::time::UNIX_EPOCH)
                    .unwrap_or_default()
                    .as_secs();
                wv_state.capture_cache.lock().unwrap().insert(
                    tab_id.to_string(),
                    TabCaptureCacheEntry {
                        tab_id: tab_id.to_string(),
                        url: url.to_string(),
                        captured_at,
                        text_hash,
                    },
                );
                let snap = serde_json::json!({
                    "tab_id": tab_id,
                    "url": url,
                    "title": title,
                    "visible_text": visible_text.unwrap_or(""),
                    "findings": findings.clone().unwrap_or_else(|| serde_json::json!([])),
                    "elements": elements.clone().unwrap_or_else(|| serde_json::json!([])),
                    "captured_at": captured_at,
                });
                wv_state
                    .last_captures
                    .lock()
                    .unwrap()
                    .insert(tab_id.to_string(), snap);
            }

            if let Some(db) = app.try_state::<DbState>() {
                let url_opt = if url.is_empty() { None } else { Some(url) };
                let title_opt = if title.is_empty() { None } else { Some(title) };
                if url_opt.is_some() || title_opt.is_some() {
                    let _ = db.record_tab_navigation_or_title(tab_id, url_opt, title_opt);
                }
            }

            let _ = app.emit(
                "tab-page-event",
                TabPageEventPayload {
                    tab_id: tab_id.to_string(),
                    event_type: "dom_captured".to_string(),
                    url: Some(url.to_string()),
                    title: if title.is_empty() {
                        None
                    } else {
                        Some(title.to_string())
                    },
                    has_password_field: Some(has_password_field),
                    favicon_url,
                },
            );

            post_ingest_to_sidecar(
                app,
                tab_id,
                url,
                title,
                visible_text,
                html,
                findings,
                elements,
                Some("dom"),
            );
            return;
        }
    }
    post_ingest_to_sidecar(
        app,
        tab_id,
        fallback_url,
        "",
        None,
        None,
        None,
        None,
        Some("timeout"),
    );
}

#[allow(clippy::too_many_arguments)]
fn post_ingest_to_sidecar<R: tauri::Runtime>(
    app: &AppHandle<R>,
    tab_id: &str,
    url: &str,
    title: &str,
    visible_text: Option<&str>,
    html: Option<&str>,
    findings: Option<serde_json::Value>,
    elements: Option<serde_json::Value>,
    capture_mode: Option<&str>,
) {
    let source = if let Some(db) = app.try_state::<DbState>() {
        db.get_latest_source_for_tab(tab_id).ok().flatten()
    } else {
        None
    };

    let Some(src) = source else {
        return;
    };

    let capped_html = html.map(|h| truncate_utf8(h, 1_500_000));
    let capped_visible = visible_text.map(|v| truncate_utf8(v, 120_000));

    let captured_len = capped_visible
        .map(|v| v.len())
        .or_else(|| capped_html.map(|h| h.len()))
        .unwrap_or(0);

    if captured_len > 0 {
        if let Some(db) = app.try_state::<DbState>() {
            let _ = db.mark_source_captured(&src.id, captured_len);
        }
    }

    let payload = serde_json::json!({
        "conversation_id": src.conversation_id,
        "source_id": src.id,
        "url": if url.is_empty() { &src.url } else { url },
        "title": if title.is_empty() { &src.title } else { title },
        "visible_text": capped_visible,
        "html": capped_html,
        "findings": findings,
        "elements": elements,
        "capture_mode": capture_mode.unwrap_or("dom"),
    });

    let (port, token) = sidecar_port_and_token(app);
    let addr_str = format!("127.0.0.1:{}", port);
    let Ok(sock_addr) = addr_str.parse() else {
        return;
    };

    let body_bytes = payload.to_string().into_bytes();
    if let Ok(mut stream) = TcpStream::connect_timeout(&sock_addr, Duration::from_millis(800)) {
        let _ = stream.set_write_timeout(Some(Duration::from_secs(3)));
        let _ = stream.set_read_timeout(Some(Duration::from_secs(3)));
        let req = format!(
            "POST /ingest HTTP/1.1\r\nHost: 127.0.0.1:{}\r\nX-Satz-Token: {}\r\nContent-Type: application/json\r\nContent-Length: {}\r\nConnection: close\r\n\r\n",
            port,
            token,
            body_bytes.len()
        );
        let _ = stream.write_all(req.as_bytes());
        let _ = stream.write_all(&body_bytes);
        let mut resp = Vec::new();
        let _ = stream.read_to_end(&mut resp);
    }
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct TabActionPayload {
    #[serde(default)]
    pub expected_origin: String,
    #[serde(default)]
    pub eid: String,
    #[serde(default)]
    pub action_kind: String,
    #[serde(default)]
    pub value: String,
    #[serde(default)]
    pub element_label: String,
    #[serde(default)]
    pub selector_hint: Option<serde_json::Value>,
}

pub fn build_tab_action_js(action: &TabActionPayload) -> String {
    let orig_json = serde_json::to_string(&action.expected_origin).unwrap_or_else(|_| "\"\"".to_string());
    let eid_json = serde_json::to_string(&action.eid).unwrap_or_else(|_| "\"\"".to_string());
    let kind_json = serde_json::to_string(&action.action_kind).unwrap_or_else(|_| "\"click\"".to_string());
    let val_json = serde_json::to_string(&action.value).unwrap_or_else(|_| "\"\"".to_string());
    let lbl_json = serde_json::to_string(&action.element_label).unwrap_or_else(|_| "\"\"".to_string());
    let hint_json = serde_json::to_string(
        action
            .selector_hint
            .as_ref()
            .unwrap_or(&serde_json::Value::Null),
    )
    .unwrap_or_else(|_| "null".to_string());

    format!(
        r##"(() => {{
  try {{
    if (window.top !== window.self) {{
      return JSON.stringify({{ ok: false, status: 'ignored_subframe', error: 'Top-frame required.' }});
    }}
    const expectedOrigin = {orig_json};
    if (expectedOrigin && window.location.origin !== expectedOrigin) {{
      return JSON.stringify({{
        ok: false,
        status: 'origin_mismatch',
        error: 'Origin changed since action was proposed (' + window.location.origin + ' != ' + expectedOrigin + ').'
      }});
    }}
    const targetEid = {eid_json};
    const actionKind = String({kind_json} || 'click').toLowerCase();
    const targetValue = String({val_json} || '');
    const targetLabel = String({lbl_json} || '').trim();
    const hint = {hint_json};

    if (actionKind === 'scroll') {{
      const dy = targetValue === 'up' ? -520 : 520;
      window.scrollBy({{ top: dy, behavior: 'instant' }});
      return JSON.stringify({{
        ok: true,
        status: 'scrolled',
        action_kind: 'scroll',
        clicked_label: targetValue || 'down',
        url: String(location.href || ''),
        title: String(document.title || '')
      }});
    }}

    let el = null;
    if (targetEid) {{
      try {{
        el = document.querySelector('[data-satz-eid="' + CSS.escape(targetEid) + '"]');
      }} catch (_) {{}}
    }}
    if (!el && hint && typeof hint === 'object') {{
      if (hint.selector || hint.css) {{
        try {{ el = document.querySelector(String(hint.selector || hint.css)); }} catch (_) {{}}
      }}
      if (!el && hint.id) el = document.getElementById(String(hint.id));
      if (!el && hint.name) {{
        try {{ el = document.querySelector('[name="' + CSS.escape(String(hint.name)) + '"]'); }} catch (_) {{}}
      }}
      if (!el && hint.aria_label) {{
        try {{ el = document.querySelector('[aria-label="' + CSS.escape(String(hint.aria_label)) + '"]'); }} catch (_) {{}}
      }}
    }} else if (!el && typeof hint === 'string' && hint.trim()) {{
      try {{ el = document.querySelector(hint.trim()); }} catch (_) {{}}
    }}
    if (!el && targetLabel) {{
      const lowTarget = targetLabel.toLowerCase();
      const cands = Array.from(document.querySelectorAll('button, input, select, textarea, a[href], [role="button"], [role="tab"], [role="checkbox"], [role="radio"], [role="combobox"], [role="switch"]'));
      for (const c of cands) {{
        const cTxt = String(c.innerText || c.value || c.getAttribute('aria-label') || c.getAttribute('placeholder') || c.getAttribute('title') || '').replace(/\s+/g, ' ').trim().toLowerCase();
        if (cTxt && (cTxt === lowTarget || cTxt.includes(lowTarget))) {{
          el = c;
          break;
        }}
      }}
    }}
    if (!el) {{
      return JSON.stringify({{ ok: false, status: 'not_found', error: 'Target element not found on current page.' }});
    }}

    const tag = (el.tagName || '').toLowerCase();
    const tp = (el.type || '').toLowerCase();
    const ac = (el.getAttribute('autocomplete') || '').toLowerCase();
    if (tp === 'password' || /(current-password|new-password|cc-number|cc-csc)/i.test(ac)) {{
      return JSON.stringify({{ ok: false, status: 'blocked_sensitive', error: 'Password and payment credential fields cannot be targeted by tab actions.' }});
    }}
    if (el.disabled) {{
      return JSON.stringify({{ ok: false, status: 'disabled', error: 'Target element is disabled.' }});
    }}

    if (typeof el.scrollIntoView === 'function') {{
      el.scrollIntoView({{ block: 'center', behavior: 'instant' }});
    }}

    const usedLabel = String(el.innerText || el.value || el.getAttribute('aria-label') || el.getAttribute('placeholder') || targetLabel || targetEid).replace(/\s+/g, ' ').trim().slice(0, 80);
    const _computeSelector = (node) => {{
      if (!node || node.nodeType !== 1) return '';
      if (node.id) return '#' + CSS.escape(String(node.id));
      const dtid = node.getAttribute && node.getAttribute('data-testid');
      if (dtid) return '[data-testid="' + String(dtid).replace(/"/g, '\\"') + '"]';
      const nm = node.getAttribute && node.getAttribute('name');
      if (nm) return (node.tagName || 'button').toLowerCase() + '[name="' + String(nm).replace(/"/g, '\\"') + '"]';
      const al = node.getAttribute && node.getAttribute('aria-label');
      if (al && al.length <= 64) return (node.tagName || 'button').toLowerCase() + '[aria-label="' + String(al).replace(/"/g, '\\"') + '"]';
      const clsList = Array.from(node.classList || []).filter(c => c && !/^(is-|active|focus|hover)/.test(c)).slice(0, 2);
      const t = (node.tagName || 'button').toLowerCase();
      return clsList.length ? t + '.' + clsList.map(c => CSS.escape(c)).join('.') : t;
    }};
    const matchedSelector = _computeSelector(el);

    if (actionKind === 'fill' || actionKind === 'type' || actionKind === 'input') {{
      try {{ el.focus(); }} catch (_) {{}}
      const proto = tag === 'textarea' ? window.HTMLTextAreaElement.prototype : window.HTMLInputElement.prototype;
      const desc = Object.getOwnPropertyDescriptor(proto, 'value');
      if (desc && desc.set) {{ desc.set.call(el, targetValue); }} else {{ el.value = targetValue; }}
      el.dispatchEvent(new Event('input', {{ bubbles: true }}));
      el.dispatchEvent(new Event('change', {{ bubbles: true }}));
      return JSON.stringify({{
        ok: true,
        status: 'filled',
        action_kind: actionKind,
        clicked_label: usedLabel,
        matched_selector: matchedSelector,
        value_after: String(el.value || '').slice(0, 80),
        url: String(location.href || ''),
        title: String(document.title || '')
      }});
    }}

    if (actionKind === 'select' && tag === 'select') {{
      let matchedVal = '';
      const want = targetValue.toLowerCase();
      for (const opt of Array.from(el.options || [])) {{
        const ot = String(opt.text || '').trim().toLowerCase();
        const ov = String(opt.value || '').trim().toLowerCase();
        if (ov === want || ot === want || ot.includes(want)) {{
          matchedVal = opt.value;
          break;
        }}
      }}
      if (!matchedVal && el.options && el.options.length > 0 && want) {{
        return JSON.stringify({{ ok: false, status: 'option_not_found', error: 'Option "' + targetValue + '" not found in dropdown.' }});
      }}
      if (matchedVal) el.value = matchedVal;
      el.dispatchEvent(new Event('input', {{ bubbles: true }}));
      el.dispatchEvent(new Event('change', {{ bubbles: true }}));
      const selOpt = el.options && el.selectedIndex >= 0 ? el.options[el.selectedIndex] : null;
      return JSON.stringify({{
        ok: true,
        status: 'selected',
        action_kind: 'select',
        clicked_label: usedLabel,
        matched_selector: matchedSelector,
        value_after: selOpt ? String(selOpt.text || selOpt.value || '') : String(el.value || ''),
        url: String(location.href || ''),
        title: String(document.title || '')
      }});
    }}

    if (actionKind === 'check' || actionKind === 'uncheck' || actionKind === 'toggle') {{
      const isChecked = Boolean(el.checked || el.getAttribute('aria-checked') === 'true');
      const wantChecked = actionKind === 'check' ? true : (actionKind === 'uncheck' ? false : !isChecked);
      if (isChecked !== wantChecked) {{
        el.click();
      }}
      return JSON.stringify({{
        ok: true,
        status: wantChecked ? 'checked' : 'unchecked',
        action_kind: actionKind,
        clicked_label: usedLabel,
        matched_selector: matchedSelector,
        value_after: String(Boolean(el.checked || el.getAttribute('aria-checked') === 'true')),
        url: String(location.href || ''),
        title: String(document.title || '')
      }});
    }}

    el.click();
    return JSON.stringify({{
      ok: true,
      status: 'clicked',
      action_kind: 'click',
      clicked_label: usedLabel,
      matched_selector: matchedSelector,
      url: String(location.href || ''),
      title: String(document.title || '')
    }});
  }} catch (e) {{
    return JSON.stringify({{ ok: false, status: 'error', error: String(e), url: String(location.href || '') }});
  }}
}})()"##
    )
}

pub fn run_tab_action_impl(
    app: &AppHandle,
    db: &DbState,
    wv_state: &WebviewManagerState,
    tab_id: &str,
    action: &TabActionPayload,
) -> Result<serde_json::Value, String> {
    let label = tab_webview_label(tab_id);
    if app.get_webview(&label).is_none() {
        let tab_url = db
            .get_tab(tab_id)
            .map_err(|e| e.to_string())?
            .map(|t| t.url)
            .unwrap_or_default();
        if tab_url.starts_with("http://") || tab_url.starts_with("https://") {
            let _ = navigate_and_capture_tab_impl(app, db, wv_state, tab_id, &tab_url, 1800);
        }
    }

    let Some(wv) = app.get_webview(&label) else {
        return Ok(serde_json::json!({
            "ok": false,
            "status": "unavailable",
            "error": "Tab webview is not mounted."
        }));
    };

    let script = build_tab_action_js(action);
    let raw_res = eval_webview_script_string(&wv, &script, Duration::from_millis(3500))
        .unwrap_or_default();
    let parsed = decode_webview_json_value(&raw_res).unwrap_or_else(|| {
        serde_json::json!({
            "ok": false,
            "status": "error",
            "error": "WebView returned empty action result."
        })
    });

    let act_ok = parsed.get("ok").and_then(|v| v.as_bool()).unwrap_or(false);
    if act_ok {
        std::thread::sleep(Duration::from_millis(1300));
        let cur_url = wv.url().ok().map(|u| u.to_string()).unwrap_or_default();
        let (tx, rx) = std::sync::mpsc::channel();
        trigger_dom_capture_with_completion(app.clone(), wv, tab_id.to_string(), cur_url.clone(), Some(tx));
        let _ = rx.recv_timeout(Duration::from_millis(1200));

        let excerpt = wv_state
            .last_captures
            .lock()
            .unwrap()
            .get(tab_id)
            .and_then(|snap| snap.get("visible_text"))
            .and_then(|v| v.as_str())
            .unwrap_or("")
            .chars()
            .take(500)
            .collect::<String>();

        return Ok(serde_json::json!({
            "ok": true,
            "status": parsed.get("status").and_then(|v| v.as_str()).unwrap_or("ok"),
            "action_kind": parsed.get("action_kind").and_then(|v| v.as_str()).unwrap_or(&action.action_kind),
            "clicked_label": parsed.get("clicked_label").and_then(|v| v.as_str()).unwrap_or(&action.element_label),
            "matched_selector": parsed.get("matched_selector").and_then(|v| v.as_str()).unwrap_or(""),
            "value_after": parsed.get("value_after").and_then(|v| v.as_str()).unwrap_or(""),
            "url": parsed.get("url").and_then(|v| v.as_str()).unwrap_or(&cur_url),
            "title": parsed.get("title").and_then(|v| v.as_str()).unwrap_or(""),
            "excerpt": excerpt
        }));
    }

    Ok(parsed)
}

pub fn build_translate_extract_js() -> String {
    String::from(
        r##"(() => {
  try {
    if (window.top !== window.self) {
      return JSON.stringify({ ok: false, error: 'Top frame required.' });
    }
    const curUrl = String(location.href || '');
    const htmlLang = String(document.documentElement.getAttribute('lang') || '').trim();
    if (
      window.__satzTr &&
      window.__satzTr.url === curUrl &&
      Object.keys(window.__satzTr.blocks || {}).length > 0
    ) {
      return JSON.stringify({
        ok: true,
        already_extracted: true,
        showing_translated: Boolean(window.__satzTr.showingTranslated),
        has_cached_translation: Boolean(window.__satzTr.hasApplied),
        url: curUrl,
        title: String(window.__satzTr.origTitle || document.title || ''),
        html_lang: htmlLang,
        block_count: Object.keys(window.__satzTr.blocks).length,
        blocks: window.__satzTr.lastExtractedBlocks || []
      });
    }

    const SKIP_TAGS = new Set([
      'SCRIPT','STYLE','NOSCRIPT','SVG','MATH','CODE','PRE','KBD','SAMP',
      'CANVAS','VIDEO','AUDIO','TEXTAREA','IFRAME','OBJECT','EMBED','TIME'
    ]);
    const BLOCK_TAGS = new Set([
      'P','H1','H2','H3','H4','H5','H6','LI','TD','TH','DT','DD',
      'BLOCKQUOTE','FIGCAPTION','CAPTION','LABEL','BUTTON','SUMMARY',
      'LEGEND','OPTION','ARTICLE','SECTION','HEADER','FOOTER','MAIN',
      'ASIDE','NAV','DIV','UL','OL','TABLE','TR','THEAD','TBODY','DL','FORM'
    ]);

    function isSkippableNode(el) {
      if (!el || el.nodeType !== 1) return true;
      const tag = el.tagName ? el.tagName.toUpperCase() : '';
      if (SKIP_TAGS.has(tag)) return true;
      if (tag === 'INPUT') {
        const tp = String(el.type || 'text').toLowerCase();
        return !(tp === 'button' || tp === 'submit' || tp === 'reset');
      }
      if (el.getAttribute && (el.getAttribute('translate') === 'no' || el.isContentEditable)) return true;
      if (el.classList && (el.classList.contains('notranslate') || el.classList.contains('CodeMirror') || el.classList.contains('monaco-editor'))) return true;
      try {
        const st = getComputedStyle(el);
        if (st && (st.display === 'none' || st.visibility === 'hidden' || st.opacity === '0')) return true;
      } catch (_e) {}
      return false;
    }

    const store = {
      url: curUrl,
      origTitle: String(document.title || ''),
      showingTranslated: false,
      hasApplied: false,
      blocks: {},
      lastTranslations: {},
      lastExtractedBlocks: []
    };
    const seenTextNodes = new WeakSet();
    const collected = [];
    let seq = 0;

    function hasChildBlock(el) {
      for (const ch of el.children) {
        if (BLOCK_TAGS.has(ch.tagName.toUpperCase())) return true;
        if (hasChildBlock(ch)) return true;
      }
      return false;
    }

    function collectInlineTextNodes(el, list) {
      if (!el || isSkippableNode(el)) return;
      for (const child of el.childNodes) {
        if (child.nodeType === 3) {
          if (seenTextNodes.has(child)) continue;
          const v = String(child.nodeValue || '');
          if (v.trim()) list.push(child);
        } else if (child.nodeType === 1) {
          collectInlineTextNodes(child, list);
        }
      }
    }

    function extractLeafBlock(el) {
      if (!el || isSkippableNode(el)) return;
      if (hasChildBlock(el)) return;

      const origNodes = [];
      const outerNodes = [];
      const inlineSlots = [];
      let serialized = '';
      let inlineIdx = 0;

      for (const ch of el.childNodes) {
        if (ch.nodeType === 3) {
          if (seenTextNodes.has(ch)) continue;
          const raw = String(ch.nodeValue || '');
          if (!raw.trim()) continue;
          origNodes.push({ node: ch, orig: raw });
          outerNodes.push(ch);
          serialized += (serialized && !/\s$/.test(serialized) && !/^\s/.test(raw) ? ' ' : '') + raw.replace(/\s+/g, ' ').trim();
        } else if (ch.nodeType === 1 && !isSkippableNode(ch)) {
          const innerNodes = [];
          collectInlineTextNodes(ch, innerNodes);
          const innerText = innerNodes.map((n) => String(n.nodeValue || '').replace(/\s+/g, ' ').trim()).filter(Boolean).join(' ');
          if (!innerText) continue;
          innerNodes.forEach((n) => origNodes.push({ node: n, orig: String(n.nodeValue || '') }));
          const slotId = inlineIdx++;
          inlineSlots.push({ slotId, nodes: innerNodes });
          const sep = serialized && !/\s$/.test(serialized) ? ' ' : '';
          serialized += `${sep}[[${slotId}]]${innerText}[[/${slotId}]]`;
        }
      }

      const plainCheck = serialized.replace(/\[\[\/?\d+\]\]/g, '').trim();
      if (!plainCheck || plainCheck.length < 2 || !/[A-Za-z\u00C0-\u024F\u0400-\u04FF\u0600-\u06FF\u3040-\u9FFF\uAC00-\uD7AF\u0370-\u03FF\u0590-\u05FF\u0E00-\u0E7F]/.test(plainCheck)) {
        return;
      }

      origNodes.forEach((item) => seenTextNodes.add(item.node));
      const rect = el.getBoundingClientRect ? el.getBoundingClientRect() : { top: 0, bottom: 0 };
      const vh = window.innerHeight || 900;
      const bid = `b${seq++}`;
      store.blocks[bid] = {
        el,
        origNodes,
        outerNodes,
        inlineSlots,
        isPlaceholder: false
      };
      collected.push({
        id: bid,
        text: serialized.slice(0, 3600),
        viewport: rect.bottom >= 0 && rect.top <= vh
      });
    }

    const candidates = document.querySelectorAll(
      'h1,h2,h3,h4,h5,h6,p,li,td,th,dt,dd,blockquote,figcaption,caption,label,button,summary,legend,a,option,span,div'
    );
    for (const el of candidates) {
      extractLeafBlock(el);
    }

    // Safe placeholders on visible inputs (never reading input .value!)
    const inputs = document.querySelectorAll('input[placeholder], textarea[placeholder]');
    for (const inp of inputs) {
      if (isSkippableNode(inp)) continue;
      const ph = String(inp.getAttribute('placeholder') || '').trim();
      if (!ph || ph.length < 2) continue;
      const rect = inp.getBoundingClientRect ? inp.getBoundingClientRect() : { top: 0, bottom: 0 };
      const vh = window.innerHeight || 900;
      const bid = `b${seq++}`;
      store.blocks[bid] = { el: inp, origAttr: ph, isPlaceholder: true };
      collected.push({
        id: bid,
        text: ph.slice(0, 300),
        viewport: rect.bottom >= 0 && rect.top <= vh
      });
    }

    // Prioritize visible viewport items first and cap total extracted text safely
    collected.sort((a, b) => (a.viewport === b.viewport ? 0 : (a.viewport ? -1 : 1)));
    const finalBlocks = [];
    let charBudget = 0;
    for (const blk of collected) {
      if (finalBlocks.length >= 750 || charBudget + blk.text.length > 42000) break;
      finalBlocks.push(blk);
      charBudget += blk.text.length;
    }

    store.lastExtractedBlocks = finalBlocks;
    window.__satzTr = store;
    return JSON.stringify({
      ok: true,
      already_extracted: false,
      showing_translated: false,
      has_cached_translation: false,
      url: curUrl,
      title: store.origTitle,
      html_lang: htmlLang,
      block_count: finalBlocks.length,
      blocks: finalBlocks
    });
  } catch (e) {
    return JSON.stringify({ ok: false, error: String(e) });
  }
})()"##,
    )
}

pub fn build_translate_apply_js(mode: &str, segments: Option<&serde_json::Value>) -> String {
    let mode_json = serde_json::to_string(mode).unwrap_or_else(|_| "\"apply\"".to_string());
    let segs_json = segments
        .and_then(|v| serde_json::to_string(v).ok())
        .unwrap_or_else(|| "{}".to_string());

    let tpl = r##"(() => {
  try {
    if (window.top !== window.self) {
      return JSON.stringify({ ok: false, error: 'Top frame required.' });
    }
    const mode = __MODE__;
    const segments = __SEGMENTS__ || {};
    const store = window.__satzTr;
    if (!store) {
      return JSON.stringify({ ok: false, status: 'missing_state', showing_translated: false });
    }

    function applyBlockTranslation(bid, rawVal) {
      const trVal = String(rawVal || '').trim();
      if (!trVal) return false;
      if (bid === '__title__') {
        document.title = trVal;
        store.translatedTitle = trVal;
        return true;
      }
      const entry = store.blocks[bid];
      if (!entry) return false;
      if (entry.isPlaceholder) {
        if (entry.el && entry.el.setAttribute) entry.el.setAttribute('placeholder', trVal);
        return true;
      }

      const inlineSlots = entry.inlineSlots || [];
      if (inlineSlots.length === 0) {
        const nodes = entry.origNodes || [];
        if (nodes.length > 0 && nodes[0].node) {
          nodes[0].node.nodeValue = trVal;
          for (let i = 1; i < nodes.length; i++) {
            if (nodes[i].node) nodes[i].node.nodeValue = '';
          }
          return true;
        }
        return false;
      }

      // Match `[[n]]...[[/n]]` placeholders cleanly back to original inline elements
      const slotContents = {};
      const outerParts = [];
      const re = /\[\[(\d+)\]\]([\s\S]*?)\[\[\/\1\]\]/g;
      let lastIdx = 0;
      let m;
      while ((m = re.exec(trVal)) !== null) {
        outerParts.push(trVal.slice(lastIdx, m.index));
        slotContents[Number(m[1])] = m[2];
        lastIdx = m.index + m[0].length;
      }
      outerParts.push(trVal.slice(lastIdx));

      const matchedCount = Object.keys(slotContents).length;
      if (matchedCount > 0 && matchedCount <= inlineSlots.length) {
        for (const slot of inlineSlots) {
          const innerTxt = slotContents[slot.slotId];
          if (innerTxt !== undefined && slot.nodes && slot.nodes.length > 0) {
            slot.nodes[0].nodeValue = innerTxt;
            for (let j = 1; j < slot.nodes.length; j++) {
              slot.nodes[j].nodeValue = '';
            }
          }
        }
        const outerNodes = entry.outerNodes || [];
        if (outerNodes.length > 0) {
          for (let i = 0; i < outerNodes.length; i++) {
            if (i < outerParts.length - 1) {
              outerNodes[i].nodeValue = outerParts[i];
            } else if (i === outerNodes.length - 1) {
              outerNodes[i].nodeValue = outerParts.slice(i).join(' ');
            } else {
              outerNodes[i].nodeValue = '';
            }
          }
        }
        return true;
      }

      // Graceful fallback if markers were dropped/reordered incompatibly
      const cleanPlain = trVal.replace(/\[\[\/?\d+\]\]/g, '').replace(/\s+/g, ' ').trim();
      const nodes = entry.origNodes || [];
      if (nodes.length > 0 && nodes[0].node) {
        nodes[0].node.nodeValue = cleanPlain;
        for (let i = 1; i < nodes.length; i++) {
          if (nodes[i].node) nodes[i].node.nodeValue = '';
        }
        return true;
      }
      return false;
    }

    if (mode === 'restore') {
      document.title = store.origTitle || document.title;
      for (const bid of Object.keys(store.blocks || {})) {
        const entry = store.blocks[bid];
        if (!entry) continue;
        if (entry.isPlaceholder && entry.el && entry.el.setAttribute) {
          entry.el.setAttribute('placeholder', entry.origAttr || '');
        } else {
          for (const item of (entry.origNodes || [])) {
            if (item && item.node) item.node.nodeValue = item.orig;
          }
        }
      }
      store.showingTranslated = false;
      return JSON.stringify({ ok: true, status: 'restored', showing_translated: false });
    }

    if (mode === 'reapply') {
      let applied = 0;
      const cached = store.lastTranslations || {};
      for (const bid of Object.keys(cached)) {
        if (applyBlockTranslation(bid, cached[bid])) applied++;
      }
      store.showingTranslated = true;
      return JSON.stringify({ ok: true, status: 'reapplied', applied, showing_translated: true });
    }

    let applied = 0;
    for (const [bid, trVal] of Object.entries(segments)) {
      if (applyBlockTranslation(bid, trVal)) {
        store.lastTranslations[bid] = String(trVal || '');
        applied++;
      }
    }
    store.hasApplied = Object.keys(store.lastTranslations || {}).length > 0;
    store.showingTranslated = store.hasApplied;
    return JSON.stringify({ ok: true, status: 'applied', applied, showing_translated: store.showingTranslated });
  } catch (e) {
    return JSON.stringify({ ok: false, error: String(e) });
  }
})()"##;

    tpl.replace("__MODE__", &mode_json).replace("__SEGMENTS__", &segs_json)
}

pub fn extract_tab_translation_dom_impl(
    app: &AppHandle,
    db: &DbState,
    wv_state: &WebviewManagerState,
    tab_id: &str,
) -> Result<serde_json::Value, String> {
    let label = tab_webview_label(tab_id);
    if app.get_webview(&label).is_none() {
        let tab_url = db
            .get_tab(tab_id)
            .map_err(|e| e.to_string())?
            .map(|t| t.url)
            .unwrap_or_default();
        if tab_url.starts_with("http://") || tab_url.starts_with("https://") {
            let _ = navigate_and_capture_tab_impl(app, db, wv_state, tab_id, &tab_url, 1800);
        }
    }
    let Some(wv) = app.get_webview(&label) else {
        return Ok(serde_json::json!({
            "ok": false,
            "error": "Tab webview is not mounted."
        }));
    };
    let script = build_translate_extract_js();
    let raw_res = eval_webview_script_string(&wv, &script, Duration::from_millis(4000))
        .unwrap_or_default();
    Ok(decode_webview_json_value(&raw_res).unwrap_or_else(|| {
        serde_json::json!({
            "ok": false,
            "error": "WebView returned empty extraction result."
        })
    }))
}

pub fn apply_tab_translation_segments_impl(
    app: &AppHandle,
    tab_id: &str,
    mode: &str,
    segments: Option<&serde_json::Value>,
) -> Result<serde_json::Value, String> {
    let label = tab_webview_label(tab_id);
    let Some(wv) = app.get_webview(&label) else {
        return Ok(serde_json::json!({
            "ok": false,
            "error": "Tab webview is not mounted."
        }));
    };
    let script = build_translate_apply_js(mode, segments);
    let raw_res = eval_webview_script_string(&wv, &script, Duration::from_millis(4000))
        .unwrap_or_default();
    Ok(decode_webview_json_value(&raw_res).unwrap_or_else(|| {
        serde_json::json!({
            "ok": false,
            "error": "WebView returned empty apply result."
        })
    }))
}

fn constant_time_eq(a: &[u8], b: &[u8]) -> bool {
    if a.len() != b.len() {
        return false;
    }
    let mut diff: u8 = 0;
    for (x, y) in a.iter().zip(b.iter()) {
        diff |= x ^ y;
    }
    diff == 0
}

fn is_authorized_bridge_request(
    host_header: Option<&str>,
    token_header: Option<&str>,
    port: u16,
    expected_token: &str,
) -> bool {
    let Some(h) = host_header else {
        return false;
    };
    let h_low = h.trim().to_ascii_lowercase();
    let valid_host = h_low == format!("127.0.0.1:{}", port) || h_low == format!("localhost:{}", port);
    if !valid_host {
        return false;
    }
    let Some(tok) = token_header else {
        return false;
    };
    !expected_token.is_empty() && constant_time_eq(tok.trim().as_bytes(), expected_token.as_bytes())
}

fn write_bridge_json_response(stream: &mut TcpStream, status_code: u16, reason: &str, body: &serde_json::Value) {
    let body_bytes = body.to_string().into_bytes();
    let header = format!(
        "HTTP/1.1 {} {}\r\nContent-Type: application/json; charset=utf-8\r\nContent-Length: {}\r\nConnection: close\r\n\r\n",
        status_code,
        reason,
        body_bytes.len()
    );
    let _ = stream.write_all(header.as_bytes());
    let _ = stream.write_all(&body_bytes);
    let _ = stream.flush();
}

fn parse_query_param(query: &str, key: &str) -> String {
    for pair in query.split('&') {
        if let Some((k, v)) = pair.split_once('=') {
            if k == key {
                return v.replace('+', " ");
            }
        }
    }
    String::new()
}

fn handle_bridge_connection(app: AppHandle, mut stream: TcpStream, port: u16, expected_token: String) {
    let _ = stream.set_read_timeout(Some(Duration::from_secs(5)));
    let _ = stream.set_write_timeout(Some(Duration::from_secs(12)));

    let mut buf = Vec::with_capacity(4096);
    let mut chunk = [0u8; 2048];
    let mut header_end: Option<usize> = None;

    loop {
        match stream.read(&mut chunk) {
            Ok(0) => break,
            Ok(n) => {
                buf.extend_from_slice(&chunk[..n]);
                if let Some(pos) = buf.windows(4).position(|w| w == b"\r\n\r\n") {
                    header_end = Some(pos + 4);
                    break;
                }
                if buf.len() > 32 * 1024 {
                    write_bridge_json_response(&mut stream, 431, "Header Too Large", &serde_json::json!({"ok": false, "error": "headers too large"}));
                    return;
                }
            }
            Err(_) => return,
        }
    }

    let Some(hdr_end) = header_end else {
        return;
    };
    let (method, target, host_hdr, token_hdr, content_len) = {
        let hdr_str = String::from_utf8_lossy(&buf[..hdr_end]);
        let mut lines = hdr_str.lines();
        let req_line = lines.next().unwrap_or("");
        let mut parts = req_line.split_whitespace();
        let method = parts.next().unwrap_or("").to_string();
        let target = parts.next().unwrap_or("/").to_string();

        let mut host_hdr: Option<String> = None;
        let mut token_hdr: Option<String> = None;
        let mut content_len: usize = 0;
        for ln in lines {
            if let Some((k, v)) = ln.split_once(':') {
                let k_low = k.trim().to_ascii_lowercase();
                let v_val = v.trim().to_string();
                if k_low == "host" {
                    host_hdr = Some(v_val);
                } else if k_low == "x-satz-bridge-token" {
                    token_hdr = Some(v_val);
                } else if k_low == "content-length" {
                    content_len = v_val.parse::<usize>().unwrap_or(0).min(256 * 1024);
                }
            }
        }
        (method, target, host_hdr, token_hdr, content_len)
    };

    if !is_authorized_bridge_request(host_hdr.as_deref(), token_hdr.as_deref(), port, &expected_token) {
        write_bridge_json_response(&mut stream, 401, "Unauthorized", &serde_json::json!({"ok": false, "error": "unauthorized"}));
        return;
    }

    while buf.len() < hdr_end + content_len {
        match stream.read(&mut chunk) {
            Ok(0) => break,
            Ok(n) => buf.extend_from_slice(&chunk[..n]),
            Err(_) => break,
        }
    }
    let body_slice = &buf[hdr_end..buf.len().min(hdr_end + content_len)];
    let (route_path, query_str) = target.split_once('?').unwrap_or((&target, ""));

    if method == "GET" && route_path == "/tabs" {
        let cid = parse_query_param(query_str, "conversation_id");
        let db = app.state::<DbState>();
        let wv_state = app.state::<WebviewManagerState>();
        if cid.is_empty() {
            write_bridge_json_response(&mut stream, 400, "Bad Request", &serde_json::json!({"ok": false, "error": "conversation_id required"}));
            return;
        }
        match db.get_conversation(&cid) {
            Ok(detail) => {
                let visible_snap = wv_state.visible_tabs.lock().unwrap().clone();
                let urls_snap = wv_state.tab_urls.lock().unwrap().clone();
                let captures_snap = wv_state.last_captures.lock().unwrap().clone();
                let mut tabs_out = Vec::new();
                for t in detail.tabs.into_iter().filter(|t| t.is_open && t.kind != "compose" && t.url != "about:blank") {
                    let matched_src = detail
                        .sources
                        .iter()
                        .find(|s| s.tab_id.as_deref() == Some(&t.id) && s.in_context)
                        .or_else(|| detail.sources.iter().find(|s| s.tab_id.as_deref() == Some(&t.id)));
                    let live_url = urls_snap.get(&t.id).cloned().unwrap_or_else(|| t.url.clone());
                    let elem_count = captures_snap
                        .get(&t.id)
                        .and_then(|c| c.get("elements"))
                        .and_then(|e| e.as_array())
                        .map(|a| a.len())
                        .unwrap_or(0);
                    tabs_out.push(serde_json::json!({
                        "tab_id": t.id,
                        "source_id": matched_src.map(|s| s.id.clone()).unwrap_or_else(|| t.id.clone()),
                        "url": live_url,
                        "title": t.title,
                        "kind": t.kind,
                        "is_active": visible_snap.contains(&t.id),
                        "text_chars": matched_src.and_then(|s| s.text_chars).unwrap_or(0),
                        "interactive_count": elem_count,
                    }));
                }
                write_bridge_json_response(&mut stream, 200, "OK", &serde_json::json!({"ok": true, "tabs": tabs_out}));
            }
            Err(e) => {
                write_bridge_json_response(&mut stream, 404, "Not Found", &serde_json::json!({"ok": false, "error": e.to_string()}));
            }
        }
        return;
    }

    if method == "POST" && route_path == "/tab/open_and_capture" {
        let Ok(req_json) = serde_json::from_slice::<serde_json::Value>(body_slice) else {
            write_bridge_json_response(&mut stream, 400, "Bad Request", &serde_json::json!({"ok": false, "error": "invalid json"}));
            return;
        };
        let cid = req_json.get("conversation_id").and_then(|v| v.as_str()).unwrap_or("").trim().to_string();
        let raw_url = req_json.get("url").and_then(|v| v.as_str()).unwrap_or("").trim().to_string();
        let explicit_tid = req_json.get("tab_id").and_then(|v| v.as_str()).unwrap_or("").trim().to_string();
        let reuse_tab = req_json.get("reuse_tab").and_then(|v| v.as_bool()).unwrap_or(true);
        let wait_ms = req_json.get("wait_ms").and_then(|v| v.as_u64()).unwrap_or(2400);

        if cid.is_empty() || (!raw_url.starts_with("http://") && !raw_url.starts_with("https://")) {
            write_bridge_json_response(&mut stream, 400, "Bad Request", &serde_json::json!({"ok": false, "error": "conversation_id and http(s) url required"}));
            return;
        }

        let db = app.state::<DbState>();
        let wv_state = app.state::<WebviewManagerState>();

        let mut target_tab_id = String::new();
        if !explicit_tid.is_empty() {
            if let Ok(Some(t)) = db.get_tab(&explicit_tid) {
                if t.is_open && t.conversation_id == cid {
                    target_tab_id = t.id;
                }
            }
        }
        if target_tab_id.is_empty() && reuse_tab {
            let nav_cand = wv_state.navigator_tabs.lock().unwrap().get(&cid).cloned();
            if let Some(ntid) = nav_cand {
                if let Ok(Some(t)) = db.get_tab(&ntid) {
                    if t.is_open && t.conversation_id == cid {
                        target_tab_id = t.id;
                    }
                }
            }
        }
        if target_tab_id.is_empty() {
            match db.open_tab_with_kind(&cid, &raw_url, None, Some("site")) {
                Ok((tab, _src)) => {
                    target_tab_id = tab.id.clone();
                    if reuse_tab {
                        wv_state.navigator_tabs.lock().unwrap().insert(cid.clone(), tab.id);
                    }
                    let _ = app.emit("tab-list-updated", &cid);
                }
                Err(e) => {
                    write_bridge_json_response(&mut stream, 500, "Internal Error", &serde_json::json!({"ok": false, "error": e.to_string()}));
                    return;
                }
            }
        }

        match navigate_and_capture_tab_impl(&app, &db, &wv_state, &target_tab_id, &raw_url, wait_ms) {
            Ok(final_url) => {
                let _ = app.emit("tab-list-updated", &cid);
                let src_id = db
                    .get_latest_source_for_tab(&target_tab_id)
                    .ok()
                    .flatten()
                    .map(|s| s.id)
                    .unwrap_or_else(|| target_tab_id.clone());
                let snap = wv_state.last_captures.lock().unwrap().get(&target_tab_id).cloned();
                let (title, visible_text, findings, elements) = match snap {
                    Some(s) => (
                        s.get("title").and_then(|v| v.as_str()).unwrap_or("").to_string(),
                        s.get("visible_text").and_then(|v| v.as_str()).unwrap_or("").to_string(),
                        s.get("findings").cloned().unwrap_or_else(|| serde_json::json!([])),
                        s.get("elements").cloned().unwrap_or_else(|| serde_json::json!([])),
                    ),
                    None => (String::new(), String::new(), serde_json::json!([]), serde_json::json!([])),
                };
                write_bridge_json_response(
                    &mut stream,
                    200,
                    "OK",
                    &serde_json::json!({
                        "ok": true,
                        "tab_id": target_tab_id,
                        "source_id": src_id,
                        "url": final_url,
                        "title": title,
                        "visible_text": visible_text,
                        "findings": findings,
                        "elements": elements,
                        "capture_mode": "dom",
                    }),
                );
            }
            Err(e) => {
                write_bridge_json_response(&mut stream, 500, "Navigation Failed", &serde_json::json!({"ok": false, "error": e}));
            }
        }
        return;
    }

    if method == "POST" && route_path == "/tab/affordances" {
        let Ok(req_json) = serde_json::from_slice::<serde_json::Value>(body_slice) else {
            write_bridge_json_response(&mut stream, 400, "Bad Request", &serde_json::json!({"ok": false, "error": "invalid json"}));
            return;
        };
        let tab_id = req_json.get("tab_id").and_then(|v| v.as_str()).unwrap_or("").trim().to_string();
        if tab_id.is_empty() {
            write_bridge_json_response(&mut stream, 400, "Bad Request", &serde_json::json!({"ok": false, "error": "tab_id required"}));
            return;
        }
        let db = app.state::<DbState>();
        let wv_state = app.state::<WebviewManagerState>();
        let label = tab_webview_label(&tab_id);
        if app.get_webview(&label).is_none() {
            if let Ok(Some(t)) = db.get_tab(&tab_id) {
                if t.url.starts_with("http://") || t.url.starts_with("https://") {
                    let _ = navigate_and_capture_tab_impl(&app, &db, &wv_state, &tab_id, &t.url, 1800);
                }
            }
        }
        if let Some(wv) = app.get_webview(&label) {
            if let Some(raw_res) = eval_webview_script_string(&wv, dom_affordance_js(), Duration::from_millis(3000)) {
                if let Some(parsed) = decode_webview_json_value(&raw_res) {
                    let url = parsed.get("url").and_then(|v| v.as_str()).unwrap_or("").to_string();
                    let title = parsed.get("title").and_then(|v| v.as_str()).unwrap_or("").to_string();
                    let elements = parsed.get("elements").cloned().unwrap_or_else(|| serde_json::json!([]));
                    {
                        let mut caps = wv_state.last_captures.lock().unwrap();
                        if let Some(entry) = caps.get_mut(&tab_id).and_then(|v| v.as_object_mut()) {
                            entry.insert("elements".to_string(), elements.clone());
                        }
                    }
                    write_bridge_json_response(
                        &mut stream,
                        200,
                        "OK",
                        &serde_json::json!({
                            "ok": true,
                            "tab_id": tab_id,
                            "url": url,
                            "title": title,
                            "elements": elements
                        }),
                    );
                    return;
                }
            }
        }
        if let Some(snap) = wv_state.last_captures.lock().unwrap().get(&tab_id).cloned() {
            write_bridge_json_response(
                &mut stream,
                200,
                "OK",
                &serde_json::json!({
                    "ok": true,
                    "tab_id": tab_id,
                    "url": snap.get("url").and_then(|v| v.as_str()).unwrap_or(""),
                    "title": snap.get("title").and_then(|v| v.as_str()).unwrap_or(""),
                    "elements": snap.get("elements").cloned().unwrap_or_else(|| serde_json::json!([])),
                    "cached": true
                }),
            );
            return;
        }
        write_bridge_json_response(&mut stream, 404, "Not Found", &serde_json::json!({"ok": false, "error": "tab webview unavailable"}));
        return;
    }

    write_bridge_json_response(&mut stream, 404, "Not Found", &serde_json::json!({"ok": false, "error": "not found"}));
}

pub fn start_webview_bridge(app: AppHandle, bridge_token: String) -> Option<String> {
    let listener = std::net::TcpListener::bind("127.0.0.1:0").ok()?;
    let port = listener.local_addr().ok()?.port();
    let url = format!("http://127.0.0.1:{}", port);
    std::thread::spawn(move || {
        for stream_res in listener.incoming() {
            if let Ok(stream) = stream_res {
                let app_c = app.clone();
                let tok_c = bridge_token.clone();
                std::thread::spawn(move || {
                    handle_bridge_connection(app_c, stream, port, tok_c);
                });
            }
        }
    });
    Some(url)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_lru_cap_evicts_oldest_non_visible_tabs_at_8() {
        let max_cap = WebviewManagerState::default().max_live_tabs;
        assert_eq!(max_cap, 8);
        let base = Instant::now();
        let mut live: Vec<String> = Vec::new();
        let mut last_shown: HashMap<String, Instant> = HashMap::new();

        // Simulate opening 10 tabs sequentially with max_live_tabs = 8
        for i in 1..=10 {
            let tid = format!("t{}", i);
            let mut protected = HashSet::new();
            protected.insert(tid.clone());
            // Suppose t1 is also currently visible in split view
            protected.insert("t1".to_string());

            let evicted =
                select_lru_eviction_candidates(live.clone(), &last_shown, &protected, max_cap);
            for ev in evicted {
                live.retain(|x| x != &ev);
                last_shown.remove(&ev);
            }

            live.push(tid.clone());
            last_shown.insert(tid, base + Duration::from_secs(i));
            assert!(
                live.len() <= max_cap,
                "Live tab webviews ({}) exceeded cap ({})",
                live.len(),
                max_cap
            );
        }

        assert_eq!(live.len(), max_cap);
        // t1 was protected (visible), so t2 and t3 (oldest non-visible) must have been evicted
        assert!(live.contains(&"t1".to_string()));
        assert!(!live.contains(&"t2".to_string()));
        assert!(!live.contains(&"t3".to_string()));
        assert!(live.contains(&"t10".to_string()));
    }

    #[test]
    fn test_url_classification_10_cases() {
        let cases = [
            ("https://bbc.com", true),
            ("bbc.co.uk/news", true),
            ("localhost:3000", true),
            ("127.0.0.1:8010", true),
            ("?bbc.co.uk", false),
            ("what is happening in Greenland", false),
            ("github.com/feamando/sgs", true),
            ("rust async traits", false),
            ("dw.com", true),
            ("how does rust borrow checker work", false),
        ];
        for (input, expected_is_url) in cases {
            assert_eq!(
                is_likely_url_token(input),
                expected_is_url,
                "Failed URL classification for {:?}",
                input
            );
        }
    }

    #[test]
    fn test_capture_cache_and_shared_deadline() {
        let mut visible = HashSet::new();
        visible.insert("tab-1".to_string());

        let mut cache = HashMap::new();
        for i in 1..=8 {
            let tid = format!("tab-{}", i);
            cache.insert(
                tid.clone(),
                TabCaptureCacheEntry {
                    tab_id: tid,
                    url: format!("https://example.com/{}", i),
                    captured_at: 1_700_000_000,
                    text_hash: 12345,
                },
            );
        }

        // Visible tab-1 MUST be recaptured even when URL matches cache
        assert!(should_recapture_tab(
            "tab-1",
            "https://example.com/1",
            &visible,
            &cache
        ));

        // Non-visible tabs 2..7 whose URL matches cache MUST NOT be recaptured (use cache)
        for i in 2..=7 {
            assert!(!should_recapture_tab(
                &format!("tab-{}", i),
                &format!("https://example.com/{}", i),
                &visible,
                &cache
            ));
        }

        // Non-visible tab-8 whose URL changed since last capture MUST be recaptured
        assert!(should_recapture_tab(
            "tab-8",
            "https://example.com/8-new-page",
            &visible,
            &cache
        ));

        // Uncached tab-9 MUST be recaptured
        assert!(should_recapture_tab(
            "tab-9",
            "https://example.com/9",
            &visible,
            &cache
        ));

        // Shared 800 ms deadline across 8 hung receivers must complete in ~800 ms, not 8 * 1200 ms
        let mut rxs = Vec::new();
        let mut _txs = Vec::new();
        for _ in 0..8 {
            let (tx, rx) = std::sync::mpsc::channel::<()>();
            _txs.push(tx);
            rxs.push(rx);
        }
        let t0 = Instant::now();
        let completed = wait_for_receivers_with_shared_deadline(rxs, Duration::from_millis(800));
        let elapsed = t0.elapsed();
        assert_eq!(completed, 0);
        assert!(
            elapsed < Duration::from_millis(980),
            "Shared deadline took {:?}, expected ~800ms",
            elapsed
        );
    }

    #[test]
    fn test_child_webview_bounds_never_overlap_toolbar() {
        // 1. Single-tab on Windows (titlebar_inset = 0) and macOS (titlebar_inset = 28)
        let single_spec = TabBoundsSpec {
            tab_id: "t-single".to_string(),
            url: "https://example.com".to_string(),
            x: 220.0,
            y: 70.0,
            w: 940.0,
            h: 808.0,
            toolbar_bottom: Some(70.0),
            viewport_h: Some(900.0),
        };
        let (_wx, wy, _ww, wh) = compute_child_webview_bounds(&single_spec, 0.0);
        assert!(wy >= 70.0, "Windows child_y ({}) must be >= toolbar_bottom (70.0)", wy);
        assert_eq!(wh, 808.0);

        let (_mx, my, _mw, mh) = compute_child_webview_bounds(&single_spec, 28.0);
        // In macOS parent_view coordinates, titlebar is 0..28, tab strip is 28..62, toolbar is 62..98
        assert!(
            my >= 70.0 + 28.0,
            "macOS child_y ({}) must be >= toolbar_bottom + titlebar_inset (98.0)",
            my
        );
        assert_eq!(mh, 808.0);

        // 2. Even if a stale layout measurement passes y < toolbar_bottom (e.g. y = 42.0 while toolbar_bottom = 70.0),
        // compute_child_webview_bounds clamps y >= toolbar_bottom and shrinks height accordingly.
        let overlapping_spec = TabBoundsSpec {
            tab_id: "t-overlap".to_string(),
            url: "https://example.com".to_string(),
            x: 220.0,
            y: 42.0,
            w: 940.0,
            h: 800.0,
            toolbar_bottom: Some(70.0),
            viewport_h: Some(900.0),
        };
        let (_, cy_win, _, ch_win) = compute_child_webview_bounds(&overlapping_spec, 0.0);
        assert_eq!(cy_win, 70.0);
        assert_eq!(ch_win, 772.0);

        let (_, cy_mac, _, ch_mac) = compute_child_webview_bounds(&overlapping_spec, 28.0);
        assert_eq!(cy_mac, 98.0);
        assert_eq!(ch_mac, 772.0);

        // 3. Compare 2-up and 4-up (top row toolbar_bottom = 70, bottom row toolbar_bottom = 490)
        for (tb_bottom, slot_y, slot_h) in [(70.0, 70.0, 380.0), (490.0, 490.0, 380.0)] {
            let tile_spec = TabBoundsSpec {
                tab_id: "t-compare".to_string(),
                url: "https://example.com".to_string(),
                x: 220.0,
                y: slot_y,
                w: 470.0,
                h: slot_h,
                toolbar_bottom: Some(tb_bottom),
                viewport_h: Some(900.0),
            };
            let (_, y_w, _, _) = compute_child_webview_bounds(&tile_spec, 0.0);
            assert!(y_w >= tb_bottom);
            let (_, y_m, _, _) = compute_child_webview_bounds(&tile_spec, 28.0);
            assert!(y_m >= tb_bottom + 28.0);
        }

        // 4. Default browser user agent is non-empty and realistic
        let ua = default_browser_user_agent();
        assert!(ua.starts_with("Mozilla/5.0 ("));
        assert!(ua.contains("AppleWebKit/"));

        // 5. WebView JSON decoder & unsubscribe actor JS builder
        let decoded = decode_webview_json_value("\"{\\\"status\\\":\\\"clicked\\\",\\\"clicked_label\\\":\\\"Abmelden\\\"}\"").unwrap();
        assert_eq!(decoded.get("status").and_then(|v| v.as_str()), Some("clicked"));
        assert_eq!(decoded.get("clicked_label").and_then(|v| v.as_str()), Some("Abmelden"));
        let actor_js = build_unsubscribe_actor_js(true, Some("button#unsub"));
        assert!(actor_js.contains("unsubscribe") && actor_js.contains("abmelden"));
        assert!(actor_js.contains("matched_selector") && actor_js.contains("button#unsub"));

        // 6. Interactive affordance DOM map & gated tab action safety guards
        let affordance_js = dom_affordance_js();
        let capture_js = dom_capture_js();
        assert!(affordance_js.contains("data-satz-eid"));
        assert!(affordance_js.contains("current-password"));
        assert!(affordance_js.contains("cc-number"));
        assert!(capture_js.contains("elements"));

        let tab_act_js = build_tab_action_js(&TabActionPayload {
            expected_origin: "https://shop.example".to_string(),
            eid: "e4".to_string(),
            action_kind: "select".to_string(),
            value: "M".to_string(),
            element_label: "Size".to_string(),
            selector_hint: None,
        });
        assert!(tab_act_js.contains("https://shop.example"));
        assert!(tab_act_js.contains("origin_mismatch"));
        assert!(tab_act_js.contains("blocked_sensitive"));
        assert!(tab_act_js.contains("e4"));

        // 7. Loopback WebView bridge auth checks
        assert!(is_authorized_bridge_request(
            Some("127.0.0.1:41234"),
            Some("secret-tok"),
            41234,
            "secret-tok"
        ));
        assert!(!is_authorized_bridge_request(
            Some("evil.com:41234"),
            Some("secret-tok"),
            41234,
            "secret-tok"
        ));
        assert!(!is_authorized_bridge_request(
            Some("127.0.0.1:41234"),
            Some("wrong-tok"),
            41234,
            "secret-tok"
        ));
        assert!(!is_authorized_bridge_request(
            Some("127.0.0.1:41234"),
            None,
            41234,
            "secret-tok"
        ));

        // 8. Middle-click / Ctrl+Click background-open deduplication state
        let mgr_state = WebviewManagerState::default();
        assert!(
            !mgr_state.consume_bg_open_if_recent("tab-1", "https://example.com/a"),
            "Without a middle/mod gesture, new window defaults to foreground"
        );
        mgr_state.record_bg_open_gesture("tab-1");
        assert!(
            mgr_state.consume_bg_open_if_recent("tab-1", "https://example.com/b"),
            "Middle/mod gesture marks next new-window event as background tab"
        );
        assert!(
            !mgr_state.should_emit_aux_fallback("tab-1", "https://example.com/b"),
            "Aux fallback must not duplicate a tab already handled by on_new_window"
        );
        assert!(
            mgr_state.should_emit_aux_fallback("tab-2", "https://example.com/c"),
            "Aux fallback emits when native NewWindowRequested did not fire on another tab"
        );
        assert!(
            !mgr_state.should_emit_aux_fallback("tab-2", "https://example.com/c"),
            "Duplicate aux fallback on same tab within cooldown is suppressed"
        );
        assert!(child_tab_bg_open_script().contains("auxclick"));

        // 9. Website DOM translation extract + in-place patch/restore builders
        let extract_js = build_translate_extract_js();
        assert!(extract_js.contains("SKIP_TAGS"));
        assert!(extract_js.contains("notranslate"));
        assert!(extract_js.contains("origNodes"));
        assert!(extract_js.contains("[[${slotId}]]"));

        let apply_js = build_translate_apply_js(
            "apply",
            Some(&serde_json::json!({"__title__": "Translated Page", "b0": "Hallo [[0]]Welt[[/0]]"})),
        );
        assert!(apply_js.contains("Translated Page"));
        assert!(apply_js.contains("showingTranslated"));
        let restore_js = build_translate_apply_js("restore", None);
        assert!(restore_js.contains("origTitle"));
        assert!(restore_js.contains("\"restore\""));
    }
}
