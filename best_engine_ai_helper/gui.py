"""
Best Engine AI Helper — single-page GUI.

This module holds the self-contained HTML document served by the FastAPI app at
``GET /gui`` (see :mod:`best_engine_ai_helper.api`). One file, Tailwind via CDN,
vanilla JavaScript — no build step, no framework, no npm, matching the rest of
the AI Helpers suite (see audio-helper's GUI.md).

The page is offered in French (default) and English. Both are rendered from a
single template plus a per-language strings table by :func:`render_gui`; a
header link switches between them (``/gui`` for French, ``/gui?lang=en`` for
English). The JSON API the page calls is language-neutral, so only the labels
differ. ``GUI_HTML`` is the French render, kept as a module constant for
callers and tests that want the default page directly.

Visual language matches the sprezzature-figures gallery
(https://harchaoui.org/warith/sprezzature/figures.html): Roboto / Roboto
Serif / Roboto Mono, the #007aff brand blue, a neutral gray scale, and a
manual light/dark toggle persisted under a ``data-color-scheme`` attribute
(not hotlinked — fonts are self-served via Google Fonts, not the reference
site's assets).

Author
------
Warith Harchaoui <warith.harchaoui@deraison.ai>
"""

from __future__ import annotations

import html
import json

# ---------------------------------------------------------------------------
# Per-language label tables
# ---------------------------------------------------------------------------
# `html` keys fill {{TOKEN}} placeholders in the markup; `js` keys are emitted
# as a `const T = {...}` object the page's script reads, so every user-facing
# string — HTML and JavaScript alike — lives here and nowhere else.

