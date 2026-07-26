#pragma once

#include <optional>
#include <string>
#include <vector>

namespace easysta::liberty {

// Minimal hand-rolled parser for the Liberty (.lib) group syntax:
//   group_name (arg1, arg2, ...) { attr : value; sub_group (...) { ... } }
//   complex_attr (arg1, arg2, ...);
//   simple_attr : value;
// Mirrors the subset of python-liberty-parser's Group/Attribute API that
// parse_cell_db.py actually uses.

struct LibAttribute {
    std::string name;
    bool is_complex = false;
    std::string value;              // simple attribute value (unquoted)
    std::vector<std::string> args;  // complex attribute args (unquoted)
};

struct LibGroup {
    std::string group_name;
    std::vector<std::string> args;
    std::vector<LibAttribute> attributes;
    std::vector<LibGroup> groups;
};

// Parses the concatenated content of one or more .lib files. Returns the
// top-level groups found (normally one `library (...) { ... }` per file).
std::vector<LibGroup> parse_liberty(const std::string& content);

// Mirrors Group.get_groups(type_name): direct sub-groups matching group_name.
std::vector<const LibGroup*> get_groups(const LibGroup& g, const std::string& type_name);

// Mirrors Group.__getitem__ / get_attribute(key): value of the first simple
// attribute named `name`, or std::nullopt if absent (Python default is None).
std::optional<std::string> get_attr(const LibGroup& g, const std::string& name);

// Mirrors Group.get_array(key): parses a complex attribute's args into rows
// of doubles — each arg string is itself a comma-separated list of numbers.
// (e.g. index_1 ("5, 10, 20") -> [[5, 10, 20]]; values ("1, 2", "3, 4") ->
// [[1, 2], [3, 4]]).
std::vector<std::vector<double>> get_array(const LibGroup& g, const std::string& name);

} // namespace easysta::liberty
