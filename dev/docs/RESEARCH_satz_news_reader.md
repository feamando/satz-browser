# Research Notes: Satz / Planck 3.0 News & Knowledge Reader

Date: 2026-11-16
Scope: Read-only synthesis of recent Planck 3.0 and Satz work in `../sgs` (`SETUP_092026_planck3.md`, `SETUP_planck_20261008.md`, `SETUP_planck_20261009.md`, `SETUP_planck_20261019.md`, `SETUP_planck_20261020.md`, `SETUP_planck_20261109.md`, `results/planck3/REPORT.md`, `src/planck3/*`, `config/planck3/source_registry.json`, `satz/*`) and comparison against the current `satz-browser` codebase.

---

## 1. Executive Summary of Recent News Reader Work (`../sgs`)

Between October 2026 and November 2026 (Rounds 4 through 11), the Planck 3.0 research track evolved from a small neural retrieval policy (`planck-g2`) into an auditable **search -> read -> weigh -> write** architecture designed specifically to handle breaking news, long-tail facts, and practical service queries without baking volatile world facts into model weights.

Five empirical findings define the latest state as of **Round 11 (2026-11-09)**:

1. **Separated Reading from Weighing (`read -> weigh -> write`):** A neural or LLM reader emits raw relevance/extraction probabilities `r in [0, 1]` *without seeing trust scores*, so personal preferences cannot bias span extraction (`src/planck3/readers.py`). All source scoring, duplicate/mirror family collapsing, agreement bonuses, conflict penalties, and question-type risk penalties happen in pure deterministic arithmetic (`src/planck3/consolidate.py`).
2. **Cross-Encoder Reader Win over Frozen Bi-Encoders (`x-hertz`):** On NewsQA (859 pools) and the fresh 220-question benchmark, 101M Planck 1.3 and Planck 1.5 failed to learn news reading (`0.461` choice acc vs `0.477` lexical ranker, `p = 0.243`), whereas fine-tuned 641M Hertz 1.2 (`x-hertz_rc`, int8 on CPU, `888.2 MB`) jumped +10.2 pts on NewsQA (`0.580`, `p = 2.73e-11`) and shipped in Round 9 (`0.491` overall, `0.512` on fresh portal news vs Gemma `0.537` in Round 9; `3.35s` CPU latency).
3. **Round 11 Diagnosis of the Remaining Gemma Gap (`diagnosis = "size"`):** On cached `fresh10` (220 questions), Gemma scored `0.609` vs shipped `x-hertz` `0.486`. Round 11 controlled view size (`top16` vs `top20` vs `top32`) and full-page fetching (`open_below = 11.0`, always read 2 pages):
   - Oracle reach in the top-16 candidate view was already **0.882** (`0.886` top-20, `0.895` top-32).
   - Expanding `x-hertz` to `top32` (`0.482`) or forcing 2 full page fetches (`0.482`) closed **0** of the gap.
   - At **identical evidence (`D_gem16P` vs `D_shipP`)**, Gemma beat `x-hertz` by **+12.7 pts** (`0.609` vs `0.482`, `45` vs `17` only-right, `McNemar p = 0.000497`).
   - **Implication for Satz Browser:** Keeping `x-hertz` int8 as a fast, zero-cost local extractive candidate scorer is sound, *and* expanding model routing so larger local models (`gemma-4-e4b`) and configured cloud models (`gemini`, `anthropic`, `openai`, `mistral`) handle complex news synthesis, query formulation, and multi-source conflict analysis directly addresses the Round 11 comprehension ceiling.
4. **Hand-Scored Source Registry & 30% Personal Trust Cap:** The Round 5 `Registry` (`config/planck3/source_registry.json`, `src/planck3/registry.py`) replaces opaque usage log-odds with an inspectable 0-10 rubric across **31 categories**, **222 explicit domains**, **35 suffix rules**, **6 keyword rules**, and **3 duplicate families**. Personal trust overrides are strictly capped (`effective = 0.7 * system + 0.3 * personal`), with every card computing a **system-only counterfactual (`divergence`)** whenever user scores shift an answer or band.
5. **Deterministic Grounding & Fail-Safe Writer:** Free-text writers (`gemma`, `hertz`, `planck`) must pass `faithful()` (`src/planck3/writer.py`: contains answer, cites only listed sources, no ungrounded numbers or proper nouns, <= 60 words for short answers), automatically falling back to `TemplateWriter` on any hallucination.

