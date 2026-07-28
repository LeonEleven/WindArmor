from setuptools import find_packages, setup

package_name = "imu_cybergear_ros2"

setup(
    name=package_name,
    version="0.2.0",
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
    maintainer="imu_cybergear_user",
    maintainer_email="user@example.com",
    description="ROS 2 package for IMU-driven dynamic CyberGear motor control.",
    license="Apache-2.0",
    tests_require=["pytest"],
    entry_points={
        "console_scripts": [
            "imu_driver_node = imu_cybergear_ros2.imu_driver_node:main",
            "imu_motor_controller_node = imu_cybergear_ros2.imu_motor_controller_node:main",
        ],
    },
)
