set design_dir "/design/aes_cipher_top/TCP_250_UTIL_0.40"
set lib_dir "/design/Platform/ASAP7/lib"





# Read liberty libraries (RVT cells)
foreach lib_file [glob $lib_dir/asap7sc7p5t_*_RVT_TT_nldm_*.lib] {
    read_liberty $lib_file
}
foreach lib_file [glob $lib_dir/asap7sc7p5t_*_LVT_TT_nldm_*.lib] {
    read_liberty $lib_file
}
foreach lib_file [glob $lib_dir/asap7sc7p5t_*_SLVT_TT_nldm_*.lib] {
    read_liberty $lib_file
}
# SRAM libs
foreach lib_file [glob $lib_dir/sram_*.lib] {
    read_liberty $lib_file
}

# Read netlist
read_verilog $design_dir/contest.v
link_design aes_cipher_top

# Read timing constraints
read_sdc $design_dir/contest.sdc


set_cmd_units -time ns -capacitance pF -current mA -voltage V -resistance kOhm -distance um
set_units -power mW


# Idea: Set load and resistance to 0 for all nets to ignore parasitics in STA
set_ideal_network [all_clocks]
set_load 0 [get_nets *]
set_resistance 0 [get_nets *]


# Report timing
puts "\n===== Setup (max) timing report: top 10 paths ====="
report_checks -path_delay max -group_path_count 10 -format full_clock_expanded

puts "\n===== Hold (min) timing report: top 5 paths ====="
report_checks -path_delay min -group_path_count 5 -format full_clock_expanded

puts "\n===== Timing summary ====="
report_check_types -max_slew -max_cap -max_fanout -violators

puts "\n===== WNS / TNS ====="
report_wns
report_tns

puts "\nDone."
