from flask import Flask, request
from .config import Config
from logging import getLogger
from logging.config import fileConfig
from flask_admin.contrib.sqla import ModelView
from sqlalchemy.orm import configure_mappers
from .extensions import db, admin
from .models import *
from .index import index

#Get logging configuration
fileConfig("logging.config")
logger=getLogger(__name__)

def create_app():
    app = Flask(__name__)
    #Configuration from object, file config.py
    app.config.from_object(Config)

    #Initialize db
    db.init_app(app)
    app.register_blueprint(index, url_prefix='/')
    admin.name='Certificate DNS record Management'
    admin.init_app(app)
    configure_mappers()
    admin.add_view(CertDNSView(CertDNS,db.session))
    logger.debug("Application started")
    return app

def init_db():
    app = Flask(__name__)
    app.config.from_object(Config)
    db.init_app(app)
    app.app_context().push()
    db.create_all()