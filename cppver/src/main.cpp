#include <fstream>
#include <iostream>
#include <sstream>
#include <string>
#include <vector>

#include "easysta/constraints/sdc_parser.hpp"
#include "easysta/graph/timing_graph.hpp"
#include "easysta/liberty/cell_db.hpp"
#include "easysta/liberty/liberty_parser.hpp"
#include "easysta/netlist/build_graph.hpp"
#include "easysta/placement/def_reader.hpp"
#include "easysta/ranking/cell_rank.hpp"
#include "easysta/sta/propagation.hpp"

namespace {

constexpr const char* kCsvFile = "gate_ranking_all_cells_analysis.csv";

// Mirrors read_lib.py: the fixed list of ASAP7 liberty files to load.
std::vector<std::string> asap7_lib_files() {
    const std::string lib_dir = "ISPD26-Contest/Platform/ASAP7/lib";
    return {
        lib_dir + "/asap7sc7p5t_AO_LVT_TT_nldm_211120.lib",
        lib_dir + "/asap7sc7p5t_AO_RVT_TT_nldm_211120.lib",
        lib_dir + "/asap7sc7p5t_AO_SLVT_TT_nldm_211120.lib",
        lib_dir + "/asap7sc7p5t_INVBUF_LVT_TT_nldm_220122.lib",
        lib_dir + "/asap7sc7p5t_INVBUF_RVT_TT_nldm_220122.lib",
        lib_dir + "/asap7sc7p5t_INVBUF_SLVT_TT_nldm_220122.lib",
        lib_dir + "/asap7sc7p5t_OA_LVT_TT_nldm_211120.lib",
        lib_dir + "/asap7sc7p5t_OA_RVT_TT_nldm_211120.lib",
        lib_dir + "/asap7sc7p5t_OA_SLVT_TT_nldm_211120.lib",
        lib_dir + "/asap7sc7p5t_SEQ_LVT_TT_nldm_220123.lib",
        lib_dir + "/asap7sc7p5t_SEQ_RVT_TT_nldm_220123.lib",
        lib_dir + "/asap7sc7p5t_SEQ_SLVT_TT_nldm_220123.lib",
        lib_dir + "/asap7sc7p5t_SIMPLE_LVT_TT_nldm_211120.lib",
        lib_dir + "/asap7sc7p5t_SIMPLE_RVT_TT_nldm_211120.lib",
        lib_dir + "/asap7sc7p5t_SIMPLE_SLVT_TT_nldm_211120.lib",
        lib_dir + "/fakeram_256x64.lib",
        lib_dir + "/sram_asap7_16x256_1rw.lib",
        lib_dir + "/sram_asap7_32x32_1rw.lib",
        lib_dir + "/sram_asap7_32x256_1rw.lib",
        lib_dir + "/sram_asap7_48x256_1rw.lib",
        lib_dir + "/sram_asap7_62x64_1rw.lib",
        lib_dir + "/sram_asap7_64x64_1rw.lib",
        lib_dir + "/sram_asap7_64x256_1rw.lib",
        lib_dir + "/sram_asap7_64x512_1rw.lib",
        lib_dir + "/sram_asap7_116x128_1rw.lib",
        lib_dir + "/sram_asap7_124x64_1rw.lib",
    };
}

std::vector<easysta::liberty::LibGroup> read_lib() {
    std::cout << std::string(40, '=') << std::endl;
    std::cout << "Reading Files..." << std::endl;

    std::string full_lib_content;
    for (const auto& path : asap7_lib_files()) {
        std::ifstream f(path);
        if (f.good()) {
            std::ostringstream ss;
            ss << f.rdbuf();
            full_lib_content += ss.str();
            full_lib_content += "\n";
        } else {
            std::cout << "[Warning] File not found: " << path << std::endl;
        }
    }

    std::cout << "Start Parsing Libs (This might take a while)..." << std::endl;
    auto libraries = easysta::liberty::parse_liberty(full_lib_content);
    std::cout << "Done!" << std::endl;
    std::cout << std::string(40, '=') << std::endl;
    return libraries;
}

} // namespace

int main(int argc, char** argv) {
    if (argc != 6) {
        std::cout << "Usage: easysta <json_file> <top_module> <sdc_file> <def_file> <output_tcl_file>" << std::endl;
        return 1;
    }

    std::string json_file = argv[1];
    std::string top_module = argv[2];
    std::string sdc_file = argv[3];
    std::string def_file = argv[4];
    // output_tcl_file (argv[5]) is accepted for CLI parity but unused, matching main.py.

    auto sdc_info = easysta::constraints::load_sdc(sdc_file);

    auto raw_libs = read_lib();
    if (raw_libs.empty()) {
        std::cout << "No libraries loaded. Exiting." << std::endl;
        return 1;
    }

    std::cout << "Extracting Cell Database..." << std::endl;
    auto cell_db = easysta::liberty::load_cell_db(raw_libs);

    auto tg = easysta::netlist::build_timing_graph(json_file, top_module, cell_db, sdc_info);
    auto order = tg.topo_sort();
    if (!order.empty()) {
        std::cout << "[SUCCESS] Topological sort finished. Length: " << order.size() << std::endl;
    } else {
        std::cout << "[FAIL] Graph contains cycles or is empty." << std::endl;
    }

    std::cout << "Running Delay Calculation..." << std::endl;

    auto gate_rank_result = easysta::ranking::load_gate_rank(kCsvFile);

    std::cout << "Reading DEF for wire length estimation..." << std::endl;
    auto def_result = easysta::placement::read_def(def_file);

    auto violation_end_points = easysta::sta::calculate_delay(
        order, cell_db, sdc_info, tg.instance_to_clocks,
        gate_rank_result.type_to_cells, &def_result.pin_wl);

    return 0;
}
