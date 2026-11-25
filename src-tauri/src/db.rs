use rusqlite::{params, Connection, OptionalExtension, Result as SqlResult};
use serde::{Deserialize, Serialize};
use std::path::PathBuf;
use std::sync::Mutex;
use std::time::{SystemTime, UNIX_EPOCH};
use url::Url;

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Conversation {
    pub id: String,
    pub title: String,
    pub status: String,
    pub pinned: bool,
    pub origin: String,
    pub created_at: String,
    pub last_active_at: String,
    pub source_count: i64,
    #[serde(default)]
    pub summary: Option<String>,
}

fn default_tab_kind() -> String {
    "site".to_string()
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct BrowserTab {
    pub id: String,
    pub conversation_id: String,
    pub position: i32,
    pub url: String,
    pub title: String,
    pub is_open: bool,
    pub created_at: String,
    #[serde(default = "default_tab_kind")]
    pub kind: String,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SourceItem {
    pub id: String,
    pub conversation_id: String,
    pub tab_id: Option<String>,
    pub url: String,
    pub title: String,
    pub domain: String,
    pub in_context: bool,
    pub added_at: String,
    pub captured_at: Option<String>,
    pub text_chars: Option<i64>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ChatMessage {
    pub id: String,
    pub conversation_id: String,
    pub role: String,
    pub content: String,
    pub model: Option<String>,
    pub source_ids_json: Option<String>,
    pub created_at: String,
    #[serde(default)]
    pub citations_ok: Option<i64>,
    #[serde(default)]
    pub citations_flagged: Option<i64>,
    #[serde(default)]
    pub citation_check_json: Option<String>,
    #[serde(default)]
    pub extras_json: Option<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct BookmarkItem {
    pub id: String,
    pub title: String,
    pub url: String,
    pub position: i32,
    pub created_at: String,
    #[serde(default)]
    pub favicon_url: Option<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct HistoryEntry {
    pub id: String,
    pub conversation_id: String,
    pub tab_id: Option<String>,
    pub url: String,
    pub title: String,
    pub visited_at: String,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ConversationDetail {
    pub conversation: Conversation,
    pub tabs: Vec<BrowserTab>,
    pub sources: Vec<SourceItem>,
    pub messages: Vec<ChatMessage>,
    pub history: Vec<HistoryEntry>,
}

pub struct DbState {
    pub conn: Mutex<Connection>,
    pub db_path: PathBuf,
}

pub fn now_epoch_secs_str() -> String {
    let secs = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .unwrap_or_default()
        .as_secs();
    format!("{}", secs)
}

fn gen_id(prefix: &str) -> String {
    use std::sync::atomic::{AtomicU64, Ordering};
    static COUNTER: AtomicU64 = AtomicU64::new(1);
    let nanos = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .unwrap_or_default()
        .as_nanos();
    let seq = COUNTER.fetch_add(1, Ordering::Relaxed);
    format!("{}-{}-{}", prefix, nanos, seq)
}

pub fn extract_domain(raw_url: &str) -> String {
    if let Ok(parsed) = Url::parse(raw_url) {
        if let Some(host) = parsed.host_str() {
            return host.strip_prefix("www.").unwrap_or(host).to_string();
        }
    }
    raw_url.to_string()
}

pub fn canonicalize_source_url(raw_url: &str) -> String {
    let trimmed = raw_url.trim();
    if let Ok(mut parsed) = Url::parse(trimmed) {
        parsed.set_fragment(None);
        if parsed.scheme() == "http" || parsed.scheme() == "https" {
            let kept_pairs: Vec<(String, String)> = parsed
                .query_pairs()
                .filter(|(k, _)| !k.to_lowercase().starts_with("utm_"))
                .map(|(k, v)| (k.into_owned(), v.into_owned()))
                .collect();
            if kept_pairs.is_empty() {
                parsed.set_query(None);
            } else {
                let mut serializer = url::form_urlencoded::Serializer::new(String::new());
                for (k, v) in kept_pairs {
                    serializer.append_pair(&k, &v);
                }
                let q = serializer.finish();
                parsed.set_query(Some(&q));
            }
            let path = parsed.path().to_string();
            if path.len() > 1 && path.ends_with('/') {
                let trimmed_path = path.trim_end_matches('/').to_string();
                parsed.set_path(&trimmed_path);
            }
        }
        let mut s = parsed.to_string();
        if (parsed.scheme() == "http" || parsed.scheme() == "https")
            && parsed.path() == "/"
            && parsed.query().is_none()
            && s.ends_with('/')
        {
            s.pop();
        }
        return s;
    }
    trimmed
        .split('#')
        .next()
        .unwrap_or(trimmed)
        .trim_end_matches('/')
        .to_string()
}

impl DbState {
    pub fn init(db_path: PathBuf) -> SqlResult<Self> {
        if let Some(parent) = db_path.parent() {
            let _ = std::fs::create_dir_all(parent);
        }
        let conn = Connection::open(&db_path)?;
        Self::init_connection(&conn)?;
        let state = Self {
            conn: Mutex::new(conn),
            db_path,
        };
        let _ = state.ensure_news_conversation();
        let _ = state.ensure_drives_conversation();
        Ok(state)
    }

    pub fn init_connection(conn: &Connection) -> SqlResult<()> {
        conn.execute_batch(
            "
            PRAGMA journal_mode = WAL;
            PRAGMA foreign_keys = ON;

            CREATE TABLE IF NOT EXISTS meta (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );
            ",
        )?;

        let version: Option<String> = conn
            .query_row(
                "SELECT value FROM meta WHERE key = 'schema_version'",
                [],
                |r| r.get(0),
            )
            .optional()?;

        if version.as_deref() == Some("2") {
            Self::ensure_v2_tables(conn)?;
            return Ok(());
        }

        // Check whether a v1 conversations table exists with intent_title
        let has_v1_conversations: bool = conn
            .query_row(
                "SELECT COUNT(*) FROM pragma_table_info('conversations') WHERE name = 'intent_title'",
                [],
                |r| {
                    let c: i64 = r.get(0)?;
                    Ok(c > 0)
                },
            )
            .unwrap_or(false);

        if has_v1_conversations {
            Self::migrate_v1_to_v2(conn)?;
        } else {
            Self::ensure_v2_tables(conn)?;
            conn.execute(
                "INSERT OR REPLACE INTO meta (key, value) VALUES ('schema_version', '2')",
                [],
            )?;
        }

        Ok(())
    }

    fn ensure_v2_tables(conn: &Connection) -> SqlResult<()> {
        conn.execute_batch(
            "
            CREATE TABLE IF NOT EXISTS conversations (
                id TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'active',
                pinned INTEGER NOT NULL DEFAULT 0,
                origin TEXT NOT NULL DEFAULT 'chat',
                created_at TEXT NOT NULL,
                last_active_at TEXT NOT NULL,
                summary TEXT NULL
            );

            CREATE TABLE IF NOT EXISTS tabs (
                id TEXT PRIMARY KEY,
                conversation_id TEXT NOT NULL,
                position INTEGER NOT NULL DEFAULT 0,
                url TEXT NOT NULL,
                title TEXT NOT NULL,
                is_open INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL,
                kind TEXT NOT NULL DEFAULT 'site',
                FOREIGN KEY (conversation_id) REFERENCES conversations(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS sources (
                id TEXT PRIMARY KEY,
                conversation_id TEXT NOT NULL,
                tab_id TEXT NULL,
                url TEXT NOT NULL,
                title TEXT NOT NULL,
                domain TEXT NOT NULL,
                in_context INTEGER NOT NULL DEFAULT 1,
                added_at TEXT NOT NULL,
                captured_at TEXT NULL,
                text_chars INTEGER NULL,
                FOREIGN KEY (conversation_id) REFERENCES conversations(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS messages (
                id TEXT PRIMARY KEY,
                conversation_id TEXT NOT NULL,
                role TEXT NOT NULL DEFAULT 'user',
                content TEXT NOT NULL,
                model TEXT NULL,
                source_ids_json TEXT NULL,
                created_at TEXT NOT NULL,
                citations_ok INTEGER NULL,
                citations_flagged INTEGER NULL,
                citation_check_json TEXT NULL,
                extras_json TEXT NULL,
                FOREIGN KEY (conversation_id) REFERENCES conversations(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS bookmarks (
                id TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                url TEXT NOT NULL,
                position INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS history_log (
                id TEXT PRIMARY KEY,
                conversation_id TEXT NOT NULL,
                tab_id TEXT NULL,
                url TEXT NOT NULL,
                title TEXT NOT NULL,
                visited_at TEXT NOT NULL,
                FOREIGN KEY (conversation_id) REFERENCES conversations(id) ON DELETE CASCADE
            );
            ",
        )?;

        let has_summary_col: bool = conn
            .query_row(
                "SELECT COUNT(*) FROM pragma_table_info('conversations') WHERE name = 'summary'",
                [],
                |r| {
                    let c: i64 = r.get(0)?;
                    Ok(c > 0)
                },
            )
            .unwrap_or(false);
        if !has_summary_col {
            conn.execute("ALTER TABLE conversations ADD COLUMN summary TEXT NULL", [])?;
        }

        let has_tab_kind_col: bool = conn
            .query_row(
                "SELECT COUNT(*) FROM pragma_table_info('tabs') WHERE name = 'kind'",
                [],
                |r| {
                    let c: i64 = r.get(0)?;
                    Ok(c > 0)
                },
            )
            .unwrap_or(false);
        if !has_tab_kind_col {
            conn.execute(
                "ALTER TABLE tabs ADD COLUMN kind TEXT NOT NULL DEFAULT 'site'",
                [],
            )?;
        }

        for (col_name, col_type) in [
            ("citations_ok", "INTEGER NULL"),
            ("citations_flagged", "INTEGER NULL"),
            ("citation_check_json", "TEXT NULL"),
            ("extras_json", "TEXT NULL"),
        ] {
            let has_col: bool = conn
                .query_row(
                    "SELECT COUNT(*) FROM pragma_table_info('messages') WHERE name = ?1",
                    params![col_name],
                    |r| {
                        let c: i64 = r.get(0)?;
                        Ok(c > 0)
                    },
                )
                .unwrap_or(false);
            if !has_col {
                conn.execute(
                    &format!("ALTER TABLE messages ADD COLUMN {} {}", col_name, col_type),
                    [],
                )?;
            }
        }

        let has_bookmark_favicon_col: bool = conn
            .query_row(
                "SELECT COUNT(*) FROM pragma_table_info('bookmarks') WHERE name = 'favicon_url'",
                [],
                |r| {
                    let c: i64 = r.get(0)?;
                    Ok(c > 0)
                },
            )
            .unwrap_or(false);
        if !has_bookmark_favicon_col {
            conn.execute("ALTER TABLE bookmarks ADD COLUMN favicon_url TEXT NULL", [])?;
        }

        let unseeded_v05: Option<String> = conn
            .query_row(
                "SELECT value FROM meta WHERE key = 'v05_unseeded_bookmarks'",
                [],
                |r| r.get(0),
            )
            .optional()?;

        if unseeded_v05.is_none() {
            conn.execute(
                "DELETE FROM bookmarks WHERE id IN ('bm-1', 'bm-2', 'bm-3', 'bm-4', 'bm-5', 'bm-6')",
                [],
            )?;
            conn.execute(
                "INSERT OR REPLACE INTO meta (key, value) VALUES ('v05_unseeded_bookmarks', '1')",
                [],
            )?;
            conn.execute(
                "INSERT OR REPLACE INTO meta (key, value) VALUES ('bookmarks_seeded', '1')",
                [],
            )?;
        }

        Ok(())
    }

    fn migrate_v1_to_v2(conn: &Connection) -> SqlResult<()> {
        // Drop untouched Phase 0 seed conversations (conv-1, conv-2, conv-3) if they have no user-added notes
        for seed_id in ["conv-1", "conv-2", "conv-3"] {
            let custom_note_count: i64 = conn
                .query_row(
                    "SELECT COUNT(*) FROM thread_notes WHERE conversation_id = ?1 AND id NOT IN ('note-1-1', 'note-1-2', 'note-2-1', 'note-3-1')",
                    params![seed_id],
                    |r| r.get(0),
                )
                .unwrap_or(0);
            if custom_note_count == 0 {
                let _ = conn.execute("DELETE FROM conversations WHERE id = ?1", params![seed_id]);
            }
        }

        conn.execute_batch(
            "
            ALTER TABLE conversations RENAME TO conversations_v1;
            ALTER TABLE history_log RENAME TO history_log_v1;
            ",
        )?;

        Self::ensure_v2_tables(conn)?;

        // Copy surviving conversations
        conn.execute(
            "INSERT INTO conversations (id, title, status, pinned, origin, created_at, last_active_at)
             SELECT id, intent_title, status, pinned, 'chat', created_at, created_at
             FROM conversations_v1",
            [],
        )?;

        // Migrate attached_pages -> tabs and sources
        let has_attached_pages: bool = conn
            .query_row(
                "SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name='attached_pages'",
                [],
                |r| {
                    let c: i64 = r.get(0)?;
                    Ok(c > 0)
                },
            )
            .unwrap_or(false);

        if has_attached_pages {
            let mut stmt = conn.prepare(
                "SELECT ap.id, ap.conversation_id, ap.url, ap.title, ap.pane_index, c.created_at
                 FROM attached_pages ap
                 JOIN conversations c ON c.id = ap.conversation_id",
            )?;
            let rows = stmt
                .query_map([], |row| {
                    Ok((
                        row.get::<_, String>(0)?,
                        row.get::<_, String>(1)?,
                        row.get::<_, String>(2)?,
                        row.get::<_, String>(3)?,
                        row.get::<_, i32>(4)?,
                        row.get::<_, String>(5)?,
                    ))
                })?
                .collect::<SqlResult<Vec<_>>>()?;

            for (page_id, conv_id, url, title, pane_idx, created_at) in rows {
                let tab_id = format!("tab-{}", page_id);
                let src_id = format!("src-{}", page_id);
                let domain = extract_domain(&url);
                conn.execute(
                    "INSERT INTO tabs (id, conversation_id, position, url, title, is_open, created_at)
                     VALUES (?1, ?2, ?3, ?4, ?5, 1, ?6)",
                    params![tab_id, conv_id, pane_idx, url, title, created_at],
                )?;
                conn.execute(
                    "INSERT INTO sources (id, conversation_id, tab_id, url, title, domain, in_context, added_at, captured_at, text_chars)
                     VALUES (?1, ?2, ?3, ?4, ?5, ?6, 1, ?7, NULL, NULL)",
                    params![src_id, conv_id, tab_id, url, title, domain, created_at],
                )?;
            }
        }

        // Migrate thread_notes -> messages
        let has_thread_notes: bool = conn
            .query_row(
                "SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name='thread_notes'",
                [],
                |r| {
                    let c: i64 = r.get(0)?;
                    Ok(c > 0)
                },
            )
            .unwrap_or(false);

        if has_thread_notes {
            conn.execute(
                "INSERT INTO messages (id, conversation_id, role, content, model, source_ids_json, created_at)
                 SELECT tn.id, tn.conversation_id,
                        CASE WHEN tn.author = 'system' THEN 'system' ELSE 'user' END,
                        tn.content, NULL, NULL, tn.created_at
                 FROM thread_notes tn
                 JOIN conversations c ON c.id = tn.conversation_id",
                [],
            )?;
        }

        // Migrate history_log_v1 -> history_log
        conn.execute(
            "INSERT INTO history_log (id, conversation_id, tab_id, url, title, visited_at)
             SELECT h.id, h.conversation_id, NULL, h.url, h.title, h.visited_at
             FROM history_log_v1 h
             JOIN conversations c ON c.id = h.conversation_id",
            [],
        )?;

        conn.execute_batch(
            "
            DROP TABLE IF EXISTS attached_pages;
            DROP TABLE IF EXISTS thread_notes;
            DROP TABLE IF EXISTS history_log_v1;
            DROP TABLE IF EXISTS conversations_v1;
            INSERT OR REPLACE INTO meta (key, value) VALUES ('schema_version', '2');
            ",
        )?;

        Ok(())
    }

    pub fn auto_archive_stale_direct_conversations(&self) -> SqlResult<()> {
        let conn = self.conn.lock().unwrap();
        let now_secs = SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .unwrap_or_default()
            .as_secs() as i64;
        let cutoff = now_secs - 86_400;

        conn.execute(
            "UPDATE conversations
             SET status = 'archived'
             WHERE origin = 'direct'
               AND status = 'active'
               AND CAST(last_active_at AS INTEGER) > 0
               AND CAST(last_active_at AS INTEGER) < ?1
               AND (SELECT COUNT(*) FROM messages m WHERE m.conversation_id = conversations.id) = 0",
            params![cutoff],
        )?;
        Ok(())
    }

    pub fn list_conversations(&self) -> SqlResult<Vec<Conversation>> {
        let _ = self.auto_archive_stale_direct_conversations();
        let conn = self.conn.lock().unwrap();
        let mut stmt = conn.prepare(
            "SELECT c.id, c.title, c.status, c.pinned, c.origin, c.created_at, c.last_active_at,
                    (SELECT COUNT(*) FROM tabs t WHERE t.conversation_id = c.id AND t.is_open = 1) AS src_cnt,
                    c.summary
             FROM conversations c
             ORDER BY CASE c.origin
                        WHEN 'mail' THEN 6
                        WHEN 'news' THEN 5
                        WHEN 'drives' THEN 4
                        WHEN 'settings' THEN 3
                        WHEN 'news_settings' THEN 2
                        WHEN 'news_perspectives' THEN 1
                        ELSE 0
                      END DESC,
                      c.pinned DESC,
                      c.last_active_at DESC,
                      c.created_at DESC",
        )?;
        let rows = stmt.query_map([], |row| {
            let pinned_int: i32 = row.get(3)?;
            Ok(Conversation {
                id: row.get(0)?,
                title: row.get(1)?,
                status: row.get(2)?,
                pinned: pinned_int != 0,
                origin: row.get(4)?,
                created_at: row.get(5)?,
                last_active_at: row.get(6)?,
                source_count: row.get(7)?,
                summary: row.get(8)?,
            })
        })?;
        rows.collect()
    }

    fn ensure_pinned_origin_conversation(
        &self,
        origin: &str,
        default_id: &str,
        default_title: &str,
    ) -> SqlResult<Conversation> {
        let target_id = {
            let conn = self.conn.lock().unwrap();
            let existing_id: Option<String> = conn
                .query_row(
                    "SELECT id FROM conversations WHERE origin = ?1 LIMIT 1",
                    params![origin],
                    |r| r.get(0),
                )
                .optional()?;
            if let Some(cid) = existing_id {
                conn.execute(
                    "UPDATE conversations SET pinned = 1, status = 'active' WHERE id = ?1",
                    params![cid],
                )?;
                cid
            } else {
                let ts = now_epoch_secs_str();
                conn.execute(
                    "INSERT OR REPLACE INTO conversations (id, title, status, pinned, origin, created_at, last_active_at)
                     VALUES (?1, ?2, 'active', 1, ?3, ?4, ?4)",
                    params![default_id, default_title, origin, ts],
                )?;
                default_id.to_string()
            }
        };
        Ok(self.get_conversation(&target_id)?.conversation)
    }

    pub fn ensure_mail_conversation(&self) -> SqlResult<Conversation> {
        self.ensure_pinned_origin_conversation("mail", "conv-mail", "mail")
    }

    pub fn ensure_news_conversation(&self) -> SqlResult<Conversation> {
        self.ensure_pinned_origin_conversation("news", "conv-news", "news")
    }

    pub fn ensure_drives_conversation(&self) -> SqlResult<Conversation> {
        self.ensure_pinned_origin_conversation("drives", "conv-drives", "Drives")
    }

    pub fn ensure_settings_conversation(&self) -> SqlResult<Conversation> {
        self.ensure_pinned_origin_conversation("settings", "conv-settings", "Settings")
    }

    pub fn ensure_news_settings_conversation(&self) -> SqlResult<Conversation> {
        self.ensure_pinned_origin_conversation(
            "news_settings",
            "conv-news-settings",
            "News Settings",
        )
    }

    pub fn ensure_news_perspectives_conversation(&self) -> SqlResult<Conversation> {
        self.ensure_pinned_origin_conversation(
            "news_perspectives",
            "conv-news-perspectives",
            "Perspectives",
        )
    }

    pub fn get_conversation(&self, conversation_id: &str) -> SqlResult<ConversationDetail> {
        let conn = self.conn.lock().unwrap();
        let conversation = conn.query_row(
            "SELECT c.id, c.title, c.status, c.pinned, c.origin, c.created_at, c.last_active_at,
                    (SELECT COUNT(*) FROM tabs t WHERE t.conversation_id = c.id AND t.is_open = 1) AS src_cnt,
                    c.summary
             FROM conversations c
             WHERE c.id = ?1",
            params![conversation_id],
            |row| {
                let pinned_int: i32 = row.get(3)?;
                Ok(Conversation {
                    id: row.get(0)?,
                    title: row.get(1)?,
                    status: row.get(2)?,
                    pinned: pinned_int != 0,
                    origin: row.get(4)?,
                    created_at: row.get(5)?,
                    last_active_at: row.get(6)?,
                    source_count: row.get(7)?,
                    summary: row.get(8)?,
                })
            },
        )?;

        let mut tab_stmt = conn.prepare(
            "SELECT id, conversation_id, position, url, title, is_open, created_at, kind
             FROM tabs
             WHERE conversation_id = ?1
             ORDER BY position ASC, created_at ASC",
        )?;
        let tabs = tab_stmt
            .query_map(params![conversation_id], |row| {
                let is_open_int: i32 = row.get(5)?;
                Ok(BrowserTab {
                    id: row.get(0)?,
                    conversation_id: row.get(1)?,
                    position: row.get(2)?,
                    url: row.get(3)?,
                    title: row.get(4)?,
                    is_open: is_open_int != 0,
                    created_at: row.get(6)?,
                    kind: row.get::<_, Option<String>>(7)?.unwrap_or_else(default_tab_kind),
                })
            })?
            .collect::<SqlResult<Vec<_>>>()?;

        let mut src_stmt = conn.prepare(
            "SELECT id, conversation_id, tab_id, url, title, domain, in_context, added_at, captured_at, text_chars
             FROM sources
             WHERE conversation_id = ?1
             ORDER BY added_at DESC, id DESC",
        )?;
        let sources = src_stmt
            .query_map(params![conversation_id], |row| {
                let in_ctx_int: i32 = row.get(6)?;
                Ok(SourceItem {
                    id: row.get(0)?,
                    conversation_id: row.get(1)?,
                    tab_id: row.get(2)?,
                    url: row.get(3)?,
                    title: row.get(4)?,
                    domain: row.get(5)?,
                    in_context: in_ctx_int != 0,
                    added_at: row.get(7)?,
                    captured_at: row.get(8)?,
                    text_chars: row.get(9)?,
                })
            })?
            .collect::<SqlResult<Vec<_>>>()?;

        let mut msg_stmt = conn.prepare(
            "SELECT id, conversation_id, role, content, model, source_ids_json, created_at,
                    citations_ok, citations_flagged, citation_check_json, extras_json
             FROM messages
             WHERE conversation_id = ?1
             ORDER BY created_at ASC, id ASC",
        )?;
        let messages = msg_stmt
            .query_map(params![conversation_id], |row| {
                Ok(ChatMessage {
                    id: row.get(0)?,
                    conversation_id: row.get(1)?,
                    role: row.get(2)?,
                    content: row.get(3)?,
                    model: row.get(4)?,
                    source_ids_json: row.get(5)?,
                    created_at: row.get(6)?,
                    citations_ok: row.get(7)?,
                    citations_flagged: row.get(8)?,
                    citation_check_json: row.get(9)?,
                    extras_json: row.get(10)?,
                })
            })?
            .collect::<SqlResult<Vec<_>>>()?;

        let mut hist_stmt = conn.prepare(
            "SELECT id, conversation_id, tab_id, url, title, visited_at
             FROM history_log
             WHERE conversation_id = ?1
             ORDER BY visited_at DESC, id DESC
             LIMIT 50",
        )?;
        let history = hist_stmt
            .query_map(params![conversation_id], |row| {
                Ok(HistoryEntry {
                    id: row.get(0)?,
                    conversation_id: row.get(1)?,
                    tab_id: row.get(2)?,
                    url: row.get(3)?,
                    title: row.get(4)?,
                    visited_at: row.get(5)?,
                })
            })?
            .collect::<SqlResult<Vec<_>>>()?;

        Ok(ConversationDetail {
            conversation,
            tabs,
            sources,
            messages,
            history,
        })
    }

    pub fn create_conversation(&self, title: &str, origin: &str) -> SqlResult<Conversation> {
        let conn = self.conn.lock().unwrap();
        let id = gen_id("conv");
        let ts = now_epoch_secs_str();
        let normalized_origin = if origin == "direct" { "direct" } else { "chat" };
        conn.execute(
            "INSERT INTO conversations (id, title, status, pinned, origin, created_at, last_active_at)
             VALUES (?1, ?2, 'active', 0, ?3, ?4, ?4)",
            params![id, title, normalized_origin, ts],
        )?;
        Ok(Conversation {
            id,
            title: title.to_string(),
            status: "active".to_string(),
            pinned: false,
            origin: normalized_origin.to_string(),
            created_at: ts.clone(),
            last_active_at: ts,
            source_count: 0,
            summary: None,
        })
    }

    pub fn set_conversation_summary(
        &self,
        conversation_id: &str,
        summary: &str,
    ) -> SqlResult<()> {
        let conn = self.conn.lock().unwrap();
        let truncated: String = summary.chars().take(600).collect();
        conn.execute(
            "UPDATE conversations SET summary = ?2 WHERE id = ?1",
            params![conversation_id, truncated],
        )?;
        Ok(())
    }

    pub fn rename_conversation(
        &self,
        conversation_id: &str,
        title: &str,
    ) -> SqlResult<Conversation> {
        {
            let conn = self.conn.lock().unwrap();
            let ts = now_epoch_secs_str();
            conn.execute(
                "UPDATE conversations SET title = ?2, last_active_at = ?3 WHERE id = ?1",
                params![conversation_id, title, ts],
            )?;
        }
        Ok(self.get_conversation(conversation_id)?.conversation)
    }

    pub fn pin_conversation(&self, conversation_id: &str) -> SqlResult<Conversation> {
        {
            let conn = self.conn.lock().unwrap();
            conn.execute(
                "UPDATE conversations SET pinned = CASE WHEN origin IN ('mail', 'news', 'drives', 'settings', 'news_settings', 'news_perspectives') THEN 1 WHEN pinned = 1 THEN 0 ELSE 1 END WHERE id = ?1",
                params![conversation_id],
            )?;
        }
        Ok(self.get_conversation(conversation_id)?.conversation)
    }

    pub fn archive_conversation(
        &self,
        conversation_id: &str,
        archived: bool,
    ) -> SqlResult<Conversation> {
        let status = if archived { "archived" } else { "active" };
        {
            let conn = self.conn.lock().unwrap();
            conn.execute(
                "UPDATE conversations SET status = CASE WHEN origin IN ('mail', 'news', 'drives', 'settings', 'news_settings', 'news_perspectives') THEN 'active' ELSE ?2 END WHERE id = ?1",
                params![conversation_id, status],
            )?;
        }
        Ok(self.get_conversation(conversation_id)?.conversation)
    }

    pub fn delete_conversation(&self, conversation_id: &str) -> SqlResult<()> {
        let conn = self.conn.lock().unwrap();
        let origin: Option<String> = conn
            .query_row(
                "SELECT origin FROM conversations WHERE id = ?1",
                params![conversation_id],
                |r| r.get(0),
            )
            .optional()?;
        if matches!(
            origin.as_deref(),
            Some("mail")
                | Some("news")
                | Some("drives")
                | Some("settings")
                | Some("news_settings")
                | Some("news_perspectives")
        ) {
            return Err(rusqlite::Error::InvalidParameterName(
                "Pinned system conversation cannot be deleted".to_string(),
            ));
        }
        conn.execute(
            "DELETE FROM conversations WHERE id = ?1 AND origin NOT IN ('mail', 'news', 'drives', 'settings', 'news_settings', 'news_perspectives')",
            params![conversation_id],
        )?;
        Ok(())
    }

    pub fn open_tab(
        &self,
        conversation_id: &str,
        url: &str,
        title: Option<&str>,
    ) -> SqlResult<(BrowserTab, SourceItem)> {
        self.open_tab_with_kind(conversation_id, url, title, None)
    }

    pub fn open_tab_with_kind(
        &self,
        conversation_id: &str,
        url: &str,
        title: Option<&str>,
        kind: Option<&str>,
    ) -> SqlResult<(BrowserTab, SourceItem)> {
        let conn = self.conn.lock().unwrap();
        let ts = now_epoch_secs_str();
        let resolved_kind = match kind {
            Some("mail") | Some("compose") | Some("site") => kind.unwrap().to_string(),
            _ if url.starts_with("satzmail://message/") => "mail".to_string(),
            _ if url.starts_with("satzmail://compose") => "compose".to_string(),
            _ => "site".to_string(),
        };

        // If an open mail tab for this message URL already exists in the conversation, return it
        if resolved_kind == "mail" {
            let existing: Option<BrowserTab> = conn
                .query_row(
                    "SELECT id, conversation_id, position, url, title, is_open, created_at, kind
                     FROM tabs
                     WHERE conversation_id = ?1 AND url = ?2 AND is_open = 1
                     LIMIT 1",
                    params![conversation_id, url],
                    |row| {
                        let is_open_int: i32 = row.get(5)?;
                        Ok(BrowserTab {
                            id: row.get(0)?,
                            conversation_id: row.get(1)?,
                            position: row.get(2)?,
                            url: row.get(3)?,
                            title: row.get(4)?,
                            is_open: is_open_int != 0,
                            created_at: row.get(6)?,
                            kind: row.get::<_, Option<String>>(7)?.unwrap_or_else(default_tab_kind),
                        })
                    },
                )
                .optional()?;
            if let Some(tab) = existing {
                let msg_id = url.strip_prefix("satzmail://message/").unwrap_or(&tab.id);
                let src_id = format!("mail:{}", msg_id);
                conn.execute(
                    "INSERT OR REPLACE INTO sources (id, conversation_id, tab_id, url, title, domain, in_context, added_at, captured_at, text_chars)
                     VALUES (?1, ?2, ?3, ?4, ?5, 'mail', 1, ?6, ?6, NULL)",
                    params![src_id, conversation_id, tab.id, url, tab.title, ts],
                )?;
                return Ok((
                    tab.clone(),
                    SourceItem {
                        id: src_id,
                        conversation_id: conversation_id.to_string(),
                        tab_id: Some(tab.id),
                        url: url.to_string(),
                        title: tab.title,
                        domain: "mail".to_string(),
                        in_context: true,
                        added_at: ts.clone(),
                        captured_at: Some(ts),
                        text_chars: None,
                    },
                ));
            }
        }

        let tab_id = gen_id("tab");
        let domain = if resolved_kind == "mail" {
            "mail".to_string()
        } else if resolved_kind == "compose" {
            "compose".to_string()
        } else {
            extract_domain(url)
        };
        let tab_title = title
            .filter(|t| !t.trim().is_empty())
            .unwrap_or(&domain)
            .to_string();

        let next_pos: i32 = conn
            .query_row(
                "SELECT COALESCE(MAX(position) + 1, 0) FROM tabs WHERE conversation_id = ?1",
                params![conversation_id],
                |r| r.get(0),
            )
            .unwrap_or(0);

        conn.execute(
            "INSERT INTO tabs (id, conversation_id, position, url, title, is_open, created_at, kind)
             VALUES (?1, ?2, ?3, ?4, ?5, 1, ?6, ?7)",
            params![tab_id, conversation_id, next_pos, url, tab_title, ts, resolved_kind],
        )?;

        let canonical_target = canonicalize_source_url(url);
        let existing_src_id: Option<String> = if resolved_kind != "mail" && resolved_kind != "compose" {
            let mut stmt = conn.prepare(
                "SELECT id, url FROM sources WHERE conversation_id = ?1 ORDER BY added_at DESC, id DESC",
            )?;
            let rows = stmt.query_map(params![conversation_id], |r| {
                Ok((r.get::<_, String>(0)?, r.get::<_, String>(1)?))
            })?;
            let mut found = None;
            for item in rows.flatten() {
                if canonicalize_source_url(&item.1) == canonical_target {
                    found = Some(item.0);
                    break;
                }
            }
            found
        } else {
            None
        };

        let src_id = if resolved_kind == "mail" {
            let msg_id = url.strip_prefix("satzmail://message/").unwrap_or(&tab_id);
            format!("mail:{}", msg_id)
        } else if let Some(existing_id) = existing_src_id {
            existing_id
        } else {
            gen_id("src")
        };

        if resolved_kind != "compose" && url != "about:blank" {
            conn.execute(
                "INSERT INTO sources (id, conversation_id, tab_id, url, title, domain, in_context, added_at, captured_at, text_chars)
                 VALUES (?1, ?2, ?3, ?4, ?5, ?6, 1, ?7, NULL, NULL)
                 ON CONFLICT(id) DO UPDATE SET
                     tab_id = excluded.tab_id,
                     url = excluded.url,
                     title = excluded.title,
                     domain = excluded.domain,
                     in_context = 1,
                     added_at = excluded.added_at",
                params![src_id, conversation_id, tab_id, url, tab_title, domain, ts],
            )?;

            let hist_id = gen_id("hist");
            conn.execute(
                "INSERT INTO history_log (id, conversation_id, tab_id, url, title, visited_at)
                 VALUES (?1, ?2, ?3, ?4, ?5, ?6)",
                params![hist_id, conversation_id, tab_id, url, tab_title, ts],
            )?;
        }

        conn.execute(
            "UPDATE conversations SET last_active_at = ?2 WHERE id = ?1",
            params![conversation_id, ts],
        )?;

        Ok((
            BrowserTab {
                id: tab_id.clone(),
                conversation_id: conversation_id.to_string(),
                position: next_pos,
                url: url.to_string(),
                title: tab_title.clone(),
                is_open: true,
                created_at: ts.clone(),
                kind: resolved_kind,
            },
            SourceItem {
                id: src_id,
                conversation_id: conversation_id.to_string(),
                tab_id: Some(tab_id),
                url: url.to_string(),
                title: tab_title,
                domain,
                in_context: true,
                added_at: ts,
                captured_at: None,
                text_chars: None,
            },
        ))
    }

    pub fn close_tab(&self, tab_id: &str) -> SqlResult<Option<String>> {
        let conn = self.conn.lock().unwrap();
        let conv_id: Option<String> = conn
            .query_row(
                "SELECT conversation_id FROM tabs WHERE id = ?1",
                params![tab_id],
                |r| r.get(0),
            )
            .optional()?;

        conn.execute("UPDATE tabs SET is_open = 0 WHERE id = ?1", params![tab_id])?;
        // Closing a tab keeps its pages as sources (unchecked by default per section 2.4)
        conn.execute(
            "UPDATE sources SET in_context = 0 WHERE tab_id = ?1",
            params![tab_id],
        )?;

        if let Some(ref cid) = conv_id {
            let ts = now_epoch_secs_str();
            let _ = conn.execute(
                "UPDATE conversations SET last_active_at = ?2 WHERE id = ?1",
                params![cid, ts],
            );
        }
        Ok(conv_id)
    }

    pub fn reorder_tabs(&self, conversation_id: &str, tab_ids: &[String]) -> SqlResult<()> {
        let conn = self.conn.lock().unwrap();
        for (idx, tid) in tab_ids.iter().enumerate() {
            conn.execute(
                "UPDATE tabs SET position = ?3 WHERE id = ?1 AND conversation_id = ?2",
                params![tid, conversation_id, idx as i32],
            )?;
        }
        Ok(())
    }

    /// Updates a tab's URL and/or title.
    /// IMPORTANT (M2 check): Writes a new `history_log` and `sources` row ONLY when the URL actually changes!
    pub fn record_tab_navigation_or_title(
        &self,
        tab_id: &str,
        new_url: Option<&str>,
        new_title: Option<&str>,
    ) -> SqlResult<Option<(BrowserTab, Option<SourceItem>)>> {
        let conn = self.conn.lock().unwrap();
        let current: Option<(String, i32, String, String, i32, String, String)> = conn
            .query_row(
                "SELECT conversation_id, position, url, title, is_open, created_at, COALESCE(kind, 'site') FROM tabs WHERE id = ?1",
                params![tab_id],
                |r| {
                    Ok((
                        r.get(0)?,
                        r.get(1)?,
                        r.get(2)?,
                        r.get(3)?,
                        r.get(4)?,
                        r.get(5)?,
                        r.get(6)?,
                    ))
                },
            )
            .optional()?;

        let (conv_id, position, cur_url, cur_title, is_open_int, created_at, tab_kind) = match current {
            Some(c) => c,
            None => return Ok(None),
        };

        let final_url = new_url.unwrap_or(&cur_url).to_string();
        let raw_url_changed = final_url != cur_url;
        let canonical_cur = canonicalize_source_url(&cur_url);
        let canonical_final = canonicalize_source_url(&final_url);
        let canonical_changed = canonical_final != canonical_cur;

        let final_title = match new_title {
            Some(t) if !t.trim().is_empty() => t.to_string(),
            _ if canonical_changed => extract_domain(&final_url),
            _ => cur_title.clone(),
        };
        let title_changed = final_title != cur_title;

        let ts = now_epoch_secs_str();

        if canonical_changed {
            conn.execute(
                "UPDATE tabs SET url = ?2, title = ?3 WHERE id = ?1",
                params![tab_id, final_url, final_title],
            )?;

            // Deactivate prior sources for this tab so active context remains 1:1 with open tabs
            conn.execute(
                "UPDATE sources SET in_context = 0 WHERE tab_id = ?1",
                params![tab_id],
            )?;

            let domain = extract_domain(&final_url);
            let existing_src: Option<(String, Option<String>, Option<i64>)> = {
                let mut stmt = conn.prepare(
                    "SELECT id, url, captured_at, text_chars FROM sources WHERE conversation_id = ?1 ORDER BY added_at DESC, id DESC",
                )?;
                let rows = stmt.query_map(params![conv_id], |r| {
                    Ok((
                        r.get::<_, String>(0)?,
                        r.get::<_, String>(1)?,
                        r.get::<_, Option<String>>(2)?,
                        r.get::<_, Option<i64>>(3)?,
                    ))
                })?;
                let mut found = None;
                for item in rows.flatten() {
                    if canonicalize_source_url(&item.1) == canonical_final {
                        found = Some((item.0, item.2, item.3));
                        break;
                    }
                }
                found
            };

            let (src_id, prev_captured_at, prev_text_chars) = existing_src
                .unwrap_or_else(|| (gen_id("src"), None, None));

            if final_url != "about:blank" {
                conn.execute(
                    "INSERT INTO sources (id, conversation_id, tab_id, url, title, domain, in_context, added_at, captured_at, text_chars)
                     VALUES (?1, ?2, ?3, ?4, ?5, ?6, 1, ?7, ?8, ?9)
                     ON CONFLICT(id) DO UPDATE SET
                         tab_id = excluded.tab_id,
                         url = excluded.url,
                         title = excluded.title,
                         domain = excluded.domain,
                         in_context = 1,
                         added_at = excluded.added_at",
                    params![
                        src_id,
                        conv_id,
                        tab_id,
                        final_url,
                        final_title,
                        domain,
                        ts,
                        prev_captured_at,
                        prev_text_chars
                    ],
                )?;

                let hist_id = gen_id("hist");
                conn.execute(
                    "INSERT INTO history_log (id, conversation_id, tab_id, url, title, visited_at)
                     VALUES (?1, ?2, ?3, ?4, ?5, ?6)",
                    params![hist_id, conv_id, tab_id, final_url, final_title, ts],
                )?;
            }

            conn.execute(
                "UPDATE conversations SET last_active_at = ?2 WHERE id = ?1",
                params![conv_id, ts],
            )?;

            let updated_tab = BrowserTab {
                id: tab_id.to_string(),
                conversation_id: conv_id.clone(),
                position,
                url: final_url.clone(),
                title: final_title.clone(),
                is_open: is_open_int != 0,
                created_at,
                kind: tab_kind,
            };
            let new_source = SourceItem {
                id: src_id,
                conversation_id: conv_id,
                tab_id: Some(tab_id.to_string()),
                url: final_url,
                title: final_title,
                domain,
                in_context: true,
                added_at: ts,
                captured_at: prev_captured_at,
                text_chars: prev_text_chars,
            };
            return Ok(Some((updated_tab, Some(new_source))));
        }

        if raw_url_changed || title_changed {
            conn.execute(
                "UPDATE tabs SET url = ?2, title = ?3 WHERE id = ?1",
                params![tab_id, final_url, final_title],
            )?;
            conn.execute(
                "UPDATE sources SET url = ?2, title = ?3 WHERE tab_id = ?1",
                params![tab_id, final_url, final_title],
            )?;
            conn.execute(
                "UPDATE history_log SET url = ?2, title = ?3 WHERE tab_id = ?1 AND url = ?4",
                params![tab_id, final_url, final_title, cur_url],
            )?;
        }

        let updated_tab = BrowserTab {
            id: tab_id.to_string(),
            conversation_id: conv_id,
            position,
            url: final_url,
            title: final_title,
            is_open: is_open_int != 0,
            created_at,
            kind: tab_kind,
        };
        Ok(Some((updated_tab, None)))
    }

    pub fn get_tab(&self, tab_id: &str) -> SqlResult<Option<BrowserTab>> {
        let conn = self.conn.lock().unwrap();
        conn.query_row(
            "SELECT id, conversation_id, position, url, title, is_open, created_at, kind
             FROM tabs
             WHERE id = ?1",
            params![tab_id],
            |row| {
                let is_open_int: i32 = row.get(5)?;
                Ok(BrowserTab {
                    id: row.get(0)?,
                    conversation_id: row.get(1)?,
                    position: row.get(2)?,
                    url: row.get(3)?,
                    title: row.get(4)?,
                    is_open: is_open_int != 0,
                    created_at: row.get(6)?,
                    kind: row.get::<_, Option<String>>(7)?.unwrap_or_else(default_tab_kind),
                })
            },
        )
        .optional()
    }

    pub fn get_latest_source_for_tab(&self, tab_id: &str) -> SqlResult<Option<SourceItem>> {
        let conn = self.conn.lock().unwrap();
        conn.query_row(
            "SELECT id, conversation_id, tab_id, url, title, domain, in_context, added_at, captured_at, text_chars
             FROM sources
             WHERE tab_id = ?1
             ORDER BY added_at DESC, id DESC
             LIMIT 1",
            params![tab_id],
            |row| {
                let in_ctx: i32 = row.get(6)?;
                Ok(SourceItem {
                    id: row.get(0)?,
                    conversation_id: row.get(1)?,
                    tab_id: row.get(2)?,
                    url: row.get(3)?,
                    title: row.get(4)?,
                    domain: row.get(5)?,
                    in_context: in_ctx != 0,
                    added_at: row.get(7)?,
                    captured_at: row.get(8)?,
                    text_chars: row.get(9)?,
                })
            },
        )
        .optional()
    }

    pub fn mark_source_captured(&self, source_id: &str, text_chars: usize) -> SqlResult<()> {
        let conn = self.conn.lock().unwrap();
        let ts = now_epoch_secs_str();
        conn.execute(
            "UPDATE sources SET captured_at = ?2, text_chars = ?3 WHERE id = ?1",
            params![source_id, ts, text_chars as i64],
        )?;
        Ok(())
    }

    pub fn set_source_in_context(&self, source_id: &str, in_context: bool) -> SqlResult<()> {
        let conn = self.conn.lock().unwrap();
        conn.execute(
            "UPDATE sources SET in_context = ?2 WHERE id = ?1",
            params![source_id, if in_context { 1 } else { 0 }],
        )?;
        Ok(())
    }

    pub fn add_message(
        &self,
        conversation_id: &str,
        role: &str,
        content: &str,
        model: Option<&str>,
        source_ids_json: Option<&str>,
    ) -> SqlResult<ChatMessage> {
        self.add_message_with_citations(
            conversation_id,
            role,
            content,
            model,
            source_ids_json,
            None,
            None,
            None,
        )
    }

    pub fn add_message_with_citations(
        &self,
        conversation_id: &str,
        role: &str,
        content: &str,
        model: Option<&str>,
        source_ids_json: Option<&str>,
        citations_ok: Option<i64>,
        citations_flagged: Option<i64>,
        citation_check_json: Option<&str>,
    ) -> SqlResult<ChatMessage> {
        self.add_message_full(
            conversation_id,
            role,
            content,
            model,
            source_ids_json,
            citations_ok,
            citations_flagged,
            citation_check_json,
            None,
        )
    }

    pub fn add_message_full(
        &self,
        conversation_id: &str,
        role: &str,
        content: &str,
        model: Option<&str>,
        source_ids_json: Option<&str>,
        citations_ok: Option<i64>,
        citations_flagged: Option<i64>,
        citation_check_json: Option<&str>,
        extras_json: Option<&str>,
    ) -> SqlResult<ChatMessage> {
        let conn = self.conn.lock().unwrap();
        let id = gen_id("msg");
        let ts = now_epoch_secs_str();
        conn.execute(
            "INSERT INTO messages (id, conversation_id, role, content, model, source_ids_json, created_at, citations_ok, citations_flagged, citation_check_json, extras_json)
             VALUES (?1, ?2, ?3, ?4, ?5, ?6, ?7, ?8, ?9, ?10, ?11)",
            params![
                id,
                conversation_id,
                role,
                content,
                model,
                source_ids_json,
                ts,
                citations_ok,
                citations_flagged,
                citation_check_json,
                extras_json
            ],
        )?;
        conn.execute(
            "UPDATE conversations SET last_active_at = ?2 WHERE id = ?1",
            params![conversation_id, ts],
        )?;
        Ok(ChatMessage {
            id,
            conversation_id: conversation_id.to_string(),
            role: role.to_string(),
            content: content.to_string(),
            model: model.map(|s| s.to_string()),
            source_ids_json: source_ids_json.map(|s| s.to_string()),
            created_at: ts,
            citations_ok,
            citations_flagged,
            citation_check_json: citation_check_json.map(|s| s.to_string()),
            extras_json: extras_json.map(|s| s.to_string()),
        })
    }

    pub fn list_bookmarks(&self) -> SqlResult<Vec<BookmarkItem>> {
        let conn = self.conn.lock().unwrap();
        let mut stmt = conn.prepare(
            "SELECT id, title, url, position, created_at, favicon_url
             FROM bookmarks
             ORDER BY position ASC, created_at ASC",
        )?;
        let rows = stmt.query_map([], |row| {
            Ok(BookmarkItem {
                id: row.get(0)?,
                title: row.get(1)?,
                url: row.get(2)?,
                position: row.get(3)?,
                created_at: row.get(4)?,
                favicon_url: row.get(5)?,
            })
        })?;
        rows.collect()
    }

    pub fn add_bookmark(&self, title: &str, url: &str) -> SqlResult<BookmarkItem> {
        self.add_bookmark_with_favicon(title, url, None)
    }

    pub fn add_bookmark_with_favicon(
        &self,
        title: &str,
        url: &str,
        favicon_url: Option<&str>,
    ) -> SqlResult<BookmarkItem> {
        let conn = self.conn.lock().unwrap();
        let id = gen_id("bm");
        let ts = now_epoch_secs_str();
        let clean_favicon = favicon_url
            .map(|s| s.trim())
            .filter(|s| !s.is_empty())
            .map(|s| s.to_string());
        let next_pos: i32 = conn
            .query_row(
                "SELECT COALESCE(MAX(position) + 1, 0) FROM bookmarks",
                [],
                |r| r.get(0),
            )
            .unwrap_or(0);
        conn.execute(
            "INSERT INTO bookmarks (id, title, url, position, created_at, favicon_url)
             VALUES (?1, ?2, ?3, ?4, ?5, ?6)",
            params![id, title, url, next_pos, ts, clean_favicon],
        )?;
        Ok(BookmarkItem {
            id,
            title: title.to_string(),
            url: url.to_string(),
            position: next_pos,
            created_at: ts,
            favicon_url: clean_favicon,
        })
    }

    pub fn set_bookmark_favicon(&self, bookmark_id: &str, favicon_url: &str) -> SqlResult<()> {
        let conn = self.conn.lock().unwrap();
        let trimmed = favicon_url.trim();
        let val: Option<&str> = if trimmed.is_empty() { None } else { Some(trimmed) };
        conn.execute(
            "UPDATE bookmarks SET favicon_url = ?1 WHERE id = ?2",
            params![val, bookmark_id],
        )?;
        Ok(())
    }

    pub fn remove_bookmark(&self, bookmark_id: &str) -> SqlResult<()> {
        let conn = self.conn.lock().unwrap();
        conn.execute("DELETE FROM bookmarks WHERE id = ?1", params![bookmark_id])?;
        Ok(())
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_v1_to_v2_migration_drops_seeds_and_preserves_user_conversations() {
        let conn = Connection::open_in_memory().unwrap();
        conn.execute_batch(
            "
            PRAGMA foreign_keys = ON;
            CREATE TABLE conversations (
                id TEXT PRIMARY KEY,
                intent_title TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'active',
                pinned INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL
            );
            CREATE TABLE attached_pages (
                id TEXT PRIMARY KEY,
                conversation_id TEXT NOT NULL,
                url TEXT NOT NULL,
                title TEXT NOT NULL,
                pane_index INTEGER NOT NULL DEFAULT 0,
                FOREIGN KEY (conversation_id) REFERENCES conversations(id) ON DELETE CASCADE
            );
            CREATE TABLE thread_notes (
                id TEXT PRIMARY KEY,
                conversation_id TEXT NOT NULL,
                author TEXT NOT NULL DEFAULT 'user',
                content TEXT NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY (conversation_id) REFERENCES conversations(id) ON DELETE CASCADE
            );
            CREATE TABLE history_log (
                id TEXT PRIMARY KEY,
                conversation_id TEXT NOT NULL,
                url TEXT NOT NULL,
                title TEXT NOT NULL,
                visited_at TEXT NOT NULL,
                FOREIGN KEY (conversation_id) REFERENCES conversations(id) ON DELETE CASCADE
            );
            ",
        )
        .unwrap();

        // Insert the 3 untouched seed conversations from Phase 0
        for (cid, note_id) in [
            ("conv-1", "note-1-1"),
            ("conv-2", "note-2-1"),
            ("conv-3", "note-3-1"),
        ] {
            conn.execute(
                "INSERT INTO conversations (id, intent_title, status, pinned, created_at) VALUES (?1, 'Seed Title', 'active', 1, '1700000000')",
                params![cid],
            )
            .unwrap();
            conn.execute(
                "INSERT INTO thread_notes (id, conversation_id, author, content, created_at) VALUES (?1, ?2, 'system', 'Seed note', '1700000000')",
                params![note_id, cid],
            )
            .unwrap();
        }

        // Insert 1 real user conversation with an attached page and a user note
        conn.execute(
            "INSERT INTO conversations (id, intent_title, status, pinned, created_at) VALUES ('conv-user-99', 'Greenland story research', 'active', 1, '1700000500')",
            [],
        )
        .unwrap();
        conn.execute(
            "INSERT INTO attached_pages (id, conversation_id, url, title, pane_index) VALUES ('p-99-0', 'conv-user-99', 'https://www.dw.com/en/greenland', 'DW Greenland', 0)",
            [],
        )
        .unwrap();
        conn.execute(
            "INSERT INTO thread_notes (id, conversation_id, author, content, created_at) VALUES ('n-99-1', 'conv-user-99', 'user', 'Key note about Denmark response', '1700000600')",
            [],
        )
        .unwrap();

        // Run v1 -> v2 migration
        DbState::init_connection(&conn).unwrap();

        let state = DbState {
            conn: Mutex::new(conn),
            db_path: PathBuf::from(":memory:"),
        };

        let convs = state.list_conversations().unwrap();
        assert_eq!(convs.len(), 1, "Untouched seeds must be dropped and user conversation preserved");
        assert_eq!(convs[0].id, "conv-user-99");
        assert_eq!(convs[0].title, "Greenland story research");
        assert_eq!(convs[0].source_count, 1);

        let detail = state.get_conversation("conv-user-99").unwrap();
        assert_eq!(detail.tabs.len(), 1);
        assert_eq!(detail.tabs[0].url, "https://www.dw.com/en/greenland");
        assert_eq!(detail.sources.len(), 1);
        assert_eq!(detail.sources[0].domain, "dw.com");
        assert_eq!(detail.messages.len(), 1);
        assert_eq!(detail.messages[0].role, "user");
        assert_eq!(detail.messages[0].content, "Key note about Denmark response");
    }

    #[test]
    fn test_history_log_dedupes_title_changes() {
        let conn = Connection::open_in_memory().unwrap();
        DbState::init_connection(&conn).unwrap();
        let state = DbState {
            conn: Mutex::new(conn),
            db_path: PathBuf::from(":memory:"),
        };

        let conv = state.create_conversation("test history", "chat").unwrap();
        let (tab, _) = state
            .open_tab(&conv.id, "https://example.com/a", Some("Initial Title"))
            .unwrap();

        let detail_initial = state.get_conversation(&conv.id).unwrap();
        assert_eq!(detail_initial.history.len(), 1);

        // Title change on the same URL must NOT add a history row
        state
            .record_tab_navigation_or_title(&tab.id, None, Some("Updated Title After Load"))
            .unwrap();

        let detail_after_title = state.get_conversation(&conv.id).unwrap();
        assert_eq!(
            detail_after_title.history.len(),
            1,
            "Title change must not add a duplicate history_log row"
        );
        assert_eq!(detail_after_title.tabs[0].title, "Updated Title After Load");
        assert_eq!(detail_after_title.sources.len(), 1);

        // Navigating to a new URL MUST add a history row and a new source row
        state
            .record_tab_navigation_or_title(
                &tab.id,
                Some("https://example.com/b"),
                Some("Page B"),
            )
            .unwrap();

        let detail_after_nav = state.get_conversation(&conv.id).unwrap();
        assert_eq!(detail_after_nav.history.len(), 2);
        assert_eq!(detail_after_nav.sources.len(), 2);
    }

    #[test]
    fn test_bookmarks_and_direct_conversation_auto_archive() {
        let conn = Connection::open_in_memory().unwrap();
        DbState::init_connection(&conn).unwrap();
        let state = DbState {
            conn: Mutex::new(conn),
            db_path: PathBuf::from(":memory:"),
        };

        // First-run in v0.5 has 0 seeded bookmarks
        let bms = state.list_bookmarks().unwrap();
        assert_eq!(bms.len(), 0);
        let added = state.add_bookmark("Rust Docs", "https://doc.rust-lang.org").unwrap();
        assert_eq!(state.list_bookmarks().unwrap().len(), 1);
        assert_eq!(added.favicon_url, None);
        state
            .set_bookmark_favicon(&added.id, "data:image/png;base64,AAAA")
            .unwrap();
        let updated_bms = state.list_bookmarks().unwrap();
        assert_eq!(
            updated_bms[0].favicon_url.as_deref(),
            Some("data:image/png;base64,AAAA")
        );
        let added_with_icon = state
            .add_bookmark_with_favicon(
                "WaniKani",
                "https://www.wanikani.com/dashboard",
                Some("https://www.wanikani.com/favicon.ico"),
            )
            .unwrap();
        assert_eq!(
            added_with_icon.favicon_url.as_deref(),
            Some("https://www.wanikani.com/favicon.ico")
        );
        state.remove_bookmark(&added_with_icon.id).unwrap();
        state.remove_bookmark(&added.id).unwrap();
        assert_eq!(state.list_bookmarks().unwrap().len(), 0);

        // Insert a 25-hour-old untouched direct conversation (0 messages, 0 open tabs)
        let stale_ts = (now_epoch_secs_str().parse::<u64>().unwrap_or(1_700_100_000).saturating_sub(90_000)).to_string();
        {
            let c = state.conn.lock().unwrap();
            c.execute(
                "INSERT INTO conversations (id, title, status, pinned, origin, created_at, last_active_at)
                 VALUES ('conv-direct-stale', 'dw.com', 'active', 0, 'direct', ?1, ?1)",
                params![stale_ts],
            )
            .unwrap();
        }
        state.auto_archive_stale_direct_conversations().unwrap();
        let stale_conv = state.get_conversation("conv-direct-stale").unwrap();
        assert_eq!(stale_conv.conversation.status, "archived");
    }

    #[test]
    fn test_conversations_summary_column_migration_and_update() {
        let conn = Connection::open_in_memory().unwrap();
        // Simulate an existing v2 DB created before M9 (without `summary` column on `conversations`)
        conn.execute_batch(
            "
            CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
            INSERT INTO meta (key, value) VALUES ('schema_version', '2');
            CREATE TABLE conversations (
                id TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'active',
                pinned INTEGER NOT NULL DEFAULT 0,
                origin TEXT NOT NULL DEFAULT 'chat',
                created_at TEXT NOT NULL,
                last_active_at TEXT NOT NULL
            );
            INSERT INTO conversations (id, title, status, pinned, origin, created_at, last_active_at)
            VALUES ('conv-m9-mig', 'Pre-M9 Conversation', 'active', 0, 'chat', '1700000000', '1700000000');
            ",
        )
        .unwrap();

        DbState::init_connection(&conn).unwrap();
        let state = DbState {
            conn: Mutex::new(conn),
            db_path: PathBuf::from(":memory:"),
        };

        let before = state.get_conversation("conv-m9-mig").unwrap();
        assert_eq!(before.conversation.summary, None);

        let long_summary = "S".repeat(750);
        state
            .set_conversation_summary("conv-m9-mig", &long_summary)
            .unwrap();

        let after = state.get_conversation("conv-m9-mig").unwrap();
        assert_eq!(after.conversation.summary.as_deref().map(|s| s.len()), Some(600));
    }

    #[test]
    fn test_messages_citation_columns_migration_and_persistence() {
        let conn = Connection::open_in_memory().unwrap();
        conn.execute_batch(
            "
            CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
            INSERT INTO meta (key, value) VALUES ('schema_version', '2');
            CREATE TABLE conversations (
                id TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'active',
                pinned INTEGER NOT NULL DEFAULT 0,
                origin TEXT NOT NULL DEFAULT 'chat',
                created_at TEXT NOT NULL,
                last_active_at TEXT NOT NULL
            );
            CREATE TABLE messages (
                id TEXT PRIMARY KEY,
                conversation_id TEXT NOT NULL,
                role TEXT NOT NULL DEFAULT 'user',
                content TEXT NOT NULL,
                model TEXT NULL,
                source_ids_json TEXT NULL,
                created_at TEXT NOT NULL
            );
            INSERT INTO conversations (id, title, status, pinned, origin, created_at, last_active_at)
            VALUES ('conv-m10', 'Citation Test', 'active', 0, 'chat', '1700000000', '1700000000');
            ",
        )
        .unwrap();

        DbState::init_connection(&conn).unwrap();
        let state = DbState {
            conn: Mutex::new(conn),
            db_path: PathBuf::from(":memory:"),
        };

        let check_json = r#"[{"n":1,"sentence_idx":0,"ok":false,"missing":["999"]}]"#;
        state
            .add_message_with_citations(
                "conv-m10",
                "assistant",
                "The price is 999 [1].",
                Some("gemma-4-e4b"),
                Some(r#"["src-1"]"#),
                Some(0),
                Some(1),
                Some(check_json),
            )
            .unwrap();

        let detail = state.get_conversation("conv-m10").unwrap();
        assert_eq!(detail.messages.len(), 1);
        assert_eq!(detail.messages[0].citations_ok, Some(0));
        assert_eq!(detail.messages[0].citations_flagged, Some(1));
        assert_eq!(
            detail.messages[0].citation_check_json.as_deref(),
            Some(check_json)
        );
    }

    #[test]
    fn test_tabs_kind_migration_and_pinned_mail_conversation() {
        let conn = Connection::open_in_memory().unwrap();
        // Simulate pre-M11 v2 database without `tabs.kind`
        conn.execute_batch(
            "
            CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
            INSERT INTO meta (key, value) VALUES ('schema_version', '2');
            CREATE TABLE conversations (
                id TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'active',
                pinned INTEGER NOT NULL DEFAULT 0,
                origin TEXT NOT NULL DEFAULT 'chat',
                created_at TEXT NOT NULL,
                last_active_at TEXT NOT NULL
            );
            CREATE TABLE tabs (
                id TEXT PRIMARY KEY,
                conversation_id TEXT NOT NULL,
                position INTEGER NOT NULL DEFAULT 0,
                url TEXT NOT NULL,
                title TEXT NOT NULL,
                is_open INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL,
                FOREIGN KEY (conversation_id) REFERENCES conversations(id) ON DELETE CASCADE
            );
            INSERT INTO conversations (id, title, status, pinned, origin, created_at, last_active_at)
            VALUES ('conv-pre-m11', 'Pre-M11', 'active', 0, 'chat', '1700000000', '1700000000');
            INSERT INTO tabs (id, conversation_id, position, url, title, is_open, created_at)
            VALUES ('tab-legacy-1', 'conv-pre-m11', 0, 'https://dw.com', 'DW', 1, '1700000000');
            ",
        )
        .unwrap();

        DbState::init_connection(&conn).unwrap();
        let state = DbState {
            conn: Mutex::new(conn),
            db_path: PathBuf::from(":memory:"),
        };

        // 1. Existing tab defaults to kind = 'site'
        let pre_detail = state.get_conversation("conv-pre-m11").unwrap();
        assert_eq!(pre_detail.tabs.len(), 1);
        assert_eq!(pre_detail.tabs[0].kind, "site");

        // 2. Pinned Mail conversation creation & protection against unpin/archive/delete
        let mail_conv = state.ensure_mail_conversation().unwrap();
        assert_eq!(mail_conv.origin, "mail");
        assert!(mail_conv.pinned);
        assert_eq!(mail_conv.status, "active");

        let after_unpin = state.pin_conversation(&mail_conv.id).unwrap();
        assert!(after_unpin.pinned, "Mail conversation must stay pinned");

        let after_archive = state.archive_conversation(&mail_conv.id, true).unwrap();
        assert_eq!(after_archive.status, "active", "Mail conversation cannot be archived");

        assert!(
            state.delete_conversation(&mail_conv.id).is_err(),
            "Mail conversation cannot be deleted"
        );

        // 3. Opening mail and compose tabs in Mail conversation
        let (mail_tab, mail_src) = state
            .open_tab_with_kind(
                &mail_conv.id,
                "satzmail://message/msg-42",
                Some("Re: Lisbon dates"),
                Some("mail"),
            )
            .unwrap();
        assert_eq!(mail_tab.kind, "mail");
        assert_eq!(mail_src.id, "mail:msg-42");

        let (compose_tab, _) = state
            .open_tab_with_kind(
                &mail_conv.id,
                "satzmail://compose/draft-1",
                Some("compose: Re: Lisbon dates"),
                Some("compose"),
            )
            .unwrap();
        assert_eq!(compose_tab.kind, "compose");
    }

    #[test]
    fn test_canonical_source_url_dedupe() {
        assert_eq!(
            canonicalize_source_url("https://www.dw.com/en/top-stories?utm_source=rss&utm_medium=web#section-2"),
            canonicalize_source_url("https://www.dw.com/en/top-stories/")
        );

        let conn = Connection::open_in_memory().unwrap();
        DbState::init_connection(&conn).unwrap();
        let state = DbState {
            conn: Mutex::new(conn),
            db_path: PathBuf::from(":memory:"),
        };

        let conv = state.create_conversation("dedupe test", "chat").unwrap();
        let (tab, src1) = state
            .open_tab(&conv.id, "https://www.dw.com/en", Some("DW"))
            .unwrap();
        state.mark_source_captured(&src1.id, 4210).unwrap();

        // Redirect/hash/utm on the same canonical URL must NOT create a duplicate source row
        state
            .record_tab_navigation_or_title(
                &tab.id,
                Some("https://www.dw.com/en/?utm_source=test#top"),
                Some("DW Top Stories"),
            )
            .unwrap();

        let detail = state.get_conversation(&conv.id).unwrap();
        assert_eq!(
            detail.sources.len(),
            1,
            "Canonical URL variations must deduplicate to a single source row"
        );
        assert_eq!(detail.sources[0].id, src1.id);
        assert_eq!(detail.sources[0].text_chars, Some(4210));
    }

    #[test]
    fn test_pinned_news_conversation_ordering_and_protections() {
        let conn = Connection::open_in_memory().unwrap();
        DbState::init_connection(&conn).unwrap();
        let state = DbState {
            conn: Mutex::new(conn),
            db_path: PathBuf::from(":memory:"),
        };

        let _chat = state.create_conversation("General chat", "chat").unwrap();
        let news_conv = state.ensure_news_conversation().unwrap();
        assert_eq!(news_conv.id, "conv-news");
        assert_eq!(news_conv.origin, "news");
        assert!(news_conv.pinned);
        assert_eq!(news_conv.status, "active");

        let mail_conv = state.ensure_mail_conversation().unwrap();
        assert_eq!(mail_conv.origin, "mail");

        let after_unpin = state.pin_conversation(&news_conv.id).unwrap();
        assert!(after_unpin.pinned, "News conversation must stay pinned");

        let after_archive = state.archive_conversation(&news_conv.id, true).unwrap();
        assert_eq!(after_archive.status, "active", "News conversation cannot be archived");

        assert!(
            state.delete_conversation(&news_conv.id).is_err(),
            "News conversation cannot be deleted"
        );

        let list = state.list_conversations().unwrap();
        assert!(list.len() >= 3);
        assert_eq!(list[0].origin, "mail");
        assert_eq!(list[1].origin, "news");
    }

    #[test]
    fn test_pinned_settings_conversation_ordering_and_protections() {
        let conn = Connection::open_in_memory().unwrap();
        DbState::init_connection(&conn).unwrap();
        let state = DbState {
            conn: Mutex::new(conn),
            db_path: PathBuf::from(":memory:"),
        };

        let _chat = state.create_conversation("General chat", "chat").unwrap();
        let settings_conv = state.ensure_settings_conversation().unwrap();
        assert_eq!(settings_conv.id, "conv-settings");
        assert_eq!(settings_conv.origin, "settings");
        assert!(settings_conv.pinned);
        assert_eq!(settings_conv.status, "active");

        let news_conv = state.ensure_news_conversation().unwrap();
        let mail_conv = state.ensure_mail_conversation().unwrap();
        assert_eq!(news_conv.origin, "news");
        assert_eq!(mail_conv.origin, "mail");

        let after_unpin = state.pin_conversation(&settings_conv.id).unwrap();
        assert!(after_unpin.pinned, "Settings conversation must stay pinned");

        let after_archive = state.archive_conversation(&settings_conv.id, true).unwrap();
        assert_eq!(
            after_archive.status, "active",
            "Settings conversation cannot be archived"
        );

        assert!(
            state.delete_conversation(&settings_conv.id).is_err(),
            "Settings conversation cannot be deleted"
        );

        let list = state.list_conversations().unwrap();
        assert!(list.len() >= 4);
        assert_eq!(list[0].origin, "mail");
        assert_eq!(list[1].origin, "news");
        assert_eq!(list[2].origin, "settings");
    }

    #[test]
    fn test_pinned_drives_conversation_ordering_and_protections() {
        let conn = Connection::open_in_memory().unwrap();
        DbState::init_connection(&conn).unwrap();
        let state = DbState {
            conn: Mutex::new(conn),
            db_path: PathBuf::from(":memory:"),
        };

        let _chat = state.create_conversation("General chat", "chat").unwrap();
        let drives_conv = state.ensure_drives_conversation().unwrap();
        assert_eq!(drives_conv.id, "conv-drives");
        assert_eq!(drives_conv.origin, "drives");
        assert!(drives_conv.pinned);
        assert_eq!(drives_conv.status, "active");

        let settings_conv = state.ensure_settings_conversation().unwrap();
        let news_conv = state.ensure_news_conversation().unwrap();
        let mail_conv = state.ensure_mail_conversation().unwrap();
        assert_eq!(settings_conv.origin, "settings");
        assert_eq!(news_conv.origin, "news");
        assert_eq!(mail_conv.origin, "mail");

        let after_unpin = state.pin_conversation(&drives_conv.id).unwrap();
        assert!(after_unpin.pinned, "Drives conversation must stay pinned");

        let after_archive = state.archive_conversation(&drives_conv.id, true).unwrap();
        assert_eq!(
            after_archive.status, "active",
            "Drives conversation cannot be archived"
        );

        assert!(
            state.delete_conversation(&drives_conv.id).is_err(),
            "Drives conversation cannot be deleted"
        );

        let list = state.list_conversations().unwrap();
        assert!(list.len() >= 5);
        assert_eq!(list[0].origin, "mail");
        assert_eq!(list[1].origin, "news");
        assert_eq!(list[2].origin, "drives");
        assert_eq!(list[3].origin, "settings");
    }

    #[test]
    fn test_news_settings_and_perspectives_conversations_protected() {
        let conn = Connection::open_in_memory().unwrap();
        DbState::init_connection(&conn).unwrap();
        let state = DbState {
            conn: Mutex::new(conn),
            db_path: PathBuf::from(":memory:"),
        };

        let ns = state.ensure_news_settings_conversation().unwrap();
        let np = state.ensure_news_perspectives_conversation().unwrap();
        assert_eq!(ns.id, "conv-news-settings");
        assert_eq!(ns.origin, "news_settings");
        assert_eq!(np.id, "conv-news-perspectives");
        assert_eq!(np.origin, "news_perspectives");
        assert!(state.delete_conversation(&ns.id).is_err());
        assert!(state.delete_conversation(&np.id).is_err());
        assert_eq!(state.archive_conversation(&ns.id, true).unwrap().status, "active");
        assert_eq!(state.archive_conversation(&np.id, true).unwrap().status, "active");
    }
}
