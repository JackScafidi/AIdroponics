cmake_minimum_required(VERSION 3.8)
project(hydroponics_msgs)

if(CMAKE_COMPILER_IS_GNUCXX OR CMAKE_CXX_COMPILER_ID MATCHES "Clang")
  add_compile_options(-Wall -Wextra -Wpedantic)
endif()

find_package(ament_cmake REQUIRED)
find_package(rosidl_default_generators REQUIRED)
find_package(std_msgs REQUIRED)
find_package(builtin_interfaces REQUIRED)

set(msg_files
  "msg/PlantPositionState.msg"
  "msg/InspectionResult.msg"
  "msg/ChannelHealthSummary.msg"
  "msg/HarvestAction.msg"
  "msg/HarvestPlan.msg"
  "msg/HarvestResult.msg"
  "msg/NutrientStatus.msg"
  "msg/TransportStatus.msg"
  "msg/GrowthDataPoint.msg"
  "msg/SystemAlert.msg"
  "msg/YieldMetrics.msg"
  "msg/LightStatus.msg"
  "msg/BehaviorTreeStatus.msg"
)

set(srv_files
  "srv/TriggerInspection.srv"
  "srv/ForceDose.srv"
  "srv/SetGrowthStage.srv"
  "srv/ResetCropCycle.srv"
  "srv/GetYieldAnalytics.srv"
  "srv/GetPlantHistory.srv"
  "srv/GetWorkStationStatus.srv"
  "srv/SetGrowLightIntensity.srv"
  "srv/SetInspectionLight.srv"
)

set(action_files
  "action/TransportTo.action"
  "action/MoveZ.action"
  "action/ExecuteHarvest.action"
)

rosidl_generate_interfaces(${PROJECT_NAME}
  ${msg_files}
  ${srv_files}
  ${action_files}
  DEPENDENCIES std_msgs builtin_interfaces
)

ament_export_dependencies(rosidl_default_runtime)
ament_package()
