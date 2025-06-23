from flask import Flask, render_template, request, redirect, url_for, flash
from flask_migrate import Migrate
import os
from sqlalchemy import func
import bleach
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from werkzeug.security import check_password_hash
from dotenv import load_dotenv
import pymysql
import logging

from models import db, Dish, Account, Photo, Feedback, UserRole
from forms import DishForm, FeedbackForm, AuthForm
from markupsafe import Markup
import markdown

pymysql.install_as_MySQLdb()

load_dotenv()

app = Flask(__name__)
app.config['SECRET_KEY'] = os.getenv('FLASK_SECRET_KEY')
app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv('DATABASE_URL')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = os.getenv('SQLALCHEMY_TRACK_MODIFICATIONS', 'False').lower() == 'true'
app.config['UPLOAD_FOLDER'] = os.getenv('UPLOAD_FOLDER')

required_env_vars = ['FLASK_SECRET_KEY', 'DATABASE_URL', 'UPLOAD_FOLDER']
missing_vars = [var for var in required_env_vars if not os.getenv(var)]
if missing_vars:
    raise RuntimeError(f'Отсутствуют обязательные переменные окружения: {", ".join(missing_vars)}')

db.init_app(app)
migrate = Migrate(app, db)

os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

# Настройка логирования
logging.basicConfig(filename='app.log', level=logging.ERROR, format='%(asctime)s %(levelname)s %(message)s')

login_manager = LoginManager(app)
login_manager.login_view = 'login_view'
login_manager.login_message = 'Для выполнения данного действия необходимо пройти процедуру аутентификации'
login_manager.login_message_category = 'warning'

@login_manager.user_loader
def load_account(account_id):
    return db.session.get(Account, int(account_id))

def save_photos(photo_files, dish_id):
    """Сохраняет фотографии блюда и добавляет записи в БД."""
    for photo in photo_files:
        if photo.filename:
            filename = photo.filename
            mime_type = photo.mimetype
            path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            photo.save(path)
            photo_obj = Photo(filename=filename, mime_type=mime_type, dish_id=dish_id)
            db.session.add(photo_obj)
    db.session.commit()

def is_dish_name_unique(name):
    return not Dish.query.filter_by(name=name).first()

@app.route('/')
@login_required
def home():
    page = request.args.get('page', 1, type=int)
    per_page = 10
    dishes_query = (
        db.session.query(
            Dish,
            func.coalesce(func.avg(Feedback.score), 0).label('avg_score'),
            func.count(Feedback.id).label('feedbacks_count')
        )
        .outerjoin(Feedback, Feedback.dish_id == Dish.id)
        .group_by(Dish.id)
        .order_by(Dish.created_at.desc())
    )
    pagination = dishes_query.paginate(page=page, per_page=per_page, error_out=False)
    dishes = pagination.items
    return render_template('index.html', recipes=dishes, pagination=pagination)

@app.route('/create-dish', methods=['GET', 'POST'])
@login_required
def create_dish():
    form = DishForm()
    if form.validate_on_submit():
        if not is_dish_name_unique(form.name.data):
            flash('Блюдо с таким названием уже существует.', 'danger')
            return render_template('add_recipe.html', form=form)
        details = bleach.clean(form.details.data)
        components = bleach.clean(form.components.data)
        instructions = bleach.clean(form.instructions.data)
        dish = Dish(
            name=form.name.data,
            details=details,
            cook_time=form.cook_time.data,
            portions=form.portions.data,
            components=components,
            instructions=instructions,
            account_id=current_user.id
        )
        try:
            db.session.add(dish)
            db.session.commit()
            if form.photos.data:
                save_photos(form.photos.data, dish.id)
            flash('Блюдо успешно добавлено!', 'success')
            return redirect(url_for('home'))
        except Exception as e:
            db.session.rollback()
            logging.error(f'Ошибка при добавлении блюда: {e}')
            flash('Ошибка при сохранении блюда. Проверьте корректность данных.', 'danger')
            return render_template('add_recipe.html', form=form)
    return render_template('add_recipe.html', form=form)