_STRINGS: dict[str, dict[str, dict[str, str]]] = {
    "fr": {
        "html": {
            "LANG": "fr",
            "META_DESC": (
                "Caractéristiques matérielles de cette machine et meilleur "
                "moteur local (LLM / VLM) pour une tâche donnée."
            ),
            "SKIP": "Aller au contenu",
            "NAV_ARIA": "Principal",
            "GITHUB": "⭐️ sur GitHub",
            "THEME_ARIA": "Changer de thème",
            "LANG_HREF": "/gui?lang=en",
            "LANG_LABEL": "EN",
            "LANG_ARIA": "English version",
            "HERO_TITLE": "Meilleur moteur local",
            "HERO_P": (
                "Caractéristiques de cette machine, et le meilleur moteur local "
                "(LLM / VLM) pour la tâche que vous décrivez."
            ),
            "SYS_H2": "Caractéristiques système",
            "REFRESH": "Rafraîchir",
            "DETECTING": "Détection en cours…",
            "TASK_H2": "Décrire la tâche",
            "TASK_P": (
                "Une phrase suffit — les mots-clés visuels ajoutent un VLM à la "
                "recommandation."
            ),
            "TASK_LABEL": "Description de la tâche",
            "TASK_PLACEHOLDER": (
                "ex. « rédiger des fiches produit et vérifier la qualité de photos »"
            ),
            "RUN_BTN": "Recommander le(s) meilleur(s) moteur(s)",
            "HEADROOM": "Marge mémoire",
            "FOOTER_NOTE": "local uniquement, aucune télémétrie",
        },
        "js": {
            "detecting": "Détection en cours…",
            "detectFail": "Détection impossible : ",
            "fPlatform": "Plateforme",
            "fVendor": "Fournisseur",
            "fChip": "Puce / accélérateur",
            "poolUnified": "Mémoire unifiée",
            "poolVram": "VRAM",
            "poolRam": "RAM système",
            "fBandwidth": "Bande passante mémoire",
            "unknown": "inconnue",
            "fBudget": "Budget modèle utilisable",
            "gb": "Go",
            "gbs": "Go/s",
            "analyzing": "Analyse de la tâche et du matériel…",
            "done": "Terminé.",
            "recFail": "Échec de la recommandation : ",
            "error": "Erreur.",
            "yes": "oui",
            "no": "non",
            "best": "Meilleur",
            "axis": "axe :",
            "overBudget": "dépasse le budget mémoire — sera lent",
            "lighterAlt": "Alternative plus légère :",
            "score": "score",
            "noCandidate": "Aucun candidat trouvé.",
            "allCandidates": "Tous les candidats",
            "thModel": "modèle",
            "thRam": "Go RAM",
            "thScore": "score",
            "thFits": "tient",
            "thTps": "tok/s",
            "task": "Tâche :",
            "genericAssistant": "assistant texte généraliste",
            "matched": "Mots-clés détectés :",
            "needs": "Besoins :",
            "tps": "tok/s",
        },
    },
    "en": {
        "html": {
            "LANG": "en",
            "META_DESC": (
                "This machine's hardware characteristics and the best local "
                "engine (LLM / VLM) for a given task."
            ),
            "SKIP": "Skip to content",
            "NAV_ARIA": "Main",
            "GITHUB": "⭐️ on GitHub",
            "THEME_ARIA": "Toggle theme",
            "LANG_HREF": "/gui",
            "LANG_LABEL": "FR",
            "LANG_ARIA": "Version française",
            "HERO_TITLE": "Best local engine",
            "HERO_P": (
                "This machine's characteristics, and the best local engine "
                "(LLM / VLM) for the task you describe."
            ),
            "SYS_H2": "System characteristics",
            "REFRESH": "Refresh",
            "DETECTING": "Detecting…",
            "TASK_H2": "Describe the task",
            "TASK_P": (
                "One sentence is enough — visual keywords add a VLM to the "
                "recommendation."
            ),
            "TASK_LABEL": "Task description",
            "TASK_PLACEHOLDER": (
                'e.g. "write product descriptions and check photo quality"'
            ),
            "RUN_BTN": "Recommend the best engine(s)",
            "HEADROOM": "Memory headroom",
            "FOOTER_NOTE": "local only, no telemetry",
        },
        "js": {
            "detecting": "Detecting…",
            "detectFail": "Detection failed: ",
            "fPlatform": "Platform",
            "fVendor": "Vendor",
            "fChip": "Chip / accelerator",
            "poolUnified": "Unified memory",
            "poolVram": "VRAM",
            "poolRam": "System RAM",
            "fBandwidth": "Memory bandwidth",
            "unknown": "unknown",
            "fBudget": "Usable model budget",
            "gb": "GB",
            "gbs": "GB/s",
            "analyzing": "Analyzing task and hardware…",
            "done": "Done.",
            "recFail": "Recommendation failed: ",
            "error": "Error.",
            "yes": "yes",
            "no": "no",
            "best": "Best",
            "axis": "axis:",
            "overBudget": "exceeds the memory budget — will be slow",
            "lighterAlt": "Lighter alternative:",
            "score": "score",
            "noCandidate": "No candidate found.",
            "allCandidates": "All candidates",
            "thModel": "model",
            "thRam": "GB RAM",
            "thScore": "score",
            "thFits": "fits",
            "thTps": "tok/s",
            "task": "Task:",
            "genericAssistant": "general-purpose text assistant",
            "matched": "Detected keywords:",
            "needs": "Needs:",
            "tps": "tok/s",
        },
    },
}

# Default language when the query string names none or an unknown one.
_DEFAULT_LANG = "fr"


