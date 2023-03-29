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
    newQuery = request.json["query"]
    insertId = -1
    aiResponse = ""
    aiStopReason = ""
    formattedMessages = []

    previousMessages = get_db().fetch(
        "SELECT * FROM messages WHERE conversation_id = %s ORDER BY id", conversation_id)

    formattedMessages = [
        {"role": "system", "content": "You are a helpful assistant."}]

    for item in previousMessages:
        formattedMessages.append({
            "role": "user", "content": item["query"]
        })
        formattedMessages.append({
            "role": "assistant", "content": item["response"]
        })

    formattedMessages.append({
        "role": "user", "content": newQuery
    })

    # Send openai completion request using request body
    response = openai.ChatCompletion.create(
        model="gpt-3.5-turbo",
        messages=formattedMessages,
        max_tokens=1000,
        temperature=0.7,
    )

    aiStopReason = response['choices'][0]['finish_reason']
    aiResponse = response['choices'][0]['message']['content']

    if aiStopReason != "stop":
        match aiStopReason:
            case "length":
                aiResponse = "I'm sorry, Your tokens have been exceeded either for this message or for your account."
            case "content_filter":
                aiResponse = "I'm sorry, I'm not allowed to talk about that."
            case "null":
                aiResponse = "I'm sorry, I'm still thinking about your question."
                # TODO: do something if api still working on response
    else:
        # Insert new message into database
        insertId = get_db().insert("messages", {
            "conversation_id": conversation_id, "query": newQuery, "response": aiResponse})

    # Return error if message is not created
    if insertId == -1:
        return {"error": "Message not created", "reason": aiResponse}, 400
    else:
        return jsonify({"id": conversation_id, "query": newQuery, "response": aiResponse})
