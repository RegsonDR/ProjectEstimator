# coding=utf-8
import gc
import time
from functools import wraps

from app_statics import SIDEBAR
from flask import Blueprint, session, abort, redirect
from forms import *
from models import *
from routes.authenticated.utils import *

authenticated = Blueprint('authenticated', __name__, template_folder='templates')


class DictMissKey(dict):
    # Create key if doesn't exist
    def __missing__(self, key):
        value = self[key] = type(self)()
        return value


class LoggedUser:
    def __init__(self, user_data, user_email, wks_data=None, projects_data=None, task_data=None, access_data=None):
        self.user_data = user_data
        self.user_key = user_data.key
        self.user_email = user_email

        if wks_data:
            self.wks_data = wks_data
            self.wks_key = wks_data.key
        if access_data:
            self.access_data = access_data
            self.access_key = access_data.key
        if projects_data:
            self.projects_data = projects_data
            self.projects_key = projects_data.key
        if task_data:
            self.task_data = task_data
            self.task_key = task_data.key

    def get_user_data(self):
        return self.user_data

    def get_wks_data(self):
        return self.wks_data

    def get_project_data(self):
        return self.projects_data

    def get_task_data(self):
        return self.task_data

    def get_role(self):
        return self.access_data.role

    def get_permitted_workspaces(self):
        return get_workspaces(self.user_email)

    def get_tasks(self):
        return get_tasks(self.projects_key)

    def get_invites(self):
        return get_invites(self.user_email)

    def get_projects(self, project_status):
        return get_projects(self.wks_key, self.get_role(), self.user_email, project_status)

    # This is used to get number on any task, not the one the page is on.
    def get_open_task_number(self, project_key):
        return get_open_task_number(project_key)

    def get_total_task_number(self, project_key):
        return get_total_task_number(project_key)

    def get_invites_number(self):
        return get_invites_number(self.user_email)

    def get_all_users(self):
        return get_all_users(self.wks_key)


# Permissions decorator, used and re-checked on every page load, first check login, account active, then workspace + role.
def login_required(roles=None):
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            if session.get('Logged_In', False):
                user_data = get_user_data_by_email(session.get('Email'))
                #
                # Check if account is active
                if not user_data.is_active:
                    session.clear()
                    gc.collect()
                    flash('Your account is no longer active.', 'danger')
                    return redirect(url_for('unauthenticated.login_page'))
                #
                wks_data = None
                projects_data = None
                task_data = None
                access_data = None
                if 'wks_id' in kwargs.keys():
                    if kwargs['wks_id'] == 0:
                        return redirect(url_for('authenticated.my_workspaces_page'))
                    wks_data = get_wks_data_by_id(kwargs['wks_id'])
                    if not wks_data:
                        abort(403)
                    access_data = check_access(wks_data.key, session.get('Email'))
                    # Check Permissions for workspace
                    if not access_data or access_data.role not in roles:
                        abort(403)
                    # Check Permission for project
                    if 'project_id' in kwargs.keys():
                        projects_data = get_project_data_by_id(kwargs['project_id'])
                        if not projects_data:
                            abort(403)
                        if not check_project_access(projects_data, session.get('Email'), access_data.role):
                            abort(403)
                    if 'task_id' in kwargs.keys():
                        task_data = get_task_data_by_id(kwargs['task_id'])
                        if not task_data:
                            abort(404)

                kwargs['user'] = LoggedUser(user_data, session.get('Email'), wks_data, projects_data, task_data,
                                            access_data)

            elif request.args.get("email") is not None:
                flash('Please login or sign up to access the requested page.', 'danger')
                return redirect(url_for('unauthenticated.register_page', email=request.args.get("email")))
            else:
                flash('Please login to access the requested page.', 'danger')
                abort(401)
            return func(*args, **kwargs)

        return wrapper

    return decorator


