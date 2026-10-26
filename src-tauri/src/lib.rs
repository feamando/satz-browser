pub mod db;
pub mod webview_manager;

use db::{
    BookmarkItem, BrowserTab, ChatMessage, Conversation, ConversationDetail, DbState,
};
use serde::{Deserialize, Serialize};
use std::path::PathBuf;
use std::process::{Child, Command, Stdio};
use std::sync::Mutex;
#[cfg(target_os = "macos")]
use tauri::{
    menu::{MenuBuilder, MenuItemBuilder, SubmenuBuilder},
    Emitter,
};
use tauri::{AppHandle, Manager, RunEvent, State};
use webview_manager::{
    autofill_tab_credentials_impl, capture_open_tabs_for_conversation, close_tab_webview,
    control_tab_webview_impl, navigate_tab_webview_impl, sync_tab_webviews_impl, TabBoundsSpec,
    WebviewManagerState,
};

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SatzSettings {
    pub sgs_root: String,
    pub python: String,
    pub gemma_path: String,
    pub port: u16,
    pub max_live_tabs: usize,
}

impl Default for SatzSettings {
    fn default() -> Self {
        Self {
            sgs_root: "..\\sgs".to_string(),
            python: "..\\sgs\\.venv\\Scripts\\python.exe".to_string(),
            gemma_path: "models/gemma-4-e4b-it".to_string(),
            port: 8020,
            max_live_tabs: 8,
        }
    }
}

pub struct SidecarState {
    pub child: Mutex<Option<Child>>,
    pub settings: SatzSettings,
}

#[tauri::command]
fn list_conversations(db: State<'_, DbState>) -> Result<Vec<Conversation>, String> {
    db.list_conversations().map_err(|e| e.to_string())
}

#[tauri::command]
fn get_conversation(
    db: State<'_, DbState>,
    conversation_id: String,
) -> Result<ConversationDetail, String> {
    db.get_conversation(&conversation_id)
        .map_err(|e| e.to_string())
}

#[tauri::command]
fn get_conversation_bundle(
    db: State<'_, DbState>,
    conversation_id: String,
) -> Result<ConversationDetail, String> {
    db.get_conversation(&conversation_id)
        .map_err(|e| e.to_string())
}

#[tauri::command]
fn create_conversation(
    db: State<'_, DbState>,
    title: String,
    origin: Option<String>,
) -> Result<Conversation, String> {
    db.create_conversation(&title, origin.as_deref().unwrap_or("chat"))
        .map_err(|e| e.to_string())
}

#[tauri::command]
fn rename_conversation(
    db: State<'_, DbState>,
    conversation_id: String,
    title: String,
) -> Result<Conversation, String> {
    db.rename_conversation(&conversation_id, &title)
        .map_err(|e| e.to_string())
}

#[tauri::command]
fn pin_conversation(
    db: State<'_, DbState>,
    conversation_id: String,
) -> Result<Conversation, String> {
    db.pin_conversation(&conversation_id)
        .map_err(|e| e.to_string())
}

#[tauri::command]
fn toggle_pin_conversation(
    db: State<'_, DbState>,
    conversation_id: String,
) -> Result<Conversation, String> {
    db.pin_conversation(&conversation_id)
        .map_err(|e| e.to_string())
}

#[tauri::command]
fn archive_conversation(
    db: State<'_, DbState>,
    conversation_id: String,
    archived: bool,
) -> Result<Conversation, String> {
    db.archive_conversation(&conversation_id, archived)
        .map_err(|e| e.to_string())
}

#[tauri::command]
fn delete_conversation(
    app: AppHandle,
    db: State<'_, DbState>,
    wv_state: State<'_, WebviewManagerState>,
    conversation_id: String,
) -> Result<(), String> {
    if let Ok(detail) = db.get_conversation(&conversation_id) {
        for tab in detail.tabs {
            close_tab_webview(&app, &wv_state, &tab.id);
        }
    }
    db.delete_conversation(&conversation_id)
        .map_err(|e| e.to_string())
}

#[tauri::command]
fn open_tab(
    db: State<'_, DbState>,
    conversation_id: String,
    url: String,
    title: Option<String>,
) -> Result<BrowserTab, String> {
    let (tab, _src) = db
        .open_tab(&conversation_id, &url, title.as_deref())
        .map_err(|e| e.to_string())?;
    Ok(tab)
}

#[tauri::command]
async fn close_tab(
    app: AppHandle,
    db: State<'_, DbState>,
    wv_state: State<'_, WebviewManagerState>,
    tab_id: String,
) -> Result<(), String> {
    close_tab_webview(&app, &wv_state, &tab_id);
    db.close_tab(&tab_id).map_err(|e| e.to_string())?;
    Ok(())
}

