# ⚙️ CPU Scheduling Algorithms Simulator (DSA)

An interactive web-based CPU Scheduling Simulator built with **Python** and **Streamlit**, supporting 8 classic operating system scheduling algorithms:
- **FCFS** (`1`) — First Come First Serve
- **RR** (`2-<q>`) — Round Robin
- **SPN** (`3`) — Shortest Process Next
- **SRT** (`4`) — Shortest Remaining Time
- **HRRN** (`5`) — Highest Response Ratio Next
- **FB-1** (`6`) — Feedback ($q = 1$)
- **FB-2i** (`7`) — Feedback ($q = 2^i$)
- **Aging** (`8-<q>`) — Priority Aging

## Interface Modes
1. **GUI 1 (Text & File Input):** Paste raw input or upload `.txt` test files to generate exact plain-text `trace` and `stats` outputs with `.txt` export.
2. **GUI 2 (Form & Multi-Algorithm Comparison):** Configure processes interactively, compare multiple algorithms or quantum variants side-by-side, and inspect Plotly Gantt & turnaround bar charts.
3. **GUI 3 (Individual Algorithm Visualizer):** Step-by-step 60 FPS interactive playback with a CPU execution strip, per-process timeline, and live process state inspector.

## Run Locally
```bash
pip install -r requirements.txt
streamlit run app.py