@authenticated.route('/Workspace/<int:wks_id>/SkillsMatrix', methods=['GET', 'POST'])
@login_required({'admin', 'manager'})
def skills_matrix_page(wks_id, **kwargs):
    skill_data = [(skill.skill_name, skill.key.id()) for skill in
                  SkillData.query(SkillData.Wks == kwargs['user'].wks_key).fetch(
                      projection=[SkillData.skill_name]) if skill.usage() > 0]

    users_data = [(user.get_name(), user.get_user_key()) for user in
                  UserProfile.query(
                      UserProfile.Wks == kwargs['user'].wks_key,
                      UserProfile.invitation_accepted == True,
                      UserProfile.disabled == False).fetch()
                  ]

    user_skill = DictMissKey()
    for user in users_data:
        for skill in skill_data:
            test = UserSkill.query(UserSkill.Wks == kwargs['user'].wks_key,
                                   UserSkill.User == user[1],
                                   UserSkill.skill_id == skill[1]
                                   ).get()
            if test:
                user_skill[user[0]][skill[0]] = test.skill_rating
            else:
                user_skill[user[0]][skill[0]] = 0

    for user, skill in user_skill.iteritems():
        print user, '-->', skill

    return render_template('authenticated/html/skills_matrix_page.html',
                           skill_data=skill_data,
                           user_skill=user_skill,
                           user_data=kwargs['user'],
                           wks_data=kwargs['user'].get_wks_data(),
                           SIDEBAR=SIDEBAR)

@authenticated.route('/Workspace/<int:wks_id>/NewProject', methods=['GET', 'POST'])
@login_required({'admin', 'manager'})
def new_project_page(wks_id, **kwargs):
    new_project = NewProject()

    if request.method == 'POST':
        if new_project.validate_on_submit():
            project_data = DictMissKey()
            taskid_list = []
            # Get all data
            for key in request.form.keys():
                # Extract ID
                component = [p[:-1] for p in key.split('[')][1:]
                if len(component) is 0:
                    project_data[key] = request.form[key]
                else:
                    task_id = component[0]
                    element = component[1]

                    if task_id not in taskid_list:
                        taskid_list.extend(task_id)
                    dic_position = taskid_list.index(task_id)

                    if element == "Skills" or element == "Developers":
                        project_data['Task'][dic_position][element] = request.form.getlist(
                            'Task[' + task_id + '][' + element + ']')
                    else:
                        project_data['Task'][dic_position][element] = request.form[
                            'Task[' + task_id + '][' + element + ']']
            project_id = create_project(kwargs['user'].wks_key, kwargs['user'].user_email, project_data)
            time.sleep(1)
            return redirect(url_for('authenticated.view_project_page', wks_id=wks_id, project_id=project_id))

    return render_template('authenticated/html/new_project_page.html',
                           form=new_project,
                           user_data=kwargs['user'],
                           wks_data=kwargs['user'].get_wks_data(),
                           SIDEBAR=SIDEBAR)



@authenticated.route('/Workspace/<int:wks_id>/ViewSkills/<int:user_id>', methods=['GET', 'POST'])
@authenticated.route('/Workspace/<int:wks_id>/MySkills', methods=['GET', 'POST'])
@login_required({'admin', 'manager'})
def my_skills_page(wks_id, user_id=None, **kwargs):
    if user_id and kwargs['user'].get_role() == "admin":
        look_up_key = AccountDetails.get_by_id(user_id).key
    else:
        look_up_key = kwargs['user'].user_key

    new_skill = AddSkill()
    new_skill.skill_name.choices = [(skill.key.id(), skill.skill_name) for skill in
                                    SkillData.query(SkillData.Wks == kwargs['user'].wks_key
                                                    ).fetch()]

    if request.method == "POST":
        create_skill(new_skill.skill_name.data, kwargs['user'].wks_key, look_up_key)
        time.sleep(1)
        return redirect(url_for('authenticated.my_skills_page', wks_id=wks_id,user_id=user_id ))

    current_skills = UserSkill.query(UserSkill.Wks == kwargs['user'].wks_key, UserSkill.User == look_up_key).fetch()

    return render_template('authenticated/html/my_skills_page.html',
                           user_data=kwargs['user'],
                           wks_data=kwargs['user'].get_wks_data(),
                           current_skills=current_skills,
                           form=new_skill,
                           SIDEBAR=SIDEBAR)


