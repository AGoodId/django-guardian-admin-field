#!/usr/bin/env python
from distutils.core import setup

setup(name='django-guardian-admin-field',
      version='0.1',
      description='Django application that extends guardian with a new field for assigning permissions inline',
      author='AGoodId',
      author_email='teknik@agoodid.se',
      url='http://github.com/AGoodId/django-guardian-admin-field/',
      packages=['guardian_admin_field'],
      license='BSD',
      include_package_data = False,
      zip_safe = False,
      classifiers = [
          'Intended Audience :: Developers',
          'License :: OSI Approved :: BSD License',
          'Programming Language :: Python',
          'Operating System :: OS Independent',
          'Environment :: Web Environment',
          'Framework :: Django',
      ],
)