---

## 2. Reader Architecture & Principles in Detail

### 2.1 Pipeline Stages (`src/planck3/answer.py`)

Every query runs through a deterministic state machine (`Answerer.run`):

1. **Question Classification (`src/planck3/qtype.py`):**
   - Classifies query into `news`, `encyclopedic`, or `general_info` via deterministic regex rules over event verbs (`won`, `elected`, `killed`, `crash`, `sanctions`, `launched`, etc.), recency cues (`today`, `latest`, current year), and practical service terms (`airport`, `opening hours`, `visa`, `timetable`, after stripping capitalized proper nouns).
   - Assigns an explicit base confidence penalty (`PENALTY = {"news": 2.0, "encyclopedic": 1.0, "general_info": 0.0}`), reflecting that early news reports frequently contain preliminary casualties, shifting tallies, or conflicting claims.
2. **Search + Relevance Check (`src/planck3/web.py`):**
   - Cached (`WebCache`, SHA-1 keyed) across `live`, `replay`, and `refresh` modes with per-host polite rate limits (`MIN_SECONDS_PER_HOST = 1.0`, `MIN_SECONDS_BRAVE = 1.1`, `MIN_SECONDS_BETWEEN_SEARCHES = 3.0`, `RATE_LIMIT_BACKOFF = 30.0`, no CAPTCHA solving or identity rotation).
   - Supports licensed Brave Search API (`BRAVE_API_KEY`) as primary or `ddgs` (`duckduckgo,bing,brave,yahoo,mojeek`) / SearXNG / Wikipedia fallback.
   - **On-topic validation (`RELEVANCE_TOP = 5`, `ON_TOPIC_RUN_MIN = 0.6`):** Rejects off-topic SERP lists (when fewer than 2 of top 5 snippets contain required content keywords) and tries the next search backend.
   - **Snippet hygiene (Round 4):** Splits Bing-style leading publish stamps (`"Sep 13, 2026 · Who won..."`) into separate sentences and rejects bare month abbreviations so datelines are not extracted as named entities.
3. **Candidate Extraction (`src/planck3/candidates.py`):**
   - First builds a `snippets` pool from SERP titles + snippets + URLs (`snippet_candidates`).
   - Escalates conditionally (`OPEN_BELOW = 7.0`, `MAX_PAGES = 2`): if snippets yield no answer or weighed confidence `< 7.0`, sorts URLs by `(-(title_aboutness >= 0.5), -effective_trust)`, fetches full HTML, strips boilerplate via `trafilatura` (`extract_main_text`) + structured `extract_jsonld`, and extracts `span_candidates`.
4. **Trust-Blind Reading (`src/planck3/readers.py`, `src/planck3/xreader.py`):**
   - `HeuristicReader`: softmax over lexical candidate scores (`HEURISTIC_TEMP = 0.25`), capped by best raw score.
   - `CrossReader` (`x-hertz` 641M / `x-planck` 101M): encodes `QUESTION + ANSWER TYPE` prefix once in KV cache (`forward_cached`, `PREFIX_TOKENS = 64`), then batches up to `MAX_CANDS = 16` continuations (`CANDIDATE / FROM / EVIDENCE[:320]`, `CAND_TOKENS = 112`) concatenated with lexical feature vector (`N_FEAT`). Emits `r_k = softmax(choice)_k * Platt(answer_logit_k)`. Includes `shift_years` augmentation (`p = 0.5`) during training so the reader cannot overfit to specific calendar years.
   - `LLMReader`: formats top `max_cands` (default 20; configurable 16) candidates cleanly and prompts an instruction-tuned model (`gemma` or cloud `bedrock`) for strict JSON `{"k": int|null, "p": 0..1}`.
