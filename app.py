import streamlit as st
from views.gui_multi_compare import render_multi_compare_gui
from views.gui_raw_io import render_raw_io_gui
from views.gui_single_visualizer import render_single_visualizer_gui

st.set_page_config(
    page_title="CPU Scheduling Simulator",
    page_icon="⚙️",
    layout="wide",
    initial_sidebar_state="expanded",
)


def init_session_state() -> None:
    """Initialize shared state keys across GUI views."""
    defaults = {
        "raw_input_text": "trace\n1\n20\n5\nA,0,3\nB,2,6\nC,4,4\nD,6,5\nE,8,2\n",
        "raw_output_text": "",
        "last_uploaded_file_id": None,
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


def main() -> None:
    init_session_state()

    with st.sidebar:
        st.title("⚙️ CPU Scheduler")
        st.caption("DSA Scheduling Algorithms Simulator")
        st.divider()

        gui_mode = st.radio(
            "Select Interface Mode",
            options=[
                "GUI 1: Text & File Input",
                "GUI 2: Form & Multi-Algo Comparison",
                "GUI 3: Individual Algo Visualizer",
            ],
            index=0,
        )

        st.divider()
        with st.expander("Algorithm ID Reference", expanded=False):
            st.markdown(
                """
                - `1` — **FCFS** (First Come First Serve)
                - `2-<q>` — **RR** (Round Robin, e.g., `2-1`, `2-4`)
                - `3` — **SPN** (Shortest Process Next)
                - `4` — **SRT** (Shortest Remaining Time)
                - `5` — **HRRN** (Highest Response Ratio Next)
                - `6` — **FB-1** (Feedback q=1)
                - `7` — **FB-2i** (Feedback q=2^i)
                - `8-<q>` — **Aging** (e.g., `8-1`)
                """
            )

    if gui_mode == "GUI 1: Text & File Input":
        render_raw_io_gui()
    elif gui_mode == "GUI 2: Form & Multi-Algo Comparison":
        render_multi_compare_gui()
    elif gui_mode == "GUI 3: Individual Algo Visualizer":
        render_single_visualizer_gui()


if __name__ == "__main__":
    main()