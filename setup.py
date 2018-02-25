#!/usr/bin/env python
# -*- coding: utf-8 -*-

from setuptools import setup, find_packages

setup(
    name='webhook-router',
    version='0.1a1',
    description='Test project for listening to webhooks and routing to '
                'websockets.',
    url='https://github.com/hjalves/webhook-router',
    author='Humberto Alves',
    author_email='hjalves@live.com',
    license='MIT',
    classifiers=[
        'Development Status :: 2 - Pre-Alpha',
        'Environment :: Console',
        'Intended Audience :: Developers',
        'Operating System :: POSIX :: Linux',
        'Programming Language :: Python :: 3',
        'Programming Language :: Python :: 3.6',
    ],
    keywords=['webhook', 'websocket'],
    packages=find_packages(),
    install_requires=[
        'aiohttp',
        'aiohttp-cors',
        'colorlog',
        'toml',
    ],
    entry_points={
        'console_scripts': [
            'webhook-router = webhook_router.app:main',
        ]
    },
    #include_package_data=True,
    zip_safe=False,
)
