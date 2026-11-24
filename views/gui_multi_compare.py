from typing import List, Tuple
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

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

DEFAULT_PROCESS_ROWS = [
    {"Name": "A", "Arrival": 0, "Service": 3},
    {"Name": "B", "Arrival": 2, "Service": 6},
]


def _parse_quantum_list(raw_quantums: str, algo_name: str) -> List[int]:
    """Parses comma-separated positive integers like '1, 4'."""
    parts = [p.strip() for p in raw_quantums.split(",") if p.strip()]
    if not parts:
        raise ValueError(f"Enter at least one quantum for {algo_name} (e.g., '1, 4').")
    quantums: List[int] = []
    for p in parts:
        try:
            q = int(p)
        except ValueError as exc:
            raise ValueError(f"Invalid quantum '{p}' for {algo_name}. Must be an integer.") from exc
        if q <= 0:
            raise ValueError(f"Quantum for {algo_name} must be positive (got {q}).")
        quantums.append(q)
    return quantums


def _build_process_list(df: pd.DataFrame) -> List[Process]:
    """Validates edited table rows and returns processes sorted by arrival time."""
    clean_df = df.dropna(how="all")
    if clean_df.empty:
        raise ValueError("Add at least one process in the table.")

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
            raise ValueError(
                f"Process '{name}': Arrival must be >= 0 and Service must be > 0."
            )

        processes.append(Process(name=name, arrival_time=arrival, service_time=service))

    processes.sort(key=lambda p: p.arrival_time)
    return processes


def _build_gantt_figure(scheduler: Scheduler, title: str) -> go.Figure:
    """Builds an integer-tick Plotly horizontal timeline from scheduler.timeline."""
    records = []
    state_map = {"*": "Running", ".": "Waiting"}

    for p_idx, proc in enumerate(scheduler.processes):
        t = 0
        while t < scheduler.last_instant:
            cell = scheduler.timeline[t][p_idx]
            if cell in state_map:
                start = t
                while t < scheduler.last_instant and scheduler.timeline[t][p_idx] == cell:
                    t += 1
                records.append(
                    {
                        "Process": proc.name,
                        "State": state_map[cell],
                        "Start": start,
                        "Duration": t - start,
                        "End": t,
                    }
                )
            else:
                t += 1

    fig = go.Figure()
    colors = {"Running": "#2E86DE", "Waiting": "#F39C12"}

    for state in ("Running", "Waiting"):
        subset = [r for r in records if r["State"] == state]
        if not subset:
            continue
        fig.add_trace(
            go.Bar(
                name=state,
                y=[r["Process"] for r in subset],
                x=[r["Duration"] for r in subset],
                base=[r["Start"] for r in subset],
                orientation="h",
                marker_color=colors[state],
                customdata=[[r["Start"], r["End"]] for r in subset],
                hovertemplate=(
                    "<b>Process %{y}</b><br>"
                    f"State: {state}<br>"
                    "Interval: %{customdata[0]} → %{customdata[1]} (Duration: %{x})<extra></extra>"
                ),
            )
        )

    fig.update_layout(
        title=title,
        barmode="overlay",
        height=max(240, 55 * len(scheduler.processes) + 100),
        margin=dict(l=20, r=20, t=45, b=30),
        xaxis=dict(
            title="Time Instant",
            range=[0, scheduler.last_instant],
            dtick=1 if scheduler.last_instant <= 25 else 2,
            gridcolor="rgba(128,128,128,0.2)",
        ),
        yaxis=dict(
            title="Process",
            categoryorder="array",
            categoryarray=[p.name for p in reversed(scheduler.processes)],
        ),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
    )
    return fig


