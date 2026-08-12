#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd -- "${SCRIPT_DIR}/.." && pwd)"
WINDARMOR_CI_PYTHON="${WINDARMOR_CI_PYTHON:-python3}"

cleanup_output=false
if [[ -n "${WINDARMOR_CI_OUTPUT_ROOT:-}" ]]; then
  CI_OUTPUT_ROOT="${WINDARMOR_CI_OUTPUT_ROOT}"
else
  CI_OUTPUT_ROOT="$(mktemp -d -t windarmor-ci.XXXXXX)"
  cleanup_output=true
fi
BUILD_BASE="${CI_OUTPUT_ROOT}/build"
INSTALL_BASE="${CI_OUTPUT_ROOT}/install"
LOG_BASE="${CI_OUTPUT_ROOT}/log"
ROS_LOG_DIR="${CI_OUTPUT_ROOT}/ros-logs"
export ROS_LOG_DIR

cleanup() {
  if [[ "${cleanup_output}" == true ]]; then
    rm -rf -- "${CI_OUTPUT_ROOT}"
  fi
}
trap cleanup EXIT

mkdir -p -- "${BUILD_BASE}" "${INSTALL_BASE}" "${LOG_BASE}" "${ROS_LOG_DIR}"
cd -- "${REPO_ROOT}"

section() {
  echo
  echo "===== $1 ====="
}

source_ros() {
  set +u
  source /opt/ros/jazzy/setup.bash
  set -u
}

source_workspace() {
  set +u
  source /opt/ros/jazzy/setup.bash
  source "${INSTALL_BASE}/setup.bash"
  set -u
}

run_stage() {
  case "$1" in
    safety)
      section "CI safety check"
      "${WINDARMOR_CI_PYTHON}" scripts/check_ci_safety.py
      ;;
    whitespace)
      section "Git whitespace check"
      "${WINDARMOR_CI_PYTHON}" scripts/check_git_whitespace.py
      ;;
    py-compile)
      section "Python compile"
      "${WINDARMOR_CI_PYTHON}" -m py_compile \
        src/imu_cybergear_ros2/imu_cybergear_ros2/*.py \
        src/windarmor_fan_controller/windarmor_fan_controller/*.py \
        src/windarmor_flight_control/windarmor_flight_control/*.py \
        src/windarmor_flight_control/windarmor_flight_control/core/*.py \
        src/windarmor_flight_control/windarmor_flight_control/algorithms/*.py \
        src/windarmor_flight_control/windarmor_flight_control/runtime/*.py \
        src/imu_cybergear_ros2/launch/*.py \
        src/windarmor_fan_controller/launch/*.py \
        src/windarmor_bringup/launch/*.py \
        src/windarmor_flight_control/launch/*.py \
        scripts/check_ci_safety.py \
        scripts/check_git_whitespace.py
      ;;
    build)
      section "Colcon build"
      source_ros
      colcon --log-base "${LOG_BASE}" build \
        --build-base "${BUILD_BASE}" \
        --install-base "${INSTALL_BASE}" \
        --symlink-install
      ;;
    motor-tests)
      section "Motor package pytest"
      source_workspace
      "${WINDARMOR_CI_PYTHON}" -m pytest src/imu_cybergear_ros2/test -q
      ;;
    fan-tests)
      section "Fan safety regression"
      source_workspace
      "${WINDARMOR_CI_PYTHON}" -m pytest \
        src/windarmor_fan_controller/test -q
      ;;
    flight-tests)
      section "Flight API pure-Python tests"
      source_workspace
      "${WINDARMOR_CI_PYTHON}" -m pytest \
        src/windarmor_flight_control/test \
        src/windarmor_interfaces/test \
        -q
      ;;
    full-tests)
      section "Full workspace colcon test"
      source_workspace
      colcon --log-base "${LOG_BASE}" test \
        --build-base "${BUILD_BASE}" \
        --install-base "${INSTALL_BASE}" \
        --packages-select \
          imu_cybergear_ros2 \
          windarmor_fan_controller \
          windarmor_interfaces \
          windarmor_flight_control \
          windarmor_bringup
      ;;
    test-result)
      section "Colcon test result"
      source_workspace
      colcon test-result --test-result-base "${BUILD_BASE}" --verbose
      ;;
    *)
      echo "Unknown CI stage: $1" >&2
      return 2
      ;;
  esac
}

if [[ $# -gt 1 ]]; then
  echo "Usage: $0 [safety|whitespace|py-compile|build|motor-tests|fan-tests|flight-tests|full-tests|test-result]" >&2
  exit 2
fi

if [[ $# -eq 1 ]]; then
  run_stage "$1"
else
  for stage in \
    safety whitespace py-compile build motor-tests fan-tests flight-tests full-tests test-result
  do
    run_stage "${stage}"
  done
fi
