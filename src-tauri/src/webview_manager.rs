use serde::{Deserialize, Serialize};
use std::collections::HashMap;
use std::sync::Mutex;
use tauri::{
    webview::{PageLoadEvent, WebviewBuilder},
    AppHandle, Emitter, LogicalPosition, LogicalSize, Manager, Rect, WebviewUrl,
};
use url::Url;

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct PaneBoundsSpec {
    pub pane_index: usize,
    pub url: String,
    pub x: f64,
    pub y: f64,
    pub width: f64,
    pub height: f64,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ChildPaneEventPayload {
    pub pane_index: usize,
    pub event_type: String,
    pub url: Option<String>,
    pub title: Option<String>,
}

#[derive(Default)]
pub struct WebviewManagerState {
    /// Tracks the last explicitly assigned URL per pane_index so we only re-navigate when the URL changes.
    pub pane_urls: Mutex<HashMap<usize, String>>,
}

pub fn normalize_url(raw: &str) -> Result<Url, String> {
    let trimmed = raw.trim();
    if trimmed.is_empty() {
        return Url::parse("https://en.wikipedia.org/wiki/Main_Page").map_err(|e| e.to_string());
    }
    if trimmed.starts_with("http://")
        || trimmed.starts_with("https://")
        || trimmed.starts_with("about:")
    {
        Url::parse(trimmed).map_err(|e| e.to_string())
    } else if trimmed.contains('.') && !trimmed.contains(' ') {
        Url::parse(&format!("https://{}", trimmed)).map_err(|e| e.to_string())
    } else {
        let encoded = trimmed.replace(' ', "+");
        Url::parse(&format!("https://duckduckgo.com/?q={}", encoded)).map_err(|e| e.to_string())
    }
}

pub fn pane_label(pane_index: usize) -> String {
    format!("pane-{}", pane_index)
}

pub fn sync_panes_impl(
    app: &AppHandle,
    state: &WebviewManagerState,
    specs: Vec<PaneBoundsSpec>,
) -> Result<(), String> {
    let active_indices: std::collections::HashSet<usize> =
        specs.iter().map(|s| s.pane_index).collect();

    // Hide any child webviews (0..4) not currently active
    for idx in 0..4 {
        if !active_indices.contains(&idx) {
            let label = pane_label(idx);
            if let Some(wv) = app.get_webview(&label) {
                let _ = wv.hide();
            }
        }
    }

    let window = app
        .get_window("main")
        .ok_or_else(|| "Main window not found".to_string())?;

    for spec in specs {
        if spec.pane_index >= 4 || spec.width < 10.0 || spec.height < 10.0 {
            continue;
        }

        let parsed_url = normalize_url(&spec.url)?;
        let normalized_str = parsed_url.to_string();
        let label = pane_label(spec.pane_index);

        let should_navigate = {
            let mut map = state.pane_urls.lock().unwrap();
            let prev = map.get(&spec.pane_index).cloned();
            if prev.as_deref() != Some(normalized_str.as_str()) {
                map.insert(spec.pane_index, normalized_str.clone());
                true
            } else {
                false
            }
        };

        if let Some(existing_wv) = app.get_webview(&label) {
            let _ = existing_wv.set_bounds(Rect {
                position: LogicalPosition::new(spec.x, spec.y).into(),
                size: LogicalSize::new(spec.width, spec.height).into(),
            });
            if should_navigate {
                let _ = existing_wv.navigate(parsed_url);
            }
            let _ = existing_wv.show();
        } else {
            let pane_idx = spec.pane_index;
            let app_for_load = app.clone();
            let app_for_title = app.clone();

            let builder = WebviewBuilder::new(&label, WebviewUrl::External(parsed_url))
                .on_page_load(move |_wv, payload| {
                    let ev_type = match payload.event() {
                        PageLoadEvent::Started => "load_started",
                        PageLoadEvent::Finished => "load_finished",
                    };
                    let _ = app_for_load.emit(
                        "child-pane-event",
                        ChildPaneEventPayload {
                            pane_index: pane_idx,
                            event_type: ev_type.to_string(),
                            url: Some(payload.url().to_string()),
                            title: None,
                        },
                    );
                })
                .on_document_title_changed(move |wv, title| {
                    let current_url = wv.url().ok().map(|u| u.to_string());
                    let _ = app_for_title.emit(
                        "child-pane-event",
                        ChildPaneEventPayload {
                            pane_index: pane_idx,
                            event_type: "title_changed".to_string(),
                            url: current_url,
                            title: Some(title),
                        },
                    );
                });

            let child_wv = window
                .add_child(
                    builder,
                    LogicalPosition::new(spec.x, spec.y),
                    LogicalSize::new(spec.width, spec.height),
                )
                .map_err(|e| format!("Failed to add child WebView2 {}: {}", label, e))?;

            let _ = child_wv.show();
        }
    }

    Ok(())
}

pub fn navigate_pane_impl(
    app: &AppHandle,
    state: &WebviewManagerState,
    pane_index: usize,
    raw_url: &str,
) -> Result<String, String> {
    let parsed_url = normalize_url(raw_url)?;
    let normalized_str = parsed_url.to_string();
    {
        let mut map = state.pane_urls.lock().unwrap();
        map.insert(pane_index, normalized_str.clone());
    }
    let label = pane_label(pane_index);
    if let Some(wv) = app.get_webview(&label) {
        wv.navigate(parsed_url).map_err(|e| e.to_string())?;
    }
    Ok(normalized_str)
}

pub fn control_pane_impl(app: &AppHandle, pane_index: usize, action: &str) -> Result<(), String> {
    let label = pane_label(pane_index);
    if let Some(wv) = app.get_webview(&label) {
        match action {
            "back" => wv
                .eval("window.history.back();")
                .map_err(|e| e.to_string())?,
            "forward" => wv
                .eval("window.history.forward();")
                .map_err(|e| e.to_string())?,
            "reload" => wv.reload().map_err(|e| e.to_string())?,
            _ => return Err(format!("Unknown pane action: {}", action)),
        }
    }
    Ok(())
}

pub fn hide_all_panes_impl(app: &AppHandle) -> Result<(), String> {
    for idx in 0..4 {
        let label = pane_label(idx);
        if let Some(wv) = app.get_webview(&label) {
            let _ = wv.hide();
        }
    }
    Ok(())
}
