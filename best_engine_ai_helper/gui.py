"""
Best Engine AI Helper — single-page GUI.

This module holds nothing but the self-contained HTML document served by the
FastAPI app at ``GET /gui`` (see :mod:`best_engine_ai_helper.api`). One file,
Tailwind via CDN, vanilla JavaScript — no build step, no framework, no npm,
matching the rest of the AI Helpers suite (see audio-helper's GUI.md).

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
<html lang="fr" class="h-full">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Best Engine AI Helper</title>
  <meta name="theme-color" content="#f7f3ea" />

  <link rel="icon" href="/static/icons/favicon.ico" sizes="any" />
  <link rel="icon" type="image/png" sizes="32x32" href="/static/icons/favicon-32x32.png" />
  <link rel="icon" type="image/png" sizes="16x16" href="/static/icons/favicon-16x16.png" />
  <link rel="apple-touch-icon" sizes="180x180" href="/static/icons/apple-touch-icon.png" />
  <link rel="manifest" href="/static/site.webmanifest" />

  <!-- Tailwind via CDN: keeps the page a single self-contained file, no build. -->
  <script src="https://cdn.tailwindcss.com"></script>
  <script>
    tailwind.config = {
      theme: {
        extend: {
          colors: {
            paper: "#f7f3ea",
            ink: "#2b2b28",
            brass: { 600: "#a8571f", 700: "#8a4519" },
          },
        },
      },
    };
  </script>
  <style>
    @media (prefers-reduced-motion: reduce) { * { transition: none !important; } }
  </style>
</head>
<body class="h-full bg-paper text-ink antialiased">
  <div class="mx-auto max-w-3xl px-4 py-8">
    <header class="mb-8 flex items-center gap-4">
      <img src="/static/icons/android-chrome-192x192.png" alt="" class="h-14 w-14 rounded-xl border border-ink/10 shadow-sm" />
      <div>
        <h1 class="text-2xl font-semibold tracking-tight">Best Engine AI Helper</h1>
        <p class="mt-1 text-sm text-ink/70">
          Caractéristiques de cette machine, et le meilleur moteur local (LLM / VLM)
          pour la tâche que vous décrivez.
        </p>
      </div>
    </header>

    <!-- 1) Hardware snapshot -->
    <section class="mb-8 rounded-xl border border-ink/10 bg-white/60 p-4">
      <div class="mb-3 flex items-center justify-between">
        <h2 class="text-sm font-semibold uppercase tracking-wide text-ink/70">Caractéristiques système</h2>
        <button id="refresh-system"
                class="rounded-lg border border-ink/20 bg-white px-3 py-1.5 text-xs font-medium
                       hover:bg-paper focus:outline-none focus:ring-2 focus:ring-brass-600">
          Rafraîchir
        </button>
      </div>
      <div id="system-grid" class="grid grid-cols-2 gap-x-4 gap-y-2 text-sm sm:grid-cols-3">
        <p class="col-span-full text-ink/50">Détection en cours…</p>
      </div>
    </section>

    <!-- 2) Task description -->
    <section class="mb-8 rounded-xl border border-ink/10 bg-white/60 p-4">
      <h2 class="mb-3 text-sm font-semibold uppercase tracking-wide text-ink/70">Décrire la tâche</h2>
      <label for="task" class="sr-only">Description de la tâche</label>
      <textarea id="task" rows="3" placeholder="ex. « rédiger des fiches produit et vérifier la qualité de photos »"
                class="w-full rounded-lg border border-ink/20 bg-white px-3 py-2 text-sm
                       focus:outline-none focus:ring-2 focus:ring-brass-600"></textarea>
      <div class="mt-3 flex flex-wrap items-center gap-3">
        <button id="run-recommend"
                class="rounded-lg bg-brass-600 px-4 py-2 text-sm font-semibold text-white
                       hover:bg-brass-700 focus:outline-none focus:ring-2 focus:ring-brass-600
                       disabled:opacity-50">
          Recommander le(s) meilleur(s) moteur(s)
        </button>
        <label class="flex items-center gap-2 text-xs text-ink/60">
          Marge mémoire
          <input id="headroom" type="number" min="0.5" max="1" step="0.05" value="0.85"
                 class="w-16 rounded border border-ink/20 bg-white px-2 py-1 text-xs" />
        </label>
        <span id="status" class="text-xs text-ink/60" role="status" aria-live="polite"></span>
      </div>
    </section>

    <!-- 3) Results -->
    <section id="results" class="space-y-4"></section>
  </div>

  <script type="module">
    const $ = (id) => document.getElementById(id);
    const status = (msg) => { $("status").textContent = msg; };
    const fmt1 = (v) => (v === null || v === undefined ? "?" : Number(v).toFixed(1));
    const fmtTps = (v) => (v ? Math.round(v) : "-");

    // --- 1) Hardware snapshot -------------------------------------------
    async function loadSystem() {
      $("system-grid").innerHTML = `<p class="col-span-full text-ink/50">Détection en cours…</p>`;
      try {
        const res = await fetch("/api/system");
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const info = await res.json();
        renderSystem(info);
      } catch (err) {
        $("system-grid").innerHTML =
          `<p class="col-span-full text-red-700">Détection impossible : ${err}</p>`;
      }
    }

    function field(label, value) {
      return `
        <div>
          <dt class="text-xs text-ink/50">${label}</dt>
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
        $("results").innerHTML = `<p class="text-sm text-red-700">Échec de la recommandation : ${err}</p>`;
        status("Erreur.");
      } finally {
        $("run-recommend").disabled = false;
      }
    }

    function candidateRow(r) {
      return `
        <tr class="border-t border-ink/10">
          <td class="py-1 pr-3 font-mono">${r.id}</td>
          <td class="py-1 pr-3">${fmt1(r.ram_gb)}</td>
          <td class="py-1 pr-3">${Math.round(r.score)}</td>
          <td class="py-1 pr-3">${r.fits ? "oui" : "non"}</td>
          <td class="py-1">${fmtTps(r.est_tokens_per_s)}</td>
        </tr>`;
    }

    function kindCard(kind, block) {
      const chosen = block.chosen;
      const alt = block.lighter_alternative;
      const chosenHtml = chosen ? `
        <p class="text-sm">
          <span class="rounded bg-brass-600/10 px-2 py-1 font-mono font-semibold text-brass-700">${chosen.id}</span>
          — ${fmt1(chosen.ram_gb)} Go, score ${Math.round(chosen.score)}, ~${fmtTps(chosen.est_tokens_per_s)} tok/s
          ${chosen.fits ? "" : ' <span class="text-red-700">(dépasse le budget mémoire — sera lent)</span>'}
        </p>
        ${alt ? `<p class="mt-1 text-xs text-ink/60">Alternative plus légère : <span class="font-mono">${alt.id}</span> — ${fmt1(alt.ram_gb)} Go, score ${Math.round(alt.score)}, ~${fmtTps(alt.est_tokens_per_s)} tok/s.</p>` : ""}
      ` : `<p class="text-sm text-ink/60">Aucun candidat trouvé.</p>`;

      return `
        <div class="rounded-xl border border-ink/10 bg-white/60 p-4">
          <h3 class="mb-2 text-sm font-semibold uppercase tracking-wide text-ink/70">
            Meilleur ${kind.toUpperCase()} <span class="normal-case text-ink/40">(axe : ${block.axis})</span>
          </h3>
          ${chosenHtml}
          <details class="mt-3">
            <summary class="cursor-pointer text-xs font-medium text-ink/60">Tous les candidats (${block.candidates.length})</summary>
            <table class="mt-2 w-full text-left text-xs">
              <thead>
                <tr class="text-ink/50">
                  <th class="pb-1 pr-3 font-medium">modèle</th>
                  <th class="pb-1 pr-3 font-medium">Go RAM</th>
                  <th class="pb-1 pr-3 font-medium">score</th>
                  <th class="pb-1 pr-3 font-medium">tient</th>
                  <th class="pb-1 font-medium">tok/s</th>
                </tr>
              </thead>
              <tbody>${block.candidates.map(candidateRow).join("")}</tbody>
            </table>
          </details>
        </div>`;
    }

    function renderResults(report) {
      const task = report.task || {};
      const parts = [];

      parts.push(`
        <div class="rounded-xl border border-ink/10 bg-white/60 p-4 text-sm">
          <p><span class="text-ink/50">Tâche :</span> ${task.input ? task.input : "assistant texte généraliste"}</p>
          ${task.matched && task.matched.length ? `<p class="mt-1 text-xs text-ink/60">Mots-clés détectés : ${task.matched.join(", ")}</p>` : ""}
          <p class="mt-1 text-xs text-ink/60">Besoins : ${task.kinds.map((k) => k.toUpperCase()).join(", ")}</p>
        </div>`);

      for (const [kind, block] of Object.entries(report.recommendations || {})) {
        parts.push(kindCard(kind, block));
      }

      $("results").innerHTML = parts.join("");
    }
  </script>
</body>
</html>
"""
