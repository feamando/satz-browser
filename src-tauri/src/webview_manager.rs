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
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct TabPageEventPayload {
    pub tab_id: String,
    pub event_type: String,
    pub url: Option<String>,
    pub title: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub has_password_field: Option<bool>,
}

pub struct WebviewManagerState {
    pub max_live_tabs: usize,
    pub tab_urls: Mutex<HashMap<String, String>>,
    pub last_shown: Mutex<HashMap<String, Instant>>,
    pub visible_tabs: Mutex<HashSet<String>>,
}

impl Default for WebviewManagerState {
    fn default() -> Self {
        Self {
            max_live_tabs: 8,
            tab_urls: Mutex::new(HashMap::new()),
            last_shown: Mutex::new(HashMap::new()),
            visible_tabs: Mutex::new(HashSet::new()),
        }
    }
}

pub fn is_likely_url_token(raw: &str) -> bool {
    let t = raw.trim();
    if t.is_empty() || t.contains(' ') || t.starts_with('?') {
        return false;
    }
    if t.starts_with("http://") || t.starts_with("https://") || t.starts_with("about:") {
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

    for spec in visible {
        if spec.w < 10.0 || spec.h < 10.0 {
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
                position: LogicalPosition::new(spec.x, spec.y).into(),
                size: LogicalSize::new(spec.w, spec.h).into(),
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

            let tid_load = spec.tab_id.clone();
            let tid_title = spec.tab_id.clone();
            let app_load = app.clone();
            let app_title = app.clone();

            let builder = WebviewBuilder::new(&label, WebviewUrl::External(parsed_url))
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
                        trigger_dom_capture_and_ingest(
                            app_load.clone(),
                            wv.clone(),
                            tid_load.clone(),
                            url_str.clone(),
                        );
                        // Second delayed capture for SPAs (e.g. Gmail, Notion, dashboards) that render asynchronously after load
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

                    let _ = app_load.emit(
                        "tab-page-event",
                        TabPageEventPayload {
                            tab_id: tid_load.clone(),
                            event_type: ev_type.to_string(),
                            url: Some(url_str),
                            title: None,
                            has_password_field: None,
                        },
                    );
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
                    // SPAs (like Gmail opening an email or finishing inbox load) update document.title on in-page navigation
                    trigger_dom_capture_and_ingest(
                        app_title.clone(),
                        wv.clone(),
                        tid_title.clone(),
                        current_url.clone().unwrap_or_default(),
                    );
                    let _ = app_title.emit(
                        "tab-page-event",
                        TabPageEventPayload {
                            tab_id: tid_title.clone(),
                            event_type: "title_changed".to_string(),
                            url: current_url,
                            title: Some(title),
                            has_password_field: None,
                        },
                    );
                });

            let child_wv = window
                .add_child(
                    builder,
                    LogicalPosition::new(spec.x, spec.y),
                    LogicalSize::new(spec.w, spec.h),
                )
                .map_err(|e| format!("failed to add child webview {}: {}", label, e))?;

            #[cfg(windows)]
            attach_child_webview_accelerators(app.clone(), &child_wv);

            let _ = child_wv.show();
        }
    }

    Ok(())
}

#[cfg(windows)]
fn attach_child_webview_accelerators(app: AppHandle, child_wv: &tauri::Webview) {
    let _ = child_wv.with_webview(move |platform_wv| {
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
                                    (0x4E, false) => Some("new_conversation"),     // Ctrl+N
                                    (0x4B, false) => Some("filter_conversations"), // Ctrl+K
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
                                    let _ = app.emit("menu-shortcut", action);
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

const DOM_CAPTURE_JS: &str = r#"(() => {
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
    return JSON.stringify({
      url: location.href,
      title: document.title,
      has_password_field: hasVisiblePass,
      visible_text: parts.join('\n\n').slice(0, 120000),
      html: document.documentElement ? document.documentElement.outerHTML.slice(0, 1500000) : ''
    });
  } catch (e) {
    return JSON.stringify({
      url: location.href,
      title: document.title,
      has_password_field: false,
      visible_text: document.body ? (document.body.innerText || '').slice(0, 100000) : '',
      html: ''
    });
  }
})()"#;

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
                let mut js: Vec<u16> = DOM_CAPTURE_JS.encode_utf16().collect();
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

    #[cfg(not(windows))]
    {
        let _ = webview;
        std::thread::spawn(move || {
            post_ingest_to_sidecar(&app, &tab_id, &fallback_url, "", None, None);
            if let Some(tx) = done_tx {
                let _ = tx.send(());
            }
        });
    }
}

/// Synchronously captures all currently open live WebView2 tabs for `conversation_id`
/// right before a chat or reader request so SPA state, opened emails, and selections are fresh.
pub fn capture_open_tabs_for_conversation(
    app: &AppHandle,
    db: &DbState,
    conversation_id: &str,
) -> Result<usize, String> {
    let detail = db
        .get_conversation(conversation_id)
        .map_err(|e| e.to_string())?;
    let open_tabs: Vec<_> = detail.tabs.into_iter().filter(|t| t.is_open).collect();
    if open_tabs.is_empty() {
        return Ok(0);
    }

    let mut receivers = Vec::new();
    for tab in open_tabs {
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
        }
    }

    let count = receivers.len();
    for rx in receivers {
        let _ = rx.recv_timeout(Duration::from_millis(1200));
    }
    Ok(count)
}

fn handle_captured_dom_json<R: tauri::Runtime>(
    app: &AppHandle<R>,
    tab_id: &str,
    fallback_url: &str,
    raw_result: &str,
) {
    // WebView2 ExecuteScript returns a JSON-encoded string literal
    let inner_json: Option<String> = serde_json::from_str(raw_result).ok();
    if let Some(json_str) = inner_json {
        if let Ok(parsed) = serde_json::from_str::<serde_json::Value>(&json_str) {
            let url = parsed
                .get("url")
                .and_then(|v| v.as_str())
                .unwrap_or(fallback_url);
            let title = parsed.get("title").and_then(|v| v.as_str()).unwrap_or("");
            let has_password_field = parsed
                .get("has_password_field")
                .and_then(|v| v.as_bool())
                .unwrap_or(false);
            let visible_text = parsed.get("visible_text").and_then(|v| v.as_str());
            let html = parsed.get("html").and_then(|v| v.as_str());

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
                },
            );

            post_ingest_to_sidecar(app, tab_id, url, title, visible_text, html);
            return;
        }
    }
    post_ingest_to_sidecar(app, tab_id, fallback_url, "", None, None);
}

fn post_ingest_to_sidecar<R: tauri::Runtime>(
    app: &AppHandle<R>,
    tab_id: &str,
    url: &str,
    title: &str,
    visible_text: Option<&str>,
    html: Option<&str>,
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
}