5. **Deterministic Weighing & Family Collapse (`src/planck3/consolidate.py`):**
   - **Cluster equivalence (`cluster`):** Merges accented/unaccented variants and normalized dates (`"Álex Palou" == "Alex Palou"`, `"5 March 2026" == "2026-03-05"`). Within a pool, equivalent candidates sum `r`; across pools (`snippets` + `page:*`), a cluster takes `max`.
   - **Family deduplication (`_families`):** Groups domains by `family` (e.g., all Wikipedia mirrors/forks + Wikidata + Grokipedia + Mapcarta map into `"wikimedia"`; `bbc.com` + `bbc.co.uk` map into `"bbc"`; `transfermarkt.*` map into `"transfermarkt"`). Each family's vote uses its highest-trust member and **counts only once** toward agreement.
   - **Winner selection:** `key = r * (0.5 + 0.5 * top_trust / 10)` (`TRUST_MIX = 0.5`), meaning the reader's semantic extraction leads, while higher-trust sources break ties.
   - **Itemized 0-10 confidence arithmetic:**

     | Term | Adjustment | Condition |
     |---|---:|---|
     | Base source trust | `+0.0 .. +10.0` | `top_trust` of strongest supporting family |
     | Independent corroboration | `+1` per family (max `+2`) | Other independent families with `effective >= 7.0` (`STRONG`) agreeing |
     | High-trust conflict | `-2.0` | Another cluster has `r >= 0.2` AND a supporting family at `>= 7.0` |
     | Reader doubt | `-2.0` or `-1.0` | Winning cluster `r < 0.3` (`-2`) or `0.3 <= r < 0.6` (`-1`) |
     | Question volatility penalty | `-2.0 / -1.0 / 0.0` | `news` (`-2`), `encyclopedic` (`-1`), `general_info` (`0`) |

   - Clamped to `[0.0, 10.0]` and mapped to bands:
     - `9-10`: `high` (`High confidence`)
     - `7-8`: `good` (`Good confidence, might have bias`)
     - `5-6`: `low` (`Low confidence in my results`)
     - `< 5`: `sceptical` (`Treat with scepticism`)
   - **System counterfactual (`divergence`):** Always runs `consolidate` twice: once with blended `effective = 0.7 * system + 0.3 * personal`, once with `personal = None`. Any shift in winning value or confidence band is surfaced explicitly on the answer card.
6. **Faithful Writing (`src/planck3/writer.py`):**
   - Receives only question, winning cluster, band, up to 3 supporting/conflicting source snippets (`SNIPPET_CHARS = 220`), and a forced band lead (`""` / `"Possibly <value>"` / `"Unclear:"`).
   - Checks `faithful()`: exact value presence, valid `[1..N]` citation bounds, zero invented integers/years, zero out-of-source capitalized entities (outside `STOPWORDS` and `ALLOWED_WORDS`), word count `<= 60`. Falls back to `TemplateWriter` on any failure.

---

## 3. Empirical Results Summary (`../sgs/results/planck3/REPORT.md`)

Key news & fresh benchmarks across Rounds 5 to 11 (n = 243 mixed in R5–R8 including 60 news; n = 220 fresh in R9–R11 including 80 Wikipedia Current Events portal news items):

| Run / Config | Overall Acc | News Split | Lat / Question | Notes |
|---|---:|---:|---:|---|
| `r5_planck_hertz` (Round 5 bi-encoder) | `0.387` (n=243) | `0.050` (n=60) | `~284 ms` (GPU) | Failed news almost completely (`5%`) |
| `r5_planck_hertz_brave` (Brave swap) | `0.514` (n=243) | `0.400` (n=60) | `~366 ms` (GPU) | Search backend caused +35 pts on news |
| `r6_gemma_template` (Brave) | `0.634` (n=243) | `0.600` (news+info) | `~2.87s` (GPU) | Reference teacher ceiling on R6 |
| `r7_x-hertz-rc_template` (CrossReader) | `0.601` (n=243) | `0.630` (news+info) | `71 ms` read (GPU) | NewsQA choice `0.580` (+10.2 pts over ranker) |
| `r8_x-hertz-rc_cpu-int8-top16` | `0.605` (n=243) | `0.640` (news+info) | `1.33s` (CPU int8) | `888.2 MB` RAM; passed phone-proxy gate |
| `r9_planck_template` (R5 on fresh9) | `0.314` (n=220) | `0.375` (n=80) | `105 ms` | Held-out 2026 baseline |
| **`r9_x-hertz-rc_cpu-int8-top16`** | **`0.491`** (n=220) | **`0.512`** (n=80) | `3.35s` (CPU int8) | Shipped R9 (`p = 1.77e-6` vs R5); Rule E drop `0.0` |
| `r9_gemma_template` (fresh9) | `0.609` (n=220) | `0.537` (n=80) | `2.68s` (GPU) | Level on portal news (`53.7%` vs `51.2%`), ahead on Wikidata |
| `r10_x-hertz-r10_cpu-int8-top16` | `0.477` (n=220) | `0.438` (n=80) | `3.42s` (CPU int8) | Soft-label Brave retrain did not beat R9 (`0.486`) |
| `r11d_gemma-top16P` vs `shipP` (fresh10) | `0.609` vs `0.482` | n=220 combined | `3.20s` ship | **Identical evidence proves `+12.7 pt` reader size gap** |

