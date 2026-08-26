from setuptools import find_packages, setup

package_name = "imu_cybergear_ros2"

setup(
    name=package_name,
    version="0.4.0",
    packages=find_packages(exclude=["test"]),
    data_files=[
        ("share/ament_index/resource_index/packages", ["resource/" + package_name]),
        ("share/" + package_name, ["package.xml"]),
        ("share/" + package_name + "/launch", [
            "launch/imu_cybergear_system.launch.py",
            "launch/imu_motor_controller.launch.py",
        ]),
        ("share/" + package_name + "/config", ["config/imu_cybergear_params.yaml"]),
        (
            "share/" + package_name + "/docs",
            [
                "docs/项目总览与功能清单.md",
                "docs/环境搭建到调试运行手册.md",
                "docs/IMU_CyberGear_Guide.md",
            ],
        ),
        ("share/" + package_name, ["README.md"]),
    ],
    install_requires=["setuptools", "pyserial", "python-can"],
    zip_safe=True,
    maintainer="LeonEleven",
    maintainer_email="elevenlianm@foxmail.com",
    description="ROS 2 package for IMU-driven CyberGear motor control with safety watchdog, emergency stop, motor feedback monitoring, and automatic reconnection.",
    license="Apache-2.0",
    tests_require=["pytest"],
    entry_points={
        "console_scripts": [
            "imu_driver_node = imu_cybergear_ros2.imu_driver_node:main",
            "imu_motor_controller_node = imu_cybergear_ros2.imu_motor_controller_node:main",
            "imu_relative_observer_node = imu_cybergear_ros2.imu_relative_observer_node:main",
            "motor_feedback_observer_node = imu_cybergear_ros2.motor_feedback_observer_node:main",
        ],
    },
)
