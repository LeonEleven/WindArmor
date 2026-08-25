from glob import glob

from setuptools import find_packages, setup


package_name = "windarmor_flight_control"

setup(
    name=package_name,
    version="0.4.0",
    packages=find_packages(exclude=["test"]),
    data_files=[
        (
            "share/ament_index/resource_index/packages",
            ["resource/" + package_name],
        ),
        ("share/" + package_name, ["package.xml"]),
        ("share/" + package_name + "/config", glob("config/*.yaml")),
        ("share/" + package_name + "/launch", glob("launch/*.launch.py")),
    ],
    install_requires=["setuptools"],
    zip_safe=True,
    maintainer="LeonEleven",
    maintainer_email="elevenlianm@foxmail.com",
    description=(
        "Flight-control API, algorithms, authority runtime, and actuator "
        "adapters for WindArmor."
    ),
    license="Apache-2.0",
    tests_require=["pytest"],
    entry_points={
        "console_scripts": [
            "flight_control_runtime_node = "
            "windarmor_flight_control.runtime.node:main",
        ],
    },
)
