import json
from typing import Any, Dict, List
import pandas as pd
import streamlit as st
import streamlit.components.v1 as components

from main import Scheduler
from parser import Process, parse_input

ALGO_CATALOG = {
    "FCFS": ("1", False),
    "RR": ("2", True),
    "SPN": ("3", False),
    "SRT": ("4", False),
    "HRRN": ("5", False),
    "FB-1": ("6", False),
    "FB-2i": ("7", False),
    "Aging": ("8", True),
}

ID_TO_ALGO_NAME = {v[0]: k for k, v in ALGO_CATALOG.items()}

PROCESS_PALETTE = [
    "#3B82F6", "#10B981", "#F59E0B", "#EC4899", "#8B5CF6",
    "#06B6D4", "#F97316", "#14B8A6", "#6366F1", "#E11D48",
]


def _empty_process_df() -> pd.DataFrame:
    """Returns a typed empty DataFrame so GUI 3 starts blank."""
    return pd.DataFrame(
        {
            "Name": pd.Series(dtype="str"),
            "Arrival": pd.Series(dtype="int"),
            "Service": pd.Series(dtype="int"),
        }
    )


def _build_process_list(df: pd.DataFrame) -> List[Process]:
    """Validates edited table rows and returns processes sorted by arrival time."""
    clean_df = df.dropna(how="all")
    if clean_df.empty:
        raise ValueError("Process table is empty. Add at least one process or upload a .txt file.")

    processes: List[Process] = []
    seen_names = set()

    for idx, row in clean_df.iterrows():
        name = str(row.get("Name", "")).strip()
        if not name or name.lower() == "nan":
            raise ValueError(f"Row {idx + 1}: Process Name cannot be empty.")
        if name in seen_names:
            raise ValueError(f"Duplicate process name '{name}'. Names must be unique.")
        seen_names.add(name)

        try:
            arrival = int(row["Arrival"])
            service = int(row["Service"])
        except (ValueError, TypeError) as exc:
            raise ValueError(f"Process '{name}': Arrival and Service times must be integers.") from exc

        if arrival < 0 or service <= 0:
            raise ValueError(f"Process '{name}': Arrival must be >= 0 and Service must be > 0.")

        processes.append(Process(name=name, arrival_time=arrival, service_time=service))

    processes.sort(key=lambda p: p.arrival_time)
    return processes


def _load_uploaded_file(raw_content: str) -> None:
    """Parses uploaded .txt content and updates GUI 3 state before widgets render."""
    _, parsed_algos, last_instant, processes = parse_input(raw_content)

    st.session_state["g3_last_instant"] = last_instant
    st.session_state["g3_process_df"] = pd.DataFrame(
        [{"Name": p.name, "Arrival": p.arrival_time, "Service": p.service_time} for p in processes]
    )

    if parsed_algos:
        alg_id, quantum = parsed_algos[0]
        algo_name = ID_TO_ALGO_NAME.get(alg_id)
        if algo_name:
            st.session_state["g3_selected_algo"] = algo_name
        if alg_id in ("2", "8") and quantum > 0:
            st.session_state["g3_quantum"] = quantum