@app.route('/edit-dish/<int:id>', methods=['GET', 'POST'])
@login_required
def edit_dish(id):
    dish = Dish.query.get_or_404(id)
    is_admin = current_user.role and current_user.role.name == 'Администратор'
    if dish.account_id != current_user.id and not is_admin:
        flash('У вас недостаточно прав для редактирования этого блюда', 'danger')
        return redirect(url_for('home'))
    form = DishForm(obj=dish)
    if form.validate_on_submit():
        dish.name = form.name.data
        dish.details = form.details.data
        dish.cook_time = form.cook_time.data
        dish.portions = form.portions.data
        dish.components = form.components.data
        dish.instructions = form.instructions.data
        try:
            db.session.commit()
            flash('Блюдо успешно обновлено!', 'success')
            return redirect(url_for('home'))
        except Exception as e:
            db.session.rollback()
            logging.error(f'Ошибка при обновлении блюда: {e}')
            flash('Ошибка при обновлении блюда.', 'danger')
    return render_template('edit_recipe.html', form=form, recipe=dish)

@app.route('/dish/<int:id>')
@login_required
def view_dish(id):
    dish = Dish.query.get_or_404(id)
    photos = Photo.query.filter_by(dish_id=dish.id).all()
    feedbacks = Feedback.query.filter_by(dish_id=dish.id).all()
    details_html = Markup(markdown.markdown(dish.details, extensions=['extra']))
    components_html = Markup(markdown.markdown(dish.components, extensions=['extra']))
    instructions_html = Markup(markdown.markdown(dish.instructions, extensions=['extra']))
    return render_template(
        'view_recipe.html',
        recipe=dish,
        images=photos,
        description_html=details_html,
        ingredients_html=components_html,
        steps_html=instructions_html,
        reviews=feedbacks
    )

@app.route('/delete-dish/<int:id>', methods=['POST'])
@login_required
def delete_dish(id):
    dish = Dish.query.get_or_404(id)
    try:
        for photo in dish.photos:
            photo_path = os.path.join(app.config['UPLOAD_FOLDER'], photo.filename)
            if os.path.exists(photo_path):
                os.remove(photo_path)
        db.session.delete(dish)
        db.session.commit()
        flash('Блюдо успешно удалено!', 'success')
    except Exception as e:
        db.session.rollback()
        logging.error(f'Ошибка при удалении блюда: {e}')
        flash('Ошибка при удалении блюда.', 'danger')
    return redirect(url_for('home'))

@app.route('/dish/<int:dish_id>/add-feedback', methods=['GET', 'POST'])
@login_required
def add_feedback(dish_id):
    dish = Dish.query.get_or_404(dish_id)
    form = FeedbackForm()
    user_id = current_user.id
    existing_feedback = Feedback.query.filter_by(dish_id=dish_id, account_id=user_id).first()
    if existing_feedback:
        flash('Вы уже оставляли отзыв на это блюдо.', 'warning')
        return redirect(url_for('view_dish', id=dish_id))
    if form.validate_on_submit():
        comment = bleach.clean(form.comment.data)
        feedback = Feedback(
            dish_id=dish_id,
            account_id=user_id,
            score=form.score.data,
            comment=comment
        )
        try:
            db.session.add(feedback)
            db.session.commit()
            flash('Отзыв успешно добавлен!', 'success')
            return redirect(url_for('view_dish', id=dish_id))
        except Exception as e:
            db.session.rollback()
            logging.error(f'Ошибка при добавлении отзыва: {e}')
            flash('Ошибка при сохранении отзыва.', 'danger')
    return render_template('add_review.html', form=form, recipe=dish)

@app.template_filter('markdown')
def markdown_filter(text):
    return Markup(markdown.markdown(text, extensions=['extra']))

@app.route('/login', methods=['GET', 'POST'])
def login_view():
    form = AuthForm()
    error = None
    if form.validate_on_submit():
        account = Account.query.filter_by(login=form.login.data).first()
        if account and check_password_hash(account.password_hash, form.password.data):
            login_user(account, remember=form.remember_me.data)
            return redirect(url_for('home'))
        else:
            error = 'Невозможно аутентифицироваться с указанными логином и паролем'
    return render_template('login.html', form=form, error=error)

@app.route('/logout')
@login_required
def logout_view():
    logout_user()
    flash('Вы вышли из аккаунта.', 'success')
    return redirect(url_for('login_view'))

if __name__ == '__main__':
    port = int(os.getenv('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=os.getenv('FLASK_DEBUG', 'False').lower() == 'true') 


