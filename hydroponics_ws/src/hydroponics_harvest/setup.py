from setuptools import setup

package_name = 'hydroponics_harvest'

setup(
    name=package_name,
    version='1.0.0',
    packages=[package_name],
    data_files=[
        ('share/ament_index/resource_index/packages', ['resource/' + package_name]),
        ('share/' + package_name, ['package.xml']),
    ],
    install_requires=['setuptools'],
    zip_safe=True,
    maintainer='Claudroponics Dev',
    maintainer_email='developer@claudroponics.local',
    description='Per-plant harvest manager with cut-and-regrow and end-of-life cycle tracking',
    license='MIT',
    entry_points={
        'console_scripts': [
            'harvest_manager = hydroponics_harvest.harvest_manager:main',
        ],
    },
)
