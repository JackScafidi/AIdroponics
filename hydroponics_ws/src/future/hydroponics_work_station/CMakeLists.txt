cmake_minimum_required(VERSION 3.8)
project(hydroponics_work_station)

if(CMAKE_COMPILER_IS_GNUCXX OR CMAKE_CXX_COMPILER_ID MATCHES "Clang")
  add_compile_options(-Wall -Wextra -Wpedantic)
endif()

find_package(ament_cmake REQUIRED)
find_package(rclcpp REQUIRED)
find_package(rclcpp_action REQUIRED)
find_package(std_msgs REQUIRED)
find_package(std_srvs REQUIRED)
find_package(hydroponics_msgs REQUIRED)

add_executable(work_station_controller
  src/work_station_controller.cpp
)

target_compile_features(work_station_controller PUBLIC cxx_std_17)

ament_target_dependencies(work_station_controller
  rclcpp
  rclcpp_action
  std_msgs
  std_srvs
  hydroponics_msgs
)

install(TARGETS
  work_station_controller
  DESTINATION lib/${PROJECT_NAME}
)

install(DIRECTORY
  config
  DESTINATION share/${PROJECT_NAME}
)

if(BUILD_TESTING)
  find_package(ament_lint_auto REQUIRED)
  ament_lint_auto_find_test_dependencies()
endif()

ament_package()