#[tauri::command]
fn reorder_tabs(
    db: State<'_, DbState>,
    conversation_id: String,
    tab_ids: Vec<String>,
) -> Result<(), String> {
    db.reorder_tabs(&conversation_id, &tab_ids)
        .map_err(|e| e.to_string())
}

#[tauri::command]
async fn navigate_tab(
    app: AppHandle,
    wv_state: State<'_, WebviewManagerState>,
    db: State<'_, DbState>,
    tab_id: String,
    url: String,
) -> Result<BrowserTab, String> {
    let normalized = navigate_tab_webview_impl(&app, &wv_state, &tab_id, &url)?;
    let res = db
        .record_tab_navigation_or_title(&tab_id, Some(&normalized), None)
        .map_err(|e| e.to_string())?;
    res.map(|(tab, _)| tab)
        .ok_or_else(|| "tab not found".to_string())
}

#[tauri::command]
async fn control_tab(app: AppHandle, tab_id: String, action: String) -> Result<(), String> {
    control_tab_webview_impl(&app, &tab_id, &action)
}

#[tauri::command]
async fn sync_tab_webviews(
    app: AppHandle,
    wv_state: State<'_, WebviewManagerState>,
    visible: Vec<TabBoundsSpec>,
) -> Result<(), String> {
    sync_tab_webviews_impl(&app, &wv_state, visible)
}

#[tauri::command]
async fn capture_open_tabs(
    app: AppHandle,
    db: State<'_, DbState>,
    conversation_id: String,
) -> Result<usize, String> {
    capture_open_tabs_for_conversation(&app, &db, &conversation_id)
}

#[tauri::command]
async fn autofill_tab_credentials(
    app: AppHandle,
    tab_id: String,
    auto_submit: bool,
) -> Result<bool, String> {
    autofill_tab_credentials_impl(&app, &tab_id, auto_submit)
}

#[tauri::command]
fn set_source_in_context(
    db: State<'_, DbState>,
    source_id: String,
    in_context: bool,
) -> Result<(), String> {
    db.set_source_in_context(&source_id, in_context)
        .map_err(|e| e.to_string())
}

#[tauri::command]
fn add_message(
    db: State<'_, DbState>,
    conversation_id: String,
    role: String,
    content: String,
    model: Option<String>,
    source_ids_json: Option<String>,
) -> Result<ChatMessage, String> {
    db.add_message(
        &conversation_id,
        &role,
        &content,
        model.as_deref(),
        source_ids_json.as_deref(),
    )
    .map_err(|e| e.to_string())
}

#[tauri::command]
fn list_bookmarks(db: State<'_, DbState>) -> Result<Vec<BookmarkItem>, String> {
    db.list_bookmarks().map_err(|e| e.to_string())
}

#[tauri::command]
fn add_bookmark(
    db: State<'_, DbState>,
    title: String,
    url: String,
) -> Result<BookmarkItem, String> {
    db.add_bookmark(&title, &url).map_err(|e| e.to_string())
}

#[tauri::command]
fn remove_bookmark(db: State<'_, DbState>, bookmark_id: String) -> Result<(), String> {
    db.remove_bookmark(&bookmark_id).map_err(|e| e.to_string())
}

#[tauri::command]
fn get_db_path(db: State<'_, DbState>) -> String {
    db.db_path.to_string_lossy().to_string()
}

fn load_or_create_settings(app_data_dir: &PathBuf) -> SatzSettings {
    let settings_path = app_data_dir.join("settings.json");
    if let Ok(raw) = std::fs::read_to_string(&settings_path) {
        if let Ok(parsed) = serde_json::from_str::<SatzSettings>(&raw) {
            return parsed;
        }
    }
    let default_settings = SatzSettings::default();
    if let Ok(json_str) = serde_json::to_string_pretty(&default_settings) {
        let _ = std::fs::write(&settings_path, json_str);
    }
    default_settings
}

fn resolve_repo_root() -> PathBuf {
    if let Ok(exe) = std::env::current_exe() {
        for anc in exe.ancestors() {
            if anc.join("sidecar").join("satz_models.py").exists() {
                return anc.to_path_buf();
            }
        }
    }
    if let Ok(cwd) = std::env::current_dir() {
        for anc in cwd.ancestors() {
            if anc.join("sidecar").join("satz_models.py").exists() {
                return anc.to_path_buf();
            }
        }
    }
    PathBuf::from("C:\\Users\\feama\\satz-browser")
}

