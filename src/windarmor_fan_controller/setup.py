from setuptools import find_packages, setup

package_name = "windarmor_fan_controller"

setup(
    name=package_name,
    version="0.3.2",
    packages=find_packages(exclude=["test"]),
    data_files=[
        (
            "share/ament_index/resource_index/packages",
            ["resource/" + package_name],
        ),
        ("share/" + package_name, ["package.xml"]),
        ("share/" + package_name + "/config", ["config/fan_params.yaml"]),
        ("share/" + package_name + "/launch", ["launch/fans.launch.py"]),
    ],
    install_requires=["setuptools"],
    zip_safe=True,
    maintainer="LeonEleven",
    maintainer_email="elevenlianm@foxmail.com",
    description="ROS 2 dual ducted-fan ESC controller for WindArmor.",
    license="Apache-2.0",
    tests_require=["pytest"],
    entry_points={
        "console_scripts": [
            "fan_controller = windarmor_fan_controller.fan_node:main",
            "fan_command_manager = windarmor_fan_controller.fan_command_manager:main",
            "fan_keyboard = windarmor_fan_controller.fan_keyboard:main",
        ],
    },
)
