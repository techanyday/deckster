from setuptools import setup, find_packages

setup(
    name="windsurf",
    version="0.1",
    packages=find_packages(include=['utils', 'utils.*']),
    install_requires=[
        'flask',
        'flask-sqlalchemy',
        'flask-login',
        'flask-migrate',
        'python-dotenv',
        'requests',
        'openai',
        'python-pptx',
        'Pillow',
        'gunicorn',
        'flask_cors',
        'werkzeug',
        'psycopg2-binary',
    ],
)