fn spawn_sidecar(settings: &SatzSettings, app_data_dir: &PathBuf) -> Option<Child> {
    let repo_root = resolve_repo_root();
    let script_path = repo_root.join("sidecar").join("satz_models.py");
    if !script_path.exists() {
        return None;
    }

    let python_candidate = repo_root.join(&settings.python);
    let python_bin = if python_candidate.exists() {
        python_candidate.to_string_lossy().to_string()
    } else {
        "python".to_string()
    };

    let sgs_candidate = repo_root.join(&settings.sgs_root);
    let sgs_root_str = if sgs_candidate.exists() {
        sgs_candidate.to_string_lossy().to_string()
    } else {
        settings.sgs_root.clone()
    };

    let store_path = app_data_dir.join("planck_store.sqlite");

    let mut cmd = Command::new(python_bin);
    cmd.arg(&script_path)
        .arg("--sgs-root")
        .arg(sgs_root_str)
        .arg("--gemma-path")
        .arg(&settings.gemma_path)
        .arg("--port")
        .arg(settings.port.to_string())
        .arg("--store")
        .arg(store_path.to_string_lossy().to_string())
        .current_dir(&repo_root)
        .stdin(Stdio::null())
        .stdout(Stdio::null())
        .stderr(Stdio::null());

    #[cfg(windows)]
    {
        use std::os::windows::process::CommandExt;
        const CREATE_NO_WINDOW: u32 = 0x08000000;
        cmd.creation_flags(CREATE_NO_WINDOW);
    }

    cmd.spawn().ok()
}

#[cfg(target_os = "macos")]
fn setup_app_menu_accelerators(app: &tauri::App) -> tauri::Result<()> {
    let shortcuts: &[(&str, &str, &str)] = &[
        ("new_conversation", "New Conversation", "CmdOrCtrl+N"),
        ("filter_conversations", "Filter Conversations", "CmdOrCtrl+K"),
        ("new_tab", "New Tab", "CmdOrCtrl+T"),
        ("close_tab", "Close Tab", "CmdOrCtrl+W"),
        ("tab_chat", "Chat Tab", "CmdOrCtrl+1"),
        ("tab_2", "Site Tab 1", "CmdOrCtrl+2"),
        ("tab_3", "Site Tab 2", "CmdOrCtrl+3"),
        ("tab_4", "Site Tab 3", "CmdOrCtrl+4"),
        ("tab_5", "Site Tab 4", "CmdOrCtrl+5"),
        ("tab_6", "Site Tab 5", "CmdOrCtrl+6"),
        ("tab_7", "Site Tab 6", "CmdOrCtrl+7"),
        ("tab_8", "Site Tab 7", "CmdOrCtrl+8"),
        ("tab_9", "Site Tab 8", "CmdOrCtrl+9"),
        ("focus_address", "Focus Address Bar", "CmdOrCtrl+L"),
        ("toggle_agent_rail", "Toggle Agent Rail", "CmdOrCtrl+J"),
        ("toggle_compare", "Compare Selected Tabs", "CmdOrCtrl+M"),
        ("bookmark_current", "Bookmark Current Page", "CmdOrCtrl+D"),
    ];

    let mut submenu = SubmenuBuilder::new(app, "satz");
    for (id, label, accel) in shortcuts {
        let item = MenuItemBuilder::with_id(*id, *label)
            .accelerator(*accel)
            .build(app)?;
        submenu = submenu.item(&item);
    }

    let menu = MenuBuilder::new(app).item(&submenu.build()?).build()?;
    app.set_menu(menu)?;

    app.on_menu_event(move |app_handle, event| {
        let _ = app_handle.emit("menu-shortcut", event.id().0.as_str());
    });

    Ok(())
}

