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
    ],
    install_requires=["setuptools"],
    zip_safe=True,
    maintainer="h-goal",
    maintainer_email="h-goal@todo.todo",
    description="Hardware-independent flight-control API and algorithms for WindArmor.",
    license="Apache-2.0",
    tests_require=["pytest"],
)
