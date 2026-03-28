from setuptools import setup

package_name = 'hydroponics_mocks'

setup(
    name=package_name,
    version='0.1.0',
    packages=[package_name],
    data_files=[
        ('share/ament_index/resource_index/packages',
         ['resource/' + package_name]),
        ('share/' + package_name, ['package.xml']),
    ],
    install_requires=['setuptools'],
    zip_safe=True,
    maintainer='Claudroponics Team',
    maintainer_email='claudroponics@example.com',
    description='Mock hardware nodes for simulation testing without real hardware.',
    license='MIT',
    tests_require=['pytest'],
    entry_points={
        'console_scripts': [
            'mock_esp32 = hydroponics_mocks.mock_esp32:main',
            'mock_cameras = hydroponics_mocks.mock_cameras:main',
        ],
    },
)
