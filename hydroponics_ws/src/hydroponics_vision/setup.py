from setuptools import setup

package_name = 'hydroponics_vision'

setup(
    name=package_name,
    version='1.0.0',
    packages=[package_name],
    data_files=[
        ('share/ament_index/resource_index/packages', ['resource/' + package_name]),
        ('share/' + package_name, ['package.xml']),
        ('share/' + package_name + '/config', ['config/vision_params.yaml']),
    ],
    install_requires=['setuptools'],
    zip_safe=True,
    maintainer='Claudroponics Dev',
    maintainer_email='developer@claudroponics.local',
    description='Plant inspection vision pipeline: dual-camera capture, YOLOv8 segmentation, health classification, and growth measurement',
    license='MIT',
    entry_points={
        'console_scripts': [
            'vision_node = hydroponics_vision.vision_node:main',
        ],
    },
)
