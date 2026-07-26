# cppver Architecture

C++17 port of the EasySTA CLI pipeline (`main.py`). Organized into domain
modules under `include/easysta/` and `src/`, each with a matching
sub-namespace. Dependencies are one-way (no cycles).

```
graph/        easysta::graph        — timing graph core data structures + lookup-table interpolation
liberty/      easysta::liberty      — .lib parser + cell/pin/timing-arc database
constraints/  easysta::constraints  — SDC / SDF parsing
placement/    easysta::placement    — DEF parsing + wire-length estimation
ranking/      easysta::ranking      — gate power-ranking CSV
netlist/      easysta::netlist      — Yosys JSON netlist -> TimingGraph
sta/          easysta::sta          — delay/slack propagation engine
```

Dependency direction: `graph`, `liberty`, `constraints`, `placement`, and
`ranking` are leaves (no dependencies on each other). `netlist` depends on
`liberty` + `constraints` + `graph`. `sta` depends on `liberty` +
`constraints` + `graph`. `main.cpp` wires everything together.

One deliberate exception: `graph::TimingArc` holds a raw
`const liberty::TimingArcDef*` (see "Hot-path / GPU-readiness notes"
below), forward-declared only — `timing_node.hpp` does not include
`liberty/cell_db.hpp` or call anything from it, so this stays a
pointer-only coupling, not a real dependency edge.

## Dataflow

Execution order, matching `main.cpp`:

```
.sdc --> constraints::load_sdc ------------------> SdcData
                                                       |
.lib --> liberty::parse_liberty --> LibGroup tree      |
              |                                       |
              v                                       |
         liberty::load_cell_db --> CellInfo database   |
              |                                       |
              +---------------+-----------------------+
              v               v
.json --> netlist::build_timing_graph --> graph::TimingGraph
                                              |
                                              v
                                    TimingGraph::topo_sort()
                                              |
.csv --> ranking::load_gate_rank             |
              |                              |
.def --> placement::read_def                 |
   (RMST wire length)                        |
              |                              v
              +--------------> sta::calculate_delay
                                    (delay/slew propagation + slack + critical path)
```

In short: the liberty files build a dictionary of "what timing arcs and
lookup tables does each cell type have"; the Yosys JSON netlist wires actual
instances onto those arcs to form a graph; the DEF file estimates wire
length for parasitic capacitance; finally, after a topological sort, forward
delay/slew propagation over the graph computes setup slack at every
endpoint.

## Key classes / structs

**`liberty::LibGroup` / `LibAttribute`** (`liberty_parser.hpp`)
Generic Liberty syntax-tree node, mirroring the Python `liberty-parser`
package's `Group`/`Attribute` API. A `LibGroup` has a `group_name`, `args`,
nested `groups`, and `attributes`. This layer has no notion of "cell" or
"pin" — it just parses the `.lib` `group (args) { ... }` syntax into a tree,
queried via `get_groups()` / `get_attr()` / `get_array()`.

**`liberty::CellInfo`** (`cell_db.hpp`)
Interprets the generic tree into what STA actually needs: `pins` (each
pin's direction/capacitance), `timing_arcs` (keyed by
`"related_pin/pin/None[/timing_type]"`, valued by `TimingArcDef` — a
`timing_sense` plus a set of `TimingTable`s), and `clocked_on` (whether this
cell is a flip-flop and which pin is its clock). `load_cell_db()` converts a
`vector<LibGroup>` into `unordered_map<cell_name, CellInfo>`.

**`graph::TimingNode`** (`timing_node.hpp`)
A node in the timing graph, corresponding to one `inst/pin`. Holds STA
runtime state: `rise_at`/`fall_at` (arrival times), `rise_slew`/`fall_slew`,
`load` (summed fanout capacitance), and `worst_pred_arc` for critical-path
traceback.

**`graph::TimingArc`**
An edge between nodes. Two `arc_type`s: `"cell"` (an intra-cell pin-to-pin
timing arc, delay from a lookup table) and `"net"` (driver pin to load pin,
delay from wire-length estimation). "cell" arcs also cache
`cell_arc_def`, a pointer to their resolved `liberty::TimingArcDef`,
set once by `build_timing_graph()`.

