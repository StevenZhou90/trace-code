# Slide deck plan (four pages)

Goal: a four-page deck that a reader can understand in two minutes. Every number on it comes from a
results file produced by the pipeline. No planned work is shown as done. No personal names.

## How to build it
- Write the deck as one HTML file, `docs/slides/deck.html`, with four 1920x1080 pages.
- Make the images with a small standard-library Python script, `docs/slides/make_figures.py`, that reads
  the real dataset and test results and writes SVG files. Matplotlib is not installed; plain SVG is
  enough and stays sharp.
- Export to PDF with headless Chrome:
  `"/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" --headless --disable-gpu --no-pdf-header-footer --print-to-pdf=docs/slides/deck.pdf docs/slides/deck.html`
- Render each page to PNG once and look at it, to check that nothing overflows or overlaps.

## Visual style
- Dark slate background, one accent color for "pass", one for "fail", one neutral; large type; at most
  about 40 words of text per page; every image has a short caption.
- Waveforms drawn as digital timing diagrams (step lines for 1-bit signals, hex value boxes for buses),
  with the clock on top and the sampling point marked.

## Pages
1. **Signal-to-code: the data and grading pipeline.** One flow diagram: Verilog sources and five
   generators -> ingest, dedup, split -> simulate with Icarus -> public trace / training target / hidden
   tests -> grade a candidate. Small caption with the timing rule (drive on falling edge, sample before
   rising edge).
2. **Five task families.** A 5-panel grid, one real waveform snippet per family (comb, counter with
   wraparound, FSM detecting the sequence, arbiter with competing requests, handshake under
   backpressure). One line per family on the behavior rule.
3. **The tests catch bugs, not only pass references.** A matrix image: rows are families, columns are
   reference, each mutant, syntax error, runtime error, timeout. Cells colored by the real status. One
   example of a failure report (cycle, inputs, expected, actual) for a mutant.
4. **What is ready for baseline training, and what is not.** Left: dataset counts by family and split,
   sample record. Right: completed / partial / missing list taken from `docs/CHECKLIST.md`, including
   limits (dedup is not semantic, external ingestion not done, simulation is not synthesis).
