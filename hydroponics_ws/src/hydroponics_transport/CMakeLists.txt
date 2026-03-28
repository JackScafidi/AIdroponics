cmake_minimum_required(VERSION 3.8)
project(hydroponics_transport)

if(CMAKE_COMPILER_IS_GNUCXX OR CMAKE_CXX_COMPILER_ID MATCHES "Clang")
  add_compile_options(-Wall -Wextra -Wpedantic)
endif()

# Find dependencies
find_package(ament_cmake REQUIRED)
find_package(rclcpp REQUIRED)
find_package(rclcpp_action REQUIRED)
find_package(hydroponics_msgs REQUIRED)
find_package(std_msgs REQUIRED)

# transport_controller executable
add_executable(transport_controller src/transport_controller.cpp)
target_compile_features(transport_controller PUBLIC cxx_std_17)
ament_target_dependencies(transport_controller
  rclcpp
  rclcpp_action
  hydroponics_msgs
  std_msgs
)

install(TARGETS
  transport_controller
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
