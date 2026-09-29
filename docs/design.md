# ruler — Design

Claude-Code-Plugin (Getty-Marketplace), das dafür sorgt, dass der **Kern der
Projekt-Instruktionen** — CLAUDE.md und die Rules ohne `paths:` — nach jeder
Compaction wieder im Kontext steht, und dass die Compaction-Zusammenfassung keine
veralteten Kopien davon mitschleppt. Codex ist in v1 bewusst draußen (siehe unten).

Stand: 2026-09-29, Claude Code 2.1.284. Umgesetzt bis Stufe 4; offen sind die Abnahme in
einer interaktiven Session und der Marketplace-Eintrag.

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

Vier Bausteine, alle über dokumentierte Hooks, kein Transkript-Parsing. Was hier über
Reihenfolge, Zeitpunkte und Payloads steht, ist gemessen (Abschnitt *Messungen*), sofern
nicht die Doku als Quelle genannt ist.

### 1. Mitschreiben — `InstructionsLoaded`

Feuert für jede geladene CLAUDE.md / `.claude/rules/*.md` mit `file_path`,
`memory_type`, `load_reason` (`session_start`, `nested_traversal`, `path_glob_match`,
`include`, `compact`), `globs`, `trigger_file_path`, `parent_file_path`. Der Hook läuft
asynchron und hat keine Entscheidungsgewalt.

ruler hängt pro Ereignis **eine Zeile** an `${CLAUDE_PLUGIN_DATA}/sessions/<session_id>.jsonl`
an (`O_APPEND`, ein einzelner `write` → keine Sperre nötig, auch wenn mehrere
asynchrone Hooks gleichzeitig laufen). Kein Lesen-Ändern-Schreiben. Drei Arten von Zeilen:
`loaded` (dieser Hook), `precompact` und `compact` (Baustein 2).

Die Hooks laufen nebeneinander, ihre Zeilen stehen deshalb in beliebiger Reihenfolge im
Log — ein `include` kann vor seiner Elterndatei stehen. Ereignisse mit `agent_id`
(Subagent: gleiche `session_id`, eigener Kontext) werden von allen Hooks ignoriert.

**Kern ableiten** (reine Funktion über das Log, unabhängig von der Zeilenreihenfolge):
- `session_start` → Kern.
- `include` → Kern, wenn `parent_file_path` im Kern ist (rekursiv).
- `compact` für eine Datei, die noch nicht im Kern ist → Kern (z. B. eine während der
  Session neu angelegte Rule, die Claude Code bei der Compaction mitlädt).
- `nested_traversal`, `path_glob_match` und deren Includes → nie Kern.

