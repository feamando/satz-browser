use rusqlite::{params, Connection, Result as SqlResult};
use serde::{Deserialize, Serialize};
use std::path::PathBuf;
use std::sync::Mutex;
use std::time::{SystemTime, UNIX_EPOCH};

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Conversation {
    pub id: String,
    pub intent_title: String,
    pub status: String,
    pub pinned: bool,
    pub created_at: String,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct AttachedPage {
    pub id: String,
    pub conversation_id: String,
    pub url: String,
    pub title: String,
    pub pane_index: i32,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ThreadNote {
    pub id: String,
    pub conversation_id: String,
    pub author: String,
    pub content: String,
    pub created_at: String,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct HistoryEntry {
    pub id: String,
    pub conversation_id: String,
    pub url: String,
    pub title: String,
    pub visited_at: String,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ConversationBundle {
    pub conversation: Conversation,
    pub attached_pages: Vec<AttachedPage>,
    pub notes: Vec<ThreadNote>,
    pub history: Vec<HistoryEntry>,
}

pub struct DbState {
    pub conn: Mutex<Connection>,
    pub db_path: PathBuf,
}

fn now_iso_timestamp() -> String {
    let secs = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .unwrap_or_default()
        .as_secs();
    format!("{}", secs)
}

fn gen_id(prefix: &str) -> String {
    let nanos = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .unwrap_or_default()
        .as_nanos();
    format!("{}-{}", prefix, nanos)
}

impl DbState {
    pub fn init(db_path: PathBuf) -> SqlResult<Self> {
        if let Some(parent) = db_path.parent() {
            let _ = std::fs::create_dir_all(parent);
        }
        let conn = Connection::open(&db_path)?;
        conn.execute_batch(
            "
            PRAGMA journal_mode = WAL;
            PRAGMA foreign_keys = ON;

            CREATE TABLE IF NOT EXISTS conversations (
                id TEXT PRIMARY KEY,
                intent_title TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'active',
                pinned INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS attached_pages (
                id TEXT PRIMARY KEY,
                conversation_id TEXT NOT NULL,
                url TEXT NOT NULL,
                title TEXT NOT NULL,
                pane_index INTEGER NOT NULL DEFAULT 0,
                FOREIGN KEY (conversation_id) REFERENCES conversations(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS thread_notes (
                id TEXT PRIMARY KEY,
                conversation_id TEXT NOT NULL,
                author TEXT NOT NULL DEFAULT 'user',
                content TEXT NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY (conversation_id) REFERENCES conversations(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS history_log (
                id TEXT PRIMARY KEY,
                conversation_id TEXT NOT NULL,
                url TEXT NOT NULL,
                title TEXT NOT NULL,
                visited_at TEXT NOT NULL,
                FOREIGN KEY (conversation_id) REFERENCES conversations(id) ON DELETE CASCADE
            );
            ",
        )?;

        let state = Self {
            conn: Mutex::new(conn),
            db_path,
        };
        state.seed_if_empty()?;
        Ok(state)
    }

    fn seed_if_empty(&self) -> SqlResult<()> {
        let conn = self.conn.lock().unwrap();
        let count: i64 = conn.query_row("SELECT COUNT(*) FROM conversations", [], |r| r.get(0))?;
        if count > 0 {
            return Ok(());
        }

        let ts = "2026-10-19T21:00:00Z";

        // Seed Conversation 1 (Pinned)
        conn.execute(
            "INSERT INTO conversations (id, intent_title, status, pinned, created_at) VALUES (?1, ?2, ?3, ?4, ?5)",
            params![
                "conv-1",
                "Tauri v2 Multi-WebView & WebView2 Architecture",
                "active",
                1,
                ts
            ],
        )?;
        let conv1_pages = [
            (
                "page-1-0",
                "https://v2.tauri.app/learn/",
                "Tauri v2 Documentation",
                0,
            ),
            (
                "page-1-1",
                "https://en.wikipedia.org/wiki/Microsoft_Edge_WebView2",
                "WebView2 — Wikipedia",
                1,
            ),
            (
                "page-1-2",
                "https://docs.rs/tauri/latest/tauri/webview/struct.WebviewBuilder.html",
                "WebviewBuilder in tauri::webview - Rust",
                2,
            ),
            (
                "page-1-3",
                "https://www.sqlite.org/wal.html",
                "Write-Ahead Logging — SQLite",
                3,
            ),
        ];
        for (id, url, title, idx) in conv1_pages {
            conn.execute(
                "INSERT INTO attached_pages (id, conversation_id, url, title, pane_index) VALUES (?1, 'conv-1', ?2, ?3, ?4)",
                params![id, url, title, idx],
            )?;
        }
        conn.execute(
            "INSERT INTO thread_notes (id, conversation_id, author, content, created_at) VALUES (?1, 'conv-1', 'system', ?2, ?3)",
            params![
                "note-1-1",
                "Intent initialized: Evaluate Tauri v2 multi-webview layout and SQLite local persistence on Windows 11. Press Ctrl+F for Focus Mode (single live WebView2 pane + side thread) or Ctrl+M for Compare View (2 to 4 tiled WebView2 panes).",
                ts
            ],
        )?;
        conn.execute(
            "INSERT INTO thread_notes (id, conversation_id, author, content, created_at) VALUES (?1, 'conv-1', 'user', ?2, ?3)",
            params![
                "note-1-2",
                "Phase 0 Gate: 100% daily browser use for 5 working days with 0 Chrome fallbacks. Zero AI models, zero search pipelines, zero mail fetching.",
                ts
            ],
        )?;

        // Seed Conversation 2 (Pinned)
        conn.execute(
            "INSERT INTO conversations (id, intent_title, status, pinned, created_at) VALUES (?1, ?2, ?3, ?4, ?5)",
            params![
                "conv-2",
                "Compare News Perspectives: European Tech & Energy",
                "active",
                1,
                ts
            ],
        )?;
        let conv2_pages = [
            ("page-2-0", "https://www.dw.com/en/", "DW — Deutsche Welle", 0),
            ("page-2-1", "https://www.bbc.com/news", "BBC News", 1),
            (
                "page-2-2",
                "https://en.wikipedia.org/wiki/Portal:Current_events",
                "Wikipedia Current Events",
                2,
            ),
            ("page-2-3", "https://news.ycombinator.com/", "Hacker News", 3),
        ];
        for (id, url, title, idx) in conv2_pages {
            conn.execute(
                "INSERT INTO attached_pages (id, conversation_id, url, title, pane_index) VALUES (?1, 'conv-2', ?2, ?3, ?4)",
                params![id, url, title, idx],
            )?;
        }
        conn.execute(
            "INSERT INTO thread_notes (id, conversation_id, author, content, created_at) VALUES (?1, 'conv-2', 'user', ?2, ?3)",
            params![
                "note-2-1",
                "Use Compare View (Ctrl+M) to tile DW, BBC, Wikipedia Current Events, and Hacker News side-by-side.",
                ts
            ],
        )?;

        // Seed Conversation 3
        conn.execute(
            "INSERT INTO conversations (id, intent_title, status, pinned, created_at) VALUES (?1, ?2, ?3, ?4, ?5)",
            params![
                "conv-3",
                "Flights Berlin → Lisbon, mid-March, under €200",
                "active",
                0,
                ts
            ],
        )?;
        let conv3_pages = [
            (
                "page-3-0",
                "https://en.wikipedia.org/wiki/Lisbon_Airport",
                "Lisbon Airport — Wikipedia",
                0,
            ),
            (
                "page-3-1",
                "https://en.wikipedia.org/wiki/Berlin_Brandenburg_Airport",
                "Berlin Brandenburg Airport — Wikipedia",
                1,
            ),
            (
                "page-3-2",
                "https://en.wikivoyage.org/wiki/Lisbon",
                "Lisbon Travel Guide — Wikivoyage",
                2,
            ),
            (
                "page-3-3",
                "https://en.wikipedia.org/wiki/TAP_Air_Portugal",
                "TAP Air Portugal — Wikipedia",
                3,
            ),
        ];
        for (id, url, title, idx) in conv3_pages {
            conn.execute(
                "INSERT INTO attached_pages (id, conversation_id, url, title, pane_index) VALUES (?1, 'conv-3', ?2, ?3, ?4)",
                params![id, url, title, idx],
            )?;
        }
        conn.execute(
            "INSERT INTO thread_notes (id, conversation_id, author, content, created_at) VALUES (?1, 'conv-3', 'user', ?2, ?3)",
            params![
                "note-3-1",
                "Checking direct morning departures from BER to LIS and luggage rules across carriers.",
                ts
            ],
        )?;

        Ok(())
    }

    pub fn list_conversations(&self) -> SqlResult<Vec<Conversation>> {
        let conn = self.conn.lock().unwrap();
        let mut stmt = conn.prepare(
            "SELECT id, intent_title, status, pinned, created_at
             FROM conversations
             ORDER BY pinned DESC, created_at DESC",
        )?;
        let rows = stmt.query_map([], |row| {
            let pinned_int: i32 = row.get(3)?;
            Ok(Conversation {
                id: row.get(0)?,
                intent_title: row.get(1)?,
                status: row.get(2)?,
                pinned: pinned_int != 0,
                created_at: row.get(4)?,
            })
        })?;
        rows.collect()
    }

    pub fn get_conversation_bundle(&self, conversation_id: &str) -> SqlResult<ConversationBundle> {
        let conn = self.conn.lock().unwrap();
        let conversation = conn.query_row(
            "SELECT id, intent_title, status, pinned, created_at FROM conversations WHERE id = ?1",
            params![conversation_id],
            |row| {
                let pinned_int: i32 = row.get(3)?;
                Ok(Conversation {
                    id: row.get(0)?,
                    intent_title: row.get(1)?,
                    status: row.get(2)?,
                    pinned: pinned_int != 0,
                    created_at: row.get(4)?,
                })
            },
        )?;

        let mut page_stmt = conn.prepare(
            "SELECT id, conversation_id, url, title, pane_index
             FROM attached_pages
             WHERE conversation_id = ?1
             ORDER BY pane_index ASC",
        )?;
        let attached_pages = page_stmt
            .query_map(params![conversation_id], |row| {
                Ok(AttachedPage {
                    id: row.get(0)?,
                    conversation_id: row.get(1)?,
                    url: row.get(2)?,
                    title: row.get(3)?,
                    pane_index: row.get(4)?,
                })
            })?
            .collect::<SqlResult<Vec<_>>>()?;

        let mut note_stmt = conn.prepare(
            "SELECT id, conversation_id, author, content, created_at
             FROM thread_notes
             WHERE conversation_id = ?1
             ORDER BY created_at ASC, id ASC",
        )?;
        let notes = note_stmt
            .query_map(params![conversation_id], |row| {
                Ok(ThreadNote {
                    id: row.get(0)?,
                    conversation_id: row.get(1)?,
                    author: row.get(2)?,
                    content: row.get(3)?,
                    created_at: row.get(4)?,
                })
            })?
            .collect::<SqlResult<Vec<_>>>()?;

        let mut hist_stmt = conn.prepare(
            "SELECT id, conversation_id, url, title, visited_at
             FROM history_log
             WHERE conversation_id = ?1
             ORDER BY visited_at DESC
             LIMIT 30",
        )?;
        let history = hist_stmt
            .query_map(params![conversation_id], |row| {
                Ok(HistoryEntry {
                    id: row.get(0)?,
                    conversation_id: row.get(1)?,
                    url: row.get(2)?,
                    title: row.get(3)?,
                    visited_at: row.get(4)?,
                })
            })?
            .collect::<SqlResult<Vec<_>>>()?;

        Ok(ConversationBundle {
            conversation,
            attached_pages,
            notes,
            history,
        })
    }

    pub fn create_conversation(
        &self,
        intent_title: &str,
        initial_url: Option<&str>,
    ) -> SqlResult<Conversation> {
        let conn = self.conn.lock().unwrap();
        let id = gen_id("conv");
        let ts = now_iso_timestamp();
        conn.execute(
            "INSERT INTO conversations (id, intent_title, status, pinned, created_at) VALUES (?1, ?2, 'active', 0, ?3)",
            params![id, intent_title, ts],
        )?;

        let default_urls = [
            (
                initial_url.unwrap_or("https://en.wikipedia.org/wiki/Main_Page"),
                "Primary Source (Pane 1)",
                0,
            ),
            (
                "https://news.ycombinator.com/",
                "Comparison Source (Pane 2)",
                1,
            ),
            ("https://v2.tauri.app/", "Reference Source (Pane 3)", 2),
            (
                "https://www.dw.com/en/",
                "Secondary Source (Pane 4)",
                3,
            ),
        ];

        for (url, title, pane_index) in default_urls {
            let page_id = format!("{}-p{}", id, pane_index);
            conn.execute(
                "INSERT INTO attached_pages (id, conversation_id, url, title, pane_index) VALUES (?1, ?2, ?3, ?4, ?5)",
                params![page_id, id, url, title, pane_index],
            )?;
        }

        let note_id = gen_id("note");
        conn.execute(
            "INSERT INTO thread_notes (id, conversation_id, author, content, created_at) VALUES (?1, ?2, 'system', ?3, ?4)",
            params![
                note_id,
                id,
                format!("Opened conversation for intent: \"{}\"", intent_title),
                ts
            ],
        )?;

        Ok(Conversation {
            id,
            intent_title: intent_title.to_string(),
            status: "active".to_string(),
            pinned: false,
            created_at: ts,
        })
    }

    pub fn toggle_pin_conversation(&self, conversation_id: &str) -> SqlResult<Conversation> {
        {
            let conn = self.conn.lock().unwrap();
            conn.execute(
                "UPDATE conversations SET pinned = CASE WHEN pinned = 1 THEN 0 ELSE 1 END WHERE id = ?1",
                params![conversation_id],
            )?;
        }
        Ok(self.get_conversation_bundle(conversation_id)?.conversation)
    }

    pub fn update_conversation_status(
        &self,
        conversation_id: &str,
        status: &str,
    ) -> SqlResult<Conversation> {
        {
            let conn = self.conn.lock().unwrap();
            conn.execute(
                "UPDATE conversations SET status = ?2 WHERE id = ?1",
                params![conversation_id, status],
            )?;
        }
        Ok(self.get_conversation_bundle(conversation_id)?.conversation)
    }

    pub fn delete_conversation(&self, conversation_id: &str) -> SqlResult<()> {
        let conn = self.conn.lock().unwrap();
        conn.execute(
            "DELETE FROM conversations WHERE id = ?1",
            params![conversation_id],
        )?;
        Ok(())
    }

    pub fn upsert_attached_page(
        &self,
        conversation_id: &str,
        pane_index: i32,
        url: &str,
        title: &str,
    ) -> SqlResult<AttachedPage> {
        let conn = self.conn.lock().unwrap();
        let existing_id: Option<String> = conn
            .query_row(
                "SELECT id FROM attached_pages WHERE conversation_id = ?1 AND pane_index = ?2",
                params![conversation_id, pane_index],
                |r| r.get(0),
            )
            .ok();

        let id = if let Some(eid) = existing_id {
            conn.execute(
                "UPDATE attached_pages SET url = ?2, title = ?3 WHERE id = ?1",
                params![eid, url, title],
            )?;
            eid
        } else {
            let new_id = gen_id("page");
            conn.execute(
                "INSERT INTO attached_pages (id, conversation_id, url, title, pane_index) VALUES (?1, ?2, ?3, ?4, ?5)",
                params![new_id, conversation_id, url, title, pane_index],
            )?;
            new_id
        };

        // Also record in history_log
        let hist_id = gen_id("hist");
        let ts = now_iso_timestamp();
        let _ = conn.execute(
            "INSERT INTO history_log (id, conversation_id, url, title, visited_at) VALUES (?1, ?2, ?3, ?4, ?5)",
            params![hist_id, conversation_id, url, title, ts],
        );

        Ok(AttachedPage {
            id,
            conversation_id: conversation_id.to_string(),
            url: url.to_string(),
            title: title.to_string(),
            pane_index,
        })
    }

    pub fn add_thread_note(
        &self,
        conversation_id: &str,
        author: &str,
        content: &str,
    ) -> SqlResult<ThreadNote> {
        let conn = self.conn.lock().unwrap();
        let id = gen_id("note");
        let ts = now_iso_timestamp();
        conn.execute(
            "INSERT INTO thread_notes (id, conversation_id, author, content, created_at) VALUES (?1, ?2, ?3, ?4, ?5)",
            params![id, conversation_id, author, content, ts],
        )?;
        Ok(ThreadNote {
            id,
            conversation_id: conversation_id.to_string(),
            author: author.to_string(),
            content: content.to_string(),
            created_at: ts,
        })
    }
}
