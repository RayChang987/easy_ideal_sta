import os
from liberty.parser import parse_multi_liberty


def read_lib():
    # Read and parse a library.
    lib_dir = "/ISPD26-Contest/Platform/ASAP7/lib"
    lib_files = [
        f"{lib_dir}/asap7sc7p5t_AO_LVT_TT_nldm_211120.lib",
        f"{lib_dir}/asap7sc7p5t_AO_RVT_TT_nldm_211120.lib",
        f"{lib_dir}/asap7sc7p5t_AO_SLVT_TT_nldm_211120.lib",
        f"{lib_dir}/asap7sc7p5t_INVBUF_LVT_TT_nldm_220122.lib",
        f"{lib_dir}/asap7sc7p5t_INVBUF_RVT_TT_nldm_220122.lib",
        f"{lib_dir}/asap7sc7p5t_INVBUF_SLVT_TT_nldm_220122.lib",
        f"{lib_dir}/asap7sc7p5t_OA_LVT_TT_nldm_211120.lib",
        f"{lib_dir}/asap7sc7p5t_OA_RVT_TT_nldm_211120.lib",
        f"{lib_dir}/asap7sc7p5t_OA_SLVT_TT_nldm_211120.lib",
        f"{lib_dir}/asap7sc7p5t_SEQ_LVT_TT_nldm_220123.lib",
        f"{lib_dir}/asap7sc7p5t_SEQ_RVT_TT_nldm_220123.lib",
        f"{lib_dir}/asap7sc7p5t_SEQ_SLVT_TT_nldm_220123.lib",
        f"{lib_dir}/asap7sc7p5t_SIMPLE_LVT_TT_nldm_211120.lib",
        f"{lib_dir}/asap7sc7p5t_SIMPLE_RVT_TT_nldm_211120.lib",
        f"{lib_dir}/asap7sc7p5t_SIMPLE_SLVT_TT_nldm_211120.lib",
        f"{lib_dir}/fakeram_256x64.lib",
        f"{lib_dir}/sram_asap7_16x256_1rw.lib",
        f"{lib_dir}/sram_asap7_32x32_1rw.lib",
        f"{lib_dir}/sram_asap7_32x256_1rw.lib",
        f"{lib_dir}/sram_asap7_48x256_1rw.lib",
        f"{lib_dir}/sram_asap7_62x64_1rw.lib",
        f"{lib_dir}/sram_asap7_64x64_1rw.lib",
        f"{lib_dir}/sram_asap7_64x256_1rw.lib",
        f"{lib_dir}/sram_asap7_64x512_1rw.lib",
        f"{lib_dir}/sram_asap7_116x128_1rw.lib",
        f"{lib_dir}/sram_asap7_124x64_1rw.lib",
    ]

    print("=" * 40)
    print("Reading Files...")

    full_lib_content = ""
    for file_path in lib_files:
        if os.path.exists(file_path):
            with open(file_path, "r") as f:
                full_lib_content += f.read() + "\n"
        else:
            print(f"[Warning] File not found: {file_path}")

    print("Start Parsing Libs (This might take a while)...")

    libararies = parse_multi_liberty(full_lib_content)

    print("Done!")
    print("=" * 40)
    return libararies
