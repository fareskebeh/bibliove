from db.extensions import db
from auth.models import User
from flask import session, jsonify, request, render_template, flash, redirect, make_response
from .models import ApiKey, ApiUsage
from payments.models import FREE_PLAN_ID
from hashlib import sha256
import secrets
import nemony as nm

def key_routes_init(app):
    
    @app.route("/count/<int:user_id>")
    def count_keys_for_user(user_id):
        user = User.query.get(user_id)
        if user is None:
            return {"error": "User not found"}, 404
        return str(user.key_count)
    
    @app.route("/keys/create", methods=["POST", "GET"])
    def create_key():
        is_authenticated=True if session.get("email") else False 
        if not is_authenticated:
            return make_response({"message": "Unable to create key, requires authentication"}, 401)
        user = User.query.filter(User.email==session.get("email")).first()
        if not user:
            return redirect("/")
        if user.plan_id==FREE_PLAN_ID and user.key_count>=1:
            return make_response({"message": "Only one key is available for Free plan, Upgrade to a paid plan to create more."}, 402)
        raw=secrets.token_urlsafe(32)
        key = ApiKey(
            key_hash= sha256(raw.encode()).hexdigest(),
            name=nm.encode(raw, sep='-'),
            user_id=user.id,
        )
        db.session.add(key)
        db.session.commit()
        return render_template('create_key.jinja', name=key.name if key else '', raw=raw, is_authenticated=is_authenticated)
    
    @app.route('/keys/delete', methods=["POST"])
    def delete_key():
        is_authenticated = True if session.get("email") else False 
        if not is_authenticated:
            return jsonify({"message": "Unauthorized to perform this operation"}), 401
        
        try:
            data = request.get_json()
            if not data:
                return jsonify({"message": "Invalid request data"}), 400
            key_id = data.get("key_id")
            if not key_id:
                return jsonify({"message": "Key ID is required"}), 400
            user_email = session.get("email")
            user = User.query.filter_by(email=user_email).first()
            if not user:
                return jsonify({"message": "User not found"}), 404
            key = ApiKey.query.filter_by(id=key_id, user_id=user.id).first()
            if not key:
                return jsonify({"message": "Key not found or you don't have permission to delete it"}), 404
            ApiUsage.query.filter_by(key_id=key.id).delete()
            db.session.delete(key)
            db.session.commit()
            return jsonify({
                "message": "Key deleted successfully",
                "key_id": key_id,
                "success": True
            }), 200
        except Exception as e:
            db.session.rollback()
            return jsonify({"message": f"Error deleting key: {str(e)}"}), 500