Two critical calibration/benchmark caveats recorded in `REPORT.md`:
- Small local readers consistently failed **C1 calibration** (`9-10 >= 90%`, `7-8 >= 70%`, strictly monotone): because confidence arithmetic trusts high-score domains even when a smaller reader mis-extracts a span (`r9`: `good` precision `0.673` on 49 items; `r10`: `0.600` on 60 items). Only Gemma reached `94.1%` / `70.1%` in Round 9 (`high`/`good`).
- For **Satz News** inside a desktop browser where the user may configure local Gemma or cloud frontier models (`gemini`, `anthropic`, `openai`, `mistral`), routing **synthesis, conflict detection, and low-confidence escalation (`< 7.0`)** to a stronger analyzer model resolves this exact precision weakness while retaining `x-hertz` for fast background candidate extraction.

---

## 4. Source Registry, Digest & Display Reference

### 4.1 Source Registry (`config/planck3/source_registry.json`, `src/planck3/registry.py`)

As of `2026-10-09`, the registry contains:
- **31 Categories** with explicit scores and rubric attribution (`owner` vs `PROPOSED`). News-relevant tiers include:
  - `10`: `independent` (`dw.com`, `tagesschau.de`, `ard.de`, `zdf.de`, `meduza.io`, `kyivindependent.com`, `novayagazeta.eu`), `science`, `health_reference`, `general_info`, explicit `britannica.com`.
  - `9`: `encyclopedia` (`*.wikipedia.org`, `wikidata.org`), `eu_gov`, `european_gov_non_eu`, `intergov`, `primary_official`, `us_agency` (noted `-1` for current admin).
  - `8`: `news_eu` (`lemonde.fr`, `spiegel.de`, `elpais.com`, `euronews.com`, `wielerflits.nl`), `public_broadcaster` (`cbc.ca`, `abc.net.au`, `nos.nl`, `yle.fi`, `svt.se`, `nrk.no`, `orf.at`, `srf.ch`), `us_gov`, `gov_other`, `edu`, `company_self`, `reference_db`.
  - `7`: `news_us_uk` (`reuters.com`, `apnews.com`, `bbc.com`, `bbc.co.uk`, `cnn.com`, `nytimes.com`, `theguardian.com`, `washingtonpost.com`, sports/culture), `news_other` (`asahi.com`, `saltwire.com`, `sundayguardianlive.com`), `specialist_db`.
  - `6`: `politicized` (`foxnews.com`, `breitbart.com`, `theatlantic.com`), `aggregator`.
  - `5`: `us_state_controlled` (`whitehouse.gov`, `voanews.com`, `rferl.org`, `stripes.com`), `fan_blog`, `scraped_db`, and **default `unscored = 5.0`**.
  - `4`: `pressure_jurisdiction` (`aljazeera.com`, `timesofisrael.com`, `haaretz.com`, `jpost.com`, `arabnews.com`, `gulfnews.com`, `thenationalnews.com`, `scmp.com`), `ai_generated` (`grokipedia.com`), `content_farm`, `betting`.
  - `3`: `user_generated` (`reddit.com`, `x.com`, social/wikis).
  - `2`: `state_media_authoritarian` (`rt.com`, `tass.com`, `sputnikglobe.com`, `xinhuanet.com`, `news.cn`, `cgtn.com`, `globaltimes.cn`).
- **35 Suffix Rules** (`.gov.uk`, `.gouv.fr`, `.bund.de`, `.ru`, `.cn`, `.fandom.com`, etc.) and **6 Keyword Rules** (`airport`, `airways`, `airlines`, `ferries`, `railway`, `museum`).
- **Conflict Gap Threshold:** `CONFLICT_GAP = 3.0` sets `conflict = True` ("you disagree" badge) whenever `|personal - system| >= 3.0`.
- **Personal Blend Cap:** `PERSONAL_WEIGHT = 0.3`; default `[trust more]` / `[trust less]` buttons step `+2.0` / `-2.0` within `[0, 10]`.