# The document template. Human-facing text is tokenised as {{TOKEN}} (HTML) or
# read from the injected `T` object (JavaScript), so this markup is shared by
# every language.
_GUI_TEMPLATE: str = r"""<!doctype html>
<html lang="{{LANG}}" data-color-scheme="light">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Best Engine AI Helper</title>
  <meta name="description" content="{{META_DESC}}" />
  <meta name="theme-color" content="#FFFFFF" media="(prefers-color-scheme: light)" />
  <meta name="theme-color" content="#0B0B0C" media="(prefers-color-scheme: dark)" />

  <link rel="icon" href="/static/icons/favicon.ico" sizes="any" />
  <link rel="icon" type="image/png" sizes="32x32" href="/static/icons/favicon-32x32.png" />
  <link rel="icon" type="image/png" sizes="16x16" href="/static/icons/favicon-16x16.png" />
  <link rel="apple-touch-icon" sizes="180x180" href="/static/icons/apple-touch-icon.png" />
  <link rel="manifest" href="/static/site.webmanifest" />

  <!-- Same type family as sprezzature-figures: Roboto / Roboto Serif / Roboto Mono. -->
  <link rel="preconnect" href="https://fonts.googleapis.com" />
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin />
  <link href="https://fonts.googleapis.com/css2?family=Roboto:wght@400;500;600;700&family=Roboto+Serif:wght@600;700&family=Roboto+Mono:wght@400;500&display=swap" rel="stylesheet" />

  <!-- Resolve light/dark before first paint (no flash), same scheme as the
       reference site but under this app's own storage key. -->
  <script>(function(){var s;try{s=localStorage.getItem('best-engine-theme');}catch(e){}
    if(!s)s=window.matchMedia&&window.matchMedia('(prefers-color-scheme: dark)').matches?'dark':'light';
    document.documentElement.setAttribute('data-color-scheme',s);})();</script>

  <!-- Tailwind via CDN: keeps the page a single self-contained file, no build. -->
  <script src="https://cdn.tailwindcss.com"></script>
  <script>
    tailwind.config = {
      darkMode: ["selector", '[data-color-scheme="dark"]'],
      theme: {
        extend: {
          fontFamily: {
            sans: ["Roboto", "system-ui", "sans-serif"],
            serif: ["Roboto Serif", "serif"],
            mono: ["Roboto Mono", "ui-monospace", "monospace"],
          },
          colors: {
            brand: {
              blue: "#007aff",
              bluedark: "#0a84ff",
              bluelight: "#cce4ff",
              navy: "#0a4da0",
            },
          },
        },
      },
    };
  </script>
  <style>
    @media (prefers-reduced-motion: reduce) { * { transition: none !important; } }
  </style>
</head>
<body class="bg-white text-neutral-900 antialiased dark:bg-[#0B0B0C] dark:text-neutral-100 font-sans">
  <a href="#main" class="sr-only focus:not-sr-only focus:absolute focus:z-50 focus:top-3 focus:left-3 focus:rounded-lg focus:bg-brand-blue focus:px-4 focus:py-2 focus:text-white">{{SKIP}}</a>

  <header class="sticky top-0 z-40 border-b border-neutral-200/70 bg-white/80 backdrop-blur dark:border-neutral-800 dark:bg-[#0B0B0C]/80">
    <nav class="mx-auto flex max-w-4xl items-center justify-between px-5 py-3" aria-label="{{NAV_ARIA}}">
      <span class="flex items-center gap-2 font-semibold tracking-tight">
        <img src="/static/icons/android-chrome-192x192.png" alt="" width="28" height="28" class="rounded-lg" />
        Best Engine AI Helper
      </span>
      <div class="flex items-center gap-3 text-sm">
        <a href="https://github.com/warith-harchaoui/best-engine-ai-helper"
           class="hidden rounded px-1 hover:text-brand-blue focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-blue sm:inline">
          {{GITHUB}}
        </a>
        <a href="{{LANG_HREF}}" aria-label="{{LANG_ARIA}}"
           class="rounded px-1.5 py-1 font-mono text-xs font-semibold hover:text-brand-blue focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-blue">
          {{LANG_LABEL}}
        </a>
        <button id="theme-toggle" type="button" aria-label="{{THEME_ARIA}}"
                class="rounded-full px-2 py-1 text-lg leading-none hover:bg-neutral-100 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-blue dark:hover:bg-neutral-800">
          🌞
        </button>
      </div>
    </nav>
  </header>

  <main id="main">
    <section class="mx-auto max-w-4xl px-5 py-14">
      <p class="font-mono text-sm text-brand-blue">best-engine-ai-helper</p>
      <h1 class="mt-1 font-serif text-4xl font-bold tracking-tight sm:text-5xl">{{HERO_TITLE}}</h1>
      <p class="mt-3 max-w-2xl text-base text-neutral-600 dark:text-neutral-300">
        {{HERO_P}}
      </p>
    </section>

    <!-- 1) Hardware snapshot -->
    <section class="border-t border-neutral-200/70 dark:border-neutral-800">
      <div class="mx-auto max-w-4xl px-5 py-10">
        <div class="mb-4 flex items-center justify-between">
          <h2 class="text-2xl font-bold tracking-tight">{{SYS_H2}}</h2>
          <button id="refresh-system"
                  class="rounded-lg border border-neutral-300 px-3 py-1.5 text-sm font-medium
                         hover:border-brand-blue focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-blue
                         dark:border-neutral-600">
            {{REFRESH}}
          </button>
        </div>
        <div id="system-grid"
             class="grid grid-cols-2 gap-4 rounded-xl border border-neutral-200 bg-white p-5 text-sm shadow-sm
                    sm:grid-cols-3 dark:border-neutral-800 dark:bg-neutral-950">
          <p class="col-span-full text-neutral-500 dark:text-neutral-400">{{DETECTING}}</p>
        </div>
      </div>
    </section>

    <!-- 2) Task description -->
    <section class="border-t border-neutral-200/70 dark:border-neutral-800">
      <div class="mx-auto max-w-4xl px-5 py-10">
        <h2 class="text-2xl font-bold tracking-tight">{{TASK_H2}}</h2>
        <p class="mt-2 max-w-3xl text-neutral-600 dark:text-neutral-300">
          {{TASK_P}}
        </p>
        <div class="mt-6 rounded-xl border border-neutral-200 bg-white p-5 shadow-sm dark:border-neutral-800 dark:bg-neutral-950">
          <label for="task" class="sr-only">{{TASK_LABEL}}</label>
          <textarea id="task" rows="3" placeholder="{{TASK_PLACEHOLDER}}"
                    class="w-full rounded-lg border border-neutral-300 bg-white px-3 py-2 text-sm text-neutral-900
                           focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-blue
                           dark:border-neutral-600 dark:bg-neutral-900 dark:text-neutral-100"></textarea>
          <div class="mt-4 flex flex-wrap items-center gap-3">
            <button id="run-recommend"
                    class="rounded-lg bg-brand-blue px-4 py-2 text-sm font-semibold text-white
                           hover:bg-brand-bluedark focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-blue
                           disabled:opacity-50">
              {{RUN_BTN}}
            </button>
            <label class="flex items-center gap-2 rounded-lg border border-neutral-200 bg-neutral-50 px-3 py-1.5 text-xs text-neutral-600
                          dark:border-neutral-800 dark:bg-neutral-900 dark:text-neutral-400">
              {{HEADROOM}}
              <input id="headroom" type="number" min="0.5" max="1" step="0.05" value="0.85"
                     class="w-16 rounded border border-neutral-300 bg-white px-2 py-1 text-xs text-neutral-900
                            focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-blue
                            dark:border-neutral-600 dark:bg-neutral-950 dark:text-neutral-100" />
            </label>
            <span id="status" class="text-xs text-neutral-500 dark:text-neutral-400" role="status" aria-live="polite"></span>
          </div>
        </div>
      </div>
    </section>

    <!-- 3) Results -->
    <section id="results-section" class="border-t border-neutral-200/70 dark:border-neutral-800">
      <div class="mx-auto max-w-4xl px-5 py-10">
        <div id="results" class="space-y-4"></div>
      </div>
    </section>
  </main>

  <footer class="border-t border-neutral-200/70 py-10 dark:border-neutral-800">
    <div class="mx-auto max-w-4xl px-5 text-sm text-neutral-500 dark:text-neutral-400">
      <p>
        <a class="underline hover:text-brand-blue" href="https://github.com/warith-harchaoui/best-engine-ai-helper">best-engine-ai-helper</a>
        · {{FOOTER_NOTE}} ·
        <a class="underline hover:text-brand-blue" href="https://www.linkedin.com/in/warith-harchaoui/">Warith Harchaoui</a>
      </p>
    </div>
  </footer>

  <script type="module">
    // All user-facing strings for this render, injected from the server.
    const T = {{JS_T}};

    const $ = (id) => document.getElementById(id);
    const status = (msg) => { $("status").textContent = msg; };
    const fmt1 = (v) => (v === null || v === undefined ? "?" : Number(v).toFixed(1));
    const fmtTps = (v) => (v ? Math.round(v) : "-");

    // --- Theme toggle ------------------------------------------------------
    const themeBtn = $("theme-toggle");
    function currentTheme() {
      return document.documentElement.getAttribute("data-color-scheme") === "dark" ? "dark" : "light";
    }
    function applyThemeIcon() {
      themeBtn.textContent = currentTheme() === "dark" ? "🌙" : "🌞";
    }
    themeBtn.addEventListener("click", () => {
      const next = currentTheme() === "dark" ? "light" : "dark";
      document.documentElement.setAttribute("data-color-scheme", next);
      try { localStorage.setItem("best-engine-theme", next); } catch (e) {}
      applyThemeIcon();
    });
    applyThemeIcon();

    // --- 1) Hardware snapshot -------------------------------------------
    async function loadSystem() {
      $("system-grid").innerHTML =
        `<p class="col-span-full text-neutral-500 dark:text-neutral-400">${T.detecting}</p>`;
      try {
        const res = await fetch("/api/system");
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const info = await res.json();
        renderSystem(info);
      } catch (err) {
        $("system-grid").innerHTML =
          `<p class="col-span-full text-red-600 dark:text-red-400">${T.detectFail}${err}</p>`;
      }
    }

    function field(label, value) {
      return `
        <div>
          <dt class="text-xs text-neutral-500 dark:text-neutral-400">${label}</dt>
          <dd class="font-medium">${value}</dd>
        </div>`;
    }

    function renderSystem(info) {
      const mem = info.memory || {};
      const comp = info.compute || {};
      const pool = mem.unified_gb ?? mem.vram_gb ?? mem.ram_gb;
      const poolLabel = mem.unified_gb != null ? T.poolUnified
        : mem.vram_gb != null ? T.poolVram : T.poolRam;

      const cells = [
        field(T.fPlatform, info.platform ?? "?"),
        field(T.fVendor, info.chip_vendor ?? "?"),
        field(T.fChip, `${comp.chip ?? "?"} (${comp.accelerator ?? "?"})`),
        field(poolLabel, `${fmt1(pool)} ${T.gb}`),
        field(T.fBandwidth, comp.bandwidth_gbs ? `${Math.round(comp.bandwidth_gbs)} ${T.gbs}` : T.unknown),
        field(T.fBudget, `${fmt1(info.memory_budget_gb)} ${T.gb}`),
      ];
      $("system-grid").innerHTML = cells.join("");
    }

    $("refresh-system").addEventListener("click", loadSystem);
    loadSystem();

    // --- 2 & 3) Recommendation -------------------------------------------
    $("run-recommend").addEventListener("click", runRecommend);
    $("task").addEventListener("keydown", (e) => {
      if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) runRecommend();
    });

    async function runRecommend() {
      const task = $("task").value.trim() || null;
      const headroom = Number($("headroom").value) || 0.85;
      $("run-recommend").disabled = true;
      status(T.analyzing);
      $("results").innerHTML = "";
      try {
        const res = await fetch("/api/recommend", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ task, headroom }),
        });
        if (!res.ok) throw new Error(`HTTP ${res.status}: ${await res.text()}`);
        const report = await res.json();
        renderResults(report);
        status(T.done);
      } catch (err) {
        $("results").innerHTML =
          `<p class="text-sm text-red-600 dark:text-red-400">${T.recFail}${err}</p>`;
        status(T.error);
      } finally {
        $("run-recommend").disabled = false;
      }
    }

    function candidateRow(r) {
      return `
        <tr class="border-t border-neutral-200 dark:border-neutral-800">
          <td class="py-1.5 pr-3 font-mono">${r.id}</td>
          <td class="py-1.5 pr-3">${fmt1(r.ram_gb)}</td>
          <td class="py-1.5 pr-3">${Math.round(r.score)}</td>
          <td class="py-1.5 pr-3">${r.fits ? T.yes : T.no}</td>
          <td class="py-1.5">${fmtTps(r.est_tokens_per_s)}</td>
        </tr>`;
    }

    function pill(text) {
      return `<span class="inline-flex items-center rounded-full border border-brand-blue/30 bg-brand-bluelight/30
                            px-3 py-1 font-mono text-sm font-semibold text-brand-navy
                            dark:border-brand-blue/40 dark:bg-brand-navy/20 dark:text-blue-300">${text}</span>`;
    }

    function kindCard(kind, block) {
      const chosen = block.chosen;
      const alt = block.lighter_alternative;
      const chosenHtml = chosen ? `
        <p class="flex flex-wrap items-center gap-2 text-sm">
          ${pill(chosen.id)}
          <span class="text-neutral-600 dark:text-neutral-300">
            ${fmt1(chosen.ram_gb)} ${T.gb}, ${T.score} ${Math.round(chosen.score)}, ~${fmtTps(chosen.est_tokens_per_s)} ${T.tps}
          </span>
          ${chosen.fits ? "" : `<span class="text-red-600 dark:text-red-400">${T.overBudget}</span>`}
        </p>
        ${alt ? `<p class="mt-2 text-xs text-neutral-500 dark:text-neutral-400">${T.lighterAlt} <span class="font-mono">${alt.id}</span> — ${fmt1(alt.ram_gb)} ${T.gb}, ${T.score} ${Math.round(alt.score)}, ~${fmtTps(alt.est_tokens_per_s)} ${T.tps}.</p>` : ""}
      ` : `<p class="text-sm text-neutral-500 dark:text-neutral-400">${T.noCandidate}</p>`;

      return `
        <div class="overflow-hidden rounded-xl border border-neutral-200 bg-white p-5 shadow-sm dark:border-neutral-800 dark:bg-neutral-950">
          <h3 class="mb-3 text-lg font-bold tracking-tight">
            ${T.best} ${kind.toUpperCase()} <span class="font-mono text-sm font-normal text-neutral-500 dark:text-neutral-400">(${T.axis} ${block.axis})</span>
          </h3>
          ${chosenHtml}
          <details class="mt-4">
            <summary class="cursor-pointer text-xs font-medium text-neutral-500 hover:text-brand-blue dark:text-neutral-400">
              ${T.allCandidates} (${block.candidates.length})
            </summary>
            <div class="mt-2 overflow-x-auto">
              <table class="w-full text-left text-xs">
                <thead>
                  <tr class="text-neutral-500 dark:text-neutral-400">
                    <th class="pb-1.5 pr-3 font-medium">${T.thModel}</th>
                    <th class="pb-1.5 pr-3 font-medium">${T.thRam}</th>
                    <th class="pb-1.5 pr-3 font-medium">${T.thScore}</th>
                    <th class="pb-1.5 pr-3 font-medium">${T.thFits}</th>
                    <th class="pb-1.5 font-medium">${T.thTps}</th>
                  </tr>
                </thead>
                <tbody>${block.candidates.map(candidateRow).join("")}</tbody>
              </table>
            </div>
          </details>
        </div>`;
    }

    function renderResults(report) {
      const task = report.task || {};
      const parts = [];

      parts.push(`
        <div class="rounded-xl border border-neutral-200 bg-neutral-50 p-4 text-sm dark:border-neutral-800 dark:bg-neutral-900">
          <p><span class="text-neutral-500 dark:text-neutral-400">${T.task}</span> ${task.input ? task.input : T.genericAssistant}</p>
          ${task.matched && task.matched.length ? `<p class="mt-1 text-xs text-neutral-500 dark:text-neutral-400">${T.matched} ${task.matched.join(", ")}</p>` : ""}
          <p class="mt-1 text-xs text-neutral-500 dark:text-neutral-400">${T.needs} ${task.kinds.map((k) => k.toUpperCase()).join(", ")}</p>
        </div>`);

      const kindBlocks = Object.entries(report.recommendations || {});
      const gridClass = kindBlocks.length > 1 ? "mt-4 grid gap-4 sm:grid-cols-2" : "mt-4 grid gap-4";
      parts.push(`<div class="${gridClass}">${kindBlocks.map(([kind, block]) => kindCard(kind, block)).join("")}</div>`);

      $("results").innerHTML = parts.join("");
    }
  </script>
</body>
</html>
"""


def render_gui(lang: str = _DEFAULT_LANG) -> str:
    """
    Render the single-page GUI in the requested language.

    Parameters
    ----------
    lang : str
        Two-letter language code. ``"fr"`` (default) and ``"en"`` are supported;
        any other value falls back to French so an unknown ``?lang=`` never 500s.

    Returns
    -------
    str
        The complete HTML document for that language.
    """
    strings = _STRINGS.get(lang, _STRINGS[_DEFAULT_LANG])
    page = _GUI_TEMPLATE
    for token, value in strings["html"].items():
        # Escape every value: these labels land in attributes (placeholder, aria,
        # href) and text nodes alike, and some carry quotes (the EN placeholder)
        # that would otherwise break out of the attribute they sit in.
        page = page.replace("{{" + token + "}}", html.escape(value, quote=True))
    # Emit the JS strings as a JSON literal so quotes/accents are escaped safely.
    page = page.replace("{{JS_T}}", json.dumps(strings["js"], ensure_ascii=False))
    return page


# French render, kept as a module constant for the default page and for callers
# and tests that want the markup without going through render_gui().
GUI_HTML: str = render_gui("fr")