**Ersatz, wenn das Log keine `session_start`-Zeilen hat** (Plugin mitten in der Session
installiert, Hook nicht gefeuert): Kern von der Platte ermitteln — `~/.claude/CLAUDE.md`,
`~/.claude/rules/**/*.md` ohne `paths:`, dann von `/` abwärts bis zum cwd in jedem
Verzeichnis `CLAUDE.md`, `.claude/CLAUDE.md`, `.claude/rules/**/*.md` ohne `paths:` und
`CLAUDE.local.md`, dazu `@imports` rekursiv (höchstens vier Sprünge, außerhalb von
Code-Spans und Code-Blöcken — Doku [memory](https://code.claude.com/docs/en/memory.md),
2026-09-29). Was das Log an `compact`-Dateien kennt, kommt dazu. Für Projekt- und
Local-Dateien deckt sich diese Liste mit dem, was `InstructionsLoaded` beim Start meldet
(Messung 5).

### 2. Zusammenfassung lenken — `PreCompact`

Eingabe `trigger` (`manual`/`auto`) und `custom_instructions` (String oder `null`).

Was ein `PreCompact`-Hook bei `exit 0` auf **stdout** schreibt, hängt Claude Code an die
Anweisungen für die Zusammenfassung an — hinter das, was der User an `/compact` übergeben
hat, getrennt durch eine Leerzeile; bei `manual` wie bei `auto` (Messung 4). Ein
`/compact focus on X` bleibt also ohne Zutun erhalten, ruler sieht und ersetzt es nicht.
**Dieses Verhalten ist gemessen, aber nicht dokumentiert**: die Doku nennt für
`PreCompact` nur das Blockieren. Fällt es weg, bleibt rulers Block wirkungslos und
Baustein 3 arbeitet unverändert weiter. (Ein Ausgabefeld `newCustomInstructions` gibt es
nicht; so heißt die Sammelvariable im Programm.)

ruler schreibt seinen Block zwischen festen Markern. Die Hook-Ausgabe bleibt nicht über
mehrere Compactions bestehen (Messung 4); steht der Marker trotzdem schon in
`custom_instructions`, schreibt ruler nichts. Wortlaut (englisch, sachlich, keine
„SYSTEM:“/„IMPORTANT“-Rahmung, die Claude Codes Prompt-Injection-Schutz auslösen kann):

```
<!-- ruler -->
These instruction files are re-attached from disk right after this compaction:
- /home/…/CLAUDE.md
- /home/…/.claude/rules/foo-rules.md
Do not reproduce their content in the summary. Do keep every instruction, decision
or correction the user gave in the conversation itself — those live in no file.
<!-- /ruler -->
```

Nebenwirkung: Claude Code zeigt die Ausgabe eines erfolgreichen `PreCompact`-Hooks dem
User an (`PreCompact [<Kommando>] completed successfully: …`); nach einem manuellen
`/compact` steht sie so auch als Kommando-Ausgabe im neuen Kontext.

Der Hook schreibt eine Zeile `{"event":"precompact","trigger":…}` ins Log. Die
Markierung `${CLAUDE_PLUGIN_DATA}/pending/<session_id>` und die Zeile
`{"event":"compact"}` legt erst `SessionStart` mit `source: compact` an — der feuert nur,
wenn die Compaction wirklich stattgefunden hat. Eine blockierte oder gescheiterte
Compaction löst so kein Nachreichen aus.

### 3. Prüfen und nachreichen

Fehlend = Kern − {Dateien mit einer `loaded`-Zeile nach der letzten `compact`-Zeile}.
Nach einer Compaction meldet Claude Code die Kerndateien mit `load_reason: compact`,
ihre `@imports` aber mit `include` (Messung 2) — deshalb zählt jede `loaded`-Zeile.
Fehlende Dateien werden **frisch von der Platte** gelesen (Änderungen während der
Session gelten), ohne ihr Frontmatter, und als `additionalContext` eingefügt; gelöschte
Dateien werden übersprungen. Danach wird `pending/<session_id>` entfernt.

Kann die Prüfung nicht sicher ausgewertet werden (Log unlesbar), wird der **ganze Kern**
von der Platte eingefügt: lieber doppelt als gar nicht.

Format pro Datei, sachlich wie oben:

```
Project instructions from /home/…/.claude/rules/foo-rules.md (re-attached by ruler after compaction):

<Inhalt>
```

**Größe:** `additionalContext` ist auf 10.000 Zeichen begrenzt; was darüber liegt,
lagert Claude Code in eine Datei aus und zeigt nur die ersten 2.000 Zeichen, ohne Claude
zum Lesen aufzufordern (Doku [hooks](https://code.claude.com/docs/en/hooks.md),
2026-09-29). ruler bleibt darunter: ganze Dateien in Kern-Reihenfolge, solange sie
passen; für den Rest ein Satz „Read these files now before continuing: …“ — die Datei
lädt dann das Read-Tool.

**Wann** (Messung 1): Claude Code meldet die nach einer Compaction neu geladenen Dateien
nicht bei der Compaction, sondern erst, wenn es den nächsten Schritt vorbereitet — und
damit **nach** `SessionStart` (compact). Im `SessionStart`-Hook lässt sich also nichts
prüfen. Geprüft wird am ersten Ereignis, an dem die Meldungen da sein können:

| Wie es nach der Compaction weitergeht | Reihenfolge | Prüfung |
|---|---|---|
| neuer Prompt (nach `/compact` oder Auto-Compaction am Turn-Ende) | `InstructionsLoaded` … und `UserPromptSubmit` nahezu gleichzeitig | im `UserPromptSubmit`-Hook |
| Turn läuft weiter (Auto-Compaction mitten im Turn) | Tools → `PostToolUse` je Tool → `PostToolBatch` → `InstructionsLoaded` … → nächste Modell-Anfrage | im `PostToolBatch`-Hook des **zweiten** Tool-Batches |

Die Markierung trägt dafür einen Zustand: `SessionStart` (compact) setzt `0`; der erste
`PostToolBatch` danach setzt nur `1` (Claude Code wartet auf den Hook, die Meldungen
kommen erst nach seiner Rückkehr); geprüft wird bei `UserPromptSubmit` in jedem Zustand
und bei `PostToolBatch` im Zustand `1`. `PostToolBatch` statt `PostToolUse`, weil er pro
Batch genau einmal feuert — parallele Tool-Aufrufe lösen sonst mehrere Prüfungen
gleichzeitig aus.

Die `InstructionsLoaded`-Hooks laufen neben dem prüfenden Hook her. Fehlt bei der
Prüfung etwas, wartet sie deshalb bis zu 1 s (in Schritten von 50 ms) auf nachkommende
Zeilen, bevor sie nachreicht.

Preis: Fehlt nach einer Auto-Compaction mitten im Turn wirklich etwas, laufen zwei
Modell-Anfragen ohne die Datei, bevor ruler sie nachreichen kann. Früher ginge es nur
blind — dann stünde in jedem Normalfall der ganze Kern doppelt im Kontext.

Heißer Pfad: `PostToolBatch` und `UserPromptSubmit` feuern ständig. Der `sh`-Starter
prüft nur mit Shell-Bordmitteln, ob `pending/` leer ist, und beendet sich dann sofort
mit `exit 0`, ohne Python zu starten (gemessen: 2,4 ms; mit Python 66 ms).

### 4. Aufräumen — `SessionEnd`

Löscht `sessions/<id>.jsonl` und `pending/<id>`. Beim `SessionStart` (`startup`) werden
Log-Dateien und Markierungen älter als 7 Tage entfernt (Sessions, die ohne `SessionEnd`
endeten).

`SessionEnd` feuert auch am Ende jedes `claude -p`-Laufs. Wird die Session später
fortgesetzt, meldet Claude Code alle Kerndateien erneut mit `session_start` (Messung 6);
das Log baut sich also von selbst wieder auf.

## Fehlerverhalten

- Jeder Hook endet mit `exit 0`, auch bei Ausnahmen, unlesbarem stdin, fehlendem
  `CLAUDE_PLUGIN_DATA`, fehlendem oder scheiterndem `python3` — ruler darf nie eine
  Session stören. Ausnahme ist nur das bewusste „ganzen Kern einfügen“, wenn die Prüfung
  selbst scheitert.
- Der Starter ruft `python3` auf und endet danach selbst mit `exit 0`, statt sich per
  `exec` ersetzen zu lassen: der Interpreter kann mit 1 oder 2 enden, bevor rulers Code
  läuft, und 2 würde eine Compaction blockieren.
- Timeouts in `hooks.json`: 5 s; `InstructionsLoaded` `async`.
- Kein Netzwerk, keine weiteren Prozesse, schreibt nur unter `${CLAUDE_PLUGIN_DATA}` —
  auch keinen Bytecode (`PYTHONDONTWRITEBYTECODE`).

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
| `README.md` | Was ruler garantiert und was nicht; Abschnitt „Keep the core small“ |

## Messungen

2026-09-29, Claude Code 2.1.284, `claude -p` mit `--input-format stream-json` (ein
Prompt nach dem anderen), Modell `claude-haiku-4-5`. Wegwerf-Projekt mit CLAUDE.md samt
einem `@import`, je einer Rule mit und ohne `paths:`, einer verschachtelten CLAUDE.md;
für Messung 5 zusätzlich CLAUDE.md und Rule im Elternverzeichnis, `CLAUDE.local.md` und
eine Rule in einem Unterverzeichnis von `.claude/rules/`. Aufzeichnungs-Hook auf allen
beteiligten Ereignissen; Auto-Compaction provoziert mit
`CLAUDE_CODE_AUTO_COMPACT_WINDOW=100000` und `CLAUDE_AUTOCOMPACT_PCT_OVERRIDE=40`.
Sieben Compactions ohne, vier mit geladenem Plugin; nach neun davon lief die Session
weiter. Kleine Stichprobe, ein Modell. Die Payloads liegen in `t/fixtures/`.

1. **Reihenfolge.** `PreCompact` → (Zusammenfassung, 20–40 s) → `SessionStart`
   (compact) → `PostCompact` (35–155 ms später) → … → `InstructionsLoaded` (compact).
   Die `compact`-Meldungen kamen nie vor `SessionStart`: nach `/compact` erst mit dem
   nächsten Prompt, ihre Hooks starteten zwischen 250 ms vor und 20 ms nach dessen
   `UserPromptSubmit`-Hook; nach einer Auto-Compaction mitten im Turn erst nach dem
   ersten Tool-Batch, und zwar nach der Rückkehr seiner Hooks (`PostToolUse` künstlich
   um 1,5 s, `PostToolBatch` um 0,7 s verzögert: die Meldungen folgten 50–70 ms nach dem
   Ende). Endet die Session direkt nach der Compaction, kommen sie gar nicht. Im Transkript steht der Anhang `instructions` dagegen schon an
   der Compaction-Grenze — die Meldung hinkt dem Kontext hinterher.
2. **Vollständigkeit.** `InstructionsLoaded` (compact) kam nach allen neun Compactions,
   nach denen die Session weiterlief, für jede Kerndatei; `@imports` kamen mit `load_reason: include` und `parent_file_path`.
   Rules mit `paths:` und verschachtelte CLAUDE.md kamen nur wieder, wenn danach eine
   passende Datei gelesen wurde.
3. **Obergrenze.** Nicht gemessen, aus der Doku übernommen (siehe Baustein 3).
4. **Anweisungen für die Zusammenfassung.** Die stdout-Ausgabe des `PreCompact`-Hooks
   wirkte bei `manual` und `auto` (ein vorgegebenes Wort stand am Anfang beider
   Zusammenfassungen). Sie blieb nicht bestehen: der zweite `PreCompact` derselben
   Session bekam als `custom_instructions` nur den Text des Users. Ohne Anweisung
   zu den Instruktionsdateien enthielten fünf von sechs Zusammenfassungen deren Inhalt.
   Mit rulers Block stand in keiner von vier Inhalt aus einer CLAUDE.md oder Rule; der
   Inhalt der importierten Datei stand in zweien — sie war in diesen Sessions auch mit
   dem Read-Tool gelesen worden und damit Teil des Gesprächs.
5. **Ersatz von der Platte.** Deckt sich für das Wegwerf-Projekt mit den
   `session_start`-Meldungen, einschließlich CLAUDE.md und `.claude/rules/` im
   Elternverzeichnis (Test `test_matches_what_claude_code_loaded_at_session_start`).
   Die User-Ebene (`~/.claude/CLAUDE.md`, `~/.claude/rules/`) kam im Aufbau nicht vor.
6. **Fortsetzen.** `--resume` meldet alle Kerndateien erneut mit `session_start` (zweimal
   hintereinander), vor und nach `SessionStart` (resume).

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

**Erledigt 2026-09-29**, Ergebnisse unter *Messungen*.

### Stufe 1 — Mitschreiben, Kern ableiten, Aufräumen

Bausteine 1 und 4, Tests gegen Fixtures. **Erledigt 2026-09-29.**

### Stufe 2 — `PreCompact`

Baustein 2, Tests für Anhängen, Idempotenz, `null`-Eingabe. **Erledigt 2026-09-29.**

### Stufe 3 — Prüfen und nachreichen

Baustein 3 am in Stufe 0 bestimmten Einfügepunkt; Größenobergrenze; Ersatz „ganzer Kern“.
**Erledigt 2026-09-29.**

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

**Abnahme 2026-09-29** (`claude -p --plugin-dir`, je eine Auto- und eine manuelle
Compaction pro Lauf):

- Plugin unverändert: nach beiden Compactions meldet `InstructionsLoaded` alle sieben
  Kerndateien, ruler hängt nichts an, und das Modell findet auf Nachfrage jede einmal
  in seinem Kontext; Zusammenfassungen wie in Messung 4; Datenverzeichnis nach
  `SessionEnd` leer.
- Fehlbestand erzwungen (Kopie des Plugins, deren `InstructionsLoaded`-Hook
  `load_reason: compact` nicht mitschreibt): ruler reicht die sechs betroffenen Dateien
  nach — nach der Auto-Compaction am zweiten `PostToolBatch`, nach `/compact` am
  `UserPromptSubmit`; der per `include` gemeldete Import wird nicht nachgereicht.

README steht. Offen: Abnahme in einer interaktiven Session, Eintrag im Marketplace.

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
- **Interaktive Session.** Alle Messungen liefen mit `claude -p`. `/clear` und `/resume`
  innerhalb einer Session sind nicht gemessen; der Ersatz von der Platte fängt ein leeres
  Log auf.
- **`PreCompact`-stdout ist undokumentiert** (Baustein 2).

