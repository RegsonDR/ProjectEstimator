from flask import Blueprint, jsonify, session
from routes.ajax.utils import *
from datetime import datetime, timedelta
from routes.authenticated.views import login_required
import pytz

ajax = Blueprint('ajax', __name__, url_prefix='/ajax', template_folder='templates')


@ajax.route('/ResetPassword', methods=['POST'])
def reset_password_email():
    email = request.form.get('reset_email')
    return jsonify({"Request": send_reset_email(email)})


@ajax.route('/Project/<int:project_id>/Chat', methods=['POST'])
@login_required()
def chat_message(project_id, **kwargs):
    try:
        username = request.form.get('username')
        message = base64.b64encode(request.form.get('message').decode('utf-8'))
        message_time = datetime.now() + timedelta(hours=1)
        email = request.form.get('email')
        role = request.form.get('role')
        log_message(project_id, username, message, message_time, email, role)
        push_chat_message(project_id, username, message, message_time, email, role)
        return jsonify({'Request': True})
    except:
        return jsonify({'Request': False})


@ajax.route('/Task/<int:task_id>/Save', methods=['POST'])
@login_required()
def save_task(task_id, **kwargs):
    try:
        log_developer = session.get("Email")
        log_minutes = int(request.form.get('minutes'))
        log_comments = request.form.get('comments')
        save_log(task_id, log_developer, log_minutes, log_comments)
        return jsonify({'Request': True})
    except:
        return jsonify({'Request': False})


@ajax.route('/Workspace/<int:wks_id>/User/Status', methods=['POST'])
@login_required('admin')
def switch_account_status(wks_id, **kwargs):
    try:
        email = request.form.get('email')
        account_switch(kwargs['user'].wks_data.key, email)
        return jsonify({'Request': True})
    except:
        return jsonify({'Request': False})


@ajax.route('/Workspace/<int:wks_id>/User/Role', methods=['POST'])
@login_required('admin')
def change_role(wks_id, **kwargs):
    try:
        email = request.form.get('email')
        new_role = request.form.get('role')
        change_user_role(kwargs['user'].wks_data.key, email, new_role)
        return jsonify({'Request': True})
    except:
        return jsonify({'Request': False})

@ajax.route('/Workspace/<int:wks_id>/Skill', methods=['POST'])
@login_required({'admin','manager','developer'})
def alter_skill(wks_id, **kwargs):
    try:
        skill_id = int(request.form.get('skill_id'))
        rating = request.form.get('rating')
        update_user_skill(skill_id,rating)
        return jsonify({'Request': True})
    except:
        return jsonify({'Request': False})