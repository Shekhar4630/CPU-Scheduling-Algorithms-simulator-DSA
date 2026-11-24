import streamlit as st
from main import SHOW_STATISTICS, TRACE, Scheduler
from parser import parse_input

SAMPLES = {
    "01a — FCFS (trace)": "trace\n1\n20\n5\nA,0,3\nB,2,6\nC,4,4\nD,6,5\nE,8,2\n",
    "02a — RR-1 (trace)": "trace\n2-1\n20\n5\nA,0,3\nB,2,6\nC,4,4\nD,6,5\nE,8,2\n",
    "03a — RR-4 (trace)": "trace\n2-4\n20\n5\nA,0,3\nB,2,6\nC,4,4\nD,6,5\nE,8,2\n",
    "Multi-Algo (stats)": "stats\n1,2-1,2-4,3,4,5,6,7,8-1\n20\n5\nA,0,3\nB,2,6\nC,4,4\nD,6,5\nE,8,2\n",
}


def _clear_inputs() -> None:
    """Callback executed before widgets re-instantiate on rerun."""
    st.session_state["raw_input_text"] = ""
    st.session_state["raw_output_text"] = ""
    st.session_state["last_uploaded_file_id"] = None


def execute_simulation(raw_text: str) -> str:
    """Parses raw text and runs the Scheduler, returning exact plain-text output."""
    operation, algorithms, last_instant, processes = parse_input(raw_text)
    output_blocks = []

    for alg_id, quantum in algorithms:
        if alg_id in ("2", "8") and quantum <= 0:
            raise ValueError(
                f"Algorithm '{alg_id}' requires a positive quantum (e.g., '{alg_id}-1')."
            )

        scheduler = Scheduler(processes, last_instant)
        label = scheduler.run(alg_id, quantum)

        if operation == TRACE:
            output_blocks.append(scheduler.format_timeline(label))
        elif operation == SHOW_STATISTICS:
            output_blocks.append(scheduler.format_stats(label))

    return "\n\n".join(output_blocks) + "\n"


def render_raw_io_gui() -> None:
    st.header("CPU Scheduler — Raw Text & File Mode")
    st.caption(
        "Paste your problem configuration directly or upload an input `.txt` file, then run the scheduler."
    )

    # Top utility bar: File Upload + Sample Loader
    util_col1, util_col2, util_col3 = st.columns([2, 2, 1], vertical_alignment="bottom")

    with util_col1:
        uploaded_file = st.file_uploader(
            "Upload Input File (.txt)",
            type=["txt"],
            help="Uploading a file populates the input textarea below.",
        )
        if uploaded_file is not None:
            file_id = f"{uploaded_file.name}_{uploaded_file.size}"
            if st.session_state["last_uploaded_file_id"] != file_id:
                content = uploaded_file.getvalue().decode("utf-8", errors="replace")
                st.session_state["raw_input_text"] = content
                st.session_state["last_uploaded_file_id"] = file_id
                st.rerun()

    with util_col2:
        selected_sample = st.selectbox(
            "Sample Presets",
            options=list(SAMPLES.keys()),
            index=0,
        )

    with util_col3:
        if st.button("Load Sample", use_container_width=True):
            st.session_state["raw_input_text"] = SAMPLES[selected_sample]
            st.session_state["last_uploaded_file_id"] = None
            st.rerun()

    st.divider()

    # Main Split Workspace: Input Left | Output Right
    in_col, out_col = st.columns(2, gap="large")

    with in_col:
        st.subheader("Input")
        raw_text = st.text_area(
            "Scheduler Input",
            key="raw_input_text",
            height=340,
            label_visibility="collapsed",
            placeholder="trace\n1\n20\n5\nA,0,3\nB,2,6\nC,4,4\nD,6,5\nE,8,2",
        )

        btn_col1, btn_col2 = st.columns([3, 1])
        with btn_col1:
            run_clicked = st.button("▶ Run Scheduler", type="primary", use_container_width=True)
        with btn_col2:
            st.button("Clear", use_container_width=True, on_click=_clear_inputs)

    with out_col:
        header_sub, dl_sub = st.columns([2, 1], vertical_alignment="center")
        with header_sub:
            st.subheader("Output")
        with dl_sub:
            if st.session_state["raw_output_text"]:
                st.download_button(
                    label="⬇ Download .txt",
                    data=st.session_state["raw_output_text"],
                    file_name="scheduler-output.txt",
                    mime="text/plain",
                    use_container_width=True,
                )

        if run_clicked:
            try:
                result = execute_simulation(raw_text)
                st.session_state["raw_output_text"] = result
                st.rerun()
            except ValueError as err:
                st.error(f"Input Error: {err}")
            except Exception as err:
                st.error(f"Simulation Error: {err}")

        if st.session_state["raw_output_text"]:
            st.code(st.session_state["raw_output_text"], language=None)
        else:
            st.info("Click **Run Scheduler** to generate the trace or statistics output.")