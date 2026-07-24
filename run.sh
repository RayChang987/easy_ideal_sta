#!/bin/bash
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")"

# ---- config -----------------------------------------------------------
TESTCASE="${TESTCASE:-aes_cipher_top}"
CONFIG="${CONFIG:-}"
OUTPUT_TCL="resize_result.tcl"
GUI=false

usage() {
    echo "Usage: $0 [-t|--testcase NAME] [-g|--gui]"
    echo "  -t, --testcase NAME  Testcase under ISPD26-Contest/ to run (default: aes_cipher_top)"
    echo "  -g, --gui            Launch the GUI viewer after the CLI run (default: off)"
    exit 1
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        -t|--testcase) TESTCASE="$2"; shift 2 ;;
        -g|--gui) GUI=true; shift ;;
        -h|--help) usage ;;
        *) echo "Unknown option: $1"; usage ;;
    esac
done

# ---- 1. sync dependencies ----------------------------------------------
echo "==> uv sync"
uv sync

# ---- 2. fetch benchmark data if missing --------------------------------
if [[ ! -d "ISPD26-Contest" ]]; then
    echo "==> ISPD26-Contest/ not found, downloading benchmarks"
    ./download_benchmark.sh
else
    echo "==> ISPD26-Contest/ already present, skipping download"
fi

if [[ ! -d "ISPD26-Contest/Platform/ASAP7/lib" ]]; then
    echo "[Warning] ISPD26-Contest/Platform/ASAP7/lib not found."
    echo "          download_benchmark.sh only fetches the Benchmarks tarball."
    echo "          Get the Platform/ASAP7 lib+lef files from"
    echo "          https://github.com/ABKGroup/ISPD26-Contest and copy them into"
    echo "          ISPD26-Contest/Platform/, or the STA run below will fail."
fi

if [[ ! -d "ISPD26-Contest/${TESTCASE}" ]]; then
    echo "[Error] Testcase '${TESTCASE}' not found under ISPD26-Contest/"
    exit 1
fi

if [[ -z "$CONFIG" ]]; then
    CONFIG="$(find "ISPD26-Contest/${TESTCASE}" -mindepth 1 -maxdepth 1 -type d -exec basename {} \; | sort | head -n1)"
fi
if [[ -z "$CONFIG" ]]; then
    echo "[Error] No config subdirectory found under ISPD26-Contest/${TESTCASE}/"
    exit 1
fi

CASE_DIR="ISPD26-Contest/${TESTCASE}/${CONFIG}"
JSON_FILE="${CASE_DIR}/${TESTCASE}_netlist.json"
SDC_FILE="${CASE_DIR}/contest.sdc"
DEF_FILE="${CASE_DIR}/contest.def"

# ---- 3. verilog -> yosys json netlist -----------------------------------
if [[ -f "$JSON_FILE" ]]; then
    echo "==> $JSON_FILE already exists, skipping yosys"
else
    echo "==> Running yosys to generate $JSON_FILE"
    if ! docker container inspect yosys >/dev/null 2>&1; then
        docker run -d --name yosys -v "$(pwd)/ISPD26-Contest:/work" hdlc/yosys sleep infinity
    fi
    docker exec yosys yosys -p \
        "read_verilog /work/${TESTCASE}/${CONFIG}/contest.v; \
         hierarchy -auto-top; \
         write_json /work/${TESTCASE}/${CONFIG}/${TESTCASE}_netlist.json"
    docker rm -f yosys >/dev/null
    docker image rm -f hdlc/yosys:latest >/dev/null
fi

# ---- 4. CLI: run STA -----------------------------------------------------
echo "==> Running CLI STA on ${TESTCASE}/${CONFIG}"
uv run python main.py "$JSON_FILE" "$TESTCASE" "$SDC_FILE" "$DEF_FILE" "$OUTPUT_TCL"

# ---- 5. GUI (opt-in) ------------------------------------------------------
if [[ "$GUI" == true ]]; then
    echo "==> Launching GUI viewer"
    uv run python gui_viewer.py "$JSON_FILE" "$SDC_FILE" "$DEF_FILE"
fi