def _serialize_simulation(scheduler: Scheduler, label: str) -> Dict[str, Any]:
    """Precomputes all tick frames and summary metrics for zero-lag client playback."""
    last_instant = scheduler.last_instant
    procs = scheduler.processes

    # Build CPU execution strip per tick (0 .. last_instant - 1)
    cpu_strip: List[Dict[str, Any]] = []
    for t in range(last_instant):
        active_idx = None
        for p_idx in range(len(procs)):
            if scheduler.timeline[t][p_idx] == "*":
                active_idx = p_idx
                break
        if active_idx is not None:
            cpu_strip.append(
                {
                    "t": t,
                    "name": procs[active_idx].name,
                    "color": PROCESS_PALETTE[active_idx % len(PROCESS_PALETTE)],
                }
            )
        else:
            cpu_strip.append({"t": t, "name": "IDLE", "color": "#334155"})

    # Build per-process timeline cells & tick-by-tick state snapshots
    timeline_matrix: List[List[str]] = []
    for p_idx in range(len(procs)):
        timeline_matrix.append([scheduler.timeline[t][p_idx] for t in range(last_instant)])

    # Precompute process states at each instant t in 0 .. last_instant
    snapshots: List[Dict[str, Any]] = []
    for t in range(last_instant + 1):
        current_cpu = cpu_strip[t]["name"] if t < last_instant else "FINISHED"
        proc_states = []
        for p_idx, p in enumerate(procs):
            executed = sum(1 for k in range(t) if scheduler.timeline[k][p_idx] == "*")
            waited = sum(1 for k in range(t) if scheduler.timeline[k][p_idx] == ".")
            remaining = max(0, p.service_time - executed)

            if t < p.arrival_time:
                status = "Not Arrived"
            elif p.finish_time > 0 and t >= p.finish_time:
                status = "Completed"
            elif t < last_instant and scheduler.timeline[t][p_idx] == "*":
                status = "Running"
            elif t < last_instant and scheduler.timeline[t][p_idx] == ".":
                status = "Waiting"
            elif remaining == 0:
                status = "Completed"
            else:
                status = "Ready"

            proc_states.append(
                {
                    "name": p.name,
                    "color": PROCESS_PALETTE[p_idx % len(PROCESS_PALETTE)],
                    "arrival": p.arrival_time,
                    "service": p.service_time,
                    "executed": executed,
                    "remaining": remaining,
                    "waited": waited,
                    "finish": p.finish_time if (p.finish_time > 0 and t >= p.finish_time) else "-",
                    "status": status,
                }
            )

        snapshots.append(
            {
                "t": t,
                "cpu": current_cpu,
                "processes": proc_states,
            }
        )

    summary_rows = []
    for p in procs:
        wait_time = p.turnaround_time - p.service_time
        summary_rows.append(
            {
                "Process": p.name,
                "Arrival": p.arrival_time,
                "Service": p.service_time,
                "Finish": p.finish_time,
                "Turnaround": p.turnaround_time,
                "NormTurn": round(p.normalized_turnaround, 2),
                "Waiting": wait_time,
            }
        )

    return {
        "label": label,
        "last_instant": last_instant,
        "cpu_strip": cpu_strip,
        "timeline_matrix": timeline_matrix,
        "snapshots": snapshots,
        "summary_rows": summary_rows,
    }


