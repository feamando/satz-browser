pub mod db;
pub mod webview_manager;

use db::{AttachedPage, Conversation, ConversationBundle, DbState, ThreadNote};
use tauri::{AppHandle, Manager, State};
use webview_manager::{
    control_pane_impl, hide_all_panes_impl, navigate_pane_impl, sync_panes_impl, PaneBoundsSpec,
    WebviewManagerState,
};

#[tauri::command]
fn list_conversations(db: State<'_, DbState>) -> Result<Vec<Conversation>, String> {
    db.list_conversations().map_err(|e| e.to_string())
}

#[tauri::command]
fn get_conversation_bundle(
    db: State<'_, DbState>,
    conversation_id: String,
) -> Result<ConversationBundle, String> {
    db.get_conversation_bundle(&conversation_id)
        .map_err(|e| e.to_string())
}

#[tauri::command]
fn create_conversation(
    db: State<'_, DbState>,
    intent_title: String,
    initial_url: Option<String>,
) -> Result<Conversation, String> {
    db.create_conversation(&intent_title, initial_url.as_deref())
        .map_err(|e| e.to_string())
}

#[tauri::command]
fn toggle_pin_conversation(
    db: State<'_, DbState>,
    conversation_id: String,
) -> Result<Conversation, String> {
    db.toggle_pin_conversation(&conversation_id)
        .map_err(|e| e.to_string())
}

#[tauri::command]
fn update_conversation_status(
    db: State<'_, DbState>,
    conversation_id: String,
    status: String,
) -> Result<Conversation, String> {
    db.update_conversation_status(&conversation_id, &status)
        .map_err(|e| e.to_string())
}

#[tauri::command]
fn delete_conversation(db: State<'_, DbState>, conversation_id: String) -> Result<(), String> {
    db.delete_conversation(&conversation_id)
        .map_err(|e| e.to_string())
}

#[tauri::command]
fn upsert_attached_page(
    db: State<'_, DbState>,
    conversation_id: String,
    pane_index: i32,
    url: String,
    title: String,
) -> Result<AttachedPage, String> {
    db.upsert_attached_page(&conversation_id, pane_index, &url, &title)
        .map_err(|e| e.to_string())
}

#[tauri::command]
fn add_thread_note(
    db: State<'_, DbState>,
    conversation_id: String,
    author: String,
    content: String,
) -> Result<ThreadNote, String> {
    db.add_thread_note(&conversation_id, &author, &content)
        .map_err(|e| e.to_string())
}

#[tauri::command]
fn get_db_path(db: State<'_, DbState>) -> String {
    db.db_path.to_string_lossy().to_string()
}

#[tauri::command]
async fn sync_child_panes(
    app: AppHandle,
    wv_state: State<'_, WebviewManagerState>,
    panes: Vec<PaneBoundsSpec>,
) -> Result<(), String> {
    sync_panes_impl(&app, &wv_state, panes)
}

#[tauri::command]
async fn navigate_child_pane(
    app: AppHandle,
    wv_state: State<'_, WebviewManagerState>,
    db: State<'_, DbState>,
    conversation_id: String,
    pane_index: usize,
    url: String,
    title: Option<String>,
) -> Result<AttachedPage, String> {
    let normalized = navigate_pane_impl(&app, &wv_state, pane_index, &url)?;
    let page_title = title.unwrap_or_else(|| normalized.clone());
    db.upsert_attached_page(&conversation_id, pane_index as i32, &normalized, &page_title)
        .map_err(|e| e.to_string())
}

#[tauri::command]
async fn control_child_pane(
    app: AppHandle,
    pane_index: usize,
    action: String,
) -> Result<(), String> {
    control_pane_impl(&app, pane_index, &action)
}

#[tauri::command]
async fn hide_all_child_panes(app: AppHandle) -> Result<(), String> {
    hide_all_panes_impl(&app)
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .setup(|app| {
            let app_data_dir = app
                .path()
                .app_data_dir()
                .unwrap_or_else(|_| std::env::temp_dir().join("satz-browser"));
            let db_path = app_data_dir.join("satz.db");
            let db_state =
                DbState::init(db_path).expect("Failed to initialize local SQLite database");

            app.manage(db_state);
            app.manage(WebviewManagerState::default());

            if let Some(main_window) = app.get_window("main") {
                let _ = main_window.show();
                let _ = main_window.unminimize();
                let _ = main_window.set_focus();
            }
            Ok(())
        })
        .invoke_handler(tauri::generate_handler![
            list_conversations,
            get_conversation_bundle,
            create_conversation,
            toggle_pin_conversation,
            update_conversation_status,
            delete_conversation,
            upsert_attached_page,
            add_thread_note,
            get_db_path,
            sync_child_panes,
            navigate_child_pane,
            control_child_pane,
            hide_all_child_panes,
        ])
        .run(tauri::generate_context!())
        .expect("error while running Satz Browser application");
}
