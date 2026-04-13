from setuptools import setup

package_name = 'hydroponics_dosing'

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
    maintainer='Autoponics',
    maintainer_email='autoponics@example.com',
    description='V0.1 explicit-chemistry auto-dosing node.',
    license='MIT',
    tests_require=['pytest'],
    entry_points={
        'console_scripts': [
            'dosing_node = hydroponics_dosing.dosing_node:main',
        ],
    },
)
