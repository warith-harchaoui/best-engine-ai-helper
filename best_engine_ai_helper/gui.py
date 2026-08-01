"""
Best Engine AI Helper — single-page GUI.

This module holds nothing but the self-contained HTML document served by the
FastAPI app at ``GET /gui`` (see :mod:`best_engine_ai_helper.api`). One file,
Tailwind via CDN, vanilla JavaScript — no build step, no framework, no npm,
matching the rest of the AI Helpers suite (see audio-helper's GUI.md).

Visual language matches the sprezzature-figures gallery
(https://harchaoui.org/warith/sprezzature/figures.html): Roboto / Roboto
Serif / Roboto Mono, the #007aff brand blue, a neutral gray scale, and a
manual light/dark toggle persisted under a ``data-color-scheme`` attribute
(not hotlinked — fonts are self-served via Google Fonts, not the reference
site's assets).

The page does two things:

1. Shows this machine's hardware characteristics (chip, accelerator, memory
   pool, usable model budget), read from ``GET /api/system``.
2. Takes a free-text task description and shows the best local engine(s) for
   it on this hardware, from ``POST /api/recommend``.

Author
------
Warith Harchaoui <warith.harchaoui@gmail.com>
"""

from __future__ import annotations

GUI_HTML: str = r"""<!doctype html>
<html lang="fr" data-color-scheme="light">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Best Engine AI Helper</title>
  <meta name="description" content="Caractéristiques matérielles de cette machine et meilleur moteur local (LLM / VLM) pour une tâche donnée." />
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
  <a href="#main" class="sr-only focus:not-sr-only focus:absolute focus:z-50 focus:top-3 focus:left-3 focus:rounded-lg focus:bg-brand-blue focus:px-4 focus:py-2 focus:text-white">Aller au contenu</a>

  <header class="sticky top-0 z-40 border-b border-neutral-200/70 bg-white/80 backdrop-blur dark:border-neutral-800 dark:bg-[#0B0B0C]/80">
    <nav class="mx-auto flex max-w-4xl items-center justify-between px-5 py-3" aria-label="Principal">
      <span class="flex items-center gap-2 font-semibold tracking-tight">
        <img src="/static/icons/android-chrome-192x192.png" alt="" width="28" height="28" class="rounded-lg" />
        Best Engine AI Helper
      </span>
      <div class="flex items-center gap-3 text-sm">
        <a href="https://github.com/warith-harchaoui/best-engine-ai-helper"
           class="hidden rounded px-1 hover:text-brand-blue focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-blue sm:inline">
          ⭐️ sur GitHub
        </a>
        <button id="theme-toggle" type="button" aria-label="Changer de thème"
                class="rounded-full px-2 py-1 text-lg leading-none hover:bg-neutral-100 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-blue dark:hover:bg-neutral-800">
          🌞
        </button>
      </div>
    </nav>
  </header>

  <main id="main">
    <section class="mx-auto max-w-4xl px-5 py-14">
      <p class="font-mono text-sm text-brand-blue">best-engine-ai-helper</p>
      <h1 class="mt-1 font-serif text-4xl font-bold tracking-tight sm:text-5xl">Meilleur moteur local</h1>
      <p class="mt-3 max-w-2xl text-base text-neutral-600 dark:text-neutral-300">
        Caractéristiques de cette machine, et le meilleur moteur local (LLM / VLM)
        pour la tâche que vous décrivez.
      </p>
    </section>

    <!-- 1) Hardware snapshot -->
    <section class="border-t border-neutral-200/70 dark:border-neutral-800">
      <div class="mx-auto max-w-4xl px-5 py-10">
        <div class="mb-4 flex items-center justify-between">
          <h2 class="text-2xl font-bold tracking-tight">Caractéristiques système</h2>
          <button id="refresh-system"
                  class="rounded-lg border border-neutral-300 px-3 py-1.5 text-sm font-medium
                         hover:border-brand-blue focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-blue
                         dark:border-neutral-600">
            Rafraîchir
          </button>
        </div>
        <div id="system-grid"
             class="grid grid-cols-2 gap-4 rounded-xl border border-neutral-200 bg-white p-5 text-sm shadow-sm
                    sm:grid-cols-3 dark:border-neutral-800 dark:bg-neutral-950">
          <p class="col-span-full text-neutral-500 dark:text-neutral-400">Détection en cours…</p>
        </div>
      </div>
    </section>

    <!-- 2) Task description -->
    <section class="border-t border-neutral-200/70 dark:border-neutral-800">
      <div class="mx-auto max-w-4xl px-5 py-10">
        <h2 class="text-2xl font-bold tracking-tight">Décrire la tâche</h2>
        <p class="mt-2 max-w-3xl text-neutral-600 dark:text-neutral-300">
          Une phrase suffit — les mots-clés visuels ajoutent un VLM à la recommandation.
        </p>
        <div class="mt-6 rounded-xl border border-neutral-200 bg-white p-5 shadow-sm dark:border-neutral-800 dark:bg-neutral-950">
          <label for="task" class="sr-only">Description de la tâche</label>
          <textarea id="task" rows="3" placeholder="ex. « rédiger des fiches produit et vérifier la qualité de photos »"
                    class="w-full rounded-lg border border-neutral-300 bg-white px-3 py-2 text-sm text-neutral-900
                           focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-blue
                           dark:border-neutral-600 dark:bg-neutral-900 dark:text-neutral-100"></textarea>
          <div class="mt-4 flex flex-wrap items-center gap-3">
            <button id="run-recommend"
                    class="rounded-lg bg-brand-blue px-4 py-2 text-sm font-semibold text-white
                           hover:bg-brand-bluedark focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-blue
                           disabled:opacity-50">
              Recommander le(s) meilleur(s) moteur(s)
            </button>
            <label class="flex items-center gap-2 rounded-lg border border-neutral-200 bg-neutral-50 px-3 py-1.5 text-xs text-neutral-600
                          dark:border-neutral-800 dark:bg-neutral-900 dark:text-neutral-400">
              Marge mémoire
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
        · local uniquement, aucune télémétrie ·
        <a class="underline hover:text-brand-blue" href="https://www.linkedin.com/in/warith-harchaoui/">Warith Harchaoui</a>
      </p>
    </div>
  </footer>

  <script type="module">
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
        `<p class="col-span-full text-neutral-500 dark:text-neutral-400">Détection en cours…</p>`;
      try {
        const res = await fetch("/api/system");
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const info = await res.json();
        renderSystem(info);
      } catch (err) {
        $("system-grid").innerHTML =
          `<p class="col-span-full text-red-600 dark:text-red-400">Détection impossible : ${err}</p>`;
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
      const poolLabel = mem.unified_gb != null ? "Mémoire unifiée"
        : mem.vram_gb != null ? "VRAM" : "RAM système";

      const cells = [
        field("Plateforme", info.platform ?? "?"),
        field("Fournisseur", info.chip_vendor ?? "?"),
        field("Puce / accélérateur", `${comp.chip ?? "?"} (${comp.accelerator ?? "?"})`),
        field(poolLabel, `${fmt1(pool)} Go`),
        field("Bande passante mémoire", comp.bandwidth_gbs ? `${Math.round(comp.bandwidth_gbs)} Go/s` : "inconnue"),
        field("Budget modèle utilisable", `${fmt1(info.memory_budget_gb)} Go`),
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
      status("Analyse de la tâche et du matériel…");
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
        status("Terminé.");
      } catch (err) {
        $("results").innerHTML =
          `<p class="text-sm text-red-600 dark:text-red-400">Échec de la recommandation : ${err}</p>`;
        status("Erreur.");
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
          <td class="py-1.5 pr-3">${r.fits ? "oui" : "non"}</td>
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
            ${fmt1(chosen.ram_gb)} Go, score ${Math.round(chosen.score)}, ~${fmtTps(chosen.est_tokens_per_s)} tok/s
          </span>
          ${chosen.fits ? "" : '<span class="text-red-600 dark:text-red-400">dépasse le budget mémoire — sera lent</span>'}
        </p>
        ${alt ? `<p class="mt-2 text-xs text-neutral-500 dark:text-neutral-400">Alternative plus légère : <span class="font-mono">${alt.id}</span> — ${fmt1(alt.ram_gb)} Go, score ${Math.round(alt.score)}, ~${fmtTps(alt.est_tokens_per_s)} tok/s.</p>` : ""}
      ` : `<p class="text-sm text-neutral-500 dark:text-neutral-400">Aucun candidat trouvé.</p>`;

      return `
        <div class="overflow-hidden rounded-xl border border-neutral-200 bg-white p-5 shadow-sm dark:border-neutral-800 dark:bg-neutral-950">
          <h3 class="mb-3 text-lg font-bold tracking-tight">
            Meilleur ${kind.toUpperCase()} <span class="font-mono text-sm font-normal text-neutral-500 dark:text-neutral-400">(axe : ${block.axis})</span>
          </h3>
          ${chosenHtml}
          <details class="mt-4">
            <summary class="cursor-pointer text-xs font-medium text-neutral-500 hover:text-brand-blue dark:text-neutral-400">
              Tous les candidats (${block.candidates.length})
            </summary>
            <div class="mt-2 overflow-x-auto">
              <table class="w-full text-left text-xs">
                <thead>
                  <tr class="text-neutral-500 dark:text-neutral-400">
                    <th class="pb-1.5 pr-3 font-medium">modèle</th>
                    <th class="pb-1.5 pr-3 font-medium">Go RAM</th>
                    <th class="pb-1.5 pr-3 font-medium">score</th>
                    <th class="pb-1.5 pr-3 font-medium">tient</th>
                    <th class="pb-1.5 font-medium">tok/s</th>
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
          <p><span class="text-neutral-500 dark:text-neutral-400">Tâche :</span> ${task.input ? task.input : "assistant texte généraliste"}</p>
          ${task.matched && task.matched.length ? `<p class="mt-1 text-xs text-neutral-500 dark:text-neutral-400">Mots-clés détectés : ${task.matched.join(", ")}</p>` : ""}
          <p class="mt-1 text-xs text-neutral-500 dark:text-neutral-400">Besoins : ${task.kinds.map((k) => k.toUpperCase()).join(", ")}</p>
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
