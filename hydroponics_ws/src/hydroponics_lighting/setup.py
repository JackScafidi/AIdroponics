from setuptools import setup

package_name = 'hydroponics_lighting'

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
    description='Lighting controller for grow panel and inspection LEDs with schedule management',
    license='MIT',
    entry_points={
        'console_scripts': [
            'light_controller = hydroponics_lighting.light_controller:main',
        ],
    },
)