**`graph::TimingGraph`** (`timing_graph.hpp`)
Owns the whole graph: `nodes` (`(inst,pin) -> TimingNode`, via
`unique_ptr`) and `arcs`. Core method `topo_sort()` orders nodes with Kahn's
algorithm; on a cycle it calls `find_cycle()` to print the offending loop.
The free function `graph::levelize(topo_order)` groups that order into
dependency-free levels — see "Hot-path / GPU-readiness notes" below.

**`netlist::build_timing_graph()`** (`build_graph.hpp` — a function, not a
class)
Takes the Yosys JSON netlist plus the `CellInfo` database and expands them
into an actual `TimingGraph`: creates nodes for every port/cell instance,
adds intra-cell arcs from `CellInfo.timing_arcs`, and adds net arcs from
each net's driver/load relationships.

**`sta::calculate_node()` / `calculate_delay()`** (`propagation.hpp` —
functions, not a class)
The STA engine itself. `calculate_delay()` first sweeps the graph in
reverse to accumulate each driver's fanout + wire capacitance, then calls
`graph::levelize()` and walks the result level by level, calling
`calculate_node()` for every node: for every fanin arc it looks up
delay/slew, takes the worst-case arrival time, computes setup slack at
endpoints, and tracks TNS/WNS.

**`placement::read_def()`** (`def_reader.hpp`)
Pure string parsing of the DEF file to get each component/pin's coordinates,
then uses Prim's algorithm to estimate each net's RMST (rectilinear minimum
spanning tree) wire length as input to wire delay/capacitance estimation.

**`constraints::SdcData`**
Holds clock periods/uncertainty and port input/output delays — the boundary
conditions `sta::calculate_node()` uses when computing slack.

## Hot-path / GPU-readiness notes

`sta::calculate_node()`, called once per fanin arc of every node in the
graph, is the only part of the pipeline whose cost scales with design size
(everything else — parsing, graph build, topo sort — runs once and is I/O-
or hashmap-bound, not a repeated numeric hot loop). Two refactors keep this
path lean and set it up for future parallel dispatch (host multi-threading
now, GPU wavefront kernels later):

1. **No string-keyed lookups in the hot loop.** `calculate_node()` used to
   rebuild a `"src_pin/dst_pin/when[/timing_type]"` string and hash into
   `CellInfo::timing_arcs` for *every* cell arc, on every call. Since a
   `TimingArc`'s cell type is fixed at build time (outside of gate
   resizing), `netlist::build_timing_graph()` now resolves that lookup once
   and caches the pointer as `TimingArc::cell_arc_def`. The hot path is a
   pointer dereference; `resolve_arc_def()` in `propagation.cpp` only falls
   back to the by-key hashmap lookup for `sizable` (resizable) nodes, whose
   effective cell type can change after the arc was built.

2. **Levelized dispatch.** `graph::levelize(topo_order)` groups the
   topological order into levels where every node's fanin lives in a
   strictly earlier level — nodes within one level have no dependency on
   each other. `calculate_delay()` walks levels in order but nodes within a
   level sequentially; this is deliberately the loop boundary a
   parallel-for (OpenMP/TBB on CPU) or a per-level GPU kernel launch would
   split on, without changing `calculate_node()` itself.

Porting the per-level loop to an actual GPU backend (CUDA on
Linux/NVIDIA, Metal on Apple Silicon — there is no CUDA on macOS) would
still require flattening the pointer-based `TimingNode`/`TimingArc` graph
and `TimingTable` lookup data into contiguous index-based (CSR-style)
arrays, since neither GPU API can efficiently walk `unique_ptr` graphs or
`std::unordered_map`. That flattening is not part of this refactor.

## Note

`constraints::load_sdf` (SDF parser) is ported for parity with the Python
version but, like the original, is not called from `main.cpp` — it's kept
as a standalone module in case it's needed later.
