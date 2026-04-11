from setuptools import setup

package_name = 'hydroponics_water'

setup(
    name=package_name,
    version='0.1.0',
    packages=[package_name],
    data_files=[
        ('share/ament_index/resource_index/packages', ['resource/' + package_name]),
        ('share/' + package_name, ['package.xml']),
    ],
    install_requires=['setuptools'],
    zip_safe=True,
    maintainer='AIdroponics',
    maintainer_email='aidroponics@example.com',
    description='V0.1 water level node.',
    license='MIT',
    tests_require=['pytest'],
    entry_points={
        'console_scripts': [
            'water_level_node = hydroponics_water.water_level_node:main',
        ],
    },
)
