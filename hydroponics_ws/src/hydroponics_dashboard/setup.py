from setuptools import setup, find_packages

package_name = 'hydroponics_dashboard'

setup(
    name=package_name,
    version='1.0.0',
    packages=find_packages(exclude=['test']),
    data_files=[
        ('share/ament_index/resource_index/packages', ['resource/' + package_name]),
        ('share/' + package_name, ['package.xml']),
    ],
    install_requires=['setuptools', 'fastapi', 'uvicorn', 'websockets'],
    zip_safe=True,
    maintainer='Claudroponics Dev',
    maintainer_email='developer@claudroponics.local',
    description='FastAPI + React web dashboard for the Claudroponics system',
    license='MIT',
    entry_points={
        'console_scripts': [
            'dashboard = hydroponics_dashboard.app:main',
        ],
    },
)
