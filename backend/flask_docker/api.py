from flask import Blueprint, g, jsonify, current_app, request
from flask_docker.db import Database
import openai

api = Blueprint('api', __name__)

def get_db():
    if "db" not in g:
        g.db = Database("gpt_project")
    return g.db


@api.route('/conversations', methods=['GET'])
def get_conversations():
    response = get_db().fetch("SELECT * FROM conversations")
    return jsonify(response)


@api.route('/conversation', methods=['POST'])
def create_conversation():
    response = openai.ChatCompletion.create(
        model="gpt-3.5-turbo",
        messages=[
            {"role": "system", "content": "You are a helpful assistant."},
            {"role": "user", "content": "Who won the world series in 2020?"},
            {"role": "assistant",
                "content": "The Los Angeles Dodgers won the World Series in 2020."},
            {"role": "user", "content": "Where was it played?"}
        ]
    )

    return jsonify(response)


@api.route('/conversation/<id>', methods=['DELETE'])
def delete_conversation(id):
    return {"id": 0}


@api.route('/conversation/<id>/messages', methods=['GET'])
def get_messages(id):
    return jsonify([])


@api.route('/conversation/<conversation_id>/message', methods=['POST'])
def create_message(conversation_id):
    return jsonify({"id": 0, "query": "Hello", "response": "world"})