@authenticated.route('/Workspace/<int:wks_id>/Project/<int:project_id>/Task/<int:task_id>', methods=['GET', 'POST'])
@login_required({'admin', 'manager'})
def view_task_page(wks_id, project_id, task_id, **kwargs):
    log_form = LogTask()
    task_form = Task()
    task_form.task_developers.choices = [(str(user.get_id()), user.get_name()) for user in
                                         UserProfile.query(UserProfile.Wks == kwargs['user'].wks_key,
                                                           UserProfile.invitation_accepted == True).fetch(
                                             projection=[UserProfile.UserEmail])]
    developer_choices = [(str(user.get_id()), user.get_name(), user.disabled) for user in
                         UserProfile.query(UserProfile.Wks == kwargs['user'].wks_key,
                                           UserProfile.invitation_accepted == True).fetch(
                             projection=[UserProfile.UserEmail, UserProfile.disabled])]

    task_data = kwargs['user'].get_task_data()

    if request.method == "POST" and task_form.validate_on_submit():
        task_data.task_name = task_form.task_name.data
        task_data.task_aminutes = task_form.task_aminutes.data
        task_data.task_status = task_form.task_status.data
        task_data.task_description = task_form.task_description.data
        task_data.task_skills = map(int, task_form.task_skills.data)
        task_data.task_developers = map(int, task_form.task_developers.data)
        if task_data.put():
            flash('Task details updated!', 'success')
            return redirect(
                url_for('authenticated.view_task_page', wks_id=wks_id, project_id=project_id, task_id=task_id))
        flash('Error occurred, please try again!', 'danger')

    task_form.task_name.data = task_data.task_name
    task_form.task_aminutes.data = task_data.task_aminutes
    task_form.task_status.data = task_data.task_status
    task_form.task_description.data = task_data.task_description
    task_form.task_skills.data = map(str, task_data.task_skills)
    task_form.task_developers.data = map(str, task_data.task_developers)

    return render_template('authenticated/html/view_task_page.html',
                           user_data=kwargs['user'],
                           form=task_form,
                           task_data=task_data,
                           developer_choices=developer_choices,
                           log_form=log_form,
                           wks_data=kwargs['user'].get_wks_data(),
                           SIDEBAR=SIDEBAR)


@authenticated.route('/Workspace/<int:wks_id>/Project/<int:project_id>', methods=['GET', 'POST'])
@login_required({'admin', 'manager'})
def view_project_page(wks_id, project_id, **kwargs):
    project_form = Project()
    project_form.project_manager.choices = [(user.UserEmail, user.get_name()) for user in
                                            UserProfile.query(UserProfile.role != "developer",
                                                              UserProfile.Wks == kwargs['user'].wks_key,
                                                              UserProfile.invitation_accepted == True).fetch(
                                                projection=[UserProfile.UserEmail])]

    manager_data = [(user.UserEmail, user.get_name(), user.disabled) for user in
                    UserProfile.query(UserProfile.role != "developer", UserProfile.Wks == kwargs['user'].wks_key,
                                      UserProfile.invitation_accepted == True).fetch(
                        projection=[UserProfile.UserEmail, UserProfile.disabled])]

    project_data = kwargs['user'].get_project_data()
    if request.method == "POST" and project_form.validate_on_submit():
        project_data.project_name = project_form.project_name.data
        project_data.project_deadline = project_form.project_deadline.data
        project_data.project_description = project_form.project_description.data
        project_data.project_manager = project_form.project_manager.data
        project_data.project_status = project_form.project_status.data
        project_data.project_stage = project_form.project_stage.data
        if project_data.put():
            flash('Project details updated!', 'success')
            return redirect(url_for('authenticated.view_project_page', wks_id=wks_id, project_id=project_id))
        flash('Error occurred, please try again!', 'danger')

    project_form.project_name.data = project_data.project_name
    project_form.project_deadline.data = project_data.project_deadline
    project_form.project_description.data = project_data.project_description
    project_form.project_manager.data = project_data.project_manager
    project_form.project_status.data = project_data.project_status
    project_form.project_stage.data = project_data.project_stage

    return render_template('authenticated/html/view_project_page.html',
                           tasks=kwargs['user'].get_tasks(),
                           user_data=kwargs['user'],
                           wks_data=kwargs['user'].get_wks_data(),
                           form=project_form,
                           project_data=project_data,
                           manager_data=manager_data,
                           SIDEBAR=SIDEBAR)


@authenticated.route('/Workspace/<int:wks_id>/Project/<int:project_id>/Chat/', methods=['GET', 'POST'])
@login_required({'admin', 'manager'})
def project_chat(wks_id, project_id, **kwargs):
    return render_template('authenticated/html/project_chat.html',
                           user_data=kwargs['user'],
                           wks_data=kwargs['user'].get_wks_data(),
                           old_messages=get_chat_messages(project_id),
                           project_data=kwargs['user'].get_project_data(),
                           SIDEBAR=SIDEBAR)


