import os
from glob import glob

from setuptools import find_packages, setup

package_name = "kiis_testbed"

setup(
    name=package_name,
    version="0.1.0",
    packages=find_packages(exclude=["test"]),
    data_files=[
        ("share/ament_index/resource_index/packages", [os.path.join("resource", package_name)]),
        (os.path.join("share", package_name), ["package.xml"]),
        (os.path.join("share", package_name, "launch"), glob("launch/*.launch.py")),
    ],
    install_requires=["setuptools"],
    zip_safe=True,
    maintainer="Yulee3542",
    maintainer_email="yulee3542@gmail.com",
    description="KIIS digital twin / control panel testbed (ROS 2)",
    license="MIT",
    entry_points={
        "console_scripts": [
            "arduino_node = kiis_testbed.nodes.arduino_node:ros_main",
            "teleop_node = kiis_testbed.nodes.teleop_node:main",
            "experiment_node = kiis_testbed.nodes.experiment_node:main",
            "recorder_node = kiis_testbed.nodes.recorder_node:main",
            "monitor_node = kiis_testbed.nodes.monitor_node:main",
            "web_monitor_node = kiis_testbed.nodes.web_monitor_node:main",
        ],
    },
)
