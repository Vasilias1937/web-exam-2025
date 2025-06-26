from flask import Flask, render_template, request, redirect, url_for, flash
from flask_migrate import Migrate
import os
from sqlalchemy import func
import bleach
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from werkzeug.security import check_password_hash, generate_password_hash
from dotenv import load_dotenv
import pymysql
import logging

from models import db, Dish, Account, Photo, Feedback, UserRole
from forms import DishForm, FeedbackForm, AuthForm, RegisterForm
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

def save_photos(photo_files, recipe_id):
    """Сохраняет фотографии блюда и добавляет записи в БД."""
    for photo in photo_files:
        if photo.filename:
            filename = photo.filename
            mime_type = photo.mimetype
            path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            photo.save(path)
            photo_obj = Photo(filename=filename, mime_type=mime_type, recipe_id=recipe_id)
            db.session.add(photo_obj)
    db.session.commit()

def is_dish_name_unique(name):
    return not Dish.query.filter_by(title=name).first()

def can_edit_or_delete_recipe(dish, user):
    is_admin = user.role and user.role.name == 'Администратор'
    return is_admin or dish.user_id == user.id

@app.route('/')
@login_required
def home():
    page = request.args.get('page', 1, type=int)
    per_page = 10
    dishes_query = (
        db.session.query(
            Dish,
            func.coalesce(func.avg(Feedback.rating), 0).label('avg_score'),
            func.count(Feedback.id).label('feedbacks_count')
        )
        .outerjoin(Feedback, Feedback.recipe_id == Dish.id)
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
        if not is_dish_name_unique(form.title.data):
            flash('Блюдо с таким названием уже существует.', 'danger')
            return render_template('add_recipe.html', form=form)
        description = bleach.clean(form.description.data)
        ingredients = bleach.clean(form.ingredients.data)
        steps = bleach.clean(form.steps.data)
        dish = Dish(
            title=form.title.data,
            description=description,
            cooking_time=form.cooking_time.data,
            servings=form.servings.data,
            ingredients=ingredients,
            steps=steps,
            user_id=current_user.id
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
    if not can_edit_or_delete_recipe(dish, current_user):
        flash('У вас недостаточно прав для редактирования этого блюда', 'danger')
        return redirect(url_for('home'))
    form = DishForm(obj=dish)
    if form.validate_on_submit():
        dish.title = form.title.data
        dish.description = form.description.data
        dish.cooking_time = form.cooking_time.data
        dish.servings = form.servings.data
        dish.ingredients = form.ingredients.data
        dish.steps = form.steps.data
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
    photos = Photo.query.filter_by(recipe_id=dish.id).all()
    feedbacks = Feedback.query.filter_by(recipe_id=dish.id).all()
    details_html = Markup(markdown.markdown(dish.description, extensions=['extra']))
    components_html = Markup(markdown.markdown(dish.ingredients, extensions=['extra']))
    instructions_html = Markup(markdown.markdown(dish.steps, extensions=['extra']))
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
    if not can_edit_or_delete_recipe(dish, current_user):
        flash('У вас недостаточно прав для удаления этого блюда', 'danger')
        return redirect(url_for('home'))
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
    existing_feedback = Feedback.query.filter_by(recipe_id=dish_id, user_id=user_id).first()
    if existing_feedback:
        flash('Вы уже оставляли отзыв на это блюдо.', 'warning')
        return redirect(url_for('view_dish', id=dish_id))
    if form.validate_on_submit():
        text = bleach.clean(form.comment.data)
        feedback = Feedback(
            recipe_id=dish_id,
            user_id=user_id,
            rating=form.rating.data,
            text=text
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
        account = Account.query.filter_by(username=form.username.data).first()
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

@app.route('/register', methods=['GET', 'POST'])
def register():
    form = RegisterForm()
    # Подгружаем роли для выбора
    form.role_id.choices = [(role.id, role.name) for role in UserRole.query.all()]
    error = None
    if form.validate_on_submit():
        if Account.query.filter_by(username=form.username.data).first():
            error = 'Пользователь с таким логином уже существует.'
        else:
            new_user = Account(
                username=form.username.data,
                password_hash=generate_password_hash(form.password.data),
                last_name=form.last_name.data,
                first_name=form.first_name.data,
                middle_name=form.middle_name.data,
                role_id=form.role_id.data
            )
            try:
                db.session.add(new_user)
                db.session.commit()
                flash('Регистрация успешна! Теперь вы можете войти.', 'success')
                return redirect(url_for('login_view'))
            except Exception as e:
                db.session.rollback()
                error = 'Ошибка при регистрации пользователя.'
    return render_template('register.html', form=form, error=error)

if __name__ == '__main__':
    port = int(os.getenv('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=os.getenv('FLASK_DEBUG', 'False').lower() == 'true') 


