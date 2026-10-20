import { escapeHtml, state } from "./state";

export interface KnowledgeActions {
  onTogglePauseLearning: (paused: boolean) => void;
  onDeletePassage: (passageId: string) => void;
  onCloseKnowledgeView: () => void;
}

export function renderKnowledgeView(
  container: HTMLElement,
  actions: KnowledgeActions
): void {
  const kb = state.knowledge;

  container.innerHTML = `
    <div class="knowledge-view">
      <div class="knowledge-section">
        <div class="panel-header">
          <span>knowledge base (local store)</span>
          <div>
            <button id="kb-pause-btn" class="${kb.pause_learning ? "active" : ""}">
              [pause learning: ${kb.pause_learning ? "on" : "off"}]
            </button>
            <button id="kb-close-btn">[close]</button>
          </div>
        </div>
        <div class="muted">
          ingest queue: ${kb.queue_len} · everything browsed and asked stays on this machine. deleting a conversation deletes its passages.
        </div>
      </div>

      <div class="knowledge-section">
        <div class="panel-header">
          <span>top domains (${kb.top_domains.length})</span>
        </div>
        ${
          kb.top_domains.length === 0
            ? `<div class="muted">no domains recorded yet</div>`
            : kb.top_domains
                .map(
                  (d) => `
              <div class="rail-row">
                <span>${escapeHtml(d.domain)}</span>
                <span class="muted">${d.visits} visits · score ${d.score.toFixed(1)}</span>
              </div>
            `
                )
                .join("")
        }
      </div>

      <div class="knowledge-section">
        <div class="panel-header">
          <span>top topics (${kb.top_topics.length})</span>
        </div>
        ${
          kb.top_topics.length === 0
            ? `<div class="muted">no topics extracted yet</div>`
            : kb.top_topics
                .map(
                  (t) => `
              <div class="rail-row">
                <span>${escapeHtml(t.topic)}</span>
                <span class="muted">weight ${t.weight.toFixed(2)}</span>
              </div>
            `
                )
                .join("")
        }
      </div>

      <div class="knowledge-section">
        <div class="panel-header">
          <span>recent passages (${kb.passages.length})</span>
        </div>
        ${
          kb.passages.length === 0
            ? `<div class="muted">no passages ingested yet</div>`
            : kb.passages
                .map(
                  (p) => `
              <div class="source-row">
                <div class="source-row-top">
                  <span>${escapeHtml(p.entity || p.url)}</span>
                  <button class="rail-menu-btn" data-delete-passage="${escapeHtml(p.id)}">[delete]</button>
                </div>
                <div class="muted">${escapeHtml(p.url)}</div>
                <div>${escapeHtml(p.text.slice(0, 260))}</div>
              </div>
            `
                )
                .join("")
        }
      </div>
    </div>
  `;

  container.querySelector("#kb-pause-btn")?.addEventListener("click", () => {
    actions.onTogglePauseLearning(!kb.pause_learning);
  });

  container.querySelector("#kb-close-btn")?.addEventListener("click", () => {
    actions.onCloseKnowledgeView();
  });

  container.querySelectorAll("[data-delete-passage]").forEach((btn) => {
    btn.addEventListener("click", () => {
      const id = (btn as HTMLElement).getAttribute("data-delete-passage");
      if (id) actions.onDeletePassage(id);
    });
  });
}