#[cfg(windows)]
fn ensure_default_desktop_on_windows() {
    #[repr(C)]
    struct StartupInfoW {
        cb: u32,
        lp_reserved: *mut u16,
        lp_desktop: *mut u16,
        lp_title: *mut u16,
        dw_x: u32,
        dw_y: u32,
        dw_x_size: u32,
        dw_y_size: u32,
        dw_x_count_chars: u32,
        dw_y_count_chars: u32,
        dw_fill_attribute: u32,
        dw_flags: u32,
        w_show_window: u16,
        cb_reserved2: u16,
        lp_reserved2: *mut u8,
        h_std_input: isize,
        h_std_output: isize,
        h_std_error: isize,
    }

    #[repr(C)]
    struct ProcessInformation {
        h_process: isize,
        h_thread: isize,
        dw_process_id: u32,
        dw_thread_id: u32,
    }

    #[link(name = "user32")]
    extern "system" {
        fn GetThreadDesktop(dwThreadId: u32) -> isize;
        fn GetUserObjectInformationW(
            hObj: isize,
            nIndex: i32,
            pvInfo: *mut u16,
            nLength: u32,
            lpnLengthNeeded: *mut u32,
        ) -> i32;
    }

    #[link(name = "kernel32")]
    extern "system" {
        fn GetCurrentThreadId() -> u32;
        fn WaitForSingleObject(hHandle: isize, dwMilliseconds: u32) -> u32;
        fn CreateProcessW(
            lpApplicationName: *const u16,
            lpCommandLine: *mut u16,
            lpProcessAttributes: *const std::ffi::c_void,
            lpThreadAttributes: *const std::ffi::c_void,
            bInheritHandles: i32,
            dwCreationFlags: u32,
            lpEnvironment: *const std::ffi::c_void,
            lpCurrentDirectory: *const u16,
            lpStartupInfo: *const StartupInfoW,
            lpProcessInformation: *mut ProcessInformation,
        ) -> i32;
    }

    unsafe {
        let h_desk = GetThreadDesktop(GetCurrentThreadId());
        let mut buf = [0u16; 256];
        let mut needed: u32 = 0;
        // UOI_NAME = 2
        if GetUserObjectInformationW(
            h_desk,
            2,
            buf.as_mut_ptr(),
            (buf.len() * 2) as u32,
            &mut needed,
        ) != 0
        {
            let end = buf.iter().position(|&c| c == 0).unwrap_or(buf.len());
            let desk_name = String::from_utf16_lossy(&buf[..end]);
            if !desk_name.eq_ignore_ascii_case("Default") {
                if let Ok(exe_path) = std::env::current_exe() {
                    let exe_wide: Vec<u16> = exe_path
                        .to_string_lossy()
                        .encode_utf16()
                        .chain(std::iter::once(0))
                        .collect();
                    let mut desktop_wide: Vec<u16> = "WinSta0\\Default"
                        .encode_utf16()
                        .chain(std::iter::once(0))
                        .collect();
                    let repo_root = resolve_repo_root();
                    let cwd_wide: Vec<u16> = repo_root
                        .to_string_lossy()
                        .encode_utf16()
                        .chain(std::iter::once(0))
                        .collect();

                    let mut si: StartupInfoW = std::mem::zeroed();
                    si.cb = std::mem::size_of::<StartupInfoW>() as u32;
                    si.lp_desktop = desktop_wide.as_mut_ptr();
                    let mut pi: ProcessInformation = std::mem::zeroed();

                    let ok = CreateProcessW(
                        exe_wide.as_ptr(),
                        std::ptr::null_mut(),
                        std::ptr::null(),
                        std::ptr::null(),
                        0,
                        0,
                        std::ptr::null(),
                        cwd_wide.as_ptr(),
                        &si,
                        &mut pi,
                    );
                    if ok != 0 {
                        let _ = WaitForSingleObject(pi.h_process, 0xFFFFFFFF);
                        std::process::exit(0);
                    }
                }
            }
        }
    }
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    #[cfg(windows)]
    ensure_default_desktop_on_windows();

    let app = tauri::Builder::default()
        .setup(|app| {
            let app_data_dir = app
                .path()
                .app_data_dir()
                .unwrap_or_else(|_| std::env::temp_dir().join("satz-browser"));
            let _ = std::fs::create_dir_all(&app_data_dir);

            let settings = load_or_create_settings(&app_data_dir);
            let db_path = app_data_dir.join("satz.db");
            let db_state =
                DbState::init(db_path).expect("failed to initialize local SQLite database");

            let mut wv_manager = WebviewManagerState::default();
            wv_manager.max_live_tabs = settings.max_live_tabs.max(1);

            let child_proc = spawn_sidecar(&settings, &app_data_dir);

            app.manage(db_state);
            app.manage(wv_manager);
            app.manage(SidecarState {
                child: Mutex::new(child_proc),
                settings,
            });

            #[cfg(target_os = "macos")]
            {
                let _ = setup_app_menu_accelerators(app);
            }

            if let Some(main_window) = app.get_window("main") {
                let _ = main_window.show();
                let _ = main_window.unminimize();
                let _ = main_window.set_focus();
            }
            Ok(())
        })
        .invoke_handler(tauri::generate_handler![
            list_conversations,
            get_conversation,
            get_conversation_bundle,
            create_conversation,
            rename_conversation,
            pin_conversation,
            toggle_pin_conversation,
            archive_conversation,
            delete_conversation,
            open_tab,
            close_tab,
            reorder_tabs,
            navigate_tab,
            control_tab,
            sync_tab_webviews,
            capture_open_tabs,
            autofill_tab_credentials,
            set_source_in_context,
            add_message,
            list_bookmarks,
            add_bookmark,
            remove_bookmark,
            get_db_path,
        ])
        .build(tauri::generate_context!())
        .expect("error while building satz application");

    app.run(|app_handle, event| {
        if let RunEvent::Exit = event {
            if let Some(sidecar) = app_handle.try_state::<SidecarState>() {
                if let Ok(mut guard) = sidecar.child.lock() {
                    if let Some(mut child) = guard.take() {
                        let _ = child.kill();
                    }
                }
            }
        }
    });
}
