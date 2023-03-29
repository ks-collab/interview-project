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
    # Get name from request body
    name = request.json["name"]
    # Return error if name is not provided
    if name == "":
        return {"error": "Name is required"}, 400
    response = get_db().insert("conversations", {"name": name})
    return jsonify({"id": response, "name": name})


@api.route('/conversation/<id>', methods=['DELETE'])
def delete_conversation(id: int):
    response = get_db().execute("DELETE FROM conversations WHERE id = %s", id)
    # Return error if conversation is not found
    return {"id": id} if (response and response > 0) else {"error": "Conversation not found"}, 404


@api.route('/conversation/<id>/messages', methods=['GET'])
def get_messages(id: int):
    # Get messages from database for provided conversation id
    response = get_db().fetch(
        "SELECT * FROM messages WHERE conversation_id = %s ORDER BY id", id)
    return jsonify(response)


@api.route('/conversation/<conversation_id>/message', methods=['POST'])
def create_message(conversation_id):
    return jsonify({"id": 0, "query": "Hello", "response": "world"})
