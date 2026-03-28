from setuptools import setup

package_name = 'hydroponics_nutrients'

setup(
    name=package_name,
    version='1.0.0',
    packages=[package_name],
    data_files=[
        ('share/ament_index/resource_index/packages', ['resource/' + package_name]),
        ('share/' + package_name, ['package.xml']),
        ('share/' + package_name + '/config', ['config/pid_params.yaml']),
    ],
    install_requires=['setuptools'],
    zip_safe=True,
    maintainer='Claudroponics Dev',
    maintainer_email='developer@claudroponics.local',
    description='PID nutrient controller for pH and EC management',
    license='MIT',
    entry_points={
        'console_scripts': [
            'nutrient_controller = hydroponics_nutrients.nutrient_controller:main',
        ],
    },
)
