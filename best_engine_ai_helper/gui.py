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

Every user-facing string is authored once, in ``locales/i18n.yaml`` (package
root's ``gui:`` namespace, loaded through :mod:`best_engine_ai_helper.i18n`)
— this module never hardcodes wording. It maps that file's stable semantic
keys onto the template's ``{{TOKEN}}`` placeholders and the JavaScript ``T``
object, and falls back to the ``meta.default_locale`` declared in the YAML
(French) for any language the file does not cover.

Visual language matches the sprezzature-figures gallery
(https://sprezzature.ai/figures.html): Roboto / Roboto
Serif / Roboto Mono, the #007aff brand blue, a neutral gray scale, and a
manual light/dark toggle persisted under a ``data-color-scheme`` attribute
(not hotlinked — fonts are self-served via Google Fonts, not the reference
site's assets).

Author
------
Warith Harchaoui <warithmetics@deraison.ai>
"""

from __future__ import annotations

import functools
import html
import json
import re
from pathlib import Path

import os_helper as osh

# The inline script's strings. The JS names are the contract between this
# module and the script below; the English beside each one is the msgid, so
# the script's copy lives in the same place as the markup's and is checked
# by the same test. Injected as JSON, which is the one encoding an
# apostrophe cannot break out of — and French copy is full of them.
_JS_NAME_TO_SOURCE: dict[str, str] = {
    "activityFail": "Failed to load: ",
    "activityLoading": "Loading…",
    "allCandidates": "All candidates",
    "analyzing": "Analyzing task and hardware…",
    "axis": "axis:",
    "best": "Best",
    "blended": "(blended)",
    "byModel": "By model",
    "byUser": "By user",
    "calls": "calls",
    "cloudNote": "Reference only — no API key read, no network call.",
    "detectFail": "Detection failed: ",
    "detecting": "Detecting…",
    "diskFree": "disk free",
    "done": "Done.",
    "error": "Error.",
    "errorRate": "Error rate:",
    "fBandwidth": "Memory bandwidth",
    "fBudget": "Usable model budget",
    "fChip": "Chip / accelerator",
    "fPlatform": "Platform",
    "fVendor": "Vendor",
    "gb": "GB",
    "gbs": "GB/s",
    "genericAssistant": "general-purpose text assistant",
    "language": "Detected language:",
    "lighterAlt": "Lighter alternative:",
    "matched": "Detected keywords:",
    "needs": "Needs:",
    "no": "no",
    "noActivity": "No calls recorded yet.",
    "noCandidate": "No candidate found.",
    "notStructured": "no structured JSON output — unfit for schema-driven tasks",
    "overBudget": "exceeds the memory budget — will be slow",
    "poolRam": "System RAM",
    "poolUnified": "Unified memory",
    "poolVram": "VRAM",
    "priceUnknown": "price unknown",
    "provNoKey": "no key",
    "provReady": "key found",
    "ramFree": "RAM free",
    "recFail": "Recommendation failed: ",
    "runningEngines": "already-running engines:",
    "score": "score",
    "serverLoad": "Server load:",
    "task": "Task:",
    "thCalls": "calls",
    "thCost": "cost",
    "thFits": "fits",
    "thModel": "model",
    "thPrice": "$/1M tokens",
    "thProvider": "provider",
    "thRam": "GB RAM",
    "thScore": "score",
    "thStructured": "structured",
    "thTps": "tok/s",
    "totalCost": "Total cost:",
    "tps": "tok/s",
    "unknown": "unknown",
    "unknownCost": "unknown cost",
    "yes": "yes",
}


#: Where the compiled catalogues live, inside the package so they travel in
#: the wheel. Up to 1.5.0 this package shipped its locale file one level above
#: the package directory, which is not package data: a clean `pip install` gave
#: a package whose every GUI string raised FileNotFoundError, while a checkout
#: and an editable install both worked.
_LOCALES_DIR = Path(__file__).resolve().parent / "locales"

#: The gettext domain, and therefore each ``.mo`` file's stem.
_DOMAIN = "best_engine_ai_helper"

#: Default language when the query string names none or an unknown one.
_DEFAULT_LANG: str = "fr"


@functools.lru_cache(maxsize=1)
def _catalog() -> osh.Catalog:
    """Resolve the catalogue directory once, through the suite's shared loader."""
    return osh.Catalog.from_package(_LOCALES_DIR, _DOMAIN, default_language=_DEFAULT_LANG)


def supported_languages() -> tuple[str, ...]:
    """Language codes the GUI can render: English plus every compiled catalogue."""
    return _catalog().languages


def default_language() -> str:
    """The language an unknown or absent ``?lang=`` falls back to."""
    return _catalog().default_language


# The language toggle is computed, not translated. Both of its parts mean "the
# other language", which is data rather than copy: a msgid of ``?lang=fr``
# whose translation is ``?lang=en`` would be nonsense, and `Catalog.problems`
# would rightly treat it as prose that had drifted.
#
#: How each language names itself. Deliberately NOT translated: a French page
#: offering English says "English version" in English, which is what a reader
#: scanning for their own language actually looks for.
_ENDONYMS: dict[str, str] = {"fr": "Version française", "en": "English version"}

#: One ``{{_("…")}}`` site in the template. Non-greedy and newline-free, so a
#: run of them on one line stays separate and an unterminated one is left
#: alone rather than swallowing the rest of the page.
_SOURCE_RE = re.compile(r'\{\{_\("(.*?)"\)\}\}')


# The document template. Human-facing text is tokenised as {{TOKEN}} (HTML) or
# read from the injected `T` object (JavaScript), so this markup is shared by
# every language.
_GUI_TEMPLATE: str = r"""<!doctype html>
<html lang="{{LANG}}" data-color-scheme="light">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Best Engine AI Helper</title>
  <meta name="description" content="{{_("This machine's hardware characteristics and the best local engine (LLM / VLM) for a given task.")}}" />
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
  <a href="#main" class="sr-only focus:not-sr-only focus:absolute focus:z-50 focus:top-3 focus:left-3 focus:rounded-lg focus:bg-brand-blue focus:px-4 focus:py-2 focus:text-white">{{_("Skip to content")}}</a>

  <header class="sticky top-0 z-40 border-b border-neutral-200/70 bg-white/80 backdrop-blur dark:border-neutral-800 dark:bg-[#0B0B0C]/80">
    <nav class="mx-auto flex max-w-4xl items-center justify-between px-5 py-3" aria-label="{{_("Main")}}">
      <span class="flex items-center gap-2 font-semibold tracking-tight">
        <img src="/static/icons/android-chrome-192x192.png" alt="" width="28" height="28" class="rounded-lg" />
        Best Engine AI Helper
      </span>
      <div class="flex items-center gap-3 text-sm">
        <a href="https://github.com/warith-harchaoui/best-engine-ai-helper"
           class="hidden rounded px-1 hover:text-brand-blue focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-blue sm:inline">
          {{_("⭐️ on GitHub")}}
        </a>
        <a href="{{LANG_HREF}}" aria-label="{{LANG_ARIA}}"
           class="rounded px-1.5 py-1 font-mono text-xs font-semibold hover:text-brand-blue focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-blue">
          {{_("🇫🇷")}}
        </a>
        <button id="theme-toggle" type="button" aria-label="{{_("Toggle theme")}}"
                class="rounded-full px-2 py-1 text-lg leading-none hover:bg-neutral-100 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-blue dark:hover:bg-neutral-800">
          🌞
        </button>
      </div>
    </nav>
  </header>

  <main id="main">
    <section class="mx-auto max-w-4xl px-5 py-14">
      <p class="font-mono text-sm text-brand-blue">best-engine-ai-helper</p>
      <h1 class="mt-1 font-serif text-4xl font-bold tracking-tight sm:text-5xl">{{_("Best local or cloud LLM / VLM")}}</h1>
      <p class="mt-3 max-w-2xl text-base text-neutral-600 dark:text-neutral-300">
        {{_("This machine's characteristics, and the best engine (LLM / VLM), local or cloud, for the task you describe.")}}
      </p>
    </section>

    <!-- 1) Hardware snapshot -->
    <section class="border-t border-neutral-200/70 dark:border-neutral-800">
      <div class="mx-auto max-w-4xl px-5 py-10">
        <div class="mb-4 flex items-center justify-between">
          <h2 class="text-2xl font-bold tracking-tight">{{_("System characteristics")}}</h2>
          <button id="refresh-system"
                  class="rounded-lg border border-neutral-300 px-3 py-1.5 text-sm font-medium
                         hover:border-brand-blue focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-blue
                         dark:border-neutral-600">
            {{_("Refresh")}}
          </button>
        </div>
        <div id="system-grid"
             class="grid grid-cols-2 gap-4 rounded-xl border border-neutral-200 bg-white p-5 text-sm shadow-sm
                    sm:grid-cols-3 dark:border-neutral-800 dark:bg-neutral-950">
          <p class="col-span-full text-neutral-500 dark:text-neutral-400">{{_("Detecting…")}}</p>
        </div>
      </div>
    </section>

    <!-- 1bis) Cloud providers, and why one is unavailable -->
    <section class="border-t border-neutral-200/70 dark:border-neutral-800">
      <div class="mx-auto max-w-4xl px-5 py-10">
        <h2 class="text-2xl font-bold tracking-tight">{{_("Cloud providers")}}</h2>
        <p class="mt-2 max-w-3xl text-neutral-600 dark:text-neutral-300">{{_("A provider whose key is missing is not a candidate. Keys are looked up in settings.yaml, then a .env file, then the environment, then the OS keychain. Only their presence is checked here; no key value is ever read or shown.")}}</p>
        <div id="provider-list"
             class="mt-4 grid gap-2 rounded-xl border border-neutral-200 bg-white p-5 text-sm shadow-sm
                    dark:border-neutral-800 dark:bg-neutral-950">
          <p class="text-neutral-500 dark:text-neutral-400">{{_("Detecting…")}}</p>
        </div>
      </div>
    </section>

    <!-- 2) Task description -->
    <section class="border-t border-neutral-200/70 dark:border-neutral-800">
      <div class="mx-auto max-w-4xl px-5 py-10">
        <h2 class="text-2xl font-bold tracking-tight">{{_("Describe the task")}}</h2>
        <p class="mt-2 max-w-3xl text-neutral-600 dark:text-neutral-300">
          {{_("One sentence is enough — visual keywords add a VLM to the recommendation.")}}
        </p>
        <div class="mt-6 rounded-xl border border-neutral-200 bg-white p-5 shadow-sm dark:border-neutral-800 dark:bg-neutral-950">
          <label for="task" class="sr-only">{{_("Task description")}}</label>
          <textarea id="task" rows="3" placeholder="{{_("e.g. “write product descriptions and check photo quality”")}}"
                    class="w-full rounded-lg border border-neutral-300 bg-white px-3 py-2 text-sm text-neutral-900
                           focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-blue
                           dark:border-neutral-600 dark:bg-neutral-900 dark:text-neutral-100"></textarea>
          <div class="mt-4 flex flex-wrap items-center gap-3">
            <button id="run-recommend"
                    class="rounded-lg bg-brand-blue px-4 py-2 text-sm font-semibold text-white
                           hover:bg-brand-bluedark focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-blue
                           disabled:opacity-50">
              {{_("Recommend the best engine(s)")}}
            </button>
            <label class="flex items-center gap-2 rounded-lg border border-neutral-200 bg-neutral-50 px-3 py-1.5 text-xs text-neutral-600
                          dark:border-neutral-800 dark:bg-neutral-900 dark:text-neutral-400">
              {{_("Mode")}}
              <select id="mode"
                      class="rounded border border-neutral-300 bg-white px-2 py-1 text-xs text-neutral-900
                             focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-blue
                             dark:border-neutral-600 dark:bg-neutral-950 dark:text-neutral-100">
                <option value="local">{{_("Local (free)")}}</option>
                <option value="cloud">{{_("Cloud (paid)")}}</option>
              </select>
            </label>
            <label id="headroom-field" class="flex items-center gap-2 rounded-lg border border-neutral-200 bg-neutral-50 px-3 py-1.5 text-xs text-neutral-600
                          dark:border-neutral-800 dark:bg-neutral-900 dark:text-neutral-400">
              {{_("Memory headroom")}}
              <input id="headroom" type="number" min="0" max="0.5" step="0.05" value="0.5"
                     class="w-16 rounded border border-neutral-300 bg-white px-2 py-1 text-xs text-neutral-900
                            focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-blue
                            dark:border-neutral-600 dark:bg-neutral-950 dark:text-neutral-100" />
            </label>
            <label id="live-field" class="flex items-center gap-2 rounded-lg border border-neutral-200 bg-neutral-50 px-3 py-1.5 text-xs text-neutral-600
                          dark:border-neutral-800 dark:bg-neutral-900 dark:text-neutral-400">
              <input id="live" type="checkbox"
                     class="rounded border-neutral-300 text-brand-blue focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-blue
                            dark:border-neutral-600" />
              {{_("Live server load")}}
            </label>
            <label id="qvc-field" style="display:none" class="items-center gap-2 rounded-lg border border-neutral-200 bg-neutral-50 px-3 py-1.5 text-xs text-neutral-600
                          dark:border-neutral-800 dark:bg-neutral-900 dark:text-neutral-400">
              {{_("quality / cost")}}
              <input id="qvc" type="number" min="0" max="1" step="0.1" value="0.7"
                     class="w-14 rounded border border-neutral-300 bg-white px-2 py-1 text-xs text-neutral-900
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

    <!-- 4) Activity ledger -->
    <section class="border-t border-neutral-200/70 dark:border-neutral-800">
      <div class="mx-auto max-w-4xl px-5 py-10">
        <div class="mb-4 flex items-center justify-between">
          <h2 class="text-2xl font-bold tracking-tight">{{_("Activity")}}</h2>
          <button id="refresh-activity"
                  class="rounded-lg border border-neutral-300 px-3 py-1.5 text-sm font-medium
                         hover:border-brand-blue focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-blue
                         dark:border-neutral-600">
            {{_("Refresh")}}
          </button>
        </div>
        <p class="mb-4 max-w-2xl text-sm text-neutral-600 dark:text-neutral-300">{{_("Local call ledger (user, model, cost) — see the `activity` command.")}}</p>
        <div id="activity" class="rounded-xl border border-neutral-200 bg-white p-5 text-sm shadow-sm dark:border-neutral-800 dark:bg-neutral-950">
          <p class="text-neutral-500 dark:text-neutral-400">{{_("Loading…")}}</p>
        </div>
      </div>
    </section>
  </main>

  <footer class="border-t border-neutral-200/70 py-10 dark:border-neutral-800">
    <div class="mx-auto max-w-4xl px-5 text-sm text-neutral-500 dark:text-neutral-400">
      <p>
        <a class="underline hover:text-brand-blue" href="https://github.com/warith-harchaoui/best-engine-ai-helper">best-engine-ai-helper</a>
        · {{_("local only, no telemetry")}} ·
        <a class="underline hover:text-brand-blue" href="https://www.linkedin.com/in/warith-harchaoui/">Warith Harchaoui</a>
      </p>
    </div>
  </footer>

  <script type="module">
    // All user-facing strings for this render, injected from the server.
    const T = {{JS_T}};

    const $ = (id) => document.getElementById(id);
    // Everything below builds HTML with template literals and assigns it via
    // innerHTML, so any value that came from outside this file has to be
    // escaped on the way in. Model ids and provider names are the ones that
    // travel: the catalog can be refreshed from ollama.com, and an engine file
    // is hand-editable. None of that is attacker-controlled in a loopback,
    // single-user GUI, which is why this is hygiene rather than a patched
    // breach -- but "it happens to be safe today" is not a property that
    // survives a new source, and one helper is cheaper than re-auditing.
    const esc = (v) =>
      String(v ?? "").replace(/[&<>"']/g, (c) =>
        ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]
      );

    const status = (msg) => { $("status").textContent = msg; };

    // Numbers are localised, not just the labels around them. `toFixed` and a
    // bare "$" prefix write English conventions whatever the page language is,
    // so the French GUI read "47.2 GB" and "$0.0020" where French writes
    // "47,2" and puts the currency after the amount. Intl does the whole job
    // with no dependency, and the formatters are built once rather than per
    // cell: this page redraws whole tables.
    const LOCALE = {{JS_LOCALE}};
    const _nf = (min, max) =>
      new Intl.NumberFormat(LOCALE, { minimumFractionDigits: min, maximumFractionDigits: max });
    const _nf0 = _nf(0, 0);
    const _nf1 = _nf(1, 1);
    const _money = new Intl.NumberFormat(LOCALE, {
      style: "currency", currency: "USD",
      minimumFractionDigits: 4, maximumFractionDigits: 4,
    });
    const _pct = new Intl.NumberFormat(LOCALE, {
      style: "percent", minimumFractionDigits: 1, maximumFractionDigits: 1,
    });
    const _money2 = new Intl.NumberFormat(LOCALE, {
      style: "currency", currency: "USD",
      minimumFractionDigits: 2, maximumFractionDigits: 2,
    });
    // Two different shapes arrive here: `error_rate` is a fraction, the load
    // figures are already percentages. Intl's percent style multiplies by 100,
    // so the second kind is divided first rather than formatted as 2500 %.
    const _pct0 = new Intl.NumberFormat(LOCALE, { style: "percent", maximumFractionDigits: 0 });
    const fmt0 = (v) => _nf0.format(Number(v));
    const fmtPrice = (v) => _money2.format(Number(v));
    const fmtPctOf100 = (v) => _pct0.format(Number(v) / 100);
    const fmtMoney = (v) => _money.format(Number(v));
    const fmtPct = (v) => _pct.format(Number(v));
    const fmt1 = (v) => (v === null || v === undefined ? "?" : _nf1.format(Number(v)));
    // Same notation as the `candidates` CLI table: a trailing "*" means the
    // figure was measured on this machine, "~" that it was estimated from
    // memory bandwidth. One marker for one fact, across every surface.
    const fmtTpsBasis = (v, basis) =>
      !v ? "-" : basis === "measured" ? fmt0(v) + "*" : "~" + fmt0(v);

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
    function renderProviders(data) {
      const rows = (data.providers || []).map((p) => {
        // Unavailable providers are dimmed rather than hidden: the point is to
        // show the rule being applied, not to quietly shorten the list.
        const dim = p.available ? "" : "opacity-60";
        const badge = p.available
          ? `<span class="rounded-full bg-emerald-100 px-2 py-0.5 text-xs font-medium text-emerald-800
                          dark:bg-emerald-900/40 dark:text-emerald-300">${T.provReady}</span>`
          : `<span class="rounded-full bg-amber-100 px-2 py-0.5 text-xs font-medium text-amber-800
                          dark:bg-amber-900/40 dark:text-amber-300">${T.provNoKey}</span>`;
        const why = p.available
          ? ""
          : `<p class="mt-0.5 text-xs text-neutral-500 dark:text-neutral-400">${esc(p.reason)}</p>`;
        return `<div class="flex items-start justify-between gap-4 ${dim}">
            <div>
              <p class="font-medium">${esc(p.provider)}
                <span class="font-mono text-xs text-neutral-500 dark:text-neutral-400">${esc(p.key_env)}</span>
              </p>
              ${why}
            </div>
            ${badge}
          </div>`;
      });
      $("provider-list").innerHTML =
        rows.join("") || `<p class="text-neutral-500 dark:text-neutral-400">-</p>`;
    }

    async function loadProviders() {
      try {
        const res = await fetch("/api/providers");
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        renderProviders(await res.json());
      } catch (err) {
        $("provider-list").innerHTML =
          `<p class="text-red-600 dark:text-red-400">${T.detectFail}${err}</p>`;
      }
    }

    // --- Preferences -------------------------------------------------------
    // The YAML on disk is the source of truth: these handlers write it and read
    // it back, rather than keeping a second copy of the state in the page.
    const PREF_FIELDS = {
      headroom: { el: "headroom", kind: "number" },
      quality_vs_cost: { el: "qvc", kind: "number" },
      live_load: { el: "live", kind: "bool" },
    };

    function applyPreferences(prefs) {
      for (const [key, spec] of Object.entries(PREF_FIELDS)) {
        const el = $(spec.el);
        if (!el || prefs[key] === undefined || prefs[key] === null) continue;
        if (spec.kind === "bool") el.checked = Boolean(prefs[key]);
        else el.value = prefs[key];
      }
    }

    async function loadPreferences() {
      try {
        const res = await fetch("/api/preferences");
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        applyPreferences(await res.json());
      } catch (err) {
        // Preferences are a convenience, not a prerequisite: the form keeps
        // its defaults and the page stays usable.
        console.warn("preferences unavailable:", err);
      }
    }

    async function savePreferences() {
      const body = {};
      for (const [key, spec] of Object.entries(PREF_FIELDS)) {
        const el = $(spec.el);
        if (!el) continue;
        body[key] = spec.kind === "bool" ? el.checked : Number(el.value);
      }
      try {
        await fetch("/api/preferences", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(body),
        });
      } catch (err) {
        console.warn("preferences not saved:", err);
      }
    }

    for (const spec of Object.values(PREF_FIELDS)) {
      const el = $(spec.el);
      if (el) el.addEventListener("change", savePreferences);
    }

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
          <dd class="font-medium">${esc(value)}</dd>
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
        field(T.fBandwidth, comp.bandwidth_gbs ? `${fmt0(comp.bandwidth_gbs)} ${T.gbs}` : T.unknown),
        field(T.fBudget, `${fmt1(info.memory_budget_gb)} ${T.gb}`),
      ];
      $("system-grid").innerHTML = cells.join("");
    }

    $("refresh-system").addEventListener("click", () => {
      loadSystem();
      loadProviders();
    });
    loadSystem();
    loadProviders();
    loadPreferences();

    // --- 4) Activity ledger ------------------------------------------------
    async function loadActivity() {
      $("activity").innerHTML =
        `<p class="text-neutral-500 dark:text-neutral-400">${T.activityLoading}</p>`;
      try {
        const res = await fetch("/api/activity");
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        renderActivity(await res.json());
      } catch (err) {
        $("activity").innerHTML =
          `<p class="text-red-600 dark:text-red-400">${T.activityFail}${err}</p>`;
      }
    }

    function activityRow(row, keyName) {
      const cost = row.cost_usd != null ? fmtMoney(row.cost_usd) : T.unknownCost;
      return `
        <tr class="border-t border-neutral-200 dark:border-neutral-800">
          <td class="py-1.5 pr-3 font-mono">${esc(row[keyName])}</td>
          <td class="py-1.5 pr-3">${row.calls}</td>
          <td class="py-1.5">${cost}</td>
        </tr>`;
    }

    function activityTable(title, rows, keyName) {
      if (!rows.length) return "";
      return `
        <div class="mt-4">
          <h3 class="mb-1 text-xs font-semibold uppercase tracking-wide text-neutral-500 dark:text-neutral-400">${title}</h3>
          <table class="w-full text-left text-xs">
            <thead><tr class="text-neutral-500 dark:text-neutral-400">
              <th class="pb-1 pr-3 font-medium">${keyName}</th>
              <th class="pb-1 pr-3 font-medium">${T.thCalls}</th>
              <th class="pb-1 font-medium">${T.thCost}</th>
            </tr></thead>
            <tbody>${rows.map((r) => activityRow(r, keyName)).join("")}</tbody>
          </table>
        </div>`;
    }

    function renderActivity(data) {
      if (!data.total_calls) {
        $("activity").innerHTML =
          `<p class="text-neutral-500 dark:text-neutral-400">${T.noActivity}</p>`;
        return;
      }
      const cost = data.total_cost_usd != null ? fmtMoney(data.total_cost_usd) : T.unknownCost;
      const parts = [`
        <p>
          <span class="font-semibold">${data.total_calls}</span> ${T.calls} ·
          ${T.totalCost} <span class="font-semibold">${cost}</span> ·
          ${T.errorRate} <span class="font-semibold">${fmtPct(data.error_rate)}</span>
        </p>`];
      parts.push(activityTable(T.byUser, data.by_user, "user"));
      parts.push(activityTable(T.byModel, data.by_model, "model"));
      $("activity").innerHTML = parts.join("");
    }

    $("refresh-activity").addEventListener("click", loadActivity);
    loadActivity();

    // --- 2 & 3) Recommendation -------------------------------------------
    $("run-recommend").addEventListener("click", runRecommend);
    $("task").addEventListener("keydown", (e) => {
      if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) runRecommend();
    });

    // The mode dropdown reflects best-engine's own mode: local / mode: cloud
    // brief distinction: only ONE mode's controls are relevant at a time
    // (headroom/live for local, quality_vs_cost for cloud), and only that
    // mode's recommendation is rendered -- see applyModeVisibility/renderResults.
    function applyModeVisibility() {
      const isCloud = $("mode").value === "cloud";
      $("headroom-field").style.display = isCloud ? "none" : "flex";
      $("live-field").style.display = isCloud ? "none" : "flex";
      $("qvc-field").style.display = isCloud ? "flex" : "none";
    }
    $("mode").addEventListener("change", () => {
      applyModeVisibility();
      // Re-run immediately if a task is already filled in, so switching
      // modes feels like a real toggle, not a setting that needs a second click.
      if ($("task").value.trim()) runRecommend();
    });
    applyModeVisibility();

    // Deep link: /gui?task=...&mode=cloud pre-fills the box and runs it on
    // load, so a recommendation is shareable by URL. ?lang is handled server-side.
    const urlParams = new URLSearchParams(location.search);
    const urlTask = urlParams.get("task");
    const urlMode = urlParams.get("mode");
    if (urlMode === "cloud" || urlMode === "local") {
      $("mode").value = urlMode;
      applyModeVisibility();
    }
    if (urlTask) {
      $("task").value = urlTask;
      runRecommend();
    }

    async function runRecommend() {
      const task = $("task").value.trim() || null;
      const mode = $("mode").value;
      // Matches score.MAX_HEADROOM: any value above 0.5 is silently clamped
      // down to it server-side, so the input's own range is capped at 0.5.
      const headroom = Number($("headroom").value) || 0.5;
      const live = $("live").checked;
      const quality_vs_cost = Number($("qvc").value);
      $("run-recommend").disabled = true;
      status(T.analyzing);
      $("results").innerHTML = "";
      try {
        const res = await fetch("/api/recommend", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          // Both local and cloud pick data are always fetched (both are
          // cheap: no API key, no network); the mode dropdown decides which
          // one is RENDERED, in renderResults(report, mode) below.
          body: JSON.stringify({ task, headroom, live, cloud: true, quality_vs_cost }),
        });
        if (!res.ok) throw new Error(`HTTP ${res.status}: ${await res.text()}`);
        const report = await res.json();
        renderResults(report, mode);
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
          <td class="py-1.5 pr-3 font-mono">${esc(r.id)}</td>
          <td class="py-1.5 pr-3">${fmt1(r.ram_gb)}</td>
          <td class="py-1.5 pr-3">${fmt0(r.score)}</td>
          <td class="py-1.5 pr-3">${r.fits ? T.yes : T.no}</td>
          <td class="py-1.5 pr-3">${r.structured_output === false ? T.no : T.yes}</td>
          <td class="py-1.5">${fmtTpsBasis(r.est_tokens_per_s, r.tps_basis)}</td>
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
          ${pill(esc(chosen.id))}
          <span class="text-neutral-600 dark:text-neutral-300">
            ${fmt1(chosen.ram_gb)} ${T.gb}, ${T.score} ${fmt0(chosen.score)}, ${fmtTpsBasis(chosen.est_tokens_per_s, chosen.tps_basis)} ${T.tps}
          </span>
          ${chosen.fits ? "" : `<span class="text-red-600 dark:text-red-400">${T.overBudget}</span>`}
          ${chosen.structured_output === false ? `<span class="text-amber-600 dark:text-amber-400">${T.notStructured}</span>` : ""}
        </p>
        ${alt ? `<p class="mt-2 text-xs text-neutral-500 dark:text-neutral-400">${T.lighterAlt} <span class="font-mono">${alt.id}</span> — ${fmt1(alt.ram_gb)} ${T.gb}, ${T.score} ${fmt0(alt.score)}, ${fmtTpsBasis(alt.est_tokens_per_s, alt.tps_basis)} ${T.tps}.</p>` : ""}
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
                    <th class="pb-1.5 pr-3 font-medium">${T.thStructured}</th>
                    <th class="pb-1.5 font-medium">${T.thTps}</th>
                  </tr>
                </thead>
                <tbody>${block.candidates.map(candidateRow).join("")}</tbody>
              </table>
            </div>
          </details>
        </div>`;
    }

    function cloudCandidateRow(r) {
      return `
        <tr class="border-t border-neutral-200 dark:border-neutral-800">
          <td class="py-1.5 pr-3 font-mono">${esc(r.id)}</td>
          <td class="py-1.5 pr-3">${esc(r.provider)}</td>
          <td class="py-1.5 pr-3">${fmt0(r.score)}</td>
          <td class="py-1.5 pr-3">${r.price_per_1m == null ? "?" : fmtPrice(r.price_per_1m)}</td>
          <td class="py-1.5">${r.structured_output === false ? T.no : T.yes}</td>
        </tr>`;
    }

    function cloudKindCard(kind, block) {
      const chosen = block.chosen;
      const chosenHtml = chosen ? `
        <p class="flex flex-wrap items-center gap-2 text-sm">
          ${pill(esc(chosen.id))}
          <span class="text-neutral-600 dark:text-neutral-300">
            ${esc(chosen.provider)}, ${T.score} ${fmt0(chosen.score)}, ${chosen.price_per_1m == null ? T.priceUnknown : `~${fmtPrice(chosen.price_per_1m)}/1M ${T.blended}`}
          </span>
          ${chosen.structured_output === false ? `<span class="text-amber-600 dark:text-amber-400">${T.notStructured}</span>` : ""}
        </p>
      ` : `<p class="text-sm text-neutral-500 dark:text-neutral-400">${T.noCandidate}</p>`;

      return `
        <div class="overflow-hidden rounded-xl border border-brand-blue/30 bg-white p-5 shadow-sm dark:border-brand-blue/40 dark:bg-neutral-950">
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
                    <th class="pb-1.5 pr-3 font-medium">${T.thProvider}</th>
                    <th class="pb-1.5 pr-3 font-medium">${T.thScore}</th>
                    <th class="pb-1.5 pr-3 font-medium">${T.thPrice}</th>
                    <th class="pb-1.5 font-medium">${T.thStructured}</th>
                  </tr>
                </thead>
                <tbody>${block.candidates.map(cloudCandidateRow).join("")}</tbody>
              </table>
            </div>
          </details>
        </div>`;
    }

    function renderResults(report, mode) {
      const task = report.task || {};
      const parts = [];

      parts.push(`
        <div class="rounded-xl border border-neutral-200 bg-neutral-50 p-4 text-sm dark:border-neutral-800 dark:bg-neutral-900">
          <p><span class="text-neutral-500 dark:text-neutral-400">${T.task}</span> ${task.input ? task.input : T.genericAssistant}</p>
          ${task.language ? `<p class="mt-1 text-xs text-neutral-500 dark:text-neutral-400">${T.language} ${task.language}</p>` : ""}
          ${task.matched && task.matched.length ? `<p class="mt-1 text-xs text-neutral-500 dark:text-neutral-400">${T.matched} ${task.matched.join(", ")}</p>` : ""}
          <p class="mt-1 text-xs text-neutral-500 dark:text-neutral-400">${T.needs} ${task.kinds.map((k) => k.toUpperCase()).join(", ")}</p>
        </div>`);

      // The mode dropdown is a real switch, not a comparison view: only the
      // selected mode's recommendation renders, mirroring how a llm.brief.yaml
      // carries exactly one mode (local or cloud), never both at once.
      if (mode === "cloud") {
        const cloudBlocks = Object.entries((report.cloud || {}).recommendations || {});
        const cloudGridClass = cloudBlocks.length > 1 ? "mt-4 grid gap-4 sm:grid-cols-2" : "mt-4 grid gap-4";
        parts.push(`
          <div class="mt-4">
            <p class="text-xs text-neutral-500 dark:text-neutral-400">${T.cloudNote}</p>
            <div class="${cloudGridClass}">${cloudBlocks.map(([kind, block]) => cloudKindCard(kind, block)).join("")}</div>
          </div>`);
      } else {
        const load = report.server_load;
        if (load) {
          const gpuPart = load.gpu_percent != null ? `, GPU ${fmtPctOf100(load.gpu_percent)}` : "";
          parts.push(`
            <div class="mt-3 rounded-xl border border-neutral-200 bg-neutral-50 p-4 text-xs text-neutral-600 dark:border-neutral-800 dark:bg-neutral-900 dark:text-neutral-400">
              <span class="font-medium text-neutral-700 dark:text-neutral-300">${T.serverLoad}</span>
              ${fmt1(load.available_ram_gb)} ${T.gb} ${T.ramFree}, CPU ${fmtPctOf100(load.cpu_percent)}${gpuPart},
              ${T.diskFree} ${fmt1(load.disk_free_gb)} ${T.gb} (${fmtPctOf100(load.disk_percent_used)}),
              ${T.runningEngines} ${load.running_engines}
            </div>`);
        }

        const kindBlocks = Object.entries(report.recommendations || {});
        const gridClass = kindBlocks.length > 1 ? "mt-4 grid gap-4 sm:grid-cols-2" : "mt-4 grid gap-4";
        parts.push(`<div class="${gridClass}">${kindBlocks.map(([kind, block]) => kindCard(kind, block)).join("")}</div>`);
      }

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
        Two-letter language code. Anything without a compiled catalogue falls
        back to :data:`_DEFAULT_LANG`, so an unknown ``?lang=`` never 500s.

    Returns
    -------
    str
        The complete HTML document for that language.
    """
    cat = _catalog()
    resolved = cat.resolve(lang)
    translate = cat.translator_for(resolved).gettext

    # The other language, for the toggle. With two languages this is "the one
    # that is not current"; with more it is the next one round, which keeps the
    # link a cycle rather than a dead end.
    languages = cat.languages
    other = languages[(languages.index(resolved) + 1) % len(languages)]

    def _render_source(match: re.Match[str]) -> str:
        """Translate one ``{{_("…")}}`` site and escape it for HTML.

        Escaping is not optional: these land in attributes (placeholder, aria,
        href) as readily as in text nodes, and a French apostrophe — or the
        curly quotes in the task placeholder — would close the attribute early.
        """
        return html.escape(translate(match.group(1)), quote=True)

    page = _SOURCE_RE.sub(_render_source, _GUI_TEMPLATE)
    page = page.replace("{{LANG}}", html.escape(resolved, quote=True))
    page = page.replace("{{LANG_HREF}}", html.escape(f"/gui?lang={other}", quote=True))
    page = page.replace("{{LANG_ARIA}}", html.escape(_ENDONYMS.get(other, other), quote=True))
    # Emit the JS strings as a JSON literal so quotes/accents are escaped safely.
    table = {name: translate(source) for name, source in _JS_NAME_TO_SOURCE.items()}
    page = page.replace("{{JS_T}}", json.dumps(table, ensure_ascii=False))
    # The page formats its own numbers, so it needs the locale it resolved to --
    # not the one that was asked for, which may have fallen back.
    page = page.replace("{{JS_LOCALE}}", json.dumps(resolved))
    return page


# French render, kept as a module constant for the default page and for callers
# and tests that want the markup without going through render_gui().
GUI_HTML: str = render_gui("fr")
