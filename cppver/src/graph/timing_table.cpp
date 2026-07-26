#include "easysta/graph/timing_table.hpp"

#include <algorithm>

namespace easysta::graph {

int find_axis_index(const std::vector<double>& axis, double x) {
    if (x <= axis.front()) return 0;
    if (x >= axis.back()) return static_cast<int>(axis.size()) - 2;
    auto it = std::lower_bound(axis.begin(), axis.end(), x);
    return static_cast<int>(it - axis.begin()) - 1;
}

double get_value_from_table(const std::vector<std::vector<double>>& values,
                             const std::vector<double>& input_slew_index,
                             const std::vector<double>& output_load_index,
                             double input_slew, double output_load) {
    const auto& axis1 = input_slew_index;
    const auto& axis2 = output_load_index;
    const auto& table = values;

    size_t size1 = axis1.size();
    size_t size2 = axis2.size();

    if (size1 == 1) {
        if (size2 == 1) {
            return table[0][0];
        }
        int j = find_axis_index(axis2, output_load);
        double x2l = axis2[j], x2u = axis2[j + 1];
        double dx2 = (output_load - x2l) / (x2u - x2l);
        double y00 = table[0][j];
        double y01 = table[0][j + 1];
        return (1 - dx2) * y00 + dx2 * y01;
    }

    if (size2 == 1) {
        int i = find_axis_index(axis1, input_slew);
        double x1l = axis1[i], x1u = axis1[i + 1];
        double dx1 = (input_slew - x1l) / (x1u - x1l);
        double y00 = table[i][0];
        double y10 = table[i + 1][0];
        return (1 - dx1) * y00 + dx1 * y10;
    }

    int i = find_axis_index(axis1, input_slew);
    int j = find_axis_index(axis2, output_load);

    double x1l = axis1[i], x1u = axis1[i + 1];
    double x2l = axis2[j], x2u = axis2[j + 1];

    double dx1 = (input_slew - x1l) / (x1u - x1l);
    double dx2 = (output_load - x2l) / (x2u - x2l);

    double y00 = table[i][j];
    double y10 = table[i + 1][j];
    double y01 = table[i][j + 1];
    double y11 = table[i + 1][j + 1];

    return (1 - dx1) * (1 - dx2) * y00
         + dx1 * (1 - dx2) * y10
         + dx1 * dx2 * y11
         + (1 - dx1) * dx2 * y01;
}

double get_1d_value_from_table(const std::vector<std::vector<double>>& values,
                                const std::vector<double>& axis_index,
                                double target_value) {
    const auto& axis = axis_index;

    // Flatten values (liberty 1D tables may be stored as a single row).
    std::vector<double> table;
    for (const auto& row : values) {
        table.insert(table.end(), row.begin(), row.end());
    }

    size_t size = axis.size();
    if (size == 1) {
        return table[0];
    }

    int i = find_axis_index(axis, target_value);
    double xl = axis[i], xu = axis[i + 1];
    double dx = (target_value - xl) / (xu - xl);

    double y0 = table[i];
    double y1 = table[i + 1];

    return (1 - dx) * y0 + dx * y1;
}

} // namespace easysta::graph
