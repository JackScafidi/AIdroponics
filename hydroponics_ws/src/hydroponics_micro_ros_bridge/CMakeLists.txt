cmake_minimum_required(VERSION 3.8)
project(hydroponics_micro_ros_bridge)

if(CMAKE_COMPILER_IS_GNUCXX OR CMAKE_CXX_COMPILER_ID MATCHES "Clang")
  add_compile_options(-Wall -Wextra -Wpedantic)
endif()

find_package(ament_cmake REQUIRED)
find_package(rclcpp REQUIRED)
find_package(std_msgs REQUIRED)
find_package(hydroponics_msgs REQUIRED)

add_executable(micro_ros_bridge src/micro_ros_bridge.cpp)
ament_target_dependencies(micro_ros_bridge
  rclcpp
  std_msgs
  hydroponics_msgs
)

install(TARGETS micro_ros_bridge
  DESTINATION lib/${PROJECT_NAME}
)

ament_package()
