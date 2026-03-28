from setuptools import setup

package_name = 'hydroponics_mqtt'

setup(
    name=package_name,
    version='1.0.0',
    packages=[package_name],
    data_files=[
        ('share/ament_index/resource_index/packages', ['resource/' + package_name]),
        ('share/' + package_name, ['package.xml']),
        ('share/' + package_name + '/config', ['config/mqtt_config.yaml']),
    ],
    install_requires=['setuptools', 'paho-mqtt'],
    zip_safe=True,
    maintainer='Claudroponics Dev',
    maintainer_email='developer@claudroponics.local',
    description='MQTT bridge to HiveMQ Cloud with Home Assistant discovery support',
    license='MIT',
    entry_points={
        'console_scripts': [
            'mqtt_bridge = hydroponics_mqtt.mqtt_bridge:main',
        ],
    },
)
