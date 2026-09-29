# ruler — Design

Claude-Code-Plugin (Getty-Marketplace), das dafür sorgt, dass der **Kern der
Projekt-Instruktionen** — CLAUDE.md und die Rules ohne `paths:` — nach jeder
Compaction wieder im Kontext steht, und dass die Compaction-Zusammenfassung keine
veralteten Kopien davon mitschleppt. Codex ist in v1 bewusst draußen (siehe unten).

Stand: 2026-09-29, Claude Code 2.1.284 (`claude -p`) und 2.1.285 (interaktiv). Umgesetzt
und als `ruler@getty` im Marketplace; abgenommen mit `claude -p` und in einer interaktiven
Session.

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

## Wo was steht

| Datei | Inhalt |
|---|---|
| dieses Dokument | Problem, Umfang, Layout, Erfolgskriterium, offene Punkte |
| [design/mechanism.md](design/mechanism.md) | die vier Bausteine, Fehlerverhalten — was ruler tut und warum |
| [design/measurements.md](design/measurements.md) | Messungen 1–7, Stufen, Abnahmen — womit wir es wissen |

## Sprache und Layout

Python 3, nur Standardbibliothek (wie agent-irc). Der heiße Pfad wird von einem
`sh`-Starter abgefangen.

| Pfad | Inhalt |
|---|---|
| `.claude-plugin/plugin.json` | Manifest, Artistic-2.0 |
| `hooks/hooks.json` | `InstructionsLoaded` (async), `PreCompact`, `SessionStart` (`startup\|compact`), `PostToolBatch`, `UserPromptSubmit`, `SessionEnd` |
| `hooks/ruler` | `sh`-Starter: schneller Ausstieg ohne `pending/`, sonst `python3 -m ruler.hook` |
| `lib/ruler/log.py` | Ereignis-Log anhängen/lesen, Markierung, Aufräumen |
| `lib/ruler/core.py` | Kern aus dem Log ableiten; Ersatz von der Platte (inkl. `@imports`, `paths:`-Erkennung) |
| `lib/ruler/compact.py` | Block für die `PreCompact`-Anweisungen (Marker, idempotent) |
| `lib/ruler/restore.py` | Fehlbestand berechnen, Kontext bauen, Größenobergrenze |
| `lib/ruler/hook.py` | Einstieg: Ereignis auf Funktion abbilden, fail-open |
| `t/` | `python3 -m unittest discover -s t -v`; Fixtures = echte Hook-Payloads aus Stufe 0 |
| `docs/design.md`, `docs/design/` | dieses Design: Einstieg, Mechanismus, Messungen |
| `.claude/rules/` | Wegweiser mit `paths:` auf die Teile des Designs |
| `.claude/skills/ruler-remeasure/` | Messung interaktiv wiederholen (Entwickler-Skill, nicht Teil des Plugins) |
| `README.md` | Was ruler garantiert und was nicht; Abschnitt „Keep the core small“ |

## Erfolgskriterium

Nach jeder Compaction steht jede Kerndatei in ihrer aktuellen Fassung im Kontext, keine
doppelt (Ausnahme: der Ersatzfall bei gescheiterter Prüfung), und die Zusammenfassung
enthält keine Kopie ihres Inhalts.

## Offen

- **Name.** Es gibt ein bekanntes Projekt `ruler` (intellectronica/ruler, npm, ~2.900 Sterne), das
  Regeln an mehrere Coding-Agenten verteilt — thematisch nah. Als `ruler@getty` im
  Marketplace eindeutig, bei Suche und Repo-Namen verwechselbar.
- **ruler sieht nur, was `InstructionsLoaded` meldet.** Die fünf Fälle unter *Problem,
  belegt* stammen aus Transkripten ohne Aufzeichnungs-Hook und lassen sich nicht auf
  Zuruf wiederholen. Ob Claude Code in solchen Fällen trotzdem `compact` meldet — ruler
  den Fehlbestand dann also nicht bemerkt —, ist ungeklärt. Messung 1 zeigt, dass Meldung
  und Kontext zeitlich auseinanderfallen können.
- **Interaktive Session.** Nur `/compact` ist interaktiv gemessen (Messung 7). Auto-
  Compaction, Fehlbestand, `/clear` und `/resume` innerhalb einer Session nicht; der
  Ersatz von der Platte fängt ein leeres Log auf.
- **`PreCompact`-stdout ist undokumentiert** (Baustein 2).

