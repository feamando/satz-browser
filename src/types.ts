export interface Conversation {
  id: string;
  intent_title: string;
  status: string;
  pinned: boolean;
  created_at: string;
}

export interface AttachedPage {
  id: string;
  conversation_id: string;
  url: string;
  title: string;
  pane_index: number;
}

export interface ThreadNote {
  id: string;
  conversation_id: string;
  author: string;
  content: string;
  created_at: string;
}

export interface HistoryEntry {
  id: string;
  conversation_id: string;
  url: string;
  title: string;
  visited_at: string;
}

export interface ConversationBundle {
  conversation: Conversation;
  attached_pages: AttachedPage[];
  notes: ThreadNote[];
  history: HistoryEntry[];
}

export interface PaneBoundsSpec {
  pane_index: number;
  url: string;
  x: number;
  y: number;
  width: number;
  height: number;
}

export interface ChildPaneEventPayload {
  pane_index: number;
  event_type: "load_started" | "load_finished" | "title_changed";
  url: string | null;
  title: string | null;
}

export type ViewMode = "thread" | "focus" | "compare";
