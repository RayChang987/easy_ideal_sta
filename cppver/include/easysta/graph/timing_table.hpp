#pragma once

#include <vector>

namespace easysta::graph {

// Mirrors timing_table.py: find_axis_index / get_value_from_table /
// get_1d_value_from_table.

// Returns i such that axis[i] <= x <= axis[i+1], clamped to [0, axis.size()-2].
int find_axis_index(const std::vector<double>& axis, double x);

// Bilinear interpolation over a 2D lookup table (values[row][col]).
// input_slew_index / output_load_index hold the axis vectors wrapped the same
// way liberty tables do (a single row: index_1, index_2).
double get_value_from_table(const std::vector<std::vector<double>>& values,
                             const std::vector<double>& input_slew_index,
                             const std::vector<double>& output_load_index,
                             double input_slew, double output_load);

// Linear interpolation over a 1D lookup table (values flattened).
double get_1d_value_from_table(const std::vector<std::vector<double>>& values,
                                const std::vector<double>& axis_index,
                                double target_value);

} // namespace easysta::graph