def _render_smooth_player(sim_data: Dict[str, Any]) -> None:
    """Renders an interactive 60-FPS client-side SVG/HTML animation player."""
    payload_json = json.dumps(sim_data)
    num_procs = len(sim_data["snapshots"][0]["processes"])
    component_height = max(540, 390 + num_procs * 44)

    html_code = f"""
    <!DOCTYPE html>
    <html>
    <head>
    <style>
      * {{ box-sizing: border-box; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; }}
      body {{ margin: 0; padding: 4px; background: transparent; color: #E2E8F0; }}
      .card {{
        background: #0F172A;
        border: 1px solid #1E293B;
        border-radius: 12px;
        padding: 16px 20px;
      }}
      .controls {{
        display: flex;
        flex-wrap: wrap;
        align-items: center;
        gap: 10px;
        margin-bottom: 14px;
        padding-bottom: 12px;
        border-bottom: 1px solid #1E293B;
      }}
      button {{
        background: #1E293B;
        color: #F8FAFC;
        border: 1px solid #334155;
        border-radius: 8px;
        padding: 7px 14px;
        font-size: 13px;
        font-weight: 600;
        cursor: pointer;
        transition: background 0.15s ease, transform 0.05s ease;
      }}
      button:hover {{ background: #334155; }}
      button:active {{ transform: scale(0.97); }}
      button.primary {{ background: #2563EB; border-color: #3B82F6; }}
      button.primary:hover {{ background: #1D4ED8; }}
      select {{
        background: #1E293B;
        color: #F8FAFC;
        border: 1px solid #334155;
        border-radius: 8px;
        padding: 6px 10px;
        font-size: 13px;
      }}
      .scrubber-wrap {{
        flex: 1;
        min-width: 180px;
        display: flex;
        align-items: center;
        gap: 10px;
      }}
      input[type="range"] {{
        flex: 1;
        accent-color: #3B82F6;
        cursor: pointer;
      }}
      .badge {{
        background: #1E293B;
        border: 1px solid #334155;
        padding: 5px 12px;
        border-radius: 8px;
        font-size: 13px;
        font-weight: 600;
        white-space: nowrap;
      }}
      .badge span {{ color: #60A5FA; }}
      .section-title {{
        font-size: 12px;
        text-transform: uppercase;
        letter-spacing: 0.06em;
        color: #94A3B8;
        margin: 10px 0 6px 0;
        font-weight: 700;
      }}
      /* Single-Row CPU Gantt Strip */
      .gantt-strip {{
        display: flex;
        width: 100%;
        height: 36px;
        background: #1E293B;
        border-radius: 8px;
        overflow: hidden;
        border: 1px solid #334155;
      }}
      .gantt-cell {{
        flex: 1;
        display: flex;
        align-items: center;
        justify-content: center;
        font-size: 11px;
        font-weight: 700;
        color: #FFFFFF;
        border-right: 1px solid rgba(15, 23, 42, 0.35);
        transition: opacity 0.12s ease;
      }}
      .gantt-cell.future {{ opacity: 0.14; }}
      .gantt-cell.active {{ outline: 2px solid #FACC15; z-index: 2; }}
      .axis-row {{
        display: flex;
        width: 100%;
        margin-top: 3px;
        margin-bottom: 12px;
        font-size: 10px;
        color: #94A3B8;
      }}
      .axis-tick {{ flex: 1; text-align: left; }}
      /* Per-Process Timeline Grid */
      .proc-row {{
        display: flex;
        align-items: center;
        margin-bottom: 6px;
        gap: 10px;
      }}
      .proc-label {{
        width: 64px;
        font-size: 13px;
        font-weight: 700;
        display: flex;
        align-items: center;
        gap: 6px;
      }}
      .dot {{ width: 9px; height: 9px; border-radius: 50%; display: inline-block; }}
      .proc-track {{
        flex: 1;
        display: flex;
        height: 24px;
        background: #1E293B;
        border-radius: 6px;
        overflow: hidden;
      }}
      .track-cell {{
        flex: 1;
        border-right: 1px solid rgba(15, 23, 42, 0.4);
        display: flex;
        align-items: center;
        justify-content: center;
        font-size: 10px;
        font-weight: 700;
      }}
      /* Live State Table */
      table {{
        width: 100%;
        border-collapse: collapse;
        margin-top: 8px;
        font-size: 13px;
      }}
      th, td {{
        text-align: left;
        padding: 7px 10px;
        border-bottom: 1px solid #1E293B;
      }}
      th {{ color: #94A3B8; font-size: 11px; text-transform: uppercase; }}
      .pill {{
        padding: 2px 8px;
        border-radius: 999px;
        font-size: 11px;
        font-weight: 700;
      }}
      .st-Running {{ background: rgba(37, 99, 235, 0.25); color: #60A5FA; border: 1px solid #3B82F6; }}
      .st-Waiting {{ background: rgba(245, 158, 11, 0.2); color: #FBBF24; border: 1px solid #F59E0B; }}
      .st-Completed {{ background: rgba(16, 185, 129, 0.2); color: #34D399; border: 1px solid #10B981; }}
      .st-NotArrived {{ background: rgba(100, 116, 139, 0.2); color: #94A3B8; }}
      .st-Ready {{ background: rgba(139, 92, 246, 0.2); color: #C4B5FD; }}
      .legend {{
        display: flex;
        gap: 14px;
        font-size: 11px;
        color: #94A3B8;
        margin-top: 6px;
      }}
      .legend-box {{
        display: inline-block;
        width: 10px;
        height: 10px;
        border-radius: 2px;
        margin-right: 4px;
        vertical-align: middle;
      }}
    </style>
    </head>
    <body>
    <div class="card">
      <div class="controls">
        <button id="btnPlay" class="primary">▶ Play</button>
        <button id="btnPrev">⏮ Prev</button>
        <button id="btnNext">⏭ Next</button>
        <button id="btnReset">↺ Reset</button>
        <label style="font-size:12px;color:#94A3B8;">Speed:
          <select id="speedSelect">
            <option value="900">0.5x</option>
            <option value="450" selected>1x</option>
            <option value="220">2x</option>
            <option value="100">4x</option>
          </select>
        </label>
        <div class="scrubber-wrap">
          <input type="range" id="timeSlider" min="0" max="1" value="0" />
        </div>
        <div class="badge">Time: <span id="timeVal">0</span> / <span id="maxVal">0</span></div>
        <div class="badge">CPU: <span id="cpuVal">-</span></div>
      </div>

      <div class="section-title">CPU Execution Gantt Strip (<span id="algoTitle"></span>)</div>
      <div class="gantt-strip" id="ganttStrip"></div>
      <div class="axis-row" id="axisRow"></div>

      <div class="section-title">Per-Process Execution &amp; Wait Timeline</div>
      <div id="procTracks"></div>
      <div class="legend">
        <span><i class="legend-box" style="background:#3B82F6;"></i>Running (*)</span>
        <span><i class="legend-box" style="background:#F59E0B;"></i>Waiting (.)</span>
        <span><i class="legend-box" style="background:#1E293B;border:1px solid #334155;"></i>Idle / Not Arrived</span>
      </div>

      <div class="section-title" style="margin-top:14px;">Live Process State Inspector</div>
      <table>
        <thead>
          <tr>
            <th>Process</th>
            <th>Status</th>
            <th>Arrival</th>
            <th>Service</th>
            <th>Executed</th>
            <th>Remaining</th>
            <th>Waited</th>
            <th>Finish</th>
          </tr>
        </thead>
        <tbody id="stateBody"></tbody>
      </table>
    </div>

    <script>
      const SIM = {payload_json};
      const maxT = SIM.last_instant;
      let currentT = 0;
      let timer = null;

      const slider = document.getElementById("timeSlider");
      const btnPlay = document.getElementById("btnPlay");
      const speedSelect = document.getElementById("speedSelect");

      slider.max = maxT;
      document.getElementById("maxVal").textContent = maxT;
      document.getElementById("algoTitle").textContent = SIM.label;

      // Build static DOM skeleton once
      const ganttStrip = document.getElementById("ganttStrip");
      const axisRow = document.getElementById("axisRow");
      SIM.cpu_strip.forEach((slot, idx) => {{
        const cell = document.createElement("div");
        cell.className = "gantt-cell future";
        cell.id = "gantt-" + idx;
        cell.style.background = slot.color;
        cell.textContent = slot.name === "IDLE" ? "·" : slot.name;
        cell.title = `t=${{idx}} → ${{idx + 1}}: ${{slot.name}}`;
        cell.onclick = () => {{ stopPlay(); renderTick(idx + 1); }};
        ganttStrip.appendChild(cell);

        const tick = document.createElement("div");
        tick.className = "axis-tick";
        tick.textContent = (maxT <= 25 || idx % 2 === 0) ? idx : "";
        axisRow.appendChild(tick);
      }});

      const procTracks = document.getElementById("procTracks");
      SIM.snapshots[0].processes.forEach((p, pIdx) => {{
        const row = document.createElement("div");
        row.className = "proc-row";

        const lbl = document.createElement("div");
        lbl.className = "proc-label";
        lbl.innerHTML = `<span class="dot" style="background:${{p.color}}"></span>${{p.name}}`;
        row.appendChild(lbl);

        const track = document.createElement("div");
        track.className = "proc-track";
        for (let t = 0; t < maxT; t++) {{
          const c = document.createElement("div");
          c.className = "track-cell";
          c.id = `track-${{pIdx}}-${{t}}`;
          track.appendChild(c);
        }}
        row.appendChild(track);
        procTracks.appendChild(row);
      }});

      function renderTick(t) {{
        currentT = Math.max(0, Math.min(maxT, t));
        slider.value = currentT;
        const snap = SIM.snapshots[currentT];

        document.getElementById("timeVal").textContent = currentT;
        document.getElementById("cpuVal").textContent = snap.cpu;

        // Update Gantt Strip
        for (let i = 0; i < maxT; i++) {{
          const el = document.getElementById("gantt-" + i);
          el.classList.toggle("future", i >= currentT);
          el.classList.toggle("active", i === currentT && currentT < maxT);
        }}

        // Update Per-Process Tracks
        snap.processes.forEach((p, pIdx) => {{
          for (let i = 0; i < maxT; i++) {{
            const cell = document.getElementById(`track-${{pIdx}}-${{i}}`);
            const sym = SIM.timeline_matrix[pIdx][i];
            if (i < currentT) {{
              if (sym === "*") {{
                cell.style.background = p.color;
                cell.style.color = "#FFF";
                cell.textContent = "*";
              }} else if (sym === ".") {{
                cell.style.background = "#F59E0B";
                cell.style.color = "#0F172A";
                cell.textContent = ".";
              }} else {{
                cell.style.background = "#1E293B";
                cell.textContent = "";
              }}
            }} else {{
              cell.style.background = "#1E293B";
              cell.textContent = "";
            }}
          }}
        }});

        // Update State Table
        const tbody = document.getElementById("stateBody");
        tbody.innerHTML = snap.processes.map(p => {{
          const cls = "st-" + p.status.replace(/\\s+/g, "");
          return `
            <tr>
              <td><span class="dot" style="background:${{p.color}};margin-right:6px;"></span><strong>${{p.name}}</strong></td>
              <td><span class="pill ${{cls}}">${{p.status}}</span></td>
              <td>${{p.arrival}}</td>
              <td>${{p.service}}</td>
              <td>${{p.executed}}</td>
              <td>${{p.remaining}}</td>
              <td>${{p.waited}}</td>
              <td>${{p.finish}}</td>
            </tr>
          `;
        }}).join("");
      }}

      function stopPlay() {{
        if (timer) {{
          clearInterval(timer);
          timer = null;
        }}
        btnPlay.textContent = "▶ Play";
      }}

      function startPlay() {{
        if (currentT >= maxT) currentT = 0;
        btnPlay.textContent = "⏸ Pause";
        const interval = parseInt(speedSelect.value, 10);
        timer = setInterval(() => {{
          if (currentT >= maxT) {{
            stopPlay();
            return;
          }}
          renderTick(currentT + 1);
        }}, interval);
      }}

      btnPlay.onclick = () => {{
        if (timer) stopPlay();
        else startPlay();
      }};
      document.getElementById("btnPrev").onclick = () => {{ stopPlay(); renderTick(currentT - 1); }};
      document.getElementById("btnNext").onclick = () => {{ stopPlay(); renderTick(currentT + 1); }};
      document.getElementById("btnReset").onclick = () => {{ stopPlay(); renderTick(0); }};
      slider.oninput = (e) => {{ stopPlay(); renderTick(parseInt(e.target.value, 10)); }};
      speedSelect.onchange = () => {{
        if (timer) {{ stopPlay(); startPlay(); }}
      }};

      renderTick(0);
    </script>
    </body>
    </html>
    """
    components.html(html_code, height=component_height, scrolling=False)


