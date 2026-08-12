from glob import glob

from setuptools import setup

package_name = "windarmor_bringup"

setup(
    name=package_name,
    version="0.3.2",
    packages=[],
    data_files=[
        (
            "share/ament_index/resource_index/packages",
            ["resource/" + package_name],
        ),
        ("share/" + package_name, ["package.xml"]),
        ("share/" + package_name + "/launch", glob("launch/*.launch.py")),
    ],
    install_requires=["setuptools"],
    zip_safe=True,
    maintainer="h-goal",
    maintainer_email="h-goal@todo.todo",
    description="Unified ROS 2 bringup for the WindArmor robot.",
    license="Apache-2.0",
    tests_require=["pytest"],
)
