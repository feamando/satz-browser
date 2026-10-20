import { IS_MAC } from "./state";

export interface ShortcutHandlers {
  onNewConversation: () => void;
  onFilterConversations: () => void;
  onNewTab: () => void;
  onCloseTab: () => void;
  onSelectTabByNumber: (num: number) => void;
  onFocusAddressBar: () => void;
  onToggleAgentRail: () => void;
  onToggleCompare: () => void;
  onBookmarkCurrentPage: () => void;
  onEscape: () => void;
}

export function isModKey(e: KeyboardEvent | MouseEvent): boolean {
  return IS_MAC ? e.metaKey : e.ctrlKey;
}

export function bindKeyboardShortcuts(handlers: ShortcutHandlers): void {
  window.addEventListener("keydown", (e: KeyboardEvent) => {
    const mod = isModKey(e);
    const key = e.key.toLowerCase();

    if (e.key === "Escape") {
      handlers.onEscape();
      return;
    }

    if (!mod || e.altKey) return;

    // Leave Mod+F untouched for native find-in-page
    if (key === "f") {
      return;
    }

    if (key === "n") {
      e.preventDefault();
      handlers.onNewConversation();
      return;
    }

    if (key === "k") {
      e.preventDefault();
      handlers.onFilterConversations();
      return;
    }

    if (key === "t") {
      e.preventDefault();
      handlers.onNewTab();
      return;
    }

    if (key === "w") {
      e.preventDefault();
      handlers.onCloseTab();
      return;
    }

    if (key === "l") {
      e.preventDefault();
      handlers.onFocusAddressBar();
      return;
    }

    if (key === "j") {
      e.preventDefault();
      handlers.onToggleAgentRail();
      return;
    }

    if (key === "m") {
      e.preventDefault();
      handlers.onToggleCompare();
      return;
    }

    if (key === "d") {
      e.preventDefault();
      handlers.onBookmarkCurrentPage();
      return;
    }

    if (/^[1-9]$/.test(key)) {
      e.preventDefault();
      handlers.onSelectTabByNumber(Number(key));
    }
  });
}
