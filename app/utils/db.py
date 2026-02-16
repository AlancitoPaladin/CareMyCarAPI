from pymongo import MongoClient


def init_db(app):
    client = MongoClient(app.config["MONGO_URI"])
    db = client[app.config["MONGO_DB_NAME"]]

    app.extensions["mongo_client"] = client
    app.extensions["mongo_db"] = db



def get_db():
    from flask import current_app

    return current_app.extensions["mongo_db"]
