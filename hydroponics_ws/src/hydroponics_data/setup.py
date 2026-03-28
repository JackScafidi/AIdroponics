from setuptools import setup

package_name = 'hydroponics_data'

setup(
    name=package_name,
    version='1.0.0',
    packages=[package_name],
    data_files=[
        ('share/ament_index/resource_index/packages', ['resource/' + package_name]),
        ('share/' + package_name, ['package.xml']),
        ('share/' + package_name + '/config', ['config/economics.yaml']),
        ('share/' + package_name + '/migrations', ['migrations/001_initial_schema.sql']),
    ],
    install_requires=['setuptools'],
    zip_safe=True,
    maintainer='Claudroponics Dev',
    maintainer_email='developer@claudroponics.local',
    description='Data pipeline, SQLite storage, growth analytics, and yield economics',
    license='MIT',
    entry_points={
        'console_scripts': [
            'data_pipeline = hydroponics_data.data_pipeline:main',
        ],
    },
)
