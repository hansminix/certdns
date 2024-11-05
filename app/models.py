from .extensions import db
from flask_sqlalchemy import SQLAlchemy
from flask_admin.contrib.sqla import ModelView
from .config import Config
from sqlalchemy.sql import func

class CertDNS(db.Model):
    __table_name__= 'cert_dns'
    id=db.Column(db.Integer, primary_key=True)
    certificatename = db.Column(db.String(255))
    hexcode= db.Column(db.String(255))
    date_set = db.Column(db.DateTime)
    date_reset = db.Column(db.DateTime)
    cname = db.Column(db.String(255))
    errors = db.Column(db.String(255))
    def __repr__(self):
        return self.certificatename 

class CertDNSView(ModelView):
    create_template = 'certdns_create.html'
    list_template = 'certdns_list.html'
    can_delete = False
    can_edit = False
    can_export = True
    column_searchable_list = ['certificatename']
    form_columns = ['certificatename', 'hexcode']

