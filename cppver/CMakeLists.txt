cmake_minimum_required(VERSION 3.16)
project(easysta_cpp CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

if(NOT CMAKE_BUILD_TYPE)
    set(CMAKE_BUILD_TYPE Release)
endif()

add_executable(easysta
    src/graph/timing_table.cpp
    src/graph/timing_graph.cpp
    src/constraints/sdc_parser.cpp
    src/constraints/sdf_parser.cpp
    src/ranking/cell_rank.cpp
    src/placement/def_reader.cpp
    src/liberty/liberty_parser.cpp
    src/liberty/cell_db.cpp
    src/netlist/build_graph.cpp
    src/sta/propagation.cpp
    src/main.cpp
)

target_include_directories(easysta PRIVATE
    ${CMAKE_CURRENT_SOURCE_DIR}/include
    ${CMAKE_CURRENT_SOURCE_DIR}/third_party
)