### 4.2 Local Digest (`src/planck3/digest.py`) & Reference UI (`src/planck3/serve.py`)

- **`build_digest(store)`** generates `"For you"` strictly from local SQLite tables (`facts`, `passages`, `edges`, `queries`, `watches`) and filters `explore` candidates to `trusted_domains(store, min_trust=0.6)`.
- **`serve.py` Reference Card Anatomy:**
  1. Band badge (`Confident` / `Low confidence in my results` / `No answer found`) + shaded meter bar with `7.0` threshold marker.
  2. Answer text + optional divergence alert box (`"Your source preferences changed this answer. Without them: <system_value> (<score>/10, <band>)"`).
  3. Expandable **`How I got this`** (default open when not confident):
     - Ordered reasoning steps list
     - Itemized `confidence10` table (`+ / -` signed deltas per source/penalty)
     - Top candidate values with `(reader_p · top_trust/10)`
     - Model attribution (`reader: ... · writer: ...` + template fallback note)
     - Sources breakdown table (`role | source | system | you | effective | category | actions: [trust more] [trust less] [more from here]` + `you disagree` badge)
  4. Expandable **`In depth: N passages from M sources`**:
     - Ranked passage cards + `Also in memory` related facts + `Further reading` unread URLs.

---

## 5. Benchmark vs. Current `satz-browser` State

| Capability | Recent `../sgs` Work | Current `satz-browser` Reality | Gap to Bridge for Satz News |
|---|---|---|---|
| **Pinned Surface** | `serve.py` single web chat page | `conv-mail` (`origin = "mail"`, pinned, undeletable in `db.rs`, multi-lane in `tabs.ts`/`mail.ts`) | Add `conv-news` (`origin = "news"`) mirroring `conv-mail` with News-specific lanes |
| **Read -> Weigh -> Write** | Full `Answerer` (`answer.py`, `consolidate.py`, `writer.py`) | `sidecar/satz_models.py` exposes `run_answer` & `run_read`, but `stream_chat` mostly sends raw Brave URLs/snippets straight into LLM prompt without card-level `consolidate()` weights, confidence meter, or counterfactual diff | Bring full `read -> weigh -> synthesize/write` audit card & counterfactual computation into News chat & story cards |
| **Multi-Model Pipeline** | `x-hertz` int8, `x-planck`, `gemma`, optional AWS Bedrock | Dynamic `/models` discovery + chat completions for local Gemma/`hertz`/`planck3` + cloud `gemini`, `anthropic`, `openai`, `mistral`; `roles` matrix only has `(chat, web_answer, reader)` | Add News role routing (`news_planner`, `news_capture`, `news_reader`, `news_analyzer`) and generalize `LLMReader` + synthesis + translation across all configured local/cloud providers |
| **Common Brain** | Simple `Store` SQLite (`facts`, `passages`, `edges`, `queries`) | Rich `SatzBrain` (`satz_brain.py`: YAML/Markdown entities, `BRAIN.md`, `[B1]` citations, `<brain_store>` neutralizer, `[accept]`/`[reject]` proposals, profile vault isolation M18) + `planck_store.sqlite` | Add `story`, `claim`, `topic`, `source` Brain types; connect Mail + Browsing entities to News topic ranking behind a local PII scrubber gate |
| **Source Registry & UI** | `source_registry.json` (222 domains, 31 categories, 3 families, rubrics) | `knowledge.ts` shows trust sliders (`0.7 * system + 0.3 * personal`) only for already-visited `top_domains` | Build full `[ sources ]` lane exposing all registry categories/rules, wire-agency families overlay, rubric notes, RSS/site feed subscriptions, and `[more from here]` |
| **Display & Perspectives** | `serve.py` cards + `digest.py` text list | `chat.ts` renders markdown + `[1]`/`[B1]` citations + persisted `findings` image previews + Compare View (`MOD+M`) tiling WebViews | Add News Story Cards, Perspective Spread matrix (side-by-side conflicting families + blind spots + Compare View launch), Reader Overlay, and Topic/Watch cards |