@authenticated.route('/MyInvites', methods=['GET', 'POST'])
@login_required()
def my_invites(**kwargs):
    if not kwargs['user'].get_invites_number():
        flash("You have no pending invites!", "danger")
        return redirect(url_for('authenticated.my_workspaces_page'))
    return render_template('authenticated/html/my_invites.html',
                           user_data=kwargs['user'])


@authenticated.route('/')
@authenticated.route('/Workspaces', methods=['GET', 'POST'])
@login_required()
def my_workspaces_page(**kwargs):
    new_wks = NewWorkspace()
    if request.method == 'POST':
        if new_wks.validate_on_submit():
            wks_id = create_wks(new_wks.workspace_name.data, kwargs['user'].user_email)
            if wks_id:
                time.sleep(1)
                return redirect(url_for('authenticated.workspace_homepage', wks_id=wks_id.key.id()))

    return render_template('authenticated/html/my_workspaces_page.html',
                           form=new_wks,
                           user_data=kwargs['user'])


@authenticated.route('/MyProfile', methods=['GET', 'POST'])
@login_required()
def my_profile_page(**kwargs):
    user_profile = ProfileUser()

    user_data = kwargs['user'].get_user_data()
    if request.method == "POST" and user_profile.validate_on_submit():
        if user_profile.first_name.data is not user_data.first_name:
            user_data.first_name = user_profile.first_name.data
        if user_profile.last_name.data is not user_data.last_name:
            user_data.last_name = user_profile.last_name.data
        if user_profile.email.data is not user_data.email:
            user_data.change_email(user_profile.email.data)
            session['Email'] = user_profile.email.data
        if user_profile.mobile_number.data is not user_data.mobile_number:
            user_data.mobile_number = user_profile.mobile_number.data
        if user_data.put():
            flash('Profile updated!', 'success')
            return redirect(url_for('authenticated.my_profile_page'))
        flash('Error occurred, please try again!', 'danger')

    user_profile.first_name.data = user_data.first_name
    user_profile.last_name.data = user_data.last_name
    user_profile.email.data = user_data.email
    user_profile.mobile_number.data = user_data.mobile_number

    return render_template('authenticated/html/my_profile_page.html',
                           form=user_profile,
                           user_data=kwargs['user'])


@authenticated.route('/Workspace/<int:wks_id>/Projects', methods=['GET', 'POST'])
@login_required({'admin', 'manager'})
def workspace_homepage(wks_id, **kwargs):
    return render_template('authenticated/html/workspace_homepage.html',
                           user_data=kwargs['user'],
                           wks_data=kwargs['user'].get_wks_data(),
                           SIDEBAR=SIDEBAR)


@authenticated.route('/Workspace/<int:wks_id>/Users', methods=['GET', 'POST'])
@login_required('admin')
def users_page(wks_id, **kwargs):
    new_user = NewUser()
    if request.method == "POST" and new_user.validate_on_submit():
        if add_user(kwargs['user'].wks_key, kwargs['user'].get_wks_data().workspace_name, new_user.user_email.data,
                    new_user.role.data):
            return redirect(url_for('authenticated.users_page', wks_id=wks_id))

    return render_template('authenticated/html/users_page.html',
                           form=new_user,
                           user_data=kwargs['user'],
                           wks_data=kwargs['user'].get_wks_data(),
                           SIDEBAR=SIDEBAR)


@authenticated.route('/Invitation', methods=['GET', 'POST'])
@login_required()
def open_invitation(**kwargs):
    code = request.args.get('code')
    email = request.args.get('email')
    if not email or not code:
        return redirect(url_for('authenticated.my_workspaces_page'))

    if not verify_invite(code, email):
        return redirect(url_for('authenticated.my_workspaces_page'))

    if request.method == "POST":
        if request.form['accepted']:
            verify_invite(code, email).invitation_accepted = True
            verify_invite(code, email).put()
            time.sleep(1)
            flash('Invitation accepted! You can access your new workspace now!', 'success')
            return redirect(url_for('authenticated.my_workspaces_page'))

    return render_template('authenticated/html/open_invitation.html',
                           user_data=kwargs['user'],
                           wks_data=verify_invite(code, email)
                           )


@authenticated.route('/Logout')
@login_required()
def logout(**kwargs):
    session.clear()
    gc.collect()
    flash("Successfully Logged Out!", "success")
    return redirect(url_for('unauthenticated.login_page'))


@authenticated.route('/debug', methods=['GET', 'POST'])
@login_required()
def debug(**kwargs):
    return render_template('authenticated/html/includes/Blank.html')
