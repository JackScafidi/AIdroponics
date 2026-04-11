cmake_minimum_required(VERSION 3.8)
project(hydroponics_bt)

if(CMAKE_COMPILER_IS_GNUCXX OR CMAKE_CXX_COMPILER_ID MATCHES "Clang")
  add_compile_options(-Wall -Wextra -Wpedantic)
endif()

# Find dependencies
find_package(ament_cmake REQUIRED)
find_package(rclcpp REQUIRED)
find_package(rclcpp_action REQUIRED)
find_package(behaviortree_cpp REQUIRED)
find_package(hydroponics_msgs REQUIRED)
find_package(std_msgs REQUIRED)
find_package(ament_index_cpp REQUIRED)

set(BT_NODE_SOURCES
  src/bt_nodes/transport_nodes.cpp
  src/bt_nodes/work_station_nodes.cpp
  src/bt_nodes/vision_nodes.cpp
  src/bt_nodes/harvest_nodes.cpp
  src/bt_nodes/nutrient_nodes.cpp
  src/bt_nodes/safety_nodes.cpp
)

# bt_manager executable
add_executable(bt_manager
  src/bt_manager.cpp
  ${BT_NODE_SOURCES}
)

target_include_directories(bt_manager PUBLIC
  $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/include>
  $<INSTALL_INTERFACE:include>
)

target_compile_features(bt_manager PUBLIC cxx_std_17)

ament_target_dependencies(bt_manager
  rclcpp
  rclcpp_action
  behaviortree_cpp
  hydroponics_msgs
  std_msgs
  ament_index_cpp
)

install(TARGETS
  bt_manager
  DESTINATION lib/${PROJECT_NAME}
)

install(DIRECTORY
  trees
  DESTINATION share/${PROJECT_NAME}
)

install(DIRECTORY
  include/
  DESTINATION include
)

if(BUILD_TESTING)
  find_package(ament_lint_auto REQUIRED)
  ament_lint_auto_find_test_dependencies()
endif()

ament_package()
