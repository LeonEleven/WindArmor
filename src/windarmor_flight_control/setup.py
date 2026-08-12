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
    maintainer="h-goal",
    maintainer_email="h-goal@todo.todo",
    description=(
        "Flight-control API, algorithms, and no-takeover authority runtime "
        "for WindArmor."
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
