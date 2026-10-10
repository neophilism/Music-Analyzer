# Export, recovery, and undo

Build an album from reviewed scores, then choose **Export**. Preview every original
name and final relative path. **Export Copies** is the default. **Organize originals**
copies to the selected output folder, verifies every output, then removes the
originals. It supports source and output locations on different volumes. No audio
is re-encoded, and no embedded audio metadata is rewritten.

The output contains `Positive Valence/` and `Negative Valence/`, with global album
positions prepended to the original basenames. Padding uses the width of the total
track count; literal unpadded numbers are also available. Original numbers that
were already in a basename are preserved. Automatic ordering makes each group
rise in intensity; a custom order can override that and its warning is shown.

`album.m3u8` reconstructs the combined album order across the folders.
`analysis.csv` includes measurements, variability, and scores for every imported
track, including exclusions and failures. `analysis.json` retains raw results,
manual overrides, provenance, and the frozen normalization snapshot.
`album-manifest.json` records hashes, original locations, album positions, and
within-group ranks.

## Completing an interrupted operation

The project remembers its export journal. Use **Tools → Resume export** after
cancellation, restart, or a recoverable failure. A journal can also be selected
manually from the original output folder. Completed file operations are reconciled
using the actual file identity and SHA-256 before the remaining operations run.

Each export has a durable `.music-analyzer-<id>.journal.json` and a staging folder
alongside its outputs. Staged copies and previous managed outputs remain available
for recovery and undo. Keep these files while undo is needed. An interrupted source
removal may also leave a `.moved` recovery file beside the source; the journal
identifies the operation and recovery verifies this file before proceeding.

## Undo and re-export

**Tools → Undo export** restores moved originals and any previous managed export.
It checks every potential conflict before removing exported files. An externally
modified or replaced file causes a descriptive conflict; recoverable bytes are
retained. Undo itself is resumable if interrupted. Resolve the reported external
conflict, then choose Undo again.

Re-exporting the same project to the same folder replaces only verified files
listed in its previous completed journal. It uses the original basenames, so
application prefixes do not accumulate. Unrelated files, including paths that
collide after Unicode or case normalization, cause a conflict instead of being
overwritten. Do not start a new export while the project's previous one is
unfinished: resume or undo it first.

Publication uses an atomic exclusive rename on macOS and Linux. Outputs are staged
on the output volume; cross-volume source movement uses verified copying. A
filesystem that cannot provide exclusive publication reports an error and retains
the originals and journal. Disk exhaustion, read-only destinations, and missing
or changed recordings are per-export errors rather than permission to overwrite
another file.