def render_single_visualizer_gui() -> None:
    if "g3_last_instant" not in st.session_state:
        st.session_state["g3_last_instant"] = 20
    if "g3_process_df" not in st.session_state:
        st.session_state["g3_process_df"] = _empty_process_df()
    if "g3_selected_algo" not in st.session_state:
        st.session_state["g3_selected_algo"] = "FCFS"
    if "g3_quantum" not in st.session_state:
        st.session_state["g3_quantum"] = 1
    if "g3_sim_data" not in st.session_state:
        st.session_state["g3_sim_data"] = None
    if "g3_last_uploaded_id" not in st.session_state:
        st.session_state["g3_last_uploaded_id"] = None

    st.header("CPU Scheduler — Individual Algorithm Visualizer")
    st.caption("Add processes manually or import a `.txt` file, then animate execution tick-by-tick.")

    uploaded_file = st.file_uploader(
        "Import Input File (.txt)",
        type=["txt"],
        key="g3_file_uploader",
        help="Upload a scheduler input file to populate the process table and horizon.",
    )
    if uploaded_file is not None:
        file_id = f"{uploaded_file.name}_{uploaded_file.size}"
        if st.session_state["g3_last_uploaded_id"] != file_id:
            try:
                content = uploaded_file.getvalue().decode("utf-8", errors="replace")
                _load_uploaded_file(content)
                st.session_state["g3_last_uploaded_id"] = file_id
                st.success(f"Loaded '{uploaded_file.name}' successfully.")
            except ValueError as err:
                st.error(f"File Import Error: {err}")

    st.divider()

    left_col, right_col = st.columns([1.2, 1], gap="large")

    with left_col:
        st.subheader("1. Process Table")
        edited_df = st.data_editor(
            st.session_state["g3_process_df"],
            num_rows="dynamic",
            use_container_width=True,
            hide_index=True,
            column_config={
                "Name": st.column_config.TextColumn("Process Name", required=True),
                "Arrival": st.column_config.NumberColumn("Arrival Time", min_value=0, step=1, required=True),
                "Service": st.column_config.NumberColumn("Service Time", min_value=1, step=1, required=True),
            },
            key="g3_editor",
        )

    with right_col:
        st.subheader("2. Algorithm & Horizon")
        last_instant = st.number_input(
            "Simulation Horizon (Last Instant)",
            min_value=1,
            max_value=500,
            key="g3_last_instant",
        )

        selected_algo = st.selectbox(
            "Select Algorithm",
            options=list(ALGO_CATALOG.keys()),
            key="g3_selected_algo",
        )

        alg_id, needs_quantum = ALGO_CATALOG[selected_algo]
        quantum = -1
        if needs_quantum:
            quantum = st.number_input(
                f"{selected_algo} Time Quantum",
                min_value=1,
                max_value=100,
                key="g3_quantum",
            )

    if st.button("▶ Run & Visualize", type="primary", use_container_width=True):
        try:
            processes = _build_process_list(edited_df)
            scheduler = Scheduler(processes, int(last_instant))
            label = scheduler.run(alg_id, int(quantum))
            st.session_state["g3_sim_data"] = _serialize_simulation(scheduler, label)
        except ValueError as err:
            st.error(f"Configuration Error: {err}")
        except Exception as err:
            st.error(f"Simulation Error: {err}")

    sim_data = st.session_state.get("g3_sim_data")
    if sim_data:
        st.divider()
        _render_smooth_player(sim_data)

        with st.expander("Final Process Summary Metrics", expanded=False):
            summary_df = pd.DataFrame(sim_data["summary_rows"])
            m1, m2, m3 = st.columns(3)
            m1.metric("Mean Turnaround", f"{summary_df['Turnaround'].mean():.2f}")
            m2.metric("Mean NormTurn", f"{summary_df['NormTurn'].mean():.2f}")
            m3.metric("Mean Waiting", f"{summary_df['Waiting'].mean():.2f}")
            st.dataframe(summary_df, use_container_width=True, hide_index=True)