from flask import jsonify


def api_error(code, message, status, **extra):
    response = jsonify({"error": code, "message": message, **extra})
    response.status_code = status
    return response
