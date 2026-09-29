# ruler — Mechanismus

Teil des Designs, Einstieg: [../design.md](../design.md). Hier steht, wie ruler arbeitet
und warum an genau diesen Stellen. Belege und Zeitmessungen (*Messung N*) stehen in
[measurements.md](measurements.md).

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
| neuer Prompt (nach `/compact` oder Auto-Compaction am Turn-Ende) | `UserPromptSubmit` → (Hook kehrt zurück) → `InstructionsLoaded` … | am **zweiten** Ereignis danach: dem nächsten `UserPromptSubmit` oder dem ersten `PostToolBatch` |
| Turn läuft weiter (Auto-Compaction mitten im Turn) | Tools → `PostToolUse` je Tool → `PostToolBatch` → (Hook kehrt zurück) → `InstructionsLoaded` … → nächste Modell-Anfrage | im `PostToolBatch` des **zweiten** Tool-Batches |

Die Markierung trägt dafür einen Zustand: `SessionStart` (compact) setzt `0`; das erste
`UserPromptSubmit` oder `PostToolBatch` danach setzt nur `1` (Claude Code wartet auf den
Hook, die Meldungen kommen erst nach seiner Rückkehr); geprüft wird beim nächsten von
beiden. `PostToolBatch` statt `PostToolUse`, weil er pro Batch genau einmal feuert —
parallele Tool-Aufrufe lösen sonst mehrere Prüfungen gleichzeitig aus.

(Bis zur Abnahme am 2026-09-29 prüfte `UserPromptSubmit` sofort, weil die `claude -p`-
Messung die Meldungen um den Hook herum zeigte. Interaktiv kommen sie erst danach: die
Prüfung wartete die ganze Sekunde, fand nichts und reichte den ganzen Kern doppelt nach.
Messung 7.)

Die `InstructionsLoaded`-Hooks laufen neben dem prüfenden Hook her. Fehlt bei der
Prüfung etwas, wartet sie deshalb bis zu 1 s (in Schritten von 50 ms) auf nachkommende
Zeilen, bevor sie nachreicht.

Preis: Fehlt nach einer Compaction wirklich etwas, läuft ein Prompt (nach `/compact`)
bzw. laufen zwei Modell-Anfragen (Auto-Compaction mitten im Turn) ohne die Datei, bevor
ruler sie nachreichen kann. Früher ginge es nur
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

