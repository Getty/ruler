# ruler — Messungen und Abnahme

Teil des Designs, Einstieg: [../design.md](../design.md). Hier stehen die Messungen
(mit Datum und Claude-Code-Version), aus denen [mechanism.md](mechanism.md) folgt, und die
Abnahmen. Die Payloads liegen in `t/fixtures/`; wie man eine Messung wiederholt, steht im
Skill `ruler-remeasure`.

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
7. **Interaktiv** (2026-09-29, Claude Code 2.1.285, tmux, Haiku, ein Lauf). Nach `/compact`
   und dem nächsten Prompt meldete Claude Code alle Kerndateien mit `compact`/`include`,
   aber erst **nach** der Rückkehr des `UserPromptSubmit`-Hooks (Transkript: Prompt
   21:00:26,488; rulers Anhang +1,06 s = volle Wartezeit; die eigene `instructions`-
   Meldung +43 ms danach; Log-Zeilen 70–90 ms nach dem Anhang). Das Muster ist das von
   `PostToolBatch` in Messung 1; ob der Unterschied zu `claude -p` am Modus oder an der
   Version liegt, ist nicht getrennt. Nach der Korrektur (erstes Ereignis setzt nur die
   Markierung): kein Anhang, `pending/` leer, das Modell findet jede Datei einmal.

## Stufen

Alle Stufen sind erledigt (2026-09-29); die Messungen sind das Ergebnis von Stufe 0.

- **Stufe 0** — Aufzeichnungs-Hook, Reihenfolge, Vollständigkeit, Obergrenze,
  `custom_instructions`, Ersatz von der Platte festnageln; Payloads → `t/fixtures/`.
- **Stufe 1** — Mitschreiben, Kern ableiten, Aufräumen (Bausteine 1 und 4).
- **Stufe 2** — `PreCompact` (Baustein 2).
- **Stufe 3** — Prüfen und nachreichen (Baustein 3), Größenobergrenze, Ersatz „ganzer Kern“.

## Stufe 4 — Live-Abnahme, README, Marketplace

Wiederholung des Stufe-0-Aufbaus mit installiertem Plugin: nach jeder Compaction sind
alle Kerndateien im Kontext, keine doppelt (außer im dokumentierten Ersatzfall).
Die Hinweise „Keep the core small“ stehen im README.

**Abnahme 2026-09-29** (`claude -p --plugin-dir`, je eine Auto- und eine manuelle
Compaction pro Lauf):

- Plugin unverändert: nach beiden Compactions meldet `InstructionsLoaded` alle sieben
  Kerndateien, ruler hängt nichts an, und das Modell findet auf Nachfrage jede einmal
  in seinem Kontext; Zusammenfassungen wie in Messung 4; Datenverzeichnis nach
  `SessionEnd` leer.
- Fehlbestand erzwungen (Kopie des Plugins, deren `InstructionsLoaded`-Hook
  `load_reason: compact` nicht mitschreibt): ruler reicht die sechs betroffenen Dateien
  nach — nach der Auto-Compaction am zweiten `PostToolBatch`, nach `/compact` am
  `UserPromptSubmit` (vor der Korrektur aus Messung 7; jetzt am zweiten Ereignis); der per `include` gemeldete Import wird nicht nachgereicht.

README steht. Im Marketplace eingetragen am 2026-09-29, nur für Claude Code.

**Interaktive Abnahme 2026-09-29** (2.1.285): fand den Fehler aus Messung 7; nach der
Korrektur nach `/compact` und zwei weiteren Prompts nichts nachgereicht, alle drei
Kerndateien einmal im Kontext, Datenverzeichnis nach `SessionEnd` leer. Nicht
interaktiv wiederholt: Fehlbestand und Auto-Compaction mitten im Turn (durch Unit-Tests
gegen die `claude -p`-Fixtures gedeckt).

