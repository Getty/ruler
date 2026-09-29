# ruler — Design

Claude-Code-Plugin (Getty-Marketplace), das dafür sorgt, dass der **Kern der
Projekt-Instruktionen** — CLAUDE.md und die Rules ohne `paths:` — nach jeder
Compaction wieder im Kontext steht, und dass die Compaction-Zusammenfassung keine
veralteten Kopien davon mitschleppt. Codex ist in v1 bewusst draußen (siehe unten).

Stand: 2026-09-29, Claude Code 2.1.284.

## Problem, belegt

**Laut Doku** ([context-window → What survives compaction](https://code.claude.com/docs/en/context-window.md))
werden Projekt-Root-CLAUDE.md und Rules ohne `paths:` nach der Compaction „re-injected
from disk“. Rules mit `paths:` und verschachtelte CLAUDE.md werden „summarized away“ und
erst wieder geladen, wenn Claude eine passende Datei liest.

**In der Praxis nicht immer.** Auswertung aller 40 Compactions in 32 lokalen
Transkripten (`~/.claude/projects/*/*.jsonl`, v2.1.257–2.1.283): Welche
Instruktionsdateien (`attachment.type` `instructions` / `nested_memory`) waren vor der
Compaction angehängt, welche danach wieder? In 5 von 40 Fällen fehlte etwas:

| Session | Compaction | Danach fehlend |
|---|---|---|
| `p5-text-nunjucks/e6ce8468` | #1 (auto) | CLAUDE.md **und** Rules, 9 Prompts / 115 Antworten bis Session-Ende |
| `sunriser/744df281` | #4 (auto) | CLAUDE.md und Rules 25 Prompts lang, dann tauchen sie wieder auf |
| `sunriser/744df281` | #5 (auto) | `sunriser-rules.md` |
| `langertha/9b3e6b6f` | #2 (auto) | `langertha-rules.md` |
| `langertha/9b3e6b6f`, `p5-beepack/4824ae4b` | #1 | verschachtelte CLAUDE.md + Rules aus Worktree/Unterverzeichnis |

Die von der Compaction wörtlich behaltenen Nachrichten (`compactMetadata.preservedMessages`)
enthalten die fehlenden Instruktionen in diesen Fällen nicht. Vorbehalt: Das
Transkript-Format ist undokumentiert; dass die Dateien auf einem Weg im Kontext waren,
der im Transkript nicht auftaucht, ist nicht völlig ausgeschlossen. Die letzte Zeile der
Tabelle ist dokumentiertes Verhalten, kein Fehler — und liegt außerhalb von rulers
Garantie (siehe Umfang).

## Umfang

**Garantiert (der Kern):** genau die Dateien, die Claude Code beim Session-Start lädt —
CLAUDE.md, `CLAUDE.local.md`, `~/.claude/CLAUDE.md`, die Rules ohne `paths:` (Projekt
und User) und alles, was diese per `@import` einbinden.

**Nicht garantiert, absichtlich:** Rules mit `paths:`, verschachtelte CLAUDE.md, Skills.
Die lädt Claude Code laut Doku selbst nach, sobald eine passende Datei wieder gelesen
wird; sie immer einzufügen, hebelt ihren Zweck aus. Wer sie über die Compaction retten
muss, macht sie zu Kern (Doku-Empfehlung: `paths:` entfernen).

**Nicht in v1:**
- **Codex.** Codex lädt AGENTS.md vom Root bis zum cwd beim Start, nicht lazy, und baut
  sie nach einer Compaction als Teil des Ausgangskontexts neu auf (nur aus
  Sekundärquellen belegt). Ohne nachgewiesene Lücke kein Codex-Teil. Ein Live-Test, der
  eine Lücke zeigt, eröffnet eine eigene Stufe.
- **Erinnerung in tiefen Sessions** ohne Compaction (seatbelt-Ansatz). Nutzen unbelegt.
- **Sichtbare Meldung / Log-Kommando.** Das Ereignis-Log pro Session (unten) reicht als
  Beleg beim Debuggen.

## Mechanismus

Vier Bausteine, alle über dokumentierte Hooks, kein Transkript-Parsing.

### 1. Mitschreiben — `InstructionsLoaded`

Feuert für jede geladene CLAUDE.md / `.claude/rules/*.md` mit `file_path`,
`memory_type`, `load_reason` (`session_start`, `nested_traversal`, `path_glob_match`,
`include`, `compact`), `globs`, `trigger_file_path`, `parent_file_path`. Der Hook läuft
asynchron und hat keine Entscheidungsgewalt.

ruler hängt pro Ereignis **eine Zeile** an `${CLAUDE_PLUGIN_DATA}/sessions/<session_id>.jsonl`
an (`O_APPEND`, eine Zeile < `PIPE_BUF` → atomar, keine Sperre nötig, auch wenn mehrere
asynchrone Hooks gleichzeitig laufen). Kein Lesen-Ändern-Schreiben.

**Kern ableiten** (reine Funktion über das Log):
- `session_start` → Kern.
- `include` → Kern, wenn `parent_file_path` im Kern ist (rekursiv).
- `compact` für eine Datei, die noch nicht im Kern ist → Kern (z. B. eine während der
  Session neu angelegte Rule, die Claude Code bei der Compaction mitlädt).
- `nested_traversal`, `path_glob_match` und deren Includes → nie Kern.

**Ersatz, wenn das Log keine `session_start`-Zeilen hat** (Plugin mitten in der Session
installiert, Hook nicht gefeuert): Kern von der Platte ermitteln — `~/.claude/CLAUDE.md`,
`~/.claude/rules/**/*.md` ohne `paths:`, vom cwd aufwärts bis `/` jede `CLAUDE.md`,
`.claude/CLAUDE.md`, `CLAUDE.local.md`, im Projekt `.claude/rules/**/*.md` ohne `paths:`,
dazu `@imports` rekursiv (Tiefe ≤ 5, wie Claude Code). Stufe 0 prüft, ob diese Liste mit
dem übereinstimmt, was `InstructionsLoaded` in derselben Session meldet.

### 2. Zusammenfassung lenken — `PreCompact`

Eingabe `trigger` (`manual`/`auto`) und `custom_instructions` (String oder `null`).
Ausgabe `hookSpecificOutput.newCustomInstructions` ersetzt die Anweisungen für die
Zusammenfassung.

ruler **hängt an**, statt zu ersetzen — ein `/compact focus on X` des Users bleibt
erhalten. Sein Block steht zwischen festen Markern; ist er schon da (Anweisungen, die
über mehrere Compactions bestehen bleiben), wird er ersetzt, nicht verdoppelt.
Wortlaut (englisch, sachlich, keine „SYSTEM:“/„IMPORTANT“-Rahmung, die Claude Codes
Prompt-Injection-Schutz auslösen kann):

```
<!-- ruler -->
These instruction files are re-attached from disk right after this compaction:
- /home/…/CLAUDE.md
- /home/…/.claude/rules/foo-rules.md
Do not reproduce their content in the summary. Do keep every instruction, decision
or correction the user gave in the conversation itself — those live in no file.
<!-- /ruler -->
```

Außerdem schreibt der Hook eine Zeile `{"event":"compact","trigger":…}` ins Log und
legt die Markierung `${CLAUDE_PLUGIN_DATA}/pending/<session_id>` an.

### 3. Prüfen und nachreichen

Fehlend = Kern − {Dateien mit `load_reason: compact` nach der letzten `compact`-Zeile}.
Fehlende Dateien werden **frisch von der Platte** gelesen (Änderungen während der
Session gelten) und als `additionalContext` eingefügt; gelöschte Dateien werden
übersprungen. Danach wird `pending/<session_id>` entfernt.

Kann die Prüfung nicht sicher ausgewertet werden (Log unlesbar, kein Kern ableitbar und
Ersatz leer), wird der **ganze Kern** eingefügt: lieber doppelt als gar nicht.

Format pro Datei, sachlich wie oben:

```
Project instructions from /home/…/.claude/rules/foo-rules.md (re-attached by ruler after compaction):

<Inhalt>
```

**Größe:** Passt der Fehlbestand nicht in die Obergrenze für `additionalContext`
(Stufe 0 misst sie), gehen ganze Dateien hinein, solange sie passen; für den Rest ein
Satz „Read these files now before continuing: …“ — die Datei lädt dann das Read-Tool.

**Wo genau** hängt an einer Frage, die nur live zu klären ist (Stufe 0):
`InstructionsLoaded` läuft asynchron. Stehen die `compact`-Zeilen im Log, **bevor**
`SessionStart` mit `source: compact` läuft?

- **Ja** → Prüfen und Einfügen im `SessionStart`-Hook (Matcher `compact`). Laut Doku
  landet dessen Ausgabe im kompaktierten Kontext.
- **Nein** → `SessionStart` (compact) tut nichts; geprüft wird beim nächsten Ereignis,
  das `additionalContext` annimmt: `PostToolUse` (jeder Tool-Aufruf — eine
  Auto-Compaction mitten im Turn läuft ohne neuen Prompt weiter) oder
  `UserPromptSubmit`. Heißer Pfad: ein `sh`-Starter prüft nur, ob `pending/` leer ist,
  und beendet sich sonst sofort mit `exit 0`, ohne Python zu starten.

### 4. Aufräumen — `SessionEnd`

Löscht `sessions/<id>.jsonl` und `pending/<id>`. Beim `SessionStart` (`startup`) werden
Log-Dateien älter als 7 Tage entfernt (Sessions, die ohne `SessionEnd` endeten).

## Fehlerverhalten

- Jeder Hook endet mit `exit 0`, auch bei Ausnahmen, unlesbarem stdin, fehlendem
  `CLAUDE_PLUGIN_DATA` — ruler darf nie eine Session stören. Ausnahme ist nur das
  bewusste „ganzen Kern einfügen“, wenn die Prüfung selbst scheitert.
- Timeouts in `hooks.json`: 5 s; `InstructionsLoaded` `async`.
- Kein Netzwerk, keine Subprozesse, schreibt nur unter `${CLAUDE_PLUGIN_DATA}`.

## Sprache und Layout

Python 3, nur Standardbibliothek (wie agent-irc). Der einzige potenziell heiße Pfad
(`PostToolUse`, falls Stufe 0 ihn verlangt) wird von einem `sh`-Starter abgefangen.

| Pfad | Inhalt |
|---|---|
| `.claude-plugin/plugin.json` | Manifest, Artistic-2.0 |
| `hooks/hooks.json` | `InstructionsLoaded` (async), `PreCompact`, `SessionStart`, `SessionEnd`, ggf. `PostToolUse` + `UserPromptSubmit` |
| `hooks/ruler` | `sh`-Starter: schneller Ausstieg ohne `pending/`, sonst `exec python3 …` |
| `lib/ruler/log.py` | Ereignis-Log anhängen/lesen |
| `lib/ruler/core.py` | Kern aus dem Log ableiten; Ersatz von der Platte (inkl. `@imports`, `paths:`-Erkennung) |
| `lib/ruler/compact.py` | `PreCompact`-Anweisungen zusammenführen (Marker, idempotent) |
| `lib/ruler/restore.py` | Fehlbestand berechnen, Kontext bauen, Größenobergrenze |
| `lib/ruler/hook.py` | Einstieg: Ereignis auf Funktion abbilden, fail-open |
| `t/` | `python3 -m unittest discover -s t -v`; Fixtures = echte Hook-Payloads aus Stufe 0 |
| `README.md` | Was ruler garantiert und was nicht; Abschnitt „Keep the core small“ |

## Stufen

### Stufe 0 — Live festnageln (vor jedem Produktcode)

Ein Aufzeichnungs-Hook (schreibt nur stdin + Zeitstempel weg) auf `InstructionsLoaded`,
`PreCompact`, `PostCompact`, `SessionStart`, `PostToolUse`, `UserPromptSubmit`, in einem
Wegwerf-Projekt mit CLAUDE.md, einer Rule ohne und einer mit `paths:`, einem `@import`
und einer verschachtelten CLAUDE.md. Eine Session, manuelles `/compact`, dann eine
provozierte Auto-Compaction. Festzuhalten, jeweils mit Claude-Code-Version:

1. Reihenfolge und Zeitabstand: `PreCompact` → … → `InstructionsLoaded`(compact) vs.
   `SessionStart`(compact) vs. `PostCompact`. Stehen die compact-Zeilen vor `SessionStart`
   auf der Platte? → entscheidet Baustein 3.
2. Feuert `InstructionsLoaded`(compact) für jede Kerndatei? Auch für `@imports` (mit
   welchem `load_reason`)?
3. Obergrenze für `additionalContext` (`SessionStart`, `PostToolUse`): ab welcher Länge
   wird gekürzt oder in eine Datei ausgelagert?
4. Bleiben `custom_instructions` über mehrere Compactions bestehen (→ Marker nötig)?
   Wirkt `newCustomInstructions` auch bei `auto`?
5. Deckt sich die Ersatz-Ermittlung von der Platte mit den `session_start`-Meldungen?

Die aufgezeichneten Payloads werden zu Fixtures in `t/fixtures/`. Ergebnisse kommen mit
Datum und Version in dieses Dokument, Baustein 3 wird entsprechend festgelegt.

Hinweis Host: reuben ist knapp an RAM — eine einzelne Session, keine parallelen Agenten.

### Stufe 1 — Mitschreiben, Kern ableiten, Aufräumen

Bausteine 1 und 4, Tests gegen Fixtures.

### Stufe 2 — `PreCompact`

Baustein 2, Tests für Anhängen, Idempotenz, `null`-Eingabe.

### Stufe 3 — Prüfen und nachreichen

Baustein 3 am in Stufe 0 bestimmten Einfügepunkt; Größenobergrenze; Ersatz „ganzer Kern“.

### Stufe 4 — Live-Abnahme, README, Marketplace

Wiederholung des Stufe-0-Aufbaus mit installiertem Plugin: nach jeder Compaction sind
alle Kerndateien im Kontext, keine doppelt (außer im dokumentierten Ersatzfall).
README mit „Keep the core small“:

- CLAUDE.md kurz halten — nur, was in *jeder* Situation gilt.
- Themenbezogenes in Rules mit `paths:`, in eine CLAUDE.md im passenden Unterverzeichnis
  oder in Skills: wird bei Bedarf geladen und nach einer Compaction wieder.
- `@imports` zählen zum Kern (werden sofort geladen) — auslagern per `@import` macht den
  Kern nicht kleiner.
- Nur der Kern überlebt eine Compaction garantiert, und er kostet in jedem Kontext Tokens.

Eintrag in `~/dev/marketplace` erst nach Getty's Go.

## Erfolgskriterium

Nach jeder Compaction steht jede Kerndatei in ihrer aktuellen Fassung im Kontext, keine
doppelt (Ausnahme: der Ersatzfall bei gescheiterter Prüfung), und die Zusammenfassung
enthält keine Kopie ihres Inhalts.

## Offen

- **Name.** Es gibt ein bekanntes Projekt `ruler` (intellectronica/ruler, npm, ~2.900 Sterne), das
  Regeln an mehrere Coding-Agenten verteilt — thematisch nah. Als `ruler@getty` im
  Marketplace eindeutig, bei Suche und Repo-Namen verwechselbar.
