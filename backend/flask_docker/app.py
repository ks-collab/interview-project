from flask import Flask
from flask_cors import CORS

from flask_docker.api import api


def create_app():
    app = Flask(__name__, instance_relative_config=True,
                static_folder='static')
    app.config.from_pyfile("config.py", silent=False)
    app.register_blueprint(api)
    CORS(app)
    return app