def _load_uploaded_file(raw_content: str) -> None:
    """Parses uploaded .txt content and updates GUI 2 state before widgets render."""
    _, parsed_algos, last_instant, processes = parse_input(raw_content)

    st.session_state["g2_last_instant"] = last_instant
    st.session_state["g2_process_df"] = pd.DataFrame(
        [{"Name": p.name, "Arrival": p.arrival_time, "Service": p.service_time} for p in processes]
    )

    selected_names: List[str] = []
    rr_qs: List[str] = []
    aging_qs: List[str] = []

    for alg_id, quantum in parsed_algos:
        algo_name = ID_TO_ALGO_NAME.get(alg_id)
        if algo_name and algo_name not in selected_names:
            selected_names.append(algo_name)
        if alg_id == "2" and quantum > 0:
            rr_qs.append(str(quantum))
        elif alg_id == "8" and quantum > 0:
            aging_qs.append(str(quantum))

    if selected_names:
        st.session_state["g2_selected_algos"] = selected_names
    if rr_qs:
        st.session_state["g2_rr_quantums"] = ", ".join(rr_qs)
    if aging_qs:
        st.session_state["g2_aging_quantums"] = ", ".join(aging_qs)


def render_multi_compare_gui() -> None:
    if "g2_last_instant" not in st.session_state:
        st.session_state["g2_last_instant"] = 20
    if "g2_process_df" not in st.session_state:
        st.session_state["g2_process_df"] = pd.DataFrame(DEFAULT_PROCESS_ROWS)
    if "g2_selected_algos" not in st.session_state:
        st.session_state["g2_selected_algos"] = ["FCFS", "RR", "SRT"]
    if "g2_rr_quantums" not in st.session_state:
        st.session_state["g2_rr_quantums"] = "1, 4"
    if "g2_aging_quantums" not in st.session_state:
        st.session_state["g2_aging_quantums"] = "1"
    if "g2_results" not in st.session_state:
        st.session_state["g2_results"] = None
    if "g2_last_uploaded_id" not in st.session_state:
        st.session_state["g2_last_uploaded_id"] = None

    st.header("CPU Scheduler — Form & Multi-Algorithm Comparison")
    st.caption("Configure processes manually or upload an input `.txt` file, then compare algorithms side-by-side.")

    # Direct .txt File Uploader (runs before form widgets are instantiated)
    uploaded_file = st.file_uploader(
        "Import Input File (.txt)",
        type=["txt"],
        key="g2_file_uploader",
        help="Upload a standard scheduler input file (e.g., 01a-input.txt) to populate the table and settings.",
    )
    if uploaded_file is not None:
        file_id = f"{uploaded_file.name}_{uploaded_file.size}"
        if st.session_state["g2_last_uploaded_id"] != file_id:
            try:
                content = uploaded_file.getvalue().decode("utf-8", errors="replace")
                _load_uploaded_file(content)
                st.session_state["g2_last_uploaded_id"] = file_id
                st.success(f"Loaded '{uploaded_file.name}' successfully.")
            except ValueError as err:
                st.error(f"File Import Error: {err}")

    st.divider()

    left_col, right_col = st.columns([1.15, 1], gap="large")

    with left_col:
        st.subheader("1. Process Table")
        edited_df = st.data_editor(
            st.session_state["g2_process_df"],
            num_rows="dynamic",
            use_container_width=True,
            hide_index=True,
            column_config={
                "Name": st.column_config.TextColumn("Process Name", required=True),
                "Arrival": st.column_config.NumberColumn("Arrival Time", min_value=0, step=1, required=True),
                "Service": st.column_config.NumberColumn("Service Time", min_value=1, step=1, required=True),
            },
            key="g2_editor",
        )

    with right_col:
        st.subheader("2. Simulation & Algorithms")
        last_instant = st.number_input(
            "Simulation Horizon (Last Instant)",
            min_value=1,
            max_value=500,
            key="g2_last_instant",
        )

        selected_algos = st.multiselect(
            "Select Algorithms to Compare",
            options=list(ALGO_CATALOG.keys()),
            key="g2_selected_algos",
        )

        q_col1, q_col2 = st.columns(2)
        rr_quantums_raw = ""
        aging_quantums_raw = ""

        if "RR" in selected_algos:
            with q_col1:
                rr_quantums_raw = st.text_input(
                    "RR Quantum(s)",
                    key="g2_rr_quantums",
                    help="Comma-separated integers (e.g., 1, 4)",
                )
        if "Aging" in selected_algos:
            with q_col2:
                aging_quantums_raw = st.text_input(
                    "Aging Quantum(s)",
                    key="g2_aging_quantums",
                    help="Comma-separated integers (e.g., 1, 2)",
                )

    run_compare = st.button("▶ Run Comparison", type="primary", use_container_width=True)

    if run_compare:
        try:
            if not selected_algos:
                raise ValueError("Select at least one algorithm to run.")

            processes = _build_process_list(edited_df)
            run_specs: List[Tuple[str, str, int]] = []

            for algo_name in selected_algos:
                alg_id, needs_quantum = ALGO_CATALOG[algo_name]
                if needs_quantum:
                    raw_q = rr_quantums_raw if algo_name == "RR" else aging_quantums_raw
                    for q in _parse_quantum_list(raw_q, algo_name):
                        display_label = f"{algo_name}-{q}"
                        run_specs.append((display_label, alg_id, q))
                else:
                    run_specs.append((algo_name, alg_id, -1))

            simulation_outputs = []
            for display_label, alg_id, quantum in run_specs:
                scheduler = Scheduler(processes, int(last_instant))
                scheduler.run(alg_id, quantum)

                proc_rows = []
                for p in scheduler.processes:
                    wait_time = p.turnaround_time - p.service_time
                    proc_rows.append(
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

                proc_df = pd.DataFrame(proc_rows)
                simulation_outputs.append(
                    {
                        "label": display_label,
                        "scheduler": scheduler,
                        "proc_df": proc_df,
                        "mean_tat": round(proc_df["Turnaround"].mean(), 2),
                        "mean_nt": round(proc_df["NormTurn"].mean(), 2),
                        "mean_wait": round(proc_df["Waiting"].mean(), 2),
                    }
                )

            st.session_state["g2_results"] = simulation_outputs

        except ValueError as err:
            st.error(f"Configuration Error: {err}")
        except Exception as err:
            st.error(f"Simulation Error: {err}")

    # Render Results
    results = st.session_state.get("g2_results")
    if results:
        st.divider()
        st.subheader("Comparison Summary")

        summary_df = pd.DataFrame(
            [
                {
                    "Algorithm": r["label"],
                    "Mean Turnaround": r["mean_tat"],
                    "Mean NormTurn": r["mean_nt"],
                    "Mean Waiting": r["mean_wait"],
                }
                for r in results
            ]
        )

        st.dataframe(
            summary_df.style.highlight_min(
                subset=["Mean Turnaround", "Mean NormTurn", "Mean Waiting"],
                color="#1e4620",
            ),
            use_container_width=True,
            hide_index=True,
        )

        chart_c1, chart_c2 = st.columns(2)
        with chart_c1:
            fig_tat = px.bar(
                summary_df,
                x="Algorithm",
                y="Mean Turnaround",
                color="Algorithm",
                text_auto=True,
                title="Mean Turnaround Time (Lower is Better)",
            )
            fig_tat.update_layout(showlegend=False, height=340)
            st.plotly_chart(fig_tat, use_container_width=True)

        with chart_c2:
            fig_nt = px.bar(
                summary_df,
                x="Algorithm",
                y="Mean NormTurn",
                color="Algorithm",
                text_auto=True,
                title="Mean Normalized Turnaround (Lower is Better)",
            )
            fig_nt.update_layout(showlegend=False, height=340)
            st.plotly_chart(fig_nt, use_container_width=True)

        st.subheader("Timelines & Per-Process Metrics")
        for r in results:
            with st.expander(
                f"{r['label']}  —  Mean Turnaround: {r['mean_tat']} | Mean NormTurn: {r['mean_nt']}",
                expanded=True,
            ):
                fig_gantt = _build_gantt_figure(r["scheduler"], f"{r['label']} Execution Timeline")
                st.plotly_chart(fig_gantt, use_container_width=True)
                st.dataframe(r["proc_df"], use_container_width=True, hide_index=True)